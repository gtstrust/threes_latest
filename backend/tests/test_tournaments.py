"""API-level tests for the tournament slice."""

import uuid

import pytest
from httpx import AsyncClient

from app.models.tournament import SUPPORTED_FORMATS, TournamentFormat, TournamentStatus


async def _organiser(client: AsyncClient, make_token, email: str = "organiser@example.com"):
    """A caller with a provisioned profile, ready to own tournaments."""
    headers = {"Authorization": f"Bearer {make_token(email=email)}"}
    await client.post("/players", headers=headers)
    return headers


async def _create_tournament(client: AsyncClient, headers, **overrides):
    payload = {"name": "Acme Corporate Day", **overrides}
    response = await client.post("/tournaments", headers=headers, json=payload)
    assert response.status_code == 201, response.text
    return response.json()


async def _create_course(client: AsyncClient, headers, name: str = "Royal Melbourne") -> str:
    response = await client.post("/courses", headers=headers, json={"name": name})
    assert response.status_code == 201, response.text
    return response.json()["id"]


async def _playable_tournament(client: AsyncClient, headers, **overrides) -> str:
    """A tournament with a course attached, so it can actually start a round."""
    course_id = await _create_course(client, headers)
    tournament = await _create_tournament(client, headers, course_id=course_id, **overrides)
    return tournament["id"]


async def _advance_to(client: AsyncClient, headers, tournament_id: str, target: TournamentStatus):
    response = await client.post(
        f"/tournaments/{tournament_id}/status",
        headers=headers,
        json={"status": target.value},
    )
    assert response.status_code == 200, response.text
    return response.json()


@pytest.mark.asyncio
async def test_creating_a_tournament_starts_it_in_created(client, make_token):
    headers = await _organiser(client, make_token)

    tournament = await _create_tournament(client, headers)

    assert tournament["status"] == TournamentStatus.CREATED.value
    assert tournament["format"] == "ROUND_ROBIN"
    assert tournament["name"] == "Acme Corporate Day"


@pytest.mark.asyncio
async def test_creating_a_tournament_without_a_profile_is_rejected(client, make_token):
    """organiser_id is an FK to players, and that row is created lazily."""
    headers = {"Authorization": f"Bearer {make_token()}"}

    response = await client.post("/tournaments", headers=headers, json={"name": "No Profile"})

    assert response.status_code == 404
    assert "POST /players" in response.json()["detail"]


@pytest.mark.asyncio
async def test_tournaments_require_authentication(client):
    assert (await client.get("/tournaments")).status_code in (401, 403)
    assert (await client.post("/tournaments", json={"name": "x"})).status_code in (401, 403)


@pytest.mark.asyncio
async def test_listing_returns_only_my_tournaments(client, make_token):
    mine = await _organiser(client, make_token, email="mine@example.com")
    theirs = await _organiser(client, make_token, email="theirs@example.com")

    await _create_tournament(client, mine, name="Mine")
    await _create_tournament(client, theirs, name="Theirs")

    response = await client.get("/tournaments", headers=mine)

    assert response.status_code == 200
    assert [row["name"] for row in response.json()] == ["Mine"]


@pytest.mark.asyncio
async def test_organiser_can_read_their_own_tournament(client, make_token):
    headers = await _organiser(client, make_token)
    tournament = await _create_tournament(client, headers)

    response = await client.get(f"/tournaments/{tournament['id']}", headers=headers)

    assert response.status_code == 200
    assert response.json()["id"] == tournament["id"]


@pytest.mark.asyncio
async def test_someone_elses_tournament_is_forbidden(client, make_token):
    owner = await _organiser(client, make_token, email="owner@example.com")
    tournament = await _create_tournament(client, owner)
    stranger = await _organiser(client, make_token, email="stranger@example.com")

    assert (
        await client.get(f"/tournaments/{tournament['id']}", headers=stranger)
    ).status_code == 403
    assert (
        await client.patch(
            f"/tournaments/{tournament['id']}", headers=stranger, json={"name": "Hijacked"}
        )
    ).status_code == 403
    assert (
        await client.post(
            f"/tournaments/{tournament['id']}/status",
            headers=stranger,
            json={"status": TournamentStatus.REGISTRATION_OPEN.value},
        )
    ).status_code == 403


@pytest.mark.asyncio
async def test_unknown_tournament_is_404(client, make_token):
    headers = await _organiser(client, make_token)

    response = await client.get(f"/tournaments/{uuid.uuid4()}", headers=headers)

    assert response.status_code == 404


@pytest.mark.asyncio
async def test_organiser_can_update_details(client, make_token):
    headers = await _organiser(client, make_token)
    tournament = await _create_tournament(client, headers)
    course_id = await _create_course(client, headers)

    response = await client.patch(
        f"/tournaments/{tournament['id']}",
        headers=headers,
        json={"name": "Renamed", "course_id": course_id},
    )

    assert response.status_code == 200
    assert response.json()["name"] == "Renamed"
    assert response.json()["course_id"] == course_id


@pytest.mark.asyncio
async def test_omitted_fields_are_left_alone_on_update(client, make_token):
    headers = await _organiser(client, make_token)
    course_id = await _create_course(client, headers)
    tournament = await _create_tournament(client, headers, course_id=course_id)

    response = await client.patch(
        f"/tournaments/{tournament['id']}", headers=headers, json={"name": "Renamed"}
    )

    assert response.json()["course_id"] == course_id


# The play statuses (ROUND_IN_PROGRESS, ROUND_COMPLETE) are owned by the round
# endpoints and can't be set here — see tests/test_rounds.py for those, and for
# the walk through a whole event.


@pytest.mark.asyncio
async def test_the_registration_transitions_can_be_walked(client, make_token):
    headers = await _organiser(client, make_token)
    tournament_id = await _playable_tournament(client, headers)

    for target in (
        TournamentStatus.REGISTRATION_OPEN,
        TournamentStatus.REGISTRATION_CLOSED,
    ):
        assert (await _advance_to(client, headers, tournament_id, target))["status"] == target.value


@pytest.mark.asyncio
async def test_skipping_a_state_conflicts(client, make_token):
    headers = await _organiser(client, make_token)
    tournament = await _create_tournament(client, headers)

    response = await client.post(
        f"/tournaments/{tournament['id']}/status",
        headers=headers,
        json={"status": TournamentStatus.REGISTRATION_CLOSED.value},
    )

    assert response.status_code == 409
    assert "REGISTRATION_OPEN" in response.json()["detail"]


@pytest.mark.asyncio
async def test_an_unrecognised_status_is_rejected_before_reaching_the_machine(client, make_token):
    headers = await _organiser(client, make_token)
    tournament = await _create_tournament(client, headers)

    response = await client.post(
        f"/tournaments/{tournament['id']}/status",
        headers=headers,
        json={"status": "ABANDONED"},
    )

    assert response.status_code == 422


@pytest.mark.asyncio
async def test_a_blank_name_is_rejected(client, make_token):
    headers = await _organiser(client, make_token)

    response = await client.post("/tournaments", headers=headers, json={"name": ""})

    assert response.status_code == 422


# "A round can't start without a course" now lives in tests/test_rounds.py — the
# rule moved into the draw, which is the only route to ROUND_IN_PROGRESS.


@pytest.mark.asyncio
async def test_a_tournament_can_be_created_before_a_venue_is_booked(client, make_token):
    headers = await _organiser(client, make_token)

    tournament = await _create_tournament(client, headers)

    assert tournament["course_id"] is None


@pytest.mark.asyncio
async def test_knockout_is_rejected_until_it_is_implemented(client, make_token):
    """Accepting it would fail silently — the event would just run as a round robin."""
    headers = await _organiser(client, make_token)

    response = await client.post(
        "/tournaments",
        headers=headers,
        json={"name": "Knockout Cup", "format": TournamentFormat.KNOCKOUT.value},
    )

    assert response.status_code == 422
    # The message must say it isn't built yet, not merely that it's invalid.
    assert "not implemented" in response.text
    assert TournamentFormat.ROUND_ROBIN.value in response.text


@pytest.mark.asyncio
@pytest.mark.parametrize("supported", sorted(SUPPORTED_FORMATS, key=lambda fmt: fmt.value))
async def test_every_supported_format_is_accepted(client, make_token, supported):
    """Parametrised over the constant so this widens by itself once knockout ships."""
    headers = await _organiser(client, make_token, email=f"{supported.value.lower()}@example.com")

    tournament = await _create_tournament(client, headers, format=supported.value)

    assert tournament["format"] == supported.value


@pytest.mark.asyncio
async def test_format_defaults_to_round_robin_when_omitted(client, make_token):
    headers = await _organiser(client, make_token)

    tournament = await _create_tournament(client, headers)

    assert tournament["format"] == TournamentFormat.ROUND_ROBIN.value


# --- Finding the tournaments you play in ------------------------------------
#
# `GET /tournaments` lists what you organise. Without the endpoint below a player
# can read an event by id — `require_can_view` admits the field — but has no way
# to learn the id, so losing the invitation link strands them.


async def _open_for_registration(client: AsyncClient, organiser) -> str:
    tournament = await _create_tournament(client, organiser)
    await client.post(
        f"/tournaments/{tournament['id']}/status",
        headers=organiser,
        json={"status": TournamentStatus.REGISTRATION_OPEN.value},
    )
    return str(tournament["id"])


@pytest.mark.asyncio
async def test_a_player_sees_the_tournaments_they_joined(client, make_token):
    organiser = await _organiser(client, make_token)
    player = await _organiser(client, make_token, email="player@example.com")
    tournament_id = await _open_for_registration(client, organiser)
    await client.post(f"/tournaments/{tournament_id}/participants", headers=player, json={})

    response = await client.get("/players/me/tournaments", headers=player)

    assert response.status_code == 200, response.text
    assert [t["id"] for t in response.json()] == [tournament_id]


@pytest.mark.asyncio
async def test_a_player_does_not_see_tournaments_they_are_not_in(client, make_token):
    organiser = await _organiser(client, make_token)
    player = await _organiser(client, make_token, email="player@example.com")
    joined = await _open_for_registration(client, organiser)
    await _open_for_registration(client, organiser)  # somebody else's event
    await client.post(f"/tournaments/{joined}/participants", headers=player, json={})

    response = await client.get("/players/me/tournaments", headers=player)

    assert [t["id"] for t in response.json()] == [joined]


@pytest.mark.asyncio
async def test_organising_is_not_playing(client, make_token):
    """The two lists answer different questions and must not bleed into each other.

    An organiser who is not in the field is running the day, not playing it —
    their event belongs on `GET /tournaments`, not here.
    """
    organiser = await _organiser(client, make_token)
    await _open_for_registration(client, organiser)

    playing = await client.get("/players/me/tournaments", headers=organiser)
    organising = await client.get("/tournaments", headers=organiser)

    assert playing.json() == []
    assert len(organising.json()) == 1


@pytest.mark.asyncio
async def test_an_organiser_who_also_plays_sees_it_in_both(client, make_token):
    """Which is the normal case for a corporate day — the organiser plays too."""
    organiser = await _organiser(client, make_token)
    tournament_id = await _open_for_registration(client, organiser)
    await client.post(f"/tournaments/{tournament_id}/participants", headers=organiser, json={})

    playing = await client.get("/players/me/tournaments", headers=organiser)
    organising = await client.get("/tournaments", headers=organiser)

    assert [t["id"] for t in playing.json()] == [tournament_id]
    assert [t["id"] for t in organising.json()] == [tournament_id]


@pytest.mark.asyncio
async def test_virtual_players_cannot_surface_in_anyone_s_list(client, make_token):
    """A virtual player has `player_id IS NULL` and no account to call the API with.

    The join matches on `player_id`, and NULL equals nothing — so a tournament
    full of virtual players stays invisible to a real player who is not in it.
    """
    organiser = await _organiser(client, make_token)
    outsider = await _organiser(client, make_token, email="outsider@example.com")
    tournament_id = await _open_for_registration(client, organiser)
    for name in ("Dave", "Baz"):
        created = await client.post(
            f"/tournaments/{tournament_id}/participants/virtual",
            headers=organiser,
            json={"display_name": name},
        )
        assert created.status_code == 201, created.text

    response = await client.get("/players/me/tournaments", headers=outsider)

    assert response.json() == []


@pytest.mark.asyncio
async def test_newest_first(client, make_token):
    organiser = await _organiser(client, make_token)
    player = await _organiser(client, make_token, email="player@example.com")
    first = await _open_for_registration(client, organiser)
    second = await _open_for_registration(client, organiser)
    for tournament_id in (first, second):
        await client.post(f"/tournaments/{tournament_id}/participants", headers=player, json={})

    response = await client.get("/players/me/tournaments", headers=player)

    assert [t["id"] for t in response.json()] == [second, first]
