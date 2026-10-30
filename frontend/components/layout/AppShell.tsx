"use client";

import { useEffect } from "react";
import { usePathname, useRouter } from "next/navigation";
import Link from "next/link";
import { Loader2 } from "lucide-react";
import { Logo } from "@/components/ui/Logo";
import { TopNav } from "@/components/layout/TopNav";
import { WorkspaceSidebar } from "@/components/layout/WorkspaceSidebar";
import { PublicNav } from "@/components/layout/PublicNav";
import { useAuth } from "@/components/providers/AuthProvider";

/** Pages anyone can open. Everything else is the operator console and needs a login. */
const PUBLIC_ROUTES = ["/", "/checkout"];
const AUTH_ROUTES = ["/login", "/signup"];

export function AppShell({ children }: { children: React.ReactNode }) {
  const pathname = usePathname();
  const router = useRouter();
  const { user, ready } = useAuth();

  const isAuthPage = AUTH_ROUTES.includes(pathname);
  const isPublic = PUBLIC_ROUTES.includes(pathname);
  const needsLogin = !isAuthPage && !isPublic;

  useEffect(() => {
    if (ready && needsLogin && !user) {
      router.replace(`/login?next=${encodeURIComponent(pathname)}`);
    }
  }, [ready, needsLogin, user, pathname, router]);

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
        <main className="mx-auto w-full max-w-7xl flex-1 px-4 py-6 sm:px-6 md:py-8">{children}</main>
        <footer className="mt-8 shrink-0 border-t border-slate-800 bg-white">
          <div className="mx-auto flex max-w-7xl flex-wrap items-center gap-x-8 gap-y-3 px-6 py-8">
            <Logo href="/dashboard" />
            <Link href="/settings" className="text-base text-black hover:underline">Help</Link>
            <Link href="/settings" className="text-base text-black hover:underline">Security</Link>
            <Link href="/checkout" className="text-base text-black hover:underline">Demo store</Link>
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
