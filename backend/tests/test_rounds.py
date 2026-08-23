"""API-level tests for drawing rounds and playing them."""

import random
import uuid

import pytest
from httpx import AsyncClient

from app.models.round import RoundStatus
from app.models.tournament import TournamentStatus


async def _player(client: AsyncClient, make_token, email: str):
    headers = {"Authorization": f"Bearer {make_token(email=email)}"}
    await client.post("/players", headers=headers)
    return headers


async def _course(client: AsyncClient, headers, hole_count: int = 18) -> str:
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


async def _tournament(client: AsyncClient, headers, course_id: str | None) -> str:
    payload: dict[str, object] = {"name": "Acme Corporate Day"}
    if course_id:
        payload["course_id"] = course_id
    created = await client.post("/tournaments", headers=headers, json=payload)
    assert created.status_code == 201, created.text
    return created.json()["id"]


async def _set_status(client: AsyncClient, headers, tournament_id: str, target: TournamentStatus):
    return await client.post(
        f"/tournaments/{tournament_id}/status", headers=headers, json={"status": target.value}
    )


async def _add_virtual(client: AsyncClient, headers, tournament_id: str, name: str) -> str:
    created = await client.post(
        f"/tournaments/{tournament_id}/participants/virtual",
        headers=headers,
        json={"display_name": name},
    )
    assert created.status_code == 201, created.text
    return created.json()["id"]


async def _ready_tournament(
    client: AsyncClient, headers, player_count: int, hole_count: int = 18
) -> tuple[str, list[str]]:
    """A tournament with a course, a field, and registration closed."""
    course_id = await _course(client, headers, hole_count)
    tournament_id = await _tournament(client, headers, course_id)
    await _set_status(client, headers, tournament_id, TournamentStatus.REGISTRATION_OPEN)

    participant_ids = [
        await _add_virtual(client, headers, tournament_id, f"Player {index:02d}")
        for index in range(player_count)
    ]

    await _set_status(client, headers, tournament_id, TournamentStatus.REGISTRATION_CLOSED)
    return tournament_id, participant_ids


async def _draw(client: AsyncClient, headers, tournament_id: str):
    return await client.post(f"/tournaments/{tournament_id}/rounds", headers=headers)


# --- The draw ---------------------------------------------------------------


@pytest.mark.asyncio
async def test_drawing_a_round_starts_play(client, make_token):
    organiser = await _player(client, make_token, "organiser@example.com")
    tournament_id, _ = await _ready_tournament(client, organiser, player_count=6)

    response = await _draw(client, organiser, tournament_id)

    assert response.status_code == 201, response.text
    assert response.json()["round_number"] == 1
    assert response.json()["status"] == RoundStatus.IN_PROGRESS.value

    tournament = await client.get(f"/tournaments/{tournament_id}", headers=organiser)
    assert tournament.json()["status"] == TournamentStatus.ROUND_IN_PROGRESS.value


@pytest.mark.asyncio
async def test_round_one_follows_registration_order_so_mates_play_together(client, make_token):
    organiser = await _player(client, make_token, "organiser@example.com")
    tournament_id, registered = await _ready_tournament(client, organiser, player_count=6)

    drawn = await _draw(client, organiser, tournament_id)

    groups = drawn.json()["groups"]
    assert [[member["participant_id"] for member in group["members"]] for group in groups] == [
        registered[0:3],
        registered[3:6],
    ]


@pytest.mark.asyncio
async def test_later_rounds_are_shuffled(client, make_token):
    """Round 2 mixes the field rather than repeating round 1's grouping."""
    random.seed(20260822)  # deterministic shuffle, so this can't flake
    organiser = await _player(client, make_token, "organiser@example.com")
    tournament_id, registered = await _ready_tournament(client, organiser, player_count=12)

    first = await _draw(client, organiser, tournament_id)
    await client.post(f"/rounds/{first.json()['id']}/complete", headers=organiser)
    second = await _draw(client, organiser, tournament_id)

    def grouping(payload) -> list[set[str]]:
        return [{member["participant_id"] for member in g["members"]} for g in payload["groups"]]

    assert second.json()["round_number"] == 2
    assert grouping(first.json()) != grouping(second.json())
    # Same field, just rearranged.
    assert {p for group in grouping(second.json()) for p in group} == set(registered)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("player_count", "expected_sizes"),
    [(2, [2]), (4, [4]), (6, [3, 3]), (7, [3, 4]), (24, [3] * 8)],
)
async def test_everyone_is_placed_in_exactly_one_group(
    client, make_token, player_count, expected_sizes
):
    organiser = await _player(client, make_token, "organiser@example.com")
    tournament_id, registered = await _ready_tournament(client, organiser, player_count)

    groups = (await _draw(client, organiser, tournament_id)).json()["groups"]

    placed = [m["participant_id"] for group in groups for m in group["members"]]
    assert sorted(placed) == sorted(registered)
    assert [len(group["members"]) for group in groups] == expected_sizes


# --- Loops ------------------------------------------------------------------


@pytest.mark.asyncio
async def test_every_group_gets_three_holes_in_sequence(client, make_token):
    organiser = await _player(client, make_token, "organiser@example.com")
    tournament_id, _ = await _ready_tournament(client, organiser, player_count=6)

    groups = (await _draw(client, organiser, tournament_id)).json()["groups"]

    for group in groups:
        assert [hole["sequence"] for hole in group["holes"]] == [1, 2, 3]


@pytest.mark.asyncio
async def test_groups_get_their_own_loops_when_the_course_allows(client, make_token):
    """A shotgun start: six groups on 18 holes means six distinct loops."""
    organiser = await _player(client, make_token, "organiser@example.com")
    tournament_id, _ = await _ready_tournament(client, organiser, player_count=18)

    groups = (await _draw(client, organiser, tournament_id)).json()["groups"]

    loops = [tuple(hole["hole_id"] for hole in group["holes"]) for group in groups]
    assert len(groups) == 6
    assert len(set(loops)) == 6


@pytest.mark.asyncio
async def test_loops_are_shared_once_groups_outnumber_them(client, make_token):
    """24 players is 8 groups, but 18 holes only make 6 loops."""
    organiser = await _player(client, make_token, "organiser@example.com")
    tournament_id, _ = await _ready_tournament(client, organiser, player_count=24)

    groups = (await _draw(client, organiser, tournament_id)).json()["groups"]

    loops = [tuple(hole["hole_id"] for hole in group["holes"]) for group in groups]
    assert len(groups) == 8
    assert len(set(loops)) == 6
    # Groups 7 and 8 double up on the first two loops.
    assert loops[6] == loops[0]
    assert loops[7] == loops[1]
    assert all(len(group["holes"]) == 3 for group in groups)


@pytest.mark.asyncio
async def test_every_hole_played_belongs_to_the_tournaments_course(client, make_token):
    """Holds by construction, since loops come from the course's own holes."""
    organiser = await _player(client, make_token, "organiser@example.com")
    course_id = await _course(client, organiser, hole_count=9)
    tournament_id = await _tournament(client, organiser, course_id)
    await _set_status(client, organiser, tournament_id, TournamentStatus.REGISTRATION_OPEN)
    for index in range(6):
        await _add_virtual(client, organiser, tournament_id, f"Player {index}")
    await _set_status(client, organiser, tournament_id, TournamentStatus.REGISTRATION_CLOSED)

    groups = (await _draw(client, organiser, tournament_id)).json()["groups"]

    course = await client.get(f"/courses/{course_id}", headers=organiser)
    course_hole_ids = {hole["id"] for hole in course.json()["holes"]}
    played = {hole["hole_id"] for group in groups for hole in group["holes"]}
    assert played <= course_hole_ids


# --- Refusing to draw -------------------------------------------------------


@pytest.mark.asyncio
async def test_a_round_cannot_be_drawn_before_registration_closes(client, make_token):
    organiser = await _player(client, make_token, "organiser@example.com")
    course_id = await _course(client, organiser)
    tournament_id = await _tournament(client, organiser, course_id)
    await _set_status(client, organiser, tournament_id, TournamentStatus.REGISTRATION_OPEN)

    response = await _draw(client, organiser, tournament_id)

    assert response.status_code == 409
    assert "Close registration first" in response.json()["detail"]


@pytest.mark.asyncio
async def test_a_round_cannot_be_drawn_without_a_course(client, make_token):
    organiser = await _player(client, make_token, "organiser@example.com")
    tournament_id = await _tournament(client, organiser, course_id=None)
    await _set_status(client, organiser, tournament_id, TournamentStatus.REGISTRATION_OPEN)
    await _add_virtual(client, organiser, tournament_id, "Pat")
    await _add_virtual(client, organiser, tournament_id, "Sam")
    await _set_status(client, organiser, tournament_id, TournamentStatus.REGISTRATION_CLOSED)

    response = await _draw(client, organiser, tournament_id)

    assert response.status_code == 409
    assert "no course set" in response.json()["detail"]


@pytest.mark.asyncio
async def test_a_round_cannot_be_drawn_on_a_course_with_too_few_holes(client, make_token):
    organiser = await _player(client, make_token, "organiser@example.com")
    tournament_id, _ = await _ready_tournament(client, organiser, player_count=4, hole_count=2)

    response = await _draw(client, organiser, tournament_id)

    assert response.status_code == 409
    assert "needs 3 holes" in response.json()["detail"]


@pytest.mark.asyncio
async def test_a_lone_player_cannot_be_drawn(client, make_token):
    organiser = await _player(client, make_token, "organiser@example.com")
    tournament_id, _ = await _ready_tournament(client, organiser, player_count=1)

    response = await _draw(client, organiser, tournament_id)

    assert response.status_code == 409
    assert "single player" in response.json()["detail"]


@pytest.mark.asyncio
async def test_only_the_organiser_can_draw(client, make_token):
    organiser = await _player(client, make_token, "organiser@example.com")
    tournament_id, _ = await _ready_tournament(client, organiser, player_count=4)
    stranger = await _player(client, make_token, "stranger@example.com")

    assert (await _draw(client, stranger, tournament_id)).status_code == 403


# --- The status endpoint no longer owns play -------------------------------


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("target", "expected_endpoint"),
    [
        (TournamentStatus.ROUND_IN_PROGRESS, "/rounds"),
        (TournamentStatus.ROUND_COMPLETE, "/complete"),
    ],
)
async def test_play_statuses_cannot_be_set_directly(client, make_token, target, expected_endpoint):
    """Otherwise a tournament could claim play had started with no round drawn."""
    organiser = await _player(client, make_token, "organiser@example.com")
    tournament_id, _ = await _ready_tournament(client, organiser, player_count=6)

    response = await _set_status(client, organiser, tournament_id, target)

    assert response.status_code == 409
    detail = response.json()["detail"]
    assert "not directly" in detail
    assert expected_endpoint in detail


# --- Completing a round -----------------------------------------------------


@pytest.mark.asyncio
async def test_completing_a_round_moves_both_it_and_the_tournament(client, make_token):
    organiser = await _player(client, make_token, "organiser@example.com")
    tournament_id, _ = await _ready_tournament(client, organiser, player_count=6)
    round_id = (await _draw(client, organiser, tournament_id)).json()["id"]

    response = await client.post(f"/rounds/{round_id}/complete", headers=organiser)

    assert response.status_code == 200
    assert response.json()["status"] == RoundStatus.COMPLETE.value
    tournament = await client.get(f"/tournaments/{tournament_id}", headers=organiser)
    assert tournament.json()["status"] == TournamentStatus.ROUND_COMPLETE.value


@pytest.mark.asyncio
async def test_a_round_cannot_be_completed_twice(client, make_token):
    organiser = await _player(client, make_token, "organiser@example.com")
    tournament_id, _ = await _ready_tournament(client, organiser, player_count=6)
    round_id = (await _draw(client, organiser, tournament_id)).json()["id"]
    await client.post(f"/rounds/{round_id}/complete", headers=organiser)

    again = await client.post(f"/rounds/{round_id}/complete", headers=organiser)

    assert again.status_code == 409
    assert "not in progress" in again.json()["detail"]


@pytest.mark.asyncio
async def test_only_the_organiser_can_complete_a_round(client, make_token):
    organiser = await _player(client, make_token, "organiser@example.com")
    tournament_id, _ = await _ready_tournament(client, organiser, player_count=6)
    round_id = (await _draw(client, organiser, tournament_id)).json()["id"]
    stranger = await _player(client, make_token, "stranger@example.com")

    response = await client.post(f"/rounds/{round_id}/complete", headers=stranger)

    assert response.status_code == 403


@pytest.mark.asyncio
async def test_the_tournament_can_finish_after_a_round_completes(client, make_token):
    organiser = await _player(client, make_token, "organiser@example.com")
    tournament_id, _ = await _ready_tournament(client, organiser, player_count=6)
    round_id = (await _draw(client, organiser, tournament_id)).json()["id"]
    await client.post(f"/rounds/{round_id}/complete", headers=organiser)

    response = await _set_status(
        client, organiser, tournament_id, TournamentStatus.TOURNAMENT_COMPLETE
    )

    assert response.status_code == 200


# --- Reading ----------------------------------------------------------------


@pytest.mark.asyncio
async def test_listing_and_reading_rounds(client, make_token):
    organiser = await _player(client, make_token, "organiser@example.com")
    tournament_id, _ = await _ready_tournament(client, organiser, player_count=6)
    round_id = (await _draw(client, organiser, tournament_id)).json()["id"]

    listed = await client.get(f"/tournaments/{tournament_id}/rounds", headers=organiser)
    detail = await client.get(f"/rounds/{round_id}", headers=organiser)

    assert [row["round_number"] for row in listed.json()] == [1]
    assert len(detail.json()["groups"]) == 2


@pytest.mark.asyncio
async def test_a_group_can_be_read_on_its_own(client, make_token):
    organiser = await _player(client, make_token, "organiser@example.com")
    tournament_id, _ = await _ready_tournament(client, organiser, player_count=6)
    drawn = await _draw(client, organiser, tournament_id)
    group_id = drawn.json()["groups"][0]["id"]

    response = await client.get(f"/groups/{group_id}", headers=organiser)

    assert response.status_code == 200
    assert len(response.json()["members"]) == 3
    assert len(response.json()["holes"]) == 3


@pytest.mark.asyncio
async def test_non_participants_cannot_read_the_draw(client, make_token):
    organiser = await _player(client, make_token, "organiser@example.com")
    tournament_id, _ = await _ready_tournament(client, organiser, player_count=6)
    drawn = await _draw(client, organiser, tournament_id)
    stranger = await _player(client, make_token, "stranger@example.com")

    assert (await client.get(f"/rounds/{drawn.json()['id']}", headers=stranger)).status_code == 403
    assert (
        await client.get(f"/groups/{drawn.json()['groups'][0]['id']}", headers=stranger)
    ).status_code == 403
    assert (
        await client.get(f"/tournaments/{tournament_id}/rounds", headers=stranger)
    ).status_code == 403


@pytest.mark.asyncio
async def test_unknown_round_and_group_are_404(client, make_token):
    headers = await _player(client, make_token, "player@example.com")

    assert (await client.get(f"/rounds/{uuid.uuid4()}", headers=headers)).status_code == 404
    assert (await client.get(f"/groups/{uuid.uuid4()}", headers=headers)).status_code == 404


@pytest.mark.asyncio
async def test_rounds_require_authentication(client, make_token):
    organiser = await _player(client, make_token, "organiser@example.com")
    tournament_id, _ = await _ready_tournament(client, organiser, player_count=4)

    assert (await client.post(f"/tournaments/{tournament_id}/rounds")).status_code in (401, 403)
    assert (await client.get(f"/tournaments/{tournament_id}/rounds")).status_code in (401, 403)
