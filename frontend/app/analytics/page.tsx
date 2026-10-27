"use client";

import { useEffect, useState } from "react";
import { api, AnalyticsData } from "@/lib/api";
import {
  BarChart3,
  TrendingUp,
  AlertTriangle,
  Clock,
  DollarSign,
  Activity,
  Loader2,
  RefreshCw,
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
  PieChart,
  Pie,
} from "recharts";

const COLORS = ["#0b73c2", "#f59e0b", "#f43f5e", "#8b5cf6", "#10b981"];

export default function AnalyticsPage() {
  const [analytics, setAnalytics] = useState<AnalyticsData | null>(null);
  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState<string | null>(null);

  const fetchAnalytics = async () => {
    try {
      setLoading(true);
      setLoadError(null);
      const data = await api.getAnalytics();
      setAnalytics(data);
    } catch (err: any) {
      setLoadError(err.message || "Unable to load analytics from the backend.");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchAnalytics();
  }, []);

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
        <button onClick={fetchAnalytics} className="mt-4 rounded-lg bg-slate-800 px-3 py-2 text-xs text-white hover:bg-slate-700">Retry</button>
      </div>
    );
  }

  return (
    <div className="space-y-8 max-w-7xl mx-auto animate-fadeIn pb-16">
      {/* Header */}
      <div className="flex flex-col md:flex-row md:items-center justify-between gap-4 pb-2">
        <div>
          <h1 className="font-display text-4xl font-bold tracking-tight text-black">
            Performance & SLA Analytics
          </h1>
          <p className="text-base text-black/70 mt-2">
            Stage latencies, failure distributions, and revenue impact trends across PayPal checkout journeys.
          </p>
        </div>
        <button
          onClick={fetchAnalytics}
          className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-slate-900 border border-slate-700 hover:bg-slate-800 text-xs text-slate-300 font-medium transition-colors"
        >
          <RefreshCw className="w-3.5 h-3.5" />
          Refresh
        </button>
      </div>

      {/* KPI Row */}
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
        <div className="glass-card rounded-xl p-5 border border-slate-800 space-y-1.5">
          <span className="text-xs font-medium text-slate-400">Total Settlement Volume</span>
          <div className="text-2xl font-extrabold text-ink">{analytics.total_payments} Transactions</div>
          <span className="text-[11px] text-emerald-400 font-semibold">{analytics.success_rate_percent}% Success Ratio</span>
        </div>

        <div className="glass-card rounded-xl p-5 border border-slate-800 space-y-1.5">
          <span className="text-xs font-medium text-slate-400">Potential Revenue at Risk</span>
          <div className="text-2xl font-extrabold text-amber-400">
            ${Number(analytics.potential_revenue_at_risk).toFixed(2)}
          </div>
          <span className="text-[11px] text-amber-400/80">From {analytics.failed_payments + analytics.uncertain_payments} unresolved payments</span>
        </div>

        <div className="glass-card rounded-xl p-5 border border-slate-800 space-y-1.5">
          <span className="text-xs font-medium text-slate-400">Average Outbound Latency</span>
          <div className="text-2xl font-extrabold text-ink">{analytics.average_latency_ms} ms</div>
          <span className="text-[11px] text-slate-400">Across API order & capture calls</span>
        </div>

        <div className="glass-card rounded-xl p-5 border border-slate-800 space-y-1.5">
          <span className="text-xs font-medium text-slate-400">Avg Webhook Arrival Delay</span>
          <div className="text-2xl font-extrabold text-ink">{analytics.average_webhook_delay_seconds} s</div>
          <span className="text-[11px] text-emerald-400">Well within healthy delivery SLA</span>
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
                <YAxis type="category" dataKey="category" stroke="var(--chart-axis)" fontSize={10} width={100} />
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
      </div>
    </div>
  );
}
