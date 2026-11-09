"""Streaming, incremental importer for the official Lichess puzzle dump
(https://database.lichess.org/#puzzles, file lichess_db_puzzle.csv.zst).

* Streams the zstd file row by row — memory use is constant (one batch).
* Incremental: existing puzzle ids are updated (rating/popularity/plays change between
  dumps), new ids are inserted. Re-running on the same file is safe.
* Every puzzle is replayed with python-chess; puzzles whose moves are not legal are skipped.
"""
from __future__ import annotations

import csv
import io
import random
from collections.abc import Iterator
from pathlib import Path
from typing import Callable

import chess
from sqlalchemy import bindparam, delete, insert, select, update
from sqlalchemy.orm import Session

from ..models import ImportJob, Puzzle, PuzzleTheme, utcnow

UPDATABLE = ("rating", "rating_deviation", "popularity", "nb_plays", "game_url", "opening_tags", "solution_len")
EXPECTED_HEADER = ["PuzzleId", "FEN", "Moves", "Rating", "RatingDeviation", "Popularity", "NbPlays",
                   "Themes", "GameUrl", "OpeningTags"]


def open_rows(path: Path) -> Iterator[list[str]]:
    """Yield CSV rows (header included) from a .csv.zst or plain .csv file."""
    if path.suffix == ".zst":
        import zstandard

        fh = open(path, "rb")
        reader = zstandard.ZstdDecompressor().stream_reader(fh, read_size=1 << 20)
        text = io.TextIOWrapper(reader, encoding="utf-8", newline="")
    else:
        fh = None
        text = open(path, "r", encoding="utf-8", newline="")
    try:
        yield from csv.reader(text)
    finally:
        text.close()
        if fh is not None:
            fh.close()


def validate_puzzle(fen: str, moves: list[str]) -> bool:
    """True when the FEN is valid and every move of the line is legal."""
    try:
        board = chess.Board(fen)
    except ValueError:
        return False
    if not board.is_valid() or len(moves) < 2:
        return False
    for uci in moves:
        try:
            mv = chess.Move.from_uci(uci)
        except ValueError:
            return False
        if mv not in board.legal_moves:
            return False
        board.push(mv)
    return True


def parse_row(row: list[str]) -> dict | None:
    if len(row) < 8:
        return None
    try:
        moves = row[2].split()
        return {
            "id": row[0],
            "fen": row[1],
            "moves": row[2],
            "rating": int(row[3]),
            "rating_deviation": int(row[4] or 0),
            "popularity": int(row[5] or 0),
            "nb_plays": int(row[6] or 0),
            "themes": row[7],
            "game_url": row[8] if len(row) > 8 else "",
            "opening_tags": row[9] if len(row) > 9 else "",
            "solution_len": len(moves) // 2,
        }
    except ValueError:
        return None


def import_puzzles(db: Session, path: Path, batch_size: int = 5000, limit: int | None = None,
                   min_rating: int | None = None, max_rating: int | None = None,
                   validate: bool = True, progress: Callable[[ImportJob], None] | None = None) -> ImportJob:
    path = Path(path)
    job = ImportJob(source=str(path))
    db.add(job)
    db.commit()
    rows = open_rows(path)
    try:
        header = next(rows)
        if [h.strip().lstrip("﻿") for h in header[:8]] != EXPECTED_HEADER[:8]:
            raise ValueError("Este arquivo não é o banco de puzzles do Lichess (o cabeçalho do CSV é diferente do esperado).")
        batch: list[dict] = []
        for row in rows:
            job.rows_read += 1
            rec = parse_row(row)
            if rec is None or (validate and not validate_puzzle(rec["fen"], rec["moves"].split())):
                job.invalid += 1
                continue
            if (min_rating and rec["rating"] < min_rating) or (max_rating and rec["rating"] > max_rating):
                continue
            batch.append(rec)
            if len(batch) >= batch_size:
                _flush(db, batch, job)
                batch = []
                if progress:
                    progress(job)
            if limit and job.inserted + job.updated + len(batch) >= limit:
                break
        if batch:
            _flush(db, batch, job)
        job.status = "done"
    except Exception as exc:
        db.rollback()
        job.status = "failed"
        job.message = str(exc)[:2000]
        raise
    finally:
        job.finished_at = utcnow()
        db.add(job)
        db.commit()
    return job


def _flush(db: Session, batch: list[dict], job: ImportJob) -> None:
    ids = [r["id"] for r in batch]
    existing = {pid: (themes, rk, rating) for pid, themes, rk, rating in db.execute(
        select(Puzzle.id, Puzzle.themes, Puzzle.rand_key, Puzzle.rating).where(Puzzle.id.in_(ids)))}
    new_rows, theme_rows, upd_rows, theme_rating_rows = [], [], [], []
    for rec in batch:
        old = existing.get(rec["id"])
        if old is None:
            rk = random.random()
            new_rows.append({**rec, "rand_key": rk})
            theme_rows.extend({"puzzle_id": rec["id"], "theme": t, "rating": rec["rating"], "rand_key": rk}
                              for t in set(rec["themes"].split()))
            job.inserted += 1
            continue
        old_themes, rk, old_rating = old
        upd_rows.append({"b_id": rec["id"], **{k: rec[k] for k in UPDATABLE}, "themes": rec["themes"]})
        if old_themes != rec["themes"]:  # rare: rebuild this puzzle's theme rows
            db.execute(delete(PuzzleTheme).where(PuzzleTheme.puzzle_id == rec["id"]))
            theme_rows.extend({"puzzle_id": rec["id"], "theme": t, "rating": rec["rating"], "rand_key": rk}
                              for t in set(rec["themes"].split()))
        elif old_rating != rec["rating"]:
            theme_rating_rows.append({"b_id": rec["id"], "rating": rec["rating"]})
        job.updated += 1
    # bulk executemany statements: far faster than one ORM object per row
    if new_rows:
        db.execute(insert(Puzzle), new_rows)
    if theme_rows:
        db.execute(insert(PuzzleTheme), theme_rows)
    if upd_rows:
        db.connection().execute(
            update(Puzzle).where(Puzzle.id == bindparam("b_id"))
            .values({k: bindparam(k) for k in (*UPDATABLE, "themes")}), upd_rows)
    if theme_rating_rows:
        db.connection().execute(
            update(PuzzleTheme).where(PuzzleTheme.puzzle_id == bindparam("b_id")).values(rating=bindparam("rating")),
            theme_rating_rows)
    db.commit()
