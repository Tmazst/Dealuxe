"""Add empty-Cup seat allocations and audited seat sources.

Revision ID: 20261012_cup_seat_allocations
Revises: 20261006_tournament_code_length
"""

from alembic import op
import sqlalchemy as sa


revision = '20261012_cup_seat_allocations'
down_revision = '20261006_tournament_code_length'
branch_labels = None
depends_on = None


def upgrade():
    for name in (
        'cup_qualifier_seats', 'cup_admin_invite_seats',
        'cup_sponsor_seats', 'cup_testing_seats',
    ):
        op.add_column('tournaments', sa.Column(name, sa.Integer(), nullable=True))
    op.add_column(
        'tournaments', sa.Column('cup_creation_mode', sa.String(30), nullable=True)
    )
    op.alter_column(
        'cup_qualifications', 'source_tournament_id',
        existing_type=sa.Integer(), nullable=True,
    )
    op.add_column(
        'cup_qualifications',
        sa.Column('target_cup_tournament_id', sa.Integer(), nullable=True),
    )
    op.add_column(
        'cup_qualifications',
        sa.Column(
            'seat_source', sa.String(30), nullable=False,
            server_default='bracket_winner',
        ),
    )
    op.add_column(
        'cup_qualifications',
        sa.Column('seat_source_reference', sa.String(120), nullable=True),
    )
    op.add_column(
        'cup_qualifications',
        sa.Column('seat_assigned_by', sa.Integer(), nullable=True),
    )
    op.create_foreign_key(
        'fk_cup_qualifications_target_cup',
        'cup_qualifications', 'tournaments',
        ['target_cup_tournament_id'], ['id'],
    )
    op.create_foreign_key(
        'fk_cup_qualifications_seat_assigner',
        'cup_qualifications', 'users', ['seat_assigned_by'], ['id'],
    )
    op.create_index(
        'idx_cup_qualifications_target_source', 'cup_qualifications',
        ['target_cup_tournament_id', 'seat_source'],
    )


def downgrade():
    raise RuntimeError(
        'Destructive schema downgrade is disabled. Deploy a reviewed forward '
        'migration or restore a verified backup.'
    )
