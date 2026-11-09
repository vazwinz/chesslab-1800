"""Build TEST_ONLY_db_v0_3_0.sqlite: a database created and filled by the REAL 0.3.0 code
(create_all, no migrations), used by tests/test_migrations.py to prove that upgrading keeps
everything. Re-create it only if you need to (it is committed):

    git worktree add /tmp/aura030 e0f43c1
    STOCKFISH_PATH=/usr/games/stockfish backend/.venv/bin/python backend/tests/fixtures/make_v030_db.py /tmp/aura030/backend

The puzzles and games inside are the TEST_ONLY fixtures (not Lichess or Chess.com data)."""
from __future__ import annotations

import os
import re
import sqlite3
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
OUT = HERE / "TEST_ONLY_db_v0_3_0.sqlite"


def main(old_backend: str) -> None:
    tmp = HERE / "_building_v030.db"
    for p in (tmp, Path(str(tmp) + "-wal"), Path(str(tmp) + "-shm")):
        p.unlink(missing_ok=True)
    os.environ["DATABASE_URL"] = f"sqlite:///{tmp.as_posix()}"
    sys.path.insert(0, old_backend)
    from fastapi.testclient import TestClient

    from app import db as dbmod  # the 0.3.0 package
    from app.main import app
    from app.services import puzzles
    from app.services.importer import import_puzzles

    assert not hasattr(dbmod, "database_url"), "this must run with the 0.3.0 code"
    dbmod.init_db()
    with dbmod.SessionLocal() as s:
        import_puzzles(s, HERE / "TEST_ONLY_lichess_format_puzzles.csv.zst")
    pgn = (HERE / "TEST_ONLY_games.pgn").read_text()
    # give the synthetic games the rating headers Chess.com exports
    pgn = re.sub(r'(\[TimeControl "[^"]*"\])', r'\1\n[WhiteElo "1432"]\n[BlackElo "1511"]', pgn)
    with TestClient(app) as c:
        for kind in ("mixed", "loop"):
            sid = c.post("/api/sessions", json={"kind": kind}).json()["id"]
            for i in range(6):
                ex = c.post(f"/api/sessions/{sid}/next").json()
                sol = c.get(f"/api/puzzles/{ex['puzzle_id']}").json()
                if i % 3 == 2:  # a wrong move
                    import chess

                    b = chess.Board(ex["fen"])
                    right = b.parse_san(sol["solution_san"][0]).uci()
                    wrong = next(m.uci() for m in b.legal_moves if m.uci() != right)
                    c.post(f"/api/attempts/{ex['attempt_id']}/move", json={"uci": wrong, "elapsed_ms": 9000})
                else:
                    with dbmod.SessionLocal() as s:
                        from app.models import Puzzle

                        moves = puzzles.solution_moves(s.get(Puzzle, ex["puzzle_id"]))
                    for k in range(0, len(moves), 2):
                        c.post(f"/api/attempts/{ex['attempt_id']}/move", json={"uci": moves[k], "elapsed_ms": 7000})
            c.post(f"/api/sessions/{sid}/end")
        r = c.post("/api/games/import", json={"pgn": pgn, "player_names": ["TestUser"], "analyze": True})
        assert r.status_code == 200, r.text
        plan = c.get("/api/plan/today").json()
        c.post(f"/api/plan/blocks/{plan['blocks'][0]['id']}", json={"completed": True})
        rid = c.post("/api/openings", json={"name": "Italiana", "color": "white"}).json()["id"]
        line = c.post(f"/api/openings/{rid}/lines", json={"name": "Principal", "moves": "1. e4 e5 2. Nf3 Nc6 3. Bc4"}).json()
        c.post(f"/api/openings/lines/{line['id']}/drill", json={"ply": 2, "uci": "b1c3"})
    dbmod.engine.dispose()
    con = sqlite3.connect(tmp)
    con.execute("PRAGMA wal_checkpoint(TRUNCATE)")
    con.execute("PRAGMA journal_mode=DELETE")
    con.execute("VACUUM")
    con.close()
    tmp.replace(OUT)
    for p in (Path(str(tmp) + "-wal"), Path(str(tmp) + "-shm")):
        p.unlink(missing_ok=True)
    print("written", OUT, OUT.stat().st_size, "bytes")


if __name__ == "__main__":
    main(sys.argv[1])
