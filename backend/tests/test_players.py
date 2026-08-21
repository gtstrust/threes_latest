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
