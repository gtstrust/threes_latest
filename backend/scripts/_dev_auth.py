"""Signing the JWTs Supabase would have issued, for local work.

There is no login endpoint to call — Supabase hands tokens straight to the client
and this API only verifies them (`app/core/security.py`). So anything that drives
the API without a browser has to sign its own, which the HS256 branch of
`decode_supabase_jwt` exists for. That branch is not a legacy path: deleting it
takes the test suite and the demo script with it.

Shared by `dev_token.py` and `demo_tournament.py` so the claims they mint cannot
drift apart, and so `tests/conftest.py` has exactly one shape to match.
"""

import argparse
import os
import sys
import uuid
from pathlib import Path

import jwt

AUDIENCE = "authenticated"


def mint_token(secret: str, email: str) -> str:
    """Sign the JWT Supabase would have issued for `email`.

    No `kid` header, which is what tells `decode_supabase_jwt` to verify against
    the shared secret rather than fetching a project's public keys.
    """
    return jwt.encode(
        {"sub": str(uuid.uuid4()), "email": email, "aud": AUDIENCE},
        secret,
        algorithm="HS256",
    )


def read_env_file(path: Path) -> dict[str, str]:
    """Pull KEY=value pairs out of a .env file. Absent file is not an error."""
    values: dict[str, str] = {}
    if not path.exists():
        return values
    for line in path.read_text().splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in stripped:
            continue
        key, _, value = stripped.partition("=")
        values[key.strip()] = value.strip().strip('"').strip("'")
    return values


def resolve_secret(args: argparse.Namespace) -> str:
    """--jwt-secret, else the environment, else backend/.env."""
    if getattr(args, "jwt_secret", None):
        return str(args.jwt_secret)
    from_env = os.environ.get("SUPABASE_JWT_SECRET")
    if from_env:
        return from_env
    from_file = read_env_file(args.env_file).get("SUPABASE_JWT_SECRET")
    if from_file:
        return from_file
    sys.exit(
        f"No SUPABASE_JWT_SECRET found. Pass --jwt-secret, export it, or put it in {args.env_file}."
    )
