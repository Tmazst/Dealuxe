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

curl -X POST \
  "https://mojapos.com/api/payments/pay" \
  -H "Authorization: Bearer pk_live_f4f8be6a58de21195be9f9b2" \
  -H "Content-Type: application/json" \
  -d '{   "provider": "MTN_MOMO",   "amount": 1,   "currency": "SZL",   "phoneNumber": "26876412255",   "metadata": {     "externalId": "TXN-12345",     "payerMessage": "Payment for order",     "payeeNote": "Order payment"   } }'

"""
import hmac
import hashlib
import json
import uuid
from datetime import datetime

import requests

from flask import current_app


# MojaPOS resource path appended to `MOJAPOS_API_URL` to initiate a payment.
# Full URL used at runtime: `{MOJAPOS_API_URL}{PAYMENT_INITIATE_ENDPOINT}`.
# Per the MojaPOS docs curl this should resolve to the documented initiate URL.
PAYMENT_INITIATE_ENDPOINT = '/payments/pay' #Please do not change this endpoint without approval. the api is always ; https://mojapos.com/api/payments/pay for initiating payment


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
        """
        Perform an authenticated request to the MojaPOS API.
        curl -X POST \
        "https://mojapos.com/api/payments/pay" \
        -H "Authorization: Bearer pk_live_f4f8be6a58de21195be9f9b2" \
        -H "Content-Type: application/json" \
        -d '{   "provider": "MTN_MOMO",   "amount": 1,   "currency": "SZL",   "phoneNumber": "26876412255",   "metadata": {     "externalId": "TXN-12345",     "payerMessage": "Payment for order",     "payeeNote": "Order payment"   } }'

        """
        api_url = self._config('MOJAPOS_API_URL', 'https://sandbox.mojapos.com/v1')
        api_key = self._config('MOJAPOS_API_KEY', '')
        merchant_id = self._config('MOJAPOS_MERCHANT_ID', '')

        url = f"{api_url}{endpoint}"
        headers = {
            'Content-Type': 'application/json',
            'Authorization': f'Bearer {api_key}',
            # 'X-Merchant-ID': merchant_id,
            # 'User-Agent': 'Dealuxe/2.0',
        }

        # if data:
        #     headers['X-Signature'] = self._generate_signature(data)

        print(f"[PAYMENT] MojaPOS PAYLOAD: {data}")
        print(f"[PAYMENT] MojaPOS HEADERS: {headers}")
        print(f"[PAYMENT] MojaPOS URL: {url}")

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
                                          amount, phone_number, tournament_code, txn=None):
        """
        Initiate a payment for a tournament entry fee.

        ``external_ref_id`` is the strong per-transaction reference generated
        by the caller (``Transaction.external_ref_id``). It is sent as
        ``metadata.externalId`` and echoed back in the callback so the server can
        map the result back to the correct transaction. ``txn`` is the optional
        pending Transaction row whose status is advanced when the gateway accepts
        the payment.

        Returns a dict with ``success`` plus the gateway transaction id
        (``transactionId``) or an error message on failure.
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
            "provider": "MTN_MOMO", 
            'amount': float(amount),
            'currency': 'SZL',
            "phoneNumber": phone_number,
            'metadata': {
                "externalId": external_ref_id,
                "payerMessage": f"Tournament Entry Fee Payment for Tournament {tournament_code}",
                "payeeNote": "Dealuxe Payment" 
            },
        }

        response = self._make_request(PAYMENT_INITIATE_ENDPOINT, data=payload)
        # A successful initiate returns HTTP 2xx with a `transactionId` and
        # status "PENDING" (MTN MoMo USSD push -- there is NO hosted payment_url).
        if response and response.get('transactionId'):
            if txn is not None and txn.status != 'completed':
                txn.status = 'pending'
            return {
                'success': True,
                'external_transaction_id': response.get('transactionId'),
                'provider_reference': response.get('providerReference'),
                'external_payment_id': external_ref_id,
                'payment_url': None,
                'amount': float(amount),
                'status': response.get('status'),
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
            "provider": "MTN_MOMO", 
            'amount': float(amount),
            'currency': 'SZL',
            "phoneNumber": mobile_number,
            'metadata': {
                "externalId": external_txn_id,
                "payerMessage": f"Tournament Entry Fee Payment for Tournament {tournament_id}",
                "payeeNote": "Dealuxe Payment" 
            },
        }

        response = self._make_request(PAYMENT_INITIATE_ENDPOINT, data=payload)
        if response and response.get('transactionId'):
            return {
                'success': True,
                'external_transaction_id': response.get('transactionId'),
                'provider_reference': response.get('providerReference'),
                'error': None,
                'status': response.get('status'),
            }
        return {
            'success': False,
            'error': (response or {}).get('message', 'Payout initiation failed'),
        }

    # -----------------------------
    # WALLET TOPUP
    # -----------------------------

    def initiate_wallet_topup(self, external_ref_id, user_id, amount, phone_number, txn=None):
        """Initiate a player loading funds into their wallet.

        ``external_ref_id`` is the strong per-transaction reference generated by
        the caller (``Transaction.external_ref_id``). It is sent as
        ``metadata.externalId`` and echoed back in the callback so the server can
        map the result back to the correct transaction idempotently. ``txn`` is
        the optional pending Transaction row whose status is advanced when the
        gateway accepts the payment.
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
            "provider": "MTN_MOMO",
            'amount': float(amount),
            'currency': 'SZL',
            "phoneNumber": phone_number,
            'metadata': {
                "externalId": external_ref_id,
                "payerMessage": f"Topup Wallet for User {user_id}",
                "payeeNote": "Dealuxe Topup Payment"
            },
        }

        response = self._make_request(PAYMENT_INITIATE_ENDPOINT, data=payload)
        if response and response.get('transactionId'):
            if txn is not None and txn.status != 'completed':
                txn.status = 'pending'
            return {
                'success': True,
                'external_transaction_id': response.get('transactionId'),
                'provider_reference': response.get('providerReference'),
                'external_payment_id': external_ref_id,
                'payment_url': None,
                'status': response.get('status'),
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
