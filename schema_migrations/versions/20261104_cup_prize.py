"""Add a public display-only prize field for Cup events.

Revision ID: 20261104_cup_prize
Revises: 20261104_reg_credit_notify
"""

from alembic import op
import sqlalchemy as sa


revision = '20261104_cup_prize'
down_revision = '20261104_reg_credit_notify'
branch_labels = None
depends_on = None


def upgrade():
    bind = op.get_bind()
    existing = {
        column['name'] for column in sa.inspect(bind).get_columns('tournaments')
    }
    if 'event_prize_description' not in existing:
        op.add_column(
            'tournaments',
            sa.Column('event_prize_description', sa.String(length=160), nullable=True),
        )


def downgrade():
    raise RuntimeError(
        'Destructive schema downgrade is disabled; use a reviewed forward migration.'
    )
