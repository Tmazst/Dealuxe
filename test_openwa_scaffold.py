"""V3-0908 tests for the intentionally inert openWA boundary."""

import unittest

from config import build_openwa_scaffold_config
from integrations.openwa_scaffold import (
    MessagePurpose,
    OpenWANotAvailable,
    OutboundMessage,
    build_openwa_adapter,
)


class OpenWAScaffoldTests(unittest.TestCase):
    def test_all_channels_are_disabled_by_default(self):
        config = build_openwa_scaffold_config({})

        self.assertFalse(config['OPENWA_ENABLED'])
        self.assertEqual(config['OPENWA_IMPLEMENTATION_STATUS'], 'scaffold_only')
        self.assertFalse(config['OPENWA_SUPPORT_ENABLED'])
        self.assertFalse(config['OPENWA_ALERTS_ENABLED'])
        self.assertFalse(config['OPENWA_FEEDBACK_ENABLED'])
        self.assertFalse(config['OPENWA_MESSAGING_ENABLED'])

    def test_child_channel_cannot_be_enabled_without_master(self):
        with self.assertRaisesRegex(RuntimeError, 'OPENWA_ENABLED is required'):
            build_openwa_scaffold_config({'OPENWA_SUPPORT_ENABLED': 'true'})

    def test_master_activation_is_rejected_until_implementation(self):
        with self.assertRaisesRegex(RuntimeError, 'not implemented or approved'):
            build_openwa_scaffold_config({'OPENWA_ENABLED': 'true'})

    def test_scaffold_names_the_four_approved_message_purposes(self):
        self.assertEqual(
            {purpose.value for purpose in MessagePurpose},
            {
                'customer_support',
                'operational_alert',
                'customer_feedback',
                'service_message',
            },
        )

    def test_disabled_adapter_exposes_no_live_capability(self):
        adapter = build_openwa_adapter(build_openwa_scaffold_config({}))
        self.assertEqual(adapter.status(), {
            'enabled': False,
            'implementation_status': 'scaffold_only',
            'provider_connected': False,
        })
        message = OutboundMessage(
            purpose=MessagePurpose.OPERATIONAL_ALERT,
            recipient_ref='opaque-recipient-reference',
            body='Service notice',
            idempotency_key='event-123',
        )
        with self.assertRaises(OpenWANotAvailable):
            adapter.send(message)


if __name__ == '__main__':
    unittest.main()
