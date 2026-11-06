"""Persist admin promotional bracket identity and payout policy."""
from alembic import op
import sqlalchemy as sa

revision = '20261106_promo_brackets'
down_revision = '20261104_cup_prize'
branch_labels = None
depends_on = None


def upgrade():
    existing = {c['name'] for c in sa.inspect(op.get_bind()).get_columns('tournaments')}
    for name in ('is_promotional', 'promotional_wallet_payouts'):
        if name not in existing:
            op.add_column('tournaments', sa.Column(name, sa.Boolean(), nullable=False, server_default=sa.false()))


def downgrade():
    raise RuntimeError('Destructive schema downgrade is disabled; use a reviewed forward migration.')
