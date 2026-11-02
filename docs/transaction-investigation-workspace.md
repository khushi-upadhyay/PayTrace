# Transaction investigation workspace

The authenticated `/transactions` workspace joins the existing payment ledger, payment lifecycle API, and browser session replay flow. `/payments` and the existing payment detail pages remain available.

## Data path

- `GET /api/v1/payments` supplies server-filtered, server-paginated, server-sorted payment rows. The workspace requests 100 rows at a time; status, source, and search filters run in the database.
- `GET /api/v1/payments/workspace` supplies database aggregates and a bounded sample of at most 500 recent rows for AG Studio. All-time counts, rates, currency totals, event latency, and daily volumes are computed from persisted records. Missing latency stays `null` and is shown as “No data”.
- `GET /api/v1/payments/{id}` and `/timeline` supply the selected payment and its persisted lifecycle events.
- `GET /api/v1/sessions/{id}/replay` supplies the associated recording and safe structured events. The panel links to the existing full replay player.
- Endpoint correlations use session events with an exact `payment_id`; they describe observed association only. Query strings are removed before endpoint aggregation.
- There are no schema or migration changes.

## Grid and dashboard capabilities

The transaction explorer uses AG Grid React 36 Community for sorting, floating and column filtering, multi-sort, column resizing/reordering/visibility, row selection, and CSV export. Grid column state and named server-filter views are saved in local storage. Persisted payment fields sort server-side; event-derived latency and floating filters operate on the bounded current page.

AG Studio 3.0 is embedded in the Analytics Studio tab with a persisted editable report, actual transaction and correlated network-event sources, declared one-to-many relationships, status, daily volume, provider, and endpoint charts, and linked cross-filtering. The Studio grid sample is explicitly bounded to the latest 500 records while status, daily-volume, provider, and workspace KPI datasets are all-time. Correlated network events are bounded to the latest 5,000 matching events.

AG Studio is a commercial package. The dependency permits local evaluation without a key; a commercial/trial license is required for production use. Local development can evaluate it without a key. Production builds keep Studio disabled unless `NEXT_PUBLIC_AG_STUDIO_LICENSE_KEY` is supplied; set this at build time and use a valid deployment/trial key. Its AI Agent Framework is **not configured**: this repository has no `AI_API_KEY` configured in the current environment and no AG Studio LLM adapter was added. Existing per-payment AI investigation remains available from the payment detail route. The workspace does not claim to provide natural-language analytics.

Grouping and integrated charts are Enterprise capabilities. Users can use the AG Studio dashboard builder and its included grid/chart widgets during local evaluation. The standalone transaction explorer is configured with Community modules.

## Findings

The workspace currently flags repeated failed transactions sharing a customer reference and payment events with recorded latency of at least 2 seconds. Findings link to actual payment IDs and describe evidence; they do not infer a causal root cause.

Payment method and completed-at timestamps are not fields in the current payment model and are not fabricated in the UI.

## Browser SDK direction (architecture only)

The current Demo Store/ShelfSwipe instrumentation already has separable building blocks, but they remain app-owned code and are not yet a reusable or published SDK:

- Session and tab identity: `frontend/lib/session-identity.mjs` plus its tests.
- Safe fetch/XHR and console instrumentation: `frontend/lib/session-instrumentation.mjs`.
- Event buffering, durable outbox, retry policy, and expiry recovery: `frontend/lib/session-outbox.ts`, `frontend/lib/session-buffer-policy.mjs`, and `frontend/components/session/SessionRecordingProvider.tsx`.
- rrweb capture, privacy masking, lifecycle ingestion, and playback: `frontend/components/session/SessionRecordingProvider.tsx`, `frontend/lib/session-recording-policy.mjs`, and `frontend/lib/session-playback.mjs`.
- Payment correlation: existing payment/order/session IDs in `frontend/lib/api.ts` and backend event schemas.

Recommended extraction sequence: define a browser-safe transport/config contract; move identity and instrumentation into a package-independent core; keep recorder/outbox as optional modules; expose explicit custom-event and payment-correlation APIs; document masking and consent defaults; then test in external sample apps before packaging. Project/environment credentials should identify an ingestion project, never contain provider secrets. Ingestion authentication, origin controls, retention, and server-side rate limits must be designed before a public release. The current backend's public session-ingestion route and app-specific identity assumptions need an explicit threat-model review before the SDK accepts external projects. Do not advertise `@paytrace/browser` as available until packaging, external integration tests, and documentation exist.
