"use client";

import { useEffect, useRef, useState } from "react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { LogOut } from "lucide-react";
import { Logo } from "@/components/ui/Logo";
import { DemoTools } from "@/components/layout/DemoTools";
import { useAuth } from "@/components/providers/AuthProvider";

const NAV_ITEMS = [
  { href: "/dashboard", label: "Summary" },
  { href: "/payments", label: "Payments" },
  { href: "/incidents", label: "Incidents" },
  { href: "/investigate", label: "AI Investigator" },
  { href: "/approvals", label: "Approvals" },
  { href: "/analytics", label: "Analytics" },
  { href: "/checkout", label: "Store" },
  { href: "/settings", label: "Settings" },
];

function initials(name: string) {
  return name
    .split(/\s+/)
    .filter(Boolean)
    .slice(0, 2)
    .map((p) => p[0]!.toUpperCase())
    .join("");
}

export function TopNav() {
  const pathname = usePathname();
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

  const isActive = (href: string) => pathname === href || pathname.startsWith(href + "/");

  return (
    <header className="sticky top-0 z-40 bg-paypal-navy text-white">
      <div className="mx-auto flex h-[68px] max-w-7xl items-center gap-6 px-6">
        <Logo href="/dashboard" tone="light" />

        <nav aria-label="Main" className="hidden flex-1 items-stretch self-stretch lg:flex">
          {NAV_ITEMS.map((item) => (
            <Link
              key={item.href}
              href={item.href}
              aria-current={isActive(item.href) ? "page" : undefined}
              className={`my-3 flex items-center rounded-full px-4 text-[15px] font-medium transition-colors ${
                isActive(item.href) ? "bg-white/15 text-white" : "text-white/85 hover:bg-white/10 hover:text-white"
              }`}
            >
              {item.label}
            </Link>
          ))}
        </nav>

        <div className="ml-auto flex items-center gap-2 lg:ml-0">
          <DemoTools />
          {user && (
            <div ref={menuRef} className="relative">
              <button
                type="button"
                onClick={() => setMenuOpen((v) => !v)}
                aria-label="Account menu"
                aria-expanded={menuOpen}
                className="flex h-9 w-9 items-center justify-center rounded-full bg-white text-sm font-bold text-paypal-navy hover:bg-paypal-sky"
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
      </div>

      {/* Below lg the nav drops to a scrollable second row */}
      <nav aria-label="Main (compact)" className="flex overflow-x-auto border-t border-white/15 px-4 lg:hidden">
        {NAV_ITEMS.map((item) => (
          <Link
            key={item.href}
            href={item.href}
            aria-current={isActive(item.href) ? "page" : undefined}
            className={`my-2 shrink-0 rounded-full px-3.5 py-1.5 text-sm font-medium ${
              isActive(item.href) ? "bg-white/15 text-white" : "text-white/85"
            }`}
          >
            {item.label}
          </Link>
        ))}
      </nav>
    </header>
  );
}
