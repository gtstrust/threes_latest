"""API-level tests for the leaderboard.

The ranking itself — order, the stroke tie-break, shared positions and the skip —
is covered against the pure engine in test_scoring.py. What matters here is
everything the engine can't know: who belongs on the board, that the stored
points from ADR-009 are what gets summed, and that a round's board and the
cumulative one differ in the right way.
"""

import uuid

import pytest
from httpx import AsyncClient

from app.models.tournament import TournamentStatus
from tests.helpers import (
    course,
    draw,
    drawn_group,
    player,
    ready_tournament,
    set_status,
    tournament,
)


async def _submit(client: AsyncClient, headers, group_id, hole_id, strokes, **tie_breaks):
    payload: dict[str, object] = {"strokes": strokes}
    payload.update({key: value for key, value in tie_breaks.items() if value is not None})
    response = await client.post(
        f"/groups/{group_id}/holes/{hole_id}/scores", headers=headers, json=payload
    )
    assert response.status_code == 200, response.text
    return response


async def _board(client: AsyncClient, headers, path: str) -> list[dict]:
    response = await client.get(path, headers=headers)
    assert response.status_code == 200, response.text
    return response.json()["entries"]


def _by_id(entries: list[dict]) -> dict[str, dict]:
    return {entry["participant_id"]: entry for entry in entries}


# --- The field --------------------------------------------------------------


@pytest.mark.asyncio
async def test_the_whole_field_appears_before_anything_is_scored(client, make_token):
    """A board missing unscored players reads as a bug, not as "still out there"."""
    organiser = await player(client, make_token, "organiser@example.com")
    tournament_id, participant_ids = await ready_tournament(client, organiser, player_count=6)

    entries = await _board(client, organiser, f"/tournaments/{tournament_id}/leaderboard")

    assert len(entries) == 6
    assert set(_by_id(entries)) == set(participant_ids)
    assert all(entry["points"] == 0 for entry in entries)
    assert all(entry["total_strokes"] == 0 for entry in entries)
    assert all(entry["holes_played"] == 0 for entry in entries)
    assert [entry["position"] for entry in entries] == [1] * 6


@pytest.mark.asyncio
async def test_a_drawn_but_unplayed_round_lists_its_field(client, make_token):
    organiser = await player(client, make_token, "organiser@example.com")
    ctx = await drawn_group(client, organiser, player_count=6)

    entries = await _board(client, organiser, f"/rounds/{ctx['round_id']}/leaderboard")

    assert set(_by_id(entries)) == set(ctx["participant_ids"])
    assert all(entry["holes_played"] == 0 for entry in entries)


@pytest.mark.asyncio
async def test_entries_carry_the_registration_snapshot_name(client, make_token):
    organiser = await player(client, make_token, "organiser@example.com")
    tournament_id, _ = await ready_tournament(client, organiser, player_count=3)

    entries = await _board(client, organiser, f"/tournaments/{tournament_id}/leaderboard")

    assert {entry["display_name"] for entry in entries} == {
        "Player 00",
        "Player 01",
        "Player 02",
    }


# --- Accumulation -----------------------------------------------------------


@pytest.mark.asyncio
async def test_points_and_strokes_accumulate_across_the_loop(client, make_token):
    organiser = await player(client, make_token, "organiser@example.com")
    ctx = await drawn_group(client, organiser)
    a, b, c = ctx["members"]

    await _submit(client, organiser, ctx["group_id"], ctx["holes"][0], {a: 3, b: 4, c: 5})
    await _submit(client, organiser, ctx["group_id"], ctx["holes"][1], {a: 4, b: 3, c: 5})
    await _submit(client, organiser, ctx["group_id"], ctx["holes"][2], {a: 3, b: 4, c: 5})

    entries = _by_id(await _board(client, organiser, f"/rounds/{ctx['round_id']}/leaderboard"))

    assert entries[a]["points"] == 2
    assert entries[b]["points"] == 1
    assert entries[c]["points"] == 0
    assert entries[a]["total_strokes"] == 10
    assert entries[b]["total_strokes"] == 11
    assert entries[c]["total_strokes"] == 15
    assert entries[a]["position"] == 1
    assert entries[b]["position"] == 2
    assert entries[c]["position"] == 3


@pytest.mark.asyncio
async def test_holes_played_tracks_a_partly_finished_loop(client, make_token):
    organiser = await player(client, make_token, "organiser@example.com")
    ctx = await drawn_group(client, organiser)
    a, b, c = ctx["members"]

    await _submit(client, organiser, ctx["group_id"], ctx["holes"][0], {a: 3, b: 4, c: 5})
    await _submit(client, organiser, ctx["group_id"], ctx["holes"][1], {a: 4, b: 3, c: 5})

    entries = _by_id(await _board(client, organiser, f"/rounds/{ctx['round_id']}/leaderboard"))

    assert all(entries[pid]["holes_played"] == 2 for pid in (a, b, c))


@pytest.mark.asyncio
async def test_a_correction_is_reflected_not_added(client, make_token):
    """Re-submitting rewrites the hole, so the board must not double-count it."""
    organiser = await player(client, make_token, "organiser@example.com")
    ctx = await drawn_group(client, organiser)
    a, b, c = ctx["members"]

    await _submit(client, organiser, ctx["group_id"], ctx["holes"][0], {a: 3, b: 4, c: 5})
    await _submit(client, organiser, ctx["group_id"], ctx["holes"][0], {a: 6, b: 4, c: 5})

    entries = _by_id(await _board(client, organiser, f"/rounds/{ctx['round_id']}/leaderboard"))

    assert entries[b]["points"] == 1
    assert entries[a]["points"] == 0
    assert entries[a]["total_strokes"] == 6
    assert entries[a]["holes_played"] == 1


# --- Ranking, over the wire -------------------------------------------------


@pytest.mark.asyncio
async def test_players_level_on_points_are_split_by_fewest_strokes(client, make_token):
    organiser = await player(client, make_token, "organiser@example.com")
    ctx = await drawn_group(client, organiser)
    a, b, c = ctx["members"]

    # A and B take a hole each; A does it in fewer strokes overall.
    await _submit(client, organiser, ctx["group_id"], ctx["holes"][0], {a: 3, b: 6, c: 7})
    await _submit(client, organiser, ctx["group_id"], ctx["holes"][1], {a: 4, b: 3, c: 7})

    entries = await _board(client, organiser, f"/rounds/{ctx['round_id']}/leaderboard")
    ranked = _by_id(entries)

    assert ranked[a]["points"] == ranked[b]["points"] == 1
    assert ranked[a]["total_strokes"] < ranked[b]["total_strokes"]
    assert [entry["participant_id"] for entry in entries] == [a, b, c]
    assert [entry["position"] for entry in entries] == [1, 2, 3]


@pytest.mark.asyncio
async def test_players_level_on_both_share_a_position(client, make_token):
    organiser = await player(client, make_token, "organiser@example.com")
    ctx = await drawn_group(client, organiser)
    a, b, c = ctx["members"]

    # Nobody wins: all three tie on strokes with no tie-break answer, so every
    # player finishes on 0 points and identical strokes (ADR-007).
    await _submit(client, organiser, ctx["group_id"], ctx["holes"][0], {a: 4, b: 4, c: 4})

    entries = await _board(client, organiser, f"/rounds/{ctx['round_id']}/leaderboard")

    assert [entry["position"] for entry in entries] == [1, 1, 1]
    assert all(entry["points"] == 0 for entry in entries)


@pytest.mark.asyncio
async def test_fully_tied_players_keep_registration_order_across_requests(client, make_token):
    """rank_leaderboard's sort is stable, so the input order must be stable too."""
    organiser = await player(client, make_token, "organiser@example.com")
    tournament_id, participant_ids = await ready_tournament(client, organiser, player_count=6)
    await draw(client, organiser, tournament_id)

    first = await _board(client, organiser, f"/tournaments/{tournament_id}/leaderboard")
    second = await _board(client, organiser, f"/tournaments/{tournament_id}/leaderboard")

    assert [entry["participant_id"] for entry in first] == participant_ids
    assert [entry["participant_id"] for entry in second] == participant_ids


# --- Round versus tournament ------------------------------------------------


@pytest.mark.asyncio
async def test_the_tournament_board_sums_rounds_the_round_board_does_not(client, make_token):
    organiser = await player(client, make_token, "organiser@example.com")
    ctx = await drawn_group(client, organiser)
    a, b, c = ctx["members"]

    await _submit(client, organiser, ctx["group_id"], ctx["holes"][0], {a: 3, b: 4, c: 5})

    completed = await client.post(f"/rounds/{ctx['round_id']}/complete", headers=organiser)
    assert completed.status_code == 200, completed.text

    drawn = await draw(client, organiser, ctx["tournament_id"])
    assert drawn.status_code == 201, drawn.text
    second = drawn.json()
    second_group = second["groups"][0]
    members = [member["participant_id"] for member in second_group["members"]]
    holes = [hole["hole_id"] for hole in second_group["holes"]]

    # Whoever the shuffle put first in round 2 wins its opening hole.
    winner = members[0]
    await _submit(
        client,
        organiser,
        second_group["id"],
        holes[0],
        {members[0]: 3, members[1]: 4, members[2]: 5},
    )

    round_one = _by_id(await _board(client, organiser, f"/rounds/{ctx['round_id']}/leaderboard"))
    round_two = _by_id(await _board(client, organiser, f"/rounds/{second['id']}/leaderboard"))
    overall = _by_id(
        await _board(client, organiser, f"/tournaments/{ctx['tournament_id']}/leaderboard")
    )

    assert round_one[a]["points"] == 1
    assert round_one[a]["holes_played"] == 1
    assert round_two[a]["holes_played"] == 1
    assert round_two[winner]["points"] == 1

    assert sum(entry["points"] for entry in overall.values()) == 2
    assert overall[a]["holes_played"] == 2
    assert overall[winner]["points"] == (2 if winner == a else 1)


@pytest.mark.asyncio
async def test_a_round_board_covers_the_whole_field_not_just_one_group(client, make_token):
    organiser = await player(client, make_token, "organiser@example.com")
    ctx = await drawn_group(client, organiser, player_count=6)
    a, b, c = ctx["members"]

    await _submit(client, organiser, ctx["group_id"], ctx["holes"][0], {a: 3, b: 4, c: 5})

    entries = _by_id(await _board(client, organiser, f"/rounds/{ctx['round_id']}/leaderboard"))

    assert len(entries) == 6
    assert entries[a]["points"] == 1
    # The other group hasn't teed off; they are listed, on nothing.
    untouched = set(ctx["participant_ids"]) - set(ctx["members"])
    assert all(entries[pid]["holes_played"] == 0 for pid in untouched)


# --- Not found, and who may look -------------------------------------------


@pytest.mark.asyncio
async def test_an_unknown_tournament_is_404(client, make_token):
    organiser = await player(client, make_token, "organiser@example.com")
    response = await client.get(f"/tournaments/{uuid.uuid4()}/leaderboard", headers=organiser)
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_an_unknown_round_is_404(client, make_token):
    organiser = await player(client, make_token, "organiser@example.com")
    response = await client.get(f"/rounds/{uuid.uuid4()}/leaderboard", headers=organiser)
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_an_outsider_cannot_read_the_board(client, make_token):
    organiser = await player(client, make_token, "organiser@example.com")
    ctx = await drawn_group(client, organiser)
    outsider = await player(client, make_token, "outsider@example.com")

    overall = await client.get(f"/tournaments/{ctx['tournament_id']}/leaderboard", headers=outsider)
    per_round = await client.get(f"/rounds/{ctx['round_id']}/leaderboard", headers=outsider)

    assert overall.status_code == 403
    assert per_round.status_code == 403


@pytest.mark.asyncio
async def test_a_player_in_the_field_can_read_the_board(client, make_token):
    organiser = await player(client, make_token, "organiser@example.com")
    course_id = await course(client, organiser)
    tournament_id = await tournament(client, organiser, course_id)
    await set_status(client, organiser, tournament_id, TournamentStatus.REGISTRATION_OPEN)

    competitor = await player(client, make_token, "competitor@example.com")
    joined = await client.post(
        f"/tournaments/{tournament_id}/participants",
        headers=competitor,
        json={"display_name": "Competitor"},
    )
    assert joined.status_code == 201, joined.text

    entries = await _board(client, competitor, f"/tournaments/{tournament_id}/leaderboard")

    assert [entry["participant_id"] for entry in entries] == [joined.json()["id"]]
