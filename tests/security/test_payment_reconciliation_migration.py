"""Isolated checks for the V3-0119 SQLite migration artifact."""

from pathlib import Path
import sqlite3

import pytest


MIGRATION = (
    Path(__file__).resolve().parents[2]
    / 'migrations'
    / '015_atomic_payment_reconciliation.sql'
)


def _legacy_database(path):
    connection = sqlite3.connect(path)
    connection.execute(
        'CREATE TABLE transactions ('
        'id INTEGER PRIMARY KEY, external_ref_id VARCHAR(64), '
        "status VARCHAR(20) DEFAULT 'pending')"
    )
    return connection


def test_migration_adds_reconciliation_contract_and_unique_indexes(tmp_path):
    connection = _legacy_database(tmp_path / 'legacy_payment.db')
    connection.execute(
        'INSERT INTO transactions (external_ref_id) VALUES (?)',
        ('server-reference-one',),
    )
    connection.commit()
    connection.executescript(MIGRATION.read_text(encoding='utf-8'))

    columns = {
        row[1] for row in connection.execute('PRAGMA table_info(transactions)')
    }
    assert {
        'gateway_transaction_id', 'currency', 'payment_environment',
        'reconciled_at', 'reconciliation_code',
    }.issubset(columns)
    indexes = {
        row[1] for row in connection.execute('PRAGMA index_list(transactions)')
    }
    assert 'uq_transactions_external_ref_id' in indexes
    assert 'uq_transactions_gateway_transaction_id' in indexes
    with pytest.raises(sqlite3.IntegrityError):
        connection.execute(
            'INSERT INTO transactions (external_ref_id) VALUES (?)',
            ('server-reference-one',),
        )
    connection.close()


def test_migration_fails_closed_when_historical_references_are_duplicated(tmp_path):
    connection = _legacy_database(tmp_path / 'duplicate_payment.db')
    connection.executemany(
        'INSERT INTO transactions (external_ref_id) VALUES (?)',
        [('duplicate-reference',), ('duplicate-reference',)],
    )
    connection.commit()
    with pytest.raises(sqlite3.IntegrityError):
        connection.executescript(MIGRATION.read_text(encoding='utf-8'))
    connection.close()
