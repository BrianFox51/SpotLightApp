"""SpotLight trailer / clip window, version 2 (compare with trailer_window.py).

Usage:   python trailer_window2.py SOURCE "Window title"
SOURCE can be:
  - a YouTube video id            e.g.  dQw4w9WgXcQ         -> YouTube's own player (muted, looping, click to unmute)
  - a local video file            e.g.  C:\\clips\\trailer.mp4 -> HTML5 player with sound controls (muted start, looping)
  - a direct http(s) video link   e.g.  https://example.com/clip.mp4

Needs the optional package:  pip install pywebview   (uses the Edge WebView2 runtime that ships with Windows 10/11).
If pywebview is missing, it falls back: YouTube ids open in your browser, local files open in your default video player."""
import os, re, sys, html, threading, http.server, socketserver, webbrowser

TYPES = {".mp4": "video/mp4", ".m4v": "video/mp4", ".mov": "video/mp4", ".webm": "video/webm", ".ogv": "video/ogg"}


def kind_of(src):
    if os.path.isfile(src): return "file"
    if re.match(r"^https?://", src): return "url"
    return "youtube"


def page(src, kind, title):
    t = html.escape(title)
    if kind == "youtube":
        body = (f'<iframe style="position:fixed;inset:0;width:100%;height:100%;border:0" '
                f'src="https://www.youtube.com/embed/{src}?autoplay=1&mute=1&loop=1&playlist={src}&rel=0&playsinline=1" '
                f'allow="autoplay; encrypted-media; picture-in-picture; fullscreen" referrerpolicy="strict-origin-when-cross-origin" allowfullscreen></iframe>')
    else:
        url = "/video" if kind == "file" else html.escape(src, quote=True)
        body = (f'<video style="position:fixed;inset:0;width:100%;height:100%;background:#000" src="{url}" autoplay muted loop controls playsinline></video>')
    return f'<!doctype html><meta charset="utf-8"><title>{t}</title><body style="margin:0;background:#000">{body}'.encode("utf-8")


def make_handler(src, kind, title):
    PAGE = page(src, kind, title)

    class H(http.server.BaseHTTPRequestHandler):
        def log_message(self, *a): pass

        def do_GET(self):
            if self.path.startswith("/video") and kind == "file": return self.send_video()
            self.send_response(200); self.send_header("Content-Type", "text/html; charset=utf-8"); self.send_header("Content-Length", str(len(PAGE)))
            self.end_headers(); self.wfile.write(PAGE)

        def send_video(self):
            """Serves the file with Range support (needed for looping and seeking in the browser engine)."""
            size = os.path.getsize(src); start, end = 0, size - 1; rng = self.headers.get("Range"); m = re.match(r"bytes=(\d*)-(\d*)", rng or "")
            if m:
                a, b = m.groups()
                if a: start = int(a); end = int(b) if b else size - 1
                elif b: start = max(0, size - int(b))
            end = min(end, size - 1)
            self.send_response(206 if m else 200)
            self.send_header("Content-Type", TYPES.get(os.path.splitext(src)[1].lower(), "video/mp4")); self.send_header("Accept-Ranges", "bytes")
            self.send_header("Content-Length", str(end - start + 1))
            if m: self.send_header("Content-Range", f"bytes {start}-{end}/{size}")
            self.end_headers()
            try:
                with open(src, "rb") as f:
                    f.seek(start); left = end - start + 1
                    while left > 0:
                        chunk = f.read(min(65536, left))
                        if not chunk: break
                        self.wfile.write(chunk); left -= len(chunk)
            except (BrokenPipeError, ConnectionResetError, ConnectionAbortedError): pass
    return H


class Server(socketserver.ThreadingMixIn, http.server.HTTPServer): daemon_threads = True


def fallback(src, kind):
    if kind == "youtube": webbrowser.open("https://www.youtube.com/watch?v=" + src)
    elif kind == "url": webbrowser.open(src)
    elif hasattr(os, "startfile"): os.startfile(src)
    else: webbrowser.open("file://" + os.path.abspath(src))


def main():
    if len(sys.argv) < 2: print(__doc__); return
    src, title = sys.argv[1], (sys.argv[2] if len(sys.argv) > 2 else "SpotLight")
    kind = kind_of(src)
    try: import webview
    except ImportError: return fallback(src, kind)
    srv = Server(("127.0.0.1", 0), make_handler(src, kind, title)); threading.Thread(target=srv.serve_forever, daemon=True).start()
    webview.create_window(title, f"http://127.0.0.1:{srv.server_address[1]}/", width=1100, height=640, background_color="#000000")
    webview.start()


if __name__ == "__main__":
    main()
