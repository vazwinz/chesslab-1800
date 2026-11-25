"""One sentence for why a move fails, from the line that punishes it. Moves are wrapped in [[ ]]
so the screen can show them in the owner's notation."""
from __future__ import annotations

from app.services import motifs


def test_mate():
    fen = "rnbqkbnr/pppp1ppp/8/4p3/8/5P2/PPPPP1PP/RNBQKBNR w KQkq - 0 2"  # 1. f3 e5, White to move
    assert motifs.describe(fen, ["g2g4", "d8h4"]) == "Depois de [[g4]], ele dá mate em 1."


def test_hanging_piece():
    fen = "4k3/8/2p5/8/8/2N5/8/4K3 w - - 0 1"
    assert motifs.describe(fen, ["c3d5", "c6d5"]) == "Depois de [[Nd5]], ele captura o cavalo em d5."


def test_fork():
    fen = "4k3/8/8/8/3n4/8/7P/R3K3 w - - 0 1"
    assert motifs.describe(fen, ["h2h3", "d4c2"]) == "Depois de [[h3]], [[Nc2+]] ataca o rei e a torre ao mesmo tempo."


def test_pin():
    fen = "4kb2/8/8/8/8/8/3N3P/4K3 w - - 0 1"
    assert motifs.describe(fen, ["h2h3", "f8b4"]) == "Depois de [[Bb4]], seu cavalo fica cravado."


def test_quiet_line_has_no_motif():
    fen = "rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1"
    assert motifs.describe(fen, ["e2e4", "e7e5"]) is None


def test_a_broken_line_has_no_motif():
    fen = "rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1"
    assert motifs.describe(fen, []) is None
    assert motifs.describe(fen, ["e2e5"]) is None
