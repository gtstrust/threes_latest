#!/usr/bin/env python3
"""Check a DATABASE_URL before it becomes a Fly secret.

Deploying this backend has one step with no feedback loop: `fly secrets set
DATABASE_URL=...` is accepted whatever it says, and the first thing that
disagrees is `alembic upgrade head` running on a throwaway machine four minutes
later, with its traceback in `fly logs` rather than on your terminal. The first
real deploy spent seven releases there, on three different mistakes.

All three are visible in under a second from a laptop, which is what this does.

    python scripts/check_db_url.py                  # prompts, nothing echoed
    python scripts/check_db_url.py --from-env       # the local .env
    python scripts/check_db_url.py --connect        # actually open it

**The URL is read from stdin, never from an argument.** A connection string on a
command line is in your shell history and in every `ps` on the machine, and this
one carries the database password.

Nothing is printed with the password in it — the URL is echoed back through
SQLAlchemy's own redaction, so what you see is what asyncpg parsed rather than
what you believe you typed. That distinction is the point: two of the seven
failures were a URL that parsed into something other than it looked like.
"""

import argparse
import asyncio
import getpass
import os
import socket
import sys
from pathlib import Path

from sqlalchemy.engine import URL, make_url

BACKEND_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_ENV_FILE = BACKEND_ROOT / ".env"

# The driver this project installs, and the only one that can work.
EXPECTED_DRIVER = "postgresql+asyncpg"

# Supabase's session pooler. The transaction pooler on 6543 hands out a
# different backend connection per statement, and app/core/db.py builds its
# engine without `statement_cache_size=0` — so asyncpg's prepared statements
# vanish underneath it, intermittently, under load.
SESSION_POOLER_PORT = 5432
TRANSACTION_POOLER_PORT = 6543

OK = "  ok  "
WARN = " warn "
FAIL = " fail "

# Counted here rather than returned by each check, so a warning cannot be raised
# and then quietly left out of the summary — which is how a report ends up
# saying "looks good" underneath two warnings.
_warnings = 0


def report(status: str, message: str) -> None:
    global _warnings
    if status == WARN:
        _warnings += 1
    print(f"[{status}] {message}")


def read_url(from_env: bool, env_file: Path) -> str:
    """Get the URL from the .env file or from stdin, never from argv."""
    if from_env:
        if not env_file.exists():
            sys.exit(f"No such file: {env_file}")
        for line in env_file.read_text().splitlines():
            key, separator, value = line.partition("=")
            if separator and key.strip() == "DATABASE_URL":
                return value.strip().strip("'\"")
        sys.exit(f"No DATABASE_URL in {env_file}")

    if sys.stdin.isatty():
        return getpass.getpass("DATABASE_URL (not echoed): ").strip()
    return sys.stdin.read().strip()


def check_driver(raw: str) -> bool:
    """The scheme names asyncpg, rather than naming no driver at all.

    A bare `postgresql://` is what the Supabase dashboard prints, and SQLAlchemy
    resolves it to psycopg2 — a package this project has never depended on. The
    app coerces it and warns (`app/core/config.py`); the right value avoids the
    warning and the ambiguity together.
    """
    if raw.startswith(f"{EXPECTED_DRIVER}://"):
        report(OK, f"driver is {EXPECTED_DRIVER}")
        return True
    if raw.startswith(("postgresql://", "postgres://")):
        report(WARN, "no driver named — the app will coerce this to asyncpg and warn")
        report(WARN, f"  prefer {EXPECTED_DRIVER}://")
        return True
    report(FAIL, f"driver is not asyncpg: {raw.split('://', 1)[0]}://")
    return False


def check_shape(url: URL) -> bool:
    """The parsed parts are present and are not still placeholders.

    Printed back through SQLAlchemy so the report describes what asyncpg will
    actually use. An unencoded `@` or `:` in the password re-splits the string,
    and the result looks nothing like what was pasted.
    """
    report(OK, f"parsed as {url.render_as_string(hide_password=True)}")

    healthy = True
    for label, value in (
        ("host", url.host),
        ("user", url.username),
        ("database", url.database),
    ):
        if not value:
            report(FAIL, f"no {label} in the URL")
            healthy = False
        elif "<" in value or ">" in value:
            report(FAIL, f"{label} still holds a placeholder: {value}")
            healthy = False

    if url.password and ("@" in url.password or "/" in url.password):
        report(WARN, "the password parsed with an @ or / in it — percent-encode those")

    return healthy


def check_port(url: URL) -> bool:
    if url.port == TRANSACTION_POOLER_PORT:
        report(FAIL, f"port {TRANSACTION_POOLER_PORT} is the transaction pooler")
        report(FAIL, f"  use the session pooler on {SESSION_POOLER_PORT}")
        return False
    report(OK, f"port {url.port or SESSION_POOLER_PORT}")
    return True


def check_dns(host: str) -> bool:
    """The host resolves at all.

    `socket.gaierror: [Errno -2] Name or service not known` in a release log is
    this, and it says nothing about which name failed.
    """
    try:
        addresses = socket.getaddrinfo(host, None)
    except socket.gaierror as error:
        report(FAIL, f"{host} does not resolve — {error}")
        return False

    families = {socket.AddressFamily(info[0]).name for info in addresses}
    report(OK, f"{host} resolves ({', '.join(sorted(families))})")
    if families == {"AF_INET6"}:
        report(WARN, "  IPv6 only — reachable from Fly, but not from every CI runner")
    return True


async def try_connect(url: URL) -> bool:
    """Open it for real and ask the server what it is.

    The one check that cannot be done by inspection: a URL can be well-formed,
    resolvable and still rejected — `(ENOTFOUND) tenant/user postgres.<ref> not
    found` is the pooler saying the project is not on that fleet.
    """
    from sqlalchemy import pool, text
    from sqlalchemy.ext.asyncio import create_async_engine

    engine = create_async_engine(url, poolclass=pool.NullPool)
    try:
        async with engine.connect() as connection:
            version = await connection.scalar(text("SELECT version()"))
        report(OK, f"connected — {str(version).split(' on ')[0]}")
        return True
    except Exception as error:  # noqa: BLE001 — every failure here is worth showing
        report(FAIL, f"{type(error).__name__}: {error}")
        return False
    finally:
        await engine.dispose()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "--from-env",
        action="store_true",
        help=f"read DATABASE_URL from {DEFAULT_ENV_FILE} instead of prompting",
    )
    parser.add_argument(
        "--connect",
        action="store_true",
        help="also open the connection and run SELECT version()",
    )
    parser.add_argument("--env-file", type=Path, default=DEFAULT_ENV_FILE)
    args = parser.parse_args()

    raw = read_url(args.from_env, args.env_file)
    if not raw:
        sys.exit("Nothing to check.")

    try:
        url = make_url(raw)
    except Exception as error:  # noqa: BLE001 — a bad URL is the thing being reported
        report(FAIL, f"could not parse: {error}")
        return 1

    checks = [check_driver(raw), check_shape(url), check_port(url)]
    if url.host:
        checks.append(check_dns(url.host))

    if args.connect and all(checks):
        checks.append(asyncio.run(try_connect(url)))
    elif args.connect:
        report(WARN, "skipped the connection — fix the above first")

    print()
    if not all(checks):
        print("Not ready to deploy.")
        return 1
    if _warnings:
        print(f"Usable, with {_warnings} warning(s) above worth fixing first.")
    else:
        print("Looks good.")
    print("Set it with:")
    print("  fly secrets set --app threes-api DATABASE_URL='...'")
    return 0


if __name__ == "__main__":
    os.environ.setdefault("PGCONNECT_TIMEOUT", "10")
    sys.exit(main())
