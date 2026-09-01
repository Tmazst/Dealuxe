"""Administrator-managed predefined caption catalogue and safe renderer."""

from datetime import datetime
import re
from string import Formatter

from database import DiscoveryCaptionTemplate, db


INTENTS = ('selling', 'seeking', 'collaboration')
CATEGORIES = ('products', 'services', 'jobs', 'business', 'community', 'other')
ALLOWED_PLACEHOLDERS = frozenset({'category', 'subcategory', 'location'})
CODE_PATTERN = re.compile(r'^[a-z][a-z0-9_]{2,79}$')

DEFAULT_CAPTION_TEMPLATES = (
    {
        'code': 'selling_products',
        'display_name': 'Selling products',
        'intent': 'selling',
        'category': 'products',
        'template_text': 'I am selling {subcategory} in {location}.',
        'sort_order': 10,
    },
    {
        'code': 'offering_services',
        'display_name': 'Offering services',
        'intent': 'selling',
        'category': 'services',
        'template_text': 'I offer {subcategory} services in {location}.',
        'sort_order': 20,
    },
    {
        'code': 'looking_to_buy',
        'display_name': 'Looking to buy',
        'intent': 'seeking',
        'category': 'products',
        'template_text': 'I am looking to buy {subcategory} in {location}.',
        'sort_order': 30,
    },
    {
        'code': 'seeking_services',
        'display_name': 'Seeking services',
        'intent': 'seeking',
        'category': 'services',
        'template_text': 'I am looking for {subcategory} services in {location}.',
        'sort_order': 40,
    },
    {
        'code': 'open_to_collaboration',
        'display_name': 'Open to collaboration',
        'intent': 'collaboration',
        'category': None,
        'template_text': (
            'I am open to collaboration opportunities in {category} '
            'around {location}.'
        ),
        'sort_order': 50,
    },
    {
        'code': 'business_networking',
        'display_name': 'Business networking',
        'intent': 'collaboration',
        'category': 'business',
        'template_text': (
            'I would like to connect with people in {category} around {location}.'
        ),
        'sort_order': 60,
    },
)


def _text(value, field, maximum, required=False):
    if value is None:
        value = ''
    if not isinstance(value, str):
        raise ValueError(f'{field} must be text')
    value = value.strip()
    if required and not value:
        raise ValueError(f'{field} is required')
    if len(value) > maximum:
        raise ValueError(f'{field} must be {maximum} characters or fewer')
    return value or None


def _boolean(value, field):
    if isinstance(value, bool):
        return value
    raise ValueError(f'{field} must be true or false')


def _integer(value, field, minimum=0, maximum=10000):
    if isinstance(value, bool):
        raise ValueError(f'{field} must be an integer')
    try:
        value = int(value)
    except (TypeError, ValueError):
        raise ValueError(f'{field} must be an integer')
    if not minimum <= value <= maximum:
        raise ValueError(f'{field} must be between {minimum} and {maximum}')
    return value


def validate_template_text(template_text):
    template_text = _text(template_text, 'template_text', 280, required=True)
    try:
        parsed = tuple(Formatter().parse(template_text))
    except ValueError as exc:
        raise ValueError('template_text contains invalid braces') from exc
    if any(format_spec or conversion for _, _, format_spec, conversion in parsed):
        raise ValueError('template_text formatting and conversions are not allowed')
    placeholders = {
        field_name for _, field_name, _, _ in parsed if field_name
    }
    unsupported = placeholders - ALLOWED_PLACEHOLDERS
    if unsupported:
        raise ValueError(
            'Unsupported template placeholders: ' + ', '.join(sorted(unsupported))
        )
    return template_text


def serialize_caption_template(template):
    if isinstance(template, dict):
        return {
            **template,
            'id': None,
            'is_active': True,
            'created_by': None,
            'updated_by': None,
            'created_at': None,
            'updated_at': None,
        }
    return {
        'id': template.id,
        'code': template.code,
        'display_name': template.display_name,
        'intent': template.intent,
        'category': template.category,
        'template_text': template.template_text,
        'is_active': bool(template.is_active),
        'sort_order': template.sort_order,
        'created_by': template.created_by,
        'updated_by': template.updated_by,
        'created_at': template.created_at.isoformat() if template.created_at else None,
        'updated_at': template.updated_at.isoformat() if template.updated_at else None,
    }


def ensure_default_caption_templates():
    if DiscoveryCaptionTemplate.query.count():
        return
    for values in DEFAULT_CAPTION_TEMPLATES:
        db.session.add(DiscoveryCaptionTemplate(**values, is_active=True))
    db.session.commit()


def list_caption_templates(active_only=False):
    query = DiscoveryCaptionTemplate.query
    if active_only:
        query = query.filter_by(is_active=True)
    templates = query.order_by(
        DiscoveryCaptionTemplate.sort_order,
        DiscoveryCaptionTemplate.display_name,
        DiscoveryCaptionTemplate.id,
    ).all()
    if not templates:
        if DiscoveryCaptionTemplate.query.count() == 0:
            return [serialize_caption_template(item) for item in DEFAULT_CAPTION_TEMPLATES]
        return []
    return [serialize_caption_template(template) for template in templates]


def get_caption_template(code, active_only=False):
    if not code:
        return None
    query = DiscoveryCaptionTemplate.query.filter_by(code=code)
    if active_only:
        query = query.filter_by(is_active=True)
    template = query.first()
    if template:
        return serialize_caption_template(template)
    if DiscoveryCaptionTemplate.query.count() == 0:
        for default in DEFAULT_CAPTION_TEMPLATES:
            if default['code'] == code:
                return serialize_caption_template(default)
    return None


def render_caption(template, *, category=None, subcategory=None, location=None):
    if template is None:
        return None
    values = {
        'category': str(category or 'business').strip(),
        'subcategory': str(subcategory or category or 'opportunities').strip(),
        'location': str(location or 'my area').strip(),
    }
    rendered = template['template_text']
    for field_name, value in values.items():
        rendered = rendered.replace('{' + field_name + '}', value)
    return rendered[:280]


def create_caption_template(payload, admin_user_id):
    if not isinstance(payload, dict):
        raise ValueError('Caption payload must be an object')
    allowed = {
        'code', 'display_name', 'intent', 'category', 'template_text',
        'is_active', 'sort_order',
    }
    unexpected = set(payload) - allowed
    if unexpected:
        raise ValueError('Unsupported caption fields: ' + ', '.join(sorted(unexpected)))
    code = _text(payload.get('code'), 'code', 80, required=True)
    if not CODE_PATTERN.fullmatch(code):
        raise ValueError('code must use lowercase letters, numbers and underscores')
    if DiscoveryCaptionTemplate.query.filter_by(code=code).first():
        raise ValueError('Caption code already exists')
    display_name = _text(
        payload.get('display_name'), 'display_name', 120, required=True
    )
    intent = _text(payload.get('intent'), 'intent', 30, required=True)
    if intent not in INTENTS:
        raise ValueError('Invalid caption intent')
    category = _text(payload.get('category'), 'category', 50)
    if category is not None and category not in CATEGORIES:
        raise ValueError('Invalid caption category')
    template = DiscoveryCaptionTemplate(
        code=code,
        display_name=display_name,
        intent=intent,
        category=category,
        template_text=validate_template_text(payload.get('template_text')),
        is_active=_boolean(payload.get('is_active', True), 'is_active'),
        sort_order=_integer(payload.get('sort_order', 100), 'sort_order'),
        created_by=admin_user_id,
        updated_by=admin_user_id,
    )
    db.session.add(template)
    db.session.flush()
    return serialize_caption_template(template)


def update_caption_template(template_id, payload, admin_user_id):
    if not isinstance(payload, dict):
        raise ValueError('Caption payload must be an object')
    allowed = {
        'display_name', 'intent', 'category', 'template_text',
        'is_active', 'sort_order',
    }
    unexpected = set(payload) - allowed
    if unexpected:
        raise ValueError('Unsupported caption fields: ' + ', '.join(sorted(unexpected)))
    if not payload:
        raise ValueError('At least one caption field is required')
    template = db.session.get(DiscoveryCaptionTemplate, template_id)
    if template is None:
        raise LookupError('Caption template not found')
    if 'display_name' in payload:
        template.display_name = _text(
            payload['display_name'], 'display_name', 120, required=True
        )
    if 'intent' in payload:
        intent = _text(payload['intent'], 'intent', 30, required=True)
        if intent not in INTENTS:
            raise ValueError('Invalid caption intent')
        template.intent = intent
    if 'category' in payload:
        category = _text(payload['category'], 'category', 50)
        if category is not None and category not in CATEGORIES:
            raise ValueError('Invalid caption category')
        template.category = category
    if 'template_text' in payload:
        template.template_text = validate_template_text(payload['template_text'])
    if 'is_active' in payload:
        template.is_active = _boolean(payload['is_active'], 'is_active')
    if 'sort_order' in payload:
        template.sort_order = _integer(payload['sort_order'], 'sort_order')
    template.updated_by = admin_user_id
    template.updated_at = datetime.utcnow()
    db.session.flush()
    return serialize_caption_template(template)
