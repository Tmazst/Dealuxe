"""V3-0907 isolated backup restore and incident-response rehearsal."""

from datetime import datetime, timedelta
import os
from pathlib import Path
import shutil
import sqlite3
import tempfile
import time
import unittest

os.environ['ENV'] = 'development'

from app import app
from database import (
    AdminAuditLog,
    DiscoveryProfile,
    GameRoom,
    HybridFeatureSetting,
    HybridPilotMetric,
    PlanEntitlement,
    PlanPurchase,
    Player,
    PricingFeatureSetting,
    Referral,
    ReferralCode,
    Tournament,
    TournamentParticipant,
    Transaction,
    TX_REFERRAL_REWARD,
    TX_PLAN_PURCHASE,
    User,
    db,
)
from hybrid.settings import EDITABLE_FLAGS, update_settings
from tools.database_recovery import (
    RecoverySafetyError,
    create_sqlite_backup,
    database_manifest,
    integrity_check,
    restore_sqlite_backup,
    verify_restored_manifest,
)


CRITICAL_TABLES = (
    'users',
    'players',
    'tournaments',
    'tournament_participants',
    'game_rooms',
    'discovery_profiles',
    'hybrid_feature_settings',
    'hybrid_pilot_metrics',
    'admin_audit_logs',
    'transactions',
    'referral_codes',
    'referrals',
    'pricing_feature_settings',
    'plan_purchases',
    'plan_entitlements',
)


class TestDatabaseRecoveryRehearsal(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.original_config = {
            key: app.config.get(key) for key in (
                'TESTING', 'WTF_CSRF_ENABLED', *EDITABLE_FLAGS,
            )
        }
        app.config.update(
            TESTING=True,
            WTF_CSRF_ENABLED=False,
            HYBRID_ENABLED=True,
            HYBRID_PROFILE_ENABLED=True,
            HYBRID_MATCHING_SHADOW_ENABLED=False,
            HYBRID_MATCHING_ENABLED=True,
            HYBRID_CHAT_ENABLED=True,
        )
        cls.context = app.app_context()
        cls.context.push()
        db.drop_all()
        db.create_all()
        cls.exercise_directory = Path(tempfile.mkdtemp(prefix='dealuxe-v3-0907-'))
        cls.source_path = Path(db.engine.url.database).resolve()
        cls.backup_path = cls.exercise_directory / 'rehearsal-backup.db'
        cls.restored_path = cls.exercise_directory / 'rehearsal-restored.db'

        cls.admin = User(
            username='recovery-admin',
            email='recovery-admin@test.com',
            is_admin=True,
        )
        cls.admin.set_password('admin-pw')
        cls.player_user = User(
            username='recovery-player',
            email='recovery-player@test.com',
            phone='+26876000123',
        )
        cls.player_user.set_password('player-pw')
        db.session.add_all([cls.admin, cls.player_user])
        db.session.flush()
        cls.admin_id = cls.admin.id
        cls.player_user_id = cls.player_user.id
        admin_player = Player(
                user_id=cls.admin.id,
                promotional_credit_balance=10,
                promotional_credit_expires_at=datetime.utcnow() + timedelta(days=30),
            )
        referred_player = Player(
                user_id=cls.player_user.id,
                promotional_credit_balance=20,
                promotional_credit_expires_at=datetime.utcnow() + timedelta(days=30),
            )
        db.session.add_all([
            admin_player,
            referred_player,
            DiscoveryProfile(
                user_id=cls.player_user.id,
                is_enabled=True,
                is_visible=True,
                chat_preference_enabled=True,
                intent='selling',
                category='services',
                location='Manzini',
                predefined_caption='offering_services',
                moderation_status='not_required',
            ),
            HybridPilotMetric(
                metric_key='chat_messages_delivered', total_count=12
            ),
        ])
        tournament = Tournament(
            tournament_code='RECOVERY-T1',
            tournament_name='Recovery Rehearsal',
            tournament_type='standard',
            creator_id=cls.admin.id,
            entry_fee=10,
            max_players=4,
            current_player_count=1,
            status='open',
        )
        db.session.add(tournament)
        db.session.flush()
        cls.tournament_id = tournament.id
        referral_code = ReferralCode(
            user_id=cls.admin.id,
            code='RECOVER123',
            is_active=True,
        )
        db.session.add(referral_code)
        db.session.flush()
        reward_transaction = Transaction(
            player_id=admin_player.id,
            transaction_type=TX_REFERRAL_REWARD,
            amount=10,
            balance_type='promotional',
            balance_before=0,
            balance_after=10,
            description='Recovery referral reward',
            tournament_id=tournament.id,
            status='completed',
        )
        db.session.add(reward_transaction)
        db.session.flush()
        plan_transaction = Transaction(
            player_id=referred_player.id,
            transaction_type=TX_PLAN_PURCHASE,
            amount=20,
            balance_type='real',
            balance_before=0,
            balance_after=0,
            external_ref_id='recovery-plan-external-reference',
            description='recovery-plan-gateway-id',
            status='completed',
        )
        db.session.add(plan_transaction)
        db.session.flush()
        plan_purchase = PlanPurchase(
            user_id=cls.player_user.id,
            plan_code='hybrid',
            amount=20,
            duration_days=7,
            status='completed',
            external_ref_id='recovery-plan-external-reference',
            gateway_transaction_id='recovery-plan-gateway-id',
            transaction_id=plan_transaction.id,
            completed_at=datetime.utcnow(),
        )
        db.session.add(plan_purchase)
        db.session.flush()
        db.session.add_all([
            TournamentParticipant(
                tournament_id=tournament.id,
                user_id=cls.player_user.id,
                status='registered',
                payment_status='completed',
                paid_amount=10,
                payment_method='promotional_credit',
            ),
            GameRoom(
                room_code='RECOVERY1',
                player1_id=cls.admin.id,
                player2_id=cls.player_user.id,
                status='in_progress',
                tournament_id=tournament.id,
            ),
            AdminAuditLog(
                admin_user_id=cls.admin.id,
                action='recovery_rehearsal_seeded',
                entity_type='incident_rehearsal',
                summary='Representative recovery data created',
            ),
            Referral(
                referral_code_id=referral_code.id,
                referrer_id=cls.admin.id,
                referred_user_id=cls.player_user.id,
                status='rewarded',
                reward_amount=10,
                first_valid_tournament_id=tournament.id,
                reward_transaction_id=reward_transaction.id,
                qualified_at=datetime.utcnow(),
                rewarded_at=datetime.utcnow(),
            ),
            PlanEntitlement(
                user_id=cls.player_user.id,
                plan_code='hybrid',
                status='active',
                purchase_id=plan_purchase.id,
                starts_at=datetime.utcnow(),
                expires_at=datetime.utcnow() + timedelta(days=7),
            ),
        ])
        for key in EDITABLE_FLAGS:
            db.session.add(HybridFeatureSetting(
                setting_key=key,
                enabled=bool(app.config[key]),
                updated_by=cls.admin.id,
            ))
        db.session.add_all([
            PricingFeatureSetting(
                setting_key='PRICING_ENABLED', enabled=True,
                updated_by=cls.admin.id,
            ),
            PricingFeatureSetting(
                setting_key='PRICING_HYBRID_ENABLED', enabled=True,
                updated_by=cls.admin.id,
            ),
            PricingFeatureSetting(
                setting_key='PRICING_HYBRID_PLUS_ENABLED', enabled=False,
                updated_by=cls.admin.id,
            ),
        ])
        db.session.commit()
        db.session.remove()

    @classmethod
    def tearDownClass(cls):
        db.session.remove()
        db.drop_all()
        cls.context.pop()
        app.config.update(cls.original_config)
        shutil.rmtree(cls.exercise_directory, ignore_errors=True)

    def test_backup_damage_containment_restore_and_verification(self):
        started = time.perf_counter()
        expected = database_manifest(self.source_path, CRITICAL_TABLES)
        create_sqlite_backup(self.source_path, self.backup_path)
        backup_elapsed_ms = (time.perf_counter() - started) * 1000
        self.assertEqual(integrity_check(self.backup_path), 'ok')

        # Incident containment: disable the Hybrid parent switch. Dependency
        # normalization must also disable profiles, matching and chat while the
        # ordinary game page continues to render.
        update_settings({'HYBRID_ENABLED': False}, self.admin_id, app.config)
        db.session.commit()
        self.assertTrue(all(not app.config[key] for key in EDITABLE_FLAGS))
        rows = HybridFeatureSetting.query.all()
        self.assertTrue(all(not row.enabled for row in rows))
        client = app.test_client()
        with client.session_transaction() as session:
            session['user_id'] = self.admin_id
            session['username'] = 'recovery-admin'
        self.assertEqual(client.get('/game/RECOVERY1').status_code, 200)
        self.assertEqual(
            client.get('/api/hybrid/game/RECOVERY1/context').status_code,
            404,
        )
        db.session.remove()

        # Simulate material record loss in the disposable source only.
        with sqlite3.connect(self.source_path) as damaged:
            damaged.execute('DELETE FROM discovery_profiles')
            damaged.execute('DELETE FROM plan_entitlements')
            damaged.execute('DELETE FROM plan_purchases')
            damaged.execute('DELETE FROM pricing_feature_settings')
            damaged.execute('DELETE FROM referrals')
            damaged.execute('DELETE FROM referral_codes')
            damaged.execute('DELETE FROM transactions')
            damaged.execute('DELETE FROM tournament_participants')
            damaged.execute('DELETE FROM tournaments')
            damaged.execute('UPDATE players SET fake_balance = 0')
            damaged.commit()
        damaged_manifest = database_manifest(self.source_path, CRITICAL_TABLES)
        self.assertNotEqual(expected, damaged_manifest)

        restore_started = time.perf_counter()
        restore_sqlite_backup(self.backup_path, self.restored_path)
        restored = database_manifest(self.restored_path, CRITICAL_TABLES)
        self.assertTrue(verify_restored_manifest(expected, restored))
        restore_elapsed_ms = (time.perf_counter() - restore_started) * 1000

        with sqlite3.connect(self.restored_path) as connection:
            self.assertEqual(
                connection.execute(
                    'SELECT fake_balance FROM players WHERE user_id = ?',
                    (self.player_user_id,),
                ).fetchone()[0],
                20,
            )
            self.assertEqual(
                connection.execute(
                    'SELECT COUNT(*) FROM tournament_participants '
                    'WHERE tournament_id = ?',
                    (self.tournament_id,),
                ).fetchone()[0],
                1,
            )
            self.assertEqual(
                connection.execute(
                    'SELECT COUNT(*) FROM discovery_profiles WHERE user_id = ?',
                    (self.player_user_id,),
                ).fetchone()[0],
                1,
            )
            self.assertEqual(
                connection.execute(
                    'SELECT COUNT(*) FROM referrals WHERE referrer_id = ?',
                    (self.admin_id,),
                ).fetchone()[0],
                1,
            )
            self.assertEqual(
                connection.execute(
                    'SELECT COUNT(*) FROM transactions '
                    'WHERE transaction_type = ?',
                    (TX_REFERRAL_REWARD,),
                ).fetchone()[0],
                1,
            )
            self.assertEqual(
                connection.execute(
                    'SELECT COUNT(*) FROM plan_entitlements '
                    'WHERE user_id = ? AND plan_code = ?',
                    (self.player_user_id, 'hybrid'),
                ).fetchone()[0],
                1,
            )

        print(
            '[V3-0907] backup={0:.3f} ms, side-by-side restore+verify={1:.3f} ms, '
            'critical_tables={2}'.format(
                backup_elapsed_ms, restore_elapsed_ms, len(CRITICAL_TABLES)
            )
        )

    def test_restore_refuses_the_protected_live_database_path(self):
        if not self.backup_path.exists():
            create_sqlite_backup(self.source_path, self.backup_path)
        protected = self.exercise_directory / 'instance' / 'dealuxe_game.db'
        with self.assertRaisesRegex(RecoverySafetyError, 'Refusing to overwrite'):
            restore_sqlite_backup(self.backup_path, protected)
        self.assertFalse(protected.exists())


if __name__ == '__main__':
    unittest.main()
