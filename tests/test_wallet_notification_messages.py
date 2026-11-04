"""Message-content regressions for direct WhatsApp credit notices."""

import unittest

from flask import Flask

from services.wallet_notification_service import _build_credit_message


class WalletNotificationMessageTests(unittest.TestCase):
    def setUp(self):
        self.app = Flask(__name__)
        self.app.config.update(
            PUBLIC_APP_URL='https://umshova.games',
            UMSHOVA_WHATSAPP_GROUP_INVITE_URL='https://chat.whatsapp.com/test-invite',
            UMSHOVA_MEMBERSHIP_FORM_URL='https://forms.gle/test-membership',
        )

    def test_first_registration_welcome_has_group_invite_only(self):
        with self.app.app_context():
            message = _build_credit_message(10, welcome=True)
        self.assertIn('Welcome to uMshova', message)
        self.assertIn('https://chat.whatsapp.com/test-invite', message)
        self.assertNotIn('https://forms.gle/test-membership', message)

    def test_admin_award_keeps_membership_invite_not_group_invite(self):
        with self.app.app_context():
            message = _build_credit_message(20, welcome=False)
        self.assertIn('https://forms.gle/test-membership', message)
        self.assertNotIn('https://chat.whatsapp.com/test-invite', message)


if __name__ == '__main__':
    unittest.main()
