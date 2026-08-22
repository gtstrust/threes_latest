"""Shared setup for API tests: the chain from an empty database to a drawn round.

Extracted from test_rounds.py so the scoring tests can reach a playable group
without repeating six requests. Every helper goes through the API rather than the
database, so the setup itself exercises the endpoints it depends on.
"""

import uuid

from httpx import AsyncClient

from app.models.tournament import TournamentStatus


async def player(client: AsyncClient, make_token, email: str) -> dict[str, str]:
    """Provision a profile and return auth headers for it."""
    headers = {"Authorization": f"Bearer {make_token(email=email)}"}
    await client.post("/players", headers=headers)
    return headers


async def course(client: AsyncClient, headers, hole_count: int = 18) -> str:
    created = await client.post(
        "/courses", headers=headers, json={"name": f"Course {uuid.uuid4()}"}
    )
    course_id = created.json()["id"]
    if hole_count:
        await client.put(
            f"/courses/{course_id}/holes",
            headers=headers,
            json={"holes": [{"hole_number": n} for n in range(1, hole_count + 1)]},
        )
    return course_id


async def tournament(client: AsyncClient, headers, course_id: str | None) -> str:
    payload: dict[str, object] = {"name": "Acme Corporate Day"}
    if course_id:
        payload["course_id"] = course_id
    created = await client.post("/tournaments", headers=headers, json=payload)
    assert created.status_code == 201, created.text
    return created.json()["id"]


async def set_status(client: AsyncClient, headers, tournament_id: str, target: TournamentStatus):
    return await client.post(
        f"/tournaments/{tournament_id}/status", headers=headers, json={"status": target.value}
    )


async def add_virtual(client: AsyncClient, headers, tournament_id: str, name: str) -> str:
    created = await client.post(
        f"/tournaments/{tournament_id}/participants/virtual",
        headers=headers,
        json={"display_name": name},
    )
    assert created.status_code == 201, created.text
    return created.json()["id"]


async def ready_tournament(
    client: AsyncClient, headers, player_count: int, hole_count: int = 18
) -> tuple[str, list[str]]:
    """A tournament with a course, a field, and registration closed."""
    course_id = await course(client, headers, hole_count)
    tournament_id = await tournament(client, headers, course_id)
    await set_status(client, headers, tournament_id, TournamentStatus.REGISTRATION_OPEN)

    participant_ids = [
        await add_virtual(client, headers, tournament_id, f"Player {index:02d}")
        for index in range(player_count)
    ]

    await set_status(client, headers, tournament_id, TournamentStatus.REGISTRATION_CLOSED)
    return tournament_id, participant_ids


async def draw(client: AsyncClient, headers, tournament_id: str):
    return await client.post(f"/tournaments/{tournament_id}/rounds", headers=headers)


async def drawn_group(client: AsyncClient, headers, player_count: int = 3) -> dict:
    """A tournament drawn into groups; returns the first group and its context."""
    tournament_id, participant_ids = await ready_tournament(client, headers, player_count)
    drawn = await draw(client, headers, tournament_id)
    assert drawn.status_code == 201, drawn.text

    round_ = drawn.json()
    group = round_["groups"][0]
    return {
        "tournament_id": tournament_id,
        "round_id": round_["id"],
        "participant_ids": participant_ids,
        "group_id": group["id"],
        "members": [member["participant_id"] for member in group["members"]],
        "holes": [hole["hole_id"] for hole in group["holes"]],
    }
