"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { Store, ShoppingBag, ArrowRight } from "lucide-react";
import { shelfswipeApi } from "@/lib/shelfswipe-api";

export default function ShelfSwipeChooserPage() {
  const [stats, setStats] = useState<{ total_shops: number; total_live_products: number } | null>(null);

  useEffect(() => {
    let active = true;
    shelfswipeApi
      .listSellers()
      .then((res) => {
        if (active) setStats({ total_shops: res.total_shops, total_live_products: res.total_live_products });
      })
      .catch(() => {
        // stats strip is a nice-to-have; fail silently
      });
    return () => {
      active = false;
    };
  }, []);

  return (
    <div className="min-h-screen bg-[#f8fafc] text-[#0f172a] pb-16">
      <div className="border-b border-[#e2e8f0] bg-white">
        <div className="mx-auto max-w-5xl px-4 py-5 sm:px-6">
          <div className="flex items-center gap-2">
            <span className="text-xs font-bold uppercase tracking-wider text-paypal-blue">ShelfSwipe</span>
            <span className="rounded-full bg-[#cffafe] px-2 py-0.5 text-[10px] font-bold text-[#155e75]">
              Local Commerce Demo
            </span>
          </div>
          <h1 className="text-xl font-bold text-[#0f172a] mt-1">What would you like to do?</h1>
        </div>
      </div>

      <div className="mx-auto max-w-4xl px-4 pt-10 sm:px-6">
        {stats && (stats.total_shops > 0 || stats.total_live_products > 0) && (
          <div className="mb-8 flex items-center justify-center gap-6 text-xs text-[#64748b]">
            <span>
              <strong className="text-[#0f172a]">{stats.total_shops}</strong> shop
              {stats.total_shops === 1 ? "" : "s"} onboarded
            </span>
            <span className="h-3 w-px bg-[#e2e8f0]" />
            <span>
              <strong className="text-[#0f172a]">{stats.total_live_products}</strong> product
              {stats.total_live_products === 1 ? "" : "s"} live
            </span>
          </div>
        )}

        <div className="grid grid-cols-1 sm:grid-cols-2 gap-6">
          {/* Seller option */}
          <Link
            href="/shelfswipe/seller-onboarding"
            className="group flex flex-col rounded-2xl border border-[#e2e8f0] bg-white p-8 shadow-sm hover:shadow-md hover:border-paypal-blue transition-all"
          >
            <div className="flex h-12 w-12 items-center justify-center rounded-xl bg-paypal-navy text-white shadow-sm">
              <Store className="h-6 w-6" />
            </div>
            <h2 className="text-lg font-bold text-[#0f172a] mt-4">Seller Store Onboarding</h2>
            <p className="text-sm text-[#64748b] mt-1.5 flex-1">
              Import a merchant catalog — pick a curated demo shop or connect your own store via
              Channel3 — then review readiness flags and approve products to go live.
            </p>
            <span className="inline-flex items-center gap-1.5 text-sm font-bold text-paypal-blue mt-5 group-hover:gap-2.5 transition-all">
              Onboard a store
              <ArrowRight className="h-4 w-4" />
            </span>
          </Link>

          {/* Buyer option */}
          <Link
            href="/shelfswipe/buyer-onboarding"
            className="group flex flex-col rounded-2xl border border-[#e2e8f0] bg-white p-8 shadow-sm hover:shadow-md hover:border-paypal-blue transition-all"
          >
            <div className="flex h-12 w-12 items-center justify-center rounded-xl bg-[#047857] text-white shadow-sm">
              <ShoppingBag className="h-6 w-6" />
            </div>
            <h2 className="text-lg font-bold text-[#0f172a] mt-4">Buyer Store Onboarding</h2>
            <p className="text-sm text-[#64748b] mt-1.5 flex-1">
              Browse every product sellers have approved to live status, in a swipeable,
              Tinder-style deck. Swipe through one shop, or every shop at once.
            </p>
            <span className="inline-flex items-center gap-1.5 text-sm font-bold text-[#047857] mt-5 group-hover:gap-2.5 transition-all">
              Start swiping
              <ArrowRight className="h-4 w-4" />
            </span>
          </Link>
        </div>

        <div className="mt-10 text-center text-xs text-[#94a3b8]">
          Local test data only &mdash; products and checkout here are sandboxed for PayTrace demos.
        </div>
      </div>
    </div>
  );
}
