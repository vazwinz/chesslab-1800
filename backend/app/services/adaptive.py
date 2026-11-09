"""Adaptive difficulty (base system). Bands are PUZZLE rating ranges, not Chess.com Elo.
Difficulty only moves after a consistent run of results, never after a single puzzle."""
from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models import KV, Attempt

BANDS = [
    {"key": "beginner", "label": "Iniciante", "min": 800, "max": 1000},
    {"key": "intermediate", "label": "Intermediário", "min": 1000, "max": 1300},
    {"key": "developing", "label": "Em evolução", "min": 1300, "max": 1500},
    {"key": "advanced", "label": "Avançado", "min": 1500, "max": 1800},
    {"key": "expert", "label": "Desafio forte", "min": 1800, "max": 2600},
]
PROMOTE_ACC, DEMOTE_ACC = 0.80, 0.45
MIN_PROMOTE_N, MIN_DEMOTE_N = 10, 8
ADAPTIVE_MODES = ("standard", "blind", "candidates")


def _state(db: Session) -> KV:
    kv = db.get(KV, "adaptive")
    if kv is None:
        kv = KV(key="adaptive", value={"band": 0, "since_attempt_id": 0, "history": []})
        db.add(kv)
        db.flush()
    return kv


def band_for(db: Session) -> dict:
    st = _state(db).value
    return {**BANDS[st["band"]], "index": st["band"]}


def update_after_attempt(db: Session) -> dict | None:
    """Re-evaluate the band. Returns a change record when the band moved."""
    kv = _state(db)
    st = dict(kv.value)
    band = BANDS[st["band"]]
    rows = db.execute(
        select(Attempt.correct, Attempt.puzzle_rating)
        .where(Attempt.id > st.get("since_attempt_id", 0), Attempt.correct.is_not(None),
               Attempt.exercise_kind == "puzzle", Attempt.mode.in_(ADAPTIVE_MODES))
        .order_by(Attempt.id.desc()).limit(15)
    ).all()
    in_band = [c for c, r in rows if r is not None and band["min"] - 50 <= r <= band["max"] + 50]
    change = None
    if len(in_band) >= MIN_PROMOTE_N and sum(in_band) / len(in_band) >= PROMOTE_ACC and st["band"] < len(BANDS) - 1:
        change = {"from": st["band"], "to": st["band"] + 1, "accuracy": sum(in_band) / len(in_band), "n": len(in_band)}
    elif len(in_band) >= MIN_DEMOTE_N and sum(in_band) / len(in_band) <= DEMOTE_ACC and st["band"] > 0:
        change = {"from": st["band"], "to": st["band"] - 1, "accuracy": sum(in_band) / len(in_band), "n": len(in_band)}
    if change:
        last_id = db.execute(select(Attempt.id).order_by(Attempt.id.desc()).limit(1)).scalar() or 0
        st["band"] = change["to"]
        st["since_attempt_id"] = last_id
        st["history"] = (st.get("history", []) + [change])[-50:]
        kv.value = st
    return change


def target_rating(db: Session, user_rating: float, offset: int = 0) -> tuple[int, int]:
    """Rating window for the next puzzle: around the player's rating, clamped to the band."""
    b = band_for(db)
    centre = min(max(user_rating + offset, b["min"]), b["max"])
    return int(centre - 100), int(centre + 100)
