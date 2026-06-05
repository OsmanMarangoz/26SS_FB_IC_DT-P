"""
stream_viewer.py — reCamera Feed im Browser (latenz-optimiert, nur zum Testen).

Start auf dem Pi:
    source .venv/bin/activate
    python3 stream_viewer.py

Dann im Browser auf dem Laptop:
    http://robopi2.local:8080

Latenz messen: Kamera auf eine Stopuhr (Handy) richten und die Zahl im Bild
mit der echten Uhr vergleichen — das Overlay zeigt unten die Pi-Zeit beim
Aufnehmen inkl. Millisekunden.
"""

from __future__ import annotations

import subprocess
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import cv2
import numpy as np

# ── Config ──────────────────────────────────────────────────────────────────
# USB-C an den Pi  → rtsp://admin:admin@192.168.42.1:554/live
# WLAN/Ethernet    → rtsp://admin:admin@<Router-IP>:554/live
RTSP_URL    = "rtsp://admin:admin@192.168.188.193:554/live"
TRANSPORT   = "udp"          # "udp" = niedrigste Latenz, "tcp" = robuster (keine Artefakte)

# Ausgabe-/Decode-Auflösung. ffmpeg skaliert direkt hierauf — kein extra resize.
# Kleiner = weniger Decode-Last auf dem Pi = weniger Latenz. 640x480 ruhig testen.
WIDTH       = 1280
HEIGHT      = 720
FRAME_BYTES = WIDTH * HEIGHT * 3
HTTP_PORT   = 8080

# ── Shared Frame ──────────────────────────────────────────────────────────────
_latest_jpeg = None
_frame_id    = 0             # zählt hoch pro neuem Frame → Handler schickt nur Neues
_lock        = threading.Lock()
_running     = True


def _read_exactly(stdout, n: int) -> bytes | None:
    """Genau n Bytes lesen (raw read bei bufsize=0 kann partiell liefern)."""
    buf = bytearray()
    while len(buf) < n:
        chunk = stdout.read(n - len(buf))
        if not chunk:
            return None
        buf.extend(chunk)
    return bytes(buf)


def _reader(proc):
    """Background thread: liest Frames von ffmpeg, konvertiert zu JPEG."""
    global _latest_jpeg, _frame_id
    while _running:
        raw = _read_exactly(proc.stdout, FRAME_BYTES)
        if raw is None:
            break
        # frombuffer ist read-only; cv2.putText braucht ein beschreibbares Array
        frame = np.frombuffer(raw, dtype=np.uint8).reshape((HEIGHT, WIDTH, 3)).copy()

        # Timestamp mit Millisekunden einblenden (zum Latenz-Messen)
        now = time.time()
        ts = time.strftime("%H:%M:%S") + f".{int((now % 1) * 1000):03d}"
        cv2.putText(frame, f"reCamera  {ts}", (10, 30),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 255, 0), 2)

        _, jpeg = cv2.imencode(".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, 75])
        with _lock:
            _latest_jpeg = jpeg.tobytes()
            _frame_id += 1


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
    <p>{RTSP_URL} [{TRANSPORT}] → {WIDTH}×{HEIGHT} MJPEG</p>
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
        last_sent = -1
        try:
            while _running:
                with _lock:
                    jpeg = _latest_jpeg
                    fid  = _frame_id

                # Nur senden, wenn es ein NEUES Frame gibt — kein 15-fps-Deckel,
                # keine doppelt gesendeten Standbilder → minimale Browser-Latenz.
                if jpeg is None or fid == last_sent:
                    time.sleep(0.002)
                    continue

                last_sent = fid
                self.wfile.write(
                    b"--frame\r\n"
                    b"Content-Type: image/jpeg\r\n\r\n"
                    + jpeg + b"\r\n"
                )
        except (BrokenPipeError, ConnectionResetError):
            pass  # Client hat Verbindung getrennt


def main():
    global _running

    print(f"Verbinde mit: {RTSP_URL} [{TRANSPORT}]")
    cmd = [
        "ffmpeg",
        "-rtsp_transport", TRANSPORT,
        "-fflags", "nobuffer+discardcorrupt",  # keine Eingangspufferung
        "-flags", "low_delay",                 # Decoder ohne Reorder-Wartezeit
        "-probesize", "32",                    # nicht lange "analysieren"
        "-analyzeduration", "0",               #   → schnellerer Start, weniger Latenz
        "-i", RTSP_URL,
        "-an",                                 # Audio wegwerfen
        "-vsync", "0",                         # keine fps-Angleichung/Pufferung
        "-vf", f"scale={WIDTH}:{HEIGHT}",      # direkt auf Zielgröße skalieren
        "-f", "rawvideo",
        "-pix_fmt", "bgr24",
        "pipe:1",
    ]
    # bufsize=0 → unbuffered; wir lesen die Pipe selbst exakt aus
    proc = subprocess.Popen(
        cmd, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, bufsize=0
    )

    reader_thread = threading.Thread(target=_reader, args=(proc,), daemon=True)
    reader_thread.start()

    print("Warte auf ersten Frame...")
    deadline = time.time() + 10.0
    while _latest_jpeg is None:
        if time.time() > deadline:
            print("❌ Kein Frame nach 10s.")
            proc.kill()
            return
        time.sleep(0.05)

    print("✅ Stream aktiv.")
    print("")
    print(f"   Browser öffnen:  http://robopi2.local:{HTTP_PORT}")
    print(f"   oder direkt:     http://<Pi-IP>:{HTTP_PORT}")
    print("")
    print("   Ctrl+C zum Beenden.")

    # ThreadingHTTPServer → HTML + Stream gleichzeitig, saubere Reconnects
    server = ThreadingHTTPServer(("0.0.0.0", HTTP_PORT), StreamHandler)
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