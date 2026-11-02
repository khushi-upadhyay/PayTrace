"use client";

import dynamic from "next/dynamic";
import Link from "next/link";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { AgGridReact } from "ag-grid-react";
import { AgGridProvider } from "ag-grid-react";
import { AllCommunityModule, ColDef, GridApi, GridReadyEvent, SelectionChangedEvent, SortChangedEvent, themeQuartz } from "ag-grid-community";
import { Activity, AlertTriangle, ArrowDownRight, ArrowUpRight, BarChart3, CheckCircle2, ChevronLeft, ChevronRight, Clock3, Download, ExternalLink, FilterX, Loader2, Search, ShieldAlert, Sparkles, X } from "lucide-react";
import { api, BrowserSessionReplay, PaymentEventItem, PaymentItem, PaymentListResponse, PaymentWorkspaceData, TimelineData } from "@/lib/api";

const StudioDashboard = dynamic(() => import("@/components/transactions/AGStudioDashboard").then((mod) => mod.AGStudioDashboard), {
  ssr: false,
  loading: () => <div className="flex h-64 items-center justify-center rounded-xl border border-slate-800 bg-slate-900 text-sm text-slate-400"><Loader2 className="mr-2 h-4 w-4 animate-spin" />Loading AG Studio…</div>,
});

type ExplorerRow = PaymentItem & { provider: string; processing_duration_ms: number | null };
const GRID_STATE_KEY = "paytrace.transaction-grid-state.v1";
const SAVED_FILTERS_KEY = "paytrace.transaction-filters.v1";
const SERVER_SORT_FIELDS = ["id", "paypal_order_id", "paypal_capture_id", "session_id", "failure_code", "failure_reason", "currency", "created_at", "amount", "status", "source_mode", "customer_ref"] as const;
type ServerSortField = typeof SERVER_SORT_FIELDS[number];

function statusClass(status: string) {
  if (["CAPTURED", "REFUNDED"].includes(status)) return "border-emerald-700 bg-emerald-950/70 text-emerald-300";
  if (["DENIED", "CAPTURE_FAILED", "DISPUTED"].includes(status)) return "border-rose-700 bg-rose-950/70 text-rose-300";
  if (["CAPTURE_UNCERTAIN", "CAPTURE_PENDING", "CREATED", "APPROVED"].includes(status)) return "border-amber-700 bg-amber-950/70 text-amber-300";
  return "border-slate-700 bg-slate-800 text-slate-300";
}

function formatDate(value: string) {
  const date = new Date(value);
  return Number.isNaN(date.valueOf()) ? "—" : date.toLocaleString();
}

export default function TransactionExplorerPage() {
  const [workspace, setWorkspace] = useState<PaymentWorkspaceData | null>(null);
  const [pageData, setPageData] = useState<PaymentListResponse | null>(null);
  const [rows, setRows] = useState<ExplorerRow[]>([]);
  const [page, setPage] = useState(1);
  const [status, setStatus] = useState("");
  const [provider, setProvider] = useState("");
  const [searchInput, setSearchInput] = useState("");
  const [search, setSearch] = useState("");
  const [sortBy, setSortBy] = useState<ServerSortField>("created_at");
  const [sortOrder, setSortOrder] = useState<"asc" | "desc">("desc");
  const [activeView, setActiveView] = useState<"explorer" | "studio">("explorer");
  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [workspaceError, setWorkspaceError] = useState<string | null>(null);
  const [selected, setSelected] = useState<ExplorerRow[]>([]);
  const [focusedPayment, setFocusedPayment] = useState<PaymentItem | null>(null);
  const [timeline, setTimeline] = useState<TimelineData | null>(null);
  const [replay, setReplay] = useState<BrowserSessionReplay | null>(null);
  const [investigationLoading, setInvestigationLoading] = useState(false);
  const [investigationError, setInvestigationError] = useState<string | null>(null);
  const [savedFilters, setSavedFilters] = useState<Array<{ name: string; status: string; provider: string; search: string }>>([]);
  const [saveFilterName, setSaveFilterName] = useState("");
  const [saveFilterOpen, setSaveFilterOpen] = useState(false);
  const gridApi = useRef<GridApi<ExplorerRow> | null>(null);
  const pendingFocusId = useRef<string | null>(null);

  useEffect(() => {
    try {
      const saved = JSON.parse(localStorage.getItem(SAVED_FILTERS_KEY) || "[]");
      if (Array.isArray(saved)) setSavedFilters(saved);
    } catch { localStorage.removeItem(SAVED_FILTERS_KEY); }
  }, []);

  const loadWorkspace = useCallback(async () => {
    try {
      const result = await api.getPaymentWorkspace(500);
      setWorkspace(result);
      setWorkspaceError(null);
    } catch (error) {
      setWorkspaceError(error instanceof Error ? error.message : "Payment analytics could not be loaded.");
    }
  }, []);

  useEffect(() => { void loadWorkspace(); }, [loadWorkspace]);

  const loadPayments = useCallback(async () => {
    setLoading(true);
    setLoadError(null);
    try {
      const result = await api.getPayments({
        page, page_size: 100, status: status || undefined,
        source_mode: provider || undefined, search: search || undefined,
        sort_by: sortBy, sort_order: sortOrder,
      });
      setPageData(result);
      const observed = new Map((workspace?.transactions || []).map((item) => [item.id, item]));
      setRows(result.items.map((item) => ({
        ...item,
        provider: observed.get(item.id)?.provider || item.source_mode,
        processing_duration_ms: observed.get(item.id)?.processing_duration_ms ?? null,
      })));
    } catch (error) {
      setLoadError(error instanceof Error ? error.message : "Transaction records could not be loaded.");
    } finally { setLoading(false); }
  }, [page, status, provider, search, sortBy, sortOrder, workspace]);

  useEffect(() => { void loadPayments(); }, [loadPayments]);

  const openInvestigation = useCallback(async (payment: PaymentItem) => {
    setFocusedPayment(payment);
    setTimeline(null);
    setReplay(null);
    setInvestigationError(null);
    setInvestigationLoading(true);
    try {
      const [fullPayment, paymentTimeline] = await Promise.all([
        api.getPayment(payment.id), api.getPaymentTimeline(payment.id),
      ]);
      setFocusedPayment(fullPayment);
      setTimeline(paymentTimeline);
      if (fullPayment.session_id) {
        try { setReplay(await api.getSessionReplay(fullPayment.session_id, 100)); }
        catch { setReplay(null); }
      }
    } catch (error) {
      setInvestigationError(error instanceof Error ? error.message : "Investigation evidence could not be loaded.");
    } finally { setInvestigationLoading(false); }
  }, []);

  const openObservedPayment = useCallback(async (paymentId: string) => {
    const known = rows.find((item) => item.id === paymentId) || workspace?.transactions.find((item) => item.id === paymentId);
    if (known) { await openInvestigation(known); return; }
    try { await openInvestigation(await api.getPayment(paymentId)); }
    catch (error) { setInvestigationError(error instanceof Error ? error.message : "The related payment could not be loaded."); }
  }, [rows, workspace, openInvestigation]);

  const columns = useMemo<ColDef<ExplorerRow>[]>(() => [
    { field: "id", headerName: "Transaction", minWidth: 155, tooltipField: "id", valueFormatter: ({ value }) => value ? `${value.slice(0, 12)}…` : "—", pinned: "left" },
    { field: "paypal_order_id", headerName: "Order ID", minWidth: 150, valueFormatter: ({ value }) => value || "—" },
    { field: "provider", headerName: "Provider / environment", minWidth: 160 },
    { field: "customer_ref", headerName: "Customer", minWidth: 145 },
    { field: "amount", headerName: "Amount", minWidth: 125, type: "rightAligned", valueFormatter: ({ value, data }) => value == null ? "—" : `${Number(value).toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })} ${data?.currency || ""}` },
    { field: "status", headerName: "Payment status", minWidth: 150, cellRenderer: ({ value }: { value: string }) => <span className={`inline-flex rounded-full border px-2 py-1 text-[10px] font-bold tracking-wide ${statusClass(value)}`}>{value}</span> },
    { field: "created_at", headerName: "Created", minWidth: 185, valueFormatter: ({ value }) => value ? formatDate(value) : "—" },
    { field: "processing_duration_ms", headerName: "Observed latency", minWidth: 145, type: "rightAligned", valueFormatter: ({ value }) => value == null ? "No event sample" : `${Math.round(Number(value))} ms` },
    { field: "session_id", headerName: "Session", minWidth: 155, valueFormatter: ({ value }) => value ? `${value.slice(0, 12)}…` : "—", tooltipField: "session_id" },
    { field: "paypal_capture_id", headerName: "Capture ID", minWidth: 155, valueFormatter: ({ value }) => value || "—" },
    { field: "failure_reason", headerName: "Failure detail", minWidth: 220, valueFormatter: ({ value }) => value || "—" },
    { field: "source_mode", headerName: "Source", minWidth: 135 },
  ], []);

  const defaultColDef = useMemo<ColDef<ExplorerRow>>(() => ({
    sortable: true, sortingOrder: ["desc", "asc", null], resizable: true,
    filter: "agTextColumnFilter", floatingFilter: true, minWidth: 115,
    suppressHeaderMenuButton: false,
  }), []);

  const onGridReady = (event: GridReadyEvent<ExplorerRow>) => {
    gridApi.current = event.api;
    try {
      const saved = localStorage.getItem(GRID_STATE_KEY);
      if (saved) event.api.applyColumnState({ state: JSON.parse(saved), applyOrder: true });
    } catch { localStorage.removeItem(GRID_STATE_KEY); }
  };

  const saveGridState = (event: { api: GridApi<ExplorerRow> }) => {
    try { localStorage.setItem(GRID_STATE_KEY, JSON.stringify(event.api.getColumnState())); } catch { /* storage may be blocked */ }
  };

  const onSortChanged = (event: SortChangedEvent<ExplorerRow>) => {
    const primary = event.api.getColumnState()
      .filter((column) => column.sort)
      .sort((left, right) => (left.sortIndex ?? 0) - (right.sortIndex ?? 0))[0];
    const field = primary?.colId;
    if (field && SERVER_SORT_FIELDS.includes(field as ServerSortField)) {
      setSortBy(field as ServerSortField);
      setSortOrder(primary?.sort === "asc" ? "asc" : "desc");
      setPage(1);
    }
    saveGridState(event);
  };

  const onSelectionChanged = (event: SelectionChangedEvent<ExplorerRow>) => {
    const selection = event.api.getSelectedRows();
    setSelected(selection);
    const focus = pendingFocusId.current;
    if (focus) {
      const row = selection.find((payment) => payment.id === focus) || rows.find((payment) => payment.id === focus);
      if (row) void openInvestigation(row);
      pendingFocusId.current = null;
    }
  };

  const applyFilters = (next: { status?: string; provider?: string; search?: string }) => {
    if (next.status !== undefined) setStatus(next.status);
    if (next.provider !== undefined) setProvider(next.provider);
    if (next.search !== undefined) { setSearchInput(next.search); setSearch(next.search); }
    setPage(1);
    setSelected([]);
  };

  const saveFilter = () => {
    const name = saveFilterName.trim();
    if (!name) return;
    const next = [...savedFilters.filter((item) => item.name !== name), { name, status, provider, search }];
    setSavedFilters(next);
    localStorage.setItem(SAVED_FILTERS_KEY, JSON.stringify(next));
    setSaveFilterName(""); setSaveFilterOpen(false);
  };

  const pageCount = Math.max(1, Math.ceil((pageData?.total || 0) / 100));
  const formattedAmounts = workspace?.processed_amounts || [];
  const totalProcessed = formattedAmounts.length === 1
    ? `${Number(formattedAmounts[0].amount).toLocaleString(undefined, { style: "currency", currency: formattedAmounts[0].currency })}`
    : formattedAmounts.length > 1 ? "Mixed currencies" : "—";
  const allEvents = replay?.events || [];
  const networkEvents = allEvents.filter((event) => event.category === "network");
  const consoleEvents = allEvents.filter((event) => event.category === "console" || event.category === "error" || event.severity === "error" || event.severity === "warn");

  return (
    <AgGridProvider modules={[AllCommunityModule]}>
      <div className="mx-auto max-w-[1600px] space-y-6">
        <header className="flex flex-col justify-between gap-4 border-b border-slate-800 pb-5 lg:flex-row lg:items-end">
          <div>
            <div className="flex items-center gap-2 text-xs text-slate-400"><span>Payments</span><span>/</span><span className="text-cyan-300">Transaction investigation</span></div>
            <h1 className="mt-2 font-display text-3xl font-bold tracking-tight text-white sm:text-4xl">Transaction Explorer</h1>
            <p className="mt-2 max-w-3xl text-sm text-slate-400">Trace a payment from persisted transaction data through lifecycle events and the customer session that produced it.</p>
          </div>
          <div className="flex items-center gap-2 rounded-lg border border-emerald-900/70 bg-emerald-950/30 px-3 py-2 text-xs text-emerald-300"><Activity className="h-4 w-4" />Authenticated PayTrace data</div>
        </header>

        {workspace && <section aria-label="Payment overview" className="grid grid-cols-2 gap-3 xl:grid-cols-6">
          <Kpi icon={<Activity className="h-4 w-4" />} label="Transactions" value={workspace.total_transactions.toLocaleString()} note="All persisted payments" />
          <Kpi icon={<CheckCircle2 className="h-4 w-4" />} label="Successful" value={workspace.successful_count.toLocaleString()} note="Captured and refunded" tone="green" />
          <Kpi icon={<ShieldAlert className="h-4 w-4" />} label="Failed" value={workspace.failed_count.toLocaleString()} note="Denied, failed, disputed" tone="rose" />
          <Kpi icon={<ArrowUpRight className="h-4 w-4" />} label="Success rate" value={`${workspace.success_rate_percent}%`} note={`${workspace.pending_count} pending or uncertain`} />
          <Kpi icon={<BarChart3 className="h-4 w-4" />} label="Processed amount" value={totalProcessed} note="Successful payments by currency" />
          <Kpi icon={<Clock3 className="h-4 w-4" />} label="Avg event latency" value={workspace.average_event_latency_ms == null ? "No data" : `${workspace.average_event_latency_ms} ms`} note={workspace.latency_sample_count ? `${workspace.latency_sample_count.toLocaleString()} recorded event samples` : "No persisted latency samples"} />
        </section>}

        {workspace?.anomalies.length ? <section className="space-y-2">
          <div className="flex items-center gap-2 text-sm font-semibold text-slate-200"><Sparkles className="h-4 w-4 text-amber-300" />Evidence-led findings <span className="text-xs font-normal text-slate-500">Deterministic rules; findings link to observed records.</span></div>
          <div className="grid gap-3 lg:grid-cols-2">{workspace.anomalies.slice(0, 4).map((finding) => <button key={finding.kind} onClick={() => {
            const hit = finding.payment_ids[0];
            if (hit) void openObservedPayment(hit);
          }} className="flex items-start justify-between gap-4 rounded-xl border border-amber-900/60 bg-amber-950/20 p-4 text-left hover:bg-amber-950/35">
            <span><span className="block text-sm font-semibold text-amber-100">{finding.title}</span><span className="mt-1 block text-xs leading-relaxed text-slate-400">{finding.evidence}</span></span>
            <span className="shrink-0 rounded-full bg-amber-900/50 px-2.5 py-1 text-xs font-bold text-amber-200">{finding.count}</span>
          </button>)}</div>
        </section> : null}

        {workspace?.failures_by_endpoint.length ? <section className="rounded-xl border border-slate-800 bg-slate-900/50 p-4">
          <div className="flex flex-wrap items-baseline justify-between gap-2"><h2 className="text-sm font-semibold text-slate-200">Network endpoints in sessions linked to failed payments</h2><span className="text-[10px] text-slate-500">Exact payment ID correlation · up to {workspace.endpoint_event_sample_limit.toLocaleString()} recent network events</span></div>
          <div className="mt-3 flex flex-wrap gap-2">{workspace.failures_by_endpoint.slice(0, 8).map((entry) => <button key={entry.endpoint} onClick={() => {
            const related = entry.payment_ids[0];
            if (related) void openObservedPayment(related);
          }} className="flex max-w-full items-center gap-2 rounded-lg border border-slate-800 bg-slate-950 px-3 py-2 text-left hover:border-rose-900/70"><span className="truncate font-mono text-[10px] text-slate-300">{entry.endpoint}</span><span className="shrink-0 rounded-full bg-rose-950/70 px-2 py-0.5 text-[10px] font-semibold text-rose-300">{entry.count}</span></button>)}</div>
        </section> : null}

        <section className="overflow-hidden rounded-2xl border border-slate-800 bg-slate-900/50 shadow-xl shadow-black/10">
          <div className="flex flex-col gap-3 border-b border-slate-800 p-4 sm:flex-row sm:items-center sm:justify-between">
            <div className="flex items-center gap-2" role="tablist" aria-label="Transaction workspace views">
              <button role="tab" aria-selected={activeView === "explorer"} onClick={() => setActiveView("explorer")} className={`rounded-lg px-3 py-2 text-xs font-semibold ${activeView === "explorer" ? "bg-cyan-500/15 text-cyan-200" : "text-slate-400 hover:bg-slate-800"}`}>Explorer</button>
              <button role="tab" aria-selected={activeView === "studio"} onClick={() => setActiveView("studio")} className={`rounded-lg px-3 py-2 text-xs font-semibold ${activeView === "studio" ? "bg-cyan-500/15 text-cyan-200" : "text-slate-400 hover:bg-slate-800"}`}>AG Studio analytics</button>
            </div>
            {activeView === "explorer" && <div className="flex flex-wrap items-center gap-2">
              <button onClick={() => gridApi.current?.exportDataAsCsv({ fileName: "paytrace-transactions.csv" })} disabled={!rows.length} className="inline-flex items-center gap-2 rounded-lg border border-slate-700 px-3 py-2 text-xs text-slate-200 hover:bg-slate-800 disabled:opacity-40"><Download className="h-3.5 w-3.5" />Export CSV</button>
              <button onClick={() => setSaveFilterOpen((open) => !open)} className="rounded-lg border border-slate-700 px-3 py-2 text-xs text-slate-200 hover:bg-slate-800">Save view</button>
              <button onClick={() => gridApi.current?.setFilterModel(null)} className="inline-flex items-center gap-1.5 rounded-lg border border-slate-700 px-3 py-2 text-xs text-slate-300 hover:bg-slate-800"><FilterX className="h-3.5 w-3.5" />Clear column filters</button>
            </div>}
          </div>

          {activeView === "studio" ? workspace ? <div className="p-4"><StudioDashboard workspace={workspace} /></div> : <LoadPanel loading={loading} error={workspaceError} retry={loadWorkspace} /> : <>
            <div className="flex flex-col gap-3 border-b border-slate-800 px-4 py-3 xl:flex-row xl:items-center">
              <form className="relative min-w-64 flex-1" onSubmit={(event) => { event.preventDefault(); setPage(1); setSearch(searchInput.trim()); }}>
                <Search className="absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-slate-500" />
                <input aria-label="Search transactions" value={searchInput} onChange={(event) => setSearchInput(event.target.value)} placeholder="Search transaction, order, customer, failure…" className="w-full rounded-lg border border-slate-700 bg-slate-950 py-2.5 pl-9 pr-3 text-xs text-slate-200 outline-none placeholder:text-slate-500 focus:border-cyan-700" />
              </form>
              <select aria-label="Filter by payment status" value={status} onChange={(event) => applyFilters({ status: event.target.value })} className="rounded-lg border border-slate-700 bg-slate-950 px-3 py-2.5 text-xs text-slate-200"><option value="">All statuses</option>{["CAPTURED", "REFUNDED", "DENIED", "CAPTURE_FAILED", "CAPTURE_UNCERTAIN", "CAPTURE_PENDING", "CREATED", "APPROVED", "DISPUTED"].map((value) => <option key={value}>{value}</option>)}</select>
              <select aria-label="Filter by provider" value={provider} onChange={(event) => applyFilters({ provider: event.target.value })} className="rounded-lg border border-slate-700 bg-slate-950 px-3 py-2.5 text-xs text-slate-200"><option value="">All providers / environments</option>{["PAYPAL_SANDBOX", "PAYPAL_LIVE", "SIMULATED"].map((value) => <option key={value}>{value}</option>)}</select>
              {saveFilterOpen && <div className="flex gap-2"><input aria-label="Saved view name" value={saveFilterName} onChange={(event) => setSaveFilterName(event.target.value)} placeholder="View name" className="w-32 rounded-lg border border-slate-700 bg-slate-950 px-3 py-2 text-xs text-slate-100" /><button onClick={saveFilter} className="rounded-lg bg-cyan-700 px-3 py-2 text-xs text-white">Save</button></div>}
              {savedFilters.length > 0 && <select aria-label="Load saved view" defaultValue="" onChange={(event) => { const saved = savedFilters.find((item) => item.name === event.target.value); if (saved) applyFilters(saved); }} className="max-w-44 rounded-lg border border-slate-700 bg-slate-950 px-3 py-2.5 text-xs text-slate-300"><option value="">Saved views…</option>{savedFilters.map((item) => <option key={item.name}>{item.name}</option>)}</select>}
            </div>

            <div className="flex flex-wrap items-center justify-between gap-2 border-b border-slate-800 bg-slate-950/60 px-4 py-2.5 text-[11px] text-slate-400">
              <div className="flex flex-wrap items-center gap-2">Showing <span className="font-semibold text-slate-200">{pageData ? Math.min((page - 1) * 100 + 1, pageData.total) : 0}–{Math.min(page * 100, pageData?.total || 0)}</span> of <span className="font-semibold text-slate-200">{(pageData?.total || 0).toLocaleString()}</span><span>· persisted fields sort server-side · floating filters and event-latency sorting apply to this page</span>{(status || provider || search) && <span className="rounded-full border border-cyan-800/60 bg-cyan-950/40 px-2 py-1 text-cyan-200">{[status, provider, search && `“${search}”`].filter(Boolean).join(" · ")}<button className="ml-2" aria-label="Clear active filters" onClick={() => applyFilters({ status: "", provider: "", search: "" })}><X className="inline h-3 w-3" /></button></span>}</div>
              <div className="flex items-center gap-2"><span>{selected.length ? `${selected.length} selected` : "Select rows for batch review"}</span><button onClick={() => { const first = selected[0]; if (first) void openInvestigation(first); }} disabled={!selected.length} className="rounded-md border border-slate-700 px-2.5 py-1.5 text-cyan-200 disabled:opacity-40">Review selection</button><button aria-label="Previous transaction page" onClick={() => setPage((value) => Math.max(1, value - 1))} disabled={page <= 1 || loading} className="rounded border border-slate-700 p-1.5 disabled:opacity-30"><ChevronLeft className="h-4 w-4" /></button><span>Page {page} / {pageCount}</span><button aria-label="Next transaction page" onClick={() => setPage((value) => Math.min(pageCount, value + 1))} disabled={page >= pageCount || loading} className="rounded border border-slate-700 p-1.5 disabled:opacity-30"><ChevronRight className="h-4 w-4" /></button></div>
            </div>

            {loadError ? <LoadPanel loading={loading} error={loadError} retry={loadPayments} /> : loading && !pageData ? <LoadPanel loading={true} /> : pageData?.total === 0 ? <div className="px-6 py-20 text-center"><Search className="mx-auto h-8 w-8 text-slate-600" /><h3 className="mt-3 text-sm font-semibold text-slate-200">No transactions match these filters</h3><p className="mt-1 text-xs text-slate-500">Clear filters or try a broader search.</p></div> : <div className="grid min-h-[600px] grid-cols-1 xl:grid-cols-[minmax(0,1fr)_370px]">
              <div className="min-w-0 p-3">
                <div className="mb-2 flex items-center justify-between px-1 text-[11px] text-slate-500"><span>AG Grid Community · multi-sort, filtering, column controls, row selection, persisted layout and CSV</span><span>Use Ctrl / Cmd + click to add a sort</span></div>
                <div className="h-[600px] overflow-hidden rounded-lg border border-slate-800">
                  <AgGridReact<ExplorerRow>
                    theme={themeQuartz.withParams({ backgroundColor: "#0b1220", foregroundColor: "#dbe4f0", headerBackgroundColor: "#111b2d", headerTextColor: "#94a3b8", borderColor: "#263449", rowHoverColor: "#142033", fontFamily: "Inter, sans-serif", fontSize: 12, accentColor: "#06b6d4" })}
                    rowData={rows}
                    columnDefs={columns}
                    defaultColDef={defaultColDef}
                    rowSelection={{ mode: "multiRow", checkboxes: true, headerCheckbox: true, enableClickSelection: true }}
                    getRowId={({ data }) => data.id}
                    multiSortKey="ctrl"
                    animateRows
                    suppressCellFocus
                    onGridReady={onGridReady}
                    onSortChanged={onSortChanged}
                    onColumnMoved={saveGridState}
                    onColumnResized={(event) => { if (event.finished) saveGridState(event); }}
                    onColumnVisible={saveGridState}
                    onSelectionChanged={onSelectionChanged}
                    onRowClicked={(event) => { if (event.data) void openInvestigation(event.data); }}
                    overlayNoRowsTemplate="<span class='ag-overlay-no-rows-center'>No transactions found for this query</span>"
                  />
                </div>
              </div>
              <InvestigationPanel payment={focusedPayment} timeline={timeline} replay={replay} loading={investigationLoading} error={investigationError} onClose={() => setFocusedPayment(null)} />
            </div>}
          </>}
        </section>
        <p className="flex items-start gap-2 px-1 text-[11px] leading-relaxed text-slate-500"><AlertTriangle className="mt-0.5 h-3.5 w-3.5 shrink-0 text-slate-600" />Payment method and completed-at timestamps are not captured by the current payment model. Processing duration is shown only when persisted payment event latency exists. Grouping and integrated charting are AG Grid Enterprise features; the Studio analytics view is separately licensed.</p>
      </div>
    </AgGridProvider>
  );
}

function Kpi({ icon, label, value, note, tone = "cyan" }: { icon: React.ReactNode; label: string; value: string; note: string; tone?: "cyan" | "green" | "rose" }) {
  const colors = tone === "green" ? "text-emerald-300" : tone === "rose" ? "text-rose-300" : "text-cyan-300";
  return <div className="rounded-xl border border-slate-800 bg-slate-900/60 p-4"><div className={`flex items-center gap-2 text-[11px] font-medium uppercase tracking-wide text-slate-500`}><span className={colors}>{icon}</span>{label}</div><p className="mt-2 truncate text-xl font-bold text-slate-100">{value}</p><p className="mt-1 truncate text-[10px] text-slate-500">{note}</p></div>;
}

function LoadPanel({ loading, error, retry }: { loading: boolean; error?: string | null; retry?: () => void }) {
  return <div className="flex min-h-64 flex-col items-center justify-center gap-3 px-6 text-center">{loading ? <Loader2 className="h-7 w-7 animate-spin text-cyan-300" /> : <AlertTriangle className="h-7 w-7 text-amber-300" />}<p className="text-sm text-slate-200">{loading ? "Loading payment evidence…" : "Payment data unavailable"}</p>{error && <p className="max-w-lg text-xs text-slate-500">{error}</p>}{retry && !loading && <button onClick={retry} className="rounded-lg border border-slate-700 px-3 py-2 text-xs text-slate-200">Retry</button>}</div>;
}

function InvestigationPanel({ payment, timeline, replay, loading, error, onClose }: { payment: PaymentItem | null; timeline: TimelineData | null; replay: BrowserSessionReplay | null; loading: boolean; error: string | null; onClose: () => void }) {
  const evidenceEvents = replay?.events.filter((event) => event.category === "network" || event.category === "console" || event.severity === "error" || event.severity === "warn") || [];
  return <aside className="min-h-[500px] border-t border-slate-800 bg-slate-950/65 p-4 xl:border-l xl:border-t-0">
    <div className="flex items-start justify-between"><div><p className="text-[10px] font-bold uppercase tracking-[0.16em] text-cyan-300">Investigation</p><h2 className="mt-1 text-sm font-semibold text-slate-100">{payment ? `Transaction ${payment.id.slice(0, 12)}…` : "Select a transaction"}</h2></div>{payment && <button aria-label="Close investigation" onClick={onClose} className="rounded p-1 text-slate-500 hover:bg-slate-800 hover:text-white"><X className="h-4 w-4" /></button>}</div>
    {!payment ? <div className="mt-8 rounded-xl border border-dashed border-slate-800 p-5 text-center"><ArrowDownRight className="mx-auto h-5 w-5 text-slate-600" /><p className="mt-2 text-xs text-slate-500">Choose a row to inspect its payment lifecycle, correlated browser events and session replay.</p></div> : loading ? <div className="flex h-40 items-center justify-center text-xs text-slate-400"><Loader2 className="mr-2 h-4 w-4 animate-spin" />Loading correlated evidence</div> : <div className="mt-4 space-y-4">
      {error && <p role="alert" className="rounded-lg border border-rose-900/70 bg-rose-950/30 p-3 text-xs text-rose-300">{error}</p>}
      <div className="rounded-xl border border-slate-800 bg-slate-900/60 p-3">
        <div className="flex items-center justify-between"><span className={`rounded-full border px-2 py-1 text-[10px] font-bold ${statusClass(payment.status)}`}>{payment.status}</span><span className="text-sm font-semibold text-slate-100">{Number(payment.amount).toLocaleString(undefined, { style: "currency", currency: payment.currency })}</span></div>
        <DetailLine label="PayPal order" value={payment.paypal_order_id || "—"} /><DetailLine label="Capture" value={payment.paypal_capture_id || "—"} /><DetailLine label="Customer" value={payment.customer_ref} /><DetailLine label="Created" value={formatDate(payment.created_at)} /><DetailLine label="Provider" value={payment.source_mode} />
        {payment.failure_reason && <p className="mt-2 rounded-md bg-rose-950/30 p-2 text-[11px] leading-relaxed text-rose-200">{payment.failure_code ? `${payment.failure_code}: ` : ""}{payment.failure_reason}</p>}
        <Link href={`/payments/${payment.id}`} className="mt-3 inline-flex items-center gap-1.5 text-xs font-medium text-cyan-300 hover:underline">Open full payment investigation <ExternalLink className="h-3 w-3" /></Link>
      </div>
      <div><h3 className="mb-2 flex items-center gap-2 text-xs font-semibold text-slate-200"><Clock3 className="h-3.5 w-3.5 text-cyan-300" />Persisted payment timeline <span className="font-normal text-slate-500">{timeline?.total_events ?? 0}</span></h3>{timeline?.events.length ? <div className="max-h-48 space-y-2 overflow-auto border-l border-slate-800 pl-3">{timeline.events.map((event: PaymentEventItem) => <div key={event.id} className="relative rounded-lg border border-slate-800 bg-slate-900/50 p-2.5 before:absolute before:-left-[17px] before:top-3 before:h-2 before:w-2 before:rounded-full before:bg-cyan-500"><p className="text-[11px] font-semibold text-slate-200">{event.event_type} · {event.status}</p><p className="mt-1 text-[10px] text-slate-500">{formatDate(event.occurred_at)} · {event.source}{event.latency_ms != null ? ` · ${event.latency_ms} ms` : ""}</p>{event.trace_id && <p className="mt-1 truncate font-mono text-[9px] text-slate-600">trace {event.trace_id}</p>}</div>)}</div> : <p className="rounded-lg border border-slate-800 p-3 text-[11px] text-slate-500">No payment lifecycle events are recorded.</p>}</div>
      <div><h3 className="mb-2 flex items-center gap-2 text-xs font-semibold text-slate-200"><Activity className="h-3.5 w-3.5 text-cyan-300" />Customer session</h3>{payment.session_id ? <><Link href={`/sessions/${payment.session_id}`} className="block truncate rounded-lg border border-cyan-900/60 bg-cyan-950/20 p-2.5 font-mono text-[10px] text-cyan-200 hover:bg-cyan-950/40">{payment.session_id} <ExternalLink className="inline h-3 w-3" /></Link><p className="mt-1 text-[10px] text-slate-500">{replay?.total_events ?? 0} session events · {replay?.events.filter((event) => event.category === "replay").length ?? 0} replay events in loaded segment</p></> : <p className="rounded-lg border border-slate-800 p-3 text-[11px] text-slate-500">No browser session is linked to this payment.</p>}</div>
      {payment.session_id && <div><h3 className="mb-1 text-xs font-semibold text-slate-200">Network & console events in this session <span className="font-normal text-slate-500">{evidenceEvents.length}</span></h3><p className="mb-2 text-[9px] leading-relaxed text-slate-500">Session context only. An event is directly payment-correlated only when it carries this transaction ID.</p>{evidenceEvents.length ? <div className="max-h-56 space-y-2 overflow-auto">{evidenceEvents.slice(0, 30).map((event) => <div key={event.id} className="rounded-lg border border-slate-800 bg-slate-900/60 p-2.5"><div className="flex justify-between gap-2"><span className="text-[10px] font-semibold text-slate-300">{event.category || event.severity || "event"} · {event.event_type}</span><span className={event.severity === "error" ? "text-[9px] text-rose-300" : "text-[9px] text-slate-500"}>{event.severity || "info"}</span></div><p className="mt-1 break-all text-[10px] text-slate-400">{event.route || String(event.payload.message || event.payload.url || event.payload.name || "Structured event details recorded")}</p><p className="mt-1 text-[9px] text-slate-600">{formatDate(event.occurred_at)}{event.payment_id === payment.id ? " · payment ID matched" : " · session-linked"}{event.trace_id ? ` · trace ${event.trace_id.slice(0, 12)}` : ""}</p></div>)}</div> : <p className="rounded-lg border border-slate-800 p-3 text-[11px] text-slate-500">No network or console events were returned for this session.</p>}</div>}
    </div>}
  </aside>;
}

function DetailLine({ label, value }: { label: string; value: string }) {
  return <div className="mt-2 flex min-w-0 items-start justify-between gap-3 text-[10px]"><span className="shrink-0 text-slate-500">{label}</span><span className="truncate text-right text-slate-300" title={value}>{value}</span></div>;
}
