"""Strict, atomic reconciliation for inbound MojaPOS payment callbacks."""

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal, InvalidOperation
import re

from flask import current_app
from sqlalchemy.exc import IntegrityError

from database import (
    PlanPurchase,
    Player,
    Tournament,
    TournamentParticipant,
    Transaction,
    TX_ENTRY_FEE,
    TX_PLAN_PURCHASE,
    TX_WALLET_TOPUP,
    db,
)
from security import audit_security_event


_MONEY_QUANTUM = Decimal('0.01')
_REFERENCE_RE = re.compile(r'^[A-Za-z0-9_-]{8,255}$')
_SUCCESS_STATUSES = {'COMPLETED', 'SUCCESS', 'SUCCESSFUL'}
_FAILED_STATUSES = {'FAILED', 'FAILURE', 'DECLINED', 'CANCELLED', 'CANCELED'}
_SUPPORTED_TYPES = {TX_ENTRY_FEE, TX_WALLET_TOPUP, TX_PLAN_PURCHASE}


class CallbackContractError(ValueError):
    """The callback is malformed and cannot be reconciled."""


class ReconciliationRejected(RuntimeError):
    """A well-formed callback does not match the server-side payment contract."""

    def __init__(self, reason, transaction_type='unknown'):
        super().__init__(reason)
        self.reason = reason
        self.transaction_type = transaction_type


@dataclass(frozen=True)
class PaymentCallback:
    callback_id: str
    gateway_transaction_id: str
    external_ref_id: str
    status: str
    amount: Decimal
    currency: str
    environment: str


@dataclass(frozen=True)
class ReconciliationResult:
    outcome: str
    reason: str
    transaction_type: str = 'unknown'
    tournament_id: int | None = None
    user_id: int | None = None


def _bounded_reference(value, field_name, maximum=255):
    if not isinstance(value, str):
        raise CallbackContractError(f'{field_name}_invalid')
    value = value.strip()
    if len(value) > maximum or not _REFERENCE_RE.fullmatch(value):
        raise CallbackContractError(f'{field_name}_invalid')
    return value


def _money(value):
    if isinstance(value, bool) or value is None:
        raise CallbackContractError('amount_invalid')
    try:
        parsed = Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError):
        raise CallbackContractError('amount_invalid') from None
    if not parsed.is_finite() or parsed <= 0 or parsed != parsed.quantize(_MONEY_QUANTUM):
        raise CallbackContractError('amount_invalid')
    return parsed


def parse_payment_callback(payload):
    """Parse only the captured, enveloped MojaPOS callback contract."""
    if not isinstance(payload, dict):
        raise CallbackContractError('payload_invalid')
    callback_id = _bounded_reference(payload.get('id'), 'callback_id')
    event = payload.get('event')
    if event not in {'payment.success', 'payment.failed'}:
        raise CallbackContractError('event_invalid')
    environment = str(payload.get('environment') or '').strip().upper()
    if environment not in {'LIVE', 'SANDBOX'}:
        raise CallbackContractError('environment_invalid')

    data = payload.get('data')
    if not isinstance(data, dict):
        raise CallbackContractError('data_invalid')
    gateway_id = _bounded_reference(
        data.get('transactionId'), 'gateway_transaction_id'
    )
    amount = _money(data.get('amount'))
    currency = str(data.get('currency') or '').strip().upper()
    if not re.fullmatch(r'[A-Z]{3}', currency):
        raise CallbackContractError('currency_invalid')

    provider = data.get('providerResponse')
    if not isinstance(provider, dict):
        raise CallbackContractError('provider_response_invalid')
    external_ref = _bounded_reference(
        provider.get('externalId'), 'external_ref_id', maximum=64
    )

    desired_status = 'completed' if event == 'payment.success' else 'failed'
    allowed_statuses = (
        _SUCCESS_STATUSES if desired_status == 'completed' else _FAILED_STATUSES
    )
    data_status = str(data.get('status') or '').strip().upper()
    if data_status not in allowed_statuses:
        raise CallbackContractError('status_event_mismatch')

    provider_status = str(provider.get('status') or '').strip().upper()
    if provider_status and provider_status not in allowed_statuses:
        raise CallbackContractError('provider_status_mismatch')
    if 'amount' in provider and _money(provider.get('amount')) != amount:
        raise CallbackContractError('provider_amount_mismatch')
    if 'currency' in provider:
        provider_currency = str(provider.get('currency') or '').strip().upper()
        if provider_currency != currency:
            raise CallbackContractError('provider_currency_mismatch')

    return PaymentCallback(
        callback_id=callback_id,
        gateway_transaction_id=gateway_id,
        external_ref_id=external_ref,
        status=desired_status,
        amount=amount,
        currency=currency,
        environment=environment,
    )


def _decimal_amount(value):
    try:
        return Decimal(str(value)).quantize(_MONEY_QUANTUM)
    except (InvalidOperation, TypeError, ValueError):
        return None


def _reject(reason, transaction=None):
    raise ReconciliationRejected(
        reason,
        transaction.transaction_type if transaction is not None else 'unknown',
    )


def _validate_server_contract(callback, transaction):
    if transaction.transaction_type not in _SUPPORTED_TYPES:
        _reject('transaction_type_unsupported', transaction)
    if transaction.gateway_transaction_id != callback.gateway_transaction_id:
        _reject('gateway_transaction_mismatch', transaction)
    if _decimal_amount(transaction.amount) != callback.amount:
        _reject('amount_mismatch', transaction)
    expected_currency = str(
        current_app.config.get('MOJAPOS_EXPECTED_CURRENCY') or 'SZL'
    ).upper()
    if (
        transaction.currency != expected_currency
        or callback.currency != expected_currency
    ):
        _reject('currency_mismatch', transaction)
    expected_environment = str(
        current_app.config.get('MOJAPOS_EXPECTED_ENVIRONMENT') or 'SANDBOX'
    ).upper()
    if (
        transaction.payment_environment != expected_environment
        or callback.environment != expected_environment
    ):
        _reject('environment_mismatch', transaction)


def _apply_entry_fee(transaction, callback):
    player = db.session.get(Player, transaction.player_id)
    tournament = db.session.get(Tournament, transaction.tournament_id)
    if player is None or tournament is None:
        _reject('entry_context_missing', transaction)
    if _decimal_amount(tournament.entry_fee) != callback.amount:
        _reject('entry_fee_mismatch', transaction)

    if callback.status == 'failed':
        changed = TournamentParticipant.query.filter_by(
            tournament_id=tournament.id,
            user_id=player.user_id,
            payment_status='pending',
        ).update({'payment_status': 'failed'}, synchronize_session=False)
        if changed != 1:
            _reject('participant_state_mismatch', transaction)
        return tournament.id, player.user_id

    now = datetime.utcnow()
    changed = TournamentParticipant.query.filter_by(
        tournament_id=tournament.id,
        user_id=player.user_id,
        status='pending',
        payment_status='pending',
    ).update({
        'status': 'registered',
        'payment_status': 'completed',
        'payment_completed_at': now,
        'transaction_id': callback.gateway_transaction_id,
        'external_payment_id': callback.external_ref_id,
        'paid_amount': float(callback.amount),
        'payment_method': 'mojapos',
    }, synchronize_session=False)
    if changed != 1:
        _reject('participant_state_mismatch', transaction)

    changed = Tournament.query.filter(
        Tournament.id == tournament.id,
        Tournament.status == 'open',
        Tournament.current_player_count < Tournament.max_players,
    ).update({
        Tournament.current_player_count: Tournament.current_player_count + 1,
        Tournament.prize_pool_amount: (
            Tournament.prize_pool_amount + float(callback.amount)
        ),
    }, synchronize_session=False)
    if changed != 1:
        _reject('tournament_not_payable', transaction)
    return tournament.id, player.user_id


def _apply_wallet_topup(transaction, callback):
    if callback.status == 'failed':
        return None, None
    changed = Player.query.filter_by(id=transaction.player_id).update({
        Player.real_balance: Player.real_balance + float(callback.amount),
    }, synchronize_session=False)
    if changed != 1:
        _reject('wallet_missing', transaction)
    db.session.flush()
    player = db.session.get(Player, transaction.player_id)
    db.session.refresh(player)
    transaction.balance_after = player.real_balance
    transaction.balance_before = player.real_balance - float(callback.amount)
    return None, player.user_id


def _apply_plan_purchase(transaction, callback):
    purchase = PlanPurchase.query.filter_by(transaction_id=transaction.id).first()
    if (
        purchase is None
        or purchase.external_ref_id != callback.external_ref_id
        or _decimal_amount(purchase.amount) != callback.amount
        or purchase.gateway_transaction_id != callback.gateway_transaction_id
    ):
        _reject('plan_contract_mismatch', transaction)
    if purchase.status not in {'initiated', 'pending'}:
        _reject('plan_state_mismatch', transaction)
    if callback.status == 'failed':
        purchase.status = 'failed'
        return None, purchase.user_id

    from pricing.service import _activate_purchase
    if not _activate_purchase(
        purchase, transaction, callback.gateway_transaction_id
    ):
        _reject('plan_activation_failed', transaction)
    return None, purchase.user_id


def reconcile_payment_callback(callback):
    """Atomically reconcile one parsed callback against its server transaction."""
    transaction = Transaction.query.filter_by(
        external_ref_id=callback.external_ref_id
    ).first()
    if transaction is None:
        return ReconciliationResult('rejected', 'reference_unknown')

    try:
        _validate_server_contract(callback, transaction)
        if transaction.status in {'completed', 'failed'}:
            if transaction.status == callback.status:
                return ReconciliationResult(
                    'duplicate', 'already_reconciled', transaction.transaction_type,
                    tournament_id=transaction.tournament_id,
                )
            return ReconciliationResult(
                'rejected', 'state_conflict', transaction.transaction_type
            )
        if transaction.status not in {'initiated', 'pending'}:
            return ReconciliationResult(
                'duplicate', 'reconciliation_in_progress', transaction.transaction_type
            )

        claimed = Transaction.query.filter(
            Transaction.id == transaction.id,
            Transaction.status.in_(('initiated', 'pending')),
        ).update({'status': 'processing'}, synchronize_session=False)
        if claimed != 1:
            db.session.rollback()
            return ReconciliationResult(
                'duplicate', 'claim_lost', transaction.transaction_type
            )
        db.session.refresh(transaction)

        if transaction.transaction_type == TX_ENTRY_FEE:
            tournament_id, user_id = _apply_entry_fee(transaction, callback)
        elif transaction.transaction_type == TX_WALLET_TOPUP:
            tournament_id, user_id = _apply_wallet_topup(transaction, callback)
        else:
            tournament_id, user_id = _apply_plan_purchase(transaction, callback)

        transaction.status = callback.status
        transaction.gateway_transaction_id = callback.gateway_transaction_id
        transaction.reconciled_at = datetime.utcnow()
        transaction.reconciliation_code = (
            'settled' if callback.status == 'completed' else 'gateway_failed'
        )
        db.session.commit()
        return ReconciliationResult(
            'accepted', transaction.reconciliation_code,
            transaction.transaction_type, tournament_id, user_id,
        )
    except ReconciliationRejected as exc:
        db.session.rollback()
        return ReconciliationResult('rejected', exc.reason, exc.transaction_type)
    except IntegrityError:
        db.session.rollback()
        return ReconciliationResult(
            'rejected', 'uniqueness_conflict', transaction.transaction_type
        )
    except Exception:
        db.session.rollback()
        raise


def audit_reconciliation(result):
    """Record only bounded, non-identifying reconciliation classifications."""
    mode = str(
        current_app.config.get('MOJAPOS_WEBHOOK_RECONCILIATION_MODE') or 'monitor'
    ).lower()
    if mode == 'off':
        return False
    return audit_security_event(
        'payment_webhook_reconciliation',
        category='payments',
        outcome=result.outcome,
        details={
            'reason': result.reason,
            'transaction_type': result.transaction_type,
            'mode': mode,
        },
    )
