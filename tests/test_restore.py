"""Logical PostgreSQL restore with matched objects and explicit missing-object recovery.

This drill verifies pg_dump/pg_restore, pending delivery, and honest reconciliation.
It does not establish WAL/PITR correctness, production RPO/RTO, or crash durability
of a backup system. A missing client or database-creation privilege is BLOCKED.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import subprocess
from datetime import datetime
from pathlib import Path
from typing import Any
from uuid import uuid4

import psycopg
import pytest
from fastapi.testclient import TestClient
from psycopg import sql
from sqlalchemy import Engine, select, text

from pulse.api import create_app
from pulse.config import Settings
from pulse.db import engine_for, transaction
from pulse.models import (
    Artifact,
    Availability,
    Consumption,
    HealthInterval,
    Observation,
    Outbox,
    Receipt,
    Revision,
    Snapshot,
    SnapshotInvalidation,
)
from pulse.objects import LocalObjectStore
from pulse.reconcile import reconcile
from pulse.snapshots import seal_snapshot
from pulse.worker import run_parser_once
from tests.helpers import approve, ingest, xml

pytestmark = [pytest.mark.postgres, pytest.mark.restore]


def _postgres_clients(engine: Engine) -> tuple[Path, Path]:
    with engine.connect() as connection:
        server_major = int(connection.scalar(text("SHOW server_version_num"))) // 10000
    directories = [
        Path(found).parent
        for name in ("pg_dump", "pg_restore")
        if (found := shutil.which(name)) is not None
    ]
    directories += sorted(Path("/usr/lib/postgresql").glob("*/bin"), reverse=True)
    directories += sorted(Path("/opt/homebrew/opt").glob("postgresql@*/bin"), reverse=True)
    for directory in dict.fromkeys(directories):
        dump, restore = directory / "pg_dump", directory / "pg_restore"
        if not dump.is_file() or not restore.is_file():
            continue
        majors = []
        for executable in (dump, restore):
            version = subprocess.run(
                [str(executable), "--version"],
                capture_output=True,
                text=True,
                check=True,
                timeout=10,
            ).stdout
            match = re.search(r"PostgreSQL\) (\d+)", version)
            majors.append(int(match.group(1)) if match else 0)
        if majors[0] >= server_major and majors[1] >= majors[0]:
            return dump, restore
    pytest.skip(
        "BLOCKED logical restore: compatible pg_dump/pg_restore clients for "
        f"PostgreSQL server major {server_major} are unavailable"
    )


def _db_state_digest(engine: Engine) -> str:
    """Compare exact committed rows, including operational delivery and witnesses."""
    state: dict[str, Any] = {}
    with transaction(engine) as session:
        for model in (
            Artifact,
            Receipt,
            Outbox,
            Consumption,
            Revision,
            Observation,
            Availability,
            HealthInterval,
            Snapshot,
            SnapshotInvalidation,
        ):
            table = model.__table__
            rows = session.execute(select(table).order_by(*table.primary_key.columns)).mappings()
            state[table.name] = [dict(row) for row in rows]
        state["migration_heads"] = sorted(
            session.scalars(text("SELECT version_num FROM alembic_version"))
        )

    def encode(value: Any) -> str:
        if isinstance(value, datetime):
            return value.isoformat()
        raise TypeError(f"Unsupported digest value: {type(value).__name__}")

    data = json.dumps(state, sort_keys=True, separators=(",", ":"), default=encode).encode()
    return hashlib.sha256(data).hexdigest()


def _cli_connection(engine: Engine) -> tuple[str, dict[str, str]]:
    # Keep passwords out of subprocess arguments and therefore process listings.
    url = engine.url.set(drivername="postgresql", password=None)
    environment = dict(os.environ)
    if engine.url.password is not None:
        environment["PGPASSWORD"] = engine.url.password
    return url.render_as_string(hide_password=False), environment


def test_logical_restore_resumes_outbox_and_missing_objects_invalidate_frozen_snapshot(
    engine: Engine,
    store: LocalObjectStore,
    tmp_path: Path,
) -> None:
    dump, restore = _postgres_clients(engine)
    approve(engine)
    first_receipt = ingest(engine, store, xml("before-backup"))
    assert run_parser_once(engine, store)
    sealed = seal_snapshot(engine, store, "logical-restore-drill")
    second_receipt = ingest(engine, store, xml("committed-but-undelivered"))
    with transaction(engine) as session:
        first = session.get(Receipt, first_receipt)
        assert first is not None
        first_key = first.artifact_key
        pending = session.scalar(select(Outbox).where(Outbox.receipt_id == second_receipt))
        assert pending is not None and pending.state == "PENDING"
        pending_id = pending.id
    expected_digest = _db_state_digest(engine)
    archive = tmp_path / "logical-postgresql-backup.dump"
    restored_root = tmp_path / "restored-object-backup"
    shutil.copytree(store.root, restored_root)
    restored_store = LocalObjectStore(restored_root)
    source_url, environment = _cli_connection(engine)
    database_name = f"pulse_restore_{uuid4().hex}"
    restored_url = engine.url.set(database=database_name)
    restored_engine: Engine | None = None
    connection_args = engine.url.translate_connect_args(username="user")
    connection_args["dbname"] = connection_args.pop("database")
    with psycopg.connect(**connection_args, autocommit=True) as admin:
        try:
            admin.execute(sql.SQL("CREATE DATABASE {}").format(sql.Identifier(database_name)))
        except psycopg.errors.InsufficientPrivilege:
            pytest.skip("BLOCKED logical restore: test database role cannot create a disposable DB")
        try:
            subprocess.run(
                [
                    str(dump),
                    "--format=custom",
                    "--no-owner",
                    "--no-privileges",
                    f"--file={archive}",
                    f"--dbname={source_url}",
                ],
                env=environment,
                capture_output=True,
                text=True,
                check=True,
                timeout=30,
            )
            assert archive.is_file() and archive.stat().st_size > 0
            restored_engine = engine_for(restored_url.render_as_string(hide_password=False))
            target_url, target_environment = _cli_connection(restored_engine)
            subprocess.run(
                [
                    str(restore),
                    "--exit-on-error",
                    "--no-owner",
                    "--no-privileges",
                    f"--dbname={target_url}",
                    str(archive),
                ],
                env=target_environment,
                capture_output=True,
                text=True,
                check=True,
                timeout=30,
            )
            assert _db_state_digest(restored_engine) == expected_digest
            restored_settings = Settings(
                database_url=restored_url.render_as_string(hide_password=False),
                object_root=restored_store.root,
                api_token="restore-reader",
                audit_token="restore-auditor",
            )
            with TestClient(create_app(restored_settings, restored_engine)) as client:
                audit_headers = {"Authorization": "Bearer restore-auditor"}
                before = client.get(f"/v1/snapshots/{sealed.id}", headers=audit_headers).json()
                assert before["validity"] == "PERMITTED"
                assert before["manifest"] == sealed.manifest
                assert before["sha256"] == sealed.sha256
                assert before["payload"][0]["fields"]["title"] == "before-backup"
                assert run_parser_once(restored_engine, restored_store)
                with transaction(restored_engine) as session:
                    delivered = session.get(Outbox, pending_id)
                    assert delivered is not None and delivered.state == "DONE"
                    assert len(list(session.scalars(select(Observation)))) == 2
                    immutable = session.get(Snapshot, sealed.id)
                    assert immutable is not None and immutable.manifest == sealed.manifest
                restored_store.delete(first_key)
                recovery = reconcile(restored_engine, restored_store)
                assert recovery["missing_artifacts"] == 1
                with transaction(restored_engine) as session:
                    invalidations = list(
                        session.scalars(
                            select(SnapshotInvalidation).where(
                                SnapshotInvalidation.snapshot_id == sealed.id,
                            )
                        )
                    )
                    assert any(row.reference_id == first_key for row in invalidations)
                    assert all(row.reason == "ARTIFACT_MISSING_OR_CORRUPT" for row in invalidations)
                    gap = session.scalar(
                        select(HealthInterval).where(
                            HealthInterval.reason == "ARTIFACT_MISSING_OR_CORRUPT",
                        )
                    )
                    assert gap is not None and gap.state == "RECOVERY_UNCERTAIN"
                    assert gap.ended_at is None
                    immutable = session.get(Snapshot, sealed.id)
                    assert immutable is not None
                    assert (immutable.manifest, immutable.sha256) == (
                        sealed.manifest,
                        sealed.sha256,
                    )
                    assert (
                        hashlib.sha256(immutable.manifest.encode()).hexdigest() == immutable.sha256
                    )
                unavailable = client.get(
                    f"/v1/snapshots/{sealed.id}",
                    headers=audit_headers,
                ).json()
                assert unavailable["validity"] == "REPLAY_UNAVAILABLE"
                assert unavailable["payload"] is None
                assert unavailable["manifest"] == sealed.manifest
                assert unavailable["sha256"] == sealed.sha256
                assert (
                    "APPEND_ONLY_INVALIDATION_PRESENT" in unavailable["replay_unavailable_reasons"]
                )
                assert reconcile(restored_engine, restored_store)["missing_artifacts"] == 0
            # Recovery mutates only the restored copy, leaving the source backup intact.
            assert _db_state_digest(engine) == expected_digest
            assert store.verify(first_key, first_key.rsplit("/", 1)[1].removesuffix(".json"))
        finally:
            if restored_engine is not None:
                restored_engine.dispose()
            admin.execute(
                sql.SQL("DROP DATABASE {} WITH (FORCE)").format(
                    sql.Identifier(database_name),
                )
            )
