"""
recamera.py — High-performance, low-latency USB camera driver for LeRobot.

Optimized for dual USB camera setups:
  - Threaded continuous frame grabbing (zero lag, eliminates V4L2 queue buildup)
  - Non-blocking async_read()
  - Automatic BGR -> RGB color conversion (LeRobot & PyTorch convention)
  - Automatic resolution validation and resizing fallback
  - MJPG FourCC encoding by default to prevent USB 2.0 bus bandwidth saturation
    when operating multiple cameras simultaneously.
"""

from __future__ import annotations

import os
import threading
import time
from dataclasses import dataclass

import numpy as np


@dataclass
class ReCameraConfig:
    """Configuration for physical USB camera."""
    # Device identification
    usb_device: str = "/dev/video0"
    usb_index: int = 0

    # Format & compression
    # "MJPG" is strongly recommended for dual USB cameras on Linux to avoid
    # USB 2.0 bus bandwidth limits. "YUYV" can be used for uncompressed streams.
    fourcc: str = "MJPG"

    # Frame properties
    width: int = 640
    height: int = 480
    fps: int = 30

    # Startup & timeouts
    warmup_s: float = 1.0
    connection_timeout_s: float = 10.0

    # Backward compatibility parameter (ignored, always USB)
    camera_type: str = "usb"


class ReCamera:
    """
    LeRobot-compatible Camera driver for USB webcams.
    Implements: connect(), disconnect(), read(), async_read().
    Returns frames as (H, W, 3) uint8 RGB numpy arrays.
    """

    def __init__(self, config: ReCameraConfig):
        self.config = config
        self.width = config.width
        self.height = config.height
        self.fps = config.fps

        self._cap = None
        self._thread = None
        self._running = False
        self._latest_frame = None
        self._lock = threading.Lock()

    # ── Connection ────────────────────────────────────────────────────────

    def connect(self) -> None:
        import cv2

        print(
            f"[USBCamera] Connecting to '{self.config.usb_device}' "
            f"(index={self.config.usb_index}, {self.width}x{self.height}@{self.fps}fps, {self.config.fourcc})..."
        )

        # 1. Try V4L2 backend with device index
        self._cap = cv2.VideoCapture(self.config.usb_index, cv2.CAP_V4L2)

        # Fallback to default backend if V4L2 fails
        if not self._cap.isOpened():
            print(f"[USBCamera] CAP_V4L2 open failed, trying default backend on index {self.config.usb_index}...")
            self._cap = cv2.VideoCapture(self.config.usb_index)

        # Fallback to device path if still not opened
        if not self._cap.isOpened() and os.path.exists(self.config.usb_device):
            print(f"[USBCamera] Trying device path '{self.config.usb_device}'...")
            self._cap = cv2.VideoCapture(self.config.usb_device, cv2.CAP_V4L2)

        if not self._cap.isOpened():
            raise RuntimeError(
                f"[USBCamera] Failed to open USB camera on index {self.config.usb_index} "
                f"or device '{self.config.usb_device}'. Check if device is connected and permissions allow access."
            )

        # Configure FourCC compression
        if self.config.fourcc:
            fourcc_code = cv2.VideoWriter_fourcc(*self.config.fourcc)
            self._cap.set(cv2.CAP_PROP_FOURCC, fourcc_code)

        self._cap.set(cv2.CAP_PROP_FRAME_WIDTH, self.width)
        self._cap.set(cv2.CAP_PROP_FRAME_HEIGHT, self.height)
        self._cap.set(cv2.CAP_PROP_FPS, self.fps)
        # Minimize driver buffer to reduce latency
        self._cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)

        # Warmup time for auto-exposure and sensor startup
        if self.config.warmup_s > 0:
            time.sleep(self.config.warmup_s)

        # Test read
        ok = False
        frame = None
        for _ in range(5):
            ok, frame = self._cap.read()
            if ok and frame is not None:
                break
            time.sleep(0.1)

        if not ok or frame is None:
            self._cap.release()
            raise RuntimeError(
                f"[USBCamera] Camera '{self.config.usb_device}' (idx {self.config.usb_index}) opened but returned no frames."
            )

        # Start background grabber thread
        self._running = True
        self._thread = threading.Thread(
            target=self._reader_loop, daemon=True, name=f"usb_cam_{self.config.usb_index}"
        )
        self._thread.start()

        # Wait for first processed RGB frame
        deadline = time.time() + self.config.connection_timeout_s
        while self._latest_frame is None:
            if time.time() > deadline:
                self.disconnect()
                raise TimeoutError(
                    f"[USBCamera] Timeout waiting for first frame from '{self.config.usb_device}'"
                )
            time.sleep(0.01)

        actual_h, actual_w = self._latest_frame.shape[:2]
        print(
            f"[USBCamera] Connected successfully: {actual_w}x{actual_h} RGB "
            f"('{self.config.usb_device}', index={self.config.usb_index})"
        )

    def disconnect(self) -> None:
        self._running = False
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=1.5)
            self._thread = None
        if self._cap:
            self._cap.release()
            self._cap = None
        self._latest_frame = None
        print(f"[USBCamera] Disconnected ('{self.config.usb_device}', index={self.config.usb_index}).")

    # ── Reader Thread ─────────────────────────────────────────────────────

    def _reader_loop(self) -> None:
        """Background thread: continuously grabs latest frame and converts to RGB."""
        import cv2

        while self._running:
            if not self._cap or not self._cap.isOpened():
                time.sleep(0.01)
                continue

            ok, frame = self._cap.read()
            if not ok or frame is None:
                time.sleep(0.005)
                continue

            # Ensure resolution matches requested target exactly
            if (frame.shape[1], frame.shape[0]) != (self.width, self.height):
                frame = cv2.resize(frame, (self.width, self.height))

            # Convert BGR (OpenCV) to RGB (LeRobot standard)
            frame_rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)

            with self._lock:
                self._latest_frame = frame_rgb

    # ── Frame Access (LeRobot API) ────────────────────────────────────────

    def async_read(self, timeout_ms: int = 200) -> np.ndarray:
        """Return the freshest RGB frame immediately without blocking hardware."""
        deadline = time.time() + timeout_ms / 1000.0
        while True:
            with self._lock:
                if self._latest_frame is not None:
                    return self._latest_frame
            if time.time() > deadline:
                raise TimeoutError(
                    f"[USBCamera] async_read timeout after {timeout_ms}ms "
                    f"('{self.config.usb_device}', index={self.config.usb_index})"
                )
            time.sleep(0.001)

    def read(self) -> np.ndarray:
        """Blocking read with generous timeout."""
        return self.async_read(timeout_ms=5000)


# Backward compatibility alias
USBCamera = ReCamera
USBCameraConfig = ReCameraConfig