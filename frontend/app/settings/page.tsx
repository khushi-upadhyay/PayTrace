"use client";

import { useCallback, useEffect, useState } from "react";
import { api, getApiBaseUrl } from "@/lib/api";
import {
  Settings,
  ShieldCheck,
  CheckCircle2,
  AlertTriangle,
  Loader2,
  Copy,
  ExternalLink,
  Lock,
  Database,
  Brain,
  Webhook,
} from "lucide-react";

export default function SettingsPage() {
  const [settingsData, setSettingsData] = useState<any | null>(null);
  const [loading, setLoading] = useState(true);
  const [copiedUrl, setCopiedUrl] = useState(false);
  const [loadError, setLoadError] = useState<string | null>(null);

  const loadSettings = useCallback(async () => {
    setLoading(true);
    setLoadError(null);
    try {
      const data = await api.getSettings();
      setSettingsData(data);
    } catch (err) {
      setLoadError(err instanceof Error ? err.message : "Unable to load settings.");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { void loadSettings(); }, [loadSettings]);

  const webhookUrl = `${getApiBaseUrl()}/api/webhooks/paypal`;

  const handleCopyWebhookUrl = () => {
    void navigator.clipboard.writeText(webhookUrl).then(() => {
      setCopiedUrl(true);
      setTimeout(() => setCopiedUrl(false), 2000);
    }).catch(() => setCopiedUrl(false));
  };

  if (loading && !settingsData) {
    return (
      <div className="flex flex-col items-center justify-center min-h-[60vh] space-y-4">
        <Loader2 className="w-8 h-8 text-cyan-400 animate-spin" />
        <p className="text-sm text-slate-400">Loading platform settings & security status...</p>
      </div>
    );
  }

  if (!settingsData) {
    return (
      <div role="alert" className="mx-auto max-w-xl rounded-xl border border-rose-500/30 bg-rose-950/20 p-8 text-center">
        <p className="text-sm font-semibold text-rose-200">Settings are unavailable</p>
        <p className="mt-2 text-xs text-slate-400">{loadError || "No settings response was returned."}</p>
        <button onClick={() => void loadSettings()} className="mt-4 rounded-lg bg-paypal-navy px-3 py-2 text-xs text-onsolid transition-colors duration-150 hover:bg-paypal-blue">Retry</button>
      </div>
    );
  }

  return (
    <div className="space-y-8 max-w-5xl mx-auto animate-fadeIn pb-16">
      {/* Header */}
      <div className="flex flex-col md:flex-row md:items-center justify-between gap-4 pb-2">
        <div>
          <h1 className="font-display text-4xl font-bold tracking-tight text-black">
            Integrations & Safety Policy
          </h1>
          <p className="text-base text-black/70 mt-2">
            Verification status of the explicitly configured PayPal environment, AI engine, and security boundaries.
          </p>
        </div>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
        {/* PayPal Integration Card */}
        <div className="glass-panel rounded-2xl p-6 border border-slate-800 space-y-4">
          <div className="flex items-center justify-between pb-3 border-b border-slate-800">
            <div className="flex items-center gap-2.5">
              <div className="w-8 h-8 rounded-lg bg-sky-500/20 text-sky-400 flex items-center justify-center font-bold">
                PP
              </div>
              <div>
                <h2 className="text-sm font-bold text-ink">PayPal {settingsData?.paypal?.environment || "Sandbox"} API</h2>
                <span className="text-[10px] text-slate-400">REST v2/checkout</span>
              </div>
            </div>
            <span
              className={`text-[10px] px-2 py-0.5 rounded border ${
                settingsData?.paypal?.is_configured
                  ? "bg-emerald-950 text-emerald-300 border-emerald-800"
                  : "bg-cyan-950 text-cyan-300 border-cyan-800"
              }`}
            >
              {settingsData?.paypal?.status_label || "SIMULATED DEMO"}
            </span>
          </div>

          <div className="space-y-2.5 text-xs">
            <div className="flex justify-between py-1 border-b border-slate-800/60">
              <span className="text-slate-400">Environment</span>
              <span className="text-slate-200 uppercase">{settingsData?.paypal?.environment || "sandbox"}</span>
            </div>
            <div className="flex justify-between py-1 border-b border-slate-800/60">
              <span className="text-slate-400">Client ID</span>
              <span className="text-slate-200">{settingsData?.paypal?.client_id_masked || "Not configured"}</span>
            </div>
            <div className="flex justify-between py-1">
              <span className="text-slate-400">Webhook Signature Verification</span>
              <span className={`flex items-center gap-1 ${settingsData?.paypal?.webhook_id_configured ? "text-emerald-400" : "text-amber-400"}`}>
                {settingsData?.paypal?.webhook_id_configured ? <CheckCircle2 className="w-3.5 h-3.5" /> : <AlertTriangle className="w-3.5 h-3.5" />}
                {settingsData?.paypal?.webhook_id_configured ? "Configured" : "Not configured"}
              </span>
            </div>
          </div>
        </div>

        {/* AI Engine Card */}
        <div className="glass-panel rounded-2xl p-6 border border-slate-800 space-y-4">
          <div className="flex items-center justify-between pb-3 border-b border-slate-800">
            <div className="flex items-center gap-2.5">
              <div className="w-8 h-8 rounded-lg bg-cyan-500/20 text-cyan-400 flex items-center justify-center font-bold">
                <Brain className="w-5 h-5" />
              </div>
              <div>
                <h2 className="text-sm font-bold text-ink">AI Investigator Engine</h2>
                <span className="text-[10px] text-slate-400">Evidence-Grounded</span>
              </div>
            </div>
            <span
              className={`text-[10px] px-2 py-0.5 rounded border ${
                settingsData?.ai?.is_configured
                  ? "bg-emerald-950 text-emerald-300 border-emerald-800"
                  : "bg-amber-950 text-amber-300 border-amber-800"
              }`}
            >
              {settingsData?.ai?.status_label || "DETERMINISTIC FALLBACK ACTIVE"}
            </span>
          </div>

          <div className="space-y-2.5 text-xs">
            <div className="flex justify-between py-1 border-b border-slate-800/60">
              <span className="text-slate-400">Provider</span>
              <span className="text-slate-200 capitalize">{settingsData?.ai?.provider || "OpenAI Compatible"}</span>
            </div>
            <div className="flex justify-between py-1 border-b border-slate-800/60">
              <span className="text-slate-400">Model</span>
              <span className="text-slate-200">{settingsData?.ai?.model || "gpt-4o-mini / Fallback v1"}</span>
            </div>
            <div className="flex justify-between py-1">
              <span className="text-slate-400">Fallback Path</span>
              <span className="text-emerald-400 flex items-center gap-1">
                <CheckCircle2 className="w-3.5 h-3.5" />
                Deterministic fallback available
              </span>
            </div>
          </div>
        </div>
      </div>

      {/* Webhook Configuration Guide */}
      <div className="glass-panel rounded-2xl p-6 border border-slate-800 space-y-4">
        <div className="flex items-center gap-2.5">
          <Webhook className="w-5 h-5 text-indigo-400" />
          <h2 className="text-sm font-bold text-ink">PayPal Webhook Endpoint Configuration</h2>
        </div>
        <p className="text-xs text-slate-300 leading-relaxed">
          Configure this URL in your PayPal Developer Sandbox application to receive real-time webhook events:
        </p>

        <div className="flex items-center gap-2 p-3 rounded-lg bg-slate-900 border border-slate-800">
          <code className="text-xs text-cyan-300 flex-1 truncate">{webhookUrl}</code>
          <button
            onClick={handleCopyWebhookUrl}
            className="px-3 py-1.5 bg-slate-800 hover:bg-slate-700 text-ink rounded text-xs font-semibold flex items-center gap-1 transition-colors duration-150"
          >
            <Copy className="w-3.5 h-3.5" />
            {copiedUrl ? "Copied" : "Copy"}
          </button>
        </div>

        <div className="text-[11px] text-slate-400 space-y-1">
          <span className="font-bold text-slate-300 block">Required Subscribed Events:</span>
          <div className="flex flex-wrap gap-1.5 pt-1">
            {["CHECKOUT.ORDER.APPROVED", "PAYMENT.CAPTURE.COMPLETED", "PAYMENT.CAPTURE.DENIED", "PAYMENT.CAPTURE.REFUNDED"].map((evt) => (
              <span key={evt} className="px-2 py-0.5 rounded bg-slate-950 border border-slate-800 text-slate-300">
                {evt}
              </span>
            ))}
          </div>
        </div>
      </div>

      {/* Security & Safety Guardrails */}
      <div className="glass-card rounded-2xl p-6 border border-slate-800 space-y-4">
        <h2 className="text-sm font-bold text-ink flex items-center gap-2">
          <Lock className="w-4 h-4 text-emerald-400" />
          PayTrace Production Safety Guardrails
        </h2>

        <div className="grid grid-cols-1 md:grid-cols-3 gap-4 text-xs">
          <div className="p-3.5 rounded-xl bg-slate-900/40 border border-slate-800 space-y-1">
            <span className="font-bold text-emerald-400 block">No Blind Retries</span>
            <p className="text-slate-400 text-[11px] leading-relaxed">
              Uncertain states suppress automatic retry execution until provider reconciliation confirms order status.
            </p>
          </div>

          <div className="p-3.5 rounded-xl bg-slate-900/40 border border-slate-800 space-y-1">
            <span className="font-bold text-emerald-400 block">Human Policy Gating</span>
            <p className="text-slate-400 text-[11px] leading-relaxed">
              AI recommendations cannot directly invoke PayPal refund APIs without operator review.
            </p>
          </div>

          <div className="p-3.5 rounded-xl bg-slate-900/40 border border-slate-800 space-y-1">
            <span className="font-bold text-emerald-400 block">Credential Redaction</span>
            <p className="text-slate-400 text-[11px] leading-relaxed">
              Secret keys, tokens, and payment card numbers are permanently redacted before database persistence.
            </p>
          </div>
        </div>
      </div>
    </div>
  );
}
