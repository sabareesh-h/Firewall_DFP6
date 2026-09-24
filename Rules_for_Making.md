# Build a Computer Vision SOP Compliance System

I am building an industrial **SOP Compliance System** using Python, YOLO, OpenCV, and a web interface.

The purpose of this system is to verify whether an operator is correctly checking required gauges on a part.

## CORE CONCEPT

The system will receive a live camera frame.

YOLO will detect:

1. The specific inspection area of the part where a gauge needs to be checked.
2. The gauge itself.

The application logic will determine whether the detected gauge is correctly positioned within its required inspection area.

Basic logic:

```text
Camera
   ↓
Live Frame
   ↓
YOLO Detection
   ↓
Detect Inspection Area + Gauge
   ↓
Check Spatial Relationship
   ↓
Gauge correctly positioned?
   ├── YES → OK
   └── NO  → NG
   ↓
Display result on website
```

IMPORTANT:

YOLO should ONLY be responsible for object detection.

The SOP/business logic must be implemented separately in Python.

Do NOT put SOP decisions directly inside the YOLO detection code.

---

# 1. PROJECT STRUCTURE

Create the following initial structure:

```text
SOP_Compliance/
│
├── app.py
│
├── models/
│   └── dfp6.pt
│
├── camera/
│   ├── __init__.py
│   └── camera.py
│
├── detection/
│   ├── __init__.py
│   └── yolo_detector.py
│
├── logic/
│   ├── __init__.py
│   └── gauge_validator.py
│
└── frontend/
    ├── index.html
    ├── style.css
    └── app.js
```

Do not create database, authentication, advanced state machine, Docker, cloud deployment, or other unnecessary infrastructure yet.

We are building the first working prototype first.

---

# 2. TECHNOLOGY

Use:

* Python 3.11+
* Ultralytics YOLO
* OpenCV
* FastAPI
* Uvicorn
* HTML
* CSS
* Vanilla JavaScript

Do not use React unless absolutely necessary.

Keep the frontend simple and lightweight.

---

# 3. app.py

`app.py` should be the main application entry point.

It should initialize:

* Camera
* YOLO detector
* SOP logic
* FastAPI server

The architecture should be:

```text
Camera
   ↓
YOLO Detector
   ↓
Detection Results
   ↓
Gauge Validator
   ↓
Current Status
   ↓
FastAPI
   ↓
Frontend
```

Keep the modules independent.

Do not put all logic inside `app.py`.

---

# 4. camera/camera.py

Create a reusable Camera class.

It should provide functionality such as:

```python
camera = Camera()
camera.start()
frame = camera.get_frame()
camera.stop()
```

For the first prototype, support a normal OpenCV camera:

```python
cv2.VideoCapture(0)
```

However, design the class so that a Basler/IP/industrial camera can be added later without changing the YOLO or SOP logic.

The camera module should:

* Open the camera
* Read frames
* Handle camera connection failure
* Release the camera cleanly
* Provide the latest frame

Do not put YOLO logic inside this file.

---

# 5. detection/yolo_detector.py

Create a reusable YOLO detector class.

Use Ultralytics.

Example concept:

```python
from ultralytics import YOLO

class YOLODetector:

    def __init__(self, model_path):
        self.model = YOLO(model_path)

    def detect(self, frame):
        ...
```

The detector should return structured detection information.

For example:

```python
[
    {
        "class_id": 0,
        "class_name": "gauge",
        "confidence": 0.94,
        "bbox": [x1, y1, x2, y2]
    },
    {
        "class_id": 1,
        "class_name": "inspection_area",
        "confidence": 0.91,
        "bbox": [x1, y1, x2, y2]
    }
]
```

Do not determine OK/NG here.

The detector should only answer:

"What objects did YOLO detect?"

Add configurable confidence thresholds.

For example:

```python
confidence_threshold = 0.50
```

Make this easy to change.

---

# 6. logic/gauge_validator.py

This is the main SOP decision logic.

The validator receives detections from YOLO.

It must determine whether a gauge is correctly positioned relative to its required inspection area.

Initially implement:

### Method 1 — Gauge center inside inspection area

Calculate the center of the gauge bounding box:

```text
center_x = (x1 + x2) / 2
center_y = (y1 + y2) / 2
```

Check whether that point is inside the inspection-area bounding box.

Return:

```python
{
    "status": "OK"
}
```

or:

```python
{
    "status": "NG"
}
```

Also calculate overlap percentage because we will likely use this later.

The validator should return useful information such as:

```python
{
    "status": "OK",
    "gauge": "gauge",
    "inspection_area": "inspection_area",
    "confidence": 0.94,
    "overlap": 0.87
}
```

Use clear functions such as:

```python
calculate_overlap()
is_gauge_inside_area()
validate_gauge()
```

Keep this logic independent from FastAPI and the frontend.

---

# 7. IMPORTANT STATUS DESIGN

Do NOT only use OK and NG.

Use these initial states:

```text
WAITING
OK
NG
NO_GAUGE
NO_AREA
UNCERTAIN
```

For example:

```text
No inspection area detected
→ WAITING

Inspection area detected but gauge missing
→ NO_GAUGE


Gauge correctly positioned
→ OK
```

This will make debugging much easier.

---

Very Very Important, 

This is the logic for OK sequence:


If Distance gauge is inside TML part - OK
If Pin Gauge is on Top of drive Shaft Thread - OK
If Dia gauge near drive shaft thread - Ok
If M8 Thread goes on the left on top of the bracket hole area - OK
If M6 Thread Goes near the bracket Hole area - OK  
If Hydraulic Head is identified - OK
If M13 Gauge is intersects inlet gauge - OK
If M1 Thread is intersects outlet gauge  - OK 

This is also very Important: 

Which class is comes inside part and which class is gauge.

Part class:
  6: Drive Shaft Thread
  7: Bracket Hole Top
  8: Bracket Hole Side
  9: Pin Check
  10: Hydraulic Head
  11: Inlet Hole
  12: Outlet Hole
  13: TML Part (This is the part itself, other class will come inside it)

Gauges class:
  0: Distance
  1: Pin Gauge
  2: Dia Gauge
  3: M8 Thread
  4: M6 Thread
  5: 13mm Gauge




# 8. LIVE WEB INTERFACE

Create a simple industrial-style dashboard.

The page should contain:

### Header

```text
DELPHI TVS
SOP COMPLIANCE SYSTEM
DFP6
```

Show live:

```text
Date
Time
System status
```

---

# 9. CAMERA VIEW

Display the live camera frame.

The image should show YOLO bounding boxes.

For example:

```text
Inspection Area → bounding box
Gauge → bounding box
```

Display the class name and confidence.

Example:

```text
Gauge 0.94
Inspection Area 0.91
```

The processed frame should be visible in the browser.

---

# 10. GAUGE STATUS PANEL

On the right side, create a panel for gauge status.

Initially support one gauge, but design it so additional gauges can be added later.

Example:

```text
GAUGE STATUS

Gauge 1       🟢 OK
Gauge 2       🟡 WAITING
Gauge 3       🔴 NG
Gauge 4       ⚪ NOT CHECKED
```

Use colored status cards.

Green = OK

Yellow = WAITING / UNCERTAIN

Red = NG

Gray = NOT CHECKED

---

# 11. OVERALL STATUS

Display a large overall status.

Example:

```text
OVERALL STATUS

        🟢 OK
```

or:

```text
        🔴 NG
```

For now:

```text
All required gauges OK
→ Overall OK

Any required gauge NG
→ Overall NG

Inspection not completed
→ IN PROGRESS
```

---

# 12. LIVE UPDATES

The webpage should update without manually refreshing.

Use a simple mechanism such as:

* WebSocket

or, if easier for the first prototype:

* periodic API polling

Prefer WebSocket if implementation remains simple.

The browser should receive current detection/status information from the Python backend.

---

# 13. API

Use FastAPI.

Create endpoints such as:

```text
GET /status
GET /video
POST /reset
```

`/status` should return something like:

```json
{
    "model": "DFP6",
    "overall_status": "OK",
    "gauges": {
        "G1": {
            "status": "OK",
            "confidence": 0.94,
            "overlap": 0.87
        }
    }
}
```

---

# 14. VIDEO STREAM

Create a browser-compatible live video stream from OpenCV.

A simple MJPEG stream is acceptable for the prototype.

Architecture:

```text
Camera
 ↓
OpenCV
 ↓
YOLO
 ↓
Draw bounding boxes
 ↓
MJPEG stream
 ↓
Browser
```

Do not send raw camera access to JavaScript.

The Python backend should control the camera.

---

# 15. FRONTEND

Use:

```text
index.html
style.css
app.js
```

### index.html

Create the dashboard structure.

### style.css

Create a clean professional industrial UI.

Use:

* dark/neutral background
* clear cards
* large status indicators
* readable fonts
* responsive layout

Do not over-design it.

The operator should be able to understand the status within one second.

### app.js

Handle:

* status updates
* gauge status
* overall status
* date/time
* API communication
* reset button

Keep JavaScript separate from HTML.

---

# 16. MODEL PATH

Use:

```text
models/dfp6.pt
```

However, if the model does not exist yet, do NOT crash the entire application during development.

Give a clear error such as:

```text
YOLO model not found:
models/dfp6.pt
```

and allow the web interface to start in DEMO mode if possible.

---

# 17. DEMO MODE

This is important.

Add a simple DEMO mode so the frontend can be developed even when:

* camera is disconnected
* YOLO model isn't available
* GPU isn't available

For example:

```text
DEMO MODE
```

can generate simulated:

```text
G1 → OK
G2 → OK
G3 → NG
```

This should be clearly marked in the UI.

Do not mix demo results with real inspection results.

---

# 18. ERROR HANDLING

The system must not silently fail.

Handle:

* Camera disconnected
* YOLO model missing
* YOLO inference error
* Invalid frame
* No detection
* Multiple gauges
* API failure

Show meaningful messages.

For example:

```text
CAMERA ERROR
YOLO MODEL ERROR
WAITING FOR PART
NO GAUGE DETECTED
```

---

# 19. PERFORMANCE

The system will eventually run continuously on an industrial PC.

Keep performance in mind.

Do not unnecessarily:

* copy images multiple times
* run YOLO repeatedly from different modules
* block the web server
* run expensive calculations unnecessarily

The camera/inference loop should run independently from frontend requests.

---

# 20. CODE QUALITY

Follow these rules:

* Use classes where appropriate.
* Use type hints.
* Add docstrings to important functions.
* Use clear variable names.
* Keep modules independent.
* Avoid global variables where possible.
* Add comments only where useful.
* Do not duplicate code.
* Keep configuration separate from logic.
* Make thresholds configurable.
* Do not hard-code product-specific rules inside YOLO code.

---

# 21. DO NOT IMPLEMENT YET

Do NOT implement these yet:

* Database
* User login
* Authentication
* Cloud deployment
* Docker
* Multiple product models
* Advanced tracking
* Production PLC integration
* Email notifications
* Historical analytics
* Complex state machine
* Advanced alarm system

We will add these later after the core pipeline works.

---

# 22. DEVELOPMENT PRIORITY

Build in this exact order:

### STEP 1

Create the folder structure.

### STEP 2

Implement camera capture.

### STEP 3

Implement YOLO detection.

### STEP 4

Display YOLO detection results on the live frame.

### STEP 5

Implement gauge/inspection-area spatial validation.

### STEP 6

Generate:

```text
OK
NG
WAITING
NO_GAUGE
NO_AREA
```

### STEP 7

Create FastAPI backend.

### STEP 8

Create frontend.

### STEP 9

Connect frontend to live backend status.

### STEP 10

Test the entire pipeline.

---

# 23. VERY IMPORTANT DEVELOPMENT RULE

Do not generate the entire application as one giant file.

Maintain this separation:

```text
Camera
    ↓
Detection
    ↓
Validation
    ↓
API
    ↓
Frontend
```

Each layer should have a single responsibility.

---

# 24. FIRST MILESTONE

The first successful milestone is:

```text
LIVE CAMERA
      ↓
YOLO
      ↓
Inspection Area detected
      +
Gauge detected
      ↓
Gauge position validated
      ↓
OK / NG
      ↓
Website shows result
```

Do not move to advanced features until this works reliably.

---

# 25. Before writing code

First inspect the project directory and tell me:

1. What files already exist.
2. What Python version is installed.
3. Whether Ultralytics is installed.
4. Whether OpenCV is installed.
5. Whether FastAPI is installed.
6. Whether a YOLO model exists in `models/`.
7. Whether a camera is available.
8. Whether CUDA/GPU is available.

Then propose any necessary dependency installation.

Do not overwrite existing files without checking them first.

After inspection, implement the project incrementally and explain what you changed.
