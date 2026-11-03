"use client";

import { useEffect } from "react";
import { usePathname, useRouter } from "next/navigation";
import Link from "next/link";
import { ChevronRight, Loader2 } from "lucide-react";
import { Logo } from "@/components/ui/Logo";
import { TopNav } from "@/components/layout/TopNav";
import { WorkspaceSidebar } from "@/components/layout/WorkspaceSidebar";
import { PublicNav } from "@/components/layout/PublicNav";
import { useAuth } from "@/components/providers/AuthProvider";

/** Pages anyone can open. Everything else is the operator console and needs a login. */
const PUBLIC_ROUTES = ["/", "/checkout", "/demo/approval"];
const AUTH_ROUTES = ["/login", "/signup"];

function Breadcrumbs({ pathname }: { pathname: string }) {
  const parts = pathname.split("/").filter(Boolean);
  const labels: Record<string, string> = {
    dashboard: "Overview", analytics: "Analytics", payments: "Payments", transactions: "Transaction Explorer",
    sessions: "Sessions", incidents: "Incidents", disputes: "Disputes", approvals: "Approvals",
    investigate: "AI Investigator", settings: "Settings", "demo-lab": "Demo Lab",
  };
  const href = (index: number) => `/${parts.slice(0, index + 1).join("/")}`;
  return <nav aria-label="Breadcrumb" className="mb-5 flex items-center gap-1.5 text-xs text-slate-500">
    <Link href="/dashboard" className="hover:text-cyan-500">Workspace</Link>
    {parts.map((part, index) => <span key={`${part}-${index}`} className="inline-flex min-w-0 items-center gap-1.5">
      <ChevronRight className="h-3 w-3 shrink-0" />
      {index === parts.length - 1 ? <span aria-current="page" className="truncate font-medium text-slate-300">{labels[part] || part.slice(0, 12)}</span> : <Link href={href(index)} className="truncate hover:text-cyan-500">{labels[part] || part.slice(0, 12)}</Link>}
    </span>)}
  </nav>;
}

export function AppShell({ children }: { children: React.ReactNode }) {
  const pathname = usePathname();
  const router = useRouter();
  const { user, ready, serverUnreachable } = useAuth();

  const isAuthPage = AUTH_ROUTES.includes(pathname);
  const isPublic = PUBLIC_ROUTES.includes(pathname);
  const needsLogin = !isAuthPage && !isPublic;

  useEffect(() => {
    if (ready && needsLogin && !user && !serverUnreachable) {
      router.replace(`/login?next=${encodeURIComponent(pathname)}`);
    }
  }, [ready, needsLogin, user, serverUnreachable, pathname, router]);

  if (isAuthPage) return <>{children}</>;

  if (pathname === "/") {
    return (
      <>
        <PublicNav />
        {children}
      </>
    );
  }

  if (isPublic) {
    return (
      <>
        <PublicNav />
        <main className="px-6 py-8">{children}</main>
      </>
    );
  }

  if (ready && !user && serverUnreachable) {
    return (
      <div className="flex min-h-screen items-center justify-center px-6" role="alert">
        <div className="max-w-md rounded-xl border border-amber-700 bg-amber-950 p-6 text-center">
          <h1 className="text-lg font-semibold text-amber-300">Can&apos;t reach the PayTrace server</h1>
          <p className="mt-2 text-sm text-amber-300">
            The API isn&apos;t responding, so your session can&apos;t be checked. You haven&apos;t been signed out.
          </p>
          <button
            type="button"
            onClick={() => window.location.reload()}
            className="mt-4 rounded-lg border border-neutral-300 bg-white px-3 py-1.5 text-xs font-semibold text-black hover:bg-neutral-100"
          >
            Try again
          </button>
        </div>
      </div>
    );
  }

  if (!ready || !user) {
    return (
      <div className="flex min-h-screen items-center justify-center text-slate-400" role="status">
        <Loader2 className="h-6 w-6 animate-spin text-cyan-400" />
        <span className="sr-only">Checking your session</span>
      </div>
    );
  }

  return (
    <div className="flex min-h-screen flex-col md:flex-row">
      <WorkspaceSidebar />
      <div className="flex min-w-0 flex-1 flex-col">
        <TopNav />
        <main className={`mx-auto w-full ${pathname === "/transactions" ? "max-w-[1700px]" : "max-w-7xl"} flex-1 px-4 py-5 sm:px-6 md:py-7`}>
          <Breadcrumbs pathname={pathname} />
          {children}
        </main>
        <footer className="mt-8 shrink-0 border-t border-slate-800 bg-white">
          <div className="mx-auto flex max-w-7xl flex-wrap items-center gap-x-8 gap-y-3 px-6 py-5">
            <Logo href="/dashboard" />
          </div>
          <div className="border-t border-slate-800">
            <div className="mx-auto max-w-7xl px-6 py-5 text-sm text-black/60">
              © 2026 PayTrace. An independent hackathon prototype for PayPal payment observability.
            </div>
          </div>
        </footer>
      </div>
    </div>
  );
}
