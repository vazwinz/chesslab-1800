"""Background work on your games: download from Chess.com, then Stockfish analysis one game at
a time, with progress, ETA and cancel. Runs on its own Stockfish process ("background"), so
training and the analysis board stay responsive. One worker thread drains a queue of tasks;
asking again while it runs just adds to the queue."""
from __future__ import annotations

import logging
import threading
import time
from collections import deque

from sqlalchemy import select

from ..db import SessionLocal
from ..models import Game

log = logging.getLogger(__name__)

_lock = threading.Lock()
_cancel = threading.Event()
_queue: deque = deque()
_worker: threading.Thread | None = None
_state: dict = {"status": "idle"}


def state() -> dict:
    with _lock:
        s = dict(_state)
        s["queued"] = sum(1 for t in _queue if t[0] == "analyze")
        return s


def _set(**kw) -> None:
    with _lock:
        _state.update(kw)


def pending_ids(db) -> list[int]:
    """Games with a known colour that were never analysed, newest first."""
    return list(db.execute(select(Game.id).where(Game.analyzed.is_(False), Game.user_color.is_not(None))
                           .order_by(Game.played_on.desc().nulls_last(), Game.id.desc())).scalars())


def _ensure_worker() -> None:
    global _worker
    if _worker is None or not _worker.is_alive():
        _cancel.clear()
        _worker = threading.Thread(target=_run, name="aura-games", daemon=True)
        _worker.start()


def enqueue_analysis(ids: list[int], depth: int | None = None) -> dict:
    with _lock:
        have = {t[1] for t in _queue if t[0] == "analyze"}
        if _state.get("status") == "running" and _state.get("game_id") is not None:
            have.add(_state["game_id"])
        for gid in ids:
            if gid not in have:
                _queue.append(("analyze", gid, depth))
                have.add(gid)
        if _state.get("status") != "running":
            _state.clear()
            _state.update({"status": "running", "phase": "analysis", "done": 0, "total": 0, "errors": [],
                           "started": time.time(), "imported": 0})
        _state["total"] = _state.get("done", 0) + sum(1 for t in _queue if t[0] == "analyze")
    _ensure_worker()
    return state()


def enqueue_chesscom(username: str, months: int, analyze: bool) -> dict:
    with _lock:
        _queue.appendleft(("chesscom", username, months, analyze))
        if _state.get("status") != "running":
            _state.clear()
            _state.update({"status": "running", "phase": "download", "done": 0, "total": 0, "errors": [],
                           "started": time.time(), "imported": 0, "username": username})
    _ensure_worker()
    return state()


def cancel() -> dict:
    _cancel.set()
    with _lock:
        _queue.clear()
    return state()


def _run() -> None:
    from ..cognitive import loop
    from .engine import EngineUnavailable, get_engine
    from .games import analyze_game

    t_games, n_games = 0.0, 0
    while True:
        with _lock:
            task = _queue.popleft() if _queue else None
        if task is None or _cancel.is_set():
            _set(status="cancelled" if _cancel.is_set() else "done", phase="done", game_id=None, current=None,
                 finished=time.time())
            return
        try:
            if task[0] == "chesscom":
                _chesscom(task[1], task[2], task[3])
                continue
            _, gid, depth = task
            with SessionLocal() as db:
                g = db.get(Game, gid)
                if g is None or g.user_color is None:
                    _set(done=state()["done"] + 1)
                    continue
                _set(phase="analysis", game_id=gid, current=f"{g.white} × {g.black}" + (f" ({g.played_on})"
                                                                                         if g.played_on else ""))
                t0 = time.time()
                analyze_game(db, g, get_engine("background"), depth, should_stop=_cancel.is_set)
                loop.advance(db)
                db.commit()
            t_games += time.time() - t0
            n_games += 1
            st = state()
            remaining = max(0, st["total"] - st["done"] - 1)
            _set(done=st["done"] + 1, eta_s=round(remaining * t_games / n_games), sec_per_game=round(t_games / n_games, 1))
        except InterruptedError:
            continue
        except EngineUnavailable as exc:
            _set(status="failed", phase="done", error=str(exc), game_id=None, current=None)
            with _lock:
                _queue.clear()
            return
        except Exception as exc:  # one bad game (or month) must not stop the others
            log.exception("game job task failed: %s", task)
            st = state()
            if task[0] == "chesscom":
                msg = str(exc) if exc.__class__.__name__ == "ChessComError" else \
                    f"não consegui baixar do Chess.com ({type(exc).__name__}); confira a internet e o usuário"
                _set(errors=(st.get("errors") or [])[-9:] + [f"Chess.com: {msg}"])
            else:
                _set(done=st["done"] + 1, errors=(st.get("errors") or [])[-9:] + [f"partida {task[1]}: {exc}"])


def _chesscom(username: str, months: int, analyze: bool) -> None:
    from . import chesscom, prefs
    from .games import import_pgn

    _set(phase="download", current=f"Chess.com: {username}")
    urls = chesscom.archives(username)[-max(1, months):]
    new_ids: list[int] = []
    for i, url in enumerate(reversed(urls)):  # newest month first
        if _cancel.is_set():
            return
        _set(phase="download", current=f"Chess.com: {url.rsplit('/', 2)[-2]}/{url.rsplit('/', 1)[-1]}",
             months_done=i, months_total=len(urls))
        pgn = chesscom.month_pgn(url)
        with SessionLocal() as db:
            names = list({username, *prefs.player_names(db)})
            res = import_pgn(db, pgn, None, names, source="chess.com")
            if res["imported"] and username.lower() not in [n.lower() for n in prefs.player_names(db)]:
                prefs.update_prefs(db, {"player_names": ", ".join([*prefs.player_names(db), username])})
        new_ids += res["game_ids"]
        st = state()
        _set(imported=st.get("imported", 0) + res["imported"], months_done=i + 1,
             duplicates=st.get("duplicates", 0) + res["duplicates"])
    if analyze and new_ids:
        with SessionLocal() as db:
            ids = [gid for gid in pending_ids(db) if gid in set(new_ids)]
        with _lock:
            for gid in ids:
                _queue.append(("analyze", gid, None))
            _state["total"] = _state.get("done", 0) + sum(1 for t in _queue if t[0] == "analyze")
