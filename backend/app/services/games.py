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
from ..models import Attempt, Game, GameMistake
from .engine import StockfishService, win_pct
from .judgement import CRITERIA, game_accuracy, move_accuracy, score_move


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


def time_class(tc: str | None) -> str | None:
    """Chess.com-style class from a PGN TimeControl: estimated duration = base + 40 × increment."""
    if not tc or tc in ("-", "?"):
        return None
    if "/" in tc:  # "1/86400": daily / correspondence
        return "daily"
    base, inc = _base_increment(tc)
    if base is None:
        return None
    est = base + 40 * inc
    if est < 180:
        return "bullet"
    if est < 600:
        return "blitz"
    return "rapid"


def _elo(v: str | None) -> int | None:
    try:
        x = int((v or "").strip())
    except ValueError:
        return None
    return x if 100 <= x <= 3500 else None


def ratings_from_headers(headers, user_color: str | None) -> tuple[int | None, int | None]:
    """Your rating and the opponent's, as written in the PGN headers (Chess.com and Lichess export them)."""
    if user_color not in ("white", "black"):
        return None, None
    w, b = _elo(headers.get("WhiteElo")), _elo(headers.get("BlackElo"))
    return (w, b) if user_color == "white" else (b, w)


def import_pgn(db: Session, pgn_text: str, user_color: str | None = None, player_names: list[str] | None = None,
               source: str = "pgn") -> dict:
    names = player_names if player_names is not None else settings.player_names
    stream = io.StringIO(pgn_text)
    added, skipped, unknown_color, errors = [], 0, 0, []
    while True:
        try:
            game = chess.pgn.read_game(stream)
        except Exception as exc:  # pragma: no cover - python-chess is lenient
            errors.append(f"PGN ilegível: {exc}")
            break
        if game is None:
            break
        if game.errors:
            errors.extend(f"partida ignorada ({game.headers.get('White', '?')} x {game.headers.get('Black', '?')}): {e}"
                          for e in game.errors[:2])
            continue
        if game.headers.get("Variant", "Standard") not in ("Standard", "", "From Position"):
            errors.append(f"partida ignorada: variante {game.headers.get('Variant')} não é suportada")
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
        mine, theirs = ratings_from_headers(game.headers, color)
        exporter = chess.pgn.StringExporter(headers=True, variations=False, comments=True)
        tc = game.headers.get("TimeControl", "")
        g = Game(fingerprint=fp, pgn=game.accept(exporter), white=game.headers.get("White", "?"),
                 black=game.headers.get("Black", "?"), result=game.headers.get("Result", "*"),
                 played_on=_parse_date(game.headers.get("UTCDate") or game.headers.get("Date", "")),
                 time_control=tc, time_class=time_class(tc), user_elo=mine, opponent_elo=theirs,
                 user_color=color, source=source)
        db.add(g)
        db.flush()
        added.append(g.id)
    db.commit()
    return {"imported": len(added), "game_ids": added, "duplicates": skipped, "unknown_user_color": unknown_color,
            "errors": errors[:10]}


def set_user_color(game: Game, color: str) -> None:
    game.user_color = color
    pg = chess.pgn.read_headers(io.StringIO(game.pgn))
    if pg is not None:
        game.user_elo, game.opponent_elo = ratings_from_headers(pg, color)


def _base_increment(tc: str) -> tuple[float | None, float]:
    m = re.match(r"^(\d+)(?:\+(\d+))?$", tc or "")
    if not m:
        return None, 0.0
    return float(m[1]), float(m[2] or 0)


def analyze_game(db: Session, game: Game, engine: StockfishService, depth: int | None = None,
                 should_stop=None) -> dict:
    """Judge every user move (judgement.score_move); store inaccuracies/mistakes/blunders with
    Error DNA labels, and the brilliant (!!) and only (!) moves in the metrics.

    All engine work happens first, without touching the database; the results are then written
    in one short transaction, so training can keep saving attempts while a game is analysed."""
    if game.user_color is None:
        raise ValueError("não sei com qual cor você jogou nesta partida; informe a cor ou o seu nome de usuário")
    depth = depth or settings.game_analysis_depth
    pg = chess.pgn.read_game(io.StringIO(game.pgn))
    user = chess.WHITE if game.user_color == "white" else chess.BLACK
    base, inc = _base_increment(game.time_control)
    found: list[GameMistake] = []
    highlights: list[dict] = []
    board = pg.board()
    plies = list(pg.mainline())
    wins: list[float | None] = [None] * (len(plies) + 1)  # your win-% in every position, for the accuracy
    user_moves: list[int] = []
    last_clock = {chess.WHITE: base, chess.BLACK: base}
    losses, counts = [], {"inaccuracy": 0, "mistake": 0, "blunder": 0}
    best_moves = 0
    phase_moves = {"opening": [0, 0.0], "middlegame": [0, 0.0], "endgame": [0, 0.0]}
    low_clock_moves = low_clock_errors = 0
    think_times: list[float] = []
    think_by_ply: list[float | None] = [None] * len(plies)  # your seconds on each of your moves
    phase_acc: dict[str, list[float]] = {"opening": [], "middlegame": [], "endgame": []}
    for ply, child in enumerate(plies):
        move = child.move
        mover = board.turn
        clock = child.clock()
        think = None
        if clock is not None and last_clock[mover] is not None:
            think = max(0.0, last_clock[mover] - clock + inc)
        if clock is not None:
            last_clock[mover] = clock
        if mover == user and not board.is_game_over():
            if should_stop is not None and should_stop():
                raise InterruptedError("análise cancelada")
            s = score_move(engine, board, move, depth)
            f = engine_features(engine, board, move, depth, scored=s)
            wins[ply], wins[ply + 1] = win_pct(s.best.cp), win_pct(s.user.cp)
            user_moves.append(ply)
            cl = min(s.cp_loss, 1000)
            losses.append(cl)
            ph = phase_of(board)
            phase_moves[ph][0] += 1
            phase_moves[ph][1] += cl
            phase_acc[ph].append(move_accuracy(wins[ply], wins[ply + 1]))
            if think is not None:
                think_times.append(think)
                think_by_ply[ply] = round(think, 1)
            low_thr = max(10.0, 0.05 * base) if base else None
            if clock is not None and low_thr is not None and clock <= low_thr:
                low_clock_moves += 1
            best_moves += s.verdict == "best"
            if s.highlight:
                highlights.append({"ply": ply, "kind": s.highlight, "san": board.san(move), "uci": move.uci(),
                                   "eval_cp": s.user.cp, "mate": s.user.mate,
                                   "second_san": s.top[1].san if len(s.top) > 1 else None,
                                   "second_cp": s.top[1].cp if len(s.top) > 1 else None})
            sev = s.verdict
            if sev in counts:
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
                found.append(GameMistake(
                    game_id=game.id, ply=ply, fen_before=board.fen(), move_uci=move.uci(), move_san=board.san(move),
                    best_uci=s.best.move, best_san=s.best.san,
                    eval_before_cp=s.best.cp, eval_after_cp=s.user.cp,
                    cp_loss=s.cp_loss, win_pct_loss=s.win_pct_loss, severity=sev, clock_s=clock, think_s=think,
                    phase=ph, category=cat, detail={**f.as_dict(), "refutation_line": s.user.pv[:8]}, pv=s.best.pv[:8]))
        board.push(move)
    if board.is_checkmate():
        wins[-1] = 0.0 if board.turn == user else 100.0
    elif board.is_game_over():
        wins[-1] = 50.0
    n = len(losses)
    metrics = {
        "user_moves": n,
        "acpl": round(sum(losses) / n, 1) if n else None,
        "accuracy": game_accuracy(_filled(wins), user_moves) if n else None,
        "inaccuracies": counts["inaccuracy"], "mistakes": counts["mistake"], "blunders": counts["blunder"],
        "blunders_per_100": round(100 * counts["blunder"] / n, 2) if n else None,
        "errors_per_100": round(100 * sum(counts.values()) / n, 2) if n else None,
        "best_moves": best_moves,
        "brilliant": sum(h["kind"] == "brilliant" for h in highlights),
        "great": sum(h["kind"] == "great" for h in highlights),
        "highlights": highlights,
        "phase_acpl": {k: (round(v[1] / v[0], 1) if v[0] else None) for k, v in phase_moves.items()},
        "low_clock_moves": low_clock_moves, "low_clock_errors": low_clock_errors,
        "median_think_s": sorted(think_times)[len(think_times) // 2] if think_times else None,
        "result_for_user": _result_for(game.result, game.user_color),
        "depth": depth,
        "criteria": CRITERIA,
        # for the daily session and the review screen: the win-% curve (your side, every position),
        # your seconds per move, accuracy by phase, and whether the deep pass is still to come
        "wins": [round(w, 1) for w in _filled(wins)],
        "think": think_by_ply,
        "phase_accuracy": {k: (round(sum(v) / len(v), 1) if v else None) for k, v in phase_acc.items()},
        "deep": "pending" if depth < settings.game_analysis_depth else "done",
    }
    _store_mistakes(db, game, found)
    game.metrics = metrics
    game.analyzed = True
    game.analysis_depth = depth
    db.commit()
    return metrics


def _filled(wins: list[float | None]) -> list[float]:
    """Positions the analysis did not evaluate (the start when you play Black, the end) take the
    nearest known value: they only set the volatility weights of the accuracy."""
    known = [w for w in wins if w is not None]
    if not known:
        return []
    out, last = [], known[0]
    for w in wins:
        last = w if w is not None else last
        out.append(last)
    return out


def _store_mistakes(db: Session, game: Game, found: list[GameMistake]) -> None:
    """Replace the game's mistakes, keeping the rows that training attempts point to: the same
    position keeps its row (updated), and a trained position that is no longer an error is
    retired (hidden everywhere) instead of deleted."""
    old = {m.ply: m for m in db.query(GameMistake).filter(GameMistake.game_id == game.id)}
    used = set(db.execute(select(Attempt.game_mistake_id).where(
        Attempt.game_mistake_id.in_([m.id for m in old.values()]))).scalars()) if old else set()
    for new in found:
        prev = old.pop(new.ply, None)
        if prev is not None and prev.move_uci == new.move_uci:
            for col in ("fen_before", "move_san", "best_uci", "best_san", "eval_before_cp", "eval_after_cp",
                        "cp_loss", "win_pct_loss", "severity", "clock_s", "think_s", "phase", "category",
                        "detail", "pv"):
                setattr(prev, col, getattr(new, col))
            continue
        if prev is not None:
            old[-1 - prev.id] = prev  # a different move at that ply (should not happen): handled below
        db.add(new)
    for prev in old.values():
        if prev.id in used:
            prev.severity = "retired"
        else:
            db.delete(prev)


def _result_for(result: str, color: str | None) -> float | None:
    if color is None or result not in ("1-0", "0-1", "1/2-1/2"):
        return None
    if result == "1/2-1/2":
        return 0.5
    return 1.0 if (result == "1-0") == (color == "white") else 0.0

