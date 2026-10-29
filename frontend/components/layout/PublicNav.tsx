"use client";

import Link from "next/link";
import { Logo } from "@/components/ui/Logo";
import { useAuth } from "@/components/providers/AuthProvider";

const LINKS = [
  { href: "/#platform", label: "Platform" },
  { href: "/#how-it-works", label: "How it works" },
  { href: "/#features", label: "Features" },
  { href: "/checkout", label: "Demo store" },
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
              Dashboard
            </Link>
          ) : (
            <>
              <Link href="/login" className="btn-pill btn-pill-grey !px-6 !py-2.5 !text-base">
                Log In
              </Link>
              <Link href="/signup" className="btn-pill btn-pill-black !px-6 !py-2.5 !text-base">
                Sign Up
              </Link>
            </>
          )}
        </div>
      </div>
    </header>
  );
}
