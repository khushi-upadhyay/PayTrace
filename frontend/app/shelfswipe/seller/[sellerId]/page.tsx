"use client";

import React, { useState, useEffect, useCallback } from "react";
import { useParams, useRouter } from "next/navigation";
import Link from "next/link";
import {
  Store,
  Layers,
  CheckCircle,
  PlusCircle,
  AlertCircle,
  Loader2,
  Compass,
  ArrowLeft,
  RefreshCw,
  ShoppingBag,
} from "lucide-react";
import {
  ShelfSwipeDraftResponse,
  ShelfSwipeDraftProductItem,
  ApproveResponse,
  shelfswipeApi,
} from "@/lib/shelfswipe-api";
import { ShopCard } from "@/components/shelfswipe/ShopCard";
import { ProductCard } from "@/components/shelfswipe/ProductCard";
import { ProductEditModal } from "@/components/shelfswipe/ProductEditModal";
import { ManualProductModal } from "@/components/shelfswipe/ManualProductModal";
import { ApproveResultModal } from "@/components/shelfswipe/ApproveResultModal";

export default function SellerReviewApprovePage() {
  const params = useParams();
  const router = useRouter();
  const sellerId = typeof params?.sellerId === "string" ? params.sellerId : "";

  // Tabs: "draft" or "live"
  const [activeTab, setActiveTab] = useState<"draft" | "live">("draft");

  // Shop & Products data
  const [shopData, setShopData] = useState<ShelfSwipeDraftResponse | null>(null);
  const [products, setProducts] = useState<ShelfSwipeDraftProductItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  // Modals state
  const [editingProduct, setEditingProduct] = useState<ShelfSwipeDraftProductItem | null>(null);
  const [showManualModal, setShowManualModal] = useState(false);
  const [approveResult, setApproveResult] = useState<ApproveResponse | null>(null);

  // Batch approving
  const [approvingAll, setApprovingAll] = useState(false);
  const [batchError, setBatchError] = useState<string | null>(null);

  const fetchShopAndProducts = useCallback(
    async (tab: "draft" | "live") => {
      if (!sellerId) return;
      try {
        setLoading(true);
        setError(null);
        const data = await shelfswipeApi.getSellerDraft(sellerId, tab);
        setShopData(data);
        setProducts(data.products || []);
      } catch (err: any) {
        setError(err.message || "Failed to load seller shop or products.");
      } finally {
        setLoading(false);
      }
    },
    [sellerId]
  );

  useEffect(() => {
    fetchShopAndProducts(activeTab);
  }, [fetchShopAndProducts, activeTab]);

  const handleShopUpdated = (updated: ShelfSwipeDraftResponse) => {
    setShopData(updated);
  };

  const handleProductUpdated = (updated: ShelfSwipeDraftProductItem) => {
    setProducts((prev) => prev.map((p) => (p.id === updated.id ? updated : p)));
  };

  const handleProductCreated = (newProd: ShelfSwipeDraftProductItem) => {
    if (activeTab === "draft") {
      setProducts((prev) => [newProd, ...prev]);
    } else {
      setActiveTab("draft");
    }
  };

  const handleSingleApproveSuccess = (productId: string, confirmedStock: number) => {
    setProducts((prev) => prev.filter((p) => p.id !== productId));
  };

  const handleApproveAllValid = async () => {
    if (!products.length) return;
    setBatchError(null);

    // Filter valid products to approve (include confirmed stock)
    const itemsToApprove = products
      .filter((p) => !p.review_flags.includes("invalid_price"))
      .map((p) => ({
        product_id: p.id,
        confirmed_stock: p.stock >= 0 ? p.stock : 10,
      }));

    if (!itemsToApprove.length) {
      setBatchError("No valid draft products available to approve. Please resolve invalid prices first.");
      return;
    }

    try {
      setApprovingAll(true);
      const res = await shelfswipeApi.approveProducts(sellerId, itemsToApprove);
      setApproveResult(res);

      // Remove approved items from current draft list
      const approvedSet = new Set(res.approved);
      setProducts((prev) => prev.filter((p) => !approvedSet.has(p.id)));
    } catch (err: any) {
      setBatchError(err.message || "Failed to approve draft products.");
    } finally {
      setApprovingAll(false);
    }
  };

  return (
    <div className="min-h-screen bg-slate-50 text-slate-900 pb-16">
      {/* Top Header */}
      <div className="border-b border-slate-200 bg-white sticky top-0 z-20">
        <div className="mx-auto max-w-6xl px-4 py-3 sm:px-6 flex items-center justify-between">
          <div className="flex items-center gap-3">
            <Link
              href="/shelfswipe"
              className="inline-flex items-center gap-1 rounded-lg border border-slate-300 px-2.5 py-1.5 text-xs font-semibold text-slate-700 hover:bg-slate-100 transition-colors"
            >
              <ArrowLeft className="h-3.5 w-3.5" />
              <span>Back to Onboarding</span>
            </Link>
            <div className="h-4 w-px bg-slate-200 hidden sm:block" />
            <span className="text-xs font-bold uppercase tracking-wider text-paypal-navy hidden sm:inline">
              Catalog Readiness & Approval
            </span>
          </div>

          <div className="flex items-center gap-2">
            <button
              type="button"
              onClick={() => fetchShopAndProducts(activeTab)}
              disabled={loading}
              className="inline-flex items-center gap-1.5 rounded-lg border border-slate-300 px-2.5 py-1.5 text-xs font-semibold text-slate-700 hover:bg-slate-50 disabled:opacity-50"
              title="Refresh"
            >
              <RefreshCw className={`h-3.5 w-3.5 ${loading ? "animate-spin" : ""}`} />
              <span className="hidden sm:inline">Refresh</span>
            </button>
            <button
              type="button"
              onClick={() => setShowManualModal(true)}
              className="inline-flex items-center gap-1.5 rounded-lg bg-paypal-navy px-3 py-1.5 text-xs font-bold text-white hover:bg-opacity-90 transition-all shadow-xs"
            >
              <PlusCircle className="h-3.5 w-3.5" />
              <span>Add Product Manually</span>
            </button>
          </div>
        </div>
      </div>

      <main className="mx-auto max-w-6xl px-4 pt-6 sm:px-6 space-y-6">
        {/* Loading State */}
        {loading && !shopData ? (
          <div className="rounded-2xl border border-slate-200 bg-white p-16 flex flex-col items-center justify-center text-slate-500 gap-3">
            <Loader2 className="h-8 w-8 animate-spin text-paypal-blue" />
            <p className="text-sm font-semibold">Loading merchant catalog and shop details...</p>
          </div>
        ) : error ? (
          /* Error State */
          <div className="rounded-2xl border border-rose-200 bg-rose-50 p-8 flex flex-col items-center justify-center text-center gap-3">
            <AlertCircle className="h-10 w-10 text-rose-600" />
            <h2 className="text-base font-bold text-rose-900">Failed to Load Seller Shop</h2>
            <p className="text-xs text-rose-700 max-w-md">{error}</p>
            <button
              type="button"
              onClick={() => fetchShopAndProducts(activeTab)}
              className="mt-2 inline-flex items-center gap-1.5 rounded-lg bg-rose-600 px-4 py-2 text-xs font-bold text-white hover:bg-rose-700"
            >
              <RefreshCw className="h-3.5 w-3.5" />
              Retry Loading
            </button>
          </div>
        ) : shopData ? (
          <>
            {/* Shop Details Card */}
            <ShopCard shop={shopData} onUpdate={handleShopUpdated} />

            {/* Catalog Control Bar with Tabs */}
            <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4 pt-2">
              {/* Tab Navigation */}
              <div className="flex items-center gap-2 border-b border-slate-200 sm:border-0 pb-2 sm:pb-0">
                <button
                  type="button"
                  onClick={() => setActiveTab("draft")}
                  className={`inline-flex items-center gap-2 rounded-xl px-4 py-2 text-xs font-bold transition-all ${
                    activeTab === "draft"
                      ? "bg-paypal-navy text-white shadow-xs"
                      : "bg-white text-slate-600 border border-slate-200 hover:bg-slate-100"
                  }`}
                >
                  <Layers className="h-4 w-4" />
                  <span>Draft Review</span>
                  <span
                    className={`rounded-full px-2 py-0.5 text-[10px] font-bold ${
                      activeTab === "draft"
                        ? "bg-white/20 text-white"
                        : "bg-slate-100 text-slate-700"
                    }`}
                  >
                    {activeTab === "draft" ? products.length : ""}
                  </span>
                </button>

                <button
                  type="button"
                  onClick={() => setActiveTab("live")}
                  className={`inline-flex items-center gap-2 rounded-xl px-4 py-2 text-xs font-bold transition-all ${
                    activeTab === "live"
                      ? "bg-emerald-700 text-white shadow-xs"
                      : "bg-white text-slate-600 border border-slate-200 hover:bg-slate-100"
                  }`}
                >
                  <CheckCircle className="h-4 w-4 text-emerald-300" />
                  <span>Live Store</span>
                  <span
                    className={`rounded-full px-2 py-0.5 text-[10px] font-bold ${
                      activeTab === "live"
                        ? "bg-white/20 text-white"
                        : "bg-slate-100 text-slate-700"
                    }`}
                  >
                    {activeTab === "live" ? products.length : ""}
                  </span>
                </button>
              </div>

              {/* Batch Approve Action (Draft Tab only) */}
              {activeTab === "draft" && products.length > 0 && (
                <div className="flex items-center gap-2">
                  <button
                    type="button"
                    onClick={handleApproveAllValid}
                    disabled={approvingAll}
                    className="inline-flex items-center gap-1.5 rounded-xl bg-emerald-600 px-4 py-2 text-xs font-bold text-white hover:bg-emerald-700 transition-colors shadow-xs disabled:opacity-50"
                  >
                    {approvingAll ? (
                      <Loader2 className="h-3.5 w-3.5 animate-spin" />
                    ) : (
                      <CheckCircle className="h-3.5 w-3.5" />
                    )}
                    <span>Approve All Valid Products</span>
                  </button>
                </div>
              )}
            </div>

            {/* Batch error notification */}
            {batchError && (
              <div className="rounded-xl border border-rose-200 bg-rose-50 p-3 text-xs text-rose-700 flex items-center gap-2">
                <AlertCircle className="h-4 w-4 shrink-0" />
                <span>{batchError}</span>
              </div>
            )}

            {/* Products Grid / Empty States */}
            {products.length === 0 ? (
              <div className="rounded-2xl border border-dashed border-slate-300 bg-white p-12 text-center">
                {activeTab === "draft" ? (
                  <div className="flex flex-col items-center justify-center max-w-sm mx-auto text-slate-500">
                    <ShoppingBag className="h-12 w-12 text-slate-300 stroke-[1.5] mb-2" />
                    <h3 className="text-sm font-bold text-slate-900">No Draft Products</h3>
                    <p className="mt-1 text-xs text-slate-500">
                      All products in this catalog have been reviewed and approved to Live status, or
                      none have been imported yet.
                    </p>
                    <button
                      type="button"
                      onClick={() => setShowManualModal(true)}
                      className="mt-4 inline-flex items-center gap-1.5 rounded-lg bg-paypal-navy px-3.5 py-1.5 text-xs font-semibold text-white hover:bg-opacity-90"
                    >
                      <PlusCircle className="h-3.5 w-3.5" />
                      Add Product Manually
                    </button>
                  </div>
                ) : (
                  <div className="flex flex-col items-center justify-center max-w-sm mx-auto text-slate-500">
                    <CheckCircle className="h-12 w-12 text-slate-300 stroke-[1.5] mb-2" />
                    <h3 className="text-sm font-bold text-slate-900">No Live Products Yet</h3>
                    <p className="mt-1 text-xs text-slate-500">
                      Confirm stock and approve draft products in the Draft tab to make them available
                      in your live ShelfSwipe local catalog.
                    </p>
                    <button
                      type="button"
                      onClick={() => setActiveTab("draft")}
                      className="mt-4 inline-flex items-center gap-1.5 rounded-lg border border-slate-300 px-3.5 py-1.5 text-xs font-semibold text-slate-700 hover:bg-slate-50"
                    >
                      <Layers className="h-3.5 w-3.5" />
                      Go to Draft Review
                    </button>
                  </div>
                )}
              </div>
            ) : (
              <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-5">
                {products.map((p) => (
                  <ProductCard
                    key={p.id}
                    product={p}
                    sellerId={sellerId}
                    onEdit={(prod) => setEditingProduct(prod)}
                    onApproveSuccess={handleSingleApproveSuccess}
                    onProductUpdated={handleProductUpdated}
                  />
                ))}
              </div>
            )}
          </>
        ) : null}

        {/* Small Bottom Note */}
        <div className="mt-12 text-center text-xs text-slate-400 flex items-center justify-center gap-1.5">
          <Compass className="h-3.5 w-3.5" />
          <span>Buyer deck: coming next</span>
        </div>
      </main>

      {/* Product Edit Modal */}
      {editingProduct && (
        <ProductEditModal
          product={editingProduct}
          sellerId={sellerId}
          onClose={() => setEditingProduct(null)}
          onUpdated={handleProductUpdated}
        />
      )}

      {/* Manual Product Add Modal */}
      {showManualModal && (
        <ManualProductModal
          sellerId={sellerId}
          onClose={() => setShowManualModal(false)}
          onCreated={handleProductCreated}
        />
      )}

      {/* Approve Result Modal */}
      {approveResult && (
        <ApproveResultModal
          result={approveResult}
          onClose={() => setApproveResult(null)}
        />
      )}
    </div>
  );
}

