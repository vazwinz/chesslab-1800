"""PRESSURE SIMULATION — progressively harder time-limited scenarios.

Decision quality (was the move right? how much did a wrong move lose?) is measured separately
from speed (fraction of the time budget used, timeouts). A timeout is a time-management event,
not counted as a wrong decision."""
from __future__ import annotations

import chess
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models import KV, Attempt, Puzzle
from .stats import wilson

LEVELS = [
    # level, seconds, extra themes, min solution length, target complexity
    {"level": 1, "seconds": 60, "themes": [], "min_len": 1, "complexity": 0.2},
    {"level": 2, "seconds": 45, "themes": [], "min_len": 1, "complexity": 0.3},
    {"level": 3, "seconds": 35, "themes": ["defensiveMove"], "min_len": 1, "complexity": 0.4},
    {"level": 4, "seconds": 30, "themes": ["defensiveMove", "equality"], "min_len": 2, "complexity": 0.5},
    {"level": 5, "seconds": 25, "themes": ["defensiveMove", "intermezzo", "quietMove"], "min_len": 2, "complexity": 0.6},
    {"level": 6, "seconds": 20, "themes": ["defensiveMove", "intermezzo", "quietMove"], "min_len": 2, "complexity": 0.7},
    {"level": 7, "seconds": 15, "themes": ["defensiveMove", "quietMove", "long"], "min_len": 3, "complexity": 0.8},
    {"level": 8, "seconds": 12, "themes": ["defensiveMove", "quietMove", "long"], "min_len": 3, "complexity": 0.9},
]
WINDOW, UP, DOWN = 6, 4, 2  # promote with ≥4/6 good decisions in time, demote with ≤2/6


def complexity(p: Puzzle) -> float:
    """0..1 score of decision difficulty that is independent of rating: how many plausible
    (forcing) candidate moves there are, line length, whether the solver is defending, and how
    uncertain the puzzle's own rating is (Lichess rating deviation)."""
    board = chess.Board(p.fen)
    board.push(chess.Move.from_uci(p.moves.split()[0]))
    legal = list(board.legal_moves)
    forcing = sum(1 for m in legal if board.is_capture(m) or board.gives_check(m))
    themes = set(p.themes.split())
    score = 0.0
    score += min(forcing, 8) / 8 * 0.35          # many tempting forcing moves = multiple candidates
    score += min(len(legal), 45) / 45 * 0.15
    score += min(p.solution_len, 4) / 4 * 0.25
    score += 0.15 if themes & {"defensiveMove", "equality"} or board.is_check() else 0.0
    score += min(p.rating_deviation, 150) / 150 * 0.10  # high RD = high uncertainty about difficulty
    return round(score, 3)


def level_state(db: Session) -> dict:
    kv = db.get(KV, "pressure")
    if kv is None:
        kv = KV(key="pressure", value={"level": 1, "since_attempt_id": 0})
        db.add(kv)
        db.flush()
    return kv.value


def current_level(db: Session) -> dict:
    return LEVELS[level_state(db)["level"] - 1]


def update_level(db: Session) -> dict | None:
    kv = db.get(KV, "pressure")
    st = dict(level_state(db))
    rows = db.execute(select(Attempt).where(Attempt.mode == "pressure", Attempt.correct.is_not(None),
                                            Attempt.id > st["since_attempt_id"],
                                            Attempt.pressure_level == st["level"])
                      .order_by(Attempt.id.desc()).limit(WINDOW)).scalars().all()
    if len(rows) < WINDOW:
        return None
    good = sum(1 for a in rows if a.correct and not a.timed_out)
    new = st["level"]
    if good >= UP and st["level"] < len(LEVELS):
        new += 1
    elif good <= DOWN and st["level"] > 1:
        new -= 1
    if new == st["level"]:
        return None
    change = {"from": st["level"], "to": new, "good": good, "window": WINDOW}
    st["level"], st["since_attempt_id"] = new, rows[0].id
    kv = db.get(KV, "pressure")
    kv.value = st
    return change


def pressure_report(db: Session) -> dict:
    atts = db.execute(select(Attempt).where(Attempt.mode == "pressure", Attempt.correct.is_not(None))).scalars().all()
    by_level = {}
    for lv in LEVELS:
        xs = [a for a in atts if a.pressure_level == lv["level"]]
        if not xs:
            continue
        decided = [a for a in xs if not a.timed_out]
        used = [a.total_ms / a.time_limit_ms for a in decided if a.total_ms and a.time_limit_ms]
        losses = [a.cp_loss for a in decided if a.correct is False and a.cp_loss is not None]
        by_level[lv["level"]] = {
            "seconds": lv["seconds"], "n": len(xs),
            "decision_quality": wilson(sum(1 for a in decided if a.correct), len(decided)),
            "timeout_rate": wilson(sum(1 for a in xs if a.timed_out), len(xs)),
            "mean_time_used": round(sum(used) / len(used), 3) if used else None,
            "mean_cp_loss_when_wrong": round(sum(losses) / len(losses), 1) if losses else None,
        }
    return {"current": current_level(db), "levels": LEVELS, "by_level": by_level,
            "note": "A qualidade das decisões não conta os tempos estourados; a velocidade aparece separada."}
