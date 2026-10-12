"""Small trusted administration/worker entry point; HTTP API is read-only."""

import argparse
import json
import time
from datetime import UTC, datetime, timedelta
from functools import partial
from pathlib import Path

from pulse.capture import run_capture_once, schedule
from pulse.collection import (
    CollectionBlocked,
    CollectionRequest,
    CollectionResponse,
    FixtureAdapter,
)
from pulse.config import Settings
from pulse.db import engine_for
from pulse.objects import LocalObjectStore
from pulse.policy import PolicyInput, register_policy, revoke_policy
from pulse.reconcile import reconcile
from pulse.snapshots import seal_snapshot
from pulse.worker import run_parser_once


def fixture_response(request: CollectionRequest, body: bytes) -> CollectionResponse:
    if not request.endpoint.startswith("fixture://"):
        raise CollectionBlocked("The fixture CLI cannot simulate a live publisher")
    return CollectionResponse(200, body, datetime.now(UTC), etag='"synthetic-software-fixture"')


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "command",
        choices=[
            "seed-fixture",
            "schedule",
            "capture-fixture",
            "parse",
            "reconcile",
            "snapshot",
            "register-policy",
            "revoke",
        ],
    )
    parser.add_argument("--fixture", type=Path, default=Path("tests/fixtures/basic.xml"))
    parser.add_argument("--policy", type=Path)
    parser.add_argument("--source-id", default="synthetic-one")
    parser.add_argument("--feed-id", default="synthetic-feed-one")
    parser.add_argument("--actor", default="local-fixture-operator")
    parser.add_argument("--run-id", default="local-observed-seal")
    parser.add_argument("--loop", action="store_true")
    parser.add_argument("--interval-seconds", type=int, default=2)
    args = parser.parse_args()
    if not 1 <= args.interval_seconds <= 300:
        parser.error("interval-seconds must be between 1 and 300")
    if args.loop and args.command not in {"schedule", "capture-fixture", "parse", "reconcile"}:
        parser.error("only bounded worker commands support --loop")
    settings = Settings.from_env()
    engine = engine_for(settings.database_url)
    store = LocalObjectStore(settings.object_root)
    while True:
        if args.command == "seed-fixture":
            now = datetime.now(UTC)
            result: object = register_policy(
                engine,
                args.source_id,
                args.feed_id,
                PolicyInput(
                    publisher_id="synthetic-publisher",
                    owner_id="synthetic-owner",
                    endpoint=f"fixture://{args.source_id}/feed",
                    allowed_host=args.source_id,
                    effective_from=now,
                    expires_at=now + timedelta(days=7),
                    approved_by=args.actor,
                    rate_scope=args.source_id,
                    attribution="SYNTHETIC SOFTWARE FIXTURE; no real publisher permission",
                ),
            )
        elif args.command == "register-policy":
            if args.policy is None:
                parser.error("--policy JSON file is required")
            result = register_policy(
                engine,
                args.source_id,
                args.feed_id,
                PolicyInput.model_validate_json(args.policy.read_text()),
            )
        elif args.command == "revoke":
            result = revoke_policy(engine, args.source_id, args.actor)
        elif args.command == "schedule":
            result = schedule(engine)
        elif args.command == "capture-fixture":
            # The fixture responder refuses live publisher endpoints.
            if args.fixture.stat().st_size > 4194304:
                parser.error("fixture exceeds maximum supported size")
            body = args.fixture.read_bytes()
            collector = FixtureAdapter(partial(fixture_response, body=body))
            result = run_capture_once(engine, settings, store, collector)
        elif args.command == "parse":
            result = run_parser_once(engine, store, settings.lease_seconds)
        elif args.command == "snapshot":
            snapshot = seal_snapshot(engine, store, args.run_id)
            result = {"snapshot_id": snapshot.id, "sha256": snapshot.sha256}
        else:
            result = reconcile(engine, store)
        print(json.dumps({"command": args.command, "result": result}), flush=True)
        if not args.loop:
            break
        time.sleep(args.interval_seconds)
    engine.dispose()


if __name__ == "__main__":
    main()
