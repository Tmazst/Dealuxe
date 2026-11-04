"""Standalone durable tournament-broadcast worker for systemd."""
import signal
import time

from app import app
from database import db
from services.tournament_broadcast_service import process_tournament_broadcasts
from services.wallet_notification_service import process_wallet_notifications


running = True


def _stop(_signum, _frame):
    global running
    running = False


def main():
    signal.signal(signal.SIGTERM, _stop)
    signal.signal(signal.SIGINT, _stop)
    print('[BROADCAST] WhatsApp outbox worker started')
    while running:
        try:
            with app.app_context():
                process_tournament_broadcasts()
                process_wallet_notifications()
                db.session.remove()
        except Exception as exc:
            print(f'[BROADCAST] Worker cycle failed: {type(exc).__name__}')
            try:
                db.session.remove()
            except Exception:
                pass
        time.sleep(5)
    print('[BROADCAST] WhatsApp outbox worker stopped')


if __name__ == '__main__':
    main()
