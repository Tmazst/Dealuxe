"""Allow wallet notifications to reference registration-credit transactions.

Revision ID: 20261104_reg_credit_notify
Revises: 20261104_wallet_notifications
"""

from alembic import op
import sqlalchemy as sa


revision = '20261104_reg_credit_notify'
down_revision = '20261104_wallet_notifications'
branch_labels = None
depends_on = None


def upgrade():
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    columns = {item['name']: item for item in inspector.get_columns('wallet_notifications')}
    if 'transaction_id' not in columns:
        op.add_column(
            'wallet_notifications',
            sa.Column('transaction_id', sa.Integer(), nullable=True),
        )
        op.create_foreign_key(
            'fk_wallet_notifications_transaction_id',
            'wallet_notifications', 'transactions', ['transaction_id'], ['id'],
        )
        op.create_unique_constraint(
            'uq_wallet_notifications_transaction_id',
            'wallet_notifications', ['transaction_id'],
        )
    if not columns.get('wallet_adjustment_id', {}).get('nullable', True):
        op.alter_column(
            'wallet_notifications', 'wallet_adjustment_id',
            existing_type=sa.Integer(), nullable=True,
        )


def downgrade():
    raise RuntimeError('Destructive schema downgrade is disabled; use a reviewed forward migration.')
