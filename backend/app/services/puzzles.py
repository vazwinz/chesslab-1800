"""Puzzle selection and solution checking (all legality via python-chess)."""
from __future__ import annotations

import random
from datetime import timedelta

import chess
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..models import Attempt, Puzzle, PuzzleTheme, utcnow

# Lichess theme keys grouped into the training categories of the base spec
TACTICAL_CATEGORIES: dict[str, list[str]] = {
    "forks": ["fork"],
    "pins": ["pin"],
    "skewers": ["skewer"],
    "discovered_attacks": ["discoveredAttack"],
    "double_attacks": ["doubleCheck", "fork", "attraction"],
    "deflection": ["deflection"],
    "decoy": ["attraction"],
    "removing_the_defender": ["capturingDefender"],
    "zwischenzug": ["intermezzo"],
    "back_rank": ["backRankMate"],
    "checkmate_patterns": ["mateIn1", "mateIn2", "mateIn3", "smotheredMate", "arabianMate", "anastasiaMate",
                           "bodenMate", "doubleBishopMate", "dovetailMate", "hookMate", "mate"],
    "sacrifices": ["sacrifice"],
    "defensive": ["defensiveMove", "equality"],
}
ENDGAME_THEMES = ["endgame", "pawnEndgame", "rookEndgame", "queenEndgame", "bishopEndgame", "knightEndgame",
                  "queenRookEndgame", "zugzwang"]
CONCEPT_THEMES = sorted({t for v in TACTICAL_CATEGORIES.values() for t in v} | set(ENDGAME_THEMES[1:]) |
                        {"hangingPiece", "trappedPiece", "xRayAttack", "quietMove", "clearance", "interference",
                         "kingsideAttack", "promotion", "advancedPawn", "exposedKing"})
# themes describing length/phase/evaluation, not a concept the player must learn
NON_CONCEPT_THEMES = {"oneMove", "short", "long", "veryLong", "middlegame", "opening", "endgame", "crushing",
                      "advantage", "mate", "master", "masterVsMaster", "superGM", "player"}


def puzzle_count(db: Session) -> int:
    return db.execute(select(func.count()).select_from(Puzzle)).scalar() or 0


def recent_puzzle_ids(db: Session, days: int = 30, cap: int = 2000) -> set[str]:
    since = utcnow() - timedelta(days=days)
    rows = db.execute(select(Attempt.puzzle_id).where(Attempt.puzzle_id.is_not(None), Attempt.served_at >= since)
                      .order_by(Attempt.id.desc()).limit(cap)).scalars()
    return set(rows)


def select_puzzle(db: Session, rating_min: int, rating_max: int, themes: list[str] | None = None,
                  min_len: int | None = None, max_len: int | None = None, exclude: set[str] | None = None,
                  exclude_recent_days: int = 30, widen: bool = True) -> Puzzle | None:
    """Random puzzle in a rating window, optionally by theme, avoiding recently seen ones.
    Uses an indexed random key instead of ORDER BY RANDOM(), so it stays fast on millions of rows."""
    excluded = set(exclude or ()) | recent_puzzle_ids(db, exclude_recent_days)
    lo, hi = rating_min, rating_max
    for _ in range(4 if widen else 1):
        theme = random.choice(themes) if themes else None
        for attempt in range(2):
            r = random.random()
            if theme:
                q = (select(Puzzle).join(PuzzleTheme, PuzzleTheme.puzzle_id == Puzzle.id)
                     .where(PuzzleTheme.theme == theme, PuzzleTheme.rating.between(lo, hi)))
                key = PuzzleTheme.rand_key
            else:
                q = select(Puzzle).where(Puzzle.rating.between(lo, hi))
                key = Puzzle.rand_key
            if min_len:
                q = q.where(Puzzle.solution_len >= min_len)
            if max_len:
                q = q.where(Puzzle.solution_len <= max_len)
            q = q.where(key >= r).order_by(key) if attempt == 0 else q.where(key < r).order_by(key.desc())
            for p in db.execute(q.limit(60)).scalars():
                if p.id not in excluded:
                    return p
        lo, hi = lo - 150, hi + 150  # widen gradually if the window is empty / exhausted
    return None


def puzzle_start(p: Puzzle) -> dict:
    """Position shown to the solver: the dump's FEN after the opponent's first move."""
    moves = p.moves.split()
    board = chess.Board(p.fen)
    opp = chess.Move.from_uci(moves[0])
    opp_san = board.san(opp)
    board.push(opp)
    return {"fen": board.fen(), "initial_fen": p.fen, "opponent_move": moves[0], "opponent_san": opp_san,
            "solver_color": "white" if board.turn == chess.WHITE else "black", "solution_len": len(moves) // 2}


def solution_moves(p: Puzzle) -> list[str]:
    return p.moves.split()[1:]


def primary_concept(themes: str) -> str | None:
    ts = [t for t in themes.split() if t not in NON_CONCEPT_THEMES]
    # prefer the most specific (mating patterns, named motifs) over generic ones
    for t in ts:
        if t in CONCEPT_THEMES:
            return t
    return ts[0] if ts else None


def check_user_move(p: Puzzle, ply_index: int, played: list[str], uci: str) -> dict:
    """Validate the solver's move number `ply_index` (0-based count of solver moves).
    `played` holds the full line so far (solver + replies). Any mating move is accepted
    at the final step, as on Lichess."""
    sol = solution_moves(p)
    board = chess.Board(p.fen)
    board.push(chess.Move.from_uci(p.moves.split()[0]))
    for mv in played:
        board.push(chess.Move.from_uci(mv))
    try:
        move = chess.Move.from_uci(uci)
    except ValueError:
        return {"legal": False}
    if move not in board.legal_moves:
        # auto-queen convenience: e7e8 → e7e8q when that is the legal move
        alt = chess.Move.from_uci(uci + "q") if len(uci) == 4 else None
        if alt is not None and alt in board.legal_moves:
            move = alt
        else:
            return {"legal": False}
    expected = sol[2 * ply_index]
    san = board.san(move)
    board.push(move)
    correct = move.uci() == expected or board.is_checkmate()
    finished = correct and (2 * ply_index + 1 >= len(sol) or board.is_checkmate())
    reply = None
    if correct and not finished:
        reply = sol[2 * ply_index + 1]
        rb = board.copy()
        reply_san = rb.san(chess.Move.from_uci(reply))
        rb.push(chess.Move.from_uci(reply))
        return {"legal": True, "correct": True, "finished": False, "san": san, "uci": move.uci(),
                "reply": reply, "reply_san": reply_san, "fen": rb.fen(), "expected": expected}
    return {"legal": True, "correct": correct, "finished": finished or not correct, "san": san,
            "uci": move.uci(), "reply": None, "fen": board.fen(), "expected": expected}


def solution_san(p: Puzzle) -> list[str]:
    board = chess.Board(p.fen)
    moves = p.moves.split()
    board.push(chess.Move.from_uci(moves[0]))
    out = []
    for m in moves[1:]:
        mv = chess.Move.from_uci(m)
        out.append(board.san(mv))
        board.push(mv)
    return out


def theme_counts(db: Session) -> dict[str, int]:
    rows = db.execute(select(PuzzleTheme.theme, func.count()).group_by(PuzzleTheme.theme)).all()
    return {t: n for t, n in rows}


def themed_any(db: Session, themes: list[str]) -> list[str]:
    """Restrict a theme list to themes present in the local database."""
    have = set(db.execute(select(PuzzleTheme.theme).where(PuzzleTheme.theme.in_(themes)).distinct()).scalars())
    return [t for t in themes if t in have]

