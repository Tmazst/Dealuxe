"""Create a local uMshova tournament test: one person versus three bots.

Run this only against a local development database while the web app is started
with TOURNAMENT_TEST_BOTS_ENABLED=true.  It creates no external payments and
uses the normal tournament models, bracket builder, match-room creator, and
result progression code.
"""

import argparse
import sys
from datetime import datetime
from pathlib import Path

# Running this file directly makes Python search ``tools/`` first. Add the
# project root explicitly so the application package resolves consistently.
PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app import app
from database import (
    db,
    Player,
    TournamentMatch,
    TournamentParticipant,
    User,
    add_tournament_participant,
    create_tournament_record,
)
from controllers.tournament_controller import (
    _build_bracket,
    _ensure_prize_pool,
    record_tournament_match_result,
)


BOT_NAMES = ('tournament_bot_1', 'tournament_bot_2', 'tournament_bot_3')
TEST_PASSWORD = 'TournamentTest!2026'


def get_or_create_player(username, email, password=TEST_PASSWORD):
    user = User.query.filter_by(username=username).first()
    created = user is None
    if created:
        user = User(username=username, email=email)
        user.set_password(password)
        db.session.add(user)
        db.session.flush()
    if Player.query.filter_by(user_id=user.id).first() is None:
        db.session.add(Player(user_id=user.id, real_balance=1_000.0))
    return user, created


def seed_tournament(manual_username):
    manual, manual_created = get_or_create_player(
        manual_username, f'{manual_username}@local.test'
    )
    bots = []
    for name in BOT_NAMES:
        bot, _ = get_or_create_player(name, f'{name}@local.test')
        bots.append(bot)
    db.session.commit()

    tournament = create_tournament_record(
        creator_id=manual.id,
        tournament_type='standard',
        tournament_name=f'Practice Arena {datetime.utcnow():%d %b %H:%M}',
        entry_fee=10.0,
        max_players=4,
        is_auto_lock=False,
    )
    for user in [manual, *bots]:
        participant = add_tournament_participant(
            tournament.id,
            user.id,
            payment_status='completed',
            paid_amount=tournament.entry_fee,
            payment_method='local-test',
        )
        participant.status = 'registered'
        participant.payment_completed_at = datetime.utcnow()

    tournament.current_player_count = 4
    tournament.prize_pool_amount = 40.0
    tournament.status = 'locked'
    tournament.locked_at = datetime.utcnow()
    tournament.locked_player_count = 4
    _ensure_prize_pool(tournament)
    _build_bracket(tournament)
    db.session.commit()

    # Settle only the bot-vs-bot semi-final, so the manual player immediately
    # has a real scheduled match against one bot. Subsequent manual matches are
    # played in normal GameRooms and progress through the same bracket logic.
    scheduled = TournamentMatch.query.filter_by(
        tournament_id=tournament.id, status='scheduled'
    ).all()
    for match in scheduled:
        if manual.id not in {match.player1_id, match.player2_id}:
            record_tournament_match_result(
                match.id, match.player1_id, match.player2_id,
                win_type='test_bot_simulation', duration_seconds=1,
            )

    next_match = TournamentMatch.query.filter_by(
        tournament_id=tournament.id, status='scheduled'
    ).filter(
        db.or_(
            TournamentMatch.player1_id == manual.id,
            TournamentMatch.player2_id == manual.id,
        )
    ).first()
    if next_match is None:
        raise RuntimeError('No manual-player match was created')

    db.session.commit()
    return tournament, manual_created, next_match


def main():
    parser = argparse.ArgumentParser(description='Seed a local manual-versus-bot tournament.')
    parser.add_argument('--manual-username', default='tournament_tester')
    args = parser.parse_args()

    with app.app_context():
        tournament, manual_created, match = seed_tournament(args.manual_username)

        print('\nLocal tournament test is ready')
        print(f'Tournament: {tournament.tournament_name} ({tournament.tournament_code})')
        print(f'Open:      http://127.0.0.1:5000/tournaments/{tournament.id}/bracket')
        print(f'Next game: match #{match.id} ({match.player1_id} vs {match.player2_id})')
        print(f'Login:     {args.manual_username}')
        if manual_created:
            print(f'Password:  {TEST_PASSWORD}')
        else:
            print('Password:  existing account password (account was reused)')
        print('\nStart the app with TOURNAMENT_TEST_BOTS_ENABLED=true so the reserved')
        print('tournament_bot_* accounts respond automatically during your matches.')


if __name__ == '__main__':
    try:
        main()
    except Exception as error:
        print(f'Unable to create local tournament test: {error}', file=sys.stderr)
        raise
