"""What the browser is told when something goes wrong on the server.

This pins **middleware order**, which is the kind of thing that is invisible at
the call site and gets undone by a tidy-up. With the error handler outside CORS —
or registered as `@app.exception_handler(Exception)`, which amounts to the same
thing — a 500 goes out with no `Access-Control-Allow-Origin`, and the browser
reports it as a CORS failure. It did, for an evening: the fun-round screen looked
like a CORS misconfiguration and the CORS configuration was correct.

The second test is the other half. Once the exception is caught it never reaches
uvicorn, so if nothing logs it the server records nothing at all and the only
account of the failure is a browser message describing it wrongly.
"""

import logging

import pytest

from app.core.db import TRANSACTION_POOLER_PORT, asyncpg_connect_args
from app.main import app

# In `settings.cors_origins` by default — the Vite dev server.
ORIGIN = "http://localhost:5173"
EXPLODING_PATH = "/__test_explode"


@pytest.fixture
def exploding_route():
    """A route that raises something nothing in the app catches."""

    async def explode() -> None:
        raise RuntimeError("boom")

    app.add_api_route(EXPLODING_PATH, explode, methods=["GET"])
    yield EXPLODING_PATH
    app.router.routes[:] = [
        route for route in app.router.routes if getattr(route, "path", None) != EXPLODING_PATH
    ]


@pytest.mark.asyncio
async def test_an_unhandled_error_answers_500_with_cors_headers(client, exploding_route):
    response = await client.get(exploding_route, headers={"Origin": ORIGIN})

    assert response.status_code == 500
    # The whole point. Without this the browser never surfaces the 500 at all.
    assert response.headers["access-control-allow-origin"] == ORIGIN
    assert response.json() == {"detail": "Internal Server Error"}


@pytest.mark.asyncio
async def test_an_unhandled_error_is_logged_with_its_route(client, exploding_route, caplog):
    with caplog.at_level(logging.ERROR):
        await client.get(exploding_route, headers={"Origin": ORIGIN})

    record = next(r for r in caplog.records if "Unhandled error" in r.getMessage())
    # Named, so the log says which request died rather than only that one did.
    assert EXPLODING_PATH in record.getMessage()
    assert "GET" in record.getMessage()
    assert record.exc_info is not None


@pytest.mark.asyncio
async def test_a_handled_error_is_untouched(client):
    """A 404 is an answer, not a failure — it must not become a 500."""
    response = await client.get("/nope", headers={"Origin": ORIGIN})

    assert response.status_code == 404
    assert response.headers["access-control-allow-origin"] == ORIGIN


class TestAsyncpgConnectArgs:
    """Which connection strings need prepared statements turned off.

    Only the transaction pooler does. Everything else keeps its backend for the
    life of the connection, so a prepared statement is still there next time.
    """

    def test_the_transaction_pooler_disables_both_caches(self):
        args = asyncpg_connect_args(
            f"postgresql+asyncpg://postgres.abc:pw@aws-0-ap-southeast-2."
            f"pooler.supabase.com:{TRANSACTION_POOLER_PORT}/postgres"
        )

        assert args["statement_cache_size"] == 0
        assert args["prepared_statement_cache_size"] == 0

    def test_the_transaction_pooler_names_statements_uniquely(self):
        # asyncpg numbers them, so two backends behind one pooler both reach for
        # `__asyncpg_stmt_1__`. Names have to differ every time, not just per run.
        args = asyncpg_connect_args(
            f"postgresql+asyncpg://u:p@host:{TRANSACTION_POOLER_PORT}/postgres"
        )
        name_func = args["prepared_statement_name_func"]

        assert name_func() != name_func()

    @pytest.mark.parametrize(
        "url",
        [
            # The session pooler, which is what DEPLOYMENT.md asks for.
            "postgresql+asyncpg://postgres.abc:pw@aws-0-ap-southeast-2.pooler.supabase.com:5432/postgres",
            # docker-compose, published on 5433 to dodge a local Postgres.
            "postgresql+asyncpg://threes:threes@localhost:5433/threes_dev",
            # No port at all — Postgres' default, and not the pooler.
            "postgresql+asyncpg://threes:threes@localhost/threes_dev",
        ],
    )
    def test_everything_else_is_left_alone(self, url):
        assert asyncpg_connect_args(url) == {}

    def test_an_unparseable_url_is_left_to_fail_on_its_own_terms(self):
        # SQLAlchemy's message about a URL it cannot read beats anything guessed
        # here, and this helper is not the place that failure belongs.
        assert asyncpg_connect_args("not-a-url") == {}

    def test_a_password_never_reaches_the_log(self, caplog):
        with caplog.at_level(logging.WARNING):
            asyncpg_connect_args(
                f"postgresql+asyncpg://postgres.abc:hunter2@host:{TRANSACTION_POOLER_PORT}/postgres"
            )

        assert "hunter2" not in caplog.text
        assert str(TRANSACTION_POOLER_PORT) in caplog.text
