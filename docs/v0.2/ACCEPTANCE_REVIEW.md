# Specification acceptance review — PR #1 / v0.2

**Date:** 2026-10-12

**Decision:** ACCEPTED engineering specification. The checks below passed with no remaining blocking specification contradiction; merge is authorized by the project owner's Step 1 instruction.

**Scope:** repository engineering specification, diagrams and documented contracts. Source enrollment, runtime reliability, measured model lift and newsroom value require separate gate evidence.

The project owner explicitly requested review and merge of PR #1 if these checks pass. This record accepts a documentation baseline only. The v0.1 blueprint, scripts and diagram assets remain the historical baseline; root README routes planning to v0.2.

## Corrections made before acceptance

| Area | Issue in review candidate | Resolution |
|---|---|---|
| Capture / diagrams | Post-fetch permission recheck and object-store reconciliation were not fully shown; claim-time fencing alone could permit stale effects; Mermaid separators broke transaction/state labels | Show recheck and valid-cache branches, both object/DB reconciliation inputs; require transaction-time fence and serialized permission checks, with deletion on revoked acceptance; correct sequence syntax and unintended disconnected editorial states |
| Identity | Observation-to-revision and content-family regrouping could lose A→B→A or change frozen inputs; model comparisons were ambiguous under one logical snapshot key | Preserve observations separately from reused payloads; version family memberships and freeze dependency identities; share one snapshot across preregistered methods with separate immutable issuance records |
| Temporal state | Logical cutoff could be confused with a later consistent DB view or issuance | Freeze a committed cutoff visibility boundary; exclude later operational/artifact state; record actual issuance and use it for lead time |
| Invalidation / deletion | In-manifest invalidation flags conflicted with byte-identical frozen history and legal erasure | Append external invalidation records; never rewrite manifest bytes; erase disallowed content and report unavailable replay |
| Label | A zero/negative delta threshold could satisfy the formula without growth; first-observation counts and late receipts were underspecified | Require positive integer thresholds; count each publication occurrence once with controlling-owner breadth; use fixed past count/matcher, exact windows and completeness of both windows |
| Lead time | Threshold crossing and label maturation could be confused | Define earliest cumulative crossing of the three fixed predicates; measure lead time from actual issuance, retaining late/negative lead times |
| Editorial/API | Operating mode and evidence status overlapped; degraded example had no gaps; snooze and post-coverage transitions were absent | Separate mode/evidence/health, define fail-closed precedence and forecast-field gating, supply a consistent healthy-empty example and complete action transitions |
| Authority / assumptions | Review-candidate status and proposed ADRs did not establish one planning authority; required signoffs and review-source limitations were implicit | Route root README to v0.2; accept design ADRs conditionally on this review; record A01–A10 and gate-specific specialist signoffs |
| Historical traceability | Register implied v0.1 explicitly permitted holdout-based selection | Correct to ambiguity in “best baseline” wording; retain its sealed-evaluation intent and make development-only selection explicit |

## Validation evidence

| Check | Executed result / scope |
|---|---|
| Mermaid syntax/rendering | All five embedded diagrams rendered with Mermaid CLI 12.0.0 / Mermaid core 12.1.0 using local Chrome; rendered images inspected for labels, unintended nodes and contract agreement. This is local rendering, not a claim of GitHub CI execution or a guarantee of its deployed renderer version. |
| Growth/count/window examples | 19 synthetic cases: growth/count/breadth floors, inclusive boundaries, invalid zero/negative/non-integer thresholds, incomplete labels, exact half-open windows, A→B→A observations, related-brand owners and syndication distribution vs reporting diversity. Passed as checks of documented semantics. |
| API examples and precedence | All 16 usable-evidence/gap/candidate/forecast-release combinations satisfy the written precedence and probability gating; illustrative JSON parses and matches a healthy-empty response. Passed as documentation examples, not server contract tests. |
| Links / formatting | All local Markdown links in root README and v0.2 package resolve; code fences balance; `git diff --check` passes. |
| Historical preservation | Git diff against base `7badece806cf28af8ba2de85844191201d86641c` confirms no edits to PULSE_BLUEPRINT.md, original diagrams, Python build scripts or stylesheet. |
| Cross-document review | Receipt/ACK/fence/revocation, immutable temporal/identity dependencies, label maturation/holdout, API failure states, gate dependencies and open assumptions reconciled. No remaining blocking specification contradiction identified after corrections. |
| CodeRabbit | Authenticated CLI review completed with **0 issues** across all ten changed files at substantive specification commit `b6d1c79`. Command: `coderabbit review --agent -t committed --base-commit 7badece806cf28af8ba2de85844191201d86641c`. The subsequent commit records this acceptance/status result without altering substantive contracts or diagrams. |

Rendering command per extracted Mermaid fence: `npx --yes @mermaid-js/mermaid-cli@12.0.0 -i diagram.mmd -o diagram.png -p puppeteer.json --size 2400`; Puppeteer config selected the installed Chrome executable. The mathematical/API cases are synthetic specification exercises. No runtime collector, database, migration, recovery drill, source permission verification or forecasting evaluation was executed; the adversarial matrix remains mandatory implementation work.

## Acceptance limits and handoff

[ASSUMPTIONS.md](ASSUMPTIONS.md) records ten open premises/decisions with responsible roles, required evidence and blocking gates. G0 remains HOLD; G1–G5 remain unqualified. Required data/legal, ML and newsroom/domain signoffs remain open for their respective live/research gates. Original source reviews and Phase 1–1C raw evidence were unavailable for independent comparison; the register and prior phase claims remain explicitly qualified.

[README.md](README.md) and its linked package are the single accepted v0.2 planning authority. FORECAST_QUALIFIED, model training, live source access and production deployment still require their documented gates; this PR supplies no measured acceptance evidence for them.
