"""Real-game import (PGN) and Stockfish analysis of the user's moves.
Game metrics are the primary outcome measure of the Cognitive Engine."""
from __future__ import annotations

import hashlib
import io
import math
import re
from datetime import date

import chess
import chess.pgn
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..cognitive.error_dna import classify, engine_features, phase_of
from ..config import settings
from ..models import Game, GameMistake
from .engine import StockfishService, classify_loss


def _fingerprint(game: chess.pgn.Game) -> str:
    h = game.headers
    moves = " ".join(m.uci() for m in game.mainline_moves())
    raw = "|".join([h.get("White", ""), h.get("Black", ""), h.get("Date", ""), h.get("UTCTime", ""),
                    h.get("Site", ""), moves])
    return hashlib.sha256(raw.encode()).hexdigest()


def _parse_date(s: str) -> date | None:
    m = re.match(r"(\d{4})\.(\d{2})\.(\d{2})", s or "")
    if not m:
        return None
    try:
        return date(int(m[1]), int(m[2]), int(m[3]))
    except ValueError:
        return None


def _user_color(game: chess.pgn.Game, names: list[str], explicit: str | None) -> str | None:
    if explicit in ("white", "black"):
        return explicit
    low = [n.lower() for n in names]
    if game.headers.get("White", "").lower() in low:
        return "white"
    if game.headers.get("Black", "").lower() in low:
        return "black"
    return None


def import_pgn(db: Session, pgn_text: str, user_color: str | None = None, player_names: list[str] | None = None,
               source: str = "pgn") -> dict:
    names = player_names if player_names is not None else settings.player_names
    stream = io.StringIO(pgn_text)
    added, skipped, unknown_color, errors = [], 0, 0, []
    while True:
        try:
            game = chess.pgn.read_game(stream)
        except Exception as exc:  # pragma: no cover - python-chess is lenient
            errors.append(str(exc))
            break
        if game is None:
            break
        if game.errors:
            errors.extend(str(e) for e in game.errors[:3])
            continue
        if not list(game.mainline_moves()):
            continue
        fp = _fingerprint(game)
        if db.execute(select(Game.id).where(Game.fingerprint == fp)).scalar():
            skipped += 1
            continue
        color = _user_color(game, names, user_color)
        if color is None:
            unknown_color += 1
        exporter = chess.pgn.StringExporter(headers=True, variations=False, comments=True)
        g = Game(fingerprint=fp, pgn=game.accept(exporter), white=game.headers.get("White", "?"),
                 black=game.headers.get("Black", "?"), result=game.headers.get("Result", "*"),
                 played_on=_parse_date(game.headers.get("Date", "")), time_control=game.headers.get("TimeControl", ""),
                 user_color=color, source=source)
        db.add(g)
        db.flush()
        added.append(g.id)
    db.commit()
    return {"imported": len(added), "game_ids": added, "duplicates": skipped, "unknown_user_color": unknown_color,
            "errors": errors[:10]}


def _base_increment(tc: str) -> tuple[float | None, float]:
    m = re.match(r"^(\d+)(?:\+(\d+))?$", tc or "")
    if not m:
        return None, 0.0
    return float(m[1]), float(m[2] or 0)


def move_accuracy(win_loss: float) -> float:
    """Lichess per-move accuracy from win% loss."""
    return max(0.0, min(100.0, 103.1668 * math.exp(-0.04354 * win_loss) - 3.1669))


def analyze_game(db: Session, game: Game, engine: StockfishService, depth: int | None = None) -> dict:
    """Evaluate every user move; store inaccuracies/mistakes/blunders with Error DNA labels."""
    if game.user_color is None:
        raise ValueError("user colour unknown for this game; set CHESSLAB_PLAYER_NAMES or pass user_color")
    depth = depth or settings.game_analysis_depth
    pg = chess.pgn.read_game(io.StringIO(game.pgn))
    user = chess.WHITE if game.user_color == "white" else chess.BLACK
    base, inc = _base_increment(game.time_control)
    db.query(GameMistake).filter(GameMistake.game_id == game.id).delete()
    board = pg.board()
    last_clock = {chess.WHITE: base, chess.BLACK: base}
    losses, accs, counts = [], [], {"inaccuracy": 0, "mistake": 0, "blunder": 0}
    phase_moves = {"opening": [0, 0.0], "middlegame": [0, 0.0], "endgame": [0, 0.0]}
    low_clock_moves = low_clock_errors = 0
    think_times: list[float] = []
    for ply, child in enumerate(pg.mainline()):
        move = child.move
        mover = board.turn
        clock = child.clock()
        think = None
        if clock is not None and last_clock[mover] is not None:
            think = max(0.0, last_clock[mover] - clock + inc)
        if clock is not None:
            last_clock[mover] = clock
        if mover == user and not board.is_game_over():
            f = engine_features(engine, board, move, depth)
            wl = f.win_pct_loss or 0.0
            cl = min(f.cp_loss or 0, 1000)
            losses.append(cl)
            accs.append(move_accuracy(wl))
            ph = phase_of(board)
            phase_moves[ph][0] += 1
            phase_moves[ph][1] += cl
            if think is not None:
                think_times.append(think)
            low_thr = max(10.0, 0.05 * base) if base else None
            if clock is not None and low_thr is not None and clock <= low_thr:
                low_clock_moves += 1
            sev = classify_loss(wl)
            if sev != "good":
                counts[sev] += 1
                if low_thr is not None and clock is not None and clock <= low_thr:
                    low_clock_errors += 1
                f.think_s = think
                f.clock_s = clock
                f.low_clock_threshold_s = low_thr
                # "impulsive": far faster than the time budget the clock allowed for a non-trivial position
                if base:
                    f.impulsive_threshold_s = max(1.5, min(5.0, 0.01 * base + inc * 0.3))
                cat = classify(f, "game")
                db.add(GameMistake(
                    game_id=game.id, ply=ply, fen_before=board.fen(), move_uci=move.uci(), move_san=board.san(move),
                    best_uci=f.best_move or move.uci(),
                    best_san=board.san(chess.Move.from_uci(f.best_move)) if f.best_move else board.san(move),
                    eval_before_cp=f.best_cp or 0, eval_after_cp=f.user_cp or 0,
                    cp_loss=f.cp_loss or 0, win_pct_loss=wl, severity=sev, clock_s=clock, think_s=think, phase=ph,
                    category=cat, detail=f.as_dict(), pv=[]))
        board.push(move)
    n = len(losses)
    metrics = {
        "user_moves": n,
        "acpl": round(sum(losses) / n, 1) if n else None,
        "accuracy": round(sum(accs) / n, 1) if n else None,
        "inaccuracies": counts["inaccuracy"], "mistakes": counts["mistake"], "blunders": counts["blunder"],
        "blunders_per_100": round(100 * counts["blunder"] / n, 2) if n else None,
        "errors_per_100": round(100 * sum(counts.values()) / n, 2) if n else None,
        "phase_acpl": {k: (round(v[1] / v[0], 1) if v[0] else None) for k, v in phase_moves.items()},
        "low_clock_moves": low_clock_moves, "low_clock_errors": low_clock_errors,
        "median_think_s": sorted(think_times)[len(think_times) // 2] if think_times else None,
        "result_for_user": _result_for(game.result, game.user_color),
        "depth": depth,
    }
    game.metrics = metrics
    game.analyzed = True
    game.analysis_depth = depth
    db.commit()
    return metrics


def _result_for(result: str, color: str | None) -> float | None:
    if color is None or result not in ("1-0", "0-1", "1/2-1/2"):
        return None
    if result == "1/2-1/2":
        return 0.5
    return 1.0 if (result == "1-0") == (color == "white") else 0.0

