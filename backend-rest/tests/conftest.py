import os
from pathlib import Path

import pytest
import pytest_asyncio
from dotenv import load_dotenv
from fastapi.testclient import TestClient

# Every test in this suite runs against the credential-free model. Set
# before app.config is imported, because that import is where .env is read,
# and a real environment variable takes precedence over the file --
# otherwise a developer with WAYFINDER_LLM=gemini in .env would silently
# point the whole suite at a paid API.
os.environ.setdefault("WAYFINDER_LLM", "mock")

# The same reasoning for the database, but the stakes are higher: pointing
# the suite at the development database would let it drop real tables. The
# URL is rewritten to a dedicated test database before the app can read it,
# and then checked, so a misconfiguration cannot quietly run against data
# that matters.
load_dotenv(Path(__file__).resolve().parents[2] / ".env", override=False)
_configured = os.environ.get("DATABASE_URL", "")
if _configured:
    os.environ["DATABASE_URL"] = _configured.rsplit("/", 1)[0] + "/wayfinder_test"
assert os.environ.get("DATABASE_URL", "").endswith("/wayfinder_test"), (
    "tests must run against wayfinder_test; refusing to touch another database"
)

from app.config import get_settings  # noqa: E402
from app.main import app  # noqa: E402
from app.routers.guide_sessions import (  # noqa: E402
    reset_sessions as reset_guide_sessions,
)


@pytest.fixture(autouse=True)
def _mock_guide_model(monkeypatch):
    monkeypatch.setenv("WAYFINDER_LLM", "mock")
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


@pytest.fixture
def client() -> TestClient:
    # Caption sessions live in PostgreSQL now; only guide mode still has an
    # in-memory store to clear between tests.
    reset_guide_sessions()
    return TestClient(app)


@pytest_asyncio.fixture
async def db_schema():
    """A schema built fresh for one test, then thrown away.

    The engine cache is cleared around it because pytest-asyncio gives each
    test its own event loop, and an asyncpg pool built in a previous loop
    cannot be used from the next one.
    """
    from app.db import models  # noqa: F401  (registers the tables)
    from app.db.base import Base
    from app.db.session import get_engine, get_sessionmaker

    get_engine.cache_clear()
    get_sessionmaker.cache_clear()
    engine = get_engine()
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.drop_all)
        await connection.run_sync(Base.metadata.create_all)
    try:
        yield engine
    finally:
        await engine.dispose()
        get_engine.cache_clear()
        get_sessionmaker.cache_clear()


@pytest_asyncio.fixture
async def api(db_schema):
    """An HTTP client for the async, database-backed routes."""
    from httpx import ASGITransport, AsyncClient

    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://testserver"
    ) as client:
        yield client
