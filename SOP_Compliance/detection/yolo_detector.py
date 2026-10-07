"""
YOLO Detector module — wraps Ultralytics YOLO for object detection.

This module is ONLY responsible for running inference and returning
structured detection results. It does NOT make SOP decisions.

Performance:
  • Automatically prefers a TensorRT .engine over .pt (3–5× faster).
    Generate it once with:  python export_tensorrt.py
  • No FP16 applied here — pure FP32 inference for correctness.
  • Per-call inference time is logged every 100 frames.
"""

import logging
import os
import time
from typing import List, Dict, Any, Optional

import cv2
import numpy as np

logger = logging.getLogger(__name__)


class YOLODetector:
    """
    Wrapper around Ultralytics YOLO model.

    Automatically prefers a TensorRT .engine over a raw .pt for speed.
    Returns structured detection dicts without any SOP logic.
    """

    def __init__(
        self,
        model_path: str,
        confidence_threshold: float = 0.50,
        iou_threshold: float = 0.45,
        imgsz: int = 1280,
        device: str = "0",
        engine_path: Optional[str] = None,
    ):
        self.model_path   = model_path
        self.engine_path  = engine_path
        self.confidence_threshold = confidence_threshold
        self.iou_threshold        = iou_threshold
        self.imgsz  = imgsz
        self.device = device
        self.model  = None
        self.class_names: Dict[int, str] = {}
        self._available  = False
        self._warmed_up  = False
        self._using_trt  = False

        # Inference timing (logged every N frames)
        self._infer_count   = 0
        self._infer_ms_sum  = 0.0
        self._LOG_EVERY     = 100

        self._load_model()

    # ─── Model Loading ───────────────────────────────────────────────────

    def _load_model(self) -> None:
        """
        Load YOLO model.  Prefers TensorRT .engine over .pt for speed.
        Falls back gracefully if either is missing.
        """
        try:
            from ultralytics import YOLO

            # 1. Try TensorRT engine first
            if self.engine_path and os.path.exists(self.engine_path):
                logger.info(f"Loading TensorRT engine: {self.engine_path}")
                self.model = YOLO(self.engine_path)
                self._using_trt = True
                load_path = self.engine_path

            # 2. Fall back to .pt
            elif os.path.exists(self.model_path):
                logger.info(f"Loading PyTorch model: {self.model_path}")
                self.model = YOLO(self.model_path)
                self._using_trt = False
                load_path = self.model_path

            else:
                logger.error(f"YOLO model not found: {self.model_path}")
                self._available = False
                return

            self.class_names = self.model.names
            self._available  = True
            backend = "TensorRT" if self._using_trt else "PyTorch"

            # ── Override class names with config.CLASS_NAMES ─────────
            # The model's embedded names may differ from what config.py
            # defines (e.g., trained with slightly different labels).
            # config.CLASS_NAMES is the single source of truth.
            import config as _cfg
            if hasattr(_cfg, "CLASS_NAMES") and _cfg.CLASS_NAMES:
                model_names = dict(self.class_names)  # copy original
                self.class_names = dict(_cfg.CLASS_NAMES)

                # Log any discrepancies so they're easy to debug
                for cid, cfg_name in _cfg.CLASS_NAMES.items():
                    model_name = model_names.get(cid)
                    if model_name and model_name != cfg_name:
                        logger.warning(
                            f"  Class {cid}: model='{model_name}' → "
                            f"config='{cfg_name}' (overridden)"
                        )

                logger.info(
                    f"Class names overridden from config.CLASS_NAMES "
                    f"({len(self.class_names)} classes)"
                )

            logger.info(
                f"YOLO model loaded [{backend}]: {load_path} "
                f"({len(self.class_names)} classes) | "
                f"imgsz={self.imgsz} | device={self.device}"
            )
            if not self._using_trt:
                logger.info(
                    "TIP: Run `python export_tensorrt.py` once for 3-5x "
                    "faster inference with zero accuracy loss."
                )

        except Exception as e:
            logger.error(f"Failed to load YOLO model: {e}")
            self._available = False

    # ─── Warm-up ─────────────────────────────────────────────────────────

    def _warmup(self) -> None:
        """
        Run one dummy inference to prime CUDA/TRT kernels.
        Called on first detect() inside the background inference thread.
        """
        try:
            dummy = np.zeros((self.imgsz, self.imgsz, 3), dtype=np.uint8)
            self.model.predict(
                dummy,
                imgsz=self.imgsz,
                device=self.device,
                verbose=False,
            )
            logger.info("YOLO GPU warm-up complete.")
        except Exception as e:
            logger.warning(f"YOLO warm-up failed (non-fatal): {e}")
        self._warmed_up = True

    # ─── Properties ──────────────────────────────────────────────────────

    @property
    def is_available(self) -> bool:
        return self._available

    @property
    def using_tensorrt(self) -> bool:
        return self._using_trt
        
    @property
    def deadzone(self) -> Optional[List[int]]:
        return getattr(self, "_deadzone", None)
        
    @deadzone.setter
    def deadzone(self, value: Optional[List[int]]):
        self._deadzone = value

    # ─── Inference ───────────────────────────────────────────────────────

    def detect(
        self,
        frame: np.ndarray,
        imgsz: Optional[int] = None,
    ) -> List[Dict[str, Any]]:
        """
        Run YOLO inference on a frame.

        Args:
            frame:  BGR image as numpy array.
            imgsz:  Override inference resolution (default: self.imgsz).

        Returns:
            List of detection dicts with class_id, class_name,
            confidence, and bbox [x1, y1, x2, y2].
        """
        if not self._available or self.model is None:
            return []
        if frame is None or frame.size == 0:
            return []

        if not self._warmed_up:
            self._warmup()

        effective_imgsz = imgsz if imgsz is not None else self.imgsz

        try:
            t0 = time.perf_counter()

            results = self.model.predict(
                frame,
                conf=self.confidence_threshold,
                iou=self.iou_threshold,
                imgsz=effective_imgsz,
                device=self.device,
                verbose=False,
            )

            elapsed_ms = (time.perf_counter() - t0) * 1000

            self._infer_ms_sum += elapsed_ms
            self._infer_count  += 1
            if self._infer_count >= self._LOG_EVERY:
                avg_ms  = self._infer_ms_sum / self._infer_count
                avg_fps = 1000.0 / avg_ms if avg_ms > 0 else 0
                backend = "TRT" if self._using_trt else "PT"
                logger.info(
                    f"[{backend}] Inference avg: {avg_ms:.1f} ms/frame "
                    f"→ {avg_fps:.1f} FPS (imgsz={effective_imgsz})"
                )
                self._infer_count  = 0
                self._infer_ms_sum = 0.0

            detections = []
            for result in results:
                if result.boxes is None:
                    continue
                for box in result.boxes:
                    cls_id = int(box.cls[0])
                    conf   = float(box.conf[0])
                    x1, y1, x2, y2 = box.xyxy[0].tolist()
                    
                    import config as _cfg
                    ignore_x = getattr(_cfg, "IGNORE_LEFT_OF_X", None)
                    cx, cy = (x1 + x2) / 2, (y1 + y2) / 2
                    
                    if ignore_x is not None and cx < ignore_x:
                        continue
                    
                    if self.deadzone and len(self.deadzone) == 4:
                        dx1, dy1, dx2, dy2 = self.deadzone
                        if dx1 <= cx <= dx2 and dy1 <= cy <= dy2:
                            continue

                    detections.append({
                        "class_id":   cls_id,
                        "class_name": self.class_names.get(cls_id, f"class_{cls_id}"),
                        "confidence": round(conf, 3),
                        "bbox":       [int(x1), int(y1), int(x2), int(y2)],
                    })

            return detections

        except Exception as e:
            logger.error(f"YOLO inference error: {e}")
            return []

    # ─── Annotation ──────────────────────────────────────────────────────

    def draw_detections(
        self,
        frame: np.ndarray,
        detections: List[Dict[str, Any]],
        gauge_classes: Optional[set] = None,
        part_classes:  Optional[set] = None,
        show_conf: bool = False
    ) -> np.ndarray:
        """Draw bounding boxes and labels on the frame with dynamic visibility."""
        annotated = frame.copy()

        # Find part boxes to determine which gauges are actively interacting
        part_boxes = [d["bbox"] for d in detections if part_classes and d["class_name"] in part_classes]

        for det in detections:
            x1, y1, x2, y2 = det["bbox"]
            name  = det["class_name"]
            conf  = det["confidence"]
            
            label = f"{name} {conf:.2f}" if show_conf else f"{name}"

            is_gauge = gauge_classes and name in gauge_classes
            is_part = part_classes and name in part_classes

            if is_gauge:
                color   = (136, 255, 0)
                text_bg = (20, 80, 0)
            elif is_part:
                color   = (255, 204, 0)
                text_bg = (80, 60, 0)
            else:
                color   = (255, 255, 255)
                text_bg = (60, 60, 60)

            # Check if gauge intersects with any part (makes it "active")
            is_active = not is_gauge  # parts and others are always active
            if is_gauge:
                for px1, py1, px2, py2 in part_boxes:
                    if not (x2 < px1 or x1 > px2 or y2 < py1 or y1 > py2):
                        is_active = True
                        break

            if not is_active:
                # Inactive gauge: draw a small crosshair and faint text to reduce clutter
                cx, cy = (x1 + x2) // 2, (y1 + y2) // 2
                cv2.drawMarker(annotated, (cx, cy), color, cv2.MARKER_CROSS, 10, 1)
                cv2.putText(annotated, label, (cx + 5, cy - 5), cv2.FONT_HERSHEY_SIMPLEX, 0.4, color, 1)
            else:
                # Active item: draw corner brackets instead of full boxes for a cleaner look
                length = 15
                thickness = 2
                
                # Top-left
                cv2.line(annotated, (x1, y1), (x1 + length, y1), color, thickness)
                cv2.line(annotated, (x1, y1), (x1, y1 + length), color, thickness)
                # Top-right
                cv2.line(annotated, (x2, y1), (x2 - length, y1), color, thickness)
                cv2.line(annotated, (x2, y1), (x2, y1 + length), color, thickness)
                # Bottom-left
                cv2.line(annotated, (x1, y2), (x1 + length, y2), color, thickness)
                cv2.line(annotated, (x1, y2), (x1, y2 - length), color, thickness)
                # Bottom-right
                cv2.line(annotated, (x2, y2), (x2 - length, y2), color, thickness)
                cv2.line(annotated, (x2, y2), (x2, y2 - length), color, thickness)

                # Draw label background and text
                (tw, th), _ = cv2.getTextSize(label, cv2.FONT_HERSHEY_SIMPLEX, 0.55, 1)
                cv2.rectangle(annotated, (x1, y1 - th - 10), (x1 + tw + 8, y1), text_bg, -1)
                cv2.putText(annotated, label, (x1 + 4, y1 - 5), cv2.FONT_HERSHEY_SIMPLEX, 0.55, color, 1, cv2.LINE_AA)

        return annotated
