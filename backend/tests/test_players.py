import pytest


@pytest.mark.asyncio
async def test_auth_me_requires_token(client):
    response = await client.get("/auth/me")
    assert response.status_code in (401, 403)


@pytest.mark.asyncio
async def test_auth_me_with_token(client, make_token):
    token = make_token()
    response = await client.get("/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert response.status_code == 200


@pytest.mark.asyncio
async def test_players_full_slice(client, make_token):
    token = make_token(email="player@example.com")
    headers = {"Authorization": f"Bearer {token}"}

    me_before = await client.get("/players/me", headers=headers)
    assert me_before.status_code == 404

    created = await client.post("/players", headers=headers)
    assert created.status_code == 200
    assert created.json()["email"] == "player@example.com"

    me_after = await client.get("/players/me", headers=headers)
    assert me_after.status_code == 200

    updated = await client.patch(
        "/players/me", headers=headers, json={"display_name": "Test Player"}
    )
    assert updated.status_code == 200
    assert updated.json()["display_name"] == "Test Player"

    no_token = await client.get("/players/me")
    assert no_token.status_code in (401, 403)


@pytest.mark.asyncio
async def test_another_players_profile_is_not_readable(client, make_token):
    """A player's email is theirs, not the field's.

    There used to be a `GET /players/{player_id}` returning `PlayerRead` — email
    included — behind nothing but a valid token. `ParticipantRead` hands out
    `player_id` to everyone who can read a field, so joining an event was enough
    to collect the guest list's email addresses (#27).

    Asserted by outcome rather than by "the route is gone", so it fails just as
    loudly if somebody reinstates a lookup that carries contact details.
    """
    someone = {"Authorization": f"Bearer {make_token(email='someone@example.com')}"}
    profile = await client.post("/players", headers=someone)
    assert profile.status_code == 200
    their_id = profile.json()["id"]

    stranger = {"Authorization": f"Bearer {make_token(email='stranger@example.com')}"}
    await client.post("/players", headers=stranger)

    looked_up = await client.get(f"/players/{their_id}", headers=stranger)

    assert looked_up.status_code == 404
    assert "someone@example.com" not in looked_up.text

    # The /me routes are the ones an ordering change could plausibly disturb, so
    # check the caller can still read themselves.
    assert (await client.get("/players/me", headers=stranger)).status_code == 200
