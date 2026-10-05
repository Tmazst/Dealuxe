"""Create the reviewed Version 3.1 application schema on an empty database.

Revision ID: 20261005_mysql_baseline
Revises: none
"""

from alembic import op
from sqlalchemy import inspect

from database import db


revision = '20261005_mysql_baseline'
down_revision = None
branch_labels = None
depends_on = None


def upgrade():
    bind = op.get_bind()
    existing = set(inspect(bind).get_table_names()) - {'alembic_version'}
    if existing:
        raise RuntimeError(
            'The baseline migration requires an empty target database; found: '
            + ', '.join(sorted(existing))
        )
    db.metadata.create_all(bind=bind)


def downgrade():
    raise RuntimeError(
        'Destructive schema downgrade is disabled. Restore a verified backup '
        'or deploy a reviewed forward migration.'
    )

