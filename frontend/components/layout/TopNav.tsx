"use client";

import Link from "next/link";
import { useEffect, useRef, useState } from "react";
import { useRouter } from "next/navigation";
import { ChevronDown, ExternalLink, LogOut, MessageCircleQuestion, Search, Store } from "lucide-react";
import { useAuth } from "@/components/providers/AuthProvider";
import { api, type WorkspaceSearchItem } from "@/lib/api";

function initials(name: string) {
  return name.split(/\s+/).filter(Boolean).slice(0, 2).map((p) => p[0]!.toUpperCase()).join("");
}

export function TopNav() {
  const { user, logout } = useAuth();
  const router = useRouter();
  const [menu, setMenu] = useState<"apps" | "account" | null>(null);
  const [searchOpen, setSearchOpen] = useState(false);
  const [query, setQuery] = useState("");
  const [items, setItems] = useState<WorkspaceSearchItem[]>([]);
  const [searchLoading, setSearchLoading] = useState(false);
  const [searchError, setSearchError] = useState("");
  const [activeIndex, setActiveIndex] = useState(0);
  const ref = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    const onKey = (event: KeyboardEvent) => {
      if ((event.metaKey || event.ctrlKey) && event.key.toLowerCase() === "k") { event.preventDefault(); setSearchOpen(true); }
      if (event.key === "Escape") setSearchOpen(false);
    };
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, []);

  useEffect(() => { if (searchOpen) inputRef.current?.focus(); }, [searchOpen]);
  useEffect(() => {
    if (!searchOpen || query.trim().length < 2) { setItems([]); setSearchError(""); setSearchLoading(false); return; }
    let cancelled = false;
    setSearchLoading(true); setSearchError("");
    const timer = window.setTimeout(() => {
      api.searchWorkspace(query.trim()).then((result) => { if (!cancelled) { setItems(result.items); setActiveIndex(0); } })
        .catch((error) => { if (!cancelled) setSearchError(error instanceof Error ? error.message : "Search is unavailable."); })
        .finally(() => { if (!cancelled) setSearchLoading(false); });
    }, 220);
    return () => { cancelled = true; window.clearTimeout(timer); };
  }, [query, searchOpen]);

  const goToSearchResult = (item: WorkspaceSearchItem) => { setSearchOpen(false); setQuery(""); router.push(item.href); };

  useEffect(() => {
    if (!menu) return;
    const onDown = (e: MouseEvent) => { if (ref.current && !ref.current.contains(e.target as Node)) setMenu(null); };
    document.addEventListener("mousedown", onDown);
    return () => document.removeEventListener("mousedown", onDown);
  }, [menu]);

  return (
    <header ref={ref} className="sticky top-0 z-40 bg-paypal-navy text-white">
      <div className="flex h-[60px] items-center justify-end gap-2 border-b border-white/10 px-4 md:h-[68px] md:px-6">
        <button type="button" onClick={() => setSearchOpen(true)} aria-label="Search workspace" className="inline-flex h-9 items-center gap-2 rounded-full border border-white/35 px-3 text-xs font-semibold hover:bg-white/10 sm:text-sm"><Search className="h-4 w-4" /><span className="hidden md:inline">Search</span><kbd className="hidden rounded border border-white/25 px-1 text-[10px] text-white/70 lg:inline">⌘K</kbd></button>
        <Link href="/investigate" className="inline-flex h-9 items-center gap-2 rounded-full border border-white/35 px-3 text-xs font-semibold hover:bg-white/10 sm:px-3.5 sm:text-sm">
          <MessageCircleQuestion className="h-4 w-4" /><span>Ask PayTrace</span>
        </Link>
        <div className="relative">
          <button type="button" onClick={() => setMenu(menu === "apps" ? null : "apps")} aria-expanded={menu === "apps"} className="inline-flex h-9 items-center gap-2 rounded-full border border-white/35 px-3 text-xs font-semibold hover:bg-white/10 sm:text-sm">
            <Store className="h-4 w-4" /><span className="hidden sm:inline">Customer apps</span><ChevronDown className="h-3.5 w-3.5" />
          </button>
          {menu === "apps" && <div className="absolute right-0 top-11 z-50 w-60 rounded-xl border border-slate-800 bg-slate-900 p-2 shadow-xl">
            <p className="px-2 py-1.5 text-[10px] font-bold uppercase tracking-wider text-slate-400">Customer applications</p>
            <Link onClick={() => setMenu(null)} href="/checkout" className="flex items-center justify-between rounded-lg px-2 py-2 text-sm text-slate-200 hover:bg-slate-800">Demo Store <ExternalLink className="h-3.5 w-3.5 text-slate-500" /></Link>
            <Link onClick={() => setMenu(null)} href="/shelfswipe/buyer-onboarding" className="flex items-center justify-between rounded-lg px-2 py-2 text-sm text-slate-100 hover:bg-slate-800">ShelfSwipe Store <ExternalLink className="h-3.5 w-3.5 text-slate-400" /></Link>
            <div className="my-1 border-t border-slate-800" />
            <Link onClick={() => setMenu(null)} href="/demo-lab" className="block rounded-lg px-2 py-2 text-sm text-cyan-200 hover:bg-slate-800">Demo Lab <span className="ml-1 text-[10px] text-slate-400">controlled scenarios</span></Link>
          </div>}
        </div>
        {user && <div className="relative">
          <button type="button" onClick={() => setMenu(menu === "account" ? null : "account")} aria-label="Account menu" aria-expanded={menu === "account"} className="flex h-9 w-9 items-center justify-center rounded-full bg-white text-sm font-bold text-paypal-navy hover:bg-paypal-sky">{initials(user.name)}</button>
          {menu === "account" && <div className="absolute right-0 top-11 z-50 w-64 rounded-xl border border-slate-800 bg-slate-900 p-1.5 shadow-xl">
            <div className="border-b border-slate-800 px-3 py-3"><div className="truncate text-sm font-bold text-ink">{user.name}</div><div className="truncate text-xs text-slate-500">{user.email}</div><div className="mt-1 text-xs text-slate-500">{user.role}</div></div>
            <button type="button" onClick={logout} className="mt-1 flex w-full items-center gap-2.5 rounded-lg px-3 py-2.5 text-sm font-medium text-slate-300 hover:bg-slate-800"><LogOut className="h-4 w-4" />Log out</button>
          </div>}
        </div>}
      </div>
      {searchOpen && <div className="light-scale fixed inset-0 z-[70] flex items-start justify-center bg-slate-900/50 px-4 pt-[12vh]" onMouseDown={(event) => { if (event.target === event.currentTarget) setSearchOpen(false); }}>
        <section role="dialog" aria-modal="true" aria-label="Search workspace" className="w-full max-w-2xl overflow-hidden rounded-2xl border border-slate-200 bg-white text-slate-900 shadow-2xl">
          <div className="flex items-center gap-3 border-b border-slate-200 px-4"><Search className="h-5 w-5 text-paypal-blue" /><input ref={inputRef} value={query} onChange={(event) => setQuery(event.target.value)} onKeyDown={(event) => {
            if (event.key === "ArrowDown" && items.length) { event.preventDefault(); setActiveIndex((index) => (index + 1) % items.length); }
            if (event.key === "ArrowUp" && items.length) { event.preventDefault(); setActiveIndex((index) => (index - 1 + items.length) % items.length); }
            if (event.key === "Enter" && items[activeIndex]) { event.preventDefault(); goToSearchResult(items[activeIndex]); }
          }} placeholder="Search payment, order, customer, session, incident, failure code…" aria-label="Search payments, sessions and incidents" className="h-14 min-w-0 flex-1 bg-transparent text-sm text-slate-900 outline-none placeholder:text-slate-500" /><kbd className="rounded border border-slate-300 px-1.5 py-0.5 text-[10px] text-slate-600">ESC</kbd></div>
          <div className="max-h-[55vh] overflow-y-auto p-2" aria-live="polite">
            {query.trim().length < 2 ? <p className="px-3 py-8 text-center text-sm text-slate-600">Enter at least 2 characters to search stored workspace records.</p> : searchLoading ? <p role="status" className="px-3 py-8 text-center text-sm text-slate-600">Searching workspace…</p> : searchError ? <p role="alert" className="px-3 py-8 text-center text-sm text-rose-700">{searchError}</p> : items.length === 0 ? <p className="px-3 py-8 text-center text-sm text-slate-600">No matching payments, sessions, or incidents.</p> : items.map((item, index) => <button key={`${item.category}:${item.id}`} type="button" onMouseEnter={() => setActiveIndex(index)} onClick={() => goToSearchResult(item)} className={`flex w-full items-start gap-3 rounded-lg px-3 py-2.5 text-left ${index === activeIndex ? "bg-blue-50" : "hover:bg-slate-50"}`}><span className="mt-0.5 min-w-20 rounded bg-blue-50 px-2 py-1 text-center text-[10px] font-semibold text-blue-800">{item.category}</span><span className="min-w-0 flex-1"><span className="block truncate text-sm font-semibold text-slate-900">{item.label}</span><span className="block truncate text-xs text-slate-600">{item.description}</span></span><span className="text-xs font-semibold text-paypal-blue">Open</span></button>)}
          </div>
          <div className="border-t border-slate-200 px-4 py-2 text-[10px] text-slate-500">Payments, PayPal orders, customer references, session IDs, incident titles/IDs, and failure codes</div>
        </section>
      </div>}
    </header>
  );
}
