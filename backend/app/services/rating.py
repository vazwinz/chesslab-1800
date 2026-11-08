"""Glicko-1 rating of the local player against puzzles (puzzle ratings treated as fixed).
This is a PUZZLE rating, not an estimate of Chess.com playing strength."""
from __future__ import annotations

import math

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models import RatingPoint

Q = math.log(10) / 400
START_RATING, START_RD, MIN_RD, MAX_RD = 1200.0, 350.0, 50.0, 350.0


def expected_score(r: float, opp: float, opp_rd: float = 0.0) -> float:
    g = 1 / math.sqrt(1 + 3 * Q * Q * opp_rd * opp_rd / math.pi ** 2)
    return 1 / (1 + 10 ** (-g * (r - opp) / 400))


def glicko_update(r: float, rd: float, opp: float, opp_rd: float, score: float) -> tuple[float, float]:
    g = 1 / math.sqrt(1 + 3 * Q * Q * opp_rd * opp_rd / math.pi ** 2)
    e = 1 / (1 + 10 ** (-g * (r - opp) / 400))
    d2 = 1 / (Q * Q * g * g * e * (1 - e))
    denom = 1 / (rd * rd) + 1 / d2
    new_r = r + (Q / denom) * g * (score - e)
    new_rd = math.sqrt(1 / denom)
    return new_r, max(MIN_RD, min(MAX_RD, new_rd))


def current_rating(db: Session) -> tuple[float, float]:
    last = db.execute(select(RatingPoint).order_by(RatingPoint.id.desc()).limit(1)).scalar_one_or_none()
    if last is None:
        return START_RATING, START_RD
    return last.rating, last.rd
