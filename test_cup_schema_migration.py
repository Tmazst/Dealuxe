import sqlite3
import unittest
from pathlib import Path


class TestCupSchemaMigration(unittest.TestCase):
    def test_migration_preserves_rows_and_enforces_type_specific_capacity(self):
        connection = sqlite3.connect(':memory:')
        connection.executescript("""
            PRAGMA foreign_keys = ON;
            CREATE TABLE users (id INTEGER PRIMARY KEY);
            INSERT INTO users (id) VALUES (1);
            CREATE TABLE tournaments (
                id INTEGER NOT NULL PRIMARY KEY,
                tournament_code VARCHAR(20) NOT NULL UNIQUE,
                tournament_name VARCHAR(255) NOT NULL,
                tournament_type VARCHAR(20) NOT NULL,
                creator_id INTEGER NOT NULL,
                entry_fee FLOAT NOT NULL,
                prize_pool_amount FLOAT NOT NULL,
                max_players INTEGER NOT NULL,
                current_player_count INTEGER NOT NULL,
                status VARCHAR(20) NOT NULL,
                is_auto_lock BOOLEAN,
                locked_player_count INTEGER,
                locked_at DATETIME,
                created_at DATETIME,
                started_at DATETIME,
                completed_at DATETIME,
                finals_match_id INTEGER,
                third_place_match_id INTEGER,
                winner_id INTEGER,
                runner_up_id INTEGER,
                third_place_id INTEGER,
                notes TEXT,
                CHECK (entry_fee >= 0),
                CHECK (max_players IN (4, 8, 16)),
                FOREIGN KEY(creator_id) REFERENCES users (id),
                FOREIGN KEY(winner_id) REFERENCES users (id),
                FOREIGN KEY(runner_up_id) REFERENCES users (id),
                FOREIGN KEY(third_place_id) REFERENCES users (id)
            );
            CREATE TABLE tournament_participants (
                id INTEGER PRIMARY KEY,
                tournament_id INTEGER NOT NULL REFERENCES tournaments(id)
            );
            INSERT INTO tournaments (
                id, tournament_code, tournament_name, tournament_type,
                creator_id, entry_fee, prize_pool_amount, max_players,
                current_player_count, status
            ) VALUES (1, 'TMT-OLD', 'Existing Tournament', 'standard',
                      1, 10, 40, 4, 4, 'completed');
            INSERT INTO tournament_participants (id, tournament_id) VALUES (1, 1);
        """)
        migration = (
            Path(__file__).parent / 'migrations' / '003_allow_64_player_cup.sql'
        ).read_text(encoding='utf-8')
        connection.executescript(migration)

        self.assertEqual(
            connection.execute(
                'SELECT tournament_name FROM tournaments WHERE id = 1'
            ).fetchone()[0],
            'Existing Tournament',
        )
        self.assertEqual(connection.execute('PRAGMA foreign_key_check').fetchall(), [])
        connection.execute("""
            INSERT INTO tournaments (
                id, tournament_code, tournament_name, tournament_type,
                creator_id, entry_fee, prize_pool_amount, max_players,
                current_player_count, status
            ) VALUES (2, 'TMT-CUP', 'Cup', 'cup', 1, 0, 0, 64, 64, 'locked')
        """)
        with self.assertRaises(sqlite3.IntegrityError):
            connection.execute("""
                INSERT INTO tournaments (
                    id, tournament_code, tournament_name, tournament_type,
                    creator_id, entry_fee, prize_pool_amount, max_players,
                    current_player_count, status
                ) VALUES (3, 'TMT-BAD', 'Bad Ordinary', 'standard',
                          1, 0, 0, 64, 64, 'locked')
            """)


if __name__ == '__main__':
    unittest.main()
