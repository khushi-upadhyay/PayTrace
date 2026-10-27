"use client";

import { useState } from "react";
import Link from "next/link";
import { ArrowRight, Brain, CheckCircle2, GitCompare, Layers, Lock, ShieldAlert, Video, Webhook } from "lucide-react";
import { Logo } from "@/components/ui/Logo";

const AUDIENCES = {
  merchants: {
    label: "Merchants",
    title: "Know exactly why a payment failed",
    body: "PayTrace follows every PayPal order from checkout to capture, matches it with webhooks and server logs, and tells you what went wrong before a blind retry charges your customer twice.",
  },
  developers: {
    label: "Developers",
    title: "Debug payments with evidence, not guesses",
    body: "Replay the checkout, read one correlated timeline of PayPal events, API latency and browser activity, and ask the AI investigator for a root cause grounded in verified facts.",
  },
} as const;

type Audience = keyof typeof AUDIENCES;

const TIMELINE = [
  { label: "Order created", detail: "PayPal sandbox order", time: "0.0s", tone: "ok" },
  { label: "Buyer approved", detail: "Approval webhook verified", time: "4.2s", tone: "ok" },
  { label: "Capture requested", detail: "Merchant backend to PayPal", time: "4.4s", tone: "ok" },
  { label: "Backend timed out", detail: "HTTP read timeout after 5000 ms", time: "9.4s", tone: "warn" },
  { label: "Retry blocked", detail: "Duplicate charge prevented", time: "9.5s", tone: "stop" },
] as const;

const TONE = {
  ok: "bg-emerald-500",
  warn: "bg-amber-400",
  stop: "bg-paypal-navy",
} as const;

const LAYERS = [
  {
    icon: Webhook,
    title: "PayPal APIs and webhooks",
    body: "Order approvals, captures and signature-verified webhooks, with out-of-order events de-duplicated.",
  },
  {
    icon: Layers,
    title: "Your application backend",
    body: "Lifecycle transitions, HTTP read timeouts and stage-by-stage latency from your own server.",
  },
  {
    icon: Video,
    title: "Customer checkout journeys",
    body: "Session replay with stalled-spinner detection. Card and form inputs are masked in the browser.",
  },
];

const FEATURES = [
  {
    icon: ShieldAlert,
    title: "Duplicate charge prevention",
    body: "When your backend times out waiting for PayPal's capture response, PayTrace marks the payment CAPTURE_UNCERTAIN and stops blind retries until the provider status is reconciled.",
    bg: "bg-[#fff1c7]",
  },
  {
    icon: Brain,
    title: "Evidence-grounded AI investigator",
    body: "Every investigation separates facts, inferences and recommendations. If the AI is offline, deterministic rules still produce a root-cause diagnosis.",
    bg: "bg-paypal-sky",
  },
  {
    icon: Lock,
    title: "Human-approved refunds",
    body: "The AI can propose a fix, but no refund or cancellation runs until an operator signs off in the Approval Inbox.",
    bg: "bg-[#dfe6fb]",
  },
  {
    icon: GitCompare,
    title: "Failed versus successful",
    body: "Compare a failed payment with a recent successful one to see exactly which stage slowed down or which confirmation went missing.",
    bg: "bg-[#e9efe6]",
  },
];

export default function LandingPage() {
  const [audience, setAudience] = useState<Audience>("merchants");
  const copy = AUDIENCES[audience];

  return (
    <div className="bg-white">
      {/* Hero */}
      <section className="bg-paypal-sky px-6 pt-16">
        <div className="mx-auto max-w-[1180px] text-center">
          <div role="tablist" aria-label="Who is PayTrace for" className="mx-auto inline-flex rounded-full bg-white/40 p-1">
            {(Object.keys(AUDIENCES) as Audience[]).map((key) => (
              <button
                key={key}
                role="tab"
                aria-selected={audience === key}
                onClick={() => setAudience(key)}
                className={`rounded-full px-7 py-3 text-lg font-semibold transition-colors ${
                  audience === key ? "bg-white text-black" : "text-[#1f4e79] hover:text-black"
                }`}
              >
                {AUDIENCES[key].label}
              </button>
            ))}
          </div>

          <h1 className="font-display mx-auto mt-14 max-w-4xl text-5xl font-extrabold leading-[1.02] tracking-tight text-black sm:text-7xl lg:text-[6.5rem]">
            {copy.title}
          </h1>
          <p className="mx-auto mt-8 max-w-2xl text-lg leading-relaxed text-black/80">{copy.body}</p>
          <div className="mt-9 flex flex-wrap items-center justify-center gap-3">
            <Link href="/signup" className="btn-pill btn-pill-black">
              Get started
              <ArrowRight className="h-4 w-4" />
            </Link>
            <Link href="/checkout" className="btn-pill btn-pill-white">
              Try the demo store
            </Link>
          </div>

          {/* Product card */}
          <div id="platform" className="mx-auto mt-16 max-w-[720px] scroll-mt-24 rounded-t-[48px] bg-white px-6 pt-10 sm:px-8">
            <div className="font-display text-center text-5xl font-extrabold tracking-tight text-black">PayTrace</div>
            <div className="mt-6 rounded-2xl bg-[#f6f3ec] p-5 text-left sm:p-6">
              <div className="flex flex-wrap items-center justify-between gap-3">
                <div>
                  <div className="text-xs font-semibold uppercase tracking-wide text-black/50">Payment</div>
                  <div className="font-display text-3xl font-bold text-black">$189.99 <span className="text-base font-medium text-black/50">USD</span></div>
                </div>
                <span className="rounded-full bg-[#fff1c7] px-3.5 py-1.5 text-sm font-bold text-[#7a4b00]">Needs review</span>
              </div>
              <ol className="mt-5 space-y-0">
                {TIMELINE.map((step, i) => (
                  <li key={step.label} className="relative flex gap-4 pb-5 last:pb-0">
                    {i < TIMELINE.length - 1 && <span className="absolute left-[7px] top-5 h-full w-px bg-black/15" />}
                    <span className={`relative mt-1 h-4 w-4 shrink-0 rounded-full ring-4 ring-[#f6f3ec] ${TONE[step.tone]}`} />
                    <div className="flex flex-1 items-start justify-between gap-4">
                      <div>
                        <div className="text-base font-semibold text-black">{step.label}</div>
                        <div className="text-sm text-black/60">{step.detail}</div>
                      </div>
                      <span className="font-mono text-sm text-black/50">{step.time}</span>
                    </div>
                  </li>
                ))}
              </ol>
            </div>
            <div className="h-10" />
          </div>
        </div>
      </section>

      {/* How it works */}
      <section id="how-it-works" className="scroll-mt-20 px-6 py-24">
        <div className="mx-auto max-w-[1180px]">
          <h2 className="font-display max-w-3xl text-4xl font-extrabold leading-tight tracking-tight text-black sm:text-6xl">
            Three signals. One timeline.
          </h2>
          <p className="mt-5 max-w-2xl text-lg text-black/70">
            A failed payment rarely leaves a single clue. PayTrace joins what PayPal, your server and the buyer&apos;s browser each saw into one lifecycle you can read top to bottom.
          </p>
          <div className="mt-12 grid gap-5 md:grid-cols-3">
            {LAYERS.map((l, i) => (
              <div key={l.title} className="rounded-[28px] bg-[#f6f3ec] p-8">
                <div className="flex h-12 w-12 items-center justify-center rounded-full bg-white">
                  <l.icon className="h-6 w-6 text-paypal-navy" />
                </div>
                <div className="mt-6 text-sm font-bold text-black/40">0{i + 1}</div>
                <h3 className="font-display mt-1 text-2xl font-bold text-black">{l.title}</h3>
                <p className="mt-3 text-base leading-relaxed text-black/70">{l.body}</p>
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* Features */}
      <section id="features" className="scroll-mt-20 px-6 pb-24">
        <div className="mx-auto max-w-[1180px]">
          <h2 className="font-display max-w-3xl text-4xl font-extrabold leading-tight tracking-tight text-black sm:text-6xl">
            Built to protect every charge
          </h2>
          <div className="mt-12 grid gap-5 md:grid-cols-2">
            {FEATURES.map((f) => (
              <div key={f.title} className={`rounded-[28px] p-8 sm:p-10 ${f.bg}`}>
                <f.icon className="h-8 w-8 text-black" />
                <h3 className="font-display mt-6 text-3xl font-bold leading-tight text-black">{f.title}</h3>
                <p className="mt-4 text-base leading-relaxed text-black/75">{f.body}</p>
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* CTA */}
      <section className="px-6 pb-24">
        <div className="mx-auto max-w-[1180px] rounded-[40px] bg-paypal-navy px-8 py-16 text-center sm:px-16">
          <h2 className="font-display mx-auto max-w-3xl text-4xl font-extrabold leading-tight tracking-tight text-white sm:text-6xl">
            Trace your first payment today
          </h2>
          <p className="mx-auto mt-5 max-w-xl text-lg text-white/80">
            Create an account and explore the sandbox data, or run a test checkout and watch PayTrace catch a timeout.
          </p>
          <div className="mt-9 flex flex-wrap items-center justify-center gap-3">
            <Link href="/signup" className="btn-pill btn-pill-white">
              Sign Up
            </Link>
            <Link href="/login" className="btn-pill border border-white text-white hover:bg-white/10">
              Log In
            </Link>
          </div>
          <div className="mt-8 inline-flex items-center gap-2 text-sm text-white/70">
            <CheckCircle2 className="h-4 w-4" />
            PayPal Sandbox only. No real money moves.
          </div>
        </div>
      </section>

      {/* Footer */}
      <footer className="border-t border-slate-800 bg-white px-6 py-10">
        <div className="mx-auto flex max-w-[1180px] flex-wrap items-center gap-x-10 gap-y-4">
          <Logo />
          <Link href="/checkout" className="text-base font-medium text-black hover:underline">Demo store</Link>
          <Link href="/login" className="text-base font-medium text-black hover:underline">Log In</Link>
          <Link href="/signup" className="text-base font-medium text-black hover:underline">Sign Up</Link>
          <p className="w-full text-sm text-black/50">
            PayTrace is an independent hackathon prototype for PayPal payment observability.
          </p>
        </div>
      </footer>
    </div>
  );
}
