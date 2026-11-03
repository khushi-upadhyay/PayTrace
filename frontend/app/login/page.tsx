"use client";

import { Suspense, useEffect, useState } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import { AlertCircle, Eye, EyeOff, Loader2, Lock } from "lucide-react";
import Link from "next/link";
import { AuthShell, Field, inputClass, safeNext } from "@/components/ui/auth-form";
import { useAuth } from "@/components/providers/AuthProvider";

function LoginForm() {
  const router = useRouter();
  const params = useSearchParams();
  const { user, ready, login } = useAuth();

  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [showPassword, setShowPassword] = useState(false);
  const [remember, setRemember] = useState(true);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const next = safeNext(params.get("next"));

  useEffect(() => {
    if (ready && user) router.replace(next);
  }, [ready, user, next, router]);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (submitting) return;
    setError(null);
    if (!email.trim() || !password) {
      setError("Enter your email and password to log in.");
      return;
    }
    setSubmitting(true);
    try {
      await login(email, password, remember);
      router.replace(next);
    } catch (err: any) {
      setError(err.message || "We couldn't log you in. Please try again.");
      setSubmitting(false);
    }
  };

  return (
    <>
      <h1 className="font-display mt-10 text-4xl font-bold leading-tight tracking-tight text-black">Log in to PayTrace</h1>
      <p className="mt-3 text-base text-black/70">Use the email and password you signed up with.</p>

      {error && (
        <div
          role="alert"
          className="mt-6 flex items-start gap-2.5 rounded-xl border border-rose-700 bg-rose-950 px-3.5 py-3 text-sm text-rose-300"
        >
          <AlertCircle className="mt-0.5 h-4 w-4 shrink-0" />
          <span>{error}</span>
        </div>
      )}

        <form onSubmit={handleSubmit} noValidate className="mt-8 space-y-4">
          <Field id="email" label="Email">
            <input
              id="email"
              type="email"
              autoComplete="username"
              autoFocus
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              placeholder="you@company.com"
              className={inputClass}
            />
          </Field>

          <Field id="password" label="Password">
            <div className="relative">
              <input
                id="password"
                type={showPassword ? "text" : "password"}
                autoComplete="current-password"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                placeholder="Password"
                className={`${inputClass} pr-12`}
              />
              <button
                type="button"
                onClick={() => setShowPassword((v) => !v)}
                aria-label={showPassword ? "Hide password" : "Show password"}
                className="absolute inset-y-0 right-0 flex w-12 items-center justify-center text-slate-500 hover:text-ink"
              >
                {showPassword ? <EyeOff className="h-4 w-4" /> : <Eye className="h-4 w-4" />}
              </button>
            </div>
          </Field>


          <div className="flex items-center justify-between text-sm">
            <label className="flex cursor-pointer items-center gap-2 text-black">
              <input
                type="checkbox"
                checked={remember}
                onChange={(e) => setRemember(e.target.checked)}
                className="h-4 w-4 accent-[#2c4fae]"
              />
              Stay logged in
            </label>
            <button
              type="button"
              onClick={() => setError("Password reset isn't available yet. Contact an administrator to reset your password.")}
              className="font-semibold text-paypal-blue hover:underline"
            >
              Forgot password?
            </button>
          </div>


          <button type="submit" disabled={submitting} className="btn-pill btn-pill-primary w-full">
            {submitting ? <Loader2 className="h-5 w-5 animate-spin" /> : null}
            {submitting ? "Logging in…" : "Log in"}
          </button>
        </form>

      <div className="my-6 flex items-center gap-4 text-sm text-black/50">
        <span className="h-px flex-1 bg-[#dfe3e8]" />
        or
        <span className="h-px flex-1 bg-[#dfe3e8]" />
      </div>

      <Link
        href={`/signup${params.get("next") ? `?next=${encodeURIComponent(next)}` : ""}`}
        className="btn-pill btn-pill-outline w-full"
      >
        Sign up
      </Link>

      <p className="mt-6 flex items-center gap-1.5 text-xs text-black/50">
        <Lock className="h-3 w-3" />
        PayPal Sandbox environment. No real money moves.
      </p>
    </>
  );
}

export default function LoginPage() {
  return (
    <AuthShell>
      <Suspense fallback={null}>
        <LoginForm />
      </Suspense>
    </AuthShell>
  );
}
