# Delivery plan, architecture decisions and verification matrix — v0.2

This work is **documentation only**. The following are release gates, not assertions that tests passed.

## Architecture decision updates

| ADR | v0.2 decision | Status |
|---|---|---|
| ADR-001 | KEEP modular monolith, isolated workers; durable PostgreSQL outbox/leases mandatory; broker only if measured fan-out/backlog/recovery justifies | Accepted design |
| ADR-002 | REVISE receipt, processing availability and committed snapshot semantics; publication time is only publisher claim | Accepted design |
| ADR-003 | KEEP C vs A vs O separate estimands | Accepted design |
| ADR-004 | REVISE publication occurrence / content family / event/development identities and append-only CAS lineage | Accepted design |
| ADR-005 | REVISE target/baselines on chronological development only; no final holdout opening for candidate selection | Accepted design |
| ADR-006 | KEEP honest OBSERVED_ONLY fallback; never conflate no candidates and no available evidence | Accepted design |
| ADR-007 (new) | Require durable capture high-watermarks, reconcilers, WAL/PITR verified with object versions and deletion logs | Accepted design |
| ADR-008 (new) | Observed news-desk lane precedes optional predictive release, separate from 6-hour cutoff | Accepted design |
| ADR-009 (new) | Unusual panel coverage GROWTH label requires positive delta and count/breadth floors; thresholds development-frozen | Accepted design |

## Gated work breakdown (estimates conditional on evidence)

| Gate | Deliverable / work | Objective acceptance and stop condition |
|---|---|---|
| **G0 RIGHTS** | owner hierarchy, authorized metadata scope, rate limits, live feed probe, source/panel manifest | >=3 independently controlling owners only for smoke eligibility, no known rights conflict, timestamps and freshness examined; otherwise HOLD |
| **G1 CAPTURE** | PostgreSQL schema + migrations; bounded collectors; receipt/object/outbox protocol; replay/reconcile, health intervals and PITR drill | Every acknowledged capture recoverable or explicitly invalidated under injected crashes; healthy sources not starved; no gap silently represented as zero |
| **G2 EVENTS** | Arabic annotation guideline and sample, three identity layers, lexical/embedding/hybrid experiment, CAS transitions | independently adjudicated quality gate preregistered; label flips/top-five perturbation and false merges examined; otherwise HOLD |
| **G3 EDITORIAL** | observed alert stream, evidence view, action/assignment state, competitor/manual timed tasks | measured utility versus accessible baselines including cost; if proxy-only, qualified evidence with limitation, not customer validation |
| **G4 LABEL FEASIBILITY** | freeze candidates, true growth label, mature labels, development folds, baselines, dependence/power audit | credible independent positive incidents and estimable effect; else HOLD without M3 training |
| **G5 FORECAST VALIDATION** | sealed prospective evaluation and independent audit; calibration/false-alert/lead-time; incremental desk outcome | practical lift with predeclared paired uncertainty plus incremental workflow gain; otherwise forecast remains unreleased |

**Scheduling:** G0 permissions may have unbounded lead time; implementation should not assume 1–2 weeks. G1/G2 can develop on explicitly synthetic/offline *software fixtures* independently of live access, but fixtures never establish source feasibility, ML accuracy or customer value. G3 may use authorized recorded evidence. G4/G5 require a mature time series: a 56-day test is a design candidate, potentially insufficient for rare independent incidents. Do not give a fake fixed release date.

## Mandatory adversarial demonstrations

| ID | Injected condition | Required invariant |
|---|---|---|
| T-CAP-01 | crash after upload before DB commit | orphan reconciled; no acknowledged-but-missing artifact |
| T-CAP-02 | crash after DB/outbox commit before relay | pending work resumes |
| T-CAP-03 | duplicate delivery, lease expiry and stale worker commits | fencing/idempotency; at most one logical effect |
| T-CAP-04 | restore PITR with missing object/erasure marker | invalidate impacted results, no silent repaired history |
| T-CAP-05 | 304 with lost validator's stored representation | disallow implicit unchanged qualification |
| T-TIME-01 | delayed earlier receipt vs later processed receipt | freeze issued snapshot; correction has new version |
| T-TIME-02 | late title edit, IDF/alias/index upgrade, future cluster merge | prefix-invariant candidate/features/predictions |
| T-TIME-03 | reused URL, same wire across publishers, A→B→A | all identities/counts/chronology correct |
| T-TIME-04 | race two event transitions at one predecessor | only one CAS winner, audited lineage |
| T-SRC-01 | concurrent 429/503 + Retry-After HTTP-date and delay + hostile feed | shared budgets, bounded retries, fair service for healthy sources |
| T-SRC-02 | parser CPU/memory/XML bomb, SSRF redirect/rebinding, source revocation midflight | no boundary breach or forbidden content persistence |
| T-ML-01 | sparse positives, shared incidents, multiple overlapping cutoffs | qualified prevalence/power and blocked invalid inference |
| T-ML-02 | holdout opened for selection, immature label used in fitting | evaluation must fail closed |
| T-ML-03 | outage recovery burst and incomplete panel | no false surge labels |
| T-PROD-01 | source degraded, no observations, no suitable candidates, repeated alert | distinct API states and bounded repeat burden |
| T-TIME-05 | build/issuance after logical cutoff; later model/alias artifact | exclude later state, report actual lead time and missed/delayed cutoffs |
| T-TIME-06 | revocation/deletion after issued manifest | append invalidation without rewriting hash; erase prohibited bytes and mark replay unavailable |
| T-ML-04 | zero/negative delta threshold; equality/window boundaries; repeated occurrence | reject invalid thresholds; count each occurrence once; score only complete windows |
| T-PROD-02 | mode/health/evidence combinations; snooze expiry and new development after coverage | deterministic status precedence, forecast fields gated and explicit action transitions |

## Stage deliverables / owner responsibilities

Backend/data engineer owns G0 integration design, G1, point-in-time infrastructure, operational observability. Applied ML engineer owns G2, G4/G5 and independent metric reproducibility with second reviewer. Product/UI owner owns G3, competitive comparison and accessibility. A source-rights/data-steward signoff is a separate required authority; three contributors alone cannot claim it.

Recommended repository implementation packages once gated: `contracts/`, `apps/api/`, `apps/web/`, `services/collector/`, `services/events/`, `services/forecast/`, `research/protocols/`, `research/evaluations/`, `infra/`, `tests/`. These directories are NOT created by this documentation PR.

## Review/merge rules

- Specification acceptance authorizes this documentation baseline only. Before their respective live/research gates, require review of rights and retention contracts by qualified data/legal reviewer (G0), audit of leakage/target by ML reviewer (G4/G5), and confirmation of editorial decision requirement by domain reviewer (G3). These unresolved signoffs are tracked in ASSUMPTIONS.md; a documentation merge grants none of them.
- CI when implemented: Markdown link check, Mermaid syntax, schema validation, static checks, migration smoke, offline failure/temporal tests. Do not mark tests green without executing them.
- Avoid claiming “exactly once” across DB/object storage or external delivery; use idempotent effects, reconciliation, and explicit invalidation instead.
- Merge PR #1 only after its specification checks pass under the project owner's explicit Step 1 authorization. Keep v0.1 source/diagram files as the historical baseline, and point the root README at the accepted v0.2 package. Do not enable unattended auto-merge or infer runtime release authorization.
