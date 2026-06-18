"""
usb_stream_viewer.py — Zeigt den Fischertechnik USB-Kamera Feed im Browser.

Start auf dem Pi:
    source .venv/bin/activate
    python3 usb_stream_viewer.py

Dann im Browser auf dem Laptop:
    http://robopi2.local:8080
"""

import threading
import time
from http.server import BaseHTTPRequestHandler, HTTPServer

import cv2

# ── Config ────────────────────────────────────────────────────────────────────
USB_INDEX = 0          # /dev/video0
WIDTH     = 640
HEIGHT    = 480
FPS       = 30
HTTP_PORT = 8080

# ── Shared Frame ──────────────────────────────────────────────────────────────
_latest_jpeg = None
_lock        = threading.Lock()
_running     = True


def _reader(cap):
    """Background thread: liest Frames von der USB-Kamera, konvertiert zu JPEG."""
    global _latest_jpeg
    while _running:
        ok, frame = cap.read()
        if not ok or frame is None:
            time.sleep(0.01)
            continue

        # Timestamp einblenden
        ts = time.strftime("%H:%M:%S")
        cv2.putText(frame, f"Fischertechnik USB  {ts}", (10, 30),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 0), 2)

        _, jpeg = cv2.imencode(".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, 80])
        with _lock:
            _latest_jpeg = jpeg.tobytes()


class StreamHandler(BaseHTTPRequestHandler):
    def log_message(self, format, *args):
        pass

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
    <title>Fischertechnik USB Camera</title>
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
    <h2>Fischertechnik USB Camera — Live Feed</h2>
    <img src="/stream" alt="Camera Stream">
    <p>/dev/video{USB_INDEX} → {WIDTH}x{HEIGHT} MJPEG</p>
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
                time.sleep(1 / FPS)
        except (BrokenPipeError, ConnectionResetError):
            pass


def main():
    global _running

    print(f"Öffne USB-Kamera /dev/video{USB_INDEX}...")
    cap = cv2.VideoCapture(USB_INDEX)
    cap.set(cv2.CAP_PROP_FOURCC, cv2.VideoWriter_fourcc(*"YUYV"))
    cap.set(cv2.CAP_PROP_FRAME_WIDTH, WIDTH)
    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, HEIGHT)
    cap.set(cv2.CAP_PROP_FPS, FPS)

    # Warmup
    time.sleep(2.0)

    ok, frame = cap.read()
    if not ok or frame is None:
        print("❌ Kamera liefert keine Frames. Steckt sie direkt am Pi (kein Hub)?")
        cap.release()
        return

    print(f"✅ Kamera offen: {frame.shape[1]}x{frame.shape[0]}")

    reader_thread = threading.Thread(target=_reader, args=(cap,), daemon=True)
    reader_thread.start()

    print(f"")
    print(f"   Browser öffnen:  http://robopi2.local:{HTTP_PORT}")
    print(f"   oder direkt:     http://<Pi-IP>:{HTTP_PORT}")
    print(f"")
    print(f"   Ctrl+C zum Beenden.")

    server = HTTPServer(("0.0.0.0", HTTP_PORT), StreamHandler)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nBeende...")
    finally:
        _running = False
        server.shutdown()
        reader_thread.join(timeout=2.0)
        cap.release()
        print("Beendet.")


if __name__ == "__main__":
    main()