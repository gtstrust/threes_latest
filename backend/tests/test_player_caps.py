"""An optional ceiling on the field.

A join link means people can arrive without being invited one at a time, so an
organiser needs a way to stop the field growing past the day they booked. The cap
is opt-in, applies only to players registering themselves, and has to be visible
on the invitation — otherwise it becomes a button that answers 409.
"""

from httpx import AsyncClient

from app.models.tournament import TournamentStatus
from tests.helpers import course, player, set_status


async def _open_tournament(client: AsyncClient, headers, **extra) -> dict:
    course_id = await course(client, headers, hole_count=3)
    created = await client.post(
        "/tournaments",
        headers=headers,
        json={"name": "Acme Corporate Day", "course_id": course_id, **extra},
    )
    assert created.status_code == 201, created.text
    body = created.json()
    await set_status(client, headers, body["id"], TournamentStatus.REGISTRATION_OPEN)
    return body


async def _join(client: AsyncClient, make_token, tournament_id: str, email: str):
    headers = await player(client, make_token, email)
    return await client.post(f"/tournaments/{tournament_id}/participants", headers=headers, json={})


async def test_a_tournament_has_no_cap_unless_one_is_set(client, make_token):
    organiser = await player(client, make_token, "organiser@example.com")
    event = await _open_tournament(client, organiser)

    assert event["max_players"] is None
    for n in range(5):
        assert (
            await _join(client, make_token, event["id"], f"p{n}@example.com")
        ).status_code == 201


async def test_self_registration_stops_at_the_cap(client, make_token):
    organiser = await player(client, make_token, "organiser@example.com")
    event = await _open_tournament(client, organiser, max_players=2)

    assert (await _join(client, make_token, event["id"], "a@example.com")).status_code == 201
    assert (await _join(client, make_token, event["id"], "b@example.com")).status_code == 201
    refused = await _join(client, make_token, event["id"], "c@example.com")

    assert refused.status_code == 409
    assert "full" in refused.json()["detail"]


async def test_the_organiser_can_still_add_someone_past_the_cap(client, make_token):
    """The cap defends against a shared link, not against the organiser's own hand."""
    organiser = await player(client, make_token, "organiser@example.com")
    event = await _open_tournament(client, organiser, max_players=2)
    await _join(client, make_token, event["id"], "a@example.com")
    await _join(client, make_token, event["id"], "b@example.com")

    added = await client.post(
        f"/tournaments/{event['id']}/participants/virtual",
        headers=organiser,
        json={"display_name": "Someone's boss"},
    )

    assert added.status_code == 201, added.text


async def test_a_full_event_says_so_on_the_invitation(client, make_token):
    """Otherwise the invite offers a button that can only answer 409."""
    organiser = await player(client, make_token, "organiser@example.com")
    event = await _open_tournament(client, organiser, max_players=2)
    code = event["join_code"]
    await _join(client, make_token, event["id"], "a@example.com")
    await _join(client, make_token, event["id"], "b@example.com")

    latecomer = await player(client, make_token, "late@example.com")
    preview = await client.get(f"/join/{code}", headers=latecomer)
    assert preview.json()["can_join"] is False

    refused = await client.post(f"/join/{code}", headers=latecomer, json={})
    assert refused.status_code == 409


async def test_a_cap_the_field_has_already_outgrown_is_refused(client, make_token):
    """Accepting it would leave an event permanently over quota with no way back."""
    organiser = await player(client, make_token, "organiser@example.com")
    event = await _open_tournament(client, organiser)
    for name in ("a", "b", "c"):
        await _join(client, make_token, event["id"], f"{name}@example.com")

    refused = await client.patch(
        f"/tournaments/{event['id']}", headers=organiser, json={"max_players": 2}
    )

    assert refused.status_code == 409
    assert "3 players have already registered" in refused.json()["detail"]

    # Exactly the field size is fine — it closes the event rather than breaking it.
    exact = await client.patch(
        f"/tournaments/{event['id']}", headers=organiser, json={"max_players": 3}
    )
    assert exact.status_code == 200
    assert exact.json()["max_players"] == 3


async def test_a_cap_can_be_raised_and_removed(client, make_token):
    organiser = await player(client, make_token, "organiser@example.com")
    event = await _open_tournament(client, organiser, max_players=2)
    await _join(client, make_token, event["id"], "a@example.com")
    await _join(client, make_token, event["id"], "b@example.com")

    raised = await client.patch(
        f"/tournaments/{event['id']}", headers=organiser, json={"max_players": 4}
    )
    assert raised.json()["max_players"] == 4
    assert (await _join(client, make_token, event["id"], "c@example.com")).status_code == 201

    cleared = await client.patch(
        f"/tournaments/{event['id']}", headers=organiser, json={"max_players": None}
    )
    assert cleared.json()["max_players"] is None
    assert (await _join(client, make_token, event["id"], "d@example.com")).status_code == 201


async def test_a_cap_below_a_playable_field_is_rejected_outright(client, make_token):
    """ADR-004 never makes a group of one, so a field of one could never tee off."""
    organiser = await player(client, make_token, "organiser@example.com")
    course_id = await course(client, organiser, hole_count=3)

    created = await client.post(
        "/tournaments",
        headers=organiser,
        json={"name": "Solo", "course_id": course_id, "max_players": 1},
    )

    assert created.status_code == 422


async def test_a_fun_round_still_caps_at_one_group(client, make_token):
    """Its ceiling is the format's, not the organiser's, and is unaffected by this."""
    host = await player(client, make_token, "host@example.com")
    created = await client.post("/fun-rounds", headers=host, json={"name": "Saturday nine"})
    fun_round = created.json()
    for name in ("A", "B", "C"):
        await client.post(
            f"/fun-rounds/{fun_round['id']}/virtual", headers=host, json={"display_name": name}
        )

    latecomer = await player(client, make_token, "late@example.com")
    refused = await client.post(
        f"/fun-rounds/{fun_round['id']}/players", headers=latecomer, json={}
    )

    assert refused.status_code == 409
    assert "up to 4" in refused.json()["detail"]
