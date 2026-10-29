import Link from "next/link";
import { LogoMark } from "@/components/ui/Logo";

/** Small pieces shared by the login and sign-up pages. */

/** Only follow same-site relative paths so `?next=` can't become an open redirect. */
export function safeNext(raw: string | null): string {
  return raw && raw.startsWith("/") && !raw.startsWith("//") ? raw : "/dashboard";
}

export const inputClass =
  "w-full rounded-xl border border-[#c4cbd4] bg-white px-4 py-3.5 text-base text-black placeholder-black/45 transition-colors focus:border-paypal-blue focus:outline-none focus:ring-2 focus:ring-paypal-blue/30";

export function Field({ id, label, children }: { id: string; label: string; children: React.ReactNode }) {
  return (
    <div>
      <label htmlFor={id} className="mb-1.5 block text-sm font-semibold text-black">
        {label}
      </label>
      {children}
    </div>
  );
}

/** White page with a single left-aligned column and a slim footer, like PayPal's sign-in. */
export function AuthShell({ children }: { children: React.ReactNode }) {
  return (
    <div className="flex min-h-screen flex-col bg-white">
      <main className="flex flex-1 justify-center px-6 pb-16 pt-16 sm:pt-24">
        <div className="w-full max-w-[468px]">
          <Link href="/" aria-label="PayTrace home" className="inline-block">
            <LogoMark className="h-12 w-12" />
          </Link>
          {children}
        </div>
      </main>
      <footer className="bg-[#f5f5f5] py-5">
        <nav className="flex flex-wrap items-center justify-center gap-x-6 gap-y-2 px-6 text-sm text-black">
          <Link href="/" className="underline">Home</Link>
          <Link href="/checkout" className="underline">Demo store</Link>
          <Link href="/login" className="underline">Log In</Link>
          <Link href="/signup" className="underline">Sign Up</Link>
        </nav>
      </footer>
    </div>
  );
}
