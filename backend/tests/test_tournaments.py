"""API-level tests for the tournament slice."""

import uuid

import pytest
from httpx import AsyncClient

from app.models.tournament import TournamentStatus


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

    response = await client.patch(
        f"/tournaments/{tournament['id']}",
        headers=headers,
        json={"name": "Renamed", "course_name": "Royal Melbourne"},
    )

    assert response.status_code == 200
    assert response.json()["name"] == "Renamed"
    assert response.json()["course_name"] == "Royal Melbourne"


@pytest.mark.asyncio
async def test_omitted_fields_are_left_alone_on_update(client, make_token):
    headers = await _organiser(client, make_token)
    tournament = await _create_tournament(client, headers, course_name="Kingston Heath")

    response = await client.patch(
        f"/tournaments/{tournament['id']}", headers=headers, json={"name": "Renamed"}
    )

    assert response.json()["course_name"] == "Kingston Heath"


@pytest.mark.asyncio
async def test_the_full_lifecycle_can_be_walked(client, make_token):
    headers = await _organiser(client, make_token)
    tournament = await _create_tournament(client, headers)
    tournament_id = tournament["id"]

    for target in (
        TournamentStatus.REGISTRATION_OPEN,
        TournamentStatus.REGISTRATION_CLOSED,
        TournamentStatus.ROUND_IN_PROGRESS,
        TournamentStatus.ROUND_COMPLETE,
        TournamentStatus.TOURNAMENT_COMPLETE,
    ):
        assert (await _advance_to(client, headers, tournament_id, target))["status"] == target.value


@pytest.mark.asyncio
async def test_a_finished_round_can_start_another(client, make_token):
    headers = await _organiser(client, make_token)
    tournament_id = (await _create_tournament(client, headers))["id"]

    for target in (
        TournamentStatus.REGISTRATION_OPEN,
        TournamentStatus.REGISTRATION_CLOSED,
        TournamentStatus.ROUND_IN_PROGRESS,
        TournamentStatus.ROUND_COMPLETE,
        TournamentStatus.ROUND_IN_PROGRESS,
    ):
        await _advance_to(client, headers, tournament_id, target)


@pytest.mark.asyncio
async def test_skipping_a_state_conflicts(client, make_token):
    headers = await _organiser(client, make_token)
    tournament = await _create_tournament(client, headers)

    response = await client.post(
        f"/tournaments/{tournament['id']}/status",
        headers=headers,
        json={"status": TournamentStatus.ROUND_IN_PROGRESS.value},
    )

    assert response.status_code == 409
    assert "REGISTRATION_OPEN" in response.json()["detail"]


@pytest.mark.asyncio
async def test_a_completed_tournament_cannot_be_restarted(client, make_token):
    headers = await _organiser(client, make_token)
    tournament_id = (await _create_tournament(client, headers))["id"]

    for target in (
        TournamentStatus.REGISTRATION_OPEN,
        TournamentStatus.REGISTRATION_CLOSED,
        TournamentStatus.ROUND_IN_PROGRESS,
        TournamentStatus.ROUND_COMPLETE,
        TournamentStatus.TOURNAMENT_COMPLETE,
    ):
        await _advance_to(client, headers, tournament_id, target)

    response = await client.post(
        f"/tournaments/{tournament_id}/status",
        headers=headers,
        json={"status": TournamentStatus.ROUND_IN_PROGRESS.value},
    )

    assert response.status_code == 409


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
