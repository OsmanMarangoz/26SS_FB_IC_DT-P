"""
ros2_camera.py — LeRobot-Kamera, die einen Unity-gerenderten Feed von einem
ROS2 sensor_msgs/Image Topic liest. Drop-in-Ersatz für ReCamera.

Datenpfad:
    Unity Camera GameObject -> RenderTexture
        -> rosbridge / ROS-TCP publiziert sensor_msgs/Image
            -> ROS2-Topic (z.B. /unity/camera_top/image_raw)
                -> ROS2Camera abonniert hier
                    -> NemaArm.get_observation() liest async_read()

Gleiche Schnittstelle wie ReCamera: connect(), disconnect(), read(), async_read().
Liefert Frames als (H, W, 3) uint8 RGB numpy arrays.

Keine cv_bridge-Abhängigkeit — die Image-Nachricht wird manuell dekodiert.
Jede Kamera betreibt einen eigenen rclpy-Node + Executor + Thread, analog zu
NemaArm/UnityTeleoperator (mehrere Executoren koexistieren problemlos).
"""

from __future__ import annotations

import threading
import time
from dataclasses import dataclass

import numpy as np


@dataclass
class ROS2CameraConfig:
    # Topic, auf dem die Unity-Kamera publiziert (eines pro Kamera).
    image_topic: str = "/unity/camera_top/image_raw"

    # Zielgröße, die an LeRobot übergeben wird. Weicht das eingehende Bild ab,
    # wird skaliert (benötigt opencv, im Projekt ohnehin vorhanden).
    width: int = 640
    height: int = 480

    # Nur Metadaten/Logging; das Abo ist event-getrieben.
    fps: int = 30

    connection_timeout_s: float = 10.0


# Unterstützte sensor_msgs/Image Encodings -> (Kanäle, ist_BGR)
_ENCODINGS = {
    "rgb8":  (3, False),
    "bgr8":  (3, True),
    "rgba8": (4, False),
    "bgra8": (4, True),
}


class ROS2Camera:
    def __init__(self, config: ROS2CameraConfig):
        self.config = config
        self.width = config.width
        self.height = config.height
        self.fps = config.fps

        self._node = None
        self._executor = None
        self._thread = None
        self._sub = None

        self._latest_frame = None
        self._lock = threading.Lock()
        self._received_first = False

    # ── Verbindung ─────────────────────────────────────────────────────
    def connect(self) -> None:
        import rclpy
        from rclpy.executors import SingleThreadedExecutor
        from sensor_msgs.msg import Image

        if not rclpy.ok():
            rclpy.init()

        # Eindeutiger Node-Name, damit mehrere Kameras koexistieren können.
        safe = self.config.image_topic.strip("/").replace("/", "_")
        self._node = rclpy.create_node(f"lerobot_cam_{safe}")
        self._sub = self._node.create_subscription(
            Image, self.config.image_topic, self._callback, 10
        )

        self._executor = SingleThreadedExecutor()
        self._executor.add_node(self._node)
        self._thread = threading.Thread(
            target=self._executor.spin, daemon=True, name=f"cam_spin_{safe}"
        )
        self._thread.start()

        print(f"[ROS2Camera] Warte auf '{self.config.image_topic}'...")
        deadline = time.time() + self.config.connection_timeout_s
        while not self._received_first:
            if time.time() > deadline:
                raise TimeoutError(
                    f"[ROS2Camera] Kein Bild auf '{self.config.image_topic}' "
                    f"nach {self.config.connection_timeout_s}s.\n"
                    "Publiziert die Unity-Kamera? Läuft rosbridge/ROS-TCP?"
                )
            time.sleep(0.05)
        print(f"[ROS2Camera] Verbunden: {self.width}x{self.height} "
              f"({self.config.image_topic})")

    def disconnect(self) -> None:
        if self._executor:
            self._executor.shutdown(timeout_sec=2.0)
            self._executor = None
        if self._node:
            self._node.destroy_node()
            self._node = None
        if self._thread:
            self._thread.join(timeout=2.0)
            self._thread = None
        self._latest_frame = None
        self._received_first = False
        print(f"[ROS2Camera] Getrennt ({self.config.image_topic}).")

    # ── ROS2 Callback ──────────────────────────────────────────────────
    def _callback(self, msg) -> None:
        frame = self._decode(msg)
        with self._lock:
            self._latest_frame = frame
            self._received_first = True

    def _decode(self, msg) -> np.ndarray:
        enc = msg.encoding.lower()
        if enc not in _ENCODINGS:
            raise ValueError(
                f"[ROS2Camera] Encoding '{msg.encoding}' nicht unterstützt. "
                f"Unity-Publisher auf eines von {list(_ENCODINGS)} setzen."
            )
        channels, is_bgr = _ENCODINGS[enc]

        buf = np.frombuffer(msg.data, dtype=np.uint8)
        # Row-Stride (step) berücksichtigen (evtl. Padding), dann auf width kürzen.
        buf = buf.reshape(msg.height, msg.step)
        buf = buf[:, : msg.width * channels]
        img = buf.reshape(msg.height, msg.width, channels)

        if channels == 4:          # Alpha verwerfen
            img = img[:, :, :3]
        if is_bgr:                 # -> RGB (LeRobot-Konvention)
            img = img[:, :, ::-1]

        # Auf die von LeRobot erwartete Größe bringen.
        if (img.shape[0], img.shape[1]) != (self.height, self.width):
            import cv2
            img = cv2.resize(img, (self.width, self.height))

        return np.ascontiguousarray(img, dtype=np.uint8)

    # ── Frame lesen (gleiche API wie ReCamera) ─────────────────────────
    def async_read(self, timeout_ms: int = 200) -> np.ndarray:
        deadline = time.time() + timeout_ms / 1000.0
        while True:
            with self._lock:
                if self._latest_frame is not None:
                    return self._latest_frame
            if time.time() > deadline:
                raise TimeoutError(
                    f"[ROS2Camera] async_read timeout nach {timeout_ms}ms "
                    f"({self.config.image_topic})"
                )
            time.sleep(0.001)

    def read(self) -> np.ndarray:
        return self.async_read(timeout_ms=5000)