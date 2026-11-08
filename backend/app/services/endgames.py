"""Endgame study: textbook theory positions played out against Stockfish, plus endgame
puzzles from the Lichess database (incl. the 'zugzwang' theme). Goals were checked with Stockfish (see tests/test_endgames.py)."""
from __future__ import annotations

import chess

from .engine import StockfishService

POSITIONS = [
    {"id": "kq_k", "module": "Basic checkmates", "title": "Queen mate", "fen": "8/8/8/4k3/8/8/8/4K2Q w - - 0 1",
     "goal": "win", "hint": "Use the queen to box the king (a knight's move away), then bring your king."},
    {"id": "kr_k", "module": "Basic checkmates", "title": "Rook mate", "fen": "8/8/8/4k3/8/8/8/R3K3 w - - 0 1",
     "goal": "win", "hint": "Cut the king off along a rank or file and shrink the box; use opposition to check."},
    {"id": "kp_6th", "module": "King and pawn", "title": "King in front on the 6th",
     "fen": "4k3/8/4K3/4P3/8/8/8/8 w - - 0 1", "goal": "win",
     "hint": "With your king on the 6th rank in front of the pawn, the win does not depend on the move."},
    {"id": "opposition", "module": "Opposition", "title": "Take the opposition",
     "fen": "8/8/4k3/8/8/4K3/4P3/8 w - - 0 1", "goal": "win",
     "hint": "Advance the king first, keeping the pawn behind; gain the opposition before pushing."},
    {"id": "opposition_def", "module": "Opposition", "title": "Defend with the opposition",
     "fen": "4k3/8/8/8/8/4P3/4K3/8 b - - 0 1", "goal": "draw",
     "hint": "Stay in front of the pawn and take the opposition when the white king comes close."},
    {"id": "lucena", "module": "Rook endings", "title": "Lucena position",
     "fen": "1K1k4/1P6/8/8/8/8/r7/2R5 w - - 0 1", "goal": "win",
     "hint": "Cut the king, then 'build a bridge' with the rook on the 4th rank."},
    {"id": "philidor", "module": "Rook endings", "title": "Philidor defence",
     "fen": "4k3/7R/8/3KP3/8/8/8/r7 b - - 0 1", "goal": "draw",
     "hint": "Keep your rook on the 3rd rank (6th from White) until the pawn advances, then check from behind."},
    {"id": "wrong_bishop", "module": "Minor-piece endings", "title": "Wrong rook-pawn bishop",
     "fen": "7k/8/6KP/8/8/8/8/3B4 b - - 0 1", "goal": "draw",
     "hint": "The bishop does not control h8: stay in the corner."},
    {"id": "q_vs_p", "module": "Queen endings", "title": "Queen vs pawn on the 7th",
     "fen": "K7/8/8/8/8/8/3pk3/7Q w - - 0 1", "goal": "win",
     "hint": "Check or pin to force the king in front of the pawn, then bring your king one step closer."},
    {"id": "pawn_ahead", "module": "Opposition", "title": "Pawn ahead of the king",
     "fen": "8/8/8/2k5/2P5/3K4/8/8 b - - 0 1", "goal": "draw",
     "hint": "The defending king blockades in front of the pawn; with the pawn ahead of its king there is no win."},
]
BY_ID = {p["id"]: p for p in POSITIONS}


def validate_positions() -> list[str]:
    errors = []
    for p in POSITIONS:
        b = chess.Board(p["fen"])
        if not b.is_valid():
            errors.append(p["id"])
    return errors


def engine_reply(engine: StockfishService, fen: str, depth: int = 18) -> dict:
    b = chess.Board(fen)
    if b.is_game_over():
        return {"game_over": True, "result": b.result(), "fen": fen}
    lines = engine.analyse(b, depth=depth)
    mv = chess.Move.from_uci(lines[0].move)
    san = b.san(mv)
    b.push(mv)
    return {"game_over": b.is_game_over(), "result": b.result() if b.is_game_over() else None, "move": mv.uci(),
            "san": san, "fen": b.fen(), "eval_for_engine": lines[0].cp, "mate": lines[0].mate}


def outcome(fen: str, user_color: chess.Color, goal: str) -> dict | None:
    b = chess.Board(fen)
    if not b.is_game_over(claim_draw=True):
        return None
    res = b.result(claim_draw=True)
    won = (res == "1-0" and user_color == chess.WHITE) or (res == "0-1" and user_color == chess.BLACK)
    drawn = res == "1/2-1/2"
    success = won if goal == "win" else (won or drawn)
    return {"result": res, "success": success}
