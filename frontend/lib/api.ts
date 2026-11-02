import { classifyFetchFailure } from "@/lib/checkout-state.mjs";

/**
 * Typed PayTrace API client.
 *
 * Browser requests use NEXT_PUBLIC_API_BASE_URL (docker-compose publishes the
 * backend on localhost:8000). Do not use the Docker service hostname here —
 * NEXT_PUBLIC_* values are inlined into the client bundle and the browser
 * cannot resolve `backend`.
 */

const API_PREFIX = "/api/v1";

export function getApiBaseUrl(): string {
  const configured = process.env.NEXT_PUBLIC_API_BASE_URL?.trim();
  return (configured && configured.length > 0 ? configured : "http://localhost:8000").replace(
    /\/$/,
    ""
  );
}

export class ApiError extends Error {
  status: number;
  detail: unknown;
  kind: "timeout" | "aborted" | "network_or_cors" | "network" | "http";

  constructor(
    message: string,
    status: number,
    detail?: unknown,
    kind: ApiError["kind"] = "http"
  ) {
    super(message);
    this.name = "ApiError";
    this.status = status;
    this.detail = detail;
    this.kind = kind;
  }
}

function formatFastApiDetail(detail: unknown): string | null {
  if (typeof detail === "string" && detail.length > 0) {
    return detail;
  }
  if (detail && typeof detail === "object" && !Array.isArray(detail)) {
    if ("message" in detail && typeof detail.message === "string" && detail.message.length > 0) return detail.message;
    if ("msg" in detail && typeof detail.msg === "string" && detail.msg.length > 0) return detail.msg;
  }
  if (Array.isArray(detail)) {
    const parts = detail
      .map((item) => {
        if (typeof item === "string") return item;
        if (item && typeof item === "object" && "msg" in item) {
          const loc = Array.isArray((item as { loc?: unknown }).loc)
            ? (item as { loc: unknown[] }).loc.join(".")
            : "";
          const msg = String((item as { msg: unknown }).msg);
          return loc ? `${loc}: ${msg}` : msg;
        }
        return JSON.stringify(item);
      })
      .filter(Boolean);
    return parts.length > 0 ? parts.join("; ") : null;
  }
  return null;
}

async function extractErrorMessage(res: Response): Promise<{ message: string; detail: unknown }> {
  const fallback = res.statusText || `HTTP ${res.status}`;
  try {
    const body = (await res.json()) as Record<string, unknown>;
    const fromDetail = formatFastApiDetail(body.detail);
    if (fromDetail) {
      return { message: fromDetail, detail: body.detail };
    }
    if (typeof body.message === "string" && body.message.length > 0) {
      return { message: body.message, detail: body };
    }
    return { message: fallback, detail: body.detail ?? body };
  } catch {
    return { message: fallback, detail: null };
  }
}

function toQuery(params: Record<string, string | number | undefined>): string {
  const search = new URLSearchParams();
  for (const [key, value] of Object.entries(params)) {
    if (value === undefined || value === "") continue;
    search.set(key, String(value));
  }
  const qs = search.toString();
  return qs ? `?${qs}` : "";
}

export interface AuthUser {
  id: string;
  name: string;
  email: string;
  role: string;
}

export interface AuthTokenResponse {
  access_token: string;
  token_type: string;
  user: AuthUser;
}

const AUTH_TOKEN_KEY = "paytrace.auth.token";
let unauthorizedHandler: (() => void) | null = null;

export function getAuthToken(): string | null {
  if (typeof window === "undefined") return null;
  try {
    return localStorage.getItem(AUTH_TOKEN_KEY) ?? sessionStorage.getItem(AUTH_TOKEN_KEY);
  } catch {
    return null;
  }
}

/** Persists the token (localStorage when `remember`, else this tab only); null clears it. */
export function setAuthToken(token: string | null, remember = true): void {
  if (typeof window === "undefined") return;
  try {
    localStorage.removeItem(AUTH_TOKEN_KEY);
    sessionStorage.removeItem(AUTH_TOKEN_KEY);
    if (token) (remember ? localStorage : sessionStorage).setItem(AUTH_TOKEN_KEY, token);
  } catch {
    /* storage unavailable */
  }
}

export function onUnauthorized(handler: (() => void) | null): void {
  unauthorizedHandler = handler;
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const url = `${getApiBaseUrl()}${API_PREFIX}${path}`;
  const headers = new Headers(init?.headers);
  headers.set("Accept", "application/json");
  const authToken = getAuthToken();
  if (authToken && !headers.has("Authorization")) {
    headers.set("Authorization", `Bearer ${authToken}`);
  }
  if (init?.body && !headers.has("Content-Type")) {
    headers.set("Content-Type", "application/json");
  }

  let res: Response;
  try {
    res = await fetch(url, { ...init, headers });
  } catch (err) {
    const failure = classifyFetchFailure(err);
    const reason = err instanceof Error ? err.message : "Unknown browser fetch error";
    throw new ApiError(
      `${failure.message} (${getApiBaseUrl()}${API_PREFIX}${path}; ${reason})`,
      0,
      undefined,
      failure.kind as "timeout" | "network" | "aborted" | "network_or_cors" | "http" | undefined
    );
  }

  if (!res.ok) {
    const { message, detail } = await extractErrorMessage(res);
    if (res.status === 401 && authToken && !path.startsWith("/auth/")) {
      unauthorizedHandler?.();
    }
    throw new ApiError(message, res.status, detail);
  }

  if (res.status === 204) {
    return undefined as T;
  }

  return (await res.json()) as T;
}

export interface PaymentItem {
  id: string;
  paypal_order_id: string | null;
  paypal_capture_id: string | null;
  customer_ref: string;
  session_id: string | null;
  amount: string | number;
  currency: string;
  status: string;
  failure_code: string | null;
  failure_reason: string | null;
  actor: string;
  source_mode: string;
  created_at: string;
  updated_at: string;
}

export interface PaymentListResponse {
  items: PaymentItem[];
  total: number;
  page: number;
  page_size: number;
}

export interface PaymentWorkspaceData {
  total_transactions: number;
  successful_count: number;
  failed_count: number;
  pending_count: number;
  success_rate_percent: number;
  processed_amounts: Array<{ currency: string; amount: string }>;
  average_event_latency_ms: number | null;
  latency_sample_count: number;
  status_breakdown: Array<{ status: string; count: number }>;
  daily_volume: Array<{ date: string; count: number }>;
  failure_sources: Array<{ provider: string; count: number }>;
  failures_by_endpoint: Array<{ endpoint: string; count: number; payment_ids: string[] }>;
  endpoint_event_sample_limit: number;
  correlated_network_events: Array<{
    event_id: string;
    payment_id: string;
    endpoint: string;
    occurred_at: string | null;
    method: string | null;
    status: number | string | null;
    duration_ms: number | null;
    trace_id: string | null;
  }>;
  anomalies: Array<{ kind: string; title: string; evidence: string; count: number; payment_ids: string[] }>;
  transactions: Array<PaymentItem & { provider: string; processing_duration_ms: number | null }>;
  transaction_sample_limit: number;
}

export interface PaymentEventItem {
  id: string;
  payment_id: string;
  event_type: string;
  source: string;
  status: string;
  occurred_at: string;
  received_at: string;
  latency_ms: number | null;
  paypal_order_id: string | null;
  paypal_capture_id: string | null;
  metadata_redacted: Record<string, unknown>;
  trace_id: string | null;
  span_id: string | null;
  is_simulated: boolean;
}

export interface TimelineData {
  payment_id: string;
  current_status: string;
  events: PaymentEventItem[];
  total_events: number;
  duration_ms: number | null;
}

export interface PaymentSessionInfo {
  has_session: boolean;
  session_id: string | null;
  started_at?: string | null;
  events_count?: number;
  recording_enabled?: boolean;
}

export interface BrowserSessionItem {
  id: string;
  visitor_ref: string;
  payment_id: string | null;
  payment_ids?: string[];
  started_at: string;
  ended_at: string | null;
  recording_enabled: boolean;
  events_count: number;
  user_agent?: string | null;
  metadata_redacted?: Record<string, unknown>;
}

export interface BrowserSessionEvent {
  id?: string;
  event_type: string;
  category?: string;
  source?: "browser" | "sdk" | "backend" | "provider";
  session_id?: string;
  tab_id?: string | null;
  segment_id?: string | null;
  occurred_at?: string;
  received_at?: string;
  session_offset_ms?: number | null;
  route?: string | null;
  payment_id?: string | null;
  order_id?: string | null;
  severity?: "debug" | "info" | "warn" | "error" | null;
  trace_id?: string | null;
  attributes?: Record<string, unknown>;
  payload: Record<string, unknown>;
}

export interface BrowserSessionReplay {
  session_id: string;
  payment_id: string | null;
  payment_ids?: string[];
  visitor_ref: string;
  started_at?: string;
  ended_at?: string | null;
  user_agent?: string | null;
  metadata_redacted?: Record<string, unknown>;
  events: Array<BrowserSessionEvent & { id: string; occurred_at: string }>;
  total_events: number;
  returned_events?: number;
  rrweb_events?: number;
  investigation_events?: number;
  offset?: number;
  limit?: number;
  has_more?: boolean;
  payment_events?: Array<Record<string, unknown>>;
}

export interface OrderCreateRequest {
  amount: number;
  currency?: string;
  session_id?: string;
  customer_ref?: string;
  simulate_scenario?: string;
}

export interface OrderCreateResponse {
  payment_id: string;
  paypal_order_id: string;
  status: string;
  approval_url: string | null;
  is_mock: boolean;
}

export interface OrderCaptureResponse {
  payment_id: string;
  paypal_order_id: string;
  paypal_capture_id: string | null;
  status: string;
  failure_code: string | null;
  failure_reason: string | null;
  reconciliation_required: boolean;
  details: Record<string, unknown>;
}

export interface ShelfProduct {
  id: string;
  seller_id: string;
  name: string;
  price: number;
  currency: string;
  image_url: string | null;
  description: string;
  category: string;
  stock: number;
  status: string;
  source: string;
  why_matches: string | null;
}

export interface ShelfDeckResponse {
  deck: ShelfProduct[];
  total_matches: number;
  query: string;
  refinements_applied: string[];
}

export interface ShelfCheckoutResponse {
  payment_id: string;
  paypal_order_id: string;
  approval_url: string | null;
  amount: number;
  currency: string;
  product_name: string;
  is_mock: boolean;
}

export interface ShelfOnboardResponse {
  status: string;
  is_demo: boolean;
  seller_id: string;
  seller_name: string;
  products_count: number;
}

export interface RefundResponse {
  ticket_id: string | null;
  status: string;
  message: string;
}

export interface AIInvestigationData {
  id: string | null;
  payment_id: string | null;
  incident_id: string | null;
  root_cause: string;
  confidence: number;
  severity: string;
  facts: string[];
  inferences: string[];
  customer_impact: string;
  business_impact: string;
  recommendation: string;
  evidence_event_ids: string[];
  is_incident_likely: boolean;
  insufficient_evidence: boolean;
  model_name: string;
  created_at: string | null;
  comparison_notes: string | null;
}

export interface AIChatMessage {
  role: string;
  content: string;
}

export interface AIChatResponse {
  response: string;
  grounded_facts: string[];
  recommended_action: string | null;
  evidence_event_ids: string[];
}

export interface IncidentRecurrence {
  window_days: number;
  distinct_days_seen: number;
  payments_in_window: number;
  pattern_label: string | null;
}

export interface IncidentItem {
  id: string;
  title: string;
  severity: string;
  status: string;
  started_at: string;
  ended_at: string | null;
  affected_payment_count: number;
  revenue_at_risk: string | number;
  currency: string;
  detection_rule: string | null;
  root_cause: string | null;
  confidence: number | null;
  ai_summary: string | null;
  created_at: string;
  updated_at: string;
  affected_payments?: PaymentItem[];
  recurrence?: IncidentRecurrence | null;
}

export interface IncidentListResponse {
  items: IncidentItem[];
  total: number;
}

export interface DisputeItem {
  id: string;
  payment_id: string;
  paypal_dispute_id: string;
  reason: string;
  status: string;
  amount: string | number;
  currency: string;
  buyer_statement: string | null;
  seller_response: string | null;
  outcome_note: string | null;
  is_simulated: boolean;
  opened_at: string;
  response_due_by: string | null;
  resolved_at: string | null;
  created_at: string;
  updated_at: string;
}

export interface DisputeListResponse {
  items: DisputeItem[];
  total: number;
}

export interface IncidentReportResponse {
  incident_id: string;
  title: string;
  severity: string;
  status: string;
  affected_payments_count: number;
  revenue_at_risk: string | number;
  currency: string;
  detection_rule: string | null;
  executive_summary: string;
  detailed_findings: string[];
  timeline_analysis: string;
  recommended_mitigations: string[];
  generated_at: string;
}

export interface VolumeOverTimePoint {
  date: string;
  total: number;
  successful: number;
  failed: number;
  uncertain: number;
}

export interface StatusBreakdownItem {
  status: string;
  count: number;
}

export interface FailureCategoryItem {
  category: string;
  count: number;
}

export interface AnalyticsData {
  total_payments: number;
  successful_payments: number;
  failed_payments: number;
  uncertain_payments: number;
  success_rate_percent: number;
  failure_rate_percent: number;
  potential_revenue_at_risk: string | number;
  currency: string;
  average_latency_ms: number;
  average_webhook_delay_seconds: number;
  volume_over_time: VolumeOverTimePoint[];
  status_breakdown: StatusBreakdownItem[];
  failure_categories: FailureCategoryItem[];
  open_incidents_count: number;
}

export interface ApprovalTicketItem {
  id: string;
  payment_id: string;
  action_type: string;
  amount: string | number | null;
  currency: string;
  reason: string;
  status: string;
  requested_by: string;
  decided_by: string | null;
  decided_at: string | null;
  paypal_result_redacted: Record<string, unknown> | null;
  created_at: string;
  updated_at: string;
}

export interface ApprovalDecisionResponse {
  ticket_id: string;
  decision: string;
  status: string;
  message: string;
  execution_result: Record<string, unknown> | null;
}

export interface SettingsData {
  paypal: {
    is_configured: boolean;
    environment: string;
    client_id_masked: string;
    webhook_id_configured: boolean;
    status_label: string;
  };
  ai: {
    is_configured: boolean;
    provider: string;
    model: string;
    status_label: string;
  };
  database: {
    type: string;
    connected: boolean;
  };
  app_env: string;
  frontend_origin: string;
}

export interface DemoScenarioResponse {
  scenario: string;
  payment_id: string | null;
  title: string;
  description: string;
  status: string;
  details: Record<string, unknown>;
}

export interface DemoResetResponse {
  success: boolean;
  message: string;
  payments_seeded: number;
  incidents_seeded: number;
}

export interface PaymentListParams {
  page?: number;
  page_size?: number;
  search?: string;
  status?: string;
  source_mode?: string;
  actor?: string;
  sort_by?: "id" | "paypal_order_id" | "paypal_capture_id" | "session_id" | "failure_code" | "failure_reason" | "currency" | "created_at" | "amount" | "status" | "source_mode" | "customer_ref";
  sort_order?: "asc" | "desc";
}

export const api = {
  me(): Promise<AuthUser> {
    return request<AuthUser>("/auth/me");
  },

  login(email: string, password: string): Promise<AuthTokenResponse> {
    return request<AuthTokenResponse>("/auth/login", {
      method: "POST",
      body: JSON.stringify({ email, password }),
    });
  },

  register(name: string, email: string, password: string): Promise<AuthTokenResponse> {
    return request<AuthTokenResponse>("/auth/register", {
      method: "POST",
      body: JSON.stringify({ name, email, password }),
    });
  },

  createSession(body: { session_id?: string; visitor_ref?: string; user_agent?: string; metadata?: Record<string, unknown> }) {
    return request<{ id: string; visitor_ref: string; payment_id: string | null; started_at: string; recording_enabled: boolean }>(
      "/sessions",
      { method: "POST", body: JSON.stringify(body), signal: AbortSignal.timeout(5000) }
    );
  },

  ingestSessionEvents(sessionId: string, events: BrowserSessionEvent[]) {
    return request<{ status: string; session_id: string; events_ingested: number }>(
      `/sessions/${encodeURIComponent(sessionId)}/events`,
      { method: "POST", body: JSON.stringify({ events }), signal: AbortSignal.timeout(10000) }
    );
  },

  stopSession(sessionId: string) {
    return request<void>(`/sessions/${encodeURIComponent(sessionId)}/stop`, { method: "POST" });
  },

  getSessions(limit = 100): Promise<BrowserSessionItem[]> {
    return request<BrowserSessionItem[]>(`/sessions${toQuery({ limit })}`);
  },

  getSessionReplay(sessionId: string, limit = 500, offset = 0, tabId?: string): Promise<BrowserSessionReplay> {
    return request<BrowserSessionReplay>(`/sessions/${encodeURIComponent(sessionId)}/replay${toQuery({ limit, offset, tab_id: tabId })}`);
  },

  getShelfDeck(query: string, buyerRef: string) {
    return request<ShelfDeckResponse>(
      `/shelfswipe/deck${toQuery({ query, buyer_ref: buyerRef })}`
    );
  },

  recordSwipe(buyerRef: string, productId: string, direction: "right" | "left") {
    return request<{ status: string; direction: string; product_id: string }>("/shelfswipe/swipe", {
      method: "POST",
      body: JSON.stringify({ buyer_ref: buyerRef, product_id: productId, direction }),
    });
  },

  onboardShelfSeller(shopUrl: string, shopName: string) {
    return request<ShelfOnboardResponse>("/shelfswipe/onboard", {
      method: "POST",
      body: JSON.stringify({ shop_url: shopUrl, shop_name: shopName, consent: true }),
    });
  },

  checkoutShelfItem(productId: string, buyerRef: string, simulateScenario?: string, sessionId?: string) {
    return request<ShelfCheckoutResponse>("/shelfswipe/checkout", {
      method: "POST",
      body: JSON.stringify({
        product_id: productId,
        buyer_ref: buyerRef,
        session_id: sessionId,
        simulate_scenario: simulateScenario,
      }),
    });
  },

  approveMockOrder(orderId: string) {
    return request<{ id: string; status: string }>(
      `/paypal/orders/${encodeURIComponent(orderId)}/approve`,
      { method: "POST" }
    );
  },

  getPayments(params: PaymentListParams = {}): Promise<PaymentListResponse> {
    return request<PaymentListResponse>(
      `/payments${toQuery({
        page: params.page,
        page_size: params.page_size,
        search: params.search,
        status: params.status,
        source_mode: params.source_mode,
        actor: params.actor,
        sort_by: params.sort_by,
        sort_order: params.sort_order,
      })}`
    );
  },

  getPaymentWorkspace(limit = 500): Promise<PaymentWorkspaceData> {
    return request<PaymentWorkspaceData>(`/payments/workspace${toQuery({ limit })}`);
  },

  getPayment(paymentId: string): Promise<PaymentItem> {
    return request<PaymentItem>(`/payments/${encodeURIComponent(paymentId)}`);
  },

  getPaymentTimeline(paymentId: string): Promise<TimelineData> {
    return request<TimelineData>(`/payments/${encodeURIComponent(paymentId)}/timeline`);
  },

  getPaymentSession(paymentId: string): Promise<PaymentSessionInfo> {
    return request<PaymentSessionInfo>(`/payments/${encodeURIComponent(paymentId)}/session`);
  },

  createOrder(body: OrderCreateRequest): Promise<OrderCreateResponse> {
    return request<OrderCreateResponse>("/paypal/orders", {
      method: "POST",
      body: JSON.stringify(body),
    });
  },

  getPayPalOrder(orderId: string): Promise<Record<string, unknown>> {
    return request<Record<string, unknown>>(`/paypal/orders/${encodeURIComponent(orderId)}`, {
      signal: AbortSignal.timeout(30000),
    });
  },

  captureOrder(orderId: string, simulateTimeout = false): Promise<OrderCaptureResponse> {
    return request<OrderCaptureResponse>(
      `/paypal/orders/${encodeURIComponent(orderId)}/capture`,
      {
        method: "POST",
        body: JSON.stringify({ simulate_timeout: simulateTimeout }),
        signal: AbortSignal.timeout(60000),
      }
    );
  },

  proposeRefund(
    paymentId: string,
    body: { reason: string; amount?: number }
  ): Promise<RefundResponse> {
    return request<RefundResponse>(
      `/paypal/payments/${encodeURIComponent(paymentId)}/refund`,
      {
        method: "POST",
        body: JSON.stringify(body),
      }
    );
  },

  investigatePayment(paymentId: string, question?: string): Promise<AIInvestigationData> {
    const payload: { payment_id: string; question?: string } = { payment_id: paymentId };
    if (question !== undefined) {
      payload.question = question;
    }
    return request<AIInvestigationData>("/ai/investigate", {
      method: "POST",
      body: JSON.stringify(payload),
    });
  },

  chatInvestigator(
    paymentId: string,
    messages: AIChatMessage[],
    question?: string
  ): Promise<AIChatResponse> {
    return request<AIChatResponse>("/ai/chat", {
      method: "POST",
      body: JSON.stringify({
        payment_id: paymentId,
        messages,
        question,
      }),
    });
  },

  getIncidents(): Promise<IncidentListResponse> {
    return request<IncidentListResponse>("/incidents");
  },

  getIncident(incidentId: string): Promise<IncidentItem> {
    return request<IncidentItem>(`/incidents/${encodeURIComponent(incidentId)}`);
  },

  generateIncidentReport(incidentId: string): Promise<IncidentReportResponse> {
    return request<IncidentReportResponse>(
      `/incidents/${encodeURIComponent(incidentId)}/report`,
      { method: "POST" }
    );
  },

  getDisputes(status?: string): Promise<DisputeListResponse> {
    return request<DisputeListResponse>(`/disputes${toQuery({ status })}`);
  },

  getDisputesForPayment(paymentId: string): Promise<DisputeListResponse> {
    return request<DisputeListResponse>(`/disputes/by-payment/${encodeURIComponent(paymentId)}`);
  },

  simulateDispute(body: { payment_id: string; reason: string; buyer_statement?: string }): Promise<DisputeItem> {
    return request<DisputeItem>("/disputes/simulate", {
      method: "POST",
      body: JSON.stringify(body),
    });
  },

  respondToDispute(disputeId: string, body: { seller_response: string; accept_liability: boolean }): Promise<DisputeItem> {
    return request<DisputeItem>(`/disputes/${encodeURIComponent(disputeId)}/respond`, {
      method: "POST",
      body: JSON.stringify(body),
    });
  },

  getAnalytics(): Promise<AnalyticsData> {
    return request<AnalyticsData>("/analytics");
  },

  getApprovals(): Promise<ApprovalTicketItem[]> {
    return request<ApprovalTicketItem[]>("/approvals");
  },

  decideApproval(
    ticketId: string,
    decision: "APPROVED" | "DENIED",
    notes?: string
  ): Promise<ApprovalDecisionResponse> {
    return request<ApprovalDecisionResponse>(
      `/approvals/${encodeURIComponent(ticketId)}/decision`,
      {
        method: "POST",
        body: JSON.stringify({ decision, notes }),
      }
    );
  },

  getSettings(): Promise<SettingsData> {
    return request<SettingsData>("/settings");
  },

  triggerScenario(scenario: string): Promise<DemoScenarioResponse> {
    return request<DemoScenarioResponse>("/demo/scenarios", {
      method: "POST",
      body: JSON.stringify({ scenario }),
    });
  },

  resetDemoData(): Promise<DemoResetResponse> {
    return request<DemoResetResponse>("/demo/reset", { method: "POST" });
  },
};
