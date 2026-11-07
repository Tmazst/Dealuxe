"""Inspect an empty live tournament; apply recovery or reopen it with --reopen."""

import argparse
import os
from pathlib import Path
import sys


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('tournament_id', type=int)
    parser.add_argument('--apply', action='store_true')
    parser.add_argument('--reopen', action='store_true', help='Reopen registration and wait for all seats instead of building matches')
    parser.add_argument('--admin-user-id', type=int)
    parser.add_argument('--list-admins', action='store_true', help='List active administrator IDs without changing the tournament')
    args = parser.parse_args()
    if args.list_admins and args.apply:
        parser.error('Use --list-admins separately from --apply')
    # Loading the maintenance process must not launch schedulers or broadcast workers.
    os.environ['DEALUXE_BROADCAST_WORKER'] = '1'
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    from app import app
    from database import db, Tournament, TournamentBracket, TournamentMatch, TournamentParticipant, User
    from admin.service import force_start, reopen_empty_tournament

    with app.app_context():
        if args.list_admins:
            admins = User.query.filter(
                User.is_active.is_(True),
                db.or_(User.is_admin.is_(True), User.is_super_admin.is_(True)),
            ).order_by(User.id).all()
            if not admins:
                print('No active administrator accounts found. Restore administrator access before recovery.')
            for admin in admins:
                print(f'Administrator ID: {admin.id}; username: {admin.username}')
            return
        tournament = db.session.get(Tournament, args.tournament_id)
        if tournament is None:
            parser.error('Tournament not found')
        brackets = TournamentBracket.query.filter_by(tournament_id=tournament.id).count()
        matches = TournamentMatch.query.filter_by(tournament_id=tournament.id).count()
        players = TournamentParticipant.query.filter_by(
            tournament_id=tournament.id, status='registered').count()
        print(f'Tournament {tournament.id}: {tournament.tournament_name}')
        print(f'Status: {tournament.status}; registered: {players}; bracket slots: {brackets}; matches: {matches}')
        if not args.apply:
            print('Inspection only. To recover, repeat with --apply --admin-user-id YOUR_ADMIN_ID.')
            return
        if tournament.status != 'in_progress' or brackets or matches:
            parser.error('Recovery requires a live tournament with no bracket slots and no matches')
        admin = db.session.get(User, args.admin_user_id) if args.admin_user_id else None
        if not admin or not (admin.is_admin or admin.is_super_admin) or not admin.is_active:
            parser.error(f'Supply an active administrator ID with --admin-user-id. List valid IDs with: python3 tools/recover_empty_tournament.py {args.tournament_id} --list-admins')
        if args.reopen:
            try:
                result = reopen_empty_tournament(tournament.id, admin.id)
            except ValueError as exc:
                parser.error(str(exc))
            print(f"Reopened: {result['registered_players']}/{result['max_players']} seats filled. Existing entries retained; waiting for all seats.")
            return
        if players < 2:
            parser.error('At least two registered players are required')
        force_start(tournament.id, admin.id)
        matches = TournamentMatch.query.filter_by(tournament_id=tournament.id).count()
        print(f'Recovered: {players} players; {matches} ready-to-play matches. Entry payments were not charged again.')


if __name__ == '__main__':
    main()
