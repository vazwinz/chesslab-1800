"""CLOSED-LOOP TRAINING: MEASURE → DIAGNOSE → INTERVENE → PRACTICE → REASSESS → ADAPT.

The loop is a persisted state machine (LoopCycle). It advances automatically after every
attempt and every game analysis. Outcomes prefer REAL GAME error rates whenever enough
games exist before and after an intervention; otherwise a mixed (non-targeted) puzzle
reassessment is used."""
from __future__ import annotations

import random

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models import Attempt, Game, GameMistake, InterventionAssignment, LoopCycle, utcnow
from . import interventions as iv
from ..timeutil import iso
from .error_dna import recurring_patterns

BASELINE_N = 20
REASSESS_N = 20
PRACTICE_N = 30
GAME_MIN_GAMES, GAME_MIN_MOVES = 3, 100
NON_TARGETED_MODES = ("standard", "assessment", "retention")


def current_cycle(db: Session) -> LoopCycle:
    c = db.execute(select(LoopCycle).where(LoopCycle.finished_at.is_(None)).order_by(LoopCycle.id.desc())
                   .limit(1)).scalar_one_or_none()
    if c is None:
        c = LoopCycle(phase="measure", baseline={"needed": BASELINE_N}, log=[], diagnosis={}, reassessment={},
                      adaptation={}, started_at=utcnow())
        db.add(c)
        db.flush()
        _log(c, "measure", "ciclo iniciado", code="cycle_started")
    return c


def _log(c: LoopCycle, phase: str, msg: str, **data) -> None:
    c.log = (c.log or []) + [{"ts": iso(utcnow()), "phase": phase, "msg": msg, **data}]
    c.updated_at = utcnow()


def puzzle_category_rate(attempts: list[Attempt], category: str) -> dict:
    graded = [a for a in attempts if a.correct is not None]
    n = len(graded)
    k = sum(1 for a in graded if a.error_category == category)
    return {"rate": (k / n) if n else None, "errors": k, "n": n}


def game_category_rate(db: Session, category: str, before=None, after=None) -> dict:
    q = select(Game).where(Game.analyzed.is_(True))
    if before is not None:
        q = q.where(Game.imported_at < before)
    if after is not None:
        q = q.where(Game.imported_at >= after)
    games = db.execute(q).scalars().all()
    ids = [g.id for g in games]
    moves = sum(int(g.metrics.get("user_moves", 0)) for g in games)
    k = 0
    if ids:
        k = len(db.execute(select(GameMistake.id).where(GameMistake.game_id.in_(ids),
                                                        GameMistake.category == category)).all())
    return {"rate": (k / moves) if moves else None, "errors": k, "moves": moves, "games": len(games)}


def baseline_attempts(db: Session, limit: int = 40) -> list[Attempt]:
    return list(db.execute(select(Attempt).where(Attempt.correct.is_not(None), Attempt.exercise_kind == "puzzle",
                                                 Attempt.mode.in_(NON_TARGETED_MODES))
                           .order_by(Attempt.id.desc()).limit(limit)).scalars())


def advance(db: Session, rng: random.Random | None = None) -> LoopCycle:
    """Move the loop forward as far as current data allows (idempotent)."""
    c = current_cycle(db)
    for _ in range(6):
        before = c.phase
        if c.phase == "measure":
            base = baseline_attempts(db)
            games = game_category_rate(db, "__none__")
            c.baseline = {"needed": c.baseline.get("needed", BASELINE_N), "attempts": len(base),
                          "games": games["games"]}
            if len(base) >= c.baseline["needed"] or games["games"] >= GAME_MIN_GAMES:
                c.phase = "diagnose"
                _log(c, "measure", "linha de base suficiente", code="baseline_sufficient", attempts=len(base), games=games["games"])
        elif c.phase == "diagnose":
            pats = recurring_patterns(db)
            targets = iv.weakness_targets(pats)
            if not targets:
                targets = [p for p in pats["patterns"] if p["count"] >= 2]
            if not targets:
                c.phase = "measure"
                c.baseline = {**c.baseline, "needed": c.baseline.get("needed", BASELINE_N) + BASELINE_N}
                _log(c, "diagnose", "nenhum erro recorrente ainda — coletando mais dados", code="no_recurring_error", needed=c.baseline["needed"])
                break
            top = targets[0]
            theme = top["top_themes"][0][0] if top["top_themes"] else None
            base = baseline_attempts(db)
            pre = {**puzzle_category_rate(base, top["category"]),
                   "games": game_category_rate(db, top["category"])}
            c.diagnosis = {"target": top["category"], "theme": theme, "patterns": pats["patterns"][:8]}
            _log(c, "diagnose", f"alvo = {top['category']}", code="target", category=top["category"], theme=theme)
            a = iv.start_assignment(db, top["category"], theme, c.id, pre, rng, target=PRACTICE_N)
            c.assignment_id = a.id
            c.phase = "practice"
            _log(c, "intervene", f"intervenção escolhida: {a.intervention_key}", code="assigned", intervention=a.intervention_key,
                 draws=a.params.get("draws"))
        elif c.phase == "practice":
            a = db.get(InterventionAssignment, c.assignment_id)
            if a is None:
                c.phase = "diagnose"
                continue
            if a.exercises_done >= a.exercises_target:
                c.phase = "reassess"
                last = db.execute(select(Attempt.id).order_by(Attempt.id.desc()).limit(1)).scalar() or 0
                c.reassessment = {"start_attempt_id": last, "needed": REASSESS_N}
                _log(c, "practice", "bloco de prática concluído", code="practice_done", exercises=a.exercises_done)
        elif c.phase == "reassess":
            start = c.reassessment.get("start_attempt_id", 0)
            atts = list(db.execute(select(Attempt).where(Attempt.id > start, Attempt.mode == "assessment",
                                                         Attempt.correct.is_not(None))).scalars())
            c.reassessment = {**c.reassessment, "done": len(atts)}
            if len(atts) >= c.reassessment.get("needed", REASSESS_N):
                c.phase = "adapt"
        elif c.phase == "adapt":
            a = db.get(InterventionAssignment, c.assignment_id)
            start = c.reassessment.get("start_attempt_id", 0)
            atts = list(db.execute(select(Attempt).where(Attempt.id > start, Attempt.mode == "assessment",
                                                         Attempt.correct.is_not(None))).scalars())
            post = puzzle_category_rate(atts, a.target_category)
            g_pre = game_category_rate(db, a.target_category, before=a.started_at)
            g_post = game_category_rate(db, a.target_category, after=a.started_at)
            use_games = (g_pre["games"] >= GAME_MIN_GAMES and g_post["games"] >= GAME_MIN_GAMES
                         and g_pre["moves"] >= GAME_MIN_MOVES and g_post["moves"] >= GAME_MIN_MOVES)
            if use_games:
                a.pre_metric = {**a.pre_metric, "rate": g_pre["rate"], "source": "games", "n": g_pre["moves"]}
                post_metric = {"rate": g_post["rate"], "n": g_post["moves"], "source": "games", "puzzles": post}
            else:
                post_metric = {**post, "source": "puzzle_reassessment", "games_after": g_post}
                a.pre_metric = {**a.pre_metric, "source": "puzzles"}
            result = iv.record_outcome(db, a, post_metric)
            c.adaptation = {"assignment": a.id, "intervention": a.intervention_key, "category": a.target_category,
                            "pre": a.pre_metric, "post": post_metric, **result}
            _log(c, "adapt", "resultado registrado", code="outcome_recorded", **{k: v for k, v in result.items() if k != "posterior"})
            c.phase = "done"
            c.finished_at = utcnow()
            nxt = LoopCycle(phase="diagnose", baseline={"from_previous_cycle": c.id, "needed": BASELINE_N}, log=[],
                            diagnosis={}, reassessment={}, adaptation={}, started_at=utcnow())
            db.add(nxt)
            db.flush()
            _log(nxt, "measure", "a reavaliação do ciclo anterior virou a nova medição", code="reassessment_reused", previous=c.id)
            c = nxt
        if c.phase == before:
            break
    db.flush()
    return c


def loop_status(db: Session) -> dict:
    c = current_cycle(db)
    a = db.get(InterventionAssignment, c.assignment_id) if c.assignment_id else None
    done = db.execute(select(LoopCycle).where(LoopCycle.finished_at.is_not(None)).order_by(LoopCycle.id.desc())
                      .limit(10)).scalars().all()
    return {
        "cycle_id": c.id, "phase": c.phase, "baseline": c.baseline, "diagnosis": c.diagnosis,
        "reassessment": c.reassessment, "log": (c.log or [])[-20:],
        "assignment": None if a is None else {
            "id": a.id, "intervention": a.intervention_key, "title": iv.CATALOG[a.intervention_key].title,
            "description": iv.CATALOG[a.intervention_key].description, "category": a.target_category,
            "theme": a.target_theme, "done": a.exercises_done, "target": a.exercises_target, "status": a.status,
            "offset": a.params.get("offset")},
        "history": [{"cycle_id": h.id, "adaptation": h.adaptation, "finished_at": iso(h.finished_at)}
                    for h in done],
        "steps": ["measure", "diagnose", "intervene", "practice", "reassess", "adapt"],
    }
