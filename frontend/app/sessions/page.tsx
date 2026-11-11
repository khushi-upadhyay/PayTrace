"use client";

import { useCallback, useEffect, useState } from "react";
import Link from "next/link";
import { Activity, ArrowRight, History, Loader2, Video } from "lucide-react";
import { RefreshButton } from "@/components/ui/RefreshButton";
import { api, type BrowserSessionItem } from "@/lib/api";

export default function SessionsPage() {
  const [sessions, setSessions] = useState<BrowserSessionItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      setSessions(await api.getSessions());
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not load browser sessions.");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { void load(); }, [load]);

  return (
    <div className="mx-auto max-w-6xl space-y-6 animate-fadeIn">
      <header className="flex flex-col gap-4 border-b border-slate-800 pb-5 sm:flex-row sm:items-center sm:justify-between">
        <div>
          <h1 className="flex items-center gap-2 text-2xl font-bold text-black"><History className="h-6 w-6 text-cyan-400" /> Sessions</h1>
          <p className="mt-1 text-xs text-slate-400">Privacy-masked browser recordings correlate with PayTrace payments when available. Recording starts automatically and can be stopped from the notice. PayPal-hosted pages are not recorded.</p>
        </div>
        <RefreshButton onClick={() => void load()} loading={loading} />
      </header>

      {loading ? (
        <div className="flex justify-center py-20"><Loader2 className="h-7 w-7 animate-spin text-cyan-400" /></div>
      ) : error ? (
        <div role="alert" className="rounded-xl border border-rose-500/30 bg-rose-950/20 p-6 text-sm text-rose-200">
          <p>{error}</p><button onClick={() => void load()} className="mt-3 text-xs text-cyan-300 hover:underline">Retry</button>
        </div>
      ) : sessions.length === 0 ? (
        <div className="rounded-xl border border-slate-800 bg-slate-900/40 p-12 text-center">
          <Video className="mx-auto h-9 w-9 text-slate-500" />
          <h2 className="mt-3 text-sm font-semibold text-ink">No sessions recorded</h2>
          <p className="mx-auto mt-1 max-w-lg text-xs leading-relaxed text-slate-400">Session recording starts automatically unless stopped from the notice at the bottom of the app. Input values are masked, and payment processing does not depend on recording.</p>
        </div>
      ) : (
        <div className="overflow-hidden rounded-xl border border-slate-800 bg-slate-900/30">
          <div className="divide-y divide-slate-800">
            {sessions.map((session) => (
              <article key={session.id} className="flex flex-col gap-4 p-4 sm:flex-row sm:items-center sm:justify-between">
                <div className="min-w-0 space-y-1.5">
                  <div className="flex flex-wrap items-center gap-2">
                  <span className="inline-flex items-center gap-1.5 text-sm font-semibold text-ink"><Activity className="h-4 w-4 text-cyan-400" />{new Date(session.started_at).toLocaleString()}</span>
                    <span className="rounded border border-slate-700 px-1.5 py-0.5 font-mono text-[10px] text-slate-400">{session.events_count} events</span>
                    {!session.recording_enabled && <span className="rounded border border-slate-700 px-1.5 py-0.5 text-[10px] text-slate-400">Recording off</span>}
                  </div>
                  <p className="truncate font-mono text-[11px] text-slate-500">Session {session.id} · {session.visitor_ref}</p>
                <p className="truncate text-[11px] text-slate-500">{session.user_agent?.split(" ").slice(0, 2).join(" ") || "Browser details unavailable"}{session.ended_at ? ` · ${Math.max(0, Math.round((new Date(session.ended_at).getTime() - new Date(session.started_at).getTime()) / 60000))} min` : " · Active"}{typeof session.metadata_redacted?.initial_path === "string" ? ` · ${session.metadata_redacted.initial_path}` : ""}</p>
                  {session.payment_id && <p className="text-[11px] text-slate-400">Linked payment <Link className="font-mono text-cyan-300 hover:underline" href={`/payments/${session.payment_id}`}>{session.payment_id}</Link></p>}
                  {(session.payment_ids?.length ?? 0) > 1 && <div className="flex flex-wrap gap-2">{session.payment_ids?.slice(1).map((paymentId) => <Link key={paymentId} className="font-mono text-[10px] text-cyan-300 hover:underline" href={`/payments/${paymentId}`}>Payment {paymentId.slice(0, 8)}</Link>)}</div>}
                </div>
                <Link href={`/sessions/${session.id}`} className="inline-flex shrink-0 items-center gap-1.5 self-start rounded-lg bg-cyan-500 px-3.5 py-2 text-xs font-bold text-slate-950 hover:bg-cyan-400 sm:self-center">
                  Investigate session <ArrowRight className="h-3.5 w-3.5" />
                </Link>
              </article>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}
