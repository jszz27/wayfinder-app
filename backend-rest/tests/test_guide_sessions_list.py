"""Reading back conversations that were saved but unreachable.

`GET /api/guide/sessions` is not in Plan.md section 4 as written; it was
added in Sprint 3. Before it, a signed-in user's conversations were stored
and could never be opened again -- reading one needs an id, and nothing
handed out ids once the tab had closed.
"""

import pytest

PASSWORD = "correct horse battery"


async def account(api, email="ann@example.com", name="Ann"):
    response = await api.post(
        "/api/auth/signup",
        json={"email": email, "password": PASSWORD, "display_name": name},
    )
    assert response.status_code == 201
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


async def converse(api, headers, *questions):
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
    response = await api.get("/api/guide/sessions", headers=headers)
    assert response.status_code == 200
    return response.json()


# --- what comes back --------------------------------------------------


@pytest.mark.asyncio
async def test_a_conversation_can_be_found_again(api, db_schema):
    headers = await account(api)
    session_id = await converse(api, headers, "How do I send money?")

    assert [row["id"] for row in await listed(api, headers)] == [session_id]


@pytest.mark.asyncio
async def test_the_opening_question_is_what_names_it(api, db_schema):
    # Nobody would name a conversation, so the thing they asked has to be
    # what makes it recognisable a week later.
    headers = await account(api)
    await converse(api, headers, "How do I send money?", "And after that?")

    assert (await listed(api, headers))[0]["opening"] == "How do I send money?"


@pytest.mark.asyncio
async def test_it_counts_questions_rather_than_messages(api, db_schema):
    # Two questions and two answers is two exchanges, not four messages.
    headers = await account(api)
    await converse(api, headers, "First", "Second")

    assert (await listed(api, headers))[0]["exchanges"] == 2


@pytest.mark.asyncio
async def test_a_conversation_with_no_questions_yet_has_no_opening(api, db_schema):
    headers = await account(api)
    await converse(api, headers)

    row = (await listed(api, headers))[0]
    assert row["opening"] is None
    assert row["exchanges"] == 0


@pytest.mark.asyncio
async def test_the_newest_conversation_is_first(api, db_schema):
    headers = await account(api)
    await converse(api, headers, "Older")
    newer = await converse(api, headers, "Newer")

    assert (await listed(api, headers))[0]["id"] == newer


@pytest.mark.asyncio
async def test_completing_shows_in_the_list(api, db_schema):
    headers = await account(api)
    session_id = await converse(api, headers, "Done now")
    await api.patch(f"/api/guide/sessions/{session_id}/complete", headers=headers)

    assert (await listed(api, headers))[0]["completed_at"] is not None


@pytest.mark.asyncio
async def test_a_listed_conversation_opens(api, db_schema):
    # The list exists to make the read endpoint reachable, so the two have
    # to actually join up.
    headers = await account(api)
    await converse(api, headers, "How do I send money?")

    found = (await listed(api, headers))[0]
    body = (await api.get(f"/api/guide/sessions/{found['id']}", headers=headers)).json()

    assert [m["content"] for m in body["messages"]][0] == "How do I send money?"


# --- whose conversations they are -------------------------------------


@pytest.mark.asyncio
async def test_only_my_own_conversations_are_listed(api, db_schema):
    mine = await account(api)
    theirs = await account(api, email="mallory@example.com", name="Mallory")
    await converse(api, theirs, "Not yours")
    await converse(api, mine, "Mine")

    rows = await listed(api, mine)
    assert [row["opening"] for row in rows] == ["Mine"]


@pytest.mark.asyncio
async def test_listing_needs_an_account(api, db_schema):
    response = await api.get("/api/guide/sessions")

    assert response.status_code == 401


@pytest.mark.asyncio
async def test_an_anonymous_conversation_never_appears(api, db_schema):
    # It is held in this process and belongs to nobody, so there is
    # nothing for a list to show.
    headers = await account(api)
    await converse(api, None, "Signed out question")

    assert await listed(api, headers) == []


@pytest.mark.asyncio
async def test_a_new_account_has_nothing_to_show(api, db_schema):
    headers = await account(api)

    assert await listed(api, headers) == []
