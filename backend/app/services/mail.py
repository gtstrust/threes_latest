"""Outbound email — the second thing this backend talks *out* to.

Deliberately the same shape as `app/services/realtime.py`, which already solved
this problem once: a Protocol so the caller depends on the capability rather than
the provider, a null implementation chosen from config so the app boots and the
whole suite runs with nothing configured, a dependency so tests can install the
null one explicitly, and failures logged rather than raised.

That last point is the one worth stating plainly. **A reminder that fails to send
must not fail the request that asked for it.** An organiser pressing "remind the
field" has already done the thing they meant to do; answering 500 because Resend
was slow would tell them their event is broken when it is not. The cost is that a
failed send is discovered in the logs rather than on screen, which is the right
way round for something whose whole purpose is to be sent later anyway.

**The test suite must never send.** `tests/conftest.py` installs `NullMailer` for
every test, exactly as it installs `NullNotifier` — without that, a developer
whose `.env` holds a real key would mail real people from a test run.
"""

import logging
from dataclasses import dataclass
from typing import Protocol

import httpx

from app.core.config import is_configured, settings
from app.core.http import get_http_client

logger = logging.getLogger(__name__)

RESEND_ENDPOINT = "https://api.resend.com/emails"


@dataclass(frozen=True)
class Message:
    """One email. Plain text alongside HTML because some clients still prefer it,
    and because a reminder that arrives as an unstyled wall of markup on a phone
    at 6am is worse than one that arrives as a sentence."""

    to: str
    subject: str
    text: str
    html: str


class Mailer(Protocol):
    """What the reminder service depends on. Two implementations, one a no-op."""

    async def send(self, message: Message) -> bool:
        """Send one message. Returns whether it went, never raises."""
        ...


class NullMailer:
    """Does nothing, for when no provider is configured.

    Making "off" an object rather than an `if` at the call site keeps the branch
    out of the service. Logging at debug rather than staying silent means a
    developer wondering why no mail arrived can find out without reading code.
    """

    async def send(self, message: Message) -> bool:
        logger.debug(
            "Mail suppressed (no provider configured): %r to %s", message.subject, message.to
        )
        return False


class ResendMailer:
    """Posts to Resend's REST API.

    Chosen for fitting the outbound-HTTP pattern this codebase already has: one
    endpoint, one key, no SDK. Swapping providers is this class and `build_mailer`,
    which is the whole reason `Mailer` is a Protocol.
    """

    def __init__(self, api_key: str, sender: str, client: httpx.AsyncClient | None = None) -> None:
        self._api_key = api_key
        self._sender = sender
        # Injectable so tests can drive a MockTransport. None in production so
        # every mailer shares the pooled client.
        self._client = client

    async def send(self, message: Message) -> bool:
        try:
            response = await (self._client or get_http_client()).post(
                RESEND_ENDPOINT,
                headers={"Authorization": f"Bearer {self._api_key}"},
                json={
                    "from": self._sender,
                    "to": [message.to],
                    "subject": message.subject,
                    "text": message.text,
                    "html": message.html,
                },
            )
            response.raise_for_status()
            return True
        except httpx.HTTPError:
            # Narrow in type, broad in effect: connection, timeout and non-2xx all
            # mean the same thing here — this message did not go. Anything that is
            # not an HTTP problem is a bug and should still surface.
            logger.warning("Sending %r to %s failed", message.subject, message.to, exc_info=True)
            return False


def build_mailer() -> Mailer:
    """A real mailer when a provider is configured, a no-op when it isn't.

    Both settings are needed: a key to authenticate with and an address to send
    from. A partial or still-placeholder configuration is "off" rather than an
    error, because the app is meant to boot on `.env.example`.
    """
    key, sender = settings.resend_api_key, settings.email_from
    if not is_configured(key) or not is_configured(sender):
        return NullMailer()
    assert key is not None and sender is not None  # narrowed by is_configured
    return ResendMailer(key, sender)
