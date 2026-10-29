"use client";

import { Suspense, useEffect, useState } from "react";
import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { AlertCircle, Eye, EyeOff, Loader2 } from "lucide-react";
import { AuthShell, Field, inputClass, safeNext } from "@/components/ui/auth-form";
import { useAuth } from "@/components/providers/AuthProvider";

function SignupForm() {
  const router = useRouter();
  const params = useSearchParams();
  const { user, ready, register } = useAuth();

  const [name, setName] = useState("");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [showPassword, setShowPassword] = useState(false);
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
    if (!name.trim() || !email.trim() || !password) {
      setError("Fill in your name, email and password to sign up.");
      return;
    }
    if (password.length < 8) {
      setError("Your password must be at least 8 characters.");
      return;
    }
    setSubmitting(true);
    try {
      await register(name, email, password);
      router.replace(next);
    } catch (err: any) {
      setError(err.message || "We couldn't create your account. Please try again.");
      setSubmitting(false);
    }
  };

  return (
    <>
      <h1 className="font-display mt-10 text-4xl font-bold leading-tight tracking-tight text-black">Create your PayTrace account</h1>
      <p className="mt-3 text-base text-black/70">Trace PayPal payments and investigate failures in one place.</p>

      {error && (
        <div
          role="alert"
          className="mt-6 flex items-start gap-2.5 rounded-xl border border-rose-300 bg-rose-50 px-3.5 py-3 text-sm text-rose-700"
        >
          <AlertCircle className="mt-0.5 h-4 w-4 shrink-0" />
          <span>{error}</span>
        </div>
      )}

        <form onSubmit={handleSubmit} noValidate className="mt-8 space-y-4">
          <Field id="name" label="Full name">
            <input
              id="name"
              autoComplete="name"
              autoFocus
              value={name}
              onChange={(e) => setName(e.target.value)}
              className={inputClass}
            />
          </Field>
          <Field id="email" label="Email">
            <input
              id="email"
              type="email"
              autoComplete="username"
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
                autoComplete="new-password"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                placeholder="At least 8 characters"
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

          <button type="submit" disabled={submitting} className="btn-pill btn-pill-primary w-full">
            {submitting ? <Loader2 className="h-5 w-5 animate-spin" /> : null}
            {submitting ? "Creating account…" : "Sign up"}
          </button>
        </form>

      <p className="mt-6 text-sm text-black/70">
        Already have an account?{" "}
        <Link
          href={`/login${params.get("next") ? `?next=${encodeURIComponent(next)}` : ""}`}
          className="font-semibold text-paypal-blue hover:underline"
        >
          Log in
        </Link>
      </p>
    </>
  );
}

export default function SignupPage() {
  return (
    <AuthShell>
      <Suspense fallback={null}>
        <SignupForm />
      </Suspense>
    </AuthShell>
  );
}
