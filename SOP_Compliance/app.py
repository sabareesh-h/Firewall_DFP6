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

# WebSocket clients
ws_clients: Set[WebSocket] = set()
ws_clients_lock = threading.Lock()

# Class name sets for drawing
gauge_class_names = set(config.GAUGE_CLASSES.values())
part_class_names = set(config.PART_CLASSES.values())

# Current source mode
current_source = config.DEFAULT_SOURCE


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

    # Initialize YOLO detector
    detector = YOLODetector(
        model_path=config.MODEL_PATH,
        confidence_threshold=config.CONFIDENCE_THRESHOLD,
        iou_threshold=config.IOU_THRESHOLD,
        imgsz=config.IMGSZ,
    )

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


# ─── Inference Loop (Background Thread) ──────────────────────────────────────
def inference_loop():
    """
    Background thread: Camera → YOLO → Validator → Annotated Frame.
    Runs independently from web server requests.
    """
    global latest_detections, latest_annotated_frame, latest_status

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
                validator.validate(detections)

            # Draw annotations on frame
            annotated = frame
            if detector and detections:
                annotated = detector.draw_detections(
                    frame, detections,
                    gauge_classes=gauge_class_names,
                    part_classes=part_class_names,
                )

            # Store results (thread-safe)
            with frame_lock:
                latest_detections = detections
                latest_annotated_frame = annotated

            # Build and store status for WebSocket broadcast
            if validator:
                status = validator.get_status()
                status["source"] = current_source
                status["detector_available"] = detector.is_available if detector else False
                status["camera_connected"] = camera.is_connected if camera else False
                with status_lock:
                    latest_status = status

            # Pace inference
            time.sleep(1.0 / config.TARGET_FPS)

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


# ─── Video Stream ──────────────────────────────────────────────────────────────
async def generate_mjpeg():
    """
    Async MJPEG generator.
    Uses asyncio.sleep() so it never blocks the event loop.
    Stops cleanly when the client disconnects.
    """
    try:
        while True:
            with frame_lock:
                frame = latest_annotated_frame

            if frame is None:
                placeholder = np.zeros((480, 640, 3), dtype=np.uint8)
                cv2.putText(
                    placeholder, "Waiting for camera...",
                    (120, 240), cv2.FONT_HERSHEY_SIMPLEX,
                    1.0, (80, 80, 80), 2, cv2.LINE_AA,
                )
                frame = placeholder

            _, buffer = cv2.imencode(
                ".jpg", frame,
                [cv2.IMWRITE_JPEG_QUALITY, 80],
            )
            frame_bytes = buffer.tobytes()

            yield (
                b"--frame\r\n"
                b"Content-Type: image/jpeg\r\n\r\n"
                + frame_bytes
                + b"\r\n"
            )

            await asyncio.sleep(1.0 / 25)  # ~25 fps stream

    except (asyncio.CancelledError, GeneratorExit):
        pass  # Client disconnected — normal, not an error


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


# ─── WebSocket ────────────────────────────────────────────────────────────────
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


# ─── Static Files ─────────────────────────────────────────────────────────────
app.mount("/static", StaticFiles(directory=config.FRONTEND_DIR), name="static")


# ─── Entry Point ──────────────────────────────────────────────────────────────
if __name__ == "__main__":
    uvicorn.run(
        "app:app",
        host=config.HOST,
        port=config.PORT,
        reload=False,
        log_level="info",
    )

