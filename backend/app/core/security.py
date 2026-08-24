"""Verifying the JWTs Supabase issues.

Two algorithms, because this backend has two kinds of caller. A real Supabase
project signs with **ES256** and publishes the public key at its JWKS endpoint —
that is what a browser gets from magic-link login. But `tests/conftest.py` and
`scripts/demo_tournament.py` mint their own **HS256** tokens against a shared
secret, because Supabase issues tokens directly to clients and there is no login
endpoint here to call. Both must work, and neither is a legacy path.

The token itself says which is which: an asymmetric token carries a `kid` naming
the key that signed it, and a shared-secret one has nothing to name.
"""

import asyncio
import time
from typing import Any
from uuid import UUID

import httpx
import jwt
from fastapi import HTTPException, status
from pydantic import BaseModel

from app.core.config import settings
from app.core.http import get_http_client

# Supabase rotates signing keys rarely, and an unknown `kid` forces a refetch
# anyway, so this only bounds how long a *revoked* key stays accepted.
JWKS_CACHE_TTL_SECONDS = 600.0

AUDIENCE = "authenticated"


class CurrentUser(BaseModel):
    """The authenticated principal, derived directly from a verified Supabase JWT."""

    id: UUID
    email: str | None = None


class _JwksCache:
    """The project's public signing keys, kept for `JWKS_CACHE_TTL_SECONDS`.

    Not `jwt.PyJWKClient`, which fetches with blocking `urllib` — inside an async
    request that stalls the whole event loop, not just the caller. The lock means
    a cold cache under load fetches once rather than once per in-flight request.
    """

    def __init__(self) -> None:
        self._keys: dict[str, Any] = {}
        self._fetched_at = 0.0
        self._lock = asyncio.Lock()

    async def get(self, kid: str, url: str) -> Any:
        """The key named by `kid`, refetching once if it isn't already known.

        An unknown `kid` is the normal signal that keys have rotated, so it forces
        a refetch even on a warm cache — otherwise every request would fail for up
        to the whole TTL after a rotation.
        """
        stale = time.monotonic() - self._fetched_at > JWKS_CACHE_TTL_SECONDS
        if kid not in self._keys or stale:
            await self._refresh(url)
        key = self._keys.get(kid)
        if key is None:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid or expired token",
            )
        return key

    async def _refresh(self, url: str) -> None:
        async with self._lock:
            # Another request may have refreshed while we waited for the lock.
            if time.monotonic() - self._fetched_at <= JWKS_CACHE_TTL_SECONDS and self._keys:
                return
            try:
                response = await get_http_client().get(url)
                response.raise_for_status()
                jwk_set = jwt.PyJWKSet.from_dict(response.json())
            except (httpx.HTTPError, jwt.PyJWKSetError, ValueError) as exc:
                # Not a 401: the caller's token may be perfectly good and we simply
                # cannot reach the authority that would prove it. Saying "invalid
                # token" here would send a user chasing their own login.
                raise HTTPException(
                    status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                    detail="Could not reach Supabase to verify the token; try again",
                ) from exc

            self._keys = {key.key_id: key.key for key in jwk_set.keys if key.key_id}
            self._fetched_at = time.monotonic()

    def clear(self) -> None:
        """Drop everything. For tests, which must not inherit another test's keys."""
        self._keys = {}
        self._fetched_at = 0.0


jwks_cache = _JwksCache()


async def decode_supabase_jwt(token: str) -> CurrentUser:
    """Verify a Supabase-issued access token and return the identity it carries.

    Raises:
        HTTPException: 401 if the token is malformed, unsigned by a key we trust,
            or expired. 500 if neither verification path is configured — a config
            error is not an auth failure. 503 if the JWKS endpoint is unreachable.
    """
    try:
        header = jwt.get_unverified_header(token)
    except jwt.InvalidTokenError as exc:
        raise _unauthorized() from exc

    kid = header.get("kid")
    jwks_url = settings.supabase_jwks_url

    if kid and jwks_url:
        payload = await _decode_asymmetric(token, kid=kid, jwks_url=jwks_url)
    else:
        payload = _decode_shared_secret(token)

    subject = payload.get("sub")
    if subject is None:
        raise _unauthorized()

    return CurrentUser(id=UUID(subject), email=payload.get("email"))


async def _decode_asymmetric(token: str, *, kid: str, jwks_url: str) -> dict[str, Any]:
    """The real path: a browser's token, signed by the project's private key."""
    key = await jwks_cache.get(kid, jwks_url)
    try:
        decoded: dict[str, Any] = jwt.decode(
            token, key, algorithms=["ES256", "RS256"], audience=AUDIENCE
        )
    except jwt.InvalidTokenError as exc:
        raise _unauthorized() from exc
    return decoded


def _decode_shared_secret(token: str) -> dict[str, Any]:
    """The offline path: a token the test suite or the demo script signed itself."""
    if not settings.supabase_jwt_secret:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Auth is not configured: SUPABASE_JWT_SECRET is unset",
        )

    try:
        decoded: dict[str, Any] = jwt.decode(
            token, settings.supabase_jwt_secret, algorithms=["HS256"], audience=AUDIENCE
        )
    except jwt.InvalidTokenError as exc:
        raise _unauthorized() from exc
    return decoded


def _unauthorized() -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Invalid or expired token",
    )
