"""The migration and the models must describe the same schema.

Every other database test builds its tables from the models, so a
migration that has drifted from them would pass the whole suite and only
fail in production, where the migration is the thing that actually runs.
"""

import asyncio
from pathlib import Path

import pytest
import sqlalchemy as sa
from alembic import command
from alembic.autogenerate import compare_metadata
from alembic.config import Config
from alembic.migration import MigrationContext

from app.db.base import Base

ALEMBIC_INI = Path(__file__).resolve().parents[1] / "alembic.ini"


def _upgrade_to_head() -> None:
    config = Config(str(ALEMBIC_INI))
    config.set_main_option("script_location", str(ALEMBIC_INI.parent / "alembic"))
    command.upgrade(config, "head")


@pytest.mark.asyncio
async def test_the_migration_builds_exactly_what_the_models_describe(db_schema):
    async with db_schema.begin() as connection:
        await connection.run_sync(Base.metadata.drop_all)
        # alembic_version is not a model, so drop_all leaves it behind.
        # Left in place, Alembic reads itself as already at head, upgrades
        # nothing, and this test then reports every table as missing --
        # which is exactly what it did before this line existed.
        await connection.execute(sa.text("DROP TABLE IF EXISTS alembic_version"))

    # Alembic's async template calls asyncio.run itself, which cannot
    # happen inside a running loop, so it goes to a worker thread.
    await asyncio.to_thread(_upgrade_to_head)

    async with db_schema.connect() as connection:
        differences = await connection.run_sync(
            lambda sync_connection: compare_metadata(
                MigrationContext.configure(sync_connection), Base.metadata
            )
        )

    # alembic_version is Alembic's own bookkeeping and is not in the models.
    differences = [
        d for d in differences if "alembic_version" not in str(d)
    ]
    assert differences == [], f"migration has drifted from the models: {differences}"
