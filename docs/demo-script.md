# PayTrace 3-Minute Hackathon Demo Script

This script walks through the three-minute hackathon presentation of PayTrace according to PRD Section 22.

---

### Segment 1: The Problem & Product Overview (0:00 – 0:25)
- **Visual**: Start on Overview Dashboard (`http://localhost:3000`) or product overview (`http://localhost:3000/about`).
- **Narrative**:
  > "When an online payment fails or hangs, merchant engineering and support teams often have to scramble across isolated silos: looking at PayPal transaction logs, application backend error logs, and customer support tickets.
  >
  > PayTrace is an AI-powered payment investigation and observability platform that unifies all three signals: the payment provider, the backend lifecycle, and the customer's checkout session into a single cohesive trace.
  >
  > Don't just know a payment failed. Know exactly why."

---

### Segment 2: Real Sandbox Checkout & Unified Timeline (0:25 – 1:00)
- **Action**: Navigate to `/checkout`. Select the **Enterprise Observability Plan** ($189.99) and complete checkout.
- **Visual**: Click through to `/payments/{payment_id}`.
- **Narrative**:
  > "Here is our payments detail page. Notice the unified, chronological timeline:
  > 1. Frontend checkout started with session tracking.
  > 2. Order created in PayPal Sandbox.
  > 3. Buyer approved the transaction.
  > 4. Merchant backend captured the funds.
  > 5. If the Sandbox webhook tunnel is configured, a signature-verified PayPal webhook can be matched to the order. Without that external Sandbox delivery, inspect only the synchronous capture lifecycle and do not claim webhook confirmation.
  >
  > Real Sandbox events and simulated events are clearly delineated—we never pretend simulated demo data came from PayPal."

---

### Segment 3: The Ambiguous Capture Timeout Scenario (1:00 – 1:55)
- **Action**: In the Header, click **Simulate Timeout** (or navigate to `/payments` and open `demo-timeout-payment-001`).
- **Visual**: Show payment in state **`CAPTURE_UNCERTAIN`**.
- **Action**: Click **Investigate with AI**.
- **Narrative**:
  > "Now let's look at the most dangerous payment failure in e-commerce: **The Merchant Backend Timeout**.
  >
  > In this scenario, the merchant backend submitted a capture request to PayPal, but the HTTP connection timed out after 5 seconds before receiving the response.
  >
  > If the merchant blindly retries the capture, the customer could be charged twice!
  >
  > PayTrace immediately flags this state as `CAPTURE_UNCERTAIN`. When we run the AI Investigator:
  > - It identifies the root cause: an unconfirmed capture outcome after a timeout.
  > - It separates hard **Facts** from probabilistic **Inferences**.
  > - And most importantly, its primary recommendation is: **DO NOT RETRY CAPTURE BLINDLY. Reconcile order state first.**"
- **Action**: Demonstrate clicking **Reconcile with PayPal** to safely verify provider state.

---

### Segment 4: Incident Clustering & Session Evidence (1:55 – 2:30)
- **Action**: Navigate to `/incidents` and select an active incident.
- **Visual**: Show the Incident Detail page and click **Generate AI Incident Report**.
- **Narrative**:
  > "PayTrace doesn't just evaluate individual payments—it aggregates failures into Incidents.
  >
  > Here, our deterministic incident engine detected an anomalous spike in capture timeouts. PayTrace calculates the exact **potential revenue at risk** ($1,029.50) without falsely claiming it as confirmed losses, groups all affected payments, and provides an incident diagnostic report."

---

### Segment 5: Human-in-the-Loop Safe Action (2:30 – 3:00)
- **Action**: Navigate to `/approvals`. Show a pending refund proposal. Click **Approve Action**.
- **Visual**: Show the action execution and audit trail updating.
- **Narrative**:
  > "Finally, safety is our top priority. We never allow AI agents or automated bots to execute consequential financial actions without human policy verification.
  >
  > When a refund is proposed, it is routed directly to the Human Approval Inbox. Only an authenticated operator can authorize execution with PayPal.
  >
  > With PayTrace, developers and operations teams get complete end-to-end payment visibility, evidence-backed AI investigations, and guaranteed financial safety."
