"""Isolated regression coverage for the 16-seat Cup rehearsal seed."""

import unittest

from flask import Flask

from database import (
    CupQualification,
    Player,
    Tournament,
    TournamentBracket,
    TournamentMatch,
    TournamentParticipant,
    User,
    db,
)
from services.cup_qualification_service import award_cup_qualification
from tools.seed_cup_qualifiers import (
    rename_legacy_qualifier_labels,
    seed_cup_qualifier_rehearsal,
)


class CupQualifierSeedTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = Flask(__name__)
        cls.app.config.update(
            TESTING=True,
            SQLALCHEMY_DATABASE_URI='sqlite:///:memory:',
            SQLALCHEMY_TRACK_MODIFICATIONS=False,
        )
        db.init_app(cls.app)
        cls.context = cls.app.app_context()
        cls.context.push()
        db.create_all()

    @classmethod
    def tearDownClass(cls):
        db.session.remove()
        db.drop_all()
        cls.context.pop()

    def setUp(self):
        for table in reversed(db.metadata.sorted_tables):
            db.session.execute(table.delete())
        db.session.commit()

        existing = User(
            username='existing_qualifier',
            email='existing-qualifier@example.test',
            is_active=True,
        )
        existing.set_password('isolated-test-password')
        db.session.add(existing)
        db.session.flush()
        db.session.add(Player(user_id=existing.id))
        source = Tournament(
            tournament_code='EXISTING-Q',
            tournament_name='Existing qualifier',
            tournament_type='standard',
            creator_id=existing.id,
            entry_fee=10.0,
            prize_pool_amount=0.0,
            max_players=4,
            current_player_count=4,
            status='completed',
            winner_id=existing.id,
        )
        db.session.add(source)
        db.session.flush()
        award_cup_qualification(
            source, existing.id, 'umshova-cup-pilot', '2026', capacity=16
        )
        db.session.commit()

    def test_creates_fifteen_qualifiers_and_full_roster_idempotently(self):
        report = seed_cup_qualifier_rehearsal(
            event_key='umshova-cup-pilot',
            season='2026',
            count=15,
            capacity=16,
            prefix='cup16_qualifier',
        )
        self.assertEqual(report['created_users'], 15)
        self.assertEqual(report['created_tournaments'], 15)
        self.assertEqual(report['created_qualifications'], 15)
        self.assertEqual(report['active_qualifiers_after'], 16)
        self.assertEqual(report['check_in_status'], 'not_checked_in')

        fake_users = User.query.filter(
            User.username.like('cup16_qualifier_%')
        ).all()
        self.assertEqual(len(fake_users), 15)
        self.assertTrue(all(user.email.endswith('@example.test') for user in fake_users))
        self.assertEqual(Tournament.query.count(), 16)
        self.assertEqual(CupQualification.query.count(), 16)

    def test_renames_only_verified_legacy_rehearsal_accounts(self):
        seed_cup_qualifier_rehearsal(
            event_key='umshova-cup-pilot',
            season='2026',
            count=15,
            capacity=16,
            prefix='cup16_winner',
        )
        report = rename_legacy_qualifier_labels(
            event_key='umshova-cup-pilot', count=15
        )
        self.assertEqual(report['renamed_accounts'], 15)
        self.assertEqual(
            User.query.filter(User.username.like('cup16_winner_%')).count(), 0
        )
        self.assertEqual(
            User.query.filter(User.username.like('cup16_qualifier_%')).count(), 15
        )
        self.assertTrue(all(
            user.full_name.startswith('Cup Pilot Qualifier ')
            for user in User.query.filter(
                User.username.like('cup16_qualifier_%')
            ).all()
        ))
        repeated = rename_legacy_qualifier_labels(
            event_key='umshova-cup-pilot', count=15
        )
        self.assertEqual(repeated['renamed_accounts'], 0)
        self.assertEqual(repeated['reused_accounts'], 15)

        synthetic = Tournament.query.filter(
            Tournament.tournament_code != 'EXISTING-Q'
        ).all()
        for tournament in synthetic:
            self.assertEqual(tournament.status, 'completed')
            self.assertEqual(tournament.max_players, 4)
            self.assertEqual(
                TournamentParticipant.query.filter_by(
                    tournament_id=tournament.id
                ).count(),
                4,
            )
            self.assertEqual(
                TournamentBracket.query.filter_by(
                    tournament_id=tournament.id
                ).count(),
                4,
            )
            self.assertEqual(
                TournamentMatch.query.filter_by(
                    tournament_id=tournament.id
                ).count(),
                4,
            )

        repeated = seed_cup_qualifier_rehearsal(
            event_key='umshova-cup-pilot',
            season='2026',
            count=15,
            capacity=16,
            prefix='cup16_qualifier',
        )
        self.assertEqual(repeated['created_users'], 0)
        self.assertEqual(repeated['created_tournaments'], 0)
        self.assertEqual(repeated['created_qualifications'], 0)
        self.assertEqual(repeated['active_qualifiers_after'], 16)
        self.assertEqual(Tournament.query.count(), 16)
        self.assertEqual(CupQualification.query.count(), 16)


if __name__ == '__main__':
    unittest.main()
