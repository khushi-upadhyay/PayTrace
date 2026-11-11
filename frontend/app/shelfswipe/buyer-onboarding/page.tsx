"use client";

import React, { useCallback, useEffect, useRef, useState } from "react";
import Link from "next/link";
import {
  Search,
  ThumbsDown,
  ThumbsUp,
  Loader2,
  Package,
  CheckCircle2,
  Store,
  Compass,
  ArrowLeft,
} from "lucide-react";
import {
  BuyerDeckProductItem,
  ShelfSwipeSellerSummary,
  getOrCreateBuyerId,
  shelfswipeApi,
} from "@/lib/shelfswipe-api";
import { api } from "@/lib/api";

export default function ShelfSwipeBuyerOnboardingPage() {
  const [buyerId, setBuyerId] = useState<string | null>(null);

  const [shops, setShops] = useState<ShelfSwipeSellerSummary[]>([]);
  const [selectedShopId, setSelectedShopId] = useState<string>("all");

  const [query, setQuery] = useState("");
  const [deck, setDeck] = useState<BuyerDeckProductItem[]>([]);
  const [currentIndex, setCurrentIndex] = useState(0);
  const [loadingDeck, setLoadingDeck] = useState(true);
  const [deckError, setDeckError] = useState<string | null>(null);

  const [liked, setLiked] = useState<BuyerDeckProductItem[]>([]);
  const [imageError, setImageError] = useState(false);
  const [checkoutBusy, setCheckoutBusy] = useState(false);
  const [checkoutError, setCheckoutError] = useState<string | null>(null);

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

  const handleSwipe = async (direction: "left" | "right") => {
    if (!currentItem || !buyerId) return;
    if (direction === "right") {
      setLiked((prev) => [...prev, currentItem]);
    }
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
    setLiked([]);
  };

  return (
    <div className="min-h-screen bg-[#f8fafc] text-[#0f172a] pb-16">
      {/* Top Banner */}
      <div className="border-b border-[#e2e8f0] bg-white">
        <div className="mx-auto max-w-5xl px-4 py-4 sm:px-6 flex items-center justify-between gap-4">
          <div className="flex items-center gap-3 min-w-0">
            <Link
              href="/shelfswipe"
              className="inline-flex shrink-0 items-center gap-1 rounded-lg border border-[#cbd5e1] px-2.5 py-1.5 text-xs font-semibold text-[#334155] hover:bg-[#f1f5f9] transition-colors"
            >
              <ArrowLeft className="h-3.5 w-3.5" />
              <span>Back</span>
            </Link>
            <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-xl bg-[#047857] text-white shadow-sm">
              <Store className="h-5 w-5" />
            </div>
            <div className="min-w-0">
              <span className="text-xs font-bold uppercase tracking-wider text-paypal-blue block">ShelfSwipe</span>
              <h1 className="text-lg font-bold text-[#0f172a] truncate">Buyer Store Onboarding</h1>
            </div>
          </div>
          <Link
            href="/shelfswipe/seller-onboarding"
            className="hidden sm:flex items-center gap-1.5 rounded-full border border-[#e2e8f0] bg-[#f8fafc] px-3 py-1.5 text-xs font-semibold text-[#334155] hover:bg-[#f1f5f9] transition-colors shrink-0"
          >
            <Compass className="h-3.5 w-3.5 text-paypal-blue" />
            <span>Onboard a seller</span>
          </Link>
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
              {liked.length > 0 && <span>{liked.length} liked this session</span>}
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
                  <div className="absolute top-3 right-3 bg-[#047857] px-2.5 py-1 rounded-full text-[10px] font-bold text-white">
                    {currentItem.stock} in stock
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
                      className="flex-1 py-3 px-4 rounded-xl bg-[#047857]/10 hover:bg-[#047857]/15 border border-[#047857]/30 text-[#047857] font-bold text-xs flex items-center justify-center gap-2 transition-all"
                    >
                      <ThumbsUp className="w-4 h-4" />
                      Like
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

          {/* Liked sidebar */}
          <div className="lg:col-span-5 space-y-3">
            <div className="rounded-2xl border border-[#e2e8f0] bg-white p-5">
              <div className="flex items-center justify-between pb-3 border-b border-[#f1f5f9]">
                <h2 className="text-sm font-bold text-[#0f172a] flex items-center gap-2">
                  <ThumbsUp className="w-4 h-4 text-[#047857]" />
                  Liked this session
                </h2>
                <span className="text-[10px] text-[#94a3b8] font-mono">{liked.length}</span>
              </div>
              {liked.length === 0 ? (
                <p className="text-xs text-[#94a3b8] text-center py-8">
                  Swipe right (Like) on products you&apos;re interested in &mdash; they&apos;ll collect here.
                </p>
              ) : (
                <div className="mt-3 space-y-2 max-h-96 overflow-y-auto pr-1">
                  {liked.map((item) => (
                    <div key={item.id} className="flex items-center justify-between gap-3 rounded-xl bg-[#f8fafc] border border-[#e2e8f0] p-2.5 text-xs">
                      <div className="min-w-0">
                        <span className="font-semibold text-[#0f172a] block truncate">{item.name}</span>
                        <span className="text-[10px] text-[#94a3b8]">{item.shop_name}</span>
                      </div>
                      <span className="font-mono font-bold text-paypal-navy shrink-0">${item.price.toFixed(2)}</span>
                    </div>
                  ))}
                </div>
              )}
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
