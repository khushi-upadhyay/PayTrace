"use client";

import { useEffect, useRef, useState } from "react";
import Link from "next/link";
import { api, PaymentItem, AIInvestigationData, IncidentItem } from "@/lib/api";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import {
  Brain,
  Search,
  Sparkles,
  Loader2,
  CheckCircle2,
  Clock,
  ArrowRight,
  ShieldAlert,
  Send,
  HelpCircle,
} from "lucide-react";

function ChatMarkdown({ content }: { content: string }) {
  return (
    <div className="chat-markdown">
      <ReactMarkdown
        remarkPlugins={[remarkGfm]}
        components={{
          h1: ({ children }) => <h1>{children}</h1>,
          h2: ({ children }) => <h2>{children}</h2>,
          h3: ({ children }) => <h3>{children}</h3>,
          p: ({ children }) => <p>{children}</p>,
          ul: ({ children }) => <ul>{children}</ul>,
          ol: ({ children }) => <ol>{children}</ol>,
          li: ({ children }) => <li>{children}</li>,
          blockquote: ({ children }) => <blockquote>{children}</blockquote>,
          code: ({ children, className }) => className
            ? <code className={className}>{children}</code>
            : <code className="chat-inline-code">{children}</code>,
          pre: ({ children }) => <pre>{children}</pre>,
          a: ({ children, href }) => <a href={href} target="_blank" rel="noreferrer">{children}</a>,
          table: ({ children }) => <div className="chat-table-wrap"><table>{children}</table></div>,
          th: ({ children }) => <th>{children}</th>,
          td: ({ children }) => <td>{children}</td>,
          br: () => <br />,
        }}
      >
        {content}
      </ReactMarkdown>
    </div>
  );
}

export default function InvestigateHubPage() {
  const [payments, setPayments] = useState<PaymentItem[]>([]);
  const [selectedPaymentId, setSelectedPaymentId] = useState<string>("");
  const [incidentContext, setIncidentContext] = useState<IncidentItem | null>(null);
  const [question, setQuestion] = useState("Investigate payment outcome, uncertainty, and root cause");
  const [investigation, setInvestigation] = useState<AIInvestigationData | null>(null);
  const [loading, setLoading] = useState(false);
  const [contextLoading, setContextLoading] = useState(true);

  // Chat follow-up
  const [chatMessages, setChatMessages] = useState<Array<{ role: string; content: string; activity?: { nodes: string[]; tools: string[]; tracing: boolean; answerMode: string; model: string; fallbackReason: string | null } }>>([]);
  const [chatInput, setChatInput] = useState("");
  const [chatLoading, setChatLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const chatThreadRef = useRef<HTMLDivElement | null>(null);
  const autoInvestigatedIncidents = useRef(new Set<string>());
  const autoInvestigatedPayments = useRef(new Set<string>());
  const promptSuggestions = ["Why did checkout failures increase in the last 15 minutes?", "Which failure pattern affects the most transactions?", "Are failures related to PayPal API latency or merchant backend errors?", "Which transactions require reconciliation?"];

  // The chat thread is a fixed-height scrollable box; without this, new
  // messages render below the visible fold and the chat looks dead.
  useEffect(() => {
    const thread = chatThreadRef.current;
    if (thread) thread.scrollTop = thread.scrollHeight;
  }, [chatMessages, chatLoading]);

  useEffect(() => {
    const params = new URLSearchParams(window.location.search);
    const requestedPayment = params.get("payment_id");
    const requestedIncident = params.get("incident_id");
    if (requestedIncident) setLoading(true);
    Promise.all([api.getPayments({ page_size: 100 }), requestedIncident ? api.getIncident(requestedIncident) : Promise.resolve(null)])
      .then(async ([res, incident]) => {
        setPayments(res.items);
        if (incident) {
          setIncidentContext(incident);
          setSelectedPaymentId(incident.affected_payments?.[0]?.id || "");
          const incidentQuestion = `Investigate incident ${incident.title} and its supporting evidence`;
          setQuestion(incidentQuestion);
          try {
            if (!autoInvestigatedIncidents.current.has(incident.id)) {
              autoInvestigatedIncidents.current.add(incident.id);
              setInvestigation(await api.investigatePayment(null, incidentQuestion, incident.id));
            }
          } catch (err) {
            setError(err instanceof Error ? err.message : "Incident investigation could not be completed.");
          } finally { setLoading(false); }
        } else if (res.items.length > 0) {
          const preferred = res.items.find((p) => p.status === "CAPTURE_UNCERTAIN" || p.status === "DENIED") || res.items[0];
          const selected = res.items.find((payment) => payment.id === requestedPayment) || preferred;
          setSelectedPaymentId(selected.id);
          const initialQuestion = "Investigate payment outcome, uncertainty, and root cause";
          if (!autoInvestigatedPayments.current.has(selected.id)) {
            autoInvestigatedPayments.current.add(selected.id);
            setLoading(true);
            try {
              setInvestigation(await api.investigatePayment(selected.id, initialQuestion));
            } catch (err) {
              setError(err instanceof Error ? err.message : "Payment investigation could not be completed.");
            } finally {
              setLoading(false);
            }
          }
        }
      }).catch((err) => { setError(err instanceof Error ? err.message : "Investigation context could not be loaded."); setLoading(false); })
      .finally(() => setContextLoading(false));
  }, []);

  const handleRunInvestigation = async (e?: React.FormEvent) => {
    if (e) e.preventDefault();

    try {
      setLoading(true);
      setError(null);
      setChatMessages([]);
      const res = await api.investigatePayment(incidentContext ? null : selectedPaymentId || null, question, incidentContext?.id);
      setInvestigation(res);
    } catch (err: any) {
      setError(err instanceof Error ? err.message : "Investigation could not be completed.");
    } finally {
      setLoading(false);
    }
  };

  const handleSendChat = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!chatInput.trim() || chatLoading || (!selectedPaymentId && !incidentContext)) return;

    const userMsg = { role: "user", content: chatInput.trim() };
    const newMessages = [...chatMessages, userMsg];
    setChatMessages(newMessages);
    setChatInput("");
    setChatLoading(true);

    try {
      const res = await api.chatInvestigator(incidentContext ? null : selectedPaymentId || null, newMessages, userMsg.content, incidentContext?.id);
      setChatMessages([...newMessages, { role: "assistant", content: res.response, activity: { nodes: res.workflow_nodes || [], tools: res.tool_calls || [], tracing: res.langsmith_tracing_enabled === true, answerMode: res.answer_mode, model: [res.model_provider, res.model_name].filter(Boolean).join(" / "), fallbackReason: res.fallback_reason } }]);
    } catch (err: any) {
      setChatMessages([
        ...newMessages,
        { role: "assistant", content: `Error querying investigator: ${err.message}` },
      ]);
    } finally {
      setChatLoading(false);
    }
  };

  const selectedPayment = payments.find((p) => p.id === selectedPaymentId);

  return (
    <div className="space-y-8 max-w-7xl mx-auto animate-fadeIn pb-16">
      {/* Header */}
      <div className="flex flex-col md:flex-row md:items-center justify-between gap-4 pb-2">
        <div>
          <h1 className="font-display text-4xl font-bold tracking-tight text-ink">
            AI Investigation Hub
          </h1>
          <p className="text-base text-slate-600 mt-2">
            Investigates stored payment and incident records, lifecycle events, verified webhooks, and linked browser telemetry.
          </p>
        </div>
      </div>

      {contextLoading && !loading && <div role="status" className="glass-panel rounded-2xl border border-slate-200 p-6 text-sm text-slate-600">Loading payment and incident evidence…</div>}

      {/* Query Formulation Card */}
      <div className="glass-panel rounded-2xl p-6 border border-slate-800 space-y-4">
        <div className="grid grid-cols-1 md:grid-cols-12 gap-4">
          {/* Payment Selector */}
          <div className="md:col-span-5 space-y-1.5">
            <label className="text-xs text-slate-400">{incidentContext ? "Affected payment (incident context is active)" : "Investigation scope"}</label>
            <select
              value={selectedPaymentId}
              onChange={(e) => setSelectedPaymentId(e.target.value)}
              disabled={Boolean(incidentContext)}
              className="w-full bg-slate-900 border border-slate-800 rounded-lg p-2.5 text-xs text-ink focus:outline-none focus:border-cyan-500"
            >
              {!incidentContext && <option value="">All recent transactions (incident command)</option>}
              {payments.map((p) => (
                <option key={p.id} value={p.id}>
                  {p.status} - ${Number(p.amount).toFixed(2)} ({p.id.slice(0, 10)}... {p.failure_code || "Normal"})
                </option>
              ))}
            </select>
          </div>

          {/* Investigation Query */}
          <div className="md:col-span-7 space-y-1.5">
            <label className="text-xs text-slate-400">Investigation Prompt / Question</label>
            <div className="flex gap-2">
              <input
                type="text"
                value={question}
                onChange={(e) => setQuestion(e.target.value)}
                placeholder="Ask about one payment or recent fleet-wide failure patterns..."
                className="flex-1 bg-slate-900 border border-slate-800 rounded-lg px-3.5 py-2 text-xs text-ink focus:outline-none focus:border-cyan-500"
              />
              <button
                type="button"
                onClick={() => handleRunInvestigation()}
                disabled={loading}
                className="px-5 py-2 bg-cyan-500 hover:bg-cyan-400 text-onsolid font-bold text-xs rounded-lg transition-all duration-150 shadow-md shadow-cyan-500/20 flex items-center gap-1.5 shrink-0 disabled:opacity-50"
              >
                {loading ? <Loader2 className="w-4 h-4 animate-spin" /> : <Sparkles className="w-4 h-4" />}
                Investigate
              </button>
            </div>
          </div>
        </div>

        <div className="border-t border-slate-700 pt-3">
          <p className="mb-2 text-xs font-semibold text-slate-200">Suggested questions</p>
          <div className="flex flex-wrap gap-2">{promptSuggestions.map((suggestion) => <button key={suggestion} type="button" onClick={() => { setQuestion(suggestion); setSelectedPaymentId(""); }} className="rounded-lg border border-slate-600 bg-slate-800 px-3 py-2 text-left text-xs font-medium text-slate-100 shadow-sm hover:border-cyan-400 hover:bg-slate-700 focus-visible:outline focus-visible:outline-2 focus-visible:outline-cyan-400">{suggestion}</button>)}</div>
        </div>
        {error && <div role="alert" className="rounded-lg border border-rose-700 bg-rose-950 px-3 py-2 text-sm text-rose-300">{error}</div>}

        {incidentContext && <section aria-label="Incident investigation context" className="rounded-xl border border-blue-200 bg-blue-50 p-4 text-slate-800">
          <div className="flex flex-wrap items-start justify-between gap-3"><div><p className="text-[10px] font-semibold uppercase tracking-wider text-blue-700">Incident context · {incidentContext.severity} · {incidentContext.status}</p><h2 className="mt-1 text-sm font-bold">{incidentContext.title}</h2><p className="mt-1 text-xs text-slate-600">Rule: {incidentContext.detection_rule || "not recorded"} · {incidentContext.affected_payment_count} affected · {incidentContext.revenue_at_risk} {incidentContext.currency}</p></div><Link href={`/incidents/${incidentContext.id}`} className="text-xs font-semibold text-blue-700 hover:underline">Open incident record →</Link></div>
          <p className="mt-2 text-xs text-slate-600">Stored evidence: {incidentContext.root_cause || incidentContext.ai_summary || "No root cause summary is stored."}</p>
          <div className="mt-3 flex flex-wrap gap-2">{(incidentContext.affected_payments || []).map((payment) => <span key={payment.id} className="inline-flex flex-wrap items-center gap-1 rounded-md border border-blue-200 bg-white px-2 py-1 text-[11px]"><Link href={`/payments/${payment.id}`} className="font-mono text-blue-700 hover:underline">Payment {payment.id.slice(0, 10)}…</Link><span className="text-slate-500">{payment.status}</span>{payment.session_id && <Link href={`/sessions/${payment.session_id}`} className="text-blue-700 hover:underline">Session ↗</Link>}</span>)}</div>
        </section>}

        {/* Selected Payment Snapshot chip */}
        {selectedPayment && (
          <div className="flex flex-wrap items-center gap-3 pt-2 border-t border-slate-800/80 text-xs">
            <span className="text-slate-400 text-[11px]">Snapshot:</span>
            <span className="text-slate-200">{selectedPayment.paypal_order_id || "No Provider Order ID"}</span>
            <span className="text-slate-500">•</span>
            <span className="font-bold text-ink">${Number(selectedPayment.amount).toFixed(2)} {selectedPayment.currency}</span>
            <span className="text-slate-500">•</span>
            <span
              className={`px-2 py-0.5 rounded-full text-[10px] font-bold ${
                selectedPayment.status === "CAPTURED"
                  ? "bg-emerald-950 text-emerald-300 border border-emerald-800"
                  : selectedPayment.status === "CAPTURE_UNCERTAIN"
                  ? "bg-amber-950 text-amber-300 border border-amber-800"
                  : "bg-rose-950 text-rose-300 border border-rose-800"
              }`}
            >
              {selectedPayment.status}
            </span>
            <span className="text-slate-500">•</span>
            <span className="text-slate-400 text-[11px]">{selectedPayment.customer_ref}</span>
            <span className={`rounded-full border px-2 py-0.5 text-[10px] font-bold ${selectedPayment.source_mode === "SIMULATED" ? "border-amber-800 bg-amber-950 text-amber-300" : "border-emerald-800 bg-emerald-950 text-emerald-300"}`}>
              {selectedPayment.source_mode === "SIMULATED" ? "Simulated payment" : `${selectedPayment.source_mode.replace("PAYPAL_", "PayPal ")} payment`}
            </span>
          </div>
        )}
      </div>

      {/* Tool Activity Indicators if loading */}
      {loading && (
        <div className="glass-panel rounded-2xl p-8 border border-cyan-500/30 text-center space-y-4">
          <Loader2 className="w-8 h-8 text-cyan-400 animate-spin mx-auto" />
          <div className="space-y-1">
            <h3 className="text-sm font-bold text-ink">Running Cross-Signal Evidence Tools...</h3>
            <p className="text-xs text-slate-400">
              [1] Querying PayPal API facts → [2] Correlating webhooks → [3] Analyzing customer checkout session → [4] Benchmarking divergences
            </p>
          </div>
        </div>
      )}

      {/* Investigation Results */}
      {investigation && !loading && (
        <div className="grid grid-cols-1 lg:grid-cols-12 gap-8 items-start animate-fadeIn">
          {/* Main Structured Findings (7 cols) */}
          <div className={`${selectedPayment || incidentContext ? "lg:col-span-7" : "lg:col-span-12"} space-y-6`}>
            <div className="glass-panel rounded-2xl p-6 border border-cyan-500/20 glow-blue space-y-6">
              {/* Header */}
              <div className="flex items-center justify-between pb-4 border-b border-slate-800">
                <div>
                  <h2 className="text-base font-bold text-ink flex items-center gap-2">
                    <Brain className="w-5 h-5 text-cyan-400" />
                    Structured Diagnostic Findings
                  </h2>
                  <p className="text-xs text-slate-400">Validated against stored database facts</p>
                </div>
                <div className="flex items-center gap-3">
                  <span
                    className={`text-[10px] font-bold px-2.5 py-1 rounded-full uppercase ${
                      investigation.severity === "HIGH"
                        ? "bg-rose-950 text-rose-300 border border-rose-800"
                        : "bg-amber-950 text-amber-300 border border-amber-800"
                    }`}
                  >
                    {investigation.severity}
                  </span>
                  <span className="text-xs text-cyan-500 font-semibold">
                    Evidence confidence: {investigation.confidence >= 0.75 ? "strong" : investigation.confidence >= 0.5 ? "partial" : "limited"}
                  </span>
                </div>
              </div>

              <section aria-label="AI workflow activity" className="rounded-lg border border-slate-700 bg-slate-900/70 p-3 space-y-2">
                <div className="flex flex-wrap items-center justify-between gap-2 text-[10px]">
                  <span className="font-bold uppercase tracking-wide text-slate-300">Workflow: {investigation.execution_mode.replaceAll("_", " ")}</span>
                  <span className={investigation.langsmith_tracing_enabled ? "text-emerald-300" : "text-amber-300"}>
                    LangSmith tracing {investigation.langsmith_tracing_enabled ? "configured" : "not configured"}
                  </span>
                </div>
                <p className="text-[10px] text-slate-400">Nodes: {(investigation.workflow_nodes || []).join(" → ") || "No graph node details returned"}</p>
                <p className="text-[10px] text-slate-400">Tool calls: {(investigation.tool_calls || []).join(", ") || "No investigation tools called"}</p>
              </section>

              {/* Root cause */}
              <div className="space-y-1.5">
                <span className="text-[10px] uppercase text-slate-400 tracking-wider">Identified Root Cause</span>
                <div className="p-4 rounded-xl bg-slate-900/80 border border-slate-800 text-xs font-semibold text-ink leading-relaxed">
                  {investigation.root_cause}
                </div>
              </div>

              {/* Facts vs Inferences */}
              <div className="grid grid-cols-1 gap-4">
                <div className="space-y-2">
                  <span className="text-[10px] uppercase text-emerald-400 tracking-wider flex items-center gap-1">
                    <CheckCircle2 className="w-3.5 h-3.5" />
                    Verified Facts (From Payment & Provider Logs)
                  </span>
                  <ul className="space-y-1.5">
                    {investigation.facts.map((fact: any, idx: number) => (
                      <li key={idx} className="text-xs text-slate-300 flex items-start gap-2 bg-slate-950/40 p-2.5 rounded border border-slate-800">
                        <span className="text-emerald-400 font-bold">•</span>
                        <span>{fact}</span>
                      </li>
                    ))}
                  </ul>
                </div>

                <div className="space-y-2">
                  <span className="text-[10px] uppercase text-sky-400 tracking-wider flex items-center gap-1">
                    <Brain className="w-3.5 h-3.5" />
                    Logical Inferences
                  </span>
                  <ul className="space-y-1.5">
                    {investigation.inferences.map((inf: any, idx: number) => (
                      <li key={idx} className="text-xs text-slate-300 flex items-start gap-2 bg-slate-950/40 p-2.5 rounded border border-slate-800">
                        <span className="text-sky-400 font-bold">↳</span>
                        <span>{inf}</span>
                      </li>
                    ))}
                  </ul>
                </div>
              </div>

              {/* Recommendation */}
              <div className="p-4 rounded-xl bg-cyan-950/40 border border-cyan-800/80 space-y-1.5">
                <span className="text-[10px] uppercase text-cyan-400 font-bold block">
                  Recommended Next Action
                </span>
                <p className="text-xs text-cyan-200 font-medium leading-relaxed">
                  {investigation.recommendation}
                </p>
              </div>

              {/* Comparison Divergence if available */}
              {investigation.comparison_notes && (
                <div className="p-4 rounded-xl bg-indigo-950/30 border border-indigo-800/50 space-y-1">
                  <span className="text-[10px] uppercase text-indigo-400 font-bold block">
                    Benchmark Comparison vs Successful Payments
                  </span>
                  <p className="text-xs text-indigo-200 leading-relaxed">
                    {investigation.comparison_notes}
                  </p>
                </div>
              )}
            </div>
          </div>

          {/* Follow-up chat is payment/incident scoped; fleet questions run through Incident Command above. */}
          {(selectedPayment || incidentContext) && <div className="lg:col-span-5 min-w-0 self-stretch">
            <section aria-label="AI Investigator follow-up chat" className="investigator-chat light-scale flex h-[520px] min-h-0 flex-col overflow-hidden rounded-2xl border border-slate-200 bg-white text-slate-800 shadow-lg shadow-slate-900/5 lg:sticky lg:top-[84px] lg:h-[calc(100vh-112px)] lg:min-h-[420px]">
              <div className="flex shrink-0 items-center justify-between gap-3 border-b border-slate-200 px-5 py-4">
                <div>
                  <h3 className="flex items-center gap-2 text-sm font-bold text-slate-900">
                    <Brain className="h-4 w-4 text-blue-600" />
                    PayTrace Investigator
                  </h3>
                  <p className="mt-1 text-[11px] text-slate-600">Continue with the same payment or incident evidence.</p>
                </div>
                <span className="rounded-full border border-blue-200 bg-blue-50 px-2 py-1 text-[9px] font-semibold tracking-wide text-blue-800">EVIDENCE-GROUNDED</span>
              </div>

              <div ref={chatThreadRef} role="log" aria-live="polite" aria-label="Conversation" className="min-h-0 flex-1 space-y-4 overflow-y-auto overscroll-contain bg-slate-50/70 p-4">
                {chatMessages.length === 0 ? (
                  <div className="space-y-2 py-8 text-center text-sm text-slate-700">
                    <HelpCircle className="mx-auto h-7 w-7 text-blue-600" />
                  <p>Have specific questions about {incidentContext ? "this incident and its linked records" : "this payment outcome"}?</p>
                    <p className="text-xs font-medium text-blue-700">Try: &ldquo;Why shouldn&apos;t I retry right now?&rdquo;</p>
                  </div>
                ) : (
                  chatMessages.map((msg, i) => (
                    <div
                      key={i}
                      className={`max-w-[94%] break-words rounded-xl border px-3.5 py-3 text-[13px] leading-6 ${
                        msg.role === "user"
                        ? "ml-auto border-blue-200 bg-blue-700 text-white"
                          : "mr-auto border-slate-200 bg-white text-slate-800 shadow-sm"
                      }`}
                    >
                      <span className={`mb-1 block text-[9px] font-semibold tracking-wide ${msg.role === "user" ? "text-blue-100" : "text-slate-500"}`}>
                        {msg.role === "user" ? "YOU" : "PAYTRACE INVESTIGATOR"}
                      </span>
                      <ChatMarkdown content={msg.content} />
                      {msg.activity && (
                        <div className={`mt-3 space-y-1 border-t pt-2 text-[10px] ${msg.role === "user" ? "border-white/20 text-blue-100" : "border-slate-200 text-slate-600"}`}>
                          <p>Workflow nodes: {msg.activity.nodes.join(" → ") || "No graph run for this answer"}</p>
                          <p>Answer: {msg.activity.answerMode}{msg.activity.model ? ` · ${msg.activity.model}` : ""} · LangSmith tracing {msg.activity.tracing ? "enabled" : "disabled"}</p>
                          <p>Tools: {msg.activity.tools.join(", ") || "none"}</p>
                          {msg.activity.fallbackReason && <p className="text-amber-700">Fallback reason: {msg.activity.fallbackReason}</p>}
                        </div>
                      )}
                    </div>
                  ))
                )}
                {chatLoading && (
                  <div role="status" className="flex items-center gap-2 rounded-lg border border-blue-200 bg-white p-3 text-xs text-blue-800">
                    <Loader2 className="w-3.5 h-3.5 animate-spin" />
                    Consulting payment records...
                  </div>
                )}
              </div>

              <form onSubmit={handleSendChat} className="flex shrink-0 items-end gap-2 border-t border-slate-200 bg-white p-4">
                <textarea
                  rows={1}
                  aria-label="Ask a follow-up question"
                  placeholder="Ask a follow-up about this evidence…"
                  value={chatInput}
                  onChange={(e) => setChatInput(e.target.value)}
                  onKeyDown={(event) => {
                    if (event.key === "Enter" && !event.shiftKey) {
                      event.preventDefault();
                      event.currentTarget.form?.requestSubmit();
                    }
                  }}
                  className="min-h-12 min-w-0 flex-1 resize-none rounded-xl border border-slate-300 bg-white px-3.5 py-3 text-sm leading-5 text-slate-900 placeholder:text-slate-500 focus:border-blue-600 focus:outline-none focus:ring-2 focus:ring-blue-600/20"
                />
                <button
                  type="submit"
                  aria-label="Send follow-up question"
                  disabled={chatLoading || !chatInput.trim() || (!selectedPaymentId && !incidentContext)}
                  className="inline-flex h-12 w-12 shrink-0 items-center justify-center rounded-xl bg-blue-700 text-white transition-colors hover:bg-blue-800 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-blue-700 disabled:cursor-not-allowed disabled:opacity-50"
                >
                  <Send className="w-3.5 h-3.5" />
                </button>
              </form>
            </section>
          </div>}
        </div>
      )}
    </div>
  );
}
