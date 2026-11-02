"""Add short-lived registration verification challenges.

Revision ID: 20261101_reg_verify
Revises: 20261012_cup_seat_allocations
"""

from alembic import op
import sqlalchemy as sa


revision = '20261101_reg_verify'
down_revision = '20261012_cup_seat_allocations'
branch_labels = None
depends_on = None


def upgrade():
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if 'registration_verifications' not in inspector.get_table_names():
        op.create_table(
            'registration_verifications',
            sa.Column('id', sa.Integer(), primary_key=True),
            sa.Column('challenge_token_hash', sa.String(64), nullable=False),
            sa.Column('purpose', sa.String(30), nullable=False, server_default='registration'),
            sa.Column('channel', sa.String(10), nullable=False),
            sa.Column('recipient', sa.String(160), nullable=False),
            sa.Column('code_hash', sa.String(64), nullable=False),
            sa.Column('pending_data', sa.Text(), nullable=False),
            sa.Column('expires_at', sa.DateTime(), nullable=False),
            sa.Column('resend_after', sa.DateTime(), nullable=False),
            sa.Column('attempts', sa.Integer(), nullable=False, server_default='0'),
            sa.Column('resends', sa.Integer(), nullable=False, server_default='0'),
            sa.Column('consumed_at', sa.DateTime(), nullable=True),
            sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.func.now()),
            sa.UniqueConstraint('challenge_token_hash', name='uq_registration_verification_token'),
        )
    indexes = {item['name'] for item in sa.inspect(bind).get_indexes('registration_verifications')}
    if 'idx_registration_verification_expiry' not in indexes:
        op.create_index('idx_registration_verification_expiry', 'registration_verifications', ['expires_at'])


def downgrade():
    raise RuntimeError('Destructive schema downgrade is disabled; use a reviewed forward migration.')
