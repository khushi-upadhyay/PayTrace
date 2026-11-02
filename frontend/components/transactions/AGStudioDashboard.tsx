"use client";

import { useCallback, useMemo, useState } from "react";
import { AgStudio, AgStudioProvider } from "ag-studio-react";
import type { AgDataSourcesDefinition } from "ag-studio";
import { PaymentWorkspaceData } from "@/lib/api";

const STORAGE_KEY = "paytrace.ag-studio.transactions.v1";

function initialReport(): any {
  if (typeof window !== "undefined") {
    try {
      const saved = window.localStorage.getItem(STORAGE_KEY);
      if (saved) return JSON.parse(saved);
    } catch {
      window.localStorage.removeItem(STORAGE_KEY);
    }
  }
  return {
    selectedPageId: "payment-investigation",
    pages: [{
      id: "payment-investigation",
      widgets: {
        "status-mix": {
          type: "donut-chart",
          dataMapping: { categoryKey: [{ id: "status" }], valueKey: [{ id: "count", aggregation: "sum" }] },
          format: { title: { enabled: true, text: "Transaction outcomes" }, crossFilter: "filter" },
        },
        "daily-volume": {
          type: "bar-chart-grouped",
          dataMapping: { categoryKey: [{ id: "date" }], valueKey: [{ id: "count", aggregation: "sum" }] },
          format: { title: { enabled: true, text: "Transactions by day" }, crossFilter: "filter" },
        },
        "provider-mix": {
          type: "bar-chart-grouped",
          dataMapping: { categoryKey: [{ id: "provider" }], valueKey: [{ id: "count", aggregation: "sum" }] },
          format: { title: { enabled: true, text: "Failures by provider / environment" }, crossFilter: "filter" },
        },
        "failure-endpoints": {
          type: "bar-chart-grouped",
          dataMapping: { categoryKey: [{ id: "endpoint" }], valueKey: [{ id: "event_id", aggregation: "count" }] },
          format: { title: { enabled: true, text: "Network events correlated to failed payments" }, crossFilter: "filter" },
        },
        "transaction-grid": {
          type: "grid",
          dataMapping: { cols: [
            { id: "transaction_id" }, { id: "paypal_order_id" }, { id: "provider" },
            { id: "customer" }, { id: "amount" }, { id: "currency" },
            { id: "status" }, { id: "created_at" }, { id: "session_id" }, { id: "failure_code" },
          ] },
          format: { title: { enabled: true, text: "Recent payment evidence" }, crossFilter: "filter" },
        },
        "network-grid": {
          type: "grid",
          dataMapping: { cols: [
            { id: "event_id" }, { id: "endpoint" }, { id: "method" }, { id: "status" },
            { id: "duration_ms" }, { id: "occurred_at" }, { id: "payment_id" }, { id: "trace_id" },
          ] },
          format: { title: { enabled: true, text: "Correlated browser network evidence" }, crossFilter: "filter" },
        },
      },
      widgetLayout: {
        "status-mix": { xTrack: 0, yTrack: 0, xSpan: 12, ySpan: 18 },
        "daily-volume": { xTrack: 12, yTrack: 0, xSpan: 12, ySpan: 18 },
        "provider-mix": { xTrack: 0, yTrack: 18, xSpan: 12, ySpan: 18 },
        "failure-endpoints": { xTrack: 12, yTrack: 18, xSpan: 12, ySpan: 18 },
        "transaction-grid": { xTrack: 0, yTrack: 36, xSpan: 24, ySpan: 28 },
        "network-grid": { xTrack: 0, yTrack: 64, xSpan: 24, ySpan: 26 },
      },
    }],
  };
}

export function AGStudioDashboard({ workspace }: { workspace: PaymentWorkspaceData }) {
  const [mode, setMode] = useState<"view" | "edit">("view");
  const [report, setReport] = useState<any>(initialReport);
  const rows = useMemo(() => workspace.transactions.map((payment) => ({
    transaction_id: payment.id,
    paypal_order_id: payment.paypal_order_id ?? "",
    provider: payment.provider,
    customer: payment.customer_ref,
    amount: Number(payment.amount),
    currency: payment.currency,
    status: payment.status,
    created_at: payment.created_at,
    created_day: new Date(payment.created_at).toISOString().slice(0, 10),
    session_id: payment.session_id ?? "",
    capture_id: payment.paypal_capture_id ?? "",
    failure_code: payment.failure_code ?? "",
    failure_reason: payment.failure_reason ?? "",
    processing_duration_ms: payment.processing_duration_ms,
  })), [workspace.transactions]);
  const data = useMemo<AgDataSourcesDefinition>(() => ({
    description: "Recent persisted PayTrace payment records from the authenticated API. Sandbox and simulated records remain identified by source mode.",
    sources: [
      { id: "transactions", name: "Recent transactions", description: "Bounded recent transaction sample from PayTrace.", data: rows },
      { id: "all_time_volume", name: "All-time daily volume", description: "Database count of transactions per day across the full dataset.", data: workspace.daily_volume },
      { id: "all_time_status", name: "All-time payment outcomes", description: "Persisted payment count grouped by status across the full dataset.", data: workspace.status_breakdown },
      { id: "all_time_failure_sources", name: "All-time failure sources", description: "Persisted failed-payment count grouped by provider / environment.", data: workspace.failure_sources },
      { id: "network_events", name: "Correlated network events", description: "Browser network events carrying an exact payment ID related to a failed payment. Temporal association is evidence, not proof of cause.", data: workspace.correlated_network_events },
    ],
    relationships: [
      { id: "status-transactions", source: { tableId: "all_time_status", fieldId: "status" }, target: { tableId: "transactions", fieldId: "status" }, type: "one-to-many" },
      { id: "day-transactions", source: { tableId: "all_time_volume", fieldId: "date" }, target: { tableId: "transactions", fieldId: "created_day" }, type: "one-to-many" },
      { id: "source-transactions", source: { tableId: "all_time_failure_sources", fieldId: "provider" }, target: { tableId: "transactions", fieldId: "provider" }, type: "one-to-many" },
      { id: "transaction-network-events", source: { tableId: "transactions", fieldId: "transaction_id" }, target: { tableId: "network_events", fieldId: "payment_id" }, type: "one-to-many" },
    ],
  }), [rows, workspace.daily_volume, workspace.status_breakdown, workspace.failure_sources, workspace.correlated_network_events]);
  const saveReport = useCallback((event: { state: any }) => {
    setReport(event.state);
    try { window.localStorage.setItem(STORAGE_KEY, JSON.stringify(event.state)); } catch { /* storage can be unavailable */ }
  }, []);
  const licenseKey = process.env.NEXT_PUBLIC_AG_STUDIO_LICENSE_KEY;
  const evaluationAllowed = process.env.NODE_ENV !== "production" || Boolean(licenseKey);

  return (
    <section className="overflow-hidden rounded-2xl border border-slate-700 bg-slate-950">
      <div className="flex flex-col gap-3 border-b border-slate-800 px-5 py-4 sm:flex-row sm:items-center sm:justify-between">
        <div>
          <h2 className="text-base font-semibold text-slate-100">AG Studio · payment analytics</h2>
          <p className="mt-1 text-xs text-slate-400">Cross-filter the actual recent transaction sample; dashboard layout saves in this browser.</p>
          <p className="mt-1 text-[10px] text-slate-500">Studio’s AI assistant is not enabled; no transaction data is sent to an LLM.</p>
        </div>
        <div className="flex items-center gap-2">
          <span className={`rounded-full border px-2.5 py-1 text-[11px] ${licenseKey ? "border-emerald-700/60 bg-emerald-950/40 text-emerald-200" : "border-amber-700/60 bg-amber-950/40 text-amber-200"}`}>{licenseKey ? "License key supplied" : "Local evaluation only"}</span>
          <button type="button" onClick={() => setMode(mode === "view" ? "edit" : "view")} className="rounded-lg border border-slate-700 px-3 py-2 text-xs font-medium text-slate-200 hover:bg-slate-900">
            {mode === "view" ? "Edit dashboard" : "Finish editing"}
          </button>
        </div>
      </div>
      <div className="h-[760px] min-h-[620px] bg-white">
        {!evaluationAllowed ? <div className="flex h-full flex-col items-center justify-center px-8 text-center"><p className="text-base font-semibold text-slate-800">AG Studio is disabled in this production build</p><p className="mt-2 max-w-xl text-sm text-slate-600">Set <code>NEXT_PUBLIC_AG_STUDIO_LICENSE_KEY</code> to a valid AG Studio deployment or trial key to enable the embedded dashboard. No key is present in this environment.</p></div> : <AgStudioProvider licenseKey={licenseKey}>
          <AgStudio
            className="h-full w-full"
            style={{ height: "100%", width: "100%" }}
            data={data}
            initialState={report}
            onStateUpdated={saveReport}
            mode={mode}
            panels={{ edit: { right: ["edit", "data"] } }}
          />
        </AgStudioProvider>}
      </div>
      <p className="px-5 py-3 text-[11px] text-slate-500">
        Dataset scope: {rows.length} most recent transaction records (of {workspace.total_transactions.toLocaleString()} total). All-time KPIs remain shown in the workspace header.
      </p>
    </section>
  );
}
