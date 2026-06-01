"""
recamera.py — LeRobot-kompatibler Kamera-Wrapper für die reCamera 2002.

Nutzt ffmpeg + RTSP statt OpenCV direkt, da OpenCV keine
fixen RTSP-Auflösungen per cap.set() ändern kann.
"""

import subprocess
import threading
import time
from dataclasses import dataclass, field

import numpy as np


@dataclass
class ReCameraConfig:
    """Konfiguration für die reCamera 2002 via RTSP."""
    rtsp_url: str = "rtsp://admin:admin@192.168.188.193:554/live"
    width: int = 1920
    height: int = 1080
    fps: int = 15


class ReCamera:
    """
    Kamera-Wrapper der reCamera 2002 für LeRobot.

    Liest Frames via ffmpeg aus dem RTSP-Stream.
    Implementiert die LeRobot Camera-Interface:
        connect(), disconnect(), read(), async_read()
    """

    def __init__(self, config: ReCameraConfig):
        self.config = config
        self.width = config.width
        self.height = config.height
        self.fps = config.fps

        self._latest_frame = None
        self._lock = threading.Lock()
        self._proc = None
        self._thread = None
        self._running = False

    def connect(self) -> None:
        """Startet ffmpeg-Prozess und wartet auf ersten Frame."""
        frame_bytes = self.width * self.height * 3

        cmd = [
            "ffmpeg",
            "-rtsp_transport", "udp",
            "-fflags", "+nobuffer+discardcorrupt",
            "-flags", "low_delay",
            "-i", self.config.rtsp_url,
            "-f", "rawvideo",
            "-pix_fmt", "bgr24",
            "-vf", f"scale={self.width}:{self.height}",
            "pipe:1"
        ]

        self._proc = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
        )
        self._running = True
        self._thread = threading.Thread(
            target=self._reader,
            args=(frame_bytes,),
            daemon=True,
            name="recamera_reader",
        )
        self._thread.start()

        print(f"[ReCamera] Warte auf ersten Frame von '{self.config.rtsp_url}'...")
        deadline = time.time() + 10.0
        while self._latest_frame is None:
            if time.time() > deadline:
                self._proc.kill()
                raise TimeoutError(
                    "[ReCamera] Kein Frame nach 10s. "
                    "Ist die reCamera erreichbar?"
                )
            time.sleep(0.05)

        print(f"[ReCamera] Verbunden: {self.width}x{self.height}@{self.fps}fps")

    def disconnect(self) -> None:
        """Stoppt ffmpeg-Prozess und Reader-Thread."""
        self._running = False
        if self._proc:
            self._proc.kill()
            self._proc = None
        if self._thread:
            self._thread.join(timeout=2.0)
            self._thread = None
        self._latest_frame = None
        print("[ReCamera] Getrennt.")

    def _reader(self, frame_bytes: int) -> None:
        """Background-Thread: liest kontinuierlich Frames von ffmpeg."""
        while self._running:
            raw = self._proc.stdout.read(frame_bytes)
            if not raw or len(raw) != frame_bytes:
                break
            frame = np.frombuffer(raw, dtype=np.uint8).reshape(
                (self.height, self.width, 3)
            )
            with self._lock:
                self._latest_frame = frame.copy()

    def async_read(self, timeout_ms: int = 200) -> np.ndarray:
        """
        Gibt den letzten verfügbaren Frame zurück.
        Wartet bis zu timeout_ms auf einen neuen Frame.
        """
        deadline = time.time() + timeout_ms / 1000.0
        while True:
            with self._lock:
                if self._latest_frame is not None:
                    return self._latest_frame.copy()
            if time.time() > deadline:
                raise TimeoutError(
                    f"[ReCamera] async_read timeout nach {timeout_ms}ms"
                )
            time.sleep(0.005)

    def read(self) -> np.ndarray:
        """Blockierender Frame-Read mit 5s Timeout."""
        return self.async_read(timeout_ms=5000)