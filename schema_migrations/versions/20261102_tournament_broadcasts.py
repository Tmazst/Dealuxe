"""Add durable tournament WhatsApp broadcast outbox.

Revision ID: 20261102_tournament_broadcasts
Revises: 20261101_reg_verify
"""

from alembic import op
import sqlalchemy as sa


revision = '20261102_tournament_broadcasts'
down_revision = '20261101_reg_verify'
branch_labels = None
depends_on = None


def upgrade():
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if 'tournament_broadcasts' not in inspector.get_table_names():
        op.create_table(
            'tournament_broadcasts',
            sa.Column('id', sa.Integer(), primary_key=True),
            sa.Column('tournament_id', sa.Integer(), sa.ForeignKey('tournaments.id'), nullable=False),
            sa.Column('event_type', sa.String(40), nullable=False),
            sa.Column('event_key', sa.String(160), nullable=False),
            sa.Column('message_body', sa.Text(), nullable=False),
            sa.Column('status', sa.String(20), nullable=False, server_default='pending'),
            sa.Column('attempt_count', sa.Integer(), nullable=False, server_default='0'),
            sa.Column('next_attempt_at', sa.DateTime(), nullable=True),
            sa.Column('openwa_message_id', sa.String(255), nullable=True),
            sa.Column('last_error', sa.String(255), nullable=True),
            sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.func.now()),
            sa.Column('sent_at', sa.DateTime(), nullable=True),
            sa.UniqueConstraint('event_key', name='uq_tournament_broadcast_event_key'),
        )
    indexes = {item['name'] for item in sa.inspect(bind).get_indexes('tournament_broadcasts')}
    if 'idx_tournament_broadcasts_status_next' not in indexes:
        op.create_index('idx_tournament_broadcasts_status_next', 'tournament_broadcasts', ['status', 'next_attempt_at'])
    if 'idx_tournament_broadcasts_tournament_id' not in indexes:
        op.create_index('idx_tournament_broadcasts_tournament_id', 'tournament_broadcasts', ['tournament_id'])


def downgrade():
    raise RuntimeError('Destructive schema downgrade is disabled; use a reviewed forward migration.')
