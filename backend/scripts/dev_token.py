#!/usr/bin/env python3
"""Print a bearer token for local work — /docs, curl, or a REST client.

Answers the question the Swagger *Authorize* dialog raises and cannot answer for
itself: where does the token come from, when the API has no login endpoint? It
comes from Supabase in real use; here it is signed locally with
`SUPABASE_JWT_SECRET`, the same way `tests/conftest.py` does.

    python scripts/dev_token.py --email you@example.com
    curl localhost:8000/auth/me -H "Authorization: Bearer $(python scripts/dev_token.py -e me@x.dev)"

The token proves identity, not existence: a fresh one names a player who has no
`players` row yet, so `POST /players` still has to be called once before anything
under /players will find them.

Development only. A token signed here is accepted by any server that trusts the
same secret, so this refuses to run unless ENVIRONMENT says development — and the
secret is a locally generated random string, never a value from a Supabase
project (see backend/CLAUDE.md).
"""

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from _dev_auth import mint_token, read_env_file, resolve_secret  # noqa: E402

DEFAULT_ENV_FILE = Path(__file__).resolve().parent.parent / ".env"


def resolve_environment(env_file: Path) -> str:
    """The configured environment, from the process env or the .env file."""
    import os

    return os.environ.get("ENVIRONMENT") or read_env_file(env_file).get(
        "ENVIRONMENT", "development"
    )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("-e", "--email", required=True, help="Email to put in the token")
    parser.add_argument("--jwt-secret", help="Override SUPABASE_JWT_SECRET")
    parser.add_argument(
        "--env-file", type=Path, default=DEFAULT_ENV_FILE, help="Where to look for the secret"
    )
    args = parser.parse_args()

    environment = resolve_environment(args.env_file)
    if environment != "development":
        sys.exit(
            f"Refusing to mint a token with ENVIRONMENT={environment!r}. This is a "
            "development helper; real tokens come from Supabase Auth."
        )

    print(mint_token(resolve_secret(args), args.email))


if __name__ == "__main__":
    main()
