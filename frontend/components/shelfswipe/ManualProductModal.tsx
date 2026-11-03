"use client";

import React, { useState } from "react";
import { X, Plus, AlertCircle, Loader2 } from "lucide-react";
import { ShelfSwipeDraftProductItem, shelfswipeApi } from "@/lib/shelfswipe-api";

interface ManualProductModalProps {
  sellerId: string;
  onClose: () => void;
  onCreated: (newProduct: ShelfSwipeDraftProductItem) => void;
}

export function ManualProductModal({
  sellerId,
  onClose,
  onCreated,
}: ManualProductModalProps) {
  const [name, setName] = useState("");
  const [price, setPrice] = useState("");
  const [stock, setStock] = useState("10");
  const [category, setCategory] = useState("General");
  const [tags, setTags] = useState("");
  const [description, setDescription] = useState("");
  const [imageUrl, setImageUrl] = useState("");
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError(null);

    if (!name.trim()) {
      setError("Product name is required.");
      return;
    }

    const priceNum = parseFloat(price);
    if (isNaN(priceNum) || priceNum < 0) {
      setError("Price must be a valid number ($0.00 or greater).");
      return;
    }

    const stockNum = parseInt(stock);
    if (isNaN(stockNum) || stockNum < 0) {
      setError("Stock must be 0 or greater.");
      return;
    }

    const tagsList = tags
      .split(",")
      .map((t) => t.trim().toLowerCase())
      .filter((t) => t.length > 0);

    try {
      setSaving(true);
      const res = await shelfswipeApi.createProduct(sellerId, {
        name: name.trim(),
        price: priceNum,
        stock: stockNum,
        category: category.trim() || "General",
        tags: tagsList,
        description: description.trim(),
        image_url: imageUrl.trim() || null,
      });
      onCreated(res);
      onClose();
    } catch (err: any) {
      setError(err.message || "Failed to create manual product.");
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-slate-900/50 p-4 backdrop-blur-xs">
      <div className="w-full max-w-lg rounded-2xl bg-white shadow-2xl border border-slate-200 overflow-hidden flex flex-col max-h-[90vh]">
        {/* Header */}
        <div className="flex items-center justify-between border-b border-slate-100 px-6 py-4">
          <div>
            <h2 className="text-base font-bold text-slate-900">Add Product Manually</h2>
            <p className="text-xs text-slate-500">Create a new local merchant catalog item</p>
          </div>
          <button
            onClick={onClose}
            className="rounded-lg p-1 text-slate-400 hover:bg-slate-100 hover:text-slate-600"
          >
            <X className="h-5 w-5" />
          </button>
        </div>

        {/* Form Body */}
        <form onSubmit={handleSubmit} className="flex-1 overflow-y-auto p-6 space-y-4">
          {error && (
            <div className="rounded-lg bg-rose-50 border border-rose-200 p-3 text-xs text-rose-700 flex items-center gap-2">
              <AlertCircle className="h-4 w-4 shrink-0" />
              <span>{error}</span>
            </div>
          )}

          <div>
            <label className="block text-xs font-semibold text-slate-700 mb-1">
              Product Name <span className="text-rose-500">*</span>
            </label>
            <input
              type="text"
              required
              value={name}
              onChange={(e) => setName(e.target.value)}
              placeholder="e.g. Handmade Ceramic Matcha Bowl"
              className="w-full rounded-lg border border-slate-300 px-3 py-2 text-sm focus:border-paypal-blue focus:outline-none focus:ring-1 focus:ring-paypal-blue"
            />
          </div>

          <div className="grid grid-cols-2 gap-3">
            <div>
              <label className="block text-xs font-semibold text-slate-700 mb-1">
                Price (USD) <span className="text-rose-500">*</span>
              </label>
              <input
                type="number"
                step="0.01"
                min="0"
                required
                value={price}
                onChange={(e) => setPrice(e.target.value)}
                placeholder="24.99"
                className="w-full rounded-lg border border-slate-300 px-3 py-2 text-sm focus:border-paypal-blue focus:outline-none focus:ring-1 focus:ring-paypal-blue"
              />
            </div>
            <div>
              <label className="block text-xs font-semibold text-slate-700 mb-1">
                Initial Stock <span className="text-rose-500">*</span>
              </label>
              <input
                type="number"
                min="0"
                required
                value={stock}
                onChange={(e) => setStock(e.target.value)}
                placeholder="10"
                className="w-full rounded-lg border border-slate-300 px-3 py-2 text-sm focus:border-paypal-blue focus:outline-none focus:ring-1 focus:ring-paypal-blue"
              />
            </div>
          </div>

          <div className="grid grid-cols-2 gap-3">
            <div>
              <label className="block text-xs font-semibold text-slate-700 mb-1">Category</label>
              <input
                type="text"
                value={category}
                onChange={(e) => setCategory(e.target.value)}
                placeholder="Kitchen & Pottery"
                className="w-full rounded-lg border border-slate-300 px-3 py-2 text-sm focus:border-paypal-blue focus:outline-none focus:ring-1 focus:ring-paypal-blue"
              />
            </div>
            <div>
              <label className="block text-xs font-semibold text-slate-700 mb-1">
                Tags <span className="text-slate-400 font-normal">(comma-separated)</span>
              </label>
              <input
                type="text"
                value={tags}
                onChange={(e) => setTags(e.target.value)}
                placeholder="handmade, artisan, gift"
                className="w-full rounded-lg border border-slate-300 px-3 py-2 text-sm focus:border-paypal-blue focus:outline-none focus:ring-1 focus:ring-paypal-blue"
              />
            </div>
          </div>

          <div>
            <label className="block text-xs font-semibold text-slate-700 mb-1">Image URL</label>
            <input
              type="url"
              value={imageUrl}
              onChange={(e) => setImageUrl(e.target.value)}
              placeholder="https://images.unsplash.com/..."
              className="w-full rounded-lg border border-slate-300 px-3 py-2 text-sm focus:border-paypal-blue focus:outline-none focus:ring-1 focus:ring-paypal-blue"
            />
          </div>

          <div>
            <label className="block text-xs font-semibold text-slate-700 mb-1">Description</label>
            <textarea
              rows={3}
              value={description}
              onChange={(e) => setDescription(e.target.value)}
              placeholder="Detailed product description, materials, sizing..."
              className="w-full rounded-lg border border-slate-300 px-3 py-2 text-sm focus:border-paypal-blue focus:outline-none focus:ring-1 focus:ring-paypal-blue"
            />
          </div>

          {/* Footer Actions */}
          <div className="flex items-center justify-end gap-2 pt-4 border-t border-slate-100">
            <button
              type="button"
              onClick={onClose}
              className="rounded-lg border border-slate-300 px-4 py-2 text-xs font-semibold text-slate-700 hover:bg-slate-50"
            >
              Cancel
            </button>
            <button
              type="submit"
              disabled={saving}
              className="inline-flex items-center gap-1.5 rounded-lg bg-paypal-navy px-4 py-2 text-xs font-semibold text-white hover:bg-opacity-90 disabled:opacity-50"
            >
              {saving ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <Plus className="h-3.5 w-3.5" />}
              Create Product
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}

