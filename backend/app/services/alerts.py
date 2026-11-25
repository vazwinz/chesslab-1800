"""The warning of the day: the kind of mistake (Error DNA category) you missed most in today's session of
"Seus erros de partida", in one line, with the count behind it ("3 dos 4 erros de hoje foram assim").
The next day it shows again on the start screen and before a game, with how often that kind of mistake
came up in your games before it and since. Nothing is stored: it is computed from the attempts."""
from __future__ import annotations

from collections import Counter
from datetime import date, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..cognitive.error_dna import INFO
from ..models import Attempt, Game, GameMistake
from .moments import SEVERITIES

HEADLINES = {
    "impulsive_decision": "Seus lances estão impulsivos.",
    "missed_opponent_threat": "Você está ignorando as ameaças dele.",
    "tactical_blindness": "Você está deixando passar táticas.",
    "calculation_error": "Seus cálculos estão parando cedo.",
    "poor_candidate_selection": "Você está olhando poucos lances antes de escolher.",
    "positional_misunderstanding": "Seus erros de hoje foram de posição, não de tática.",
    "time_management_failure": "Você está se enrolando no relógio.",
    "endgame_technique_failure": "Você está escorregando nos finais.",
}
LOOK_BACK_DAYS = 14  # how far back the last day with a warning is looked for


def _label(category: str) -> str:
    return (INFO.get(category) or {}).get("name") or category


def alert(db: Session, day: date) -> dict | None:
    """The warning of `day`: the category you missed most in the session (ties: the latest one)."""
    from .routine import _bounds

    lo, hi = _bounds(day)
    rows = db.execute(select(GameMistake.category, Attempt.finished_at)
                      .join(GameMistake, GameMistake.id == Attempt.game_mistake_id)
                      .where(Attempt.mode == "daily_review", Attempt.correct.is_(False),
                             Attempt.finished_at >= lo, Attempt.finished_at < hi)
                      .order_by(Attempt.finished_at)).all()
    rows = [(c, t) for c, t in rows if c in HEADLINES]
    if not rows:
        return None
    counts = Counter(c for c, _ in rows)
    top = max(counts.values())
    latest_at = {c: t for c, t in rows}
    cat = max((c for c, n in counts.items() if n == top), key=lambda c: latest_at[c])
    return {"category": cat, "label": _label(cat), "text": HEADLINES[cat], "count": counts[cat], "wrong": len(rows)}


def trend(db: Session, category: str, day: date) -> dict:
    """That category's mistakes in your games of the week up to the warning's day, and of the week after
    it (only games judged with the current criteria)."""
    def count(lo: date, hi: date) -> tuple[int, int]:
        games = [g for g in db.execute(select(Game).where(Game.analyzed.is_(True), Game.user_color.is_not(None),
                                                           Game.played_on >= lo, Game.played_on <= hi)).scalars()
                 if int((g.metrics or {}).get("criteria") or 1) >= 2]
        ids = [g.id for g in games]
        n = len(db.execute(select(GameMistake.id).where(GameMistake.game_id.in_(ids), GameMistake.category == category,
                                                        GameMistake.severity.in_(SEVERITIES))).all()) if ids else 0
        return n, len(games)

    before, games_before = count(day - timedelta(days=6), day)
    after, games_after = count(day + timedelta(days=1), day + timedelta(days=7))
    return {"before": before, "after": after, "games_before": games_before, "games_after": games_after}


def latest(db: Session, day: date) -> dict | None:
    """The warning of the last day before `day` that had one, with its trend."""
    for back in range(1, LOOK_BACK_DAYS + 1):
        d = day - timedelta(days=back)
        a = alert(db, d)
        if a:
            return {**a, "day": d.isoformat(), "trend": trend(db, a["category"], d)}
    return None


def state(db: Session, day: date | None = None) -> dict:
    day = day or date.today()
    return {"today": alert(db, day), "active": latest(db, day)}
