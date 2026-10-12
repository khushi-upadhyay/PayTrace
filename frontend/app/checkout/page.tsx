"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import Link from "next/link";
import { api } from "@/lib/api";
import {
  ShoppingCart,
  CheckCircle2,
  AlertTriangle,
  Loader2,
  Lock,
  ArrowRight,
  ShieldAlert,
  Zap,
  CreditCard,
  Video,
} from "lucide-react";

const PRODUCTS = [
  { id: "p1", name: "Enterprise Observability Plan", price: 189.99, desc: "Full cluster tracing, unlimited AI investigations" },
  { id: "p2", name: "Developer Cloud License", price: 49.99, desc: "Standard sandbox monitoring and webhook validation" },
  { id: "p3", name: "Telemetry Starter Pack", price: 25.00, desc: "Single application checkout tracer" },
];

export default function CheckoutDemoPage() {
  const router = useRouter();
  const [selectedProduct, setSelectedProduct] = useState(PRODUCTS[0]);
  const [scenario, setScenario] = useState("normal"); // "normal", "timeout_before_response", "capture_denied"
  const [buyerEmail, setBuyerEmail] = useState("sandbox-buyer@paytrace.dev");

  const [processing, setProcessing] = useState(false);
  const [result, setResult] = useState<any | null>(null);

  const handleCheckout = async (e: React.FormEvent) => {
    e.preventDefault();
    try {
      setProcessing(true);
      setResult(null);

      // 1. Create Order via FastAPI
      const orderRes = await api.createOrder({
        amount: selectedProduct.price,
        customer_ref: buyerEmail,
        simulate_scenario: scenario === "normal" ? undefined : scenario,
      });

      // 2. Perform Capture (simulating buyer approval step)
      const capRes = await api.captureOrder(
        orderRes.paypal_order_id,
        scenario === "timeout_before_response"
      );

      setResult({
        payment_id: capRes.payment_id,
        order_id: capRes.paypal_order_id,
        capture_id: capRes.paypal_capture_id,
        status: capRes.status,
        failure_code: capRes.failure_code,
        failure_reason: capRes.failure_reason,
        reconciliation_required: capRes.reconciliation_required,
      });
    } catch (err: any) {
      alert(`Checkout failed: ${err.message}`);
    } finally {
      setProcessing(false);
    }
  };

  return (
    <div className="space-y-8 max-w-4xl mx-auto animate-fadeIn pb-16">
      {/* Header */}
      <div className="text-center space-y-2 pb-4 border-b border-slate-800">
        <h1 className="text-2xl font-bold tracking-tight text-white flex items-center justify-center gap-2.5">
          <ShoppingCart className="w-6 h-6 text-cyan-400" />
          PayPal Sandbox Demo Checkout
        </h1>
        <p className="text-xs text-slate-400 max-w-lg mx-auto">
          Test real PayPal Sandbox orders or trigger controlled timeout scenarios to verify
          PayTrace&apos;s cross-signal detection and duplicate prevention guardrails.
        </p>
      </div>

      {/* Session Recording Privacy Notice */}
      <div className="p-3.5 rounded-xl bg-slate-900/60 border border-slate-800 flex items-center justify-between text-xs text-slate-400">
        <div className="flex items-center gap-2">
          <Video className="w-4 h-4 text-emerald-400" />
          <span>Session telemetry active: Form inputs and cards masked client-side before storage.</span>
        </div>
        <span className="text-[10px] font-mono text-emerald-400 bg-emerald-950 px-2 py-0.5 rounded border border-emerald-800">
          PRIVACY MASKING ON
        </span>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-12 gap-8">
        {/* Left: Product & Scenario Selector (7 cols) */}
        <div className="md:col-span-7 space-y-6">
          {/* Product Selector */}
          <div className="glass-panel rounded-2xl p-6 border border-slate-800 space-y-4">
            <h2 className="text-sm font-bold text-white uppercase font-mono tracking-wider">
              1. Select Demo Item
            </h2>
            <div className="space-y-2.5">
              {PRODUCTS.map((prod) => (
                <div
                  key={prod.id}
                  onClick={() => setSelectedProduct(prod)}
                  className={`p-4 rounded-xl border cursor-pointer transition-all ${
                    selectedProduct.id === prod.id
                      ? "border-cyan-500 bg-cyan-950/20 text-white shadow-sm shadow-cyan-500/10"
                      : "border-slate-800 bg-slate-900/40 text-slate-300 hover:border-slate-700"
                  }`}
                >
                  <div className="flex items-center justify-between">
                    <span className="text-xs font-bold">{prod.name}</span>
                    <span className="text-sm font-extrabold text-cyan-400">${prod.price.toFixed(2)}</span>
                  </div>
                  <p className="text-[11px] text-slate-400 mt-1">{prod.desc}</p>
                </div>
              ))}
            </div>
          </div>

          {/* Scenario Trigger Mode */}
          <div className="glass-panel rounded-2xl p-6 border border-slate-800 space-y-4">
            <h2 className="text-sm font-bold text-white uppercase font-mono tracking-wider flex items-center gap-2">
              <Zap className="w-4 h-4 text-amber-400" />
              2. Choose Test Scenario
            </h2>
            <div className="space-y-2.5">
              <label className="flex items-start gap-3 p-3.5 rounded-xl border border-slate-800 bg-slate-900/40 cursor-pointer hover:border-slate-700">
                <input
                  type="radio"
                  name="scenario"
                  value="normal"
                  checked={scenario === "normal"}
                  onChange={() => setScenario("normal")}
                  className="mt-1 text-cyan-500"
                />
                <div>
                  <span className="text-xs font-bold text-white block">Standard Successful Payment</span>
                  <span className="text-[11px] text-slate-400">Order created, approved, and captured normally.</span>
                </div>
              </label>

              <label className="flex items-start gap-3 p-3.5 rounded-xl border border-amber-500/30 bg-amber-950/10 cursor-pointer hover:border-amber-500/50">
                <input
                  type="radio"
                  name="scenario"
                  value="timeout_before_response"
                  checked={scenario === "timeout_before_response"}
                  onChange={() => setScenario("timeout_before_response")}
                  className="mt-1 text-amber-500"
                />
                <div>
                  <span className="text-xs font-bold text-amber-200 block">
                    Merchant Backend Timeout / Ambiguous Capture State (Recommended Demo)
                  </span>
                  <span className="text-[11px] text-amber-300/80">
                    PayPal captures order, but merchant times out before receiving the HTTP response.
                    PayTrace halts blind retry to prevent duplicate charges.
                  </span>
                </div>
              </label>

              <label className="flex items-start gap-3 p-3.5 rounded-xl border border-slate-800 bg-slate-900/40 cursor-pointer hover:border-slate-700">
                <input
                  type="radio"
                  name="scenario"
                  value="capture_denied"
                  checked={scenario === "capture_denied"}
                  onChange={() => setScenario("capture_denied")}
                  className="mt-1 text-rose-500"
                />
                <div>
                  <span className="text-xs font-bold text-white block">Card Instrument Declined</span>
                  <span className="text-[11px] text-slate-400">Simulates buyer bank decline (INSTRUMENT_DECLINED).</span>
                </div>
              </label>
            </div>
          </div>
        </div>

        {/* Right: Checkout Order Summary (5 cols) */}
        <div className="md:col-span-5 space-y-6">
          <div className="glass-panel rounded-2xl p-6 border border-slate-800 space-y-5">
            <h2 className="text-sm font-bold text-white uppercase font-mono tracking-wider">
              Order Summary
            </h2>

            <div className="space-y-3 text-xs divide-y divide-slate-800/80">
              <div className="flex justify-between pt-2">
                <span className="text-slate-400">Item</span>
                <span className="text-white font-medium">{selectedProduct.name}</span>
              </div>
              <div className="flex justify-between pt-2">
                <span className="text-slate-400">Buyer Identifier</span>
                <span className="text-slate-200 font-mono text-[11px]">{buyerEmail}</span>
              </div>
              <div className="flex justify-between pt-2 text-sm font-extrabold text-white">
                <span>Total Due</span>
                <span className="text-cyan-400 font-black">${selectedProduct.price.toFixed(2)} USD</span>
              </div>
            </div>

            <form onSubmit={handleCheckout} className="pt-2">
              <button
                type="submit"
                disabled={processing}
                className="w-full py-3.5 px-4 rounded-xl font-extrabold text-xs text-slate-950 bg-gradient-to-r from-amber-400 via-yellow-400 to-amber-500 hover:from-amber-300 hover:to-yellow-300 shadow-lg shadow-amber-500/20 transition-all flex items-center justify-center gap-2 disabled:opacity-50"
              >
                {processing ? (
                  <>
                    <Loader2 className="w-4 h-4 animate-spin text-slate-950" />
                    Processing with PayPal Sandbox...
                  </>
                ) : (
                  <>
                    <CreditCard className="w-4 h-4 text-slate-950" />
                    Pay with PayPal Sandbox
                  </>
                )}
              </button>
            </form>

            <p className="text-[10px] text-slate-500 text-center flex items-center justify-center gap-1">
              <Lock className="w-3 h-3" />
              Sandbox Environment — No live monetary transactions
            </p>
          </div>

          {/* Outcome Result Card */}
          {result && (
            <div
              className={`glass-panel rounded-2xl p-6 border space-y-4 animate-scaleUp ${
                result.status === "CAPTURED"
                  ? "border-emerald-500/40 glow-blue bg-emerald-950/20"
                  : result.status === "CAPTURE_UNCERTAIN"
                  ? "border-amber-500/40 glow-amber bg-amber-950/25"
                  : "border-rose-500/40 glow-red bg-rose-950/20"
              }`}
            >
              <div className="flex items-center gap-2">
                {result.status === "CAPTURED" ? (
                  <CheckCircle2 className="w-5 h-5 text-emerald-400" />
                ) : (
                  <ShieldAlert className="w-5 h-5 text-amber-400" />
                )}
                <h3 className="text-sm font-bold text-white">
                  Checkout Outcome: {result.status}
                </h3>
              </div>

              <div className="space-y-1.5 text-xs text-slate-300">
                <p>
                  PayTrace ID: <span className="font-mono text-cyan-300 font-bold">{result.payment_id}</span>
                </p>
                <p>
                  Order ID: <span className="font-mono text-slate-200">{result.order_id}</span>
                </p>
                {result.failure_reason && (
                  <p className="text-amber-300/90 text-[11px] pt-1">
                    <strong>Notice:</strong> {result.failure_reason}
                  </p>
                )}
              </div>

              <Link
                href={`/payments/${result.payment_id}`}
                className="w-full py-2.5 px-4 rounded-lg bg-cyan-500 hover:bg-cyan-400 text-slate-950 text-xs font-bold transition-colors inline-flex items-center justify-center gap-1.5"
              >
                Inspect Lifecycle in PayTrace
                <ArrowRight className="w-3.5 h-3.5" />
              </Link>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
