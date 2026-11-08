"""COGNITIVE ENGINE API."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..cognitive import attention, error_dna, interventions, loop, prediction, pressure, principles, profiling, retention
from ..db import get_db
from ..models import TrainingSession

router = APIRouter(prefix="/api/cognitive", tags=["cognitive"])


@router.get("/profile")
def profile(days: int = 60, db: Session = Depends(get_db)):
    return profiling.build_profile(db, days)


@router.get("/error-dna")
def error_profile(days: int = 90, db: Session = Depends(get_db)):
    return {**error_dna.recurring_patterns(db, days), "categories": error_dna.CATEGORIES,
            "priority": error_dna.PRIORITY}


@router.get("/retention")
def retention_view(db: Session = Depends(get_db)):
    return retention.retention_report(db)


@router.get("/interventions")
def interventions_view(db: Session = Depends(get_db)):
    return {"catalog": [{"key": i.key, "title": i.title, "targets": i.targets, "description": i.description,
                         "principles": i.principles} for i in interventions.CATALOG.values()],
            "effectiveness": interventions.effectiveness_report(db)}


@router.get("/loop")
def loop_view(db: Session = Depends(get_db)):
    loop.advance(db)
    db.commit()
    return loop.loop_status(db)


@router.get("/attention/{session_id}")
def attention_view(session_id: int, db: Session = Depends(get_db)):
    if db.get(TrainingSession, session_id) is None:
        raise HTTPException(404)
    return attention.session_trend(db, session_id)


@router.get("/attention")
def attention_latest(db: Session = Depends(get_db)):
    s = db.execute(select(TrainingSession).order_by(TrainingSession.id.desc()).limit(1)).scalar_one_or_none()
    return {"latest": attention.session_trend(db, s.id) if s else None,
            "light_day": attention.should_offer_light_day(db)}


@router.get("/pressure")
def pressure_view(db: Session = Depends(get_db)):
    r = pressure.pressure_report(db)
    db.commit()
    return r


@router.get("/prediction")
def prediction_view(db: Session = Depends(get_db)):
    return prediction.prediction_report(db)


@router.get("/principles")
def principles_view():
    return principles.report()
