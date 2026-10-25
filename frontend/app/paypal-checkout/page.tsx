"use client";

import { useState, useEffect, useRef, Suspense } from "react";
import { useRouter, useSearchParams } from "next/navigation";
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
  XCircle,
  ExternalLink,
} from "lucide-react";

const PRODUCTS = [
  { id: "p1", name: "Enterprise Observability Plan", price: 189.99, desc: "Full cluster tracing, unlimited AI investigations" },
  { id: "p2", name: "Developer Cloud License", price: 49.99, desc: "Standard sandbox monitoring and webhook validation" },
  { id: "p3", name: "Telemetry Starter Pack", price: 25.00, desc: "Single application checkout tracer" },
];

function CheckoutContent() {
  const searchParams = useSearchParams();

  const [selectedProduct, setSelectedProduct] = useState(PRODUCTS[0]);
  const [scenario, setScenario] = useState("normal"); // "normal", "timeout_before_response", "capture_denied"
  const [buyerEmail, setBuyerEmail] = useState("sandbox-buyer@paytrace.dev");

  const [processing, setProcessing] = useState(false);
  const [verifying, setVerifying] = useState(false);
  const [waitingApproval, setWaitingApproval] = useState(false);
  const [activeOrderId, setActiveOrderId] = useState<string | null>(null);
  const [approvalUrl, setApprovalUrl] = useState<string | null>(null);
  const [result, setResult] = useState<any | null>(null);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);
  const [cancelledMessage, setCancelledMessage] = useState<string | null>(null);
  const [unapprovedWarning, setUnapprovedWarning] = useState<string | null>(null);

  const capturedOrders = useRef<Set<string>>(new Set());

  // Restore pending active order from localStorage if available
  useEffect(() => {
    try {
      const stored = sessionStorage.getItem("paytrace_pending_order");
      if (stored) {
        const parsed = JSON.parse(stored);
        if (parsed.orderId) {
          setActiveOrderId(parsed.orderId);
          if (parsed.approvalUrl) setApprovalUrl(parsed.approvalUrl);
        }
      }
    } catch {
      // Ignore sessionStorage error
    }
  }, []);

  // Handle PayPal return flow (e.g. ?status=approved&token=ORDER_ID or ?status=cancelled)
  useEffect(() => {
    const statusParam = searchParams.get("status");
    const tokenParam = searchParams.get("token") || searchParams.get("orderId");

    if (statusParam === "cancelled" || statusParam === "cancel") {
      setCancelledMessage("Payment was cancelled by buyer on PayPal Sandbox. No funds were debited.");
      setWaitingApproval(false);
      setProcessing(false);
      sessionStorage.removeItem("paytrace_pending_order");
      return;
    }

    if (statusParam === "approved" || statusParam === "success" || tokenParam) {
      const orderToCapture = tokenParam || activeOrderId;
      if (orderToCapture && !capturedOrders.current.has(orderToCapture)) {
        verifyAndCapture(orderToCapture);
      }
    }
  }, [searchParams, activeOrderId]);

  const handleCheckout = async (e: React.FormEvent) => {
    e.preventDefault();
    if (processing || waitingApproval) return;

    try {
      setProcessing(true);
      setResult(null);
      setErrorMessage(null);
      setCancelledMessage(null);
      setUnapprovedWarning(null);

      // 1. Create Order via FastAPI
      const orderRes = await api.createOrder({
        amount: selectedProduct.price,
        customer_ref: buyerEmail,
        simulate_scenario: scenario === "normal" ? undefined : scenario,
      });

      setActiveOrderId(orderRes.paypal_order_id);

      // 2. Real Sandbox Order Flow: Must be approved by buyer first
      if (!orderRes.is_mock && orderRes.approval_url) {
        setApprovalUrl(orderRes.approval_url);
        setWaitingApproval(true);
        setProcessing(false);

        // Store pending order in sessionStorage for return verification
        try {
          sessionStorage.setItem(
            "paytrace_pending_order",
            JSON.stringify({
              orderId: orderRes.paypal_order_id,
              paymentId: orderRes.payment_id,
              approvalUrl: orderRes.approval_url,
            })
          );
        } catch {}

        // Redirect directly to PayPal Sandbox buyer approval flow
        window.location.href = orderRes.approval_url;
        return;
      }

      // 3. Simulated Demo Order Flow (Local mock or simulated timeout/declined scenarios)
      await executeCaptureDirect(orderRes.paypal_order_id);
    } catch (err: any) {
      setErrorMessage(`Checkout initiation failed: ${err.message}`);
      setProcessing(false);
    }
  };

  /**
   * For Sandbox transactions, verify provider status is APPROVED before capturing.
   */
  const verifyAndCapture = async (orderId: string) => {
    if (capturedOrders.current.has(orderId)) return;

    try {
      setVerifying(true);
      setProcessing(true);
      setErrorMessage(null);
      setUnapprovedWarning(null);

      // Fetch order details directly from PayPal via backend
      const providerOrder = await api.getPayPalOrder(orderId);
      const providerStatus = (providerOrder.status as string) || "UNKNOWN";

      if (providerStatus !== "APPROVED" && providerStatus !== "COMPLETED") {
        setVerifying(false);
        setProcessing(false);
        setWaitingApproval(true);
        setUnapprovedWarning(
          `PayPal reports order status as "${providerStatus}". Buyer approval has not been completed. Please approve the order on PayPal before capturing.`
        );
        return;
      }

      // Order is confirmed APPROVED by PayPal -> Proceed to capture
      await executeCaptureDirect(orderId);
    } catch (err: any) {
      setErrorMessage(`Verification before capture failed: ${err.message}`);
      setVerifying(false);
      setProcessing(false);
    }
  };

  const executeCaptureDirect = async (orderId: string) => {
    if (capturedOrders.current.has(orderId)) {
      return;
    }
    capturedOrders.current.add(orderId);

    try {
      setProcessing(true);
      setWaitingApproval(false);
      setVerifying(false);
      setErrorMessage(null);
      setCancelledMessage(null);
      setUnapprovedWarning(null);
      sessionStorage.removeItem("paytrace_pending_order");

      const capRes = await api.captureOrder(
        orderId,
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
      capturedOrders.current.delete(orderId); // Allow retry on failure
      setErrorMessage(`Capture failed: ${err.message}`);
    } finally {
      setProcessing(false);
      setVerifying(false);
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

            {waitingApproval && (
              <div className="p-3.5 rounded-xl bg-amber-950/30 border border-amber-500/40 text-amber-200 text-xs space-y-2.5 animate-fadeIn">
                <div className="flex items-center gap-2 font-bold">
                  <Loader2 className="w-4 h-4 animate-spin text-amber-400" />
                  <span>Awaiting PayPal Buyer Approval</span>
                </div>
                <p className="text-[11px] text-amber-300/80">
                  Redirecting to PayPal Sandbox. If not redirected automatically, click below to open PayPal checkout and approve the payment with your Sandbox account.
                </p>
                {approvalUrl && (
                  <a
                    href={approvalUrl}
                    className="inline-flex items-center gap-1.5 text-xs text-cyan-300 bg-cyan-950/60 px-3 py-1.5 rounded-lg border border-cyan-800 hover:bg-cyan-900/60 transition-colors"
                  >
                    Open PayPal Approval Page
                    <ExternalLink className="w-3.5 h-3.5" />
                  </a>
                )}
                {activeOrderId && (
                  <button
                    type="button"
                    onClick={() => verifyAndCapture(activeOrderId)}
                    disabled={processing || verifying}
                    className="w-full mt-2 py-2.5 px-3 rounded-lg bg-emerald-500 hover:bg-emerald-400 text-slate-950 text-xs font-bold transition-all disabled:opacity-50 flex items-center justify-center gap-2"
                  >
                    {verifying || processing ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : null}
                    Confirm Buyer Approval & Capture
                  </button>
                )}
              </div>
            )}

            {unapprovedWarning && (
              <div className="p-3.5 rounded-xl bg-amber-950/30 border border-amber-500/40 text-amber-200 text-xs space-y-2 animate-fadeIn">
                <div className="flex items-start gap-2">
                  <AlertTriangle className="w-4 h-4 text-amber-400 shrink-0 mt-0.5" />
                  <span>{unapprovedWarning}</span>
                </div>
                {approvalUrl && (
                  <a
                    href={approvalUrl}
                    className="inline-flex items-center gap-1.5 text-xs text-amber-300 underline hover:text-amber-200"
                  >
                    Resume Buyer Approval on PayPal
                    <ExternalLink className="w-3 h-3" />
                  </a>
                )}
              </div>
            )}

            {cancelledMessage && (
              <div className="p-3.5 rounded-xl bg-slate-900/80 border border-slate-700 text-slate-300 text-xs flex items-start gap-2 animate-fadeIn">
                <XCircle className="w-4 h-4 text-slate-400 shrink-0 mt-0.5" />
                <span>{cancelledMessage}</span>
              </div>
            )}

            {errorMessage && (
              <div className="p-3.5 rounded-xl bg-rose-950/30 border border-rose-500/40 text-rose-200 text-xs flex items-start gap-2 animate-fadeIn">
                <AlertTriangle className="w-4 h-4 text-rose-400 shrink-0 mt-0.5" />
                <span>{errorMessage}</span>
              </div>
            )}

            <form onSubmit={handleCheckout} className="pt-2">
              <button
                type="submit"
                disabled={processing || waitingApproval}
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

export default function CheckoutDemoPage() {
  return (
    <Suspense
      fallback={
        <div className="py-20 text-center text-slate-400 text-xs flex items-center justify-center gap-2">
          <Loader2 className="w-4 h-4 animate-spin text-cyan-400" />
          Loading PayTrace Checkout...
        </div>
      }
    >
      <CheckoutContent />
    </Suspense>
  );
}
