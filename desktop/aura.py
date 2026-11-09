"""AURA — desktop launcher for ChessLab 1800.

Starts the FastAPI backend on a free local port and opens it in a native window (pywebview:
Edge WebView2 on Windows, Qt WebEngine/GTK on Linux). If no native window toolkit is available,
it opens your default browser instead. Data lives in your user profile, not next to the app:
  Windows: %LOCALAPPDATA%\\AURA      Linux: ~/.local/share/aura

    python desktop/aura.py               # dev run from the repo
    AURA.exe / ./AURA                    # packaged app
    --browser   open in the default browser instead of a window
    --headless  only run the server (prints the URL), for testing
"""
from __future__ import annotations

import argparse
import logging
import os
import socket
import subprocess
import sys
import threading
import time
import urllib.request
import webbrowser
from pathlib import Path

APP_NAME = "AURA"
FROZEN = getattr(sys, "frozen", False)
BUNDLE = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent.parent))


def user_data_dir() -> Path:
    if os.name == "nt":
        base = Path(os.getenv("LOCALAPPDATA") or Path.home() / "AppData" / "Local")
        d = base / APP_NAME
    else:
        d = Path(os.getenv("XDG_DATA_HOME") or Path.home() / ".local" / "share") / APP_NAME.lower()
    d.mkdir(parents=True, exist_ok=True)
    return d


def configure_env() -> Path:
    data = user_data_dir()
    os.environ.setdefault("CHESSLAB_DATA_DIR", str(data))
    if FROZEN:
        os.environ.setdefault("FRONTEND_DIST", str(BUNDLE / "frontend_dist"))
        exe = "stockfish.exe" if os.name == "nt" else "stockfish"
        bundled = BUNDLE / "stockfish" / exe
        if bundled.exists() and not os.getenv("STOCKFISH_PATH"):
            os.environ["STOCKFISH_PATH"] = str(bundled)
    else:
        sys.path.insert(0, str(BUNDLE / "backend"))
    return data


def free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def wait_ready(url: str, timeout: float = 30) -> bool:
    end = time.time() + timeout
    while time.time() < end:
        try:
            with urllib.request.urlopen(url + "/api/health", timeout=2):
                return True
        except Exception:
            time.sleep(0.2)
    return False


def run_window(url: str) -> int:
    try:
        import webview

        webview.create_window(APP_NAME, url, width=1440, height=920, min_size=(380, 600), background_color="#111214")
        webview.start()
        return 0
    except Exception as exc:  # no WebView2 / Qt / GTK available
        print(f"native window unavailable: {exc}", file=sys.stderr)
        return 3


def main() -> int:
    ap = argparse.ArgumentParser(prog=APP_NAME)
    ap.add_argument("--browser", action="store_true")
    ap.add_argument("--headless", action="store_true")
    ap.add_argument("--port", type=int, default=0)
    ap.add_argument("--window", metavar="URL", help=argparse.SUPPRESS)  # internal: child window process
    args = ap.parse_args()
    if args.window:
        return run_window(args.window)

    data = configure_env()
    logging.basicConfig(filename=data / "aura.log", level=logging.INFO,
                        format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    log = logging.getLogger("aura")

    import uvicorn

    from app.main import app  # imported after env is configured

    port = args.port or free_port()
    url = f"http://127.0.0.1:{port}"
    server = uvicorn.Server(uvicorn.Config(app, host="127.0.0.1", port=port, log_level="warning", log_config=None))
    t = threading.Thread(target=server.run, daemon=True)
    t.start()
    if not wait_ready(url):
        log.error("backend did not start")
        print("AURA: backend did not start, see", data / "aura.log", file=sys.stderr)
        return 1
    log.info("serving %s (data: %s)", url, data)
    print(f"AURA running at {url}  (data: {data})", flush=True)

    def stop():
        server.should_exit = True
        t.join(timeout=5)

    if args.headless:
        try:
            while t.is_alive():
                time.sleep(0.5)
        except KeyboardInterrupt:
            pass
        stop()
        return 0
    if not args.browser:
        # The window runs in a child process: a toolkit that is missing can abort the whole
        # process at C level (Qt does), and we still want to fall back to the browser.
        cmd = [sys.executable, "--window", url] if FROZEN else [sys.executable, str(Path(__file__).resolve()), "--window", url]
        started = time.time()
        rc = subprocess.call(cmd)
        if rc == 0:
            stop()
            return 0
        log.warning("native window failed (exit %s after %.1fs); falling back to the browser", rc, time.time() - started)
    webbrowser.open(url)
    print("Opened in your browser. Close this window / press Ctrl+C to quit.", flush=True)
    try:
        while t.is_alive():
            time.sleep(0.5)
    except KeyboardInterrupt:
        pass
    stop()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
