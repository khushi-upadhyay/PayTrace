"use client";

import { useEffect, useRef, useState } from "react";
import { useParams } from "next/navigation";
import Link from "next/link";
import {
  api,
  PaymentItem,
  TimelineData,
  PaymentEventItem,
  AIInvestigationData,
  DisputeItem,
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
  Scale,
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
  const chatThreadEndRef = useRef<HTMLDivElement | null>(null);

  // Refund modal state
  const [showRefundModal, setShowRefundModal] = useState(false);
  const [refundReason, setRefundReason] = useState("Customer requested cancellation");
  const [refundSubmitting, setRefundSubmitting] = useState(false);
  const [refundNotice, setRefundNotice] = useState<string | null>(null);

  // Reconcile status state
  const [reconciling, setReconciling] = useState(false);
  const [reconcileResult, setReconcileResult] = useState<any>(null);

  // Dispute state
  const [disputes, setDisputes] = useState<DisputeItem[]>([]);
  const [showDisputeModal, setShowDisputeModal] = useState(false);
  const [disputeReason, setDisputeReason] = useState("MERCHANDISE_OR_SERVICE_NOT_RECEIVED");
  const [disputeStatement, setDisputeStatement] = useState("");
  const [disputeSubmitting, setDisputeSubmitting] = useState(false);
  const [respondingDisputeId, setRespondingDisputeId] = useState<string | null>(null);
  const [disputeResponseText, setDisputeResponseText] = useState("");
  const [disputeAcceptLiability, setDisputeAcceptLiability] = useState(false);
  const [disputeNotice, setDisputeNotice] = useState<string | null>(null);

  const loadData = async () => {
    try {
      setLoading(true);
      setError(null);
      const [pm, tl, sess, disp] = await Promise.all([
        api.getPayment(paymentId),
        api.getPaymentTimeline(paymentId),
        api.getPaymentSession(paymentId).catch(() => null),
        api.getDisputesForPayment(paymentId).catch(() => null),
      ]);
      setPayment(pm);
      setTimeline(tl);
      setSessionInfo(sess);
      setDisputes(disp?.items || []);
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

  // The chat thread is a fixed-height scrollable box; without this, new
  // messages render below the visible fold and the chat looks dead.
  useEffect(() => {
    chatThreadEndRef.current?.scrollIntoView({ block: "nearest" });
  }, [chatMessages, chatLoading]);

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

  const handleSimulateDispute = async () => {
    try {
      setDisputeSubmitting(true);
      await api.simulateDispute({
        payment_id: paymentId,
        reason: disputeReason,
        buyer_statement: disputeStatement.trim() || undefined,
      });
      setDisputeNotice("Simulated dispute opened. Respond within the demo's 10-day window to resolve it.");
      setShowDisputeModal(false);
      setDisputeStatement("");
      loadData();
    } catch (err: any) {
      alert(`Error opening dispute: ${err.message}`);
    } finally {
      setDisputeSubmitting(false);
    }
  };

  const handleRespondToDispute = async (disputeId: string) => {
    if (!disputeResponseText.trim()) return;
    try {
      setDisputeSubmitting(true);
      const updated = await api.respondToDispute(disputeId, {
        seller_response: disputeResponseText.trim(),
        accept_liability: disputeAcceptLiability,
      });
      setDisputeNotice(
        updated.status === "RESOLVED_BUYER_FAVOUR"
          ? "Response submitted. Liability accepted — route a refund through Approvals to reconcile the ledger."
          : "Response submitted. Dispute moved to UNDER_REVIEW."
      );
      setRespondingDisputeId(null);
      setDisputeResponseText("");
      setDisputeAcceptLiability(false);
      loadData();
    } catch (err: any) {
      alert(`Error responding to dispute: ${err.message}`);
    } finally {
      setDisputeSubmitting(false);
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
        <h2 className="text-lg font-bold text-ink">Payment Record Not Found</h2>
        <p className="text-xs text-slate-400">{error || "Payment record could not be loaded."}</p>
        <Link href="/payments" className="px-4 py-2 bg-slate-800 hover:bg-slate-700 text-ink text-xs font-semibold rounded-lg inline-block transition-colors duration-150">
          Return to Ledger
        </Link>
      </div>
    );
  }

  const isTimeoutUncertain = payment.status === "CAPTURE_UNCERTAIN" || payment.failure_code === "TIMEOUT_BEFORE_RESPONSE";
  const hasOpenDispute = disputes.some((d) => d.status === "OPEN" || d.status === "UNDER_REVIEW");
  const canOpenDispute = payment.status === "CAPTURED" && !hasOpenDispute;

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
              className="px-3.5 py-1.5 rounded-lg bg-cyan-600 hover:bg-cyan-500 text-onsolid text-xs font-bold transition-colors flex items-center gap-1.5"
            >
              {reconciling ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <RotateCcw className="w-3.5 h-3.5" />}
              Reconcile with PayPal
            </button>
          )}
          {canOpenDispute && (
            <button
              onClick={() => setShowDisputeModal(true)}
              className="px-3.5 py-1.5 rounded-lg bg-slate-900 border border-slate-700 hover:bg-slate-800 text-slate-200 text-xs font-semibold transition-colors flex items-center gap-1.5"
            >
              <Scale className="w-3.5 h-3.5" />
              Simulate Dispute
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

      {disputeNotice && (
        <div className="p-3.5 rounded-lg bg-sky-950/70 border border-sky-800 text-sky-300 text-xs flex items-center gap-2">
          <Scale className="w-4 h-4 text-sky-400 shrink-0" />
          {disputeNotice}
        </div>
      )}

      {/* Payment Master Header Card */}
      <div className="glass-panel rounded-2xl p-6 border border-slate-800 space-y-6">
        <div className="flex flex-col lg:flex-row lg:items-center justify-between gap-6 pb-6 border-b border-slate-800">
          <div>
            <div className="flex items-center gap-3">
              <h1 className="text-xl font-extrabold text-ink tracking-tight">
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
                <span className="text-[10px] text-cyan-400">Copied!</span>
              )}
            </div>
            <p className="text-xs text-slate-400 mt-1 flex items-center gap-2">
              Customer: <span className="text-slate-200 font-medium">{payment.customer_ref}</span>
              <span>•</span>
              Created: <span className="text-slate-200">{new Date(payment.created_at).toLocaleString()}</span>
            </p>
          </div>

          <div className="flex flex-wrap items-center gap-3">
            <Link href={`/investigate?payment_id=${encodeURIComponent(payment.id)}`} className="inline-flex items-center gap-2 rounded-lg border border-cyan-200 bg-blue-50 px-3 py-2 text-xs font-semibold text-cyan-800 hover:bg-blue-100 focus-visible:outline focus-visible:outline-2 focus-visible:outline-cyan-600">
              <Brain className="h-3.5 w-3.5" /> Ask AI about this payment
            </Link>
            {/* Status Pill */}
            <div className="flex flex-col items-end">
              <span className="text-[10px] text-slate-500 uppercase tracking-wider">Lifecycle State</span>
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
              <span className="text-[10px] text-slate-500 uppercase tracking-wider">Amount</span>
              <span className="text-xl font-black text-ink mt-0.5">
                ${Number(payment.amount).toFixed(2)} <span className="text-xs text-slate-400">{payment.currency}</span>
              </span>
            </div>
          </div>
        </div>

        {/* Provider IDs & Metadata Bar */}
        <div className="grid grid-cols-1 md:grid-cols-4 gap-4 text-xs">
          <div className="rounded-lg p-3 bg-slate-900/60 border border-slate-800/80">
            <span className="text-[10px] text-slate-500 uppercase block">PayPal Order ID</span>
            <div className="flex items-center justify-between mt-1">
              <span className="text-slate-200 font-medium">
                {payment.paypal_order_id || "None"}
              </span>
              {payment.paypal_order_id && (
                <button
                  onClick={() => handleCopy(payment.paypal_order_id!, "oid")}
                  className="text-slate-500 transition-colors duration-150 hover:text-cyan-400"
                >
                  <Copy className="w-3 h-3" />
                </button>
              )}
            </div>
          </div>

          <div className="rounded-lg p-3 bg-slate-900/60 border border-slate-800/80">
            <span className="text-[10px] text-slate-500 uppercase block">PayPal Capture ID</span>
            <div className="flex items-center justify-between mt-1">
              <span className="text-slate-200 font-medium">
                {payment.paypal_capture_id || "Unresolved"}
              </span>
              {payment.paypal_capture_id && (
                <button
                  onClick={() => handleCopy(payment.paypal_capture_id!, "cid")}
                  className="text-slate-500 transition-colors duration-150 hover:text-cyan-400"
                >
                  <Copy className="w-3 h-3" />
                </button>
              )}
            </div>
          </div>

          <div className="rounded-lg p-3 bg-slate-900/60 border border-slate-800/80">
            <span className="text-[10px] text-slate-500 uppercase block">Source Environment</span>
            <span
              className={`text-xs font-semibold inline-block mt-1 ${
                payment.source_mode === "SIMULATED" ? "text-amber-400" : "text-cyan-400"
              }`}
            >
              {payment.source_mode === "SIMULATED" ? "SIMULATED DEMO EVENT" : payment.source_mode}
            </span>
          </div>

          <div className="rounded-lg p-3 bg-slate-900/60 border border-slate-800/80">
            <span className="text-[10px] text-slate-500 uppercase block">Total Lifecycle Duration</span>
            <span className="text-slate-200 font-medium block mt-1">
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
                Funds may already be captured at PayPal. <strong className="text-ink underline">DO NOT BLINDLY RETRY</strong>.
              </p>
            </div>
          </div>
          <div className="text-xs bg-slate-950/70 p-3 rounded-lg border border-amber-800/50 text-slate-300">
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
                <h2 className="text-base font-bold text-ink flex items-center gap-2">
                  <Activity className="w-4 h-4 text-cyan-400" />
                  Unified Chronological Timeline
                </h2>
                <p className="text-xs text-slate-400 mt-0.5">
                  Append-only trace correlating frontend, PayPal APIs, and webhooks
                </p>
              </div>
              <span className="text-xs text-slate-400">
                {timeline?.total_events || 0} Events
              </span>
            </div>

            {/* Timeline Events Stack */}
            <div className="relative pl-6 space-y-6 before:absolute before:left-2.5 before:top-3 before:bottom-3 before:w-0.5 before:bg-slate-800">
              {timeline?.events.map((ev: any, idx: number) => (
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
                        <span className="text-xs font-bold text-ink">
                          {ev.event_type}
                        </span>
                        <span
                          className={`text-[10px] px-2 py-0.5 rounded ${
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
                          <span className="text-[9px] text-amber-500/90 font-bold uppercase">
                            [SIMULATED]
                          </span>
                        )}
                      </div>
                      <span className="text-[11px] text-slate-500">
                        {new Date(ev.occurred_at).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit' })}
                      </span>
                    </div>

                    {/* Latency and Details */}
                    <div className="flex items-center gap-4 text-xs text-slate-400">
                      {ev.latency_ms !== null && ev.latency_ms !== undefined && (
                        <span className="flex items-center gap-1 text-[11px] text-cyan-400">
                          <Clock className="w-3 h-3" />
                          {ev.latency_ms} ms
                        </span>
                      )}
                      {ev.paypal_capture_id && (
                        <span className="text-[11px] text-slate-400">
                          Capture: {ev.paypal_capture_id}
                        </span>
                      )}
                    </div>

                    {/* Metadata summary */}
                    {Object.keys(ev.metadata_redacted || {}).length > 0 && (
                      <div className="p-2.5 rounded bg-slate-950/70 border border-slate-800/70 text-[11px] text-slate-300 overflow-x-auto">
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
                  <h3 className="text-sm font-bold text-ink">Linked Customer Checkout Session</h3>
                </div>
                <span className="text-xs text-emerald-400 bg-emerald-950 px-2 py-0.5 rounded border border-emerald-800">
                  {sessionInfo.events_count} SESSION EVENTS
                </span>
              </div>
              <p className="text-xs text-slate-400">
                Session ID <span className="text-slate-200">{sessionInfo.session_id}</span> recorded
                with privacy masking on input elements. PayPal-hosted pages are not recorded.
              </p>
              <Link href={`/sessions/${sessionInfo.session_id}`} className="inline-flex items-center gap-1.5 rounded-lg border border-cyan-500/30 bg-cyan-950/30 px-3 py-2 text-xs font-semibold text-cyan-200 transition-colors duration-150 hover:bg-cyan-950/60">
                Replay customer session <Video className="h-3.5 w-3.5" />
              </Link>
            </div>
          )}

          {/* Disputes */}
          {disputes.length > 0 && (
            <div className="glass-panel rounded-2xl p-6 border border-slate-800 space-y-4">
              <div className="flex items-center gap-2.5">
                <Scale className="w-4 h-4 text-amber-400" />
                <h3 className="text-sm font-bold text-ink">Disputes</h3>
              </div>
              {disputes.map((d) => (
                <div key={d.id} className="rounded-xl border border-slate-800 bg-slate-900/60 p-4 space-y-3">
                  <div className="flex items-center justify-between flex-wrap gap-2">
                    <span
                      className={`text-[10px] font-bold px-2 py-0.5 rounded-full uppercase tracking-wider ${
                        d.status === "OPEN"
                          ? "bg-amber-950 text-amber-300 border border-amber-800"
                          : d.status === "UNDER_REVIEW"
                          ? "bg-sky-950 text-sky-300 border border-sky-800"
                          : d.status === "RESOLVED_BUYER_FAVOUR"
                          ? "bg-purple-950 text-purple-300 border border-purple-800"
                          : "bg-emerald-950 text-emerald-300 border border-emerald-800"
                      }`}
                    >
                      {d.status.replace(/_/g, " ")}
                    </span>
                    <span className="text-[10px] text-slate-500 font-mono">{d.paypal_dispute_id}</span>
                  </div>
                  <p className="text-xs text-slate-300">
                    Reason: <span className="text-slate-100 font-medium">{d.reason.replace(/_/g, " ")}</span>
                    {" "}· ${Number(d.amount).toFixed(2)} {d.currency}
                  </p>
                  {d.buyer_statement && (
                    <p className="text-xs text-slate-400 italic">&ldquo;{d.buyer_statement}&rdquo;</p>
                  )}
                  {d.response_due_by && (d.status === "OPEN" || d.status === "UNDER_REVIEW") && (
                    <p className="text-[11px] text-amber-400">
                      Respond by {new Date(d.response_due_by).toLocaleDateString()}
                    </p>
                  )}
                  {d.seller_response && (
                    <p className="text-xs text-slate-400">
                      <span className="text-slate-500">Your response:</span> {d.seller_response}
                    </p>
                  )}
                  {d.outcome_note && (
                    <p className="text-xs text-cyan-300 bg-cyan-950/30 border border-cyan-800/40 rounded-lg p-2.5">
                      {d.outcome_note}
                    </p>
                  )}

                  {(d.status === "OPEN" || d.status === "UNDER_REVIEW") && (
                    respondingDisputeId === d.id ? (
                      <div className="space-y-2 pt-2 border-t border-slate-800">
                        <textarea
                          value={disputeResponseText}
                          onChange={(e) => setDisputeResponseText(e.target.value)}
                          maxLength={1024}
                          rows={3}
                          placeholder="Evidence or explanation for this dispute..."
                          className="w-full bg-slate-950 border border-slate-800 rounded-lg p-2.5 text-xs text-ink placeholder-slate-500 focus:outline-none focus:border-cyan-500"
                        />
                        <label className="flex items-center gap-2 text-[11px] text-slate-400">
                          <input
                            type="checkbox"
                            checked={disputeAcceptLiability}
                            onChange={(e) => setDisputeAcceptLiability(e.target.checked)}
                            className="rounded accent-cyan-500"
                          />
                          Accept liability (resolves in the buyer&apos;s favour)
                        </label>
                        <div className="flex gap-2">
                          <button
                            onClick={() => { setRespondingDisputeId(null); setDisputeResponseText(""); setDisputeAcceptLiability(false); }}
                            className="px-3 py-1.5 rounded-lg bg-slate-800 hover:bg-slate-700 text-slate-300 text-xs font-medium"
                          >
                            Cancel
                          </button>
                          <button
                            onClick={() => handleRespondToDispute(d.id)}
                            disabled={disputeSubmitting || !disputeResponseText.trim()}
                            className="px-3 py-1.5 rounded-lg bg-cyan-500 hover:bg-cyan-400 text-onsolid text-xs font-bold disabled:opacity-50"
                          >
                            Submit Response
                          </button>
                        </div>
                      </div>
                    ) : (
                      <button
                        onClick={() => setRespondingDisputeId(d.id)}
                        className="px-3 py-1.5 rounded-lg bg-slate-800 hover:bg-slate-700 text-slate-200 text-xs font-semibold"
                      >
                        Respond to Dispute
                      </button>
                    )
                  )}
                </div>
              ))}
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
                  <h2 className="text-base font-bold text-ink">AI Payment Investigator</h2>
                  <p className="text-xs text-slate-400">Cross-signal root cause & safe recommendations</p>
                </div>
              </div>
            </div>

            {/* If not investigated yet, show prompt button */}
            {!investigation ? (
              <div className="text-center py-8 space-y-4">
                <Sparkles className="w-10 h-10 text-cyan-400 mx-auto animate-pulse" />
                <h3 className="text-sm font-bold text-ink">Launch Evidence-Grounded Analysis</h3>
                <p className="text-xs text-slate-400 max-w-sm mx-auto">
                  The AI investigator will gather deterministic payment facts, check for timeout/decline patterns,
                  and formulate verified findings without inventing unobserved events.
                </p>
                <button
                  onClick={handleRunInvestigation}
                  disabled={investigating}
                  className="px-5 py-2.5 rounded-lg bg-cyan-500 text-onsolid font-bold text-xs hover:bg-cyan-400 transition-all duration-150 shadow-md shadow-cyan-500/20 flex items-center gap-2 mx-auto disabled:opacity-50"
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
                    <span className="text-[10px] text-slate-400 uppercase block">Severity Assessment</span>
                    <span
                      className={`text-xs font-bold ${
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
                    <span className="text-[10px] text-slate-400 uppercase block">Evidence confidence</span>
                    <span className="text-xs font-bold text-cyan-700">
                      {investigation.confidence >= 0.75 ? "Strong" : investigation.confidence >= 0.5 ? "Partial" : "Limited"}
                    </span>
                  </div>
                </div>

                {/* Root Cause Card */}
                <div className="space-y-2">
                  <span className="text-[10px] uppercase text-slate-400 tracking-wider">Likely Root Cause</span>
                  <div className="p-3.5 rounded-xl bg-slate-900/60 border border-slate-800 text-xs font-semibold text-ink leading-relaxed">
                    {investigation.root_cause}
                  </div>
                </div>

                {/* FACTS vs INFERENCES: PRD Differentiator */}
                <div className="space-y-4">
                  {/* Verified Facts */}
                  <div className="space-y-1.5">
                    <span className="text-[10px] uppercase text-emerald-400 tracking-wider flex items-center gap-1">
                      <CheckCircle2 className="w-3 h-3" />
                      Verified Provider Facts
                    </span>
                    <ul className="space-y-1.5">
                      {investigation.facts.map((fact: any, idx: number) => (
                        <li key={idx} className="text-xs text-slate-300 flex items-start gap-2 bg-slate-950/40 p-2 rounded border border-slate-800/60">
                          <span className="text-emerald-400 font-bold">•</span>
                          <span>{fact}</span>
                        </li>
                      ))}
                    </ul>
                  </div>

                  {/* Logical Inferences */}
                  <div className="space-y-1.5">
                    <span className="text-[10px] uppercase text-sky-400 tracking-wider flex items-center gap-1">
                      <Brain className="w-3 h-3" />
                      Investigative Inferences
                    </span>
                    <ul className="space-y-1.5">
                      {investigation.inferences.map((inf: any, idx: number) => (
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
                    <span className="text-[10px] text-slate-500 uppercase block">Customer Impact</span>
                    <p className="text-slate-300 leading-relaxed text-[11px]">{investigation.customer_impact}</p>
                  </div>
                  <div className="p-3 rounded-lg bg-slate-900/40 border border-slate-800 space-y-1">
                    <span className="text-[10px] text-amber-400/80 uppercase block">Potential Revenue at Risk</span>
                    <p className="text-slate-300 leading-relaxed text-[11px]">{investigation.business_impact}</p>
                  </div>
                </div>

                {/* Recommended Next Action */}
                <div className="p-4 rounded-xl bg-cyan-950/30 border border-cyan-800/60 space-y-1.5">
                  <span className="text-[10px] uppercase text-cyan-400 font-bold block">
                    Recommended Operator Action
                  </span>
                  <p className="text-xs text-cyan-200 font-medium leading-relaxed">
                    {investigation.recommendation}
                  </p>
                </div>

                {/* Model Attribution */}
                <div className="text-[10px] text-slate-500 flex items-center justify-between pt-2 border-t border-slate-800">
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
                <h3 className="text-xs font-bold text-ink uppercase tracking-wider">
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
                        ? "bg-slate-800 text-ink ml-6"
                        : "bg-cyan-950/60 border border-cyan-800/60 text-cyan-100 mr-6"
                    }`}
                  >
                    <span className="text-[9px] text-slate-400 block mb-1">
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
                <div ref={chatThreadEndRef} />
              </div>

              {/* Input */}
              <form onSubmit={handleSendChat} className="flex gap-2">
                <input
                  type="text"
                  placeholder="e.g. Is it safe to retry this payment?"
                  value={chatInput}
                  onChange={(e) => setChatInput(e.target.value)}
                  className="flex-1 bg-slate-900 border border-slate-800 rounded-lg px-3 py-2 text-xs text-ink placeholder-slate-500 focus:outline-none focus:border-cyan-500"
                />
                <button
                  type="submit"
                  disabled={chatLoading || !chatInput.trim()}
                  className="px-3 py-2 bg-cyan-500 hover:bg-cyan-400 text-onsolid rounded-lg text-xs font-bold transition-colors disabled:opacity-50"
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
            <h3 className="text-base font-bold text-ink flex items-center gap-2">
              <DollarSign className="w-5 h-5 text-purple-400" />
              Propose Refund for Approval
            </h3>
            <p className="text-xs text-slate-400">
              In accordance with PayTrace policy, refunds require explicit human operator confirmation.
              This action creates a pending ticket in the Approval Inbox.
            </p>

            <div className="space-y-2">
              <label className="text-xs text-slate-400">Refund Amount</label>
              <div className="p-2.5 bg-slate-900 rounded-lg border border-slate-800 text-xs font-bold text-ink">
                ${Number(payment.amount).toFixed(2)} {payment.currency} (Full Refund)
              </div>
            </div>

            <div className="space-y-2">
              <label className="text-xs text-slate-400">Reason / Justification</label>
              <textarea
                value={refundReason}
                onChange={(e) => setRefundReason(e.target.value)}
                rows={3}
                className="w-full bg-slate-900 border border-slate-800 rounded-lg p-2.5 text-xs text-ink placeholder-slate-500 focus:outline-none focus:border-cyan-500"
              />
            </div>

            <div className="flex items-center justify-end gap-3 pt-2">
              <button
                type="button"
                onClick={() => setShowRefundModal(false)}
                className="px-4 py-2 rounded-lg text-xs font-medium text-slate-400 transition-colors duration-150 hover:text-ink"
              >
                Cancel
              </button>
              <button
                type="button"
                onClick={handleProposeRefund}
                disabled={refundSubmitting}
                className="px-4 py-2 rounded-lg bg-purple-600 hover:bg-purple-500 text-onsolid text-xs font-bold transition-colors flex items-center gap-1.5"
              >
                {refundSubmitting ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : null}
                Submit Proposal
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Simulate Dispute Modal */}
      {showDisputeModal && (
        <div className="fixed inset-0 bg-slate-950/80 backdrop-blur-sm z-50 flex items-center justify-center p-4">
          <div className="glass-panel max-w-md w-full rounded-2xl p-6 border border-slate-700 space-y-5 animate-scaleUp">
            <h3 className="text-base font-bold text-ink flex items-center gap-2">
              <Scale className="w-5 h-5 text-amber-400" />
              Simulate a Buyer Dispute
            </h3>
            <p className="text-xs text-slate-400">
              This sandbox does not call PayPal&apos;s live Disputes API. It creates a clearly-labelled
              simulated dispute so you can exercise the respond/resolve workflow end to end.
            </p>

            <div className="space-y-2">
              <label className="text-xs text-slate-400">Reason</label>
              <select
                value={disputeReason}
                onChange={(e) => setDisputeReason(e.target.value)}
                className="w-full bg-slate-900 border border-slate-800 rounded-lg p-2.5 text-xs text-ink focus:outline-none focus:border-cyan-500"
              >
                <option value="MERCHANDISE_OR_SERVICE_NOT_RECEIVED">Merchandise/service not received</option>
                <option value="MERCHANDISE_OR_SERVICE_NOT_AS_DESCRIBED">Not as described</option>
                <option value="UNAUTHORIZED">Unauthorized transaction</option>
                <option value="CREDIT_NOT_PROCESSED">Credit not processed</option>
                <option value="DUPLICATE_TRANSACTION">Duplicate transaction</option>
                <option value="OTHER">Other</option>
              </select>
            </div>

            <div className="space-y-2">
              <label className="text-xs text-slate-400">Buyer statement (optional)</label>
              <textarea
                value={disputeStatement}
                onChange={(e) => setDisputeStatement(e.target.value)}
                maxLength={1024}
                rows={3}
                placeholder="What the buyer says went wrong..."
                className="w-full bg-slate-900 border border-slate-800 rounded-lg p-2.5 text-xs text-ink placeholder-slate-500 focus:outline-none focus:border-cyan-500"
              />
            </div>

            <div className="flex items-center justify-end gap-3 pt-2">
              <button
                type="button"
                onClick={() => setShowDisputeModal(false)}
                className="px-4 py-2 rounded-lg text-xs font-medium text-slate-400 transition-colors duration-150 hover:text-ink"
              >
                Cancel
              </button>
              <button
                type="button"
                onClick={handleSimulateDispute}
                disabled={disputeSubmitting}
                className="px-4 py-2 rounded-lg bg-amber-600 hover:bg-amber-500 text-onsolid text-xs font-bold transition-colors flex items-center gap-1.5"
              >
                {disputeSubmitting ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : null}
                Open Dispute
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
