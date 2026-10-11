# Three-review disposition and traceability register

This is an *engineering change register*, not a claim that findings are fixed in running code. Review identifiers are local to this document. Source reviews were supplied by the project owner. Status **SPECIFIED** means described here but not implemented or tested.

| ID | Reviewer / severity | Finding | Decision / destination | Verification required |
|---|---|---|---|---|
| R1-01 | Architecture / critical | DB/object-store/worker handoff has no durability contract | ACCEPT → ARCHITECTURE: attempt ledger, object receipts, same-transaction outbox, recovery, fencing | Crash matrix and restore drill at each boundary |
| R1-02 | Architecture / critical | Identity and temporal versions underspecified | ACCEPT → DATA_CONTRACTS: revision ledger, distinct times, manifest dependencies | A→B→A, late edits, replay invariance |
| R1-03 | Architecture / high | Feed starvation and shared 429/503 throttling | ACCEPT → ARCHITECTURE: persisted origin budgets, isolated pools, gap history | Fault load with one hostile feed |
| R1-04 | Architecture / high | 24-hour capture RPO untenable | ACCEPT → DELIVERY: acknowledged-capture loss budget and PITR | Reconciliation to capture high-watermarks |
| R1-05 | Architecture / high | Polling drives unnecessary write amplification | ACCEPT → ARCHITECTURE: immutable new receipts vs deduplicated unchanged revisions, operational capacity metrics | Write/WAL/queue benchmark before partitioning |
| R1-06 | Architecture / high | ETag/304 recovery & SSRF/XML/LLM privileges | ACCEPT → DATA_CONTRACTS and ARCHITECTURE | 304 missing cache, SSRF rebinding, parser limits, untrusted text tests |
| R1-07 | Architecture / high | Merge/split/closure state and uniqueness collisions | ACCEPT → DATA_CONTRACTS: transition CAS, lineage, logical snapshot key | Race tests, reassignment and closed-event update tests |
| R2-01 | ML / critical | Upper quantile does not ensure positives; future volume is not surge | ACCEPT → FORECASTING_PROTOCOL: increase plus volume and breadth; prevalence feasibility | Frozen label audit on development period |
| R2-02 | ML / critical | Availability and transformations leak across historical cutoffs | ACCEPT → DATA_CONTRACTS and FORECASTING_PROTOCOL | Prefix invariance and model/transform as-of audit |
| R2-03 | ML / high | Training may see immature labels; final holdout may drive model selection | ACCEPT → FORECASTING_PROTOCOL: label availability predicate and chronological development | Walk-forward fold audit; untouched final test |
| R2-04 | ML / high | Overlap/rare incidents invalidate naive independent-day bootstrap | ACCEPT → FORECASTING_PROTOCOL: incident and contiguous block analysis | Dependence diagnostics and sensitivity report |
| R2-05 | ML / high | P@5 and Brier alone inadequate | ACCEPT → FORECASTING_PROTOCOL: ceiling, false alerts, unique incidents, calibration skill | Independent denominator reproduction |
| R2-06 | ML / high | Arabic event matching and syndication not independently benchmarked | ACCEPT → DATA_CONTRACTS: three identities, action-time-location event definition | Chronological adjudicated Arabic dataset |
| R2-07 | ML / high | Recovered RSS bursts may mimic organic news growth | ACCEPT → ARCHITECTURE and FORECASTING_PROTOCOL: completeness eligibility and warm-up | Simulated outage/rollover data |
| R3-01 | Product / critical | Coverage increase ≠ useful editorial decision | ACCEPT → EDITORIAL_WORKFLOW: decision time/value primary outcome | Timed comparative editorial task test |
| R3-02 | Product / high | Evidence cards and predictions are competitive parity | ACCEPT → EDITORIAL_WORKFLOW: native product comparison and build-vs-buy | Benchmark against commercial and simple tools; no unsupported differentiation |
| R3-03 | Product / high | Three feeds/owner panel not robust; latency and rights uncertain | ACCEPT → DATA_CONTRACTS and DELIVERY: enrollment and panel resilience | Permission, ownership, latency, outage study |
| R3-04 | Product / high | Six-hour cutoffs too slow for live desk | ACCEPT → ARCHITECTURE and EDITORIAL_WORKFLOW: observed change stream independent from forecast cadence | Alert lifecycle tests and timeliness measurement |
| R3-05 | Product / high | Top-five reading UI lacks workflow actions | ACCEPT → EDITORIAL_WORKFLOW: verification, assignment, snooze, dismissal, shared status | Task completion and repeat alert burden |
| R3-06 | Product / high | Incomplete panel: ambiguous empty output | ACCEPT → EDITORIAL_WORKFLOW: distinct NOT_AVAILABLE / NO_QUALIFIED_CANDIDATES / OBSERVED_ONLY | API state-machine contract tests |
| R3-07 | Product / high | Seven days qualifies smoke, not sustained operational value | ACCEPT → DELIVERY: smoke gate separate from reliability evidence | Extended prospective health/latency evidence |

## Explicit disagreements and decisions

1. **Original ADR-005 vs Review 2:** Reject use of the final holdout to choose baselines, target, preprocessing, M3 or tuning. Use only chronological development selection; reserve the final test once, and acquire a new one if compromised.
2. **Original surge label:** Reject high future volume as synonymous with surge. Rename a volume-only analysis HIGH_FUTURE_COVERAGE; use growth for the primary candidate target. No numeric thresholds endorsed until feasible on observed development data.
3. **Three owners:** Retain as *minimum G0 smoke eligibility*, not evidence of representativeness, independent reporting, uptime or useful newsroom latency. Enlarge or reject the panel on evidence.
4. **Database architecture:** Keep ADR-001. Broker adoption is a measurement-driven decision. A modular monolith can have separate deployed workers and a DB outbox.
5. **Commercial path:** Observed-only editorial utility precedes optional trained forecasting. With no access to editors, run proxy task tests and disclose the external-validity limitation; neither interviews nor procurement evidence are fabricated.
6. **Public opinion:** Explicitly out of operational and predictive MVP scope. No population claim from articles, search or posts.

## Source mapping

- Review 1: 149 lines, architecture/recovery review supplied 12 Oct 2026.
- Review 2: 169 lines, ML/temporal/evaluation review supplied 12 Oct 2026.
- Review 3: 114 lines, newsroom/product review supplied 12 Oct 2026.
- Baseline source: v0.1 Sections 1–13 and diagrams 01–09, in repository root.

The review texts were not added verbatim to this repository; this register records their technical findings and our dispositions. References in v0.1 remain supporting materials rather than new measurements.