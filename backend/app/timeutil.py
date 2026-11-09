"""Timestamps are stored as naive UTC. These helpers turn them into what the user sees:
calendar days in the computer's local time zone and ISO strings that say they are UTC."""
from __future__ import annotations

from datetime import date, datetime, timezone


def local_date(dt: datetime | None) -> date | None:
    if dt is None:
        return None
    return dt.replace(tzinfo=timezone.utc).astimezone().date()


def iso(dt: datetime | None) -> str | None:
    if dt is None:
        return None
    return dt.replace(tzinfo=timezone.utc).isoformat().replace("+00:00", "Z")
