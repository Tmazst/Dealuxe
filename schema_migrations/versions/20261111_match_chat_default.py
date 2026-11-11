"""Store the default-on match chat preference on the account."""
from alembic import op
import sqlalchemy as sa

revision = '20261111_match_chat_default'
down_revision = '20261111_mobile_money_number'
branch_labels = None
depends_on = None


def upgrade():
    columns = sa.inspect(op.get_bind()).get_columns('users')
    if not any(column['name'] == 'match_chat_enabled' for column in columns):
        op.add_column('users', sa.Column(
            'match_chat_enabled', sa.Boolean(), nullable=False, server_default=sa.true(),
        ))


def downgrade():
    raise RuntimeError('Destructive schema downgrade is disabled; use a reviewed forward migration.')
