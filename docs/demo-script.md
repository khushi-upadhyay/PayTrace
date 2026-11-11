# PayTrace Sandbox and AI Investigation Demo

This walkthrough demonstrates one real PayPal Sandbox payment and one explicitly simulated merchant-side response loss. The separate `/demo/scenarios` fixtures remain fully simulated and are not PayPal evidence.

## Before the demo

1. Follow [PayPal Sandbox setup](paypal-setup.md) and configure `PAYPAL_CLIENT_ID`, `PAYPAL_CLIENT_SECRET`, and `PAYPAL_MODE=sandbox` in `backend/.env`.
2. Optionally configure `PAYPAL_WEBHOOK_ID` and a public HTTPS tunnel to receive verified Sandbox webhooks. Webhook delivery is asynchronous and should only be claimed if a verified event appears in PayTrace.
3. Configure the AI provider and (optionally) `LANGCHAIN_API_KEY` or `LANGSMITH_API_KEY` for LangSmith traces.
4. Start the backend and frontend using the README setup instructions. Sign in and open `/checkout`.

## Reproduce the uncertain capture

1. On checkout, select **Merchant Backend Timeout / Ambiguous Capture State** and submit the order.
2. Complete buyer approval in the PayPal Sandbox account. This approval and the resulting Sandbox order are real PayPal operations when credentials are configured.
3. After the buyer returns, PayTrace makes one real Sandbox capture request. The demo deliberately discards the returned response and records a simulated merchant-side response-loss event. PayTrace sets the local payment to `CAPTURE_UNCERTAIN` and does not persist a fabricated capture ID.
4. Open the payment and run **Investigate with AI**. LangGraph retrieves local payment state, merchant lifecycle events, linked webhook processing history, then calls PayPal's live order endpoint and capture endpoint for IDs returned by the order. The report shows the provider order and capture statuses beside the local status and webhook evidence.
5. If the live capture is `COMPLETED`, the report identifies PayPal's confirmation and recommends reconciling the local payment record. If the API is unavailable or no conclusive capture details are returned, it says the outcome remains uncertain. In both cases, it prohibits a blind retry.
6. Open LangSmith and filter the `paytrace` project for `PayTrace payment investigation` to show the graph trace, when tracing is configured.

### What is real and what is simulated?

| Step | Sandbox credentials configured | No Sandbox credentials |
| --- | --- | --- |
| Order creation and buyer approval | Real PayPal Sandbox | In-memory simulated demo |
| Capture operation | One real PayPal Sandbox capture request | No PayPal request; mock order remains simulated |
| Merchant response loss | Simulated by PayTrace after the request | Simulated demo event |
| Investigation provider evidence | Live PayPal order and capture responses | Clearly labeled in-memory demo response or unavailable |
| Webhook evidence | Real only when a verified webhook was received and processed | No external PayPal webhook evidence |

The checkout payment record's source mode, lifecycle event source, simulation marker, and investigation tool result identify which path ran. A mock/demo response must never be presented as a PayPal Sandbox API response.

## Fleet-level natural-language query

Open `/investigate`, choose **All recent transactions (incident command)**, and ask: “Why did checkout failures increase in the last 15 minutes?” The SQL aggregation compares the last 15 minutes with the immediately preceding 15 minutes, groups failure and payment statuses, summarizes merchant event latency and webhook processing, and lists uncertain payments that need reconciliation. The report's counts come directly from SQL results.

## Credential-less fallback

If Sandbox credentials are unavailable, the same checkout path uses the clearly labeled in-memory demo provider. It is useful for walking through local state transitions and the deterministic investigator, but it does not prove a PayPal capture or webhook. The standalone `/demo/scenarios` endpoint also creates simulated fixtures only.
