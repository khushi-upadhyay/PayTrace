"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import {
  Activity, BadgeCheck, BarChart3, CircleAlert, CreditCard,
  LayoutDashboard, MonitorPlay, Scale, Settings, ShoppingBag, Sparkles,
  ListFilter,
} from "lucide-react";
import { Logo } from "@/components/ui/Logo";

const ITEMS = [
  { href: "/dashboard", label: "Summary", icon: LayoutDashboard },
  { href: "/payments", label: "Payments", icon: CreditCard },
  { href: "/transactions", label: "Transaction Explorer", icon: ListFilter },
  { href: "/sessions", label: "Session Replay", icon: MonitorPlay },
  { href: "/incidents", label: "Incidents", icon: CircleAlert },
  { href: "/disputes", label: "Disputes", icon: Scale },
  { href: "/investigate", label: "AI Investigator", icon: Sparkles },
  { href: "/approvals", label: "Approvals", icon: BadgeCheck },
  { href: "/analytics", label: "Analytics", icon: BarChart3 },
  { href: "/checkout", label: "Demo Store", icon: ShoppingBag },
  { href: "/shelfswipe", label: "ShelfSwipe", icon: Activity },
  { href: "/settings", label: "Settings", icon: Settings },
];

export function WorkspaceSidebar() {
  const pathname = usePathname();
  const isActive = (href: string) => pathname === href || pathname.startsWith(`${href}/`);

  return (
    <aside className="z-30 flex shrink-0 flex-col border-b border-slate-800 bg-paypal-navy text-white md:sticky md:top-0 md:h-screen md:w-64 md:border-b-0 md:border-r">
      <div className="flex h-[56px] items-center border-b border-white/10 px-4 md:hidden">
        <Logo href="/dashboard" tone="light" />
      </div>
      <div className="hidden h-[68px] items-center border-b border-white/10 px-6 md:flex">
        <Logo href="/dashboard" tone="light" />
      </div>
      <div className="px-4 pb-1 pt-3 text-[10px] font-bold uppercase tracking-[0.18em] text-white/45 md:px-5 md:pb-2 md:pt-6">
        Workspace
      </div>
      <nav aria-label="Workspace" className="flex gap-1 overflow-x-auto px-3 pb-3 md:flex-1 md:flex-col md:overflow-visible md:px-3 md:pb-5">
        {ITEMS.map(({ href, label, icon: Icon }) => (
          <Link
            key={href}
            href={href}
            aria-current={isActive(href) ? "page" : undefined}
            className={`flex shrink-0 items-center gap-3 rounded-lg px-3 py-2.5 text-sm font-medium transition-colors ${
              isActive(href) ? "bg-white/15 text-white" : "text-white/70 hover:bg-white/10 hover:text-white"
            }`}
          >
            <Icon className="h-4 w-4 shrink-0" aria-hidden="true" />
            <span>{label}</span>
          </Link>
        ))}
      </nav>
      <div className="hidden border-t border-white/10 px-5 py-4 text-xs leading-relaxed text-white/45 md:block">
        Payment and session observability
      </div>
    </aside>
  );
}
