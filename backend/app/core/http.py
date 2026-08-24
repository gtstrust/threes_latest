"""The process-wide outbound HTTP client.

Lives in `core` rather than beside its first caller because two layers need it —
`core/security.py` fetches the Supabase JWKS, `services/realtime.py` posts the
leaderboard broadcast — and a service importing into core, or core importing out
into services, would invert the one-way layering the rest of the app keeps to.

One client, not one per call: both callers run on every scored hole or every
authenticated request, and a fresh connection each time would throw away pooling
and TLS session reuse on exactly the paths that matter most.
"""

import httpx

# Generous enough for a JWKS fetch on a cold cache, short enough that a hung
# third party can't pin a task indefinitely. Individual calls can pass their own.
DEFAULT_TIMEOUT_SECONDS = 5.0

_client: httpx.AsyncClient | None = None


def get_http_client() -> httpx.AsyncClient:
    """The shared client, built on first use.

    Lazy for the same reason `get_engine` is (`app/core/db.py`): constructing it
    at import time binds it to whatever event loop happens to be current, which
    for the test suite is a different one per test.
    """
    global _client
    if _client is None:
        _client = httpx.AsyncClient(timeout=DEFAULT_TIMEOUT_SECONDS)
    return _client
