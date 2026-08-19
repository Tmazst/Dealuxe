"""Create the four browser test players: Chrome, Opera, Firefox and Edge.

All four use the SAME password so they are easy to test with. Run from the
project root once:

    python create_test_players.py [--password BrowserTest!2026]

Idempotent: if an account already exists it is reused (and reported) instead
of being duplicated. Players are funded so they can pay tournament entry fees
(real balance) and play versus-lobby fake games (fake balance).
"""

import argparse
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

try:
    from dotenv import load_dotenv
    load_dotenv(PROJECT_ROOT / '.env')
except Exception:
    pass

from app import app
from database import db, Player, create_user, get_user_by_username

BROWSER_PLAYERS = [
    ('Chrome', 'chrome@dealuxe.test'),
    ('Opera', 'opera@dealuxe.test'),
    ('Firefox', 'firefox@dealuxe.test'),
    ('Edge', 'edge@dealuxe.test'),
]
INITIAL_REAL_BALANCE = 1000.0
INITIAL_FAKE_BALANCE = 500.0


def main():
    parser = argparse.ArgumentParser(
        description='Create the four browser test players (Chrome, Opera, Firefox, Edge).')
    parser.add_argument('--password', default='BrowserTest!2026',
                        help='Shared password for all four test players (default: %(default)s)')
    args = parser.parse_args()

    with app.app_context():
        created, reused = [], []
        for username, email in BROWSER_PLAYERS:
            existing = get_user_by_username(username)
            if existing is not None:
                player = Player.query.filter_by(user_id=existing.id).first()
                if player is None:
                    player = Player(user_id=existing.id)
                    db.session.add(player)
                player.real_balance = max(player.real_balance or 0, INITIAL_REAL_BALANCE)
                db.session.commit()
                reused.append(username)
                continue

            user, player = create_user(username, email, args.password)
            player.real_balance = INITIAL_REAL_BALANCE
            player.fake_balance = INITIAL_FAKE_BALANCE
            db.session.commit()
            created.append(username)

        print('\nBrowser test players ready')
        print('Created: ' + (', '.join(created) or 'none'))
        print('Reused:  ' + (', '.join(reused) or 'none'))
        print('Password (all players): ' + args.password)
        print('\nLogin at http://127.0.0.1:5000/login')


if __name__ == '__main__':
    try:
        main()
    except Exception as error:
        print('Unable to create test players: ' + str(error), file=sys.stderr)
        raise
