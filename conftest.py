"""Pytest safety boundary: never let tests connect to the local app database."""

import os
from pathlib import Path
import tempfile
import uuid


_TEST_DATABASE_PATH = Path(tempfile.gettempdir()) / (
    f'dealuxe_pytest_{os.getpid()}_{uuid.uuid4().hex}.db'
)
os.environ['DEALUXE_DATABASE_URI'] = (
    f"sqlite:///{_TEST_DATABASE_PATH.as_posix()}"
)


def pytest_sessionfinish(session, exitstatus):
    try:
        from app import app
        from database import db

        with app.app_context():
            db.session.remove()
            db.engine.dispose()
        _TEST_DATABASE_PATH.unlink(missing_ok=True)
    except Exception:
        # Cleanup must not hide test results; the OS temp folder remains safe.
        pass
