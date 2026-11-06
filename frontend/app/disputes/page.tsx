"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { api, DisputeItem } from "@/lib/api";
import { Scale, Loader2, ArrowRight, ShieldCheck, Clock } from "lucide-react";

const STATUS_FILTERS = ["ALL", "OPEN", "UNDER_REVIEW", "RESOLVED_BUYER_FAVOUR", "RESOLVED_SELLER_FAVOUR", "CLOSED"];

const STATUS_STYLE: Record<string, string> = {
  OPEN: "bg-amber-950 text-amber-300 border border-amber-800",
  UNDER_REVIEW: "bg-sky-950 text-sky-300 border border-sky-800",
  RESOLVED_BUYER_FAVOUR: "bg-purple-950 text-purple-300 border border-purple-800",
  RESOLVED_SELLER_FAVOUR: "bg-emerald-950 text-emerald-300 border border-emerald-800",
  CLOSED: "bg-slate-800 text-slate-300 border border-slate-700",
};

export default function DisputesPage() {
  const [disputes, setDisputes] = useState<DisputeItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [statusFilter, setStatusFilter] = useState("ALL");

  const fetchDisputes = async (status: string) => {
    try {
      setLoading(true);
      setLoadError(null);
      const res = await api.getDisputes(status === "ALL" ? undefined : status);
      setDisputes(res.items);
    } catch (err: any) {
      setLoadError(err.message || "Unable to load disputes from the backend.");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchDisputes(statusFilter);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [statusFilter]);

  const openCount = disputes.filter((d) => d.status === "OPEN" || d.status === "UNDER_REVIEW").length;

  return (
    <div className="space-y-6 max-w-7xl mx-auto animate-fadeIn">
      <div className="flex flex-col md:flex-row md:items-center justify-between gap-4 pb-2">
        <div>
          <h1 className="font-display text-4xl font-bold tracking-tight text-black">Disputes <span className="ml-2 align-middle rounded-full border border-amber-500/50 bg-amber-950 px-2 py-1 text-[10px] font-bold uppercase tracking-wide text-amber-300">Experimental</span></h1>
          <p className="text-base text-black/70 mt-2">
            Every buyer dispute linked to a payment, with response deadlines and resolution state.
            This sandbox simulates disputes locally — none of these call PayPal&apos;s live Disputes API.
          </p>
        </div>
        <div className="text-xs text-slate-400 bg-slate-900 border border-slate-800 px-3 py-1.5 rounded-lg">
          Needs Response: <span className="text-amber-400 font-bold">{openCount}</span>
        </div>
      </div>

      <div className="flex flex-wrap gap-2">
        {STATUS_FILTERS.map((s) => (
          <button
            key={s}
            onClick={() => setStatusFilter(s)}
            className={`px-3 py-1.5 rounded-lg text-xs font-semibold border transition-colors ${
              statusFilter === s
                ? "bg-cyan-500 border-cyan-500 text-onsolid"
                : "bg-slate-900 border-slate-800 text-slate-300 hover:border-slate-700"
            }`}
          >
            {s.replace(/_/g, " ")}
          </button>
        ))}
      </div>

      {loading ? (
        <div className="flex flex-col items-center justify-center py-20 space-y-3">
          <Loader2 className="w-8 h-8 text-cyan-400 animate-spin" />
          <span className="text-xs text-slate-400">Loading disputes...</span>
        </div>
      ) : loadError ? (
        <div role="alert" className="rounded-xl border border-rose-500/30 bg-rose-950/20 p-6 text-center">
          <p className="text-sm font-semibold text-rose-200">Dispute data is unavailable</p>
          <p className="mt-2 text-xs text-slate-400">{loadError}</p>
          <button onClick={() => fetchDisputes(statusFilter)} className="mt-3 rounded-lg bg-paypal-navy px-3 py-2 text-xs text-onsolid transition-colors duration-150 hover:bg-paypal-blue">Retry</button>
        </div>
      ) : disputes.length === 0 ? (
        <div className="glass-panel p-12 rounded-xl text-center space-y-3 border border-slate-800">
          <ShieldCheck className="w-10 h-10 text-emerald-400 mx-auto" />
          <h3 className="text-base font-bold text-ink">No disputes in this state</h3>
          <p className="text-xs text-slate-400 max-w-md mx-auto">
            Open one from a captured payment&apos;s detail page via &ldquo;Simulate Dispute&rdquo; to exercise this workflow.
          </p>
        </div>
      ) : (
        <div className="grid grid-cols-1 gap-4">
          {disputes.map((d) => (
            <div key={d.id} className="glass-panel rounded-2xl p-6 border border-slate-800 hover:border-slate-700 transition-colors duration-150">
              <div className="flex flex-col lg:flex-row lg:items-center justify-between gap-4">
                <div className="space-y-2">
                  <div className="flex items-center gap-3 flex-wrap">
                    <span className={`text-[10px] font-bold px-2.5 py-1 rounded-full uppercase tracking-wider ${STATUS_STYLE[d.status] || "bg-slate-800 text-slate-300"}`}>
                      {d.status.replace(/_/g, " ")}
                    </span>
                    <span className="text-xs text-slate-500 font-mono">{d.paypal_dispute_id}</span>
                    {d.is_simulated && (
                      <span className="text-[10px] text-amber-400 border border-amber-800/60 bg-amber-950/30 px-1.5 py-0.5 rounded">SIMULATED</span>
                    )}
                  </div>
                  <p className="text-sm text-ink font-semibold">
                    {d.reason.replace(/_/g, " ")} — ${Number(d.amount).toFixed(2)} {d.currency}
                  </p>
                  {d.buyer_statement && <p className="text-xs text-slate-400 italic max-w-xl">&ldquo;{d.buyer_statement}&rdquo;</p>}
                  {(d.status === "OPEN" || d.status === "UNDER_REVIEW") && d.response_due_by && (
                    <p className="text-[11px] text-amber-400 flex items-center gap-1">
                      <Clock className="w-3 h-3" /> Respond by {new Date(d.response_due_by).toLocaleDateString()}
                    </p>
                  )}
                </div>
                <Link
                  href={`/payments/${d.payment_id}`}
                  className="px-4 py-2 rounded-lg bg-cyan-500 hover:bg-cyan-400 text-onsolid text-xs font-bold transition-colors inline-flex items-center gap-1.5 shrink-0"
                >
                  <Scale className="w-3.5 h-3.5" />
                  Open Payment
                  <ArrowRight className="w-3.5 h-3.5" />
                </Link>
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
