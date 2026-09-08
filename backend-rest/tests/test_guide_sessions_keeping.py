"""Keeping, naming and removing a conversation.

Auto-save off holds a signed-in conversation the same way an anonymous one
is held -- in this process, reaching no table -- until the person asks for
it. What then gets written is the copy this service already has, so a
client cannot put words in the assistant's mouth by asking for them to be
saved.
"""

import pytest
import sqlalchemy as sa

PASSWORD = "correct horse battery"
GONE = "00000000-0000-4000-8000-000000000000"


async def account(api, email="ann@example.com", name="Ann"):
    response = await api.post(
        "/api/auth/signup",
        json={"email": email, "password": PASSWORD, "display_name": name},
    )
    assert response.status_code == 201
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


async def unkept(api, *questions):
    """A conversation started without an account, as auto-save off does."""
    session_id = (await api.post("/api/guide/sessions")).json()["session_id"]
    for question in questions:
        await api.post(
            f"/api/guide/sessions/{session_id}/messages", json={"content": question}
        )
    return session_id


async def kept(api, headers, *questions):
    session_id = (await api.post("/api/guide/sessions", headers=headers)).json()[
        "session_id"
    ]
    for question in questions:
        await api.post(
            f"/api/guide/sessions/{session_id}/messages",
            json={"content": question},
            headers=headers,
        )
    return session_id


async def listed(api, headers):
    return (await api.get("/api/guide/sessions", headers=headers)).json()


async def count(engine, table):
    async with engine.connect() as connection:
        return await connection.scalar(sa.text(f"select count(*) from {table}"))


# --- keeping one by hand ----------------------------------------------


@pytest.mark.asyncio
async def test_nothing_is_written_until_it_is_asked_for(api, db_schema):
    headers = await account(api)
    await unkept(api, "How do I send money?")

    assert await count(db_schema, "guide_sessions") == 0
    assert await listed(api, headers) == []


@pytest.mark.asyncio
async def test_a_conversation_can_be_kept_on_request(api, db_schema):
    headers = await account(api)
    session_id = await unkept(api, "How do I send money?")

    response = await api.post(f"/api/guide/sessions/{session_id}/save", headers=headers)

    assert response.status_code == 201
    assert response.json()["opening"] == "How do I send money?"
    assert [row["opening"] for row in await listed(api, headers)] == [
        "How do I send money?"
    ]


@pytest.mark.asyncio
async def test_what_is_kept_is_what_the_guide_actually_said(api, db_schema):
    # The saved copy comes from this service, not from the browser.
    headers = await account(api)
    session_id = await unkept(api, "How do I send money?")

    await api.post(f"/api/guide/sessions/{session_id}/save", headers=headers)

    async with db_schema.connect() as connection:
        rows = (
            await connection.execute(
                sa.text("select role, content from guide_messages order by created_at")
            )
        ).all()
    assert [row.role for row in rows] == ["user", "assistant"]
    assert rows[0].content == "How do I send money?"
    assert "reply 1" in rows[1].content


@pytest.mark.asyncio
async def test_keeping_it_again_after_carrying_on_adds_the_rest(api, db_schema):
    # One conversation, not two, and not one holding a second copy of its
    # own beginning.
    headers = await account(api)
    session_id = await unkept(api, "First")
    await api.post(f"/api/guide/sessions/{session_id}/save", headers=headers)

    await api.post(
        f"/api/guide/sessions/{session_id}/messages", json={"content": "Second"}
    )
    await api.post(f"/api/guide/sessions/{session_id}/save", headers=headers)

    rows = await listed(api, headers)
    assert len(rows) == 1
    assert rows[0]["exchanges"] == 2
    assert await count(db_schema, "guide_messages") == 4


@pytest.mark.asyncio
async def test_keeping_it_twice_unchanged_adds_nothing(api, db_schema):
    headers = await account(api)
    session_id = await unkept(api, "Only once")

    await api.post(f"/api/guide/sessions/{session_id}/save", headers=headers)
    await api.post(f"/api/guide/sessions/{session_id}/save", headers=headers)

    assert len(await listed(api, headers)) == 1
    assert await count(db_schema, "guide_messages") == 2


@pytest.mark.asyncio
async def test_keeping_needs_an_account(api, db_schema):
    session_id = await unkept(api, "Anyone's question")

    response = await api.post(f"/api/guide/sessions/{session_id}/save")

    assert response.status_code == 401


@pytest.mark.asyncio
async def test_a_conversation_this_service_no_longer_holds_cannot_be_kept(
    api, db_schema
):
    # It lives in this process, so a restart loses it. Saying so beats
    # writing an empty conversation and calling it kept.
    headers = await account(api)

    response = await api.post(f"/api/guide/sessions/{GONE}/save", headers=headers)

    assert response.status_code == 404
    assert await count(db_schema, "guide_sessions") == 0


@pytest.mark.asyncio
async def test_keeping_one_that_was_deleted_does_not_resurrect_it(api, db_schema):
    headers = await account(api)
    session_id = await unkept(api, "Thrown away")
    saved = (
        await api.post(f"/api/guide/sessions/{session_id}/save", headers=headers)
    ).json()["id"]
    await api.delete(f"/api/guide/sessions/{saved}", headers=headers)

    response = await api.post(f"/api/guide/sessions/{session_id}/save", headers=headers)

    assert response.status_code == 404
    assert await count(db_schema, "guide_sessions") == 0


# --- naming -----------------------------------------------------------


@pytest.mark.asyncio
async def test_a_conversation_starts_unnamed(api, db_schema):
    headers = await account(api)
    await kept(api, headers, "How do I send money?")

    assert (await listed(api, headers))[0]["title"] is None


@pytest.mark.asyncio
async def test_a_conversation_can_be_renamed(api, db_schema):
    headers = await account(api)
    session_id = await kept(api, headers, "How do I send money?")

    response = await api.patch(
        f"/api/guide/sessions/{session_id}",
        json={"title": "Bank transfer"},
        headers=headers,
    )

    assert response.status_code == 200
    assert response.json()["title"] == "Bank transfer"


@pytest.mark.asyncio
async def test_renaming_does_not_lose_the_opening_question(api, db_schema):
    headers = await account(api)
    session_id = await kept(api, headers, "How do I send money?")

    await api.patch(
        f"/api/guide/sessions/{session_id}",
        json={"title": "Bank transfer"},
        headers=headers,
    )

    row = (await listed(api, headers))[0]
    assert row["title"] == "Bank transfer"
    assert row["opening"] == "How do I send money?"


@pytest.mark.asyncio
async def test_an_empty_name_goes_back_to_being_unnamed(api, db_schema):
    headers = await account(api)
    session_id = await kept(api, headers, "How do I send money?")
    await api.patch(
        f"/api/guide/sessions/{session_id}", json={"title": "Temp"}, headers=headers
    )

    response = await api.patch(
        f"/api/guide/sessions/{session_id}", json={"title": "   "}, headers=headers
    )

    assert response.json()["title"] is None


@pytest.mark.asyncio
async def test_one_person_cannot_rename_anothers_conversation(api, db_schema):
    mine = await account(api)
    theirs = await account(api, email="mallory@example.com", name="Mallory")
    session_id = await kept(api, theirs, "Not yours")

    response = await api.patch(
        f"/api/guide/sessions/{session_id}", json={"title": "Mine now"}, headers=mine
    )

    assert response.status_code == 404


# --- deleting ---------------------------------------------------------


@pytest.mark.asyncio
async def test_a_conversation_can_be_deleted(api, db_schema):
    headers = await account(api)
    session_id = await kept(api, headers, "Forget this")

    response = await api.delete(f"/api/guide/sessions/{session_id}", headers=headers)

    assert response.status_code == 204
    assert await listed(api, headers) == []


@pytest.mark.asyncio
async def test_deleting_takes_the_messages_with_it(api, db_schema):
    headers = await account(api)
    session_id = await kept(api, headers, "Forget this", "And this")

    await api.delete(f"/api/guide/sessions/{session_id}", headers=headers)

    assert await count(db_schema, "guide_messages") == 0


@pytest.mark.asyncio
async def test_one_person_cannot_delete_anothers_conversation(api, db_schema):
    mine = await account(api)
    theirs = await account(api, email="mallory@example.com", name="Mallory")
    session_id = await kept(api, theirs, "Not yours")

    response = await api.delete(f"/api/guide/sessions/{session_id}", headers=mine)

    assert response.status_code == 404
    assert await count(db_schema, "guide_sessions") == 1


@pytest.mark.asyncio
async def test_deleting_an_unknown_conversation_is_not_found(api, db_schema):
    headers = await account(api)

    response = await api.delete(f"/api/guide/sessions/{GONE}", headers=headers)

    assert response.status_code == 404
