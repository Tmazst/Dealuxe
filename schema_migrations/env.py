"""Alembic environment for the uMshova Dealuxe application schema."""

from __future__ import annotations

import os
from pathlib import Path

from alembic import context
from dotenv import load_dotenv
from sqlalchemy import engine_from_config, pool
from sqlalchemy.engine import make_url

from database import db


config = context.config
target_metadata = db.metadata

# Match app.py: load the checkout's private .env without overriding values
# supplied by a deployment service or the current shell.
if config.config_file_name:
    load_dotenv(
        Path(config.config_file_name).resolve().parent / '.env',
        override=False,
    )


def _configured_url():
    value = str(os.environ.get('DEALUXE_DATABASE_URI') or '').strip()
    if not value:
        raise RuntimeError('DEALUXE_DATABASE_URI is required for schema migrations')
    url = make_url(value)
    if not url.database:
        raise RuntimeError('The migration URL must select an explicit database')
    return value


def run_migrations_offline():
    url = _configured_url()
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={'paramstyle': 'named'},
        compare_type=True,
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online():
    section = config.get_section(config.config_ini_section) or {}
    section['sqlalchemy.url'] = _configured_url()
    connectable = engine_from_config(
        section,
        prefix='sqlalchemy.',
        poolclass=pool.NullPool,
        pool_pre_ping=True,
    )
    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            compare_type=True,
        )
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
