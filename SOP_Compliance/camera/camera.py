"""
Camera module — provides a unified abstraction for live camera,
pre-recorded video files, and demo mode.

Designed to be swappable without affecting detection or SOP logic.
"""

import threading
import time
import logging
from typing import Optional

import cv2
import numpy as np

logger = logging.getLogger(__name__)


class Camera:
    """
    Thread-safe camera/video capture abstraction.

    Modes:
        "live"  — OpenCV webcam via VideoCapture(index)
        "video" — Pre-recorded video file (loops at end)
        "demo"  — Generates blank frames with a grid pattern
    """

    def __init__(
        self,
        mode: str = "demo",
        source: Optional[str] = None,
        camera_index: int = 0,
    ):
        self.mode = mode
        self.source = source          # video file path (for "video" mode)
        self.camera_index = camera_index
        self._cap: Optional[cv2.VideoCapture] = None
        self._frame: Optional[np.ndarray] = None
        self._lock = threading.Lock()
        self._running = False
        self._thread: Optional[threading.Thread] = None
        self._connected = False
        self._fps = 30.0
        self._frame_count = 0

    # ─── Public API ──────────────────────────────────────────────────────

    def start(self) -> bool:
        """Start the camera capture thread."""
        if self._running:
            logger.warning("Camera already running.")
            return True

        success = self._open_source()
        if not success and self.mode != "demo":
            logger.error(f"Failed to open camera source: mode={self.mode}")
            # Fall back to demo mode
            self.mode = "demo"
            self._connected = False

        self._running = True
        self._thread = threading.Thread(target=self._capture_loop, daemon=True)
        self._thread.start()
        logger.info(f"Camera started in '{self.mode}' mode.")
        return True

    def stop(self) -> None:
        """Stop the camera and release resources."""
        self._running = False
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=3.0)
        self._release()
        logger.info("Camera stopped.")

    def get_frame(self) -> Optional[np.ndarray]:
        """Return the latest frame (thread-safe copy)."""
        with self._lock:
            if self._frame is not None:
                return self._frame.copy()
        return None

    def switch_source(self, mode: str, source: Optional[str] = None) -> bool:
        """Switch the video source at runtime."""
        logger.info(f"Switching camera source: {mode} (source={source})")
        was_running = self._running
        if was_running:
            self.stop()

        self.mode = mode
        self.source = source
        self._frame_count = 0

        if was_running:
            return self.start()
        return True

    @property
    def is_connected(self) -> bool:
        return self._connected

    @property
    def fps(self) -> float:
        return self._fps

    @property
    def frame_count(self) -> int:
        return self._frame_count

    # ─── Private ─────────────────────────────────────────────────────────

    def _open_source(self) -> bool:
        """Open the appropriate video source based on mode."""
        self._release()

        if self.mode == "live":
            # If a source is provided (like an RTSP URL), use it. Otherwise fallback to camera index.
            capture_target = self.source if self.source else self.camera_index
            self._cap = cv2.VideoCapture(capture_target)
            if not self._cap.isOpened():
                logger.error(f"Cannot open camera source {capture_target}")
                self._connected = False
                return False
            self._fps = self._cap.get(cv2.CAP_PROP_FPS) or 30.0
            self._connected = True
            return True

        elif self.mode == "video":
            if not self.source:
                logger.error("Video mode requires a source file path.")
                return False
            self._cap = cv2.VideoCapture(self.source)
            if not self._cap.isOpened():
                logger.error(f"Cannot open video file: {self.source}")
                self._connected = False
                return False
            self._fps = self._cap.get(cv2.CAP_PROP_FPS) or 30.0
            self._connected = True
            return True

        elif self.mode == "demo":
            self._connected = True
            self._fps = 30.0
            return True

        else:
            logger.error(f"Unknown camera mode: {self.mode}")
            return False

    def _release(self) -> None:
        """Release the OpenCV capture object."""
        if self._cap is not None:
            self._cap.release()
            self._cap = None
        self._connected = False

    def _capture_loop(self) -> None:
        """Background thread that continuously reads frames."""
        while self._running:
            try:
                if self.mode == "demo":
                    frame = self._generate_demo_frame()
                    with self._lock:
                        self._frame = frame
                    self._frame_count += 1
                    time.sleep(1.0 / self._fps)
                    continue

                if self._cap is None or not self._cap.isOpened():
                    self._connected = False
                    time.sleep(0.5)
                    continue

                ret, frame = self._cap.read()
                if not ret:
                    if self.mode == "video":
                        # Loop the video
                        self._cap.set(cv2.CAP_PROP_POS_FRAMES, 0)
                        continue
                    else:
                        logger.warning("Camera frame read failed.")
                        self._connected = False
                        time.sleep(0.1)
                        continue

                self._connected = True
                with self._lock:
                    self._frame = frame
                self._frame_count += 1

                # Pacing for video mode to match original FPS
                if self.mode == "video":
                    time.sleep(1.0 / max(self._fps, 1.0))

            except Exception as e:
                logger.error(f"Camera capture error: {e}")
                time.sleep(0.5)

    def _generate_demo_frame(self) -> np.ndarray:
        """Create a synthetic demo frame with a grid pattern."""
        frame = np.zeros((720, 1280, 3), dtype=np.uint8)
        frame[:] = (30, 30, 30)  # Dark gray background

        # Draw grid
        for x in range(0, 1280, 80):
            cv2.line(frame, (x, 0), (x, 720), (50, 50, 50), 1)
        for y in range(0, 720, 80):
            cv2.line(frame, (0, y), (1280, y), (50, 50, 50), 1)

        # "DEMO MODE" text
        cv2.putText(
            frame,
            "DEMO MODE",
            (440, 340),
            cv2.FONT_HERSHEY_SIMPLEX,
            2.0,
            (0, 200, 255),
            3,
            cv2.LINE_AA,
        )
        cv2.putText(
            frame,
            "No camera / video source active",
            (370, 400),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.8,
            (150, 150, 150),
            1,
            cv2.LINE_AA,
        )

        return frame
