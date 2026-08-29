"""Reminding a field about an event.

Two ways in — the organiser's button and the scheduled sweep — and the properties
that matter are the same for both: nobody without an account is written to, a
failed send doesn't fail the request, and running the sweep twice doesn't mail
anyone twice.

The suite never sends: `conftest.py` installs `NullMailer` for every test, and
the ones here that assert on messages install a recorder explicitly.
"""

from datetime import UTC, datetime, timedelta

import pytest
from httpx import AsyncClient

from app.core.config import settings
from app.core.deps import get_mailer
from app.main import app
from app.models.tournament import TournamentStatus
from tests.conftest import FailingMailer
from tests.helpers import add_virtual, course, player, set_status

CRON_SECRET = "test-cron-secret"


async def _event(
    client: AsyncClient, make_token, organiser, *, scheduled_in: timedelta | None = None
) -> str:
    course_id = await course(client, organiser, hole_count=3)
    payload: dict[str, object] = {"name": "Acme Corporate Day", "course_id": course_id}
    if scheduled_in is not None:
        payload["scheduled_at"] = (datetime.now(UTC) + scheduled_in).isoformat()
    created = await client.post("/tournaments", headers=organiser, json=payload)
    assert created.status_code == 201, created.text
    tournament_id = created.json()["id"]
    await set_status(client, organiser, tournament_id, TournamentStatus.REGISTRATION_OPEN)
    return tournament_id


async def _with_field(client: AsyncClient, make_token, organiser, tournament_id: str) -> None:
    """One real player and one virtual, so the difference between them shows."""
    guest = await player(client, make_token, "guest@example.com")
    joined = await client.post(f"/tournaments/{tournament_id}/participants", headers=guest, json={})
    assert joined.status_code == 201, joined.text
    await add_virtual(client, organiser, tournament_id, "No Phone")


# --- The organiser's own send ----------------------------------------------


async def test_the_organiser_can_mail_the_field(client, make_token, mailer):
    organiser = await player(client, make_token, "organiser@example.com")
    tournament_id = await _event(client, make_token, organiser)
    await _with_field(client, make_token, organiser, tournament_id)

    response = await client.post(f"/tournaments/{tournament_id}/reminders", headers=organiser)

    assert response.status_code == 200, response.text
    assert response.json() == {"sent": 1}
    # One real player in the field; the virtual one has nowhere to write to.
    assert [message.to for message in mailer.messages] == ["guest@example.com"]


async def test_a_virtual_player_is_never_written_to(client, make_token, mailer):
    """They have no account by definition — somebody else carries their card."""
    organiser = await player(client, make_token, "organiser@example.com")
    tournament_id = await _event(client, make_token, organiser)
    for name in ("A", "B", "C"):
        await add_virtual(client, organiser, tournament_id, name)

    await client.post(f"/tournaments/{tournament_id}/reminders", headers=organiser)

    assert mailer.messages == []


async def test_the_message_carries_the_event_and_a_link(client, make_token, mailer):
    organiser = await player(client, make_token, "organiser@example.com")
    tournament_id = await _event(client, make_token, organiser, scheduled_in=timedelta(days=2))
    await _with_field(client, make_token, organiser, tournament_id)

    await client.post(f"/tournaments/{tournament_id}/reminders", headers=organiser)

    message = mailer.messages[0]
    assert "Acme Corporate Day" in message.subject
    assert tournament_id in message.text
    assert tournament_id in message.html
    # Both bodies say the same thing about when it is.
    assert "Acme Corporate Day" in message.text


async def test_only_the_organiser_can_send_one(client, make_token, mailer):
    organiser = await player(client, make_token, "organiser@example.com")
    tournament_id = await _event(client, make_token, organiser)
    intruder = await player(client, make_token, "intruder@example.com")

    refused = await client.post(f"/tournaments/{tournament_id}/reminders", headers=intruder)

    assert refused.status_code == 403
    assert mailer.messages == []


async def test_a_failed_send_does_not_fail_the_request(client, make_token):
    """The organiser has already done the thing they meant to do."""
    failing = FailingMailer()
    app.dependency_overrides[get_mailer] = lambda: failing

    organiser = await player(client, make_token, "organiser@example.com")
    tournament_id = await _event(client, make_token, organiser)
    await _with_field(client, make_token, organiser, tournament_id)

    response = await client.post(f"/tournaments/{tournament_id}/reminders", headers=organiser)

    assert response.status_code == 200
    # Reported honestly as nothing sent, rather than as a failure or a lie.
    assert response.json() == {"sent": 0}
    assert failing.attempts == 1


async def test_a_fun_round_has_no_reminders(client, make_token, mailer):
    """It is arranged in a group chat an hour beforehand; mail would be strange."""
    host = await player(client, make_token, "host@example.com")
    created = await client.post("/fun-rounds", headers=host, json={"name": "Saturday nine"})
    fun_round_id = created.json()["id"]

    refused = await client.post(f"/tournaments/{fun_round_id}/reminders", headers=host)

    assert refused.status_code == 404
    assert mailer.messages == []


# --- The scheduled sweep ----------------------------------------------------


@pytest.fixture
def cron(monkeypatch):
    monkeypatch.setattr(settings, "cron_secret", CRON_SECRET)
    return {"X-Cron-Key": CRON_SECRET}


async def test_the_sweep_mails_an_event_happening_tomorrow(client, make_token, mailer, cron):
    organiser = await player(client, make_token, "organiser@example.com")
    tournament_id = await _event(client, make_token, organiser, scheduled_in=timedelta(hours=12))
    await _with_field(client, make_token, organiser, tournament_id)

    response = await client.post("/internal/reminders/sweep", headers=cron)

    assert response.status_code == 200, response.text
    assert response.json() == {"events_reminded": 1}
    assert [message.to for message in mailer.messages] == ["guest@example.com"]


async def test_the_sweep_is_idempotent(client, make_token, mailer, cron):
    """A run that fails halfway through has to be safe to run again."""
    organiser = await player(client, make_token, "organiser@example.com")
    tournament_id = await _event(client, make_token, organiser, scheduled_in=timedelta(hours=12))
    await _with_field(client, make_token, organiser, tournament_id)

    first = await client.post("/internal/reminders/sweep", headers=cron)
    second = await client.post("/internal/reminders/sweep", headers=cron)

    assert first.json() == {"events_reminded": 1}
    assert second.json() == {"events_reminded": 0}
    assert len(mailer.messages) == 1


async def test_the_organisers_send_does_not_satisfy_the_sweep(client, make_token, mailer, cron):
    """Different kinds on purpose: pressing the button is not the day-before mail."""
    organiser = await player(client, make_token, "organiser@example.com")
    tournament_id = await _event(client, make_token, organiser, scheduled_in=timedelta(hours=12))
    await _with_field(client, make_token, organiser, tournament_id)

    await client.post(f"/tournaments/{tournament_id}/reminders", headers=organiser)
    swept = await client.post("/internal/reminders/sweep", headers=cron)

    assert swept.json() == {"events_reminded": 1}
    assert len(mailer.messages) == 2


async def test_an_event_with_no_date_is_never_swept(client, make_token, mailer, cron):
    """It cannot be "coming up" if nobody has said when it is."""
    organiser = await player(client, make_token, "organiser@example.com")
    tournament_id = await _event(client, make_token, organiser)
    await _with_field(client, make_token, organiser, tournament_id)

    response = await client.post("/internal/reminders/sweep", headers=cron)

    assert response.json() == {"events_reminded": 0}
    assert mailer.messages == []


async def test_an_event_further_out_than_the_window_waits(client, make_token, mailer, cron):
    organiser = await player(client, make_token, "organiser@example.com")
    tournament_id = await _event(client, make_token, organiser, scheduled_in=timedelta(days=9))
    await _with_field(client, make_token, organiser, tournament_id)

    response = await client.post("/internal/reminders/sweep", headers=cron)

    assert response.json() == {"events_reminded": 0}


async def test_an_event_already_being_played_is_not_reminded(client, make_token, mailer, cron):
    """They are on the course. A reminder is noise at best."""
    organiser = await player(client, make_token, "organiser@example.com")
    tournament_id = await _event(client, make_token, organiser, scheduled_in=timedelta(hours=2))
    await _with_field(client, make_token, organiser, tournament_id)
    await set_status(client, organiser, tournament_id, TournamentStatus.REGISTRATION_CLOSED)
    drawn = await client.post(f"/tournaments/{tournament_id}/rounds", headers=organiser)
    assert drawn.status_code == 201, drawn.text

    response = await client.post("/internal/reminders/sweep", headers=cron)

    assert response.json() == {"events_reminded": 0}


# --- Guarding the sweep -----------------------------------------------------


async def test_the_sweep_refuses_a_wrong_key(client, cron, mailer):
    response = await client.post("/internal/reminders/sweep", headers={"X-Cron-Key": "nope"})

    assert response.status_code == 403
    assert mailer.messages == []


async def test_the_sweep_refuses_a_missing_key(client, cron, mailer):
    response = await client.post("/internal/reminders/sweep")

    assert response.status_code == 403


async def test_an_unconfigured_sweep_is_closed_not_open(client, monkeypatch, mailer):
    """A route that mails an entire field must not default to open."""
    monkeypatch.setattr(settings, "cron_secret", None)

    response = await client.post("/internal/reminders/sweep", headers={"X-Cron-Key": "anything"})

    # 404 rather than 503: an unconfigured internal route should not advertise
    # that it exists and is merely switched off.
    assert response.status_code == 404
    assert mailer.messages == []
