/**
 * PayTrace Frontend API Client
 * Connects the Next.js frontend with the FastAPI backend (/api/v1).
 */

const API_BASE_URL =
  process.env.NEXT_PUBLIC_API_BASE_URL?.replace(/\/$/, "") || "http://localhost:8000";

async function request<T>(endpoint: string, options: RequestInit = {}): Promise<T> {
  const url = `${API_BASE_URL}${endpoint.startsWith("/") ? endpoint : `/${endpoint}`}`;
  const headers = {
    "Content-Type": "application/json",
    ...(options.headers || {}),
  };

  const response = await fetch(url, {
    ...options,
    headers,
  });

  if (!response.ok) {
    let errorMessage = `HTTP ${response.status} ${response.statusText}`;
    try {
      const errorData = await response.json();
      if (errorData?.detail) {
        errorMessage = typeof errorData.detail === "string" ? errorData.detail : JSON.stringify(errorData.detail);
      }
    } catch {
      // Ignore if response body is not JSON
    }
    throw new Error(errorMessage);
  }

  // Handle 204 No Content
  if (response.status === 204) {
    return {} as T;
  }

  return response.json();
}

// ----------------------------------------------------------------------
// Interfaces & Types
// ----------------------------------------------------------------------

export interface AnalyticsData {
  total_payments: number;
  successful_payments: number;
  failed_payments: number;
  uncertain_payments: number;
  success_rate_percent: number;
  failure_rate_percent: number;
  potential_revenue_at_risk: number | string;
  currency: string;
  average_latency_ms: number;
  average_webhook_delay_seconds: number;
  volume_over_time: Array<{
    date: string;
    successful: number;
    failed: number;
    uncertain: number;
    total?: number;
  }>;
  status_breakdown: Array<{
    status: string;
    count: number;
  }>;
  failure_categories: Array<{
    category: string;
    count: number;
  }>;
  open_incidents_count: number;
}

export interface PaymentItem {
  id: string;
  paypal_order_id?: string | null;
  paypal_capture_id?: string | null;
  customer_ref: string;
  session_id?: string | null;
  amount: number | string;
  currency: string;
  status: string;
  failure_code?: string | null;
  failure_reason?: string | null;
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

export interface PaymentEventItem {
  id: string;
  payment_id: string;
  event_type: string;
  source: string;
  status: string;
  occurred_at: string;
  received_at: string;
  latency_ms?: number | null;
  paypal_order_id?: string | null;
  paypal_capture_id?: string | null;
  metadata_redacted: Record<string, any>;
  trace_id?: string | null;
  span_id?: string | null;
  is_simulated: boolean;
}

export interface TimelineData {
  payment_id: string;
  current_status: string;
  events: PaymentEventItem[];
  total_events: number;
  duration_ms?: number | null;
}

export interface IncidentItem {
  id: string;
  title: string;
  severity: string;
  status: string;
  started_at: string;
  ended_at?: string | null;
  affected_payment_count: number;
  revenue_at_risk: number | string;
  currency: string;
  detection_rule?: string | null;
  root_cause?: string | null;
  confidence?: number | null;
  ai_summary?: string | null;
  created_at: string;
  updated_at: string;
  affected_payments?: PaymentItem[];
}

export interface IncidentListResponse {
  items: IncidentItem[];
  total: number;
}

export interface ApprovalTicketItem {
  id: string;
  payment_id: string;
  action_type: string;
  amount?: number | string | null;
  currency: string;
  reason: string;
  status: string;
  requested_by: string;
  decided_by?: string | null;
  decided_at?: string | null;
  paypal_result_redacted?: Record<string, any> | null;
  created_at: string;
  updated_at: string;
}

export interface AIInvestigationData {
  id?: string | null;
  payment_id?: string | null;
  incident_id?: string | null;
  root_cause: string;
  confidence: number;
  severity: string;
  facts: string[] ;
  inferences: string[];
  customer_impact: string;
  business_impact: string;
  recommendation: string;
  evidence_event_ids?: string[];
  is_incident_likely?: boolean;
  insufficient_evidence?: boolean;
  model_name?: string;
  created_at?: string | null;
  comparison_notes?: string | null;
}

export interface ShelfProductItem {
  id: string;
  seller_id: string;
  name: string;
  price: number;
  currency: string;
  image_url: string;
  description: string;
  category: string;
  stock: number;
  status: string;
  why_matches: string;
}

export interface ShelfDeckResponse {
  deck: ShelfProductItem[];
  total_matches: number;
  query: string;
  refinements_applied: string[];
}

// ----------------------------------------------------------------------
// API Methods
// ----------------------------------------------------------------------

export const api = {
  // Analytics
  getAnalytics: async (): Promise<AnalyticsData> => {
    return request<AnalyticsData>("/api/v1/analytics");
  },

  // Payments
  getPayments: async (params?: {
    page?: number;
    page_size?: number;
    search?: string;
    status?: string;
    source_mode?: string;
    actor?: string;
  }): Promise<PaymentListResponse> => {
    const query = new URLSearchParams();
    if (params?.page) query.set("page", params.page.toString());
    if (params?.page_size) query.set("page_size", params.page_size.toString());
    if (params?.search) query.set("search", params.search);
    if (params?.status) query.set("status", params.status);
    if (params?.source_mode) query.set("source_mode", params.source_mode);
    if (params?.actor) query.set("actor", params.actor);

    const queryString = query.toString();
    return request<PaymentListResponse>(`/api/v1/payments${queryString ? `?${queryString}` : ""}`);
  },

  getPayment: async (paymentId: string): Promise<PaymentItem> => {
    return request<PaymentItem>(`/api/v1/payments/${paymentId}`);
  },

  getPaymentTimeline: async (paymentId: string): Promise<TimelineData> => {
    return request<TimelineData>(`/api/v1/payments/${paymentId}/timeline`);
  },

  getPaymentSession: async (paymentId: string): Promise<any> => {
    return request<any>(`/api/v1/payments/${paymentId}/session`);
  },

  // Incidents
  getIncidents: async (): Promise<IncidentListResponse> => {
    return request<IncidentListResponse>("/api/v1/incidents");
  },

  getIncident: async (incidentId: string): Promise<IncidentItem> => {
    return request<IncidentItem>(`/api/v1/incidents/${incidentId}`);
  },

  generateIncidentReport: async (incidentId: string): Promise<any> => {
    return request<any>(`/api/v1/incidents/${incidentId}/report`, {
      method: "POST",
    });
  },

  // Approvals & Policy
  getApprovals: async (): Promise<ApprovalTicketItem[]> => {
    return request<ApprovalTicketItem[]>("/api/v1/approvals");
  },

  decideApproval: async (
    ticketId: string,
    decision: "APPROVED" | "DENIED",
    notes?: string,
    operatorToken?: string
  ): Promise<any> => {
    return request<any>(`/api/v1/approvals/${ticketId}/decision`, {
      method: "POST",
      body: JSON.stringify({
        decision,
        notes,
        operator_token: operatorToken,
      }),
    });
  },

  // PayPal Operations
  createOrder: async (data: {
    amount: number;
    currency?: string;
    customer_ref?: string;
    session_id?: string;
    simulate_scenario?: string;
  }): Promise<any> => {
    return request<any>("/api/v1/paypal/orders", {
      method: "POST",
      body: JSON.stringify(data),
    });
  },

  captureOrder: async (orderId: string, simulateTimeout: boolean = false): Promise<any> => {
    return request<any>(`/api/v1/paypal/orders/${orderId}/capture`, {
      method: "POST",
      body: JSON.stringify({
        simulate_timeout: simulateTimeout,
      }),
    });
  },

  getOrderDetails: async (orderId: string): Promise<any> => {
    return request<any>(`/api/v1/paypal/orders/${orderId}`);
  },

  proposeRefund: async (
    paymentId: string,
    data: { amount?: number; reason: string }
  ): Promise<any> => {
    return request<any>(`/api/v1/paypal/payments/${paymentId}/refund`, {
      method: "POST",
      body: JSON.stringify(data),
    });
  },

  // AI Investigator
  investigatePayment: async (
    paymentId: string,
    question: string = "Investigate payment outcome, uncertainty, and root cause"
  ): Promise<AIInvestigationData> => {
    return request<AIInvestigationData>("/api/v1/ai/investigate", {
      method: "POST",
      body: JSON.stringify({
        payment_id: paymentId,
        question,
      }),
    });
  },

  chatInvestigator: async (
    paymentId: string,
    messages: Array<{ role: string; content: string }>,
    question?: string
  ): Promise<{ response: string; grounded_facts?: string[]; recommended_action?: string; evidence_event_ids?: string[] }> => {
    return request<any>("/api/v1/ai/chat", {
      method: "POST",
      body: JSON.stringify({
        payment_id: paymentId,
        messages,
        question,
      }),
    });
  },

  // Demo Controls
  triggerScenario: async (scenario: string): Promise<any> => {
    return request<any>("/api/v1/demo/scenarios", {
      method: "POST",
      body: JSON.stringify({ scenario }),
    });
  },

  resetDemoData: async (): Promise<any> => {
    return request<any>("/api/v1/demo/reset", {
      method: "POST",
    });
  },

  // Settings
  getSettings: async (): Promise<any> => {
    return request<any>("/api/v1/settings");
  },

  // ShelfSwipe Discovery Loop
  getShelfDeck: async (query: string, buyerRef: string): Promise<ShelfDeckResponse> => {
    const q = encodeURIComponent(query);
    const b = encodeURIComponent(buyerRef);
    return request<ShelfDeckResponse>(`/api/v1/shelfswipe/deck?query=${q}&buyer_ref=${b}`);
  },

  recordSwipe: async (
    buyerRef: string,
    productId: string,
    direction: "right" | "left"
  ): Promise<any> => {
    return request<any>("/api/v1/shelfswipe/swipe", {
      method: "POST",
      body: JSON.stringify({
        buyer_ref: buyerRef,
        product_id: productId,
        direction,
      }),
    });
  },

  onboardShelfSeller: async (shopUrl: string, shopName: string): Promise<any> => {
    return request<any>("/api/v1/shelfswipe/onboard", {
      method: "POST",
      body: JSON.stringify({
        shop_url: shopUrl,
        shop_name: shopName,
      }),
    });
  },

  checkoutShelfItem: async (
    productId: string,
    buyerRef: string,
    simulateScenario?: string,
    quantity: number = 1
  ): Promise<any> => {
    return request<any>("/api/v1/shelfswipe/checkout", {
      method: "POST",
      body: JSON.stringify({
        product_id: productId,
        buyer_ref: buyerRef,
        simulate_scenario: simulateScenario,
        quantity,
      }),
    });
  },
};
