"use client";

import Link from "next/link";
import { useState } from "react";
import { AlertTriangle, CheckCircle2, FlaskConical, Loader2, RotateCcw, Timer, XCircle } from "lucide-react";
import { api } from "@/lib/api";

const SCENARIOS = [
  { id: "timeout_before_response", title: "Capture response timeout", detail: "Creates an explicitly simulated ambiguous capture with payment lifecycle events and runs incident detection.", icon: Timer },
  { id: "capture_denied", title: "Payment declined", detail: "Creates an explicitly simulated declined payment and its lifecycle evidence.", icon: XCircle },
];

export default function DemoLabPage() {
  const [busy, setBusy] = useState<string | null>(null);
  const [notice, setNotice] = useState<{ message: string; paymentId?: string } | null>(null);
  const [error, setError] = useState<string | null>(null);

  async function run(scenario: string) {
    setBusy(scenario); setError(null); setNotice(null);
    try {
      const result = await api.triggerScenario(scenario);
      setNotice({ message: `${result.title} — generated labelled simulated payment evidence.`, paymentId: result.payment_id || undefined });
    } catch (err) { setError(err instanceof Error ? err.message : "Scenario could not be generated."); }
    finally { setBusy(null); }
  }

  async function reset() {
    if (!window.confirm("Reset only the designated demo dataset? This cannot be undone.")) return;
    setBusy("reset"); setError(null); setNotice(null);
    try { const result = await api.resetDemoData(); setNotice({ message: result.message }); }
    catch (err) { setError(err instanceof Error ? err.message : "Demo data reset is unavailable in this environment."); }
    finally { setBusy(null); }
  }

  return <div className="mx-auto max-w-5xl space-y-7">
    <header className="flex flex-wrap items-start justify-between gap-4 border-b border-slate-800 pb-5">
      <div><div className="inline-flex items-center gap-2 rounded-full border border-amber-700/50 bg-amber-950/30 px-2.5 py-1 text-[10px] font-bold uppercase tracking-wider text-amber-300"><FlaskConical className="h-3.5 w-3.5" /> Demo environment</div>
        <h1 className="mt-3 text-3xl font-bold tracking-tight text-ink">Demo Lab</h1>
        <p className="mt-2 max-w-2xl text-sm leading-relaxed text-slate-500">Generate controlled, labelled payment failure scenarios using PayTrace’s observability pipeline. These records are simulated evidence, not PayPal Sandbox transactions or verified provider events.</p>
      </div>
    </header>
    {error && <div role="alert" className="rounded-xl border border-rose-700 bg-rose-950 p-4 text-sm text-rose-300"><AlertTriangle className="mr-2 inline h-4 w-4" />{error}</div>}
    {notice && <div role="status" className="rounded-xl border border-emerald-700 bg-emerald-950 p-4 text-sm text-emerald-300"><CheckCircle2 className="mr-2 inline h-4 w-4" />{notice.message}{notice.paymentId && <> <Link className="ml-2 underline" href={`/payments/${notice.paymentId}`}>Inspect payment</Link></>}</div>}
    <section className="grid gap-4 md:grid-cols-2" aria-label="Demo scenarios">
      {SCENARIOS.map(({ id, title, detail, icon: Icon }) => <article key={id} className="glass-panel rounded-xl border border-slate-800 p-5">
        <div className="flex items-start gap-3"><span className="rounded-lg bg-cyan-950 p-2 text-paypal-blue"><Icon className="h-5 w-5" /></span><div><h2 className="font-semibold text-ink">{title}</h2><p className="mt-1 text-sm leading-relaxed text-slate-500">{detail}</p></div></div>
        <button type="button" disabled={!!busy} onClick={() => void run(id)} className="mt-5 inline-flex items-center gap-2 rounded-lg bg-paypal-navy px-4 py-2.5 text-sm font-semibold text-white hover:bg-paypal-blue disabled:opacity-50">
          {busy === id ? <Loader2 className="h-4 w-4 animate-spin" /> : <FlaskConical className="h-4 w-4" />} Generate scenario
        </button>
      </article>)}
    </section>
    <section className="rounded-xl border border-rose-700 bg-rose-950 p-5">
      <div className="flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between"><div><h2 className="font-semibold text-rose-300">Reset demo data</h2><p className="mt-1 max-w-2xl text-sm text-rose-400">Available only where the backend explicitly enables development/test resets. The server protects other environments.</p></div>
        <button type="button" disabled={!!busy} onClick={() => void reset()} className="inline-flex shrink-0 items-center justify-center gap-2 rounded-lg border border-rose-500 bg-rose-900 px-4 py-2.5 text-sm font-semibold text-rose-300 hover:bg-rose-800 disabled:opacity-50">{busy === "reset" ? <Loader2 className="h-4 w-4 animate-spin" /> : <RotateCcw className="h-4 w-4" />} Reset demo dataset</button></div>
    </section>
  </div>;
}
