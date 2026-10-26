"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useEffect, useState } from "react";
import { api, type SettingsData } from "@/lib/api";
import {
  LayoutDashboard,
  CreditCard,
  AlertTriangle,
  Brain,
  ShieldCheck,
  BarChart3,
  ShoppingCart,
  Store,
  Settings,
  Activity,
  History,
} from "lucide-react";

const NAV_ITEMS = [
  { href: "/dashboard", label: "Dashboard", icon: LayoutDashboard },
  { href: "/payments", label: "Payments", icon: CreditCard },
  { href: "/sessions", label: "Session Replay", icon: History },
  { href: "/incidents", label: "Incidents", icon: AlertTriangle },
  { href: "/investigate", label: "AI Investigator", icon: Brain },
  { href: "/approvals", label: "Approval Inbox", icon: ShieldCheck },
  { href: "/analytics", label: "Analytics", icon: BarChart3 },
  { href: "/checkout", label: "PayPal Checkout", icon: ShoppingCart },
  { href: "/shelfswipe", label: "ShelfSwipe AI Store", icon: Store },
  { href: "/settings", label: "Settings", icon: Settings },
];

export function Sidebar() {
  const pathname = usePathname();
  const [settings, setSettings] = useState<SettingsData | null>(null);

  useEffect(() => {
    let active = true;
    api.getSettings().then((value) => { if (active) setSettings(value); }).catch(() => undefined);
    return () => { active = false; };
  }, []);

  return (
    <aside className="w-64 border-r border-slate-800 bg-slate-950/80 backdrop-blur-xl flex flex-col h-screen fixed left-0 top-0 z-40">
      {/* Brand */}
      <div className="h-16 px-6 border-b border-slate-800 flex items-center justify-between">
        <Link href="/" className="flex items-center gap-2.5">
          <div className="w-8 h-8 rounded-lg bg-gradient-to-tr from-cyan-600 to-sky-400 flex items-center justify-center text-slate-950 font-bold shadow-md shadow-cyan-500/20">
            <Activity className="w-5 h-5 text-slate-950 stroke-[2.5]" />
          </div>
          <div>
            <span className="font-bold tracking-tight text-white text-lg">Pay<span className="text-cyan-400">Trace</span></span>
            <span className="text-[10px] text-cyan-400/80 font-mono block -mt-1">PAYPAL AI OBSERVABILITY</span>
          </div>
        </Link>
      </div>

      {/* Nav List */}
      <nav className="flex-1 px-3 py-4 space-y-1 overflow-y-auto">
        <div className="px-3 pb-2 text-[11px] font-semibold tracking-wider text-slate-500 uppercase">
          Investigation Platform
        </div>
        {NAV_ITEMS.map((item) => {
          const Icon = item.icon;
          const isActive = pathname === item.href || pathname.startsWith(`${item.href}/`);
          return (
            <Link
              key={item.href}
              href={item.href}
              className={`flex items-center gap-3 px-3 py-2.5 rounded-lg text-sm font-medium transition-all duration-150 ${
                isActive
                  ? "bg-cyan-500/10 text-cyan-300 border border-cyan-500/30 shadow-sm shadow-cyan-500/10"
                  : "text-slate-400 hover:text-slate-200 hover:bg-slate-900/60"
              }`}
            >
              <Icon className={`w-4 h-4 ${isActive ? "text-cyan-400" : "text-slate-400"}`} />
              {item.label}
            </Link>
          );
        })}
      </nav>

      {/* Mode & Environment Indicator */}
      <div className="p-4 border-t border-slate-800/80 bg-slate-950/40">
        <div className="rounded-lg p-3 border border-slate-800 bg-slate-900/40 space-y-2">
          <div className="flex items-center justify-between">
            <span className="text-xs text-slate-400 font-medium">Environment</span>
            <span className="text-[10px] font-semibold uppercase px-2 py-0.5 rounded-full bg-cyan-950 text-cyan-300 border border-cyan-800/60">
              {settings?.paypal.environment || "Unknown"}
            </span>
          </div>
          <div className="flex items-center justify-between">
            <span className="text-xs text-slate-400 font-medium">PayPal Connection</span>
            <span className={`text-[10px] font-semibold px-2 py-0.5 rounded-full border flex items-center gap-1 ${settings?.paypal.is_configured ? "bg-emerald-950 text-emerald-300 border-emerald-800/60" : "bg-slate-800 text-slate-300 border-slate-700"}`}>
              <span className={`h-1.5 w-1.5 rounded-full ${settings?.paypal.is_configured ? "bg-emerald-400" : "bg-slate-500"}`} />
              {settings ? (settings.paypal.is_configured ? "Configured" : "Simulated") : "Unknown"}
            </span>
          </div>
        </div>
      </div>
    </aside>
  );
}
