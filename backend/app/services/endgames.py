"""Endgame study: textbook theory positions played out against Stockfish, plus endgame
puzzles from the Lichess database (incl. the 'zugzwang' theme). Goals were checked with Stockfish (see tests/test_endgames.py)."""
from __future__ import annotations

import chess

from .engine import StockfishService

POSITIONS = [
    {"id": "kq_k", "module": "Mates básicos", "title": "Mate de dama", "fen": "8/8/8/4k3/8/8/8/4K2Q w - - 0 1",
     "goal": "win", "hint": "Use a dama para encurralar o rei (a um salto de cavalo dele) e traga o seu rei para ajudar."},
    {"id": "kr_k", "module": "Mates básicos", "title": "Mate de torre", "fen": "8/8/8/4k3/8/8/8/R3K3 w - - 0 1",
     "goal": "win", "hint": "Corte o rei numa fileira ou coluna e vá diminuindo a caixa; use a oposição para dar o xeque."},
    {"id": "kp_6th", "module": "Rei e peão", "title": "Rei na frente, na 6ª fileira",
     "fen": "4k3/8/4K3/4P3/8/8/8/8 w - - 0 1", "goal": "win",
     "hint": "Com o seu rei na 6ª fileira na frente do peão, a vitória não depende de quem joga."},
    {"id": "opposition", "module": "Oposição", "title": "Ganhe a oposição",
     "fen": "8/8/4k3/8/8/4K3/4P3/8 w - - 0 1", "goal": "win",
     "hint": "Avance primeiro o rei, com o peão atrás; ganhe a oposição antes de empurrar o peão."},
    {"id": "opposition_def", "module": "Oposição", "title": "Defenda com a oposição",
     "fen": "4k3/8/8/8/8/4P3/4K3/8 b - - 0 1", "goal": "draw",
     "hint": "Fique na frente do peão e tome a oposição quando o rei branco chegar perto."},
    {"id": "lucena", "module": "Finais de torre", "title": "Posição de Lucena",
     "fen": "1K1k4/1P6/8/8/8/8/r7/2R5 w - - 0 1", "goal": "win",
     "hint": "Corte o rei adversário e depois 'construa a ponte' com a torre na 4ª fileira."},
    {"id": "philidor", "module": "Finais de torre", "title": "Defesa de Philidor",
     "fen": "4k3/7R/8/3KP3/8/8/8/r7 b - - 0 1", "goal": "draw",
     "hint": "Mantenha a torre na sua 3ª fileira (6ª das Brancas) até o peão avançar; aí dê xeques por trás."},
    {"id": "wrong_bishop", "module": "Finais de peças menores", "title": "Bispo da cor errada",
     "fen": "7k/8/6KP/8/8/8/8/3B4 b - - 0 1", "goal": "draw",
     "hint": "O bispo não controla h8: fique no canto."},
    {"id": "q_vs_p", "module": "Finais de dama", "title": "Dama contra peão na 7ª",
     "fen": "K7/8/8/8/8/8/3pk3/7Q w - - 0 1", "goal": "win",
     "hint": "Dê xeque ou crave para obrigar o rei a ficar na frente do peão; então aproxime o seu rei um passo."},
    {"id": "pawn_ahead", "module": "Oposição", "title": "Peão na frente do rei",
     "fen": "8/8/8/2k5/2P5/3K4/8/8 b - - 0 1", "goal": "draw",
     "hint": "O rei que defende bloqueia na frente do peão; com o peão na frente do próprio rei, não há vitória."},
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
