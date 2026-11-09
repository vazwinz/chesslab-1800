"""Background puzzle import for the desktop app: download the official Lichess dump (or use a
local file) and run the streaming importer in a worker thread, exposing progress to the UI."""
from __future__ import annotations

import logging
import os
import threading
import time
from pathlib import Path

from ..config import settings
from ..db import SessionLocal
from .importer import import_puzzles

LICHESS_PUZZLE_URL = "https://database.lichess.org/lichess_db_puzzle.csv.zst"
log = logging.getLogger(__name__)
_sleep = time.sleep  # replaced in tests

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


def _download(url: str, dest: Path) -> Path:
    """Download with resume. Returns the file to import (normally `dest`).

    * an earlier complete download (same size as on the server) is reused, not downloaded again;
    * an interrupted `.part` is continued with an HTTP Range request;
    * the final rename is retried, because on Windows an antivirus or the search indexer often
      holds a freshly written file for a few seconds ("[WinError 5] Acesso negado"); if it still
      fails, the complete `.part` file is imported directly instead of failing."""
    import httpx

    from ..version import __version__

    tmp = dest.with_suffix(dest.suffix + ".part")
    headers = {"User-Agent": f"AURA/{__version__} (app de treino de xadrez)"}
    with httpx.Client(follow_redirects=True, timeout=httpx.Timeout(60, connect=15), headers=headers) as c:
        total = None
        try:
            h = c.head(url)
            if h.status_code == 200:
                total = int(h.headers.get("content-length") or 0) or None
        except httpx.HTTPError:
            pass
        if total and dest.exists() and dest.stat().st_size == total:
            _set(phase="download", downloaded=total, total_bytes=total, reused=True)
            return dest
        if total and tmp.exists() and tmp.stat().st_size == total:
            _set(phase="download", downloaded=total, total_bytes=total, reused=True)
            return _finalize(tmp, dest)
        start = tmp.stat().st_size if (tmp.exists() and total and tmp.stat().st_size < total) else 0
        with c.stream("GET", url, headers={"Range": f"bytes={start}-"} if start else {}) as r:
            r.raise_for_status()
            if start and r.status_code != 206:
                start = 0  # the server ignored the Range header: start over
            length = int(r.headers.get("content-length") or 0)
            total = total or ((start + length) if length else None)
            done, t0 = start, time.time()
            with open(tmp, "ab" if start else "wb") as fh:
                for chunk in r.iter_bytes(1 << 20):
                    fh.write(chunk)
                    done += len(chunk)
                    _set(phase="download", downloaded=done, total_bytes=total or 0, resumed_from=start,
                         rate_mb_s=round((done - start) / 1e6 / max(1e-6, time.time() - t0), 2))
    if total and done != total:
        raise IOError(f"download incompleto ({done} de {total} bytes); clique de novo para continuar de onde parou")
    return _finalize(tmp, dest)


def _finalize(tmp: Path, dest: Path) -> Path:
    for i in range(12):
        try:
            os.replace(tmp, dest)
            return dest
        except PermissionError:  # WinError 5 / 32: another program still has the file open
            _sleep(min(2.0, 0.25 * (i + 1)))
    log.warning("could not rename %s (file locked by another program); importing it directly", tmp)
    return tmp


def _cleanup(*paths: Path) -> None:
    for p in paths:
        try:
            p.unlink(missing_ok=True)
        except OSError:  # still locked: harmless, it is reused or overwritten next time
            pass


def _run(path: Path | None, url: str | None, kwargs: dict) -> None:
    downloaded: Path | None = None
    try:
        if url:
            dest = data_dir() / "lichess_db_puzzle.csv.zst"
            _set(phase="download", source=url, file=str(dest))
            path = downloaded = _download(url, dest)
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
        if downloaded is not None:  # the puzzles are in the database now; free the ~300 MB
            _cleanup(downloaded.with_name("lichess_db_puzzle.csv.zst.part"),
                     downloaded.with_name("lichess_db_puzzle.csv.zst"))
    except Exception as exc:  # surfaced to the UI
        log.exception("puzzle import failed")
        _set(status="failed", error=_friendly(exc)[:500])


def _friendly(exc: Exception) -> str:
    name = type(exc).__name__
    if name in ("ConnectError", "ConnectTimeout", "ReadTimeout", "RemoteProtocolError"):
        return "Sem conexão com database.lichess.org. Confira a internet e tente de novo (o download recomeça do zero)."
    if name == "HTTPStatusError":
        return f"O Lichess respondeu com erro ({exc}). Tente mais tarde."
    if isinstance(exc, OSError) and getattr(exc, "errno", None) == 28:
        return "Disco cheio: libere espaço (o arquivo tem algumas centenas de MB) e tente de novo."
    return f"Falha na importação: {exc}"


def start(path: str | None = None, download: bool = False, url: str = LICHESS_PUZZLE_URL,
          limit: int | None = None, min_rating: int | None = None, max_rating: int | None = None) -> dict:
    with _lock:
        if _state.get("status") == "running":
            raise RuntimeError("Já existe uma importação em andamento.")
    p = None
    if not download:
        if not path:
            raise ValueError("Informe o caminho do arquivo ou escolha baixar do Lichess.")
        p = Path(path).expanduser()
        if not p.exists():
            raise ValueError(f"Arquivo não encontrado: {p}")
        if "TEST_ONLY" in p.name:
            raise ValueError("Recusado: arquivos TEST_ONLY são dados de teste, não puzzles do Lichess.")
    with _lock:
        _state.clear()
        _state.update({"status": "running", "phase": "starting", "started": time.time()})
    kw = {"limit": limit, "min_rating": min_rating, "max_rating": max_rating}
    threading.Thread(target=_run, args=(p, url if download else None, kw), daemon=True).start()
    return state()
