"""RETENTION ENGINE — spaced reintroduction of learned concepts (tactical themes).

Validated principle: spaced repetition / distributed practice and retrieval practice.
ChessLab-specific design (experimental): a concept is "retained" only when the player solves a
NEW, never-seen puzzle of that concept after a delay (transfer probe). Re-solving the same
puzzle (recall probe) is tracked separately because it can be mere recognition of the position.
"""
from __future__ import annotations

from datetime import timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models import Attempt, ConceptMemory, Puzzle, utcnow

FIRST_INTERVALS = [1.0, 3.0]  # days after the 1st and 2nd successful review
MAX_INTERVAL = 120.0
MIN_EASE, MAX_EASE = 1.3, 3.0
DELAY_BUCKETS = [(0, 1, "<1d"), (1, 3, "1-3d"), (3, 7, "3-7d"), (7, 21, "1-3w"), (21, 10_000, ">3w")]


def quality_from(correct: bool, total_ms: int | None, median_ms: float | None, hesitant: bool) -> int:
    """SM-2 style 0-5 grade from observable performance."""
    if not correct:
        return 1
    if median_ms and total_ms is not None and total_ms <= median_ms and not hesitant:
        return 5
    if hesitant or (median_ms and total_ms is not None and total_ms > 2 * median_ms):
        return 3
    return 4


def record_exposure(db: Session, concept: str | None, correct: bool, quality: int) -> ConceptMemory | None:
    if not concept:
        return None
    now = utcnow()
    cm = db.get(ConceptMemory, concept)
    if cm is None:
        cm = ConceptMemory(concept=concept, due_at=now, ease=2.5, interval_days=0.0, reps=0, lapses=0,
                           recall_n=0, recall_ok=0, transfer_n=0, transfer_ok=0)
        db.add(cm)
    elapsed = (now - cm.last_reviewed_at).total_seconds() / 86400 if cm.last_reviewed_at else None
    if correct:
        if cm.learned_at is None:
            cm.learned_at = now
        # massed repetition before half the interval has passed does not grow the interval
        if elapsed is None or cm.interval_days == 0 or elapsed >= 0.5 * cm.interval_days:
            cm.reps += 1
            if cm.reps <= len(FIRST_INTERVALS):
                cm.interval_days = FIRST_INTERVALS[cm.reps - 1]
            else:
                cm.interval_days = min(MAX_INTERVAL, cm.interval_days * cm.ease)
            cm.ease = max(MIN_EASE, min(MAX_EASE, cm.ease + 0.1 - (5 - quality) * (0.08 + (5 - quality) * 0.02)))
            cm.due_at = now + timedelta(days=cm.interval_days)
    else:
        if cm.learned_at is not None:
            cm.lapses += 1
        cm.reps = 0
        cm.interval_days = 1.0 if cm.learned_at else 0.0
        cm.ease = max(MIN_EASE, cm.ease - 0.2)
        cm.due_at = now + timedelta(days=cm.interval_days)
    cm.last_reviewed_at = now
    return cm


def record_probe(cm: ConceptMemory | None, probe: str | None, correct: bool) -> None:
    if cm is None or probe not in ("recall", "transfer"):
        return
    if probe == "recall":
        cm.recall_n += 1
        cm.recall_ok += int(correct)
    else:
        cm.transfer_n += 1
        cm.transfer_ok += int(correct)


def due_concepts(db: Session, limit: int = 20) -> list[ConceptMemory]:
    return list(db.execute(select(ConceptMemory).where(ConceptMemory.learned_at.is_not(None),
                                                       ConceptMemory.due_at <= utcnow())
                           .order_by(ConceptMemory.due_at).limit(limit)).scalars())


def recall_candidate(db: Session, concept: str, min_age_days: float) -> Puzzle | None:
    """A puzzle of this concept the player solved at least `min_age_days` ago and not since."""
    cutoff = utcnow() - timedelta(days=min_age_days)
    rows = db.execute(select(Attempt.puzzle_id, Attempt.served_at, Attempt.correct)
                      .where(Attempt.concept == concept, Attempt.puzzle_id.is_not(None))
                      .order_by(Attempt.served_at.desc()).limit(200)).all()
    seen_recent = {pid for pid, ts, _ in rows if ts > cutoff}
    for pid, ts, ok in rows:
        if ok and ts <= cutoff and pid not in seen_recent:
            return db.get(Puzzle, pid)
    return None


def probe_kind(cm: ConceptMemory) -> str:
    """Mostly transfer probes (the real test); every 4th review is a same-position recall probe."""
    return "recall" if (cm.recall_n + cm.transfer_n) % 4 == 3 else "transfer"


def retention_report(db: Session) -> dict:
    """Success on a concept as a function of the delay since the previous exposure to that concept.
    If the player only 'recognises recent positions', success collapses at long delays."""
    rows = db.execute(select(Attempt.concept, Attempt.served_at, Attempt.correct, Attempt.retention_probe,
                             Attempt.puzzle_id)
                      .where(Attempt.concept.is_not(None), Attempt.correct.is_not(None))
                      .order_by(Attempt.served_at)).all()
    last_seen: dict[str, object] = {}
    seen_puzzles: set[str] = set()
    buckets = {label: {"n": 0, "ok": 0, "new_n": 0, "new_ok": 0} for *_, label in DELAY_BUCKETS}
    for concept, ts, ok, probe, pid in rows:
        prev = last_seen.get(concept)
        if prev is not None:
            delay = (ts - prev).total_seconds() / 86400
            for lo, hi, label in DELAY_BUCKETS:
                if lo <= delay < hi:
                    b = buckets[label]
                    b["n"] += 1
                    b["ok"] += int(ok)
                    if pid not in seen_puzzles:
                        b["new_n"] += 1
                        b["new_ok"] += int(ok)
                    break
        last_seen[concept] = ts
        if pid:
            seen_puzzles.add(pid)
    curve = [{"delay": label, "n": b["n"], "success": (b["ok"] / b["n"]) if b["n"] else None,
              "new_positions_n": b["new_n"], "new_positions_success": (b["new_ok"] / b["new_n"]) if b["new_n"] else None}
             for label, b in buckets.items()]
    concepts = db.execute(select(ConceptMemory).order_by(ConceptMemory.due_at)).scalars().all()
    now = utcnow()
    return {
        "curve": curve,
        "concepts": [{
            "concept": c.concept, "interval_days": round(c.interval_days, 2), "ease": round(c.ease, 2),
            "reps": c.reps, "lapses": c.lapses, "due_at": c.due_at.isoformat(), "due": c.due_at <= now and c.learned_at is not None,
            "learned": c.learned_at is not None,
            "transfer": {"n": c.transfer_n, "ok": c.transfer_ok}, "recall": {"n": c.recall_n, "ok": c.recall_ok},
        } for c in concepts],
        "due_count": sum(1 for c in concepts if c.learned_at is not None and c.due_at <= now),
        "note": "Retention = success on NEW puzzles of a concept after a delay. Same-puzzle recall is reported "
                "separately because it can reflect recognition of the position rather than understanding.",
    }
