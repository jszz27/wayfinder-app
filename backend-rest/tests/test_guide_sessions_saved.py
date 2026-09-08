"""Guide mode for a signed-in user, where the conversation is kept.

test_guide_sessions.py covers the same endpoints signed out, where nothing
is written. The pair of files is the point: the endpoints behave the same
either way, and the only difference is whether anything survives.
"""

import base64
import uuid

import pytest
import sqlalchemy as sa

PASSWORD = "correct horse battery"

# A real 1x1 PNG, so the decode path runs on actual image bytes.
PNG_1X1 = (
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8"
    "z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg=="
)
assert base64.b64decode(PNG_1X1)


async def account(api, email="ann@example.com", name="Ann"):
    response = await api.post(
        "/api/auth/signup",
        json={"email": email, "password": PASSWORD, "display_name": name},
    )
    assert response.status_code == 201
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


async def start(api, headers=None):
    return await api.post("/api/guide/sessions", headers=headers or {})


async def ask(
    api,
    session_id,
    content="Which button do I press?",
    headers=None,
    screenshot=None,
):
    payload = {"content": content}
    if screenshot is not None:
        payload["screenshot"] = screenshot
    return await api.post(
        f"/api/guide/sessions/{session_id}/messages",
        json=payload,
        headers=headers or {},
    )


async def count(engine, table):
    async with engine.connect() as connection:
        return await connection.scalar(sa.text(f"select count(*) from {table}"))


# --- what gets kept ---------------------------------------------------


@pytest.mark.asyncio
async def test_a_signed_in_conversation_is_saved(api, db_schema):
    headers = await account(api)

    response = await start(api, headers)

    assert response.status_code == 201
    assert response.json()["saved"] is True
    assert await count(db_schema, "guide_sessions") == 1


@pytest.mark.asyncio
async def test_a_signed_out_conversation_reaches_no_table(api, db_schema):
    started = await start(api)
    session_id = started.json()["session_id"]
    await ask(api, session_id, "How do I send money?")
    await ask(api, session_id, "And after that?")

    assert started.json()["saved"] is False
    assert await count(db_schema, "guide_sessions") == 0
    assert await count(db_schema, "guide_messages") == 0


@pytest.mark.asyncio
async def test_both_turns_are_written(api, db_schema):
    headers = await account(api)
    session_id = (await start(api, headers)).json()["session_id"]

    await ask(api, session_id, "How do I send money?", headers)

    async with db_schema.connect() as connection:
        rows = (
            await connection.execute(
                sa.text("select role, content from guide_messages order by created_at")
            )
        ).all()
    assert [row.role for row in rows] == ["user", "assistant"]
    assert rows[0].content == "How do I send money?"


@pytest.mark.asyncio
async def test_the_history_comes_back(api, db_schema):
    headers = await account(api)
    session_id = (await start(api, headers)).json()["session_id"]
    await ask(api, session_id, "First question", headers)
    await ask(api, session_id, "Second question", headers)

    body = (await api.get(f"/api/guide/sessions/{session_id}", headers=headers)).json()

    assert [m["role"] for m in body["messages"]] == [
        "user",
        "assistant",
        "user",
        "assistant",
    ]
    assert [m["content"] for m in body["messages"]][::2] == [
        "First question",
        "Second question",
    ]


@pytest.mark.asyncio
async def test_earlier_turns_reach_the_model(api, db_schema):
    # The mock counts user turns, so a rising count proves the stored
    # history was loaded and passed on, rather than each question being
    # answered in isolation.
    headers = await account(api)
    session_id = (await start(api, headers)).json()["session_id"]

    first = (await ask(api, session_id, "First", headers)).json()["content"]
    second = (await ask(api, session_id, "Second", headers)).json()["content"]

    assert "reply 1" in first
    assert "reply 2" in second


# --- the screenshot ---------------------------------------------------


@pytest.mark.asyncio
async def test_the_screenshot_is_not_written_down(api, db_schema):
    # Plan.md section 10: only the response text is logged, so that
    # sensitive on-screen content is not retained.
    headers = await account(api)
    session_id = (await start(api, headers)).json()["session_id"]

    await ask(api, session_id, "Help", headers, screenshot=PNG_1X1)

    async with db_schema.connect() as connection:
        contents = (
            await connection.scalars(sa.text("select content from guide_messages"))
        ).all()
    assert all(PNG_1X1 not in content for content in contents)
    assert any("I can see your screen" in content for content in contents)


# --- whose conversation it is -----------------------------------------


@pytest.mark.asyncio
async def test_another_persons_conversation_is_not_found(api, db_schema):
    mine = await account(api)
    theirs = await account(api, email="mallory@example.com", name="Mallory")
    session_id = (await start(api, theirs)).json()["session_id"]

    response = await api.get(f"/api/guide/sessions/{session_id}", headers=mine)

    assert response.status_code == 404


@pytest.mark.asyncio
async def test_another_person_cannot_add_to_it(api, db_schema):
    mine = await account(api)
    theirs = await account(api, email="mallory@example.com", name="Mallory")
    session_id = (await start(api, theirs)).json()["session_id"]

    response = await ask(api, session_id, "Sneaking in", mine)

    assert response.status_code == 404
    assert await count(db_schema, "guide_messages") == 0


@pytest.mark.asyncio
async def test_an_unknown_session_is_not_found(api, db_schema):
    headers = await account(api)

    response = await api.get(f"/api/guide/sessions/{uuid.uuid4()}", headers=headers)

    assert response.status_code == 404


# --- completing -------------------------------------------------------


@pytest.mark.asyncio
async def test_completing_is_written_down(api, db_schema):
    headers = await account(api)
    session_id = (await start(api, headers)).json()["session_id"]

    response = await api.patch(
        f"/api/guide/sessions/{session_id}/complete", headers=headers
    )

    assert response.status_code == 200
    assert response.json()["completed_at"] is not None
    async with db_schema.connect() as connection:
        stored = await connection.scalar(
            sa.text("select completed_at from guide_sessions")
        )
    assert stored is not None


@pytest.mark.asyncio
async def test_a_completed_conversation_takes_no_more_questions(api, db_schema):
    headers = await account(api)
    session_id = (await start(api, headers)).json()["session_id"]
    await api.patch(f"/api/guide/sessions/{session_id}/complete", headers=headers)

    response = await ask(api, session_id, "One more", headers)

    assert response.status_code == 409


@pytest.mark.asyncio
async def test_deleting_the_account_takes_the_conversation_with_it(api, db_schema):
    headers = await account(api)
    session_id = (await start(api, headers)).json()["session_id"]
    await ask(api, session_id, "How do I send money?", headers)

    async with db_schema.begin() as connection:
        await connection.execute(sa.text("delete from users"))

    assert await count(db_schema, "guide_sessions") == 0
    assert await count(db_schema, "guide_messages") == 0
