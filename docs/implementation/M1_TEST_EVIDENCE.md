# M1 executed verification evidence

Executive verdict: **PARTIAL**. The offline observed-only vertical slice passes its executed
software checks. Operational G0/G1 qualification and the blocked controls below do not pass by
inference from these tests.

## PR #3 review fixes: latest verification

The owner review of `e1284e729302ef4849042455791a38b8c1067974` is recorded in
[review 5494912411](https://github.com/Ahmaddaghra/pulse_engineering_source/pull/3#pullrequestreview-5494912411).
Latest executed application revision: **`f781814444dfb33bd95abe1d802835c09ffc62f6`**.
The feature incorporated `main` at `f98889d3efd4d5deefd3e1909212be4406c67e90` via merge
`8aa55ac`; the owner explicitly selected `main` as the draft PR base. Original design documents
remain unchanged. The baseline evidence below is retained as historical evidence, not the
verification result for these fixes.

On the same isolated PostgreSQL 17.10 / CPython 3.12.14 environment, the complete suite passed
**298 tests, 0 failures, 0 errors, 0 skips**, in **30.55 seconds**:

```sh
make check
PULSE_DATABASE_URL=postgresql+psycopg://ahmad@127.0.0.1:55432/pulse_m1 uv run alembic check
git diff --check
PULSE_TEST_DATABASE_URL=postgresql+psycopg://ahmad@127.0.0.1:55432/pulse_m1 uv run pytest -q --junitxml=../m1-review-test-results.xml
```

Ruff lint/format and strict mypy passed. Alembic detected no new upgrade operations; identity
versioning changes require no schema migration. The existing Starlette/httpx warning remains.

| Test module | Latest cases passed | New review regression evidence |
| --- | ---: | --- |
| `tests/test_collection.py` | 154 | Header-only 429/503 handling, compressed/oversized error bodies, malformed ancillary headers, response/connection cleanup faults |
| `tests/test_capture.py` | 35 | Actual HTTPS-adapter path with fake transport and real PostgreSQL preserves Retry-After/RATE_LIMITED state, reads no error body, stores no payload/receipt/outbox |
| `tests/test_worker.py` | 41 | Mutable timestamp/precision cannot split identity; unique legacy continuation is audited; conflicting legacy identities are quarantined; final incoming and cross-source legacy approval/artifact/receipt-retention expiry rolls back new effects |
| `tests/test_api_snapshots.py` | 67 | Mixed-case and malformed HTTP(S) GUID suppression across observations/articles/sealed replay; opaque GUIDs and permitted replay remain intact |
| `tests/test_restore.py` | 1 | Complete logical restore/reconciliation test rerun with the revised source |

The 110 additional cases supplement the baseline durability, temporal, rights and restore
tests. A legacy-continuation regression verifies the original occurrence/revision/observation IDs,
manifest, hash and replay payload remain unchanged after a corrected timestamp arrives. Multiple
compatible historical occurrences remain immutable and produce explicit degraded rejection
evidence rather than another occurrence. Existing consumed `parser-v1` events remain idempotent;
new revisions record `normalization-v2`. Cross-source expiry regressions deliberately delay the
final permission read; the subsequent fresh DB timestamp rejects approval, artifact and
receipt-retention expiry and rolls back new audit/consumption/evidence. A permitted control
continues the same legacy identity successfully.

All transport responses in these regressions are controlled fixtures; no publisher request was
made. Hosted verification for this revision is pending and will be recorded after execution.

## Baseline immutable tested revision and environment

Executed source revision: **`3c55202bcc41b3e8ebf7b8e4ed6adb8f3a521851`**.
Application tests use that source; later CI-only changes isolate disposable Compose volumes
and install matching restore clients. The evidence documentation changes no application code. Branch:
`feat/m1-durable-ingestion`, based on specification branch commit
`d7d4eceb8ff0fa940370c8847ba6813f5b0af39f`.

Date: 2026-10-12 (user timezone Asia/Hebron). Local environment: macOS arm64,
CPython **3.12.14**, uv **0.12.13**, PostgreSQL server/clients **17.10**.
An isolated native PostgreSQL cluster listened only at `127.0.0.1:55432`; database
`pulse_m1` was exclusively for tests and truncated per test. No SQLite test establishes any
concurrency or transaction guarantee. No publisher feed was accessed.

Locked dependencies are in `uv.lock`. All synthetic observations are explicitly fixture-scoped.
They establish software correctness only, not throughput, source feasibility, representative
coverage, forecasting accuracy or newsroom utility.

## Baseline commands and results

```sh
uv sync --frozen --python 3.12
PULSE_DATABASE_URL=postgresql+psycopg://ahmad@127.0.0.1:55432/pulse_m1 uv run alembic upgrade head
PULSE_DATABASE_URL=postgresql+psycopg://ahmad@127.0.0.1:55432/pulse_m1 uv run alembic check
make check
PULSE_TEST_DATABASE_URL=postgresql+psycopg://ahmad@127.0.0.1:55432/pulse_m1 uv run pytest -q --junitxml=../m1-test-results.xml
```

Baseline full-suite result: **188 passed, 0 failed, 0 skipped**, in **18.96 seconds**.
One Starlette/httpx test-client deprecation warning remains; it is documented as dependency
maintenance work and is not suppressed. Earlier review runs exposed failures; those defects were
fixed and the final full suite was rerun. The final result is not an aggregation of selectively
passing earlier runs.

| Test module | Cases passed | Evidence type |
| --- | ---: | --- |
| `tests/test_collection.py` | 111 | Unit, Hypothesis properties, synthetic DNS/HTTPS controls, real AF_UNIX stalled-I/O interruption |
| `tests/test_capture.py` | 29 | Real PostgreSQL capture/rights/fence/retention/throttle and fault injection |
| `tests/test_worker.py` | 25 | Timestamp/identity unit/property checks plus real PostgreSQL revision/outbox/fence tests |
| `tests/test_api_snapshots.py` | 22 | Real PostgreSQL API, rights/retention expiry, visibility and immutable replay |
| `tests/test_restore.py` | 1 | Actual PostgreSQL custom dump/restore, object backup/reconciliation and replay invalidation |

`make check`: Ruff lint **PASS**, Ruff format **PASS** (30 Python files), strict mypy **PASS**
(16 application modules). `alembic check`: **no new upgrade operations detected**.
`git diff --check`: **PASS**. Original `PULSE_BLUEPRINT.md` and all `docs/v0.2` files have no diff
against the requested specification base.

Migrations applied on empty local databases and upgraded on existing test databases:

1. `0001` — evidence ledgers, registry, receipt/artifact, identity/provenance, outbox and manifests.
2. `0002` — append-only evidence triggers, policy/lease constraints and due/history indexes.
3. `0003` — immutable XML extraction transform provenance on receipts.
4. `0004` — attempt payload expiry independent of lease lifetime for orphan retention.

Compose configuration **PASS** for default and CI override:

```sh
PULSE_API_TOKEN=local-reader-token PULSE_AUDIT_TOKEN=local-auditor-token docker compose config --quiet
PULSE_API_TOKEN=local-reader-token PULSE_AUDIT_TOKEN=local-auditor-token docker compose -f compose.yaml -f compose.ci.yaml config --quiet
bash -n scripts/compose_smoke.sh
```

Local Docker image/service execution: **BLOCKED**. `docker info` failed because
`/Users/ahmad/.docker/run/docker.sock` did not exist. Config validation is not runtime evidence.
The GitHub Actions workflow is configured to build/run the Compose stack and test actual API
startup; the executed remote PASS is recorded below.

## Baseline hosted CI and Docker runtime evidence

GitHub Actions run [38292026796](https://github.com/Ahmaddaghra/pulse_engineering_source/actions/runs/38292026796)
**PASS** on runtime/CI revision **`f385cb3c7e50416f08722e4f963943feb44b90c8`**.
Its JUnit artifact reports **188 tests, 0 failures, 0 errors, 0 skipped**. Matching PostgreSQL 17
clients are installed using the [official PostgreSQL Ubuntu repository instructions](https://www.postgresql.org/download/linux/ubuntu/);
CI explicitly rejects any skipped fault scenario. An earlier run had 187 pass/1 BLOCKED restore
skip; that environment gap was resolved and is not counted as the final result.

Hosted checks passed Ruff/format/mypy, empty-database migrations and schema drift, the full test
suite including logical restore, and the fixture CLI flow. The Compose smoke built the Docker
image, initialized a separate PostgreSQL/object-volume project, applied head0004, captured and
parsed a fixture, sealed a snapshot, and started the configured ASGI server. Actual container
readiness returned `ready/reachable/0004`; actual observations asserted `OBSERVED_ONLY`,
`AVAILABLE`, one stored record and receipt/extraction provenance: **Compose offline API smoke PASS**.

Docker runtime is therefore **test-passed on the hosted Linux runner**. The local Mac daemon
remains unavailable. This is a software smoke, not sustained production qualification. Disposable
CI volumes use project `pulse-m1-ci-smoke` so cleanup cannot erase development project volumes.

## Baseline fresh database and actual server smoke

On a separate empty `pulse_m1_demo` native database, migrations and `alembic check` passed.
The following commands executed (environment pointed at that separate database/object root):

```sh
make demo
uv run python scripts/audit_m1.py
uv run uvicorn pulse.asgi:app --host 127.0.0.1 --port 18080
curl --fail -H 'Authorization: Bearer local-smoke-reader' http://127.0.0.1:18080/ready
curl --fail -H 'Authorization: Bearer local-smoke-reader' http://127.0.0.1:18080/v1/observations
```

Observed persistent state: **one attempt, receipt, outbox event, occurrence, revision,
observation and sealed snapshot**. Independent audit returned **PASS** with no findings. Actual
Uvicorn readiness returned HTTP 200 with the installed migration head; actual observations
returned `OBSERVED_ONLY`, `AVAILABLE`, one persisted synthetic record, receipt/fetch/revision
IDs, checksums and extraction/parser/schema versions. This is a real local server smoke using
stored fixture evidence, not only FastAPI's test client. The smoke initially exercised head0003;
the demo was then upgraded to head0004 and migration drift checked. The final full suite tests
head0004.

The ASGI entrypoint defect discovered during review was repaired (`pulse.asgi:app`); it was not
hidden by application-factory unit tests. Checked-in OpenAPI was retrieved from the server.

## Mandatory scenario matrix

| Requirement / scenario | Executed state assertions | Verdict |
| --- | --- | --- |
| Crash after object write, before receipt commit | Zero receipt/artifact/outbox rows, orphan present, expiry/lease reconciliation removes it; same fetch ID reclaims with higher fence and succeeds | PASS |
| Crash after receipt/outbox commit, before delivery | Receipt and pending event survive; witness recovery and parser polling produce linked durable observations | PASS |
| Duplicate downstream delivery | One consumption and logical revision effect after crash/redelivery; separate ACK resumes | PASS |
| Expired/stale worker leases | Capture and parser fence/expiry rejection; lease expiring inside effects transaction rolls back DB changes | PASS |
| Duplicate observations and out-of-order receipt processing | Receipt/ordinal observations remain distinct; current state follows receive chronology and derived qualifying first_seen | PASS |
| Article edit and A → B → A | Two distinct revisions can serve three immutable observations; all exact receipt links and chronology remain | PASS |
| Reused URL / identical content at different publishers | Distinct GUID separates occurrences; mutable publisher times remain revision data; publisher scope separates syndicated copies; no event/origin identity is invented | PASS within explicit ambiguous-identity limit (review contract supersedes timestamp identity) |
| 304 missing cached artifact | Validators cleared, no accepted 304 receipt, gap/retry persisted, next attempt unconditional | PASS |
| Simultaneous 429/503 and healthy work | Parallel responses persist separate backoffs, healthy source processes; one shared-account active lease and limited half-open probe; long throttle cannot fill backlog with repeated same-source polls | PASS synthetic bounded scenario |
| Revocation during fetch/object write | Source head/version rechecked before acceptance; no receipt/outbox, unaccepted content erased, safe failure evidence remains | PASS |
| Malformed/oversized XML | DTD/entities/structure/depth/items/text/bytes rejected, no artifact/receipt; response body not saved in errors | PASS structural/bounded software checks |
| Outage observations | Unavailable/partially degraded/healthy empty are distinct; retained gaps visible after later successes; no invented zero coverage | PASS |
| PostgreSQL logical restore and object reconciliation | Real pg_dump/pg_restore reproduces persisted row digests; pending parser resumes; deleted restored object appends RECOVERY_UNCERTAIN and snapshot invalidations without rewriting manifest; API replay unavailable | PASS logical restore |
| Historical invariance after future revisions/parser version/late earlier receipt | Original manifest, hash and replay payload stay unchanged; frozen first_seen survives current restatement | PASS |
| Retention during active orphan lease | Durable payload deadline overrides a longer lease; final and interrupted staging files erased when disallowed/abandoned | PASS |
| Rights/retention expiry during checksum/build/replay | Expired refs removed, current first_seen recomputed; unsafe seal rejected before insert; replay payload hidden | PASS |
| Unapproved/live-disabled access | Unknown/revoked/expired/non-metadata policy cannot acquire collection; live-disabled gate runs before adapter/DNS | PASS |
| Reader/auditor boundary | Missing, equal, wrong-scope bearer credentials denied; reader cannot seal/replay; no policy/fetch mutation HTTP routes | PASS single-operator scope |

Fault injection uses deterministic crash hooks/controlled lease expiry and observable committed
PostgreSQL state. It does not pretend to simulate hardware power loss, a production storage
system, or a sustained publisher panel. The transport deadline test uses real local AF_UNIX I/O,
not an external publisher connection.

## Explicitly blocked or unqualified scenarios

- **BLOCKED locally — Docker daemon**: no running local socket. Hosted Linux Docker/Compose
  runtime passed; no local Docker success is asserted.
- **BLOCKED — WAL/PITR restore**: no WAL archive, recovery target or production backup/deletion
  policy configured. A logical dump/restore does not prove PITR or an acknowledged-capture RPO.
- **BLOCKED — approved-origin live TLS/DNS/egress qualification**: no confirmed publisher/feed
  permissions were supplied. Mocked/pinned socket tests cannot qualify deployment DNS rebinding
  defenses or deny-by-default system egress.
- **BLOCKED — hard parser process CPU/address-space exhaustion**: no sandbox/quota deployment was
  provisioned. Malicious XML and bounded in-process tests pass; OS-enforced isolation remains work.
- **UNQUALIFIED — sustained operation, fairness/capacity, clock discipline, RPO/RTO, source/feed
  completeness and erasure latency**: no prospective operational study or source panel exists.

## Claim levels

- **Design-complete for this narrow slice**: implemented diagrams/contracts describe its actual
  behavior; full v0.2 research/editorial design is broader and remains gated.
- **Code-complete for the offline path**: durable attempt → policy-gated fixture → permitted object
  → receipt/cache/outbox → fenced/idempotent revisions → witnessed observed API → immutable seal.
- **Test-passed**: latest review source has 298/0/0 locally; hosted verification is pending.
  Baseline 188/0/0 local/hosted and real Docker/Compose/server smoke remain historical evidence
  on the named immutable source revisions.
- **Operationally-qualified**: **NO**. M1's whole Definition of Done is **not declared complete**.
  G0 rights and G1 operational release remain HOLD until their independent evidence exists.
