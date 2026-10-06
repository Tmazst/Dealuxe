"""Fail-closed SQLite-to-MySQL bootstrap and privacy-safe verification.

The source SQLite database is opened read-only. The target must be an explicitly
confirmed, empty MySQL database. This utility never drops tables and never logs
credentials or row values.
"""

from __future__ import annotations

import argparse
from contextlib import closing
from datetime import date, datetime, time
from decimal import Decimal
import hashlib
import json
import os
from pathlib import Path
import sqlite3

from alembic import command
from alembic.config import Config
from dotenv import load_dotenv
from sqlalchemy import DateTime as SQLAlchemyDateTime
from sqlalchemy import MetaData, create_engine, inspect, select, text
from sqlalchemy.engine import make_url
from sqlalchemy.pool import NullPool

from database import db


class MigrationSafetyError(RuntimeError):
    """Raised when a migration safety boundary is not satisfied."""


class MigrationVerificationError(RuntimeError):
    """Raised when schemas or migrated content differ."""


def _normalise(value):
    if value is None or isinstance(value, (bool, int, str)):
        return value
    if isinstance(value, float):
        return {'float': format(value, '.17g')}
    if isinstance(value, Decimal):
        return {'decimal': format(value, 'f')}
    if isinstance(value, datetime):
        return {'datetime': value.isoformat(sep=' ', timespec='microseconds')}
    if isinstance(value, (date, time)):
        return {type(value).__name__: value.isoformat()}
    if isinstance(value, (bytes, bytearray, memoryview)):
        return {'bytes_sha256': hashlib.sha256(bytes(value)).hexdigest()}
    return {'text': str(value)}


def _source_engine(source_path):
    source = Path(source_path).expanduser().resolve()
    if not source.is_file():
        raise FileNotFoundError('SQLite migration source was not found')
    uri = 'sqlite:///file:{0}?mode=ro&uri=true'.format(source.as_posix())
    return source, create_engine(uri, poolclass=NullPool)


def _target_engine(expected_database):
    value = str(os.environ.get('DEALUXE_DATABASE_URI') or '').strip()
    if not value:
        raise MigrationSafetyError('DEALUXE_DATABASE_URI is not configured')
    url = make_url(value)
    if url.get_backend_name() != 'mysql':
        raise MigrationSafetyError('The target must use the MySQL backend')
    if not url.database or url.database != expected_database:
        raise MigrationSafetyError(
            'The selected target database does not match --confirm-database'
        )
    if url.database.lower() in {
        'mysql', 'information_schema', 'performance_schema', 'sys',
    }:
        raise MigrationSafetyError('A MySQL system database cannot be a target')
    return create_engine(value, pool_pre_ping=True, pool_recycle=1800)


def _sqlite_integrity(source_path):
    source = Path(source_path).expanduser().resolve()
    with closing(sqlite3.connect(
        source.as_uri() + '?mode=ro', uri=True
    )) as connection:
        integrity = tuple(
            str(row[0]) for row in connection.execute('PRAGMA integrity_check')
        )
        foreign_key_errors = connection.execute(
            'PRAGMA foreign_key_check'
        ).fetchall()
    if integrity != ('ok',):
        raise MigrationVerificationError('SQLite integrity check did not pass')
    if foreign_key_errors:
        raise MigrationVerificationError(
            'SQLite foreign-key verification reported errors'
        )


def _file_sha256(path):
    digest = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b''):
            digest.update(chunk)
    return digest.hexdigest()


def _schema_audit(source_engine, target_engine=None):
    source_inspector = inspect(source_engine)
    model_tables = set(db.metadata.tables)
    source_tables = set(source_inspector.get_table_names())
    if source_tables != model_tables:
        raise MigrationVerificationError(
            'SQLite/model table sets differ (source={0}, model={1})'.format(
                len(source_tables), len(model_tables)
            )
        )
    for table_name in sorted(model_tables):
        source_columns = {
            column['name'] for column in source_inspector.get_columns(table_name)
        }
        model_columns = set(db.metadata.tables[table_name].columns.keys())
        if source_columns != model_columns:
            raise MigrationVerificationError(
                'SQLite/model columns differ for {0}'.format(table_name)
            )
    if target_engine is None:
        return
    target_inspector = inspect(target_engine)
    target_tables = set(target_inspector.get_table_names()) - {'alembic_version'}
    if target_tables != model_tables:
        raise MigrationVerificationError(
            'MySQL/model table sets differ (target={0}, model={1})'.format(
                len(target_tables), len(model_tables)
            )
        )
    for table_name in sorted(model_tables):
        target_columns = {
            column['name'] for column in target_inspector.get_columns(table_name)
        }
        model_columns = set(db.metadata.tables[table_name].columns.keys())
        if target_columns != model_columns:
            raise MigrationVerificationError(
                'MySQL/model columns differ for {0}'.format(table_name)
            )


def _reflect_source(source_engine):
    metadata = MetaData()
    metadata.reflect(bind=source_engine)
    return metadata


def _ordered_rows(connection, table):
    primary_key = list(table.primary_key.columns)
    ordering = primary_key or list(table.columns)
    return connection.execute(select(table).order_by(*ordering))


def _table_manifest(engine, metadata, table_names):
    manifest = {}
    with engine.connect() as connection:
        for table_name in table_names:
            table = metadata.tables[table_name]
            # SQLite ALTER migrations append columns, while the declarative
            # MySQL baseline uses model order. Compare by stable column name so
            # identical records do not fail solely because physical order differs.
            column_names = sorted(column.name for column in table.columns)
            rows = _ordered_rows(connection, table)
            digest = hashlib.sha256()
            count = 0
            for row in rows:
                payload = [
                    _normalise(row._mapping[name]) for name in column_names
                ]
                digest.update(json.dumps(
                    payload,
                    ensure_ascii=False,
                    separators=(',', ':'),
                    sort_keys=True,
                ).encode('utf-8'))
                digest.update(b'\n')
                count += 1
            manifest[table_name] = {
                'row_count': count,
                'sha256': digest.hexdigest(),
            }
    return manifest


def _column_manifest(engine, table):
    digests = {
        column.name: hashlib.sha256() for column in table.columns
    }
    count = 0
    with engine.connect() as connection:
        for row in _ordered_rows(connection, table):
            count += 1
            for column_name, digest in digests.items():
                digest.update(json.dumps(
                    _normalise(row._mapping[column_name]),
                    ensure_ascii=False,
                    separators=(',', ':'),
                    sort_keys=True,
                ).encode('utf-8'))
                digest.update(b'\n')
    return count, {
        column_name: digest.hexdigest()
        for column_name, digest in digests.items()
    }


def _copy_rows(source_engine, target_engine, source_metadata, chunk_size=500):
    copied = {}
    with source_engine.connect() as source_connection:
        with target_engine.begin() as target_connection:
            for model_table in db.metadata.sorted_tables:
                table_name = model_table.name
                source_table = source_metadata.tables[table_name]
                target_table = db.metadata.tables[table_name]
                result = _ordered_rows(source_connection, source_table)
                batch = []
                count = 0
                for row in result:
                    batch.append(dict(row._mapping))
                    if len(batch) >= chunk_size:
                        target_connection.execute(target_table.insert(), batch)
                        count += len(batch)
                        batch = []
                if batch:
                    target_connection.execute(target_table.insert(), batch)
                    count += len(batch)
                copied[table_name] = count
    return copied


def _verify_storage(target_engine):
    query = text(
        "SELECT TABLE_NAME, ENGINE, TABLE_COLLATION "
        "FROM information_schema.TABLES "
        "WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME <> 'alembic_version'"
    )
    with target_engine.connect() as connection:
        rows = connection.execute(query).mappings().all()
    wrong_engine = sorted(
        row['TABLE_NAME'] for row in rows
        if str(row['ENGINE'] or '').lower() != 'innodb'
    )
    wrong_charset = sorted(
        row['TABLE_NAME'] for row in rows
        if not str(row['TABLE_COLLATION'] or '').lower().startswith('utf8mb4_')
    )
    if wrong_engine or wrong_charset:
        raise MigrationVerificationError(
            'MySQL storage verification failed (engine={0}, charset={1})'.format(
                len(wrong_engine), len(wrong_charset)
            )
        )


def repair_datetime_precision(source_engine, target_engine):
    """Repair only MySQL DATETIME precision after a verified first-copy run.

    MySQL's plain DATETIME drops microseconds. This narrowly scoped recovery
    converts model datetime columns to DATETIME(6), then restores those values
    from the read-only source by primary key. It never deletes rows or tables.
    """
    _schema_audit(source_engine, target_engine)
    source_metadata = _reflect_source(source_engine)
    preparer = target_engine.dialect.identifier_preparer

    with target_engine.connect() as connection:
        for model_table in db.metadata.sorted_tables:
            datetime_columns = [
                column for column in model_table.columns
                if isinstance(column.type, SQLAlchemyDateTime)
            ]
            if not datetime_columns:
                continue
            clauses = []
            for column in datetime_columns:
                nullability = 'NULL' if column.nullable else 'NOT NULL'
                clauses.append(
                    'MODIFY COLUMN {0} DATETIME(6) {1}'.format(
                        preparer.quote(column.name), nullability
                    )
                )
            connection.execute(text(
                'ALTER TABLE {0} {1}'.format(
                    preparer.quote(model_table.name), ', '.join(clauses)
                )
            ))
            connection.commit()

    with source_engine.connect() as source_connection:
        with target_engine.begin() as target_connection:
            for model_table in db.metadata.sorted_tables:
                datetime_columns = [
                    column for column in model_table.columns
                    if isinstance(column.type, SQLAlchemyDateTime)
                ]
                if not datetime_columns:
                    continue
                primary_keys = list(model_table.primary_key.columns)
                if not primary_keys:
                    raise MigrationSafetyError(
                        'Datetime repair requires a primary key on {0}'.format(
                            model_table.name
                        )
                    )
                source_table = source_metadata.tables[model_table.name]
                for row in _ordered_rows(source_connection, source_table):
                    values = {
                        column.name: row._mapping[column.name]
                        for column in datetime_columns
                    }
                    condition = None
                    for primary_key in primary_keys:
                        comparison = primary_key == row._mapping[primary_key.name]
                        condition = comparison if condition is None else (
                            condition & comparison
                        )
                    target_connection.execute(
                        model_table.update().where(condition).values(**values)
                    )
    return verify(source_engine, target_engine)


def verify(source_engine, target_engine):
    _schema_audit(source_engine, target_engine)
    source_metadata = _reflect_source(source_engine)
    table_names = [table.name for table in db.metadata.sorted_tables]
    source_manifest = _table_manifest(
        source_engine, source_metadata, table_names
    )
    target_manifest = _table_manifest(
        target_engine, db.metadata, table_names
    )
    mismatches = [
        table_name for table_name in table_names
        if source_manifest[table_name] != target_manifest[table_name]
    ]
    if mismatches:
        mismatch_details = []
        for table_name in mismatches:
            source_count, source_columns = _column_manifest(
                source_engine, source_metadata.tables[table_name]
            )
            target_count, target_columns = _column_manifest(
                target_engine, db.metadata.tables[table_name]
            )
            differing_columns = sorted(
                column_name for column_name in source_columns
                if source_columns[column_name] != target_columns[column_name]
            )
            if source_count != target_count:
                differing_columns.insert(0, 'row_count')
            mismatch_details.append(
                '{0}({1})'.format(table_name, ','.join(differing_columns))
            )
        raise MigrationVerificationError(
            'Migrated data differs in {0} table(s): {1}'.format(
                len(mismatches), '; '.join(mismatch_details)
            )
        )
    _verify_storage(target_engine)
    return source_manifest


def _apply_baseline(project_root):
    config = Config(str(project_root / 'alembic.ini'))
    config.set_main_option('script_location', str(project_root / 'schema_migrations'))
    command.upgrade(config, 'head')


def _assert_empty_migration_schema(target_engine):
    """Allow recovery only from an Alembic-created schema with zero data."""
    inspector = inspect(target_engine)
    existing = set(inspector.get_table_names())
    expected = set(db.metadata.tables) | {'alembic_version'}
    if existing != expected:
        raise MigrationSafetyError(
            'Resume requires exactly the reviewed migration schema '
            '(target={0}, expected={1})'.format(len(existing), len(expected))
        )
    populated = []
    preparer = target_engine.dialect.identifier_preparer
    with target_engine.connect() as connection:
        for table_name in sorted(db.metadata.tables):
            count = connection.execute(text(
                'SELECT COUNT(*) FROM {0}'.format(preparer.quote(table_name))
            )).scalar_one()
            if count:
                populated.append(table_name)
    if populated:
        raise MigrationSafetyError(
            'Resume refused because the target contains application data in: '
            + ', '.join(populated)
        )


def migrate(
    source_path,
    expected_database,
    project_root,
    resume_empty_target=False,
):
    source, source_engine = _source_engine(source_path)
    target_engine = _target_engine(expected_database)
    source_hash_before = _file_sha256(source)
    _sqlite_integrity(source)
    _schema_audit(source_engine)

    existing = set(inspect(target_engine).get_table_names())
    if existing:
        if not resume_empty_target:
            raise MigrationSafetyError(
                'The MySQL target must be empty; found {0} table(s). If this '
                'is a schema-only remainder from a failed first transfer, use '
                '--resume-empty-target.'.format(len(existing))
            )
        _assert_empty_migration_schema(target_engine)

    _apply_baseline(project_root)
    _schema_audit(source_engine, target_engine)
    source_metadata = _reflect_source(source_engine)
    copied = _copy_rows(source_engine, target_engine, source_metadata)
    manifest = verify(source_engine, target_engine)

    source_hash_after = _file_sha256(source)
    if source_hash_before != source_hash_after:
        raise MigrationVerificationError(
            'The SQLite source changed while migration was running'
        )
    return {
        'database': expected_database,
        'table_count': len(manifest),
        'row_count': sum(item['row_count'] for item in manifest.values()),
        'copied_row_count': sum(copied.values()),
        'source_sha256': source_hash_after,
        'verification': 'passed',
    }


def main(argv=None):
    parser = argparse.ArgumentParser(
        description='Bootstrap and verify uMshova MySQL from read-only SQLite.'
    )
    parser.add_argument('--env-file', required=True)
    parser.add_argument('--source', required=True)
    parser.add_argument('--confirm-database', required=True)
    parser.add_argument(
        '--verify-only', action='store_true',
        help='Verify an already migrated target without changing it.',
    )
    parser.add_argument(
        '--repair-datetime-precision', action='store_true',
        help=(
            'Repair a first-copy MySQL DATETIME precision mismatch without '
            'dropping tables, then re-run full verification.'
        ),
    )
    parser.add_argument(
        '--resume-empty-target', action='store_true',
        help=(
            'Resume after a failed first copy only when the reviewed MySQL '
            'schema exists and every application table is empty.'
        ),
    )
    args = parser.parse_args(argv)

    env_file = Path(args.env_file).expanduser().resolve()
    if not env_file.is_file():
        raise FileNotFoundError('The requested environment file was not found')
    load_dotenv(env_file, override=False)
    project_root = Path(__file__).resolve().parents[1]
    source, source_engine = _source_engine(args.source)
    target_engine = _target_engine(args.confirm_database)

    selected_recovery_modes = sum(bool(value) for value in (
        args.verify_only,
        args.repair_datetime_precision,
        args.resume_empty_target,
    ))
    if selected_recovery_modes > 1:
        parser.error(
            '--verify-only, --repair-datetime-precision and '
            '--resume-empty-target are mutually exclusive'
        )
    if args.verify_only:
        _sqlite_integrity(source)
        manifest = verify(source_engine, target_engine)
        report = {
            'database': args.confirm_database,
            'table_count': len(manifest),
            'row_count': sum(item['row_count'] for item in manifest.values()),
            'source_sha256': _file_sha256(source),
            'verification': 'passed',
        }
    elif args.repair_datetime_precision:
        _sqlite_integrity(source)
        source_hash_before = _file_sha256(source)
        manifest = repair_datetime_precision(source_engine, target_engine)
        source_hash_after = _file_sha256(source)
        if source_hash_before != source_hash_after:
            raise MigrationVerificationError(
                'The SQLite source changed while repair was running'
            )
        report = {
            'database': args.confirm_database,
            'table_count': len(manifest),
            'row_count': sum(item['row_count'] for item in manifest.values()),
            'source_sha256': source_hash_after,
            'verification': 'passed',
            'repair': 'datetime_precision',
        }
    else:
        report = migrate(
            source,
            args.confirm_database,
            project_root,
            resume_empty_target=args.resume_empty_target,
        )
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
