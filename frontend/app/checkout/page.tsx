"use client";

import { useState, useEffect } from "react";
import { useRouter } from "next/navigation";
import Link from "next/link";
import { api } from "@/lib/api";
import {
  Sparkles,
  Search,
  ThumbsUp,
  ThumbsDown,
  CheckCircle2,
  AlertTriangle,
  Loader2,
  Lock,
  ArrowRight,
  ShieldCheck,
  Zap,
  RotateCcw,
  Store,
  Compass,
} from "lucide-react";

export default function ShelfSwipePage() {
  const router = useRouter();

  // Search & Deck State
  const [query, setQuery] = useState("birthday gift under $40 nearby");
  const [buyerRef] = useState("buyer_demo_01");
  const [deck, setDeck] = useState<any[]>([]);
  const [currentIndex, setCurrentIndex] = useState(0);
  const [refinements, setRefinements] = useState<string[]>([]);
  const [loadingDeck, setLoadingDeck] = useState(false);

  // Seller Onboard Modal State
  const [sellerModal, setSellerModal] = useState(false);
  const [shopUrl, setShopUrl] = useState("https://artisan-local.dev/shop");
  const [shopName, setShopName] = useState("Artisan Local Crafts");
  const [onboarding, setOnboarding] = useState(false);
  const [onboardSuccess, setOnboardSuccess] = useState<string | null>(null);

  // Checkout Execution State
  const [scenario, setScenario] = useState("normal"); // "normal" or "timeout_before_response"
  const [processing, setProcessing] = useState(false);
  const [checkoutResult, setCheckoutResult] = useState<any | null>(null);

  const fetchDeck = async (searchQuery: string) => {
    try {
      setLoadingDeck(true);
      const res = await api.getShelfDeck(searchQuery, buyerRef);
      setDeck(res.deck || []);
      setRefinements(res.refinements_applied || []);
      setCurrentIndex(0);
    } catch (err: any) {
      console.error("Failed to load deck", err);
    } finally {
      setLoadingDeck(false);
    }
  };

  useEffect(() => {
    fetchDeck(query);
  }, []);

  const handleSearch = (e: React.FormEvent) => {
    e.preventDefault();
    fetchDeck(query);
  };

  const handleSwipe = async (direction: "right" | "left") => {
    const currentItem = deck[currentIndex];
    if (!currentItem) return;

    try {
      // Record swipe in backend to teach AI preference vector
      await api.recordSwipe(buyerRef, currentItem.id, direction);

      if (direction === "right") {
        // Automatically re-fetch deck to reflect AI re-ranking learning loop
        const res = await api.getShelfDeck(query, buyerRef);
        setDeck(res.deck || []);
        setRefinements(res.refinements_applied || []);
      }

      setCurrentIndex((prev) => Math.min(prev + 1, deck.length));
    } catch (err) {
      console.error(err);
    }
  };

  const handleSellerOnboard = async (e: React.FormEvent) => {
    e.preventDefault();
    try {
      setOnboarding(true);
      const res = await api.onboardShelfSeller(shopUrl, shopName);
      setOnboardSuccess(`AI successfully extracted ${res.products_count} items from ${res.seller_name}!`);
      setTimeout(() => {
        setSellerModal(false);
        setOnboardSuccess(null);
        fetchDeck(query);
      }, 1500);
    } catch (err: any) {
      alert(`Onboarding failed: ${err.message}`);
    } finally {
      setOnboarding(false);
    }
  };

  const handleBuyCurrent = async () => {
    const item = deck[currentIndex];
    if (!item) return;

    try {
      setProcessing(true);
      setCheckoutResult(null);

      // 1. Create order in PayTrace backend
      const res = await api.checkoutShelfItem(
        item.id,
        buyerRef,
        scenario === "timeout_before_response" ? "timeout_before_response" : undefined
      );

      // 2. Capture Order with simulated outcome
      const cap = await api.captureOrder(
        res.paypal_order_id,
        scenario === "timeout_before_response"
      );

      setCheckoutResult({
        payment_id: cap.payment_id,
        order_id: cap.paypal_order_id,
        status: cap.status,
        failure_reason: cap.failure_reason,
        product_name: item.name,
      });

      // Refresh deck stock
      fetchDeck(query);
    } catch (err: any) {
      alert(`Checkout failed: ${err.message}`);
    } finally {
      setProcessing(false);
    }
  };

  const currentItem = deck[currentIndex];

  return (
    <div className="space-y-8 max-w-5xl mx-auto animate-fadeIn pb-16">
      {/* Header Banner */}
      <div className="flex flex-col md:flex-row md:items-center justify-between gap-4 border-b border-slate-800 pb-6">
        <div>
          <div className="flex items-center gap-2">
            <span className="px-2.5 py-0.5 rounded-full text-[10px] font-bold uppercase tracking-wider bg-gradient-to-r from-sky-500/20 to-cyan-500/20 text-cyan-300 border border-cyan-500/30">
              ShelfSwipe + PayTrace Engine
            </span>
          </div>
          <h1 className="text-2xl font-extrabold text-white mt-1 flex items-center gap-2">
            AI-Powered Local Store Sync & Swipe Discovery
          </h1>
          <p className="text-xs text-slate-400 mt-0.5">
            Tiny shops put products online with AI extraction. Buyers discover gifts by chatting and swiping, secured by PayTrace intelligent payment recovery.
          </p>
        </div>

        <button
          onClick={() => setSellerModal(true)}
          className="flex items-center gap-2 px-3.5 py-2 rounded-lg bg-slate-900 border border-slate-700 hover:border-cyan-500/50 text-slate-200 text-xs font-semibold transition-all shadow-sm"
        >
          <Store className="w-4 h-4 text-cyan-400" />
          Onboard Local Shop
        </button>
      </div>

      {/* Natural Language Search Bar */}
      <form onSubmit={handleSearch} className="flex gap-2.5">
        <div className="relative flex-1">
          <Search className="w-4 h-4 text-slate-500 absolute left-3.5 top-1/2 -translate-y-1/2" />
          <input
            type="text"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            placeholder="Describe what you want (e.g. 'thoughtful birthday gift under $35')"
            className="w-full bg-slate-950/80 border border-slate-800 rounded-xl pl-10 pr-4 py-2.5 text-xs text-white placeholder-slate-500 focus:outline-none focus:border-cyan-500 transition-colors"
          />
        </div>
        <button
          type="submit"
          disabled={loadingDeck}
          className="px-5 py-2.5 rounded-xl bg-cyan-500 hover:bg-cyan-400 text-slate-950 font-bold text-xs transition-colors flex items-center gap-1.5"
        >
          {loadingDeck ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <Sparkles className="w-3.5 h-3.5" />}
          Ask AI
        </button>
      </form>

      {/* AI Preference Adaptation Notice */}
      {refinements.length > 0 && (
        <div className="px-4 py-2.5 rounded-lg bg-cyan-950/40 border border-cyan-800/60 text-cyan-300 text-xs flex items-center gap-2 animate-fadeIn">
          <Compass className="w-4 h-4 text-cyan-400 shrink-0" />
          <span>{refinements.join(" • ")}</span>
        </div>
      )}

      {/* Main Swipe & Checkout Area */}
      <div className="grid grid-cols-1 lg:grid-cols-12 gap-8 items-start">
        {/* Swipe Card Deck */}
        <div className="lg:col-span-7 space-y-4">
          <div className="flex items-center justify-between text-xs text-slate-400">
            <span className="font-mono">Card {currentIndex + 1} of {deck.length}</span>
            <span>Swipes teach AI your taste</span>
          </div>

          {loadingDeck ? (
            <div className="h-[460px] glass-panel rounded-2xl flex flex-col items-center justify-center space-y-3">
              <Loader2 className="w-8 h-8 text-cyan-400 animate-spin" />
              <p className="text-xs text-slate-400">AI is curating your personalized shelf...</p>
            </div>
          ) : currentItem ? (
            <div className="glass-panel rounded-2xl overflow-hidden border border-slate-800 shadow-2xl transition-all duration-300 hover:border-slate-700">
              <div className="relative h-60 w-full overflow-hidden bg-slate-900">
                <img
                  src={currentItem.image_url || "https://images.unsplash.com/photo-1544716278-ca5e3f4abd8c?auto=format&fit=crop&w=600&q=80"}
                  alt={currentItem.name}
                  className="w-full h-full object-cover"
                />
                <div className="absolute top-3 left-3 bg-slate-950/80 backdrop-blur-md px-2.5 py-1 rounded-full border border-slate-700 text-[10px] font-mono font-medium text-cyan-300">
                  {currentItem.category}
                </div>
                <div className="absolute top-3 right-3 bg-emerald-950/90 backdrop-blur-md px-2.5 py-1 rounded-full border border-emerald-700 text-[10px] font-bold text-emerald-300">
                  {currentItem.stock} in stock
                </div>
              </div>

              <div className="p-6 space-y-4">
                <div className="flex items-start justify-between gap-4">
                  <div>
                    <h3 className="text-lg font-bold text-white">{currentItem.name}</h3>
                    <p className="text-xs text-slate-400 mt-1 line-clamp-2">{currentItem.description}</p>
                  </div>
                  <span className="text-xl font-extrabold text-cyan-400 font-mono">
                    ${Number(currentItem.price).toFixed(2)}
                  </span>
                </div>

                {/* AI Reasoning Box */}
                {currentItem.why_matches && (
                  <div className="p-3 rounded-lg bg-slate-900/90 border border-slate-800 text-[11px] text-slate-300 flex items-start gap-2">
                    <Sparkles className="w-3.5 h-3.5 text-cyan-400 shrink-0 mt-0.5" />
                    <span><strong>Why this matches:</strong> {currentItem.why_matches}</span>
                  </div>
                )}

                {/* Swipe Action Buttons */}
                <div className="pt-2 flex items-center justify-between gap-3 border-t border-slate-800/80">
                  <button
                    onClick={() => handleSwipe("left")}
                    className="flex-1 py-2.5 px-4 rounded-xl bg-slate-900 hover:bg-slate-800 border border-slate-700 text-slate-300 font-medium text-xs flex items-center justify-center gap-2 transition-all"
                  >
                    <ThumbsDown className="w-3.5 h-3.5 text-slate-400" />
                    Pass (Swipe Left)
                  </button>
                  <button
                    onClick={() => handleSwipe("right")}
                    className="flex-1 py-2.5 px-4 rounded-xl bg-cyan-500/10 hover:bg-cyan-500/20 border border-cyan-500/30 text-cyan-300 font-bold text-xs flex items-center justify-center gap-2 transition-all"
                  >
                    <ThumbsUp className="w-3.5 h-3.5 text-cyan-400" />
                    Like (Swipe Right)
                  </button>
                </div>
              </div>
            </div>
          ) : (
            <div className="h-[460px] glass-panel rounded-2xl flex flex-col items-center justify-center space-y-3 p-6 text-center">
              <CheckCircle2 className="w-10 h-10 text-emerald-400" />
              <h4 className="text-sm font-bold text-white">You've explored the shelf!</h4>
              <p className="text-xs text-slate-400">Search another term or reset the deck to keep discovering.</p>
              <button
                onClick={() => fetchDeck(query)}
                className="px-4 py-2 bg-slate-800 hover:bg-slate-700 text-white rounded-lg text-xs font-semibold"
              >
                Reset Swipe Deck
              </button>
            </div>
          )}
        </div>

        {/* Checkout & PayTrace Recovery Side-Panel */}
        <div className="lg:col-span-5 space-y-6">
          <div className="glass-panel rounded-2xl p-6 border border-slate-800 space-y-5">
            <div className="flex items-center justify-between pb-3 border-b border-slate-800">
              <h2 className="text-sm font-bold text-white flex items-center gap-2">
                <Lock className="w-4 h-4 text-cyan-400" />
                PayPal Sandbox Instant Checkout
              </h2>
              <span className="text-[10px] text-emerald-400 font-mono font-medium">Safe Mode</span>
            </div>

            {currentItem ? (
              <div className="space-y-4">
                <div className="p-3.5 rounded-xl bg-slate-900/80 border border-slate-800 flex items-center justify-between text-xs">
                  <div>
                    <span className="text-slate-400 block text-[11px]">Selected Item</span>
                    <span className="font-semibold text-white">{currentItem.name}</span>
                  </div>
                  <span className="font-mono font-bold text-cyan-300">${Number(currentItem.price).toFixed(2)}</span>
                </div>

                {/* Scenario Selector for Demo Simulation */}
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
                    <option value="timeout_before_response">
                      Simulate Capture Timeout (PayTrace Duplicate Protection)
                    </option>
                  </select>
                  <p className="text-[10px] text-slate-500">
                    {scenario === "timeout_before_response"
                      ? "Demonstrates how PayTrace prevents duplicate charges when the backend times out after capture."
                      : "Standard real/mock PayPal sandbox transaction with stock decrement on verified webhook."}
                  </p>
                </div>

                <button
                  onClick={handleBuyCurrent}
                  disabled={processing || currentItem.stock <= 0}
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
                      Buy Now with PayPal (${Number(currentItem.price).toFixed(2)})
                    </>
                  )}
                </button>
              </div>
            ) : (
              <p className="text-xs text-slate-500 text-center py-6">Select a product from the deck to checkout.</p>
            )}

            {/* Post-Checkout PayTrace Result Box */}
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

                <p className="text-[11px] leading-relaxed opacity-90">
                  {checkoutResult.status === "CAPTURE_UNCERTAIN"
                    ? "Merchant backend timed out. PayTrace prevented blind retrying to avoid charging the customer twice."
                    : "Payment captured and order verified."}
                </p>

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

      {/* Seller Onboard Modal */}
      {sellerModal && (
        <div className="fixed inset-0 bg-slate-950/80 backdrop-blur-sm z-50 flex items-center justify-center p-4">
          <div className="glass-panel max-w-md w-full rounded-2xl p-6 border border-slate-800 space-y-5 animate-scaleUp">
            <div>
              <h3 className="text-base font-bold text-white flex items-center gap-2">
                <Store className="w-5 h-5 text-cyan-400" />
                Onboard Local Shop via AI
              </h3>
              <p className="text-xs text-slate-400 mt-1">
                Paste your shop URL with consent. AI extracts products into a live shelf in seconds without code integration.
              </p>
            </div>

            <form onSubmit={handleSellerOnboard} className="space-y-4 text-xs">
              <div>
                <label className="block text-slate-400 mb-1">Shop Name</label>
                <input
                  type="text"
                  value={shopName}
                  onChange={(e) => setShopName(e.target.value)}
                  className="w-full bg-slate-900 border border-slate-700 rounded-lg p-2.5 text-white"
                  required
                />
              </div>

              <div>
                <label className="block text-slate-400 mb-1">Store / Website URL</label>
                <input
                  type="url"
                  value={shopUrl}
                  onChange={(e) => setShopUrl(e.target.value)}
                  className="w-full bg-slate-900 border border-slate-700 rounded-lg p-2.5 text-white"
                  required
                />
              </div>

              <div className="flex items-center gap-2 p-3 bg-slate-900/60 border border-slate-800 rounded-lg">
                <input type="checkbox" id="consent" defaultChecked required className="rounded accent-cyan-500" />
                <label htmlFor="consent" className="text-[11px] text-slate-400">
                  I give consent for ShelfSwipe AI to extract my product catalog.
                </label>
              </div>

              {onboardSuccess && (
                <p className="text-emerald-400 text-xs font-semibold">{onboardSuccess}</p>
              )}

              <div className="flex justify-end gap-2 pt-2">
                <button
                  type="button"
                  onClick={() => setSellerModal(false)}
                  className="px-4 py-2 rounded-lg bg-slate-800 hover:bg-slate-700 text-slate-300 font-medium"
                >
                  Cancel
                </button>
                <button
                  type="submit"
                  disabled={onboarding}
                  className="px-4 py-2 rounded-lg bg-cyan-500 hover:bg-cyan-400 text-slate-950 font-bold flex items-center gap-1.5"
                >
                  {onboarding && <Loader2 className="w-3.5 h-3.5 animate-spin" />}
                  Extract Shelf with AI
                </button>
              </div>
            </form>
          </div>
        </div>
      )}
    </div>
  );
}
