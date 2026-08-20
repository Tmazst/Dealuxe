"""
MojaPOS Payment Gateway Service

Integrates the uMshova Deluxe platform with the MojaPOS payment gateway
(mojapos.com). Provides:
  - Tournament entry fee initiation
  - Prize payout initiation
  - Wallet topup initiation
  - HMAC-SHA256 signature generation/verification
  - Callback verification (idempotent)

Configuration values are read from the Flask app config (see
`config.PaymentConfig`). In mock mode (`MOJAPOS_MOCK_MODE=true`) the service
returns a synthetic success without calling the real gateway, so the rest of
the system can be developed/tested locally against a sandbox path.
"""
import hmac
import hashlib
import json
import uuid
from datetime import datetime

import requests

from flask import current_app


class MojaPOSError(Exception):
    """Raised when the MojaPOS gateway returns an error we cannot handle."""


class MojaPOSService:
    """Integration with the MojaPOS payment gateway."""

    def __init__(self, app=None):
        if app is not None:
            self.init_app(app)

    def init_app(self, app):
        """Allow the service to be initialised with a Flask app context."""
        app.extensions = getattr(app, 'extensions', {})
        app.extensions['mojapos_service'] = self

    # -----------------------------
    # CONFIG HELPERS
    # -----------------------------

    @property
    def _mock_mode(self):
        return bool(current_app.config.get('MOJAPOS_MOCK_MODE', True))

    def _config(self, key, default=None):
        return current_app.config.get(key, default)

    # -----------------------------
    # SIGNATURE HELPERS
    # -----------------------------

    def _generate_signature(self, payload_dict):
        """
        Generate an HMAC-SHA256 signature for a payload dict.

        The payload is canonicalised by dumping with sorted keys, which both
        the SDK and the gateway must agree on for verification to work.
        """
        secret = self._config('MOJAPOS_WEBHOOK_SECRET') or self._config('MOJAPOS_SECRET_KEY', '')
        sorted_payload = json.dumps(payload_dict, sort_keys=True, default=str)
        return hmac.new(
            secret.encode(),
            sorted_payload.encode(),
            hashlib.sha256
        ).hexdigest()

    def verify_callback_signature(self, payload_dict, provided_signature):
        """Verify that a callback came from MojaPOS (constant-time compare)."""
        if not provided_signature:
            return False
        expected = self._generate_signature(payload_dict)
        return hmac.compare_digest(expected, provided_signature)

    # -----------------------------
    # LOW-LEVEL HTTP
    # -----------------------------

    def _make_request(self, endpoint, method='POST', data=None):
        """Perform an authenticated request to the MojaPOS API."""
        api_url = self._config('MOJAPOS_API_URL', 'https://sandbox.mojapos.com/v1')
        api_key = self._config('MOJAPOS_API_KEY', '')
        merchant_id = self._config('MOJAPOS_MERCHANT_ID', '')

        url = f"{api_url}{endpoint}"
        headers = {
            'Content-Type': 'application/json',
            'Authorization': f'Bearer {api_key}',
            'X-Merchant-ID': merchant_id,
            'User-Agent': 'Dealuxe/2.0',
        }

        if data:
            headers['X-Signature'] = self._generate_signature(data)

        try:
            if method == 'POST':
                response = requests.post(url, json=data, headers=headers, timeout=10)
            elif method == 'GET':
                response = requests.get(url, headers=headers, timeout=10)
            else:
                return None

            response.raise_for_status()
            return response.json()
        except requests.exceptions.RequestException as exc:
            print(f"[PAYMENT] MojaPOS API error: {str(exc)}")
            return None

    # -----------------------------
    # ENTRY FEE PAYMENT
    # -----------------------------

    def initiate_tournament_entry_payment(self, external_ref_id, user_id,
                                          amount, phone_number, tournament_code):
        """
        Initiate a payment for a tournament entry fee.

        ``external_ref_id`` is the strong per-transaction reference generated
        by the caller (``Transaction.external_ref_id``). It is used directly as
        the gateway ``reference`` and echoed back in the callback metadata, so
        the server can map the result back to the correct transaction WITHOUT
        relying on the small, guessable internal integer id.

        Returns a dict with ``success`` plus either the external IDs/payment
        URL (on success) or an error message (on failure).
        """
        if self._mock_mode:
            return {
                'success': True,
                'external_transaction_id': f"mock_entry_{external_ref_id}",
                'external_payment_id': external_ref_id,
                'payment_url': None,
                'amount': float(amount),
                'mock': True,
            }

        payload = {
            'merchant_id': self._config('MOJAPOS_MERCHANT_ID', ''),
            'amount': float(amount),
            'currency': 'SZL',
            'phone_number': phone_number,
            'description': f'Tournament Entry - {tournament_code}',
            'reference': external_ref_id,
            'callback_url': self._config('MOJAPOS_CALLBACK_URL', ''),
            'metadata': {
                'transaction_type': 'tournament_entry',
                'external_ref_id': external_ref_id,
                'user_id': str(user_id),
                'tournament_code': tournament_code,
            },
        }

        response = self._make_request('/payments/initiate', data=payload)
        if response and response.get('status') == 'success':
            return {
                'success': True,
                'external_transaction_id': response.get('transaction_id'),
                'external_payment_id': external_ref_id,
                'payment_url': response.get('payment_url'),
                'amount': float(amount),
            }
        return {
            'success': False,
            'error': (response or {}).get('message', 'API call failed'),
        }

    # -----------------------------
    # PRIZE WITHDRAWAL
    # -----------------------------

    def initiate_prize_withdrawal(self, withdrawal_request_id, user_id,
                                  amount, mobile_number, tournament_id):
        """
        Initiate a payout of a prize to a mobile-money number.

        Returns a dict with ``success`` plus external transaction ID or error.
        """
        external_txn_id = f"payout_{withdrawal_request_id}_{uuid.uuid4().hex[:8]}"

        if self._mock_mode:
            return {
                'success': True,
                'external_transaction_id': f"mock_payout_{withdrawal_request_id}",
                'error': None,
                'mock': True,
            }

        payload = {
            'merchant_id': self._config('MOJAPOS_MERCHANT_ID', ''),
            'amount': float(amount),
            'currency': 'SZL',
            'phone_number': mobile_number,
            'type': 'payout',
            'description': f'Tournament Prize Payout - Tournament #{tournament_id}',
            'reference': external_txn_id,
            'callback_url': self._config('MOJAPOS_CALLBACK_URL', ''),
            'metadata': {
                'transaction_type': 'prize_payout',
                'withdrawal_request_id': str(withdrawal_request_id),
                'user_id': str(user_id),
                'tournament_id': str(tournament_id),
            },
        }

        response = self._make_request('/payouts/initiate', data=payload)
        if response and response.get('status') == 'success':
            return {
                'success': True,
                'external_transaction_id': response.get('transaction_id'),
                'error': None,
            }
        return {
            'success': False,
            'error': (response or {}).get('message', 'Payout initiation failed'),
        }

    # -----------------------------
    # WALLET TOPUP
    # -----------------------------

    def initiate_wallet_topup(self, external_ref_id, user_id, amount, phone_number):
        """Initiate a player loading funds into their wallet.

        ``external_ref_id`` is the strong per-transaction reference generated by
        the caller (``Transaction.external_ref_id``). It is used as the gateway
        ``reference`` and echoed back in the callback metadata so the server can
        map the result back to the correct transaction idempotently.
        """
        if self._mock_mode:
            return {
                'success': True,
                'external_transaction_id': f"mock_topup_{external_ref_id}",
                'external_payment_id': external_ref_id,
                'payment_url': None,
                'mock': True,
            }

        payload = {
            'merchant_id': self._config('MOJAPOS_MERCHANT_ID', ''),
            'amount': float(amount),
            'currency': 'SZL',
            'phone_number': phone_number,
            'description': 'Dealuxe Wallet Topup',
            'reference': external_ref_id,
            'callback_url': self._config('MOJAPOS_CALLBACK_URL', ''),
            'metadata': {
                'transaction_type': 'wallet_topup',
                'external_ref_id': external_ref_id,
                'user_id': str(user_id),
            },
        }

        response = self._make_request('/payments/initiate', data=payload)
        if response and response.get('status') == 'success':
            return {
                'success': True,
                'external_transaction_id': response.get('transaction_id'),
                'external_payment_id': external_ref_id,
                'payment_url': response.get('payment_url'),
            }
        return {
            'success': False,
            'error': (response or {}).get('message', 'Failed to initiate topup'),
        }

    # -----------------------------
    # STATUS LOOKUP
    # -----------------------------

    def get_transaction_status(self, external_transaction_id):
        """Query MojaPOS for the current status of a transaction."""
        if self._mock_mode:
            return {'status': 'completed', 'amount': 0, 'timestamp': datetime.utcnow().isoformat()}

        response = self._make_request(
            f'/transactions/{external_transaction_id}',
            method='GET',
        )
        if response:
            return {
                'status': response.get('status'),
                'amount': response.get('amount'),
                'timestamp': response.get('timestamp'),
            }
        return None


# Singleton instance (initialised lazily against the app config).
payment_service = MojaPOSService()
