
import os
import cv2
import torch
import threading
import time
from ultralytics import YOLO

# ==========================================
# 1. CONFIGURATION
# ==========================================

# Force RTSP-over-TCP to prevent UDP packet loss (smearing)
os.environ["OPENCV_FFMPEG_CAPTURE_OPTIONS"] = "rtsp_transport;tcp"

# Hikvision camera RTSP URL
CAMERA_IP = "192.168.1.66"
USERNAME = "admin"
PASSWORD = "Wedit@2024"

RTSP_URL = (
    f"rtsp://{USERNAME}:{PASSWORD}@{CAMERA_IP}:554"
    "/Streaming/Channels/101"
)

# Your trained YOLO model
MODEL_PATH = r"C:\Users\RohithSuryaCKM\Downloads\Projects\Image_detection\runs\detect\models\HMI_v2\weights\best.pt"

# ==========================================
# 2. LOAD YOLO MODEL
# ==========================================

device = 0 if torch.cuda.is_available() else "cpu"
print("Using device:", device)

model = YOLO(MODEL_PATH)

# ==========================================
# 3. THREADED RTSP STREAM
# ==========================================

class RTSPStream:
    def __init__(self, url):
        self.cap = cv2.VideoCapture(url, cv2.CAP_FFMPEG)
        self.cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
        self.ret = False
        self.frame = None
        self.running = False
        
        if self.cap.isOpened():
            self.ret, self.frame = self.cap.read()
            self.running = True
            self.thread = threading.Thread(target=self.update, daemon=True)
            self.thread.start()

    def update(self):
        while self.running:
            ret, frame = self.cap.read()
            if ret:
                self.ret = ret
                self.frame = frame
            else:
                time.sleep(0.01)

    def read(self):
        return self.ret, self.frame

    def release(self):
        self.running = False
        if hasattr(self, 'thread'):
            self.thread.join(timeout=1.0)
        self.cap.release()

stream = RTSPStream(RTSP_URL)

if not stream.running:
    print("ERROR: Cannot connect to Hikvision camera.")
    print("Check IP address, username, password and RTSP.")
    exit()

print("Hikvision camera connected!")
print("Starting YOLO detection...")

# ==========================================
# 4. REAL-TIME YOLO DETECTION
# ==========================================

while True:
    ret, frame = stream.read()

    if not ret or frame is None:
        print("Failed to read frame from camera")
        break

    # Run YOLO inference
    results = model.predict(
        source=frame,
        imgsz=1024,
        conf=0.40,
        device=device,
        verbose=False
    )

    # Draw bounding boxes and class names
    annotated_frame = results[0].plot()

    # Pre-scale for display so the window isn't huge on screen
    display_w = 960
    h, w = annotated_frame.shape[:2]
    if w > display_w:
        scale = display_w / w
        annotated_frame = cv2.resize(
            annotated_frame,
            (display_w, int(h * scale)),
            interpolation=cv2.INTER_LINEAR,
        )

    # Display live camera with detections
    cv2.imshow("Hikvision - YOLO Live Detection", annotated_frame)

    # Press Q to stop
    if cv2.waitKey(1) & 0xFF == ord("q"):
        break

# ==========================================
# 5. RELEASE RESOURCES
# ==========================================

stream.release()
cv2.destroyAllWindows()
print("YOLO detection stopped.")