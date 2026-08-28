"""Joining an event by its code.

The flow this covers is the one that was impossible before it existed: somebody
is sent a link, opens it without being in the field, sees what they were invited
to, and takes their place. Both kinds of event are invited the same way, so a fun
round's single-group cap has to keep enforcing itself down this route too.
"""

from httpx import AsyncClient

from app.models.tournament import TournamentStatus
from tests.helpers import course, player, set_status, tournament


async def _open_tournament(client: AsyncClient, headers) -> dict:
    course_id = await course(client, headers, hole_count=3)
    tournament_id = await tournament(client, headers, course_id)
    await set_status(client, headers, tournament_id, TournamentStatus.REGISTRATION_OPEN)
    read = await client.get(f"/tournaments/{tournament_id}", headers=headers)
    return read.json()


async def _fun_round(client: AsyncClient, headers) -> dict:
    created = await client.post("/fun-rounds", headers=headers, json={"name": "Saturday nine"})
    assert created.status_code == 201, created.text
    return created.json()


# --- The code itself --------------------------------------------------------


async def test_every_tournament_is_created_with_a_code(client, make_token):
    organiser = await player(client, make_token, "organiser@example.com")
    event = await _open_tournament(client, organiser)

    assert event["join_code"].startswith("THR-")


async def test_two_events_never_share_a_code(client, make_token):
    organiser = await player(client, make_token, "organiser@example.com")
    codes = {(await _open_tournament(client, organiser))["join_code"] for _ in range(5)}

    assert len(codes) == 5


async def test_the_code_belongs_to_the_organiser_alone(client, make_token):
    """A player who could read the code could invite people the organiser didn't."""
    organiser = await player(client, make_token, "organiser@example.com")
    event = await _open_tournament(client, organiser)
    mate = await player(client, make_token, "mate@example.com")
    await client.post(f"/join/{event['join_code']}", headers=mate, json={})

    theirs = await client.get(f"/tournaments/{event['id']}", headers=mate)
    assert theirs.status_code == 200
    assert theirs.json()["join_code"] is None

    listed = await client.get("/players/me/tournaments", headers=mate)
    assert [row["join_code"] for row in listed.json()] == [None]


# --- Previewing and accepting -----------------------------------------------


async def test_a_stranger_can_see_what_they_were_invited_to(client, make_token):
    organiser = await player(client, make_token, "organiser@example.com")
    event = await _open_tournament(client, organiser)

    mate = await player(client, make_token, "mate@example.com")
    preview = await client.get(f"/join/{event['join_code']}", headers=mate)

    assert preview.status_code == 200, preview.text
    body = preview.json()
    assert body["kind"] == "tournament"
    assert body["id"] == event["id"]
    assert body["can_join"] is True
    # An invitation says what it is, not who else is coming.
    assert "participants" not in body


async def test_a_lowercase_code_still_finds_the_event(client, make_token):
    """It gets read off a sign and typed into a phone."""
    organiser = await player(client, make_token, "organiser@example.com")
    event = await _open_tournament(client, organiser)
    mate = await player(client, make_token, "mate@example.com")

    preview = await client.get(f"/join/{event['join_code'].lower()}", headers=mate)

    assert preview.status_code == 200


async def test_joining_by_code_puts_you_in_the_field(client, make_token):
    organiser = await player(client, make_token, "organiser@example.com")
    event = await _open_tournament(client, organiser)

    mate = await player(client, make_token, "mate@example.com")
    joined = await client.post(f"/join/{event['join_code']}", headers=mate, json={})
    assert joined.status_code == 201, joined.text

    field = await client.get(f"/tournaments/{event['id']}/participants", headers=organiser)
    assert len(field.json()) == 1

    # And now the tournament itself is readable, which it was not a moment ago.
    assert (await client.get(f"/tournaments/{event['id']}", headers=mate)).status_code == 200


async def test_an_unknown_code_is_not_found(client, make_token):
    mate = await player(client, make_token, "mate@example.com")

    assert (await client.get("/join/THR-ZZZZZ", headers=mate)).status_code == 404


async def test_a_closed_event_says_so_rather_than_offering_the_button(client, make_token):
    organiser = await player(client, make_token, "organiser@example.com")
    event = await _open_tournament(client, organiser)
    await set_status(client, organiser, event["id"], TournamentStatus.REGISTRATION_CLOSED)

    mate = await player(client, make_token, "mate@example.com")
    preview = await client.get(f"/join/{event['join_code']}", headers=mate)
    assert preview.json()["can_join"] is False

    refused = await client.post(f"/join/{event['join_code']}", headers=mate, json={})
    assert refused.status_code == 409


# --- Revoking ---------------------------------------------------------------


async def test_regenerating_retires_the_old_code(client, make_token):
    """The point of a code rather than an id: a printed QR outlives its event."""
    organiser = await player(client, make_token, "organiser@example.com")
    event = await _open_tournament(client, organiser)
    old = event["join_code"]

    minted = await client.post(f"/tournaments/{event['id']}/join-code", headers=organiser)
    assert minted.status_code == 200, minted.text
    new = minted.json()["join_code"]
    assert new != old

    mate = await player(client, make_token, "mate@example.com")
    assert (await client.get(f"/join/{old}", headers=mate)).status_code == 404
    assert (await client.get(f"/join/{new}", headers=mate)).status_code == 200


async def test_only_the_organiser_can_regenerate(client, make_token):
    organiser = await player(client, make_token, "organiser@example.com")
    event = await _open_tournament(client, organiser)
    mate = await player(client, make_token, "mate@example.com")

    refused = await client.post(f"/tournaments/{event['id']}/join-code", headers=mate)

    assert refused.status_code == 403


# --- Fun rounds are invited the same way ------------------------------------


async def test_a_fun_round_is_invited_by_code_too(client, make_token):
    host = await player(client, make_token, "host@example.com")
    fun_round = await _fun_round(client, host)
    read = await client.get(f"/fun-rounds/{fun_round['id']}", headers=host)
    code = read.json()["join_code"]

    mate = await player(client, make_token, "mate@example.com")
    preview = await client.get(f"/join/{code}", headers=mate)

    assert preview.json()["kind"] == "fun_round"
    assert (await client.post(f"/join/{code}", headers=mate, json={})).status_code == 201


async def test_the_fun_round_cap_still_applies_when_joining_by_code(client, make_token):
    """The cap is a rule about fun rounds, not about the endpoint doing the joining."""
    host = await player(client, make_token, "host@example.com")
    fun_round = await _fun_round(client, host)
    read = await client.get(f"/fun-rounds/{fun_round['id']}", headers=host)
    code = read.json()["join_code"]
    for name in ("A", "B", "C"):
        await client.post(
            f"/fun-rounds/{fun_round['id']}/virtual", headers=host, json={"display_name": name}
        )

    latecomer = await player(client, make_token, "late@example.com")
    assert (await client.get(f"/join/{code}", headers=latecomer)).json()["can_join"] is False
    refused = await client.post(f"/join/{code}", headers=latecomer, json={})

    assert refused.status_code == 409
    assert "full" in refused.json()["detail"]


async def test_the_fun_round_endpoints_still_refuse_a_tournament_code_holder(client, make_token):
    """Joining is open to a code holder; reading the field is not."""
    organiser = await player(client, make_token, "organiser@example.com")
    event = await _open_tournament(client, organiser)
    mate = await player(client, make_token, "mate@example.com")

    assert (await client.get(f"/tournaments/{event['id']}", headers=mate)).status_code == 403
