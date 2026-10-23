"""
SOP Compliance System — Main Application Entry Point

Initializes camera, YOLO detectors (TML + HMI pre-loaded), gauge validator,
and FastAPI server. Runs the inference loop in a background thread and serves
the web dashboard.

Multi-model support:
    Both TML and HMI YOLO models are loaded at startup and kept warm in GPU
    memory. Switching between profiles via /switch_profile is instantaneous —
    it's a simple pointer swap with no file I/O or reload delay.
"""

import asyncio
import json
import logging
import os
import queue
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
from logic import GaugeValidator, classify_scan
from scan_listener import ScanKeyListener

# ─── Logging ──────────────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-7s | %(name)s | %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("sop_app")

# ─── Global Components ────────────────────────────────────────────────────────
camera: Optional[Camera] = None

# One detector per profile, pre-loaded at startup
detectors: dict = {}          # { "TML": YOLODetector, "HMI": YOLODetector }
validators: dict = {}         # { "TML": GaugeValidator, "HMI": GaugeValidator }

# Active profile (switched instantly via API)
active_profile: str = config.DEFAULT_PROFILE

# Convenience accessors — always point to the active profile's objects
def get_detector() -> Optional[YOLODetector]:
    return detectors.get(active_profile)

def get_validator() -> Optional[GaugeValidator]:
    return validators.get(active_profile)

# Inference state
latest_detections = []
latest_annotated_frame: Optional[np.ndarray] = None
latest_status: Optional[dict] = None
frame_lock = threading.Lock()
status_lock = threading.Lock()
inference_running = False

# ── Pre-encoded MJPEG cache ──────────────────────────────────────────────────
_mjpeg_jpeg_bytes: Optional[bytes] = None
_mjpeg_frame_id: int = 0
_mjpeg_lock = threading.Lock()

# WebSocket clients — status updates (JSON)
ws_clients: Set[WebSocket] = set()
ws_clients_lock = threading.Lock()

# Current source mode
current_source = config.DEFAULT_SOURCE

# ── Global barcode scan listener ────────────────────────────────────────────
# Captures scanner keystrokes from an OS-level global hook, passively, so the
# scan still reaches the Firewall software unchanged while this app also gets
# the part number.  Scans are NOT applied from the hook thread directly — they
# are queued and applied by the inference thread (thread-safe hand-off).
scan_listener: Optional[ScanKeyListener] = None
scan_queue: "queue.Queue[str]" = queue.Queue()

# ── Auto model switching (scan → profile) ───────────────────────────────────
# A recognised scan (config.SCAN_PART_PREFIXES) selects the application.
# Everything here is only ever touched from the inference thread, except for
# the manual /switch_profile endpoint which also goes through the same helper.
pending_profile: Optional[str] = None      # profile waiting for the hold to end
pending_profile_since: float = 0.0         # when the switch was requested
last_switch_source: str = "startup"        # "scan" | "manual" | "startup"
scan_latch_active: bool = False            # a scan was already accepted for the part on the table

# ── Supervisor bypass ───────────────────────────────────────────────────────
# Deliberately NOT persisted: a restart always returns to normal checking.
# Enabled only through /bypass with the configured password.
bypass_active: bool = False

# UI Settings
show_confidence_score = False
enable_pacing = True

# Privacy blur / ignore zone (normalised [x1, y1, x2, y2], 0.0–1.0)
blur_enabled: bool = config.BLUR_ZONE_ENABLED
blur_zone: List[float] = list(config.DEFAULT_BLUR_ZONE)

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
    mode: str
    source: Optional[str] = None

class ProfileSwitch(BaseModel):
    profile: str   # "TML" or "HMI"

class BypassRequest(BaseModel):
    enabled: bool
    password: Optional[str] = None


# ─── Lifespan ─────────────────────────────────────────────────────────────────
@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup and shutdown logic using modern lifespan pattern."""
    global camera, inference_running, active_profile, blur_enabled, blur_zone

    logger.info("=" * 60)
    logger.info("  SOP Compliance System — Starting Up (Multi-Model)")
    logger.info("=" * 60)

    saved_settings = load_settings()
    detector_conf   = saved_settings.get("confidence_threshold", config.CONFIDENCE_THRESHOLD)
    validator_overlap = saved_settings.get("overlap_threshold", config.OVERLAP_THRESHOLD)
    validator_near  = saved_settings.get("near_distance_threshold", config.NEAR_DISTANCE_THRESHOLD)
    validator_hold  = saved_settings.get("ok_hold_seconds", config.OK_HOLD_SECONDS)
    visual_deadzone = saved_settings.get("visual_deadzone", None)
    active_profile  = saved_settings.get("active_profile", config.DEFAULT_PROFILE)

    # Privacy blur / ignore zone
    blur_enabled = bool(saved_settings.get("blur_enabled", config.BLUR_ZONE_ENABLED))
    saved_zone = saved_settings.get("blur_zone", config.DEFAULT_BLUR_ZONE)
    blur_zone = _coerce_blur_zone(saved_zone) or list(config.DEFAULT_BLUR_ZONE)

    # ── Pre-load ALL profile models in parallel threads ───────────────────────
    for profile_name, profile_cfg in config.PROFILES.items():
        def _build_detector(pname=profile_name, pcfg=profile_cfg):
            logger.info(f"Loading model for profile: {pname} ...")
            d = YOLODetector(
                model_path=pcfg["model_path"],
                confidence_threshold=detector_conf,
                iou_threshold=config.IOU_THRESHOLD,
                imgsz=config.IMGSZ,
                device=config.DEVICE,
                engine_path=pcfg.get("engine_path"),
                # Pass profile-specific class names so they override model defaults
                class_names_override=pcfg["class_names"],
            )
            d.deadzone = visual_deadzone
            detectors[pname] = d
            if d.is_available:
                logger.info(f"  ✓ {pname} model loaded successfully.")
            else:
                logger.warning(f"  ✗ {pname} model NOT available.")

        await asyncio.to_thread(_build_detector)

    # ── Build a GaugeValidator per profile ────────────────────────────────────
    for profile_name, profile_cfg in config.PROFILES.items():
        gauge_ids = set(profile_cfg["gauge_classes"].keys())
        v = GaugeValidator(
            checkpoints=profile_cfg["checkpoints"],
            gauge_class_ids=gauge_ids,
            gauge_confusion=profile_cfg.get("gauge_confusion"),
            u_gauge_cfg=profile_cfg.get("u_gauge_identity"),
            overlap_threshold=validator_overlap,
            near_distance_threshold=validator_near,
            ok_hold_frames=config.OK_HOLD_FRAMES,
            ok_hold_seconds=validator_hold,
            gauge_grace_frames=config.GAUGE_GRACE_FRAMES,
            part_clear_time_complete=config.PART_CLEAR_TIME_COMPLETE,
            part_clear_time_inspecting=config.PART_CLEAR_TIME_INSPECTING,
        )
        validators[profile_name] = v

    # Restore per-gauge settings from saved_settings into TML validator
    if "gauge_configs" in saved_settings and saved_settings["gauge_configs"]:
        tml_validator = validators.get("TML")
        if tml_validator:
            for g_conf in saved_settings["gauge_configs"]:
                cp_id = g_conf.get("id")
                if cp_id in tml_validator._checkpoint_configs:
                    tml_validator._checkpoint_configs[cp_id]["method"] = g_conf.get("method", "near")
                    if "overlap_threshold" in g_conf:
                        tml_validator._checkpoint_configs[cp_id]["overlap_threshold"] = g_conf["overlap_threshold"]
                    if "near_distance_threshold" in g_conf:
                        tml_validator._checkpoint_configs[cp_id]["near_distance_threshold"] = g_conf["near_distance_threshold"]

    logger.info(f"Active profile on startup: {active_profile}")
    logger.info(
        "Auto model switch: %s | prefixes: %s | hold: %.1fs (+part out of view, max %.1fs)",
        "ENABLED" if config.SCAN_AUTO_SWITCH else "disabled",
        ", ".join(
            f"{name}={list(prefixes) if not isinstance(prefixes, str) else prefixes}"
            for name, prefixes in config.SCAN_PART_PREFIXES.items()
        ),
        config.SCAN_SWITCH_HOLD_SECONDS,
        config.SCAN_SWITCH_MAX_WAIT,
    )
    logger.info(
        "Supervisor bypass: available (password protected), currently %s.",
        "ON" if bypass_active else "OFF",
    )

    # ── Global barcode scan listener (inside this app — nothing to install) ──
    global scan_listener

    def _on_scan(code: str) -> None:
        # Keep the hook thread fast: queue the value, apply it on the
        # inference thread (avoids touching validator state concurrently
        # with validate()).
        logger.info(f"[SCAN] Captured part number: {code}")
        scan_queue.put(code)

    scan_listener = ScanKeyListener(on_scan=_on_scan, enabled=config.SCAN_LISTENER_ENABLED)
    if scan_listener.start():
        logger.info("Barcode scan listener started — scans are captured "
                    "regardless of which window has focus.")

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
    if scan_listener is not None:
        scan_listener.stop()
    if camera:
        camera.stop()
    logger.info("SOP Compliance System shut down.")


# ─── FastAPI App ──────────────────────────────────────────────────────────────
app = FastAPI(
    title="SOP Compliance System",
    version=config.APP_VERSION,
    lifespan=lifespan,
)


# ─── Privacy Blur / Ignore Zone ──────────────────────────────────────────────
def scan_listener_status() -> dict:
    return (
        scan_listener.status() if scan_listener is not None
        else {"scan_listener_running": False, "scans_captured": 0, "last_scan": None}
    )


# ─── Auto Model Switching (scan → profile) ───────────────────────────────────
def _inspection_state_name(validator: Optional[GaugeValidator]) -> Optional[str]:
    """Current inspection state as a plain string, or None without a validator."""
    if validator is None:
        return None
    state = getattr(validator, "inspection_state", None)
    return getattr(state, "value", state)


def _apply_profile_switch(profile: str, source: str = "manual") -> None:
    """
    Make `profile` the active one, reset it for a clean session and persist it.

    Both models are pre-loaded, so this is a pointer swap — no reload.  The
    old profile's counters/log are untouched (each profile owns its own
    validator), so nothing is lost by switching.
    """
    global active_profile, pending_profile, pending_profile_since
    global scan_latch_active, last_switch_source

    profile = str(profile).upper()
    if profile not in config.PROFILES:
        return

    # Close the outgoing session first.  If its part never left the view its
    # state is frozen at COMPLETE/INSPECTING; resetting now logs that result
    # exactly once instead of re-logging it when we switch back later.
    outgoing = validators.get(active_profile)
    if outgoing is not None and _inspection_state_name(outgoing) not in (None, "IDLE"):
        logger.info("Closing the %s session before switching away.", active_profile)
        outgoing.reset()

    active_profile = profile
    last_switch_source = source

    v = validators.get(profile)
    if v:
        v.reset()
        v.set_bypass(bypass_active)

    pending_profile = None
    pending_profile_since = 0.0
    scan_latch_active = False

    saved = load_settings()
    saved["active_profile"] = profile
    save_settings(saved)

    logger.info(f"Profile switched to: {profile} (source: {source})")


def _handle_scan_code(code: str) -> None:
    """
    Apply one scanned string.  Called from the inference thread only.

    Flow:
      1. Classify by prefix.  Unrecognised text (the operator's other codes)
         is ignored completely — no switch, no reset, no UI noise.
      2. Store the part number on the *current* profile (the scan labels the
         part that was just checked).  Never restore part memory here: a late
         scan must not re-latch gauges.
      3. If the scan belongs to another application, queue the switch.  The
         swap happens after the hold, once the part has left the view.
    """
    global pending_profile, pending_profile_since, scan_latch_active

    target = classify_scan(code)
    if target is None:
        logger.debug("Scan ignored (not an application code): %s", code)
        return

    validator = get_validator()
    state = _inspection_state_name(validator)

    # Latch: the first recognised scan of a part on the table wins; repeats
    # during the same inspection are ignored.  Cleared when the part leaves.
    if state == "IDLE":
        scan_latch_active = False
    elif scan_latch_active:
        logger.info(f"Repeat scan ignored (first scan already applied): {code}")
        return

    if validator:
        validator.set_part_no(code, restore_memory=False)

    if bypass_active and validator:
        # Supervisor bypass: a recognised scan closes the part as all-OK.
        validator.force_bypass_complete()
        scan_latch_active = True
    elif state in ("INSPECTING", "COMPLETE"):
        scan_latch_active = True

    if target == active_profile:
        # The latest recognised scan says the current model is the right one —
        # cancel a switch that may have been queued by an earlier mis-scan.
        if pending_profile is not None:
            logger.info(
                "Pending switch to %s cancelled — scan confirms %s.",
                pending_profile, target,
            )
            pending_profile = None
            pending_profile_since = 0.0
        logger.info(f"Scan {code} → {target} (already active)")
        return

    # Only start/refresh the countdown when the target actually changes.
    if pending_profile != target:
        pending_profile = target
        pending_profile_since = time.time()
        logger.info(
            "Scan %s → %s. Switch queued: holding the current result for at "
            "least %.1fs and until the part leaves the view.",
            code, target, config.SCAN_SWITCH_HOLD_SECONDS,
        )


def _resolve_pending_switch() -> None:
    """
    Finish a queued auto-switch once the hold has elapsed AND the part is out
    of view.  A safety cap prevents the operator ever getting stuck.
    """
    global pending_profile

    if pending_profile is None:
        return

    held = time.time() - pending_profile_since
    if held < config.SCAN_SWITCH_HOLD_SECONDS:
        return

    state = _inspection_state_name(get_validator())
    part_still_present = state in ("INSPECTING", "COMPLETE")

    if part_still_present and held < config.SCAN_SWITCH_MAX_WAIT:
        return  # keep showing the finished result until the part is removed

    if part_still_present:
        logger.warning(
            "Part still in view after %.1fs — switching to %s anyway.",
            held, pending_profile,
        )

    _apply_profile_switch(pending_profile, source="scan")


def _coerce_blur_zone(zone) -> Optional[List[float]]:
    """
    Validate a normalised [x1, y1, x2, y2] blur zone.

    Accepts nothing outside 0.0–1.0 and rejects an empty rectangle.  Returns
    the cleaned list, or None when the value is not usable.
    """
    if not zone or len(zone) != 4:
        return None
    try:
        x1, y1, x2, y2 = (float(v) for v in zone)
    except (TypeError, ValueError):
        return None

    x1, x2 = sorted((max(0.0, min(1.0, x1)), max(0.0, min(1.0, x2))))
    y1, y2 = sorted((max(0.0, min(1.0, y1)), max(0.0, min(1.0, y2))))
    if x2 - x1 < 0.01 or y2 - y1 < 0.01:
        return None
    return [round(x1, 4), round(y1, 4), round(x2, 4), round(y2, 4)]


def _blur_zone_pixels(zone: List[float], w: int, h: int):
    """Convert a normalised blur zone to pixel coordinates for a frame."""
    x1 = int(round(zone[0] * w))
    y1 = int(round(zone[1] * h))
    x2 = int(round(zone[2] * w))
    y2 = int(round(zone[3] * h))
    x1, x2 = sorted((max(0, min(w - 1, x1)), max(0, min(w, x2))))
    y1, y2 = sorted((max(0, min(h - 1, y1)), max(0, min(h, y2))))
    return x1, y1, x2, y2


def _detection_in_blur_zone(det: dict, w: int, h: int) -> bool:
    """True when a detection's centre falls inside the active blur zone."""
    if not blur_enabled or not blur_zone:
        return False
    x1, y1, x2, y2 = _blur_zone_pixels(blur_zone, w, h)
    bx1, by1, bx2, by2 = det["bbox"]
    cx, cy = (bx1 + bx2) / 2, (by1 + by2) / 2
    return x1 <= cx <= x2 and y1 <= cy <= y2


def _apply_blur_zone(frame: np.ndarray) -> np.ndarray:
    """
    Heavily blur the privacy zone in-place (display only).

    The blur is applied after the frame is downscaled for streaming, so the
    cost stays low regardless of the camera resolution.
    """
    if not blur_enabled or not blur_zone:
        return frame

    h, w = frame.shape[:2]
    x1, y1, x2, y2 = _blur_zone_pixels(blur_zone, w, h)
    if x2 - x1 < 2 or y2 - y1 < 2:
        return frame

    roi = frame[y1:y2, x1:x2]
    # Kernel scales with the zone height but is capped for performance.
    k = max(31, min(61, ((y2 - y1) // 3) | 1))
    frame[y1:y2, x1:x2] = cv2.GaussianBlur(roi, (k, k), 0)
    return frame


# ─── JPEG Encoding Helper ────────────────────────────────────────────────────
def _encode_mjpeg_frame(frame: np.ndarray) -> None:
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

    # Hide the operator / accessories before streaming the frame.
    frame = _apply_blur_zone(frame)

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
    Background thread: Camera → YOLO (active profile) → Validator → Frame.
    Automatically uses whichever profile is currently active.
    """
    global latest_detections, latest_annotated_frame, latest_status

    _fps_frame_count = 0
    _fps_last_time   = time.time()
    _live_fps        = 0.0
    _last_state      = "IDLE"
    _state_change_time = time.time()

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

            # Snapshot the active profile objects (thread-safe — Python GIL)
            detector  = get_detector()
            validator = get_validator()

            # Apply any scanner part numbers queued by the global scan
            # listener (applied here so the validator is only touched from
            # the inference thread).
            while not scan_queue.empty():
                try:
                    code = scan_queue.get_nowait()
                except queue.Empty:
                    break
                if validators:
                    logger.info(f"Scanner input received: {code}")
                    if config.SCAN_AUTO_SWITCH:
                        # Classify → (maybe) queue profile switch → store part no
                        _handle_scan_code(code)
                    else:
                        # Auto-switch disabled: behave exactly as before.
                        active_validator = get_validator()
                        if active_validator:
                            active_validator.set_part_no(code, restore_memory=False)
                else:
                    # No validator yet — keep it for the next profile/loop.
                    scan_queue.put(code)
                    break

            # Run YOLO detection
            detections = []
            if detector and detector.is_available:
                detections = detector.detect(frame)

            # Drop anything inside the privacy blur zone — that region holds
            # the operator, hands and surrounding accessories, none of which
            # should influence the SOP decision.
            if blur_enabled and blur_zone and detections:
                fh, fw = frame.shape[:2]
                detections = [
                    d for d in detections
                    if not _detection_in_blur_zone(d, fw, fh)
                ]

            # Run SOP validation.  The frame width lets the U-gauge logic
            # scale its pixel thresholds (live feed is pre-scaled to a
            # different width than a recorded video).
            status_from_validate = None
            if validator:
                fh, fw = frame.shape[:2]
                status_from_validate = validator.validate(
                    detections, frame_width=fw
                )

            annotated = frame

            with frame_lock:
                latest_detections = detections
                latest_annotated_frame = annotated

            _encode_mjpeg_frame(annotated)

            # Track inference FPS
            _fps_frame_count += 1
            now = time.time()
            elapsed = now - _fps_last_time
            if elapsed >= 2.0:
                _live_fps = round(_fps_frame_count / elapsed, 1)
                _fps_frame_count = 0
                _fps_last_time   = now

            # Build and store status
            if validator:
                status = status_from_validate if status_from_validate else validator.get_status()
                status["source"]             = current_source
                status["active_profile"]     = active_profile
                status["detector_available"] = detector.is_available if detector else False
                status["camera_connected"]   = camera.is_connected if camera else False
                status["inference_fps"]      = _live_fps
                status["raw_detections"]     = detections
                status["frame_width"]        = frame.shape[1] if frame is not None else 1280
                status["frame_height"]       = frame.shape[0] if frame is not None else 720
                status["show_confidence_score"] = show_confidence_score
                status["blur_enabled"]       = blur_enabled
                status["blur_zone"]          = blur_zone
                status["scan_listener"]      = scan_listener_status()
                # Auto-switch state so the UI can show "Switching to X…"
                status["scan_auto_switch"]   = bool(config.SCAN_AUTO_SWITCH)
                status["bypass_active"]      = bool(bypass_active)
                status["pending_profile"]    = pending_profile
                status["pending_profile_display_name"] = (
                    config.PROFILES[pending_profile]["display_name"]
                    if pending_profile in config.PROFILES else None
                )
                # Send profile metadata so the UI can update gauge list/images
                status["profile_meta"] = {
                    "name": active_profile,
                    "display_name": config.PROFILES[active_profile]["display_name"],
                    "gauge_images": config.PROFILES[active_profile]["gauge_images"],
                }
                if status.get("glove_warning"):
                    logger.warning("[BROADCAST] glove_warning=True being sent to frontend!")
                with status_lock:
                    latest_status = status

            # Finish a queued auto-switch only after the status of this frame
            # has been stored, so the old result stays visible for the hold.
            _resolve_pending_switch()

            if enable_pacing:
                state = "IDLE"
                if validator and 'status' in locals() and status:
                    state = status.get("inspection_state", "IDLE")

                if state != _last_state:
                    _last_state = state
                    _state_change_time = time.time()

                time_in_state = time.time() - _state_change_time

                if state == "COMPLETE":
                    idle_fps = 0.0 if time_in_state < 2.0 else 5.0
                elif state == "IDLE":
                    idle_fps = 1.0 if time_in_state > 60.0 else 5.0
                else:
                    idle_fps = 0.0  # Full speed while INSPECTING

                if idle_fps > 0.0:
                    elapsed_loop_time = time.time() - loop_start_time
                    sleep_time = (1.0 / idle_fps) - elapsed_loop_time
                    if sleep_time > 0:
                        time.sleep(sleep_time)

        except Exception as e:
            logger.error(f"Inference loop error: {e}")
            time.sleep(0.5)


# ─── WebSocket Broadcast ─────────────────────────────────────────────────────
async def ws_broadcast_loop():
    while True:
        try:
            await asyncio.sleep(0.1)

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


# ─── MJPEG Fallback ──────────────────────────────────────────────────────────
async def generate_mjpeg():
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
    index_path = os.path.join(config.FRONTEND_DIR, "index.html")
    with open(index_path, "r", encoding="utf-8") as f:
        return HTMLResponse(content=f.read())


@app.get("/video")
async def video_feed():
    return StreamingResponse(
        generate_mjpeg(),
        media_type="multipart/x-mixed-replace; boundary=frame",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@app.get("/status")
async def get_status():
    validator = get_validator()
    detector  = get_detector()
    if validator is None:
        return JSONResponse({"error": "System not initialized"}, status_code=503)

    status = validator.get_status()
    status["source"]             = current_source
    status["active_profile"]     = active_profile
    status["detector_available"] = detector.is_available if detector else False
    status["camera_connected"]   = camera.is_connected if camera else False
    status["blur_enabled"]       = blur_enabled
    status["blur_zone"]          = blur_zone
    status["scan_listener"]      = scan_listener_status()
    status["scan_auto_switch"]   = bool(config.SCAN_AUTO_SWITCH)
    status["bypass_active"]      = bool(bypass_active)
    status["pending_profile"]    = pending_profile
    status["pending_profile_display_name"] = (
        config.PROFILES[pending_profile]["display_name"]
        if pending_profile in config.PROFILES else None
    )
    status["profile_meta"] = {
        "name": active_profile,
        "display_name": config.PROFILES[active_profile]["display_name"],
        "gauge_images": config.PROFILES[active_profile]["gauge_images"],
    }
    return JSONResponse(status)


@app.post("/reset")
async def reset_inspection():
    global scan_latch_active
    validator = get_validator()
    if validator is None:
        return JSONResponse({"error": "System not initialized"}, status_code=503)

    status = validator.reset()
    # A manual reset starts a fresh part session — the first scan counts again.
    scan_latch_active = False
    logger.info("Inspection reset by user.")
    return JSONResponse(status)


# ─── Profile Switching ────────────────────────────────────────────────────────
@app.post("/switch_profile")
async def switch_profile(body: ProfileSwitch):
    """
    Manual profile switch (TML ↔ HMI) — the operator override.

    Both models are pre-loaded, so this is an instantaneous in-memory swap.
    A manual switch is explicit, so it takes effect immediately (no hold) and
    cancels any auto-switch that was waiting for the part to be removed.
    """
    profile = body.profile.upper()
    if profile not in config.PROFILES:
        return JSONResponse(
            {"error": f"Unknown profile '{profile}'. Valid options: {list(config.PROFILES.keys())}"},
            status_code=400,
        )

    _apply_profile_switch(profile, source="manual")

    return JSONResponse({
        "status": "ok",
        "active_profile": profile,
        "display_name": config.PROFILES[profile]["display_name"],
    })


# ─── Supervisor Bypass ───────────────────────────────────────────────────────
@app.post("/bypass")
async def set_bypass(body: BypassRequest):
    """
    Emergency bypass — every gauge is reported CHECKED (OK) automatically.

    Enabling always requires the configured password; disabling never does.
    The state is deliberately NOT persisted: a restart always returns to
    normal checking.  Passwords are verified here, never trusted from the page.
    """
    global bypass_active

    was_active = bypass_active

    if body.enabled:
        if (body.password or "") != config.ADMIN_PASSWORD:
            logger.warning("Supervisor bypass enable REJECTED — wrong password.")
            return JSONResponse({"error": "Invalid password"}, status_code=401)
        if not bypass_active:
            logger.warning("=" * 60)
            logger.warning("  SUPERVISOR BYPASS ENABLED — gauges report OK without checks")
            logger.warning("=" * 60)
        bypass_active = True
    else:
        if bypass_active:
            logger.warning("Supervisor bypass DISABLED — normal checking restored.")
        bypass_active = False

    for v in validators.values():
        v.set_bypass(bypass_active)

    # Leaving bypass with a part on the table: drop the fabricated OKs and
    # start that part again with real checking.
    if was_active and not body.enabled:
        active_validator = get_validator()
        if active_validator is not None and _inspection_state_name(active_validator) != "IDLE":
            active_validator.reset()

    return JSONResponse({
        "status": "ok",
        "bypass_active": bypass_active,
    })


@app.get("/profiles")
async def get_profiles():
    """Return available profiles and the currently active one."""
    return JSONResponse({
        "active": active_profile,
        "profiles": {
            k: {
                "display_name": v["display_name"],
                "num_checkpoints": len(v["checkpoints"]),
            }
            for k, v in config.PROFILES.items()
        },
    })


@app.post("/source")
async def switch_source(body: SourceSwitch):
    global current_source

    mode   = body.mode
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
    validator = get_validator()
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
    validator = get_validator()
    if validator:
        validator.set_part_no(body.part_no)
    return JSONResponse({"status": "ok"})


class ConfidenceToggle(BaseModel):
    show: bool

@app.post("/settings/confidence")
async def toggle_confidence(body: ConfidenceToggle):
    global show_confidence_score
    show_confidence_score = body.show
    logger.info(f"Show confidence score: {show_confidence_score}")
    return JSONResponse({"status": "ok", "show_confidence_score": show_confidence_score})

class PacingToggle(BaseModel):
    enable: bool

@app.post("/settings/pacing")
async def toggle_pacing(body: PacingToggle):
    global enable_pacing
    enable_pacing = body.enable
    logger.info(f"Enable pacing: {enable_pacing}")
    return JSONResponse({"status": "ok", "enable_pacing": enable_pacing})

class BlurSettingsUpdate(BaseModel):
    enabled: Optional[bool] = None
    zone: Optional[List[float]] = None    # normalised [x1, y1, x2, y2]

@app.post("/settings/blur")
async def update_blur_settings(body: BlurSettingsUpdate):
    """Turn the privacy blur zone on/off or change its rectangle."""
    global blur_enabled, blur_zone

    if body.enabled is not None:
        blur_enabled = bool(body.enabled)

    if body.zone is not None:
        zone = _coerce_blur_zone(body.zone)
        if zone is None:
            return JSONResponse(
                {"error": "zone must be 4 normalised values (0.0–1.0) forming a non-empty rectangle"},
                status_code=400,
            )
        blur_zone = zone

    saved = load_settings()
    saved["blur_enabled"] = blur_enabled
    saved["blur_zone"] = blur_zone
    save_settings(saved)

    logger.info(f"Blur zone: enabled={blur_enabled} zone={blur_zone}")
    return JSONResponse({
        "status": "ok",
        "blur_enabled": blur_enabled,
        "blur_zone": blur_zone,
    })


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
    blur_enabled: Optional[bool] = None
    blur_zone: Optional[List[float]] = None

@app.get("/settings")
async def get_settings_endpoint():
    validator = get_validator()
    detector  = get_detector()
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
        "visual_deadzone": detector.deadzone if detector else None,
        "blur_enabled": blur_enabled,
        "blur_zone": blur_zone,
    })

@app.post("/settings")
async def update_settings_endpoint(settings: SettingsUpdate):
    global blur_enabled, blur_zone

    detector  = get_detector()
    validator = get_validator()

    # Privacy blur zone
    if settings.blur_enabled is not None:
        blur_enabled = bool(settings.blur_enabled)
    if settings.blur_zone is not None:
        zone = _coerce_blur_zone(settings.blur_zone)
        if zone is None:
            return JSONResponse(
                {"error": "blur_zone must be 4 normalised values (0.0–1.0) forming a non-empty rectangle"},
                status_code=400,
            )
        blur_zone = zone

    # Apply to ALL detectors (confidence is global)
    for d in detectors.values():
        d.confidence_threshold = settings.confidence_threshold
        d.deadzone = settings.visual_deadzone

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
        "visual_deadzone": settings.visual_deadzone,
        "active_profile": active_profile,
        "blur_enabled": blur_enabled,
        "blur_zone": blur_zone,
    })

    logger.info(f"Settings updated: {settings.dict()}")
    return JSONResponse({"status": "ok"})


@app.post("/settings/reset")
async def reset_settings_endpoint():
    global blur_enabled, blur_zone

    if os.path.exists(SETTINGS_FILE):
        try:
            os.remove(SETTINGS_FILE)
        except Exception as e:
            logger.error(f"Failed to delete settings.json: {e}")

    for d in detectors.values():
        d.confidence_threshold = config.CONFIDENCE_THRESHOLD
        d.deadzone = None

    for profile_name, v in validators.items():
        v.overlap_threshold = config.OVERLAP_THRESHOLD
        v.near_distance_threshold = config.NEAR_DISTANCE_THRESHOLD
        v.ok_hold_seconds = config.OK_HOLD_SECONDS
        profile_cps = config.PROFILES[profile_name]["checkpoints"]
        for cp in profile_cps:
            cp_id = cp["id"]
            if cp_id in v._checkpoint_configs:
                v._checkpoint_configs[cp_id]["method"] = cp.get("method", "near")
                # Restore config defaults when present (HMI uses 50 px per
                # checkpoint); otherwise fall back to the global value.
                for key in ("overlap_threshold", "near_distance_threshold"):
                    if key in cp:
                        v._checkpoint_configs[cp_id][key] = cp[key]
                    else:
                        v._checkpoint_configs[cp_id].pop(key, None)

    blur_enabled = config.BLUR_ZONE_ENABLED
    blur_zone = list(config.DEFAULT_BLUR_ZONE)

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
            data = await ws.receive_text()
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
                await asyncio.sleep(1.0 / 20)
            else:
                await asyncio.sleep(0.005)

    except Exception:
        pass
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
