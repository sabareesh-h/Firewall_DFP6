"""
YOLO Detector module — wraps Ultralytics YOLO for object detection.

This module is ONLY responsible for running inference and returning
structured detection results. It does NOT make SOP decisions.
"""

import logging
import os
from typing import List, Dict, Any, Optional

import cv2
import numpy as np

logger = logging.getLogger(__name__)


class YOLODetector:
    """
    Wrapper around Ultralytics YOLO model.

    Returns structured detection dicts without any SOP logic.
    """

    def __init__(
        self,
        model_path: str,
        confidence_threshold: float = 0.50,
        iou_threshold: float = 0.45,
        imgsz: int = 640,
    ):
        self.model_path = model_path
        self.confidence_threshold = confidence_threshold
        self.iou_threshold = iou_threshold
        self.imgsz = imgsz
        self.model = None
        self.class_names: Dict[int, str] = {}
        self._available = False

        self._load_model()

    def _load_model(self) -> None:
        """Load the YOLO model. Handles missing model gracefully."""
        if not os.path.exists(self.model_path):
            logger.error(f"YOLO model not found: {self.model_path}")
            self._available = False
            return

        try:
            from ultralytics import YOLO
            self.model = YOLO(self.model_path)
            self.class_names = self.model.names
            self._available = True
            logger.info(
                f"YOLO model loaded: {self.model_path} "
                f"({len(self.class_names)} classes)"
            )
        except Exception as e:
            logger.error(f"Failed to load YOLO model: {e}")
            self._available = False

    @property
    def is_available(self) -> bool:
        return self._available

    def detect(self, frame: np.ndarray) -> List[Dict[str, Any]]:
        """
        Run YOLO inference on a frame.

        Returns:
            List of detection dicts:
            [
                {
                    "class_id": int,
                    "class_name": str,
                    "confidence": float,
                    "bbox": [x1, y1, x2, y2]   # pixel coords
                },
                ...
            ]
        """
        if not self._available or self.model is None:
            return []

        if frame is None or frame.size == 0:
            return []

        try:
            results = self.model(
                frame,
                conf=self.confidence_threshold,
                iou=self.iou_threshold,
                imgsz=self.imgsz,
                verbose=False,
            )

            detections = []
            for result in results:
                if result.boxes is None:
                    continue
                for box in result.boxes:
                    cls_id = int(box.cls[0])
                    conf = float(box.conf[0])
                    x1, y1, x2, y2 = box.xyxy[0].tolist()

                    detections.append({
                        "class_id": cls_id,
                        "class_name": self.class_names.get(cls_id, f"class_{cls_id}"),
                        "confidence": round(conf, 3),
                        "bbox": [int(x1), int(y1), int(x2), int(y2)],
                    })

            return detections

        except Exception as e:
            logger.error(f"YOLO inference error: {e}")
            return []

    def draw_detections(
        self,
        frame: np.ndarray,
        detections: List[Dict[str, Any]],
        gauge_classes: Optional[set] = None,
        part_classes: Optional[set] = None,
    ) -> np.ndarray:
        """
        Draw bounding boxes and labels on the frame.

        Color coding:
            Gauges  → Green (#00FF88)
            Parts   → Cyan  (#00CCFF)
            Other   → White
        """
        annotated = frame.copy()

        for det in detections:
            x1, y1, x2, y2 = det["bbox"]
            name = det["class_name"]
            conf = det["confidence"]
            label = f"{name} {conf:.2f}"

            # Choose color based on class type
            if gauge_classes and name in gauge_classes:
                color = (136, 255, 0)    # Green for gauges (BGR)
                text_bg = (20, 80, 0)
            elif part_classes and name in part_classes:
                color = (255, 204, 0)    # Cyan for parts (BGR)
                text_bg = (80, 60, 0)
            else:
                color = (255, 255, 255)
                text_bg = (60, 60, 60)

            # Draw bounding box
            cv2.rectangle(annotated, (x1, y1), (x2, y2), color, 2)

            # Draw label background
            (tw, th), _ = cv2.getTextSize(
                label, cv2.FONT_HERSHEY_SIMPLEX, 0.55, 1
            )
            cv2.rectangle(
                annotated,
                (x1, y1 - th - 10),
                (x1 + tw + 8, y1),
                text_bg,
                -1,
            )

            # Draw label text
            cv2.putText(
                annotated,
                label,
                (x1 + 4, y1 - 5),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.55,
                color,
                1,
                cv2.LINE_AA,
            )

        return annotated
