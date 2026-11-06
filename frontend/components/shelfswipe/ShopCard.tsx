"use client";

import React, { useState } from "react";
import { MapPin, Edit3, Check, X, Store, AlertCircle } from "lucide-react";
import { ShelfSwipeDraftResponse, shelfswipeApi } from "@/lib/shelfswipe-api";
import { SourceBadge } from "./SourceBadge";

interface ShopCardProps {
  shop: ShelfSwipeDraftResponse;
  onUpdate: (updated: ShelfSwipeDraftResponse) => void;
}

export function ShopCard({ shop, onUpdate }: ShopCardProps) {
  const [editing, setEditing] = useState(false);
  const [pickupNotes, setPickupNotes] = useState(shop.pickup_notes || "");
  const [latitude, setLatitude] = useState(shop.latitude !== null ? String(shop.latitude) : "");
  const [longitude, setLongitude] = useState(shop.longitude !== null ? String(shop.longitude) : "");
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const startEdit = () => {
    setPickupNotes(shop.pickup_notes || "");
    setLatitude(shop.latitude !== null ? String(shop.latitude) : "");
    setLongitude(shop.longitude !== null ? String(shop.longitude) : "");
    setError(null);
    setEditing(true);
  };

  const handleSave = async (e: React.FormEvent) => {
    e.preventDefault();
    setError(null);

    let latNum: number | undefined = undefined;
    let lngNum: number | undefined = undefined;

    if (latitude.trim() !== "") {
      latNum = parseFloat(latitude.trim());
      if (isNaN(latNum) || latNum < -90 || latNum > 90) {
        setError("Latitude must be a valid number between -90 and 90.");
        return;
      }
    }

    if (longitude.trim() !== "") {
      lngNum = parseFloat(longitude.trim());
      if (isNaN(lngNum) || lngNum < -180 || lngNum > 180) {
        setError("Longitude must be a valid number between -180 and 180.");
        return;
      }
    }

    try {
      setSaving(true);
      const res = await shelfswipeApi.patchShop(shop.seller_id, {
        pickup_notes: pickupNotes.trim(),
        latitude: latNum,
        longitude: lngNum,
      });
      onUpdate(res);
      setEditing(false);
    } catch (err: any) {
      setError(err.message || "Failed to update shop details.");
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className="rounded-xl border border-[#e2e8f0] bg-white p-6 shadow-sm">
      <div className="flex flex-col sm:flex-row sm:items-start sm:justify-between gap-4">
        <div className="space-y-1">
          <div className="flex items-center gap-2.5">
            <div className="flex h-10 w-10 items-center justify-center rounded-lg bg-paypal-navy text-white">
              <Store className="h-5 w-5" />
            </div>
            <div>
              <h1 className="text-xl font-bold text-[#0f172a]">{shop.name}</h1>
              <div className="flex items-center gap-2 mt-0.5">
                <SourceBadge source={shop.is_demo ? "demo" : "channel3"} />
                <span className="text-xs text-[#64748b]">Seller ID: {shop.seller_id}</span>
              </div>
            </div>
          </div>
          {shop.description && (
            <p className="text-sm text-[#475569] mt-2 max-w-2xl">{shop.description}</p>
          )}
        </div>

        {!editing && (
          <button
            type="button"
            onClick={startEdit}
            className="inline-flex items-center gap-1.5 self-start rounded-lg border border-[#cbd5e1] px-3 py-1.5 text-xs font-semibold text-[#334155] hover:bg-[#f8fafc] transition-colors"
          >
            <Edit3 className="h-3.5 w-3.5" />
            Edit Location & Notes
          </button>
        )}
      </div>

      {!editing ? (
        <div className="mt-4 pt-4 border-t border-[#f1f5f9] grid grid-cols-1 sm:grid-cols-2 gap-4 text-xs">
          <div>
            <span className="font-semibold text-[#64748b] uppercase tracking-wider block">Pickup Notes</span>
            <span className="text-[#1e293b] text-sm mt-0.5 block">
              {shop.pickup_notes || "No pickup notes set"}
            </span>
          </div>
          <div>
            <span className="font-semibold text-[#64748b] uppercase tracking-wider block">Coordinates</span>
            <span className="text-[#1e293b] text-sm mt-0.5 flex items-center gap-1">
              <MapPin className="h-3.5 w-3.5 text-[#94a3b8]" />
              {shop.latitude !== null && shop.longitude !== null
                ? `${shop.latitude.toFixed(4)}, ${shop.longitude.toFixed(4)}`
                : "Not configured"}
            </span>
          </div>
        </div>
      ) : (
        <form onSubmit={handleSave} className="mt-4 pt-4 border-t border-[#f1f5f9] space-y-3">
          {error && (
            <div className="rounded-lg bg-[#fff1f2] border border-[#fecdd3] p-2.5 text-xs text-[#be123c] flex items-center gap-2">
              <AlertCircle className="h-4 w-4 shrink-0" />
              <span>{error}</span>
            </div>
          )}
          <div>
            <label className="block text-xs font-semibold text-[#334155] mb-1">Pickup Notes</label>
            <textarea
              value={pickupNotes}
              onChange={(e) => setPickupNotes(e.target.value)}
              placeholder="e.g. Curbside pickup at the storefront entrance, 10am-5pm"
              rows={2}
              className="w-full rounded-lg border border-[#cbd5e1] px-3 py-1.5 text-sm focus:border-paypal-blue focus:outline-none focus:ring-1 focus:ring-paypal-blue"
            />
          </div>
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
            <div>
              <label className="block text-xs font-semibold text-[#334155] mb-1">
                Latitude <span className="text-[#94a3b8] font-normal">(-90 to 90)</span>
              </label>
              <input
                type="number"
                step="any"
                value={latitude}
                onChange={(e) => setLatitude(e.target.value)}
                placeholder="37.7749"
                className="w-full rounded-lg border border-[#cbd5e1] px-3 py-1.5 text-sm focus:border-paypal-blue focus:outline-none focus:ring-1 focus:ring-paypal-blue"
              />
            </div>
            <div>
              <label className="block text-xs font-semibold text-[#334155] mb-1">
                Longitude <span className="text-[#94a3b8] font-normal">(-180 to 180)</span>
              </label>
              <input
                type="number"
                step="any"
                value={longitude}
                onChange={(e) => setLongitude(e.target.value)}
                placeholder="-122.4194"
                className="w-full rounded-lg border border-[#cbd5e1] px-3 py-1.5 text-sm focus:border-paypal-blue focus:outline-none focus:ring-1 focus:ring-paypal-blue"
              />
            </div>
          </div>
          <div className="flex items-center gap-2 pt-1">
            <button
              type="submit"
              disabled={saving}
              className="inline-flex items-center gap-1.5 rounded-lg bg-paypal-navy px-3.5 py-1.5 text-xs font-semibold text-white hover:bg-opacity-90 disabled:opacity-50"
            >
              <Check className="h-3.5 w-3.5" />
              {saving ? "Saving..." : "Save Shop Details"}
            </button>
            <button
              type="button"
              onClick={() => setEditing(false)}
              className="inline-flex items-center gap-1.5 rounded-lg border border-[#cbd5e1] px-3 py-1.5 text-xs font-semibold text-[#334155] hover:bg-[#f8fafc]"
            >
              <X className="h-3.5 w-3.5" />
              Cancel
            </button>
          </div>
        </form>
      )}
    </div>
  );
}

