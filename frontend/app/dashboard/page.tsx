"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { api, AnalyticsData, PaymentItem, IncidentItem } from "@/lib/api";
import { useAuth } from "@/components/providers/AuthProvider";
import {
  AlertTriangle,
  Clock,
  ShieldAlert,
  Loader2,
  RefreshCw,
  CheckCircle,
  HelpCircle,
  Brain,
  ShieldCheck,
  ShoppingCart,
  ChevronRight,
  XCircle,
  RotateCcw,
  BarChart3,
} from "lucide-react";
import {
  ResponsiveContainer,
  AreaChart,
  Area,
  XAxis,
  YAxis,
  Tooltip,
  CartesianGrid,
  Cell,
  PieChart,
  Pie,
} from "recharts";

const PIE_COLORS = ["#2c4fae", "#f59e0b", "#f43f5e", "#8b5cf6", "#10b981"];

const STATUS_META: Record<string, { label: string; chip: string; icon: any; iconBox: string }> = {
  CAPTURED: { label: "Completed", chip: "bg-emerald-950 text-emerald-300", icon: CheckCircle, iconBox: "bg-emerald-950 text-emerald-400" },
  CAPTURE_UNCERTAIN: { label: "Needs review", chip: "bg-amber-950 text-amber-300", icon: HelpCircle, iconBox: "bg-amber-950 text-amber-400" },
  DENIED: { label: "Declined", chip: "bg-rose-950 text-rose-300", icon: XCircle, iconBox: "bg-rose-950 text-rose-400" },
  CAPTURE_FAILED: { label: "Failed", chip: "bg-rose-950 text-rose-300", icon: XCircle, iconBox: "bg-rose-950 text-rose-400" },
  REFUNDED: { label: "Refunded", chip: "bg-purple-950 text-purple-300", icon: RotateCcw, iconBox: "bg-purple-950 text-purple-400" },
};
const FALLBACK_STATUS = { label: "", chip: "bg-slate-800 text-slate-300", icon: Clock, iconBox: "bg-slate-800 text-slate-400" };

function greeting() {
  const h = new Date().getHours();
  return h < 12 ? "Good morning" : h < 18 ? "Good afternoon" : "Good evening";
}

function formatDate(iso?: string) {
  if (!iso) return "";
  const d = new Date(iso.endsWith("Z") ? iso : iso + "Z");
  return d.toLocaleDateString(undefined, { month: "short", day: "numeric" });
}

export default function DashboardPage() {
  const { user } = useAuth();
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
        <h2 className="text-lg font-bold text-ink">Observability Gateway Unreachable</h2>
        <p className="text-xs text-slate-400">{error || "Could not retrieve analytics data from backend."}</p>
        <button
          onClick={loadData}
          className="px-4 py-2 bg-slate-800 hover:bg-slate-700 text-ink text-xs font-semibold rounded-lg transition-colors duration-150"
        >
          Retry Connection
        </button>
      </div>
    );
  }

  const tooltipStyle = {
    backgroundColor: "var(--chart-tooltip-bg)",
    borderColor: "var(--chart-tooltip-border)",
    borderRadius: "8px",
    fontSize: "12px",
  };
  const firstName = user?.name.split(/\s+/)[0] ?? "there";
  const openIncident = incidents[0];

  const settledPct = analytics.total_payments > 0 ? (analytics.successful_payments / analytics.total_payments) * 100 : 0;
  const ring = 2 * Math.PI * 22;
  const reviewHref = openIncident ? `/incidents/${openIncident.id}` : "/incidents";

  return (
    <div className="animate-fadeIn overflow-x-clip">
      {/* Alert strip, like PayPal's red "you're almost there" bar */}
      {openIncident && (
        <Link
          href={reviewHref}
          className="relative left-1/2 -mt-8 mb-0 flex w-screen -translate-x-1/2 items-center bg-[#c3281c] text-white transition-colors duration-150 hover:bg-[#b02217]"
        >
          <div className="mx-auto flex w-full max-w-7xl items-center gap-4 px-6 py-5">
            <AlertTriangle className="h-5 w-5 shrink-0" />
            <div className="min-w-0 flex-1">
              <div className="text-xl leading-tight">
                {incidents.length} active incident{incidents.length > 1 ? "s" : ""}
              </div>
              <div className="truncate text-base opacity-90">
                {openIncident.title}: {openIncident.affected_payment_count} payment(s) affected ($
                {Number(openIncident.revenue_at_risk).toFixed(2)} at risk)
              </div>
            </div>
            <ChevronRight className="h-6 w-6 shrink-0" />
          </div>
        </Link>
      )}

      <div className="relative isolate mx-auto grid max-w-[1100px] gap-10 pt-8 lg:grid-cols-[minmax(0,690px)_minmax(0,1fr)]">
        {/* Left column */}
        <div className="space-y-5 pb-10">
          <section className="rounded-xl border border-slate-800 bg-white px-6 py-5">
            <div className="text-base text-black/70">Revenue at risk</div>
            <div className="font-display mt-1 text-5xl font-medium tracking-tight text-black">
              ${Number(analytics.potential_revenue_at_risk).toFixed(2)}
              <span className="ml-2 text-lg font-normal text-black/50">{analytics.currency || "USD"}</span>
            </div>
            <p className="mt-2 text-sm text-black/70">
              Potential loss, not confirmed. {analytics.successful_payments} of {analytics.total_payments} payments settled
              {analytics.uncertain_payments > 0 && <> · {analytics.uncertain_payments} waiting on reconciliation</>}.
            </p>
          </section>

          {/* Promo tiles */}
          <div className="grid gap-5 sm:grid-cols-2">
            <div className="flex min-h-[420px] flex-col rounded-xl bg-[#2a3fb5] p-7 text-white">
              <svg viewBox="0 0 160 110" className="mx-auto h-28 w-40" aria-hidden="true">
                <ellipse cx="80" cy="102" rx="62" ry="6" fill="#1b2a86" />
                <path d="M80 8 38 24v34c0 22 17 36 42 44 25-8 42-22 42-44V24L80 8Z" fill="#f4cf5a" />
                <rect x="75" y="34" width="10" height="32" rx="5" fill="#2a3fb5" />
                <circle cx="80" cy="78" r="6" fill="#2a3fb5" />
              </svg>
              <h2 className="mt-5 text-4xl font-light leading-tight">Review incident</h2>
              <p className="mt-3 text-lg leading-snug text-white/90">
                {openIncident
                  ? `${openIncident.affected_payment_count} payment(s) need a look, $${Number(openIncident.revenue_at_risk).toFixed(2)} at risk.`
                  : "No open incidents. Check past detections and diagnostic reports."}
              </p>
              <Link href={reviewHref} className="mt-auto rounded-full border-2 border-white bg-white py-3 text-center text-lg font-bold text-paypal-navy transition-colors duration-150 hover:bg-white/90">
                {openIncident ? "Review incident" : "View incidents"}
              </Link>
            </div>

            <div className="flex min-h-[420px] flex-col rounded-xl bg-[#141b66] p-7 text-white">
              <svg viewBox="0 0 160 110" className="mx-auto h-28 w-40" aria-hidden="true">
                <ellipse cx="80" cy="102" rx="62" ry="6" fill="#0b1048" />
                <path d="M40 24h50v68H52a12 12 0 0 1-12-12V24Z" fill="#dbe9fb" />
                <rect x="50" y="38" width="30" height="5" rx="2.5" fill="#9ec0ee" />
                <rect x="50" y="50" width="22" height="5" rx="2.5" fill="#9ec0ee" />
                <circle cx="104" cy="44" r="30" fill="#6aa9f5" />
                <circle cx="104" cy="44" r="14" fill="none" stroke="#fff" strokeWidth="6" />
                <path d="m115 55 12 12" stroke="#fff" strokeWidth="6" strokeLinecap="round" />
              </svg>
              <h2 className="mt-5 text-4xl font-light leading-tight">Investigate with AI</h2>
              <p className="mt-3 text-lg leading-snug text-white/90">
                Find the root cause of any payment from verified PayPal events, logs and browser activity.
              </p>
              <Link href="/investigate" className="mt-auto rounded-full border-2 border-white bg-white py-3 text-center text-lg font-bold text-paypal-navy transition-colors duration-150 hover:bg-white/90">
                Open investigator
              </Link>
            </div>
          </div>

          {/* Progress card, like "Set up your account" */}
          <section className="flex items-center gap-5 rounded-xl border border-slate-800 bg-white px-6 py-5">
            <div className="relative h-14 w-14 shrink-0">
              <svg viewBox="0 0 56 56" className="h-14 w-14 -rotate-90">
                <circle cx="28" cy="28" r="22" fill="none" stroke="#e6e9ee" strokeWidth="4" />
                <circle
                  cx="28" cy="28" r="22" fill="none" stroke="#2c4fae" strokeWidth="4" strokeLinecap="round"
                  strokeDasharray={ring} strokeDashoffset={ring * (1 - settledPct / 100)}
                />
              </svg>
              <span className="absolute inset-0 flex items-center justify-center text-sm text-paypal-blue">
                {analytics.successful_payments}/{analytics.total_payments}
              </span>
            </div>
            <div>
              <div className="text-xl text-black">Payments settled</div>
              <div className="text-base text-black/70">{analytics.success_rate_percent}% success rate across all PayPal orders.</div>
            </div>
          </section>

          {/* Recent activity */}
          <section className="overflow-hidden rounded-xl border border-slate-800 bg-white">
            <div className="flex items-center justify-between px-6 pb-3 pt-5">
              <h2 className="font-display text-2xl font-bold text-black">Recent activity</h2>
              <Link href="/payments" className="text-base text-paypal-blue hover:underline">
                See all
              </Link>
            </div>
            <ul className="divide-y divide-slate-800">
              {recentPayments.map((p) => {
                const meta = STATUS_META[p.status] ?? { ...FALLBACK_STATUS, label: p.status };
                const Icon = meta.icon;
                return (
                  <li key={p.id}>
                    <Link href={`/payments/${p.id}`} className="flex items-center gap-4 px-6 py-4 transition-colors hover:bg-[#f7f5f0]">
                      <div className={`flex h-11 w-11 shrink-0 items-center justify-center rounded-full ${meta.iconBox}`}>
                        <Icon className="h-5 w-5" />
                      </div>
                      <div className="min-w-0 flex-1">
                        <div className="truncate text-base text-black">
                          {p.customer_ref || p.paypal_order_id || p.id.slice(0, 13)}
                        </div>
                        <div className="truncate text-sm text-black/60">
                          {formatDate(p.created_at)} · {p.paypal_order_id || "No order ID"} ·{" "}
                          {p.failure_reason || (p.status === "CAPTURED" ? "Normal settlement" : "In progress")}
                        </div>
                      </div>
                      <div className="shrink-0 text-right">
                        <div className="text-base text-black">
                          ${Number(p.amount).toFixed(2)} <span className="text-xs text-black/50">{p.currency}</span>
                        </div>
                        <span className={`mt-0.5 inline-block rounded-full px-2 py-0.5 text-xs font-semibold ${meta.chip}`}>
                          {meta.label}
                        </span>
                      </div>
                    </Link>
                  </li>
                );
              })}
              {recentPayments.length === 0 && (
                <li className="px-6 py-10 text-center text-base text-black/60">No payments yet.</li>
              )}
            </ul>
          </section>

          {/* Volume trend */}
          <section className="rounded-xl border border-slate-800 bg-white p-6">
            <h2 className="font-display text-2xl font-bold text-black">Payment volume</h2>
            <p className="text-base text-black/60">Daily transactions, total and settled</p>
            <div className="mt-4 h-64 w-full">
              <ResponsiveContainer width="100%" height="100%">
                <AreaChart data={analytics.volume_over_time} margin={{ top: 10, right: 10, left: -20, bottom: 0 }}>
                  <defs>
                    <linearGradient id="colorTotal" x1="0" y1="0" x2="0" y2="1">
                      <stop offset="5%" stopColor="#2c4fae" stopOpacity={0.35} />
                      <stop offset="95%" stopColor="#2c4fae" stopOpacity={0} />
                    </linearGradient>
                    <linearGradient id="colorSuccess" x1="0" y1="0" x2="0" y2="1">
                      <stop offset="5%" stopColor="#10b981" stopOpacity={0.3} />
                      <stop offset="95%" stopColor="#10b981" stopOpacity={0} />
                    </linearGradient>
                  </defs>
                  <CartesianGrid strokeDasharray="3 3" stroke="var(--chart-grid)" />
                  <XAxis dataKey="date" stroke="var(--chart-axis)" fontSize={11} />
                  <YAxis stroke="var(--chart-axis)" fontSize={11} />
                  <Tooltip contentStyle={tooltipStyle} />
                  <Area type="monotone" dataKey="total" stroke="#2c4fae" fillOpacity={1} fill="url(#colorTotal)" name="Total" />
                  <Area type="monotone" dataKey="successful" stroke="#10b981" fillOpacity={1} fill="url(#colorSuccess)" name="Successful" />
                </AreaChart>
              </ResponsiveContainer>
            </div>
          </section>
        </div>

        {/* Right panel: white, runs to the page edge like PayPal's */}
        <aside className="relative space-y-9 pb-10 before:absolute before:-bottom-8 before:-top-8 before:-left-10 before:-right-[100vw] before:-z-10 before:border-l before:border-slate-800 before:bg-white before:content-['']">
          <div className="flex items-center justify-end">
            <button onClick={loadData} className="inline-flex items-center gap-1.5 text-base text-paypal-blue hover:underline">
              <RefreshCw className="h-4 w-4" />
              Refresh
            </button>
          </div>
          <div className="grid grid-cols-2 gap-4">
            <Link href="/payments" className="rounded-full bg-paypal-navy py-3.5 text-center text-lg font-bold text-white transition-colors duration-150 hover:bg-paypal-blue">
              Payments
            </Link>
            <Link href="/approvals" className="rounded-full bg-paypal-navy py-3.5 text-center text-lg font-bold text-white transition-colors duration-150 hover:bg-paypal-blue">
              Approvals
            </Link>
          </div>

          <div className="grid grid-cols-3 gap-2 text-center">
            {[
              { href: "/investigate", icon: Brain, label: "AI investigator" },
              { href: "/analytics", icon: BarChart3, label: "Analytics" },
              { href: "/checkout", icon: ShoppingCart, label: "Try the demo store" },
            ].map(({ href, icon: Icon, label }) => (
              <Link key={href} href={href} className="group flex flex-col items-center gap-2">
                <span className="flex h-[74px] w-[74px] items-center justify-center rounded-full bg-[#f4f1ea] text-paypal-navy transition-colors duration-150 group-hover:bg-[#e9e5db]">
                  <Icon className="h-7 w-7" />
                </span>
                <span className="text-base leading-tight text-black">{label}</span>
              </Link>
            ))}
          </div>

          <section>
            <h2 className="font-display text-xl font-bold text-black">Payment health</h2>
            <div className="mt-4">
              <div className="flex items-baseline justify-between">
                <span className="text-base text-black/70">Success rate</span>
                <span className="text-3xl font-light text-black">{analytics.success_rate_percent}%</span>
              </div>
              <div className="mt-2 h-2 overflow-hidden rounded-full bg-[#e6e9ee]">
                <div
                  className="h-full rounded-full bg-emerald-500"
                  style={{ width: `${Math.min(100, Math.max(0, Number(analytics.success_rate_percent)))}%` }}
                />
              </div>
            </div>
            <dl className="mt-4 divide-y divide-slate-800 text-base">
              <div className="flex items-center justify-between py-3">
                <dt className="flex items-center gap-2 text-black/70"><AlertTriangle className="h-4 w-4 text-rose-500" />Failed</dt>
                <dd className="text-black">{analytics.failed_payments} <span className="text-black/50">({analytics.failure_rate_percent}%)</span></dd>
              </div>
              <div className="flex items-center justify-between py-3">
                <dt className="flex items-center gap-2 text-black/70"><HelpCircle className="h-4 w-4 text-amber-500" />Uncertain</dt>
                <dd className="text-black">{analytics.uncertain_payments}</dd>
              </div>
              <div className="flex items-center justify-between py-3">
                <dt className="flex items-center gap-2 text-black/70"><Clock className="h-4 w-4 text-paypal-blue" />Avg API latency</dt>
                <dd className="text-black">{analytics.average_latency_ms} ms</dd>
              </div>
            </dl>
          </section>

          <section>
            <h2 className="font-display text-xl font-bold text-black">Failure breakdown</h2>
            <div className="mt-2 h-52 w-full">
              {analytics.failure_categories.length > 0 ? (
                <ResponsiveContainer width="100%" height="100%">
                  <PieChart>
                    <Pie
                      data={analytics.failure_categories}
                      dataKey="count"
                      nameKey="category"
                      cx="50%"
                      cy="50%"
                      innerRadius={42}
                      outerRadius={70}
                      paddingAngle={2}
                      stroke="none"
                    >
                      {analytics.failure_categories.map((entry, index) => (
                        <Cell key={`cell-${index}`} fill={PIE_COLORS[index % PIE_COLORS.length]} />
                      ))}
                    </Pie>
                    <Tooltip contentStyle={tooltipStyle} />
                  </PieChart>
                </ResponsiveContainer>
              ) : (
                <div className="flex h-full items-center justify-center text-base text-black/60">No failures detected</div>
              )}
            </div>
            <ul className="space-y-1.5 text-base">
              {analytics.failure_categories.map((c, i) => (
                <li key={c.category} className="flex items-center gap-2 text-black/70">
                  <span className="h-2.5 w-2.5 shrink-0 rounded-full" style={{ background: PIE_COLORS[i % PIE_COLORS.length] }} />
                  <span className="min-w-0 flex-1 truncate">{c.category}</span>
                  <span className="text-black">{c.count}</span>
                </li>
              ))}
            </ul>
          </section>
        </aside>
      </div>
    </div>
  );
}
