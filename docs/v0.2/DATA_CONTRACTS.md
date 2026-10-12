# Data, identity, availability and event-resolution contracts — v0.2

**Normative for proposed implementation, not verified in a running system.**

## Eligible panel and rights

Every `source_manifest_version` MUST include effective approval interval, controlling owner ID, publication brand ID, original feed endpoint and access scope, retention/derived-data/training/link-display restrictions, attribution, polling and retry conditions, timestamp quality, expected feed rollover, allowed payload fields, approval actor, approval timestamp and revocation/deletion procedure. Check legal permission *before request* and at persistence. Unknown rights = BLOCKED. No full-text retention/model training by default. No substitution of government bulletins, mirrors or related brands to satisfy an independence gate. Panel version is immutable; additions constitute a new panel with separate study identity. Minimum three controlling owners is smoke eligibility only, not representativeness.

`source_manifest_version` is the per-source approval contract represented by SOURCE_POLICY_VERSION in the ER diagram. `panel_version`/SOURCE_PANEL_VERSION is the separately frozen set of eligible sources and their policy versions; the two scopes are not interchangeable.

## Entity identities (do not collapse)

```mermaid
erDiagram
 SOURCE_POLICY_VERSION ||--o{ FETCH_ATTEMPT : authorizes
 FEED ||--o{ FETCH_ATTEMPT : scheduled
 FETCH_ATTEMPT ||--o| FETCH_RECEIPT : yields
 PERMITTED_OBJECT ||--o{ FETCH_RECEIPT : referenced_by
 FETCH_RECEIPT ||--o{ FEED_ITEM_OBSERVATION : contains
 FEED_ITEM_OBSERVATION }o--|| PUBLICATION_OCCURRENCE : links
 FEED_ITEM_OBSERVATION }o--o| ARTICLE_REVISION : observes
 PUBLICATION_OCCURRENCE ||--o{ ARTICLE_REVISION : has
 CONTENT_FAMILY ||--o{ CONTENT_FAMILY_VERSION : evolves
 CONTENT_FAMILY_VERSION ||--o{ CONTENT_FAMILY_MEMBERSHIP : freezes
 ARTICLE_REVISION ||--o{ CONTENT_FAMILY_MEMBERSHIP : grouped
 ARTICLE_REVISION ||--o{ EVENT_MEMBERSHIP_VERSION : assigned
 EVENT ||--o{ EVENT_VERSION : evolves
 EVENT_VERSION ||--o{ EVENT_MEMBERSHIP_VERSION : contains
 EVENT_VERSION ||--o{ EVENT_TRANSITION : changes
 SOURCE_PANEL_VERSION ||--o{ SNAPSHOT_MANIFEST : qualified
 SNAPSHOT_MANIFEST ||--o{ SNAPSHOT_INPUT : freezes
 ARTICLE_REVISION ||--o{ SNAPSHOT_INPUT : referenced
 SNAPSHOT_MANIFEST ||--o{ PREDICTION_ISSUANCE : inputs
 MODEL_VERSION ||--o{ PREDICTION_ISSUANCE : scores
 SNAPSHOT_MANIFEST ||--o{ SNAPSHOT_INVALIDATION : affected_by
```

**Four different identity scopes:** (1) feed item GUID/URL observed in an individual feed, (2) publisher publication occurrence, (3) content or syndication family and original reporting lineage where known, (4) event/development. URL aliases and normalization algorithm version are preserved. Same syndicated story across publishers counts as separate occurrences for **distribution breadth**, but not independent origin content. Reused URL does not imply same revision/event. Publication edits append revisions; never overwrite old content. Deduplication keys must be versioned per source; `(feed_id, canonical_url_hash)` alone is insufficient.

The ER diagram covers accepted/parsed entities; malformed items remain receipt-level diagnostics. Each accepted feed-item observation references its observed revision when resolved, preserving A→B→A observation order independently of payload reuse. Content-family assignments use immutable membership versions; no later regrouping changes a frozen input. One recoverable object may back multiple receipts, including 304 receipts. Snapshot dependencies also freeze event/membership/family and transform versions; `SNAPSHOT_INPUT` is the article subset, not the complete dependency manifest.

## Time contract

| Time | Meaning | May establish historical availability? |
|---|---|---|
| `published_at` | Publisher claim, precision/timezone/confidence stored | NO |
| `received_at` | Network response evidence arrived at collector | Not sufficient alone |
| `recorded_at` | Durable receipt/revision event committed; persist observation order/commit witness | Candidate availability, only when operationally usable |
| `processing_available_at` | Derived state published for operational use | YES when included in committed snapshot |
| `effective_at` | A corrected fact's domain time | NEVER alone |
| `label_available_at` | Future outcome became complete and final for training | YES for model training only |
| `snapshot_issued_at` | Actual frozen forecast publication time with exact candidate/transform/artifact identities | Authoritative operational prediction; may be later than logical cutoff |

Transaction start timestamp is not proof of commit visibility. All times use UTC with precision and clock-quality metadata. At logical cutoff `t`, persist a committed visibility boundary and enumerate a consistent view of inputs with qualifying receipt and derived-state availability no later than `t`; a later build must use that boundary, never its current DB view. A backdated field cannot establish eligibility. Model, transform, alias and index artifacts must also have been available by `t`. Freeze exact IDs/checksums, followed by issuance without later reopening. A `snapshot_manifest` MUST include source panel version, health intervals, full candidate set (including unsuccessful candidates), permitted receipt/article revision IDs, event versions, membership versions, content-family rules/versions, IDF/index/entity-alias versions, feature schema and implementation hashes, all planned model/calibration identities, candidate/label/future-matcher policy versions and event anchors, logical cutoff and visibility witness, snapshot build timestamp and stable commit/issuance record identifiers, processing-lag state, and validity status at sealing. Commit witnesses and actual issuance timestamps are append-only records, rather than predictions of future commit/publication times inside the manifest. Later invalidations are append-only `SNAPSHOT_INVALIDATION` records referencing the frozen manifest; current validity is derived without changing its bytes/hash. A retrospective reconstruction is **not** evidence of a prediction actually issued at the historical cutoff.

If issuance occurs after `t`, preserve that delay. The research target retains `(t,t+24h]`, but operational lead time uses actual `snapshot_issued_at`; never attribute an alert before issuance. Any latency limit or exclusion is preregistered on development data, and missed/delayed cutoffs remain in the evaluation availability report.

## Logical uniqueness, immutability and races

Logical snapshot key: `(experiment_id, panel_version, cutoff_at, candidate_policy_version, snapshot_kind)`. A second attempt with a different manifest hash at that same logical key is **a determinism conflict requiring audit**, not an accepted additional historical version. If a legitimate rerun uses altered code/transforms, it gets a new experiment/run family and explicit relationship. `PREDICTION_ISSUANCE` references exactly one frozen snapshot and model version.

Paired methods share one frozen candidate/feature snapshot, whose manifest lists all planned method artifacts, including heuristic versions and random seeds. Each method has a separate issuance/result record and actual publication timestamp, unique by `(snapshot_id, method_version)`; never replace an issued result or append an unplanned method to the snapshot. Build metadata is frozen with the manifest; actual commit/issuance times belong to their append-only witness/issuance records. A retry reuses an existing committed logical snapshot and its metadata instead of resealing it with new build timestamps. Reproducibility/hash comparison concerns the committed manifest content, not a mutable aggregate of later issuance or validity records.

Event transitions use compare-and-swap `expected_predecessor_version`, transition ID, actor/model/reason and recorded time. A merge/split checks every affected predecessor head and writes all successor versions, memberships and lineage atomically; any mismatch aborts the entire transition. Merge and split create lineage links and reversible review actions; remove memberships through new versions instead of deleting history. Closed events can reopen only through an explicit new-development transition; collector outage alone must not cause inactivity closure.

`first_seen_at` is **derived from immutable qualifying receipt history**, not a mutable timestamp column corrected in place. Out-of-order receipts may change the *current* earliest justified observation, but released snapshots must remain untouched and any restatement gets an explicit version/audit record. A→B→A captures all three observed chronological states even if payload A is content-address-reused.

## Prefix invariance

For any issued cutoff `t`, capture original manifest and emitted outputs. Then append future receipts, edited headlines, alias updates, clustering merges/splits and parser upgrades. Re-verify that the original manifest, ranking, evidence and hash are byte-identical. If they differ, block release and investigate; do not silently repair historical predictions. Parser/schema/normalizer, alias tables and retrieval indexes are immutable or version-addressed inputs.

## Event granularity and resolution benchmark

An event represents a **specific action/development** with actors, location and relevant time, not a broad theme; a parent story may link multiple separate developments (announcement vs reversal). Benchmark lexical TF-IDF/character n-grams, Arabic morphological features, embeddings and hybrid systems on **permitted stored fields only**. Annotate chronological Arabic examples with variants, transliterations, near-identical official announcements, paraphrases, repeated headline templates, syndicated wire, evolving incidents and distinct developments. Preserve Arabic originals. Hold out content families and evaluate false merges, fragmentation, pairwise P/R, origin attribution and the downstream proportion of label flips/top-five changes. Predefine sampling, adjudication disagreement and thresholds before gate G2.

## Rights revocation / deletion

Revocation stops new access immediately and blocks acceptance of in-flight fetched content. Delete or expire disallowed artifacts, embeddings and derivative displays as required; retain only policy-permitted non-content audit traces. Enumerate impacted manifests and append invalidations rather than quietly recomputing missing historical evidence. Legal deletion takes precedence over retaining prohibited bytes: erase them, keep only allowed invalidation/audit metadata, and report replay as unavailable. Prefix invariance requires no silent rewriting; it does not authorize retaining erased content. Handle legal holds only on explicit authorized basis.

## Health and publication completeness

`OK`, `NO_CHANGE_VALID_CACHE`, `STALE`, `PARSER_DEGRADED`, `RATE_LIMITED`, `UNAVAILABLE`, `RIGHTS_BLOCKED`, `OWNER_UNVERIFIED`, `RECOVERY_UNCERTAIN` are distinct states. `304` is usable only when corresponding cached representation is durably recoverable. Poll success is not feed completeness. Persist missing intervals; distinguish unknown vs observed zero; recovered bursts may be measurement artifacts.

See [ARCHITECTURE.md](ARCHITECTURE.md), [FORECASTING_PROTOCOL.md](FORECASTING_PROTOCOL.md).
