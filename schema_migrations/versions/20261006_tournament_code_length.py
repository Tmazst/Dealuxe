"""Allow historical timestamp-based tournament codes.

Revision ID: 20261006_tournament_code_length
Revises: 20261005_cup_event_details
"""

from alembic import op
import sqlalchemy as sa


revision = '20261006_tournament_code_length'
down_revision = '20261005_cup_event_details'
branch_labels = None
depends_on = None


def upgrade():
    op.alter_column(
        'tournaments',
        'tournament_code',
        existing_type=sa.String(length=20),
        type_=sa.String(length=32),
        existing_nullable=False,
    )


def downgrade():
    raise RuntimeError(
        'Destructive schema downgrade is disabled. Deploy a reviewed forward '
        'migration or restore a verified backup.'
    )
