"""Public Cup event-detail parsing and validation."""

from __future__ import annotations

from datetime import datetime
import json


class CupEventDetailsError(ValueError):
    """Raised when administrator-supplied public Cup details are invalid."""


def _clean_text(value, field_name, maximum):
    cleaned = str(value or '').strip()
    if len(cleaned) > maximum:
        raise CupEventDetailsError(
            '{0} must be {1} characters or fewer'.format(field_name, maximum)
        )
    return cleaned or None


def _parse_datetime(value, field_name):
    value = str(value or '').strip()
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace('Z', '+00:00')).replace(
            tzinfo=None
        )
    except ValueError as exc:
        raise CupEventDetailsError(
            '{0} must be a valid date and time'.format(field_name)
        ) from exc


def apply_cup_event_details(tournament, data):
    """Validate and apply editable public event fields to one Cup."""
    if tournament.tournament_type != 'cup':
        raise CupEventDetailsError('Event details are limited to Cup tournaments')
    data = data or {}
    event_start_at = _parse_datetime(data.get('event_start_at'), 'Event start')
    event_check_in_at = _parse_datetime(
        data.get('event_check_in_at'), 'Event check-in'
    )
    if event_start_at and event_check_in_at and event_check_in_at > event_start_at:
        raise CupEventDetailsError('Event check-in cannot be after the Cup start')

    tournament.event_start_at = event_start_at
    tournament.event_check_in_at = event_check_in_at
    tournament.event_venue_name = _clean_text(
        data.get('event_venue_name'), 'Venue name', 160
    )
    tournament.event_venue_address = _clean_text(
        data.get('event_venue_address'), 'Venue address', 255
    )
    tournament.event_public_notes = _clean_text(
        data.get('event_public_notes'), 'Public event notes', 1000
    )
    return serialize_cup_event_details(tournament)


def serialize_cup_event_details(tournament):
    """Return public, contact-free Cup event metadata."""
    metadata = {}
    try:
        parsed = json.loads(tournament.notes or '{}')
        if isinstance(parsed, dict):
            metadata = parsed
    except (TypeError, ValueError):
        metadata = {}
    return {
        'event_key': metadata.get('event_key'),
        'season': metadata.get('season'),
        'start_at': (
            tournament.event_start_at.isoformat()
            if tournament.event_start_at else None
        ),
        'check_in_at': (
            tournament.event_check_in_at.isoformat()
            if tournament.event_check_in_at else None
        ),
        'venue_name': tournament.event_venue_name,
        'venue_address': tournament.event_venue_address,
        'public_notes': tournament.event_public_notes,
        'details_complete': bool(
            tournament.event_start_at and tournament.event_venue_name
        ),
    }

