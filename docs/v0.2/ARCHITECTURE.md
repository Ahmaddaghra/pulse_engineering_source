# Architecture, failure boundaries and recovery — v0.2

**Status:** prescriptive design; not implemented. Preserve modular monolith ADR-001. Workloads may run as independently resource-bounded processes while sharing source and domain contracts.

## C4-style container and trust boundaries

```mermaid
flowchart TB
 Editor[Duty / planning editor] --> UI[Editorial workbench]
 Steward[Data steward] --> Admin[Policy approval API]
 UI --> API[Application API / RBAC]
 Admin --> API
 API --> DB[(PostgreSQL: policy, receipt, revisions, outbox, queues, actions)]
 Scheduler[Scheduler: due and allowed origins] --> Collector[Bounded RSS collectors]
 Collector --> Policy[Rights + origin/egress gate]
 Policy --> Remote[(Approved RSS publishers)]
 Collector --> Object[(Versioned permitted object storage)]
 Collector --> DB
 DB --> Relay[Transactional outbox relay]
 Relay --> Parser[Sandboxed parsers and canonicalization]
 Parser --> DB
 DB --> Cluster[Event and syndication workers]
 Cluster --> DB
 DB --> Observed[Prompt observed-alert worker]
 Observed --> API
 DB --> Snapshot[Consistent snapshot manifest builder]
 Snapshot --> Forecast[Research-only prediction worker]
 Forecast --> DB
 DB --> Reconciler[Receipt / object / deletion reconciler]
 Object --> Reconciler
 Reconciler --> DB
 DB --> Auditor[Independent replay / retention / gap auditor]
 Object --> Auditor
 API --> Audit[Read-only evidence audit view]
 classDef blocked fill:#eee,stroke:#555
```

**Separation:** No direct collector-to-clustering delivery. All work transitions persist in PostgreSQL. Forecasting never gates the observed alert stream. LLM text interpretation, if enabled, runs without database-write privileges, secrets, or network tools; schema/evidence IDs are validated by a trusted process. No automatic publishing or opinion manipulation.

## Transaction boundary contract

1. **Preflight**: approve origin/permission *before* any network request; persist a due `fetch_attempt` and stable `fetch_id`. Permission is checked again before accepting durable content.
2. **Fetch**: use bounded network/parse budgets. Recheck current permission after the response and before any object persistence. Store the allowed raw representation or policy-permitted metadata envelope as a content-addressed, policy-scoped, immutable object. An unapproved payload must not remain in quarantine. A valid 304 references the existing permitted, recoverable object; it creates a receipt without inventing new publication occurrences.
3. **Receipt transaction**: in one PostgreSQL transaction, verify the current lease/fence and serialize the approval-version check with revocation; commit `fetch_receipt`, artifact reference, the origin cache/validator update (only if recoverable), and a `parse_requested` outbox entry. ACK only after this transaction commits. If permission changed during the object put, reject acceptance and erase the now-disallowed object under the deletion contract. A prior object-only write is *orphaned*, not acknowledged capture.
4. **Revision transaction**: parse workers perform idempotent receipt processing. In one transaction, commit content revision, origin/occurrence provenance and `event_resolution_requested` outbox event.
5. **Outbox**: relay delivers at least once; consumers deduplicate by `(consumer, logical_event_id, version)`. Validate the current lease/fence inside the same transaction as every worker's effects and deduplication record; a check made only when claiming work is insufficient. No exactly-once network delivery claim.
6. **Reconcile**: scan unfinished attempts, orphaned objects, missing referenced objects, undelivered outbox work, and invalidated/deleted records. Audit all exception intervals.

```mermaid
sequenceDiagram
  participant S as Scheduler
  participant C as Collector
  participant P as Policy
  participant O as Object store
  participant D as PostgreSQL
  participant R as Outbox relay
  participant W as Parser /<br/>event worker
  S->>D: Insert due attempt + stable fetch_id
  C->>D: Claim attempt (lease/fence)
  C->>P: Check permission & safe origin
  P-->>C: Allow / block
  alt Approved
    C->>C: HTTP fetch bounded by shared origin budget
    C->>P: Recheck rights after fetch, before persistence
    alt Still permitted
      alt New permitted representation
        C->>O: Put immutable permitted envelope (conditional)
        O-->>C: Object key, checksum
      else 304 with valid permitted cache
        C->>O: Verify referenced cached object is recoverable
        O-->>C: Existing object key, checksum
      end
      C->>D: Transaction: validate fence and serialize rights<br/>receipt, object reference, cache validators, parse outbox
      D-->>C: Committed receipt or rejected acceptance
      alt Receipt committed
        Note over C,D: Ack only on committed recoverable receipt
        R->>D: Claim outbox with fencing
        R->>W: Deliver event (at least once)
        W->>D: Transaction: validate fence and dedup<br/>revision and downstream outbox, commit
        W-->>R: Ack after commit
      else Acceptance rejected
        C->>O: Erase disallowed orphan or reconcile permitted orphan
        C->>D: Persist policy-safe failure
      end
    else Revoked during fetch
      C->>D: Persist policy-safe failure, discard response
    end
  else Blocked/revoked
    C->>D: Persist policy-safe failure and stop
  end
  Note over O,D: Reconciler detects orphaned objects<br/>and missing references
```

## Failure matrix and recovery invariants

| Crash point | Expected recovery | Prohibited outcome |
|---|---|---|
| Before permitted object put | Retry due attempt if still authorized | Silent success |
| After put, before DB commit | Object is orphan; re-fetch/reconcile or expire within retention policy | Claimed captured article without DB reference |
| After receipt DB commit, before relay | Outbox worker resumes | Permanent unprocessed receipt |
| After worker DB commit, before ack | Idempotent redelivery | Duplicate revision/member/publisher count |
| 304 after cache object deleted | Invalidate validator, perform authorized unconditional fetch; mark gap if impossible | Claim usable unchanged representation |
| Restart during origin throttle | Persisted next_allowed_at still enforced | Thundering herd |
| Backup restore with missing objects | Reconcile and invalidate impacted cutoff windows | False PASS after partial restoration |

**Capture durability SLO** is defined by committed acknowledgments, not network response alone. Design target: **no silently lost acknowledged capture**; any unrecoverable receipt causes explicit invalidation of impacted snapshots. Define quantitative RPO/RTO only after testing WAL-backed point-in-time restore with matching immutable object versions and deletion records. The prior 24-hour metadata RPO is superseded, not accepted.

## Worker control and degraded history

Persist `origin_budget` keyed to provider-enforced scope (origin/account where known): next_allowed_at, retry budget, breaker state, failure category. Support both RFC-compliant Retry-After delay and HTTP-date, bounded exponential jitter, half-open probing, capped in-flight requests, and no IP/proxy evasion. Isolate collector, parser, event, snapshot, and inference CPU/connection pools. 429/503, timeouts, malformed data and rights revocation have distinct transitions. Stale successful feeds and large parser rejection rates are **DEGRADED**.

Record immutable `source_health_interval` including fetch freshness, original publication-to-receipt latency estimate (publisher timestamp caveats), parse/revision lag, missingness/rollover risk and downstream queue lag. A healthy later request **must not clear a historical gap**. Recovery bursts require warm-up exclusion and cannot be called organic article growth without evidence.

## Data and scaling

Write one lightweight receipt per valid fetch, but do not rewrite article revisions, syndication memberships or event features for unchanged bytes. A→B→A still yields three chronological *observations*, even where payload A is reused by checksum. Keep volatile queue state apart from immutable evidence. Monitor pending age, drain time, WAL bytes, DB contention, bloat, source lag and manifest latency. Consider partitioning and brokers only on measured thresholds; preserve uniqueness across partitions.

## Security boundaries

SSRF: allowlisted scheme/host/port, resolved IPv4/IPv6 destination checks, every redirect, pinned validated connection destination, deny-by-default network egress; apply to previews and article links. XML: disable DTD/entities; bound encoded/decompressed bytes, nesting, items, text, wall and CPU time and memory. LLM: untrusted text remains data; privileged trusted code validates output structure/citations, with zero credential or network privilege in summarization workers. Tenant separation and retention/deletion tests are release gates.

See [DATA_CONTRACTS.md](DATA_CONTRACTS.md), [DELIVERY_AND_VERIFICATION.md](DELIVERY_AND_VERIFICATION.md).
