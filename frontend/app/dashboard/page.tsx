"use client";

import { useCallback, useEffect, useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { Activity, AlertTriangle, ArrowRight, CircleCheck, CreditCard, Loader2, RefreshCw, ShieldAlert } from "lucide-react";
import { Area, AreaChart, CartesianGrid, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { api, type AnalyticsData, type IncidentItem, type PaymentItem, type PaymentWorkspaceData } from "@/lib/api";

const FAILING = new Set(["DENIED", "CAPTURE_FAILED", "DISPUTED"]);
const money = (n: number, currency: string) => new Intl.NumberFormat(undefined, { style: "currency", currency }).format(n);

export default function DashboardPage() {
  const router = useRouter();
  const [workspace, setWorkspace] = useState<PaymentWorkspaceData | null>(null);
  const [analytics, setAnalytics] = useState<AnalyticsData | null>(null);
  const [payments, setPayments] = useState<PaymentItem[]>([]);
  const [incidents, setIncidents] = useState<IncidentItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    setLoading(true); setError(null);
    try {
      const [w, a, p, i] = await Promise.all([api.getPaymentWorkspace(500), api.getAnalytics(), api.getPayments({ page: 1, page_size: 8 }), api.getIncidents()]);
      setWorkspace(w); setAnalytics(a); setPayments(p.items); setIncidents(i.items.filter((item) => item.status !== "RESOLVED"));
    } catch (err) { setError(err instanceof Error ? err.message : "Overview data is unavailable."); }
    finally { setLoading(false); }
  }, []);

  useEffect(() => { void load(); }, [load]);

  if (loading) return <div className="flex min-h-[45vh] items-center justify-center gap-3 text-sm text-slate-500"><Loader2 className="h-5 w-5 animate-spin text-cyan-500" />Loading operational payment health…</div>;
  if (error || !workspace || !analytics) return <div role="alert" className="mx-auto max-w-xl rounded-xl border border-rose-300 bg-rose-50 p-6 text-rose-900"><h1 className="font-semibold">Overview is unavailable</h1><p className="mt-2 text-sm">{error}</p><button onClick={() => void load()} className="mt-4 inline-flex items-center gap-2 rounded-lg bg-paypal-navy px-3 py-2 text-sm text-white"><RefreshCw className="h-4 w-4" />Retry</button></div>;

  const successfulAmounts = workspace.processed_amounts;
  const processedValue = successfulAmounts.length === 1 ? money(Number(successfulAmounts[0].amount), successfulAmounts[0].currency) : successfulAmounts.length ? `${successfulAmounts.length} currencies` : "—";
  const currency = analytics.currency || "USD";
  const recentIncidents = incidents.slice(0, 4);
  const anomalies = workspace.anomalies.slice(0, 4);
  const riskAmounts = workspace.revenue_at_risk_amounts;
  const riskValue = riskAmounts.length ? riskAmounts.map((item) => money(Number(item.amount), item.currency)).join(" · ") : money(0, currency);
  const uncertainRiskCount = workspace.status_breakdown.find((item) => item.status === "CAPTURE_UNCERTAIN")?.count || 0;
  const risks = [...recentIncidents.map((i) => ({ id: i.id, title: i.title, detail: `${i.affected_payment_count} affected · ${money(Number(i.revenue_at_risk), i.currency)}`, href: `/incidents/${i.id}`, severity: i.severity })), ...anomalies.map((a) => ({ id: a.kind, title: a.title, detail: a.evidence, href: a.payment_ids[0] ? `/payments/${a.payment_ids[0]}` : "/transactions", severity: "MEDIUM" }))].slice(0, 6);

  return <div className="space-y-7">
    <header className="flex flex-wrap items-end justify-between gap-3">
      <div><p className="text-xs font-semibold uppercase tracking-[0.14em] text-cyan-600">Monitor</p><h1 className="mt-1 text-3xl font-bold tracking-tight text-ink">Overview</h1><p className="mt-1 text-sm text-slate-500">Live payment health from records available in this workspace.</p></div>
      <button onClick={() => void load()} className="inline-flex items-center gap-2 rounded-lg border border-slate-300 bg-white px-3 py-2 text-sm font-medium text-slate-700 hover:bg-slate-50"><RefreshCw className="h-4 w-4" />Refresh</button>
    </header>

    <section aria-label="Payment KPIs" className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
      <Kpi label="Processed amount" value={processedValue} note="Captured or refunded records · grouped by currency" icon={<CreditCard />} href="/payments?status=CAPTURED" />
      <Kpi label="Payment success rate" value={`${workspace.success_rate_percent.toFixed(1)}%`} note={`${workspace.successful_count} successful of ${workspace.total_transactions} total`} icon={<CircleCheck />} href="/transactions" />
      <Kpi label="Failed payments" value={workspace.failed_count.toLocaleString()} note="Declined, failed, or disputed" icon={<ShieldAlert />} href="/payments" />
      <Kpi label="Revenue at risk" value={riskValue} note={`${workspace.failed_count + uncertainRiskCount} failed or uncertain records · grouped by currency`} icon={<AlertTriangle />} href="/transactions" />
    </section>

    <div className="grid gap-5 xl:grid-cols-[minmax(0,1.5fr)_minmax(300px,1fr)]">
      <section className="glass-panel rounded-xl border border-slate-200 p-5">
        <div className="flex items-start justify-between gap-3"><div><h2 className="font-semibold text-ink">Payment activity</h2><p className="mt-1 text-xs text-slate-500">Persisted transaction counts by day. Select the chart to explore records.</p></div><Link href="/transactions" className="text-xs font-semibold text-cyan-700 hover:underline">Explore <ArrowRight className="ml-1 inline h-3.5 w-3.5" /></Link></div>
        {workspace.daily_volume.length ? <div aria-label="Select a date to filter transactions" className="mt-4 h-64"><ResponsiveContainer width="100%" height="100%"><AreaChart data={workspace.daily_volume} onClick={(state: any) => { const day = state?.activeLabel; if (typeof day === "string" && /^\d{4}-\d{2}-\d{2}$/.test(day)) router.push(`/transactions?date_from=${day}&date_to=${day}`); }}><CartesianGrid strokeDasharray="3 3" stroke="var(--chart-grid)" /><XAxis dataKey="date" stroke="var(--chart-axis)" fontSize={11} /><YAxis allowDecimals={false} stroke="var(--chart-axis)" fontSize={11} /><Tooltip /><Area type="monotone" dataKey="count" name="Payments" stroke="#0b73c2" fill="#0b73c2" fillOpacity={0.15} activeDot={{ r: 5, cursor: "pointer" }} /></AreaChart></ResponsiveContainer></div> : <Empty>No payment volume is recorded yet.</Empty>}
        <div className="mt-4 flex flex-wrap gap-x-6 gap-y-2 border-t border-slate-200 pt-3 text-xs text-slate-500"><span>Successful <strong className="text-emerald-700">{workspace.successful_count}</strong></span><span>Failed <strong className="text-rose-700">{workspace.failed_count}</strong></span><span>Pending <strong className="text-amber-700">{workspace.pending_count}</strong></span></div>
      </section>

      <section className="glass-panel rounded-xl border border-slate-200 p-5">
        <div className="flex items-center justify-between"><div><h2 className="font-semibold text-ink">Requires attention</h2><p className="mt-1 text-xs text-slate-500">Active incidents and evidence-backed anomalies.</p></div><Link href="/incidents" className="text-xs font-semibold text-cyan-700 hover:underline">All incidents</Link></div>
        {risks.length ? <div className="mt-4 divide-y divide-slate-200">{risks.map((risk) => <Link key={risk.id} href={risk.href} className="flex gap-3 py-3 first:pt-0 hover:bg-slate-50"><span className={`mt-1 h-2 w-2 shrink-0 rounded-full ${risk.severity === "HIGH" || risk.severity === "CRITICAL" ? "bg-rose-500" : "bg-amber-500"}`} /><span className="min-w-0"><span className="block truncate text-sm font-semibold text-ink">{risk.title}</span><span className="mt-1 block text-xs text-slate-500">{risk.detail}</span></span><ArrowRight className="ml-auto mt-1 h-4 w-4 shrink-0 text-slate-400" /></Link>)}</div> : <Empty>No active incidents or current anomaly findings.</Empty>}
      </section>
    </div>

    <section className="glass-panel overflow-hidden rounded-xl border border-slate-200">
      <div className="flex items-center justify-between gap-3 border-b border-slate-200 px-5 py-4"><div><h2 className="font-semibold text-ink">Recent payments</h2><p className="mt-1 text-xs text-slate-500">Latest persisted payment records</p></div><Link href="/payments" className="text-xs font-semibold text-cyan-700 hover:underline">Open payments <ArrowRight className="ml-1 inline h-3.5 w-3.5" /></Link></div>
      {payments.length ? <div className="overflow-x-auto"><table className="w-full min-w-[650px] text-left text-sm"><thead className="border-b border-slate-200 bg-white text-xs text-slate-500"><tr><th className="px-5 py-3">Payment</th><th className="px-5 py-3">Customer</th><th className="px-5 py-3">Amount</th><th className="px-5 py-3">Status</th><th className="px-5 py-3">Created</th></tr></thead><tbody className="divide-y divide-slate-100">{payments.map((payment) => <tr key={payment.id} className="bg-white hover:bg-blue-50/60 focus-within:bg-blue-50"><td className="px-5 py-3"><Link className="font-mono text-xs text-cyan-700 hover:underline focus-visible:outline focus-visible:outline-2 focus-visible:outline-cyan-600" href={`/payments/${payment.id}`}>{payment.id.slice(0, 12)}…</Link></td><td className="px-5 py-3 text-slate-600">{payment.customer_ref}</td><td className="px-5 py-3 font-medium text-ink">{money(Number(payment.amount), payment.currency)}</td><td className="px-5 py-3"><span className={`rounded-full px-2 py-1 text-[10px] font-semibold ${FAILING.has(payment.status) ? "bg-rose-50 text-rose-700" : payment.status === "CAPTURED" ? "bg-emerald-50 text-emerald-700" : "bg-amber-50 text-amber-700"}`}>{payment.status.replaceAll("_", " ")}</span></td><td className="px-5 py-3 text-xs text-slate-500">{new Date(payment.created_at).toLocaleString()}</td></tr>)}</tbody></table></div> : <Empty>No payments have been recorded.</Empty>}
    </section>
  </div>;
}

function Kpi({ label, value, note, icon, href }: { label: string; value: string; note: string; icon: React.ReactNode; href: string }) {
  return <Link href={href} className="glass-panel rounded-xl border border-slate-200 p-4 transition hover:border-cyan-400 hover:shadow-sm"><div className="flex items-center justify-between text-sm text-slate-500"><span>{label}</span><span className="text-cyan-700">{icon}</span></div><p className="mt-3 truncate text-2xl font-bold tracking-tight text-ink">{value}</p><p className="mt-1 text-[11px] leading-relaxed text-slate-500">{note}</p></Link>;
}

function Empty({ children }: { children: React.ReactNode }) { return <p className="py-10 text-center text-sm text-slate-500">{children}</p>; }
