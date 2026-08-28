#!/usr/bin/env python3
"""Mint a bearer token for testing this API locally — no Supabase project needed.

There is no login endpoint to call here: Supabase hands tokens straight to the
client, and this API only ever verifies one (`app/core/security.py`). So
`GET /auth/me` can't be where a token comes from — it requires one already.

Locally, without a real Supabase project, `decode_supabase_jwt` also accepts a
token signed with the same `SUPABASE_JWT_SECRET` the server is running with
(HS256) — exactly what `tests/conftest.py` and `scripts/demo_tournament.py`
already do to authenticate. This script mints one of those standalone, to paste
into curl, httpie, or the "Authorize" button at /docs.

    python scripts/mint_token.py you@example.com

Against a real Supabase project this won't work — those tokens are ES256,
verified against the project's JWKS instead, and are only ever issued by
Supabase Auth itself (magic link) to a real client.
"""

from __future__ import annotations

import argparse
import sys
import uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from demo_tournament import mint_token, resolve_secret  # noqa: E402

BACKEND_ROOT = Path(__file__).resolve().parent.parent


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "email",
        nargs="?",
        default=f"dev-{uuid.uuid4().hex[:8]}@threes.example",
        help="email claim carried by the token (default: a random @threes.example address)",
    )
    parser.add_argument("--jwt-secret", default=None, help="overrides the environment and .env")
    parser.add_argument(
        "--env-file", type=Path, default=BACKEND_ROOT / ".env", help="where to look for the secret"
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    secret = resolve_secret(args)
    print(mint_token(secret, args.email))
    return 0


if __name__ == "__main__":
    sys.exit(main())
