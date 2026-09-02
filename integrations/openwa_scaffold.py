"""Inert V3-0908 contract for a possible future openWA integration.

This module does not import openWA, connect to WhatsApp, register webhooks,
persist provider payloads or send messages.  It exists so a later approved
implementation has an explicit, testable boundary instead of being coupled to
gameplay, Hybrid matching or Q-messànger.
"""

from dataclasses import dataclass
from enum import Enum
from typing import Mapping, Protocol


class OpenWANotAvailable(RuntimeError):
    """Raised when code attempts to use the intentionally disabled scaffold."""


class MessagePurpose(str, Enum):
    CUSTOMER_SUPPORT = 'customer_support'
    OPERATIONAL_ALERT = 'operational_alert'
    CUSTOMER_FEEDBACK = 'customer_feedback'
    SERVICE_MESSAGE = 'service_message'


@dataclass(frozen=True)
class OutboundMessage:
    """Provider-neutral message request for a future adapter.

    ``recipient_ref`` is deliberately provider-neutral. The application must
    not place raw telephone numbers in logs, audit summaries or idempotency
    keys when the real adapter is implemented.
    """

    purpose: MessagePurpose
    recipient_ref: str
    body: str
    idempotency_key: str


class OpenWAAdapter(Protocol):
    def status(self) -> Mapping[str, object]:
        """Return non-sensitive channel health information."""

    def send(self, message: OutboundMessage) -> str:
        """Return a provider message reference after an accepted send."""


class DisabledOpenWAAdapter:
    """Fail-closed adapter used until openWA is separately implemented."""

    def status(self) -> Mapping[str, object]:
        return {
            'enabled': False,
            'implementation_status': 'scaffold_only',
            'provider_connected': False,
        }

    def send(self, message: OutboundMessage) -> str:
        del message
        raise OpenWANotAvailable(
            'openWA is scaffolded but not implemented or enabled'
        )


def build_openwa_adapter(config: Mapping[str, object]) -> OpenWAAdapter:
    """Build only the inert adapter; live configuration is rejected."""
    if bool(config.get('OPENWA_ENABLED', False)):
        raise OpenWANotAvailable(
            'No live openWA adapter exists in the Version 3 MVP'
        )
    return DisabledOpenWAAdapter()
