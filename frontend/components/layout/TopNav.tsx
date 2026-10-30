"use client";

import { useEffect, useRef, useState } from "react";
import { LogOut } from "lucide-react";
import { DemoTools } from "@/components/layout/DemoTools";
import { useAuth } from "@/components/providers/AuthProvider";

function initials(name: string) {
  return name
    .split(/\s+/)
    .filter(Boolean)
    .slice(0, 2)
    .map((p) => p[0]!.toUpperCase())
    .join("");
}

export function TopNav() {
  const { user, logout } = useAuth();
  const [menuOpen, setMenuOpen] = useState(false);
  const menuRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!menuOpen) return;
    const onDown = (e: MouseEvent) => {
      if (menuRef.current && !menuRef.current.contains(e.target as Node)) setMenuOpen(false);
    };
    document.addEventListener("mousedown", onDown);
    return () => document.removeEventListener("mousedown", onDown);
  }, [menuOpen]);

  return (
    <header className="sticky top-0 z-40 bg-paypal-navy text-white">
      <div className="flex h-[60px] items-center justify-end gap-2 border-b border-white/10 px-4 md:h-[68px] md:px-6">
        <DemoTools />
        {user && (
          <div ref={menuRef} className="relative">
            <button
              type="button"
              onClick={() => setMenuOpen((v) => !v)}
              aria-label="Account menu"
              aria-expanded={menuOpen}
              className="flex h-9 w-9 items-center justify-center rounded-full bg-white text-sm font-bold text-paypal-navy transition-colors duration-150 hover:bg-paypal-sky"
            >
              {initials(user.name)}
            </button>
            {menuOpen && (
              <div className="absolute right-0 top-11 z-50 w-64 rounded-xl border border-slate-800 bg-slate-900 p-1.5 shadow-xl">
                <div className="border-b border-slate-800 px-3 py-3">
                  <div className="truncate text-sm font-bold text-ink">{user.name}</div>
                  <div className="truncate text-xs text-slate-500">{user.email}</div>
                  <div className="mt-1 text-xs text-slate-500">{user.role}</div>
                </div>
                <button
                  type="button"
                  onClick={logout}
                  className="mt-1 flex w-full items-center gap-2.5 rounded-lg px-3 py-2.5 text-sm font-medium text-slate-300 hover:bg-slate-800"
                >
                  <LogOut className="h-4 w-4" />
                  Log out
                </button>
              </div>
            )}
          </div>
        )}
      </div>
    </header>
  );
}
