"""
recamera.py — Kamera-Wrapper mit Auto-Erkennung (latenz-optimiert).

Erkennt automatisch:
  - Fischertechnik USB-Kamera (/dev/video0)  → OpenCV
  - reCamera 2002 (RTSP)                      → ffmpeg

Beide liefern Frames als (H, W, 3) uint8 numpy arrays über dieselbe
LeRobot Camera-Schnittstelle: connect(), disconnect(), read(), async_read()

LATENZ — bitte lesen:
  Der größte Hebel ist NICHT dieser Code, sondern die Kamera-Konfiguration:
    1. reCamera direkt auf width x height @ fps streamen lassen (z.B. 640x480@30),
       damit der Pi KEIN 1080p dekodieren muss. Das spart CPU und Latenz.
    2. Falls einstellbar: kurzes GOP (Keyframe-Intervall ~= fps) und KEINE
       B-Frames (Baseline-Profil). B-Frames erzwingen Reordering = Latenz.
    3. Per Ethernet statt WLAN anbinden — WLAN-Jitter ist für Datasets giftig.
  Dieser Code minimiert zusätzlich jede Pufferung auf der Pi-Seite.
"""

from __future__ import annotations  # bytes | None Annotation auch auf Py3.9

import os
import subprocess
import threading
import time
from dataclasses import dataclass

import numpy as np


# ════════════════════════════════════════════════════════════════════════
#  Auto-Erkennung
# ════════════════════════════════════════════════════════════════════════

def detect_camera_type(usb_device: str = "/dev/video0") -> str:
    """'usb' wenn die Fischertechnik USB-Kamera da ist, sonst 'rtsp'."""
    if os.path.exists(usb_device):
        return "usb"
    return "rtsp"


# ════════════════════════════════════════════════════════════════════════
#  Config
# ════════════════════════════════════════════════════════════════════════

@dataclass
class ReCameraConfig:
    """
    camera_type:
        "auto" → automatisch (USB bevorzugt, sonst RTSP)
        "usb"  → Fischertechnik USB erzwingen
        "rtsp" → reCamera erzwingen
    """
    camera_type: str = "auto"

    # USB (Fischertechnik)
    usb_device: str = "/dev/video0"
    usb_index: int = 0

    # RTSP (reCamera)
    rtsp_url: str = "rtsp://admin:admin@192.168.188.193:554/live"
    # "udp" = niedrigste Latenz (kann bei Paketverlust Artefakte geben)
    # "tcp" = robuster / keine Artefakte, etwas mehr Latenz
    rtsp_transport: str = "udp"

    # Gemeinsam — IDEAL: identisch zur Stream-Auflösung der reCamera einstellen!
    width: int = 640
    height: int = 480
    fps: int = 30


# ════════════════════════════════════════════════════════════════════════
#  Kamera-Wrapper
# ════════════════════════════════════════════════════════════════════════

class ReCamera:
    def __init__(self, config: ReCameraConfig):
        self.config = config
        self.width = config.width
        self.height = config.height
        self.fps = config.fps

        if config.camera_type == "auto":
            self.camera_type = detect_camera_type(config.usb_device)
        else:
            self.camera_type = config.camera_type

        # USB state
        self._cap = None

        # RTSP state
        self._proc = None
        self._thread = None
        self._latest_frame = None
        self._lock = threading.Lock()
        self._running = False

    # ── Verbindung ─────────────────────────────────────────────────────

    def connect(self) -> None:
        if self.camera_type == "usb":
            self._connect_usb()
        else:
            self._connect_rtsp()

    def disconnect(self) -> None:
        if self.camera_type == "usb":
            self._disconnect_usb()
        else:
            self._disconnect_rtsp()

    # ── USB (Fischertechnik) ───────────────────────────────────────────

    def _connect_usb(self) -> None:
        import cv2

        print(f"[Camera] USB-Kamera erkannt: {self.config.usb_device}")
        # CAP_V4L2 explizit → zuverlässigere Property-Kontrolle unter Linux
        self._cap = cv2.VideoCapture(self.config.usb_index, cv2.CAP_V4L2)

        self._cap.set(cv2.CAP_PROP_FOURCC, cv2.VideoWriter_fourcc(*"YUYV"))
        self._cap.set(cv2.CAP_PROP_FRAME_WIDTH, self.width)
        self._cap.set(cv2.CAP_PROP_FRAME_HEIGHT, self.height)
        self._cap.set(cv2.CAP_PROP_FPS, self.fps)
        # Nur 1 Frame puffern → immer das aktuellste Bild (driver-abhängig)
        self._cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)

        time.sleep(2.0)  # Warmup

        ok, frame = self._cap.read()
        if not ok or frame is None:
            self._cap.release()
            raise RuntimeError(
                f"[Camera] USB-Kamera {self.config.usb_device} liefert keine Frames"
            )

        print(f"[Camera] USB verbunden: {frame.shape[1]}x{frame.shape[0]}@{self.fps}fps")

    def _disconnect_usb(self) -> None:
        if self._cap:
            self._cap.release()
            self._cap = None
        print("[Camera] USB getrennt.")

    # ── RTSP (reCamera) ────────────────────────────────────────────────

    def _connect_rtsp(self) -> None:
        frame_bytes = self.width * self.height * 3
        print(f"[Camera] RTSP (reCamera): {self.config.rtsp_url} "
              f"[{self.config.rtsp_transport}]")

        cmd = [
            "ffmpeg",
            "-rtsp_transport", self.config.rtsp_transport,
            "-fflags", "nobuffer+discardcorrupt",  # keine Eingangspufferung
            "-flags", "low_delay",                 # Decoder ohne Reorder-Wartezeit
            "-probesize", "32",                    # nicht erst lange "analysieren"
            "-analyzeduration", "0",               #   → spart Startup-Latenz
            "-i", self.config.rtsp_url,
            "-an",                                 # Audio (reCamera-Mic) wegwerfen
            "-vsync", "0",                         # keine fps-Angleichung/Pufferung
            "-vf", f"scale={self.width}:{self.height}",
            "-f", "rawvideo",
            "-pix_fmt", "bgr24",                   # BGR — passt zur OpenCV/USB-Seite
            "pipe:1",
        ]
        # bufsize=0 → unbuffered; wir lesen die Pipe selbst exakt aus
        self._proc = subprocess.Popen(
            cmd, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, bufsize=0
        )
        self._running = True
        self._thread = threading.Thread(
            target=self._rtsp_reader, args=(frame_bytes,), daemon=True
        )
        self._thread.start()

        print("[Camera] Warte auf ersten RTSP-Frame...")
        deadline = time.time() + 10.0
        while self._latest_frame is None:
            if time.time() > deadline:
                self._proc.kill()
                raise TimeoutError("[Camera] Kein RTSP-Frame nach 10s")
            time.sleep(0.05)

        print(f"[Camera] RTSP verbunden: {self.width}x{self.height}")

    def _read_exactly(self, n: int) -> bytes | None:
        """Genau n Bytes lesen (raw read bei bufsize=0 kann partiell liefern)."""
        buf = bytearray()
        stdout = self._proc.stdout
        while len(buf) < n:
            chunk = stdout.read(n - len(buf))
            if not chunk:          # EOF / ffmpeg beendet
                return None
            buf.extend(chunk)
        return bytes(buf)

    def _rtsp_reader(self, frame_bytes: int) -> None:
        """Hintergrund-Thread: hält immer NUR das neueste Frame vor."""
        while self._running:
            raw = self._read_exactly(frame_bytes)
            if raw is None:
                break
            # .copy() → eigenes, beschreibbares Array (frombuffer ist read-only)
            frame = np.frombuffer(raw, dtype=np.uint8).reshape(
                (self.height, self.width, 3)
            ).copy()
            with self._lock:
                self._latest_frame = frame  # alte Referenz wird verworfen

    def _disconnect_rtsp(self) -> None:
        self._running = False
        if self._proc:
            self._proc.kill()
            self._proc = None
        if self._thread:
            self._thread.join(timeout=2.0)
            self._thread = None
        self._latest_frame = None
        print("[Camera] RTSP getrennt.")

    # ── Frame lesen (einheitlich) ──────────────────────────────────────

    def async_read(self, timeout_ms: int = 200) -> np.ndarray:
        if self.camera_type == "usb":
            ok, frame = self._cap.read()
            if not ok or frame is None:
                raise TimeoutError("[Camera] USB-Frame konnte nicht gelesen werden")
            return frame

        # RTSP: das vom Reader-Thread vorgehaltene neueste Frame zurückgeben.
        # Kein zusätzliches copy() — der Reader ersetzt die Referenz, mutiert nie.
        deadline = time.time() + timeout_ms / 1000.0
        while True:
            with self._lock:
                if self._latest_frame is not None:
                    return self._latest_frame
            if time.time() > deadline:
                raise TimeoutError(
                    f"[Camera] RTSP async_read timeout nach {timeout_ms}ms"
                )
            time.sleep(0.001)

    def read(self) -> np.ndarray:
        return self.async_read(timeout_ms=5000)