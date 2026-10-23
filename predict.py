from ultralytics import YOLO

# Load trained model
model = YOLO(r"C:\Users\RohithSuryaCKM\Downloads\Projects\Image_detection\runs\detect\models\HMI_v14\weights\best.pt")

# Predict on prerecorded video
model.predict(
    source=r"C:\Users\RohithSuryaCKM\Videos\Screen Recordings\Screen Recording 2026-10-12 103648.mp4",  # Video file path
    conf=0.2,             # Confidence threshold: 20%
    show=True,             # Display predictions
    save=True,             # Save output video
    imgsz=1024,
    verbose=False
)