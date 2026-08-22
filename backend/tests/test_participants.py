"""API-level tests for tournament participants, including virtual players."""

import uuid

import pytest
from httpx import AsyncClient

from app.models.tournament import TournamentStatus


async def _player(client: AsyncClient, make_token, email: str):
    headers = {"Authorization": f"Bearer {make_token(email=email)}"}
    await client.post("/players", headers=headers)
    return headers


async def _tournament(client: AsyncClient, headers, with_course: bool = True) -> str:
    payload: dict[str, object] = {"name": "Acme Corporate Day"}
    if with_course:
        course = await client.post(
            "/courses", headers=headers, json={"name": f"Course {uuid.uuid4()}"}
        )
        course_id = course.json()["id"]
        # Three holes, so a round can actually be drawn on it.
        await client.put(
            f"/courses/{course_id}/holes",
            headers=headers,
            json={"holes": [{"hole_number": n} for n in (1, 2, 3)]},
        )
        payload["course_id"] = course_id
    response = await client.post("/tournaments", headers=headers, json=payload)
    assert response.status_code == 201, response.text
    return response.json()["id"]


async def _set_status(client: AsyncClient, headers, tournament_id: str, target: TournamentStatus):
    response = await client.post(
        f"/tournaments/{tournament_id}/status", headers=headers, json={"status": target.value}
    )
    assert response.status_code == 200, response.text


async def _open_registration(client: AsyncClient, headers, tournament_id: str) -> None:
    await _set_status(client, headers, tournament_id, TournamentStatus.REGISTRATION_OPEN)


async def _start_play(client: AsyncClient, headers, tournament_id: str) -> None:
    """Close registration and draw a round — the only route to ROUND_IN_PROGRESS."""
    await _set_status(client, headers, tournament_id, TournamentStatus.REGISTRATION_CLOSED)
    drawn = await client.post(f"/tournaments/{tournament_id}/rounds", headers=headers)
    assert drawn.status_code == 201, drawn.text


# --- Self-registration ------------------------------------------------------


@pytest.mark.asyncio
async def test_a_player_can_register_themselves(client, make_token):
    organiser = await _player(client, make_token, "organiser@example.com")
    tournament_id = await _tournament(client, organiser)
    await _open_registration(client, organiser, tournament_id)
    player = await _player(client, make_token, "player@example.com")

    response = await client.post(
        f"/tournaments/{tournament_id}/participants", headers=player, json={}
    )

    assert response.status_code == 201, response.text
    assert response.json()["is_virtual"] is False
    assert response.json()["player_id"] is not None


@pytest.mark.asyncio
async def test_display_name_falls_back_to_the_profile_then_the_email(client, make_token):
    organiser = await _player(client, make_token, "organiser@example.com")
    tournament_id = await _tournament(client, organiser)
    await _open_registration(client, organiser, tournament_id)

    no_name = await _player(client, make_token, "nameless@example.com")
    named = await _player(client, make_token, "named@example.com")
    await client.patch("/players/me", headers=named, json={"display_name": "Jo Bloggs"})

    from_email = await client.post(
        f"/tournaments/{tournament_id}/participants", headers=no_name, json={}
    )
    from_profile = await client.post(
        f"/tournaments/{tournament_id}/participants", headers=named, json={}
    )

    assert from_email.json()["display_name"] == "nameless@example.com"
    assert from_profile.json()["display_name"] == "Jo Bloggs"


@pytest.mark.asyncio
async def test_an_explicit_display_name_wins(client, make_token):
    organiser = await _player(client, make_token, "organiser@example.com")
    tournament_id = await _tournament(client, organiser)
    await _open_registration(client, organiser, tournament_id)
    player = await _player(client, make_token, "player@example.com")

    response = await client.post(
        f"/tournaments/{tournament_id}/participants",
        headers=player,
        json={"display_name": "Sandy"},
    )

    assert response.json()["display_name"] == "Sandy"


@pytest.mark.asyncio
async def test_registering_twice_conflicts(client, make_token):
    organiser = await _player(client, make_token, "organiser@example.com")
    tournament_id = await _tournament(client, organiser)
    await _open_registration(client, organiser, tournament_id)
    player = await _player(client, make_token, "player@example.com")

    await client.post(f"/tournaments/{tournament_id}/participants", headers=player, json={})
    again = await client.post(f"/tournaments/{tournament_id}/participants", headers=player, json={})

    assert again.status_code == 409
    assert "already registered" in again.json()["detail"].lower()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "status_before",
    [TournamentStatus.CREATED, TournamentStatus.REGISTRATION_CLOSED],
)
async def test_self_registration_only_works_while_registration_is_open(
    client, make_token, status_before
):
    organiser = await _player(client, make_token, "organiser@example.com")
    tournament_id = await _tournament(client, organiser)
    if status_before is TournamentStatus.REGISTRATION_CLOSED:
        await _open_registration(client, organiser, tournament_id)
        await _set_status(client, organiser, tournament_id, status_before)
    player = await _player(client, make_token, "player@example.com")

    response = await client.post(
        f"/tournaments/{tournament_id}/participants", headers=player, json={}
    )

    assert response.status_code == 409
    assert "not open" in response.json()["detail"]


@pytest.mark.asyncio
async def test_registering_without_a_profile_is_rejected(client, make_token):
    organiser = await _player(client, make_token, "organiser@example.com")
    tournament_id = await _tournament(client, organiser)
    await _open_registration(client, organiser, tournament_id)
    stranger = {"Authorization": f"Bearer {make_token()}"}

    response = await client.post(
        f"/tournaments/{tournament_id}/participants", headers=stranger, json={}
    )

    assert response.status_code == 404
    assert "POST /players" in response.json()["detail"]


# --- Virtual players --------------------------------------------------------


@pytest.mark.asyncio
async def test_organiser_can_add_a_virtual_player(client, make_token):
    organiser = await _player(client, make_token, "organiser@example.com")
    tournament_id = await _tournament(client, organiser)
    await _open_registration(client, organiser, tournament_id)

    response = await client.post(
        f"/tournaments/{tournament_id}/participants/virtual",
        headers=organiser,
        json={"display_name": "Pat (no phone)"},
    )

    assert response.status_code == 201, response.text
    assert response.json()["is_virtual"] is True
    assert response.json()["player_id"] is None


@pytest.mark.asyncio
async def test_many_virtual_players_are_allowed_in_one_tournament(client, make_token):
    """UNIQUE(tournament_id, player_id) must not collapse NULLs into one row.

    Postgres treats NULLs as distinct, which is what lets a whole field of
    device-less players coexist without a partial index.
    """
    organiser = await _player(client, make_token, "organiser@example.com")
    tournament_id = await _tournament(client, organiser)
    await _open_registration(client, organiser, tournament_id)

    for name in ("Pat", "Sam", "Alex", "Jo"):
        response = await client.post(
            f"/tournaments/{tournament_id}/participants/virtual",
            headers=organiser,
            json={"display_name": name},
        )
        assert response.status_code == 201, response.text

    field = await client.get(f"/tournaments/{tournament_id}/participants", headers=organiser)
    assert len(field.json()) == 4


@pytest.mark.asyncio
async def test_two_virtual_players_can_share_a_name(client, make_token):
    """Two people really can both be John Smith."""
    organiser = await _player(client, make_token, "organiser@example.com")
    tournament_id = await _tournament(client, organiser)
    await _open_registration(client, organiser, tournament_id)

    first = await client.post(
        f"/tournaments/{tournament_id}/participants/virtual",
        headers=organiser,
        json={"display_name": "John Smith"},
    )
    second = await client.post(
        f"/tournaments/{tournament_id}/participants/virtual",
        headers=organiser,
        json={"display_name": "John Smith"},
    )

    assert first.status_code == 201
    assert second.status_code == 201
    assert first.json()["id"] != second.json()["id"]


@pytest.mark.asyncio
async def test_only_the_organiser_can_add_a_virtual_player(client, make_token):
    organiser = await _player(client, make_token, "organiser@example.com")
    tournament_id = await _tournament(client, organiser)
    await _open_registration(client, organiser, tournament_id)
    other = await _player(client, make_token, "other@example.com")

    response = await client.post(
        f"/tournaments/{tournament_id}/participants/virtual",
        headers=other,
        json={"display_name": "Sneaky"},
    )

    assert response.status_code == 403


# --- The organiser's override ----------------------------------------------


@pytest.mark.asyncio
async def test_organiser_can_still_add_after_registration_closes(client, make_token):
    """The late arrival. Registration can't reopen, so the organiser needs this."""
    organiser = await _player(client, make_token, "organiser@example.com")
    tournament_id = await _tournament(client, organiser)
    await _open_registration(client, organiser, tournament_id)
    await _set_status(client, organiser, tournament_id, TournamentStatus.REGISTRATION_CLOSED)

    response = await client.post(
        f"/tournaments/{tournament_id}/participants/virtual",
        headers=organiser,
        json={"display_name": "Late Arrival"},
    )

    assert response.status_code == 201


@pytest.mark.asyncio
async def test_organiser_can_remove_a_no_show_after_registration_closes(client, make_token):
    organiser = await _player(client, make_token, "organiser@example.com")
    tournament_id = await _tournament(client, organiser)
    await _open_registration(client, organiser, tournament_id)
    added = await client.post(
        f"/tournaments/{tournament_id}/participants/virtual",
        headers=organiser,
        json={"display_name": "No Show"},
    )
    await _set_status(client, organiser, tournament_id, TournamentStatus.REGISTRATION_CLOSED)

    response = await client.delete(
        f"/tournaments/{tournament_id}/participants/{added.json()['id']}", headers=organiser
    )

    assert response.status_code == 204
    field = await client.get(f"/tournaments/{tournament_id}/participants", headers=organiser)
    assert field.json() == []


@pytest.mark.asyncio
async def test_the_field_is_fixed_once_play_starts(client, make_token):
    organiser = await _player(client, make_token, "organiser@example.com")
    tournament_id = await _tournament(client, organiser)
    await _open_registration(client, organiser, tournament_id)
    added = await client.post(
        f"/tournaments/{tournament_id}/participants/virtual",
        headers=organiser,
        json={"display_name": "Pat"},
    )
    # A draw needs at least two players to make a group.
    await client.post(
        f"/tournaments/{tournament_id}/participants/virtual",
        headers=organiser,
        json={"display_name": "Sam"},
    )
    await _start_play(client, organiser, tournament_id)

    adding = await client.post(
        f"/tournaments/{tournament_id}/participants/virtual",
        headers=organiser,
        json={"display_name": "Too Late"},
    )
    removing = await client.delete(
        f"/tournaments/{tournament_id}/participants/{added.json()['id']}", headers=organiser
    )

    assert adding.status_code == 409
    assert removing.status_code == 409
    assert "fixed once play starts" in adding.json()["detail"]


@pytest.mark.asyncio
async def test_only_the_organiser_can_remove(client, make_token):
    organiser = await _player(client, make_token, "organiser@example.com")
    tournament_id = await _tournament(client, organiser)
    await _open_registration(client, organiser, tournament_id)
    added = await client.post(
        f"/tournaments/{tournament_id}/participants/virtual",
        headers=organiser,
        json={"display_name": "Pat"},
    )
    other = await _player(client, make_token, "other@example.com")

    response = await client.delete(
        f"/tournaments/{tournament_id}/participants/{added.json()['id']}", headers=other
    )

    assert response.status_code == 403


@pytest.mark.asyncio
async def test_a_participant_of_another_tournament_is_not_found_here(client, make_token):
    """A real participant id, but reached through the wrong tournament's URL."""
    organiser = await _player(client, make_token, "organiser@example.com")
    theirs = await _tournament(client, organiser)
    ours = await _tournament(client, organiser)
    await _open_registration(client, organiser, theirs)
    added = await client.post(
        f"/tournaments/{theirs}/participants/virtual",
        headers=organiser,
        json={"display_name": "Pat"},
    )
    await _open_registration(client, organiser, ours)

    response = await client.delete(
        f"/tournaments/{ours}/participants/{added.json()['id']}", headers=organiser
    )

    assert response.status_code == 404


# --- Visibility, and the TODO(M3) this milestone clears ---------------------


@pytest.mark.asyncio
async def test_a_registered_player_can_now_read_the_tournament(client, make_token):
    """Before participants existed, require_can_view was organiser-only, so an
    invited player couldn't read the event they'd been invited to."""
    organiser = await _player(client, make_token, "organiser@example.com")
    tournament_id = await _tournament(client, organiser)
    await _open_registration(client, organiser, tournament_id)
    player = await _player(client, make_token, "player@example.com")

    before = await client.get(f"/tournaments/{tournament_id}", headers=player)
    await client.post(f"/tournaments/{tournament_id}/participants", headers=player, json={})
    after = await client.get(f"/tournaments/{tournament_id}", headers=player)

    assert before.status_code == 403
    assert after.status_code == 200


@pytest.mark.asyncio
async def test_a_stranger_still_cannot_read_the_tournament(client, make_token):
    organiser = await _player(client, make_token, "organiser@example.com")
    tournament_id = await _tournament(client, organiser)
    stranger = await _player(client, make_token, "stranger@example.com")

    response = await client.get(f"/tournaments/{tournament_id}", headers=stranger)

    assert response.status_code == 403


@pytest.mark.asyncio
async def test_the_field_is_visible_to_the_organiser_and_its_players(client, make_token):
    organiser = await _player(client, make_token, "organiser@example.com")
    tournament_id = await _tournament(client, organiser)
    await _open_registration(client, organiser, tournament_id)
    player = await _player(client, make_token, "player@example.com")
    await client.post(f"/tournaments/{tournament_id}/participants", headers=player, json={})
    stranger = await _player(client, make_token, "stranger@example.com")

    assert (
        await client.get(f"/tournaments/{tournament_id}/participants", headers=organiser)
    ).status_code == 200
    assert (
        await client.get(f"/tournaments/{tournament_id}/participants", headers=player)
    ).status_code == 200
    assert (
        await client.get(f"/tournaments/{tournament_id}/participants", headers=stranger)
    ).status_code == 403


@pytest.mark.asyncio
async def test_the_field_is_listed_in_registration_order(client, make_token):
    organiser = await _player(client, make_token, "organiser@example.com")
    tournament_id = await _tournament(client, organiser)
    await _open_registration(client, organiser, tournament_id)

    for name in ("First", "Second", "Third"):
        await client.post(
            f"/tournaments/{tournament_id}/participants/virtual",
            headers=organiser,
            json={"display_name": name},
        )

    field = await client.get(f"/tournaments/{tournament_id}/participants", headers=organiser)

    assert [entry["display_name"] for entry in field.json()] == ["First", "Second", "Third"]


@pytest.mark.asyncio
async def test_participants_require_authentication(client, make_token):
    organiser = await _player(client, make_token, "organiser@example.com")
    tournament_id = await _tournament(client, organiser)

    assert (await client.get(f"/tournaments/{tournament_id}/participants")).status_code in (
        401,
        403,
    )
    assert (
        await client.post(f"/tournaments/{tournament_id}/participants", json={})
    ).status_code in (401, 403)


@pytest.mark.asyncio
async def test_unknown_tournament_is_404(client, make_token):
    headers = await _player(client, make_token, "player@example.com")

    response = await client.get(f"/tournaments/{uuid.uuid4()}/participants", headers=headers)

    assert response.status_code == 404


@pytest.mark.asyncio
async def test_a_blank_virtual_player_name_is_rejected(client, make_token):
    organiser = await _player(client, make_token, "organiser@example.com")
    tournament_id = await _tournament(client, organiser)
    await _open_registration(client, organiser, tournament_id)

    response = await client.post(
        f"/tournaments/{tournament_id}/participants/virtual",
        headers=organiser,
        json={"display_name": ""},
    )

    assert response.status_code == 422
