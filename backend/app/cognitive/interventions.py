"""ADAPTIVE INTERVENTION ENGINE — chooses exercises aimed at measured recurring errors,
with controlled difficulty, interleaving and spaced reviews, and learns per user which
interventions actually reduce each error category (Thompson sampling on Beta posteriors)."""
from __future__ import annotations

import random
from dataclasses import dataclass, field

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models import Attempt, InterventionAssignment, InterventionStat, utcnow

INTERLEAVE_EVERY = 4
TARGET_SUCCESS = (0.70, 0.85)
OFFSET_BOUNDS = (-350, 200)


@dataclass
class Intervention:
    key: str
    title: str
    targets: list[str]
    description: str
    mode: str = "intervention"
    themes: list[str] = field(default_factory=list)
    min_len: int | None = None
    max_len: int | None = None
    start_offset: int = -150          # start below current rating: learn the pattern first
    min_think_ms: int | None = None   # board locked for this long (anti-impulsivity)
    blind: bool = False
    candidates: bool = False
    own_games: bool = False           # positions from the user's own analysed mistakes
    time_limit_s: int | None = None
    principles: list[str] = field(default_factory=list)


CATALOG: dict[str, Intervention] = {i.key: i for i in [
    Intervention("pattern_drill", "Pattern drill", ["tactical_blindness"],
                 "Many short puzzles of the motifs you miss, below your rating, then interleaved.",
                 themes=[], max_len=2, start_offset=-200,
                 principles=["deliberate_practice", "active_retrieval", "interleaving", "feedback"]),
    Intervention("blind_ladder", "Blind calculation ladder", ["calculation_error"],
                 "Calculate the whole line before touching a piece; line length grows as you succeed.",
                 min_len=2, start_offset=-250, blind=True,
                 principles=["active_retrieval", "progressive_challenge", "feedback"]),
    Intervention("threat_scan", "Threat scan (defence)", ["missed_opponent_threat"],
                 "Defensive puzzles. Before moving, ask: what does my opponent threaten?",
                 themes=["defensiveMove", "equality"], start_offset=-150, min_think_ms=8000,
                 principles=["deliberate_practice", "feedback"]),
    Intervention("slow_down", "Slow-down protocol", ["impulsive_decision"],
                 "Board stays locked for a minimum thinking time: checks, captures, threats — then move.",
                 start_offset=-100, min_think_ms=15000,
                 principles=["deliberate_practice", "feedback"]),
    Intervention("candidate_listing", "Candidate listing", ["poor_candidate_selection", "positional_misunderstanding"],
                 "Write down 3 candidate moves before playing; scored against Stockfish's top lines.",
                 themes=["quietMove", "defensiveMove", "intermezzo"], start_offset=-150, candidates=True,
                 principles=["deliberate_practice", "feedback"]),
    Intervention("own_mistakes", "Your own game mistakes", ["positional_misunderstanding", "tactical_blindness",
                                                            "missed_opponent_threat", "calculation_error",
                                                            "poor_candidate_selection", "endgame_technique_failure"],
                 "Positions where you went wrong in your real games: find the better move.",
                 own_games=True, start_offset=0,
                 principles=["deliberate_practice", "active_retrieval", "feedback"]),
    Intervention("endgame_technique", "Endgame technique", ["endgame_technique_failure"],
                 "Endgame puzzles (rook, pawn, minor-piece, queen) at controlled difficulty.",
                 themes=["rookEndgame", "pawnEndgame", "endgame", "knightEndgame", "bishopEndgame", "queenEndgame"],
                 start_offset=-200, principles=["deliberate_practice", "progressive_challenge"]),
    Intervention("clock_ladder", "Clock ladder", ["time_management_failure"],
                 "Comfortable puzzles under a shrinking time budget to build fast, safe decisions.",
                 start_offset=-250, time_limit_s=40,
                 principles=["progressive_challenge", "deliberate_practice"]),
]}


def weakness_targets(patterns: dict, min_count: int = 3) -> list[dict]:
    """Recurring categories, strongest first."""
    return [p for p in patterns["patterns"] if p["count"] >= min_count and p["recurring"]]


def _stat(db: Session, key: str, cat: str) -> InterventionStat:
    st = db.get(InterventionStat, (key, cat))
    if st is None:
        st = InterventionStat(intervention_key=key, target_category=cat, alpha=1.0, beta=1.0, trials=0, mean_effect=0.0)
        db.add(st)
        db.flush()
    return st


def choose_intervention(db: Session, category: str, rng: random.Random | None = None) -> tuple[Intervention, dict]:
    """Thompson sampling among interventions designed for this category. Each draw comes from
    the user's own Beta posterior of 'this intervention reduced this error'."""
    rng = rng or random.Random()
    options = [i for i in CATALOG.values() if category in i.targets]
    if not options:
        options = [CATALOG["own_mistakes"]]
    draws = {}
    for i in options:
        st = _stat(db, i.key, category)
        # interventions designed primarily for the category get a mild prior advantage
        bonus = 1.0 if i.targets[0] == category else 0.0
        draws[i.key] = rng.betavariate(st.alpha + bonus, st.beta)
    best = max(options, key=lambda i: draws[i.key])
    return best, draws


def assignment_offset(db: Session, a: InterventionAssignment) -> int:
    """Controlled difficulty: keep success in the target band using the last 6 attempts."""
    rows = db.execute(select(Attempt.correct).where(Attempt.assignment_id == a.id, Attempt.correct.is_not(None),
                                                    Attempt.mode == "intervention")
                      .order_by(Attempt.id.desc()).limit(6)).scalars().all()
    off = int(a.params.get("offset", CATALOG[a.intervention_key].start_offset))
    if len(rows) >= 6:
        rate = sum(bool(r) for r in rows) / len(rows)
        if rate > TARGET_SUCCESS[1]:
            off += 50
        elif rate < TARGET_SUCCESS[0] - 0.1:
            off -= 50
    return max(OFFSET_BOUNDS[0], min(OFFSET_BOUNDS[1], off))


def exercise_spec(db: Session, a: InterventionAssignment) -> dict:
    """What the next exercise of this assignment should be."""
    iv = CATALOG[a.intervention_key]
    n = a.exercises_done
    off = assignment_offset(db, a)
    params = dict(a.params)
    params["offset"] = off
    a.params = params
    interleave = n > 0 and n % INTERLEAVE_EVERY == INTERLEAVE_EVERY - 1
    themes = list(iv.themes)
    if a.target_theme and not themes:
        themes = [a.target_theme]
    min_len = iv.min_len
    if iv.blind:  # ladder: grow the required line length with success
        min_len = 2 + min(3, max(0, off - iv.start_offset) // 100)
    spec = {
        "intervention": iv.key, "mode": "intervention", "themes": themes, "offset": off, "min_len": min_len,
        "max_len": iv.max_len, "min_think_ms": iv.min_think_ms, "blind": iv.blind, "candidates": iv.candidates,
        "own_games": iv.own_games and not interleave, "interleaved": interleave,
        "time_limit_s": None,
    }
    if iv.time_limit_s:
        spec["time_limit_s"] = max(10, iv.time_limit_s - 2 * n)
    if interleave:
        spec.update({"themes": [], "min_len": None, "max_len": None, "min_think_ms": None, "blind": False,
                     "candidates": False, "interleave_with_due_review": True})
    return spec


def start_assignment(db: Session, category: str, theme: str | None, cycle_id: int | None, pre_metric: dict,
                     rng: random.Random | None = None, target: int = 30) -> InterventionAssignment:
    iv, draws = choose_intervention(db, category, rng)
    a = InterventionAssignment(cycle_id=cycle_id, intervention_key=iv.key, target_category=category,
                               target_theme=theme, params={"offset": iv.start_offset, "draws": draws},
                               exercises_target=target, pre_metric=pre_metric, exercises_done=0,
                               status="active", started_at=utcnow(), post_metric={})
    db.add(a)
    db.flush()
    return a


def record_outcome(db: Session, a: InterventionAssignment, post_metric: dict) -> dict:
    """Bayesian update: did the target error rate fall by a meaningful margin?"""
    a.post_metric = post_metric
    a.status = "completed"
    a.ended_at = utcnow()
    pre, post = a.pre_metric.get("rate"), post_metric.get("rate")
    st = _stat(db, a.intervention_key, a.target_category)
    if pre is None or post is None or post_metric.get("n", 0) < 10:
        a.improved = None
        return {"updated": False, "reason": "insufficient reassessment data"}
    effect = pre - post
    a.improved = effect >= 0.02 or (pre > 0 and post <= 0.8 * pre)
    if a.improved:
        st.alpha += 1
    else:
        st.beta += 1
    st.trials += 1
    st.mean_effect = st.mean_effect + (effect - st.mean_effect) / st.trials
    return {"updated": True, "improved": a.improved, "effect": effect, "posterior": [st.alpha, st.beta]}


def effectiveness_report(db: Session) -> list[dict]:
    rows = db.execute(select(InterventionStat)).scalars().all()
    out = []
    for r in rows:
        mean = r.alpha / (r.alpha + r.beta)
        out.append({"intervention": r.intervention_key, "title": CATALOG[r.intervention_key].title
                    if r.intervention_key in CATALOG else r.intervention_key,
                    "category": r.target_category, "trials": r.trials, "p_improves": round(mean, 3),
                    "mean_effect": round(r.mean_effect, 4), "alpha": r.alpha, "beta": r.beta})
    return sorted(out, key=lambda x: (-x["trials"], -x["p_improves"]))
