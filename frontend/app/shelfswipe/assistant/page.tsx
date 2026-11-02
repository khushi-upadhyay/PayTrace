"use client";

import { useEffect, useRef, useState } from "react";
import Link from "next/link";
import { api, ShelfCartItem, ShelfChatMessage } from "@/lib/api";
import { useSessionRecording } from "@/components/session/SessionRecordingProvider";
import {
  Bot,
  Send,
  Loader2,
  ShoppingCart,
  Sparkles,
  ArrowLeft,
  ArrowRight,
  CheckCircle2,
  AlertTriangle,
  Zap,
  HelpCircle,
} from "lucide-react";

export default function ShelfSwipeAssistantPage() {
  const { sessionId, addSessionMarker } = useSessionRecording();
  const [buyerRef] = useState("buyer_demo_01");

  const [messages, setMessages] = useState<ShelfChatMessage[]>([]);
  const [input, setInput] = useState("");
  const [sending, setSending] = useState(false);
  const [actionsTaken, setActionsTaken] = useState<string[]>([]);
  const threadEndRef = useRef<HTMLDivElement | null>(null);

  const [cart, setCart] = useState<ShelfCartItem[]>([]);
  const [cartTotal, setCartTotal] = useState(0);

  const [scenario, setScenario] = useState("normal");
  const [processing, setProcessing] = useState(false);
  const [checkoutMessage, setCheckoutMessage] = useState<string | null>(null);
  const [checkoutResult, setCheckoutResult] = useState<any | null>(null);
  const capturedOrders = useRef<Set<string>>(new Set());

  useEffect(() => {
    threadEndRef.current?.scrollIntoView({ block: "nearest" });
  }, [messages, sending]);

  const refreshCart = async () => {
    try {
      const res = await api.getShelfCart(buyerRef);
      setCart(res.items);
      setCartTotal(res.total);
    } catch (err) {
      console.error(err);
    }
  };

  useEffect(() => {
    refreshCart();
  }, []);

  useEffect(() => {
    const params = new URLSearchParams(window.location.search);
    const status = params.get("status");
    const orderId = params.get("token") || params.get("orderId");
    if (status === "cancelled" || status === "cancel") {
      setCheckoutMessage("Payment was cancelled. No capture was requested.");
      sessionStorage.removeItem("paytrace_shelf_assistant_pending_order");
      return;
    }
    if ((status === "approved" || orderId) && orderId && !capturedOrders.current.has(orderId)) {
      void verifyAndCapture(orderId);
    }
  }, []);

  const verifyAndCapture = async (orderId: string) => {
    if (capturedOrders.current.has(orderId)) return;
    setProcessing(true);
    setCheckoutMessage("Verifying buyer approval with PayPal...");
    try {
      const pending = JSON.parse(sessionStorage.getItem("paytrace_shelf_assistant_pending_order") || "{}");
      if (pending.orderId !== orderId) throw new Error("No matching pending checkout was found.");
      const providerOrder = await api.getPayPalOrder(orderId);
      const providerStatus = providerOrder.status;
      if (providerStatus !== "APPROVED" && providerStatus !== "COMPLETED") {
        setCheckoutMessage(`PayPal reports ${String(providerStatus || "UNKNOWN")}; approve the order before capture.`);
        return;
      }
      capturedOrders.current.add(orderId);
      const cap = await api.captureOrder(orderId, pending.scenario === "timeout_before_response");
      addSessionMarker("shelfswipe_assistant_capture_response", {
        payment_id: cap.payment_id,
        status: cap.status,
      });
      setCheckoutResult({
        payment_id: cap.payment_id,
        order_id: cap.paypal_order_id,
        status: cap.status,
        failure_reason: cap.failure_reason,
        items: pending.items,
        is_simulated: pending.isMock === true,
      });
      setCheckoutMessage(null);
      sessionStorage.removeItem("paytrace_shelf_assistant_pending_order");
      void refreshCart();
    } catch (err: any) {
      capturedOrders.current.delete(orderId);
      setCheckoutMessage(`Checkout verification failed: ${err.message}`);
    } finally {
      setProcessing(false);
    }
  };

  const handleSend = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!input.trim() || sending) return;

    const userMsg: ShelfChatMessage = { role: "user", content: input.trim() };
    const newMessages = [...messages, userMsg];
    setMessages(newMessages);
    setInput("");
    setSending(true);

    try {
      const res = await api.shelfChat(buyerRef, userMsg.content, messages, sessionId || undefined);
      setMessages([...newMessages, { role: "assistant", content: res.response }]);
      setActionsTaken(res.actions_taken);
      setCart(res.cart);
      setCartTotal(res.cart_total);

      if (res.checkout) {
        addSessionMarker("shelfswipe_assistant_order_created", {
          payment_id: res.checkout.payment_id,
          amount: res.checkout.amount,
          currency: res.checkout.currency,
        });
        if (res.checkout.approval_url) {
          sessionStorage.setItem(
            "paytrace_shelf_assistant_pending_order",
            JSON.stringify({
              orderId: res.checkout.paypal_order_id,
              isMock: res.checkout.is_mock,
              scenario,
              items: res.cart,
            })
          );
          window.location.assign(res.checkout.approval_url);
        }
      }
    } catch (err: any) {
      setMessages([
        ...newMessages,
        { role: "assistant", content: `Error reaching the shopping assistant: ${err.message}` },
      ]);
    } finally {
      setSending(false);
    }
  };

  const handleCheckoutCart = async () => {
    if (cart.length === 0) return;
    try {
      setProcessing(true);
      setCheckoutResult(null);
      const res = await api.checkoutShelfCart(
        buyerRef,
        scenario === "timeout_before_response" ? "timeout_before_response" : undefined,
        sessionId || undefined
      );
      addSessionMarker("shelfswipe_assistant_cart_checkout_created", {
        payment_id: res.payment_id,
        amount: res.amount,
        currency: res.currency,
      });
      if (!res.approval_url) throw new Error("PayPal did not return an approval URL.");
      sessionStorage.setItem(
        "paytrace_shelf_assistant_pending_order",
        JSON.stringify({
          orderId: res.paypal_order_id,
          isMock: res.is_mock,
          scenario,
          items: res.items,
        })
      );
      window.location.assign(res.approval_url);
    } catch (err: any) {
      setCheckoutMessage(`Checkout failed: ${err.message}`);
      setProcessing(false);
    }
  };

  return (
    <div className="space-y-8 max-w-6xl mx-auto animate-fadeIn pb-16">
      {/* Header */}
      <div className="flex flex-col md:flex-row md:items-center justify-between gap-4 border-b border-slate-800 pb-6">
        <div>
          <div className="flex items-center gap-2">
            <span className="px-2.5 py-0.5 rounded-full text-[10px] font-bold uppercase tracking-wider bg-gradient-to-r from-sky-500/20 to-cyan-500/20 text-cyan-300 border border-cyan-500/30">
              Agentic Commerce
            </span>
          </div>
          <h1 className="text-2xl font-extrabold text-ink mt-1 flex items-center gap-2">
            <Bot className="w-5 h-5 text-cyan-400" />
            ShelfSwipe Shopping Assistant
          </h1>
          <p className="text-xs text-slate-400 mt-0.5">
            Describe what you want in one message, even multiple products at once, and check out conversationally.
          </p>
        </div>
        <Link
          href="/shelfswipe"
          className="flex items-center gap-2 px-3.5 py-2 rounded-lg bg-slate-900 border border-slate-700 hover:border-cyan-500/50 text-slate-200 text-xs font-semibold transition-all shadow-sm"
        >
          <ArrowLeft className="w-4 h-4 text-cyan-400" />
          Back to Swipe Deck
        </Link>
      </div>

      <div className="px-4 py-2.5 rounded-lg bg-slate-900/70 border border-slate-800 text-[11px] text-slate-400">
        <strong className="text-cyan-300">DEMO CATALOG:</strong> try &ldquo;I want the lavender candle and the honey dipper set&rdquo; to add two products in one prompt.
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-12 gap-8 items-start">
        {/* Chat Thread */}
        <div className="lg:col-span-7 space-y-4">
          <div className="glass-panel rounded-2xl p-6 border border-slate-800 space-y-4">
            <div className="flex items-center justify-between pb-3 border-b border-slate-800">
              <h3 className="text-sm font-bold text-ink flex items-center gap-2">
                <Sparkles className="w-4 h-4 text-cyan-400" />
                Chat with the Shopping Assistant
              </h3>
              <span className="text-[10px] text-slate-500">MULTI-PRODUCT AWARE</span>
            </div>

            <div className="space-y-3 max-h-96 overflow-y-auto pr-1">
              {messages.length === 0 ? (
                <div className="text-center py-10 text-xs text-slate-500 space-y-2">
                  <HelpCircle className="w-6 h-6 mx-auto text-slate-600" />
                  <p>Tell the assistant what you&apos;re looking for.</p>
                  <p className="text-[11px] text-cyan-400">
                    Try: &ldquo;I want the lavender candle and the ceramic matcha bowl&rdquo;
                  </p>
                </div>
              ) : (
                messages.map((msg, i) => (
                  <div
                    key={i}
                    className={`p-3 rounded-lg text-xs leading-relaxed ${
                      msg.role === "user"
                        ? "bg-slate-800 text-ink ml-6"
                        : "bg-cyan-950/60 border border-cyan-800/60 text-cyan-100 mr-6"
                    }`}
                  >
                    <span className="text-[9px] text-slate-400 block mb-1">
                      {msg.role === "user" ? "YOU" : "ASSISTANT"}
                    </span>
                    {msg.content}
                  </div>
                ))
              )}
              {sending && (
                <div className="p-3 rounded-lg bg-cyan-950/40 text-xs text-cyan-300 flex items-center gap-2">
                  <Loader2 className="w-3.5 h-3.5 animate-spin" />
                  Resolving products and updating cart...
                </div>
              )}
              <div ref={threadEndRef} />
            </div>

            {actionsTaken.length > 0 && (
              <div className="px-3 py-2 rounded-lg bg-slate-900/80 border border-slate-800 text-[10px] text-slate-400">
                <strong className="text-slate-300">Actions taken:</strong> {actionsTaken.join(" • ")}
              </div>
            )}

            <form onSubmit={handleSend} className="flex gap-2 pt-2 border-t border-slate-800">
              <input
                type="text"
                placeholder="e.g. 'add the leather journal and 2 soap bar trios'"
                value={input}
                onChange={(e) => setInput(e.target.value)}
                className="flex-1 bg-slate-900 border border-slate-800 rounded-lg px-3 py-2 text-xs text-ink placeholder-slate-500 focus:outline-none focus:border-cyan-500"
              />
              <button
                type="submit"
                disabled={sending || !input.trim()}
                className="px-3 py-2 bg-cyan-500 hover:bg-cyan-400 text-slate-950 rounded-lg text-xs font-bold transition-colors disabled:opacity-50"
              >
                <Send className="w-3.5 h-3.5" />
              </button>
            </form>
          </div>
        </div>

        {/* Cart & Checkout */}
        <div className="lg:col-span-5 space-y-6">
          <div className="glass-panel rounded-2xl p-6 border border-slate-800 space-y-5">
            <div className="flex items-center justify-between pb-3 border-b border-slate-800">
              <h2 className="text-sm font-bold text-ink flex items-center gap-2">
                <ShoppingCart className="w-4 h-4 text-cyan-400" />
                Cart
              </h2>
              <span className="text-[10px] text-emerald-400 font-mono font-medium">Safe Mode</span>
            </div>

            {cart.length === 0 ? (
              <p className="text-xs text-slate-500 text-center py-6">
                Your cart is empty. Ask the assistant for a product to get started.
              </p>
            ) : (
              <div className="space-y-3">
                {cart.map((item) => (
                  <div
                    key={item.product_id}
                    className="p-3 rounded-xl bg-slate-900/80 border border-slate-800 flex items-center justify-between text-xs"
                  >
                    <div>
                      <span className="font-semibold text-ink block">{item.name}</span>
                      <span className="text-slate-400 text-[11px]">Qty {item.quantity}</span>
                    </div>
                    <span className="font-mono font-bold text-cyan-300">${item.line_total.toFixed(2)}</span>
                  </div>
                ))}

                <div className="flex items-center justify-between text-xs pt-2 border-t border-slate-800">
                  <span className="text-slate-400">Cart Total</span>
                  <span className="font-mono font-extrabold text-ink">${cartTotal.toFixed(2)}</span>
                </div>

                <div className="space-y-1.5">
                  <label className="text-[11px] font-semibold text-slate-400 uppercase tracking-wider block">
                    Payment Safety Test Scenario:
                  </label>
                  <select
                    value={scenario}
                    onChange={(e) => setScenario(e.target.value)}
                    className="w-full bg-slate-950 border border-slate-800 rounded-lg px-3 py-2 text-xs text-slate-200 focus:outline-none focus:border-cyan-500"
                  >
                    <option value="normal">Normal Verified Checkout (Success)</option>
                    <option value="timeout_before_response">Simulate Capture Timeout</option>
                  </select>
                </div>

                <button
                  onClick={handleCheckoutCart}
                  disabled={processing}
                  className="w-full py-3 px-4 rounded-xl bg-cyan-500 hover:bg-cyan-400 disabled:opacity-50 text-slate-950 text-xs font-extrabold shadow-lg shadow-cyan-500/20 transition-all flex items-center justify-center gap-2"
                >
                  {processing ? (
                    <>
                      <Loader2 className="w-4 h-4 animate-spin" />
                      Communicating with PayPal...
                    </>
                  ) : (
                    <>
                      <Zap className="w-4 h-4 fill-slate-950" />
                      Checkout Cart (${cartTotal.toFixed(2)})
                    </>
                  )}
                </button>
              </div>
            )}

            {checkoutMessage && (
              <div className="p-3 rounded-xl bg-amber-950/30 border border-amber-500/40 text-amber-200 text-xs">
                {checkoutMessage}
              </div>
            )}

            {checkoutResult && (
              <div
                className={`p-4 rounded-xl border animate-fadeIn space-y-3 ${
                  checkoutResult.status === "CAPTURE_UNCERTAIN"
                    ? "bg-amber-950/40 border-amber-800 text-amber-200"
                    : "bg-emerald-950/40 border-emerald-800 text-emerald-200"
                }`}
              >
                <div className="flex items-center gap-2">
                  {checkoutResult.status === "CAPTURE_UNCERTAIN" ? (
                    <AlertTriangle className="w-4 h-4 text-amber-400 shrink-0" />
                  ) : (
                    <CheckCircle2 className="w-4 h-4 text-emerald-400 shrink-0" />
                  )}
                  <h4 className="text-xs font-bold">
                    {checkoutResult.status === "CAPTURE_UNCERTAIN"
                      ? "PayTrace Protected: Ambiguous Capture State Detected!"
                      : "Order Successfully Placed!"}
                  </h4>
                </div>

                {checkoutResult.is_simulated && (
                  <p className="text-[10px] font-semibold uppercase tracking-wide text-amber-300">Simulated demo transaction</p>
                )}

                <div className="pt-1 flex items-center justify-between text-[11px] font-mono border-t border-slate-700/50">
                  <span>ID: {checkoutResult.payment_id.slice(0, 12)}...</span>
                  <Link
                    href={`/payments/${checkoutResult.payment_id}`}
                    className="text-cyan-400 hover:underline inline-flex items-center gap-1 font-bold"
                  >
                    Investigate in PayTrace
                    <ArrowRight className="w-3 h-3" />
                  </Link>
                </div>
              </div>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}
