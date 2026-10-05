"""Seed an idempotent 16-seat Cup qualification rehearsal.

The default creates fifteen clearly labelled fake qualifiers. Each wins one
completed synthetic four-player promotional tournament and receives a valid
qualification through the normal Cup qualification service. Existing users,
qualifications and genuine records are never deleted or overwritten.
"""

from __future__ import annotations

import argparse
from datetime import datetime, timedelta
import hashlib
import json
from pathlib import Path
import secrets
import sys


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


from database import (
    AdminAuditLog,
    CupQualification,
    Player,
    Tournament,
    TournamentBracket,
    TournamentMatch,
    TournamentParticipant,
    TournamentPrizePool,
    User,
    db,
)
from services.cup_qualification_service import (
    ACTIVE_QUALIFICATION_STATUSES,
    award_cup_qualification,
)


class CupSeedSafetyError(RuntimeError):
    """Raised when the requested rehearsal seed is not safe to apply."""


def _seed_code(event_key, season, index):
    event_hash = hashlib.sha256(event_key.encode('utf-8')).hexdigest()[:6].upper()
    season_suffix = str(season)[-2:]
    return 'CQ{0}{1}{2:02d}'.format(season_suffix, event_hash, index)


def _fake_identity(prefix, index):
    username = '{0}_{1:02d}'.format(prefix, index)
    email = '{0}-{1:02d}@example.test'.format(prefix.replace('_', '-'), index)
    full_name = 'Cup Pilot Qualifier {0:02d}'.format(index)
    return username, email, full_name


def _ensure_fake_users(count, prefix):
    users = []
    created = 0
    for index in range(1, count + 1):
        username, email, full_name = _fake_identity(prefix, index)
        user = User.query.filter_by(username=username).first()
        if user is not None:
            if user.email != email:
                raise CupSeedSafetyError(
                    'Existing username is not the expected rehearsal account: '
                    + username
                )
            if user.player is None:
                db.session.add(Player(user_id=user.id))
        else:
            if User.query.filter_by(email=email).first() is not None:
                raise CupSeedSafetyError(
                    'Expected rehearsal email belongs to another account'
                )
            user = User(
                username=username,
                email=email,
                full_name=full_name,
                country='Eswatini',
                is_active=True,
            )
            user.set_password(secrets.token_urlsafe(32))
            db.session.add(user)
            db.session.flush()
            db.session.add(Player(user_id=user.id))
            created += 1
        users.append(user)
    return users, created


def _add_participant(tournament, user, placement, timestamp):
    participant = TournamentParticipant(
        tournament_id=tournament.id,
        user_id=user.id,
        status='active' if placement in {1, 2, 3} else 'eliminated',
        payment_status='completed',
        paid_amount=10.0,
        payment_method='promotional_credit',
        final_placement=placement if placement in {1, 2, 3} else None,
        prize_awarded=0.0,
        registered_at=timestamp,
        payment_completed_at=timestamp,
        notes='Synthetic Cup qualification rehearsal participant',
    )
    db.session.add(participant)


def _add_completed_match(
    tournament, bracket, player1, player2, winner, loser, timestamp
):
    match = TournamentMatch(
        tournament_id=tournament.id,
        bracket_id=bracket.id,
        player1_id=player1.id,
        player2_id=player2.id,
        status='completed',
        winner_id=winner.id,
        loser_id=loser.id,
        card_count=6,
        bet_amount=0.0,
        started_at=timestamp,
        completed_at=timestamp + timedelta(seconds=30),
        win_type='synthetic_rehearsal',
        duration_seconds=30,
        notes='Synthetic completed match for Cup qualification rehearsal',
    )
    db.session.add(match)
    db.session.flush()
    bracket.match_id = match.id


def _create_completed_four_player_tournament(
    *, code, winner, opponents, index, timestamp, event_key
):
    tournament = Tournament(
        tournament_code=code,
        tournament_name='Cup Qualifier Rehearsal {0:02d}'.format(index),
        tournament_type='standard',
        creator_id=winner.id,
        entry_fee=10.0,
        prize_pool_amount=0.0,
        max_players=4,
        current_player_count=4,
        status='completed',
        is_auto_lock=True,
        locked_player_count=4,
        locked_at=timestamp,
        created_at=timestamp,
        started_at=timestamp + timedelta(seconds=5),
        completed_at=timestamp + timedelta(minutes=3),
        winner_id=winner.id,
        runner_up_id=opponents[0].id,
        third_place_id=opponents[1].id,
        notes=json.dumps({
            'synthetic': True,
            'purpose': 'cup_qualification_rehearsal',
            'event_key': event_key,
            'seed_index': index,
        }, sort_keys=True),
    )
    db.session.add(tournament)
    db.session.flush()

    placements = [winner, opponents[0], opponents[1], opponents[2]]
    for placement, user in enumerate(placements, start=1):
        _add_participant(tournament, user, placement, timestamp)

    semi1 = TournamentBracket(
        tournament_id=tournament.id,
        round_number=1,
        round_name='Semi-Final',
        match_number=1,
        player1_id=winner.id,
        player2_id=opponents[2].id,
        winner_id=winner.id,
        status='completed',
        started_at=timestamp + timedelta(seconds=10),
        completed_at=timestamp + timedelta(seconds=40),
    )
    semi2 = TournamentBracket(
        tournament_id=tournament.id,
        round_number=1,
        round_name='Semi-Final',
        match_number=2,
        player1_id=opponents[0].id,
        player2_id=opponents[1].id,
        winner_id=opponents[0].id,
        status='completed',
        started_at=timestamp + timedelta(seconds=10),
        completed_at=timestamp + timedelta(seconds=40),
    )
    db.session.add_all([semi1, semi2])
    db.session.flush()
    _add_completed_match(
        tournament, semi1, winner, opponents[2], winner, opponents[2],
        timestamp + timedelta(seconds=10),
    )
    _add_completed_match(
        tournament, semi2, opponents[0], opponents[1], opponents[0],
        opponents[1], timestamp + timedelta(seconds=10),
    )

    final = TournamentBracket(
        tournament_id=tournament.id,
        round_number=2,
        round_name='Final',
        match_number=1,
        player1_id=winner.id,
        player2_id=opponents[0].id,
        winner_id=winner.id,
        status='completed',
        started_at=timestamp + timedelta(minutes=1),
        completed_at=timestamp + timedelta(minutes=2),
    )
    third = TournamentBracket(
        tournament_id=tournament.id,
        round_number=3,
        round_name='Third-Place',
        match_number=1,
        player1_id=opponents[1].id,
        player2_id=opponents[2].id,
        winner_id=opponents[1].id,
        status='completed',
        started_at=timestamp + timedelta(minutes=1),
        completed_at=timestamp + timedelta(minutes=2),
    )
    db.session.add_all([final, third])
    db.session.flush()
    _add_completed_match(
        tournament, final, winner, opponents[0], winner, opponents[0],
        timestamp + timedelta(minutes=1),
    )
    _add_completed_match(
        tournament, third, opponents[1], opponents[2], opponents[1],
        opponents[2], timestamp + timedelta(minutes=1),
    )

    for placement, user in enumerate(placements[:3], start=1):
        db.session.add(TournamentPrizePool(
            tournament_id=tournament.id,
            placement=placement,
            prize_percentage=0.0,
            prize_amount=0.0,
            user_id=user.id,
            status='awarded',
            award_date=tournament.completed_at,
            notes='No-cash promotional Cup qualification rehearsal',
            created_at=timestamp,
        ))
    return tournament


def seed_cup_qualifier_rehearsal(
    *, event_key, season, count=15, capacity=16,
    prefix='cup16_qualifier', admin_user_id=None,
):
    if int(count) <= 0 or int(capacity) not in {16, 32, 64}:
        raise CupSeedSafetyError('Invalid rehearsal count or Cup capacity')
    if int(count) >= int(capacity):
        raise CupSeedSafetyError(
            'Seed count must leave at least one seat for an existing qualifier'
        )

    fake_users, created_users = _ensure_fake_users(int(count), prefix)
    active_before = CupQualification.query.filter(
        CupQualification.event_key == event_key,
        CupQualification.status.in_(ACTIVE_QUALIFICATION_STATUSES),
    ).count()
    if active_before > int(capacity):
        raise CupSeedSafetyError('The active roster already exceeds capacity')

    users_needing_seats = [
        user for user in fake_users
        if CupQualification.query.filter(
            CupQualification.user_id == user.id,
            CupQualification.event_key == event_key,
            CupQualification.status.in_(ACTIVE_QUALIFICATION_STATUSES),
        ).first() is None
    ]
    if active_before + len(users_needing_seats) > int(capacity):
        raise CupSeedSafetyError(
            'The seed would exceed the configured Cup capacity'
        )

    created_tournaments = 0
    created_qualifications = 0
    base_time = datetime.utcnow() - timedelta(days=2)
    for offset, winner in enumerate(fake_users):
        index = offset + 1
        code = _seed_code(event_key, season, index)
        tournament = Tournament.query.filter_by(tournament_code=code).first()
        if tournament is None:
            opponents = [
                fake_users[(offset + step) % len(fake_users)]
                for step in (1, 2, 3)
            ]
            tournament = _create_completed_four_player_tournament(
                code=code,
                winner=winner,
                opponents=opponents,
                index=index,
                timestamp=base_time + timedelta(minutes=index * 10),
                event_key=event_key,
            )
            created_tournaments += 1
        elif not (
            tournament.winner_id == winner.id
            and tournament.status == 'completed'
            and tournament.max_players == 4
            and tournament.notes
            and 'cup_qualification_rehearsal' in tournament.notes
        ):
            raise CupSeedSafetyError(
                'Existing tournament code is not the expected rehearsal record'
            )

        source_qualification = CupQualification.query.filter_by(
            source_tournament_id=tournament.id
        ).first()
        if source_qualification is None:
            qualification, _seat_awarded = award_cup_qualification(
                tournament=tournament,
                user_id=winner.id,
                event_key=event_key,
                season=str(season),
                capacity=int(capacity),
            )
            qualification.qualified_at = (
                base_time + timedelta(minutes=index * 10 + 4)
            )
            created_qualifications += 1
        elif source_qualification.user_id != winner.id:
            raise CupSeedSafetyError(
                'Existing source qualification belongs to another user'
            )

    active_after = CupQualification.query.filter(
        CupQualification.event_key == event_key,
        CupQualification.status.in_(ACTIVE_QUALIFICATION_STATUSES),
    ).count()
    if active_after != int(capacity):
        raise CupSeedSafetyError(
            'Expected a full {0}-seat roster, found {1}'.format(
                capacity, active_after
            )
        )

    if admin_user_id and (created_users or created_tournaments or created_qualifications):
        db.session.add(AdminAuditLog(
            admin_user_id=admin_user_id,
            action='cup_qualification.seed_rehearsal',
            entity_type='cup_event',
            summary=(
                'Seeded {0} synthetic four-player Cup qualifier wins'.format(count)
            ),
            details=json.dumps({
                'event_key': event_key,
                'capacity': int(capacity),
                'fake_players': int(count),
                'created_users': created_users,
                'created_tournaments': created_tournaments,
                'created_qualifications': created_qualifications,
            }, sort_keys=True),
        ))

    db.session.commit()
    return {
        'event_key': event_key,
        'capacity': int(capacity),
        'active_qualifiers_before': active_before,
        'active_qualifiers_after': active_after,
        'created_users': created_users,
        'created_tournaments': created_tournaments,
        'created_qualifications': created_qualifications,
        'check_in_status': 'not_checked_in',
        'fake_usernames': [user.username for user in fake_users],
    }


def rename_legacy_qualifier_labels(
    *, event_key, count=15, old_prefix='cup16_winner',
    new_prefix='cup16_qualifier', admin_user_id=None,
):
    """Rename only verified rehearsal accounts with the earlier poor label."""
    renamed = 0
    reused = 0
    usernames = []
    for index in range(1, int(count) + 1):
        old_username, old_email, _old_name = _fake_identity(old_prefix, index)
        new_username, new_email, new_full_name = _fake_identity(new_prefix, index)
        old_user = User.query.filter_by(username=old_username).first()
        new_user = User.query.filter_by(username=new_username).first()
        if old_user is None:
            if new_user is None or new_user.email != new_email:
                raise CupSeedSafetyError(
                    'Expected rehearsal qualifier account is missing'
                )
            user = new_user
            reused += 1
        else:
            if old_user.email != old_email:
                raise CupSeedSafetyError(
                    'Legacy username is not the expected rehearsal account'
                )
            if new_user is not None and new_user.id != old_user.id:
                raise CupSeedSafetyError(
                    'New qualifier username already belongs to another account'
                )
            email_owner = User.query.filter_by(email=new_email).first()
            if email_owner is not None and email_owner.id != old_user.id:
                raise CupSeedSafetyError(
                    'New qualifier email already belongs to another account'
                )
            user = old_user

        qualification = CupQualification.query.filter(
            CupQualification.user_id == user.id,
            CupQualification.event_key == event_key,
            CupQualification.status.in_(ACTIVE_QUALIFICATION_STATUSES),
        ).first()
        source = qualification.source_tournament if qualification else None
        if not (
            qualification
            and source
            and source.status == 'completed'
            and source.max_players == 4
            and source.notes
            and 'cup_qualification_rehearsal' in source.notes
        ):
            raise CupSeedSafetyError(
                'Account is not backed by the expected qualifying tournament'
            )

        if user.username != new_username:
            user.username = new_username
            user.email = new_email
            user.full_name = new_full_name
            renamed += 1
        usernames.append(new_username)

    if admin_user_id and renamed:
        db.session.add(AdminAuditLog(
            admin_user_id=admin_user_id,
            action='cup_qualification.rename_rehearsal_accounts',
            entity_type='cup_event',
            summary='Renamed synthetic Cup accounts from winner to qualifier labels',
            details=json.dumps({
                'event_key': event_key,
                'renamed_accounts': renamed,
                'new_prefix': new_prefix,
            }, sort_keys=True),
        ))
    db.session.commit()
    return {
        'event_key': event_key,
        'renamed_accounts': renamed,
        'reused_accounts': reused,
        'qualifier_usernames': usernames,
    }


def main(argv=None):
    parser = argparse.ArgumentParser(
        description='Seed fifteen completed four-player Cup qualifier wins.'
    )
    parser.add_argument('--confirm-database', required=True)
    parser.add_argument('--confirm-event-key', required=True)
    parser.add_argument('--count', type=int, default=15)
    parser.add_argument('--capacity', type=int, default=16)
    parser.add_argument('--prefix', default='cup16_qualifier')
    parser.add_argument(
        '--rename-legacy-labels', action='store_true',
        help='Rename verified cup16_winner rehearsal accounts as qualifiers.',
    )
    args = parser.parse_args(argv)

    from dotenv import load_dotenv
    load_dotenv(PROJECT_ROOT / '.env', override=False)
    from app import app

    with app.app_context():
        database_url = db.engine.url
        if database_url.get_backend_name() != 'mysql':
            raise CupSeedSafetyError('CLI rehearsal seeding requires MySQL')
        if database_url.database != args.confirm_database:
            raise CupSeedSafetyError('The selected database was not confirmed')
        event_key = str(app.config.get('CUP_EVENT_KEY') or '').strip()
        if not event_key or event_key != args.confirm_event_key:
            raise CupSeedSafetyError('The configured Cup event was not confirmed')
        if not app.config.get('CUP_ENABLED'):
            raise CupSeedSafetyError('CUP_ENABLED must be true')
        if not app.config.get('CUP_QUALIFICATION_ENABLED'):
            raise CupSeedSafetyError('CUP_QUALIFICATION_ENABLED must be true')
        if args.capacity not in tuple(app.config.get('CUP_ALLOWED_CAPACITIES', ())):
            raise CupSeedSafetyError('Requested capacity is not allowed')

        administrator = User.query.filter_by(is_super_admin=True).order_by(User.id).first()
        if args.rename_legacy_labels:
            report = rename_legacy_qualifier_labels(
                event_key=event_key,
                count=args.count,
                admin_user_id=administrator.id if administrator else None,
            )
        else:
            report = seed_cup_qualifier_rehearsal(
                event_key=event_key,
                season=app.config.get('CUP_SEASON'),
                count=args.count,
                capacity=args.capacity,
                prefix=args.prefix,
                admin_user_id=administrator.id if administrator else None,
            )
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
