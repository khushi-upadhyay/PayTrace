"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { api, ApprovalTicketItem } from "@/lib/api";
import {
  ShieldCheck,
  CheckCircle2,
  XCircle,
  Loader2,
  Clock,
  DollarSign,
  AlertTriangle,
  ArrowRight,
  UserCheck,
} from "lucide-react";

export default function ApprovalsPage() {
  const [tickets, setTickets] = useState<ApprovalTicketItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [decidingId, setDecidingId] = useState<string | null>(null);

  const fetchTickets = async () => {
    try {
      setLoading(true);
      const data = await api.getApprovals();
      setTickets(data);
    } catch (err: any) {
      console.error("Failed to fetch approvals:", err);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchTickets();
  }, []);

  const handleDecision = async (ticketId: string, decision: "APPROVED" | "DENIED") => {
    if (!confirm(`Are you sure you want to mark this proposal as ${decision}?`)) return;

    try {
      setDecidingId(ticketId);
      await api.decideApproval(ticketId, decision, `Actioned by Operator at ${new Date().toISOString()}`);
      await fetchTickets();
    } catch (err: any) {
      alert(`Decision error: ${err.message}`);
    } finally {
      setDecidingId(null);
    }
  };

  const pendingTickets = tickets.filter((t) => t.status === "PENDING");
  const historicalTickets = tickets.filter((t) => t.status !== "PENDING");

  return (
    <div className="space-y-8 max-w-7xl mx-auto animate-fadeIn pb-16">
      {/* Header */}
      <div className="flex flex-col md:flex-row md:items-center justify-between gap-4 pb-2 border-b border-slate-800">
        <div>
          <h1 className="text-2xl font-bold tracking-tight text-white flex items-center gap-2.5">
            <ShieldCheck className="w-6 h-6 text-purple-400" />
            Human Approval Inbox
          </h1>
          <p className="text-xs text-slate-400 mt-1">
            Enforces policy checks before executing sensitive financial actions like customer refunds.
          </p>
        </div>
        <div className="flex items-center gap-3">
          <span className="text-xs font-mono text-purple-300 bg-purple-950/80 border border-purple-800 px-3 py-1.5 rounded-lg">
            Pending Review: <span className="font-bold">{pendingTickets.length}</span>
          </span>
        </div>
      </div>

      {/* Pending Approvals Section */}
      <div className="space-y-4">
        <h2 className="text-sm font-bold text-white uppercase font-mono tracking-wider flex items-center gap-2">
          <Clock className="w-4 h-4 text-amber-400" />
          Pending Authorization ({pendingTickets.length})
        </h2>

        {loading ? (
          <div className="flex items-center justify-center py-12 space-y-2">
            <Loader2 className="w-6 h-6 text-cyan-400 animate-spin" />
          </div>
        ) : pendingTickets.length === 0 ? (
          <div className="glass-panel p-8 rounded-xl text-center text-xs text-slate-500 border border-slate-800">
            No pending actions awaiting approval. You can propose a refund from any payment detail page.
          </div>
        ) : (
          <div className="grid grid-cols-1 gap-4">
            {pendingTickets.map((t) => (
              <div
                key={t.id}
                className="glass-panel rounded-2xl p-6 border border-purple-500/30 bg-purple-950/10 space-y-4 glow-blue"
              >
                <div className="flex flex-col lg:flex-row lg:items-center justify-between gap-4">
                  <div className="space-y-2">
                    <div className="flex items-center gap-3">
                      <span className="px-2.5 py-0.5 rounded-full text-[10px] font-bold font-mono bg-purple-950 text-purple-300 border border-purple-800">
                        {t.action_type} REQUEST
                      </span>
                      <span className="text-xs font-mono text-slate-400">
                        Ticket ID: <span className="text-white">{t.id.slice(0, 8)}...</span>
                      </span>
                    </div>

                    <h3 className="text-base font-bold text-white">
                      Authorize Refund of ${Number(t.amount || 0).toFixed(2)} {t.currency}
                    </h3>

                    <p className="text-xs text-slate-300 leading-relaxed">
                      <strong>Policy Justification:</strong> {t.reason}
                    </p>

                    <div className="flex items-center gap-4 text-xs text-slate-400 pt-1">
                      <span>
                        Target Payment:{" "}
                        <Link href={`/payments/${t.payment_id}`} className="text-cyan-400 hover:underline font-mono">
                          {t.payment_id.slice(0, 12)}...
                        </Link>
                      </span>
                      <span>•</span>
                      <span>Requested by: <strong className="text-slate-200">{t.requested_by}</strong></span>
                    </div>
                  </div>

                  {/* Approve / Deny Buttons */}
                  <div className="flex items-center gap-3 shrink-0">
                    <button
                      onClick={() => handleDecision(t.id, "DENIED")}
                      disabled={decidingId === t.id}
                      className="px-4 py-2 rounded-lg bg-slate-900 border border-slate-700 hover:bg-slate-800 text-slate-300 text-xs font-semibold transition-colors flex items-center gap-1.5 disabled:opacity-50"
                    >
                      <XCircle className="w-3.5 h-3.5 text-rose-400" />
                      Deny
                    </button>

                    <button
                      onClick={() => handleDecision(t.id, "APPROVED")}
                      disabled={decidingId === t.id}
                      className="px-4 py-2 rounded-lg bg-emerald-600 hover:bg-emerald-500 text-slate-950 text-xs font-bold transition-colors flex items-center gap-1.5 shadow-md shadow-emerald-600/20 disabled:opacity-50"
                    >
                      {decidingId === t.id ? (
                        <Loader2 className="w-3.5 h-3.5 animate-spin" />
                      ) : (
                        <CheckCircle2 className="w-3.5 h-3.5" />
                      )}
                      Authorize & Execute Refund
                    </button>
                  </div>
                </div>
              </div>
            ))}
          </div>
        )}
      </div>

      {/* Historical Audit Trail Section */}
      <div className="space-y-4">
        <h2 className="text-sm font-bold text-white uppercase font-mono tracking-wider flex items-center gap-2">
          <UserCheck className="w-4 h-4 text-slate-400" />
          Audit Trail ({historicalTickets.length})
        </h2>

        {historicalTickets.length === 0 ? (
          <div className="glass-panel p-6 rounded-xl text-center text-xs text-slate-500 border border-slate-800">
            No historical decisions recorded yet.
          </div>
        ) : (
          <div className="glass-panel rounded-2xl border border-slate-800 overflow-hidden">
            <div className="overflow-x-auto">
              <table className="w-full text-left text-xs">
                <thead className="bg-slate-900/60 border-b border-slate-800 text-slate-400 font-mono uppercase text-[10px]">
                  <tr>
                    <th className="px-5 py-3">Ticket ID</th>
                    <th className="px-5 py-3">Action</th>
                    <th className="px-5 py-3">Amount</th>
                    <th className="px-5 py-3">Status</th>
                    <th className="px-5 py-3">Decided By</th>
                    <th className="px-5 py-3">Decided At</th>
                    <th className="px-5 py-3 text-right">Payment</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-slate-800/80">
                  {historicalTickets.map((t) => (
                    <tr key={t.id} className="hover:bg-slate-900/40 transition-colors">
                      <td className="px-5 py-3.5 font-mono text-slate-300 font-medium">
                        {t.id.slice(0, 10)}...
                      </td>
                      <td className="px-5 py-3.5 font-bold text-white">
                        {t.action_type}
                      </td>
                      <td className="px-5 py-3.5 text-slate-200 font-semibold">
                        ${Number(t.amount || 0).toFixed(2)} {t.currency}
                      </td>
                      <td className="px-5 py-3.5">
                        <span
                          className={`inline-flex items-center px-2 py-0.5 rounded-full text-[10px] font-bold ${
                            t.status === "EXECUTED" || t.status === "APPROVED"
                              ? "bg-emerald-950 text-emerald-300 border border-emerald-800"
                              : "bg-rose-950 text-rose-300 border border-rose-800"
                          }`}
                        >
                          {t.status}
                        </span>
                      </td>
                      <td className="px-5 py-3.5 text-slate-300 font-medium">
                        {t.decided_by || "Operator"}
                      </td>
                      <td className="px-5 py-3.5 text-slate-500 font-mono text-[11px]">
                        {t.decided_at ? new Date(t.decided_at).toLocaleString() : "—"}
                      </td>
                      <td className="px-5 py-3.5 text-right">
                        <Link
                          href={`/payments/${t.payment_id}`}
                          className="text-cyan-400 hover:underline text-[11px] inline-flex items-center gap-1 font-mono"
                        >
                          Inspect
                          <ArrowRight className="w-3 h-3" />
                        </Link>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
