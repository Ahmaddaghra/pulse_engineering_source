# M1 contract decisions and open issues

## Baseline observations (2026-10-12)

Requested base is `origin/docs/pulse-v0.2-review-integration` at
`d7d4eceb8ff0fa940370c8847ba6813f5b0af39f`. GitHub PR #1 was already merged at
2026-10-12T05:47:14Z before this implementation began; the pasted request describes an older state.
This work does not alter that PR or push to main. Original v0.1/v0.2 documents are preserved.

## Narrow interpretations recorded before affected implementation

- v0.1's monotone first-seen wording conflicts with v0.2's late-receipt correction contract.
  v0.2 governs: current first_seen is derived from qualifying receipt history; sealed snapshots retain
  their frozen value. No historical forecast is reconstructed.
- Original interpretation, superseded by PR #3 remediation below: publisher GUID plus publication
  timestamp identified an occurrence where present. URL-only or
  GUID-only identities are explicitly ambiguous. Same GUID and timestamp reused by a publisher
  cannot be disambiguated from an edit without additional licensed evidence. No news-event or
  independent-reporting identity is inferred from content equality.
- Metadata envelope fields only are durable. Raw XML is transient and resource bounded. A policy
  must permit metadata plus at least GUID or URL; observation derivation requires derived_allowed.
- Clock timestamps recorded inside a transaction describe insertion, not proven commit time.
  Separate postcommit observation witnesses delay operational availability safely after crashes.
  A snapshot seals the committed view while holding the shared evidence writer lock. Arbitrary
  retrospective cutoffs without an already stored visibility boundary are unsupported.
- Observed snapshots freeze references, checksums, times, first_seen and versions; they contain no
  article text or URLs. They are observation primitives, not the full future research manifest
  (events, models, features, aliases, labels and outcome matcher are out of scope).
- Offline approval actor and publisher/owner identities are fixture declarations, never legal
  approval of a real feed or evidence for G0 owner diversity.
- The local object store assumes a trusted private directory and one PostgreSQL instance. Its
  immutable keys include policy, fetch and fence; PostgreSQL/object writes have separate failure
  boundaries. No cross-store exactly-once guarantee is claimed.

## Qualification limits

M1 has no rights-qualified live panel, sustained operations, forecasting, event clustering,
content-family attribution, editorial workflow or dashboard. Docker execution and WAL/PITR
qualification are tracked separately from local PostgreSQL fault tests in M1_TEST_EVIDENCE.md.

## Remaining engineering work and specification gaps

| Item | State | Consequence / next verification |
| --- | --- | --- |
| Docker services locally | BLOCKED locally: Docker socket absent; hosted smoke PASS | Hosted CI executed image, migrations, capture/parser/seal and actual ASGI startup; local Docker remains unavailable |
| WAL/PITR and deletion-aware backup retention | BLOCKED / not configured | Logical restore passes; no production RPO/RTO or acknowledged-capture loss qualification |
| Approved-origin live TLS/DNS/egress drill | BLOCKED: no confirmed publisher permissions | Network controls tested with synthetic resolvers/sockets only; keep live disabled |
| Hard parser CPU/address-space sandbox and process quotas | NOT IMPLEMENTED | In-process structural/byte/time checks pass; isolated hostile-process exhaustion qualification remains |
| Production DB roles, immutable remote object versions and tamper-resistant audit | NOT IMPLEMENTED | Local development uses a trusted DB operator and private filesystem |
| Retention service operation and backup erasure | PARTIAL | Reconciler erases local expired/revoked bytes and derives invalidation; sustained erasure latency and remote/backup deletion need proof |
| Multi-tenant/user authorization | NOT IMPLEMENTED | Two bearer capabilities are a single-operator deployment boundary |
| Exact ambiguous occurrence identity | OPEN CONTRACT LIMIT | GUID or URL reuse cannot be resolved as edit vs new publication without extra evidence |
| Parser-version replay administration | PARTIAL | Version-addressed records and future-version invariance are tested; no general reparse/upgrade workflow |
| Content-family/event identity and downstream event outbox | OUT OF M1 SLICE | No inferred content families, events or event-resolution worker; full v0.2 event/research manifests unavailable |
| Coverage completeness and gap resolution | PARTIAL | All retained gaps stay visible and conservatively degrade results; no automatic completeness certification, closure, recovery warm-up or panel enrollment study |
| Throughput, fairness and lock contention | UNQUALIFIED | Synthetic throttling/backlog cases pass; all evidence reads/writes serialize on an advisory lock and reads verify retained history before paging |
| Production metrics/alerts and sustained service qualification | NOT IMPLEMENTED | DB/audit/API evidence exists; no prospective reliability, WAL/write amplification or latency benchmark |
| Forecasting, sentiment, opinion estimation, paid integrations and dashboard | INTENTIONALLY EXCLUDED | No code/outputs/claims for these capabilities |

`HEALTHY_EMPTY` means a valid, permitted, parsed offline observation checkpoint contains no items.
It does not mean no news existed, and it does not assert event/editorial candidate qualification.
The v0.2 editorial `NO_QUALIFIED_CANDIDATES` state requires later event/editorial logic and is not
misused here. Polling success alone never qualifies a publisher panel.

The XML transform is fixed as `xml-metadata-v1`; receipt/revision/manifest versions and an
implementation source hash are recorded. Historical seals are references to stored state, not
permission to recalculate old interpretations under changed code. Retrospective cutoff requests
are rejected. Legal erasure takes precedence over replay; invalidations preserve the original
manifest hash while payload replay becomes unavailable.

Retry-After is parsed as seconds or HTTP-date and capped at seven days. There is at most one
pending/leased capture per source and one active lease per shared rate scope. A real publisher's
longer prescribed retry conditions would require a policy revision before live operation.
Synthetic admission tests do not establish throughput or sustained fairness.

One installed Starlette/httpx test-client deprecation warning remains. The locked dependencies
work in executed tests; replacing the client should follow compatible FastAPI/Starlette guidance
and a separate dependency update, not expand this runtime's dependency surface during M1.

## PR #3 review remediation contract (2026-10-12)

The independent review of `e1284e729302ef4849042455791a38b8c1067974` identified timestamp-driven
occurrence splitting, error-body handling that discards 429/503 retry instructions, and case-sensitive
URL GUID display suppression. Regression tests accompany the fixes.

The revised identity transform `occurrence-v2` uses publisher-scoped opaque GUID, otherwise a
conservatively normalized URL; mutable publication time, precision and title remain revision data.
`normalization-v2` identifies this revised identity-resolution transform. Envelope parser/message
version `parser-v1` stays compatible with already queued requests; committed consumption prevents
old receipts from being reparsed automatically.

A unique retained, currently permitted legacy identity can be continued by future observations,
with an append-only audit reference. Legacy approval, artifact and receipt-retention deadlines
are checked again before new effects commit, including evidence from another source at the
same publisher. Legacy occurrences/revisions/observations and sealed snapshots
are never reassigned or edited. If old timestamp-based identities produce multiple compatible
candidates, the item is rejected as identity ambiguity with candidate IDs in policy-safe audit
records; another occurrence is not manufactured. GUID reuse and URL-only reuse remain unresolvable
without stronger source-specific identity evidence. Changing a timestamp alone cannot establish
an independent publication occurrence.

The project owner explicitly selected retargeting this draft to `main` after PR #1's merge. The
feature branch incorporates `origin/main` without rewriting earlier implementation/review commits.
No merge of PR #3 or live ingestion is authorized by this remediation.
