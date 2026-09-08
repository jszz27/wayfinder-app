"""Plan.md section 4: signup, login, refresh and logout.

These run against a real PostgreSQL schema rather than a stand-in, because
most of what is worth checking is enforced by the database: the unique
email, the cascade, and the refresh token rows that make logout mean
something.
"""

import pytest
import sqlalchemy as sa

from app.routers.auth import MIN_PASSWORD_LENGTH

EMAIL = "ann@example.com"
PASSWORD = "correct horse battery"


async def signup(api, email=EMAIL, password=PASSWORD, name="Ann"):
    return await api.post(
        "/api/auth/signup",
        json={"email": email, "password": password, "display_name": name},
    )


async def login(api, email=EMAIL, password=PASSWORD):
    return await api.post(
        "/api/auth/login", json={"email": email, "password": password}
    )


async def logout(api, tokens, refresh_token=None, access_token=None):
    return await api.request(
        "DELETE",
        "/api/auth/logout",
        json={"refresh_token": refresh_token or tokens["refresh_token"]},
        headers={"Authorization": f"Bearer {access_token or tokens['access_token']}"},
    )


async def refresh(api, token):
    return await api.post("/api/auth/refresh", json={"refresh_token": token})


# --- signing up -------------------------------------------------------


@pytest.mark.asyncio
async def test_signup_returns_a_usable_token_pair(api):
    response = await signup(api)

    assert response.status_code == 201
    body = response.json()
    assert body["access_token"] and body["refresh_token"]
    assert body["token_type"] == "bearer"
    assert body["expires_in"] == 900


@pytest.mark.asyncio
async def test_an_email_can_only_be_registered_once(api):
    await signup(api)

    assert (await signup(api)).status_code == 409


@pytest.mark.asyncio
async def test_the_same_email_in_another_case_is_the_same_account(api):
    # Otherwise Ann@example.com walks around the unique index and ends up
    # with a second account she cannot tell apart from the first.
    await signup(api)

    assert (await signup(api, email="Ann@Example.COM")).status_code == 409


@pytest.mark.asyncio
async def test_a_short_password_is_refused(api):
    response = await signup(api, password="x" * (MIN_PASSWORD_LENGTH - 1))

    assert response.status_code == 422


@pytest.mark.asyncio
async def test_the_password_is_never_stored_in_the_clear(api, db_schema):
    await signup(api)

    async with db_schema.connect() as connection:
        stored = await connection.scalar(sa.text("select password_hash from users"))

    assert PASSWORD not in stored
    assert stored.startswith("$argon2id$")


# --- signing in -------------------------------------------------------


@pytest.mark.asyncio
async def test_login_accepts_the_right_password(api):
    await signup(api)

    response = await login(api)

    assert response.status_code == 200
    assert response.json()["access_token"]


@pytest.mark.asyncio
async def test_login_is_case_insensitive_on_email(api):
    await signup(api)

    assert (await login(api, email="ANN@EXAMPLE.COM")).status_code == 200


@pytest.mark.asyncio
async def test_the_wrong_password_is_rejected(api):
    await signup(api)

    assert (await login(api, password="not the password")).status_code == 401


@pytest.mark.asyncio
async def test_an_unknown_email_answers_exactly_like_a_wrong_password(api):
    # Any difference here turns the endpoint into a way of finding out
    # which email addresses have accounts.
    await signup(api)

    wrong = await login(api, password="not the password")
    unknown = await login(api, email="nobody@example.com")

    assert wrong.status_code == unknown.status_code == 401
    assert wrong.json() == unknown.json()


# --- refreshing -------------------------------------------------------


@pytest.mark.asyncio
async def test_refresh_returns_a_new_pair(api):
    tokens = (await signup(api)).json()

    response = await refresh(api, tokens["refresh_token"])

    assert response.status_code == 200
    assert response.json()["refresh_token"] != tokens["refresh_token"]


@pytest.mark.asyncio
async def test_a_refresh_token_cannot_be_used_twice(api):
    # Rotation is what makes a stolen token good for one use at most, and
    # what makes the theft visible as a rejected refresh.
    tokens = (await signup(api)).json()
    await refresh(api, tokens["refresh_token"])

    assert (await refresh(api, tokens["refresh_token"])).status_code == 401


@pytest.mark.asyncio
async def test_nonsense_is_not_a_refresh_token(api):
    await signup(api)

    assert (await refresh(api, "not-a-real-token")).status_code == 401


# --- logging out ------------------------------------------------------


@pytest.mark.asyncio
async def test_logout_needs_an_access_token(api):
    tokens = (await signup(api)).json()

    response = await api.request(
        "DELETE", "/api/auth/logout", json={"refresh_token": tokens["refresh_token"]}
    )

    assert response.status_code == 401


@pytest.mark.asyncio
async def test_logout_kills_that_refresh_token(api):
    tokens = (await signup(api)).json()

    out = await logout(api, tokens)

    assert out.status_code == 204
    assert (await refresh(api, tokens["refresh_token"])).status_code == 401


@pytest.mark.asyncio
async def test_logging_out_one_session_leaves_the_others_alone(api):
    # Signing out on a phone should not sign you out on a laptop.
    first = (await signup(api)).json()
    second = (await login(api)).json()

    await logout(api, second)

    assert (await refresh(api, first["refresh_token"])).status_code == 200


@pytest.mark.asyncio
async def test_one_account_cannot_revoke_another_accounts_session(api):
    victim = (await signup(api)).json()
    attacker = (await signup(api, email="mallory@example.com", name="Mallory")).json()

    response = await logout(
        api, attacker, refresh_token=victim["refresh_token"]
    )

    # Answered as though it worked, because saying otherwise would confirm
    # the token exists -- but the victim's session is untouched.
    assert response.status_code == 204
    assert (await refresh(api, victim["refresh_token"])).status_code == 200


@pytest.mark.asyncio
async def test_logging_out_an_unknown_token_is_quietly_fine(api):
    tokens = (await signup(api)).json()

    response = await logout(api, tokens, refresh_token="not-a-real-token")

    assert response.status_code == 204


# --- the access token -------------------------------------------------


@pytest.mark.asyncio
async def test_a_refresh_token_is_not_accepted_as_an_access_token(api):
    tokens = (await signup(api)).json()

    response = await logout(api, tokens, access_token=tokens["refresh_token"])

    assert response.status_code == 401


@pytest.mark.asyncio
async def test_a_tampered_access_token_is_rejected(api):
    tokens = (await signup(api)).json()
    access = tokens["access_token"]
    tampered = access[:-2] + ("aa" if access[-2:] != "aa" else "bb")

    response = await logout(api, tokens, access_token=tampered)

    assert response.status_code == 401


@pytest.mark.asyncio
async def test_deleting_a_user_takes_their_tokens_with_them(api, db_schema):
    await signup(api)
    await login(api)

    async with db_schema.begin() as connection:
        before = await connection.scalar(sa.text("select count(*) from refresh_tokens"))
        await connection.execute(sa.text("delete from users"))
        after = await connection.scalar(sa.text("select count(*) from refresh_tokens"))

    assert before == 2
    assert after == 0
