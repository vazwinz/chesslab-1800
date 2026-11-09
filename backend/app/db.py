from __future__ import annotations

from pathlib import Path
from typing import Iterator

from sqlalchemy import create_engine, event
from sqlalchemy.engine import Engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from .config import settings


class Base(DeclarativeBase):
    pass


def make_engine(url: str) -> Engine:
    kwargs: dict = {}
    if url.startswith("sqlite"):
        path = url.replace("sqlite:///", "", 1)
        if path and path != ":memory:":
            Path(path).parent.mkdir(parents=True, exist_ok=True)
        kwargs["connect_args"] = {"check_same_thread": False, "timeout": 15}
    eng = create_engine(url, future=True, **kwargs)
    if url.startswith("sqlite"):

        @event.listens_for(eng, "connect")
        def _pragmas(dbapi_conn, _):  # pragma: no cover - trivial
            cur = dbapi_conn.cursor()
            cur.execute("PRAGMA journal_mode=WAL")
            cur.execute("PRAGMA foreign_keys=ON")
            cur.execute("PRAGMA synchronous=NORMAL")
            cur.close()

    return eng


engine = make_engine(settings.database_url)
SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
database_url = settings.database_url


def configure(url: str) -> None:
    """Re-point the app at another database (used by tests and scripts)."""
    global engine, database_url
    engine.dispose()
    engine = make_engine(url)
    database_url = url
    SessionLocal.configure(bind=engine)


def init_db() -> dict:
    """Create or upgrade the schema with the migrations (never with create_all), then record
    which app version last opened this database. Returns the migration report."""
    from . import models  # noqa: F401  (register tables)
    from .migrate import run_migrations, sqlite_path
    from .version import __version__

    db_file = sqlite_path(database_url)
    backups = db_file.parent / "backups" if db_file is not None else None
    with SessionLocal() as s:
        previous = _previous_version(s)
    # the copy is named after the version whose data it holds: chesslab-copia-da-0.3.0-<data>.db
    report = run_migrations(database_url, backup_dir=backups, label=f"da-{previous or '0.3.0'}")
    with SessionLocal() as s:
        from .models import KV

        kv = s.get(KV, "app_version")
        prev = kv.value.get("version") if kv else None
        if kv is None:
            s.add(KV(key="app_version", value={"version": __version__, "previous": None}))
        elif prev != __version__:
            kv.value = {"version": __version__, "previous": prev}
        if report.get("changed") and report.get("backup"):
            s.merge(KV(key="last_migration", value={**report, "seen": False}))
        s.commit()
    return report


def _previous_version(s: Session) -> str | None:
    try:
        from sqlalchemy import text

        row = s.execute(text("SELECT value FROM kv WHERE key = 'app_version'")).first()
    except Exception:  # table does not exist yet
        return None
    if not row:
        return None
    import json

    v = row[0]
    v = json.loads(v) if isinstance(v, str) else v
    return (v or {}).get("version")


def get_db() -> Iterator[Session]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
