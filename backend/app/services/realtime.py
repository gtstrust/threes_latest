"""Realtime — telling clients that the leaderboard moved.

The signal carries **no scores**. ADR-001 keeps ranking server-side, so all a
client learns here is "something changed on tournament X"; it then refetches
`GET /tournaments/{id}/leaderboard` through FastAPI, where `require_can_view`
already decides who may see what. That is the whole reason this is a Supabase
*Broadcast* rather than Postgres Changes — see ADR-010. Postgres Changes would
stream the `hole_scores` row itself and gate it on an RLS policy, which means
writing `require_can_view` a second time in SQL. Nothing here needs a policy,
because nothing here is worth protecting.

Not a repository and not pure: it talks to a third party over HTTP, so it lives
in the service layer like every other piece of orchestration, and imports no
`fastapi` — the route decides *when* to send, this decides *what*.
"""

import logging
from typing import Protocol
from uuid import UUID

import httpx

from app.core.config import is_configured, settings
from app.core.http import get_http_client

logger = logging.getLogger(__name__)

# One event today. Named for what the client should do about it, not for what
# happened server-side: a client that also cared about "a round was drawn" would
# still just refetch, so the vocabulary stays in terms of the reader.
LEADERBOARD_CHANGED = "leaderboard_changed"

# Supabase namespaces a channel by its topic string. Prefixing with the resource
# keeps room for `round:{uuid}` later without the two ever colliding.
TOURNAMENT_TOPIC = "tournament:{tournament_id}"


class RealtimeNotifier(Protocol):
    """What the score route depends on. Two implementations, one of them a no-op."""

    async def leaderboard_changed(self, *, tournament_id: UUID, round_id: UUID) -> None: ...


class NullNotifier:
    """Does nothing, for when Supabase isn't configured.

    Making "off" an object rather than an `if` at the call site keeps the branch
    out of the route. Note this is chosen from config, so a developer whose `.env`
    holds a real project *will* broadcast from a local run — which is why
    `tests/conftest.py` installs this explicitly rather than relying on config.
    """

    async def leaderboard_changed(self, *, tournament_id: UUID, round_id: UUID) -> None:
        return None


class SupabaseNotifier:
    """Posts a broadcast to Supabase Realtime's REST endpoint.

    Failure is logged and swallowed. By the time this runs the hole is already
    committed, and a player who has just holed a putt should not see an error
    because Supabase was slow — the worst case is that clients find out on their
    next poll instead of immediately.
    """

    def __init__(
        self, base_url: str, api_key: str, client: httpx.AsyncClient | None = None
    ) -> None:
        self._endpoint = f"{base_url.rstrip('/')}/realtime/v1/api/broadcast"
        self._api_key = api_key
        # Injectable so tests can drive a MockTransport. Left None in production
        # so every notifier shares one pooled client rather than opening a
        # connection per hole.
        self._client = client

    async def leaderboard_changed(self, *, tournament_id: UUID, round_id: UUID) -> None:
        await self._broadcast(
            topic=TOURNAMENT_TOPIC.format(tournament_id=tournament_id),
            event=LEADERBOARD_CHANGED,
            payload={"tournament_id": str(tournament_id), "round_id": str(round_id)},
        )

    async def _broadcast(self, *, topic: str, event: str, payload: dict[str, str]) -> None:
        try:
            response = await (self._client or get_http_client()).post(
                self._endpoint,
                headers={"apikey": self._api_key, "Authorization": f"Bearer {self._api_key}"},
                json={"messages": [{"topic": topic, "event": event, "payload": payload}]},
            )
            response.raise_for_status()
        except httpx.HTTPError:
            # Deliberately broad in effect but narrow in type: connection, timeout
            # and non-2xx all mean the same thing here — clients will refetch on
            # their own schedule instead. Anything that isn't an HTTP problem is a
            # bug and should still surface.
            logger.warning("Realtime broadcast to %s failed", topic, exc_info=True)


def build_notifier() -> RealtimeNotifier:
    """A real notifier when Supabase is configured, a no-op when it isn't.

    Both settings are needed: the URL to reach and the service key to authenticate
    with. A partial or still-placeholder configuration is treated as "off" rather
    than as an error, because the app is meant to boot on `.env.example` and the
    whole test suite runs with no Supabase project at all.
    """
    url, key = settings.supabase_url, settings.supabase_key
    if not is_configured(url) or not is_configured(key):
        return NullNotifier()
    assert url is not None and key is not None  # narrowed by is_configured
    return SupabaseNotifier(url, key)
