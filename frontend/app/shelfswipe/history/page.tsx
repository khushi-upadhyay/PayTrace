"use client";

import React, { useCallback, useEffect, useState } from "react";
import Link from "next/link";
import {
  Store,
  Loader2,
  AlertCircle,
  Layers,
  Grid3x3,
  CheckCircle,
  ShoppingBag,
} from "lucide-react";
import {
  ShelfSwipeSellerSummary,
  ShelfSwipeProductWithShop,
  ApproveResponse,
  ApproveRejectedItem,
  shelfswipeApi,
} from "@/lib/shelfswipe-api";
import { ProductCard } from "@/components/shelfswipe/ProductCard";
import { ProductEditModal } from "@/components/shelfswipe/ProductEditModal";
import { ApproveResultModal } from "@/components/shelfswipe/ApproveResultModal";

export default function ShelfSwipeHistoryPage() {
  const [tab, setTab] = useState<"shops" | "products">("shops");

  const [sellers, setSellers] = useState<ShelfSwipeSellerSummary[]>([]);
  const [loadingSellers, setLoadingSellers] = useState(true);

  const [products, setProducts] = useState<ShelfSwipeProductWithShop[]>([]);
  const [loadingProducts, setLoadingProducts] = useState(true);
  const [productsError, setProductsError] = useState<string | null>(null);

  const [editingProduct, setEditingProduct] = useState<ShelfSwipeProductWithShop | null>(null);
  const [approveResult, setApproveResult] = useState<ApproveResponse | null>(null);
  const [approvingAll, setApprovingAll] = useState(false);
  const [batchError, setBatchError] = useState<string | null>(null);

  const fetchSellers = useCallback(async () => {
    try {
      setLoadingSellers(true);
      const res = await shelfswipeApi.listSellers();
      setSellers(res.sellers);
    } catch {
      // handled inline below via empty state
    } finally {
      setLoadingSellers(false);
    }
  }, []);

  const fetchProducts = useCallback(async () => {
    try {
      setLoadingProducts(true);
      setProductsError(null);
      const res = await shelfswipeApi.listAllProducts("draft");
      setProducts(res.products);
    } catch (err: any) {
      setProductsError(err.message || "Failed to load draft products across shops.");
    } finally {
      setLoadingProducts(false);
    }
  }, []);

  useEffect(() => {
    fetchSellers();
    fetchProducts();
  }, [fetchSellers, fetchProducts]);

  const handleProductUpdated = (updated: ShelfSwipeProductWithShop | any) => {
    setProducts((prev) => prev.map((p) => (p.id === updated.id ? { ...p, ...updated } : p)));
  };

  const handleSingleApproveSuccess = (productId: string) => {
    setProducts((prev) => prev.filter((p) => p.id !== productId));
  };

  const handleApproveAllAcrossShops = async () => {
    if (products.length === 0) return;
    setBatchError(null);

    const bySeller = new Map<string, ShelfSwipeProductWithShop[]>();
    for (const p of products) {
      if (p.review_flags.includes("invalid_price")) continue;
      const list = bySeller.get(p.seller_id) || [];
      list.push(p);
      bySeller.set(p.seller_id, list);
    }

    if (bySeller.size === 0) {
      setBatchError("No valid draft products available to approve. Resolve invalid prices first.");
      return;
    }

    try {
      setApprovingAll(true);
      const approved: string[] = [];
      const rejected: ApproveRejectedItem[] = [];

      await Promise.all(
        Array.from(bySeller.entries()).map(async ([sellerId, items]) => {
          const res = await shelfswipeApi.approveProducts(
            sellerId,
            items.map((p) => ({ product_id: p.id, confirmed_stock: p.stock >= 0 ? p.stock : 10 }))
          );
          approved.push(...res.approved);
          rejected.push(...res.rejected);
        })
      );

      setApproveResult({ approved, rejected, still_draft_count: 0 });
      const approvedSet = new Set(approved);
      setProducts((prev) => prev.filter((p) => !approvedSet.has(p.id)));
      fetchSellers();
    } catch (err: any) {
      setBatchError(err.message || "Failed to approve draft products across shops.");
    } finally {
      setApprovingAll(false);
    }
  };

  return (
    <div className="min-h-screen bg-[#f8fafc] text-[#0f172a] pb-16">
      <div className="border-b border-[#e2e8f0] bg-white sticky top-0 z-20">
        <div className="mx-auto max-w-6xl px-4 py-3 sm:px-6 flex items-center justify-between gap-3">
          <div className="flex items-center gap-3">
            <span className="text-xs font-bold uppercase tracking-wider text-paypal-navy hidden sm:inline">
              Onboarding History
            </span>
          </div>
          <Link
            href="/shelfswipe/buyer-onboarding"
            className="inline-flex items-center gap-1.5 rounded-full border border-[#e2e8f0] px-3 py-1.5 text-xs font-semibold text-[#334155] hover:bg-[#f8fafc]"
          >
            <ShoppingBag className="h-3.5 w-3.5 text-paypal-blue" />
            Buyer deck
          </Link>
        </div>
      </div>

      <main className="mx-auto max-w-6xl px-4 pt-6 sm:px-6 space-y-6">
        {/* Tabs */}
        <div className="flex items-center gap-2">
          <button
            type="button"
            onClick={() => setTab("shops")}
            className={`inline-flex items-center gap-2 rounded-full px-4 py-2 text-xs font-bold transition-all ${
              tab === "shops"
                ? "bg-paypal-navy text-white shadow-xs"
                : "bg-white text-[#475569] border border-[#e2e8f0] hover:bg-[#f1f5f9]"
            }`}
          >
            <Layers className="h-4 w-4" />
            By Shop
            <span
              className={`rounded-full px-2 py-0.5 text-[10px] font-bold ${
                tab === "shops" ? "bg-white/20 text-white" : "bg-[#f1f5f9] text-[#334155]"
              }`}
            >
              {sellers.length}
            </span>
          </button>
          <button
            type="button"
            onClick={() => setTab("products")}
            className={`inline-flex items-center gap-2 rounded-full px-4 py-2 text-xs font-bold transition-all ${
              tab === "products"
                ? "bg-paypal-navy text-white shadow-xs"
                : "bg-white text-[#475569] border border-[#e2e8f0] hover:bg-[#f1f5f9]"
            }`}
          >
            <Grid3x3 className="h-4 w-4" />
            All Products
            <span
              className={`rounded-full px-2 py-0.5 text-[10px] font-bold ${
                tab === "products" ? "bg-white/20 text-white" : "bg-[#f1f5f9] text-[#334155]"
              }`}
            >
              {products.length}
            </span>
          </button>

          {tab === "products" && products.length > 0 && (
            <button
              type="button"
              onClick={handleApproveAllAcrossShops}
              disabled={approvingAll}
              className="ml-auto inline-flex items-center gap-1.5 rounded-full bg-[#059669] px-4 py-2 text-xs font-bold text-white hover:bg-[#047857] transition-colors shadow-xs disabled:opacity-50"
            >
              {approvingAll ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <CheckCircle className="h-3.5 w-3.5" />}
              Approve All Valid Products (All Shops)
            </button>
          )}
        </div>

        {batchError && (
          <div className="rounded-xl border border-[#fecdd3] bg-[#fff1f2] p-3 text-xs text-[#be123c] flex items-center gap-2">
            <AlertCircle className="h-4 w-4 shrink-0" />
            <span>{batchError}</span>
          </div>
        )}

        {tab === "shops" ? (
          loadingSellers ? (
            <div className="rounded-2xl border border-[#e2e8f0] bg-white p-16 flex flex-col items-center justify-center text-[#64748b] gap-3">
              <Loader2 className="h-8 w-8 animate-spin text-paypal-blue" />
              <p className="text-sm font-semibold">Loading onboarding history...</p>
            </div>
          ) : sellers.length === 0 ? (
            <div className="rounded-2xl border border-dashed border-[#cbd5e1] bg-white p-12 text-center">
              <Store className="h-12 w-12 text-[#cbd5e1] stroke-[1.5] mx-auto mb-2" />
              <h3 className="text-sm font-bold text-[#0f172a]">No shops onboarded yet</h3>
              <p className="mt-1 text-xs text-[#64748b]">
                Head to Seller Store Onboarding to import your first catalog.
              </p>
              <Link
                href="/shelfswipe/seller-onboarding"
                className="mt-4 inline-flex items-center gap-1.5 rounded-lg bg-paypal-navy px-3.5 py-1.5 text-xs font-semibold text-white hover:bg-opacity-90"
              >
                Onboard a shop
              </Link>
            </div>
          ) : (
            <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
              {sellers.map((s) => (
                <Link
                  key={s.seller_id}
                  href={`/shelfswipe/seller/${s.seller_id}`}
                  className="flex flex-col rounded-xl border border-[#e2e8f0] bg-white p-5 shadow-sm hover:shadow-md hover:border-paypal-blue transition-all"
                >
                  <div className="flex items-center gap-2.5">
                    <div className="flex h-9 w-9 items-center justify-center rounded-lg bg-paypal-navy text-white shrink-0">
                      <Store className="h-4 w-4" />
                    </div>
                    <div className="min-w-0">
                      <span className="text-sm font-bold text-[#0f172a] block truncate">{s.shop_name}</span>
                      <span className="text-[11px] font-mono text-[#94a3b8] block truncate">{s.source_url}</span>
                    </div>
                  </div>
                  <div className="mt-3 flex items-center gap-1.5 text-[10px] font-bold">
                    <span className="rounded-full bg-[#fef3c7] px-2 py-0.5 text-[#b45309]">{s.draft_count} draft</span>
                    <span className="rounded-full bg-[#d1fae5] px-2 py-0.5 text-[#065f46]">{s.live_count} live</span>
                    {s.is_demo && (
                      <span className="rounded-full bg-[#cffafe] px-2 py-0.5 text-[#155e75]">Demo</span>
                    )}
                  </div>
                </Link>
              ))}
            </div>
          )
        ) : loadingProducts ? (
          <div className="rounded-2xl border border-[#e2e8f0] bg-white p-16 flex flex-col items-center justify-center text-[#64748b] gap-3">
            <Loader2 className="h-8 w-8 animate-spin text-paypal-blue" />
            <p className="text-sm font-semibold">Loading draft products across all shops...</p>
          </div>
        ) : productsError ? (
          <div className="rounded-2xl border border-[#fecdd3] bg-[#fff1f2] p-8 text-center text-xs text-[#be123c]">
            {productsError}
          </div>
        ) : products.length === 0 ? (
          <div className="rounded-2xl border border-dashed border-[#cbd5e1] bg-white p-12 text-center">
            <CheckCircle className="h-12 w-12 text-[#cbd5e1] stroke-[1.5] mx-auto mb-2" />
            <h3 className="text-sm font-bold text-[#0f172a]">No draft products across any shop</h3>
            <p className="mt-1 text-xs text-[#64748b]">
              Everything imported so far has already been reviewed and approved to Live.
            </p>
          </div>
        ) : (
          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-5">
            {products.map((p) => (
              <div key={p.id} className="relative">
                <span className="absolute -top-2 left-3 z-10 rounded-full bg-paypal-navy px-2 py-0.5 text-[10px] font-bold text-white shadow-sm">
                  {p.shop_name}
                </span>
                <ProductCard
                  product={p}
                  sellerId={p.seller_id}
                  onEdit={(prod) => setEditingProduct(p)}
                  onApproveSuccess={(productId) => handleSingleApproveSuccess(productId)}
                  onProductUpdated={handleProductUpdated}
                />
              </div>
            ))}
          </div>
        )}
      </main>

      {editingProduct && (
        <ProductEditModal
          product={editingProduct}
          sellerId={editingProduct.seller_id}
          onClose={() => setEditingProduct(null)}
          onUpdated={(updated) => {
            handleProductUpdated(updated);
            setEditingProduct(null);
          }}
        />
      )}

      {approveResult && (
        <ApproveResultModal result={approveResult} onClose={() => setApproveResult(null)} />
      )}
    </div>
  );
}
