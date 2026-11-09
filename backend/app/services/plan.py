"""Daily training program (~3 h by default) with a lighter day when fatigue / poor results accumulate."""
from __future__ import annotations

from datetime import date, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..cognitive.attention import should_offer_light_day
from ..models import KV, PlanBlock, utcnow

DEFAULT_BLOCKS = [
    {"key": "tactics", "title": "Padrões táticos", "minutes": 40},
    {"key": "calculation", "title": "Cálculo profundo", "minutes": 30},
    {"key": "endgames", "title": "Finais", "minutes": 30},
    {"key": "openings", "title": "Preparação de aberturas", "minutes": 25},
    {"key": "games", "title": "Partidas sérias", "minutes": 45},
    {"key": "analysis", "title": "Análise dos erros", "minutes": 10},
]
LIGHT_FACTOR = {"tactics": 0.5, "calculation": 0.5, "endgames": 0.5, "openings": 0.4, "games": 0.0, "analysis": 1.0}


def get_config(db: Session) -> list[dict]:
    kv = db.get(KV, "plan_config")
    return kv.value["blocks"] if kv else DEFAULT_BLOCKS


def set_config(db: Session, blocks: list[dict]) -> list[dict]:
    clean = [{"key": b["key"], "title": b["title"], "minutes": max(0, int(b["minutes"]))} for b in blocks]
    kv = db.get(KV, "plan_config")
    if kv is None:
        db.add(KV(key="plan_config", value={"blocks": clean}))
    else:
        kv.value = {"blocks": clean}
    db.commit()
    return clean


def today(db: Session, day: date | None = None, light: bool | None = None) -> dict:
    day = day or date.today()
    rows = db.execute(select(PlanBlock).where(PlanBlock.day == day).order_by(PlanBlock.id)).scalars().all()
    advice = should_offer_light_day(db)
    if not rows:
        use_light = advice["light_day"] if light is None else light
        for b in get_config(db):
            mins = round(b["minutes"] * (LIGHT_FACTOR.get(b["key"], 0.5) if use_light else 1))
            if mins > 0:
                db.add(PlanBlock(day=day, key=b["key"], title=b["title"], minutes=mins, light_day=use_light))
        db.commit()
        rows = db.execute(select(PlanBlock).where(PlanBlock.day == day).order_by(PlanBlock.id)).scalars().all()
    return {"day": day.isoformat(), "light_day": any(r.light_day for r in rows), "light_day_advice": advice,
            "blocks": [{"id": r.id, "key": r.key, "title": r.title, "minutes": r.minutes, "completed": r.completed}
                       for r in rows]}


def regenerate(db: Session, light: bool) -> dict:
    db.query(PlanBlock).filter(PlanBlock.day == date.today(), PlanBlock.completed.is_(False)).delete()
    done = db.execute(select(PlanBlock).where(PlanBlock.day == date.today())).scalars().all()
    if done:
        db.commit()
        return today(db)
    db.commit()
    return today(db, light=light)


def complete(db: Session, block_id: int, completed: bool = True) -> dict:
    b = db.get(PlanBlock, block_id)
    if b is None:
        raise KeyError(block_id)
    b.completed, b.completed_at = completed, (utcnow() if completed else None)
    db.commit()
    return today(db, b.day)


def consistency(db: Session, days: int = 28) -> dict:
    start = date.today() - timedelta(days=days - 1)
    rows = db.execute(select(PlanBlock).where(PlanBlock.day >= start)).scalars().all()
    per_day: dict[date, list[PlanBlock]] = {}
    for r in rows:
        per_day.setdefault(r.day, []).append(r)
    series = []
    for i in range(days):
        d = start + timedelta(days=i)
        bl = per_day.get(d, [])
        planned = sum(b.minutes for b in bl)
        done = sum(b.minutes for b in bl if b.completed)
        series.append({"day": d.isoformat(), "planned_min": planned, "completed_min": done,
                       "completion": (done / planned) if planned else None})
    streak = 0
    for s in reversed(series):
        if s["completed_min"] > 0:
            streak += 1
        elif s["day"] != date.today().isoformat():
            break
    last7 = series[-7:]
    return {"series": series, "streak_days": streak,
            "days_trained_last_7": sum(1 for s in last7 if s["completed_min"] > 0),
            "completion_last_7": (sum(s["completed_min"] for s in last7) / sum(s["planned_min"] for s in last7))
            if sum(s["planned_min"] for s in last7) else None}
