"""AURA — desktop launcher for ChessLab 1800.

Starts the FastAPI backend on a free local port and opens it in a native window (pywebview:
Edge WebView2 on Windows, Qt WebEngine/GTK on Linux). If no native window toolkit is available,
it opens your default browser instead. Data lives in your user profile, not next to the app:
  Windows: %LOCALAPPDATA%\\AURA      Linux: ~/.local/share/aura      (or CHESSLAB_DATA_DIR)

    python desktop/aura.py               # dev run from the repo
    AURA.exe / ./AURA                    # packaged app
    --browser   open in the default browser instead of a window
    --headless  only run the server (prints the URL), for testing

Start-up order: one instance only (Windows) -> database migrations (with a backup first) ->
server -> window. A failure in any step is shown in a native dialog, in Portuguese, with the
path of the log file; it never leaves a half-open window behind.
"""
from __future__ import annotations

import argparse
import json
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
MUTEX_NAME = "Local\\AURA-ChessLab1800"  # the installer checks this name too
LIGHT_BG, DARK_BG = "#F3F5F8", "#14181F"   # the app's page colour in each theme


def user_data_dir() -> Path:
    """The one folder for the database, backups, secrets.json, aura.log and the window profile.
    CHESSLAB_DATA_DIR wins when it is set (tests, a second profile), so nothing is written to
    the default folder in that case."""
    override = os.getenv("CHESSLAB_DATA_DIR")
    if override:
        d = Path(override).expanduser()
    elif os.name == "nt":
        base = Path(os.getenv("LOCALAPPDATA") or Path.home() / "AppData" / "Local")
        d = base / APP_NAME
    else:
        d = Path(os.getenv("XDG_DATA_HOME") or Path.home() / ".local" / "share") / APP_NAME.lower()
    d.mkdir(parents=True, exist_ok=True)
    return d


def configure_env() -> Path:
    data = user_data_dir()
    os.environ["CHESSLAB_DATA_DIR"] = str(data)  # the backend and the window process read it
    if FROZEN:
        os.environ.setdefault("FRONTEND_DIST", str(BUNDLE / "frontend_dist"))
        exe = "stockfish.exe" if os.name == "nt" else "stockfish"
        bundled = BUNDLE / "stockfish" / exe
        if bundled.exists() and not os.getenv("STOCKFISH_PATH"):
            os.environ["STOCKFISH_PATH"] = str(bundled)
    else:
        sys.path.insert(0, str(BUNDLE / "backend"))
    return data


def message_box(text: str, error: bool = True) -> None:
    """Native dialog on Windows (the packaged app has no console); stderr everywhere."""
    print(f"AURA: {text}", file=sys.stderr, flush=True)
    if os.name == "nt":
        try:
            import ctypes

            ctypes.windll.user32.MessageBoxW(None, text, APP_NAME, 0x10 if error else 0x40)
        except Exception:  # pragma: no cover - best effort
            pass


def single_instance():
    """A handle that holds the instance mutex while AURA runs; None when AURA is already open."""
    if os.name != "nt":
        return True
    import ctypes

    k32 = ctypes.windll.kernel32
    handle = k32.CreateMutexW(None, False, MUTEX_NAME)
    if k32.GetLastError() == 183:  # ERROR_ALREADY_EXISTS
        return None
    return handle


def system_dark() -> bool:
    if os.name != "nt":
        return False
    try:
        import winreg

        key = r"Software\Microsoft\Windows\CurrentVersion\Themes\Personalize"
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, key) as k:
            return winreg.QueryValueEx(k, "AppsUseLightTheme")[0] == 0
    except OSError:
        return False


def window_background(url: str) -> str:
    """The window paints this colour before the page loads, so it must match the saved theme."""
    try:
        with urllib.request.urlopen(url + "/api/prefs", timeout=2) as r:
            theme = json.load(r).get("theme", "system")
    except Exception:
        theme = "system"
    dark = theme == "dark" or (theme == "system" and system_dark())
    return DARK_BG if dark else LIGHT_BG


def db_error_message(exc: Exception, data: Path, log_file: Path) -> str:
    """Text of the dialog shown when the database cannot be prepared (the details are in the log)."""
    text = f"O AURA não conseguiu preparar o banco de dados e não vai abrir.\n\n{exc}\n\nOs seus dados continuam na pasta {data}."
    backups = data / "backups"
    copies = sorted(backups.glob("chesslab-*.db"), key=lambda p: p.stat().st_mtime, reverse=True) if backups.is_dir() else []
    if copies:
        text += f"\nAs cópias de segurança do banco ficam em {backups} (a mais recente: {copies[0].name})."
    return text + f"\nDetalhes técnicos: {log_file}"


def free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def wait_ready(url: str, alive, timeout: float = 30) -> bool:
    end = time.time() + timeout
    while time.time() < end and alive():
        try:
            with urllib.request.urlopen(url + "/api/health", timeout=2):
                return True
        except Exception:
            time.sleep(0.2)
    return False


def enable_zoom_keys(edgechromium=None) -> bool:
    """Ctrl + / Ctrl - / Ctrl 0 zoom on Windows. pywebview (6.x) turns WebView2's "browser
    accelerator keys" off unless debug=True, and the zoom keys are among them, so zoomable=True
    alone only gives Ctrl + mouse wheel. Turn them back on once WebView2 is ready (this also brings
    back Ctrl+F find and F5 reload); DevTools and the default context menu have their own settings
    and stay off. Best effort: if pywebview changes, the window still opens."""
    if edgechromium is None:
        if os.name != "nt":
            return False
        try:
            from webview.platforms import edgechromium
        except Exception:
            return False
    ready = getattr(getattr(edgechromium, "EdgeChrome", None), "on_webview_ready", None)
    if ready is None or getattr(ready, "aura_zoom_keys", False):
        return False

    def on_webview_ready(self, sender, args):
        ready(self, sender, args)
        try:
            if args.IsSuccess:
                sender.CoreWebView2.Settings.AreBrowserAcceleratorKeysEnabled = True
        except Exception as exc:  # pragma: no cover - Windows only
            print(f"zoom keys not enabled: {exc}", file=sys.stderr)

    on_webview_ready.aura_zoom_keys = True
    edgechromium.EdgeChrome.on_webview_ready = on_webview_ready
    return True


def run_window(url: str, bg: str) -> int:
    try:
        import webview

        enable_zoom_keys()

        # text_select: PGNs, FENs and explanations must be selectable; zoomable: Ctrl + / - like a browser
        webview.create_window(APP_NAME, url, width=1440, height=920, min_size=(380, 600), background_color=bg,
                              text_select=True, zoomable=True)
        # keep the WebView2/Qt profile in AURA's data folder: preferences survive restarts and
        # nothing is written next to the program files
        webview.start(private_mode=False, storage_path=str(user_data_dir() / "webview"))
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
    ap.add_argument("--bg", default=LIGHT_BG, help=argparse.SUPPRESS)
    args = ap.parse_args()
    if args.window:
        return run_window(args.window, args.bg)

    data = configure_env()
    log_file = data / "aura.log"
    logging.basicConfig(filename=log_file, level=logging.INFO,
                        format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    log = logging.getLogger("aura")

    lock = single_instance()
    if lock is None:
        message_box("O AURA já está aberto. Procure a janela dele na barra de tarefas.", error=False)
        return 0

    # migrations run here, before the server, so a failure gets a clear dialog instead of a
    # window that never loads (the server's own start-up check then finds nothing to do)
    try:
        from app.db import init_db

        report = init_db()
        log.info("database ready: %s", report)
    except Exception as exc:
        log.exception("database preparation failed")
        message_box(db_error_message(exc, data, log_file))
        return 1

    import uvicorn

    from app.main import app  # imported after env is configured

    port = args.port or free_port()
    url = f"http://127.0.0.1:{port}"
    server = uvicorn.Server(uvicorn.Config(app, host="127.0.0.1", port=port, log_level="warning", log_config=None))
    t = threading.Thread(target=server.run, daemon=True)
    t.start()
    if not wait_ready(url, t.is_alive):
        log.error("backend did not start")
        message_box(f"O AURA não conseguiu iniciar o servidor interno.\n\nDetalhes técnicos: {log_file}")
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
        bg = window_background(url)
        base = [sys.executable] if FROZEN else [sys.executable, str(Path(__file__).resolve())]
        started = time.time()
        rc = subprocess.call(base + ["--window", url, "--bg", bg])
        if rc == 0:
            stop()
            return 0
        log.warning("native window failed (exit %s after %.1fs); falling back to the browser", rc, time.time() - started)
    webbrowser.open(url)
    print("Aberto no navegador. Feche esta janela ou aperte Ctrl+C para sair.", flush=True)
    try:
        while t.is_alive():
            time.sleep(0.5)
    except KeyboardInterrupt:
        pass
    stop()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
