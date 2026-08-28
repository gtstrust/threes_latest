"""API-level tests for Fun Rounds.

A fun round is a casual round stored as a `kind=fun_round` tournament and driven by
FunRoundService. These tests exercise the orchestration — the lobby, the cap, the
single-group draw, scoring through the shared endpoints, finishing — and the
cross-kind guard that keeps fun rounds and tournaments from leaking into each
other's endpoints. The scoring cascade itself is covered against the pure engine in
test_scoring.py.
"""

import uuid

from httpx import AsyncClient

from app.models.tournament import TournamentStatus
from tests.helpers import course, player


async def _fun_round(client: AsyncClient, headers, course_id: str | None = None) -> dict:
    payload: dict[str, object] = {"name": "Saturday nine"}
    if course_id:
        payload["course_id"] = course_id
    created = await client.post("/fun-rounds", headers=headers, json=payload)
    assert created.status_code == 201, created.text
    return created.json()


async def _add_virtual(client: AsyncClient, headers, fun_round_id: str, name: str):
    return await client.post(
        f"/fun-rounds/{fun_round_id}/virtual", headers=headers, json={"display_name": name}
    )


async def _started_fun_round(client: AsyncClient, make_token) -> tuple[dict, dict]:
    """A host, a two-player fun round on a 3-hole course, started. Returns (detail, headers)."""
    host = await player(client, make_token, "host@example.com")
    course_id = await course(client, host, hole_count=3)
    fun_round = await _fun_round(client, host, course_id)
    await _add_virtual(client, host, fun_round["id"], "Mate")
    started = await client.post(f"/fun-rounds/{fun_round['id']}/start", headers=host)
    assert started.status_code == 200, started.text
    return started.json(), host


# --- Creating and joining ---------------------------------------------------


async def test_create_opens_a_lobby_with_the_host_enrolled(client, make_token):
    host = await player(client, make_token, "host@example.com")
    detail = await _fun_round(client, host)

    assert detail["status"] == "lobby"
    assert detail["round"] is None
    assert len(detail["participants"]) == 1
    enrolled = detail["participants"][0]
    assert enrolled["is_virtual"] is False


async def test_a_second_player_self_joins_by_link(client, make_token):
    host = await player(client, make_token, "host@example.com")
    detail = await _fun_round(client, host)

    mate = await player(client, make_token, "mate@example.com")
    joined = await client.post(f"/fun-rounds/{detail['id']}/players", headers=mate, json={})
    assert joined.status_code == 201, joined.text

    read = await client.get(f"/fun-rounds/{detail['id']}", headers=host)
    assert len(read.json()["participants"]) == 2


async def test_the_field_is_capped_at_four(client, make_token):
    host = await player(client, make_token, "host@example.com")
    detail = await _fun_round(client, host)  # host is #1
    for index in range(3):  # fill to four
        added = await _add_virtual(client, host, detail["id"], f"Mate {index}")
        assert added.status_code == 201, added.text

    fifth_virtual = await _add_virtual(client, host, detail["id"], "One too many")
    assert fifth_virtual.status_code == 409

    latecomer = await player(client, make_token, "late@example.com")
    join = await client.post(f"/fun-rounds/{detail['id']}/players", headers=latecomer, json={})
    assert join.status_code == 409


# --- Starting ---------------------------------------------------------------


async def test_start_draws_a_single_group_over_three_holes(client, make_token):
    detail, _ = await _started_fun_round(client, make_token)

    assert detail["status"] == "playing"
    assert len(detail["round"]["groups"]) == 1
    group = detail["round"]["groups"][0]
    assert len(group["members"]) == 2
    assert len(group["holes"]) == 3


async def test_start_needs_at_least_two_players(client, make_token):
    host = await player(client, make_token, "host@example.com")
    course_id = await course(client, host, hole_count=3)
    fun_round = await _fun_round(client, host, course_id)  # host alone

    started = await client.post(f"/fun-rounds/{fun_round['id']}/start", headers=host)
    assert started.status_code == 409


async def test_start_needs_a_course(client, make_token):
    host = await player(client, make_token, "host@example.com")
    fun_round = await _fun_round(client, host)  # no course
    await _add_virtual(client, host, fun_round["id"], "Mate")

    started = await client.post(f"/fun-rounds/{fun_round['id']}/start", headers=host)
    assert started.status_code == 409


# --- Scoring and finishing --------------------------------------------------


async def test_scoring_a_hole_shows_up_on_the_leaderboard(client, make_token):
    detail, host = await _started_fun_round(client, make_token)
    group = detail["round"]["groups"][0]
    round_id = detail["round"]["id"]
    hole_id = group["holes"][0]["hole_id"]
    members = [member["participant_id"] for member in group["members"]]

    submitted = await client.post(
        f"/groups/{group['id']}/holes/{hole_id}/scores",
        headers=host,
        json={"strokes": {members[0]: 3, members[1]: 5}},
    )
    assert submitted.status_code == 200, submitted.text

    board = await client.get(f"/rounds/{round_id}/leaderboard", headers=host)
    assert board.status_code == 200, board.text
    rows = {row["participant_id"]: row for row in board.json()["entries"]}
    assert rows[members[0]]["points"] == 1
    assert rows[members[1]]["points"] == 0


async def test_finish_marks_the_round_complete(client, make_token):
    detail, host = await _started_fun_round(client, make_token)

    finished = await client.post(f"/fun-rounds/{detail['id']}/finish", headers=host)
    assert finished.status_code == 200, finished.text
    assert finished.json()["status"] == "finished"


# --- The cross-kind guard ---------------------------------------------------


async def test_a_tournament_id_is_not_a_fun_round(client, make_token):
    host = await player(client, make_token, "host@example.com")
    created = await client.post("/tournaments", headers=host, json={"name": "Real event"})
    tournament_id = created.json()["id"]

    read = await client.get(f"/fun-rounds/{tournament_id}", headers=host)
    assert read.status_code == 404


async def test_a_fun_round_id_is_rejected_by_tournament_endpoints(client, make_token):
    host = await player(client, make_token, "host@example.com")
    fun_round = await _fun_round(client, host)

    # Cannot be hand-driven through the raw state machine...
    status_change = await client.post(
        f"/tournaments/{fun_round['id']}/status",
        headers=host,
        json={"status": TournamentStatus.REGISTRATION_CLOSED.value},
    )
    assert status_change.status_code == 404

    # ...nor have its single-group cap bypassed via the tournament participant route.
    joiner = await player(client, make_token, "sneaky@example.com")
    join = await client.post(
        f"/tournaments/{fun_round['id']}/participants", headers=joiner, json={}
    )
    assert join.status_code == 404


async def test_missing_fun_round_is_404(client, make_token):
    host = await player(client, make_token, "host@example.com")
    read = await client.get(f"/fun-rounds/{uuid.uuid4()}", headers=host)
    assert read.status_code == 404
