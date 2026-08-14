"""Create a local uMshova tournament test: one person versus three bots.

CLI twin of the admin "Test arena" UI — both call
``admin.service.create_test_tournament()`` so the behaviour is identical.

Run this only against a local development database while the web app is started
with ``TOURNAMENT_TEST_BOTS_ENABLED=true``. It creates no external payments and
uses the normal tournament models, bracket builder, match-room creator, and
result progression code.
"""

import argparse
import sys
from pathlib import Path

# Running this file directly makes Python search ``tools/`` first. Add the
# project root explicitly so the application package resolves consistently.
PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

# Load environment variables from a .env file if one exists.
try:
    from dotenv import load_dotenv
    load_dotenv(PROJECT_ROOT / '.env')
except Exception:
    pass

from app import app
from admin.service import create_test_tournament


def main():
    parser = argparse.ArgumentParser(description='Seed a local manual-versus-bot tournament.')
    parser.add_argument('--manual-username', default='tournament_tester')
    args = parser.parse_args()

    with app.app_context():
        test = create_test_tournament(manual_username=args.manual_username)

        print('\nLocal tournament test is ready')
        print(f"Tournament: {test['tournament_name']} ({test['tournament_code']})")
        print(f"Open:      http://127.0.0.1:5000{test['bracket_url']}")
        print(f"Next game: match #{test['next_match_id']}")
        print(f"Login:     {test['manual_username']}")
        if test['manual_created']:
            print(f"Password:  {test['manual_password']}")
        else:
            print('Password:  existing account password (account was reused)')
        if not test['bots_enabled']:
            print('\nWARNING: TOURNAMENT_TEST_BOTS_ENABLED is not set — start the app with')
            print('TOURNAMENT_TEST_BOTS_ENABLED=true or matches will stall on the bot turn.')


if __name__ == '__main__':
    try:
        main()
    except Exception as error:
        print(f'Unable to create local tournament test: {error}', file=sys.stderr)
        raise

