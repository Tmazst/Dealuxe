"""Opt-in Web Push for private match chat."""

import hashlib
import json
import os
import re
import uuid
from urllib.parse import urlsplit

import requests
from flask import Blueprint, abort, current_app, jsonify, request, session
from sqlalchemy.exc import IntegrityError

from database import MatchChatPushSubscription, User, db


push_bp = Blueprint('match_chat_push', __name__)
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


def revoke_browser_push():
    browser_id = session.get('match_chat_push_browser')
    if browser_id:
        MatchChatPushSubscription.query.filter_by(
            browser_id=browser_id, user_id=session.get('user_id'),
        ).delete()
        db.session.commit()
        session.pop('match_chat_push_browser', None)


@push_bp.route('/api/match-chat/push', methods=['GET', 'POST', 'DELETE'])
def browser_push():
    user_id = session.get('user_id')
    if not user_id:
        abort(401)
    if request.method == 'DELETE':
        revoke_browser_push()
        return '', 204
    config = current_app.config
    user = db.session.get(User, user_id)
    if not (push_enabled(config) and config.get('HYBRID_ENABLED') and
            config.get('HYBRID_PROFILE_ENABLED') and config.get('HYBRID_CHAT_ENABLED') and
            user and user.is_active and user.match_chat_enabled):
        abort(404)
    browser_id = session.get('match_chat_push_browser')
    row = db.session.get(MatchChatPushSubscription, browser_id) if browser_id else None
    if request.method == 'GET':
        response = jsonify(public_key=config['MATCH_CHAT_PUSH_PUBLIC_KEY'],
                           subscribed=bool(row and row.user_id == user_id))
        response.cache_control.no_store = True
        return response
    try:
        subscription = _validated_subscription(request.get_json(silent=True))
    except ValueError:
        abort(400)
    if row is None or row.user_id != user_id:
        row = MatchChatPushSubscription(browser_id=uuid.uuid4().hex, user_id=user_id)
    row.subscription = subscription
    row.endpoint_hash = hashlib.sha256(subscription['endpoint'].encode()).hexdigest()
    db.session.add(row)
    try:
        db.session.commit()
    except IntegrityError:
        db.session.rollback()
        abort(409)
    session['match_chat_push_browser'] = row.browser_id
    return '', 204


class _PushTransport(requests.Session):
    def request(self, method, url, **kwargs):
        kwargs['allow_redirects'] = False
        return super().request(method, url, **kwargs)


def send_match_chat_push(user_id, message, game_url):
    from pywebpush import WebPushException, webpush

    config = current_app.config
    payload = json.dumps({'body': message['message'], 'url': game_url, 'id': message['id']}, ensure_ascii=False)
    with _PushTransport() as transport:
        for row in MatchChatPushSubscription.query.filter_by(user_id=user_id).all():
            try:
                webpush(
                    _validated_subscription(row.subscription),
                    data=payload, ttl=3600, timeout=5, requests_session=transport,
                    vapid_private_key=config['MATCH_CHAT_PUSH_PRIVATE_KEY'],
                    vapid_claims={'sub': config['MATCH_CHAT_PUSH_SUBJECT']},
                )
            except WebPushException as exc:
                status = exc.response.status_code if exc.response is not None else None
                if status in (404, 410):
                    MatchChatPushSubscription.query.filter_by(
                        browser_id=row.browser_id, endpoint_hash=row.endpoint_hash,
                    ).delete()
                    db.session.commit()
                else:
                    current_app.logger.warning('Match chat push rejected (%s)', status)
            except (requests.RequestException, ValueError):
                current_app.logger.warning('Match chat push transport failed')
