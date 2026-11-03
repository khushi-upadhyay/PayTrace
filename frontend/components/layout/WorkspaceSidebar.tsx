"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import {
  BadgeCheck, BarChart3, CircleAlert, CreditCard,
  LayoutDashboard, ListFilter, MonitorPlay, Scale, Settings, Sparkles, Store,
} from "lucide-react";
import { Logo } from "@/components/ui/Logo";

const GROUPS = [
  { label: "Monitor", items: [
    { href: "/dashboard", label: "Overview", icon: LayoutDashboard },
    { href: "/analytics", label: "Analytics", icon: BarChart3 },
  ] },
  { label: "Investigate", items: [
    { href: "/payments", label: "Payments", icon: CreditCard },
    { href: "/transactions", label: "Transaction Explorer", icon: ListFilter },
    { href: "/sessions", label: "Sessions", icon: MonitorPlay },
  ] },
  { label: "Resolve", items: [
    { href: "/incidents", label: "Incidents", icon: CircleAlert },
    { href: "/disputes", label: "Disputes", icon: Scale },
    { href: "/approvals", label: "Approvals", icon: BadgeCheck },
  ] },
  { label: "Workspace", items: [
    { href: "/investigate", label: "AI Investigator", icon: Sparkles },
    { href: "/shelfswipe", label: "ShelfSwipe", icon: Store },
    { href: "/settings", label: "Settings", icon: Settings },
  ] },
];

export function WorkspaceSidebar() {
  const pathname = usePathname();
  const isActive = (href: string) => pathname === href || pathname.startsWith(`${href}/`);

  return (
    <aside className="z-30 flex shrink-0 flex-col border-b border-slate-800 bg-paypal-navy text-white md:sticky md:top-0 md:h-screen md:w-60 md:border-b-0 md:border-r">
      <div className="hidden h-[68px] items-center border-b border-white/10 px-6 md:flex">
        <Logo href="/dashboard" tone="light" />
      </div>
      <nav aria-label="Workspace" className="flex gap-4 overflow-x-auto px-3 py-2 md:flex-1 md:flex-col md:gap-2 md:overflow-y-auto md:py-4">
        {GROUPS.map((group) => (
          <section key={group.label} className="shrink-0 md:shrink">
            <h2 className="px-3 pb-1 pt-1 text-[10px] font-bold uppercase tracking-[0.16em] text-white/45">{group.label}</h2>
            <div className="flex gap-1 md:flex-col">
              {group.items.map(({ href, label, icon: Icon }) => (
                <Link key={href} href={href} aria-current={isActive(href) ? "page" : undefined}
                  className={`flex shrink-0 items-center gap-2.5 rounded-lg px-3 py-2 text-[13px] font-medium transition-colors ${isActive(href) ? "bg-white/15 text-white" : "text-white/70 hover:bg-white/10 hover:text-white"}`}>
                  <Icon className="h-4 w-4 shrink-0" aria-hidden="true" /><span>{label}</span>
                </Link>
              ))}
            </div>
          </section>
        ))}
      </nav>
      <div className="hidden border-t border-white/10 px-5 py-4 text-xs leading-relaxed text-white/45 md:block">Payment observability workspace</div>
    </aside>
  );
}
