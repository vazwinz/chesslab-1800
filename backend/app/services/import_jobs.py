"""Background puzzle import for the desktop app: download the official Lichess dump (or use a
local file) and run the streaming importer in a worker thread, exposing progress to the UI."""
from __future__ import annotations

import threading
import time
from pathlib import Path

from ..config import settings
from ..db import SessionLocal
from .importer import import_puzzles

LICHESS_PUZZLE_URL = "https://database.lichess.org/lichess_db_puzzle.csv.zst"

_lock = threading.Lock()
_state: dict = {"status": "idle"}


def state() -> dict:
    with _lock:
        return dict(_state)


def _set(**kw) -> None:
    with _lock:
        _state.update(kw)


def data_dir() -> Path:
    d = Path(settings.data_dir)
    d.mkdir(parents=True, exist_ok=True)
    return d


def _download(url: str, dest: Path) -> None:
    import httpx

    tmp = dest.with_suffix(dest.suffix + ".part")
    with httpx.stream("GET", url, follow_redirects=True, timeout=60) as r:
        r.raise_for_status()
        total = int(r.headers.get("content-length") or 0)
        done, t0 = 0, time.time()
        with open(tmp, "wb") as fh:
            for chunk in r.iter_bytes(1 << 20):
                fh.write(chunk)
                done += len(chunk)
                _set(phase="download", downloaded=done, total_bytes=total,
                     rate_mb_s=round(done / 1e6 / max(1e-6, time.time() - t0), 2))
    tmp.replace(dest)


def _run(path: Path | None, url: str | None, kwargs: dict) -> None:
    try:
        if url:
            path = data_dir() / "lichess_db_puzzle.csv.zst"
            _set(phase="download", source=url, file=str(path))
            _download(url, path)
        assert path is not None
        _set(phase="import", file=str(path), rows_read=0, inserted=0, updated=0, invalid=0)
        t0 = time.time()

        def progress(job):
            _set(rows_read=job.rows_read, inserted=job.inserted, updated=job.updated, invalid=job.invalid,
                 rows_per_s=round(job.rows_read / max(1e-6, time.time() - t0)))

        with SessionLocal() as db:
            job = import_puzzles(db, path, progress=progress, **kwargs)
        _set(status="done", phase="done", rows_read=job.rows_read, inserted=job.inserted, updated=job.updated,
             invalid=job.invalid, seconds=round(time.time() - t0))
    except Exception as exc:  # surfaced to the UI
        _set(status="failed", error=str(exc)[:500])


def start(path: str | None = None, download: bool = False, url: str = LICHESS_PUZZLE_URL,
          limit: int | None = None, min_rating: int | None = None, max_rating: int | None = None) -> dict:
    with _lock:
        if _state.get("status") == "running":
            raise RuntimeError("an import is already running")
    p = None
    if not download:
        if not path:
            raise ValueError("give a file path or choose download")
        p = Path(path).expanduser()
        if not p.exists():
            raise ValueError(f"file not found: {p}")
        if "TEST_ONLY" in p.name:
            raise ValueError("refusing to import a TEST_ONLY fixture")
    with _lock:
        _state.clear()
        _state.update({"status": "running", "phase": "starting", "started": time.time()})
    kw = {"limit": limit, "min_rating": min_rating, "max_rating": max_rating}
    threading.Thread(target=_run, args=(p, url if download else None, kw), daemon=True).start()
    return state()
