# M1 executed verification evidence

Executive verdict: **PARTIAL**. The offline observed-only vertical slice passes its executed
software checks. Operational G0/G1 qualification and the blocked controls below do not pass by
inference from these tests.

## Immutable tested revision and environment

Executed source revision: **`3c55202bcc41b3e8ebf7b8e4ed6adb8f3a521851`**.
The following documentation commit changes handoff/evidence text only. Branch:
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

## Commands and results

```sh
uv sync --frozen --python 3.12
PULSE_DATABASE_URL=postgresql+psycopg://ahmad@127.0.0.1:55432/pulse_m1 uv run alembic upgrade head
PULSE_DATABASE_URL=postgresql+psycopg://ahmad@127.0.0.1:55432/pulse_m1 uv run alembic check
make check
PULSE_TEST_DATABASE_URL=postgresql+psycopg://ahmad@127.0.0.1:55432/pulse_m1 uv run pytest -q --junitxml=../m1-test-results.xml
```

Final full-suite result: **188 passed, 0 failed, 0 skipped**, in **18.96 seconds**.
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
startup; its separate result must be inspected in the draft PR before claiming remote PASS.

## Fresh database and actual server smoke

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
| Reused URL / identical content at different publishers | GUID/time change splits occurrence; publisher scope separates syndicated copies; no event/origin identity is invented | PASS within explicit ambiguous-identity limit |
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

- **BLOCKED — local Docker runtime**: no running Docker daemon/socket. Native PostgreSQL/service
  verification is separate; hosted Compose smoke is required before Docker runtime PASS.
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
- **Test-passed**: the 188-case final suite and commands above passed on the named source revision.
- **Operationally-qualified**: **NO**. M1's whole Definition of Done is **not declared complete**.
  G0 rights and G1 operational release remain HOLD until their independent evidence exists.
