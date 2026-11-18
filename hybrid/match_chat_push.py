"""Opt-in browser push for match chat and announcements."""

import hashlib
import json
import os
import re
import uuid
from urllib.parse import urlsplit

import requests
from flask import Blueprint, abort, after_this_request, current_app, jsonify, make_response, request, session
from sqlalchemy.exc import IntegrityError

from database import MatchChatPushSubscription, User, db


push_bp = Blueprint('match_chat_push', __name__)
_BROWSER_COOKIE = 'umshova_push_browser'
_PROVIDERS = {'fcm.googleapis.com', 'updates.push.services.mozilla.com', 'web.push.apple.com'}
_PROVIDER_SUFFIXES = ('.push.apple.com', '.notify.windows.com')


def configure_match_chat_push(app):
    for name in ('PUBLIC_KEY', 'PRIVATE_KEY', 'SUBJECT'):
        setting = 'MATCH_CHAT_PUSH_' + name
        app.config[setting] = os.environ.get(setting, '').strip()
    app.register_blueprint(push_bp)


def push_enabled(config):
    return all(config.get('MATCH_CHAT_PUSH_' + name) for name in ('PUBLIC_KEY', 'PRIVATE_KEY', 'SUBJECT'))


def _validated_subscription(data):
    if not isinstance(data, dict):
        raise ValueError
    endpoint = data.get('endpoint')
    keys = data.get('keys')
    if (not isinstance(endpoint, str) or len(endpoint) > 2048 or
            not re.fullmatch(r'https://[^\s\\]+', endpoint) or not isinstance(keys, dict)):
        raise ValueError
    target = urlsplit(endpoint)
    host = target.hostname or ''
    if (target.netloc != host or target.fragment or not target.path or
            not (host in _PROVIDERS or host.endswith(_PROVIDER_SUFFIXES))):
        raise ValueError
    for field, length in (('auth', 22), ('p256dh', 87)):
        if not isinstance(keys.get(field), str) or not re.fullmatch(r'[\w-]{%d}' % length, keys[field], re.ASCII):
            raise ValueError
    return {'endpoint': endpoint, 'keys': {field: keys[field] for field in ('auth', 'p256dh')}}


def _browser_id():
    value = request.cookies.get(_BROWSER_COOKIE) or session.get('match_chat_push_browser')
    return value if value and re.fullmatch(r'[0-9a-f]{32}', value) else None


def _remember_browser(response, browser_id):
    response.set_cookie(
        _BROWSER_COOKIE, browser_id, max_age=365 * 24 * 60 * 60,
        httponly=True, secure=request.is_secure or current_app.config['SESSION_COOKIE_SECURE'],
        samesite='Lax',
    )
    session.pop('match_chat_push_browser', None)
    return response


def preserve_legacy_push_on_logout():
    browser_id = _browser_id()
    if browser_id and not request.cookies.get(_BROWSER_COOKIE):
        after_this_request(lambda response: _remember_browser(response, browser_id))


def detach_push_on_account_switch(user_id):
    browser_id = _browser_id()
    if browser_id and MatchChatPushSubscription.query.filter(
        MatchChatPushSubscription.browser_id == browser_id,
        MatchChatPushSubscription.user_id != user_id,
    ).delete():
        db.session.commit()


@push_bp.route('/api/match-chat/push', methods=['GET', 'POST', 'DELETE'])
def browser_push():
    user_id = session.get('user_id')
    if not user_id:
        abort(401)
    user = db.session.get(User, user_id)
    if not user or not user.is_active:
        abort(403)

    browser_id = _browser_id()
    row = (
        MatchChatPushSubscription.query.filter_by(browser_id=browser_id, user_id=user_id).first()
        if browser_id else None
    )
    if request.method == 'DELETE':
        if row:
            db.session.delete(row)
            db.session.commit()
        session.pop('match_chat_push_browser', None)
        response = make_response('', 204)
        response.delete_cookie(_BROWSER_COOKIE)
        return response

    config = current_app.config
    if request.method == 'GET':
        response = jsonify(
            public_key=config['MATCH_CHAT_PUSH_PUBLIC_KEY'] if push_enabled(config) else None,
            subscribed=row is not None,
            endpoint_hash=row.endpoint_hash if row else None,
        )
        response.cache_control.no_store = True
        return _remember_browser(response, row.browser_id) if row else response
    if not push_enabled(config):
        abort(503)
    try:
        subscription = _validated_subscription(request.get_json(silent=True))
    except ValueError:
        abort(400)
    endpoint_hash = hashlib.sha256(subscription['endpoint'].encode()).hexdigest()
    if row is None:
        existing = MatchChatPushSubscription.query.filter_by(endpoint_hash=endpoint_hash).first()
        if existing and (existing.user_id != user_id or existing.subscription != subscription):
            abort(409)
        row = existing or MatchChatPushSubscription(browser_id=uuid.uuid4().hex, user_id=user_id)
    row.subscription = subscription
    row.endpoint_hash = endpoint_hash
    db.session.add(row)
    try:
        db.session.commit()
    except IntegrityError:
        db.session.rollback()
        abort(409)
    return _remember_browser(make_response('', 204), row.browser_id)


class _PushTransport(requests.Session):
    def request(self, method, url, **kwargs):
        kwargs['allow_redirects'] = False
        return super().request(method, url, **kwargs)


def send_match_chat_push(user_id, message, game_url):
    return send_user_push(user_id, {
        'body': 'You have a new message from your opponent.',
        'url': game_url,
        'id': message['id'],
    })


def schedule_refund_push(user_id, dispute_id, tournament_name, amount_label):
    """Send a wallet reversal alert after the approval transaction has committed."""
    app = current_app._get_current_object()
    socketio = app.extensions.get('socketio')
    if not socketio or not push_enabled(app.config):
        return

    def deliver():
        with app.app_context():
            try:
                send_user_push(user_id, {
                    'type': 'refund',
                    'body': f'{amount_label} was returned to your uMshova wallet for {tournament_name}.',
                    'url': '/account',
                    'id': str(dispute_id),
                })
            except Exception:
                app.logger.exception('Refund push failed for dispute %s', dispute_id)

    try:
        socketio.start_background_task(deliver)
    except Exception:
        app.logger.exception('Could not schedule refund push for dispute %s', dispute_id)


def send_user_push(user_id, message):
    subscriptions = MatchChatPushSubscription.query.filter_by(user_id=user_id)
    return _send_push(subscriptions.all(), message)


def send_broadcast_push(message):
    subscriptions = MatchChatPushSubscription.query.join(User).filter(User.is_active.is_(True))
    results = {'accepted': 0, 'expired': 0, 'failed': 0}
    last_browser_id = ''
    while True:
        batch = subscriptions.filter(
            MatchChatPushSubscription.browser_id > last_browser_id,
        ).order_by(MatchChatPushSubscription.browser_id).limit(100).all()
        if not batch:
            return results
        last_browser_id = batch[-1].browser_id
        for key, count in _send_push(batch, message).items():
            results[key] += count
        db.session.remove()


def _send_push(subscriptions, message):
    from py_vapid import VapidException
    from pywebpush import WebPushException, webpush

    config = current_app.config
    payload = json.dumps(message, ensure_ascii=False)
    results = {'accepted': 0, 'expired': 0, 'failed': 0}
    with _PushTransport() as transport:
        for row in subscriptions:
            try:
                webpush(
                    _validated_subscription(row.subscription),
                    data=payload, ttl=3600, timeout=5, requests_session=transport,
                    vapid_private_key=config['MATCH_CHAT_PUSH_PRIVATE_KEY'],
                    vapid_claims={'sub': config['MATCH_CHAT_PUSH_SUBJECT']},
                )
                results['accepted'] += 1
            except WebPushException as exc:
                status = exc.response.status_code if exc.response is not None else None
                if status in (404, 410):
                    MatchChatPushSubscription.query.filter_by(
                        browser_id=row.browser_id, endpoint_hash=row.endpoint_hash, user_id=row.user_id,
                    ).delete()
                    db.session.commit()
                    results['expired'] += 1
                else:
                    results['failed'] += 1
                    current_app.logger.warning('Web push rejected (%s)', status)
            except (requests.RequestException, ValueError, OSError, VapidException) as exc:
                results['failed'] += 1
                current_app.logger.warning('Web push failed (%s)', type(exc).__name__)
    return results
