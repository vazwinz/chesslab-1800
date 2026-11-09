"""Baseline: the schema AURA 0.3.0 created with SQLAlchemy create_all (no migrations back then).

A 0.3.0 database already has exactly these tables, so app/migrate.py does not run this
revision on it: it checks the tables and stamps the database at this revision instead.
Fresh installs run it to create everything.

Revision ID: 0001_baseline_030
Revises:
Create Date: 2026-11-08
"""
from alembic import op
import sqlalchemy as sa


revision = '0001_baseline_030'
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table('concept_memory',
    sa.Column('concept', sa.String(length=40), nullable=False),
    sa.Column('ease', sa.Float(), nullable=False),
    sa.Column('interval_days', sa.Float(), nullable=False),
    sa.Column('reps', sa.Integer(), nullable=False),
    sa.Column('lapses', sa.Integer(), nullable=False),
    sa.Column('due_at', sa.DateTime(), nullable=False),
    sa.Column('last_reviewed_at', sa.DateTime(), nullable=True),
    sa.Column('learned_at', sa.DateTime(), nullable=True),
    sa.Column('recall_n', sa.Integer(), nullable=False),
    sa.Column('recall_ok', sa.Integer(), nullable=False),
    sa.Column('transfer_n', sa.Integer(), nullable=False),
    sa.Column('transfer_ok', sa.Integer(), nullable=False),
    sa.PrimaryKeyConstraint('concept')
    )
    with op.batch_alter_table('concept_memory', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_concept_memory_due_at'), ['due_at'], unique=False)

    op.create_table('engine_cache',
    sa.Column('key', sa.String(length=160), nullable=False),
    sa.Column('result', sa.JSON(), nullable=False),
    sa.Column('created_at', sa.DateTime(), nullable=False),
    sa.PrimaryKeyConstraint('key')
    )
    op.create_table('games',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('fingerprint', sa.String(length=64), nullable=False),
    sa.Column('pgn', sa.Text(), nullable=False),
    sa.Column('white', sa.String(length=80), nullable=False),
    sa.Column('black', sa.String(length=80), nullable=False),
    sa.Column('result', sa.String(length=10), nullable=False),
    sa.Column('played_on', sa.Date(), nullable=True),
    sa.Column('time_control', sa.String(length=30), nullable=False),
    sa.Column('user_color', sa.String(length=5), nullable=True),
    sa.Column('source', sa.String(length=30), nullable=False),
    sa.Column('imported_at', sa.DateTime(), nullable=False),
    sa.Column('analyzed', sa.Boolean(), nullable=False),
    sa.Column('analysis_depth', sa.Integer(), nullable=True),
    sa.Column('metrics', sa.JSON(), nullable=False),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('fingerprint')
    )
    op.create_table('import_jobs',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('source', sa.String(length=500), nullable=False),
    sa.Column('started_at', sa.DateTime(), nullable=False),
    sa.Column('finished_at', sa.DateTime(), nullable=True),
    sa.Column('rows_read', sa.Integer(), nullable=False),
    sa.Column('inserted', sa.Integer(), nullable=False),
    sa.Column('updated', sa.Integer(), nullable=False),
    sa.Column('invalid', sa.Integer(), nullable=False),
    sa.Column('status', sa.String(length=20), nullable=False),
    sa.Column('message', sa.Text(), nullable=False),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_table('intervention_stats',
    sa.Column('intervention_key', sa.String(length=40), nullable=False),
    sa.Column('target_category', sa.String(length=40), nullable=False),
    sa.Column('alpha', sa.Float(), nullable=False),
    sa.Column('beta', sa.Float(), nullable=False),
    sa.Column('trials', sa.Integer(), nullable=False),
    sa.Column('mean_effect', sa.Float(), nullable=False),
    sa.PrimaryKeyConstraint('intervention_key', 'target_category')
    )
    op.create_table('kv',
    sa.Column('key', sa.String(length=60), nullable=False),
    sa.Column('value', sa.JSON(), nullable=False),
    sa.PrimaryKeyConstraint('key')
    )
    op.create_table('loop_cycles',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('phase', sa.String(length=20), nullable=False),
    sa.Column('started_at', sa.DateTime(), nullable=False),
    sa.Column('updated_at', sa.DateTime(), nullable=False),
    sa.Column('finished_at', sa.DateTime(), nullable=True),
    sa.Column('baseline', sa.JSON(), nullable=False),
    sa.Column('diagnosis', sa.JSON(), nullable=False),
    sa.Column('reassessment', sa.JSON(), nullable=False),
    sa.Column('adaptation', sa.JSON(), nullable=False),
    sa.Column('assignment_id', sa.Integer(), nullable=True),
    sa.Column('log', sa.JSON(), nullable=False),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_table('plan_blocks',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('day', sa.Date(), nullable=False),
    sa.Column('key', sa.String(length=30), nullable=False),
    sa.Column('title', sa.String(length=80), nullable=False),
    sa.Column('minutes', sa.Integer(), nullable=False),
    sa.Column('completed', sa.Boolean(), nullable=False),
    sa.Column('completed_at', sa.DateTime(), nullable=True),
    sa.Column('light_day', sa.Boolean(), nullable=False),
    sa.PrimaryKeyConstraint('id')
    )
    with op.batch_alter_table('plan_blocks', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_plan_blocks_day'), ['day'], unique=False)

    op.create_table('puzzles',
    sa.Column('id', sa.String(length=16), nullable=False),
    sa.Column('fen', sa.String(length=100), nullable=False),
    sa.Column('moves', sa.Text(), nullable=False),
    sa.Column('rating', sa.Integer(), nullable=False),
    sa.Column('rating_deviation', sa.Integer(), nullable=False),
    sa.Column('popularity', sa.Integer(), nullable=False),
    sa.Column('nb_plays', sa.Integer(), nullable=False),
    sa.Column('themes', sa.Text(), nullable=False),
    sa.Column('game_url', sa.String(length=200), nullable=False),
    sa.Column('opening_tags', sa.String(length=300), nullable=False),
    sa.Column('solution_len', sa.Integer(), nullable=False),
    sa.Column('rand_key', sa.Float(), nullable=False),
    sa.PrimaryKeyConstraint('id')
    )
    with op.batch_alter_table('puzzles', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_puzzles_rand_key'), ['rand_key'], unique=False)
        batch_op.create_index(batch_op.f('ix_puzzles_rating'), ['rating'], unique=False)
        batch_op.create_index('ix_puzzles_rating_rand', ['rating', 'rand_key'], unique=False)

    op.create_table('repertoires',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('name', sa.String(length=80), nullable=False),
    sa.Column('color', sa.String(length=5), nullable=False),
    sa.Column('created_at', sa.DateTime(), nullable=False),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_table('game_mistakes',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('game_id', sa.Integer(), nullable=False),
    sa.Column('ply', sa.Integer(), nullable=False),
    sa.Column('fen_before', sa.String(length=100), nullable=False),
    sa.Column('move_uci', sa.String(length=8), nullable=False),
    sa.Column('move_san', sa.String(length=12), nullable=False),
    sa.Column('best_uci', sa.String(length=8), nullable=False),
    sa.Column('best_san', sa.String(length=12), nullable=False),
    sa.Column('eval_before_cp', sa.Integer(), nullable=False),
    sa.Column('eval_after_cp', sa.Integer(), nullable=False),
    sa.Column('cp_loss', sa.Integer(), nullable=False),
    sa.Column('win_pct_loss', sa.Float(), nullable=False),
    sa.Column('severity', sa.String(length=12), nullable=False),
    sa.Column('clock_s', sa.Float(), nullable=True),
    sa.Column('think_s', sa.Float(), nullable=True),
    sa.Column('phase', sa.String(length=12), nullable=False),
    sa.Column('category', sa.String(length=40), nullable=False),
    sa.Column('detail', sa.JSON(), nullable=False),
    sa.Column('pv', sa.JSON(), nullable=False),
    sa.Column('created_at', sa.DateTime(), nullable=False),
    sa.ForeignKeyConstraint(['game_id'], ['games.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id')
    )
    with op.batch_alter_table('game_mistakes', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_game_mistakes_category'), ['category'], unique=False)
        batch_op.create_index(batch_op.f('ix_game_mistakes_game_id'), ['game_id'], unique=False)

    op.create_table('intervention_assignments',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('cycle_id', sa.Integer(), nullable=True),
    sa.Column('intervention_key', sa.String(length=40), nullable=False),
    sa.Column('target_category', sa.String(length=40), nullable=False),
    sa.Column('target_theme', sa.String(length=40), nullable=True),
    sa.Column('params', sa.JSON(), nullable=False),
    sa.Column('status', sa.String(length=20), nullable=False),
    sa.Column('started_at', sa.DateTime(), nullable=False),
    sa.Column('ended_at', sa.DateTime(), nullable=True),
    sa.Column('exercises_done', sa.Integer(), nullable=False),
    sa.Column('exercises_target', sa.Integer(), nullable=False),
    sa.Column('pre_metric', sa.JSON(), nullable=False),
    sa.Column('post_metric', sa.JSON(), nullable=False),
    sa.Column('improved', sa.Boolean(), nullable=True),
    sa.ForeignKeyConstraint(['cycle_id'], ['loop_cycles.id'], ),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_table('puzzle_themes',
    sa.Column('puzzle_id', sa.String(length=16), nullable=False),
    sa.Column('theme', sa.String(length=40), nullable=False),
    sa.Column('rating', sa.Integer(), nullable=False),
    sa.Column('rand_key', sa.Float(), nullable=False),
    sa.ForeignKeyConstraint(['puzzle_id'], ['puzzles.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('puzzle_id', 'theme')
    )
    with op.batch_alter_table('puzzle_themes', schema=None) as batch_op:
        batch_op.create_index('ix_theme_rating_rand', ['theme', 'rating', 'rand_key'], unique=False)

    op.create_table('repertoire_lines',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('repertoire_id', sa.Integer(), nullable=False),
    sa.Column('name', sa.String(length=120), nullable=False),
    sa.Column('start_fen', sa.String(length=100), nullable=False),
    sa.Column('moves_uci', sa.JSON(), nullable=False),
    sa.Column('moves_san', sa.JSON(), nullable=False),
    sa.Column('plans', sa.Text(), nullable=False),
    sa.Column('created_at', sa.DateTime(), nullable=False),
    sa.ForeignKeyConstraint(['repertoire_id'], ['repertoires.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id')
    )
    with op.batch_alter_table('repertoire_lines', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_repertoire_lines_repertoire_id'), ['repertoire_id'], unique=False)

    op.create_table('opening_drills',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('line_id', sa.Integer(), nullable=False),
    sa.Column('ply', sa.Integer(), nullable=False),
    sa.Column('expected_uci', sa.String(length=8), nullable=False),
    sa.Column('played_uci', sa.String(length=8), nullable=False),
    sa.Column('correct', sa.Boolean(), nullable=False),
    sa.Column('ts', sa.DateTime(), nullable=False),
    sa.ForeignKeyConstraint(['line_id'], ['repertoire_lines.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id')
    )
    with op.batch_alter_table('opening_drills', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_opening_drills_line_id'), ['line_id'], unique=False)

    op.create_table('training_sessions',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('kind', sa.String(length=30), nullable=False),
    sa.Column('theme', sa.String(length=40), nullable=True),
    sa.Column('started_at', sa.DateTime(), nullable=False),
    sa.Column('last_activity_at', sa.DateTime(), nullable=False),
    sa.Column('ended_at', sa.DateTime(), nullable=True),
    sa.Column('assignment_id', sa.Integer(), nullable=True),
    sa.Column('pressure_level', sa.Integer(), nullable=True),
    sa.Column('break_suggested_at', sa.DateTime(), nullable=True),
    sa.ForeignKeyConstraint(['assignment_id'], ['intervention_assignments.id'], ),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_table('attempts',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('session_id', sa.Integer(), nullable=True),
    sa.Column('exercise_kind', sa.String(length=20), nullable=False),
    sa.Column('puzzle_id', sa.String(length=16), nullable=True),
    sa.Column('game_mistake_id', sa.Integer(), nullable=True),
    sa.Column('mode', sa.String(length=30), nullable=False),
    sa.Column('concept', sa.String(length=40), nullable=True),
    sa.Column('themes', sa.Text(), nullable=False),
    sa.Column('served_at', sa.DateTime(), nullable=False),
    sa.Column('finished_at', sa.DateTime(), nullable=True),
    sa.Column('first_move_ms', sa.Integer(), nullable=True),
    sa.Column('total_ms', sa.Integer(), nullable=True),
    sa.Column('time_limit_ms', sa.Integer(), nullable=True),
    sa.Column('min_think_ms', sa.Integer(), nullable=True),
    sa.Column('timed_out', sa.Boolean(), nullable=False),
    sa.Column('correct', sa.Boolean(), nullable=True),
    sa.Column('fail_ply', sa.Integer(), nullable=True),
    sa.Column('moves_played', sa.JSON(), nullable=False),
    sa.Column('move_times_ms', sa.JSON(), nullable=False),
    sa.Column('expected_move', sa.String(length=8), nullable=True),
    sa.Column('hesitation', sa.JSON(), nullable=False),
    sa.Column('candidates', sa.JSON(), nullable=False),
    sa.Column('candidate_score', sa.Float(), nullable=True),
    sa.Column('puzzle_rating', sa.Integer(), nullable=True),
    sa.Column('solution_len', sa.Integer(), nullable=True),
    sa.Column('user_rating_before', sa.Float(), nullable=True),
    sa.Column('user_rating_after', sa.Float(), nullable=True),
    sa.Column('expected_score', sa.Float(), nullable=True),
    sa.Column('index_in_session', sa.Integer(), nullable=True),
    sa.Column('cp_loss', sa.Integer(), nullable=True),
    sa.Column('error_category', sa.String(length=40), nullable=True),
    sa.Column('error_detail', sa.JSON(), nullable=False),
    sa.Column('assignment_id', sa.Integer(), nullable=True),
    sa.Column('retention_probe', sa.String(length=20), nullable=True),
    sa.Column('pressure_level', sa.Integer(), nullable=True),
    sa.ForeignKeyConstraint(['assignment_id'], ['intervention_assignments.id'], ),
    sa.ForeignKeyConstraint(['game_mistake_id'], ['game_mistakes.id'], ),
    sa.ForeignKeyConstraint(['puzzle_id'], ['puzzles.id'], ),
    sa.ForeignKeyConstraint(['session_id'], ['training_sessions.id'], ),
    sa.PrimaryKeyConstraint('id')
    )
    with op.batch_alter_table('attempts', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_attempts_concept'), ['concept'], unique=False)
        batch_op.create_index(batch_op.f('ix_attempts_error_category'), ['error_category'], unique=False)
        batch_op.create_index(batch_op.f('ix_attempts_puzzle_id'), ['puzzle_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_attempts_served_at'), ['served_at'], unique=False)
        batch_op.create_index(batch_op.f('ix_attempts_session_id'), ['session_id'], unique=False)

    op.create_table('rating_history',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('ts', sa.DateTime(), nullable=False),
    sa.Column('rating', sa.Float(), nullable=False),
    sa.Column('rd', sa.Float(), nullable=False),
    sa.Column('attempt_id', sa.Integer(), nullable=True),
    sa.ForeignKeyConstraint(['attempt_id'], ['attempts.id'], ),
    sa.PrimaryKeyConstraint('id')
    )
    with op.batch_alter_table('rating_history', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_rating_history_ts'), ['ts'], unique=False)



def downgrade() -> None:
    with op.batch_alter_table('rating_history', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_rating_history_ts'))

    op.drop_table('rating_history')
    with op.batch_alter_table('attempts', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_attempts_session_id'))
        batch_op.drop_index(batch_op.f('ix_attempts_served_at'))
        batch_op.drop_index(batch_op.f('ix_attempts_puzzle_id'))
        batch_op.drop_index(batch_op.f('ix_attempts_error_category'))
        batch_op.drop_index(batch_op.f('ix_attempts_concept'))

    op.drop_table('attempts')
    op.drop_table('training_sessions')
    with op.batch_alter_table('opening_drills', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_opening_drills_line_id'))

    op.drop_table('opening_drills')
    with op.batch_alter_table('repertoire_lines', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_repertoire_lines_repertoire_id'))

    op.drop_table('repertoire_lines')
    with op.batch_alter_table('puzzle_themes', schema=None) as batch_op:
        batch_op.drop_index('ix_theme_rating_rand')

    op.drop_table('puzzle_themes')
    op.drop_table('intervention_assignments')
    with op.batch_alter_table('game_mistakes', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_game_mistakes_game_id'))
        batch_op.drop_index(batch_op.f('ix_game_mistakes_category'))

    op.drop_table('game_mistakes')
    op.drop_table('repertoires')
    with op.batch_alter_table('puzzles', schema=None) as batch_op:
        batch_op.drop_index('ix_puzzles_rating_rand')
        batch_op.drop_index(batch_op.f('ix_puzzles_rating'))
        batch_op.drop_index(batch_op.f('ix_puzzles_rand_key'))

    op.drop_table('puzzles')
    with op.batch_alter_table('plan_blocks', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_plan_blocks_day'))

    op.drop_table('plan_blocks')
    op.drop_table('loop_cycles')
    op.drop_table('kv')
    op.drop_table('intervention_stats')
    op.drop_table('import_jobs')
    op.drop_table('games')
    op.drop_table('engine_cache')
    with op.batch_alter_table('concept_memory', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_concept_memory_due_at'))

    op.drop_table('concept_memory')
