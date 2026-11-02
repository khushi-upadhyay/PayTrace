"use client";

import Link from "next/link";
import { Logo } from "@/components/ui/Logo";
import { useAuth } from "@/components/providers/AuthProvider";

const LINKS = [
  { href: "/#how-it-works", label: "What it does" },
];

export function PublicNav() {
  const { user, ready } = useAuth();
  return (
    <header className="sticky top-0 z-30 border-b border-slate-800 bg-white">
      <div className="mx-auto flex h-[72px] max-w-[1180px] items-center gap-10 px-6">
        <Logo />
        <nav aria-label="Main" className="hidden flex-1 items-center gap-8 md:flex">
          {LINKS.map((l) => (
            <Link key={l.href} href={l.href} className="text-base font-semibold text-black hover:text-paypal-blue">
              {l.label}
            </Link>
          ))}
        </nav>
        <div className="ml-auto flex items-center gap-3 md:ml-0">
          {ready && user ? (
            <Link href="/dashboard" className="btn-pill btn-pill-black !px-6 !py-2.5 !text-base">
              Open workspace
            </Link>
          ) : (
            <>
              <Link href="/login" className="btn-pill btn-pill-grey !px-6 !py-2.5 !text-base">
                Sign in
              </Link>
              <Link href="/signup" className="btn-pill btn-pill-black !px-6 !py-2.5 !text-base">
                Get started
              </Link>
            </>
          )}
          <Link href="/checkout" className="hidden rounded-full px-4 py-2 text-sm font-semibold text-black hover:bg-slate-100 sm:inline-flex">Explore demo</Link>
        </div>
      </div>
    </header>
  );
}
