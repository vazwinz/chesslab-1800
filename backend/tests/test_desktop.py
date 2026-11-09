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
    # imported, so the ~300 MB download is deleted
    assert not list((tmp_path / "data").glob("lichess_db_puzzle.csv.zst*"))
    assert client.get("/api/setup").json()["puzzles"] == st["inserted"]


def test_download_reuses_a_complete_part_file_when_rename_is_blocked(client, tmp_path, monkeypatch):
    """The Windows failure: 310/310 MB downloaded, then '[WinError 5] Acesso negado' on rename.
    The complete .part must be reused (no new download) and imported even if rename keeps failing."""
    import os

    data = tmp_path / "data"
    data.mkdir()
    monkeypatch.setattr(settings, "data_dir", str(data))
    www = tmp_path / "www"
    www.mkdir()
    shutil.copy(PUZZLE_FIXTURE, www / "dump.csv.zst")
    shutil.copy(PUZZLE_FIXTURE, data / "lichess_db_puzzle.csv.zst.part")  # left over by the failed run
    real_replace, calls = os.replace, []

    def locked(src, dst):
        calls.append(src)
        raise PermissionError(5, "Acesso negado")

    monkeypatch.setattr(import_jobs.os, "replace", locked)
    monkeypatch.setattr(import_jobs, "_sleep", lambda s: None)
    srv = _serve(www)
    try:
        st = import_jobs.start(download=True, url=f"http://127.0.0.1:{srv.server_port}/dump.csv.zst")
        st = _wait()
    finally:
        srv.shutdown()
        monkeypatch.setattr(import_jobs.os, "replace", real_replace)
    assert st["status"] == "done", st
    assert st.get("reused") is True and len(calls) == 12
    assert st["inserted"] >= 40


def test_interrupted_download_continues_or_restarts(client, tmp_path, monkeypatch):
    data = tmp_path / "data"
    data.mkdir()
    monkeypatch.setattr(settings, "data_dir", str(data))
    www = tmp_path / "www"
    www.mkdir()
    shutil.copy(PUZZLE_FIXTURE, www / "dump.csv.zst")
    blob = PUZZLE_FIXTURE.read_bytes()
    (data / "lichess_db_puzzle.csv.zst.part").write_bytes(blob[: len(blob) // 2])  # half done
    srv = _serve(www)  # http.server ignores Range, so the download must restart cleanly
    try:
        import_jobs.start(download=True, url=f"http://127.0.0.1:{srv.server_port}/dump.csv.zst")
        st = _wait()
    finally:
        srv.shutdown()
    assert st["status"] == "done", st
    assert st["downloaded"] == len(blob) and st["inserted"] >= 40


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
