"""Database migrations, run automatically every time the app starts.

* New database: Alembic creates every table (revision 0001 and up).
* Database from AURA 0.3.0: it was created with create_all and has no `alembic_version`
  table. Its tables are checked (anything missing is added), it is stamped at the 0.3.0
  baseline, then the newer revisions run. Your progress stays where it is.
* Before changing an existing database, a full copy is written to `backups/` next to it
  (SQLite backup API, safe with WAL). The 5 most recent copies are kept.
* The whole upgrade runs in ONE SQLite transaction (DDL included): if any step fails,
  nothing is changed and the error is reported instead of leaving a half-migrated file.
"""
from __future__ import annotations

import logging
import sqlite3
from datetime import datetime
from pathlib import Path

from alembic import command
from alembic.config import Config
from alembic.runtime.migration import MigrationContext
from alembic.script import ScriptDirectory
from sqlalchemy import MetaData, create_engine, event, inspect
from sqlalchemy.engine import Connection, Engine, make_url

log = logging.getLogger(__name__)

MIGRATIONS_DIR = Path(__file__).resolve().parent / "migrations"
BASELINE = "0001_baseline_030"
LEGACY_TABLES = {"puzzles", "attempts", "kv", "rating_history"}  # present in every 0.3.0 database
KEEP_BACKUPS = 5


class MigrationError(RuntimeError):
    pass


# SQLite failures a person can act on, said in Portuguese (the full error still goes to aura.log)
_DB_ERRORS = (
    ("file is not a database", "o arquivo chesslab.db está corrompido ou não é um banco de dados do AURA"),
    ("database disk image is malformed", "o arquivo chesslab.db está danificado"),
    ("database is locked", "o banco de dados está em uso por outro programa"),
    ("unable to open database file", "não foi possível abrir o arquivo do banco de dados (pasta ou permissão)"),
    ("disk i/o error", "erro de leitura ou gravação no disco"),
    ("database or disk is full", "o disco está cheio"),
    ("readonly database", "o arquivo do banco de dados está como somente leitura"),
)


def describe_error(exc: BaseException) -> str:
    """One short line for the error dialog: a Portuguese reason for the usual SQLite failures,
    otherwise the first line of the error, without SQLAlchemy's SQL dump and documentation link."""
    orig = getattr(exc, "orig", None) or exc  # SQLAlchemy wraps the sqlite3 error
    text = str(orig).strip()
    low = text.lower()
    for needle, reason in _DB_ERRORS:
        if needle in low:
            return reason
    return (text.splitlines()[0] if text else type(orig).__name__)[:300]


def alembic_config() -> Config:
    cfg = Config()
    cfg.set_main_option("script_location", str(MIGRATIONS_DIR))
    return cfg


def head_revision() -> str:
    return ScriptDirectory.from_config(alembic_config()).get_current_head()


def sqlite_path(url: str) -> Path | None:
    u = make_url(url)
    if u.get_backend_name() != "sqlite" or not u.database or u.database == ":memory:":
        return None
    return Path(u.database)


def _migration_engine(url: str) -> Engine:
    eng = create_engine(url)
    if url.startswith("sqlite"):
        @event.listens_for(eng, "connect")
        def _connect(dbapi_conn, _rec):  # pragma: no cover - trivial
            # take transaction control away from pysqlite so DDL runs inside our transaction
            dbapi_conn.isolation_level = None
            dbapi_conn.execute("PRAGMA busy_timeout = 15000")

        @event.listens_for(eng, "begin")
        def _begin(conn):  # pragma: no cover - trivial
            conn.exec_driver_sql("BEGIN IMMEDIATE")
    return eng


def database_state(conn: Connection) -> dict:
    tables = set(inspect(conn).get_table_names())
    current = MigrationContext.configure(conn).get_current_revision()
    return {"tables": tables, "current": current,
            "legacy": current is None and bool(tables & LEGACY_TABLES),
            "empty": not (tables - {"alembic_version"})}


def backup_sqlite(db_path: Path, backup_dir: Path, label: str) -> Path:
    backup_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    dest = backup_dir / f"chesslab-copia-{label}-{stamp}.db"
    src = sqlite3.connect(str(db_path))
    dst = sqlite3.connect(str(dest))
    try:
        src.backup(dst)
    finally:
        dst.close()
        src.close()
    old = sorted(list(backup_dir.glob("chesslab-copia-*.db")) + list(backup_dir.glob("chesslab-antes-de-*.db")),
                 key=lambda p: p.stat().st_mtime, reverse=True)
    for p in old[KEEP_BACKUPS:]:
        try:
            p.unlink()
        except OSError:
            pass
    return dest


def _baseline_metadata() -> MetaData:
    """The 0.3.0 schema, obtained by running the baseline revision on an in-memory database."""
    eng = _migration_engine("sqlite://")
    cfg = alembic_config()
    with eng.begin() as conn:
        cfg.attributes["connection"] = conn
        command.upgrade(cfg, BASELINE)
        md = MetaData()
        md.reflect(conn)
    eng.dispose()
    md.remove(md.tables["alembic_version"])
    return md


def _repair_legacy(conn: Connection) -> list[str]:
    """Make an unversioned (0.3.0) database match the baseline before stamping it."""
    fixes = []
    base = _baseline_metadata()
    insp = inspect(conn)
    have = set(insp.get_table_names())
    for name, table in base.tables.items():
        if name not in have:
            table.create(conn)
            fixes.append(f"tabela criada: {name}")
            continue
        cols = {c["name"] for c in insp.get_columns(name)}
        for col in table.columns:
            if col.name not in cols:
                ddl = col.type.compile(dialect=conn.dialect)
                conn.exec_driver_sql(f'ALTER TABLE "{name}" ADD COLUMN "{col.name}" {ddl}')
                fixes.append(f"coluna criada: {name}.{col.name}")
        idx = {i["name"] for i in insp.get_indexes(name)}
        for index in table.indexes:
            if index.name not in idx:
                index.create(conn)
                fixes.append(f"índice criado: {index.name}")
    return fixes


def run_migrations(url: str, backup_dir: Path | None = None, label: str = "antes-da-atualizacao") -> dict:
    """Bring the database at `url` to the newest schema. Returns a small report."""
    mig = _migration_engine(url)
    try:
        with mig.connect() as conn:
            state = database_state(conn)
        head = head_revision()
        report: dict = {"from": "0.3.0 (sem migrações)" if state["legacy"] else state["current"], "to": head,
                        "changed": False, "backup": None, "repairs": []}
        if state["current"] == head:
            return report
        db_path = sqlite_path(url)
        if backup_dir is not None and db_path is not None and db_path.exists() and not state["empty"]:
            report["backup"] = str(backup_sqlite(db_path, backup_dir, label))
            log.info("backup before migrating: %s", report["backup"])
        cfg = alembic_config()
        with mig.begin() as conn:
            cfg.attributes["connection"] = conn
            if state["legacy"]:
                report["repairs"] = _repair_legacy(conn)
                command.stamp(cfg, BASELINE)
            command.upgrade(cfg, "head")
        report["changed"] = True
        log.info("database migrated %s -> %s", report["from"], head)
        return report
    except Exception as exc:
        log.exception("database migration failed")
        raise MigrationError(f"Não foi possível atualizar o banco de dados: {describe_error(exc)}. "
                             "Nada foi alterado.") from exc
    finally:
        mig.dispose()
