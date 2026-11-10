"""0.4.0 API: preferences, AI coach settings, "Explicar" coach, new-version check (and, since
0.5.0, the in-place update) and the Portuguese vocabulary the interface shows (themes, Error
DNA, interventions)."""
from __future__ import annotations

import chess
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from ..cognitive.error_dna import INFO as DNA_INFO
from ..cognitive.interventions import CATALOG
from ..config import settings
from ..db import get_db
from ..i18n import PHASE, SEVERITY
from ..models import KV, Attempt, GameMistake, Puzzle
from ..services import coach, coach_ai, prefs, puzzles, updater, updates
from ..services.engine import EngineUnavailable, get_engine
from ..services.explain import CATEGORY_NAMES, themes_payload
from ..version import __version__

router = APIRouter(prefix="/api")


# ---------------------------------------------------------------- app info / vocabulary
@router.get("/app")
def app_info(db: Session = Depends(get_db)):
    kv = db.get(KV, "app_version")
    mig = db.get(KV, "last_migration")
    return {"version": __version__, "previous_version": (kv.value or {}).get("previous") if kv else None,
            "data_dir": settings.data_dir,
            "migration": mig.value if mig and not (mig.value or {}).get("seen") else None}


@router.post("/app/migration-seen")
def migration_seen(db: Session = Depends(get_db)):
    mig = db.get(KV, "last_migration")
    if mig:
        mig.value = {**(mig.value or {}), "seen": True}
        db.commit()
    return {"ok": True}


@router.get("/meta")
def meta():
    return {"version": __version__, "themes": themes_payload(), "categories": CATEGORY_NAMES,
            "error_dna": DNA_INFO, "severity": SEVERITY, "phases": PHASE,
            "interventions": {k: {"title": i.title, "description": i.description, "targets": i.targets}
                              for k, i in CATALOG.items()}}


# ---------------------------------------------------------------- preferences
@router.get("/prefs")
def get_prefs(db: Session = Depends(get_db)):
    return prefs.get_prefs(db)


@router.put("/prefs")
def put_prefs(body: dict, db: Session = Depends(get_db)):
    try:
        return prefs.update_prefs(db, body)
    except (ValueError, TypeError) as exc:
        raise HTTPException(422, str(exc))


# ---------------------------------------------------------------- AI coach settings
class CoachSettingsIn(BaseModel):
    provider: str
    base_url: str | None = Field(None, max_length=300)
    model: str | None = Field(None, max_length=120)
    api_key: str | None = Field(None, max_length=400, description="omit = keep, empty = delete")


@router.get("/settings/coach")
def coach_settings(db: Session = Depends(get_db)):
    return coach_ai.get_settings(db)


@router.put("/settings/coach")
def coach_settings_put(body: CoachSettingsIn, db: Session = Depends(get_db)):
    try:
        return coach_ai.update_settings(db, body.provider, body.base_url, body.model, body.api_key)
    except ValueError as exc:
        raise HTTPException(422, str(exc))


@router.post("/settings/coach/test")
def coach_settings_test(db: Session = Depends(get_db)):
    return coach_ai.test_connection(db)


# ---------------------------------------------------------------- "Explicar"
class ExplainIn(BaseModel):
    fen: str | None = None
    move: str | None = Field(None, max_length=10)
    attempt_id: int | None = None
    game_mistake_id: int | None = None
    ai: bool = False


def _push_san(board: chess.Board, ucis: list[str]) -> list[str]:
    b, out = board.copy(), []
    for u in ucis:
        mv = chess.Move.from_uci(u)
        if mv not in b.legal_moves:
            break
        out.append(b.san(mv))
        b.push(mv)
    return out


def _attempt_context(db: Session, aid: int) -> tuple[str, str | None, dict]:
    a = db.get(Attempt, aid)
    if a is None:
        raise HTTPException(404, "Exercício não encontrado.")
    if a.correct is None:
        raise HTTPException(409, "Termine o exercício antes de pedir a explicação.")
    if a.exercise_kind == "game_position":
        gm = db.get(GameMistake, a.game_mistake_id)
        b = chess.Board(gm.fen_before)
        played = (a.moves_played or [None])[0]
        cat = a.error_category or gm.category
        return b.fen(), played, {"kind": "partida", "user_color": b.turn, "error_category": cat,
                                 "error_category_label": DNA_INFO.get(cat, {}).get("name")}
    p = db.get(Puzzle, a.puzzle_id)
    start = chess.Board(p.fen)
    start.push(chess.Move.from_uci(p.moves.split()[0]))
    sol = puzzles.solution_moves(p)
    played = list(a.moves_played or [])
    ctx = {"kind": "puzzle", "user_color": start.turn, "themes": p.themes.split(),
           "error_category": a.error_category,
           "error_category_label": DNA_INFO.get(a.error_category or "", {}).get("name")}
    if a.correct:
        ctx.update(solution_uci=sol, solution_san=_push_san(start, sol))
        return start.fen(), None, ctx
    fp = a.fail_ply or 0
    b = start.copy()
    for mv in played[: 2 * fp]:
        b.push(chess.Move.from_uci(mv))
    rest = sol[2 * fp:]
    ctx.update(solution_uci=rest, solution_san=_push_san(b, rest))
    wrong = played[2 * fp] if len(played) > 2 * fp else None
    return b.fen(), wrong, ctx


@router.post("/coach/explain")
def coach_explain(body: ExplainIn, db: Session = Depends(get_db)):
    if body.attempt_id:
        fen, move, ctx = _attempt_context(db, body.attempt_id)
    elif body.game_mistake_id:
        gm = db.get(GameMistake, body.game_mistake_id)
        if gm is None:
            raise HTTPException(404, "Erro de partida não encontrado.")
        b = chess.Board(gm.fen_before)
        fen, move = b.fen(), gm.move_uci
        ctx = {"kind": "partida", "user_color": b.turn, "error_category": gm.category,
               "error_category_label": DNA_INFO.get(gm.category, {}).get("name")}
    else:
        if not body.fen:
            raise HTTPException(422, "Informe a posição (FEN) ou o exercício.")
        try:
            b = chess.Board(body.fen)
        except ValueError:
            raise HTTPException(422, "FEN inválido.")
        if not b.is_valid():
            raise HTTPException(422, "Posição ilegal.")
        fen, move, ctx = b.fen(), None, {"kind": "análise"}
        if body.move:
            try:
                mv = chess.Move.from_uci(body.move)
            except ValueError:
                try:
                    mv = b.parse_san(body.move)
                except ValueError:
                    raise HTTPException(422, "Lance ilegível.")
            if mv not in b.legal_moves:
                raise HTTPException(422, "Lance ilegal nesta posição.")
            move = mv.uci()
    try:
        rules = coach.explain(get_engine(), fen, move, ctx, depth=settings.coach_depth, db=db)
    except EngineUnavailable as exc:
        raise HTTPException(503, str(exc))
    except ValueError as exc:
        raise HTTPException(422, str(exc))
    if not rules.get("terminal"):
        rules["sections"]["tip"] = coach.tip(ctx, rules)
    out = {"rules": rules, "ai": None, "ai_enabled": coach_ai.get_settings(db)["enabled"],
           "context": {k: v for k, v in ctx.items() if k in ("kind", "error_category", "error_category_label")}}
    if body.ai and not rules.get("terminal"):
        out["ai"] = coach_ai.ask(db, rules, ctx)
    return out


# ---------------------------------------------------------------- new version
@router.get("/update/check")
def update_check(force: bool = False, db: Session = Depends(get_db)):
    return updates.check(db, force=force)


@router.post("/update/start")
def update_start(db: Session = Depends(get_db)):
    """ "Atualizar agora": download and check the new version, then close and reinstall."""
    try:
        return updater.start(db)
    except updater.UpdateError as exc:
        raise HTTPException(409, str(exc))


@router.get("/update/job")
def update_job():
    return updater.state()


@router.post("/update/cancel")
def update_cancel():
    return updater.cancel()
