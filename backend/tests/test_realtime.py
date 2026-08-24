"""Realtime signalling (M9, ADR-010).

Two halves. The first drives the API and asks *when* a signal is sent — which is
the part a regression would break silently, since nothing in the response body
changes either way. The second drives `SupabaseNotifier` directly over a mock
transport and asks *what* goes on the wire, including that it carries no scores.

The load-bearing test is `test_the_signal_fires_only_after_the_score_is_visible`.
The commit happens in the `get_db` dependency's exit code, and FastAPI runs that
before background tasks — a behaviour of the framework, not of this code, so it
is pinned here rather than trusted.
"""

import json
from uuid import UUID, uuid4

import httpx
import pytest
from httpx import AsyncClient

from app.core.config import settings
from app.models.tournament import TournamentStatus
from app.services.realtime import (
    LEADERBOARD_CHANGED,
    NullNotifier,
    SupabaseNotifier,
    build_notifier,
)
from tests.helpers import drawn_group, player, set_status


async def _submit(client: AsyncClient, headers, group_id, hole_id, strokes, **tie_breaks):
    payload: dict[str, object] = {"strokes": strokes}
    payload.update({key: value for key, value in tie_breaks.items() if value is not None})
    return await client.post(
        f"/groups/{group_id}/holes/{hole_id}/scores", headers=headers, json=payload
    )


# --- When a signal is sent --------------------------------------------------


async def test_scoring_a_hole_signals_its_tournament(client, make_token, notifier):
    organiser = await player(client, make_token, "organiser@example.com")
    ctx = await drawn_group(client, organiser)
    a, b, c = ctx["members"]

    response = await _submit(
        client, organiser, ctx["group_id"], ctx["holes"][0], {a: 3, b: 5, c: 4}
    )

    assert response.status_code == 200, response.text
    assert len(notifier.signals) == 1
    assert notifier.signals[0].tournament_id == ctx["tournament_id"]
    assert notifier.signals[0].round_id == ctx["round_id"]


async def test_the_signal_fires_only_after_the_score_is_visible(client, make_token, notifier):
    """The whole reason the broadcast is a background task rather than an await.

    Sent from inside the service it would fire mid-transaction, and a client fast
    enough to act on it would refetch a leaderboard without the hole that caused
    the refetch. The recorder counts rows on its own connection, so seeing all
    three means the commit had already landed.
    """
    organiser = await player(client, make_token, "organiser@example.com")
    ctx = await drawn_group(client, organiser)
    a, b, c = ctx["members"]

    await _submit(client, organiser, ctx["group_id"], ctx["holes"][0], {a: 3, b: 5, c: 4})

    assert notifier.signals[0].committed_scores == 3


async def test_each_scored_hole_signals_once(client, make_token, notifier):
    organiser = await player(client, make_token, "organiser@example.com")
    ctx = await drawn_group(client, organiser)
    a, b, c = ctx["members"]

    for index, hole in enumerate(ctx["holes"]):
        await _submit(client, organiser, ctx["group_id"], hole, {a: 3 + index, b: 5, c: 4})

    assert len(notifier.signals) == len(ctx["holes"]) == 3


async def test_a_tie_break_answer_signals_again(client, make_token, notifier):
    """The re-submit changes who won the hole, so the board moved twice."""
    organiser = await player(client, make_token, "organiser@example.com")
    ctx = await drawn_group(client, organiser)
    a, b, c = ctx["members"]
    hole = ctx["holes"][0]

    await _submit(client, organiser, ctx["group_id"], hole, {a: 3, b: 3, c: 5})
    decided = await _submit(
        client, organiser, ctx["group_id"], hole, {a: 3, b: 3, c: 5}, closest_to_pin=b
    )

    assert decided.json()["decided_by"] == "closest_to_pin"
    assert len(notifier.signals) == 2


async def test_a_rejected_card_signals_nothing(client, make_token, notifier):
    """Nothing was persisted, so there is nothing for anyone to refetch."""
    organiser = await player(client, make_token, "organiser@example.com")
    ctx = await drawn_group(client, organiser)
    a, b, _c = ctx["members"]

    response = await _submit(client, organiser, ctx["group_id"], ctx["holes"][0], {a: 3, b: 5})

    assert response.status_code == 422
    assert notifier.signals == []


async def test_scoring_a_closed_round_signals_nothing(client, make_token, notifier):
    organiser = await player(client, make_token, "organiser@example.com")
    ctx = await drawn_group(client, organiser)
    a, b, c = ctx["members"]
    await client.post(f"/rounds/{ctx['round_id']}/complete", headers=organiser)

    response = await _submit(
        client, organiser, ctx["group_id"], ctx["holes"][0], {a: 3, b: 5, c: 4}
    )

    assert response.status_code == 409
    assert notifier.signals == []


async def test_reading_the_board_signals_nothing(client, make_token, notifier):
    """Only a write moves the leaderboard. A poll must not trigger more polls."""
    organiser = await player(client, make_token, "organiser@example.com")
    ctx = await drawn_group(client, organiser)
    a, b, c = ctx["members"]
    await _submit(client, organiser, ctx["group_id"], ctx["holes"][0], {a: 3, b: 5, c: 4})
    notifier.signals.clear()

    await client.get(f"/tournaments/{ctx['tournament_id']}/leaderboard", headers=organiser)
    await client.get(f"/groups/{ctx['group_id']}/scores", headers=organiser)
    await set_status(client, organiser, ctx["tournament_id"], TournamentStatus.TOURNAMENT_COMPLETE)

    assert notifier.signals == []


# --- Choosing a notifier ----------------------------------------------------


def test_no_supabase_project_means_no_notifier(monkeypatch):
    monkeypatch.setattr(settings, "supabase_url", None)
    monkeypatch.setattr(settings, "supabase_key", None)

    assert isinstance(build_notifier(), NullNotifier)


@pytest.mark.parametrize(
    ("url", "key"),
    [
        ("https://your-project.supabase.co", "your-service-role-key"),
        ("https://real.supabase.co", "your-service-role-key"),
        ("https://your-project.supabase.co", "real-key"),
    ],
)
def test_env_example_placeholders_count_as_unconfigured(monkeypatch, url, key):
    """Otherwise a fresh `cp .env.example .env` posts to a domain that isn't ours."""
    monkeypatch.setattr(settings, "supabase_url", url)
    monkeypatch.setattr(settings, "supabase_key", key)

    assert isinstance(build_notifier(), NullNotifier)


def test_a_real_project_gets_a_real_notifier(monkeypatch):
    monkeypatch.setattr(settings, "supabase_url", "https://abc123.supabase.co")
    monkeypatch.setattr(settings, "supabase_key", "service-role-key")

    assert isinstance(build_notifier(), SupabaseNotifier)


async def test_the_null_notifier_does_nothing():
    assert await NullNotifier().leaderboard_changed(tournament_id=uuid4(), round_id=uuid4()) is None


# --- What goes on the wire --------------------------------------------------

TOURNAMENT = UUID(int=1)
ROUND = UUID(int=2)


async def _broadcast(handler) -> list[httpx.Request]:
    """Send one signal through a mock transport and hand back what it saw."""
    seen: list[httpx.Request] = []

    def recording(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return handler(request)

    async with httpx.AsyncClient(transport=httpx.MockTransport(recording)) as http:
        notifier = SupabaseNotifier("https://abc123.supabase.co", "service-role-key", client=http)
        await notifier.leaderboard_changed(tournament_id=TOURNAMENT, round_id=ROUND)
    return seen


def _accepted(request: httpx.Request) -> httpx.Response:
    return httpx.Response(202, json={})


async def test_the_broadcast_names_the_tournament_topic():
    request = (await _broadcast(_accepted))[0]

    assert str(request.url) == "https://abc123.supabase.co/realtime/v1/api/broadcast"
    assert request.headers["apikey"] == "service-role-key"

    message = json.loads(request.content)["messages"][0]
    assert message["topic"] == f"tournament:{TOURNAMENT}"
    assert message["event"] == LEADERBOARD_CHANGED


async def test_the_broadcast_carries_no_scores():
    """ADR-010: the signal says the board moved, never what it now says."""
    request = (await _broadcast(_accepted))[0]

    payload = json.loads(request.content)["messages"][0]["payload"]
    assert set(payload) == {"tournament_id", "round_id"}
    assert payload["tournament_id"] == str(TOURNAMENT)
    assert payload["round_id"] == str(ROUND)


def _server_error(request: httpx.Request) -> httpx.Response:
    return httpx.Response(500, json={"error": "boom"})


def _unreachable(request: httpx.Request) -> httpx.Response:
    raise httpx.ConnectError("unreachable")


@pytest.mark.parametrize("handler", [_server_error, _unreachable], ids=["5xx", "unreachable"])
async def test_a_failed_broadcast_never_reaches_the_caller(handler):
    """The hole is already committed by now — a slow Supabase must not undo that.

    Worst case is that clients hear about it on their next poll instead.
    """
    assert await _broadcast(handler) is not None
