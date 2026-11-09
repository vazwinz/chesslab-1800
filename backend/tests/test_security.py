"""The local server must only serve the built frontend and answer this computer."""
from __future__ import annotations

import importlib
import socket
import threading
import time

import pytest
import uvicorn


@pytest.fixture()
def server(tmp_path, db_url, monkeypatch):
    dist = tmp_path / "dist"
    (dist / "assets").mkdir(parents=True)
    (dist / "index.html").write_text('<!doctype html><html lang="pt-BR"><body>AURA</body></html>')
    (dist / "assets" / "app.js").write_text("console.log(1)")
    (tmp_path / "secret.txt").write_text("TOP-SECRET")
    from app.config import settings

    monkeypatch.setattr(settings, "frontend_dist", dist)
    import app.main as main

    importlib.reload(main)
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        port = s.getsockname()[1]
    srv = uvicorn.Server(uvicorn.Config(main.app, host="127.0.0.1", port=port, log_level="error"))
    t = threading.Thread(target=srv.run, daemon=True)
    t.start()
    for _ in range(100):
        if srv.started:
            break
        time.sleep(0.05)
    yield port, tmp_path
    srv.should_exit = True
    t.join(5)
    importlib.reload(main)


def _raw(port: int, path: str, host: str = "127.0.0.1", method: str = "GET", extra: str = "") -> tuple[str, bytes]:
    s = socket.create_connection(("127.0.0.1", port))
    s.sendall(f"{method} {path} HTTP/1.1\r\nHost: {host}\r\nConnection: close\r\n{extra}\r\n".encode())
    data = b""
    while chunk := s.recv(65536):
        data += chunk
    s.close()
    head, _, body = data.partition(b"\r\n\r\n")
    return head.split(b"\r\n")[0].decode(), body


@pytest.mark.parametrize("path", ["/../secret.txt", "/%2e%2e/secret.txt", "//etc/passwd", "/..%5csecret.txt",
                                  "/assets/../../secret.txt", "/../../../../../../etc/passwd"])
def test_no_file_outside_the_frontend_is_served(server, path):
    port, _ = server
    status, body = _raw(port, path)
    assert b"TOP-SECRET" not in body and b"root:" not in body, (path, status)


def test_frontend_files_and_spa_routes_still_work(server):
    port, _ = server
    assert _raw(port, "/assets/app.js")[1] == b"console.log(1)"
    status, body = _raw(port, "/treinar")
    assert status.endswith("200 OK") and b"AURA" in body
    status, body = _raw(port, "/api/does-not-exist")
    assert status.startswith("HTTP/1.1 404") and b"AURA" not in body


def test_foreign_host_header_is_refused(server):
    port, _ = server
    status, body = _raw(port, "/api/health", host="evil.example")
    assert status.startswith("HTTP/1.1 400") and "computador".encode() in body
    assert _raw(port, "/api/health", host=f"localhost:{port}")[0].endswith("200 OK")
    assert _raw(port, "/api/health", host=f"[::1]:{port}")[0].endswith("200 OK")


def test_cross_site_write_is_refused(server):
    port, _ = server
    hdr = "Origin: https://evil.example\r\nContent-Length: 0\r\n"
    status, _ = _raw(port, "/api/games/analyze-pending", method="POST", extra=hdr)
    assert status.startswith("HTTP/1.1 403")
    same = f"Origin: http://127.0.0.1:{port}\r\nContent-Length: 0\r\n"  # the app itself (browsers send host:port)
    assert _raw(port, "/api/games/analyze-pending", method="POST", extra=same,
                host=f"127.0.0.1:{port}")[0].endswith("200 OK")
    dev = "Origin: http://localhost:5173\r\nContent-Length: 0\r\n"  # Vite dev server
    assert _raw(port, "/api/games/analyze-pending", method="POST", extra=dev)[0].endswith("200 OK")


def test_saved_theme_is_applied_before_first_paint(server):
    port, _ = server
    import json

    body = json.dumps({"theme": "dark"})
    status, _ = _raw(port, "/api/prefs", method="PUT",
                     extra=f"Content-Type: application/json\r\nContent-Length: {len(body)}\r\n\r\n{body}")
    status, html = _raw(port, "/")
    assert b'data-theme="dark"' in html
