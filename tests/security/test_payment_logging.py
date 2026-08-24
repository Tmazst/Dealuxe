import unittest
from unittest.mock import Mock, patch

from flask import Flask

from services.payment_service import MojaPOSService


class PaymentLoggingTests(unittest.TestCase):
    def test_gateway_request_log_excludes_credentials_and_customer_payload(self):
        app = Flask(__name__)
        app.config.update({
            'MOJAPOS_API_URL': 'https://payments.example',
            'MOJAPOS_API_KEY': 'super-secret-api-key',
            'MOJAPOS_MERCHANT_ID': 'merchant-secret',
        })
        service = MojaPOSService()
        response = Mock()
        response.raise_for_status.return_value = None
        response.json.return_value = {'transactionId': 'gateway-transaction'}
        payload = {
            'phoneNumber': '26876000000',
            'metadata': {'payerMessage': 'private customer message'},
        }

        with app.app_context(), patch(
            'services.payment_service.requests.post', return_value=response
        ), patch('builtins.print') as logged:
            result = service._make_request('/payments/pay', data=payload)

        self.assertEqual(result['transactionId'], 'gateway-transaction')
        rendered_log = ' '.join(
            ' '.join(str(item) for item in call.args)
            for call in logged.call_args_list
        )
        self.assertIn('endpoint=/payments/pay', rendered_log)
        self.assertNotIn('super-secret-api-key', rendered_log)
        self.assertNotIn('merchant-secret', rendered_log)
        self.assertNotIn('26876000000', rendered_log)
        self.assertNotIn('private customer message', rendered_log)


if __name__ == '__main__':
    unittest.main()
