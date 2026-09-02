"""Version 3 pricing catalogue and universal referral acceptance tests."""

from datetime import datetime
import os
import unittest

os.environ['ENV'] = 'development'

from app import app
from database import (
    Player,
    Referral,
    ReferralCode,
    Tournament,
    TournamentParticipant,
    Transaction,
    TX_REFERRAL_REWARD,
    User,
    create_user,
    db,
)
from pricing.catalog import get_plan, serialize_catalog
from pricing.referrals import (
    attribute_referral,
    get_or_create_referral_code,
    reward_referral_for_completed_tournament,
)
from controllers.tournament_controller import _finalize_tournament


class PricingAndReferralTests(unittest.TestCase):
    def setUp(self):
        app.config.update(TESTING=True, WTF_CSRF_ENABLED=False)
        self.context = app.app_context()
        self.context.push()
        db.drop_all()
        db.create_all()

    def tearDown(self):
        db.session.remove()
        db.drop_all()
        self.context.pop()

    def _user(self, username):
        return create_user(
            username=username,
            email=f'{username}@example.test',
            password='password123',
            phone=f'+2687600{User.query.count():04d}',
        )

    def _completed_tournament(self, user_id, *, tournament_type='standard'):
        creator, _ = self._user(f'creator{Tournament.query.count()}')
        tournament = Tournament(
            tournament_code=f'REF{Tournament.query.count():05d}',
            tournament_name='Referral acceptance tournament',
            tournament_type=tournament_type,
            creator_id=creator.id,
            entry_fee=10.0,
            max_players=64 if tournament_type == 'cup' else 4,
            current_player_count=1,
            status='completed',
            completed_at=datetime.utcnow(),
        )
        db.session.add(tournament)
        db.session.flush()
        db.session.add(TournamentParticipant(
            tournament_id=tournament.id,
            user_id=user_id,
            status='active',
            payment_status='completed',
            payment_method='promotional_credit',
            paid_amount=10.0,
        ))
        db.session.commit()
        return tournament

    def test_catalog_has_the_approved_scalable_four_tier_scope(self):
        catalog = serialize_catalog()
        self.assertFalse(catalog['paid_activation_enabled'])
        self.assertEqual(
            catalog['billing_period_status'],
            'configured_non_renewing_passes',
        )
        self.assertEqual(
            [(row['code'], row['price_emalangeni']) for row in catalog['plans']],
            [('free', 0), ('hybrid', 20), ('hybrid_plus', 40), ('premium', 60)],
        )
        self.assertEqual(get_plan('hybrid').matching_scope, 'joined_bracket')
        self.assertEqual(
            get_plan('hybrid_plus').matching_scope, 'all_open_brackets'
        )
        self.assertIn('openWA', get_plan('premium').features[1])
        self.assertTrue(all(not row['purchasable'] for row in catalog['plans']))

    def test_public_catalog_has_no_checkout_or_activation_surface(self):
        response = app.test_client().get('/api/pricing/plans')
        self.assertEqual(response.status_code, 200)
        payload = response.get_json()
        self.assertFalse(payload['paid_activation_enabled'])
        self.assertNotIn('checkout_url', str(payload))

    def test_every_active_user_can_receive_one_reusable_code(self):
        user, _ = self._user('universal')
        first = get_or_create_referral_code(user.id)
        second = get_or_create_referral_code(user.id)
        self.assertEqual(first.id, second.id)
        self.assertEqual(ReferralCode.query.count(), 1)

    def test_registration_accepts_code_and_creates_attribution(self):
        referrer, _ = self._user('referrer')
        code = get_or_create_referral_code(referrer.id)

        response = app.test_client().post('/api/auth/register', json={
            'username': 'referred',
            'email': 'referred@example.test',
            'phone': '+26876123456',
            'password': 'password123',
            'referral_code': code.code.lower(),
        })

        self.assertEqual(response.status_code, 201, response.get_data(as_text=True))
        referred_id = response.get_json()['user']['id']
        referral = Referral.query.filter_by(referred_user_id=referred_id).one()
        self.assertEqual(referral.referrer_id, referrer.id)
        self.assertEqual(referral.status, 'pending')
        self.assertIsNotNone(ReferralCode.query.filter_by(user_id=referred_id).first())

    def test_invalid_referral_code_rejects_registration_without_partial_user(self):
        response = app.test_client().post('/api/auth/register', json={
            'username': 'invalidcode',
            'email': 'invalidcode@example.test',
            'phone': '+26876999999',
            'password': 'password123',
            'referral_code': 'NOT-A-CODE',
        })
        self.assertEqual(response.status_code, 400)
        self.assertIsNone(User.query.filter_by(username='invalidcode').first())

    def test_first_valid_ordinary_tournament_rewards_referrer_once(self):
        referrer, referrer_player = self._user('rewarder')
        referred, _ = self._user('finisher')
        referrer_player.grant_promotional_credits(5.0)
        code = get_or_create_referral_code(referrer.id)
        referral = attribute_referral(code.code, referred.id)

        cup = self._completed_tournament(referred.id, tournament_type='cup')
        self.assertFalse(reward_referral_for_completed_tournament(referred.id, cup))
        ordinary = self._completed_tournament(referred.id)
        self.assertTrue(
            reward_referral_for_completed_tournament(referred.id, ordinary)
        )
        db.session.commit()

        db.session.refresh(referrer_player)
        db.session.refresh(referral)
        self.assertEqual(referrer_player.promotional_credit_balance, 15.0)
        self.assertEqual(referral.status, 'rewarded')
        self.assertEqual(referral.first_valid_tournament_id, ordinary.id)
        self.assertEqual(referrer.verified_referral_count, 1)
        self.assertEqual(Transaction.query.filter_by(
            transaction_type=TX_REFERRAL_REWARD
        ).count(), 1)

        self.assertFalse(
            reward_referral_for_completed_tournament(referred.id, ordinary)
        )
        db.session.commit()
        self.assertEqual(Transaction.query.filter_by(
            transaction_type=TX_REFERRAL_REWARD
        ).count(), 1)
        self.assertEqual(referrer.verified_referral_count, 1)

    def test_reward_is_independent_of_every_pricing_plan(self):
        referrer, _ = self._user('allplans')
        for plan_code in ('free', 'hybrid', 'hybrid_plus', 'premium'):
            referred, _ = self._user(f'user_{plan_code}')
            code = get_or_create_referral_code(referrer.id)
            attribute_referral(code.code, referred.id)
            tournament = self._completed_tournament(referred.id)
            self.assertTrue(
                reward_referral_for_completed_tournament(referred.id, tournament),
                plan_code,
            )
            db.session.commit()

        self.assertEqual(referrer.verified_referral_count, 4)
        self.assertEqual(Transaction.query.filter_by(
            transaction_type=TX_REFERRAL_REWARD
        ).count(), 4)

    def test_real_tournament_finalization_triggers_the_reward_hook(self):
        referrer, referrer_player = self._user('hookreferrer')
        referred, _ = self._user('hookreferred')
        runner_up, _ = self._user('hookrunner')
        code = get_or_create_referral_code(referrer.id)
        attribute_referral(code.code, referred.id)

        tournament = Tournament(
            tournament_code='REFHOOK',
            tournament_name='Referral hook tournament',
            tournament_type='standard',
            creator_id=referred.id,
            entry_fee=10.0,
            max_players=4,
            current_player_count=2,
            status='in_progress',
            winner_id=referred.id,
            runner_up_id=runner_up.id,
        )
        db.session.add(tournament)
        db.session.flush()
        for user_id in (referred.id, runner_up.id):
            db.session.add(TournamentParticipant(
                tournament_id=tournament.id,
                user_id=user_id,
                status='registered',
                payment_status='completed',
                payment_method='promotional_credit',
                paid_amount=10.0,
            ))
        db.session.flush()

        _finalize_tournament(tournament)
        db.session.commit()

        db.session.refresh(referrer_player)
        self.assertEqual(tournament.status, 'completed')
        self.assertEqual(referrer_player.promotional_credit_balance, 10.0)
        self.assertEqual(Referral.query.one().status, 'rewarded')


if __name__ == '__main__':
    unittest.main()
