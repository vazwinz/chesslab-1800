"""Jogar contra o computador: levels, the computer's move, a judge for your moves, where a game
can start (openings, your repertoire, endgames, the positions before your mistakes) and saving a
finished game (analysed like any other; your rating against the computer follows the result)."""
from __future__ import annotations

from typing import Literal

import chess
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from ..db import get_db
from ..services import endgames, game_jobs, play
from ..services import openings as openings_svc
from ..services.engine import get_engine
from ..services.games import import_pgn
from .core import _board, _engine_call

router = APIRouter(prefix="/api/play")


@router.get("/state")
def play_state(db: Session = Depends(get_db)):
    return {**play.state(db), "levels": [{"elo": e, "name": n} for e, n in play.LEVELS],
            "min": play.MIN_ELO, "max": play.MAX_ELO}


@router.get("/starts")
def play_starts(db: Session = Depends(get_db)):
    reps = []
    for r in openings_svc.list_repertoires(db):
        for line in r["lines"]:
            b = chess.Board(line["start_fen"])
            try:
                for u in line["moves_uci"]:
                    b.push(chess.Move.from_uci(u))
            except (ValueError, AssertionError):
                continue
            if b.is_valid() and not b.is_game_over():
                reps.append({"id": f"rep-{line['id']}", "name": f"{r['name']}: {line['name']}", "fen": b.fen(),
                             "color": r["color"]})
    return {"openings": play.openings_list(), "repertoire": reps,
            "endgames": [{"id": p["id"], "name": p["title"], "module": p["module"], "fen": p["fen"], "goal": p["goal"]}
                         for p in endgames.POSITIONS],
            "mistakes": play.mistake_starts(db)}


class MoveIn(BaseModel):
    fen: str
    level: int = Field(..., ge=play.MIN_ELO, le=play.MAX_ELO)


@router.post("/move")
def play_move(body: MoveIn):
    b = _board(body.fen)
    if b.is_game_over():
        raise HTTPException(409, "A partida já terminou.")
    return _engine_call(lambda: play.engine_move(get_engine("play"), b, body.level))


class JudgeIn(BaseModel):
    fen: str
    move: str = Field(..., min_length=4, max_length=5)


@router.post("/judge")
def play_judge(body: JudgeIn):
    b = _board(body.fen)
    try:
        mv = chess.Move.from_uci(body.move)
    except ValueError:
        raise HTTPException(422, "Lance ilegível.")
    if mv not in b.legal_moves:
        raise HTTPException(422, "Lance ilegal nesta posição.")
    return _engine_call(lambda: play.judge(get_engine("play"), b, mv))


class FinishIn(BaseModel):
    start_fen: str
    moves: list[str] = Field(default_factory=list, max_length=1200)
    user_color: Literal["white", "black"]
    level: int = Field(..., ge=play.MIN_ELO, le=play.MAX_ELO)
    result: Literal["1-0", "0-1", "1/2-1/2"]
    reason: str = Field("", max_length=40)
    helped: bool = False
    practice: bool = False  # started from an endgame, one of your mistakes or a pasted FEN
    time_control: str | None = Field(None, max_length=20)
    opening: str | None = Field(None, max_length=80)


@router.post("/finish")
def play_finish(body: FinishIn, db: Session = Depends(get_db)):
    _board(body.start_fen)
    try:
        pgn = play.pgn_for(body.start_fen, body.moves, body.user_color, body.level, body.result, body.reason,
                           body.time_control, body.opening)
    except ValueError as exc:
        raise HTTPException(422, str(exc))
    gid = None
    if body.moves:
        imp = import_pgn(db, pgn, user_color=body.user_color, player_names=[], source="aura")
        gid = (imp["game_ids"] or [None])[0]
        if gid:
            game_jobs.enqueue_analysis([gid])
    won = (body.result == "1-0") == (body.user_color == "white")
    score = 0.5 if body.result == "1/2-1/2" else 1.0 if won else 0.0
    # a game you got help in (hints, takebacks), one from a position that is not an even start
    # (an endgame, one of your mistakes, a pasted FEN) or one that never really started does not
    # move your level
    rated = not body.helped and not body.practice and len(body.moves) >= 2
    out = {"game_id": gid, "rated": rated, "score": score}
    if rated:
        out.update(play.record(db, body.level, score, gid))
    else:
        st = play.state(db)
        out.update(rating_before=st["rating"], rating_after=st["rating"], next_level=st["suggested_level"],
                   next_level_name=st["level_name"])
    return out
