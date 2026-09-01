"""Private discovery-profile service; no matching or public exposure yet."""

from datetime import datetime

from sqlalchemy import and_, or_

from database import (
    DiscoveryProfile,
    DiscoveryReport,
    GameRoom,
    Tournament,
    User,
    UserBlock,
    db,
)
from hybrid.catalog import (
    CATEGORIES,
    DEFAULT_CAPTION_TEMPLATES,
    INTENTS,
    get_caption_template,
    list_caption_templates,
    render_caption,
)


PREDEFINED_CAPTIONS = tuple(
    template['code'] for template in DEFAULT_CAPTION_TEMPLATES
)
EDITABLE_FIELDS = {
    'is_enabled', 'intent', 'category', 'subcategory', 'location',
    'predefined_caption', 'custom_caption', 'is_visible',
    'chat_preference_enabled',
}
REPORT_REASONS = ('harassment', 'spam', 'scam', 'inappropriate_profile', 'other')
REPORT_STATUSES = ('pending', 'in_review', 'resolved', 'rejected')
MODERATION_DECISIONS = ('approved', 'rejected')


def hybrid_profile_enabled(config):
    return bool(
        config.get('HYBRID_ENABLED', False)
        and config.get('HYBRID_PROFILE_ENABLED', False)
    )


def profile_options():
    caption_templates = list_caption_templates(active_only=True)
    return {
        'intents': INTENTS,
        'categories': CATEGORIES,
        'predefined_captions': tuple(
            template['code'] for template in caption_templates
        ),
        'caption_templates': caption_templates,
        'report_reasons': REPORT_REASONS,
    }


def _boolean(value, field):
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        normalized = value.strip().lower()
        if normalized in {'1', 'true', 'yes', 'on'}:
            return True
        if normalized in {'0', 'false', 'no', 'off', ''}:
            return False
    if value in (0, 1):
        return bool(value)
    raise ValueError(f'{field} must be true or false')


def _text(value, field, maximum):
    value = str(value or '').strip()
    if len(value) > maximum:
        raise ValueError(f'{field} must be {maximum} characters or fewer')
    return value or None


def serialize_profile(profile, user=None):
    if profile is None:
        return {
            'id': None,
            'user_id': user.id if user else None,
            'username': user.username if user else None,
            'is_enabled': False,
            'intent': None,
            'category': None,
            'subcategory': None,
            'location': None,
            'predefined_caption': None,
            'custom_caption': None,
            'caption_preview': None,
            'moderation_status': 'not_required',
            'moderation_note': None,
            'moderated_by': None,
            'moderated_at': None,
            'is_visible': True,
            'chat_preference_enabled': False,
            'created_at': None,
            'updated_at': None,
        }
    caption_template = get_caption_template(profile.predefined_caption)
    caption_preview = (
        profile.custom_caption
        if profile.custom_caption and profile.moderation_status == 'approved'
        else render_caption(
            caption_template,
            category=profile.category,
            subcategory=profile.subcategory,
            location=profile.location,
        )
    )
    return {
        'id': profile.id,
        'user_id': profile.user_id,
        'username': profile.user.username if profile.user else None,
        'is_enabled': bool(profile.is_enabled),
        'intent': profile.intent,
        'category': profile.category,
        'subcategory': profile.subcategory,
        'location': profile.location,
        'predefined_caption': profile.predefined_caption,
        'custom_caption': profile.custom_caption,
        'caption_preview': caption_preview,
        'moderation_status': profile.moderation_status,
        'moderation_note': profile.moderation_note,
        'moderated_by': profile.moderated_by,
        'moderated_at': profile.moderated_at.isoformat() if profile.moderated_at else None,
        'is_visible': bool(profile.is_visible),
        'chat_preference_enabled': bool(profile.chat_preference_enabled),
        'created_at': profile.created_at.isoformat() if profile.created_at else None,
        'updated_at': profile.updated_at.isoformat() if profile.updated_at else None,
    }


def get_profile(user):
    return DiscoveryProfile.query.filter_by(user_id=user.id).first()


def get_profile_payload(user):
    return serialize_profile(get_profile(user), user=user)


def update_profile(user, payload):
    payload = payload or {}
    if not isinstance(payload, dict):
        raise ValueError('Discovery profile payload must be an object')
    unexpected = set(payload) - EDITABLE_FIELDS
    if unexpected:
        raise ValueError('Unsupported discovery profile fields: ' + ', '.join(sorted(unexpected)))

    profile = get_profile(user)
    current = serialize_profile(profile, user=user)
    candidate = {field: current.get(field) for field in EDITABLE_FIELDS}
    for field in ('is_enabled', 'is_visible', 'chat_preference_enabled'):
        if field in payload:
            candidate[field] = _boolean(payload[field], field)
    if 'intent' in payload:
        candidate['intent'] = _text(payload['intent'], 'intent', 30)
    if candidate['intent'] is not None and candidate['intent'] not in INTENTS:
        raise ValueError('Invalid discovery intent')
    if 'category' in payload:
        candidate['category'] = _text(payload['category'], 'category', 50)
    if candidate['category'] is not None and candidate['category'] not in CATEGORIES:
        raise ValueError('Invalid discovery category')
    if 'subcategory' in payload:
        candidate['subcategory'] = _text(payload['subcategory'], 'subcategory', 80)
    if 'location' in payload:
        candidate['location'] = _text(payload['location'], 'location', 120)
    if 'predefined_caption' in payload:
        candidate['predefined_caption'] = _text(
            payload['predefined_caption'], 'predefined_caption', 80
        )
    caption_template = get_caption_template(candidate['predefined_caption'])
    if candidate['predefined_caption'] is not None:
        if caption_template is None:
            raise ValueError('Invalid predefined caption')
        if 'predefined_caption' in payload and not caption_template['is_active']:
            raise ValueError('Selected predefined caption is inactive')
        if candidate['intent'] and caption_template['intent'] != candidate['intent']:
            raise ValueError('Selected caption does not match the discovery intent')
        if (
            candidate['category']
            and caption_template['category']
            and caption_template['category'] != candidate['category']
        ):
            raise ValueError('Selected caption does not match the discovery category')
    if 'custom_caption' in payload:
        candidate['custom_caption'] = _text(
            payload['custom_caption'], 'custom_caption', 280
        )

    custom_changed = (
        'custom_caption' in payload
        and candidate['custom_caption'] != (profile.custom_caption if profile else None)
    )
    effective_moderation_status = current.get('moderation_status')
    if custom_changed:
        effective_moderation_status = (
            'pending_review' if candidate['custom_caption'] else 'not_required'
        )
    if (
        candidate['is_visible']
        and candidate['custom_caption']
        and effective_moderation_status != 'approved'
    ):
        candidate['is_visible'] = False

    if candidate['is_enabled']:
        for field in ('intent', 'category', 'location'):
            if not candidate[field]:
                raise ValueError(f'{field} is required when discovery is enabled')
        if not candidate['predefined_caption'] and not candidate['custom_caption']:
            raise ValueError('A predefined or custom caption is required')

    if profile is None:
        profile = DiscoveryProfile(user_id=user.id)
        db.session.add(profile)
    for field, value in candidate.items():
        setattr(profile, field, value)
    if custom_changed:
        profile.moderation_status = (
            'pending_review' if candidate['custom_caption'] else 'not_required'
        )
        profile.moderation_note = None
        profile.moderated_by = None
        profile.moderated_at = None
    profile.updated_at = datetime.utcnow()
    db.session.commit()
    return serialize_profile(profile)


def list_profiles():
    return [
        serialize_profile(profile)
        for profile in DiscoveryProfile.query.order_by(
            DiscoveryProfile.updated_at.desc(), DiscoveryProfile.id.desc()
        ).all()
    ]


def moderate_profile(profile_id, admin_user_id, decision, note=None):
    decision = _text(decision, 'decision', 30)
    if decision not in MODERATION_DECISIONS:
        raise ValueError('Decision must be approved or rejected')
    note = _text(note, 'note', 500)
    if decision == 'rejected' and not note:
        raise ValueError('A rejection reason is required')
    profile = db.session.get(DiscoveryProfile, profile_id)
    if profile is None:
        raise LookupError('Discovery profile not found')
    if not profile.custom_caption:
        raise ValueError('This profile has no custom caption to moderate')
    profile.moderation_status = decision
    profile.moderation_note = note
    profile.moderated_by = admin_user_id
    profile.moderated_at = datetime.utcnow()
    if decision == 'rejected':
        profile.is_visible = False
    db.session.commit()
    return serialize_profile(profile)


def serialize_block(block):
    return {
        'id': block.id,
        'blocked_user_id': block.blocked_id,
        'blocked_username': block.blocked.username if block.blocked else None,
        'is_active': bool(block.is_active),
        'created_at': block.created_at.isoformat() if block.created_at else None,
        'updated_at': block.updated_at.isoformat() if block.updated_at else None,
    }


def list_blocks(user_id):
    blocks = UserBlock.query.filter_by(blocker_id=user_id, is_active=True).order_by(
        UserBlock.updated_at.desc(), UserBlock.id.desc()
    ).all()
    return [serialize_block(block) for block in blocks]


def block_user(blocker_id, blocked_id):
    try:
        blocked_id = int(blocked_id)
    except (TypeError, ValueError):
        raise ValueError('blocked_user_id must be a valid user ID')
    if blocker_id == blocked_id:
        raise ValueError('You cannot block yourself')
    if db.session.get(User, blocked_id) is None:
        raise LookupError('User not found')
    block = UserBlock.query.filter_by(
        blocker_id=blocker_id, blocked_id=blocked_id
    ).first()
    if block is None:
        block = UserBlock(blocker_id=blocker_id, blocked_id=blocked_id)
        db.session.add(block)
    else:
        block.is_active = True
        block.updated_at = datetime.utcnow()
    db.session.commit()
    return serialize_block(block)


def unblock_user(blocker_id, blocked_id):
    block = UserBlock.query.filter_by(
        blocker_id=blocker_id, blocked_id=blocked_id, is_active=True
    ).first()
    if block is None:
        raise LookupError('Active block not found')
    block.is_active = False
    block.updated_at = datetime.utcnow()
    db.session.commit()


def users_are_blocked(first_user_id, second_user_id):
    return UserBlock.query.filter(
        UserBlock.is_active.is_(True),
        or_(
            and_(UserBlock.blocker_id == first_user_id, UserBlock.blocked_id == second_user_id),
            and_(UserBlock.blocker_id == second_user_id, UserBlock.blocked_id == first_user_id),
        ),
    ).first() is not None


def get_game_context(user_id, room_code):
    """Return only the opponent profile fields authorized for one room member."""
    room = GameRoom.query.filter_by(room_code=str(room_code or '').strip()).first()
    if room is None:
        raise LookupError('Game room not found')
    if not room.is_player_in_room(user_id):
        raise PermissionError('You are not a participant in this game room')

    opponent_id = room.get_opponent_id(user_id)
    own_profile_visible = bool(
        room.player1_profile_visible
        if user_id == room.player1_id
        else room.player2_profile_visible
    )
    if opponent_id is None:
        return {
            'available': False,
            'reason': 'opponent_unavailable',
            'own_profile_visible': own_profile_visible,
        }
    if users_are_blocked(user_id, opponent_id):
        return {
            'available': False,
            'reason': 'blocked',
            'own_profile_visible': own_profile_visible,
        }

    opponent_profile_visible = bool(
        room.player2_profile_visible
        if opponent_id == room.player2_id
        else room.player1_profile_visible
    )
    if not opponent_profile_visible:
        return {
            'available': False,
            'reason': 'hidden_for_game',
            'own_profile_visible': own_profile_visible,
        }

    profile = DiscoveryProfile.query.filter_by(user_id=opponent_id).first()
    if profile is None or not profile.is_enabled or not profile.is_visible:
        return {
            'available': False,
            'reason': 'profile_unavailable',
            'own_profile_visible': own_profile_visible,
        }

    serialized = serialize_profile(profile)
    opponent = db.session.get(User, opponent_id)
    caption = serialized.get('caption_preview')
    if not caption:
        return {
            'available': False,
            'reason': 'caption_unavailable',
            'own_profile_visible': own_profile_visible,
        }

    return {
        'available': True,
        'own_profile_visible': own_profile_visible,
        'opponent': {
            'username': serialized.get('username'),
            'email': opponent.email if opponent else None,
            'phone': opponent.phone if opponent else None,
            'has_profile_image': bool(opponent and opponent.profile_image_path),
            'profile_image_url': (
                f'/api/hybrid/game/{room.room_code}/opponent-image?v='
                f'{opponent.profile_image_path.rsplit("/", 1)[-1]}'
                if opponent and opponent.profile_image_path
                else None
            ),
            'intent': serialized.get('intent'),
            'category': serialized.get('category'),
            'subcategory': serialized.get('subcategory'),
            'caption': caption,
            'label': 'Hybrid discovery profile',
        },
    }


def update_game_profile_visibility(user_id, room_code, visible):
    """Set one participant's profile-sharing choice for one game room."""
    room = GameRoom.query.filter_by(room_code=str(room_code or '').strip()).first()
    if room is None:
        raise LookupError('Game room not found')
    if not room.is_player_in_room(user_id):
        raise PermissionError('You are not a participant in this game room')
    visible = _boolean(visible, 'profile_visible')
    if user_id == room.player1_id:
        room.player1_profile_visible = visible
    else:
        room.player2_profile_visible = visible
    db.session.commit()
    return visible


def _optional_positive_id(value, field):
    if value in (None, ''):
        return None
    try:
        value = int(value)
    except (TypeError, ValueError):
        raise ValueError(f'{field} must be a valid ID')
    if value <= 0:
        raise ValueError(f'{field} must be a valid ID')
    return value


def serialize_report(report, include_private=False):
    payload = {
        'id': report.id,
        'reported_user_id': report.reported_user_id,
        'reported_username': (
            report.reported_user.username if report.reported_user else None
        ),
        'profile_id': report.profile_id,
        'tournament_id': report.tournament_id,
        'match_id': report.match_id,
        'reason_code': report.reason_code,
        'details': report.details,
        'status': report.status,
        'resolution': report.resolution,
        'created_at': report.created_at.isoformat() if report.created_at else None,
        'updated_at': report.updated_at.isoformat() if report.updated_at else None,
    }
    if include_private:
        payload.update({
            'reporter_id': report.reporter_id,
            'reporter_username': report.reporter.username if report.reporter else None,
            'reviewed_by': report.reviewed_by,
            'reviewed_at': report.reviewed_at.isoformat() if report.reviewed_at else None,
        })
    return payload


def create_report(reporter_id, payload):
    payload = payload or {}
    if not isinstance(payload, dict):
        raise ValueError('Report payload must be an object')
    allowed = {'reported_user_id', 'reason_code', 'details', 'tournament_id', 'match_id'}
    unexpected = set(payload) - allowed
    if unexpected:
        raise ValueError('Unsupported report fields: ' + ', '.join(sorted(unexpected)))
    reported_user_id = _optional_positive_id(payload.get('reported_user_id'), 'reported_user_id')
    if reported_user_id is None:
        raise ValueError('reported_user_id is required')
    if reported_user_id == reporter_id:
        raise ValueError('You cannot report yourself')
    reported_user = db.session.get(User, reported_user_id)
    if reported_user is None:
        raise LookupError('User not found')
    reason = _text(payload.get('reason_code'), 'reason_code', 40)
    if reason not in REPORT_REASONS:
        raise ValueError('Invalid report reason')
    details = _text(payload.get('details'), 'details', 1000)
    tournament_id = _optional_positive_id(payload.get('tournament_id'), 'tournament_id')
    if tournament_id is not None and db.session.get(Tournament, tournament_id) is None:
        raise LookupError('Tournament not found')
    match_id = _optional_positive_id(payload.get('match_id'), 'match_id')
    profile = get_profile(reported_user)
    report = DiscoveryReport(
        reporter_id=reporter_id,
        reported_user_id=reported_user_id,
        profile_id=profile.id if profile else None,
        tournament_id=tournament_id,
        match_id=match_id,
        reason_code=reason,
        details=details,
    )
    db.session.add(report)
    db.session.commit()
    return serialize_report(report)


def list_own_reports(user_id):
    reports = DiscoveryReport.query.filter_by(reporter_id=user_id).order_by(
        DiscoveryReport.created_at.desc(), DiscoveryReport.id.desc()
    ).all()
    return [serialize_report(report) for report in reports]


def list_reports(status=None):
    if status and status not in REPORT_STATUSES:
        raise ValueError('Invalid report status')
    query = DiscoveryReport.query
    if status:
        query = query.filter_by(status=status)
    return [
        serialize_report(report, include_private=True)
        for report in query.order_by(
            DiscoveryReport.created_at.desc(), DiscoveryReport.id.desc()
        ).all()
    ]


def review_report(report_id, admin_user_id, status, resolution=None):
    status = _text(status, 'status', 30)
    if status not in ('in_review', 'resolved', 'rejected'):
        raise ValueError('Invalid report review status')
    resolution = _text(resolution, 'resolution', 1000)
    if status in ('resolved', 'rejected') and not resolution:
        raise ValueError('A resolution is required when closing a report')
    report = db.session.get(DiscoveryReport, report_id)
    if report is None:
        raise LookupError('Discovery report not found')
    report.status = status
    report.resolution = resolution
    report.reviewed_by = admin_user_id
    report.reviewed_at = datetime.utcnow()
    report.updated_at = datetime.utcnow()
    db.session.commit()
    return serialize_report(report, include_private=True)
