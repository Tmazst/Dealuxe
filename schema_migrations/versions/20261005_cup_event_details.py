"""Add public event details for Cup tournaments.

Revision ID: 20261005_cup_event_details
Revises: 20261005_mysql_baseline
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect
from sqlalchemy.dialects import mysql


revision = '20261005_cup_event_details'
down_revision = '20261005_mysql_baseline'
branch_labels = None
depends_on = None


def upgrade():
    bind = op.get_bind()
    existing = {
        column['name'] for column in inspect(bind).get_columns('tournaments')
    }
    datetime_type = sa.DateTime().with_variant(mysql.DATETIME(fsp=6), 'mysql')
    columns = [
        sa.Column('event_start_at', datetime_type, nullable=True),
        sa.Column('event_check_in_at', datetime_type, nullable=True),
        sa.Column('event_venue_name', sa.String(length=160), nullable=True),
        sa.Column('event_venue_address', sa.String(length=255), nullable=True),
        sa.Column('event_public_notes', sa.Text(), nullable=True),
    ]
    for column in columns:
        if column.name not in existing:
            op.add_column('tournaments', column)


def downgrade():
    raise RuntimeError(
        'Destructive schema downgrade is disabled. Deploy a reviewed forward '
        'migration or restore a verified backup.'
    )

