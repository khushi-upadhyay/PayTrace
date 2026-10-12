"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { api } from "@/lib/api";
import { AlertCircle, RotateCcw, Zap, CheckCircle2, Loader2, ExternalLink } from "lucide-react";

export function Header() {
  const router = useRouter();
  const [loadingAction, setLoadingAction] = useState<string | null>(null);
  const [statusNotice, setStatusNotice] = useState<string | null>(null);

  const handleTriggerScenario = async (scenario: string, label: string) => {
    try {
      setLoadingAction(scenario);
      const res = await api.triggerScenario(scenario);
      setStatusNotice(`Triggered: ${res.title}`);
      setTimeout(() => setStatusNotice(null), 5000);
      if (res.payment_id) {
        router.push(`/payments/${res.payment_id}`);
      } else {
        router.refresh();
      }
    } catch (err: any) {
      alert(`Error triggering scenario: ${err.message}`);
    } finally {
      setLoadingAction(null);
    }
  };

  const handleResetData = async () => {
    if (!confirm("Reset demo data to default clean state?")) return;
    try {
      setLoadingAction("reset");
      await api.resetDemoData();
      setStatusNotice("Demo data cleanly reset and re-seeded.");
      setTimeout(() => setStatusNotice(null), 4000);
      router.refresh();
      window.location.reload();
    } catch (err: any) {
      alert(`Error resetting demo data: ${err.message}`);
    } finally {
      setLoadingAction(null);
    }
  };

    <header className="h-16 border-b border-slate-800 bg-slate-950/70 backdrop-blur-md px-8 flex items-center justify-between sticky top-0 z-30">
      {/* Left: Status notice or context */}
      <div className="flex items-center gap-3">
        {statusNotice ? (
          <div className="flex items-center gap-2 px-3 py-1.5 rounded-full bg-cyan-950/80 border border-cyan-800/80 text-cyan-300 text-xs font-medium animate-fadeIn">
            <CheckCircle2 className="w-3.5 h-3.5 text-cyan-400" />
            {statusNotice}
          </div>
        ) : (
          <div className="flex items-center gap-2 text-xs text-slate-400">
            <span className="w-2 h-2 rounded-full bg-emerald-400 animate-pulse"></span>
            <span>API Gateway <span className="text-slate-200 font-mono">http://localhost:8000</span></span>
          </div>
        )}
      </div>

      {/* Right: Demo Scenario Action Bar */}
      <div className="flex items-center gap-2.5">
        <div className="flex items-center gap-1.5 p-1 rounded-lg bg-slate-900/80 border border-slate-800">
          <span className="text-[11px] font-semibold text-slate-400 px-2 uppercase tracking-wide">
            Demo Scenarios:
          </span>

          <button
            onClick={() => handleTriggerScenario("timeout_before_response", "Timeout Scenario")}
            disabled={!!loadingAction}
            className="flex items-center gap-1.5 px-3 py-1.5 rounded-md text-xs font-semibold bg-amber-500/10 text-amber-300 border border-amber-500/30 hover:bg-amber-500/20 transition-all duration-150 disabled:opacity-50"
            title="Demonstrate capture timeout where provider captured but merchant backend timed out"
          >
            {loadingAction === "timeout_before_response" ? (
              <Loader2 className="w-3.5 h-3.5 animate-spin" />
            ) : (
              <Zap className="w-3.5 h-3.5 text-amber-400" />
            )}
            Simulate Timeout
          </button>

          <button
            onClick={() => handleTriggerScenario("capture_denied", "Card Declined")}
            disabled={!!loadingAction}
            className="flex items-center gap-1.5 px-3 py-1.5 rounded-md text-xs font-semibold bg-rose-500/10 text-rose-300 border border-rose-500/30 hover:bg-rose-500/20 transition-all duration-150 disabled:opacity-50"
          >
            {loadingAction === "capture_denied" ? (
              <Loader2 className="w-3.5 h-3.5 animate-spin" />
            ) : (
              <AlertCircle className="w-3.5 h-3.5 text-rose-400" />
            )}
            Simulate Decline
          </button>

          <button
            onClick={handleResetData}
            disabled={!!loadingAction}
            className="flex items-center gap-1.5 px-3 py-1.5 rounded-md text-xs font-medium text-slate-400 hover:text-slate-200 hover:bg-slate-800 transition-all duration-150 disabled:opacity-50"
            title="Reset seeded demonstration payments"
          >
            {loadingAction === "reset" ? (
              <Loader2 className="w-3.5 h-3.5 animate-spin" />
            ) : (
              <RotateCcw className="w-3.5 h-3.5" />
            )}
            Reset Data
          </button>
        </div>
      </div>
    </header>
  );
}
