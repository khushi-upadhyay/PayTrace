"use client";

import React, { useState } from "react";
import Image from "next/image";
import {
  Package,
  Edit2,
  CheckCircle,
  AlertTriangle,
  Loader2,
  DollarSign,
  Layers,
} from "lucide-react";
import { ShelfSwipeDraftProductItem, shelfswipeApi } from "@/lib/shelfswipe-api";
import { ReviewFlagChip } from "./ReviewFlagChip";
import { SourceBadge } from "./SourceBadge";

interface ProductCardProps {
  product: ShelfSwipeDraftProductItem;
  sellerId: string;
  onEdit: (product: ShelfSwipeDraftProductItem) => void;
  onApproveSuccess: (productId: string, confirmedStock: number) => void;
  onProductUpdated: (product: ShelfSwipeDraftProductItem) => void;
}

export function ProductCard({
  product,
  sellerId,
  onEdit,
  onApproveSuccess,
  onProductUpdated,
}: ProductCardProps) {
  const [stockInput, setStockInput] = useState<number>(product.stock >= 0 ? product.stock : 0);
  const [approving, setApproving] = useState(false);
  const [approveError, setApproveError] = useState<string | null>(null);
  const [imageError, setImageError] = useState(false);

  const isDraft = product.status === "draft";
  const hasInvalidPrice = product.review_flags.includes("invalid_price");

  const handleApprove = async () => {
    if (stockInput < 0) {
      setApproveError("Stock must be 0 or greater.");
      return;
    }
    if (hasInvalidPrice) {
      setApproveError("Cannot approve product with invalid price ($0.00 or negative). Please edit price first.");
      return;
    }

    try {
      setApproving(true);
      setApproveError(null);
      const res = await shelfswipeApi.approveProducts(sellerId, [
        { product_id: product.id, confirmed_stock: stockInput },
      ]);
      if (res.approved.includes(product.id)) {
        onApproveSuccess(product.id, stockInput);
      } else {
        const rej = res.rejected.find((r) => r.id === product.id);
        setApproveError(`Approval rejected: ${rej?.reason || "unknown reason"}`);
      }
    } catch (err: any) {
      setApproveError(err.message || "Failed to approve product.");
    } finally {
      setApproving(false);
    }
  };

  return (
    <div className="flex flex-col rounded-xl border border-[#e2e8f0] bg-white shadow-sm overflow-hidden hover:shadow-md transition-shadow">
      {/* Product Image Banner */}
      <div className="relative h-44 w-full bg-[#f1f5f9] flex items-center justify-center border-b border-[#f1f5f9] overflow-hidden">
        {product.image_url && !imageError ? (
          <img
            src={product.image_url}
            alt={product.name}
            onError={() => setImageError(true)}
            className="h-full w-full object-cover"
          />
        ) : (
          <div className="flex flex-col items-center justify-center text-[#94a3b8] gap-1.5 p-4 text-center">
            <Package className="h-10 w-10 text-[#cbd5e1] stroke-[1.5]" />
            <span className="text-xs font-medium">No Image Available</span>
          </div>
        )}
        <div className="absolute top-2.5 right-2.5">
          <SourceBadge source={product.data_source} />
        </div>
        {product.category && (
          <div className="absolute bottom-2.5 left-2.5">
            <span className="rounded-md bg-black/60 px-2 py-0.5 text-[11px] font-semibold text-white backdrop-blur-sm">
              {product.category}
            </span>
          </div>
        )}
      </div>

      {/* Body Content */}
      <div className="flex flex-1 flex-col p-4">
        <div className="flex items-start justify-between gap-2">
          <h2 className="text-sm font-bold text-[#0f172a] line-clamp-2 leading-snug">
            {product.name}
          </h2>
          <div className="text-right shrink-0">
            <span className="text-base font-bold text-paypal-navy">
              ${Number(product.price).toFixed(2)}
            </span>
            <span className="block text-[10px] text-[#94a3b8] uppercase">{product.currency}</span>
          </div>
        </div>

        {product.description && (
          <p className="mt-1.5 text-xs text-[#64748b] line-clamp-2">
            {product.description}
          </p>
        )}

        {/* Tags */}
        {product.tags && product.tags.length > 0 && (
          <div className="mt-2.5 flex flex-wrap gap-1">
            {product.tags.map((tag, idx) => (
              <span
                key={idx}
                className="rounded bg-[#f1f5f9] px-1.5 py-0.5 text-[10px] text-[#475569] font-medium"
              >
                #{tag}
              </span>
            ))}
          </div>
        )}

        {/* Review Flags */}
        {product.review_flags && product.review_flags.length > 0 && (
          <div className="mt-3 flex flex-wrap gap-1.5 pt-2 border-t border-[#f1f5f9]">
            {product.review_flags.map((flag, idx) => (
              <ReviewFlagChip key={idx} flag={flag} />
            ))}
          </div>
        )}

        {/* Error notification */}
        {approveError && (
          <div className="mt-2.5 rounded-lg bg-[#fff1f2] p-2 text-xs text-[#be123c] flex items-start gap-1.5 border border-[#fecdd3]">
            <AlertTriangle className="h-3.5 w-3.5 shrink-0 mt-0.5" />
            <span>{approveError}</span>
          </div>
        )}

        <div className="mt-auto pt-4 flex flex-col gap-2">
          {/* Action Row */}
          {isDraft ? (
            <div className="space-y-2 pt-2 border-t border-[#f1f5f9]">
              <div>
                <label className="block text-[10px] font-semibold text-[#64748b] uppercase tracking-wider mb-0.5">
                  Confirm Stock
                </label>
                <input
                  type="number"
                  min="0"
                  value={stockInput}
                  onChange={(e) => setStockInput(Math.max(0, parseInt(e.target.value) || 0))}
                  className="w-full rounded-lg border border-[#cbd5e1] px-2.5 py-1.5 text-xs font-semibold text-[#1e293b] focus:border-paypal-blue focus:outline-none focus:ring-1 focus:ring-paypal-blue"
                />
              </div>
              <div className="flex items-center gap-2">
                <button
                  type="button"
                  onClick={handleApprove}
                  disabled={approving || hasInvalidPrice}
                  className="flex-1 inline-flex items-center justify-center gap-1.5 rounded-lg bg-[#059669] px-3 py-1.5 text-xs font-semibold text-white hover:bg-[#047857] transition-colors disabled:opacity-40 disabled:cursor-not-allowed"
                  title={hasInvalidPrice ? "Fix invalid price before approving" : "Approve and publish"}
                >
                  {approving ? (
                    <Loader2 className="h-3.5 w-3.5 animate-spin" />
                  ) : (
                    <CheckCircle className="h-3.5 w-3.5" />
                  )}
                  Approve
                </button>
                <button
                  type="button"
                  onClick={() => onEdit(product)}
                  className="inline-flex items-center gap-1 rounded-lg border border-[#cbd5e1] px-2.5 py-1.5 text-xs font-semibold text-[#334155] hover:bg-[#f8fafc] shrink-0"
                  title="Edit Product"
                >
                  <Edit2 className="h-3.5 w-3.5" />
                </button>
              </div>
            </div>
          ) : (
            <div className="flex items-center justify-between pt-2 border-t border-[#f1f5f9]">
              <div className="flex items-center gap-1.5 text-xs font-semibold text-[#047857]">
                <CheckCircle className="h-4 w-4" />
                <span>Live in store</span>
                <span className="text-[#94a3b8] ml-1">({product.stock} in stock)</span>
              </div>
              <button
                type="button"
                onClick={() => onEdit(product)}
                className="inline-flex items-center gap-1 rounded-lg border border-[#cbd5e1] px-2 py-1 text-xs font-semibold text-[#334155] hover:bg-[#f8fafc]"
              >
                <Edit2 className="h-3 w-3" />
                Edit
              </button>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

