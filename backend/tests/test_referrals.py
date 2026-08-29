"""Referral attribution.

Who brought whom, and nothing else. There is no reward here on purpose: the
question worth being able to ask before there is revenue is "is word of mouth
working?", and a rewards scheme invented now would collide with an organiser fee
Phase 3 has yet to design.

The rule that carries the weight is that attribution happens **once, at
creation**. `POST /players` runs on every login, so anything looser would let the
last person to send a link claim a player who has been here for months.
"""

from httpx import AsyncClient

from app.services.join_code import REFERRAL_PREFIX


async def _profile(client: AsyncClient, make_token, email: str, referral_code: str | None = None):
    """Provision a profile the way the client does, optionally with a code."""
    headers = {"Authorization": f"Bearer {make_token(email=email)}"}
    body = {"referral_code": referral_code} if referral_code else {}
    created = await client.post("/players", headers=headers, json=body)
    assert created.status_code == 200, created.text
    return headers


async def _referrals(client: AsyncClient, headers) -> dict:
    response = await client.get("/players/me/referrals", headers=headers)
    assert response.status_code == 200, response.text
    return response.json()


async def test_every_player_gets_a_code_the_moment_they_exist(client, make_token):
    """A code you have to go and ask for is a code nobody shares."""
    headers = await _profile(client, make_token, "solo@example.com")

    body = await _referrals(client, headers)

    assert body["referral_code"].startswith(REFERRAL_PREFIX)
    assert body["players_referred"] == 0


async def test_codes_are_distinct_between_players(client, make_token):
    codes = set()
    for n in range(5):
        headers = await _profile(client, make_token, f"p{n}@example.com")
        codes.add((await _referrals(client, headers))["referral_code"])

    assert len(codes) == 5


async def test_signing_up_through_a_code_is_attributed(client, make_token):
    referrer = await _profile(client, make_token, "referrer@example.com")
    code = (await _referrals(client, referrer))["referral_code"]

    await _profile(client, make_token, "newcomer@example.com", referral_code=code)

    assert (await _referrals(client, referrer))["players_referred"] == 1


async def test_a_lowercase_code_still_attributes(client, make_token):
    """It arrives from a URL somebody typed or a link they retyped."""
    referrer = await _profile(client, make_token, "referrer@example.com")
    code = (await _referrals(client, referrer))["referral_code"]

    await _profile(client, make_token, "newcomer@example.com", referral_code=code.lower())

    assert (await _referrals(client, referrer))["players_referred"] == 1


async def test_an_existing_profile_is_never_re_attributed(client, make_token):
    """POST /players runs on every login, so this is the rule that matters."""
    first = await _profile(client, make_token, "first@example.com")
    second = await _profile(client, make_token, "second@example.com")
    established = await _profile(client, make_token, "established@example.com")

    # The established player logs in again, this time carrying a code.
    for referrer in (first, second):
        code = (await _referrals(client, referrer))["referral_code"]
        again = await client.post("/players", headers=established, json={"referral_code": code})
        assert again.status_code == 200

    assert (await _referrals(client, first))["players_referred"] == 0
    assert (await _referrals(client, second))["players_referred"] == 0


async def test_an_unknown_code_is_ignored_rather_than_refused(client, make_token):
    """Failing a login over a mistyped query parameter trades a real sign-in for
    a piece of analytics."""
    headers = {"Authorization": f"Bearer {make_token(email='newcomer@example.com')}"}

    created = await client.post("/players", headers=headers, json={"referral_code": "MATE-ZZZZZ"})

    assert created.status_code == 200
    assert (await _referrals(client, headers))["players_referred"] == 0


async def test_an_empty_body_still_provisions_a_profile(client, make_token):
    """The endpoint predates referrals; every existing caller sends nothing."""
    headers = {"Authorization": f"Bearer {make_token(email='plain@example.com')}"}

    created = await client.post("/players", headers=headers)

    assert created.status_code == 200, created.text
    assert (await _referrals(client, headers))["referral_code"].startswith(REFERRAL_PREFIX)


async def test_one_referrer_can_bring_several_players(client, make_token):
    referrer = await _profile(client, make_token, "referrer@example.com")
    code = (await _referrals(client, referrer))["referral_code"]

    for n in range(3):
        await _profile(client, make_token, f"newcomer{n}@example.com", referral_code=code)

    assert (await _referrals(client, referrer))["players_referred"] == 3


async def test_referrals_need_a_profile(client, make_token):
    """A verified token does not imply a row — the same 404 every /players route gives."""
    headers = {"Authorization": f"Bearer {make_token(email='nobody@example.com')}"}

    response = await client.get("/players/me/referrals", headers=headers)

    assert response.status_code == 404
    assert "POST /players" in response.json()["detail"]
