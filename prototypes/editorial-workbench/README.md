# PULSE editorial workbench

An offline, Arabic-first product prototype of the evidence-backed editorial workflow in the [v0.2 specification](../../docs/v0.2/README.md). All publishers, observations, developments, recommendations and projections are fictional. This does not connect to the M1 backend or qualify any operational/research gate.

## Open

Open `index.html` directly in Chrome or Safari. No server, install, account, network request or API key is needed. Keep `styles.css`, `data.js` and `app.js` alongside it. The interface starts in Arabic RTL; **English** switches the entire interface to LTR. All changes live in memory and disappear on reload. **Reset Demo** restores the initial workflow, quality state, filters and research settings.

## A 3–5 minute team walkthrough

Choose **Guided Demo**; use Next/Back and exit at any time.

1. **Discover (40 sec):** review the airport shuttle scenario. Compare publisher breadth, reporting origins and verification status. Every scenario is fictional, not an actual Saudi announcement.
2. **Inspect (50 sec):** open event intelligence, switch the 6-hour/24-hour/7-day observed activity windows, and read original versus syndicated evidence.
3. **Decide (30 sec):** read the illustrative editorial opportunity and unresolved claims. Support outputs require a human decision.
4. **Act (40 sec):** assign to an editor or watch. Request verification, snooze, dismiss and mark already covered are also supported. The workspace and activity history update immediately.
5. **Research (45 sec):** compare a hypothetical 24-hour coverage scenario with a simple momentum continuation. The shaded band is a scenario range, not a statistical confidence interval. Other horizons are future design concepts.
6. **Explain (40 sec):** follow the observed pipeline and separately gated research branch. Coverage, attention and opinion have different measurement contracts.

Optional: in Source Health, degrade Publisher A. Historical observations remain; related evidence gets a gap warning and the affected hypothetical projection becomes unavailable. Restoring A does not erase the recorded gap; Reset Demo starts a clean fictional session.

## Simulated behavior

- Five fictional Saudi-relevant developments across transport, technology, sports, culture and economy; six fictional publisher brands and four fictional controlling-owner groups.
- Local editorial state, editor selection, verification queue, watch list, recorded snooze deadlines, dismissal, already-covered state, restore-to-review action and activity history.
- Search and beat/status filters, event selection, observed timeline windows and keyboard-focusable chart points.
- Source health and gap simulation. Unknown completeness, unavailable data, delayed feeds and known zero observations remain distinct. Positive historical observations are never deleted or invented by a source control.
- Fixed scenario projections with no probabilities, calibration or performance claims. Only the 24-hour growth outcome is the initial research target. No projection predicts a new incident.
- Fixed observation checkpoint: 12 October 2026, 15:00 Riyadh (UTC+03:00). Action timestamps use the current session clock. The checkpoint is illustrative, not live freshness.

## What the actual MVP requires

Follow the authoritative v0.2 documents; this UI replaces none of their contracts. The intended MVP needs rights-qualified source policies and owner identity (G0); durable receipts, permitted object storage, transactional outbox, bounded workers and replayable provenance (G1); adjudicated Arabic event identity, versioned article/event/syndication membership and origin uncertainty (G2); tenancy, permissions, idempotent editorial actions, human control and a measured workflow-utility study (G3). Source freshness, missing intervals, retention/deletion and evidence availability must be enforced. AI may assist Arabic matching, event detection, lineage analysis and evidence-bound explanations; it has no privileged write/network role.

## Research only

Forecasting remains **HOLD**. G4 requires feasible frozen 24-hour growth labels and development baselines; G5 requires prospective sealed evaluation and incremental editorial utility. Statistical forecasting may use conventional ML, not LLM guesses. Production probabilities remain absent until independently qualified. Incomplete windows are unscorable, not negative outcomes. Publication breadth is not independent corroboration, audience attention or public opinion.

## Known limitations

No live news, genuine permissions, authenticated users, shared assignments, database, durable audit, model, scientific validation, real-time updates or automatic publishing. Evidence and recommendations are scripted examples. Source restoration retains simulated historical gaps; no historical completeness repair is implemented. The snooze deadline uses the session clock and resumes to Watching while the page is open; browser suspension may delay it. Local state is single-user, not a production concurrency contract. System fonts vary by OS; no remote fonts or assets are requested. Desktop is primary; mobile uses horizontal navigation and single-column panels.

Browser verification evidence is recorded in the pull request. Chrome/Chromium and Safari/WebKit coverage should be distinguished; browser automation is not a claim of a newsroom utility study.

## Browser verification

Playwright Chromium opened the entry point through `file://`, with no HTTP requests or console/page errors. 78 browser assertions passed, including all navigation, Arabic/English search, filters, timeline windows, all editorial actions, native dialog Escape handling, automatic snooze expiry (with browser-clock advancement), baseline/horizon controls, quality degradation, retained gaps, reset and the complete guided demo. Desktop 1536×1024, laptop 1280×800 and mobile 390×844 were checked. Safari/WebKit was not tested because its runtime was unavailable. No dependency is needed to open the shipped prototype.

The desktop render was compared to the generated visual concept at 1536×1024: right-side navigation, navy/teal palette, heading/control typography, editorial row hierarchy and source-health ring were inspected. Intentional refinements: a fourth health metric, explicit fictional/unverified wording, ownership/lineage counts derived from evidence, additional gap warnings, and scrolling to retain all requested editorial explanations. No decorative raster assets are used in the UI.
