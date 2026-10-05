"""Privacy-safe Flask/MySQL post-migration smoke check."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path

from dotenv import load_dotenv


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument('--env-file', required=True)
    parser.add_argument('--confirm-database', required=True)
    args = parser.parse_args(argv)

    env_file = Path(args.env_file).expanduser().resolve()
    if not env_file.is_file():
        raise FileNotFoundError('The requested environment file was not found')
    load_dotenv(env_file, override=False)
    os.environ['DATABASE_SCHEMA_MODE'] = 'verify'

    from app import app
    from database import Tournament, User, db

    with app.app_context():
        url = db.engine.url
        if url.get_backend_name() != 'mysql':
            raise RuntimeError('The smoke check is not connected to MySQL')
        if url.database != args.confirm_database:
            raise RuntimeError('The connected database was not explicitly confirmed')
        counts = {
            'users': db.session.query(User).count(),
            'tournaments': db.session.query(Tournament).count(),
        }
        try:
            db.drop_all()
        except RuntimeError:
            drop_guard = 'passed'
        else:
            raise RuntimeError('The MySQL drop safeguard did not block cleanup')

    with app.test_client() as client:
        login_response = client.get('/login')
    if login_response.status_code != 200:
        raise RuntimeError('The login page smoke check failed')

    print(json.dumps({
        'backend': 'mysql',
        'database': args.confirm_database,
        'drop_guard': drop_guard,
        'login_status': login_response.status_code,
        'record_counts': counts,
        'schema_mode': 'verify',
    }, indent=2, sort_keys=True))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())

