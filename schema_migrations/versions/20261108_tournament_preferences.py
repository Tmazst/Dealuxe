"""Persist tournament starting cards and turn duration."""
from alembic import op
import sqlalchemy as sa

revision = '20261108_tournament_prefs'
down_revision = '20261106_promo_brackets'
branch_labels = None
depends_on = None


def upgrade():
    existing = {c['name'] for c in sa.inspect(op.get_bind()).get_columns('tournaments')}
    for name, default in (('card_count', '6'), ('turn_duration_seconds', '300')):
        if name not in existing:
            op.add_column('tournaments', sa.Column(name, sa.Integer(), nullable=False, server_default=default))


def downgrade():
    raise RuntimeError('Destructive schema downgrade is disabled; use a reviewed forward migration.')
