"""API-level tests for entering scores and reading a group's card.

The cascade itself is covered exhaustively in test_scoring.py against the pure
engine. What matters here is the wiring: that the right strokes reach it, that
what it decides is persisted, and that the tie-break conversation works over HTTP.
"""

import uuid

import pytest
from httpx import AsyncClient

from app.models.tournament import TournamentStatus
from tests.helpers import add_virtual, course, drawn_group, player, set_status, tournament


async def _submit(client: AsyncClient, headers, group_id, hole_id, strokes, **tie_breaks):
    payload: dict[str, object] = {"strokes": strokes}
    payload.update({key: value for key, value in tie_breaks.items() if value is not None})
    return await client.post(
        f"/groups/{group_id}/holes/{hole_id}/scores", headers=headers, json=payload
    )


async def _open_tournament(
    client: AsyncClient, headers, virtual_count: int = 2
) -> tuple[str, list[str]]:
    """A tournament with a course and open registration, so real players can join."""
    course_id = await course(client, headers)
    tournament_id = await tournament(client, headers, course_id)
    await set_status(client, headers, tournament_id, TournamentStatus.REGISTRATION_OPEN)
    virtual_ids = [
        await add_virtual(client, headers, tournament_id, f"Virtual {index:02d}")
        for index in range(virtual_count)
    ]
    return tournament_id, virtual_ids


# --- Scoring a hole ---------------------------------------------------------


@pytest.mark.asyncio
async def test_outright_stroke_win_is_persisted(client, make_token):
    organiser = await player(client, make_token, "organiser@example.com")
    ctx = await drawn_group(client, organiser)
    a, b, c = ctx["members"]

    response = await _submit(
        client, organiser, ctx["group_id"], ctx["holes"][0], {a: 3, b: 5, c: 4}
    )

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["winner_participant_id"] == a
    assert body["decided_by"] == "strokes"
    assert body["tied_participants"] == []
    assert {s["participant_id"]: s["points"] for s in body["scores"]} == {a: 1, b: 0, c: 0}


@pytest.mark.asyncio
async def test_a_tie_reports_who_must_be_asked(client, make_token):
    organiser = await player(client, make_token, "organiser@example.com")
    ctx = await drawn_group(client, organiser)
    a, b, c = ctx["members"]

    response = await _submit(
        client, organiser, ctx["group_id"], ctx["holes"][0], {a: 3, b: 3, c: 5}
    )

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["winner_participant_id"] is None
    assert body["decided_by"] == "no_winner"
    # The two tied players, so the app knows exactly who to ask -- not c.
    assert sorted(body["tied_participants"]) == sorted([a, b])
    assert all(score["points"] == 0 for score in body["scores"])


@pytest.mark.asyncio
async def test_resubmitting_with_closest_to_pin_decides_the_hole(client, make_token):
    organiser = await player(client, make_token, "organiser@example.com")
    ctx = await drawn_group(client, organiser)
    a, b, c = ctx["members"]
    hole = ctx["holes"][0]

    await _submit(client, organiser, ctx["group_id"], hole, {a: 3, b: 3, c: 5})
    response = await _submit(
        client, organiser, ctx["group_id"], hole, {a: 3, b: 3, c: 5}, closest_to_pin=b
    )

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["winner_participant_id"] == b
    assert body["decided_by"] == "closest_to_pin"
    assert body["closest_to_pin_participant_id"] == b
    assert body["tied_participants"] == []
    assert {s["participant_id"]: s["points"] for s in body["scores"]} == {a: 0, b: 1, c: 0}


@pytest.mark.asyncio
async def test_a_tie_break_that_did_not_decide_is_not_recorded(client, make_token):
    """ADR-007: nothing is recorded unless it actually decided a hole."""
    organiser = await player(client, make_token, "organiser@example.com")
    ctx = await drawn_group(client, organiser)
    a, b, c = ctx["members"]

    # a wins outright on strokes, so closest-to-pin never gets consulted.
    response = await _submit(
        client, organiser, ctx["group_id"], ctx["holes"][0], {a: 3, b: 5, c: 4}, closest_to_pin=a
    )

    assert response.status_code == 200, response.text
    assert response.json()["decided_by"] == "strokes"
    assert response.json()["closest_to_pin_participant_id"] is None


@pytest.mark.asyncio
async def test_correcting_a_miskeyed_score_overwrites_it(client, make_token):
    organiser = await player(client, make_token, "organiser@example.com")
    ctx = await drawn_group(client, organiser)
    a, b, c = ctx["members"]
    hole = ctx["holes"][0]

    await _submit(client, organiser, ctx["group_id"], hole, {a: 3, b: 5, c: 4})
    corrected = await _submit(client, organiser, ctx["group_id"], hole, {a: 6, b: 5, c: 4})

    assert corrected.status_code == 200, corrected.text
    assert corrected.json()["winner_participant_id"] == c
    assert {s["participant_id"]: s["strokes"] for s in corrected.json()["scores"]} == {
        a: 6,
        b: 5,
        c: 4,
    }

    # And the correction replaced the row rather than adding a second one.
    card = await client.get(f"/groups/{ctx['group_id']}/scores", headers=organiser)
    assert len(card.json()["holes"]) == 1
    assert len(card.json()["holes"][0]["scores"]) == 3


# --- What gets rejected -----------------------------------------------------


@pytest.mark.asyncio
async def test_a_hole_outside_the_groups_loop_is_rejected(client, make_token):
    organiser = await player(client, make_token, "organiser@example.com")
    ctx = await drawn_group(client, organiser)
    a, b, c = ctx["members"]

    response = await _submit(
        client, organiser, ctx["group_id"], str(uuid.uuid4()), {a: 3, b: 4, c: 5}
    )

    assert response.status_code == 404
    assert "not part of this group's loop" in response.json()["detail"]


@pytest.mark.asyncio
async def test_a_card_missing_a_player_is_rejected(client, make_token):
    organiser = await player(client, make_token, "organiser@example.com")
    ctx = await drawn_group(client, organiser)
    a, b, _c = ctx["members"]

    response = await _submit(client, organiser, ctx["group_id"], ctx["holes"][0], {a: 3, b: 4})

    assert response.status_code == 422
    assert "Every player in the group needs a score" in response.json()["detail"]


@pytest.mark.asyncio
async def test_scoring_a_player_from_another_group_is_rejected(client, make_token):
    organiser = await player(client, make_token, "organiser@example.com")
    ctx = await drawn_group(client, organiser, player_count=6)
    a, b, c = ctx["members"]
    outsider = next(pid for pid in ctx["participant_ids"] if pid not in ctx["members"])

    response = await _submit(
        client, organiser, ctx["group_id"], ctx["holes"][0], {a: 3, b: 4, c: 5, outsider: 2}
    )

    assert response.status_code == 422
    assert "not in this group" in response.json()["detail"]


@pytest.mark.asyncio
async def test_strokes_below_one_are_rejected(client, make_token):
    organiser = await player(client, make_token, "organiser@example.com")
    ctx = await drawn_group(client, organiser)
    a, b, c = ctx["members"]

    response = await _submit(
        client, organiser, ctx["group_id"], ctx["holes"][0], {a: 0, b: 4, c: 5}
    )

    assert response.status_code == 422
    assert "Strokes must be 1 or more" in response.json()["detail"]


@pytest.mark.asyncio
async def test_naming_a_non_tied_player_as_closest_to_pin_is_rejected(client, make_token):
    organiser = await player(client, make_token, "organiser@example.com")
    ctx = await drawn_group(client, organiser)
    a, b, c = ctx["members"]

    # a and b tie; c is not in the running, so naming c is a data error.
    response = await _submit(
        client, organiser, ctx["group_id"], ctx["holes"][0], {a: 3, b: 3, c: 5}, closest_to_pin=c
    )

    assert response.status_code == 422
    assert "not tied for fewest strokes" in response.json()["detail"]


@pytest.mark.asyncio
async def test_scores_are_closed_once_the_round_is_complete(client, make_token):
    organiser = await player(client, make_token, "organiser@example.com")
    ctx = await drawn_group(client, organiser)
    a, b, c = ctx["members"]

    await client.post(f"/rounds/{ctx['round_id']}/complete", headers=organiser)
    response = await _submit(
        client, organiser, ctx["group_id"], ctx["holes"][0], {a: 3, b: 4, c: 5}
    )

    assert response.status_code == 409
    assert "scores are closed" in response.json()["detail"]


# --- Who may enter scores ---------------------------------------------------


@pytest.mark.asyncio
async def test_a_player_in_the_group_can_enter_its_scores(client, make_token):
    """The whole point of the rule: a real player enters for their virtual mates."""
    organiser = await player(client, make_token, "organiser@example.com")
    tournament_id, _ = await _open_tournament(client, organiser)

    member = await player(client, make_token, "member@example.com")
    joined = await client.post(
        f"/tournaments/{tournament_id}/participants", headers=member, json={}
    )
    assert joined.status_code == 201, joined.text

    await set_status(client, organiser, tournament_id, TournamentStatus.REGISTRATION_CLOSED)
    drawn = await client.post(f"/tournaments/{tournament_id}/rounds", headers=organiser)
    group = drawn.json()["groups"][0]

    strokes = {m["participant_id"]: 4 for m in group["members"]}
    strokes[joined.json()["id"]] = 3

    response = await _submit(client, member, group["id"], group["holes"][0]["hole_id"], strokes)

    assert response.status_code == 200, response.text
    assert response.json()["winner_participant_id"] == joined.json()["id"]


@pytest.mark.asyncio
async def test_a_player_from_another_group_cannot_enter_scores(client, make_token):
    organiser = await player(client, make_token, "organiser@example.com")
    tournament_id, _ = await _open_tournament(client, organiser, virtual_count=5)

    outsider = await player(client, make_token, "outsider@example.com")
    joined = await client.post(
        f"/tournaments/{tournament_id}/participants", headers=outsider, json={}
    )
    outsider_id = joined.json()["id"]
    await set_status(client, organiser, tournament_id, TournamentStatus.REGISTRATION_CLOSED)

    drawn = await client.post(f"/tournaments/{tournament_id}/rounds", headers=organiser)
    groups = drawn.json()["groups"]

    other_group = next(
        g for g in groups if outsider_id not in {m["participant_id"] for m in g["members"]}
    )
    strokes = {m["participant_id"]: 4 for m in other_group["members"]}

    response = await _submit(
        client, outsider, other_group["id"], other_group["holes"][0]["hole_id"], strokes
    )

    assert response.status_code == 403
    assert "Only players in this group" in response.json()["detail"]


@pytest.mark.asyncio
async def test_a_stranger_cannot_enter_scores(client, make_token):
    organiser = await player(client, make_token, "organiser@example.com")
    ctx = await drawn_group(client, organiser)
    a, b, c = ctx["members"]

    stranger = await player(client, make_token, "stranger@example.com")
    response = await _submit(client, stranger, ctx["group_id"], ctx["holes"][0], {a: 3, b: 4, c: 5})

    assert response.status_code == 403


# --- The card ---------------------------------------------------------------


@pytest.mark.asyncio
async def test_the_card_returns_played_holes_in_loop_order(client, make_token):
    organiser = await player(client, make_token, "organiser@example.com")
    ctx = await drawn_group(client, organiser)
    a, b, c = ctx["members"]

    # Score the loop out of order; the card should still read 1, 2, 3.
    await _submit(client, organiser, ctx["group_id"], ctx["holes"][2], {a: 3, b: 4, c: 5})
    await _submit(client, organiser, ctx["group_id"], ctx["holes"][0], {a: 5, b: 3, c: 4})

    card = await client.get(f"/groups/{ctx['group_id']}/scores", headers=organiser)

    assert card.status_code == 200, card.text
    body = card.json()
    assert body["group_id"] == ctx["group_id"]
    # Only the two played holes, in the order the group plays them.
    assert [hole["hole_id"] for hole in body["holes"]] == [ctx["holes"][0], ctx["holes"][2]]
    assert body["holes"][0]["winner_participant_id"] == b


@pytest.mark.asyncio
async def test_an_unscored_group_has_an_empty_card(client, make_token):
    organiser = await player(client, make_token, "organiser@example.com")
    ctx = await drawn_group(client, organiser)

    card = await client.get(f"/groups/{ctx['group_id']}/scores", headers=organiser)

    assert card.status_code == 200
    assert card.json()["holes"] == []


@pytest.mark.asyncio
async def test_points_sum_to_the_shape_the_leaderboard_needs(client, make_token):
    """M8 reads SUM(points) per participant -- prove the totals come out right."""
    organiser = await player(client, make_token, "organiser@example.com")
    ctx = await drawn_group(client, organiser)
    a, b, c = ctx["members"]

    await _submit(client, organiser, ctx["group_id"], ctx["holes"][0], {a: 3, b: 4, c: 5})
    await _submit(client, organiser, ctx["group_id"], ctx["holes"][1], {a: 4, b: 3, c: 5})
    await _submit(client, organiser, ctx["group_id"], ctx["holes"][2], {a: 3, b: 4, c: 5})

    card = await client.get(f"/groups/{ctx['group_id']}/scores", headers=organiser)

    totals: dict[str, int] = {}
    for hole in card.json()["holes"]:
        for score in hole["scores"]:
            totals[score["participant_id"]] = (
                totals.get(score["participant_id"], 0) + score["points"]
            )

    assert totals == {a: 2, b: 1, c: 0}
    assert sum(totals.values()) == 3  # one point per hole, never halved


@pytest.mark.asyncio
async def test_an_unknown_group_is_404(client, make_token):
    organiser = await player(client, make_token, "organiser@example.com")
    response = await client.get(f"/groups/{uuid.uuid4()}/scores", headers=organiser)
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_scores_require_authentication(client):
    response = await client.get(f"/groups/{uuid.uuid4()}/scores")
    assert response.status_code == 403
