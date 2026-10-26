# Frontend route inventory

These routes are implemented by the Next.js App Router under `frontend/app/`. The root route redirects to the operator dashboard. There is no catch-all route.

| Route | Implementation | Purpose |
| --- | --- | --- |
| `/` | `app/page.tsx` | Redirects to `/dashboard`. |
| `/about` | `app/about/page.tsx` | Product overview retained from the original root page. |
| `/dashboard` | `app/dashboard/page.tsx` | Payment observability dashboard. |
| `/payments` | `app/payments/page.tsx` | Searchable payment ledger. |
| `/payments/[id]` | `app/payments/[id]/page.tsx` | Payment detail and lifecycle timeline. |
| `/incidents` | `app/incidents/page.tsx` | Incident list. |
| `/incidents/[id]` | `app/incidents/[id]/page.tsx` | Incident report and affected payments. |
| `/investigate` | `app/investigate/page.tsx` | AI payment investigator. |
| `/approvals` | `app/approvals/page.tsx` | Operator approval inbox. |
| `/analytics` | `app/analytics/page.tsx` | Payment analytics. |
| `/checkout` | `app/checkout/page.tsx` | PayPal checkout, buyer approval return, and capture verification. |
| `/demo/approval` | `app/demo/approval/page.tsx` | Explicit simulated approval step for credential-free demo orders. |
| `/shelfswipe` | `app/shelfswipe/page.tsx` | Separate ShelfSwipe sample catalog and checkout experience. |
| `/paypal-checkout` | `app/paypal-checkout/page.tsx` | Legacy redirect to `/checkout`, preserving its query string. |
| `/settings` | `app/settings/page.tsx` | Integration status and settings. |

The backend mounts versioned REST endpoints under `/api/v1`; PayPal webhooks accept both `/api/webhooks/paypal` and `/api/v1/webhooks/paypal` for compatibility. The registered ShelfSwipe endpoints are `/api/v1/shelfswipe/{deck,swipe,onboard,checkout}`.
