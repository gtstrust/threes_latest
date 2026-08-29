"""A player's own record.

The load-bearing claim is that a position here is the same position the
leaderboard gives — which is what reusing `LeaderboardService` rather than
ranking in SQL was for. That is asserted directly rather than against a
hand-written expectation, so the two cannot drift apart without failing.
"""

from httpx import AsyncClient

from app.models.tournament import TournamentStatus
from tests.helpers import add_virtual, course, draw, player, set_status, tournament


async def _played_event(client: AsyncClient, make_token, organiser, guest_email: str) -> dict:
    """An event with two players, one round drawn and one hole scored."""
    course_id = await course(client, organiser, hole_count=3)
    tournament_id = await tournament(client, organiser, course_id)
    await set_status(client, organiser, tournament_id, TournamentStatus.REGISTRATION_OPEN)

    guest = await player(client, make_token, guest_email)
    joined = await client.post(f"/tournaments/{tournament_id}/participants", headers=guest, json={})
    assert joined.status_code == 201, joined.text
    guest_participant = joined.json()["id"]
    other = await add_virtual(client, organiser, tournament_id, "Someone")

    await set_status(client, organiser, tournament_id, TournamentStatus.REGISTRATION_CLOSED)
    drawn = await draw(client, organiser, tournament_id)
    assert drawn.status_code == 201, drawn.text
    group = drawn.json()["groups"][0]
    hole_id = group["holes"][0]["hole_id"]

    # The guest wins the hole outright.
    scored = await client.post(
        f"/groups/{group['id']}/holes/{hole_id}/scores",
        headers=organiser,
        json={"strokes": {guest_participant: 3, other: 5}},
    )
    assert scored.status_code == 200, scored.text
    return {"tournament_id": tournament_id, "guest": guest, "participant": guest_participant}


async def test_a_player_who_has_played_nothing_gets_zeroes_not_an_error(client, make_token):
    fresh = await player(client, make_token, "fresh@example.com")

    stats = await client.get("/players/me/stats", headers=fresh)

    assert stats.status_code == 200, stats.text
    body = stats.json()
    assert body["history"] == []
    assert body["career"] == {
        "events_played": 0,
        "holes_played": 0,
        "holes_won": 0,
        "total_strokes": 0,
        "win_rate": 0.0,
        "average_strokes": 0.0,
    }


async def test_career_totals_count_holes_won_and_strokes(client, make_token):
    organiser = await player(client, make_token, "organiser@example.com")
    played = await _played_event(client, make_token, organiser, "guest@example.com")

    body = (await client.get("/players/me/stats", headers=played["guest"])).json()

    career = body["career"]
    assert career["events_played"] == 1
    assert career["holes_played"] == 1
    # SUM(points) is holes won — ADR-007 makes a hole worth 1 or 0.
    assert career["holes_won"] == 1
    assert career["total_strokes"] == 3
    assert career["win_rate"] == 1.0
    assert career["average_strokes"] == 3.0


async def test_the_history_position_matches_the_leaderboard(client, make_token):
    """The point of ranking through LeaderboardService instead of a SQL window."""
    organiser = await player(client, make_token, "organiser@example.com")
    played = await _played_event(client, make_token, organiser, "guest@example.com")

    board = await client.get(
        f"/tournaments/{played['tournament_id']}/leaderboard", headers=played["guest"]
    )
    theirs = next(
        entry
        for entry in board.json()["entries"]
        if entry["participant_id"] == played["participant"]
    )

    body = (await client.get("/players/me/stats", headers=played["guest"])).json()
    row = body["history"][0]

    assert row["position"] == theirs["position"]
    assert row["points"] == theirs["points"]
    assert row["total_strokes"] == theirs["total_strokes"]


async def test_an_event_not_yet_played_is_listed_without_a_position(client, make_token):
    """Being in something is part of a history; a placing it hasn't earned is not."""
    organiser = await player(client, make_token, "organiser@example.com")
    course_id = await course(client, organiser, hole_count=3)
    tournament_id = await tournament(client, organiser, course_id)
    await set_status(client, organiser, tournament_id, TournamentStatus.REGISTRATION_OPEN)
    guest = await player(client, make_token, "guest@example.com")
    await client.post(f"/tournaments/{tournament_id}/participants", headers=guest, json={})

    row = (await client.get("/players/me/stats", headers=guest)).json()["history"][0]

    assert row["position"] is None
    assert row["holes_played"] == 0
    assert row["status"] == "REGISTRATION_OPEN"


async def test_fun_rounds_appear_in_a_players_history(client, make_token):
    """Same table, same scoring — hiding half a record because it was casual
    would make the count on the same page wrong."""
    host = await player(client, make_token, "host@example.com")
    created = await client.post("/fun-rounds", headers=host, json={"name": "Saturday nine"})
    assert created.status_code == 201, created.text

    body = (await client.get("/players/me/stats", headers=host)).json()

    assert [row["kind"] for row in body["history"]] == ["FUN_ROUND"]
    assert body["career"]["events_played"] == 1


async def test_two_events_come_back_newest_first(client, make_token):
    organiser = await player(client, make_token, "organiser@example.com")
    first = await _played_event(client, make_token, organiser, "guest@example.com")
    guest = first["guest"]

    course_id = await course(client, organiser, hole_count=3)
    second_id = await tournament(client, organiser, course_id)
    await set_status(client, organiser, second_id, TournamentStatus.REGISTRATION_OPEN)
    await client.post(f"/tournaments/{second_id}/participants", headers=guest, json={})

    history = (await client.get("/players/me/stats", headers=guest)).json()["history"]

    assert [row["tournament_id"] for row in history] == [second_id, first["tournament_id"]]


async def test_a_virtual_player_never_appears_in_anyone_s_record(client, make_token):
    """They have no account, so there is nobody whose record it would be."""
    organiser = await player(client, make_token, "organiser@example.com")
    played = await _played_event(client, make_token, organiser, "guest@example.com")

    # The organiser entered the virtual player's scores but did not play.
    career = (await client.get("/players/me/stats", headers=organiser)).json()["career"]

    assert career["holes_played"] == 0
    assert career["events_played"] == 0
    assert played["participant"] is not None
