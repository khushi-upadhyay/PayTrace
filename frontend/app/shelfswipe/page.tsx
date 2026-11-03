"use client";

import React, { useState, useEffect } from "react";
import { useRouter } from "next/navigation";
import Link from "next/link";
import {
  Store,
  Sparkles,
  Globe,
  CheckCircle,
  AlertCircle,
  Loader2,
  ArrowRight,
  Clock,
  WifiOff,
  ShieldCheck,
  PlusCircle,
  Compass,
} from "lucide-react";
import {
  DemoShopItem,
  ShelfSwipeApiError,
  shelfswipeApi,
} from "@/lib/shelfswipe-api";

const LAST_SELLER_KEY = "paytrace_shelfswipe_last_seller_id";

export default function ShelfSwipeOnboardingPage() {
  const router = useRouter();

  // Mode: "demo" (Demo shops) or "channel3" (My own products via Channel3)
  const [mode, setMode] = useState<"demo" | "channel3">("demo");

  // Demo Shops state
  const [demoShops, setDemoShops] = useState<DemoShopItem[]>([]);
  const [loadingShops, setLoadingShops] = useState(true);
  const [shopsError, setShopsError] = useState<string | null>(null);
  const [selectedDemoUrl, setSelectedDemoUrl] = useState<string>("");

  // Channel3 form state
  const [shopUrl, setShopUrl] = useState<string>("https://aprikamatcha.com");
  const [productLinksText, setProductLinksText] = useState<string>("");

  // Consent & Attestation Checkbox
  const [ticked, setTicked] = useState(false);

  // Submission state
  const [submitting, setSubmitting] = useState(false);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);
  const [errorCode, setErrorCode] = useState<number | null>(null);

  // Remembered seller
  const [lastSellerId, setLastSellerId] = useState<string | null>(null);

  useEffect(() => {
    try {
      const stored = localStorage.getItem(LAST_SELLER_KEY);
      if (stored) setLastSellerId(stored);
    } catch {
      // storage unavailable
    }
  }, []);

  // Fetch demo shops
  useEffect(() => {
    let active = true;
    async function loadDemoShops() {
      try {
        setLoadingShops(true);
        setShopsError(null);
        const shops = await shelfswipeApi.getDemoShops();
        if (active) {
          setDemoShops(shops);
          if (shops.length > 0) {
            setSelectedDemoUrl(shops[0].url);
          }
        }
      } catch (err: any) {
        if (active) {
          setShopsError(err.message || "Unable to load demo shop catalog.");
        }
      } finally {
        if (active) setLoadingShops(false);
      }
    }
    loadDemoShops();
    return () => {
      active = false;
    };
  }, []);

  // Reset checkbox when switching modes
  const handleModeChange = (newMode: "demo" | "channel3") => {
    setMode(newMode);
    setTicked(false);
    setErrorMessage(null);
    setErrorCode(null);
  };

  const parseProductUrls = (raw: string): string[] => {
    return raw
      .split("\n")
      .map((line) => line.trim())
      .filter((line) => line.startsWith("http://") || line.startsWith("https://"))
      .slice(0, 20);
  };

  const handleOnboardSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setErrorMessage(null);
    setErrorCode(null);

    const targetShopUrl = mode === "demo" ? selectedDemoUrl : shopUrl.trim();

    if (!targetShopUrl) {
      setErrorMessage("Please specify a valid shop URL.");
      return;
    }

    const productUrls = mode === "channel3" ? parseProductUrls(productLinksText) : undefined;

    try {
      setSubmitting(true);
      const res = await shelfswipeApi.onboardSeller({
        shop_url: targetShopUrl,
        consent: true,
        ownership_attested: mode === "channel3" ? ticked : false,
        provider: mode === "channel3" ? "channel3" : "fixture",
        product_urls: productUrls && productUrls.length > 0 ? productUrls : undefined,
      });

      // Remember seller ID in localStorage as convenience
      try {
        localStorage.setItem(LAST_SELLER_KEY, res.seller_id);
      } catch {
        // storage ignored
      }

      // Redirect to review & approve screen
      router.push(`/shelfswipe/seller/${res.seller_id}`);
    } catch (err: any) {
      const status = err instanceof ShelfSwipeApiError ? err.status : 0;
      setErrorCode(status);

      if (status === 400) {
        setErrorMessage(
          mode === "channel3"
            ? "Ownership attestation is required. You must attest that you own or are authorised to list products for this shop."
            : "Consent is required to import this catalog."
        );
      } else if (status === 422) {
        setErrorMessage(
          err.message ||
            "No usable products were found for this store domain or URL. You can try a demo shop or add products manually."
        );
      } else if (status === 429) {
        setErrorMessage(
          "Channel3 rate limit exceeded. The provider is temporarily rate limiting requests. Please wait a moment and try again."
        );
      } else if (status === 502) {
        setErrorMessage(
          "Catalog provider service is currently unavailable. Please check your network or try again shortly."
        );
      } else {
        setErrorMessage(err.message || "Failed to onboard merchant shop.");
      }
    } finally {
      setSubmitting(false);
    }
  };

  const handleTryDemoShop = () => {
    handleModeChange("demo");
    if (demoShops.length > 0) {
      setSelectedDemoUrl(demoShops[0].url);
    }
    setTicked(true);
  };

  const handleAddProductsManually = async () => {
    // If we have a last remembered seller, go there
    if (lastSellerId) {
      router.push(`/shelfswipe/seller/${lastSellerId}`);
      return;
    }
    // Otherwise onboard the first demo shop so seller and shop exist, then redirect
    if (demoShops.length > 0) {
      try {
        setSubmitting(true);
        const res = await shelfswipeApi.onboardSeller({
          shop_url: demoShops[0].url,
          consent: true,
          ownership_attested: false,
          provider: "fixture",
        });
        try {
          localStorage.setItem(LAST_SELLER_KEY, res.seller_id);
        } catch {}
        router.push(`/shelfswipe/seller/${res.seller_id}`);
      } catch (err: any) {
        setErrorMessage("Unable to initialize seller shop. Please select a demo shop below.");
      } finally {
        setSubmitting(false);
      }
    }
  };

  return (
    <div className="min-h-screen bg-slate-50 text-slate-900 pb-16">
      {/* Top Banner / Breadcrumb */}
      <div className="border-b border-slate-200 bg-white">
        <div className="mx-auto max-w-5xl px-4 py-4 sm:px-6 flex items-center justify-between">
          <div className="flex items-center gap-3">
            <div className="flex h-10 w-10 items-center justify-center rounded-xl bg-paypal-navy text-white shadow-sm">
              <Store className="h-5 w-5" />
            </div>
            <div>
              <div className="flex items-center gap-2">
                <span className="text-xs font-bold uppercase tracking-wider text-paypal-blue">
                  ShelfSwipe Merchant
                </span>
                <span className="rounded-full bg-cyan-100 px-2 py-0.5 text-[10px] font-bold text-cyan-800">
                  Onboarding
                </span>
              </div>
              <h1 className="text-lg font-bold text-slate-900">Seller Store Onboarding</h1>
            </div>
          </div>

          {/* Coming Next note */}
          <div className="hidden sm:flex items-center gap-1.5 rounded-full border border-slate-200 bg-slate-50 px-3 py-1 text-xs text-slate-500">
            <Compass className="h-3.5 w-3.5 text-slate-400" />
            <span>Buyer deck: coming next</span>
          </div>
        </div>
      </div>

      <div className="mx-auto max-w-3xl px-4 pt-8 sm:px-6">
        {/* Remembered Seller Alert */}
        {lastSellerId && (
          <div className="mb-6 rounded-xl border border-blue-200 bg-blue-50/70 p-4 flex items-center justify-between gap-3 shadow-xs">
            <div className="flex items-center gap-2.5 text-xs text-blue-900">
              <CheckCircle className="h-4 w-4 text-paypal-blue shrink-0" />
              <span>
                You have a recently onboarded shop (ID:{" "}
                <code className="font-mono font-semibold">{lastSellerId.slice(0, 8)}...</code>).
              </span>
            </div>
            <Link
              href={`/shelfswipe/seller/${lastSellerId}`}
              className="inline-flex items-center gap-1 text-xs font-bold text-paypal-blue hover:underline shrink-0"
            >
              Continue to Review & Approve
              <ArrowRight className="h-3.5 w-3.5" />
            </Link>
          </div>
        )}

        {/* Main Card */}
        <div className="rounded-2xl border border-slate-200 bg-white p-6 sm:p-8 shadow-sm">
          <div className="max-w-xl">
            <h2 className="text-xl font-bold text-slate-900">Import your merchant catalog</h2>
            <p className="mt-1 text-sm text-slate-600">
              Select a pre-built demo catalog or connect your online store via Channel3 to import
              products, review readiness flags, and confirm local pickup stock.
            </p>
          </div>

          {/* Data Source Selector Tabs */}
          <div className="mt-6 grid grid-cols-2 gap-3 p-1 rounded-xl bg-slate-100 border border-slate-200">
            <button
              type="button"
              onClick={() => handleModeChange("demo")}
              className={`flex items-center justify-center gap-2 rounded-lg py-2.5 px-3 text-xs font-bold transition-all ${
                mode === "demo"
                  ? "bg-white text-paypal-navy shadow-sm"
                  : "text-slate-600 hover:text-slate-900"
              }`}
            >
              <Sparkles className="h-4 w-4 text-amber-500" />
              Demo shops
            </button>
            <button
              type="button"
              onClick={() => handleModeChange("channel3")}
              className={`flex items-center justify-center gap-2 rounded-lg py-2.5 px-3 text-xs font-bold transition-all ${
                mode === "channel3"
                  ? "bg-white text-paypal-navy shadow-sm"
                  : "text-slate-600 hover:text-slate-900"
              }`}
            >
              <Globe className="h-4 w-4 text-paypal-blue" />
              My own products via Channel3
            </button>
          </div>

          {/* Form */}
          <form onSubmit={handleOnboardSubmit} className="mt-6 space-y-5">
            {mode === "demo" ? (
              /* Demo Shops Picker */
              <div className="space-y-3">
                <label className="block text-xs font-bold uppercase tracking-wider text-slate-700">
                  Select a Curated Demo Shop
                </label>

                {loadingShops ? (
                  <div className="rounded-xl border border-slate-200 p-8 flex flex-col items-center justify-center text-slate-500 gap-2">
                    <Loader2 className="h-6 w-6 animate-spin text-paypal-blue" />
                    <span className="text-xs">Loading available demo shops...</span>
                  </div>
                ) : shopsError ? (
                  <div className="rounded-xl border border-rose-200 bg-rose-50 p-4 text-xs text-rose-700 flex items-center gap-2">
                    <AlertCircle className="h-4 w-4 shrink-0" />
                    <span>{shopsError}</span>
                  </div>
                ) : demoShops.length === 0 ? (
                  <div className="rounded-xl border border-slate-200 p-6 text-center text-xs text-slate-500">
                    No demo shops returned from server.
                  </div>
                ) : (
                  <div className="space-y-2 max-h-64 overflow-y-auto pr-1">
                    {demoShops.map((shop) => (
                      <label
                        key={shop.id}
                        className={`flex items-start gap-3 rounded-xl border p-3.5 cursor-pointer transition-colors ${
                          selectedDemoUrl === shop.url
                            ? "border-paypal-blue bg-blue-50/50 ring-1 ring-paypal-blue"
                            : "border-slate-200 hover:bg-slate-50"
                        }`}
                      >
                        <input
                          type="radio"
                          name="demoShop"
                          value={shop.url}
                          checked={selectedDemoUrl === shop.url}
                          onChange={() => setSelectedDemoUrl(shop.url)}
                          className="mt-0.5 text-paypal-blue focus:ring-paypal-blue"
                        />
                        <div className="flex-1 min-w-0">
                          <div className="flex items-center justify-between">
                            <span className="text-sm font-bold text-slate-900">{shop.name}</span>
                            <span className="rounded bg-slate-100 px-2 py-0.5 text-[10px] font-semibold text-slate-600">
                              {shop.item_count || 5} items
                            </span>
                          </div>
                          {shop.description && (
                            <p className="text-xs text-slate-500 mt-0.5 line-clamp-1">
                              {shop.description}
                            </p>
                          )}
                          <span className="text-[11px] font-mono text-slate-400 mt-1 block truncate">
                            {shop.url}
                          </span>
                        </div>
                      </label>
                    ))}
                  </div>
                )}
              </div>
            ) : (
              /* Channel3 Store Input */
              <div className="space-y-4">
                <div>
                  <label className="block text-xs font-bold uppercase tracking-wider text-slate-700 mb-1">
                    Store URL <span className="text-rose-500">*</span>
                  </label>
                  <input
                    type="url"
                    required
                    value={shopUrl}
                    onChange={(e) => setShopUrl(e.target.value)}
                    placeholder="https://yourstore.com"
                    className="w-full rounded-xl border border-slate-300 px-3.5 py-2.5 text-sm focus:border-paypal-blue focus:outline-none focus:ring-1 focus:ring-paypal-blue"
                  />
                  <p className="mt-1 text-[11px] text-slate-500">
                    Channel3 filters against catalog website domains (e.g. aprikamatcha.com, abchome.com).
                  </p>
                </div>

                <div>
                  <label className="block text-xs font-bold uppercase tracking-wider text-slate-700 mb-1">
                    Optional Product Links <span className="text-slate-400 font-normal">(max 20, one per line)</span>
                  </label>
                  <textarea
                    rows={4}
                    value={productLinksText}
                    onChange={(e) => setProductLinksText(e.target.value)}
                    placeholder="https://yourstore.com/products/item-1&#10;https://yourstore.com/products/item-2"
                    className="w-full rounded-xl border border-slate-300 px-3.5 py-2.5 text-xs font-mono focus:border-paypal-blue focus:outline-none focus:ring-1 focus:ring-paypal-blue"
                  />
                  <p className="mt-1 text-[11px] text-slate-500">
                    If left empty, ShelfSwipe automatically executes store-wide catalog import using website filtering.
                  </p>
                </div>
              </div>
            )}

            {/* Checkbox Section */}
            <div className="pt-2">
              <label className="flex items-start gap-3 rounded-xl border border-slate-200 bg-slate-50 p-4 cursor-pointer hover:bg-slate-100/60 transition-colors">
                <input
                  type="checkbox"
                  checked={ticked}
                  onChange={(e) => setTicked(e.target.checked)}
                  className="mt-0.5 h-4 w-4 rounded border-slate-300 text-paypal-blue focus:ring-paypal-blue"
                />
                <span className="text-xs font-medium text-slate-700 leading-relaxed">
                  {mode === "demo" ? (
                    <>
                      <strong>I consent to importing this demo catalog</strong> into PayTrace ShelfSwipe
                      for sandbox verification and testing purposes.
                    </>
                  ) : (
                    <>
                      <strong>I own or am authorised to list these products</strong> on ShelfSwipe and agree
                      to extract catalog details via Channel3 for merchant review.
                    </>
                  )}
                </span>
              </label>
            </div>

            {/* Error Message with Mapped Action Buttons */}
            {errorMessage && (
              <div className="rounded-xl border border-rose-200 bg-rose-50 p-4 space-y-3">
                <div className="flex items-start gap-2.5 text-xs text-rose-800">
                  {errorCode === 429 ? (
                    <Clock className="h-4 w-4 shrink-0 mt-0.5 text-rose-600" />
                  ) : errorCode === 502 ? (
                    <WifiOff className="h-4 w-4 shrink-0 mt-0.5 text-rose-600" />
                  ) : (
                    <AlertCircle className="h-4 w-4 shrink-0 mt-0.5 text-rose-600" />
                  )}
                  <div className="flex-1">
                    <p className="font-semibold">
                      {errorCode === 400
                        ? "Attestation / Consent Error"
                        : errorCode === 422
                        ? "Catalog Not Found"
                        : errorCode === 429
                        ? "Channel3 Rate Limited"
                        : errorCode === 502
                        ? "Provider Unavailable"
                        : "Onboarding Error"}
                    </p>
                    <p className="mt-0.5">{errorMessage}</p>
                  </div>
                </div>

                {/* Specific 422 recovery buttons */}
                {errorCode === 422 && (
                  <div className="flex flex-wrap items-center gap-2 pt-1 border-t border-rose-200/60">
                    <button
                      type="button"
                      onClick={handleTryDemoShop}
                      className="inline-flex items-center gap-1.5 rounded-lg bg-white px-3 py-1.5 text-xs font-bold text-slate-800 border border-slate-300 hover:bg-slate-50 shadow-xs"
                    >
                      <Sparkles className="h-3.5 w-3.5 text-amber-500" />
                      Try a demo shop
                    </button>
                    <button
                      type="button"
                      onClick={handleAddProductsManually}
                      className="inline-flex items-center gap-1.5 rounded-lg bg-paypal-navy px-3 py-1.5 text-xs font-bold text-white hover:bg-opacity-90 shadow-xs"
                    >
                      <PlusCircle className="h-3.5 w-3.5" />
                      Add products manually
                    </button>
                  </div>
                )}
              </div>
            )}

            {/* Submit Button */}
            <div className="pt-2">
              <button
                type="submit"
                disabled={!ticked || submitting || (mode === "demo" && loadingShops)}
                className="w-full flex items-center justify-center gap-2 rounded-xl bg-paypal-navy py-3 px-4 text-sm font-bold text-white shadow-sm hover:bg-opacity-90 transition-all disabled:opacity-40 disabled:cursor-not-allowed"
              >
                {submitting ? (
                  <>
                    <Loader2 className="h-4 w-4 animate-spin" />
                    <span>Importing & Normalizing Catalog...</span>
                  </>
                ) : (
                  <>
                    <ShieldCheck className="h-4 w-4" />
                    <span>Continue to Review & Approval</span>
                    <ArrowRight className="h-4 w-4" />
                  </>
                )}
              </button>
              {!ticked && (
                <p className="text-center text-[11px] text-slate-400 mt-2">
                  Please tick the attestation checkbox above to enable import.
                </p>
              )}
            </div>
          </form>
        </div>

        {/* Small Bottom Note */}
        <div className="mt-8 text-center text-xs text-slate-400 flex items-center justify-center gap-1.5">
          <Compass className="h-3.5 w-3.5" />
          <span>Buyer deck: coming next</span>
        </div>
      </div>
    </div>
  );
}
