"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { api, AnalyticsData, PaymentItem, IncidentItem } from "@/lib/api";
import {
  TrendingUp,
  AlertTriangle,
  Clock,
  DollarSign,
  Activity,
  ArrowRight,
  ShieldAlert,
  Loader2,
  RefreshCw,
  CheckCircle,
  HelpCircle,
} from "lucide-react";
import {
  ResponsiveContainer,
  AreaChart,
  Area,
  XAxis,
  YAxis,
  Tooltip,
  BarChart,
  Bar,
  CartesianGrid,
  Cell,
  PieChart,
  Pie,
} from "recharts";

const PIE_COLORS = ["#06b6d4", "#f59e0b", "#f43f5e", "#8b5cf6", "#10b981"];

export default function DashboardPage() {
  const [analytics, setAnalytics] = useState<AnalyticsData | null>(null);
  const [recentPayments, setRecentPayments] = useState<PaymentItem[]>([]);
  const [incidents, setIncidents] = useState<IncidentItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const loadData = async () => {
    try {
      setLoading(true);
      setError(null);
      const [anData, pmData, incData] = await Promise.all([
        api.getAnalytics(),
        api.getPayments({ page: 1, page_size: 6 }),
        api.getIncidents(),
      ]);
      setAnalytics(anData);
      setRecentPayments(pmData.items);
      setIncidents(incData.items.filter((i) => i.status !== "RESOLVED"));
    } catch (err: any) {
      setError(err.message || "Failed to load dashboard metrics");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    loadData();
  }, []);

  if (loading) {
    return (
      <div className="flex flex-col items-center justify-center min-h-[60vh] space-y-4">
        <Loader2 className="w-8 h-8 text-cyan-400 animate-spin" />
        <p className="text-sm text-slate-400">Loading cross-signal payment observability metrics...</p>
      </div>
    );
  }

  if (error || !analytics) {
    return (
      <div className="glass-panel p-8 rounded-xl border border-rose-500/30 text-center space-y-4 max-w-xl mx-auto my-12">
        <AlertTriangle className="w-10 h-10 text-rose-400 mx-auto" />
        <h2 className="text-lg font-bold text-white">Observability Gateway Unreachable</h2>
        <p className="text-xs text-slate-400">{error || "Could not retrieve analytics data from backend."}</p>
        <button
          onClick={loadData}
          className="px-4 py-2 bg-slate-800 hover:bg-slate-700 text-white text-xs font-semibold rounded-lg"
        >
          Retry Connection
        </button>
      </div>
    );
  }

  return (
    <div className="space-y-8 animate-fadeIn max-w-7xl mx-auto">
      {/* Page Header */}
      <div className="flex flex-col md:flex-row md:items-center justify-between gap-4 pb-2 border-b border-slate-800">
        <div>
          <h1 className="text-2xl font-bold tracking-tight text-white flex items-center gap-2.5">
            <Activity className="w-6 h-6 text-cyan-400" />
            Payment Observability Overview
          </h1>
          <p className="text-xs text-slate-400 mt-1">
            Real-time telemetry, stage latencies, and revenue at risk across PayPal transactions.
          </p>
        </div>
        <div className="flex items-center gap-3">
          <span className="text-[11px] font-mono px-2.5 py-1 rounded bg-slate-900 border border-slate-800 text-slate-400">
            DEMO SEED DATA ACTIVE
          </span>
          <button
            onClick={loadData}
            className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-slate-900 border border-slate-700 hover:bg-slate-800 text-xs text-slate-300 font-medium transition-colors"
          >
            <RefreshCw className="w-3.5 h-3.5" />
            Refresh
          </button>
        </div>
      </div>

      {/* Active Incidents Alert Banner if any */}
      {incidents.length > 0 && (
        <div className="glass-panel rounded-xl p-4 border border-amber-500/30 bg-amber-950/20 glow-amber flex flex-col md:flex-row items-start md:items-center justify-between gap-4">
          <div className="flex items-center gap-3">
            <div className="p-2 rounded-lg bg-amber-500/20 text-amber-400">
              <ShieldAlert className="w-5 h-5" />
            </div>
            <div>
              <h3 className="text-sm font-bold text-amber-200">
                {incidents.length} Active Incident{incidents.length > 1 ? "s" : ""} Detected by Deterministic Rules
              </h3>
              <p className="text-xs text-amber-300/80">
                {incidents[0].title} — {incidents[0].affected_payment_count} payment(s) affected (${Number(incidents[0].revenue_at_risk).toFixed(2)} at risk).
              </p>
            </div>
          </div>
          <Link
            href={`/incidents/${incidents[0].id}`}
            className="flex items-center gap-1.5 px-3.5 py-1.5 rounded-lg bg-amber-500 text-slate-950 text-xs font-bold hover:bg-amber-400 transition-colors shrink-0"
          >
            Review Diagnostic
            <ArrowRight className="w-3.5 h-3.5" />
          </Link>
        </div>
      )}

      {/* KPI Cards Grid */}
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-5 gap-4">
        {/* Success Rate */}
        <div className="glass-card rounded-xl p-5 border border-slate-800 space-y-2">
          <div className="flex items-center justify-between">
            <span className="text-xs font-medium text-slate-400">Success Rate</span>
            <CheckCircle className="w-4 h-4 text-emerald-400" />
          </div>
          <div className="text-2xl font-extrabold text-white">{analytics.success_rate_percent}%</div>
          <div className="text-[11px] text-emerald-400 font-medium flex items-center gap-1">
            <span>{analytics.successful_payments} of {analytics.total_payments} settled</span>
          </div>
        </div>

        {/* Failed Payments */}
        <div className="glass-card rounded-xl p-5 border border-slate-800 space-y-2">
          <div className="flex items-center justify-between">
            <span className="text-xs font-medium text-slate-400">Failed Payments</span>
            <AlertTriangle className="w-4 h-4 text-rose-400" />
          </div>
          <div className="text-2xl font-extrabold text-rose-400">{analytics.failed_payments}</div>
          <div className="text-[11px] text-slate-400">
            {analytics.failure_rate_percent}% total failure rate
          </div>
        </div>

        {/* Revenue at Risk */}
        <div className="glass-card rounded-xl p-5 border border-slate-800 space-y-2">
          <div className="flex items-center justify-between">
            <span className="text-xs font-medium text-slate-400">Revenue at Risk</span>
            <DollarSign className="w-4 h-4 text-amber-400" />
          </div>
          <div className="text-2xl font-extrabold text-amber-400">
            ${Number(analytics.potential_revenue_at_risk).toFixed(2)}
          </div>
          <div className="text-[11px] text-amber-400/80">
            Potential loss; unconfirmed
          </div>
        </div>

        {/* Latency */}
        <div className="glass-card rounded-xl p-5 border border-slate-800 space-y-2">
          <div className="flex items-center justify-between">
            <span className="text-xs font-medium text-slate-400">Avg API Latency</span>
            <Clock className="w-4 h-4 text-sky-400" />
          </div>
          <div className="text-2xl font-extrabold text-white">{analytics.average_latency_ms} ms</div>
          <div className="text-[11px] text-slate-400">
            Stage SLA target: &lt;800ms
          </div>
        </div>

        {/* Uncertain States */}
        <div className="glass-card rounded-xl p-5 border border-slate-800 space-y-2">
          <div className="flex items-center justify-between">
            <span className="text-xs font-medium text-slate-400">Uncertain / Timeouts</span>
            <HelpCircle className="w-4 h-4 text-amber-400" />
          </div>
          <div className="text-2xl font-extrabold text-white">{analytics.uncertain_payments}</div>
          <div className="text-[11px] text-amber-400 font-medium">
            Requires reconciliation
          </div>
        </div>
      </div>

      {/* Analytics Charts Row */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        {/* Payment Volume Trend */}
        <div className="glass-panel rounded-xl p-6 border border-slate-800 lg:col-span-2 space-y-4">
          <div className="flex items-center justify-between">
            <div>
              <h3 className="text-sm font-bold text-white">Payment Volume & Settlement Trend</h3>
              <p className="text-xs text-slate-400">Daily lifecycle transaction volume breakdown</p>
            </div>
            <span className="text-[11px] font-mono text-cyan-400">Volume</span>
          </div>

          <div className="h-64 w-full">
            <ResponsiveContainer width="100%" height="100%">
              <AreaChart data={analytics.volume_over_time} margin={{ top: 10, right: 10, left: -20, bottom: 0 }}>
                <defs>
                  <linearGradient id="colorTotal" x1="0" y1="0" x2="0" y2="1">
                    <stop offset="5%" stopColor="#06b6d4" stopOpacity={0.4} />
                    <stop offset="95%" stopColor="#06b6d4" stopOpacity={0} />
                  </linearGradient>
                  <linearGradient id="colorSuccess" x1="0" y1="0" x2="0" y2="1">
                    <stop offset="5%" stopColor="#10b981" stopOpacity={0.3} />
                    <stop offset="95%" stopColor="#10b981" stopOpacity={0} />
                  </linearGradient>
                </defs>
                <CartesianGrid strokeDasharray="3 3" stroke="#1e293b" />
                <XAxis dataKey="date" stroke="#64748b" fontSize={11} />
                <YAxis stroke="#64748b" fontSize={11} />
                <Tooltip
                  contentStyle={{ backgroundColor: "#0f172a", borderColor: "#334155", borderRadius: "8px", fontSize: "12px" }}
                />
                <Area type="monotone" dataKey="total" stroke="#06b6d4" fillOpacity={1} fill="urlColorTotal" name="Total Volume" />
                <Area type="monotone" dataKey="successful" stroke="#10b981" fillOpacity={1} fill="urlColorSuccess" name="Successful" />
              </AreaChart>
            </ResponsiveContainer>
          </div>
        </div>

        {/* Failure Breakdown Pie */}
        <div className="glass-panel rounded-xl p-6 border border-slate-800 space-y-4">
          <div className="flex items-center justify-between">
            <div>
              <h3 className="text-sm font-bold text-white">Failure Code Distribution</h3>
              <p className="text-xs text-slate-400">Categorized error occurrences</p>
            </div>
            <span className="text-[11px] font-mono text-rose-400">Failures</span>
          </div>

          <div className="h-64 w-full flex items-center justify-center">
            {analytics.failure_categories.length > 0 ? (
              <ResponsiveContainer width="100%" height="100%">
                <PieChart>
                  <Pie
                    data={analytics.failure_categories}
                    dataKey="count"
                    nameKey="category"
                    cx="50%"
                    cy="50%"
                    outerRadius={75}
                    label={({ category, count }) => `${category.slice(0, 10)}: ${count}`}
                    fontSize={10}
                  >
                    {analytics.failure_categories.map((entry, index) => (
                      <Cell key={`cell-${index}`} fill={PIE_COLORS[index % PIE_COLORS.length]} />
                    ))}
                  </Pie>
                  <Tooltip
                    contentStyle={{ backgroundColor: "#0f172a", borderColor: "#334155", borderRadius: "8px", fontSize: "12px" }}
                  />
                </PieChart>
              </ResponsiveContainer>
            ) : (
              <div className="text-center text-xs text-slate-500">No active failures detected</div>
            )}
          </div>
        </div>
      </div>

      {/* Recent Activity Table */}
      <div className="glass-panel rounded-xl border border-slate-800 overflow-hidden">
        <div className="p-5 border-b border-slate-800 flex items-center justify-between">
          <div>
            <h3 className="text-sm font-bold text-white">Recent Payment Journeys</h3>
            <p className="text-xs text-slate-400">Latest transactions correlated across PayPal and merchant backend</p>
          </div>
          <Link
            href="/payments"
            className="flex items-center gap-1.5 text-xs text-cyan-400 hover:text-cyan-300 font-semibold transition-colors"
          >
            View Full Ledger
            <ArrowRight className="w-3.5 h-3.5" />
          </Link>
        </div>

        <div className="overflow-x-auto">
          <table className="w-full text-left text-xs">
            <thead className="bg-slate-900/60 border-b border-slate-800 text-slate-400 font-mono uppercase text-[10px]">
              <tr>
                <th className="px-5 py-3">PayTrace ID</th>
                <th className="px-5 py-3">PayPal Order ID</th>
                <th className="px-5 py-3">Amount</th>
                <th className="px-5 py-3">Status</th>
                <th className="px-5 py-3">Failure Reason</th>
                <th className="px-5 py-3">Source</th>
                <th className="px-5 py-3 text-right">Action</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-800/80">
              {recentPayments.map((p) => (
                <tr key={p.id} className="hover:bg-slate-900/40 transition-colors">
                  <td className="px-5 py-3.5 font-mono text-cyan-400 font-medium">
                    {p.id.slice(0, 13)}...
                  </td>
                  <td className="px-5 py-3.5 font-mono text-slate-300">
                    {p.paypal_order_id || "N/A"}
                  </td>
                  <td className="px-5 py-3.5 font-semibold text-white">
                    ${Number(p.amount).toFixed(2)} {p.currency}
                  </td>
                  <td className="px-5 py-3.5">
                    <span
                      className={`inline-flex items-center px-2 py-0.5 rounded-full text-[10px] font-semibold tracking-wide ${
                        p.status === "CAPTURED"
                          ? "bg-emerald-950 text-emerald-300 border border-emerald-800/60"
                          : p.status === "CAPTURE_UNCERTAIN"
                          ? "bg-amber-950 text-amber-300 border border-amber-800/60 animate-pulse"
                          : p.status === "DENIED" || p.status === "CAPTURE_FAILED"
                          ? "bg-rose-950 text-rose-300 border border-rose-800/60"
                          : p.status === "REFUNDED"
                          ? "bg-purple-950 text-purple-300 border border-purple-800/60"
                          : "bg-slate-800 text-slate-300"
                      }`}
                    >
                      {p.status}
                    </span>
                  </td>
                  <td className="px-5 py-3.5 text-slate-400 max-w-xs truncate">
                    {p.failure_reason || (p.status === "CAPTURED" ? "Normal settlement" : "—")}
                  </td>
                  <td className="px-5 py-3.5">
                    <span className="text-[10px] font-mono px-1.5 py-0.5 rounded bg-slate-900 text-slate-400 border border-slate-800">
                      {p.source_mode}
                    </span>
                  </td>
                  <td className="px-5 py-3.5 text-right">
                    <Link
                      href={`/payments/${p.id}`}
                      className="px-2.5 py-1 rounded bg-cyan-950/80 hover:bg-cyan-900 border border-cyan-800/80 text-cyan-300 text-[11px] font-medium transition-colors inline-flex items-center gap-1"
                    >
                      Investigate
                      <ArrowRight className="w-3 h-3" />
                    </Link>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
}
