"""Import the official Lichess puzzle database (lichess_db_puzzle.csv.zst) into ChessLab.

    python scripts/import_puzzles.py path/to/lichess_db_puzzle.csv.zst
    python scripts/import_puzzles.py path/to/lichess_db_puzzle.csv.zst --min-rating 800 --max-rating 2400
    python scripts/import_puzzles.py path/to/file --limit 200000        # quick partial import

Streams the file (constant memory), validates every line with python-chess, and is incremental:
re-running with a newer dump updates existing puzzles and adds new ones.
Separate from app startup on purpose — the full import takes several minutes."""
from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.db import SessionLocal, configure, init_db  # noqa: E402
from app.services.importer import import_puzzles  # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("path", type=Path)
    ap.add_argument("--database-url", help="override DATABASE_URL")
    ap.add_argument("--limit", type=int)
    ap.add_argument("--min-rating", type=int)
    ap.add_argument("--max-rating", type=int)
    ap.add_argument("--batch-size", type=int, default=5000)
    ap.add_argument("--no-validate", action="store_true", help="skip python-chess replay of each puzzle (faster)")
    a = ap.parse_args()
    if not a.path.exists():
        print(f"file not found: {a.path}", file=sys.stderr)
        return 2
    if "TEST_ONLY" in a.path.name:
        print("Refusing to import a TEST_ONLY fixture into an application database.", file=sys.stderr)
        return 2
    if a.database_url:
        configure(a.database_url)
    init_db()
    t0 = time.time()

    def progress(job):
        rate = job.rows_read / max(1e-9, time.time() - t0)
        print(f"\rread {job.rows_read:,}  inserted {job.inserted:,}  updated {job.updated:,}  "
              f"invalid {job.invalid:,}  ({rate:,.0f} rows/s)", end="", flush=True)

    with SessionLocal() as db:
        job = import_puzzles(db, a.path, batch_size=a.batch_size, limit=a.limit, min_rating=a.min_rating,
                             max_rating=a.max_rating, validate=not a.no_validate, progress=progress)
    print(f"\n{job.status}: read {job.rows_read:,}, inserted {job.inserted:,}, updated {job.updated:,}, "
          f"invalid {job.invalid:,} in {time.time() - t0:,.0f}s")
    return 0 if job.status == "done" else 1


if __name__ == "__main__":
    raise SystemExit(main())
