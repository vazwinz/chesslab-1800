"""Dashboard statistics — computed only from stored attempts, ratings, games and plan rows."""
from __future__ import annotations

from collections import defaultdict
from datetime import date, timedelta

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..cognitive.stats import wilson
from ..models import Attempt, Game, RatingPoint, TrainingSession
from . import adaptive
from .plan import consistency
from .rating import current_rating

MIN_THEME_N = 5


def overview(db: Session) -> dict:
    graded = db.execute(select(Attempt).where(Attempt.correct.is_not(None))).scalars().all()
    puzzles = [a for a in graded if a.exercise_kind == "puzzle"]
    r, rd = current_rating(db)
    solved = sum(1 for a in puzzles if a.correct)
    # time per day (measured solving time)
    per_day: dict[date, float] = defaultdict(float)
    for a in graded:
        if a.total_ms:
            per_day[a.served_at.date()] += a.total_ms / 60000
    start = date.today() - timedelta(days=27)
    daily = [{"day": (start + timedelta(days=i)).isoformat(), "minutes": round(per_day.get(start + timedelta(days=i), 0), 1)}
             for i in range(28)]
    # themes
    theme_stats: dict[str, list[bool]] = defaultdict(list)
    for a in puzzles:
        for t in (a.themes or "").split():
            theme_stats[t].append(bool(a.correct))
    themes = [{"theme": t, **wilson(sum(v), len(v))} for t, v in theme_stats.items() if len(v) >= MIN_THEME_N]
    weakest = sorted(themes, key=lambda x: x["rate"])[:6]
    strongest = sorted(themes, key=lambda x: -x["rate"])[:6]
    # by band
    by_band = []
    for b in adaptive.BANDS:
        xs = [bool(a.correct) for a in puzzles if a.puzzle_rating and b["min"] <= a.puzzle_rating < b["max"]]
        by_band.append({"band": b["label"], "range": f"{b['min']}–{b['max']}", **wilson(sum(xs), len(xs))})
    # streak of consecutive correct answers
    streak = 0
    for a in sorted(puzzles, key=lambda a: a.id, reverse=True):
        if a.correct:
            streak += 1
        else:
            break
    times = sorted(a.total_ms for a in puzzles if a.correct and a.total_ms)
    rating_series = db.execute(select(RatingPoint.ts, RatingPoint.rating).order_by(RatingPoint.id)).all()
    # down-sample for charts
    step = max(1, len(rating_series) // 300)
    sessions = db.execute(select(TrainingSession).order_by(TrainingSession.id.desc()).limit(15)).scalars().all()
    hist = []
    for s in sessions:
        xs = db.execute(select(Attempt.correct, func.coalesce(Attempt.total_ms, 0)).where(
            Attempt.session_id == s.id, Attempt.correct.is_not(None))).all()
        hist.append({"id": s.id, "kind": s.kind, "theme": s.theme, "started_at": s.started_at.isoformat(),
                     "attempts": len(xs), "correct": sum(1 for c, _ in xs if c),
                     "minutes": round(sum(t for _, t in xs) / 60000, 1), "break_suggested": s.break_suggested_at is not None})
    games = db.execute(select(Game).where(Game.analyzed.is_(True)).order_by(Game.played_on, Game.id)).scalars().all()
    return {
        "has_data": bool(graded),
        "rating": {"current": round(r), "rd": round(rd), "provisional": rd > 110,
                   "series": [{"ts": t.isoformat(), "rating": round(v, 1)} for t, v in rating_series[::step]],
                   "note": "Puzzle rating (Glicko-1 vs. Lichess puzzle ratings). Not a Chess.com rating."},
        "band": adaptive.band_for(db),
        "totals": {"attempts": len(puzzles), "solved": solved, "accuracy": wilson(solved, len(puzzles)),
                   "current_streak": streak, "median_solve_ms": times[len(times) // 2] if times else None,
                   "mistakes": len(puzzles) - solved},
        "daily_minutes": daily, "weakest_themes": weakest, "strongest_themes": strongest, "by_band": by_band,
        "consistency": consistency(db), "history": hist,
        "games": [{"id": g.id, "date": g.played_on.isoformat() if g.played_on else None, "white": g.white,
                   "black": g.black, "result": g.result, **{k: g.metrics.get(k) for k in
                   ("accuracy", "acpl", "blunders", "mistakes", "inaccuracies", "user_moves")}} for g in games],
    }
