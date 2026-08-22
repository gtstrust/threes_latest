"""API-level tests for courses and holes."""

import uuid

import pytest
from httpx import AsyncClient


async def _player(client: AsyncClient, make_token, email: str = "creator@example.com"):
    headers = {"Authorization": f"Bearer {make_token(email=email)}"}
    await client.post("/players", headers=headers)
    return headers


async def _create_course(client: AsyncClient, headers, name: str = "Royal Melbourne", **extra):
    response = await client.post("/courses", headers=headers, json={"name": name, **extra})
    assert response.status_code == 201, response.text
    return response.json()


@pytest.mark.asyncio
async def test_creating_a_course(client, make_token):
    headers = await _player(client, make_token)

    course = await _create_course(client, headers, location="Black Rock, VIC")

    assert course["name"] == "Royal Melbourne"
    assert course["location"] == "Black Rock, VIC"


@pytest.mark.asyncio
async def test_course_names_collide_regardless_of_case(client, make_token):
    """The whole reason courses exist: one club shouldn't become several records."""
    headers = await _player(client, make_token)
    original = await _create_course(client, headers, name="Royal Melbourne")

    response = await client.post("/courses", headers=headers, json={"name": "royal melbourne"})

    assert response.status_code == 409
    # The caller is told which course to reuse rather than just being refused.
    assert original["id"] in response.json()["detail"]


@pytest.mark.asyncio
async def test_surrounding_whitespace_does_not_create_a_second_course(client, make_token):
    headers = await _player(client, make_token)
    await _create_course(client, headers, name="Kingston Heath")

    response = await client.post("/courses", headers=headers, json={"name": "  Kingston Heath  "})

    assert response.status_code == 409


@pytest.mark.asyncio
async def test_courses_require_authentication(client):
    assert (await client.get("/courses")).status_code in (401, 403)
    assert (await client.post("/courses", json={"name": "x"})).status_code in (401, 403)


@pytest.mark.asyncio
async def test_creating_a_course_without_a_profile_is_rejected(client, make_token):
    headers = {"Authorization": f"Bearer {make_token()}"}

    response = await client.post("/courses", headers=headers, json={"name": "No Profile"})

    assert response.status_code == 404
    assert "POST /players" in response.json()["detail"]


@pytest.mark.asyncio
async def test_anyone_authenticated_can_read_and_search_courses(client, make_token):
    owner = await _player(client, make_token, email="owner@example.com")
    await _create_course(client, owner, name="Barnbougle Dunes")
    stranger = await _player(client, make_token, email="stranger@example.com")

    listed = await client.get("/courses", headers=stranger, params={"name": "barnbougle"})

    assert listed.status_code == 200
    assert [row["name"] for row in listed.json()] == ["Barnbougle Dunes"]


@pytest.mark.asyncio
async def test_only_the_creator_can_edit_a_course(client, make_token):
    owner = await _player(client, make_token, email="owner@example.com")
    course = await _create_course(client, owner)
    stranger = await _player(client, make_token, email="stranger@example.com")

    assert (
        await client.patch(f"/courses/{course['id']}", headers=stranger, json={"name": "Hijacked"})
    ).status_code == 403
    assert (
        await client.put(
            f"/courses/{course['id']}/holes",
            headers=stranger,
            json={"holes": [{"hole_number": 1}]},
        )
    ).status_code == 403


@pytest.mark.asyncio
async def test_renaming_onto_an_existing_course_conflicts(client, make_token):
    headers = await _player(client, make_token)
    await _create_course(client, headers, name="Royal Melbourne")
    other = await _create_course(client, headers, name="Kingston Heath")

    response = await client.patch(
        f"/courses/{other['id']}", headers=headers, json={"name": "ROYAL MELBOURNE"}
    )

    assert response.status_code == 409


@pytest.mark.asyncio
async def test_unknown_course_is_404(client, make_token):
    headers = await _player(client, make_token)

    assert (await client.get(f"/courses/{uuid.uuid4()}", headers=headers)).status_code == 404


@pytest.mark.asyncio
async def test_a_three_hole_loop_needs_only_three_holes(client, make_token):
    """No requirement to enter all 18 before an event can run."""
    headers = await _player(client, make_token)
    course = await _create_course(client, headers)

    response = await client.put(
        f"/courses/{course['id']}/holes",
        headers=headers,
        json={
            "holes": [
                {"hole_number": 4, "par": 4},
                {"hole_number": 5, "par": 3},
                {"hole_number": 6, "par": 5},
            ]
        },
    )

    assert response.status_code == 200
    assert [hole["hole_number"] for hole in response.json()] == [4, 5, 6]
    assert [hole["par"] for hole in response.json()] == [4, 3, 5]


@pytest.mark.asyncio
async def test_upserting_holes_updates_rather_than_duplicating(client, make_token):
    headers = await _player(client, make_token)
    course = await _create_course(client, headers)

    await client.put(
        f"/courses/{course['id']}/holes",
        headers=headers,
        json={"holes": [{"hole_number": 4, "par": 4}]},
    )
    corrected = await client.put(
        f"/courses/{course['id']}/holes",
        headers=headers,
        json={"holes": [{"hole_number": 4, "par": 5}]},
    )

    assert len(corrected.json()) == 1
    assert corrected.json()[0]["par"] == 5


@pytest.mark.asyncio
async def test_upserting_holes_leaves_untouched_holes_alone(client, make_token):
    headers = await _player(client, make_token)
    course = await _create_course(client, headers)

    await client.put(
        f"/courses/{course['id']}/holes",
        headers=headers,
        json={"holes": [{"hole_number": 1}, {"hole_number": 2}]},
    )
    later = await client.put(
        f"/courses/{course['id']}/holes",
        headers=headers,
        json={"holes": [{"hole_number": 3}]},
    )

    assert [hole["hole_number"] for hole in later.json()] == [1, 2, 3]


@pytest.mark.asyncio
async def test_par_and_stroke_index_are_optional(client, make_token):
    """Scoring never uses par (ADR-007), so holes are playable without it."""
    headers = await _player(client, make_token)
    course = await _create_course(client, headers)

    response = await client.put(
        f"/courses/{course['id']}/holes",
        headers=headers,
        json={"holes": [{"hole_number": 7}]},
    )

    assert response.status_code == 200
    assert response.json()[0]["par"] is None
    assert response.json()[0]["stroke_index"] is None


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "bad_hole",
    [
        {"hole_number": 0},
        {"hole_number": 19},
        {"hole_number": 1, "par": 2},
        {"hole_number": 1, "par": 7},
        {"hole_number": 1, "stroke_index": 0},
        {"hole_number": 1, "stroke_index": 19},
    ],
)
async def test_out_of_range_hole_values_are_rejected(client, make_token, bad_hole):
    headers = await _player(client, make_token)
    course = await _create_course(client, headers)

    response = await client.put(
        f"/courses/{course['id']}/holes", headers=headers, json={"holes": [bad_hole]}
    )

    assert response.status_code == 422


@pytest.mark.asyncio
async def test_duplicate_hole_numbers_in_one_payload_are_rejected(client, make_token):
    """Ambiguous which one wins, so reject rather than let the constraint 500."""
    headers = await _player(client, make_token)
    course = await _create_course(client, headers)

    response = await client.put(
        f"/courses/{course['id']}/holes",
        headers=headers,
        json={"holes": [{"hole_number": 4, "par": 4}, {"hole_number": 4, "par": 5}]},
    )

    assert response.status_code == 422
    assert "Duplicate hole numbers" in response.text


@pytest.mark.asyncio
async def test_an_empty_hole_list_is_rejected(client, make_token):
    headers = await _player(client, make_token)
    course = await _create_course(client, headers)

    response = await client.put(
        f"/courses/{course['id']}/holes", headers=headers, json={"holes": []}
    )

    assert response.status_code == 422


@pytest.mark.asyncio
async def test_reading_a_course_includes_its_holes(client, make_token):
    headers = await _player(client, make_token)
    course = await _create_course(client, headers)
    await client.put(
        f"/courses/{course['id']}/holes",
        headers=headers,
        json={"holes": [{"hole_number": 2}, {"hole_number": 1}]},
    )

    response = await client.get(f"/courses/{course['id']}", headers=headers)

    assert response.status_code == 200
    # Ordered by hole number, not insertion order.
    assert [hole["hole_number"] for hole in response.json()["holes"]] == [1, 2]
