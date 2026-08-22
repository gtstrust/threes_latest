import uuid

import jwt
import pytest
from fastapi import HTTPException

from app.core.config import settings
from app.core.security import decode_supabase_jwt

SECRET = "dev-local-only-secret-change-me!"


def _token(**overrides):
    payload = {"sub": str(uuid.uuid4()), "email": "test@example.com", "aud": "authenticated"}
    payload.update(overrides)
    return jwt.encode(payload, SECRET, algorithm="HS256")


def test_decode_valid_token(monkeypatch):
    monkeypatch.setattr(settings, "supabase_jwt_secret", SECRET)
    user = decode_supabase_jwt(_token())
    assert user.email == "test@example.com"


def test_decode_bad_signature(monkeypatch):
    monkeypatch.setattr(settings, "supabase_jwt_secret", SECRET)
    bad_token = jwt.encode(
        {"sub": str(uuid.uuid4()), "aud": "authenticated"}, "wrong-secret", algorithm="HS256"
    )
    with pytest.raises(HTTPException) as exc_info:
        decode_supabase_jwt(bad_token)
    assert exc_info.value.status_code == 401


def test_decode_missing_secret(monkeypatch):
    monkeypatch.setattr(settings, "supabase_jwt_secret", None)
    with pytest.raises(HTTPException) as exc_info:
        decode_supabase_jwt(_token())
    assert exc_info.value.status_code == 500
