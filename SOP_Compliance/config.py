"""
Centralized configuration for SOP Compliance System.
All thresholds, class mappings, and validation rules live here.
"""

import os

# ─── Paths ────────────────────────────────────────────────────────────────────
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
MODEL_PATH = os.path.join(BASE_DIR, "models", "best_v2.pt")
FRONTEND_DIR = os.path.join(BASE_DIR, "frontend")

# Default video file for testing
DEFAULT_VIDEO_PATH = r"C:\Users\RohithSuryaCKM\Videos\Screen Recordings\Screen Recording 2026-09-24 155434.mp4"
# Hikvision Camera URL
# RTSP (raw stream):  rtsp://admin:Wedit@2024@192.168.1.66:554/Streaming/Channels/101
# HTTP (browser-like): http://admin:Wedit@2024@192.168.1.66/Streaming/Channels/101/httppreview
LIVE_CAMERA_URL = "rtsp://admin:Wedit@2024@192.168.1.66:554/Streaming/Channels/101"


# ─── YOLO Settings ───────────────────────────────────────────────────────────
CONFIDENCE_THRESHOLD = 0.10
IOU_THRESHOLD = 0.15
IMGSZ = 1024         # Must match what model was trained/predicted with
DEVICE = "0"         # "0" = GPU (CUDA device 0). Change to "cpu" if no GPU.

# Live-camera inference — same imgsz as training (must match)
LIVE_IMGSZ = 1024

# TensorRT compiled engine path (optional, created by export_tensorrt.py).
# If this file exists the detector will load it instead of best.pt and
# inference will be 3–5× faster with identical accuracy.
MODEL_ENGINE_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "models", "best.engine")

# ─── Class Definitions ───────────────────────────────────────────────────────
# Gauge classes (things the operator holds / uses)
GAUGE_CLASSES = {
    0: "Distance",
    1: "Pin",
    2: "Dia",
    3: "M6",
    4: "M8",
    5: "13mm",
    14: "11mm"
}

# Part classes (areas on the physical part being inspected)
PART_CLASSES = {
    6: "DS Thread",
    7: "Top",
    8: "Bracket Hole Side",
    9: "Pin Check",
    11: "In",
    12: "Out",
    13: "Part",
    15: "Hand"
}

# All class names by ID
CLASS_NAMES = {
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
    15: "Hand"
}

# ─── Gauge Validation Rules ──────────────────────────────────────────────────
# Each rule defines: which gauge must be near/inside which part area.
# "method" controls how spatial proximity is evaluated.
#
# From Rules_for_Making.md lines 331-338:
#   Distance gauge inside TML Part → OK
#   Pin Gauge on top of Drive Shaft Thread → OK
#   Dia Gauge near Drive Shaft Thread → OK
#   M8 Thread on left on top of Bracket Hole Top → OK
#   M6 Thread near Bracket Hole Side → OK
#   Hydraulic Head identified → OK (standalone)
#   13mm Gauge intersects Inlet Hole → OK
#   M1 Thread intersects Outlet Hole → OK  (NOTE: M1 not in class list, skipping)

GAUGE_CHECKPOINTS = [
    {
        "id": 1,
        "name": "Distance Gauge",
        "gauge_class": "Distance",
        "part_class": "Part",
        "method": "fully_inside",   # Gauge bbox must be entirely within Part bbox
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
]

# ─── Validation Thresholds ───────────────────────────────────────────────────
OVERLAP_THRESHOLD = 0.15          # Minimum IoU for "intersects" / "overlap" method
NEAR_DISTANCE_THRESHOLD = 50    # Max pixel distance for "near" method
OK_HOLD_FRAMES = 3               # Consecutive OK frames needed to latch a gauge as checked (kept for fallback)
OK_HOLD_SECONDS = 0.1            # Seconds gauge must stay valid on part before latching as checked

# ─── Part-Presence State Machine ─────────────────────────────────────────────
# When a gauge disappears from frame (operator moves it to the next spot),
# preserve its ok_count for this many frames before treating it as absent.
GAUGE_GRACE_FRAMES = 15          # ~0.5s grace — gauge stays "in progress" when moved away

# Frames TML Part must be absent before we treat it as "part removed"
# (operator removed the part from the table → auto-log + reset)
PART_ABSENT_PATIENCE = 45        # ~1.5s absent before auto-reset

# ─── Video Source ─────────────────────────────────────────────────────────────
# "live" | "video" | "demo"
DEFAULT_SOURCE = "video"

# Camera index for live mode
CAMERA_INDEX = 0

# ─── Server ───────────────────────────────────────────────────────────────────
HOST = "0.0.0.0"
PORT = 8000

# ─── Inference ────────────────────────────────────────────────────────────────
# Target FPS for inference loop (caps processing speed to reduce heat)
TARGET_FPS = 10

# ─── UI Labels ────────────────────────────────────────────────────────────────
APP_TITLE = "SOP Compliance Software"
APP_MODEL = "Fire Wall DFP6"
COMPANY_NAME = "Delphi-TVS Technologies Limited"
COMPANY_TAGLINE = "Tomorrow's Engineering Today"
APP_VERSION = "1.0.0"
