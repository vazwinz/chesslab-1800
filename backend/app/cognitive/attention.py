"""ATTENTION AND DECISION TRACKING — within-session performance degradation.

Status: EXPERIMENTAL heuristic. It detects a *consistent* decline of performance relative to
puzzle difficulty (plus slower/more hesitant decisions) late in a session and suggests a break.
It is a training-performance signal, not a medical or psychological assessment."""
from __future__ import annotations

from datetime import timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models import Attempt, TrainingSession, utcnow
from .stats import median

MIN_ATTEMPTS = 16
WINDOW = 8
RESIDUAL_DROP = 0.20      # late window performs ≥20 points below the early window, relative to difficulty
LATE_RESIDUAL_MAX = -0.15  # and clearly below expectation in absolute terms
LATENCY_RATIO = 1.25       # and takes ≥25% longer than the early window (or hesitates more)
LONG_SESSION_MIN = 100


def _hes(a: Attempt) -> float:
    h = a.hesitation or {}
    return float(h.get("selection_changes", 0)) + float(h.get("cancelled_drags", 0))


def session_trend(db: Session, session_id: int) -> dict:
    atts = db.execute(select(Attempt).where(Attempt.session_id == session_id, Attempt.correct.is_not(None))
                      .order_by(Attempt.id)).scalars().all()
    sess = db.get(TrainingSession, session_id)
    series = []
    for i, a in enumerate(atts):
        series.append({"i": i + 1, "correct": bool(a.correct), "expected": a.expected_score,
                       "residual": (int(bool(a.correct)) - a.expected_score) if a.expected_score is not None else None,
                       "total_ms": a.total_ms, "first_move_ms": a.first_move_ms, "hesitation": _hes(a)})
    out = {"session_id": session_id, "n": len(atts), "series": series, "suggest_break": False, "reasons": [],
           "disclaimer": "É só um sinal da tendência do seu desempenho, não um diagnóstico médico ou psicológico."}
    minutes = ((sess.last_activity_at - sess.started_at).total_seconds() / 60) if sess else 0
    out["minutes"] = round(minutes, 1)
    if len(atts) < MIN_ATTEMPTS:
        out["status"] = f"coletando dados ({len(atts)}/{MIN_ATTEMPTS} exercícios)"
        return out
    early = series[: max(WINDOW, len(series) // 3)]
    late = series[-WINDOW:]

    def avg(xs):
        xs = [x for x in xs if x is not None]
        return sum(xs) / len(xs) if xs else None

    e_res, l_res = avg([s["residual"] for s in early]), avg([s["residual"] for s in late])
    e_ms = median([s["total_ms"] for s in early if s["total_ms"]])
    l_ms = median([s["total_ms"] for s in late if s["total_ms"]])
    e_h, l_h = avg([s["hesitation"] for s in early]), avg([s["hesitation"] for s in late])
    out.update({"early_residual": e_res, "late_residual": l_res, "early_median_ms": e_ms, "late_median_ms": l_ms,
                "early_hesitation": e_h, "late_hesitation": l_h})
    # consistency: the decline must hold in both halves of the late window, not one bad streak
    half = WINDOW // 2
    l1, l2 = avg([s["residual"] for s in late[:half]]), avg([s["residual"] for s in late[half:]])
    declined = (e_res is not None and l_res is not None and e_res - l_res >= RESIDUAL_DROP
                and l_res <= LATE_RESIDUAL_MAX and l1 is not None and l2 is not None and l1 < e_res and l2 < e_res)
    slower = bool(e_ms and l_ms and l_ms >= LATENCY_RATIO * e_ms) or bool(e_h is not None and l_h is not None and l_h >= e_h + 1)
    if declined:
        out["reasons"].append(f"o acerto em relação à dificuldade caiu de {e_res:+.2f} para {l_res:+.2f}")
    if slower:
        out["reasons"].append("as decisões ficaram mais lentas / mais hesitantes do que no começo da sessão")
    if declined and (slower or minutes >= LONG_SESSION_MIN):
        out["suggest_break"] = True
        out["recommendation"] = "Seu desempenho caiu de forma consistente. Faça uma pausa de 10–15 minutos longe do tabuleiro."
    out["status"] = "queda detectada" if out["suggest_break"] else "estável"
    return out


def recent_fatigue_days(db: Session, days: int = 3) -> int:
    since = utcnow() - timedelta(days=days)
    return len(db.execute(select(TrainingSession.id).where(TrainingSession.break_suggested_at.is_not(None),
                                                            TrainingSession.started_at >= since)).all())


def should_offer_light_day(db: Session) -> dict:
    """Light day when breaks were flagged repeatedly or recent results are well below expectation."""
    flagged = recent_fatigue_days(db)
    since = utcnow() - timedelta(days=3)
    rows = db.execute(select(Attempt.correct, Attempt.expected_score).where(
        Attempt.served_at >= since, Attempt.correct.is_not(None), Attempt.expected_score.is_not(None))).all()
    resid = [int(bool(c)) - e for c, e in rows]
    mean_r = sum(resid) / len(resid) if resid else None
    poor = mean_r is not None and len(resid) >= 30 and mean_r <= -0.15
    return {"light_day": flagged >= 2 or poor, "break_flags_3d": flagged, "residual_3d": mean_r, "n_3d": len(resid)}
