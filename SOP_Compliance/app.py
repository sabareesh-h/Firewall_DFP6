"""
SOP Compliance System — Main Application Entry Point

Initializes camera, YOLO detector, gauge validator, and FastAPI server.
Runs the inference loop in a background thread and serves the web dashboard.
"""

import asyncio
import json
import logging
import os
os.environ["YOLO_OFFLINE"] = "True"
os.environ["YOLOV8_NO_TELEMETRY"] = "1"
os.environ["YOLO_VERBOSE"] = "False"

import threading
import time
from contextlib import asynccontextmanager
from typing import Optional, Set, List

import cv2
import numpy as np
import uvicorn
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse, StreamingResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

import config
from camera import Camera
from detection import YOLODetector
from logic import GaugeValidator

# ─── Logging ──────────────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-7s | %(name)s | %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("sop_app")

# ─── Global Components ────────────────────────────────────────────────────────
camera: Optional[Camera] = None
detector: Optional[YOLODetector] = None
validator: Optional[GaugeValidator] = None

# Inference state
latest_detections = []
latest_annotated_frame: Optional[np.ndarray] = None
latest_status: Optional[dict] = None
frame_lock = threading.Lock()
status_lock = threading.Lock()
inference_running = False

# ── Pre-encoded MJPEG cache ──────────────────────────────────────────────────────
# The inference thread encodes the annotated frame to JPEG right after
# drawing, so the async MJPEG generator can yield bytes without blocking
# the event loop with expensive cv2.imencode / cv2.resize calls.
_mjpeg_jpeg_bytes: Optional[bytes] = None
_mjpeg_frame_id: int = 0          # monotonic counter — lets clients skip duplicates
_mjpeg_lock = threading.Lock()

# WebSocket clients — status updates (JSON)
ws_clients: Set[WebSocket] = set()
ws_clients_lock = threading.Lock()

# Class name sets for drawing
gauge_class_names = set(config.GAUGE_CLASSES.values())
part_class_names = set(config.PART_CLASSES.values())

# Current source mode
current_source = config.DEFAULT_SOURCE

# UI Settings
show_confidence_score = False
enable_pacing = True

SETTINGS_FILE = os.path.join(config.BASE_DIR, "settings.json")

def load_settings():
    if os.path.exists(SETTINGS_FILE):
        try:
            with open(SETTINGS_FILE, "r") as f:
                return json.load(f)
        except Exception as e:
            logger.error(f"Failed to load settings.json: {e}")
    return {}

def save_settings(data):
    try:
        with open(SETTINGS_FILE, "w") as f:
            json.dump(data, f, indent=4)
    except Exception as e:
        logger.error(f"Failed to save settings.json: {e}")


# ─── Pydantic Models ─────────────────────────────────────────────────────────
class SourceSwitch(BaseModel):
    mode: str                  # "live" | "video" | "demo"
    source: Optional[str] = None  # video file path (optional)


# ─── Lifespan ─────────────────────────────────────────────────────────────────
@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup and shutdown logic using modern lifespan pattern."""
    global camera, detector, validator, inference_running

    logger.info("=" * 60)
    logger.info("  SOP Compliance System — Starting Up")
    logger.info("=" * 60)

    saved_settings = load_settings()
    detector_conf = saved_settings.get("confidence_threshold", config.CONFIDENCE_THRESHOLD)
    validator_overlap = saved_settings.get("overlap_threshold", config.OVERLAP_THRESHOLD)
    validator_near = saved_settings.get("near_distance_threshold", config.NEAR_DISTANCE_THRESHOLD)
    validator_hold = saved_settings.get("ok_hold_seconds", config.OK_HOLD_SECONDS)
    visual_deadzone = saved_settings.get("visual_deadzone", None)

    # Initialize YOLO detector — run in a thread so the heavy model load
    # does NOT block the asyncio event loop (which causes CancelledError).
    def _build_detector():
        d = YOLODetector(
            model_path=config.MODEL_PATH,
            confidence_threshold=detector_conf,
            iou_threshold=config.IOU_THRESHOLD,
            imgsz=config.IMGSZ,
            device=config.DEVICE,
            engine_path=config.MODEL_ENGINE_PATH,
        )
        d.deadzone = visual_deadzone
        return d

    detector = await asyncio.to_thread(_build_detector)

    if detector.is_available:
        logger.info("YOLO model loaded successfully.")
    else:
        logger.warning("YOLO model not available — running in DEMO mode.")

    # Initialize gauge validator
    validator = GaugeValidator(
        checkpoints=config.GAUGE_CHECKPOINTS,
        overlap_threshold=validator_overlap,
        near_distance_threshold=validator_near,
        ok_hold_frames=config.OK_HOLD_FRAMES,
        ok_hold_seconds=validator_hold,
        gauge_grace_frames=config.GAUGE_GRACE_FRAMES,
        part_clear_time_complete=config.PART_CLEAR_TIME_COMPLETE,
        part_clear_time_inspecting=config.PART_CLEAR_TIME_INSPECTING,
    )
    
    if "gauge_configs" in saved_settings and saved_settings["gauge_configs"]:
        for g_conf in saved_settings["gauge_configs"]:
            cp_id = g_conf.get("id")
            if cp_id in validator._checkpoint_configs:
                validator._checkpoint_configs[cp_id]["method"] = g_conf.get("method", "near")
                if "overlap_threshold" in g_conf:
                    validator._checkpoint_configs[cp_id]["overlap_threshold"] = g_conf["overlap_threshold"]
                if "near_distance_threshold" in g_conf:
                    validator._checkpoint_configs[cp_id]["near_distance_threshold"] = g_conf["near_distance_threshold"]

    # Initialize camera
    camera = Camera(
        mode=config.DEFAULT_SOURCE,
        source=config.DEFAULT_VIDEO_PATH if config.DEFAULT_SOURCE == "video" else None,
        camera_index=config.CAMERA_INDEX,
    )
    camera.start()

    # Start inference loop in background thread
    inference_running = True
    threading.Thread(target=inference_loop, daemon=True).start()
    logger.info("Inference loop started.")

    # Start WebSocket broadcast task
    broadcast_task = asyncio.create_task(ws_broadcast_loop())

    yield  # App is running

    # Shutdown
    inference_running = False
    broadcast_task.cancel()
    if camera:
        camera.stop()
    logger.info("SOP Compliance System shut down.")


# ─── FastAPI App ──────────────────────────────────────────────────────────────
app = FastAPI(
    title="SOP Compliance System",
    version=config.APP_VERSION,
    lifespan=lifespan,
)


# ─── JPEG Encoding Helper (called from inference thread) ─────────────────
def _encode_mjpeg_frame(frame: np.ndarray) -> None:
    """
    Resize + JPEG-encode the annotated frame and store the result in a
    shared buffer.  Called from the inference thread so the async MJPEG
    generator never has to touch cv2.imencode (which would block the
    event loop and tank the stream FPS).
    """
    global _mjpeg_jpeg_bytes, _mjpeg_frame_id

    display_w = 960
    h, w = frame.shape[:2]
    if w > display_w:
        scale = display_w / w
        frame = cv2.resize(
            frame,
            (display_w, int(h * scale)),
            interpolation=cv2.INTER_LINEAR,
        )

    _, buffer = cv2.imencode(
        ".jpg", frame,
        [cv2.IMWRITE_JPEG_QUALITY, 80],
    )

    with _mjpeg_lock:
        _mjpeg_jpeg_bytes = buffer.tobytes()
        _mjpeg_frame_id += 1


# ─── Inference Loop (Background Thread) ──────────────────────────────────────
def inference_loop():
    """
    Background thread: Camera → YOLO → Validator → Annotated Frame.
    Runs independently from web server requests.
    """
    global latest_detections, latest_annotated_frame, latest_status

    # FPS tracking
    _fps_frame_count = 0
    _fps_last_time   = time.time()
    _live_fps        = 0.0

    while inference_running:
        loop_start_time = time.time()
        try:
            if camera is None:
                time.sleep(0.1)
                continue

            frame = camera.get_frame()
            if frame is None:
                time.sleep(0.05)
                continue

            # Run YOLO detection
            detections = []
            if detector and detector.is_available:
                detections = detector.detect(frame)

            # Run SOP validation
            if validator:
                status_from_validate = validator.validate(detections)

            # Draw annotations on frame (Disabled OpenCV drawing, handled in frontend)
            annotated = frame

            # Store results (thread-safe)
            with frame_lock:
                latest_detections = detections
                latest_annotated_frame = annotated

            # Pre-encode JPEG for the MJPEG stream (runs in this thread,
            # keeps the async generator non-blocking)
            _encode_mjpeg_frame(annotated)

            # Track inference FPS
            _fps_frame_count += 1
            now = time.time()
            elapsed = now - _fps_last_time
            if elapsed >= 2.0:
                _live_fps = round(_fps_frame_count / elapsed, 1)
                _fps_frame_count = 0
                _fps_last_time   = now

            # Build and store status for WebSocket broadcast
            if validator:
                status = status_from_validate if status_from_validate else validator.get_status()
                status["source"] = current_source
                status["detector_available"] = detector.is_available if detector else False
                status["camera_connected"] = camera.is_connected if camera else False
                status["inference_fps"] = _live_fps
                status["raw_detections"] = detections
                status["frame_width"] = frame.shape[1] if frame is not None else 1280
                status["frame_height"] = frame.shape[0] if frame is not None else 720
                status["show_confidence_score"] = show_confidence_score
                if status.get("glove_warning"):
                    logger.warning(f"[BROADCAST] glove_warning=True being sent to frontend!")
                with status_lock:
                    latest_status = status

            if enable_pacing:
                state = "IDLE"
                if validator and 'status' in locals() and status:
                    state = status.get("inspection_state", "IDLE")

                if state in ("IDLE", "COMPLETE"):
                    idle_fps = 5.0
                    elapsed_loop_time = time.time() - loop_start_time
                    sleep_time = (1.0 / idle_fps) - elapsed_loop_time
                    if sleep_time > 0:
                        time.sleep(sleep_time)
                # If state is INSPECTING, it bypasses sleep and runs at full speed.

        except Exception as e:
            logger.error(f"Inference loop error: {e}")
            time.sleep(0.5)


# ─── WebSocket Broadcast (Async Task) ────────────────────────────────────────
async def ws_broadcast_loop():
    """
    Async task that periodically reads the latest status from the
    inference thread and pushes it to all connected WebSocket clients.
    Runs inside FastAPI's event loop — no cross-thread async issues.
    """
    while True:
        try:
            await asyncio.sleep(0.1)  # ~10 Hz broadcast rate

            with status_lock:
                status = latest_status

            if status is None:
                continue

            with ws_clients_lock:
                clients = ws_clients.copy()

            if not clients:
                continue

            message = json.dumps(status)
            disconnected = []
            for ws in clients:
                try:
                    await ws.send_text(message)
                except Exception:
                    disconnected.append(ws)

            if disconnected:
                with ws_clients_lock:
                    for ws in disconnected:
                        ws_clients.discard(ws)

        except asyncio.CancelledError:
            break
        except Exception as e:
            logger.error(f"WS broadcast error: {e}")
            await asyncio.sleep(1.0)



# ─── Video Stream (MJPEG fallback) ─────────────────────────────────────────
async def generate_mjpeg():
    """
    MJPEG fallback for browsers that don't support WebSocket video.
    Primary video delivery is now via /ws/video WebSocket.
    """
    _last_served_id = -1

    try:
        while True:
            with _mjpeg_lock:
                jpeg = _mjpeg_jpeg_bytes
                fid  = _mjpeg_frame_id

            if jpeg is None or fid == _last_served_id:
                await asyncio.sleep(0.005)
                continue

            _last_served_id = fid

            yield (
                b"--frame\r\n"
                b"Content-Type: image/jpeg\r\n\r\n"
                + jpeg
                + b"\r\n"
            )

            await asyncio.sleep(1.0 / 20)

    except (asyncio.CancelledError, GeneratorExit):
        pass


# ─── API Routes ──────────────────────────────────────────────────────────────

@app.get("/", response_class=HTMLResponse)
async def root():
    """Serve the main dashboard."""
    index_path = os.path.join(config.FRONTEND_DIR, "index.html")
    with open(index_path, "r", encoding="utf-8") as f:
        return HTMLResponse(content=f.read())


@app.get("/video")
async def video_feed():
    """MJPEG live video stream. Handles client disconnect cleanly."""
    return StreamingResponse(
        generate_mjpeg(),
        media_type="multipart/x-mixed-replace; boundary=frame",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@app.get("/status")
async def get_status():
    """Return current inspection status as JSON."""
    if validator is None:
        return JSONResponse({"error": "System not initialized"}, status_code=503)

    status = validator.get_status()
    status["source"] = current_source
    status["detector_available"] = detector.is_available if detector else False
    status["camera_connected"] = camera.is_connected if camera else False
    return JSONResponse(status)


@app.post("/reset")
async def reset_inspection():
    """Reset all gauge checkpoint states."""
    if validator is None:
        return JSONResponse({"error": "System not initialized"}, status_code=503)

    status = validator.reset()
    logger.info("Inspection reset by user.")
    return JSONResponse(status)


@app.post("/source")
async def switch_source(body: SourceSwitch):
    """Switch between live camera, prerecorded video, or demo mode."""
    global current_source

    mode = body.mode
    source = body.source

    if mode not in ("live", "video", "demo"):
        return JSONResponse(
            {"error": f"Invalid mode: {mode}. Use 'live', 'video', or 'demo'."},
            status_code=400,
        )

    if mode == "video" and not source:
        source = config.DEFAULT_VIDEO_PATH
    elif mode == "live" and config.LIVE_CAMERA_URL:
        source = config.LIVE_CAMERA_URL

    if camera:
        camera.switch_source(mode, source)

    current_source = mode
    logger.info(f"Source switched to: {mode} (source={source})")

    return JSONResponse({"status": "ok", "mode": mode, "source": source})


@app.post("/reset_counter")
async def reset_counter():
    """Reset production counters."""
    if validator:
        validator.total_count = 0
        validator.pass_count = 0
        validator.fail_count = 0
        validator.recent_logs = []
    return JSONResponse({"status": "ok"})


class PartNoUpdate(BaseModel):
    part_no: str

@app.post("/set_part_no")
async def set_part_no(body: PartNoUpdate):
    """Set the part number from the barcode scanner."""
    if validator:
        validator.set_part_no(body.part_no)
    return JSONResponse({"status": "ok"})


class ConfidenceToggle(BaseModel):
    show: bool

@app.post("/settings/confidence")
async def toggle_confidence(body: ConfidenceToggle):
    """Toggle the display of confidence scores on the video feed."""
    global show_confidence_score
    show_confidence_score = body.show
    logger.info(f"Show confidence score: {show_confidence_score}")
    return JSONResponse({"status": "ok", "show_confidence_score": show_confidence_score})

class PacingToggle(BaseModel):
    enable: bool

@app.post("/settings/pacing")
async def toggle_pacing(body: PacingToggle):
    """Toggle the inference frame pacing."""
    global enable_pacing
    enable_pacing = body.enable
    logger.info(f"Enable pacing: {enable_pacing}")
    return JSONResponse({"status": "ok", "enable_pacing": enable_pacing})

class GaugeConfigUpdate(BaseModel):
    id: int
    method: str
    overlap_threshold: float
    near_distance_threshold: int

class SettingsUpdate(BaseModel):
    confidence_threshold: float
    overlap_threshold: float
    near_distance_threshold: int
    ok_hold_seconds: float
    gauge_configs: Optional[List[GaugeConfigUpdate]] = None
    visual_deadzone: Optional[List[int]] = None

@app.get("/settings")
async def get_settings_endpoint():
    """Get the current dynamic AI thresholds."""
    gauge_configs = []
    if validator:
        for cp_id, cp_conf in validator._checkpoint_configs.items():
            gauge_configs.append({
                "id": cp_id,
                "name": cp_conf["name"],
                "method": cp_conf.get("method", "near"),
                "overlap_threshold": cp_conf.get("overlap_threshold", validator.overlap_threshold),
                "near_distance_threshold": cp_conf.get("near_distance_threshold", validator.near_distance_threshold),
            })
            
    return JSONResponse({
        "confidence_threshold": detector.confidence_threshold if detector else config.CONFIDENCE_THRESHOLD,
        "overlap_threshold": validator.overlap_threshold if validator else config.OVERLAP_THRESHOLD,
        "near_distance_threshold": validator.near_distance_threshold if validator else config.NEAR_DISTANCE_THRESHOLD,
        "ok_hold_seconds": validator.ok_hold_seconds if validator else config.OK_HOLD_SECONDS,
        "gauge_configs": gauge_configs,
        "visual_deadzone": detector.deadzone if detector else None
    })

@app.post("/settings")
async def update_settings_endpoint(settings: SettingsUpdate):
    """Update dynamic AI thresholds in memory and save to file."""
    if detector:
        detector.confidence_threshold = settings.confidence_threshold
        detector.deadzone = settings.visual_deadzone
    if validator:
        validator.overlap_threshold = settings.overlap_threshold
        validator.near_distance_threshold = settings.near_distance_threshold
        validator.ok_hold_seconds = settings.ok_hold_seconds
        
        if settings.gauge_configs:
            for g_conf in settings.gauge_configs:
                if g_conf.id in validator._checkpoint_configs:
                    validator._checkpoint_configs[g_conf.id]["method"] = g_conf.method
                    validator._checkpoint_configs[g_conf.id]["overlap_threshold"] = g_conf.overlap_threshold
                    validator._checkpoint_configs[g_conf.id]["near_distance_threshold"] = g_conf.near_distance_threshold
        
    save_settings({
        "confidence_threshold": settings.confidence_threshold,
        "overlap_threshold": settings.overlap_threshold,
        "near_distance_threshold": settings.near_distance_threshold,
        "ok_hold_seconds": settings.ok_hold_seconds,
        "gauge_configs": [g.dict() for g in settings.gauge_configs] if settings.gauge_configs else [],
        "visual_deadzone": settings.visual_deadzone
    })
    
    logger.info(f"Settings updated: {settings.dict()}")
    return JSONResponse({"status": "ok"})


@app.post("/settings/reset")
async def reset_settings_endpoint():
    """Reset settings to default."""
    if os.path.exists(SETTINGS_FILE):
        try:
            os.remove(SETTINGS_FILE)
        except Exception as e:
            logger.error(f"Failed to delete settings.json: {e}")
            
    # Reset in-memory values
    if detector:
        detector.confidence_threshold = config.CONFIDENCE_THRESHOLD
        detector.deadzone = None
    if validator:
        validator.overlap_threshold = config.OVERLAP_THRESHOLD
        validator.near_distance_threshold = config.NEAR_DISTANCE_THRESHOLD
        validator.ok_hold_seconds = config.OK_HOLD_SECONDS
        
        # Reset gauge configs from config.GAUGE_CHECKPOINTS
        for cp in config.GAUGE_CHECKPOINTS:
            cp_id = cp["id"]
            if cp_id in validator._checkpoint_configs:
                validator._checkpoint_configs[cp_id]["method"] = cp.get("method", "near")
                if "overlap_threshold" in validator._checkpoint_configs[cp_id]:
                    del validator._checkpoint_configs[cp_id]["overlap_threshold"]
                if "near_distance_threshold" in validator._checkpoint_configs[cp_id]:
                    del validator._checkpoint_configs[cp_id]["near_distance_threshold"]
                
    return JSONResponse({"status": "ok"})


# ─── WebSocket — Status Updates ───────────────────────────────────────────────
@app.websocket("/ws")
async def websocket_endpoint(ws: WebSocket):
    await ws.accept()
    with ws_clients_lock:
        ws_clients.add(ws)
    logger.info(f"WebSocket client connected. Total: {len(ws_clients)}")

    try:
        while True:
            # Keep connection alive — listen for any incoming messages
            data = await ws.receive_text()
            # Client can send "ping" to keep alive
            if data == "ping":
                await ws.send_text("pong")
    except WebSocketDisconnect:
        with ws_clients_lock:
            ws_clients.discard(ws)
        logger.info(f"WebSocket client disconnected. Total: {len(ws_clients)}")
    except Exception:
        with ws_clients_lock:
            ws_clients.discard(ws)


# ─── WebSocket — Video Frames ─────────────────────────────────────────────────
@app.websocket("/ws/video")
async def websocket_video_endpoint(ws: WebSocket):
    """
    Per-client video push loop.

    A dedicated asyncio task (_push_frames) sends new JPEG frames while
    the main coroutine blocks on receive_text() for disconnect detection.
    This avoids the concurrent send/receive conflict in FastAPI WebSockets.
    """
    await ws.accept()
    logger.info("Video WS client connected")

    last_fid = -1
    try:
        while True:
            with _mjpeg_lock:
                jpeg = _mjpeg_jpeg_bytes
                fid  = _mjpeg_frame_id

            if jpeg is not None and fid != last_fid:
                last_fid = fid
                await ws.send_bytes(jpeg)
                await asyncio.sleep(1.0 / 20)   # pace to ~20 FPS
            else:
                await asyncio.sleep(0.005)       # poll for next frame

    except Exception:
        pass  # client disconnected — normal
    finally:
        logger.info("Video WS client disconnected")


# ─── Static Files ─────────────────────────────────────────────────────────────
app.mount("/static", StaticFiles(directory=config.FRONTEND_DIR), name="static")
app.mount("/reference_images", StaticFiles(directory=os.path.join(config.BASE_DIR, "Reference_gauge_images")), name="reference_images")


# ─── Entry Point ──────────────────────────────────────────────────────────────
if __name__ == "__main__":
    try:
        uvicorn.run(
            "app:app",
            host=config.HOST,
            port=config.PORT,
            reload=False,
            log_level="info",
        )
    except KeyboardInterrupt:
        logger.info("Stopped by operator (Ctrl+C). Goodbye.")
