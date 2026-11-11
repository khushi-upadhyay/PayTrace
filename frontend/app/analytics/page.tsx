"use client";

import { useEffect, useState } from "react";
import { RefreshButton } from "@/components/ui/RefreshButton";
import { api, AnalyticsData } from "@/lib/api";
import {
  BarChart3,
  TrendingUp,
  AlertTriangle,
  Clock,
  DollarSign,
  Activity,
  Loader2,
} from "lucide-react";
import {
  ResponsiveContainer,
  AreaChart,
  Area,
  BarChart,
  Bar,
  XAxis,
  YAxis,
  Tooltip,
  CartesianGrid,
  Cell,
  Legend,
  PieChart,
  Pie,
} from "recharts";

const COLORS = ["#0b73c2", "#f59e0b", "#f43f5e", "#8b5cf6", "#10b981"];
const STATUS_COLORS: Record<string, string> = {
  CAPTURED: "#059669",
  REFUNDED: "#0b73c2",
  CREATED: "#64748b",
  APPROVED: "#7c3aed",
  CAPTURE_PENDING: "#d97706",
  CAPTURE_UNCERTAIN: "#ea580c",
  CAPTURE_FAILED: "#e11d48",
  DENIED: "#be123c",
  DISPUTED: "#9333ea",
};

export default function AnalyticsPage() {
  const [analytics, setAnalytics] = useState<AnalyticsData | null>(null);
  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [providerOutcomes, setProviderOutcomes] = useState<Array<{ provider: string; status: string; count: number }>>([]);

  const fetchAnalytics = async () => {
    try {
      setLoading(true);
      setLoadError(null);
      const [data, workspace] = await Promise.all([api.getAnalytics(), api.getPaymentWorkspace(1)]);
      setAnalytics(data);
      setProviderOutcomes(workspace.provider_outcomes);
    } catch (err: any) {
      setLoadError(err.message || "Unable to load analytics from the backend.");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchAnalytics();
  }, []);

  const providerOutcomeRows = Array.from(providerOutcomes.reduce((providers, entry) => {
    const row = providers.get(entry.provider) ?? { provider: entry.provider } as Record<string, string | number>;
    row[entry.status] = entry.count;
    providers.set(entry.provider, row);
    return providers;
  }, new Map<string, Record<string, string | number>>()).values());
  const providerStatuses = Array.from(new Set(providerOutcomes.map((entry) => entry.status)));

  if (loading) {
    return (
      <div className="flex flex-col items-center justify-center min-h-[60vh] space-y-4">
        <Loader2 className="w-8 h-8 text-cyan-400 animate-spin" />
        <p className="text-sm text-slate-400">Aggregating telemetry metrics...</p>
      </div>
    );
  }

  if (!analytics) {
    return (
      <div role="alert" className="mx-auto max-w-xl rounded-xl border border-rose-500/30 bg-rose-950/20 p-8 text-center">
        <p className="text-sm font-semibold text-rose-200">Analytics are unavailable</p>
        <p className="mt-2 text-xs text-slate-400">{loadError || "No analytics response was returned."}</p>
        <button onClick={fetchAnalytics} className="mt-4 rounded-lg bg-paypal-navy px-3 py-2 text-xs text-onsolid transition-colors duration-150 hover:bg-paypal-blue">Retry</button>
      </div>
    );
  }

  return (
    <div className="space-y-8 max-w-7xl mx-auto animate-fadeIn pb-16">
      {/* Header */}
      <div className="flex flex-col md:flex-row md:items-center justify-between gap-4 pb-2">
        <div>
          <h1 className="font-display text-4xl font-bold tracking-tight text-black">
            Historical Performance
          </h1>
          <p className="text-base text-black/70 mt-2">
            Historical payment volume, outcomes, recorded event latency, and failure categories. Settlement metrics are not available in this data model.
          </p>
        </div>
        <RefreshButton onClick={fetchAnalytics} />
      </div>

      {/* KPI Row */}
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-5 gap-4">
        <div className="glass-card rounded-xl p-5 border border-slate-800 space-y-1.5">
          <span className="text-xs font-medium text-slate-400">Payment records</span>
          <div className="text-2xl font-extrabold text-ink">{analytics.total_payments.toLocaleString()}</div>
          <span className="text-[11px] text-emerald-400 font-semibold">{analytics.success_rate_percent}% Success Ratio</span>
        </div>

        <div className="glass-card rounded-xl p-5 border border-slate-800 space-y-1.5">
          <span className="text-xs font-medium text-slate-400">Potential Revenue at Risk</span>
          <div className="text-2xl font-extrabold text-amber-400">
            {analytics.potential_revenue_at_risk == null ? "Multiple currencies" : new Intl.NumberFormat(undefined, { style: "currency", currency: analytics.currency }).format(Number(analytics.potential_revenue_at_risk))}
          </div>
          <span className="text-[11px] text-amber-400/80">From {analytics.failed_payments + analytics.uncertain_payments} unresolved payments</span>
          {analytics.revenue_at_risk_by_currency.length > 1 && <span className="block text-[10px] text-slate-400">{analytics.revenue_at_risk_by_currency.map((item) => new Intl.NumberFormat(undefined, { style: "currency", currency: item.currency }).format(Number(item.amount))).join(" · ")}</span>}
        </div>

        <div className="glass-card rounded-xl p-5 border border-slate-800 space-y-1.5">
          <span className="text-xs font-medium text-slate-400">Recorded event latency</span>
          <div className="text-2xl font-extrabold text-ink">{analytics.average_latency_ms == null ? "No data" : `${analytics.average_latency_ms} ms`}</div>
          <span className="text-[11px] text-slate-400">Average of persisted payment event samples</span>
        </div>

        <div className="glass-card rounded-xl p-5 border border-slate-800 space-y-1.5">
          <span className="text-xs font-medium text-slate-400">Webhook arrival delay</span>
          <div className="text-2xl font-extrabold text-ink">{analytics.average_webhook_delay_seconds == null ? "No data" : `${analytics.average_webhook_delay_seconds} s`}</div>
          <span className="text-[11px] text-slate-400">Provider event timestamps are not currently persisted</span>
        </div>

        <div className="glass-card rounded-xl p-5 border border-slate-800 space-y-1.5">
          <span className="text-xs font-medium text-slate-400">Open incidents</span>
          <div className="text-2xl font-extrabold text-ink">{analytics.open_incidents_count.toLocaleString()}</div>
          <span className="text-[11px] text-slate-400">Unresolved incidents in the stored workspace</span>
        </div>
      </div>

      {/* Detailed Charts Grid */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        {/* Daily Volume Trend */}
        <div className="glass-panel rounded-2xl p-6 border border-slate-800 space-y-4">
          <div>
            <h3 className="text-sm font-bold text-ink">Transaction Outcome Volume</h3>
            <p className="text-xs text-slate-400">Succeeded vs Failed vs Ambiguous/Uncertain</p>
          </div>
          <div className="h-72 w-full">
            <ResponsiveContainer width="100%" height="100%">
              <BarChart data={analytics.volume_over_time} margin={{ top: 10, right: 10, left: -20, bottom: 0 }}>
                <CartesianGrid strokeDasharray="3 3" stroke="var(--chart-grid)" />
                <XAxis dataKey="date" stroke="var(--chart-axis)" fontSize={11} />
                <YAxis stroke="var(--chart-axis)" fontSize={11} />
                <Tooltip contentStyle={{ backgroundColor: "var(--chart-tooltip-bg)", borderColor: "var(--chart-tooltip-border)", borderRadius: "8px", fontSize: "12px" }} />
                <Bar dataKey="successful" fill="#10b981" name="Successful" radius={[4, 4, 0, 0]} />
                <Bar dataKey="failed" fill="#f43f5e" name="Failed" radius={[4, 4, 0, 0]} />
                <Bar dataKey="uncertain" fill="#f59e0b" name="Uncertain / Timeout" radius={[4, 4, 0, 0]} />
              </BarChart>
            </ResponsiveContainer>
          </div>
        </div>

        {/* Failure Breakdown Distribution */}
        <div className="glass-panel rounded-2xl p-6 border border-slate-800 space-y-4">
          <div>
            <h3 className="text-sm font-bold text-ink">Failure Code Categorization</h3>
            <p className="text-xs text-slate-400">Frequency of failure codes across recorded incidents</p>
          </div>
          <div className="h-72 w-full">
            <ResponsiveContainer width="100%" height="100%">
              <BarChart
                layout="vertical"
                data={analytics.failure_categories}
                margin={{ top: 10, right: 20, left: 40, bottom: 0 }}
              >
                <CartesianGrid strokeDasharray="3 3" stroke="var(--chart-grid)" />
                <XAxis type="number" stroke="var(--chart-axis)" fontSize={11} />
                <YAxis type="category" dataKey="category" stroke="var(--chart-axis)" fontSize={10} width={170} />
                <Tooltip contentStyle={{ backgroundColor: "var(--chart-tooltip-bg)", borderColor: "var(--chart-tooltip-border)", borderRadius: "8px", fontSize: "12px" }} />
                <Bar dataKey="count" fill="#0b73c2" name="Occurrences" radius={[0, 4, 4, 0]}>
                  {analytics.failure_categories.map((entry, index) => (
                    <Cell key={`cell-${index}`} fill={COLORS[index % COLORS.length]} />
                  ))}
                </Bar>
              </BarChart>
            </ResponsiveContainer>
          </div>
        </div>

        <div className="glass-panel rounded-2xl p-6 border border-slate-800 space-y-4 lg:col-span-2">
          <div><h3 className="text-sm font-bold text-ink">Payment outcomes by provider environment</h3><p className="text-xs text-slate-400">Counts grouped from persisted payment source and status fields.</p></div>
          {providerOutcomeRows.length ? <div className="h-72 w-full"><ResponsiveContainer width="100%" height="100%"><BarChart data={providerOutcomeRows} margin={{ top: 10, right: 20, left: -15, bottom: 4 }}><CartesianGrid strokeDasharray="3 3" stroke="var(--chart-grid)" /><XAxis dataKey="provider" stroke="var(--chart-axis)" fontSize={11} /><YAxis stroke="var(--chart-axis)" fontSize={11} allowDecimals={false} /><Tooltip contentStyle={{ backgroundColor: "var(--chart-tooltip-bg)", borderColor: "var(--chart-tooltip-border)", borderRadius: "8px", fontSize: "12px" }} /><Legend />{providerStatuses.map((status, index) => <Bar key={status} dataKey={status} stackId="outcomes" fill={COLORS[index % COLORS.length]} name={status.replaceAll("_", " ")} />)}</BarChart></ResponsiveContainer></div> : <p className="py-12 text-center text-xs text-slate-500">No provider outcome data is stored.</p>}
        </div>

        <div className="glass-panel rounded-2xl p-6 border border-slate-800 space-y-4 lg:col-span-2">
          <div>
            <h3 className="text-sm font-bold text-ink">Payment lifecycle status mix</h3>
            <p className="text-xs text-slate-400">Persisted payment records grouped by their current lifecycle status.</p>
          </div>
          {analytics.status_breakdown.length ? <div className="grid grid-cols-1 items-center gap-4 sm:grid-cols-[minmax(0,1fr)_minmax(0,1fr)]">
            <div className="h-64 min-w-0">
              <ResponsiveContainer width="100%" height="100%">
                <PieChart>
                  <Pie data={analytics.status_breakdown} dataKey="count" nameKey="status" innerRadius={58} outerRadius={92} paddingAngle={2}>
                    {analytics.status_breakdown.map((entry, index) => <Cell key={entry.status} fill={STATUS_COLORS[entry.status] || COLORS[index % COLORS.length]} />)}
                  </Pie>
                  <Tooltip contentStyle={{ backgroundColor: "var(--chart-tooltip-bg)", borderColor: "var(--chart-tooltip-border)", borderRadius: "8px", fontSize: "12px" }} />
                  <Legend formatter={(value) => String(value).replaceAll("_", " ")} />
                </PieChart>
              </ResponsiveContainer>
            </div>
            <ul className="space-y-2" aria-label="Payment counts by status">
              {analytics.status_breakdown.slice().sort((a, b) => b.count - a.count).map((entry) => <li key={entry.status} className="flex items-center justify-between gap-3 rounded-lg border border-slate-700 bg-slate-900/50 px-3 py-2 text-xs">
                <span className="flex min-w-0 items-center gap-2 font-medium text-slate-200"><span className="h-2.5 w-2.5 shrink-0 rounded-full" style={{ backgroundColor: STATUS_COLORS[entry.status] || "#64748b" }} /> <span className="truncate">{entry.status.replaceAll("_", " ")}</span></span>
                <span className="font-bold tabular-nums text-white">{entry.count.toLocaleString()}</span>
              </li>)}
            </ul>
          </div> : <p className="py-12 text-center text-xs text-slate-400">No payment status records are stored.</p>}
        </div>
      </div>
    </div>
  );
}
