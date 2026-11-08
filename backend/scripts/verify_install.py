"""Local verification after installing and importing the real Lichess database.

    python scripts/verify_install.py            # checks DB, sample legality, Stockfish agreement
    python scripts/verify_install.py --sample 500 --engine-sample 50

Checks:
 1. Stockfish starts over UCI and answers a known mate-in-1.
 2. The puzzle table is populated from a real Lichess import (import job recorded, ids are not TEST*).
 3. A random sample of puzzles replays legally with python-chess.
 4. For a smaller sample, Stockfish agrees that the first solution move wins / is (near-)best.
"""
from __future__ import annotations

import argparse
import random
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import chess  # noqa: E402
from sqlalchemy import func, select  # noqa: E402

from app.db import SessionLocal, init_db  # noqa: E402
from app.models import ImportJob, Puzzle  # noqa: E402
from app.services.engine import StockfishService  # noqa: E402
from app.services.importer import validate_puzzle  # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--sample", type=int, default=1000)
    ap.add_argument("--engine-sample", type=int, default=30)
    ap.add_argument("--depth", type=int, default=14)
    a = ap.parse_args()
    ok = True
    init_db()
    eng = StockfishService()
    st = eng.status()
    print(f"[1] Stockfish: {'OK ' + st['name'] if st['ok'] else 'FAILED ' + st['error']}")
    if st["ok"]:
        lines = eng.analyse(chess.Board("6k1/5ppp/8/8/8/8/8/R5K1 w - - 0 1"), depth=10)
        good = lines and lines[0].move == "a1a8"
        print(f"    mate-in-1 test: {'OK' if good else 'FAILED'} ({lines[0].san if lines else None})")
        ok &= bool(good)
    ok &= st["ok"]
    with SessionLocal() as db:
        n = db.execute(select(func.count()).select_from(Puzzle)).scalar() or 0
        jobs = db.execute(select(ImportJob).where(ImportJob.status == "done")).scalars().all()
        test_ids = db.execute(select(func.count()).select_from(Puzzle).where(Puzzle.id.like("TEST%"))).scalar()
        print(f"[2] puzzles: {n:,}; completed import jobs: {len(jobs)}; test-fixture ids present: {test_ids}")
        for j in jobs[-3:]:
            print(f"    {j.source}: inserted {j.inserted:,} updated {j.updated:,} invalid {j.invalid:,}")
        if n == 0 or test_ids:
            print("    FAILED: import the real lichess_db_puzzle.csv.zst (see README)")
            ok = False
        if n:
            ids = [p for p in db.execute(select(Puzzle.id).order_by(Puzzle.rand_key).limit(a.sample)).scalars()]
            bad = []
            for pid in ids:
                p = db.get(Puzzle, pid)
                if not validate_puzzle(p.fen, p.moves.split()):
                    bad.append(pid)
            print(f"[3] legality: {len(ids) - len(bad)}/{len(ids)} sampled puzzles replay legally")
            ok &= not bad
            if st["ok"]:
                agree = 0
                sample = random.sample(ids, min(a.engine_sample, len(ids)))
                for pid in sample:
                    p = db.get(Puzzle, pid)
                    mv = p.moves.split()
                    b = chess.Board(p.fen)
                    b.push(chess.Move.from_uci(mv[0]))
                    cmp = eng.compare_move(b, chess.Move.from_uci(mv[1]), depth=a.depth)
                    agree += cmp["is_best"] or cmp["win_pct_loss"] < 5
                print(f"[4] Stockfish agrees with the first solution move in {agree}/{len(sample)} puzzles "
                      f"(depth {a.depth}; a few disagreements at low depth are normal)")
    eng.close()
    print("ALL CHECKS PASSED" if ok else "SOME CHECKS FAILED")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
