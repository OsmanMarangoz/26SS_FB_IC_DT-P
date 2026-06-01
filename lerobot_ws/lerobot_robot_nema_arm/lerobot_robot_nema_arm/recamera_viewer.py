"""
stream_viewer.py — Zeigt den reCamera Feed im Browser.

Start auf dem Pi:
    source .venv/bin/activate
    python3 stream_viewer.py

Dann im Browser auf dem Laptop:
    http://robopi2.local:8080
"""

import subprocess
import threading
import time
from http.server import BaseHTTPRequestHandler, HTTPServer

import cv2
import numpy as np

# ── Config ────────────────────────────────────────────────────────────────────
RTSP_URL    = "rtsp://admin:admin@192.168.188.193:554/live"
WIDTH       = 1920
HEIGHT      = 1080
FRAME_BYTES = WIDTH * HEIGHT * 3
HTTP_PORT   = 8080

# ── Shared Frame ──────────────────────────────────────────────────────────────
_latest_jpeg = None
_lock        = threading.Lock()
_running     = True


def _reader(proc):
    """Background thread: liest Frames von ffmpeg, konvertiert zu JPEG."""
    global _latest_jpeg
    while _running:
        raw = proc.stdout.read(FRAME_BYTES)
        if not raw or len(raw) != FRAME_BYTES:
            break
        frame = np.frombuffer(raw, dtype=np.uint8).reshape((HEIGHT, WIDTH, 3))

        # Resize für flüssigeres Streaming im Browser (optional)
        display = cv2.resize(frame, (1280, 720))

        # Timestamp einblenden
        ts = time.strftime("%H:%M:%S")
        cv2.putText(display, f"reCamera  {ts}", (10, 30),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 255, 0), 2)

        _, jpeg = cv2.imencode(".jpg", display, [cv2.IMWRITE_JPEG_QUALITY, 75])
        with _lock:
            _latest_jpeg = jpeg.tobytes()


class StreamHandler(BaseHTTPRequestHandler):
    """HTTP Handler — liefert MJPEG Stream oder HTML-Seite."""

    def log_message(self, format, *args):
        pass  # HTTP Logs unterdrücken

    def do_GET(self):
        if self.path == "/":
            self._serve_html()
        elif self.path == "/stream":
            self._serve_mjpeg()
        else:
            self.send_response(404)
            self.end_headers()

    def _serve_html(self):
        html = f"""<!DOCTYPE html>
<html>
<head>
    <title>reCamera Live Feed</title>
    <style>
        body {{ background: #111; color: #eee; font-family: monospace;
               display: flex; flex-direction: column; align-items: center;
               justify-content: center; height: 100vh; margin: 0; }}
        h2 {{ margin-bottom: 12px; color: #0f0; }}
        img {{ border: 2px solid #0f0; max-width: 100%; }}
        p  {{ color: #888; font-size: 12px; margin-top: 8px; }}
    </style>
</head>
<body>
    <h2>reCamera 2002 — Live Feed</h2>
    <img src="/stream" alt="Camera Stream">
    <p>{RTSP_URL} → 1280×720 MJPEG</p>
</body>
</html>"""
        self.send_response(200)
        self.send_header("Content-Type", "text/html")
        self.end_headers()
        self.wfile.write(html.encode())

    def _serve_mjpeg(self):
        self.send_response(200)
        self.send_header("Content-Type",
                         "multipart/x-mixed-replace; boundary=frame")
        self.end_headers()
        try:
            while _running:
                with _lock:
                    jpeg = _latest_jpeg

                if jpeg is None:
                    time.sleep(0.05)
                    continue

                self.wfile.write(
                    b"--frame\r\n"
                    b"Content-Type: image/jpeg\r\n\r\n"
                    + jpeg + b"\r\n"
                )
                time.sleep(1 / 15)  # ~15 fps
        except (BrokenPipeError, ConnectionResetError):
            pass  # Client hat Verbindung getrennt


def main():
    global _running

    # ffmpeg starten
    print(f"Verbinde mit: {RTSP_URL}")
    cmd = [
        "ffmpeg",
        "-rtsp_transport", "udp",
        "-fflags", "+nobuffer+discardcorrupt",
        "-flags", "low_delay",
        "-i", RTSP_URL,
        "-f", "rawvideo",
        "-pix_fmt", "bgr24",
        "-vf", f"scale={WIDTH}:{HEIGHT}",
        "pipe:1"
    ]
    proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)

    reader_thread = threading.Thread(target=_reader, args=(proc,), daemon=True)
    reader_thread.start()

    # Auf ersten Frame warten
    print("Warte auf ersten Frame...")
    deadline = time.time() + 10.0
    while _latest_jpeg is None:
        if time.time() > deadline:
            print("❌ Kein Frame nach 10s.")
            proc.kill()
            return
        time.sleep(0.05)

    print(f"✅ Stream aktiv.")
    print(f"")
    print(f"   Browser öffnen:  http://robopi2.local:{HTTP_PORT}")
    print(f"   oder direkt:     http://<Pi-IP>:{HTTP_PORT}")
    print(f"")
    print(f"   Ctrl+C zum Beenden.")

    # HTTP Server starten
    server = HTTPServer(("0.0.0.0", HTTP_PORT), StreamHandler)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nBeende...")
    finally:
        _running = False
        server.shutdown()
        proc.kill()
        reader_thread.join(timeout=2.0)
        print("Beendet.")


if __name__ == "__main__":
    main()