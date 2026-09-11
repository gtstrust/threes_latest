"""Knockout brackets — ADR-012: each group is a match and one player goes through.

The headline is a full 64-player bracket end to end, because the arithmetic is
the feature: 64 fourballs collapse to 16 groups, then 4, then 1. Everything else
uses an 8-player field so the suite stays quick.
"""

import uuid

import pytest
from httpx import AsyncClient

from app.models.tournament import TournamentStatus
from tests.helpers import add_virtual, course, player, set_status, tournament

KNOCKOUT = "KNOCKOUT"


async def _bracket(
    client: AsyncClient, headers, player_count: int, hole_count: int = 18
) -> tuple[str, str, list[str]]:
    """A knockout in fourballs on a shotgun, registration closed."""
    course_id = await course(client, headers, hole_count)
    tournament_id = await tournament(
        client, headers, course_id, format=KNOCKOUT, group_size=4, loop_style="SHOTGUN"
    )
    await set_status(client, headers, tournament_id, TournamentStatus.REGISTRATION_OPEN)
    participant_ids = [
        await add_virtual(client, headers, tournament_id, f"Player {index:02d}")
        for index in range(player_count)
    ]
    await set_status(client, headers, tournament_id, TournamentStatus.REGISTRATION_CLOSED)
    return tournament_id, course_id, participant_ids


async def _draw(client: AsyncClient, headers, tournament_id: str):
    return await client.post(f"/tournaments/{tournament_id}/rounds", headers=headers)


async def _score(client, headers, group, strokes_by_member, hole_index=0, ctp=None):
    """Submit one hole for a group, optionally answering the tie-break."""
    hole_id = sorted(group["holes"], key=lambda h: h["sequence"])[hole_index]["hole_id"]
    body: dict[str, object] = {"strokes": strokes_by_member}
    if ctp is not None:
        body["closest_to_pin"] = ctp
    return await client.post(
        f"/groups/{group['id']}/holes/{hole_id}/scores", headers=headers, json=body
    )


async def _play(client, headers, round_payload, *, winner_of=None):
    """Play every hole of every group. `winner_of(group) -> member` takes the loop."""
    for group in round_payload["groups"]:
        members = [m["participant_id"] for m in group["members"]]
        winner = winner_of(group) if winner_of else members[0]
        for hole_index in range(len(group["holes"])):
            strokes = {member: 5 for member in members}
            strokes[winner] = 3
            response = await _score(client, headers, group, strokes, hole_index)
            assert response.status_code == 200, response.text


async def _halve(client, headers, group, first=None):
    """Halve every hole of a group, leaving `first` on the fewest strokes.

    Each hole ties the intended winner with a different opponent on the lowest
    score, so nobody wins a hole (ADR-007 halves it with no tie-break answer) and
    yet the totals still separate: the winner is on 3 every hole, everyone else
    on 3 once and 4 twice.
    """
    members = [m["participant_id"] for m in group["members"]]
    if first is not None:
        members = [first] + [member for member in members if member != first]

    for hole_index in range(len(group["holes"])):
        strokes = {member: 4 for member in members}
        strokes[members[0]] = 3
        strokes[members[1 + hole_index % (len(members) - 1)]] = 3
        response = await _score(client, headers, group, strokes, hole_index)
        assert response.status_code == 200, response.text


async def _complete(client, headers, round_id: str):
    return await client.post(f"/rounds/{round_id}/complete", headers=headers)


# --- The bracket ------------------------------------------------------------


@pytest.mark.asyncio
async def test_sixty_four_players_collapse_to_a_champion_in_three_rounds(client, make_token):
    """The whole feature, end to end. The slowest test here, and worth it.

    64 sequential participant POSTs plus 84 scored holes — it is the only thing
    that proves the arithmetic holds at the scale the format was designed for.
    """
    organiser = await player(client, make_token, "organiser@example.com")
    tournament_id, course_id, participant_ids = await _bracket(client, organiser, 64)

    survivors = set(participant_ids)
    for expected_groups in (16, 4, 1):
        drawn = await _draw(client, organiser, tournament_id)
        assert drawn.status_code == 201, drawn.text
        payload = drawn.json()

        assert len(payload["groups"]) == expected_groups
        assert all(len(group["members"]) == 4 for group in payload["groups"])

        drawn_players = {
            member["participant_id"] for group in payload["groups"] for member in group["members"]
        }
        # Only players who won their last group are here — nobody sneaks back in.
        assert drawn_players <= survivors
        assert len(drawn_players) == expected_groups * 4

        await _play(client, organiser, payload)
        assert (await _complete(client, organiser, payload["id"])).status_code == 200

        current = await client.get(f"/rounds/{payload['id']}", headers=organiser)
        survivors = {group["advancing_participant_id"] for group in current.json()["groups"]}
        assert None not in survivors
        assert len(survivors) == expected_groups
        assert all(group["advanced_by"] == "points" for group in current.json()["groups"])

    # One player left: the draw refuses rather than answering "single player".
    refused = await _draw(client, organiser, tournament_id)
    assert refused.status_code == 409
    detail = refused.json()["detail"]
    assert "has won" in detail
    assert "TOURNAMENT_COMPLETE" in detail

    finished = await set_status(
        client, organiser, tournament_id, TournamentStatus.TOURNAMENT_COMPLETE
    )
    assert finished.status_code == 200


@pytest.mark.asyncio
async def test_a_later_round_is_drawn_from_the_winners_not_the_field(client, make_token):
    organiser = await player(client, make_token, "organiser@example.com")
    tournament_id, _, participant_ids = await _bracket(client, organiser, 8)

    first = (await _draw(client, organiser, tournament_id)).json()
    await _play(client, organiser, first)
    await _complete(client, organiser, first["id"])

    winners = {
        group["advancing_participant_id"]
        for group in (await client.get(f"/rounds/{first['id']}", headers=organiser)).json()[
            "groups"
        ]
    }

    second = (await _draw(client, organiser, tournament_id)).json()
    drawn = {m["participant_id"] for g in second["groups"] for m in g["members"]}

    assert drawn == winners
    assert len(drawn) == 2  # eight players, two groups, two winners
    assert len(set(participant_ids) - drawn) == 6


@pytest.mark.asyncio
async def test_a_round_board_lists_only_the_players_still_in(client, make_token):
    """`_round_field` was written for exactly this and needs no change."""
    organiser = await player(client, make_token, "organiser@example.com")
    tournament_id, _, _ = await _bracket(client, organiser, 8)

    first = (await _draw(client, organiser, tournament_id)).json()
    await _play(client, organiser, first)
    await _complete(client, organiser, first["id"])
    second = (await _draw(client, organiser, tournament_id)).json()

    board = await client.get(f"/rounds/{second['id']}/leaderboard", headers=organiser)

    assert len(board.json()["entries"]) == 2
    # A round board is one round's play; how far anyone got means nothing on it.
    assert all(entry["rounds_survived"] is None for entry in board.json()["entries"])


# --- The cascade ------------------------------------------------------------


@pytest.mark.asyncio
async def test_a_group_level_on_points_goes_through_on_strokes(client, make_token):
    organiser = await player(client, make_token, "organiser@example.com")
    tournament_id, _, _ = await _bracket(client, organiser, 4)

    drawn = (await _draw(client, organiser, tournament_id)).json()
    group = drawn["groups"][0]
    a, b, c, d = [m["participant_id"] for m in group["members"]]

    # A and B take a hole each; A goes round in fewer shots.
    await _score(client, organiser, group, {a: 2, b: 5, c: 5, d: 5}, 0)
    await _score(client, organiser, group, {a: 4, b: 3, c: 5, d: 5}, 1)
    await _score(client, organiser, group, {a: 4, b: 5, c: 5, d: 4}, 2, ctp=a)

    await _complete(client, organiser, drawn["id"])
    decided = (await client.get(f"/groups/{group['id']}", headers=organiser)).json()

    assert decided["advanced_by"] == "points"
    assert decided["advancing_participant_id"] == a


@pytest.mark.asyncio
async def test_a_group_level_on_everything_goes_through_on_countback(client, make_token):
    """A and B tie on points and strokes; B took the later hole."""
    organiser = await player(client, make_token, "organiser@example.com")
    tournament_id, _, _ = await _bracket(client, organiser, 4)

    drawn = (await _draw(client, organiser, tournament_id)).json()
    group = drawn["groups"][0]
    a, b, c, d = [m["participant_id"] for m in group["members"]]

    await _score(client, organiser, group, {a: 3, b: 5, c: 5, d: 5}, 0)  # A wins
    await _score(client, organiser, group, {a: 5, b: 5, c: 5, d: 5}, 1)  # halved
    await _score(client, organiser, group, {a: 5, b: 3, c: 5, d: 5}, 2)  # B wins

    await _complete(client, organiser, drawn["id"])
    decided = (await client.get(f"/groups/{group['id']}", headers=organiser)).json()

    assert decided["advanced_by"] == "countback"
    assert decided["advancing_participant_id"] == b


# --- Adjudication -----------------------------------------------------------


async def _all_square(client, organiser, tournament_id):
    """One group that halved every hole — the one case the cascade cannot settle.

    Every *other* group is played normally, so the refusal names this group alone
    rather than every group that happens to be unscored.
    """
    drawn = (await _draw(client, organiser, tournament_id)).json()
    group = drawn["groups"][0]
    members = [m["participant_id"] for m in group["members"]]

    for hole_index in range(3):
        await _score(client, organiser, group, {m: 4 for m in members}, hole_index)
    await _play(
        client, organiser, {"groups": [g for g in drawn["groups"] if g["id"] != group["id"]]}
    )

    await _complete(client, organiser, drawn["id"])
    return drawn, group, members


@pytest.mark.asyncio
async def test_an_all_square_group_blocks_the_draw_until_the_organiser_says(client, make_token):
    organiser = await player(client, make_token, "organiser@example.com")
    tournament_id, _, _ = await _bracket(client, organiser, 8)
    drawn, group, members = await _all_square(client, organiser, tournament_id)

    undecided = await client.get(f"/groups/{group['id']}", headers=organiser)
    assert undecided.json()["advancing_participant_id"] is None
    assert undecided.json()["advanced_by"] is None

    refused = await _draw(client, organiser, tournament_id)
    assert refused.status_code == 409
    assert f"group {group['group_number']}" in refused.json()["detail"]
    assert "advancement" in refused.json()["detail"]

    sent = await client.post(
        f"/groups/{group['id']}/advancement",
        headers=organiser,
        json={"participant_id": members[0]},
    )
    assert sent.status_code == 200, sent.text
    assert sent.json()["advanced_by"] == "organiser"
    assert sent.json()["advancing_participant_id"] == members[0]

    assert (await _draw(client, organiser, tournament_id)).status_code == 201


@pytest.mark.asyncio
async def test_a_decided_group_cannot_be_overwritten(client, make_token):
    """The verdict is the record of what the group was told, not an editable field."""
    organiser = await player(client, make_token, "organiser@example.com")
    tournament_id, _, _ = await _bracket(client, organiser, 4)

    drawn = (await _draw(client, organiser, tournament_id)).json()
    group = drawn["groups"][0]
    members = [m["participant_id"] for m in group["members"]]
    await _play(client, organiser, drawn)
    await _complete(client, organiser, drawn["id"])

    refused = await client.post(
        f"/groups/{group['id']}/advancement",
        headers=organiser,
        json={"participant_id": members[-1]},
    )

    assert refused.status_code == 409
    assert "already decided" in refused.json()["detail"]


@pytest.mark.asyncio
async def test_adjudication_is_refused_while_the_round_is_still_being_played(client, make_token):
    organiser = await player(client, make_token, "organiser@example.com")
    tournament_id, _, _ = await _bracket(client, organiser, 4)
    drawn = (await _draw(client, organiser, tournament_id)).json()
    group = drawn["groups"][0]

    refused = await client.post(
        f"/groups/{group['id']}/advancement",
        headers=organiser,
        json={"participant_id": group["members"][0]["participant_id"]},
    )

    assert refused.status_code == 409
    assert "Finish it first" in refused.json()["detail"]


@pytest.mark.asyncio
async def test_nobody_advances_from_a_round_robin(client, make_token):
    organiser = await player(client, make_token, "organiser@example.com")
    course_id = await course(client, organiser, 18)
    tournament_id = await tournament(client, organiser, course_id)
    await set_status(client, organiser, tournament_id, TournamentStatus.REGISTRATION_OPEN)
    for index in range(6):
        await add_virtual(client, organiser, tournament_id, f"Player {index}")
    await set_status(client, organiser, tournament_id, TournamentStatus.REGISTRATION_CLOSED)

    drawn = (await _draw(client, organiser, tournament_id)).json()
    group = drawn["groups"][0]
    await _play(client, organiser, drawn)
    await _complete(client, organiser, drawn["id"])

    decided = await client.get(f"/groups/{group['id']}", headers=organiser)
    assert decided.json()["advancing_participant_id"] is None
    assert decided.json()["advanced_by"] is None

    refused = await client.post(
        f"/groups/{group['id']}/advancement",
        headers=organiser,
        json={"participant_id": group["members"][0]["participant_id"]},
    )
    assert refused.status_code == 409
    assert "round robin" in refused.json()["detail"]


@pytest.mark.asyncio
async def test_a_player_from_another_group_cannot_be_sent_through(client, make_token):
    organiser = await player(client, make_token, "organiser@example.com")
    tournament_id, _, _ = await _bracket(client, organiser, 8)
    drawn, group, _ = await _all_square(client, organiser, tournament_id)

    stranger = next(
        member["participant_id"]
        for other in drawn["groups"]
        if other["id"] != group["id"]
        for member in other["members"]
    )

    refused = await client.post(
        f"/groups/{group['id']}/advancement",
        headers=organiser,
        json={"participant_id": stranger},
    )

    assert refused.status_code == 422
    assert "did not play in" in refused.json()["detail"]


@pytest.mark.asyncio
async def test_only_the_organiser_can_send_a_player_through(client, make_token):
    organiser = await player(client, make_token, "organiser@example.com")
    stranger = await player(client, make_token, "stranger@example.com")
    tournament_id, _, _ = await _bracket(client, organiser, 8)
    _, group, members = await _all_square(client, organiser, tournament_id)

    refused = await client.post(
        f"/groups/{group['id']}/advancement",
        headers=stranger,
        json={"participant_id": members[0]},
    )

    assert refused.status_code == 403


@pytest.mark.asyncio
async def test_an_unknown_group_is_404(client, make_token):
    organiser = await player(client, make_token, "organiser@example.com")

    response = await client.post(
        f"/groups/{uuid.uuid4()}/advancement",
        headers=organiser,
        json={"participant_id": str(uuid.uuid4())},
    )

    assert response.status_code == 404


# --- The board --------------------------------------------------------------


@pytest.mark.asyncio
async def test_the_board_ranks_by_how_far_a_player_got(client, make_token):
    """A champion who scored *less* than a round-one casualty still leads.

    Sixteen players rather than eight, because the point only exists when the
    final is a fourball: in a two-player final a player cannot advance without
    winning a hole, so the champion can never finish on fewer points than
    somebody knocked out early. With four in the final they can advance on
    strokes having won nothing, which is the case a points-ordered board gets
    wrong.

    HALVED gives a group three halved holes with distinct totals — everyone on
    zero points, separated only by strokes.
    """
    organiser = await player(client, make_token, "organiser@example.com")
    tournament_id, _, _ = await _bracket(client, organiser, 16)

    first = (await _draw(client, organiser, tournament_id)).json()
    groups = sorted(first["groups"], key=lambda g: g["group_number"])

    # Group 1: every hole halved, so its winner goes through on strokes alone.
    champion_group = groups[0]
    champion = [m["participant_id"] for m in champion_group["members"]][0]
    await _halve(client, organiser, champion_group)

    # Group 2: its winner takes two holes and the runner-up takes one, so
    # somebody leaves round one with more points than the champion ever gets.
    runner_up_group = groups[1]
    others = [m["participant_id"] for m in runner_up_group["members"]]
    high_scorer = others[1]
    for hole_index, winner in enumerate((others[0], high_scorer, others[0])):
        strokes = {member: 5 for member in others}
        strokes[winner] = 2
        assert (
            await _score(client, organiser, runner_up_group, strokes, hole_index)
        ).status_code == 200

    await _play(client, organiser, {"groups": groups[2:]})
    await _complete(client, organiser, first["id"])

    # The final: four players, every hole halved again, champion fewest strokes.
    final_round = (await _draw(client, organiser, tournament_id)).json()
    final = final_round["groups"][0]
    assert len(final["members"]) == 4
    await _halve(client, organiser, final, first=champion)
    await _complete(client, organiser, final_round["id"])

    entries = (
        await client.get(f"/tournaments/{tournament_id}/leaderboard", headers=organiser)
    ).json()["entries"]
    by_id = {entry["participant_id"]: entry for entry in entries}

    assert by_id[champion]["position"] == 1
    assert by_id[champion]["rounds_survived"] == 3  # drawn into round 2, and won it
    assert by_id[champion]["points"] == 0  # won the whole thing without a single hole

    # The player knocked out in round one outscored them, and is still below.
    assert by_id[high_scorer]["points"] > by_id[champion]["points"]
    assert by_id[high_scorer]["position"] > by_id[champion]["position"]
    assert by_id[high_scorer]["rounds_survived"] == 1

    # And everyone who reached round two is above everyone who did not.
    survived = [entry["position"] for entry in entries if entry["rounds_survived"] >= 2]
    knocked_out = [entry["position"] for entry in entries if entry["rounds_survived"] == 1]
    assert max(survived) < min(knocked_out)


@pytest.mark.asyncio
async def test_a_round_robin_board_says_nothing_about_rounds_survived(client, make_token):
    """The one wire change, and it must stay null where it would mean nothing."""
    organiser = await player(client, make_token, "organiser@example.com")
    course_id = await course(client, organiser, 18)
    tournament_id = await tournament(client, organiser, course_id)
    await set_status(client, organiser, tournament_id, TournamentStatus.REGISTRATION_OPEN)
    for index in range(6):
        await add_virtual(client, organiser, tournament_id, f"Player {index}")
    await set_status(client, organiser, tournament_id, TournamentStatus.REGISTRATION_CLOSED)

    drawn = (await _draw(client, organiser, tournament_id)).json()
    await _play(client, organiser, drawn)
    await _complete(client, organiser, drawn["id"])

    entries = (
        await client.get(f"/tournaments/{tournament_id}/leaderboard", headers=organiser)
    ).json()["entries"]

    assert len(entries) == 6
    assert all(entry["rounds_survived"] is None for entry in entries)
