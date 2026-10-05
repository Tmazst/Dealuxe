"""Database-cutover safety tests that never connect to a live database."""

import os
from contextlib import closing
from pathlib import Path
import sqlite3
import tempfile
import unittest
from unittest.mock import patch

from sqlalchemy.engine import make_url
from sqlalchemy.dialects import mysql
from sqlalchemy import DateTime as SQLAlchemyDateTime

from database import (
    db,
    _is_protected_sqlite_url,
    _mysql_test_database_is_explicitly_disposable,
)
from tools.mysql_migration import (
    MigrationSafetyError,
    _file_sha256,
    _schema_audit,
    _source_engine,
    _sqlite_integrity,
    _target_engine,
)


class MySQLMigrationSafetyTests(unittest.TestCase):
    def test_mysql_datetime_columns_keep_microseconds(self):
        datetime_columns = [
            column
            for table in db.metadata.tables.values()
            for column in table.columns
            if isinstance(column.type, SQLAlchemyDateTime)
        ]
        self.assertGreater(len(datetime_columns), 0)
        self.assertTrue(all(
            column.type.compile(dialect=mysql.dialect()) == 'DATETIME(6)'
            for column in datetime_columns
        ))

    def test_default_sqlite_database_is_protected(self):
        with tempfile.TemporaryDirectory() as directory:
            instance = Path(directory) / 'instance'
            self.assertTrue(_is_protected_sqlite_url(
                make_url('sqlite:///dealuxe_game.db'), instance
            ))
            self.assertFalse(_is_protected_sqlite_url(
                make_url('sqlite:///isolated_test.db'), instance
            ))

    def test_mysql_drop_requires_test_suffix_and_explicit_switch(self):
        url = make_url(
            'mysql+mysqlconnector://user:secret@127.0.0.1/app_test'
        )
        with patch.dict(os.environ, {}, clear=False):
            os.environ.pop('DEALUXE_ALLOW_TEST_DATABASE_DROP', None)
            self.assertFalse(_mysql_test_database_is_explicitly_disposable(url))
        with patch.dict(
            os.environ, {'DEALUXE_ALLOW_TEST_DATABASE_DROP': 'true'}
        ):
            self.assertTrue(_mysql_test_database_is_explicitly_disposable(url))
            self.assertFalse(_mysql_test_database_is_explicitly_disposable(
                make_url('mysql+mysqlconnector://user:secret@127.0.0.1/app')
            ))

    def test_target_confirmation_must_match_without_exposing_credentials(self):
        environment = {
            'DEALUXE_DATABASE_URI':
                'mysql+mysqlconnector://user:secret@127.0.0.1/umshova_dealuxe_3'
        }
        with patch.dict(os.environ, environment):
            with self.assertRaisesRegex(
                MigrationSafetyError, 'does not match'
            ) as caught:
                _target_engine('wrong_database')
        self.assertNotIn('secret', str(caught.exception))

    def test_target_rejects_non_mysql(self):
        with patch.dict(
            os.environ, {'DEALUXE_DATABASE_URI': 'sqlite:///local.db'}
        ):
            with self.assertRaisesRegex(MigrationSafetyError, 'MySQL'):
                _target_engine('local')

    def test_source_is_opened_read_only_and_hash_stays_unchanged(self):
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / 'source.db'
            with closing(sqlite3.connect(source)) as connection:
                connection.execute('CREATE TABLE sample (id INTEGER PRIMARY KEY)')
                connection.execute('INSERT INTO sample (id) VALUES (1)')
                connection.commit()
            before = _file_sha256(source)
            _sqlite_integrity(source)
            _, engine = _source_engine(source)
            try:
                with engine.connect() as connection:
                    count = connection.exec_driver_sql(
                        'SELECT COUNT(*) FROM sample'
                    ).scalar()
                    self.assertEqual(count, 1)
                    with self.assertRaises(Exception):
                        connection.exec_driver_sql(
                            'INSERT INTO sample (id) VALUES (2)'
                        )
            finally:
                engine.dispose()
            self.assertEqual(_file_sha256(source), before)

    def test_schema_audit_rejects_unrelated_source(self):
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / 'source.db'
            with closing(sqlite3.connect(source)) as connection:
                connection.execute('CREATE TABLE sample (id INTEGER PRIMARY KEY)')
                connection.commit()
            _, engine = _source_engine(source)
            try:
                with self.assertRaisesRegex(Exception, 'table sets differ'):
                    _schema_audit(engine)
            finally:
                engine.dispose()


if __name__ == '__main__':
    unittest.main()
