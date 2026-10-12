#!/usr/bin/env bash
set -euo pipefail
# Requires configured distinct reader/auditor tokens, Docker and Compose v2.
compose=(docker compose -f compose.yaml -f compose.ci.yaml)
trap '"${compose[@]}" down --volumes' EXIT
"${compose[@]}" build api
"${compose[@]}" up -d --wait db
"${compose[@]}" run --rm migrate
"${compose[@]}" run --rm collector python -m pulse.cli seed-fixture
"${compose[@]}" run --rm collector python -m pulse.cli schedule
"${compose[@]}" run --rm collector python -m pulse.cli capture-fixture
"${compose[@]}" run --rm parser python -m pulse.cli parse
"${compose[@]}" run --rm api python -m pulse.cli snapshot
"${compose[@]}" up -d --wait api
curl --fail --silent -H "Authorization: Bearer ${PULSE_API_TOKEN}" http://localhost:8000/ready
curl --fail --silent -H "Authorization: Bearer ${PULSE_API_TOKEN}" http://localhost:8000/v1/observations |
  python3 -c 'import json,sys; r=json.load(sys.stdin); assert r["mode"]=="OBSERVED_ONLY"; assert r["evidence_status"]=="AVAILABLE"; assert r["total"]==1; assert r["records"][0]["receipt_id"]; assert r["records"][0]["collection_parser_version"]=="xml-metadata-v1"; print("Compose offline API smoke: PASS")'
