"""Naming a saved session, editing its text, and keeping one by hand.

The property worth protecting: `caption_lines` is what the recogniser
produced and is never rewritten. An edit lands beside it, so a correction
can be undone and it stays clear which words came from the machine and
which from the person.
"""

import uuid

import pytest
import sqlalchemy as sa

PASSWORD = "correct horse battery"


async def account(api, email="ann@example.com", name="Ann"):
    response = await api.post(
        "/api/auth/signup",
        json={"email": email, "password": PASSWORD, "display_name": name},
    )
    assert response.status_code == 201
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


async def start(api, headers):
    response = await api.post(
        "/api/caption-sessions", json={"audio_source": "mic"}, headers=headers
    )
    return response.json()["session_id"]


async def add_lines(engine, session_id, *texts):
    async with engine.begin() as connection:
        for seq, text in enumerate(texts):
            await connection.execute(
                sa.text(
                    "insert into caption_lines (id, session_id, seq, text) "
                    "values (:id, :session_id, :seq, :text)"
                ),
                {
                    "id": str(uuid.uuid4()),
                    "session_id": session_id,
                    "seq": seq,
                    "text": text,
                },
            )


async def detail(api, session_id, headers):
    response = await api.get(f"/api/caption-sessions/{session_id}", headers=headers)
    return response.json()


# --- naming -----------------------------------------------------------


@pytest.mark.asyncio
async def test_a_session_starts_unnamed(api, db_schema):
    headers = await account(api)
    session_id = await start(api, headers)

    # Null rather than a placeholder, so the interface can show the date
    # instead of a name nobody chose.
    assert (await detail(api, session_id, headers))["title"] is None


@pytest.mark.asyncio
async def test_a_session_can_be_renamed(api, db_schema):
    headers = await account(api)
    session_id = await start(api, headers)

    response = await api.patch(
        f"/api/caption-sessions/{session_id}",
        json={"title": "Doctor's appointment"},
        headers=headers,
    )

    assert response.status_code == 200
    assert response.json()["title"] == "Doctor's appointment"


@pytest.mark.asyncio
async def test_an_empty_name_goes_back_to_being_unnamed(api, db_schema):
    headers = await account(api)
    session_id = await start(api, headers)
    await api.patch(
        f"/api/caption-sessions/{session_id}", json={"title": "Temp"}, headers=headers
    )

    response = await api.patch(
        f"/api/caption-sessions/{session_id}", json={"title": "   "}, headers=headers
    )

    assert response.json()["title"] is None


# --- editing ----------------------------------------------------------


@pytest.mark.asyncio
async def test_before_editing_the_text_is_the_recognised_lines(api, db_schema):
    headers = await account(api)
    session_id = await start(api, headers)
    await add_lines(db_schema, session_id, "Hello there.", "How are you?")

    body = await detail(api, session_id, headers)

    assert body["text"] == "Hello there.\nHow are you?"
    assert body["edited"] is False


@pytest.mark.asyncio
async def test_an_edit_replaces_what_is_shown(api, db_schema):
    headers = await account(api)
    session_id = await start(api, headers)
    await add_lines(db_schema, session_id, "Hello there.", "How are you?")

    await api.patch(
        f"/api/caption-sessions/{session_id}",
        json={"text": "Hello there.\nHow are you today?"},
        headers=headers,
    )
    body = await detail(api, session_id, headers)

    assert body["text"] == "Hello there.\nHow are you today?"
    assert body["edited"] is True


@pytest.mark.asyncio
async def test_editing_never_rewrites_what_was_recognised(api, db_schema):
    # The whole reason the edit lives in a column of its own.
    headers = await account(api)
    session_id = await start(api, headers)
    await add_lines(db_schema, session_id, "Hello there.", "How are you?")

    await api.patch(
        f"/api/caption-sessions/{session_id}",
        json={"text": "Something else entirely"},
        headers=headers,
    )

    body = await detail(api, session_id, headers)
    assert [line["text"] for line in body["lines"]] == [
        "Hello there.",
        "How are you?",
    ]


@pytest.mark.asyncio
async def test_renaming_does_not_discard_an_edit(api, db_schema):
    headers = await account(api)
    session_id = await start(api, headers)
    await api.patch(
        f"/api/caption-sessions/{session_id}",
        json={"text": "Kept text"},
        headers=headers,
    )

    await api.patch(
        f"/api/caption-sessions/{session_id}", json={"title": "A name"}, headers=headers
    )

    body = await detail(api, session_id, headers)
    assert body["title"] == "A name"
    assert body["text"] == "Kept text"


@pytest.mark.asyncio
async def test_editing_does_not_discard_a_name(api, db_schema):
    headers = await account(api)
    session_id = await start(api, headers)
    await api.patch(
        f"/api/caption-sessions/{session_id}", json={"title": "A name"}, headers=headers
    )

    await api.patch(
        f"/api/caption-sessions/{session_id}",
        json={"text": "Kept text"},
        headers=headers,
    )

    assert (await detail(api, session_id, headers))["title"] == "A name"


@pytest.mark.asyncio
async def test_an_empty_update_is_refused(api, db_schema):
    headers = await account(api)
    session_id = await start(api, headers)

    response = await api.patch(
        f"/api/caption-sessions/{session_id}", json={}, headers=headers
    )

    assert response.status_code == 422


@pytest.mark.asyncio
async def test_one_person_cannot_rename_anothers_session(api, db_schema):
    mine = await account(api)
    theirs = await account(api, email="mallory@example.com", name="Mallory")
    session_id = await start(api, theirs)

    response = await api.patch(
        f"/api/caption-sessions/{session_id}", json={"title": "Mine now"}, headers=mine
    )

    assert response.status_code == 404


# --- keeping one by hand ----------------------------------------------


@pytest.mark.asyncio
async def test_a_transcript_can_be_saved_on_request(api, db_schema):
    # Auto-save off: nothing was written while recording, so the text
    # arrives from the browser when the user asks to keep it.
    headers = await account(api)

    response = await api.post(
        "/api/caption-sessions/saved",
        json={
            "audio_source": "mic",
            "text": "Hello there.\nHow are you?",
            "title": "Kept by hand",
        },
        headers=headers,
    )

    assert response.status_code == 201
    body = response.json()
    assert body["title"] == "Kept by hand"
    assert body["edited"] is True
    assert body["ended_at"] is not None


@pytest.mark.asyncio
async def test_a_hand_saved_transcript_reads_back(api, db_schema):
    headers = await account(api)
    created = await api.post(
        "/api/caption-sessions/saved",
        json={"audio_source": "tab_audio", "text": "The whole transcript"},
        headers=headers,
    )

    body = await detail(api, created.json()["id"], headers)

    assert body["text"] == "The whole transcript"
    # It was never recognised line by line, so there are no lines.
    assert body["lines"] == []


@pytest.mark.asyncio
async def test_saving_by_hand_needs_an_account(api, db_schema):
    response = await api.post(
        "/api/caption-sessions/saved",
        json={"audio_source": "mic", "text": "Anyone's words"},
    )

    assert response.status_code == 401


@pytest.mark.asyncio
async def test_an_empty_transcript_is_not_worth_keeping(api, db_schema):
    headers = await account(api)

    response = await api.post(
        "/api/caption-sessions/saved",
        json={"audio_source": "mic", "text": ""},
        headers=headers,
    )

    assert response.status_code == 422


# --- the auto-save preference -----------------------------------------


@pytest.mark.asyncio
async def test_auto_save_is_on_to_begin_with(api, db_schema):
    headers = await account(api)

    body = (await api.get("/api/users/me", headers=headers)).json()

    assert body["auto_save"] is True


@pytest.mark.asyncio
async def test_auto_save_can_be_turned_off_and_follows_the_account(api, db_schema):
    headers = await account(api)

    await api.patch("/api/users/me", json={"auto_save": False}, headers=headers)

    body = (await api.get("/api/users/me", headers=headers)).json()
    assert body["auto_save"] is False
