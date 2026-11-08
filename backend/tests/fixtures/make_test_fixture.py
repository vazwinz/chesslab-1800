"""Generates tests/fixtures/TEST_ONLY_lichess_format_puzzles.csv.zst.

TEST-ONLY DATA. These puzzles are NOT from Lichess. They are produced here by Stockfish
from semi-random play, written in the exact column layout of lichess_db_puzzle.csv.zst so
the streaming importer can be tested without the real (multi-GB) download, which is blocked
in the build environment. Ratings/popularity/plays/themes are synthetic placeholders.
IDs start with "TEST" so they can never be confused with real Lichess ids.
Never import this file into a production database.

Usage:  python tests/fixtures/make_test_fixture.py [count]
"""
from __future__ import annotations

import csv
import io
import random
import sys
from pathlib import Path

import chess
import chess.engine
import zstandard

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from app.config import settings  # noqa: E402

OUT = Path(__file__).with_name("TEST_ONLY_lichess_format_puzzles.csv.zst")
VALUES = {chess.PAWN: 1, chess.KNIGHT: 3, chess.BISHOP: 3, chess.ROOK: 5, chess.QUEEN: 9, chess.KING: 100}


def themes_for(board_before_user: chess.Board, line: list[chess.Move], mate: int | None) -> list[str]:
    t = []
    if mate:
        t.append(f"mateIn{min(mate, 5)}" if mate <= 5 else "mate")
        t.append("mate")
    else:
        t.append("crushing")
    user_moves = (len(line) + 1) // 2
    t.append("oneMove" if user_moves == 1 else ("short" if user_moves == 2 else "long"))
    mat = sum(VALUES[p.piece_type] for p in board_before_user.piece_map().values() if p.piece_type != chess.KING)
    t.append("endgame" if mat <= 26 else "middlegame")
    b = board_before_user.copy()
    first = line[0]
    if b.is_capture(first):
        t.append("hangingPiece" if not b.is_attacked_by(not b.turn, first.to_square) else "capturingDefender")
    b.push(first)
    moved = b.piece_at(first.to_square)
    if moved:
        attacked = [sq for sq in b.attacks(first.to_square)
                    if b.piece_at(sq) and b.piece_at(sq).color == b.turn
                    and VALUES[b.piece_at(sq).piece_type] >= VALUES[moved.piece_type] - 0]
        if len(attacked) >= 2:
            t.append("fork")
    if b.is_check() and not mate:
        t.append("kingsideAttack")
    return t


def main(count: int = 40, seed: int = 1800) -> None:
    rng = random.Random(seed)
    eng = chess.engine.SimpleEngine.popen_uci(settings.stockfish_path)
    rows, tries = [], 0
    try:
        while len(rows) < count and tries < 4000:
            tries += 1
            board = chess.Board()
            for _ in range(rng.randint(8, 70)):
                if board.is_game_over():
                    break
                moves = list(board.legal_moves)
                if rng.random() < 0.6:
                    mv = eng.play(board, chess.engine.Limit(depth=4)).move
                else:
                    mv = rng.choice(moves)
                board.push(mv)
            if board.is_game_over():
                continue
            start_fen = board.fen()
            blunder = rng.choice(list(board.legal_moves))
            board.push(blunder)
            if board.is_game_over():
                continue
            line: list[chess.Move] = []
            mate_n = None
            b = board.copy()
            ok = True
            for user_step in range(3):
                infos = eng.analyse(b, chess.engine.Limit(depth=12), multipv=2)
                best = infos[0]["score"].pov(b.turn)
                if user_step == 0:
                    if best.mate() is None and (best.score() or 0) < 350:
                        ok = False
                        break
                    mate_n = best.mate()
                if len(infos) > 1:
                    second = infos[1]["score"].pov(b.turn).score(mate_score=10000)
                    if best.score(mate_score=10000) - second < 250:
                        ok = user_step > 0
                        break
                mv = infos[0]["pv"][0]
                line.append(mv)
                b.push(mv)
                if b.is_game_over() or (mate_n is None and user_step >= 0 and rng.random() < 0.5):
                    break
                reply = eng.analyse(b, chess.engine.Limit(depth=10))["pv"][0]
                line.append(reply)
                b.push(reply)
            if not ok or not line:
                continue
            if len(line) % 2 == 0:
                line = line[:-1]  # puzzle always ends with the solver's move
            user_moves = (len(line) + 1) // 2
            themes = themes_for(board, line, mate_n if mate_n and mate_n > 0 else None)
            rating = 900 + 250 * user_moves + rng.randint(-150, 250) + (0 if mate_n else 150)
            all_moves = " ".join([blunder.uci()] + [m.uci() for m in line])
            rows.append([f"TEST{len(rows):04d}", start_fen, all_moves, rating, 80, rng.randint(50, 100),
                         rng.randint(100, 5000), " ".join(themes), "", ""])
    finally:
        eng.quit()
    buf = io.StringIO()
    w = csv.writer(buf, lineterminator="\n")
    w.writerow(["PuzzleId", "FEN", "Moves", "Rating", "RatingDeviation", "Popularity", "NbPlays", "Themes",
                "GameUrl", "OpeningTags"])
    w.writerows(rows)
    # one deliberately illegal row, so the importer's validation path is exercised
    w.writerow(["TESTBAD1", chess.STARTING_FEN, "e2e4 e7e5 e1e3", 1200, 80, 90, 100, "short", "", ""])
    OUT.write_bytes(zstandard.ZstdCompressor(level=10).compress(buf.getvalue().encode()))
    print(f"wrote {len(rows)} test-only puzzles (+1 invalid) to {OUT}")


if __name__ == "__main__":
    main(int(sys.argv[1]) if len(sys.argv) > 1 else 40)
