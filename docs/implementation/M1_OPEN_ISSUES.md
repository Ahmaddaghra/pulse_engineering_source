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
- Publisher GUID plus publication timestamp identifies an occurrence where present. URL-only or
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
