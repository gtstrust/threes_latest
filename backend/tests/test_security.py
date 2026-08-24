"""Token verification: the ES256 path a real project uses, and the HS256 one we sign ourselves.

Both matter. A browser coming from magic-link login presents an ES256 token
signed by Supabase's private key, verified against the project's JWKS. The test
suite and `scripts/demo_tournament.py` present HS256 tokens they signed against
a shared secret, because there is no login endpoint here to call — so that path
has to keep working with no Supabase project configured at all.

The JWKS is served from an in-process keypair over `httpx.MockTransport`; nothing
here touches the network.
"""

import time
import uuid

import httpx
import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import ec
from fastapi import HTTPException

from app.core import security
from app.core.config import settings
from app.core.security import decode_supabase_jwt

SECRET = "dev-local-only-secret-change-me!"
PROJECT_URL = "https://abc123.supabase.co"
KID = "505bee7a-test-key"


# --- A signing key, and a JWKS endpoint that publishes it -------------------


def _keypair():
    private = ec.generate_private_key(ec.SECP256R1())
    jwk = jwt.algorithms.ECAlgorithm.to_jwk(private.public_key(), as_dict=True)
    jwk.update({"kid": KID, "use": "sig", "alg": "ES256"})
    return private, jwk


@pytest.fixture
def signing_key(monkeypatch):
    """Point the app at a project whose JWKS we serve ourselves."""
    private, jwk = _keypair()
    monkeypatch.setattr(settings, "supabase_url", PROJECT_URL)
    security.jwks_cache.clear()

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/auth/v1/.well-known/jwks.json"
        return httpx.Response(200, json={"keys": [jwk]})

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    monkeypatch.setattr(security, "get_http_client", lambda: client)
    yield private
    security.jwks_cache.clear()


def _es256(private, *, kid: str = KID, **overrides) -> str:
    payload = {"sub": str(uuid.uuid4()), "email": "player@example.com", "aud": "authenticated"}
    payload.update(overrides)
    return jwt.encode(payload, private, algorithm="ES256", headers={"kid": kid})


def _hs256(secret: str = SECRET, **overrides) -> str:
    payload = {"sub": str(uuid.uuid4()), "email": "test@example.com", "aud": "authenticated"}
    payload.update(overrides)
    return jwt.encode(payload, secret, algorithm="HS256")


# --- The real path: ES256 against the project's JWKS ------------------------


async def test_a_real_supabase_token_is_verified(signing_key):
    user = await decode_supabase_jwt(_es256(signing_key))

    assert user.email == "player@example.com"


async def test_a_token_signed_by_someone_else_is_rejected(signing_key):
    """Right kid, wrong private key — the shape of a forged token."""
    impostor = ec.generate_private_key(ec.SECP256R1())

    with pytest.raises(HTTPException) as exc:
        await decode_supabase_jwt(_es256(impostor))

    assert exc.value.status_code == 401


async def test_an_unknown_kid_is_rejected(signing_key):
    with pytest.raises(HTTPException) as exc:
        await decode_supabase_jwt(_es256(signing_key, kid="not-a-key-we-know"))

    assert exc.value.status_code == 401


async def test_an_expired_token_is_rejected(signing_key):
    with pytest.raises(HTTPException) as exc:
        await decode_supabase_jwt(_es256(signing_key, exp=int(time.time()) - 60))

    assert exc.value.status_code == 401


async def test_the_wrong_audience_is_rejected(signing_key):
    with pytest.raises(HTTPException) as exc:
        await decode_supabase_jwt(_es256(signing_key, aud="anon"))

    assert exc.value.status_code == 401


async def test_keys_are_fetched_once_and_reused(signing_key, monkeypatch):
    """A JWKS fetch per request would put a network round trip on every call."""
    private, jwk = _keypair()
    fetches = []

    def handler(request: httpx.Request) -> httpx.Response:
        fetches.append(request)
        return httpx.Response(200, json={"keys": [jwk]})

    monkeypatch.setattr(
        security,
        "get_http_client",
        lambda: httpx.AsyncClient(transport=httpx.MockTransport(handler)),
    )
    security.jwks_cache.clear()

    for _ in range(3):
        await decode_supabase_jwt(_es256(private))

    assert len(fetches) == 1


async def test_an_unreachable_jwks_is_not_the_callers_fault(monkeypatch):
    """503, not 401: the token may be fine and we simply cannot check it.

    Answering 401 would send a player back to log in again over an outage that
    has nothing to do with their credentials.
    """
    private, _jwk = _keypair()
    monkeypatch.setattr(settings, "supabase_url", PROJECT_URL)
    security.jwks_cache.clear()

    def unreachable(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("no route to host")

    monkeypatch.setattr(
        security,
        "get_http_client",
        lambda: httpx.AsyncClient(transport=httpx.MockTransport(unreachable)),
    )

    with pytest.raises(HTTPException) as exc:
        await decode_supabase_jwt(_es256(private))

    assert exc.value.status_code == 503
    security.jwks_cache.clear()


# --- The offline path: HS256, no Supabase project at all --------------------


async def test_decode_valid_token(monkeypatch):
    monkeypatch.setattr(settings, "supabase_url", None)
    monkeypatch.setattr(settings, "supabase_jwt_secret", SECRET)

    user = await decode_supabase_jwt(_hs256())

    assert user.email == "test@example.com"


async def test_decode_bad_signature(monkeypatch):
    monkeypatch.setattr(settings, "supabase_url", None)
    monkeypatch.setattr(settings, "supabase_jwt_secret", SECRET)

    with pytest.raises(HTTPException) as exc:
        await decode_supabase_jwt(_hs256("wrong-secret"))

    assert exc.value.status_code == 401


async def test_decode_missing_secret(monkeypatch):
    """500, not 401 — an unconfigured server is not a bad token."""
    monkeypatch.setattr(settings, "supabase_url", None)
    monkeypatch.setattr(settings, "supabase_jwt_secret", None)

    with pytest.raises(HTTPException) as exc:
        await decode_supabase_jwt(_hs256())

    assert exc.value.status_code == 500


async def test_a_shared_secret_token_still_works_with_a_project_configured(
    signing_key, monkeypatch
):
    """The demo script keeps working against a server wired to a real project.

    Its tokens carry no `kid`, so they never reach the JWKS path.
    """
    monkeypatch.setattr(settings, "supabase_jwt_secret", SECRET)

    user = await decode_supabase_jwt(_hs256())

    assert user.email == "test@example.com"


async def test_a_malformed_token_is_rejected(monkeypatch):
    monkeypatch.setattr(settings, "supabase_jwt_secret", SECRET)

    with pytest.raises(HTTPException) as exc:
        await decode_supabase_jwt("not-a-jwt")

    assert exc.value.status_code == 401
