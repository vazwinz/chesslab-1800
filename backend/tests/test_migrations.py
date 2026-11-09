"""Upgrading from 0.3.0 must keep every bit of progress. TEST_ONLY_db_v0_3_0.sqlite was created
and filled by the real 0.3.0 code (see fixtures/make_v030_db.py): create_all, no alembic_version."""
from __future__ import annotations

import shutil
import sqlite3
from pathlib import Path

import pytest
from alembic.autogenerate import compare_metadata
from alembic.runtime.migration import MigrationContext
from sqlalchemy import create_engine

from app import db as dbmod
from app import migrate
from app.db import Base

from .conftest import FIXTURES

V030 = FIXTURES / "TEST_ONLY_db_v0_3_0.sqlite"
TABLES = ["puzzles", "puzzle_themes", "attempts", "rating_history", "games", "game_mistakes", "loop_cycles",
          "plan_blocks", "kv", "repertoires", "repertoire_lines", "opening_drills", "concept_memory",
          "training_sessions", "intervention_assignments", "intervention_stats", "engine_cache", "import_jobs"]


def _counts(path: Path) -> dict:
    con = sqlite3.connect(path)
    try:
        return {t: con.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0] for t in TABLES}
    finally:
        con.close()


@pytest.fixture()
def old_db(tmp_path):
    p = tmp_path / "data" / "chesslab.db"
    p.parent.mkdir()
    shutil.copy(V030, p)
    return p


def test_fixture_is_a_real_unversioned_030_database():
    con = sqlite3.connect(V030)
    names = {r[0] for r in con.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    con.close()
    assert "alembic_version" not in names and set(TABLES) <= names


def test_upgrade_from_030_keeps_all_progress(old_db):
    before = _counts(old_db)
    assert before["attempts"] > 0 and before["games"] > 0 and before["rating_history"] > 0
    con = sqlite3.connect(old_db)
    last_rating = con.execute("SELECT rating FROM rating_history ORDER BY id DESC LIMIT 1").fetchone()[0]
    con.close()

    url = f"sqlite:///{old_db.as_posix()}"
    dbmod.configure(url)
    report = dbmod.init_db()
    assert report["changed"] and report["from"].startswith("0.3.0") and report["to"] == migrate.head_revision()
    assert report["backup"] and Path(report["backup"]).exists()
    assert _counts(Path(report["backup"])) == before, "the backup is a full copy of the old database"
    after = _counts(old_db)
    for t in TABLES:
        if t == "kv":
            assert after[t] >= before[t]
        elif t == "engine_cache":
            continue
        else:
            assert after[t] == before[t], t

    from fastapi.testclient import TestClient

    from app.main import app

    with TestClient(app) as c:
        d = c.get("/api/dashboard").json()
        assert d["totals"]["attempts"] == 12
        assert d["rating"]["current"] == round(last_rating)
        rr = d["real_rating"]  # filled from the PGN headers stored by 0.3.0
        assert rr["main"]["current"] in (1432, 1511) and rr["main"]["games"] == 4
        assert rr["main"]["time_class"] == "blitz"
        plan = c.get("/api/plan/today").json()
        titles = {b["title"] for b in plan["blocks"]}
        assert "Padrões táticos" in titles and "Tactical patterns" not in titles
        loop = c.get("/api/cognitive/loop").json()
        assert all("cycle started" != e["msg"] for e in loop["log"])
        assert any(e.get("code") == "cycle_started" and e["msg"] == "ciclo iniciado" for e in loop["log"])
        assert c.get("/api/app").json()["migration"]["backup"] == report["backup"]
        # the old games can be reviewed with the 0.4.0 API
        gid = c.get("/api/games").json()[0]["id"]
        g = c.get(f"/api/games/{gid}").json()
        assert g["moves_san"] and g["user_elo"] in (1432, 1511)


def test_upgrade_is_idempotent_and_backs_up_only_once(old_db):
    url = f"sqlite:///{old_db.as_posix()}"
    dbmod.configure(url)
    first = dbmod.init_db()
    second = dbmod.init_db()
    assert first["changed"] and not second["changed"] and second["backup"] is None
    assert len(list((old_db.parent / "backups").glob("*.db"))) == 1


def test_fresh_database_matches_the_models(tmp_path):
    """Every model change must ship with a migration: the migrated schema equals the ORM metadata."""
    url = f"sqlite:///{(tmp_path / 'fresh.db').as_posix()}"
    rep = migrate.run_migrations(url)
    assert rep["changed"] and rep["backup"] is None
    eng = create_engine(url)
    with eng.connect() as conn:
        diff = compare_metadata(MigrationContext.configure(conn, opts={"compare_type": True}), Base.metadata)
    eng.dispose()
    assert diff == [], diff


def test_failed_migration_changes_nothing(old_db, tmp_path, monkeypatch):
    """A revision that crashes halfway must leave the 0.3.0 database exactly as it was."""
    mig = tmp_path / "migrations"
    shutil.copytree(migrate.MIGRATIONS_DIR, mig, ignore=shutil.ignore_patterns("__pycache__"))
    (mig / "versions" / "9999_boom.py").write_text(
        'import sqlalchemy as sa\nfrom alembic import op\nrevision = "9999_boom"\n'
        f'down_revision = "{migrate.head_revision()}"\nbranch_labels = None\ndepends_on = None\n'
        'def upgrade():\n    op.create_table("should_not_exist", sa.Column("id", sa.Integer, primary_key=True))\n'
        '    raise RuntimeError("boom")\n'
        'def downgrade():\n    pass\n')
    monkeypatch.setattr(migrate, "MIGRATIONS_DIR", mig)
    before = _counts(old_db)
    with pytest.raises(migrate.MigrationError) as e:
        migrate.run_migrations(f"sqlite:///{old_db.as_posix()}", backup_dir=old_db.parent / "backups")
    assert "Nada foi alterado" in str(e.value)
    con = sqlite3.connect(old_db)
    names = {r[0] for r in con.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    cols = {r[1] for r in con.execute("PRAGMA table_info(games)")}
    titles = {r[0] for r in con.execute("SELECT title FROM plan_blocks")}
    con.close()
    assert "should_not_exist" not in names and "alembic_version" not in names
    assert "user_elo" not in cols and "Tactical patterns" in titles
    assert _counts(old_db) == before
