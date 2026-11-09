"""ORM models. ChessLab is a single-user local application, so there is no user table:
all rows belong to the local player."""
from __future__ import annotations

from datetime import date, datetime, timezone

from sqlalchemy import (
    JSON,
    Boolean,
    Date,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
)
from sqlalchemy.orm import Mapped, mapped_column

from .db import Base


def utcnow() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


# ---------------------------------------------------------------- puzzles
class Puzzle(Base):
    __tablename__ = "puzzles"
    id: Mapped[str] = mapped_column(String(16), primary_key=True)
    fen: Mapped[str] = mapped_column(String(100))
    moves: Mapped[str] = mapped_column(Text)  # space separated UCI, first move = opponent's
    rating: Mapped[int] = mapped_column(Integer, index=True)
    rating_deviation: Mapped[int] = mapped_column(Integer, default=0)
    popularity: Mapped[int] = mapped_column(Integer, default=0)
    nb_plays: Mapped[int] = mapped_column(Integer, default=0)
    themes: Mapped[str] = mapped_column(Text, default="")
    game_url: Mapped[str] = mapped_column(String(200), default="")
    opening_tags: Mapped[str] = mapped_column(String(300), default="")
    solution_len: Mapped[int] = mapped_column(Integer, default=1)  # number of moves the user must find
    rand_key: Mapped[float] = mapped_column(Float, index=True)

    __table_args__ = (Index("ix_puzzles_rating_rand", "rating", "rand_key"),)


class PuzzleTheme(Base):
    __tablename__ = "puzzle_themes"
    puzzle_id: Mapped[str] = mapped_column(ForeignKey("puzzles.id", ondelete="CASCADE"), primary_key=True)
    theme: Mapped[str] = mapped_column(String(40), primary_key=True)
    rating: Mapped[int] = mapped_column(Integer)  # denormalised for (theme, rating) range scans
    rand_key: Mapped[float] = mapped_column(Float)

    __table_args__ = (Index("ix_theme_rating_rand", "theme", "rating", "rand_key"),)


class ImportJob(Base):
    __tablename__ = "import_jobs"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    source: Mapped[str] = mapped_column(String(500))
    started_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    rows_read: Mapped[int] = mapped_column(Integer, default=0)
    inserted: Mapped[int] = mapped_column(Integer, default=0)
    updated: Mapped[int] = mapped_column(Integer, default=0)
    invalid: Mapped[int] = mapped_column(Integer, default=0)
    status: Mapped[str] = mapped_column(String(20), default="running")
    message: Mapped[str] = mapped_column(Text, default="")


# ---------------------------------------------------------------- training data
class TrainingSession(Base):
    __tablename__ = "training_sessions"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    kind: Mapped[str] = mapped_column(String(30), default="mixed")
    theme: Mapped[str | None] = mapped_column(String(40), nullable=True)
    started_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    last_activity_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    ended_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    assignment_id: Mapped[int | None] = mapped_column(ForeignKey("intervention_assignments.id"), nullable=True)
    pressure_level: Mapped[int | None] = mapped_column(Integer, nullable=True)
    break_suggested_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)


class Attempt(Base):
    """One exercise attempt with full timing data (the Cognitive Engine's raw material)."""

    __tablename__ = "attempts"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    session_id: Mapped[int | None] = mapped_column(ForeignKey("training_sessions.id"), nullable=True, index=True)
    exercise_kind: Mapped[str] = mapped_column(String(20), default="puzzle")  # puzzle | game_position
    puzzle_id: Mapped[str | None] = mapped_column(ForeignKey("puzzles.id"), nullable=True, index=True)
    game_mistake_id: Mapped[int | None] = mapped_column(ForeignKey("game_mistakes.id"), nullable=True)
    mode: Mapped[str] = mapped_column(String(30), default="standard")
    concept: Mapped[str | None] = mapped_column(String(40), nullable=True, index=True)
    themes: Mapped[str] = mapped_column(Text, default="")
    served_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, index=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    first_move_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    total_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    time_limit_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    min_think_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    timed_out: Mapped[bool] = mapped_column(Boolean, default=False)
    correct: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    fail_ply: Mapped[int | None] = mapped_column(Integer, nullable=True)  # index of user move that failed
    moves_played: Mapped[list] = mapped_column(JSON, default=list)
    move_times_ms: Mapped[list] = mapped_column(JSON, default=list)
    expected_move: Mapped[str | None] = mapped_column(String(8), nullable=True)
    hesitation: Mapped[dict] = mapped_column(JSON, default=dict)
    candidates: Mapped[list] = mapped_column(JSON, default=list)
    candidate_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    puzzle_rating: Mapped[int | None] = mapped_column(Integer, nullable=True)
    solution_len: Mapped[int | None] = mapped_column(Integer, nullable=True)
    user_rating_before: Mapped[float | None] = mapped_column(Float, nullable=True)
    user_rating_after: Mapped[float | None] = mapped_column(Float, nullable=True)
    expected_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    index_in_session: Mapped[int | None] = mapped_column(Integer, nullable=True)
    cp_loss: Mapped[int | None] = mapped_column(Integer, nullable=True)
    error_category: Mapped[str | None] = mapped_column(String(40), nullable=True, index=True)
    error_detail: Mapped[dict] = mapped_column(JSON, default=dict)
    assignment_id: Mapped[int | None] = mapped_column(ForeignKey("intervention_assignments.id"), nullable=True)
    retention_probe: Mapped[str | None] = mapped_column(String(20), nullable=True)  # recall | transfer
    pressure_level: Mapped[int | None] = mapped_column(Integer, nullable=True)


class RatingPoint(Base):
    __tablename__ = "rating_history"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    ts: Mapped[datetime] = mapped_column(DateTime, default=utcnow, index=True)
    rating: Mapped[float] = mapped_column(Float)
    rd: Mapped[float] = mapped_column(Float)
    attempt_id: Mapped[int | None] = mapped_column(ForeignKey("attempts.id"), nullable=True)


# ---------------------------------------------------------------- games
class Game(Base):
    __tablename__ = "games"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    fingerprint: Mapped[str] = mapped_column(String(64), unique=True)
    pgn: Mapped[str] = mapped_column(Text)
    white: Mapped[str] = mapped_column(String(80), default="?")
    black: Mapped[str] = mapped_column(String(80), default="?")
    result: Mapped[str] = mapped_column(String(10), default="*")
    played_on: Mapped[date | None] = mapped_column(Date, nullable=True)
    time_control: Mapped[str] = mapped_column(String(30), default="")
    time_class: Mapped[str | None] = mapped_column(String(12), nullable=True)  # bullet | blitz | rapid | daily
    user_color: Mapped[str | None] = mapped_column(String(5), nullable=True)  # white | black
    user_elo: Mapped[int | None] = mapped_column(Integer, nullable=True)  # your rating in the PGN header
    opponent_elo: Mapped[int | None] = mapped_column(Integer, nullable=True)
    source: Mapped[str] = mapped_column(String(30), default="pgn")
    imported_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    analyzed: Mapped[bool] = mapped_column(Boolean, default=False)
    analysis_depth: Mapped[int | None] = mapped_column(Integer, nullable=True)
    metrics: Mapped[dict] = mapped_column(JSON, default=dict)


class GameMistake(Base):
    """A meaningful mistake by the user in one of their real games (Error DNA source)."""

    __tablename__ = "game_mistakes"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    game_id: Mapped[int] = mapped_column(ForeignKey("games.id", ondelete="CASCADE"), index=True)
    ply: Mapped[int] = mapped_column(Integer)
    fen_before: Mapped[str] = mapped_column(String(100))
    move_uci: Mapped[str] = mapped_column(String(8))
    move_san: Mapped[str] = mapped_column(String(12))
    best_uci: Mapped[str] = mapped_column(String(8))
    best_san: Mapped[str] = mapped_column(String(12))
    eval_before_cp: Mapped[int] = mapped_column(Integer)
    eval_after_cp: Mapped[int] = mapped_column(Integer)
    cp_loss: Mapped[int] = mapped_column(Integer)
    win_pct_loss: Mapped[float] = mapped_column(Float)
    severity: Mapped[str] = mapped_column(String(12))  # inaccuracy | mistake | blunder
    clock_s: Mapped[float | None] = mapped_column(Float, nullable=True)
    think_s: Mapped[float | None] = mapped_column(Float, nullable=True)
    phase: Mapped[str] = mapped_column(String(12))
    category: Mapped[str] = mapped_column(String(40), index=True)
    detail: Mapped[dict] = mapped_column(JSON, default=dict)
    pv: Mapped[list] = mapped_column(JSON, default=list)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class EngineCache(Base):
    __tablename__ = "engine_cache"
    key: Mapped[str] = mapped_column(String(160), primary_key=True)
    result: Mapped[dict] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


# ---------------------------------------------------------------- cognitive engine
class ConceptMemory(Base):
    """Spaced-repetition state for one concept (a tactical theme)."""

    __tablename__ = "concept_memory"
    concept: Mapped[str] = mapped_column(String(40), primary_key=True)
    ease: Mapped[float] = mapped_column(Float, default=2.5)
    interval_days: Mapped[float] = mapped_column(Float, default=0.0)
    reps: Mapped[int] = mapped_column(Integer, default=0)
    lapses: Mapped[int] = mapped_column(Integer, default=0)
    due_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, index=True)
    last_reviewed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    learned_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    recall_n: Mapped[int] = mapped_column(Integer, default=0)
    recall_ok: Mapped[int] = mapped_column(Integer, default=0)
    transfer_n: Mapped[int] = mapped_column(Integer, default=0)
    transfer_ok: Mapped[int] = mapped_column(Integer, default=0)


class LoopCycle(Base):
    """One MEASURE → DIAGNOSE → INTERVENE → PRACTICE → REASSESS → ADAPT cycle."""

    __tablename__ = "loop_cycles"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    phase: Mapped[str] = mapped_column(String(20), default="measure")
    started_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    baseline: Mapped[dict] = mapped_column(JSON, default=dict)
    diagnosis: Mapped[dict] = mapped_column(JSON, default=dict)
    reassessment: Mapped[dict] = mapped_column(JSON, default=dict)
    adaptation: Mapped[dict] = mapped_column(JSON, default=dict)
    assignment_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    log: Mapped[list] = mapped_column(JSON, default=list)


class InterventionAssignment(Base):
    __tablename__ = "intervention_assignments"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    cycle_id: Mapped[int | None] = mapped_column(ForeignKey("loop_cycles.id"), nullable=True)
    intervention_key: Mapped[str] = mapped_column(String(40))
    target_category: Mapped[str] = mapped_column(String(40))
    target_theme: Mapped[str | None] = mapped_column(String(40), nullable=True)
    params: Mapped[dict] = mapped_column(JSON, default=dict)
    status: Mapped[str] = mapped_column(String(20), default="active")  # active | completed | abandoned
    started_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    ended_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    exercises_done: Mapped[int] = mapped_column(Integer, default=0)
    exercises_target: Mapped[int] = mapped_column(Integer, default=30)
    pre_metric: Mapped[dict] = mapped_column(JSON, default=dict)
    post_metric: Mapped[dict] = mapped_column(JSON, default=dict)
    improved: Mapped[bool | None] = mapped_column(Boolean, nullable=True)


class InterventionStat(Base):
    """Per-user Beta posterior of 'this intervention improved this error category'."""

    __tablename__ = "intervention_stats"
    intervention_key: Mapped[str] = mapped_column(String(40), primary_key=True)
    target_category: Mapped[str] = mapped_column(String(40), primary_key=True)
    alpha: Mapped[float] = mapped_column(Float, default=1.0)
    beta: Mapped[float] = mapped_column(Float, default=1.0)
    trials: Mapped[int] = mapped_column(Integer, default=0)
    mean_effect: Mapped[float] = mapped_column(Float, default=0.0)


# ---------------------------------------------------------------- plan / openings / misc
class PlanBlock(Base):
    __tablename__ = "plan_blocks"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    day: Mapped[date] = mapped_column(Date, index=True)
    key: Mapped[str] = mapped_column(String(30))
    title: Mapped[str] = mapped_column(String(80))
    minutes: Mapped[int] = mapped_column(Integer)
    completed: Mapped[bool] = mapped_column(Boolean, default=False)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    light_day: Mapped[bool] = mapped_column(Boolean, default=False)


class Repertoire(Base):
    __tablename__ = "repertoires"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(80))
    color: Mapped[str] = mapped_column(String(5))  # white | black
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class RepertoireLine(Base):
    __tablename__ = "repertoire_lines"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    repertoire_id: Mapped[int] = mapped_column(ForeignKey("repertoires.id", ondelete="CASCADE"), index=True)
    name: Mapped[str] = mapped_column(String(120))
    start_fen: Mapped[str] = mapped_column(String(100))
    moves_uci: Mapped[list] = mapped_column(JSON, default=list)
    moves_san: Mapped[list] = mapped_column(JSON, default=list)
    plans: Mapped[str] = mapped_column(Text, default="")  # the user's own notes on plans / structures
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class OpeningDrill(Base):
    __tablename__ = "opening_drills"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    line_id: Mapped[int] = mapped_column(ForeignKey("repertoire_lines.id", ondelete="CASCADE"), index=True)
    ply: Mapped[int] = mapped_column(Integer)
    expected_uci: Mapped[str] = mapped_column(String(8))
    played_uci: Mapped[str] = mapped_column(String(8))
    correct: Mapped[bool] = mapped_column(Boolean)
    ts: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class KV(Base):
    __tablename__ = "kv"
    key: Mapped[str] = mapped_column(String(60), primary_key=True)
    value: Mapped[dict] = mapped_column(JSON, default=dict)
