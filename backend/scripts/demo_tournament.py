#!/usr/bin/env python3
"""Play a whole corporate golf day against a running Threes API.

Six players, two courses, one tournament, two rounds of three holes with the
groups redrawn in between, every hole scored, a winner declared — over real HTTP,
against whatever database the server is pointed at.

The pytest suite drives the app in-process with the schema dropped and rebuilt
around every test. This does not, which is the point: it is the only thing that
exercises the server's own configuration (SUPABASE_JWT_SECRET, CORS,
DATABASE_URL), the schema Alembic actually applied, and state accumulating across
requests rather than being wiped between them.

    docker compose up -d postgres
    alembic upgrade head
    uvicorn app.main:app --port 8000        # in another shell
    python scripts/demo_tournament.py

Exits 0 if every check passes and 1 otherwise. The data is left behind on
purpose: there is no DELETE for a tournament or a course in the API, and each run
creates its own players and courses, so runs accumulate rather than collide.
"""

from __future__ import annotations

import argparse
import os
import random
import sys
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import httpx
import jwt

DEFAULT_BASE_URL = "http://localhost:8000"
BACKEND_ROOT = Path(__file__).resolve().parent.parent

# Player 1 organises as well as plays. POST /tournaments needs a players row for
# the caller anyway (OrganiserProfileMissing), so a seventh identity that never
# swings a club would earn nothing.
PLAYER_NAMES = (
    "Marcus Webb",
    "Priya Nair",
    "Tom Ellery",
    "Ana Duarte",
    "Jules Okafor",
    "Kim Sandoval",
)
ORGANISER = 0

# Six holes make exactly two loops (build_loops chunks into consecutive triples)
# for exactly two groups of three, so the whole course is in play and each
# group's loop is legible in the output. Par is carried for realism only —
# ADR-007 scores on strokes alone and never reads it.
RIVERSIDE_HOLES = ((1, 4), (2, 3), (3, 5), (4, 4), (5, 3), (6, 4))
HIGHLANDS_HOLE_COUNT = 18


@dataclass(frozen=True)
class Card:
    """A scripted hole: strokes by seat, what the group can answer, what follows.

    Strokes are assigned by *seat within the group* rather than to a named
    player, because round 2's groups are shuffled server-side and this script
    cannot seed that. The pattern of ties is therefore deterministic even though
    who lands in them is not.
    """

    strokes: tuple[int, int, int]
    closest_to_pin_known: bool
    longest_drive_known: bool
    decided_by: str


# Twelve cards, one per group per hole: six decided outright on strokes, three on
# closest to the pin, two on longest drive, and one nobody wins. Every level of
# the ADR-007 cascade appears.
#
# The patterns assume groups of three, which six players always produce.
DECK: tuple[Card, ...] = (
    Card((4, 3, 5), False, False, "strokes"),
    Card((3, 3, 5), True, False, "closest_to_pin"),
    Card((3, 3, 4), False, False, "no_winner"),
    Card((5, 4, 3), False, False, "strokes"),
    Card((4, 4, 4), False, True, "longest_drive"),
    Card((3, 5, 4), False, False, "strokes"),
    Card((4, 4, 5), True, False, "closest_to_pin"),
    Card((4, 3, 5), False, False, "strokes"),
    Card((5, 5, 5), False, True, "longest_drive"),
    Card((5, 4, 3), False, False, "strokes"),
    Card((3, 3, 5), True, False, "closest_to_pin"),
    Card((3, 5, 4), False, False, "strokes"),
)

CARDS_PER_ROUND = 6


class ApiError(RuntimeError):
    """A request came back with a status the script did not expect."""

    def __init__(self, method: str, path: str, response: httpx.Response) -> None:
        super().__init__(
            f"{method} {path} → {response.status_code} (expected otherwise)\n  {response.text}"
        )
        self.response = response


class Api:
    """A thin httpx wrapper that counts requests and fails loudly with the body."""

    def __init__(self, base_url: str, timeout: float = 15.0) -> None:
        self._client = httpx.Client(base_url=base_url, timeout=timeout)
        self.base_url = base_url
        self.requests = 0

    def close(self) -> None:
        self._client.close()

    def call(
        self,
        method: str,
        path: str,
        *,
        token: str | None = None,
        json: Any = None,
        expect: tuple[int, ...] = (200,),
    ) -> Any:
        self.requests += 1
        headers = {"Authorization": f"Bearer {token}"} if token else None
        response = self._client.request(method, path, headers=headers, json=json)
        if response.status_code not in expect:
            raise ApiError(method, path, response)
        return response.json() if response.content else None

    def get(self, path: str, **kwargs: Any) -> Any:
        return self.call("GET", path, **kwargs)

    def post(self, path: str, **kwargs: Any) -> Any:
        return self.call("POST", path, **kwargs)

    def put(self, path: str, **kwargs: Any) -> Any:
        return self.call("PUT", path, **kwargs)


@dataclass
class Checks:
    """Assertions gathered as the day is played, reported at the end."""

    results: list[tuple[bool, str, str]] = field(default_factory=list)

    def check(self, ok: bool, label: str, detail: str = "") -> bool:
        self.results.append((ok, label, detail))
        return ok

    @property
    def failures(self) -> list[tuple[bool, str, str]]:
        return [result for result in self.results if not result[0]]


@dataclass
class Totals:
    """What one participant has accumulated, summed from the score responses."""

    points: int = 0
    strokes: int = 0
    holes: int = 0


def mint_token(secret: str, email: str) -> str:
    """Sign the JWT Supabase would have issued.

    There is no login endpoint to call: Supabase hands tokens straight to the
    client and this API only verifies them (app/core/security.py). Same claims as
    tests/conftest.py, minus pytest.
    """
    return jwt.encode(
        {"sub": str(uuid.uuid4()), "email": email, "aud": "authenticated"},
        secret,
        algorithm="HS256",
    )


def read_env_file(path: Path) -> dict[str, str]:
    """Pull KEY=value pairs out of a .env file. Absent file is not an error."""
    values: dict[str, str] = {}
    if not path.exists():
        return values
    for line in path.read_text().splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in stripped:
            continue
        key, _, value = stripped.partition("=")
        values[key.strip()] = value.strip().strip('"').strip("'")
    return values


def resolve_secret(args: argparse.Namespace) -> str:
    """--jwt-secret, else the environment, else backend/.env."""
    if args.jwt_secret:
        return str(args.jwt_secret)
    from_env = os.environ.get("SUPABASE_JWT_SECRET")
    if from_env:
        return from_env
    from_file = read_env_file(args.env_file).get("SUPABASE_JWT_SECRET")
    if from_file:
        return from_file
    sys.exit(
        f"No SUPABASE_JWT_SECRET found. Pass --jwt-secret, export it, or put it in {args.env_file}."
    )


class Reporter:
    """Everything the script prints, in one place so --quiet has one switch."""

    def __init__(self, quiet: bool) -> None:
        self.quiet = quiet

    def say(self, line: str = "") -> None:
        if not self.quiet:
            print(line)

    def heading(self, title: str) -> None:
        self.say()
        self.say(title)
        self.say("─" * max(len(title), 60))


def preflight(api: Api, token: str, report: Reporter) -> None:
    """Prove the server is up and agrees with us about the JWT secret.

    Worth its own step: a 500 here means the server's SUPABASE_JWT_SECRET is
    unset and a 401 means it is set to something else. Both are one-line fixes,
    and both otherwise surface as an inexplicable failure fifteen requests later.
    """
    try:
        health = api.get("/health")
    except httpx.ConnectError:
        sys.exit(
            f"Nothing listening on {api.base_url}.\n"
            "  Start it with: uvicorn app.main:app --port 8000"
        )
    report.say(f"  {api.base_url} → health {health['status']}")

    response = api.call("GET", "/auth/me", token=token, expect=(200, 401, 500))
    if response is None or "id" not in response:
        sys.exit(
            "The server rejected a token this script signed.\n"
            "  500 → its SUPABASE_JWT_SECRET is unset.\n"
            "  401 → it is set to a different value than this script is using.\n"
            f"  Detail: {response}"
        )
    report.say(f"  token accepted as {response['email']}")


def provision_players(
    api: Api, secret: str, run_tag: str, report: Reporter
) -> list[dict[str, Any]]:
    """Six authenticated players, each with a profile row."""
    report.heading("PLAYERS")
    players: list[dict[str, Any]] = []
    for name in PLAYER_NAMES:
        handle = name.split()[0].lower()
        token = mint_token(secret, f"{handle}.{run_tag}@threes.example")
        profile = api.post("/players", token=token)
        players.append({"name": name, "token": token, "player_id": profile["id"]})
        report.say(f"  {name:<16} {profile['id']}")
    return players


def create_courses(api: Api, token: str, run_tag: str, report: Reporter) -> tuple[str, str]:
    """Riverside, which the tournament is played at, and Highlands, which is not.

    Two courses because they are shared reference data rather than something a
    tournament owns — Highlands is created, given its holes, and left alone.
    """
    report.heading("COURSES")

    riverside = api.post(
        "/courses",
        token=token,
        json={"name": f"Riverside Threes Loop {run_tag}", "location": "Melbourne, VIC"},
        expect=(201,),
    )
    api.put(
        f"/courses/{riverside['id']}/holes",
        token=token,
        json={"holes": [{"hole_number": n, "par": par} for n, par in RIVERSIDE_HOLES]},
    )
    report.say(f"  {riverside['name']:<34} {len(RIVERSIDE_HOLES)} holes  ← the venue")

    highlands = api.post(
        "/courses",
        token=token,
        json={"name": f"Highlands Golf Club {run_tag}", "location": "Ballarat, VIC"},
        expect=(201,),
    )
    api.put(
        f"/courses/{highlands['id']}/holes",
        token=token,
        json={"holes": [{"hole_number": n} for n in range(1, HIGHLANDS_HOLE_COUNT + 1)]},
    )
    report.say(f"  {highlands['name']:<34} {HIGHLANDS_HOLE_COUNT} holes  (unused)")

    return str(riverside["id"]), str(highlands["id"])


def open_tournament(
    api: Api, players: list[dict[str, Any]], course_id: str, report: Reporter
) -> str:
    """Create the event and fill the field, each player registering themselves."""
    report.heading("TOURNAMENT")
    organiser = players[ORGANISER]

    tournament = api.post(
        "/tournaments",
        token=organiser["token"],
        json={"name": "Acme Corporate Golf Day", "course_id": course_id},
        expect=(201,),
    )
    tournament_id = str(tournament["id"])
    report.say(f"  created {tournament_id}  organised by {organiser['name']}")

    set_status(api, organiser["token"], tournament_id, "REGISTRATION_OPEN")
    report.say("  status → REGISTRATION_OPEN")

    for player in players:
        # Each player registers with their own token, in a fixed order. That
        # order is load-bearing: round 1 is drawn in it, and the leaderboard's
        # sort is stable, so it also settles who comes first among players level
        # on both points and strokes.
        participant = api.post(
            f"/tournaments/{tournament_id}/participants",
            token=player["token"],
            json={"display_name": player["name"]},
            expect=(201,),
        )
        player["participant_id"] = str(participant["id"])
        report.say(f"    registered {player['name']}")

    set_status(api, organiser["token"], tournament_id, "REGISTRATION_CLOSED")
    report.say("  status → REGISTRATION_CLOSED")
    return tournament_id


def set_status(api: Api, token: str, tournament_id: str, target: str) -> dict[str, Any]:
    result = api.post(f"/tournaments/{tournament_id}/status", token=token, json={"status": target})
    return dict(result)


def play_hole(
    api: Api,
    group: dict[str, Any],
    hole_id: str,
    card: Card,
    scorer: dict[str, Any],
    names: dict[str, str],
    hole_numbers: dict[str, int],
    report: Reporter,
) -> dict[str, Any]:
    """Enter one hole for one group, answering a tie-break only if one is asked.

    This is the real client flow from ADR-007: strokes go in first, and only if
    they tie does the app ask the *tied* players who was closest to the pin, then
    who hit the longest drive on the fairway. The answer is always taken from the
    `tied_participants` the API came back with — naming anyone else is rejected.
    """
    members = [str(member["participant_id"]) for member in group["members"]]
    strokes = {pid: card.strokes[seat] for seat, pid in enumerate(members)}
    body: dict[str, Any] = {"strokes": strokes}

    result = api.post(
        f"/groups/{group['id']}/holes/{hole_id}/scores", token=scorer["token"], json=body
    )

    card_line = "  ".join(f"{names[pid].split()[0]} {count}" for pid, count in strokes.items())
    report.say(f"    hole {hole_numbers[hole_id]}   {card_line}")

    tied = [str(pid) for pid in result["tied_participants"]]
    if tied and (card.closest_to_pin_known or card.longest_drive_known):
        answer: dict[str, Any] = {}
        if card.closest_to_pin_known:
            answer["closest_to_pin"] = tied[0]
            question = "closest to the pin"
            answered = tied[0]
        else:
            answer["longest_drive"] = tied[-1]
            question = "longest drive on the fairway"
            answered = tied[-1]

        tied_names = ", ".join(names[pid].split()[0] for pid in tied)
        report.say(f"             tied on strokes ({tied_names}) → asked {question}")
        result = api.post(
            f"/groups/{group['id']}/holes/{hole_id}/scores",
            token=scorer["token"],
            json={**body, **answer},
        )
        report.say(f"             answer: {names[answered].split()[0]}")

    winner = result["winner_participant_id"]
    won_by = names[str(winner)].split()[0] if winner else "nobody"
    report.say(f"             → {won_by} ({result['decided_by']})")
    return dict(result)


def play_round(
    api: Api,
    tournament_id: str,
    round_index: int,
    players: list[dict[str, Any]],
    names: dict[str, str],
    hole_numbers: dict[str, int],
    deck: list[Card],
    checks: Checks,
    report: Reporter,
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    """Draw a round, play every group's loop, and return the draw and the results."""
    organiser = players[ORGANISER]
    by_participant = {player["participant_id"]: player for player in players}

    round_ = api.post(
        f"/tournaments/{tournament_id}/rounds", token=organiser["token"], expect=(201,)
    )
    groups = sorted(round_["groups"], key=lambda group: group["group_number"])

    report.heading(f"ROUND {round_['round_number']}")
    results: list[dict[str, Any]] = []

    for group in groups:
        members = [str(member["participant_id"]) for member in group["members"]]
        holes = [
            str(hole["hole_id"])
            for hole in sorted(group["holes"], key=lambda hole: hole["sequence"])
        ]

        # A member of this group enters its card, never the organiser —
        # require_group_member lets the organiser score any group, so using them
        # would hide a broken membership check.
        scorer = next(
            (by_participant[pid] for pid in members if pid != organiser["participant_id"]),
            organiser,
        )

        loop = ", ".join(str(hole_numbers[hole_id]) for hole_id in holes)
        report.say()
        report.say(
            f"  Group {group['group_number']}: "
            f"{', '.join(names[pid] for pid in members)}  —  holes {loop}"
        )
        report.say(f"  card kept by {scorer['name']}")

        for sequence, hole_id in enumerate(holes):
            card = deck[round_index * CARDS_PER_ROUND + (group["group_number"] - 1) * 3 + sequence]
            result = play_hole(api, group, hole_id, card, scorer, names, hole_numbers, report)
            checks.check(
                result["decided_by"] == card.decided_by,
                f"round {round_['round_number']} hole {hole_numbers[hole_id]} "
                f"decided by {card.decided_by}",
                f"got {result['decided_by']}",
            )
            results.append(result)

    return dict(round_), results


def accumulate(results: list[dict[str, Any]]) -> dict[str, Totals]:
    """Sum the score responses the API already returned, per participant."""
    totals: dict[str, Totals] = {}
    for result in results:
        for score in result["scores"]:
            entry = totals.setdefault(str(score["participant_id"]), Totals())
            entry.points += score["points"]
            entry.strokes += score["strokes"]
            entry.holes += 1
    return totals


def expected_board(
    totals: dict[str, Totals], registration_order: list[str]
) -> list[tuple[int, str, int, int]]:
    """Rank the accumulated totals the way ADR-007 says the board should read.

    Points first, fewest strokes second, and — because Python's sort is stable
    and `registration_order` is the input order — registration order third, which
    is exactly the tie-break-of-last-resort the server relies on. Genuinely level
    players share a position and the next one skips (1, 2, 2, 4).
    """
    ordered = sorted(
        registration_order,
        key=lambda pid: (-totals[pid].points, totals[pid].strokes),
    )

    board: list[tuple[int, str, int, int]] = []
    for index, pid in enumerate(ordered):
        previous = ordered[index - 1] if index else None
        level = previous is not None and (
            totals[pid].points,
            totals[pid].strokes,
        ) == (totals[previous].points, totals[previous].strokes)
        position = board[-1][0] if level and board else index + 1
        board.append((position, pid, totals[pid].points, totals[pid].strokes))
    return board


def print_board(title: str, board: dict[str, Any], report: Reporter) -> None:
    report.say()
    report.say(f"  {title}")
    report.say(f"  {'pos':>3}  {'player':<16} {'pts':>4} {'strokes':>8} {'holes':>6}")
    for entry in board["entries"]:
        report.say(
            f"  {entry['position']:>3}  {entry['display_name']:<16} "
            f"{entry['points']:>4} {entry['total_strokes']:>8} {entry['holes_played']:>6}"
        )


def verify_board(
    board: dict[str, Any],
    totals: dict[str, Totals],
    registration_order: list[str],
    label: str,
    checks: Checks,
) -> None:
    """Hold a leaderboard response against the score responses it came from."""
    entries = board["entries"]

    ids = [str(entry["participant_id"]) for entry in entries]
    checks.check(
        sorted(ids) == sorted(registration_order),
        f"{label}: every participant listed exactly once",
        f"got {len(ids)} entries for {len(registration_order)} participants",
    )
    if sorted(ids) != sorted(registration_order):
        return

    for participant_id in registration_order:
        totals.setdefault(participant_id, Totals())

    expected = expected_board(totals, registration_order)
    actual = [
        (
            entry["position"],
            str(entry["participant_id"]),
            entry["points"],
            entry["total_strokes"],
        )
        for entry in entries
    ]
    checks.check(
        actual == expected,
        f"{label}: positions, points and strokes match the scores entered",
        f"\n      api      {actual}\n      expected {expected}",
    )

    holes_ok = all(
        entry["holes_played"] == totals[str(entry["participant_id"])].holes for entry in entries
    )
    checks.check(holes_ok, f"{label}: holes_played matches the cards submitted")


def declare_winner(board: dict[str, Any], report: Reporter) -> None:
    entries = board["entries"]
    leaders = [entry for entry in entries if entry["position"] == 1]
    report.say()
    if len(leaders) == 1:
        winner = leaders[0]
        report.say(
            f"  WINNER: {winner['display_name']} — "
            f"{winner['points']} points, {winner['total_strokes']} strokes"
        )
    else:
        names = ", ".join(entry["display_name"] for entry in leaders)
        report.say(f"  SHARED WIN: {names} — level on points and strokes")


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--base-url", default=DEFAULT_BASE_URL, help="the running API")
    parser.add_argument("--jwt-secret", default=None, help="overrides the environment and .env")
    parser.add_argument(
        "--env-file", type=Path, default=BACKEND_ROOT / ".env", help="where to look for the secret"
    )
    parser.add_argument(
        "--seed",
        type=int,
        default=None,
        help="shuffle which scripted card goes to which hole (the server's own "
        "round-2 shuffle is not seedable from here)",
    )
    parser.add_argument("--quiet", action="store_true", help="only print the verdict")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    secret = resolve_secret(args)
    report = Reporter(args.quiet)
    checks = Checks()
    run_tag = uuid.uuid4().hex[:8]

    deck = list(DECK)
    if args.seed is not None:
        random.Random(args.seed).shuffle(deck)

    api = Api(args.base_url)
    try:
        report.heading("PREFLIGHT")
        preflight(api, mint_token(secret, f"preflight.{run_tag}@threes.example"), report)

        players = provision_players(api, secret, run_tag, report)
        organiser = players[ORGANISER]
        course_id, _unused_course_id = create_courses(api, organiser["token"], run_tag, report)
        tournament_id = open_tournament(api, players, course_id, report)

        course = api.get(f"/courses/{course_id}", token=organiser["token"])
        hole_numbers = {str(hole["id"]): hole["hole_number"] for hole in course["holes"]}
        names = {player["participant_id"]: player["name"] for player in players}
        registration_order = [player["participant_id"] for player in players]

        rounds: list[dict[str, Any]] = []
        per_round_results: list[list[dict[str, Any]]] = []
        groupings: list[list[frozenset[str]]] = []

        for round_index in range(2):
            round_, results = play_round(
                api,
                tournament_id,
                round_index,
                players,
                names,
                hole_numbers,
                deck,
                checks,
                report,
            )
            rounds.append(round_)
            per_round_results.append(results)
            groupings.append(
                [
                    frozenset(str(member["participant_id"]) for member in group["members"])
                    for group in round_["groups"]
                ]
            )

            drawn_ids = {
                str(member["participant_id"])
                for group in round_["groups"]
                for member in group["members"]
            }
            # Registration order, not draw order. The server ranks a round by
            # filtering the tournament's field, and rank_leaderboard's sort is
            # stable, so registration order is what separates players level on
            # both points and strokes. Reading the draw instead only agrees in
            # round 1, where the two happen to coincide.
            drawn = [pid for pid in registration_order if pid in drawn_ids]
            board = api.get(f"/rounds/{round_['id']}/leaderboard", token=organiser["token"])
            print_board(f"Round {round_['round_number']} standings", board, report)
            verify_board(
                board,
                accumulate(results),
                drawn,
                f"round {round_['round_number']} board",
                checks,
            )

            api.post(f"/rounds/{round_['id']}/complete", token=organiser["token"])
            report.say(f"  round {round_['round_number']} complete")

        # Reported, not asserted: six players split into two threes ten ways, so
        # the round-2 shuffle reproduces round 1 about one run in ten.
        report.say()
        if set(groupings[0]) == set(groupings[1]):
            report.say("  note: the round-2 shuffle happened to reproduce round 1's groups")
        else:
            report.say("  groups were redrawn between rounds")

        set_status(api, organiser["token"], tournament_id, "TOURNAMENT_COMPLETE")
        final = api.get(f"/tournaments/{tournament_id}", token=organiser["token"])
        checks.check(
            final["status"] == "TOURNAMENT_COMPLETE",
            "tournament finished in TOURNAMENT_COMPLETE",
            f"got {final['status']}",
        )

        report.heading("FINAL STANDINGS")
        cumulative = api.get(f"/tournaments/{tournament_id}/leaderboard", token=organiser["token"])
        all_results = [result for results in per_round_results for result in results]
        totals = accumulate(all_results)
        print_board("Acme Corporate Golf Day", cumulative, report)
        verify_board(cumulative, totals, registration_order, "tournament board", checks)
        declare_winner(cumulative, report)

        checks.check(
            all(entry.holes == 6 for entry in totals.values()),
            "every player scored six holes",
            f"got {sorted({entry.holes for entry in totals.values()})}",
        )
        round_points = [sum(t.points for t in accumulate(r).values()) for r in per_round_results]
        board_points = sum(entry["points"] for entry in cumulative["entries"])
        checks.check(
            sum(round_points) == board_points,
            "the two round boards sum to the tournament board",
            f"rounds {round_points} vs board {board_points}",
        )

    except ApiError as exc:
        report.say()
        print(f"REQUEST FAILED\n  {exc}", file=sys.stderr)
        return 1
    finally:
        api.close()

    report.heading("CHECKS")
    for ok, label, detail in checks.results:
        report.say(f"  {'✓' if ok else '✗'} {label}{'' if ok else f' — {detail}'}")

    failures = checks.failures
    verdict = "PASS" if not failures else f"FAIL ({len(failures)} of {len(checks.results)})"
    print(f"\n{verdict} · {len(checks.results)} checks · {api.requests} requests")
    if failures and args.quiet:
        for _ok, label, detail in failures:
            print(f"  ✗ {label} — {detail}")
    return 0 if not failures else 1


if __name__ == "__main__":
    sys.exit(main())
