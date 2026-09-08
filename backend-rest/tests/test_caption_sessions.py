"""Plan.md section 4: starting a caption session, and reading the log back.

The behaviour worth protecting here is the decision that captioning works
without an account and keeps nothing when it does. A signed-out session
must leave no row, because a row is what backend-ws looks for before it
writes anyone's speech down.
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


async def start(api, headers=None, audio_source="mic"):
    return await api.post(
        "/api/caption-sessions",
        json={"audio_source": audio_source},
        headers=headers or {},
    )


async def add_lines(engine, session_id, *texts):
    """Stand in for backend-ws, which is what writes the confirmed lines."""
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


async def count(engine, table):
    async with engine.connect() as connection:
        return await connection.scalar(sa.text(f"select count(*) from {table}"))


# --- starting a session -----------------------------------------------


@pytest.mark.asyncio
@pytest.mark.parametrize("audio_source", ["mic", "tab_audio"])
async def test_a_signed_in_session_is_saved(api, db_schema, audio_source):
    headers = await account(api)

    response = await start(api, headers, audio_source)

    assert response.status_code == 201
    body = response.json()
    uuid.UUID(body["session_id"])
    assert body["saved"] is True
    assert await count(db_schema, "caption_sessions") == 1


@pytest.mark.asyncio
async def test_a_signed_out_session_writes_no_row(api, db_schema):
    # This is the whole privacy position: with no row, backend-ws has
    # nowhere to write the transcript, so it does not write one.
    response = await start(api)

    assert response.status_code == 201
    uuid.UUID(response.json()["session_id"])
    assert response.json()["saved"] is False
    assert await count(db_schema, "caption_sessions") == 0


@pytest.mark.asyncio
async def test_each_session_gets_its_own_id(api, db_schema):
    headers = await account(api)

    first = (await start(api, headers)).json()["session_id"]
    second = (await start(api, headers)).json()["session_id"]

    assert first != second


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "payload", [{"audio_source": "speaker"}, {"audio_source": None}, {}]
)
async def test_an_unknown_audio_source_is_refused(api, db_schema, payload):
    response = await api.post("/api/caption-sessions", json=payload)

    assert response.status_code == 422


# --- reading the log back ---------------------------------------------


@pytest.mark.asyncio
async def test_listing_sessions_requires_signing_in(api, db_schema):
    assert (await api.get("/api/caption-sessions")).status_code == 401


@pytest.mark.asyncio
async def test_the_log_comes_back_in_order(api, db_schema):
    headers = await account(api)
    session_id = (await start(api, headers)).json()["session_id"]
    await add_lines(db_schema, session_id, "Hello there.", "How are you?", "I am well.")

    response = await api.get(f"/api/caption-sessions/{session_id}", headers=headers)

    assert response.status_code == 200
    body = response.json()
    assert [line["seq"] for line in body["lines"]] == [0, 1, 2]
    assert body["lines"][1]["text"] == "How are you?"
    assert body["audio_source"] == "mic"
    assert body["ended_at"] is None


@pytest.mark.asyncio
async def test_my_list_holds_only_my_sessions(api, db_schema):
    mine = await account(api)
    theirs = await account(api, email="mallory@example.com", name="Mallory")
    await start(api, mine)
    await start(api, mine)
    await start(api, theirs)

    response = await api.get("/api/caption-sessions", headers=mine)

    assert response.status_code == 200
    assert len(response.json()) == 2


@pytest.mark.asyncio
async def test_another_persons_session_is_simply_not_found(api, db_schema):
    # Not 403: answering "forbidden" would confirm the id exists.
    mine = await account(api)
    theirs = await account(api, email="mallory@example.com", name="Mallory")
    session_id = (await start(api, theirs)).json()["session_id"]

    response = await api.get(f"/api/caption-sessions/{session_id}", headers=mine)

    assert response.status_code == 404


@pytest.mark.asyncio
async def test_an_unknown_session_is_not_found(api, db_schema):
    headers = await account(api)

    response = await api.get(f"/api/caption-sessions/{uuid.uuid4()}", headers=headers)

    assert response.status_code == 404


# --- deleting ---------------------------------------------------------


@pytest.mark.asyncio
async def test_deleting_a_session_takes_its_lines_with_it(api, db_schema):
    headers = await account(api)
    session_id = (await start(api, headers)).json()["session_id"]
    await add_lines(db_schema, session_id, "Hello there.", "How are you?")

    response = await api.delete(f"/api/caption-sessions/{session_id}", headers=headers)

    assert response.status_code == 204
    assert await count(db_schema, "caption_sessions") == 0
    assert await count(db_schema, "caption_lines") == 0


@pytest.mark.asyncio
async def test_one_person_cannot_delete_anothers_session(api, db_schema):
    mine = await account(api)
    theirs = await account(api, email="mallory@example.com", name="Mallory")
    session_id = (await start(api, theirs)).json()["session_id"]

    response = await api.delete(f"/api/caption-sessions/{session_id}", headers=mine)

    assert response.status_code == 404
    assert await count(db_schema, "caption_sessions") == 1


@pytest.mark.asyncio
async def test_deleting_needs_signing_in(api, db_schema):
    headers = await account(api)
    session_id = (await start(api, headers)).json()["session_id"]

    assert (await api.delete(f"/api/caption-sessions/{session_id}")).status_code == 401
