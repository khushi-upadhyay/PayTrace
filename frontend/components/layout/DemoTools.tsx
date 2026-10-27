"use client";

import { useEffect, useRef, useState } from "react";
import { useRouter } from "next/navigation";
import { AlertCircle, CheckCircle2, FlaskConical, Loader2, RotateCcw, Zap } from "lucide-react";
import { api } from "@/lib/api";

/** Demo scenario triggers and data reset, tucked into a menu so the nav stays clean. */
export function DemoTools() {
  const router = useRouter();
  const [open, setOpen] = useState(false);
  const [loadingAction, setLoadingAction] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const ref = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!open) return;
    const onDown = (e: MouseEvent) => {
      if (ref.current && !ref.current.contains(e.target as Node)) setOpen(false);
    };
    document.addEventListener("mousedown", onDown);
    return () => document.removeEventListener("mousedown", onDown);
  }, [open]);

  const flash = (msg: string, ms = 5000) => {
    setNotice(msg);
    setTimeout(() => setNotice(null), ms);
  };

  const triggerScenario = async (scenario: string) => {
    try {
      setLoadingAction(scenario);
      const res = await api.triggerScenario(scenario);
      flash(`Triggered: ${res.title}`);
      setOpen(false);
      if (res.payment_id) router.push(`/payments/${res.payment_id}`);
      else router.refresh();
    } catch (err: any) {
      alert(`Error triggering scenario: ${err.message}`);
    } finally {
      setLoadingAction(null);
    }
  };

  const resetData = async () => {
    if (!confirm("Reset demo data to default clean state?")) return;
    try {
      setLoadingAction("reset");
      await api.resetDemoData();
      window.location.reload();
    } catch (err: any) {
      alert(`Error resetting demo data: ${err.message}`);
      setLoadingAction(null);
    }
  };

  const item =
    "flex w-full items-center gap-2.5 rounded-lg px-3 py-2.5 text-left text-sm font-medium text-slate-300 hover:bg-slate-800 disabled:opacity-50";

  return (
    <div ref={ref} className="relative">
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        aria-expanded={open}
        aria-haspopup="menu"
        className="flex h-9 items-center gap-2 rounded-full border border-white/40 px-3.5 text-sm font-semibold text-white hover:bg-white/10"
      >
        <FlaskConical className="h-4 w-4" />
        <span className="hidden lg:inline">Demo tools</span>
      </button>

      {notice && (
        <div className="absolute right-0 top-11 z-50 flex items-center gap-2 whitespace-nowrap rounded-full border border-cyan-800 bg-cyan-950 px-3 py-1.5 text-xs font-medium text-cyan-300 shadow-lg">
          <CheckCircle2 className="h-3.5 w-3.5" />
          {notice}
        </div>
      )}

      {open && (
        <div
          role="menu"
          className="absolute right-0 top-11 z-50 w-64 rounded-xl border border-slate-800 bg-slate-900 p-1.5 shadow-xl"
        >
          <div className="px-3 pb-1 pt-2 text-[11px] font-semibold uppercase tracking-wider text-slate-500">
            Demo scenarios
          </div>
          <button role="menuitem" className={item} disabled={!!loadingAction} onClick={() => triggerScenario("timeout_before_response")}>
            {loadingAction === "timeout_before_response" ? <Loader2 className="h-4 w-4 animate-spin" /> : <Zap className="h-4 w-4 text-amber-400" />}
            Simulate timeout
          </button>
          <button role="menuitem" className={item} disabled={!!loadingAction} onClick={() => triggerScenario("capture_denied")}>
            {loadingAction === "capture_denied" ? <Loader2 className="h-4 w-4 animate-spin" /> : <AlertCircle className="h-4 w-4 text-rose-400" />}
            Simulate decline
          </button>
          <div className="my-1 h-px bg-slate-800" />
          <button role="menuitem" className={item} disabled={!!loadingAction} onClick={resetData}>
            {loadingAction === "reset" ? <Loader2 className="h-4 w-4 animate-spin" /> : <RotateCcw className="h-4 w-4" />}
            Reset demo data
          </button>
        </div>
      )}
    </div>
  );
}
