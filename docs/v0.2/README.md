# PULSE Engineering Blueprint v0.2

**Status:** ENGINEERING SPECIFICATION / NOT IMPLEMENTED / Forecasting HOLD

**Date:** 2026-10-12

**Supersedes for planning:** v0.1, without modifying or erasing its historical source files.

**Change authority:** PR #1, subject to the specification acceptance recorded in [ACCEPTANCE_REVIEW.md](ACCEPTANCE_REVIEW.md). Operational/data/research gates require their own evidence and signoffs.

## Executive decision

PULSE is first an **evidence-backed editorial decision support service**, with an independently gated 24-hour **publisher-panel coverage growth** research component. The primary operational outcome is *better editorial decisions per unit of editor time*, not future article volume. PULSE does not measure national public opinion, and publisher coverage is not a proxy for Saudi residents' views.

**Keep:** modular monolith (one codebase), PostgreSQL, independent bounded workers, append-only evidence, human editorial control.

**Change:** make transaction/recovery and as-of interpretation contracts enforceable; separate publication, syndication and event identities; formalize a real growth target; prove data/label feasibility on chronological development data before training; separate immediate observed alerts from 6-hour forecasting cutoffs.

**Stop:** claims of observed predictive lift, customer willingness to pay, or verified superiority over NewsWhip/Feedly/Meltwater/Lucidya. Previous Phase 1–1C outcomes remain HOLD, as reported by the team, and were not re-audited from raw files here.

## Authoritative v0.2 package

| Artifact | Purpose |
|---|---|
| [REVIEW_REGISTER.md](REVIEW_REGISTER.md) | Every material review finding, disposition, change and verification path |
| [ARCHITECTURE.md](ARCHITECTURE.md) | Deployment and failure boundaries; capture transactions; identity/versions; diagrams |
| [DATA_CONTRACTS.md](DATA_CONTRACTS.md) | Rights, provenance, cutoff snapshots, event-resolution and retention contracts |
| [FORECASTING_PROTOCOL.md](FORECASTING_PROTOCOL.md) | Eligibility, true coverage growth, baselines, temporal evaluation, inference |
| [EDITORIAL_WORKFLOW.md](EDITORIAL_WORKFLOW.md) | User decisions, distinct observed/forecast states, product benchmark and APIs |
| [DELIVERY_AND_VERIFICATION.md](DELIVERY_AND_VERIFICATION.md) | ADRs, risk ownership, gate acceptance, test matrix, staged work plan |
| [ASSUMPTIONS.md](ASSUMPTIONS.md) | Unresolved premises, responsible roles, evidence needed and blocking gates |
| [ACCEPTANCE_REVIEW.md](ACCEPTANCE_REVIEW.md) | Specification review scope, corrections, checks and acceptance decision |

These are **design specifications**, not implemented artifacts. Diagrams are Mermaid source embedded in the Markdown files, rendered by GitHub. Their identities and contracts are normative when marked MUST; examples are not operational evidence.

## Critical system boundaries

- **C — Coverage:** publisher-panel *first observed publication occurrences*, conditional on eligibility and completeness. Distinguish owner distribution from independent originating reporting.
- **A — Attention:** licensed/search-platform aggregate interest; optional, distinct observational and prediction protocol with separate ground truth.
- **O — Opinion:** representative research with a declared sampling frame only; neither C nor A can be relabeled opinion.
- **Operational intelligence:** prompt observed changes to editors, even if forecasts are blocked, only where permitted evidence exists. Never hide degraded source history.
- **Predictive research:** already observed event candidates only; no prediction of unknowable incidents; immutable issuance records; no production probability until sealed validation.

## Dependency gates

G0 source authorization/owner diversity → G1 durable capture and reproducible temporal state → G2 adjudicated Arabic event identity → G3 observed editorial workflow benefit → G4 feasible frozen label & development baselines → G5 prospective sealed forecast and incremental editorial utility.

Each gate has its own **GO / HOLD / KILL** verdict; qualifying a downstream live capability also requires its prerequisite gates. G3 does not imply G5. If G3 wins and G5 fails, retain an honestly named monitoring product. If source rights are blocked, stop network capture and use lawful fixtures for software checks, never invented measurements. Gate numbering in this v0.2 package supersedes v0.1; do not mix the older G3-label/G4-forecast/G5-utility names with these gates.

## Review acceptance checklist

- Every review point is traceable, with unverified premises explicitly noted.
- The architecture/sequence diagrams cover outbox, object-store reconciliation and failure boundaries; the ER, research and editorial diagrams agree with their corresponding version and state contracts.
- Freshness is measured end-to-end as publisher-to-editor delay, not scheduler punctuality only.
- Every submitted forecast has a frozen candidate population and content/feature/transform identity.
- Coverage-surges require **growth**, not merely future volume; missingness is never a negative label.
- No final-test metric may be used to tune thresholds, feature selection or models.
- Observed alerts and forecasts are distinct services; data-quality degradation affects them differently.
- Every released metric reports cutoff denominators, incidents, coverage exclusions and uncertainty.

## Status and handoff

This package is the engineering planning authority after specification acceptance. No runtime source integrations, database migrations, models, scheduler, customer interviews or deployments were created. Exact numerical release thresholds must be preregistered **after development feasibility measurements**, before final evaluation, not invented in this document. All operational gates remain unqualified; unresolved assumptions and required specialist signoffs are recorded in ASSUMPTIONS.md.

**Original baseline:** [PULSE_BLUEPRINT.md](../../PULSE_BLUEPRINT.md).
