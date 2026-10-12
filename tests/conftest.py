import os
from pathlib import Path

import pytest
from sqlalchemy import Engine, text

from pulse.config import Settings
from pulse.db import engine_for
from pulse.objects import LocalObjectStore


@pytest.fixture
def engine() -> Engine:
    url = os.environ.get("PULSE_TEST_DATABASE_URL")
    if not url:
        pytest.fail("Set PULSE_TEST_DATABASE_URL to an isolated migrated PostgreSQL database")
    db = engine_for(url)
    with db.begin() as connection:
        tables = (
            connection.execute(
                text(
                    "SELECT tablename FROM pg_tables WHERE schemaname='public' "
                    "AND tablename != 'alembic_version'"
                )
            )
            .scalars()
            .all()
        )
        if not tables:
            pytest.fail("Apply Alembic migrations before integration tests")
        quoted = ", ".join('"' + table.replace('"', '""') + '"' for table in tables)
        connection.execute(text(f"TRUNCATE {quoted} RESTART IDENTITY CASCADE"))
    yield db
    db.dispose()


@pytest.fixture
def store(tmp_path: Path) -> LocalObjectStore:
    return LocalObjectStore(tmp_path / "objects")


@pytest.fixture
def settings(engine: Engine, store: LocalObjectStore) -> Settings:
    return Settings(
        database_url=engine.url.render_as_string(hide_password=False),
        object_root=store.root,
        api_token="test-reader",
        audit_token="test-auditor",
    )
