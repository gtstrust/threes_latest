"""API-level tests for handicap scoring (ADR-013).

The allocation and the net cascade are covered exhaustively against the pure
engine in `test_scoring.py`. What matters here is the wiring: that the draw
refuses an event it cannot score fairly, that shots reach the engine and are
persisted beside the strokes they applied to, and that net reaches the two
rankings that read it.

**The last test in this file is the important one.** Handicaps touch the hole
winner, the leaderboard tie-break and the knockout cascade at once, so the thing
most worth proving is that an event which did not ask for them is untouched.
"""

import uuid

import pytest
from httpx import AsyncClient

from app.models.tournament import TournamentStatus
from tests.helpers import (
    add_virtual,
    course,
    draw,
    player,
    set_status,
    tournament,
)


async def _submit(client: AsyncClient, headers, group_id, hole_id, strokes, **tie_breaks):
    payload: dict[str, object] = {"strokes": strokes}
    payload.update({key: value for key, value in tie_breaks.items() if value is not None})
    return await client.post(
        f"/groups/{group_id}/holes/{hole_id}/scores", headers=headers, json=payload
    )


async def _handicap_event(
    client: AsyncClient,
    headers,
    handicaps: list[int | None],
    *,
    stroke_indexes: bool = True,
    format: str = "ROUND_ROBIN",
) -> tuple[str, list[str]]:
    """An event with handicaps on, a field, and registration closed."""
    course_id = await course(client, headers, 18, stroke_indexes=stroke_indexes)
    tournament_id = await tournament(
        client, headers, course_id, format=format, handicap_enabled=True
    )
    await set_status(client, headers, tournament_id, TournamentStatus.REGISTRATION_OPEN)
    participant_ids = [
        await add_virtual(client, headers, tournament_id, f"Player {index:02d}", handicap)
        for index, handicap in enumerate(handicaps)
    ]
    await set_status(client, headers, tournament_id, TournamentStatus.REGISTRATION_CLOSED)
    return tournament_id, participant_ids


async def _first_group(client: AsyncClient, headers, tournament_id: str) -> dict:
    drawn = await draw(client, headers, tournament_id)
    assert drawn.status_code == 201, drawn.text
    round_ = drawn.json()
    group = round_["groups"][0]
    return {
        "round_id": round_["id"],
        "group_id": group["id"],
        "members": [member["participant_id"] for member in group["members"]],
        "holes": [hole["hole_id"] for hole in group["holes"]],
    }


# --- The draw refuses what it cannot score fairly ---------------------------


@pytest.mark.asyncio
async def test_the_draw_refuses_holes_with_no_stroke_index(client, make_token):
    # The whole point of ADR-013 depending on stroke_index: it fails at a desk,
    # not on the first tee with the field assembled.
    organiser = await player(client, make_token, "organiser@example.com")
    tournament_id, _ = await _handicap_event(client, organiser, [10, 18, 24], stroke_indexes=False)

    refused = await draw(client, organiser, tournament_id)

    assert refused.status_code == 409, refused.text
    assert "stroke index" in refused.json()["detail"]


@pytest.mark.asyncio
async def test_the_draw_names_the_holes_that_are_missing_one(client, make_token):
    organiser = await player(client, make_token, "organiser@example.com")
    course_id = await course(client, organiser, 0)
    await client.put(
        f"/courses/{course_id}/holes",
        headers=organiser,
        json={
            "holes": [
                {"hole_number": 1, "stroke_index": 5},
                {"hole_number": 2},
                {"hole_number": 3, "stroke_index": 11},
            ]
        },
    )
    tournament_id = await tournament(client, organiser, course_id, handicap_enabled=True)
    await set_status(client, organiser, tournament_id, TournamentStatus.REGISTRATION_OPEN)
    for index in range(3):
        await add_virtual(client, organiser, tournament_id, f"Player {index}", 12)
    await set_status(client, organiser, tournament_id, TournamentStatus.REGISTRATION_CLOSED)

    refused = await draw(client, organiser, tournament_id)

    # Named by hole number, which is the only name the organiser will recognise.
    assert refused.status_code == 409
    assert "hole 2" in refused.json()["detail"]


@pytest.mark.asyncio
async def test_the_draw_refuses_a_player_with_no_handicap(client, make_token):
    # Not defaulted to 0: zero is the hardest handicap there is, so guessing would
    # silently penalise exactly the player nobody remembered to ask.
    organiser = await player(client, make_token, "organiser@example.com")
    tournament_id, _ = await _handicap_event(client, organiser, [10, None, 24])

    refused = await draw(client, organiser, tournament_id)

    assert refused.status_code == 409, refused.text
    assert "Player 01" in refused.json()["detail"]


@pytest.mark.asyncio
async def test_a_scratch_event_needs_neither(client, make_token):
    # The same course and the same field, with handicaps off, draws fine.
    organiser = await player(client, make_token, "organiser@example.com")
    course_id = await course(client, organiser, 18)
    tournament_id = await tournament(client, organiser, course_id)
    await set_status(client, organiser, tournament_id, TournamentStatus.REGISTRATION_OPEN)
    for index in range(3):
        await add_virtual(client, organiser, tournament_id, f"Player {index}")
    await set_status(client, organiser, tournament_id, TournamentStatus.REGISTRATION_CLOSED)

    assert (await draw(client, organiser, tournament_id)).status_code == 201


# --- Shots reach the engine, and are stored -------------------------------


@pytest.mark.asyncio
async def test_a_net_winner_takes_a_hole_they_lost_on_gross(client, make_token):
    organiser = await player(client, make_token, "organiser@example.com")
    # 54 is the WHS maximum and pro-rates to nine shots over three holes — three a
    # hole, which is what makes the gap wide enough to reverse a result outright.
    tournament_id, _ = await _handicap_event(client, organiser, [0, 54, 0])
    ctx = await _first_group(client, organiser, tournament_id)
    a, b, c = ctx["members"]

    response = await _submit(
        client, organiser, ctx["group_id"], ctx["holes"][0], {a: 5, b: 7, c: 6}
    )

    assert response.status_code == 200, response.text
    body = response.json()
    # B took seven to A's five and wins it: 7 less three shots is a net 4.
    assert body["winner_participant_id"] == b
    assert body["decided_by"] == "strokes"
    assert {s["participant_id"]: s["points"] for s in body["scores"]} == {a: 0, b: 1, c: 0}


@pytest.mark.asyncio
async def test_shots_received_are_persisted_beside_the_strokes(client, make_token):
    organiser = await player(client, make_token, "organiser@example.com")
    tournament_id, _ = await _handicap_event(client, organiser, [0, 18, 6])
    ctx = await _first_group(client, organiser, tournament_id)
    a, b, c = ctx["members"]

    body = (
        await _submit(client, organiser, ctx["group_id"], ctx["holes"][0], {a: 5, b: 7, c: 6})
    ).json()

    received = {s["participant_id"]: s["strokes_received"] for s in body["scores"]}
    # Scratch gets nothing; 18 gets one a hole; 6 pro-rates to one shot, dealt to
    # the hardest hole of the loop — which this may or may not be.
    assert received[a] == 0
    assert received[b] == 1
    assert received[c] in {0, 1}
    # Gross is untouched by any of it.
    assert {s["participant_id"]: s["strokes"] for s in body["scores"]} == {a: 5, b: 7, c: 6}


@pytest.mark.asyncio
async def test_a_handicap_can_create_a_tie_that_gross_did_not_have(client, make_token):
    organiser = await player(client, make_token, "organiser@example.com")
    tournament_id, _ = await _handicap_event(client, organiser, [0, 18, 0])
    ctx = await _first_group(client, organiser, tournament_id)
    a, b, c = ctx["members"]

    # A on 4, B on 5 less a shot = 4. Level on net, which gross never was.
    body = (
        await _submit(client, organiser, ctx["group_id"], ctx["holes"][0], {a: 4, b: 5, c: 9})
    ).json()

    assert body["winner_participant_id"] is None
    assert sorted(body["tied_participants"]) == sorted([a, b])


@pytest.mark.asyncio
async def test_the_tie_break_is_contested_among_the_net_tied_players(client, make_token):
    organiser = await player(client, make_token, "organiser@example.com")
    tournament_id, _ = await _handicap_event(client, organiser, [0, 18, 0])
    ctx = await _first_group(client, organiser, tournament_id)
    a, b, c = ctx["members"]

    answered = await _submit(
        client, organiser, ctx["group_id"], ctx["holes"][0], {a: 4, b: 5, c: 9}, closest_to_pin=b
    )

    assert answered.status_code == 200, answered.text
    assert answered.json()["winner_participant_id"] == b
    assert answered.json()["decided_by"] == "closest_to_pin"


@pytest.mark.asyncio
async def test_naming_a_player_not_tied_on_net_is_refused_in_those_terms(client, make_token):
    """The ADR-007 guard still fires, and says which number it measured.

    Worth stating what this case is *not*, because it looks like it should exist:
    a player level on gross can never be worse off on net, since shots only ever
    come off. So "tied on gross but not on net" is unreachable — being excluded
    always means being genuinely behind on net, as C is here.

    What matters is the wording. An error reading "fewest strokes" would send
    whoever debugs it to the gross column, where they would find C level with
    nobody and no explanation.
    """
    organiser = await player(client, make_token, "organiser@example.com")
    tournament_id, _ = await _handicap_event(client, organiser, [0, 0, 18])
    ctx = await _first_group(client, organiser, tournament_id)
    a, b, c = ctx["members"]

    # A and B tie on a net 4; C is on 6 less a shot, so a stroke adrift.
    refused = await _submit(
        client, organiser, ctx["group_id"], ctx["holes"][0], {a: 4, b: 4, c: 6}, closest_to_pin=c
    )

    assert refused.status_code == 422, refused.text
    assert "fewest net strokes" in refused.json()["detail"]


# --- Net reaches the rankings ---------------------------------------------


@pytest.mark.asyncio
async def test_the_board_ranks_on_net_and_still_reports_gross(client, make_token):
    organiser = await player(client, make_token, "organiser@example.com")
    tournament_id, _ = await _handicap_event(client, organiser, [0, 18, 0])
    ctx = await _first_group(client, organiser, tournament_id)
    a, b, c = ctx["members"]

    for hole in ctx["holes"]:
        await _submit(client, organiser, ctx["group_id"], hole, {a: 6, b: 7, c: 8})

    board = (
        await client.get(f"/tournaments/{tournament_id}/leaderboard", headers=organiser)
    ).json()
    rows = {row["participant_id"]: row for row in board["entries"]}

    # B played 21 gross and received three shots, so 18 net — fewer than A's 18?
    # A is on 18 gross with none. They are level on net, and both are reported.
    assert rows[b]["total_strokes"] == 21
    assert rows[b]["net_strokes"] == 18
    assert rows[a]["total_strokes"] == 18
    assert rows[a]["net_strokes"] == 18


@pytest.mark.asyncio
async def test_a_scratch_player_on_a_handicap_event_still_gets_a_net_figure(client, make_token):
    # Net is a property of the event, not of the player. Blanking one cell while
    # the rest of the column had numbers would read as missing data.
    organiser = await player(client, make_token, "organiser@example.com")
    tournament_id, _ = await _handicap_event(client, organiser, [0, 18, 0])
    ctx = await _first_group(client, organiser, tournament_id)
    a, b, c = ctx["members"]
    await _submit(client, organiser, ctx["group_id"], ctx["holes"][0], {a: 4, b: 6, c: 5})

    board = (
        await client.get(f"/tournaments/{tournament_id}/leaderboard", headers=organiser)
    ).json()

    assert all(row["net_strokes"] is not None for row in board["entries"])


# --- The regression that matters ------------------------------------------


@pytest.mark.asyncio
async def test_a_scratch_event_is_the_event_it_always_was(client, make_token):
    """Handicaps touch three rankings at once. This is the proof they moved none.

    `strokes_received` defaults to 0 and sums to 0, so net equals gross, the board
    is ordered identically, and the wire says `net_strokes: null` rather than a
    number that would read as a real net score.
    """
    organiser = await player(client, make_token, "organiser@example.com")
    course_id = await course(client, organiser, 18)
    tournament_id = await tournament(client, organiser, course_id)
    await set_status(client, organiser, tournament_id, TournamentStatus.REGISTRATION_OPEN)
    for index in range(3):
        await add_virtual(client, organiser, tournament_id, f"Player {index:02d}")
    await set_status(client, organiser, tournament_id, TournamentStatus.REGISTRATION_CLOSED)
    ctx = await _first_group(client, organiser, tournament_id)
    a, b, c = ctx["members"]

    body = (
        await _submit(client, organiser, ctx["group_id"], ctx["holes"][0], {a: 3, b: 5, c: 4})
    ).json()

    assert body["winner_participant_id"] == a
    assert body["decided_by"] == "strokes"
    assert all(score["strokes_received"] == 0 for score in body["scores"])

    board = (
        await client.get(f"/tournaments/{tournament_id}/leaderboard", headers=organiser)
    ).json()
    assert [row["participant_id"] for row in board["entries"]][0] == a
    for row in board["entries"]:
        assert row["net_strokes"] is None


# --- The organiser sets a handicap after the fact --------------------------


@pytest.mark.asyncio
async def test_the_organiser_can_set_a_handicap_until_play_starts(client, make_token):
    organiser = await player(client, make_token, "organiser@example.com")
    tournament_id, participant_ids = await _handicap_event(client, organiser, [10, None, 24])

    patched = await client.patch(
        f"/tournaments/{tournament_id}/participants/{participant_ids[1]}",
        headers=organiser,
        json={"playing_handicap": 14},
    )

    assert patched.status_code == 200, patched.text
    assert patched.json()["playing_handicap"] == 14
    # And the draw it was blocking now goes through.
    assert (await draw(client, organiser, tournament_id)).status_code == 201


@pytest.mark.asyncio
async def test_a_handicap_cannot_be_changed_once_play_starts(client, make_token):
    # Shots are dealt from this number, so changing it mid-round would re-decide
    # holes the group has already been given the result of.
    organiser = await player(client, make_token, "organiser@example.com")
    tournament_id, participant_ids = await _handicap_event(client, organiser, [10, 18, 24])
    await _first_group(client, organiser, tournament_id)

    refused = await client.patch(
        f"/tournaments/{tournament_id}/participants/{participant_ids[0]}",
        headers=organiser,
        json={"playing_handicap": 2},
    )

    assert refused.status_code == 409, refused.text


@pytest.mark.asyncio
async def test_only_the_organiser_may_set_one(client, make_token):
    organiser = await player(client, make_token, "organiser@example.com")
    stranger = await player(client, make_token, "stranger@example.com")
    tournament_id, participant_ids = await _handicap_event(client, organiser, [10, 18, 24])

    refused = await client.patch(
        f"/tournaments/{tournament_id}/participants/{participant_ids[0]}",
        headers=stranger,
        json={"playing_handicap": 2},
    )

    assert refused.status_code == 403, refused.text


@pytest.mark.asyncio
async def test_an_out_of_range_handicap_is_refused(client, make_token):
    organiser = await player(client, make_token, "organiser@example.com")
    tournament_id, participant_ids = await _handicap_event(client, organiser, [10, 18, 24])

    refused = await client.patch(
        f"/tournaments/{tournament_id}/participants/{participant_ids[0]}",
        headers=organiser,
        json={"playing_handicap": 55},
    )

    assert refused.status_code == 422, refused.text


@pytest.mark.asyncio
async def test_patching_an_unknown_participant_is_a_404(client, make_token):
    organiser = await player(client, make_token, "organiser@example.com")
    tournament_id, _ = await _handicap_event(client, organiser, [10, 18, 24])

    refused = await client.patch(
        f"/tournaments/{tournament_id}/participants/{uuid.uuid4()}",
        headers=organiser,
        json={"playing_handicap": 8},
    )

    assert refused.status_code == 404, refused.text
