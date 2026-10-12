# M1 handoff

Executive status: **PARTIAL**. The offline PostgreSQL capture → receipt/outbox → idempotent parser
→ immutable observed evidence → API path is implemented and tested. M1 is not operationally
qualified. Exact test revision/results and blocked requirements are in
[M1_TEST_EVIDENCE.md](M1_TEST_EVIDENCE.md); remaining work is in
[M1_OPEN_ISSUES.md](M1_OPEN_ISSUES.md).

## Git and review

Feature branch: `feat/m1-durable-ingestion`.
Current PR base: `main`, reconciled at `f98889d3efd4d5deefd3e1909212be4406c67e90`.
Original implementation base: `docs/pulse-v0.2-review-integration` at
`d7d4eceb8ff0fa940370c8847ba6813f5b0af39f`. The project owner explicitly requested
retargeting after PR #1 merged; the feature incorporates main without rewriting review history.
Draft [pull request #3](https://github.com/Ahmaddaghra/pulse_engineering_source/pull/3) now targets main.
PR #1 was already merged before this run; this implementation did not change or merge it.
No push to main, production deployment or live publisher request was performed.
Latest executed source revision: `f781814444dfb33bd95abe1d802835c09ffc62f6`.
The complete review suite passed 298 tests locally with no failures or skips; hosted results
are recorded separately in the test evidence. Review fixes preserve identity across timestamp
corrections, honor 429/503 retry headers without reading error bodies, and apply link-display
restrictions to mixed-case and malformed HTTP(S) GUIDs. Legacy identity continuation/quarantine
and `normalization-v2` are described in the data model and open issues.
Use `git rev-parse HEAD` for the checkout revision; the recorded test revision is immutable.

## Reproducible Docker development path

Requirements: Git, Docker Engine with Compose v2, and two distinct locally chosen bearer secrets.
The Docker path passed the hosted CI Compose smoke job (see test evidence). Local execution status is reported
separately; `docker compose config` does not prove a working image/service.

```sh
git clone --branch feat/m1-durable-ingestion https://github.com/Ahmaddaghra/pulse_engineering_source.git
cd pulse_engineering_source
cp .env.example .env
# Edit PULSE_API_TOKEN and PULSE_AUDIT_TOKEN in .env to distinct local secrets.
docker compose build api
docker compose up -d db
docker compose run --rm migrate
docker compose run --rm api python -m pulse.cli seed-fixture
docker compose run --rm api python -m pulse.cli schedule
docker compose run --rm api python -m pulse.cli capture-fixture
docker compose run --rm api python -m pulse.cli parse
docker compose run --rm api python -m pulse.cli snapshot --run-id first-observed-seal
docker compose up -d api
# Optional separate, bounded offline worker processes after fixture enrollment:
docker compose --profile workers up -d scheduler collector parser reconciler
```

Seed once on a new database. Running seed again appends a new policy version, conservatively
hiding prior-version content until reconciliation. The fixture labels itself synthetic and contains
no real news measurement. `capture-fixture` refuses live publisher endpoints even when a caller
changes the environment live flag. There is no live ingestion command in this slice.

The API listens on `127.0.0.1:8000`. `/health` is public minimal liveness. For example, after
exporting the reader secret chosen in `.env` as `PULSE_API_TOKEN`:

```sh
curl --fail -H "Authorization: Bearer $PULSE_API_TOKEN" http://localhost:8000/ready
curl --fail -H "Authorization: Bearer $PULSE_API_TOKEN" http://localhost:8000/v1/observations
curl --fail -H "Authorization: Bearer $PULSE_API_TOKEN" http://localhost:8000/v1/articles
```

Auditor token is required for POST `/v1/snapshots` and GET `/v1/snapshots/{id}` or its `/manifest`
alias. Readers cannot seal/replay snapshots; missing/equal tokens fail closed. OpenAPI is served
at `/openapi.json`; checked-in contracts are `contracts/openapi.json` and
`contracts/source-policy.schema.json`. This is a single-operator boundary, not tenant RBAC.

## Native PostgreSQL fallback and test dependencies

The executed local path used CPython 3.12.14 and PostgreSQL/client tools 17.10. `uv sync` installs
locked FastAPI, SQLAlchemy, Alembic, psycopg, Pydantic and defusedxml dependencies plus pytest,
Hypothesis, Ruff, mypy and the HTTP test client. A dedicated PostgreSQL database is mandatory:
the test fixture truncates its tables. Never point tests at a database containing wanted data.

For an existing locally administered isolated PostgreSQL instance:

```sh
uv sync --frozen --python 3.12
# Substitute your own isolated PostgreSQL role/port/database. This run used the values below.
createdb -h 127.0.0.1 -p 55432 pulse_m1_test
export PULSE_DATABASE_URL=postgresql+psycopg://ahmad@127.0.0.1:55432/pulse_m1_test
export PULSE_TEST_DATABASE_URL="$PULSE_DATABASE_URL"
export PULSE_OBJECT_ROOT=./work/test-objects
export PULSE_LIVE_ENABLED=false
uv run alembic upgrade head
uv run alembic check
make check
uv run pytest -q
```

If no PostgreSQL instance exists, a regular non-root user can initialize an isolated native
server; PostgreSQL executables must be in PATH:

```sh
mkdir -p work
initdb -D work/pgdata -A trust --no-locale --encoding=UTF8
pg_ctl -D work/pgdata -l work/postgres.log -o '-h 127.0.0.1 -p 55432 -k /tmp' start
```

This trust-authenticated instance is only a loopback development fixture. Shut it down with
`pg_ctl -D work/pgdata stop` when finished. Logical restore tests need compatible `pg_dump` and
`pg_restore` plus the test role's permission to create/drop a disposable database. Missing tools
or privileges produce an explicitly BLOCKED skip. Tests run serially, since each test resets the
isolated database. No SQLite substitute is supported.

For a separate clean native demo database, export its `PULSE_DATABASE_URL`, the object root and
distinct `PULSE_API_TOKEN`/`PULSE_AUDIT_TOKEN`, apply migrations, then:

```sh
make demo
uv run python scripts/audit_m1.py
uv run uvicorn pulse.asgi:app --host 127.0.0.1 --port 8000
```

The independent audit does not import ingestion code. It queries receipt/outbox and observation
provenance, recomputes revision/manifest/object checksums, and reports stored counts. This is a
software invariant check, not a production compliance certification.

## Recovery and operation

`python -m pulse.cli reconcile` removes abandoned/expired staging and final objects, detects
missing/corrupt referenced objects, erases currently disallowed local content, appends audit and
snapshot invalidations, and recovers missing postcommit witnesses. Capture and parser polling
reclaim expired leases with a new fence. The parser reuses committed consumption records after
an acknowledgment crash. Retry deadlines and origin breaker state survive process restarts.

Object and DB backups must be matched. Missing objects after restore invalidate affected seals,
make replay unavailable and produce open `RECOVERY_UNCERTAIN` gaps. A successful later poll does
not erase outage history. Logical dump/restore is tested; WAL/PITR, deletion-aware backup handling,
production RPO/RTO and sustained operation still require engineering evidence.

Recommended next step: qualify the Compose runtime and hard parser/egress/role controls, then
perform a deletion-aware WAL/PITR drill. Keep live ingestion disabled until the source steward
confirms real publisher permissions. Do not start forecasting or claim G0/G1 operational GO from
synthetic fixtures.
