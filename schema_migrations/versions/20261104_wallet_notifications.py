"""Add durable WhatsApp wallet-notification outbox.

Revision ID: 20261104_wallet_notifications
Revises: 20261102_tournament_broadcasts
"""

from alembic import op
import sqlalchemy as sa


revision = '20261104_wallet_notifications'
down_revision = '20261102_tournament_broadcasts'
branch_labels = None
depends_on = None


def upgrade():
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if 'wallet_notifications' not in inspector.get_table_names():
        op.create_table(
            'wallet_notifications',
            sa.Column('id', sa.Integer(), primary_key=True),
            sa.Column('user_id', sa.Integer(), sa.ForeignKey('users.id'), nullable=False),
            sa.Column('wallet_adjustment_id', sa.Integer(), sa.ForeignKey('wallet_adjustments.id'), nullable=True, unique=True),
            sa.Column('transaction_id', sa.Integer(), sa.ForeignKey('transactions.id'), nullable=True, unique=True),
            sa.Column('event_type', sa.String(40), nullable=False),
            sa.Column('event_key', sa.String(160), nullable=False),
            sa.Column('recipient_chat_id', sa.String(64), nullable=False),
            sa.Column('message_body', sa.Text(), nullable=False),
            sa.Column('status', sa.String(20), nullable=False, server_default='pending'),
            sa.Column('attempt_count', sa.Integer(), nullable=False, server_default='0'),
            sa.Column('next_attempt_at', sa.DateTime(), nullable=True),
            sa.Column('openwa_message_id', sa.String(255), nullable=True),
            sa.Column('last_error', sa.String(255), nullable=True),
            sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.func.now()),
            sa.Column('sent_at', sa.DateTime(), nullable=True),
            sa.UniqueConstraint('event_key', name='uq_wallet_notification_event_key'),
        )
    indexes = {item['name'] for item in sa.inspect(bind).get_indexes('wallet_notifications')}
    if 'idx_wallet_notifications_status_next' not in indexes:
        op.create_index('idx_wallet_notifications_status_next', 'wallet_notifications', ['status', 'next_attempt_at'])
    if 'idx_wallet_notifications_user_id' not in indexes:
        op.create_index('idx_wallet_notifications_user_id', 'wallet_notifications', ['user_id'])


def downgrade():
    raise RuntimeError('Destructive schema downgrade is disabled; use a reviewed forward migration.')
