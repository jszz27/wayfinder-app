"""Plan.md section 4: profile and accessibility settings.

The interesting case is the partial update. Sending `caption_language:
null` means "go back to detecting" and leaving the field out means "do not
touch it" -- two different intentions that a naive handler collapses into
one, quietly resetting a setting the user never mentioned.
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


async def settings(api, headers, **changes):
    return await api.patch("/api/users/me", json=changes, headers=headers)


# --- reading ----------------------------------------------------------


@pytest.mark.asyncio
async def test_the_profile_needs_signing_in(api, db_schema):
    assert (await api.get("/api/users/me")).status_code == 401


@pytest.mark.asyncio
async def test_a_new_account_starts_with_sensible_defaults(api, db_schema):
    headers = await account(api)

    body = (await api.get("/api/users/me", headers=headers)).json()

    assert body["email"] == "ann@example.com"
    assert body["display_name"] == "Ann"
    assert body["font_size"] == 20
    # Detect the language rather than pin it, matching what the caption
    # pipeline does when nothing is configured.
    assert body["caption_language"] is None


@pytest.mark.asyncio
async def test_the_password_hash_is_not_part_of_the_profile(api, db_schema):
    headers = await account(api)

    body = (await api.get("/api/users/me", headers=headers)).json()

    assert "password_hash" not in body
    assert "password" not in body


# --- updating ---------------------------------------------------------


@pytest.mark.asyncio
async def test_text_size_can_be_changed_and_sticks(api, db_schema):
    headers = await account(api)

    updated = await settings(api, headers, font_size=34)

    assert updated.status_code == 200
    assert updated.json()["font_size"] == 34
    assert (await api.get("/api/users/me", headers=headers)).json()["font_size"] == 34


@pytest.mark.asyncio
async def test_a_language_can_be_pinned(api, db_schema):
    headers = await account(api)

    updated = await settings(api, headers, caption_language="ko-KR")

    assert updated.status_code == 200
    assert updated.json()["caption_language"] == "ko-KR"


@pytest.mark.asyncio
async def test_sending_null_goes_back_to_detecting(api, db_schema):
    headers = await account(api)
    await settings(api, headers, caption_language="ko-KR")

    updated = await settings(api, headers, caption_language=None)

    assert updated.json()["caption_language"] is None


@pytest.mark.asyncio
async def test_an_empty_string_means_the_same_as_null(api, db_schema):
    # Which is what a form sends when no language is chosen.
    headers = await account(api)
    await settings(api, headers, caption_language="ko-KR")

    updated = await settings(api, headers, caption_language="")

    assert updated.json()["caption_language"] is None


@pytest.mark.asyncio
async def test_a_field_that_was_not_sent_is_left_alone(api, db_schema):
    # The trap: treating "absent" as "null" would clear the pinned language
    # every time somebody nudged the text size.
    headers = await account(api)
    await settings(api, headers, caption_language="ja-JP", font_size=26)

    updated = await settings(api, headers, font_size=16)

    assert updated.json()["font_size"] == 16
    assert updated.json()["caption_language"] == "ja-JP"


@pytest.mark.asyncio
async def test_settings_belong_to_one_account(api, db_schema):
    mine = await account(api)
    theirs = await account(api, email="mallory@example.com", name="Mallory")
    await settings(api, mine, font_size=34)

    body = (await api.get("/api/users/me", headers=theirs)).json()

    assert body["font_size"] == 20


# --- refusing nonsense ------------------------------------------------


@pytest.mark.asyncio
async def test_updating_needs_signing_in(api, db_schema):
    assert (await api.patch("/api/users/me", json={"font_size": 26})).status_code == 401


@pytest.mark.asyncio
@pytest.mark.parametrize("size", [0, 7, 97, 5000, -20])
async def test_an_impossible_text_size_is_refused(api, db_schema, size):
    # The database would refuse these too; catching them here makes it a
    # clear 422 rather than an integrity error surfacing as a 500.
    headers = await account(api)

    assert (await settings(api, headers, font_size=size)).status_code == 422


@pytest.mark.asyncio
@pytest.mark.parametrize("tag", ["not a tag", "!!", "e", "x" * 40])
async def test_something_that_is_not_a_language_tag_is_refused(api, db_schema, tag):
    headers = await account(api)

    assert (await settings(api, headers, caption_language=tag)).status_code == 422


@pytest.mark.asyncio
async def test_an_empty_update_is_refused(api, db_schema):
    headers = await account(api)

    response = await api.patch("/api/users/me", json={}, headers=headers)

    assert response.status_code == 422


@pytest.mark.asyncio
async def test_text_size_cannot_be_cleared(api, db_schema):
    # There is no "no text size"; the column is not nullable.
    headers = await account(api)

    assert (await settings(api, headers, font_size=None)).status_code == 422
