"""
User account blueprint: dedicated account page, profile editing, KYC / ID photo
uploads, and gateway-aware wallet topup.

Mirrors the `admin/` package layout (routes.py + service.py + templates/).
"""
import os
from functools import wraps

from flask import (
    Blueprint,
    abort,
    flash,
    jsonify,
    redirect,
    render_template,
    request,
    session,
    url_for,
    send_from_directory,
)

from controllers.auth_controller import login_required
from database import User, db, get_player_by_user_id
from user.forms import ProfileForm, KYCDocumentForm, IDPhotoForm
from user.service import (
    get_account_json,
    initiate_topup,
    recent_transactions,
    store_id_photos,
    store_kyc_document,
    update_profile_fields,
    upload_dir,
)

user_bp = Blueprint('user', __name__, url_prefix='/account', template_folder='templates')


def _page_login_required(f):
    """Page-level login guard (redirects to the login page instead of 401 JSON)."""
    @wraps(f)
    def wrapper(*args, **kwargs):
        if not session.get('user_id'):
            return redirect(url_for('auth.login'))
        return f(*args, **kwargs)
    return wrapper


def _current_user():
    user = User.query.get(session.get('user_id'))
    if not user:
        abort(401)
    return user


@user_bp.route('')
@_page_login_required
def account_page():
    """The user's dedicated account main page."""
    user = _current_user()
    profile_form = ProfileForm(
        full_name=user.full_name,
        phone=user.phone,
        country=user.country,
        address=user.address,
        date_of_birth=user.date_of_birth,
        id_number=user.id_number,
    )
    return render_template(
        'account.html',
        user=user,
        player=get_player_by_user_id(user.id),
        account=get_account_json(user),
        profile_form=profile_form,
        kyc_form=KYCDocumentForm(),
        id_form=IDPhotoForm(),
        transactions=recent_transactions(user),
    )


@user_bp.route('/profile', methods=['POST'])
@_page_login_required
def profile_update():
    """Update editable profile fields (phone, full name, country, etc.)."""
    user = _current_user()
    form = ProfileForm(request.form)
    if not form.validate():
        for field_errors in form.errors.values():
            for error in field_errors:
                flash(error, 'error')
        return redirect(url_for('user.account_page'))

    if form.phone.data:
        existing = User.query.filter(
            User.phone == form.phone.data,
            User.id != user.id,
        ).first()
        if existing:
            flash('That phone number is already linked to another account', 'error')
            return redirect(url_for('user.account_page'))

    update_profile_fields(user, form)
    flash('Profile updated successfully', 'success')
    return redirect(url_for('user.account_page'))


@user_bp.route('/kyc', methods=['POST'])
@_page_login_required
def kyc_upload():
    """Upload a KYC document (proof of address / utility bill)."""
    user = _current_user()
    form = KYCDocumentForm()
    if not form.validate() or not form.kyc_document.data:
        flash('Please choose a valid KYC document (png/jpg/pdf)', 'error')
        return redirect(url_for('user.account_page'))

    store_kyc_document(user, form.kyc_document.data)
    flash('KYC document uploaded', 'success')
    return redirect(url_for('user.account_page'))


@user_bp.route('/id-photo', methods=['POST'])
@_page_login_required
def id_photo_upload():
    """Upload ID / passport photos (front and back)."""
    user = _current_user()
    form = IDPhotoForm()
    if not form.validate():
        flash('Please choose valid ID photo images (png/jpg)', 'error')
        return redirect(url_for('user.account_page'))
    if not form.id_photo.data or not form.id_photo_back.data:
        flash('Please provide both the front and back of your ID', 'error')
        return redirect(url_for('user.account_page'))

    store_id_photos(user, form.id_photo.data, form.id_photo_back.data)
    flash('ID photos uploaded', 'success')
    return redirect(url_for('user.account_page'))


@user_bp.route('/api', methods=['GET'])
@login_required
def account_api():
    """Full account JSON (used by account-page scripts)."""
    user = _current_user()
    return jsonify({'account': get_account_json(user)})


@user_bp.route('/topup', methods=['POST'])
@login_required
def wallet_topup():
    """Initiate a wallet topup (gateway-aware; local credit in mock mode)."""
    user = _current_user()
    if request.is_json:
        amount = (request.get_json(silent=True) or {}).get('amount')
    else:
        amount = request.form.get('amount')
    result = initiate_topup(user, amount)
    if not result.get('success'):
        return jsonify({'error': result.get('error', 'Topup failed')}), 400
    return jsonify(result)


@user_bp.route('/uploads/<path:filename>')
@_page_login_required
def uploaded_file(filename):
    """Serve a user's own KYC/ID file (owner or admin only)."""
    user = _current_user()
    owner_id, _, fname = filename.partition('/')
    if not owner_id.isdigit():
        abort(404)
    if int(owner_id) != user.id and not (user.is_admin or user.is_super_admin):
        abort(403)
    directory = upload_dir(int(owner_id))
    return send_from_directory(directory, fname)
