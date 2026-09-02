"""Universal, idempotent Version 3 referral attribution and rewards."""

from datetime import datetime
import secrets
import string

from database import (
    Player,
    Referral,
    ReferralCode,
    TournamentParticipant,
    Transaction,
    TX_REFERRAL_REWARD,
    User,
    db,
)


REFERRAL_REWARD_AMOUNT = 10.0
_CODE_ALPHABET = string.ascii_uppercase + string.digits


def normalize_referral_code(value):
    return ''.join(str(value or '').strip().upper().split())


def get_or_create_referral_code(user_id, *, commit=True):
    user = db.session.get(User, int(user_id))
    if user is None or not user.is_active:
        raise LookupError('Active user not found')
    existing = ReferralCode.query.filter_by(user_id=user.id).first()
    if existing:
        return existing

    for _ in range(20):
        code = ''.join(secrets.choice(_CODE_ALPHABET) for _ in range(10))
        if ReferralCode.query.filter_by(code=code).first() is None:
            record = ReferralCode(user_id=user.id, code=code, is_active=True)
            db.session.add(record)
            db.session.flush()
            if commit:
                db.session.commit()
            return record
    raise RuntimeError('Unable to allocate a unique referral code')


def find_active_referral_code(value):
    code = normalize_referral_code(value)
    if not code:
        return None
    return ReferralCode.query.filter_by(code=code, is_active=True).first()


def attribute_referral(code_value, referred_user_id, *, commit=True):
    code = find_active_referral_code(code_value)
    if code is None:
        raise ValueError('Referral code is invalid or inactive')
    referred_user_id = int(referred_user_id)
    if code.user_id == referred_user_id:
        raise ValueError('You cannot refer yourself')
    existing = Referral.query.filter_by(referred_user_id=referred_user_id).first()
    if existing:
        if existing.referral_code_id == code.id:
            return existing
        raise ValueError('This account already has a referrer')

    record = Referral(
        referral_code_id=code.id,
        referrer_id=code.user_id,
        referred_user_id=referred_user_id,
        status='pending',
        reward_amount=REFERRAL_REWARD_AMOUNT,
    )
    db.session.add(record)
    db.session.flush()
    if commit:
        db.session.commit()
    return record


def reward_referral_for_completed_tournament(referred_user_id, tournament):
    """Reward once after the referred account's first valid ordinary event."""
    referral = Referral.query.filter_by(
        referred_user_id=int(referred_user_id)
    ).first()
    if referral is None or referral.status == 'rewarded':
        return False
    if (
        tournament is None
        or tournament.status != 'completed'
        or tournament.tournament_type not in {'standard', 'premium', 'deluxe'}
    ):
        return False

    referred = db.session.get(User, referral.referred_user_id)
    referrer = db.session.get(User, referral.referrer_id)
    participation = TournamentParticipant.query.filter_by(
        tournament_id=tournament.id,
        user_id=referral.referred_user_id,
    ).first()
    if not (
        referred and referred.is_active and referred.email
        and referrer and referrer.is_active
        and participation
        and participation.status != 'withdrawn'
        and participation.payment_status == 'completed'
    ):
        return False

    player = Player.query.filter_by(user_id=referrer.id).first()
    if player is None:
        return False

    # Claim the pending row with a compare-and-set update. This keeps two
    # simultaneous tournament-finalization workers from crediting the same
    # referral twice; a failed transaction rolls the claim back with the grant.
    claimed = Referral.query.filter_by(
        id=referral.id, status='pending'
    ).update({'status': 'rewarding'}, synchronize_session=False)
    if claimed != 1:
        return False
    db.session.flush()
    referral.status = 'rewarding'

    amount = float(referral.reward_amount or REFERRAL_REWARD_AMOUNT)
    balance_before = float(player.promotional_credit_balance or 0.0)
    player.grant_promotional_credits(amount, commit=False)
    transaction = Transaction(
        player_id=player.id,
        transaction_type=TX_REFERRAL_REWARD,
        amount=amount,
        balance_type='promotional',
        balance_before=balance_before,
        balance_after=player.promotional_credit_balance,
        description='Referral reward after first valid tournament',
        tournament_id=tournament.id,
        status='completed',
    )
    db.session.add(transaction)
    db.session.flush()

    referral.status = 'rewarded'
    referral.first_valid_tournament_id = tournament.id
    referral.qualified_at = datetime.utcnow()
    referral.rewarded_at = datetime.utcnow()
    referral.reward_transaction_id = transaction.id
    referrer.verified_referral_count = int(referrer.verified_referral_count or 0) + 1
    return True


def referral_summary(user_id):
    code = get_or_create_referral_code(user_id)
    referrals = Referral.query.filter_by(referrer_id=int(user_id)).order_by(
        Referral.created_at.desc()
    ).all()
    return {
        'code': code.code,
        'reward_amount': REFERRAL_REWARD_AMOUNT,
        'total_referrals': len(referrals),
        'rewarded_referrals': sum(1 for row in referrals if row.status == 'rewarded'),
        'pending_referrals': sum(1 for row in referrals if row.status == 'pending'),
    }
