# Investigation cases: persistence proposal

## Current model

The database stores incidents, payments, payment lifecycle events, browser sessions and session events, plus AI investigation records. An AI investigation can optionally reference a payment or incident. There is no case, case-note, or general evidence-reference model. Incident-to-payment membership is currently derived from each incident rule, and payment-to-session correlation uses `payments.session_id`.

## Safest incremental design

Add an `investigation_cases` table with a generated UUID, title, description, status (`OPEN`, `INVESTIGATING`, `RESOLVED`), creator, and created/updated/resolved timestamps. Add append-only `investigation_case_links` rows with `(case_id, target_type, target_id)` for payment, session, or incident references; validate each target exists in the service layer and index both `(case_id, target_type)` and `(target_type, target_id)`. Add append-only `investigation_case_notes` rows with author, body, timestamp, and optional AI-investigation reference. Store evidence as typed links to existing record IDs, not copied snapshots, so records remain the source of truth.

## Migration and rollout plan (not implemented)

Create a forward-only Alembic revision that creates these three new tables and indexes, with no alterations or deletion of existing records. Deploy the schema first, then add authenticated CRUD/list endpoints and UI. Backfill nothing: existing incidents and AI findings remain untouched until an operator explicitly links them to a case. Verify fresh installs and upgrades from the current revision before enabling the UI. This proposal needs review before any migration is authored.
