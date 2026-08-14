#!/usr/bin/env python
"""
uMshova Deluxe — Super Admin CLI

Administrator accounts are managed from the command line ONLY (never through
the web UI). The first super admin is created with the `bootstrap` command;
that account is the only role able to grant or revoke `is_admin` on other
users, and every privileged command re-verifies the super admin's password.

Usage:
    python super_admin_cli.py bootstrap                 # create the first super admin
    python super_admin_cli.py assign <username>         # promote a user to admin (asks super admin password)
    python super_admin_cli.py revoke <username>         # demote an admin (asks super admin password)
    python super_admin_cli.py list                      # list users + roles
    python super_admin_cli.py reset-password <username> # reset a user's password (asks super admin password)

The script talks to the same SQLite database as the Flask app
(instance/dealuxe_game.db).
"""
import argparse
import getpass
import os
import sys

# Allow running directly from the project root (`python super_admin_cli.py`).
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from flask import Flask  # noqa: E402

from database import (  # noqa: E402
    User,
    db,
    create_user,
    get_user_by_username,
    init_db,
)


class SuperAdminError(Exception):
    """Raised for any CLI-level validation/authentication failure."""


def _make_app():
    """Build a minimal Flask app bound to the same DB file as the server."""
    app = Flask(__name__)
    init_db(app)
    return app


def create_super_admin(app, username, email, password, phone=None, full_name=None):
    """Create the first super admin account (fails if one already exists)."""
    with app.app_context():
        if User.query.filter_by(is_super_admin=True).first():
            raise SuperAdminError(
                'A super admin already exists. Use "assign <username>" to grant admin roles.'
            )
        if get_user_by_username(username):
            raise SuperAdminError(f'Username already exists: {username}')

        user, _player = create_user(
            username=username,
            email=email,
            password=password,
            phone=phone,
            full_name=full_name,
        )
        user.is_super_admin = True
        db.session.commit()
        return {
            'id': user.id,
            'username': user.username,
            'email': user.email,
            'is_admin': user.is_admin,
            'is_super_admin': user.is_super_admin,
        }


def _authenticate_super_admin(app, super_username, super_password):
    """Verify the caller is a super admin with the correct password."""
    with app.app_context():
        user = get_user_by_username(super_username)
        if not user or not user.is_super_admin:
            raise SuperAdminError(f'"{super_username}" is not a super admin account.')
        if not user.check_password(super_password):
            raise SuperAdminError('Incorrect super admin password.')
        return user


def assign_admin(app, super_username, super_password, target_username):
    """Promote a user to admin (super admin password required)."""
    _authenticate_super_admin(app, super_username, super_password)
    with app.app_context():
        target = get_user_by_username(target_username)
        if not target:
            raise SuperAdminError(f'User not found: {target_username}')
        target.is_admin = True
        db.session.commit()
        return {
            'id': target.id,
            'username': target.username,
            'is_admin': target.is_admin,
            'is_super_admin': target.is_super_admin,
        }


def revoke_admin(app, super_username, super_password, target_username):
    """Demote an admin (super admin password required)."""
    _authenticate_super_admin(app, super_username, super_password)
    with app.app_context():
        target = get_user_by_username(target_username)
        if not target:
            raise SuperAdminError(f'User not found: {target_username}')
        if not target.is_admin:
            raise SuperAdminError(f'"{target_username}" is not an admin.')
        if target.is_super_admin:
            raise SuperAdminError('Super admin privileges cannot be revoked with this command.')
        target.is_admin = False
        db.session.commit()
        return {
            'id': target.id,
            'username': target.username,
            'is_admin': target.is_admin,
            'is_super_admin': target.is_super_admin,
        }


def reset_password(app, super_username, super_password, target_username, new_password):
    """Reset another user's password (super admin password required)."""
    _authenticate_super_admin(app, super_username, super_password)
    with app.app_context():
        target = get_user_by_username(target_username)
        if not target:
            raise SuperAdminError(f'User not found: {target_username}')
        target.set_password(new_password)
        db.session.commit()
        return {'id': target.id, 'username': target.username}


def list_users(app):
    """Return all users with their roles."""
    with app.app_context():
        users = User.query.order_by(User.id).all()
        return [
            {
                'id': user.id,
                'username': user.username,
                'email': user.email,
                'is_active': user.is_active,
                'is_admin': user.is_admin,
                'is_super_admin': user.is_super_admin,
            }
            for user in users
        ]


# -----------------------------
# INTERACTIVE PROMPTS + ENTRY POINT
# -----------------------------

def _prompt_super_admin():
    username = input('Super admin username: ').strip()
    password = getpass.getpass('Super admin password: ')
    return username, password


def _prompt_password(label):
    password = getpass.getpass(f'{label}: ')
    confirm = getpass.getpass(f'Confirm {label.lower()}: ')
    if password != confirm:
        raise SuperAdminError('Passwords do not match.')
    if len(password) < 6:
        raise SuperAdminError('Password must be at least 6 characters.')
    return password


def main(argv=None):
    parser = argparse.ArgumentParser(
        prog='super_admin_cli.py',
        description='uMshova Deluxe super admin CLI — manage administrator accounts.',
    )
    subparsers = parser.add_subparsers(dest='command', required=True)

    bootstrap = subparsers.add_parser('bootstrap', help='create the first super admin account')
    bootstrap.add_argument('--username', required=True)
    bootstrap.add_argument('--email', required=True)
    bootstrap.add_argument('--phone', default=None)
    bootstrap.add_argument('--full-name', default=None)

    for name in ('assign', 'revoke'):
        cmd = subparsers.add_parser(name, help=f'{name} an admin role')
        cmd.add_argument('target', help='target username')

    reset = subparsers.add_parser('reset-password', help='reset a user password')
    reset.add_argument('target', help='target username')

    subparsers.add_parser('list', help='list users and roles')

    args = parser.parse_args(argv)
    app = _make_app()

    try:
        if args.command == 'bootstrap':
            password = _prompt_password(f'Password for {args.username}')
            user = create_super_admin(
                app, args.username, args.email, password,
                phone=args.phone, full_name=args.full_name,
            )
            print(f"Super admin created: {user['username']} (id={user['id']})")

        elif args.command == 'assign':
            super_username, super_password = _prompt_super_admin()
            user = assign_admin(app, super_username, super_password, args.target)
            print(f"{user['username']} is now an admin.")

        elif args.command == 'revoke':
            super_username, super_password = _prompt_super_admin()
            user = revoke_admin(app, super_username, super_password, args.target)
            print(f"Admin role removed from {user['username']}.")

        elif args.command == 'reset-password':
            super_username, super_password = _prompt_super_admin()
            new_password = _prompt_password(f'New password for {args.target}')
            user = reset_password(app, super_username, super_password, args.target, new_password)
            print(f"Password reset for {user['username']}.")

        elif args.command == 'list':
            users = list_users(app)
            print(f'{"ID":<4} {"Username":<20} {"Admin":<6} {"SuperAdmin":<11} Active')
            for user in users:
                print(
                    f'{user["id"]:<4} {user["username"]:<20} '
                    f'{str(user["is_admin"]):<6} {str(user["is_super_admin"]):<11} '
                    f'{user["is_active"]}'
                )
            print(f'\n{len(users)} user(s) total.')
    except (SuperAdminError, ValueError) as exc:
        print(f'Error: {exc}', file=sys.stderr)
        return 1

    return 0


if __name__ == '__main__':
    sys.exit(main())

