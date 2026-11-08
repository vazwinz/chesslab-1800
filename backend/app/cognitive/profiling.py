"""COGNITIVE PROFILING — observable chess-performance measures only.

These are behavioural measures from YOUR attempts and games (accuracy, timing, success by
line length...). They are not measures of IQ, brain activity, working-memory capacity or any
clinical/psychological trait. Each metric reports its sample size and a 95% interval, and says
"insufficient data" instead of guessing."""
from __future__ import annotations

from collections import defaultdict
from datetime import timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models import Attempt, Game, GameMistake, utcnow
from .stats import median, wilson

MIN_N = 10


def _rate(rows: list[bool]) -> dict:
    w = wilson(sum(rows), len(rows))
    w["sufficient"] = len(rows) >= MIN_N
    return w


def _residual(attempts: list[Attempt]) -> float | None:
    """Mean of (actual - expected) success, i.e. performance relative to puzzle difficulty."""
    xs = [int(bool(a.correct)) - a.expected_score for a in attempts if a.expected_score is not None]
    return round(sum(xs) / len(xs), 3) if xs else None


def build_profile(db: Session, days: int = 60) -> dict:
    since = utcnow() - timedelta(days=days)
    atts = db.execute(select(Attempt).where(Attempt.correct.is_not(None), Attempt.served_at >= since,
                                            Attempt.exercise_kind == "puzzle")).scalars().all()
    standard = [a for a in atts if a.mode in ("standard", "assessment", "intervention", "retention")]
    themes_of = {a.id: set((a.themes or "").split()) for a in atts}

    # 1 pattern recognition: first-move accuracy on short (1–2 move) puzzles, board visible
    short = [a for a in standard if (a.solution_len or 1) <= 2]
    first_move_ok = [a.correct or (a.fail_ply or 0) > 0 for a in short]
    # 2 calculation: success by solution length + blind-mode accuracy
    by_len: dict[int, list[bool]] = defaultdict(list)
    for a in standard:
        by_len[min(a.solution_len or 1, 5)].append(bool(a.correct))
    depth_reached = 0
    for length in sorted(by_len):
        r = by_len[length]
        if len(r) >= 5 and sum(r) / len(r) >= 0.5:
            depth_reached = length
    blind = [a for a in atts if a.mode == "blind"]
    # 3 threat detection: defensive puzzles + share of game errors that were missed threats
    defensive = [bool(a.correct) for a in atts if themes_of[a.id] & {"defensiveMove", "equality"}]
    gm = db.execute(select(GameMistake).where(GameMistake.created_at >= since)).scalars().all()
    games = db.execute(select(Game).where(Game.analyzed.is_(True))).scalars().all()
    user_moves = sum(int(g.metrics.get("user_moves", 0)) for g in games)
    missed_threats = sum(1 for m in gm if m.category == "missed_opponent_threat")
    # 4 candidate generation: candidates mode — was the engine's best move among the listed candidates?
    cand = [a for a in atts if a.mode == "candidates" and a.candidate_score is not None]
    # 5 working-memory demand: board-visible vs blind accuracy at equal line length
    wm = []
    for length in range(1, 6):
        vis = by_len.get(length, [])
        bl = [bool(a.correct) for a in blind if min(a.solution_len or 1, 5) == length]
        if vis or bl:
            wm.append({"solution_len": length, "board": wilson(sum(vis), len(vis)), "blind": wilson(sum(bl), len(bl))})
    # 6 decision latency
    first_ms_ok = [a.first_move_ms for a in standard if a.correct and a.first_move_ms]
    first_ms_bad = [a.first_move_ms for a in standard if a.correct is False and a.first_move_ms]
    # 7 consistency under time pressure
    pressure = [a for a in atts if a.mode == "pressure"]
    p_decided = [a for a in pressure if not a.timed_out]
    low_clock_err = sum(int(g.metrics.get("low_clock_errors", 0)) for g in games)
    low_clock_moves = sum(int(g.metrics.get("low_clock_moves", 0)) for g in games)

    return {
        "window_days": days,
        "disclaimer": "Observable chess performance only. Not a measure of intelligence, brain activity or any "
                      "clinical or psychological trait.",
        "pattern_recognition": {"description": "First-move accuracy on 1–2 move puzzles (board visible)",
                                **_rate(first_move_ok), "rating_adjusted_residual": _residual(short)},
        "calculation": {
            "description": "Success rate by number of moves to find; 'depth' = longest line solved ≥50% (n≥5)",
            "by_length": {str(k): wilson(sum(v), len(v)) for k, v in sorted(by_len.items())},
            "depth_reached": depth_reached if by_len else None,
            "blind_accuracy": _rate([bool(a.correct) for a in blind]),
        },
        "threat_detection": {
            "description": "Accuracy on defensive puzzles; missed-threat errors per 100 analysed game moves",
            "defensive_puzzles": _rate(defensive),
            "game_missed_threats_per_100": round(100 * missed_threats / user_moves, 2) if user_moves else None,
            "game_moves_analysed": user_moves,
        },
        "candidate_generation": {
            "description": "Candidates mode: fraction of positions where Stockfish's best move was in your list",
            "n": len(cand), "sufficient": len(cand) >= MIN_N,
            "mean_score": round(sum(a.candidate_score for a in cand) / len(cand), 3) if cand else None,
        },
        "working_memory_load": {
            "description": "Accuracy with the board visible vs. blind, at equal line length. A large drop means "
                           "lines that must be held mentally are a bottleneck (a task measure, not a capacity test).",
            "by_length": wm,
        },
        "decision_latency": {
            "description": "Time to first move (ms)",
            "median_correct_ms": median(first_ms_ok), "median_wrong_ms": median(first_ms_bad),
            "n_correct": len(first_ms_ok), "n_wrong": len(first_ms_bad),
        },
        "time_pressure_consistency": {
            "description": "Decision quality in pressure mode (excluding timeouts) vs. normal mode, and error rate "
                           "of game moves made in time trouble",
            "pressure_quality": _rate([bool(a.correct) for a in p_decided]),
            "pressure_timeouts": {"n": len(pressure), "timeouts": sum(1 for a in pressure if a.timed_out)},
            "normal_quality": _rate([bool(a.correct) for a in standard]),
            "pressure_residual": _residual(p_decided), "normal_residual": _residual(standard),
            "game_low_clock_error_rate": wilson(low_clock_err, low_clock_moves),
        },
        "sample": {"puzzle_attempts": len(atts), "analysed_games": len(games)},
    }
