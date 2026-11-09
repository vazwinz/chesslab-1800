"""Today's routine: a short list of concrete steps that the app counts by itself, ending with games
against the computer. Open the app, follow the steps, play the games; the mistakes of today's games
come back as tomorrow's first step.

It replaces the 0.4.0 "Plano do dia" (blocks of minutes ticked by hand). Each day's steps are kept in
`plan_blocks`, one row per step with its time estimate in `minutes`, so the calendar of days trained
goes on across the change. The day's targets live in the KV row "routine"."""
from __future__ import annotations

from datetime import date, datetime, time, timedelta, timezone

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..cognitive.attention import should_offer_light_day
from ..cognitive.retention import due_concepts
from ..models import KV, Attempt, OpeningDrill, PlanBlock, RepertoireLine, TrainingSession, utcnow
from . import play, puzzles
from .trainer import own_mistake_pool

KEY = "routine"
# in order; "light" is the target on a light day (0: the step is left out)
STEPS: dict[str, dict] = {
    "own_mistakes": {"title": "Seus erros de partida", "unit": ("posição", "posições"), "target": 5, "light": 3,
                     "minutes": 8, "to": "/treinar?modo=own_mistakes",
                     "why": "Posições em que você errou nas suas partidas, as mais recentes primeiro. Ache o lance que faltou."},
    "loop": {"title": "Treino em ciclo", "unit": ("puzzle", "puzzles"), "target": 15, "light": 8, "minutes": 20,
             "to": "/treinar?modo=loop", "why": "Mede você, acha o erro que mais se repete e treina exatamente ele."},
    "retention": {"title": "Revisão espaçada", "unit": ("puzzle", "puzzles"), "target": 5, "light": 5, "minutes": 6,
                  "to": "/treinar?modo=retention", "why": "Temas que você já aprendeu e estão na hora de rever."},
    "endgame": {"title": "Puzzles de final", "unit": ("puzzle", "puzzles"), "target": 5, "light": 0, "minutes": 8,
                "to": "/treinar?modo=endgame", "why": "Técnica de final, um pouco por dia."},
    "openings": {"title": "Seu repertório", "unit": ("lance", "lances"), "target": 15, "light": 0, "minutes": 8,
                 "to": "/aberturas", "why": "As linhas do seu repertório, de memória."},
    "games": {"title": "Partidas contra o AURA", "unit": ("partida", "partidas"), "target": 3, "light": 1, "minutes": 30,
              "to": "/jogar", "why": "No seu nível e sem voltar lance. Os erros de hoje viram os seus erros de partida de amanhã."},
}
SESSION_STEPS = ("own_mistakes", "loop", "retention", "endgame")  # counted by training-session kind


def _bounds(day: date) -> tuple[datetime, datetime]:
    """The local day as naive UTC times, which is how the database stores them."""
    def utc(d: date) -> datetime:
        return datetime.combine(d, time()).astimezone().astimezone(timezone.utc).replace(tzinfo=None)
    return utc(day), utc(day + timedelta(days=1))


def _has_repertoire(db: Session) -> bool:
    return db.execute(select(RepertoireLine.id).limit(1)).first() is not None


def _plan(db: Session, day: date, light: bool) -> list[tuple[str, int]]:
    """Which steps today, with their targets. A step that cannot be done today is left out (no game
    mistakes yet, no puzzles downloaded, nothing due for review)."""
    out: list[tuple[str, int]] = []

    def add(key: str, available: int | None = None) -> None:
        target = STEPS[key]["light" if light else "target"]
        if available is not None:
            target = min(target, available)
        if target > 0:
            out.append((key, target))

    pool = len(own_mistake_pool(db))
    if pool:
        add("own_mistakes", pool)
    has_puzzles = puzzles.puzzle_count(db) > 0
    if has_puzzles:
        add("loop")
        due = len(due_concepts(db, limit=50))
        if due:
            add("retention", due)
    # endgames and the repertoire take turns, one each day
    side = "openings" if (day.toordinal() % 2 and _has_repertoire(db)) else "endgame"
    if side == "endgame" and not (has_puzzles and puzzles.themed_any(db, puzzles.ENDGAME_THEMES)):
        side = "openings" if _has_repertoire(db) else None
    if side:
        add(side)
    add("games")
    return out


def _minutes(key: str, target: int) -> int:
    s = STEPS[key]
    return max(2, round(s["minutes"] * target / s["target"]))


def _done(db: Session, key: str, day: date) -> int:
    lo, hi = _bounds(day)
    if key in SESSION_STEPS:
        return db.execute(select(func.count()).select_from(Attempt)
                          .join(TrainingSession, TrainingSession.id == Attempt.session_id)
                          .where(TrainingSession.kind == key, Attempt.finished_at >= lo, Attempt.finished_at < hi)).scalar() or 0
    if key == "openings":
        return db.execute(select(func.count()).select_from(OpeningDrill)
                          .where(OpeningDrill.ts >= lo, OpeningDrill.ts < hi)).scalar() or 0
    if key == "games":
        return play.games_on(db, day)
    return 0


def _rows(db: Session, day: date) -> list[PlanBlock]:
    return list(db.execute(select(PlanBlock).where(PlanBlock.day == day).order_by(PlanBlock.id)).scalars())


def _is_step(r: PlanBlock) -> bool:
    """A routine step, not a block of the 0.4.0 plan (two of whose keys, "openings" and "games", were reused)."""
    return r.key in STEPS and r.title == STEPS[r.key]["title"]


def _steps(db: Session, day: date) -> list[PlanBlock]:
    order = list(STEPS)
    return sorted((r for r in _rows(db, day) if _is_step(r)), key=lambda r: order.index(r.key))


def _day(db: Session, day: date) -> dict:
    """The KV record of the day: which steps it has ("keys", fixed when the day is first planned) and
    their targets."""
    kv = db.get(KV, KEY)
    if kv and isinstance(kv.value, dict) and kv.value.get("day") == day.isoformat():
        return dict(kv.value)
    return {}


def _fill(db: Session, day: date, light: bool, keep: list[PlanBlock]) -> None:
    """Add the day's steps that are not among `keep`, with the targets of a full or a light day. The
    kinds of step are fixed the first time the day is planned: switching to a light day only shortens
    or drops steps, it never brings in one that was not there (say, the mistakes of a game just played)."""
    rec = _day(db, day)
    keys = rec.get("keys") or [k for k, _ in _plan(db, day, False)]
    targets = dict(rec.get("targets") or {})
    have = {r.key for r in keep}
    for key, target in _plan(db, day, light):
        if key in have or key not in keys:
            continue
        db.add(PlanBlock(day=day, key=key, title=STEPS[key]["title"], minutes=_minutes(key, target), light_day=light))
        targets[key] = target
    value = {"day": day.isoformat(), "keys": keys, "targets": targets}
    kv = db.get(KV, KEY)
    if kv is None:
        db.add(KV(key=KEY, value=value))
    else:
        kv.value = value
    db.commit()


def today(db: Session, day: date | None = None) -> dict:
    day = day or date.today()
    rows = _rows(db, day)
    # a day planned by 0.4.0: its unticked blocks give way to the routine (ticked ones stay in the calendar)
    old = [r for r in rows if not _is_step(r) and not r.completed]
    for r in old:
        db.delete(r)
    if old:
        db.commit()
    steps = _steps(db, day)
    advice = should_offer_light_day(db)
    if not steps:
        _fill(db, day, advice["light_day"], [])
        steps = _steps(db, day)
    targets = _day(db, day).get("targets") or {}

    out, changed = [], False
    for r in steps:
        s = STEPS[r.key]
        target = targets.get(r.key) or s["light" if r.light_day else "target"] or s["target"]
        done = _done(db, r.key, day)
        # nothing left to do in that mode counts as done (every mistake already seen, nothing due)
        exhausted = (r.key == "own_mistakes" and not own_mistake_pool(db)) or \
                    (r.key == "retention" and not due_concepts(db, limit=1))
        if not r.completed and (done >= target or exhausted):
            r.completed, r.completed_at, changed = True, utcnow(), True
        out.append({"id": r.id, "key": r.key, "title": r.title, "why": s["why"], "to": s["to"], "done": done,
                    "target": target, "unit": s["unit"][0] if target == 1 else s["unit"][1], "minutes": r.minutes,
                    "completed": r.completed})
    if changed:
        db.commit()
    current = next((x["key"] for x in out if not x["completed"]), None)
    return {"day": day.isoformat(), "light_day": any(r.light_day for r in steps), "light_day_advice": advice,
            "steps": out, "current": current, "finished": bool(out) and current is None,
            "minutes_left": sum(x["minutes"] for x in out if not x["completed"]),
            "streak_days": consistency(db, 28)["streak_days"]}


def set_light(db: Session, light: bool) -> dict:
    """Switch today between the full and the light routine. Steps already done stay done."""
    day = date.today()
    today(db, day)  # first record what is already done, so a finished step is not planned again
    rows = _steps(db, day)
    keep = [r for r in rows if r.completed]
    for r in rows:
        if not r.completed:
            db.delete(r)
    db.commit()
    _fill(db, day, light, keep)
    return today(db, day)


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
