"use client";

import { useEffect, useState } from "react";
import { api, PaymentItem, AIInvestigationData } from "@/lib/api";
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

export default function InvestigateHubPage() {
  const [payments, setPayments] = useState<PaymentItem[]>([]);
  const [selectedPaymentId, setSelectedPaymentId] = useState<string>("");
  const [question, setQuestion] = useState("Investigate payment outcome, uncertainty, and root cause");
  const [investigation, setInvestigation] = useState<AIInvestigationData | null>(null);
  const [loading, setLoading] = useState(false);

  // Chat follow-up
  const [chatMessages, setChatMessages] = useState<Array<{ role: string; content: string }>>([]);
  const [chatInput, setChatInput] = useState("");
  const [chatLoading, setChatLoading] = useState(false);

  useEffect(() => {
    api.getPayments({ page_size: 30 }).then((res) => {
      setPayments(res.items);
      if (res.items.length > 0) {
        // Default to uncertain or failed payment if available
        const preferred = res.items.find(
          (p) => p.status === "CAPTURE_UNCERTAIN" || p.status === "DENIED"
        ) || res.items[0];
        setSelectedPaymentId(preferred.id);
      }
    });
  }, []);

  const handleRunInvestigation = async (e?: React.FormEvent) => {
    if (e) e.preventDefault();
    if (!selectedPaymentId) return;

    try {
      setLoading(true);
      setChatMessages([]);
      const res = await api.investigatePayment(selectedPaymentId, question);
      setInvestigation(res);
    } catch (err: any) {
      alert(`Investigation failed: ${err.message}`);
    } finally {
      setLoading(false);
    }
  };

  const handleSendChat = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!chatInput.trim() || chatLoading || !selectedPaymentId) return;

    const userMsg = { role: "user", content: chatInput.trim() };
    const newMessages = [...chatMessages, userMsg];
    setChatMessages(newMessages);
    setChatInput("");
    setChatLoading(true);

    try {
      const res = await api.chatInvestigator(selectedPaymentId, newMessages, userMsg.content);
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

  const selectedPayment = payments.find((p) => p.id === selectedPaymentId);

  return (
    <div className="space-y-8 max-w-7xl mx-auto animate-fadeIn pb-16">
      {/* Header */}
      <div className="flex flex-col md:flex-row md:items-center justify-between gap-4 pb-2">
        <div>
          <h1 className="font-display text-4xl font-bold tracking-tight text-black">
            AI Investigation Hub
          </h1>
          <p className="text-base text-black/70 mt-2">
            Autonomous root-cause investigator grounded in PayPal APIs, webhooks, and customer telemetry.
          </p>
        </div>
      </div>

      {/* Query Formulation Card */}
      <div className="glass-panel rounded-2xl p-6 border border-slate-800 space-y-4">
        <div className="grid grid-cols-1 md:grid-cols-12 gap-4">
          {/* Payment Selector */}
          <div className="md:col-span-5 space-y-1.5">
            <label className="text-xs text-slate-400">Select Target Payment</label>
            <select
              value={selectedPaymentId}
              onChange={(e) => setSelectedPaymentId(e.target.value)}
              className="w-full bg-slate-900 border border-slate-800 rounded-lg p-2.5 text-xs text-ink focus:outline-none focus:border-cyan-500"
            >
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
                placeholder="Ask investigator to explain root cause..."
                className="flex-1 bg-slate-900 border border-slate-800 rounded-lg px-3.5 py-2 text-xs text-ink focus:outline-none focus:border-cyan-500"
              />
              <button
                type="button"
                onClick={() => handleRunInvestigation()}
                disabled={loading || !selectedPaymentId}
                className="px-5 py-2 bg-cyan-500 hover:bg-cyan-400 text-onsolid font-bold text-xs rounded-lg transition-all duration-150 shadow-md shadow-cyan-500/20 flex items-center gap-1.5 shrink-0 disabled:opacity-50"
              >
                {loading ? <Loader2 className="w-4 h-4 animate-spin" /> : <Sparkles className="w-4 h-4" />}
                Investigate
              </button>
            </div>
          </div>
        </div>

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
          <div className="lg:col-span-7 space-y-6">
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
                  <span className="text-xs text-cyan-400 font-bold">
                    {(investigation.confidence * 100).toFixed(0)}% Confidence
                  </span>
                </div>
              </div>

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
                    {investigation.facts.map((fact, idx) => (
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
                    {investigation.inferences.map((inf, idx) => (
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

          {/* Interactive Chat Thread (5 cols) */}
          <div className="lg:col-span-5 space-y-6">
            <div className="glass-panel rounded-2xl p-6 border border-slate-800 space-y-4">
              <div className="flex items-center justify-between pb-3 border-b border-slate-800">
                <h3 className="text-sm font-bold text-ink flex items-center gap-2">
                  <Brain className="w-4 h-4 text-cyan-400" />
                  Interactive Investigation Chat
                </h3>
                <span className="text-[10px] text-slate-500">EVIDENCE-GROUNDED</span>
              </div>

              <div className="space-y-3 max-h-80 overflow-y-auto pr-1">
                {chatMessages.length === 0 ? (
                  <div className="text-center py-8 text-xs text-slate-500 space-y-2">
                    <HelpCircle className="w-6 h-6 mx-auto text-slate-600" />
                    <p>Have specific questions about this payment outcome?</p>
                    <p className="text-[11px] text-cyan-400">Try: &ldquo;Why shouldn&apos;t I retry right now?&rdquo;</p>
                  </div>
                ) : (
                  chatMessages.map((msg, i) => (
                    <div
                      key={i}
                      className={`p-3 rounded-lg text-xs leading-relaxed ${
                        msg.role === "user"
                          ? "bg-slate-800 text-ink ml-6"
                          : "bg-cyan-950/60 border border-cyan-800/60 text-cyan-100 mr-6"
                      }`}
                    >
                      <span className="text-[9px] text-slate-400 block mb-1">
                        {msg.role === "user" ? "OPERATOR" : "INVESTIGATOR"}
                      </span>
                      {msg.content}
                    </div>
                  ))
                )}
                {chatLoading && (
                  <div className="p-3 rounded-lg bg-cyan-950/40 text-xs text-cyan-300 flex items-center gap-2">
                    <Loader2 className="w-3.5 h-3.5 animate-spin" />
                    Consulting payment records...
                  </div>
                )}
              </div>

              <form onSubmit={handleSendChat} className="flex gap-2 pt-2 border-t border-slate-800">
                <input
                  type="text"
                  placeholder="Ask a question..."
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
          </div>
        </div>
      )}
    </div>
  );
}
