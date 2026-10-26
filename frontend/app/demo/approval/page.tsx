"use client";

import { useState } from "react";
import { api } from "@/lib/api";
import { AlertTriangle, CheckCircle2, Loader2 } from "lucide-react";

type ReturnRoute = "checkout" | "shelfswipe";
type DemoApprovalProps = {
  searchParams: { token?: string; return_to?: string };
};

export default function DemoApprovalPage({ searchParams }: DemoApprovalProps) {
  const orderId = searchParams.token || null;
  const returnRoute: ReturnRoute = searchParams.return_to === "shelfswipe" ? "shelfswipe" : "checkout";
  const [processing, setProcessing] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const returnToCheckout = (status: "approved" | "cancelled") => {
    if (!orderId) return;
    window.location.assign(`/${returnRoute}?status=${status}&token=${encodeURIComponent(orderId)}`);
  };

  const approveDemoOrder = async () => {
    if (!orderId) return;
    setProcessing(true);
    setError(null);
    try {
      await api.approveMockOrder(orderId);
      returnToCheckout("approved");
    } catch (err: any) {
      setError(err.message || "Unable to approve this simulated order.");
      setProcessing(false);
    }
  };

  return (
    <main className="max-w-xl mx-auto mt-12 glass-panel rounded-2xl p-8 border border-slate-800 space-y-6 text-center">
      <div className="mx-auto w-12 h-12 rounded-full bg-amber-500/10 flex items-center justify-center">
        <AlertTriangle className="w-6 h-6 text-amber-400" />
      </div>
      <div className="space-y-2">
        <h1 className="text-xl font-bold text-white">Simulated Buyer Approval</h1>
        <p className="text-sm text-slate-300">This credential-free demo does not contact PayPal or move money. Continue to mark the sample order approved, or cancel it.</p>
        {orderId && <p className="text-xs text-slate-500 font-mono">Order: {orderId}</p>}
      </div>
      {error && <p role="alert" className="text-sm text-rose-300">{error}</p>}
      {!orderId && <p role="alert" className="text-sm text-rose-300">This approval link does not contain an order ID.</p>}
      <div className="flex flex-col sm:flex-row gap-3 justify-center">
        <button
          type="button"
          onClick={approveDemoOrder}
          disabled={!orderId || processing}
          className="px-5 py-3 rounded-xl bg-cyan-500 hover:bg-cyan-400 disabled:opacity-50 text-slate-950 text-sm font-bold inline-flex items-center justify-center gap-2"
        >
          {processing ? <Loader2 className="w-4 h-4 animate-spin" /> : <CheckCircle2 className="w-4 h-4" />}
          Simulate Buyer Approval
        </button>
        <button
          type="button"
          onClick={() => returnToCheckout("cancelled")}
          disabled={!orderId || processing}
          className="px-5 py-3 rounded-xl bg-slate-900 border border-slate-700 hover:bg-slate-800 disabled:opacity-50 text-slate-200 text-sm font-semibold"
        >
          Cancel Order
        </button>
      </div>
    </main>
  );
}
