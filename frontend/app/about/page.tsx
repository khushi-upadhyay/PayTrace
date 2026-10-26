import Link from "next/link";
import {
  Brain,
  ShieldAlert,
  ArrowRight,
  Activity,
  Layers,
  Sparkles,
  GitCompare,
  Webhook,
  Lock,
} from "lucide-react";

export default function LandingPage() {
  return (
    <div className="max-w-6xl mx-auto space-y-16 py-6 animate-fadeIn">
      {/* Hero Section */}
      <div className="text-center space-y-6 pt-4">
        <div className="inline-flex items-center gap-2 px-4 py-1.5 rounded-full bg-cyan-950/70 border border-cyan-800/80 text-cyan-300 text-xs font-semibold tracking-wide uppercase">
          <Sparkles className="w-3.5 h-3.5 text-cyan-400" />
          PayPal AI Hackathon 2026 Prototype
        </div>

        <h1 className="text-4xl md:text-6xl font-extrabold tracking-tight text-white max-w-4xl mx-auto leading-tight">
          Don’t just know a payment failed. <br />
          <span className="bg-gradient-to-r from-cyan-400 via-sky-300 to-indigo-400 bg-clip-text text-transparent">
            Know exactly why.
          </span>
        </h1>

        <p className="text-lg text-slate-300 max-w-2xl mx-auto leading-relaxed">
          PayTrace is a cross-signal observability and AI investigation platform for PayPal.
          It correlates PayPal orders, captures, verified webhooks, application latency, and
          customer checkout journeys into unified lifecycles—grounding root-cause AI in verified facts.
        </p>

        <div className="flex items-center justify-center gap-4 pt-2">
          <Link
            href="/dashboard"
            className="flex items-center gap-2 px-6 py-3 rounded-lg bg-cyan-500 text-slate-950 font-bold hover:bg-cyan-400 transition-all duration-150 shadow-lg shadow-cyan-500/25"
          >
            Open Dashboard
            <ArrowRight className="w-4 h-4" />
          </Link>
          <Link
            href="/checkout"
            className="flex items-center gap-2 px-6 py-3 rounded-lg bg-slate-900 border border-slate-700 text-slate-200 font-semibold hover:bg-slate-800 transition-all duration-150"
          >
            Try Demo Checkout
          </Link>
          <Link
            href="/payments"
            className="flex items-center gap-2 px-6 py-3 rounded-lg bg-slate-900/60 border border-slate-800 text-slate-400 font-semibold hover:text-slate-200 transition-all duration-150"
          >
            Inspect Payments
          </Link>
        </div>
      </div>

      {/* Cross-Signal Architecture Diagram */}
      <div className="glass-panel rounded-2xl p-8 border border-slate-800 relative overflow-hidden">
        <div className="absolute top-0 right-0 w-96 h-96 bg-cyan-500/5 rounded-full blur-3xl -z-10" />
        <div className="flex items-center justify-between mb-8 pb-4 border-b border-slate-800/80">
          <div>
            <h2 className="text-lg font-bold text-white flex items-center gap-2">
              <Layers className="w-5 h-5 text-cyan-400" />
              Cross-Signal Correlation Architecture
            </h2>
            <p className="text-xs text-slate-400 mt-1">
              Synchronizing three disjoint observation layers into one append-only lifecycle
            </p>
          </div>
          <span className="text-xs font-mono text-cyan-400 px-2.5 py-1 rounded bg-cyan-950/60 border border-cyan-800/60">
            DEMO READY
          </span>
        </div>

        <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
          <div className="glass-card rounded-xl p-5 border border-slate-800 space-y-3">
            <div className="w-8 h-8 rounded-lg bg-sky-500/20 text-sky-400 flex items-center justify-center font-bold">
              1
            </div>
            <h3 className="text-sm font-bold text-white">PayPal Sandbox APIs & Webhooks</h3>
            <p className="text-xs text-slate-400 leading-relaxed">
              Order approvals, captures, signature-verified webhooks, and out-of-order event deduplication.
            </p>
          </div>

          <div className="glass-card rounded-xl p-5 border border-slate-800 space-y-3">
            <div className="w-8 h-8 rounded-lg bg-indigo-500/20 text-indigo-400 flex items-center justify-center font-bold">
              2
            </div>
            <h3 className="text-sm font-bold text-white">Merchant Application Backend</h3>
            <p className="text-xs text-slate-400 leading-relaxed">
              FastAPI lifecycle transitions, HTTP read timeout detection, and stage-by-stage latency monitoring.
            </p>
          </div>

          <div className="glass-card rounded-xl p-5 border border-slate-800 space-y-3">
            <div className="w-8 h-8 rounded-lg bg-cyan-500/20 text-cyan-400 flex items-center justify-center font-bold">
              3
            </div>
            <h3 className="text-sm font-bold text-white">Customer Browser Journeys</h3>
            <p className="text-xs text-slate-400 leading-relaxed">
              rrweb interaction markers, spinner stall detection, and privacy-masked sensitive inputs.
            </p>
          </div>
        </div>
      </div>

      {/* Core Differentiators Grid */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
        <div className="glass-card rounded-xl p-6 border border-slate-800 space-y-3">
          <div className="flex items-center gap-3">
            <div className="p-2.5 rounded-lg bg-amber-500/10 text-amber-400 border border-amber-500/20">
              <ShieldAlert className="w-5 h-5" />
            </div>
            <div>
              <h3 className="text-base font-bold text-white">Duplicate Charge Prevention</h3>
              <span className="text-xs text-amber-400/90 font-mono">CRITICAL SAFETY ENGINE</span>
            </div>
          </div>
          <p className="text-xs text-slate-300 leading-relaxed">
            When a merchant backend times out while awaiting PayPal&apos;s capture response, PayTrace flags
            the state as <span className="font-mono text-amber-300">CAPTURE_UNCERTAIN</span> and halts blind retries,
            instructing operators to reconcile provider status before taking further money actions.
          </p>
        </div>

        <div className="glass-card rounded-xl p-6 border border-slate-800 space-y-3">
          <div className="flex items-center gap-3">
            <div className="p-2.5 rounded-lg bg-cyan-500/10 text-cyan-400 border border-cyan-500/20">
              <Brain className="w-5 h-5" />
            </div>
            <div>
              <h3 className="text-base font-bold text-white">Evidence-Grounded AI Investigator</h3>
              <span className="text-xs text-cyan-400/90 font-mono">STRUCTURED PYDANTIC OUTPUT</span>
            </div>
          </div>
          <p className="text-xs text-slate-300 leading-relaxed">
            AI investigations strictly separate <strong className="text-white">FACTS</strong>,{" "}
            <strong className="text-white">INFERENCES</strong>, and{" "}
            <strong className="text-white">RECOMMENDATIONS</strong>. When AI is offline, deterministic rule-based
            fallbacks provide 100% reliable root-cause diagnosis.
          </p>
        </div>

        <div className="glass-card rounded-xl p-6 border border-slate-800 space-y-3">
          <div className="flex items-center gap-3">
            <div className="p-2.5 rounded-lg bg-emerald-500/10 text-emerald-400 border border-emerald-500/20">
              <Lock className="w-5 h-5" />
            </div>
            <div>
              <h3 className="text-base font-bold text-white">Human-in-the-Loop Refunds</h3>
              <span className="text-xs text-emerald-400/90 font-mono">POLICY ENFORCEMENT</span>
            </div>
          </div>
          <p className="text-xs text-slate-300 leading-relaxed">
            AI can propose remediation actions, but no money-moving refund or cancellation can execute
            without explicit operator sign-off in the Human Approval Inbox.
          </p>
        </div>

        <div className="glass-card rounded-xl p-6 border border-slate-800 space-y-3">
          <div className="flex items-center gap-3">
            <div className="p-2.5 rounded-lg bg-indigo-500/10 text-indigo-400 border border-indigo-500/20">
              <GitCompare className="w-5 h-5" />
            </div>
            <div>
              <h3 className="text-base font-bold text-white">Failed vs Successful Comparison</h3>
              <span className="text-xs text-indigo-400/90 font-mono">DIAGNOSTIC BENCHMARKING</span>
            </div>
          </div>
          <p className="text-xs text-slate-300 leading-relaxed">
            Instantly compare any failed transaction with a recently captured successful transaction to highlight
            exact stage latency divergences and missing provider confirmations.
          </p>
        </div>
      </div>
    </div>
  );
}
