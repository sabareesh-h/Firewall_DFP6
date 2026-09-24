"""
Centralized configuration for SOP Compliance System.
All thresholds, class mappings, and validation rules live here.
"""

import os

# ─── Paths ────────────────────────────────────────────────────────────────────
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
MODEL_PATH = os.path.join(BASE_DIR, "models", "dfp6.pt")
FRONTEND_DIR = os.path.join(BASE_DIR, "frontend")

# Default video file for testing
DEFAULT_VIDEO_PATH = r"C:\Users\RohithSuryaCKM\Videos\Screen Recordings\Screen Recording 2026-09-18 153923.mp4"

# RTSP Stream URL for Hikvision / CCTV Cameras
# Example: rtsp://username:password@192.168.1.66:554/Streaming/Channels/101
LIVE_CAMERA_URL = ""


# ─── YOLO Settings ───────────────────────────────────────────────────────────
CONFIDENCE_THRESHOLD = 0.25
IOU_THRESHOLD = 0.45
IMGSZ = 1280

# ─── Class Definitions ───────────────────────────────────────────────────────
# Gauge classes (things the operator holds / uses)
GAUGE_CLASSES = {
    0: "Distance",
    1: "Pin Gauge",
    2: "Dia Gauge",
    3: "M8 Thread",
    4: "M6 Thread",
    5: "13mm Gauge",
}

# Part classes (areas on the physical part being inspected)
PART_CLASSES = {
    6: "Drive Shaft Thread",
    7: "Bracket Hole Top",
    8: "Bracket Hole Side",
    9: "Pin Check",
    10: "Hydraulic Head",
    11: "Inlet Hole",
    12: "Outlet Hole",
    13: "TML Part",
}

# All class names by ID
CLASS_NAMES = {
    0: "Distance",
    1: "Pin Gauge",
    2: "Dia Gauge",
    3: "M8 Thread",
    4: "M6 Thread",
    5: "13mm Gauge",
    6: "Drive Shaft Thread",
    7: "Bracket Hole Top",
    8: "Bracket Hole Side",
    9: "Pin Check",
    10: "Hydraulic Head",
    11: "Inlet Hole",
    12: "Outlet Hole",
    13: "TML Part",
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
        "part_class": "TML Part",
        "method": "intersects",       # TEMP: any bbox overlap → OK
        "description": "Distance gauge overlapping TML Part",
    },
    {
        "id": 2,
        "name": "Pin Gauge",
        "gauge_class": "Pin Gauge",
        "part_class": "TML Part",
        "method": "intersects",
        "description": "Pin Gauge overlapping TML Part",
    },
    {
        "id": 3,
        "name": "Dia Gauge",
        "gauge_class": "Dia Gauge",
        "part_class": "TML Part",
        "method": "intersects",
        "description": "Dia Gauge overlapping TML Part",
    },
    {
        "id": 4,
        "name": "M8 Thread",
        "gauge_class": "M8 Thread",
        "part_class": "TML Part",
        "method": "intersects",
        "description": "M8 Thread overlapping TML Part",
    },
    {
        "id": 5,
        "name": "M6 Thread",
        "gauge_class": "M6 Thread",
        "part_class": "TML Part",
        "method": "intersects",
        "description": "M6 Thread overlapping TML Part",
    },
    {
        "id": 6,
        "name": "Hydraulic Head",
        "gauge_class": None,
        "part_class": "Hydraulic Head",       # Looks specifically for Hydraulic Head
        "method": "exists",
        "description": "Hydraulic Head identified",
    },
    {
        "id": 7,
        "name": "13mm Gauge",
        "gauge_class": "13mm Gauge",
        "part_class": "TML Part",
        "method": "intersects",
        "description": "13mm Gauge overlapping TML Part",
    },
]

# ─── Validation Thresholds ───────────────────────────────────────────────────
OVERLAP_THRESHOLD = 0.15          # Minimum IoU for "intersects" / "overlap" method
NEAR_DISTANCE_THRESHOLD = 150    # Max pixel distance for "near" method
OK_HOLD_FRAMES = 3               # Consecutive OK frames needed to latch a gauge as checked

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
# Target FPS for inference loop (caps processing speed)
TARGET_FPS = 30

# ─── UI Labels ────────────────────────────────────────────────────────────────
APP_TITLE = "SOP Compliance Software"
APP_MODEL = "Fire Wall DFP6"
COMPANY_NAME = "Delphi-TVS Technologies Limited"
COMPANY_TAGLINE = "Safer. Greener. Together."
APP_VERSION = "1.0.0"
