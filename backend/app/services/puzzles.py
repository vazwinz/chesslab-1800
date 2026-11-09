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


PROBES_PER_WINDOW = 80
MAX_EMPTY_PROBES = 40  # a filter that matches almost nothing: widen instead of probing forever


def _query(theme: str | None, rating_eq: int | None, lo: int, hi: int, min_len, max_len, r: float, forward: bool):
    if theme:
        q = select(Puzzle).join(PuzzleTheme, PuzzleTheme.puzzle_id == Puzzle.id).where(PuzzleTheme.theme == theme)
        q = q.where(PuzzleTheme.rating == rating_eq) if rating_eq is not None else \
            q.where(PuzzleTheme.rating.between(lo, hi))
        key = PuzzleTheme.rand_key
    else:
        q = select(Puzzle)
        q = q.where(Puzzle.rating == rating_eq) if rating_eq is not None else q.where(Puzzle.rating.between(lo, hi))
        key = Puzzle.rand_key
    if min_len:
        q = q.where(Puzzle.solution_len >= min_len)
    if max_len:
        q = q.where(Puzzle.solution_len <= max_len)
    return q.where(key >= r).order_by(key) if forward else q.where(key < r).order_by(key.desc())


def select_puzzle(db: Session, rating_min: int, rating_max: int, themes: list[str] | None = None,
                  min_len: int | None = None, max_len: int | None = None, exclude: set[str] | None = None,
                  exclude_recent_days: int = 30, widen: bool = True) -> Puzzle | None:
    """Random puzzle in a rating window, optionally by theme, avoiding recently seen ones.

    Fast on the full Lichess dump (millions of rows): instead of a range on rating, which made
    SQLite sort every puzzle of the window by rand_key (~0.7 s per puzzle on 3M rows), it first
    probes single random rating VALUES (`rating = R AND rand_key >= r`), which the composite
    indexes (rating, rand_key) and (theme, rating, rand_key) answer in order without sorting.
    Only when the probes find nothing (a small or sparse database, or a very narrow filter) it
    falls back to the range query, which is cheap exactly in those cases."""
    excluded = set(exclude or ()) | recent_puzzle_ids(db, exclude_recent_days)
    lo, hi = int(rating_min), int(rating_max)
    for _ in range(4 if widen else 1):
        values = list(range(lo, hi + 1))
        random.shuffle(values)
        empty = 0
        for value in values[:PROBES_PER_WINDOW]:
            if empty >= MAX_EMPTY_PROBES:
                break
            empty += 1
            theme = random.choice(themes) if themes else None
            r = random.random()
            for forward in (True, False):
                for p in db.execute(_query(theme, value, lo, hi, min_len, max_len, r, forward).limit(20)).scalars():
                    empty = 0
                    if p.id not in excluded:
                        return p
        for theme in (random.sample(themes, len(themes)) if themes else [None]):
            r = random.random()
            for forward in (True, False):
                for p in db.execute(_query(theme, None, lo, hi, min_len, max_len, r, forward).limit(60)).scalars():
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


def theme_counts(db: Session, refresh: bool = False) -> dict[str, int]:
    """Puzzles per theme. Counting 15M theme rows takes ~0.5 s on the full dump, so the result is
    cached in the database and recomputed only when the number of puzzles changes."""
    from ..models import KV

    total = puzzle_count(db)
    kv = db.get(KV, "theme_counts")
    if kv is not None and not refresh and (kv.value or {}).get("total") == total:
        return dict(kv.value.get("counts") or {})
    counts = {t: n for t, n in db.execute(select(PuzzleTheme.theme, func.count()).group_by(PuzzleTheme.theme))}
    value = {"total": total, "counts": counts}
    if kv is None:
        db.add(KV(key="theme_counts", value=value))
    else:
        kv.value = value
    db.commit()
    return counts


def themed_any(db: Session, themes: list[str]) -> list[str]:
    """Restrict a theme list to themes present in the local database."""
    have = theme_counts(db)
    return [t for t in themes if have.get(t)]

