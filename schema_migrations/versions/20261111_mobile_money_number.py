"""Add an optional mobile money number to user accounts."""
from alembic import op
import sqlalchemy as sa

revision = '20261111_mobile_money_number'
down_revision = '20261108_tournament_prefs'
branch_labels = None
depends_on = None


def upgrade():
    columns = sa.inspect(op.get_bind()).get_columns('users')
    if not any(column['name'] == 'mobile_money_number' for column in columns):
        op.add_column('users', sa.Column('mobile_money_number', sa.String(20), nullable=True))


def downgrade():
    raise RuntimeError('Destructive schema downgrade is disabled; use a reviewed forward migration.')
