"""
Service layer for the user account area: profile updates, secure KYC/ID file
uploads, account JSON and wallet topup (gateway-aware).
"""
import os
import uuid
from datetime import datetime

from flask import current_app
from werkzeug.utils import secure_filename

from database import (
    db,
    Transaction,
    TX_WALLET_TOPUP,
    get_player_by_user_id,
    log_transaction,
)


KYC_NOT_SUBMITTED = 'not_submitted'
KYC_PENDING = 'pending_review'
KYC_VERIFIED = 'verified'
KYC_REJECTED = 'rejected'


def upload_dir(user_id):
    """Absolute per-user upload directory (created on demand)."""
    base = current_app.config.get('UPLOAD_FOLDER')
    if not base:
        base = os.path.join(current_app.instance_path, 'uploads')
    directory = os.path.join(base, str(user_id))
    os.makedirs(directory, exist_ok=True)
    return directory


def _save_file(file_storage, user_id, prefix):
    """Save an uploaded file with a UUID name; return a relative path.

    The relative path is ``<user_id>/<uuid>.<ext>`` and is served through the
    protected /account/uploads route (never through the public static folder).
    """
    if file_storage is None or not file_storage.filename:
        return None
    original = secure_filename(file_storage.filename or 'file')
    ext = original.rsplit('.', 1)[-1].lower() if '.' in original else 'bin'
    fname = f"{prefix}_{uuid.uuid4().hex[:12]}.{ext}"
    file_storage.save(os.path.join(upload_dir(user_id), fname))
    return os.path.join(str(user_id), fname).replace('\\', '/')


def get_account_json(user):
    """Full JSON view of a user's account (for the widget and account page)."""
    player = get_player_by_user_id(user.id)
    return {
        'id': user.id,
        'username': user.username,
        'email': user.email,
        'phone': user.phone,
        'full_name': user.full_name,
        'country': user.country,
        'address': user.address,
        'date_of_birth': user.date_of_birth.isoformat() if user.date_of_birth else None,
        'id_number': user.id_number,
        'kyc_status': user.kyc_status or KYC_NOT_SUBMITTED,
        'kyc_submitted_at': user.kyc_submitted_at.isoformat() if user.kyc_submitted_at else None,
        'kyc_document_path': user.kyc_document_path,
        'id_photo_path': user.id_photo_path,
        'id_photo_back_path': user.id_photo_back_path,
        'is_admin': user.is_admin,
        'is_super_admin': user.is_super_admin,
        'created_at': user.created_at.isoformat() if user.created_at else None,
        'last_login': user.last_login.isoformat() if user.last_login else None,
        'player': player.to_dict() if player else None,
    }


def update_profile_fields(user, form):
    """Apply editable profile fields from a validated ProfileForm."""
    user.full_name = form.full_name.data
    if form.phone.data:
        user.phone = form.phone.data
    user.country = form.country.data
    user.address = form.address.data
    user.date_of_birth = form.date_of_birth.data
    user.id_number = form.id_number.data
    db.session.commit()


def _refresh_kyc_status(user):
    """Auto-set KYC status based on which documents are present."""
    if user.kyc_document_path and user.id_photo_path and user.id_photo_back_path:
        if user.kyc_status not in (KYC_VERIFIED, KYC_PENDING):
            user.kyc_status = KYC_PENDING
            user.kyc_submitted_at = datetime.utcnow()
    else:
        user.kyc_status = KYC_NOT_SUBMITTED
        user.kyc_submitted_at = None
    db.session.commit()


def store_kyc_document(user, file_storage):
    """Store the KYC document and refresh status."""
    user.kyc_document_path = _save_file(file_storage, user.id, 'kyc_document')
    _refresh_kyc_status(user)


def store_id_photos(user, front, back):
    """Store ID photo front + back and refresh status."""
    if front and front.filename:
        user.id_photo_path = _save_file(front, user.id, 'id_front')
    if back and back.filename:
        user.id_photo_back_path = _save_file(back, user.id, 'id_back')
    _refresh_kyc_status(user)

def recent_transactions(user, limit=10):
    """Most recent wallet transactions for the account page."""
    player = get_player_by_user_id(user.id)
    if not player:
        return []
    return Transaction.query.filter_by(player_id=player.id)\
        .order_by(Transaction.id.desc()).limit(limit).all()


def initiate_topup(user, amount):
    """Gateway-aware wallet topup.

    Mock/sandbox mode credits the wallet locally (same pattern as tournament
    entry); real mode initiates a MojaPOS payment and waits for the callback
    (``_handle_wallet_topup_callback`` in app.py) to credit the wallet.
    """
    player = get_player_by_user_id(user.id)
    if not player:
        return {'success': False, 'error': 'Player profile not found'}
    try:
        amount = float(amount)
    except (TypeError, ValueError):
        return {'success': False, 'error': 'Invalid amount'}
    if amount <= 0:
        return {'success': False, 'error': 'Invalid amount'}

    if current_app.config.get('MOJAPOS_MOCK_MODE', True):
        balance_before = player.real_balance
        player.real_balance += amount
        db.session.commit()
        log_transaction(
            player_id=player.id,
            transaction_type=TX_WALLET_TOPUP,
            amount=amount,
            balance_type='real',
            balance_before=balance_before,
            balance_after=player.real_balance,
            description='Wallet top-up (mock/sandbox)',
        )
        return {'success': True, 'mock': True, 'new_balance': player.real_balance}

    from services.payment_service import payment_service

    # Create a pending transaction so the gateway callback can be mapped back
    # idempotently via external_ref_id (same pattern as tournament entry).
    external_ref_id = uuid.uuid4().hex[:12]
    pending = Transaction(
        player_id=player.id,
        transaction_type=TX_WALLET_TOPUP,
        amount=amount,
        balance_type='real',
        balance_before=player.real_balance,
        balance_after=player.real_balance,
        external_ref_id=external_ref_id,
        description='Wallet top-up (pending)',
    )
    db.session.add(pending)
    db.session.flush()

    result = payment_service.initiate_wallet_topup(
        external_ref_id=external_ref_id,
        user_id=user.id,
        amount=amount,
        phone_number=user.phone or '',
    )
    if not result.get('success'):
        pending.status = 'failed'
        db.session.commit()
        return {'success': False, 'error': result.get('error', 'Topup initiation failed')}

    # Record the gateway's own transaction id for idempotency on callbacks.
    pending.description = result.get('external_transaction_id') or pending.description
    db.session.commit()
    return {
        'success': True,
        'payment_url': result.get('payment_url'),
        'external_transaction_id': result.get('external_transaction_id'),
        'external_ref_id': external_ref_id,
    }

