"""
Centralized configuration for SOP Compliance System.
All thresholds, class mappings, and validation rules live here.

Multi-model support:
    Two inspection profiles are defined — TML and HMI.
    The active profile is selected at runtime via /switch_profile API.
    Both model weights are pre-loaded into GPU memory at startup so
    switching between profiles is instantaneous (zero reload lag).
"""

import os

# ─── Paths ────────────────────────────────────────────────────────────────────
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
FRONTEND_DIR = os.path.join(BASE_DIR, "frontend")

# Default video file for testing
_LOCAL_VIDEO = os.path.join(BASE_DIR, "video.mp4")
DEFAULT_VIDEO_PATH = _LOCAL_VIDEO if os.path.exists(_LOCAL_VIDEO) else r"C:\Users\RohithSuryaCKM\Videos\Screen Recordings\Screen Recording 2026-10-10 141820.mp4"

# Hikvision Camera URL
LIVE_CAMERA_URL = "rtsp://admin:Wedit@2024@192.168.1.66:554/Streaming/Channels/101"


# ─── YOLO Settings ───────────────────────────────────────────────────────────
CONFIDENCE_THRESHOLD = 0.10
IOU_THRESHOLD = 0.15
IMGSZ = 1024         # Must match what model was trained/predicted with
DEVICE = "0"         # "0" = GPU (CUDA device 0). Change to "cpu" if no GPU.

LIVE_IMGSZ = 1024

# ─── Validation Thresholds ───────────────────────────────────────────────────
OVERLAP_THRESHOLD = 0.15
NEAR_DISTANCE_THRESHOLD = 50
IGNORE_LEFT_OF_X = 320
OK_HOLD_FRAMES = 3
OK_HOLD_SECONDS = 0.1

# ─── Part-Presence State Machine ─────────────────────────────────────────────
GAUGE_GRACE_FRAMES = 15
PART_CLEAR_TIME_COMPLETE = 3.0
PART_CLEAR_TIME_INSPECTING = 8.0

# ─── Privacy Blur / Ignore Zone ──────────────────────────────────────────────
# Rectangular area of the frame that is blurred in the video feed AND excluded
# from YOLO detections (used to hide the operator, hands and surrounding
# accessories).  Coordinates are NORMALISED: [x1, y1, x2, y2] where every
# value is 0.0–1.0 of the frame width / height.  This keeps the zone correct
# for any camera / video resolution.
# Editable at runtime from the camera header toggle or the Admin panel.
BLUR_ZONE_ENABLED = True
DEFAULT_BLUR_ZONE = [0.0, 0.0, 0.36, 1.0]

# ─── Video Source ─────────────────────────────────────────────────────────────
DEFAULT_SOURCE = "video"
CAMERA_INDEX = 0

# ─── Barcode Scan Listener (global keyboard watcher) ─────────────────────────
# The scanner is a keyboard wedge always aimed at the Firewall software window.
# This listener (in scan_listener.py) runs INSIDE this application and captures
# scans from a global OS-level keyboard hook, passively — no keys are ever
# blocked, the Firewall software receives every scan unchanged.  Requires:
#     pip install pynput
SCAN_LISTENER_ENABLED = True

# ─── Auto Model Switching (scan → profile) ───────────────────────────────────
# The operator scans several codes per part; only ONE of them identifies the
# application.  A scan is matched by its PREFIX — everything after the prefix
# may vary freely.  Any scan that matches no prefix is ignored completely
# (no switch, no state change).
#
# To support a new application, add one line here and one PROFILES entry above.
SCAN_AUTO_SWITCH = True

SCAN_PART_PREFIXES = {
    "TML": ("005724",),              # TML scans start with these 6 digits
    "HMI": ("33100-2A160",),         # HMI scans start with this code
}

# When a scan points at a DIFFERENT profile, the finished result of the part
# currently on the table stays on screen for at least this long, and only then
# does the model swap — but never while the part is still in view.
SCAN_SWITCH_HOLD_SECONDS = 2.0

# Safety cap: if the part never leaves the view, switch anyway after this long
# so the operator can never get stuck on the wrong model.
SCAN_SWITCH_MAX_WAIT = 10.0

# ─── Supervisor Bypass ───────────────────────────────────────────────────────
# Emergency escape hatch for a crashed / misbehaving inspection: with the
# password below, every gauge is reported CHECKED (OK) automatically so the
# line keeps running until an engineer arrives.
#
# Safety rules:
#   * Never persisted — the app always starts with the bypass OFF.
#   * Enabling always requires the password; no password is stored in the page.
#   * Switching it OFF returns to normal checking immediately.
# Change the password here (and in the admin login in frontend/app.js).
ADMIN_PASSWORD = "1234"

# ─── Server ───────────────────────────────────────────────────────────────────
HOST = "0.0.0.0"
PORT = 8000

# ─── Inference ────────────────────────────────────────────────────────────────
TARGET_FPS = 10

# ─── UI Labels ────────────────────────────────────────────────────────────────
APP_TITLE = "SOP Compliance Software"
APP_MODEL = "Fire Wall DFP6"
COMPANY_NAME = "Delphi-TVS Technologies Limited"
COMPANY_TAGLINE = "Tomorrow's Engineering Today"
APP_VERSION = "1.0.0"


# ═══════════════════════════════════════════════════════════════════════════════
#  INSPECTION PROFILES
#  Each profile is self-contained: model weights, class maps, checkpoints.
#  The validator and detector swap the active profile at runtime.
# ═══════════════════════════════════════════════════════════════════════════════

PROFILES = {

    # ──────────────────────────────────────────────────────────────────────────
    "TML": {
        "display_name": "TML Part",
        "model_path": os.path.join(BASE_DIR, "models", "best_v2.pt"),
        "engine_path": os.path.join(BASE_DIR, "models", "best.engine"),

        # Gauge classes (objects the operator holds / uses)
        "gauge_classes": {
            0: "Distance",
            1: "Pin",
            2: "Dia",
            3: "M6",
            4: "M8",
            5: "13mm",
            14: "11mm",
        },

        # Part classes (fixed inspection areas / the physical part)
        "part_classes": {
            6: "DS Thread",
            7: "Top",
            8: "Bracket Hole Side",
            9: "Pin Check",
            11: "In",
            12: "Out",
            13: "Part",
            15: "Hand",
        },

        # All class names by ID (used by detector for label lookup)
        "class_names": {
            0: "Distance",
            1: "Pin",
            2: "Dia",
            3: "M6",
            4: "M8",
            5: "13mm",
            6: "DS Thread",
            7: "Top",
            8: "Bracket Hole Side",
            9: "Pin Check",
            10: "HH",
            11: "In",
            12: "Out",
            13: "Part",
            14: "11mm",
            15: "Hand",
        },

        # Gauge reference images (served from /reference_images/)
        "gauge_images": {
            1: "Distance.png",
            2: "Pin Gauge.png",
            3: "Dia Gauge.png",
            4: "M6 Gauge.png",
            5: "M8 Gauge.png",
            6: "11mm Gauge.png",
            7: "13mm Gauge.png",
        },

        # SOP validation checkpoints
        "checkpoints": [
            {
                "id": 1,
                "name": "Distance Gauge",
                "gauge_class": "Distance",
                "part_class": "Part",
                "method": "fully_inside",
                "description": "Distance gauge fully inside TML Part",
            },
            {
                "id": 2,
                "name": "Pin Gauge",
                "gauge_class": "Pin",
                "part_class": "DS Thread",
                "method": "intersects",
                "description": "Pin Gauge overlapping DS Thread",
            },
            {
                "id": 3,
                "name": "Dia Gauge",
                "gauge_class": "Dia",
                "part_class": "DS Thread",
                "method": "near",
                "near_distance_threshold": 180,
                "description": "Dia Gauge near DS Thread",
            },
            {
                "id": 4,
                "name": "M6 Thread",
                "gauge_class": "M6",
                "part_class": "Top",
                "method": "near",
                "description": "M6 Thread near Hole Top",
            },
            {
                "id": 5,
                "name": "M8 Thread",
                "gauge_class": "M8",
                "part_class": "Top",
                "method": "near",
                "description": "M8 Thread near Hole Top",
            },
            {
                "id": 6,
                "name": "11mm Gauge",
                "gauge_class": "11mm",
                "part_class": "Out",
                "method": "near",
                "description": "11mm Gauge near Outlet",
            },
            {
                "id": 7,
                "name": "13mm Gauge",
                "gauge_class": "13mm",
                "part_class": "In",
                "method": "near",
                "description": "13mm Gauge near Inlet",
            },
        ],
    },

    # ──────────────────────────────────────────────────────────────────────────
    "HMI": {
        "display_name": "HMI Part",
        "model_path": os.path.join(BASE_DIR, "models", "best_hmi_v2.pt"),
        "engine_path": os.path.join(BASE_DIR, "models", "best_hmi_v2.engine"),  # optional TRT

        # Gauge classes
        "gauge_classes": {
            0: "11mm",
            1: "8mm",
            2: "Outer Seal",
            3: "U Gauge",
        },

        # Part classes (inspection areas on the HMI part)
        "part_classes": {
            4: "Inlet Hole",
            5: "Outlet Hole",
            6: "Part",
        },

        # All class names by ID
        "class_names": {
            0: "11mm",
            1: "8mm",
            2: "Outer Seal",
            3: "U Gauge",
            4: "Inlet Hole",
            5: "Outlet Hole",
            6: "Part",
        },

        # Gauge reference images (add your HMI images to Reference_gauge_images/)
        # If an image is missing the UI will show a placeholder icon.
        "gauge_images": {
            1: "HMI_11mm.png",
            2: "HMI_8mm.png",
            3: "HMI_OuterSeal.png",
            4: "HMI_UGauge.png",
            5: "HMI_UGauge.png",
            6: "HMI_UGauge.png",
            7: "HMI_UGauge.png",
        },

        # 8mm / 11mm look almost identical to the model.  When the same frame
        # contains two boxes with the same label, the higher-confidence box
        # keeps that label and the lower-confidence one is the other gauge —
        # but only if it has moved away from its resting position.
        "gauge_confusion": {
            "pair": ["8mm", "11mm"],
            "min_rest_distance": 30,   # px a gauge must move from rest to count
        },

        # ── U-Gauge identity tracking ─────────────────────────────────────────
        # All four U-gauges are detected as a single YOLO class "U Gauge".
        # The validator identifies each one by its resting vertical rank
        # (top → bottom = Inlet Go, Inlet NoGo, LP Go, LP NoGo) and tracks
        # each gauge independently through pickup, check, and return.
        "u_gauge_identity": {
            "enabled": True,
            "gauge_class": "U Gauge",         # the single YOLO class name
            "count": 4,                        # expected number of U-gauges
            "min_rest_distance": 40,           # px a gauge must move to count as picked up
            "min_stable_frames": 8,            # stable frames before rest slots are learned
            "learning_max_spread": 250,        # reject a "rest layout" this far apart (px)
            "checkpoint_ids": [4, 5, 6, 7],    # must match checkpoint ids below
            "dedupe_px": 15.0,

            # The model sometimes reports a U-gauge as 8mm / 11mm while the
            # operator is checking it at the Inlet/Outlet hole.  One gauge is
            # away from the rack at a time, so the empty rack slot identifies
            # it: the extra box at the part is bound to that gauge's rank.
            # The real 8mm / 11mm pins (highest-confidence boxes on the table)
            # always keep their labels.  When all four U-gauges are in the
            # rack, nothing is re-labelled.
            "confusable_classes": ["8mm", "11mm"],

            # A hand can hide one or more gauges for a moment.  Keep the
            # identity, position and checkpoint progress of *every* hidden
            # gauge for this many seconds instead of deciding that it was
            # taken.  The gauges do not move on their own; only the one the
            # operator carries to the part does.  While hidden the checkpoint
            # is WAITING; if the gauge is later confirmed away and is not at
            # an Inlet/Outlet hole it stays PENDING (never a false NG).
            "occlusion_hold_seconds": 3.0,

            # The normal workflow is ranks 0/1 at the Inlet and 2/3 at the
            # Outlet, but this mapping is a preference, not a hard rule.
            # When True, a gauge taken to the other hole is still accepted
            # as checked instead of being rejected or reported NG.
            "allow_cross_hole_check": True,
        },

        # SOP validation checkpoints
        # require_movement: the gauge must move at least min_rest_distance
        # away from its resting position before the check can latch OK.
        "checkpoints": [
            {
                "id": 1,
                "name": "11mm Gauge",
                "gauge_class": "11mm",
                "part_classes": ["Inlet Hole", "Outlet Hole"],
                "method": "near",
                "near_distance_threshold": 50,
                "require_movement": True,
                "description": "11mm Gauge near Inlet or Outlet Hole (50 px)",
            },
            {
                "id": 2,
                "name": "8mm Gauge",
                "gauge_class": "8mm",
                "part_classes": ["Inlet Hole", "Outlet Hole"],
                "method": "near",
                "near_distance_threshold": 50,
                "require_movement": True,
                "description": "8mm Gauge near Inlet or Outlet Hole (50 px)",
            },
            {
                "id": 3,
                "name": "Outer Seal",
                "gauge_class": "Outer Seal",
                "part_class": "Part",
                "method": "fully_inside",
                "require_movement": True,
                "persist_rest": True,
                "description": "Outer Seal fully inside HMI Part",
            },
            # ── Four U-Gauge checkpoints (identity resolved at runtime) ──────
            {
                "id": 4,
                "name": "Inlet Go",
                "gauge_class": "U Gauge",
                "part_class": "Inlet Hole",
                "method": "near",
                "near_distance_threshold": 60,
                "require_movement": True,
                "u_gauge_rank": 0,             # top-most resting position
                "description": "Inlet Go U-Gauge near Inlet Hole",
            },
            {
                "id": 5,
                "name": "Inlet NoGo",
                "gauge_class": "U Gauge",
                "part_class": "Inlet Hole",
                "method": "near",
                "near_distance_threshold": 60,
                "require_movement": True,
                "u_gauge_rank": 1,             # second from top
                "description": "Inlet NoGo U-Gauge near Inlet Hole",
            },
            {
                "id": 6,
                "name": "LP Go",
                "gauge_class": "U Gauge",
                "part_class": "Outlet Hole",
                "method": "near",
                "near_distance_threshold": 60,
                "require_movement": True,
                "u_gauge_rank": 2,             # third from top
                "description": "LP Go U-Gauge near Outlet Hole",
            },
            {
                "id": 7,
                "name": "LP NoGo",
                "gauge_class": "U Gauge",
                "part_class": "Outlet Hole",
                "method": "near",
                "near_distance_threshold": 60,
                "require_movement": True,
                "u_gauge_rank": 3,             # bottom-most resting position
                "description": "LP NoGo U-Gauge near Outlet Hole",
            },
        ],
    },
}

# ─── Backward-Compatibility Aliases ──────────────────────────────────────────
# These keep the existing code in app.py / yolo_detector.py working without
# changes until the refactor is complete. They always reflect the TML profile.
_TML = PROFILES["TML"]
MODEL_PATH        = _TML["model_path"]
MODEL_ENGINE_PATH = _TML["engine_path"]
GAUGE_CLASSES     = _TML["gauge_classes"]
PART_CLASSES      = _TML["part_classes"]
CLASS_NAMES       = _TML["class_names"]
GAUGE_CHECKPOINTS = _TML["checkpoints"]

# Default active profile
DEFAULT_PROFILE = "TML"
