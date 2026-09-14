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


async def course(
    client: AsyncClient, headers, hole_count: int = 18, *, stroke_indexes: bool = False
) -> str:
    """A course. `stroke_indexes` gives every hole one, which handicaps need.

    Off by default, because that is what every course in the product looks like:
    nothing has ever sent a stroke index, so a test that assumes one would be
    testing a database no organiser has.
    """
    created = await client.post(
        "/courses", headers=headers, json={"name": f"Course {uuid.uuid4()}"}
    )
    course_id = created.json()["id"]
    if hole_count:
        holes: list[dict[str, int]] = []
        for n in range(1, hole_count + 1):
            hole: dict[str, int] = {"hole_number": n}
            if stroke_indexes:
                # Reversed, so stroke index never equals hole number — a test that
                # passes only because the two coincide is testing nothing.
                hole["stroke_index"] = hole_count - n + 1
            holes.append(hole)
        await client.put(f"/courses/{course_id}/holes", headers=headers, json={"holes": holes})
    return course_id


async def tournament(
    client: AsyncClient,
    headers,
    course_id: str | None,
    *,
    format: str = "ROUND_ROBIN",
    group_size: int = 3,
    loop_style: str = "BLOCKS",
    handicap_enabled: bool = False,
) -> str:
    """Defaults are today's values, so every existing caller is unchanged."""
    payload: dict[str, object] = {
        "name": "Acme Corporate Day",
        "format": format,
        "group_size": group_size,
        "loop_style": loop_style,
        "handicap_enabled": handicap_enabled,
    }
    if course_id:
        payload["course_id"] = course_id
    created = await client.post("/tournaments", headers=headers, json=payload)
    assert created.status_code == 201, created.text
    return created.json()["id"]


async def set_status(client: AsyncClient, headers, tournament_id: str, target: TournamentStatus):
    return await client.post(
        f"/tournaments/{tournament_id}/status", headers=headers, json={"status": target.value}
    )


async def add_virtual(
    client: AsyncClient,
    headers,
    tournament_id: str,
    name: str,
    playing_handicap: int | None = None,
) -> str:
    body: dict[str, object] = {"display_name": name}
    if playing_handicap is not None:
        body["playing_handicap"] = playing_handicap
    created = await client.post(
        f"/tournaments/{tournament_id}/participants/virtual",
        headers=headers,
        json=body,
    )
    assert created.status_code == 201, created.text
    return created.json()["id"]


async def ready_tournament(
    client: AsyncClient,
    headers,
    player_count: int,
    hole_count: int = 18,
    *,
    format: str = "ROUND_ROBIN",
    group_size: int = 3,
    loop_style: str = "BLOCKS",
) -> tuple[str, list[str]]:
    """A tournament with a course, a field, and registration closed."""
    course_id = await course(client, headers, hole_count)
    tournament_id = await tournament(
        client,
        headers,
        course_id,
        format=format,
        group_size=group_size,
        loop_style=loop_style,
    )
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
