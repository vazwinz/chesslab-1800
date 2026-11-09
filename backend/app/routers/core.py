"""Base ChessLab API: engine, puzzles, training sessions/attempts, games, plan, openings, endgames, dashboard."""
from __future__ import annotations

from typing import Literal

import chess
import chess.pgn
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..config import settings
from ..db import get_db
from ..timeutil import iso
from ..models import Attempt, EngineCache, Game, Puzzle, Repertoire, RepertoireLine, TrainingSession, utcnow
from ..services import dashboard, endgames, openings, plan, prefs, puzzles, trainer
from ..services.engine import EngineUnavailable, get_engine
from ..services import game_jobs
from ..services.games import analyze_game, import_pgn, set_user_color

router = APIRouter(prefix="/api")


def _board(fen: str) -> chess.Board:
    try:
        b = chess.Board(fen)
    except ValueError as exc:
        raise HTTPException(422, f"FEN inválido: {exc}")
    if not b.is_valid():
        raise HTTPException(422, "Posição ilegal (confira reis, peões na primeira/última fileira e de quem é a vez).")
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
    from ..version import __version__

    return {"ok": True, "version": __version__, "engine": get_engine().status(wait=False)}


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
            raise HTTPException(422, "Lance ilegível.")
    if mv not in board.legal_moves:
        raise HTTPException(422, "Lance ilegal nesta posição.")
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
        raise HTTPException(422, "Não consegui ler o PGN" + (f": {g.errors[0]}" if g and g.errors else "."))
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
                         "finished_at": iso(j.finished_at)} for j in jobs]}


@router.get("/puzzles/random")
def random_puzzle(min_rating: int = 800, max_rating: int = 3000, theme: str | None = None,
                  db: Session = Depends(get_db)):
    p = puzzles.select_puzzle(db, min_rating, max_rating, themes=[theme] if theme else None)
    if p is None:
        raise HTTPException(404, "Nenhum puzzle com esses filtros.")
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
        raise HTTPException(404, "Sessão de treino não encontrada.")
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
        raise HTTPException(404, "Exercício não encontrado.")
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
    pgn: str = Field(..., min_length=10, max_length=20_000_000)
    user_color: Literal["white", "black"] | None = None
    player_names: list[str] | None = None
    analyze: bool = False
    wait: bool = False  # analyse inside the request (scripts/tests); the app uses the background queue


@router.post("/games/import")
def games_import(body: GamesIn, db: Session = Depends(get_db)):
    names = [n.strip() for n in body.player_names or [] if n.strip()]
    if names:
        prefs.update_prefs(db, {"player_names": ", ".join(names)})  # remembered for next time
    else:
        names = prefs.player_names(db) or settings.player_names
    res = import_pgn(db, body.pgn, body.user_color, names)
    if body.analyze:
        ids = [gid for gid in res["game_ids"] if db.get(Game, gid).user_color]
        if body.wait:
            from ..cognitive import loop

            for gid in ids:
                _engine_call(lambda gid=gid: analyze_game(db, db.get(Game, gid), get_engine("background")))
            loop.advance(db)
            db.commit()
        elif ids:
            res["job"] = game_jobs.enqueue_analysis(ids)
    return res


class ChessComIn(BaseModel):
    username: str = Field(..., min_length=2, max_length=40)
    months: int = Field(3, ge=1, le=24)
    analyze: bool = True


@router.post("/games/import/chesscom")
def games_import_chesscom(body: ChessComIn):
    from ..services.chesscom import USERNAME_RE

    if not USERNAME_RE.match(body.username.strip()):
        raise HTTPException(422, "Nome de usuário do Chess.com inválido.")
    return game_jobs.enqueue_chesscom(body.username.strip(), body.months, body.analyze)


@router.get("/games/jobs")
def games_job_state():
    return game_jobs.state()


@router.post("/games/jobs/cancel")
def games_job_cancel():
    return game_jobs.cancel()


@router.post("/games/analyze-pending")
def games_analyze_pending(db: Session = Depends(get_db)):
    ids = game_jobs.pending_ids(db)
    if not ids:
        return {**game_jobs.state(), "message": "Nenhuma partida pendente de análise."}
    return game_jobs.enqueue_analysis(ids)


@router.post("/games/{gid}/analyze")
def games_analyze(gid: int, depth: int | None = Query(None, ge=6, le=30),
                  user_color: Literal["white", "black"] | None = None, wait: bool = False,
                  db: Session = Depends(get_db)):
    g = db.get(Game, gid)
    if g is None:
        raise HTTPException(404, "Partida não encontrada.")
    if user_color:
        set_user_color(g, user_color)
        db.commit()
    if not g.user_color:
        raise HTTPException(422, "Diga com qual cor você jogou (ou salve seu nome de usuário em Partidas).")
    if not wait:
        return game_jobs.enqueue_analysis([gid], depth)
    m = _engine_call(lambda: analyze_game(db, g, get_engine("background"), depth))
    from ..cognitive import loop

    loop.advance(db)
    db.commit()
    return m


@router.get("/games")
def games_list(db: Session = Depends(get_db)):
    gs = db.execute(select(Game).order_by(Game.played_on.desc().nulls_last(), Game.id.desc()).limit(500)).scalars().all()
    job = game_jobs.state()
    return [{"id": g.id, "white": g.white, "black": g.black, "result": g.result, "date": g.played_on.isoformat()
             if g.played_on else None, "time_control": g.time_control, "time_class": g.time_class,
             "user_color": g.user_color, "user_elo": g.user_elo, "opponent_elo": g.opponent_elo, "source": g.source,
             "analyzed": g.analyzed, "analyzing": job.get("status") == "running" and job.get("game_id") == g.id,
             "metrics": g.metrics} for g in gs]


@router.get("/games/{gid}")
def games_detail(gid: int, db: Session = Depends(get_db)):
    from ..models import GameMistake

    g = db.get(Game, gid)
    if g is None:
        raise HTTPException(404)
    ms = db.execute(select(GameMistake).where(GameMistake.game_id == gid).order_by(GameMistake.ply)).scalars().all()
    import io

    pg = chess.pgn.read_game(io.StringIO(g.pgn))
    b = pg.board() if pg else chess.Board()
    start, ucis, sans = b.fen(), [], []
    for mv in (pg.mainline_moves() if pg else []):
        sans.append(b.san(mv))
        ucis.append(mv.uci())
        b.push(mv)
    return {"id": g.id, "pgn": g.pgn, "white": g.white, "black": g.black, "result": g.result,
            "date": g.played_on.isoformat() if g.played_on else None, "time_control": g.time_control,
            "time_class": g.time_class, "user_elo": g.user_elo, "opponent_elo": g.opponent_elo,
            "user_color": g.user_color, "metrics": g.metrics, "analyzed": g.analyzed,
            "start_fen": start, "moves_uci": ucis, "moves_san": sans,
            "mistakes": [{"id": m.id, "ply": m.ply, "fen": m.fen_before, "move": m.move_san, "move_uci": m.move_uci,
                          "best": m.best_san, "best_uci": m.best_uci, "cp_loss": m.cp_loss,
                          "win_pct_loss": m.win_pct_loss, "severity": m.severity, "category": m.category,
                          "phase": m.phase, "clock_s": m.clock_s, "think_s": m.think_s, "evidence": m.detail}
                         for m in ms]}


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
        raise HTTPException(422, "Lance ilegível.")
    if b.turn != user_color or mv not in b.legal_moves:
        raise HTTPException(422, "Lance ilegal nesta posição.")
    b.push(mv)
    done = endgames.outcome(b.fen(), user_color, pos["goal"])
    if done:
        return {"fen": b.fen(), "finished": True, **done}
    reply = _engine_call(lambda: endgames.engine_reply(get_engine("train"), b.fen(), body.depth))
    done = endgames.outcome(reply["fen"], user_color, pos["goal"])
    return {**reply, "finished": bool(done), **(done or {})}


# ---------------------------------------------------------------- setup (desktop app)
@router.get("/setup")
def setup_status(db: Session = Depends(get_db)):
    from ..services import import_jobs

    return {"engine": get_engine().status(wait=False), "puzzles": puzzles.puzzle_count(db), "data_dir": settings.data_dir,
            "database_url": settings.database_url, "import": import_jobs.state(),
            "lichess_url": import_jobs.LICHESS_PUZZLE_URL}


class ImportIn(BaseModel):
    download: bool = False
    path: str | None = None
    limit: int | None = Field(None, ge=1)
    min_rating: int | None = Field(None, ge=0, le=4000)
    max_rating: int | None = Field(None, ge=0, le=4000)


@router.post("/setup/import")
def setup_import(body: ImportIn):
    from ..services import import_jobs

    try:
        return import_jobs.start(body.path, body.download, limit=body.limit, min_rating=body.min_rating,
                                 max_rating=body.max_rating)
    except RuntimeError as exc:
        raise HTTPException(409, str(exc))
    except ValueError as exc:
        raise HTTPException(422, str(exc))


# ---------------------------------------------------------------- dashboard
@router.get("/dashboard")
def dash(db: Session = Depends(get_db)):
    return dashboard.overview(db)


@router.get("/puzzles/{pid}")
def puzzle_detail(pid: str, db: Session = Depends(get_db)):
    p = db.get(Puzzle, pid)
    if p is None:
        raise HTTPException(404)
    return {"id": p.id, "rating": p.rating, "themes": p.themes.split(), "game_url": p.game_url,
            "solution_san": puzzles.solution_san(p), **puzzles.puzzle_start(p)}
