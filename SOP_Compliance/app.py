"""
SOP Compliance System — Main Application Entry Point

Initializes camera, YOLO detector, gauge validator, and FastAPI server.
Runs the inference loop in a background thread and serves the web dashboard.
"""

import asyncio
import json
import logging
import os
import threading
import time
from contextlib import asynccontextmanager
from typing import Optional, Set

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

    # Initialize YOLO detector — run in a thread so the heavy model load
    # does NOT block the asyncio event loop (which causes CancelledError).
    def _build_detector():
        return YOLODetector(
            model_path=config.MODEL_PATH,
            confidence_threshold=config.CONFIDENCE_THRESHOLD,
            iou_threshold=config.IOU_THRESHOLD,
            imgsz=config.IMGSZ,
            device=config.DEVICE,
            engine_path=config.MODEL_ENGINE_PATH,
        )

    detector = await asyncio.to_thread(_build_detector)

    if detector.is_available:
        logger.info("YOLO model loaded successfully.")
    else:
        logger.warning("YOLO model not available — running in DEMO mode.")

    # Initialize gauge validator
    validator = GaugeValidator(
        checkpoints=config.GAUGE_CHECKPOINTS,
        overlap_threshold=config.OVERLAP_THRESHOLD,
        near_distance_threshold=config.NEAR_DISTANCE_THRESHOLD,
        ok_hold_frames=config.OK_HOLD_FRAMES,
        ok_hold_seconds=config.OK_HOLD_SECONDS,
        gauge_grace_frames=config.GAUGE_GRACE_FRAMES,
        part_absent_patience=config.PART_ABSENT_PATIENCE,
    )

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

            # Draw annotations on frame
            annotated = frame
            if detector and detections:
                annotated = detector.draw_detections(
                    frame, detections,
                    gauge_classes=gauge_class_names,
                    part_classes=part_class_names,
                    show_conf=show_confidence_score,
                )

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
                if status.get("glove_warning"):
                    logger.warning(f"[BROADCAST] glove_warning=True being sent to frontend!")
                with status_lock:
                    latest_status = status

            # No sleep — run as fast as GPU allows

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


class ConfidenceToggle(BaseModel):
    show: bool

@app.post("/settings/confidence")
async def toggle_confidence(body: ConfidenceToggle):
    """Toggle the display of confidence scores on the video feed."""
    global show_confidence_score
    show_confidence_score = body.show
    logger.info(f"Show confidence score: {show_confidence_score}")
    return JSONResponse({"status": "ok", "show_confidence_score": show_confidence_score})


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
