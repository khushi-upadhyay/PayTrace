"use client";

import React, { useCallback, useEffect, useRef, useState } from "react";
import Link from "next/link";
import {
  Search,
  ThumbsDown,
  ShoppingCart,
  Loader2,
  Package,
  CheckCircle2,
  Store,
  MessageCircle,
  Send,
} from "lucide-react";
import CartPayment, { CartLine } from "@/components/shelfswipe/CartPayment";
import { api } from "@/lib/api";
import { useSessionRecording } from "@/components/session/SessionRecordingProvider";
import {
  BuyerDeckProductItem,
  ShelfSwipeSellerSummary,
  getOrCreateBuyerId,
  shelfswipeApi,
} from "@/lib/shelfswipe-api";

export default function ShelfSwipeBuyerOnboardingPage() {
  const [buyerId, setBuyerId] = useState<string | null>(null);

  const [shops, setShops] = useState<ShelfSwipeSellerSummary[]>([]);
  const [selectedShopId, setSelectedShopId] = useState<string>("all");

  const [query, setQuery] = useState("");
  const [deck, setDeck] = useState<BuyerDeckProductItem[]>([]);
  const [currentIndex, setCurrentIndex] = useState(0);
  const [loadingDeck, setLoadingDeck] = useState(true);
  const [deckError, setDeckError] = useState<string | null>(null);
  const [assistantQuery, setAssistantQuery] = useState("");
  const [assistantMessages, setAssistantMessages] = useState<Array<{
    id: string;
    query: string;
    text: string;
    products: BuyerDeckProductItem[];
  }>>([]);
  const [assistantBusy, setAssistantBusy] = useState(false);
  const [assistantError, setAssistantError] = useState<string | null>(null);

  const { sessionId, addSessionMarker } = useSessionRecording();
  const [cart, setCart] = useState<CartLine[]>([]);
  const [imageError, setImageError] = useState(false);
  const [checkoutBusy, setCheckoutBusy] = useState(false);
  const [checkoutError, setCheckoutError] = useState<string | null>(null);

  // Checkout state
  const [processing, setProcessing] = useState(false);
  const [checkoutMessage, setCheckoutMessage] = useState<string | null>(null);
  const [checkoutResult, setCheckoutResult] = useState<{
    payment_id: string;
    status: string;
    failure_reason?: string | null;
    product_name?: string;
    is_simulated: boolean;
  } | null>(null);
  const capturedOrders = useRef<Set<string>>(new Set());

  useEffect(() => {
    setBuyerId(getOrCreateBuyerId());
  }, []);

  // Shop filter chips
  useEffect(() => {
    shelfswipeApi
      .listSellers()
      .then((res) => setShops(res.sellers.filter((s) => s.live_count > 0)))
      .catch(() => {
        // filter chips are a nice-to-have
      });
  }, []);

  const fetchDeck = useCallback(async (shopId: string, searchQuery: string) => {
    try {
      setLoadingDeck(true);
      setDeckError(null);
      const res = await shelfswipeApi.getBuyerDeck(
        shopId === "all" ? undefined : shopId,
        searchQuery.trim() || undefined
      );
      setDeck(res.deck);
      setCurrentIndex(0);
    } catch (err: any) {
      setDeck([]);
      setDeckError(err.message || "Unable to load the buyer deck.");
    } finally {
      setLoadingDeck(false);
    }
  }, []);

  useEffect(() => {
    fetchDeck(selectedShopId, query);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [selectedShopId]);

  const handleSearch = (e: React.FormEvent) => {
    e.preventDefault();
    fetchDeck(selectedShopId, query);
  };

  const currentItem = deck[currentIndex];

  const addToCart = (product: BuyerDeckProductItem) => {
    if (product.stock < 1) return;
    setCart((previous) => {
      const existing = previous.find((line) => line.id === product.id);
      if (existing) {
        return previous.map((line) => line.id === product.id
          ? { ...line, quantity: Math.min(line.quantity + 1, line.stock) }
          : line);
      }
      return [...previous, {
        id: product.id,
        name: product.name,
        shop_name: product.shop_name,
        price: Number(product.price),
        stock: product.stock,
        image_url: product.image_url,
        quantity: 1,
      }];
    });
  };

  const askStoreAssistant = async (event: React.FormEvent) => {
    event.preventDefault();
    const question = assistantQuery.trim();
    if (!question || assistantBusy) return;
    setAssistantBusy(true);
    setAssistantError(null);
    try {
      const result = await shelfswipeApi.getBuyerDeck(
        selectedShopId === "all" ? undefined : selectedShopId,
        question,
      );
      const available = result.deck.filter((product) => product.stock > 0);
      const text = available.length
          ? `Yes — I found ${available.length} in-stock ${available.length === 1 ? "product" : "products"} matching “${question}” in the approved store catalog.`
          : result.deck.length
            ? `I found matching products for “${question}”, but they are currently out of stock.`
            : `I couldn't find “${question}” in the currently approved store catalog. Try another name or category.`;
      setAssistantMessages((previous) => [...previous.slice(-7), {
        id: `${Date.now()}-${previous.length}`,
        query: question,
        text,
        products: (available.length ? available : result.deck).slice(0, 4),
      }]);
      addSessionMarker("shelfswipe_catalog_assistant_search", {
        query: question,
        result_count: result.deck.length,
        in_stock_count: available.length,
        shop_id: selectedShopId === "all" ? null : selectedShopId,
      });
    } catch (error) {
      setAssistantError(error instanceof Error ? error.message : "The store catalog could not be searched.");
    } finally {
      setAssistantBusy(false);
    }
  };

  const handleSwipe = async (direction: "left" | "right") => {
    if (!currentItem || !buyerId) return;
    if (direction === "right") addToCart(currentItem);
    setImageError(false);
    setCurrentIndex((prev) => Math.min(prev + 1, deck.length));

    try {
      await shelfswipeApi.recordBuyerSwipe(buyerId, currentItem.id, direction);
    } catch {
      // swipe recording is best-effort; the browsing experience should not block on it
    }
  };

  const handleCheckout = async () => {
    if (!currentItem || !buyerId || checkoutBusy) return;
    setCheckoutBusy(true);
    setCheckoutError(null);
    try {
      const order = await api.checkoutShelfItem(currentItem.id, buyerId);
      if (!order.approval_url) throw new Error("PayPal did not return a buyer approval URL.");
      sessionStorage.setItem("paytrace_shelfswipe_pending_order", JSON.stringify({
        orderId: order.paypal_order_id,
        isMock: order.is_mock,
        scenario: "normal",
        productName: order.product_name,
      }));
      window.location.assign(order.approval_url);
    } catch (err) {
      setCheckoutError(err instanceof Error ? err.message : "Could not start PayPal checkout.");
      setCheckoutBusy(false);
    }
  };

  const handleReset = () => {
    fetchDeck(selectedShopId, query);
  };

  const changeQty = (id: string, qty: number) => {
    setCart((prev) =>
      prev
        .map((l) => (l.id === id ? { ...l, quantity: Math.min(qty, l.stock) } : l))
        .filter((l) => l.quantity > 0)
    );
  };
  const removeLine = (id: string) => setCart((prev) => prev.filter((l) => l.id !== id));

  const handlePay = async (method: "paypal" | "paylater" | "card") => {
    if (!buyerId || cart.length === 0 || processing) return;
    try {
      setProcessing(true);
      setCheckoutResult(null);
      setCheckoutMessage(method === "card" ? "Processing card payment..." : "Redirecting to PayPal...");
      const res = await api.checkoutShelfCart(
        cart.map((l) => ({ product_id: l.id, quantity: l.quantity })),
        buyerId,
        { returnPath: "/shelfswipe/buyer-onboarding", sessionId: sessionId || undefined }
      );
      addSessionMarker("shelfswipe_order_created", {
        payment_id: res.payment_id,
        amount: res.amount,
        currency: res.currency,
        method,
      });
      if (!res.approval_url) throw new Error("PayPal did not return an approval URL.");
      sessionStorage.setItem(
        "paytrace_shelfswipe_pending_order",
        JSON.stringify({ orderId: res.paypal_order_id, isMock: res.is_mock, scenario: "normal", productName: res.product_name })
      );
      window.location.assign(res.approval_url);
    } catch (err: any) {
      setCheckoutMessage(`Checkout failed: ${err.message}`);
      setProcessing(false);
    }
  };

  const verifyAndCapture = async (orderId: string) => {
    if (capturedOrders.current.has(orderId)) return;
    setProcessing(true);
    setCheckoutMessage("Verifying buyer approval with PayPal...");
    try {
      const pending = JSON.parse(sessionStorage.getItem("paytrace_shelfswipe_pending_order") || "{}");
      if (pending.orderId !== orderId) throw new Error("No matching pending checkout was found.");
      const providerOrder = await api.getPayPalOrder(orderId);
      const providerStatus = providerOrder.status;
      if (providerStatus !== "APPROVED" && providerStatus !== "COMPLETED") {
        setCheckoutMessage(`PayPal reports ${String(providerStatus || "UNKNOWN")}; approve the order before capture.`);
        return;
      }
      capturedOrders.current.add(orderId);
      const cap = await api.captureOrder(orderId, false);
      addSessionMarker("shelfswipe_capture_response", { payment_id: cap.payment_id, status: cap.status });
      setCheckoutResult({
        payment_id: cap.payment_id,
        status: cap.status,
        failure_reason: cap.failure_reason,
        product_name: pending.productName,
        is_simulated: pending.isMock === true,
      });
      setCheckoutMessage(null);
      sessionStorage.removeItem("paytrace_shelfswipe_pending_order");
      if (cap.status === "CAPTURED") setCart([]);
      void fetchDeck(selectedShopId, query);
    } catch (err: any) {
      capturedOrders.current.delete(orderId);
      setCheckoutMessage(`Checkout verification failed: ${err.message}`);
    } finally {
      setProcessing(false);
    }
  };

  // PayPal return (?status=approved&token=ORDER_ID or ?status=cancelled)
  useEffect(() => {
    const params = new URLSearchParams(window.location.search);
    const status = params.get("status");
    const orderId = params.get("token") || params.get("orderId");
    if (status === "cancelled" || status === "cancel") {
      setCheckoutMessage("Payment was cancelled. Your cart is unchanged and nothing was charged.");
      sessionStorage.removeItem("paytrace_shelfswipe_pending_order");
      return;
    }
    if ((status === "approved" || orderId) && orderId) {
      void verifyAndCapture(orderId);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  return (
    <div className="min-h-screen bg-[#f8fafc] text-[#0f172a] pb-16">
      {/* Top Banner */}
      <div className="border-b border-[#e2e8f0] bg-white">
        <div className="mx-auto max-w-5xl px-4 py-4 sm:px-6 flex items-center justify-between gap-4">
          <div className="flex items-center gap-3 min-w-0">
            <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-xl bg-[#047857] text-white shadow-sm">
              <Store className="h-5 w-5" />
            </div>
            <div className="min-w-0">
              <span className="text-xs font-bold uppercase tracking-wider text-paypal-blue block">ShelfSwipe</span>
              <h1 className="text-lg font-bold text-[#0f172a] truncate">ShelfSwipe Store</h1>
            </div>
          </div>
        </div>
      </div>

      <div className="mx-auto max-w-5xl px-4 pt-6 sm:px-6 space-y-5">
        {/* Shop filter chips */}
        <div className="flex items-center gap-2 overflow-x-auto pb-1">
          <button
            type="button"
            onClick={() => setSelectedShopId("all")}
            className={`shrink-0 inline-flex items-center gap-1.5 rounded-full px-3.5 py-1.5 text-xs font-bold transition-all ${
              selectedShopId === "all"
                ? "bg-paypal-navy text-white shadow-xs"
                : "bg-white border border-[#e2e8f0] text-[#475569] hover:bg-[#f1f5f9]"
            }`}
          >
            All Shops
          </button>
          {shops.map((s) => (
            <button
              key={s.shop_id}
              type="button"
              onClick={() => setSelectedShopId(s.shop_id)}
              className={`shrink-0 inline-flex items-center gap-1.5 rounded-full px-3.5 py-1.5 text-xs font-bold transition-all ${
                selectedShopId === s.shop_id
                  ? "bg-paypal-navy text-white shadow-xs"
                  : "bg-white border border-[#e2e8f0] text-[#475569] hover:bg-[#f1f5f9]"
              }`}
            >
              <Store className="h-3.5 w-3.5" />
              {s.shop_name}
              <span className={`rounded-full px-1.5 text-[10px] ${selectedShopId === s.shop_id ? "bg-white/20" : "bg-[#f1f5f9]"}`}>
                {s.live_count}
              </span>
            </button>
          ))}
        </div>

        {/* Search */}
        <form onSubmit={handleSearch} className="flex gap-2.5">
          <div className="relative flex-1">
            <Search className="w-4 h-4 text-[#94a3b8] absolute left-3.5 top-1/2 -translate-y-1/2" />
            <input
              type="text"
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              placeholder="Search what you're looking for (e.g. 'ceramic gift under $40')"
              className="w-full rounded-full border border-[#cbd5e1] pl-10 pr-4 py-2.5 text-xs text-[#0f172a] placeholder-[#94a3b8] focus:outline-none focus:border-paypal-blue focus:ring-1 focus:ring-paypal-blue"
            />
          </div>
          <button type="submit" className="btn-pill btn-pill-primary !py-2.5 !px-5 !text-xs">
            Search
          </button>
        </form>

        <section aria-label="ShelfSwipe catalog chat" className="rounded-2xl border border-[#cbd5e1] bg-white p-4 shadow-sm sm:p-5">
          <div className="flex items-start gap-3">
            <span className="flex h-9 w-9 shrink-0 items-center justify-center rounded-xl bg-[#eaf3ff] text-[#075ca8]"><MessageCircle className="h-4 w-4" /></span>
            <div className="min-w-0 flex-1">
              <h2 className="text-sm font-bold text-[#0f172a]">Ask the ShelfSwipe catalog</h2>
              <p className="mt-1 text-xs leading-relaxed text-[#475569]">Search live, approved products by name or category, then add a match to your cart. Results use the local catalog, including products imported through Channel3.</p>
              <form onSubmit={askStoreAssistant} className="mt-3 flex gap-2">
                <input value={assistantQuery} onChange={(event) => setAssistantQuery(event.target.value)} aria-label="Ask the product catalog" placeholder="Do you have a lavender candle?" className="min-w-0 flex-1 rounded-xl border border-[#94a3b8] bg-white px-3 py-2.5 text-sm text-[#0f172a] placeholder:text-[#64748b] focus:border-[#075ca8] focus:outline-none focus:ring-2 focus:ring-[#075ca8]/20" />
                <button type="submit" disabled={assistantBusy || !assistantQuery.trim()} className="inline-flex shrink-0 items-center gap-2 rounded-xl bg-[#075ca8] px-3.5 py-2.5 text-xs font-bold text-white hover:bg-[#064b88] disabled:cursor-not-allowed disabled:opacity-50"><Send className="h-3.5 w-3.5" /><span className="hidden sm:inline">Ask</span></button>
              </form>
              {assistantBusy && <p role="status" className="mt-3 text-xs font-medium text-[#334155]">Searching approved store inventory…</p>}
              {assistantError && <p role="alert" className="mt-3 text-xs font-semibold text-[#b42318]">{assistantError}</p>}
              {assistantMessages.length > 0 && <div aria-live="polite" className="mt-3 max-h-80 space-y-3 overflow-y-auto pr-1">
                {assistantMessages.map((message) => <div key={message.id} className="space-y-2">
                  <div className="flex justify-end"><p className="max-w-[85%] rounded-xl rounded-br-sm bg-[#075ca8] px-3 py-2 text-xs font-medium text-white">{message.query}</p></div>
                  <div className="max-w-[95%] rounded-xl rounded-bl-sm bg-[#f1f5f9] p-3">
                    <p className="text-sm font-medium text-[#1e293b]">{message.text}</p>
                    {message.products.length > 0 && <div className="mt-2 grid gap-2 sm:grid-cols-2">
                      {message.products.map((product) => <div key={product.id} className="flex items-center justify-between gap-3 rounded-lg border border-[#cbd5e1] bg-white p-2.5">
                        <div className="min-w-0"><p className="truncate text-xs font-bold text-[#0f172a]">{product.name}</p><p className="mt-0.5 truncate text-[11px] text-[#475569]">{product.shop_name} · ${Number(product.price).toFixed(2)} · {product.stock > 0 ? `${product.stock} in stock` : "Out of stock"}</p></div>
                        <button type="button" onClick={() => addToCart(product)} disabled={product.stock < 1} className="shrink-0 rounded-lg border border-[#075ca8] px-2.5 py-1.5 text-[11px] font-bold text-[#075ca8] hover:bg-[#eaf3ff] disabled:opacity-50">Add</button>
                      </div>)}
                    </div>}
                  </div>
                </div>)}
              </div>}
            </div>
          </div>
        </section>

        {/* Deck */}
        <div className="grid grid-cols-1 lg:grid-cols-12 gap-6 items-start">
          <div className="lg:col-span-7 space-y-3">
            <div className="flex items-center justify-between text-xs text-[#64748b]">
              <span>
                {loadingDeck
                  ? "Loading live catalog..."
                  : deckError
                  ? "Catalog unavailable"
                  : deck.length
                  ? `Product ${Math.min(currentIndex + 1, deck.length)} of ${deck.length}`
                  : "No live products found"}
              </span>
              {cart.length > 0 && <span>{cart.reduce((n, l) => n + l.quantity, 0)} in cart</span>}
            </div>

            {loadingDeck ? (
              <div className="h-[460px] rounded-2xl border border-[#e2e8f0] bg-white flex flex-col items-center justify-center gap-3">
                <Loader2 className="w-8 h-8 text-paypal-blue animate-spin" />
                <p className="text-xs text-[#64748b]">Loading approved products...</p>
              </div>
            ) : deckError ? (
              <div className="h-[460px] rounded-2xl border border-[#e2e8f0] bg-white flex flex-col items-center justify-center gap-3 p-6 text-center">
                <Package className="w-8 h-8 text-[#f59e0b]" />
                <p className="text-sm font-semibold text-[#0f172a]">Could not load the buyer deck</p>
                <p className="text-xs text-[#64748b]">{deckError}</p>
                <button onClick={handleReset} className="px-4 py-2 bg-[#f1f5f9] hover:bg-[#e2e8f0] text-[#0f172a] rounded-lg text-xs font-semibold">
                  Retry
                </button>
              </div>
            ) : currentItem ? (
              <div className="rounded-2xl overflow-hidden border border-[#e2e8f0] bg-white shadow-sm transition-all duration-300 hover:shadow-md">
                <div className="relative h-64 w-full overflow-hidden bg-[#f1f5f9] flex items-center justify-center">
                  {currentItem.image_url && !imageError ? (
                    <img
                      src={currentItem.image_url}
                      alt={currentItem.name}
                      onError={() => setImageError(true)}
                      className="w-full h-full object-cover"
                    />
                  ) : (
                    <div className="flex flex-col items-center gap-1.5 text-[#94a3b8]">
                      <Package className="h-10 w-10" />
                      <span className="text-xs font-medium">No Image Available</span>
                    </div>
                  )}
                  <div className="absolute top-3 left-3 bg-white/90 backdrop-blur-sm px-2.5 py-1 rounded-full border border-[#e2e8f0] text-[10px] font-mono font-medium text-[#334155]">
                    {currentItem.category}
                  </div>
                  <div className={`absolute top-3 right-3 px-2.5 py-1 rounded-full text-[10px] font-bold text-white ${currentItem.stock > 0 ? "bg-[#047857]" : "bg-[#b91c1c]"}`}>
                    {currentItem.stock > 0 ? `${currentItem.stock} in stock` : "Out of stock"}
                  </div>
                  <div className="absolute bottom-3 left-3 flex items-center gap-1 bg-black/60 backdrop-blur-sm px-2.5 py-1 rounded-full text-[10px] font-semibold text-white">
                    <Store className="h-3 w-3" />
                    {currentItem.shop_name}
                  </div>
                </div>

                <div className="p-6 space-y-4">
                  <div className="flex items-start justify-between gap-4">
                    <div>
                      <h3 className="text-lg font-bold text-[#0f172a]">{currentItem.name}</h3>
                      <p className="text-xs text-[#64748b] mt-1 line-clamp-2">{currentItem.description}</p>
                    </div>
                    <span className="text-xl font-extrabold text-paypal-navy font-mono shrink-0">
                      ${Number(currentItem.price).toFixed(2)}
                    </span>
                  </div>

                  {currentItem.tags && currentItem.tags.length > 0 && (
                    <div className="flex flex-wrap gap-1.5">
                      {currentItem.tags.map((tag, idx) => (
                        <span key={idx} className="rounded-full bg-[#f1f5f9] px-2.5 py-0.5 text-[10px] text-[#475569] font-medium">
                          #{tag}
                        </span>
                      ))}
                    </div>
                  )}

                  <div className="pt-3 flex items-center justify-between gap-3 border-t border-[#f1f5f9]">
                    <button
                      type="button"
                      onClick={() => handleSwipe("left")}
                      className="flex-1 py-3 px-4 rounded-xl bg-[#f8fafc] hover:bg-[#f1f5f9] border border-[#e2e8f0] text-[#475569] font-semibold text-xs flex items-center justify-center gap-2 transition-all"
                    >
                      <ThumbsDown className="w-4 h-4" />
                      Pass
                    </button>
                    <button
                      type="button"
                      onClick={() => handleSwipe("right")}
                      disabled={currentItem.stock <= 0}
                      className="flex-1 py-3 px-4 rounded-xl bg-[#047857]/10 hover:bg-[#047857]/15 border border-[#047857]/30 text-[#047857] font-bold text-xs flex items-center justify-center gap-2 transition-all disabled:opacity-50 disabled:cursor-not-allowed"
                    >
                      <ShoppingCart className="w-4 h-4" />
                      {currentItem.stock <= 0 ? "Out of Stock" : "Add to Cart"}
                    </button>
                  </div>
                  {checkoutError && <p role="alert" className="text-xs text-rose-700">{checkoutError}</p>}
                  <button
                    type="button"
                    onClick={handleCheckout}
                    disabled={!buyerId || checkoutBusy || currentItem.stock < 1}
                    className="w-full py-3 px-4 rounded-xl bg-[#0070ba] hover:bg-[#005ea6] disabled:opacity-50 text-white font-bold text-xs flex items-center justify-center gap-2 transition-all"
                  >
                    {checkoutBusy ? <Loader2 className="w-4 h-4 animate-spin" /> : null}
                    {checkoutBusy ? "Opening PayPal…" : `Buy with PayPal · $${Number(currentItem.price).toFixed(2)}`}
                  </button>
                </div>
              </div>
            ) : (
              <div className="h-[460px] rounded-2xl border border-dashed border-[#cbd5e1] bg-white flex flex-col items-center justify-center gap-3 p-6 text-center">
                {deck.length === 0 && !query ? (
                  <>
                    <Package className="w-10 h-10 text-[#cbd5e1] stroke-[1.5]" />
                    <h4 className="text-sm font-bold text-[#0f172a]">No live products yet</h4>
                    <p className="text-xs text-[#64748b] max-w-xs">
                      Nothing has been approved to live status {selectedShopId === "all" ? "across any shop" : "for this shop"} yet.
                    </p>
                    <Link
                      href="/shelfswipe/seller-onboarding"
                      className="mt-1 inline-flex items-center gap-1.5 rounded-lg bg-paypal-navy px-3.5 py-1.5 text-xs font-semibold text-white hover:bg-opacity-90"
                    >
                      Go onboard &amp; approve a shop
                    </Link>
                  </>
                ) : (
                  <>
                    <CheckCircle2 className="w-10 h-10 text-[#10b981]" />
                    <h4 className="text-sm font-bold text-[#0f172a]">
                      {deck.length === 0 ? "No matching products found" : "You've seen everything!"}
                    </h4>
                    <p className="text-xs text-[#64748b]">
                      {deck.length === 0 ? "Try a broader search or clear the search box." : "Reset to go through the deck again."}
                    </p>
                    <button
                      onClick={handleReset}
                      className="mt-1 px-4 py-2 bg-[#f1f5f9] hover:bg-[#e2e8f0] text-[#0f172a] rounded-lg text-xs font-semibold"
                    >
                      Reset Deck
                    </button>
                  </>
                )}
              </div>
            )}
          </div>

          {/* Cart + PayPal-style payment */}
          <div className="lg:col-span-5 space-y-3">
            {checkoutResult && (
              <div
                role="status"
                className={`rounded-2xl border p-4 text-xs space-y-1.5 ${
                  checkoutResult.status === "CAPTURED"
                    ? "border-[#047857]/30 bg-[#047857]/10 text-[#065f46]"
                    : "border-[#f59e0b]/40 bg-[#fffbeb] text-[#92400e]"
                }`}
              >
                <p className="text-sm font-bold flex items-center gap-1.5">
                  <CheckCircle2 className="h-4 w-4" />
                  {checkoutResult.status === "CAPTURED" ? "Payment complete" : `Payment ${checkoutResult.status.toLowerCase().replace(/_/g, " ")}`}
                </p>
                {checkoutResult.product_name && <p>{checkoutResult.product_name}</p>}
                {checkoutResult.failure_reason && <p>{checkoutResult.failure_reason}</p>}
                {checkoutResult.is_simulated && <p className="opacity-80">Simulated sandbox order &mdash; no real money moved.</p>}
                <Link href={`/payments/${checkoutResult.payment_id}`} className="font-semibold underline">
                  View in PayTrace
                </Link>
              </div>
            )}
            <CartPayment
              lines={cart}
              processing={processing}
              message={checkoutMessage}
              onChangeQty={changeQty}
              onRemove={removeLine}
              onPay={handlePay}
            />
          </div>
        </div>
      </div>
    </div>
  );
}
