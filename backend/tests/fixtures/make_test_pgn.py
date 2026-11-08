"""Generates tests/fixtures/TEST_ONLY_games.pgn — TEST-ONLY synthetic games.

"TestUser" is a weak, partly random Stockfish setting; "Opponent" is stronger. Clock comments
([%clk]) are synthetic. Used only to test PGN import, game analysis and Error DNA.
Usage: python tests/fixtures/make_test_pgn.py"""
from __future__ import annotations

import random
import sys
from pathlib import Path

import chess
import chess.engine
import chess.pgn

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from app.config import settings  # noqa: E402

OUT = Path(__file__).with_name("TEST_ONLY_games.pgn")


def fmt_clock(s: float) -> str:
    s = max(0, int(s))
    return f"{s // 3600}:{(s % 3600) // 60:02d}:{s % 60:02d}"


def main(n_games: int = 4, seed: int = 11) -> None:
    rng = random.Random(seed)
    eng = chess.engine.SimpleEngine.popen_uci(settings.stockfish_path)
    out = []
    try:
        for gi in range(n_games):
            user_white = gi % 2 == 0
            board = chess.Board()
            game = chess.pgn.Game()
            game.headers.update({"Event": "TEST-ONLY synthetic game", "Site": "test", "Date": f"2026.10.{gi + 1:02d}",
                                 "White": "TestUser" if user_white else "Opponent",
                                 "Black": "Opponent" if user_white else "TestUser", "TimeControl": "300+0"})
            node = game
            clocks = {chess.WHITE: 300.0, chess.BLACK: 300.0}
            while not board.is_game_over() and board.fullmove_number <= 45:
                user_turn = board.turn == (chess.WHITE if user_white else chess.BLACK)
                if user_turn:
                    if rng.random() < 0.15:
                        mv = rng.choice(list(board.legal_moves))
                        think = rng.uniform(0.5, 1.5)  # fast random move
                    else:
                        mv = eng.play(board, chess.engine.Limit(depth=rng.choice([1, 2, 6]))).move
                        think = rng.uniform(2, 14)
                else:
                    mv = eng.play(board, chess.engine.Limit(depth=8)).move
                    think = rng.uniform(1, 6)
                clocks[board.turn] = max(1.0, clocks[board.turn] - think)
                board.push(mv)
                node = node.add_variation(mv)
                node.comment = f"[%clk {fmt_clock(clocks[not board.turn])}]"
            game.headers["Result"] = board.result(claim_draw=True) if board.is_game_over() else "*"
            out.append(str(game))
    finally:
        eng.quit()
    OUT.write_text("\n\n".join(out) + "\n")
    print(f"wrote {n_games} games to {OUT}")


if __name__ == "__main__":
    main()
