"""Store per-browser Web Push subscriptions for match chat."""

from alembic import op
import sqlalchemy as sa

revision = '20261112_match_chat_push'
down_revision = '20261111_match_chat_default'
branch_labels = None
depends_on = None


def upgrade():
    if sa.inspect(op.get_bind()).has_table('match_chat_push_subscriptions'):
        return
    op.create_table(
        'match_chat_push_subscriptions',
        sa.Column('browser_id', sa.String(32), primary_key=True),
        sa.Column('user_id', sa.Integer(), sa.ForeignKey('users.id', ondelete='CASCADE'), nullable=False),
        sa.Column('endpoint_hash', sa.String(64), nullable=False, unique=True),
        sa.Column('subscription', sa.JSON(), nullable=False),
    )
    op.create_index('ix_match_chat_push_subscriptions_user_id', 'match_chat_push_subscriptions', ['user_id'])


def downgrade():
    raise RuntimeError('Destructive schema downgrade is disabled.')
