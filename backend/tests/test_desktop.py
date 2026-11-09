"""Desktop-app support: background download + import job, setup endpoint, launcher."""
from __future__ import annotations

import functools
import http.server
import shutil
import subprocess
import sys
import threading
import time
import urllib.request
from pathlib import Path

import pytest

from app.config import settings
from app.services import import_jobs

from .conftest import PUZZLE_FIXTURE


def _serve(directory: Path):
    handler = functools.partial(http.server.SimpleHTTPRequestHandler, directory=str(directory))
    srv = http.server.ThreadingHTTPServer(("127.0.0.1", 0), handler)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    return srv


def _wait():
    for _ in range(200):
        st = import_jobs.state()
        if st["status"] != "running":
            return st
        time.sleep(0.05)
    raise AssertionError("import did not finish")


def test_download_and_import_job(client, tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "data_dir", str(tmp_path / "data"))
    www = tmp_path / "www"
    www.mkdir()
    shutil.copy(PUZZLE_FIXTURE, www / "dump.csv.zst")  # local stand-in for database.lichess.org
    srv = _serve(www)
    try:
        url = f"http://127.0.0.1:{srv.server_port}/dump.csv.zst"
        st = import_jobs.start(download=True, url=url)
        assert st["status"] == "running"
        st = _wait()
    finally:
        srv.shutdown()
    assert st["status"] == "done", st
    assert st["inserted"] >= 40 and st["invalid"] == 1
    assert (tmp_path / "data" / "lichess_db_puzzle.csv.zst").exists()
    assert client.get("/api/setup").json()["puzzles"] == st["inserted"]


def test_setup_import_validation(client):
    r = client.post("/api/setup/import", json={"path": str(PUZZLE_FIXTURE)})
    assert r.status_code == 422 and "TEST_ONLY" in r.json()["detail"]
    assert client.post("/api/setup/import", json={"path": "/no/such/file.zst"}).status_code == 422
    assert client.post("/api/setup/import", json={}).status_code == 422


@pytest.mark.skipif(sys.platform == "win32", reason="uses a POSIX env var for the data dir")
def test_launcher_headless(tmp_path):
    launcher = Path(__file__).resolve().parents[2] / "desktop" / "aura.py"
    env = {"XDG_DATA_HOME": str(tmp_path), "PATH": "/usr/bin:/bin:/usr/games", "HOME": str(tmp_path)}
    p = subprocess.Popen([sys.executable, str(launcher), "--headless", "--port", "8799"], env=env,
                         stdout=subprocess.PIPE, text=True)
    try:
        line = p.stdout.readline()
        assert "AURA running at http://127.0.0.1:8799" in line
        with urllib.request.urlopen("http://127.0.0.1:8799/api/setup") as r:
            assert b'"puzzles":0' in r.read()
        assert (tmp_path / "aura" / "chesslab.db").exists()
    finally:
        p.terminate()
        p.wait(10)
