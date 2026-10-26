"use client";

import { useEffect, useState } from "react";
import { useParams } from "next/navigation";
import Link from "next/link";
import {
  api,
  PaymentItem,
  TimelineData,
  PaymentEventItem,
  AIInvestigationData,
} from "@/lib/api";
import {
  Activity,
  ArrowLeft,
  Brain,
  CheckCircle2,
  AlertTriangle,
  Clock,
  Copy,
  ExternalLink,
  ShieldAlert,
  Send,
  Loader2,
  DollarSign,
  Video,
  FileText,
  RotateCcw,
  Sparkles,
  HelpCircle,
  Eye,
} from "lucide-react";

export default function PaymentDetailPage() {
  const params = useParams();
  const paymentId = params.id as string;

  const [payment, setPayment] = useState<PaymentItem | null>(null);
  const [timeline, setTimeline] = useState<TimelineData | null>(null);
  const [sessionInfo, setSessionInfo] = useState<any>(null);
  const [investigation, setInvestigation] = useState<AIInvestigationData | null>(null);

  const [loading, setLoading] = useState(true);
  const [investigating, setInvestigating] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [copiedField, setCopiedField] = useState<string | null>(null);

  // Chat follow-up state
  const [chatMessages, setChatMessages] = useState<Array<{ role: string; content: string }>>([]);
  const [chatInput, setChatInput] = useState("");
  const [chatLoading, setChatLoading] = useState(false);

  // Refund modal state
  const [showRefundModal, setShowRefundModal] = useState(false);
  const [refundReason, setRefundReason] = useState("Customer requested cancellation");
  const [refundSubmitting, setRefundSubmitting] = useState(false);
  const [refundNotice, setRefundNotice] = useState<string | null>(null);

  // Reconcile status state
  const [reconciling, setReconciling] = useState(false);
  const [reconcileResult, setReconcileResult] = useState<any>(null);

  const loadData = async () => {
    try {
      setLoading(true);
      setError(null);
      const [pm, tl, sess] = await Promise.all([
        api.getPayment(paymentId),
        api.getPaymentTimeline(paymentId),
        api.getPaymentSession(paymentId).catch(() => null),
      ]);
      setPayment(pm);
      setTimeline(tl);
      setSessionInfo(sess);
    } catch (err: any) {
      setError(err.message || "Failed to load payment detail");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    if (paymentId) {
      loadData();
    }
  }, [paymentId]);

  const handleCopy = (text: string, field: string) => {
    navigator.clipboard.writeText(text);
    setCopiedField(field);
    setTimeout(() => setCopiedField(null), 2000);
  };

  const handleRunInvestigation = async () => {
    try {
      setInvestigating(true);
      const inv = await api.investigatePayment(paymentId);
      setInvestigation(inv);
    } catch (err: any) {
      alert(`Investigation failed: ${err.message}`);
    } finally {
      setInvestigating(false);
    }
  };

  const handleSendChat = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!chatInput.trim() || chatLoading) return;

    const userMsg = { role: "user", content: chatInput.trim() };
    const newMessages = [...chatMessages, userMsg];
    setChatMessages(newMessages);
    setChatInput("");
    setChatLoading(true);

    try {
      const res = await api.chatInvestigator(paymentId, newMessages, userMsg.content);
      setChatMessages([...newMessages, { role: "assistant", content: res.response }]);
    } catch (err: any) {
      setChatMessages([
        ...newMessages,
        { role: "assistant", content: `Error querying investigator: ${err.message}` },
      ]);
    } finally {
      setChatLoading(false);
    }
  };

  const handleProposeRefund = async () => {
    try {
      setRefundSubmitting(true);
      const res = await api.proposeRefund(paymentId, { reason: refundReason });
      setRefundNotice(`Proposal created (Ticket #${res.ticket_id?.slice(0, 8)}). Submitted to Human Approval Inbox.`);
      setShowRefundModal(false);
      loadData();
    } catch (err: any) {
      alert(`Error proposing refund: ${err.message}`);
    } finally {
      setRefundSubmitting(false);
    }
  };

  const handleReconcileOrder = async () => {
    if (!payment?.paypal_order_id) return;
    try {
      setReconciling(true);
      const order = await api.captureOrder(payment.paypal_order_id, false);
      setReconcileResult(order);
      loadData();
    } catch (err: any) {
      alert(`Reconciliation error: ${err.message}`);
    } finally {
      setReconciling(false);
    }
  };

  if (loading) {
    return (
      <div className="flex flex-col items-center justify-center min-h-[60vh] space-y-4">
        <Loader2 className="w-8 h-8 text-cyan-400 animate-spin" />
        <p className="text-sm text-slate-400">Reconstructing unified payment lifecycle...</p>
      </div>
    );
  }

  if (error || !payment) {
    return (
      <div className="glass-panel p-8 rounded-xl border border-rose-500/30 text-center space-y-4 max-w-xl mx-auto my-12">
        <AlertTriangle className="w-10 h-10 text-rose-400 mx-auto" />
        <h2 className="text-lg font-bold text-white">Payment Record Not Found</h2>
        <p className="text-xs text-slate-400">{error || "Payment record could not be loaded."}</p>
        <Link href="/payments" className="px-4 py-2 bg-slate-800 hover:bg-slate-700 text-white text-xs font-semibold rounded-lg inline-block">
          Return to Ledger
        </Link>
      </div>
    );
  }

  const isTimeoutUncertain = payment.status === "CAPTURE_UNCERTAIN" || payment.failure_code === "TIMEOUT_BEFORE_RESPONSE";

  return (
    <div className="space-y-8 max-w-7xl mx-auto animate-fadeIn pb-16">
      {/* Back button & Action Row */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
        <Link
          href="/payments"
          className="inline-flex items-center gap-1.5 text-xs text-slate-400 hover:text-slate-200 transition-colors"
        >
          <ArrowLeft className="w-4 h-4" />
          Back to Payments Ledger
        </Link>
        <div className="flex items-center gap-2.5">
          <button
            onClick={() => setShowRefundModal(true)}
            className="px-3.5 py-1.5 rounded-lg bg-slate-900 border border-slate-700 hover:bg-slate-800 text-slate-200 text-xs font-semibold transition-colors"
          >
            Propose Refund
          </button>
          {isTimeoutUncertain && (
            <button
              onClick={handleReconcileOrder}
              disabled={reconciling}
              className="px-3.5 py-1.5 rounded-lg bg-cyan-600 hover:bg-cyan-500 text-slate-950 text-xs font-bold transition-colors flex items-center gap-1.5"
            >
              {reconciling ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <RotateCcw className="w-3.5 h-3.5" />}
              Reconcile with PayPal
            </button>
          )}
        </div>
      </div>

      {refundNotice && (
        <div className="p-3.5 rounded-lg bg-emerald-950/70 border border-emerald-800 text-emerald-300 text-xs flex items-center gap-2">
          <CheckCircle2 className="w-4 h-4 text-emerald-400" />
          {refundNotice}
        </div>
      )}

      {/* Payment Master Header Card */}
      <div className="glass-panel rounded-2xl p-6 border border-slate-800 space-y-6">
        <div className="flex flex-col lg:flex-row lg:items-center justify-between gap-6 pb-6 border-b border-slate-800">
          <div>
            <div className="flex items-center gap-3">
              <h1 className="text-xl font-extrabold text-white font-mono tracking-tight">
                {payment.id}
              </h1>
              <button
                onClick={() => handleCopy(payment.id, "pid")}
                className="text-slate-400 hover:text-cyan-400 transition-colors"
                title="Copy Payment ID"
              >
                <Copy className="w-3.5 h-3.5" />
              </button>
              {copiedField === "pid" && (
                <span className="text-[10px] text-cyan-400 font-mono">Copied!</span>
              )}
            </div>
            <p className="text-xs text-slate-400 mt-1 flex items-center gap-2">
              Customer: <span className="text-slate-200 font-medium">{payment.customer_ref}</span>
              <span>•</span>
              Created: <span className="text-slate-200">{new Date(payment.created_at).toLocaleString()}</span>
            </p>
          </div>

          <div className="flex flex-wrap items-center gap-3">
            {/* Status Pill */}
            <div className="flex flex-col items-end">
              <span className="text-[10px] text-slate-500 uppercase tracking-wider font-mono">Lifecycle State</span>
              <span
                className={`inline-flex items-center px-3 py-1 rounded-full text-xs font-bold tracking-wide mt-0.5 ${
                  payment.status === "CAPTURED"
                    ? "bg-emerald-950 text-emerald-300 border border-emerald-800"
                    : isTimeoutUncertain
                    ? "bg-amber-950 text-amber-300 border border-amber-800 glow-amber animate-pulse"
                    : payment.status === "DENIED" || payment.status === "CAPTURE_FAILED"
                    ? "bg-rose-950 text-rose-300 border border-rose-800 glow-red"
                    : payment.status === "REFUNDED"
                    ? "bg-purple-950 text-purple-300 border border-purple-800"
                    : "bg-slate-800 text-slate-300"
                }`}
              >
                {payment.status}
              </span>
            </div>

            {/* Amount */}
            <div className="flex flex-col items-end pl-4 border-l border-slate-800">
              <span className="text-[10px] text-slate-500 uppercase tracking-wider font-mono">Amount</span>
              <span className="text-xl font-black text-white mt-0.5">
                ${Number(payment.amount).toFixed(2)} <span className="text-xs text-slate-400">{payment.currency}</span>
              </span>
            </div>
          </div>
        </div>

        {/* Provider IDs & Metadata Bar */}
        <div className="grid grid-cols-1 md:grid-cols-4 gap-4 text-xs">
          <div className="rounded-lg p-3 bg-slate-900/60 border border-slate-800/80">
            <span className="text-[10px] text-slate-500 uppercase font-mono block">PayPal Order ID</span>
            <div className="flex items-center justify-between mt-1">
              <span className="font-mono text-slate-200 font-medium">
                {payment.paypal_order_id || "None"}
              </span>
              {payment.paypal_order_id && (
                <button
                  onClick={() => handleCopy(payment.paypal_order_id!, "oid")}
                  className="text-slate-500 hover:text-cyan-400"
                >
                  <Copy className="w-3 h-3" />
                </button>
              )}
            </div>
          </div>

          <div className="rounded-lg p-3 bg-slate-900/60 border border-slate-800/80">
            <span className="text-[10px] text-slate-500 uppercase font-mono block">PayPal Capture ID</span>
            <div className="flex items-center justify-between mt-1">
              <span className="font-mono text-slate-200 font-medium">
                {payment.paypal_capture_id || "Unresolved"}
              </span>
              {payment.paypal_capture_id && (
                <button
                  onClick={() => handleCopy(payment.paypal_capture_id!, "cid")}
                  className="text-slate-500 hover:text-cyan-400"
                >
                  <Copy className="w-3 h-3" />
                </button>
              )}
            </div>
          </div>

          <div className="rounded-lg p-3 bg-slate-900/60 border border-slate-800/80">
            <span className="text-[10px] text-slate-500 uppercase font-mono block">Source Environment</span>
            <span
              className={`font-mono text-xs font-semibold inline-block mt-1 ${
                payment.source_mode === "SIMULATED" ? "text-amber-400" : "text-cyan-400"
              }`}
            >
              {payment.source_mode === "SIMULATED" ? "SIMULATED DEMO EVENT" : payment.source_mode}
            </span>
          </div>

          <div className="rounded-lg p-3 bg-slate-900/60 border border-slate-800/80">
            <span className="text-[10px] text-slate-500 uppercase font-mono block">Total Lifecycle Duration</span>
            <span className="text-slate-200 font-mono font-medium block mt-1">
              {timeline?.duration_ms ? `${timeline.duration_ms} ms` : "Instant / In-Progress"}
            </span>
          </div>
        </div>
      </div>

      {/* CRITICAL STATE WARNING: Timeout before response banner */}
      {isTimeoutUncertain && (
        <div className="rounded-xl p-5 border border-amber-500/40 bg-amber-950/25 glow-amber space-y-3 animate-fadeIn">
          <div className="flex items-center gap-3">
            <div className="p-2 rounded-lg bg-amber-500/20 text-amber-400">
              <ShieldAlert className="w-5 h-5" />
            </div>
            <div>
              <h3 className="text-sm font-bold text-amber-200 uppercase tracking-wide">
                Critical Observability Alert: Ambiguous Capture Outcome
              </h3>
              <p className="text-xs text-amber-300/90 mt-0.5">
                The merchant backend timed out (&gt;5000ms) waiting for PayPal&apos;s capture response.
                Funds may already be captured at PayPal. <strong className="text-white underline">DO NOT BLINDLY RETRY</strong>.
              </p>
            </div>
          </div>
          <div className="text-xs bg-slate-950/70 p-3 rounded-lg border border-amber-800/50 text-slate-300 font-mono">
            Safety Guardrail Active: Automatic retries have been suppressed to prevent duplicate customer charges.
            Next step: Reconcile provider order state via <span className="text-cyan-300">GET /paypal/orders/{payment.paypal_order_id}</span> or await incoming webhooks.
          </div>
        </div>
      )}

      {/* Main Two-Column Layout: Left Timeline, Right AI Investigation Panel */}
      <div className="grid grid-cols-1 lg:grid-cols-12 gap-8 items-start">
        {/* Left: Unified Chronological Timeline (7 cols) */}
        <div className="lg:col-span-7 space-y-6">
          <div className="glass-panel rounded-2xl p-6 border border-slate-800 space-y-6">
            <div className="flex items-center justify-between pb-4 border-b border-slate-800">
              <div>
                <h2 className="text-base font-bold text-white flex items-center gap-2">
                  <Activity className="w-4 h-4 text-cyan-400" />
                  Unified Chronological Timeline
                </h2>
                <p className="text-xs text-slate-400 mt-0.5">
                  Append-only trace correlating frontend, PayPal APIs, and webhooks
                </p>
              </div>
              <span className="text-xs font-mono text-slate-400">
                {timeline?.total_events || 0} Events
              </span>
            </div>

            {/* Timeline Events Stack */}
            <div className="relative pl-6 space-y-6 before:absolute before:left-2.5 before:top-3 before:bottom-3 before:w-0.5 before:bg-slate-800">
              {timeline?.events.map((ev, idx) => (
                <div key={ev.id} className="relative group">
                  {/* Event Marker Dot */}
                  <div
                    className={`absolute -left-[1.8rem] top-1.5 w-3.5 h-3.5 rounded-full border-2 bg-slate-950 ${
                      ev.status === "SUCCESS"
                        ? "border-emerald-400"
                        : ev.status === "UNCERTAIN"
                        ? "border-amber-400 ring-4 ring-amber-500/20"
                        : ev.status === "FAILED"
                        ? "border-rose-400 ring-4 ring-rose-500/20"
                        : "border-sky-400"
                    }`}
                  />

                  {/* Event Card */}
                  <div className="rounded-xl p-4 bg-slate-900/50 border border-slate-800 hover:border-slate-700 transition-colors space-y-2">
                    <div className="flex items-center justify-between">
                      <div className="flex items-center gap-2 flex-wrap">
                        <span className="font-mono text-xs font-bold text-white">
                          {ev.event_type}
                        </span>
                        <span
                          className={`text-[10px] font-mono px-2 py-0.5 rounded ${
                            ev.source === "PAYPAL_API"
                              ? "bg-sky-950 text-sky-300 border border-sky-800/60"
                              : ev.source === "PAYPAL_WEBHOOK"
                              ? "bg-indigo-950 text-indigo-300 border border-indigo-800/60"
                              : ev.source === "SIMULATED"
                              ? "bg-slate-950 text-amber-400 border border-amber-900/60"
                              : "bg-slate-800 text-slate-300"
                          }`}
                        >
                          {ev.source}
                        </span>
                        {ev.is_simulated && (
                          <span className="text-[9px] font-mono text-amber-500/90 font-bold uppercase">
                            [SIMULATED]
                          </span>
                        )}
                      </div>
                      <span className="text-[11px] font-mono text-slate-500">
                        {new Date(ev.occurred_at).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit' })}
                      </span>
                    </div>

                    {/* Latency and Details */}
                    <div className="flex items-center gap-4 text-xs text-slate-400">
                      {ev.latency_ms !== null && ev.latency_ms !== undefined && (
                        <span className="flex items-center gap-1 font-mono text-[11px] text-cyan-400">
                          <Clock className="w-3 h-3" />
                          {ev.latency_ms} ms
                        </span>
                      )}
                      {ev.paypal_capture_id && (
                        <span className="font-mono text-[11px] text-slate-400">
                          Capture: {ev.paypal_capture_id}
                        </span>
                      )}
                    </div>

                    {/* Metadata summary */}
                    {Object.keys(ev.metadata_redacted || {}).length > 0 && (
                      <div className="p-2.5 rounded bg-slate-950/70 border border-slate-800/70 font-mono text-[11px] text-slate-300 overflow-x-auto">
                        <pre className="whitespace-pre-wrap">
                          {JSON.stringify(ev.metadata_redacted, null, 2)}
                        </pre>
                      </div>
                    )}
                  </div>
                </div>
              ))}
            </div>
          </div>

          {/* Session Recording Marker Box if available */}
          {sessionInfo?.has_session && (
            <div className="glass-panel rounded-2xl p-6 border border-slate-800 space-y-3">
              <div className="flex items-center justify-between">
                <div className="flex items-center gap-2.5">
                  <Video className="w-4 h-4 text-cyan-400" />
                  <h3 className="text-sm font-bold text-white">Linked Customer Checkout Session</h3>
                </div>
                <span className="text-xs font-mono text-emerald-400 bg-emerald-950 px-2 py-0.5 rounded border border-emerald-800">
                  {sessionInfo.events_count} RRWEB EVENTS
                </span>
              </div>
              <p className="text-xs text-slate-400">
                Session ID <span className="font-mono text-slate-200">{sessionInfo.session_id}</span> recorded
                with privacy masking on input elements. Replay is correlated with the timeline events above.
              </p>
            </div>
          )}
        </div>

        {/* Right: AI Investigator & Root Cause Diagnosis (5 cols) */}
        <div className="lg:col-span-5 space-y-6">
          <div className="glass-panel rounded-2xl p-6 border border-cyan-500/20 glow-blue space-y-6">
            <div className="flex items-center justify-between pb-4 border-b border-slate-800">
              <div className="flex items-center gap-2.5">
                <div className="p-2 rounded-lg bg-cyan-500/20 text-cyan-400">
                  <Brain className="w-5 h-5" />
                </div>
                <div>
                  <h2 className="text-base font-bold text-white">AI Payment Investigator</h2>
                  <p className="text-xs text-slate-400">Cross-signal root cause & safe recommendations</p>
                </div>
              </div>
            </div>

            {/* If not investigated yet, show prompt button */}
            {!investigation ? (
              <div className="text-center py-8 space-y-4">
                <Sparkles className="w-10 h-10 text-cyan-400 mx-auto animate-pulse" />
                <h3 className="text-sm font-bold text-white">Launch Evidence-Grounded Analysis</h3>
                <p className="text-xs text-slate-400 max-w-sm mx-auto">
                  The AI investigator will gather deterministic payment facts, check for timeout/decline patterns,
                  and formulate verified findings without inventing unobserved events.
                </p>
                <button
                  onClick={handleRunInvestigation}
                  disabled={investigating}
                  className="px-5 py-2.5 rounded-lg bg-cyan-500 text-slate-950 font-bold text-xs hover:bg-cyan-400 transition-all duration-150 shadow-md shadow-cyan-500/20 flex items-center gap-2 mx-auto disabled:opacity-50"
                >
                  {investigating ? <Loader2 className="w-4 h-4 animate-spin" /> : <Brain className="w-4 h-4" />}
                  Investigate Payment with AI
                </button>
              </div>
            ) : (
              <div className="space-y-6 animate-fadeIn">
                {/* Confidence & Severity Header */}
                <div className="flex items-center justify-between p-3.5 rounded-xl bg-slate-900/80 border border-slate-800">
                  <div>
                    <span className="text-[10px] text-slate-400 uppercase font-mono block">Severity Assessment</span>
                    <span
                      className={`text-xs font-bold font-mono ${
                        investigation.severity === "HIGH"
                          ? "text-rose-400"
                          : investigation.severity === "MEDIUM"
                          ? "text-amber-400"
                          : "text-emerald-400"
                      }`}
                    >
                      {investigation.severity} SEVERITY
                    </span>
                  </div>
                  <div className="text-right">
                    <span className="text-[10px] text-slate-400 uppercase font-mono block">Evidence Confidence</span>
                    <span className="text-xs font-bold text-cyan-400 font-mono">
                      {(investigation.confidence * 100).toFixed(0)}%
                    </span>
                  </div>
                </div>

                {/* Root Cause Card */}
                <div className="space-y-2">
                  <span className="text-[10px] font-mono uppercase text-slate-400 tracking-wider">Likely Root Cause</span>
                  <div className="p-3.5 rounded-xl bg-slate-900/60 border border-slate-800 text-xs font-semibold text-white leading-relaxed">
                    {investigation.root_cause}
                  </div>
                </div>

                {/* FACTS vs INFERENCES: PRD Differentiator */}
                <div className="space-y-4">
                  {/* Verified Facts */}
                  <div className="space-y-1.5">
                    <span className="text-[10px] font-mono uppercase text-emerald-400 tracking-wider flex items-center gap-1">
                      <CheckCircle2 className="w-3 h-3" />
                      Verified Provider Facts
                    </span>
                    <ul className="space-y-1.5">
                      {investigation.facts.map((fact, idx) => (
                        <li key={idx} className="text-xs text-slate-300 flex items-start gap-2 bg-slate-950/40 p-2 rounded border border-slate-800/60">
                          <span className="text-emerald-400 font-bold">•</span>
                          <span>{fact}</span>
                        </li>
                      ))}
                    </ul>
                  </div>

                  {/* Logical Inferences */}
                  <div className="space-y-1.5">
                    <span className="text-[10px] font-mono uppercase text-sky-400 tracking-wider flex items-center gap-1">
                      <Brain className="w-3 h-3" />
                      Investigative Inferences
                    </span>
                    <ul className="space-y-1.5">
                      {investigation.inferences.map((inf, idx) => (
                        <li key={idx} className="text-xs text-slate-300 flex items-start gap-2 bg-slate-950/40 p-2 rounded border border-slate-800/60">
                          <span className="text-sky-400 font-bold">↳</span>
                          <span>{inf}</span>
                        </li>
                      ))}
                    </ul>
                  </div>
                </div>

                {/* Customer & Revenue Impact */}
                <div className="grid grid-cols-1 sm:grid-cols-2 gap-3 text-xs">
                  <div className="p-3 rounded-lg bg-slate-900/40 border border-slate-800 space-y-1">
                    <span className="text-[10px] text-slate-500 uppercase font-mono block">Customer Impact</span>
                    <p className="text-slate-300 leading-relaxed text-[11px]">{investigation.customer_impact}</p>
                  </div>
                  <div className="p-3 rounded-lg bg-slate-900/40 border border-slate-800 space-y-1">
                    <span className="text-[10px] text-amber-400/80 uppercase font-mono block">Potential Revenue at Risk</span>
                    <p className="text-slate-300 leading-relaxed text-[11px]">{investigation.business_impact}</p>
                  </div>
                </div>

                {/* Recommended Next Action */}
                <div className="p-4 rounded-xl bg-cyan-950/30 border border-cyan-800/60 space-y-1.5">
                  <span className="text-[10px] font-mono uppercase text-cyan-400 font-bold block">
                    Recommended Operator Action
                  </span>
                  <p className="text-xs text-cyan-200 font-medium leading-relaxed">
                    {investigation.recommendation}
                  </p>
                </div>

                {/* Model Attribution */}
                <div className="text-[10px] font-mono text-slate-500 flex items-center justify-between pt-2 border-t border-slate-800">
                  <span>Engine: {investigation.model_name}</span>
                  <button
                    onClick={handleRunInvestigation}
                    disabled={investigating}
                    className="text-cyan-400 hover:underline"
                  >
                    Re-analyze
                  </button>
                </div>
              </div>
            )}
          </div>

          {/* Interactive Investigator Chat Box */}
          {investigation && (
            <div className="glass-panel rounded-2xl p-5 border border-slate-800 space-y-4">
              <div className="flex items-center gap-2">
                <Brain className="w-4 h-4 text-cyan-400" />
                <h3 className="text-xs font-bold text-white uppercase tracking-wider font-mono">
                  Ask Follow-Up Question
                </h3>
              </div>

              {/* Chat Thread */}
              <div className="space-y-3 max-h-56 overflow-y-auto pr-1">
                {chatMessages.length === 0 && (
                  <p className="text-xs text-slate-500 italic">
                    Ask questions like &ldquo;Can I immediately retry this capture?&rdquo; or &ldquo;What did the customer experience?&rdquo;
                  </p>
                )}
                {chatMessages.map((msg, i) => (
                  <div
                    key={i}
                    className={`p-3 rounded-lg text-xs leading-relaxed ${
                      msg.role === "user"
                        ? "bg-slate-800 text-white ml-6"
                        : "bg-cyan-950/60 border border-cyan-800/60 text-cyan-100 mr-6"
                    }`}
                  >
                    <span className="text-[9px] font-mono text-slate-400 block mb-1">
                      {msg.role === "user" ? "OPERATOR" : "AI INVESTIGATOR"}
                    </span>
                    {msg.content}
                  </div>
                ))}
                {chatLoading && (
                  <div className="p-2.5 rounded-lg bg-cyan-950/40 text-xs text-cyan-300 flex items-center gap-2">
                    <Loader2 className="w-3.5 h-3.5 animate-spin" />
                    Querying grounded evidence tools...
                  </div>
                )}
              </div>

              {/* Input */}
              <form onSubmit={handleSendChat} className="flex gap-2">
                <input
                  type="text"
                  placeholder="e.g. Is it safe to retry this payment?"
                  value={chatInput}
                  onChange={(e) => setChatInput(e.target.value)}
                  className="flex-1 bg-slate-900 border border-slate-800 rounded-lg px-3 py-2 text-xs text-white placeholder-slate-500 focus:outline-none focus:border-cyan-500"
                />
                <button
                  type="submit"
                  disabled={chatLoading || !chatInput.trim()}
                  className="px-3 py-2 bg-cyan-500 hover:bg-cyan-400 text-slate-950 rounded-lg text-xs font-bold transition-colors disabled:opacity-50"
                >
                  <Send className="w-3.5 h-3.5" />
                </button>
              </form>
            </div>
          )}
        </div>
      </div>

      {/* Propose Refund Modal */}
      {showRefundModal && (
        <div className="fixed inset-0 bg-slate-950/80 backdrop-blur-sm z-50 flex items-center justify-center p-4">
          <div className="glass-panel max-w-md w-full rounded-2xl p-6 border border-slate-700 space-y-5 animate-scaleUp">
            <h3 className="text-base font-bold text-white flex items-center gap-2">
              <DollarSign className="w-5 h-5 text-purple-400" />
              Propose Refund for Approval
            </h3>
            <p className="text-xs text-slate-400">
              In accordance with PayTrace policy, refunds require explicit human operator confirmation.
              This action creates a pending ticket in the Approval Inbox.
            </p>

            <div className="space-y-2">
              <label className="text-xs font-mono text-slate-400">Refund Amount</label>
              <div className="p-2.5 bg-slate-900 rounded-lg border border-slate-800 text-xs font-bold text-white">
                ${Number(payment.amount).toFixed(2)} {payment.currency} (Full Refund)
              </div>
            </div>

            <div className="space-y-2">
              <label className="text-xs font-mono text-slate-400">Reason / Justification</label>
              <textarea
                value={refundReason}
                onChange={(e) => setRefundReason(e.target.value)}
                rows={3}
                className="w-full bg-slate-900 border border-slate-800 rounded-lg p-2.5 text-xs text-white placeholder-slate-500 focus:outline-none focus:border-cyan-500"
              />
            </div>

            <div className="flex items-center justify-end gap-3 pt-2">
              <button
                type="button"
                onClick={() => setShowRefundModal(false)}
                className="px-4 py-2 rounded-lg text-xs font-medium text-slate-400 hover:text-white"
              >
                Cancel
              </button>
              <button
                type="button"
                onClick={handleProposeRefund}
                disabled={refundSubmitting}
                className="px-4 py-2 rounded-lg bg-purple-600 hover:bg-purple-500 text-white text-xs font-bold transition-colors flex items-center gap-1.5"
              >
                {refundSubmitting ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : null}
                Submit Proposal
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
