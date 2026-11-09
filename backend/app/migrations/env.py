"""Alembic environment for AURA.

At runtime the app calls app.migrate.run_migrations(), which passes an open connection in
config.attributes["connection"]. For development you can also run Alembic from backend/:

    .venv/bin/python -m alembic -c alembic.ini revision --autogenerate -m "describe change"
    .venv/bin/python -m alembic -c alembic.ini upgrade head
"""
from __future__ import annotations

from alembic import context
from sqlalchemy import create_engine

from app import models  # noqa: F401  (registers every table on Base.metadata)
from app.config import settings
from app.db import Base

config = context.config
target_metadata = Base.metadata


def _configure(connection) -> None:
    context.configure(
        connection=connection,
        target_metadata=target_metadata,
        render_as_batch=True,  # SQLite cannot ALTER most things in place; batch mode copies the table
        compare_type=True,
    )


def run_migrations_online() -> None:
    connection = config.attributes.get("connection")
    if connection is not None:
        _configure(connection)
        with context.begin_transaction():
            context.run_migrations()
        return
    url = config.get_main_option("sqlalchemy.url") or settings.database_url
    engine = create_engine(url)
    with engine.connect() as conn:
        _configure(conn)
        with context.begin_transaction():
            context.run_migrations()


def run_migrations_offline() -> None:
    url = config.get_main_option("sqlalchemy.url") or settings.database_url
    context.configure(url=url, target_metadata=target_metadata, literal_binds=True, render_as_batch=True)
    with context.begin_transaction():
        context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
