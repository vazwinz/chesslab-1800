"""How a single move is judged: the Lichess thresholds and mate rules, the sacrifice test behind
"brilhante" (!!), the "lance único" (!) and the Lichess game accuracy. Pure functions first (no
engine), then a few checks against the real Stockfish."""
from __future__ import annotations

import chess
import pytest

from app.services import judgement as J
from app.services.engine import Line, StockfishService

from .conftest import needs_engine


def line(uci: str, cp: int = 0, mate: int | None = None) -> Line:
    return Line(move=uci, san=uci, cp=cp, mate=mate, pv=[uci], pv_san=[uci], depth=18)


# ------------------------------------------------------------------ verdict: win-% loss
@pytest.mark.parametrize("best_cp,user_cp,want", [
    (30, 10, "good"),          # 1.8 points
    (50, -30, "inaccuracy"),   # 7.3 points: "bom lance" under the old 10/20/30 thresholds
    (0, -100, "inaccuracy"),   # 9.1 points: almost a pawn given away in an equal position
    (100, -20, "mistake"),     # 10.9 points
    (300, 100, "blunder"),     # 16.0 points
])
def test_win_percent_loss_uses_the_real_lichess_thresholds(best_cp, user_cp, want):
    assert J.classify_move(best_cp, None, user_cp, None) == want


# ------------------------------------------------------------------ verdict: mates (Lichess MateAdvice)
@pytest.mark.parametrize("user_cp,want", [(1200, "inaccuracy"), (800, "mistake"), (300, "blunder")])
def test_letting_a_forced_mate_slip_is_judged_by_what_is_left(user_cp, want):
    # you had mate in 3 and played a move that leaves only an advantage
    assert J.classify_move(9997, 3, user_cp, None) == want


@pytest.mark.parametrize("best_cp,want", [(-1200, "inaccuracy"), (-800, "mistake"), (50, "blunder")])
def test_allowing_a_forced_mate_is_judged_by_how_bad_things_already_were(best_cp, want):
    assert J.classify_move(best_cp, None, -9996, -4) == want


def test_a_slower_mate_is_still_fine_and_turning_a_win_into_being_mated_is_a_blunder():
    assert J.classify_move(9998, 2, 9995, 5) == "good"        # mate in 5 instead of mate in 2
    assert J.classify_move(-9997, -3, -9998, -2) == "good"    # mated either way
    assert J.classify_move(9997, 3, -9998, -2) == "blunder"   # had mate, now gets mated


# ------------------------------------------------------------------ static exchange
def test_static_exchange_counts_the_recapture():
    free = chess.Board("4k3/8/8/3p4/4P3/8/8/4K3 w - - 0 1")
    assert J.see(free, chess.Move.from_uci("e4d5")) == 1
    defended = chess.Board("4k3/8/2p5/3p4/4P3/8/8/4K3 w - - 0 1")
    assert J.see(defended, chess.Move.from_uci("e4d5")) == 0
    greedy = chess.Board("4k3/8/2p5/3p4/8/8/3Q4/4K3 w - - 0 1")
    assert J.see(greedy, chess.Move.from_uci("d2d5")) == -8


SMOTHERED = "5r1k/6pp/7N/3Q4/8/8/8/6K1 w - - 0 1"  # 1. Qg8+!! Rxg8 2. Nf7#


def test_offered_material_is_what_the_opponent_can_win_from_the_moved_piece():
    b = chess.Board(SMOTHERED)
    assert J.offered_material(b, chess.Move.from_uci("d5g8")) == 7   # Q for R, then Kxg8 takes the N back
    assert J.offered_material(chess.Board("4k3/8/8/3p4/4P3/8/8/4K3 w - - 0 1"),
                              chess.Move.from_uci("e4d5")) == 0      # a free pawn is not a sacrifice


# ------------------------------------------------------------------ !! brilhante
def test_a_mating_queen_sacrifice_is_brilliant():
    b = chess.Board(SMOTHERED)
    top = [line("d5g8", 9998, 2), line("h6f7", 900)]
    assert J.highlight(b, chess.Move.from_uci("d5g8"), top, top[0]) == "brilliant"


def test_a_sacrifice_in_a_position_already_crushing_is_not_brilliant():
    b = chess.Board(SMOTHERED)
    top = [line("d5g8", 900), line("h6f7", 880)]
    assert J.highlight(b, chess.Move.from_uci("d5g8"), top, top[0]) is None


def test_a_sacrifice_that_is_not_the_engine_move_is_not_brilliant():
    b = chess.Board(SMOTHERED)
    top = [line("h6f7", 300), line("d5d8", 250)]
    assert J.highlight(b, chess.Move.from_uci("d5g8"), top, line("d5g8", -500)) is None


# ------------------------------------------------------------------ ! lance único
PAWN_ENDING = "4k3/8/8/8/8/8/4P3/4K3 w - - 0 1"


def test_the_only_move_that_keeps_the_balance_is_great():
    b = chess.Board(PAWN_ENDING)
    top = [line("e1d2", 50), line("e2e4", -200)]
    assert J.highlight(b, chess.Move.from_uci("e1d2"), top, top[0]) == "great"


def test_a_best_move_with_close_alternatives_is_not_great():
    b = chess.Board(PAWN_ENDING)
    top = [line("e1d2", 50), line("e2e4", 20)]
    assert J.highlight(b, chess.Move.from_uci("e1d2"), top, top[0]) is None


def test_not_great_when_the_second_best_still_wins_clearly():
    b = chess.Board(PAWN_ENDING)
    top = [line("e1d2", 9995, 5), line("e2e4", 400)]
    assert J.highlight(b, chess.Move.from_uci("e1d2"), top, top[0]) is None


def test_a_recapture_is_never_great():
    b = chess.Board("4k3/8/8/3p4/4P3/2N5/8/4K3 b - - 0 1")
    b.push_uci("d5e4")
    top = [line("c3e4", 0), line("e1d2", -300)]
    assert J.highlight(b, chess.Move.from_uci("c3e4"), top, top[0]) is None


def test_mate_in_one_is_never_great():
    b = chess.Board("6rk/6pp/7N/8/8/8/8/6K1 w - - 0 2")  # after 1. Qg8+ Rxg8: 2. Nf7# ends it
    top = [line("h6f7", 9999, 1), line("h6g8", 0)]
    assert J.highlight(b, chess.Move.from_uci("h6f7"), top, top[0]) is None


# ------------------------------------------------------------------ game accuracy (Lichess)
def test_a_game_without_a_drop_is_100_percent_accurate():
    wins = [52.0] * 41
    assert J.game_accuracy(wins, list(range(0, 40, 2))) == 100.0


def test_one_blunder_weighs_more_than_its_share_of_the_moves():
    wins = [55.0] * 21 + [10.0] * 20                        # one move drops 45 points, the rest are perfect
    user = list(range(0, 40, 2))                            # the blunder is ply 20, one of the user's moves
    plain = sum(J.move_accuracy(wins[i], wins[i + 1]) for i in user) / len(user)
    acc = J.game_accuracy(wins, user)
    assert acc is not None and acc < plain - 5, (acc, plain)


def test_move_accuracy_matches_lichess():
    assert J.move_accuracy(60.0, 60.0) == 100.0
    assert J.move_accuracy(40.0, 50.0) == 100.0             # the position got better
    assert J.move_accuracy(60.0, 40.0) == pytest.approx(41.0, abs=0.1)  # 103.17*e^(-0.8709)-3.17+1


# ------------------------------------------------------------------ with Stockfish
@pytest.fixture()
def eng():  # a fresh engine (empty hash) per test: what Stockfish sees depends on what it searched before
    e = StockfishService(threads=1)
    yield e
    e.close()


@needs_engine
def test_the_engine_finds_the_smothered_mate_sacrifice_brilliant(eng):
    s = J.score_move(eng, chess.Board(SMOTHERED), chess.Move.from_uci("d5g8"), depth=12)
    assert s.verdict == "best" and s.highlight == "brilliant" and s.win_pct_loss == 0


@needs_engine
def test_a_move_outside_the_top_lines_is_scored_from_the_same_root(eng):
    # 1. e4 e5 2. Nf3 and Black hangs the queen: 2... Qh4?? is not in the top lines, it is searched on its own
    b = chess.Board("rnbqkbnr/pppp1ppp/8/4p3/4P3/5N2/PPPP1PPP/RNBQKB1R b KQkq - 1 2")
    s = J.score_move(eng, b, chess.Move.from_uci("d8h4"), depth=12)
    assert s.verdict == "blunder" and s.reply.move == "f3h4"
    assert s.top[0].move != "d8h4" and s.user.move == "d8h4"


@needs_engine
def test_a_mate_that_multipv_misses_at_low_depth_still_counts(eng):
    # Stockfish 17.1 with MultiPV 3 at depth 12 does not see 1. Qg8+ (mate in 2) here; a single-line
    # search does. Playing Nf5 instead must be a mate thrown away, not "the best move".
    s = J.score_move(eng, chess.Board(SMOTHERED), chess.Move.from_uci("h6f5"), depth=12)
    assert s.best.move == "d5g8" and s.best.mate == 2
    assert s.verdict == "blunder"


@needs_engine
def test_an_illegal_move_is_refused(eng):
    with pytest.raises(ValueError):
        J.score_move(eng, chess.Board(SMOTHERED), chess.Move.from_uci("d5e7"), depth=8)  # a knight jump for a queen
