"""0.4.0: your real rating. Imported games get the rating written in their PGN headers
(WhiteElo/BlackElo, which Chess.com and Lichess export) and a time class (bullet, blitz,
rapid, daily). Games you already imported are filled in from the PGN stored with them.

Revision ID: 0003_v040_game_ratings
Revises: 0002_v040_ptbr
Create Date: 2026-11-08
"""
from __future__ import annotations

import re

import sqlalchemy as sa
from alembic import op

revision = "0003_v040_game_ratings"
down_revision = "0002_v040_ptbr"
branch_labels = None
depends_on = None

HEADER = re.compile(r'^\[(\w+)\s+"([^"]*)"\]\s*$', re.MULTILINE)


def _time_class(tc: str | None) -> str | None:
    if not tc or tc in ("-", "?"):
        return None
    if "/" in tc:
        return "daily"
    m = re.match(r"^(\d+)(?:\+(\d+))?$", tc)
    if not m:
        return None
    est = int(m[1]) + 40 * int(m[2] or 0)
    return "bullet" if est < 180 else "blitz" if est < 600 else "rapid"


def _elo(v: str | None) -> int | None:
    try:
        x = int((v or "").strip())
    except ValueError:
        return None
    return x if 100 <= x <= 3500 else None


def upgrade() -> None:
    with op.batch_alter_table("games") as b:
        b.add_column(sa.Column("time_class", sa.String(length=12), nullable=True))
        b.add_column(sa.Column("user_elo", sa.Integer(), nullable=True))
        b.add_column(sa.Column("opponent_elo", sa.Integer(), nullable=True))
    bind = op.get_bind()
    rows = bind.execute(sa.text("SELECT id, pgn, user_color, time_control FROM games")).all()
    for gid, pgn, color, tc in rows:
        headers = dict(HEADER.findall((pgn or "")[:4000]))
        w, bl = _elo(headers.get("WhiteElo")), _elo(headers.get("BlackElo"))
        mine, theirs = (w, bl) if color == "white" else (bl, w) if color == "black" else (None, None)
        bind.execute(sa.text("UPDATE games SET time_class = :c, user_elo = :m, opponent_elo = :o WHERE id = :id"),
                     {"c": _time_class(tc or headers.get("TimeControl")), "m": mine, "o": theirs, "id": gid})


def downgrade() -> None:
    with op.batch_alter_table("games") as b:
        b.drop_column("opponent_elo")
        b.drop_column("user_elo")
        b.drop_column("time_class")
