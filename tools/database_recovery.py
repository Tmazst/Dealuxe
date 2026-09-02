"""Fail-closed SQLite backup and side-by-side restore verification.

This module deliberately does not promote a restored file over the active
``instance/dealuxe_game.db`` database.  An operator must stop the application,
review the verification report and explicitly approve that separate step.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import re
import sqlite3


_SAFE_IDENTIFIER = re.compile(r'^[A-Za-z_][A-Za-z0-9_]*$')


class RecoverySafetyError(RuntimeError):
    """Raised when a recovery operation could mutate a protected database."""


class RecoveryVerificationError(RuntimeError):
    """Raised when a backup or restored database fails integrity verification."""


def _resolved(path):
    return Path(path).expanduser().resolve()


def is_protected_database(path):
    """Protect every checkout's conventional live/local database path."""
    candidate = _resolved(path)
    return (
        candidate.name.casefold() == 'dealuxe_game.db'
        and candidate.parent.name.casefold() == 'instance'
    )


def refuse_protected_mutation(path):
    candidate = _resolved(path)
    if is_protected_database(candidate):
        raise RecoverySafetyError(
            'Refusing to overwrite instance/dealuxe_game.db. Restore into a '
            'separate file, verify it, stop the application and require explicit '
            'operator approval before promotion.'
        )
    return candidate


def _read_only_connection(path):
    source = _resolved(path)
    if not source.is_file():
        raise FileNotFoundError('SQLite source database was not found')
    return sqlite3.connect(source.as_uri() + '?mode=ro', uri=True)


def integrity_check(path):
    """Return ``ok`` only when SQLite's full integrity check succeeds."""
    with _read_only_connection(path) as connection:
        rows = connection.execute('PRAGMA integrity_check').fetchall()
    messages = tuple(str(row[0]) for row in rows)
    if messages != ('ok',):
        raise RecoveryVerificationError(
            'SQLite integrity check failed: ' + '; '.join(messages[:5])
        )
    return 'ok'


def create_sqlite_backup(source_path, destination_path):
    """Create and verify a consistent backup without mutating the source."""
    source = _resolved(source_path)
    destination = refuse_protected_mutation(destination_path)
    if source == destination:
        raise RecoverySafetyError('Backup destination must differ from the source')
    if destination.exists():
        raise RecoverySafetyError('Backup destination already exists')
    destination.parent.mkdir(parents=True, exist_ok=True)

    try:
        with _read_only_connection(source) as source_connection:
            with sqlite3.connect(destination) as destination_connection:
                source_connection.backup(destination_connection)
                destination_connection.commit()
        integrity_check(destination)
    except Exception:
        destination.unlink(missing_ok=True)
        raise
    return destination


def restore_sqlite_backup(backup_path, restored_path):
    """Restore into a new side-by-side file and verify SQLite integrity."""
    integrity_check(backup_path)
    return create_sqlite_backup(backup_path, restored_path)


def _safe_table_name(table_name):
    if not isinstance(table_name, str) or not _SAFE_IDENTIFIER.fullmatch(table_name):
        raise ValueError('Unsafe SQLite table name')
    return table_name


def database_manifest(path, critical_tables):
    """Build a privacy-safe manifest of counts and content hashes.

    Row values are hashed inside the process and are never returned.  This lets
    operators compare a restore without placing credentials, contact details,
    captions or other private fields in the recovery report.
    """
    integrity_check(path)
    tables = tuple(dict.fromkeys(_safe_table_name(name) for name in critical_tables))
    manifest = {'integrity': 'ok', 'tables': {}}
    with _read_only_connection(path) as connection:
        existing = {
            row[0] for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type = 'table'"
            ).fetchall()
        }
        for table_name in tables:
            if table_name not in existing:
                raise RecoveryVerificationError(
                    'Critical table is missing: {0}'.format(table_name)
                )
            quoted = '"{0}"'.format(table_name)
            schema_row = connection.execute(
                "SELECT sql FROM sqlite_master WHERE type = 'table' AND name = ?",
                (table_name,),
            ).fetchone()
            rows = connection.execute(
                'SELECT * FROM {0} ORDER BY rowid'.format(quoted)
            ).fetchall()
            digest = hashlib.sha256()
            digest.update((schema_row[0] or '').encode('utf-8'))
            for row in rows:
                digest.update(json.dumps(
                    list(row),
                    default=str,
                    ensure_ascii=False,
                    separators=(',', ':'),
                ).encode('utf-8'))
                digest.update(b'\n')
            manifest['tables'][table_name] = {
                'row_count': len(rows),
                'sha256': digest.hexdigest(),
            }
    return manifest


def verify_restored_manifest(expected, restored):
    """Raise on any critical count/content mismatch without exposing row data."""
    if expected.get('integrity') != 'ok' or restored.get('integrity') != 'ok':
        raise RecoveryVerificationError('Source or restored integrity is not ok')
    expected_tables = expected.get('tables', {})
    restored_tables = restored.get('tables', {})
    if set(expected_tables) != set(restored_tables):
        raise RecoveryVerificationError('Critical table sets do not match')
    mismatches = [
        table_name for table_name in expected_tables
        if expected_tables[table_name] != restored_tables[table_name]
    ]
    if mismatches:
        raise RecoveryVerificationError(
            'Restored critical data does not match: ' + ', '.join(mismatches)
        )
    return True


def main(argv=None):
    """Small operator CLI; restore always targets a new side-by-side file."""
    parser = argparse.ArgumentParser(
        description='Create or verify fail-closed uMshova SQLite recovery files.'
    )
    subparsers = parser.add_subparsers(dest='command', required=True)

    backup_parser = subparsers.add_parser('backup')
    backup_parser.add_argument('source')
    backup_parser.add_argument('destination')

    restore_parser = subparsers.add_parser('restore')
    restore_parser.add_argument('backup')
    restore_parser.add_argument('restored')

    verify_parser = subparsers.add_parser('verify')
    verify_parser.add_argument('database')
    verify_parser.add_argument('tables', nargs='+')

    args = parser.parse_args(argv)
    if args.command == 'backup':
        result = create_sqlite_backup(args.source, args.destination)
        print('Verified backup created: {0}'.format(result))
        return 0
    if args.command == 'restore':
        result = restore_sqlite_backup(args.backup, args.restored)
        print('Verified side-by-side restore created: {0}'.format(result))
        return 0

    manifest = database_manifest(args.database, args.tables)
    print(json.dumps(manifest, indent=2, sort_keys=True))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
