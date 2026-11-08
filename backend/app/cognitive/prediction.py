"""PERFORMANCE PREDICTION — short-range trend estimates from your own data, with 95% intervals.

Never an Elo promise. Real-game metrics (accuracy, blunders per 100 moves) are reported first;
the puzzle rating trend is secondary. Below minimum sample sizes the answer is 'insufficient data'."""
from __future__ import annotations

from datetime import date, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models import Game, RatingPoint, utcnow
from .stats import ols, predict

MIN_GAMES = 10
MIN_RATING_DAYS = 14
HORIZONS = [14, 30]
DISCLAIMER = ("Trend extrapolation from your own past data with 95% prediction intervals. Learning is not linear, "
              "so treat this as 'where the current trend points', not a forecast or a promised rating. "
              "Puzzle ratings are not Chess.com ratings.")


def _days(d: date | datetime, origin: date) -> float:
    if isinstance(d, datetime):
        d = d.date()
    return float((d - origin).days)


def _trend(points: list[tuple[float, float]], horizons: list[int], last_x: float) -> dict:
    xs, ys = [p[0] for p in points], [p[1] for p in points]
    fit = ols(xs, ys)
    if fit is None:
        return {"status": "insufficient_variation"}
    return {
        "status": "ok", "n": fit["n"], "slope_per_30d": round(fit["slope"] * 30, 3),
        "slope_per_30d_ci": [round(fit["slope_low"] * 30, 3), round(fit["slope_high"] * 30, 3)],
        "direction_certain": fit["slope_low"] > 0 or fit["slope_high"] < 0,
        "forecasts": [{"days_ahead": h, **{k: round(v, 2) for k, v in predict(fit, last_x + h).items() if k != "x"}}
                      for h in horizons],
    }


def game_trajectory(db: Session) -> dict:
    games = db.execute(select(Game).where(Game.analyzed.is_(True))).scalars().all()
    games = [g for g in games if g.metrics.get("accuracy") is not None]
    if len(games) < MIN_GAMES:
        return {"status": "insufficient_data", "games": len(games), "needed": MIN_GAMES}
    games.sort(key=lambda g: (g.played_on or g.imported_at.date(), g.id))
    origin = games[0].played_on or games[0].imported_at.date()
    pts_acc, pts_bl = [], []
    for g in games:
        x = _days(g.played_on or g.imported_at, origin)
        pts_acc.append((x, float(g.metrics["accuracy"])))
        pts_bl.append((x, float(g.metrics.get("blunders_per_100") or 0)))
    last_x = pts_acc[-1][0]
    if last_x == 0:
        # all games on the same day: use game index instead of date
        pts_acc = [(i, y) for i, (_, y) in enumerate(pts_acc)]
        pts_bl = [(i, y) for i, (_, y) in enumerate(pts_bl)]
        return {"status": "ok", "x_unit": "game", "games": len(games),
                "accuracy": _trend(pts_acc, [10, 20], len(games) - 1),
                "blunders_per_100": _trend(pts_bl, [10, 20], len(games) - 1)}
    return {"status": "ok", "x_unit": "day", "games": len(games),
            "accuracy": _trend(pts_acc, HORIZONS, last_x), "blunders_per_100": _trend(pts_bl, HORIZONS, last_x)}


def puzzle_trajectory(db: Session) -> dict:
    pts = db.execute(select(RatingPoint).order_by(RatingPoint.id)).scalars().all()
    by_day: dict[date, float] = {}
    for p in pts:
        by_day[p.ts.date()] = p.rating  # last rating of each day
    if len(by_day) < MIN_RATING_DAYS:
        return {"status": "insufficient_data", "days": len(by_day), "needed": MIN_RATING_DAYS}
    days = sorted(by_day)
    origin = days[0]
    series = [(_days(d, origin), by_day[d]) for d in days]
    return {"status": "ok", "x_unit": "day", "days": len(days), "rating": _trend(series, HORIZONS, series[-1][0])}


def prediction_report(db: Session) -> dict:
    return {"generated_at": utcnow().isoformat(), "disclaimer": DISCLAIMER,
            "games": game_trajectory(db), "puzzle_rating": puzzle_trajectory(db)}
