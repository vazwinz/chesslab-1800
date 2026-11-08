"""Base ChessLab API: engine, puzzles, training sessions/attempts, games, plan, openings, endgames, dashboard."""
from __future__ import annotations

from typing import Literal

import chess
import chess.pgn
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..db import get_db
from ..models import Attempt, EngineCache, Game, Puzzle, Repertoire, RepertoireLine, TrainingSession, utcnow
from ..services import coach, dashboard, endgames, openings, plan, puzzles, trainer
from ..services.engine import EngineUnavailable, get_engine
from ..services.games import analyze_game, import_pgn

router = APIRouter(prefix="/api")


def _board(fen: str) -> chess.Board:
    try:
        b = chess.Board(fen)
    except ValueError as exc:
        raise HTTPException(422, f"invalid FEN: {exc}")
    if not b.is_valid():
        raise HTTPException(422, f"illegal position: {b.status()!r}")
    return b


def _engine_call(fn):
    try:
        return fn()
    except EngineUnavailable as exc:
        raise HTTPException(503, str(exc))


# ---------------------------------------------------------------- engine
class AnalyseIn(BaseModel):
    fen: str
    depth: int | None = Field(None, ge=1, le=40)
    movetime: float | None = Field(None, gt=0, le=60)
    multipv: int = Field(1, ge=1, le=10)


@router.get("/health")
def health():
    return {"ok": True, "engine": get_engine().status()}


@router.post("/engine/analyse")
def analyse(body: AnalyseIn, db: Session = Depends(get_db)):
    board = _board(body.fen)
    key = f"{board.fen()}|d{body.depth}|t{body.movetime}|m{body.multipv}"
    cached = db.get(EngineCache, key) if body.movetime is None else None
    if cached:
        return {**cached.result, "cached": True}
    lines = _engine_call(lambda: get_engine().analyse(board, depth=body.depth, movetime=body.movetime,
                                                      multipv=body.multipv))
    res = {"fen": board.fen(), "engine": get_engine().name, "lines": [l.as_dict() for l in lines],
           "terminal": board.is_game_over(), "result": board.result() if board.is_game_over() else None}
    if body.movetime is None:
        db.merge(EngineCache(key=key, result=res))
        db.commit()
    return {**res, "cached": False}


class CompareIn(BaseModel):
    fen: str
    move: str
    depth: int | None = Field(None, ge=1, le=40)


@router.post("/engine/compare")
def compare(body: CompareIn):
    board = _board(body.fen)
    try:
        mv = chess.Move.from_uci(body.move)
    except ValueError:
        try:
            mv = board.parse_san(body.move)
        except ValueError:
            raise HTTPException(422, "unreadable move")
    if mv not in board.legal_moves:
        raise HTTPException(422, "illegal move")
    return _engine_call(lambda: get_engine().compare_move(board, mv, depth=body.depth))


class FenIn(BaseModel):
    fen: str


@router.post("/board/legal")
def legal(body: FenIn):
    b = _board(body.fen)
    return {"fen": b.fen(), "turn": "white" if b.turn else "black", "check": b.is_check(),
            "checkmate": b.is_checkmate(), "stalemate": b.is_stalemate(), "game_over": b.is_game_over(),
            "moves": [m.uci() for m in b.legal_moves]}


class PgnIn(BaseModel):
    pgn: str


@router.post("/board/pgn")
def parse_pgn(body: PgnIn):
    import io

    g = chess.pgn.read_game(io.StringIO(body.pgn))
    if g is None or g.errors:
        raise HTTPException(422, "could not parse PGN" + (f": {g.errors[0]}" if g and g.errors else ""))
    b = g.board()
    start, ucis, sans = b.fen(), [], []
    for mv in g.mainline_moves():
        sans.append(b.san(mv))
        ucis.append(mv.uci())
        b.push(mv)
    return {"start_fen": start, "moves_uci": ucis, "moves_san": sans, "headers": dict(g.headers), "final_fen": b.fen()}


# ---------------------------------------------------------------- puzzles
@router.get("/puzzles/stats")
def puzzle_stats(db: Session = Depends(get_db)):
    from ..models import ImportJob

    jobs = db.execute(select(ImportJob).order_by(ImportJob.id.desc()).limit(5)).scalars().all()
    return {"count": puzzles.puzzle_count(db), "themes": puzzles.theme_counts(db),
            "categories": puzzles.TACTICAL_CATEGORIES,
            "imports": [{"id": j.id, "source": j.source, "status": j.status, "inserted": j.inserted,
                         "updated": j.updated, "invalid": j.invalid, "rows_read": j.rows_read,
                         "finished_at": j.finished_at.isoformat() if j.finished_at else None} for j in jobs]}


@router.get("/puzzles/random")
def random_puzzle(min_rating: int = 800, max_rating: int = 3000, theme: str | None = None,
                  db: Session = Depends(get_db)):
    p = puzzles.select_puzzle(db, min_rating, max_rating, themes=[theme] if theme else None)
    if p is None:
        raise HTTPException(404, "no puzzle matches")
    return {"id": p.id, "rating": p.rating, "themes": p.themes.split(), **puzzles.puzzle_start(p)}


# ---------------------------------------------------------------- training
class SessionIn(BaseModel):
    kind: Literal["mixed", "theme", "blind", "candidates", "retention", "pressure", "endgame", "own_mistakes", "loop"]
    theme: str | None = None


@router.post("/sessions")
def create_session(body: SessionIn, db: Session = Depends(get_db)):
    s = TrainingSession(kind=body.kind, theme=body.theme)
    db.add(s)
    db.commit()
    return {"id": s.id, "kind": s.kind, "theme": s.theme}


@router.post("/sessions/{sid}/end")
def end_session(sid: int, db: Session = Depends(get_db)):
    s = db.get(TrainingSession, sid)
    if s is None:
        raise HTTPException(404)
    s.ended_at = utcnow()
    db.commit()
    return {"ok": True}


@router.post("/sessions/{sid}/next")
def next_exercise(sid: int, db: Session = Depends(get_db)):
    s = db.get(TrainingSession, sid)
    if s is None:
        raise HTTPException(404, "session not found")
    try:
        return trainer.next_exercise(db, s)
    except trainer.NoExercise as exc:
        db.rollback()
        raise HTTPException(409, str(exc))


class Hesitation(BaseModel):
    selection_changes: int = Field(0, ge=0)
    cancelled_drags: int = Field(0, ge=0)
    piece_selections: int = Field(0, ge=0)


class MoveIn(BaseModel):
    uci: str = Field(..., min_length=4, max_length=5)
    elapsed_ms: int | None = Field(None, ge=0)
    hesitation: Hesitation | None = None


def _attempt(db: Session, aid: int) -> Attempt:
    a = db.get(Attempt, aid)
    if a is None:
        raise HTTPException(404, "attempt not found")
    return a


@router.post("/attempts/{aid}/move")
def attempt_move(aid: int, body: MoveIn, db: Session = Depends(get_db)):
    a = _attempt(db, aid)
    res = trainer.play_move(db, a, body.uci, body.elapsed_ms, body.hesitation.model_dump() if body.hesitation else None)
    if res.get("error"):
        raise HTTPException(409, res["error"])
    return res


class LineIn(BaseModel):
    moves: list[str] = Field(..., min_length=1, max_length=20)
    elapsed_ms: int | None = Field(None, ge=0)
    first_move_ms: int | None = Field(None, ge=0)
    hesitation: Hesitation | None = None


@router.post("/attempts/{aid}/line")
def attempt_line(aid: int, body: LineIn, db: Session = Depends(get_db)):
    a = _attempt(db, aid)
    res = trainer.submit_line(db, a, body.moves, body.elapsed_ms, body.first_move_ms,
                              body.hesitation.model_dump() if body.hesitation else None)
    if res.get("error"):
        raise HTTPException(409, res["error"])
    return res


class CandidatesIn(BaseModel):
    moves: list[str] = Field(..., min_length=1, max_length=3)


@router.post("/attempts/{aid}/candidates")
def attempt_candidates(aid: int, body: CandidatesIn, db: Session = Depends(get_db)):
    res = trainer.submit_candidates(db, _attempt(db, aid), body.moves)
    if res.get("error"):
        raise HTTPException(422, res["error"])
    return res


class GiveUpIn(BaseModel):
    elapsed_ms: int | None = Field(None, ge=0)
    timed_out: bool = False
    hesitation: Hesitation | None = None


@router.post("/attempts/{aid}/give-up")
def attempt_give_up(aid: int, body: GiveUpIn, db: Session = Depends(get_db)):
    res = trainer.give_up(db, _attempt(db, aid), body.elapsed_ms,
                          body.hesitation.model_dump() if body.hesitation else None, body.timed_out)
    if res.get("error"):
        raise HTTPException(409, res["error"])
    return res


# ---------------------------------------------------------------- games
class GamesIn(BaseModel):
    pgn: str = Field(..., min_length=10, max_length=5_000_000)
    user_color: Literal["white", "black"] | None = None
    player_names: list[str] | None = None
    analyze: bool = False


@router.post("/games/import")
def games_import(body: GamesIn, db: Session = Depends(get_db)):
    res = import_pgn(db, body.pgn, body.user_color, body.player_names)
    if body.analyze:
        res["analysis"] = {}
        for gid in res["game_ids"]:
            g = db.get(Game, gid)
            if g.user_color:
                res["analysis"][gid] = _engine_call(lambda g=g: analyze_game(db, g, get_engine()))
        from ..cognitive import loop

        loop.advance(db)
        db.commit()
    return res


@router.post("/games/{gid}/analyze")
def games_analyze(gid: int, depth: int | None = Query(None, ge=6, le=30),
                  user_color: Literal["white", "black"] | None = None, db: Session = Depends(get_db)):
    g = db.get(Game, gid)
    if g is None:
        raise HTTPException(404)
    if user_color:
        g.user_color = user_color
    if not g.user_color:
        raise HTTPException(422, "set user_color (or CHESSLAB_PLAYER_NAMES) first")
    m = _engine_call(lambda: analyze_game(db, g, get_engine(), depth))
    from ..cognitive import loop

    loop.advance(db)
    db.commit()
    return m


@router.get("/games")
def games_list(db: Session = Depends(get_db)):
    gs = db.execute(select(Game).order_by(Game.id.desc()).limit(200)).scalars().all()
    return [{"id": g.id, "white": g.white, "black": g.black, "result": g.result, "date": g.played_on.isoformat()
             if g.played_on else None, "time_control": g.time_control, "user_color": g.user_color,
             "analyzed": g.analyzed, "metrics": g.metrics} for g in gs]


@router.get("/games/{gid}")
def games_detail(gid: int, db: Session = Depends(get_db)):
    from ..models import GameMistake

    g = db.get(Game, gid)
    if g is None:
        raise HTTPException(404)
    ms = db.execute(select(GameMistake).where(GameMistake.game_id == gid).order_by(GameMistake.ply)).scalars().all()
    return {"id": g.id, "pgn": g.pgn, "white": g.white, "black": g.black, "result": g.result,
            "user_color": g.user_color, "metrics": g.metrics,
            "mistakes": [{"ply": m.ply, "fen": m.fen_before, "move": m.move_san, "best": m.best_san,
                          "cp_loss": m.cp_loss, "severity": m.severity, "category": m.category, "phase": m.phase,
                          "clock_s": m.clock_s, "think_s": m.think_s, "evidence": m.detail} for m in ms]}


# ---------------------------------------------------------------- daily plan
@router.get("/plan/today")
def plan_today(db: Session = Depends(get_db)):
    return plan.today(db)


class PlanRegenIn(BaseModel):
    light: bool


@router.post("/plan/today/regenerate")
def plan_regen(body: PlanRegenIn, db: Session = Depends(get_db)):
    return plan.regenerate(db, body.light)


class CompleteIn(BaseModel):
    completed: bool = True


@router.post("/plan/blocks/{bid}")
def plan_complete(bid: int, body: CompleteIn, db: Session = Depends(get_db)):
    try:
        return plan.complete(db, bid, body.completed)
    except KeyError:
        raise HTTPException(404)


class PlanBlockIn(BaseModel):
    key: str
    title: str
    minutes: int = Field(..., ge=0, le=600)


@router.get("/plan/config")
def plan_config(db: Session = Depends(get_db)):
    return plan.get_config(db)


@router.put("/plan/config")
def plan_config_set(blocks: list[PlanBlockIn], db: Session = Depends(get_db)):
    return plan.set_config(db, [b.model_dump() for b in blocks])


@router.get("/plan/consistency")
def plan_consistency(db: Session = Depends(get_db)):
    return plan.consistency(db)


# ---------------------------------------------------------------- openings
class RepIn(BaseModel):
    name: str = Field(..., min_length=1, max_length=80)
    color: Literal["white", "black"]


@router.get("/openings")
def rep_list(db: Session = Depends(get_db)):
    return openings.list_repertoires(db)


@router.post("/openings")
def rep_create(body: RepIn, db: Session = Depends(get_db)):
    r = Repertoire(name=body.name, color=body.color)
    db.add(r)
    db.commit()
    return {"id": r.id}


@router.delete("/openings/{rid}")
def rep_delete(rid: int, db: Session = Depends(get_db)):
    r = db.get(Repertoire, rid)
    if r is None:
        raise HTTPException(404)
    db.query(RepertoireLine).filter(RepertoireLine.repertoire_id == rid).delete()
    db.delete(r)
    db.commit()
    return {"ok": True}


class LineCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=120)
    moves: str = Field(..., min_length=1, description="PGN, SAN or UCI moves")
    start_fen: str | None = None
    plans: str = ""

    @field_validator("start_fen")
    @classmethod
    def _fen(cls, v):
        if v:
            _board(v)
        return v


@router.post("/openings/{rid}/lines")
def line_create(rid: int, body: LineCreate, db: Session = Depends(get_db)):
    if db.get(Repertoire, rid) is None:
        raise HTTPException(404)
    try:
        fen0, ucis, sans = openings.parse_line(body.moves, body.start_fen)
    except ValueError as exc:
        raise HTTPException(422, str(exc))
    line = RepertoireLine(repertoire_id=rid, name=body.name, start_fen=fen0, moves_uci=ucis, moves_san=sans,
                          plans=body.plans)
    db.add(line)
    db.commit()
    return {"id": line.id, "moves_san": sans}


class PlansIn(BaseModel):
    plans: str


@router.put("/openings/lines/{lid}/plans")
def line_plans(lid: int, body: PlansIn, db: Session = Depends(get_db)):
    line = db.get(RepertoireLine, lid)
    if line is None:
        raise HTTPException(404)
    line.plans = body.plans
    db.commit()
    return {"ok": True}


class DrillIn(BaseModel):
    ply: int = Field(..., ge=0)
    uci: str


@router.post("/openings/lines/{lid}/drill")
def line_drill(lid: int, body: DrillIn, db: Session = Depends(get_db)):
    line = db.get(RepertoireLine, lid)
    if line is None:
        raise HTTPException(404)
    return openings.drill_check(db, line, body.ply, body.uci)


@router.get("/openings/lines/{lid}/study")
def line_study(lid: int, depth: int = Query(16, ge=6, le=30), db: Session = Depends(get_db)):
    """Where the line leads: final position, pawn structure, and Stockfish's top plans there."""
    line = db.get(RepertoireLine, lid)
    if line is None:
        raise HTTPException(404)
    b = chess.Board(line.start_fen)
    for u in line.moves_uci:
        b.push(chess.Move.from_uci(u))
    out = {"final_fen": b.fen(), "structure": openings.structure(b.fen()), "plans_notes": line.plans}
    try:
        out["engine_plans"] = [l.as_dict() for l in get_engine().analyse(b, depth=depth, multipv=3)]
    except EngineUnavailable as exc:
        out["engine_plans"], out["engine_error"] = [], str(exc)
    return out


@router.get("/openings/mistakes")
def opening_mistakes(repertoire_id: int | None = None, db: Session = Depends(get_db)):
    return openings.common_mistakes(db, repertoire_id)


# ---------------------------------------------------------------- endgames
@router.get("/endgames")
def endgame_list():
    return endgames.POSITIONS


class EndgameMoveIn(BaseModel):
    position_id: str
    fen: str
    uci: str
    depth: int = Field(18, ge=4, le=30)


@router.post("/endgames/move")
def endgame_move(body: EndgameMoveIn):
    pos = endgames.BY_ID.get(body.position_id)
    if pos is None:
        raise HTTPException(404)
    user_color = chess.Board(pos["fen"]).turn
    b = _board(body.fen)
    try:
        mv = chess.Move.from_uci(body.uci)
    except ValueError:
        raise HTTPException(422, "unreadable move")
    if b.turn != user_color or mv not in b.legal_moves:
        raise HTTPException(422, "illegal move")
    b.push(mv)
    done = endgames.outcome(b.fen(), user_color, pos["goal"])
    if done:
        return {"fen": b.fen(), "finished": True, **done}
    reply = _engine_call(lambda: endgames.engine_reply(get_engine(), b.fen(), body.depth))
    done = endgames.outcome(reply["fen"], user_color, pos["goal"])
    return {**reply, "finished": bool(done), **(done or {})}


# ---------------------------------------------------------------- dashboard & coach
@router.get("/dashboard")
def dash(db: Session = Depends(get_db)):
    return dashboard.overview(db)


class CoachIn(BaseModel):
    fen: str
    move: str | None = None


@router.post("/coach/explain")
def coach_explain(body: CoachIn):
    _board(body.fen)
    return _engine_call(lambda: coach.explain(get_engine(), body.fen, body.move))


@router.get("/puzzles/{pid}")
def puzzle_detail(pid: str, db: Session = Depends(get_db)):
    p = db.get(Puzzle, pid)
    if p is None:
        raise HTTPException(404)
    return {"id": p.id, "rating": p.rating, "themes": p.themes.split(), "game_url": p.game_url,
            "solution_san": puzzles.solution_san(p), **puzzles.puzzle_start(p)}
