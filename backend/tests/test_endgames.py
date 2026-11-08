"""Endgame curriculum: every position is legal and its goal agrees with Stockfish."""
import chess
import pytest

from app.services.endgames import POSITIONS
from app.services.engine import StockfishService

from .conftest import needs_engine


@needs_engine
@pytest.mark.parametrize("pos", POSITIONS, ids=[p["id"] for p in POSITIONS])
def test_endgame_goal_matches_stockfish(pos):
    board = chess.Board(pos["fen"])
    assert board.is_valid()
    eng = StockfishService()
    try:
        line = eng.analyse(board, movetime=3)[0]
    finally:
        eng.close()
    if pos["goal"] == "win":
        assert line.mate is not None and line.mate > 0 or line.cp >= 400, (pos["id"], line)
    else:  # draw: the side to move (the user) can hold
        assert line.mate is None and line.cp >= -150, (pos["id"], line)
