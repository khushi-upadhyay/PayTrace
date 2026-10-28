"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { api, IncidentItem } from "@/lib/api";
import {
  AlertTriangle,
  ShieldAlert,
  ArrowRight,
  Loader2,
  Clock,
  DollarSign,
  Activity,
  Layers,
  FileText,
} from "lucide-react";

export default function IncidentsPage() {
  const [incidents, setIncidents] = useState<IncidentItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState<string | null>(null);

  const fetchIncidents = async () => {
    try {
      setLoading(true);
      setLoadError(null);
      const res = await api.getIncidents();
      setIncidents(res.items);
    } catch (err: any) {
      setLoadError(err.message || "Unable to load incidents from the backend.");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchIncidents();
  }, []);

  return (
    <div className="space-y-6 max-w-7xl mx-auto animate-fadeIn">
      {/* Header */}
      <div className="flex flex-col md:flex-row md:items-center justify-between gap-4 pb-2">
        <div>
          <h1 className="font-display text-4xl font-bold tracking-tight text-black">
            Detected Incidents
          </h1>
          <p className="text-base text-black/70 mt-2">
            Deterministic rule engine tracking failure spikes, timeout anomalies, and revenue at risk.
          </p>
        </div>
        <div className="text-xs text-slate-400 bg-slate-900 border border-slate-800 px-3 py-1.5 rounded-lg">
          Active Incidents: <span className="text-amber-400 font-bold">{incidents.length}</span>
        </div>
      </div>

      {loading ? (
        <div className="flex flex-col items-center justify-center py-20 space-y-3">
          <Loader2 className="w-8 h-8 text-cyan-400 animate-spin" />
          <span className="text-xs text-slate-400">Evaluating incident detection rules...</span>
        </div>
      ) : loadError ? (
        <div role="alert" className="rounded-xl border border-rose-500/30 bg-rose-950/20 p-6 text-center">
          <p className="text-sm font-semibold text-rose-200">Incident data is unavailable</p>
          <p className="mt-2 text-xs text-slate-400">{loadError}</p>
          <button onClick={fetchIncidents} className="mt-3 rounded-lg bg-paypal-navy px-3 py-2 text-xs text-onsolid transition-colors duration-150 hover:bg-paypal-blue">Retry</button>
        </div>
      ) : incidents.length === 0 ? (
        <div className="glass-panel p-12 rounded-xl text-center space-y-3 border border-slate-800">
          <Activity className="w-10 h-10 text-emerald-400 mx-auto" />
          <h3 className="text-base font-bold text-ink">All Systems Operating Normally</h3>
          <p className="text-xs text-slate-400 max-w-md mx-auto">
            No active threshold breaches or failure spikes detected. You can simulate an incident via the demo controls.
          </p>
        </div>
      ) : (
        <div className="grid grid-cols-1 gap-4">
          {incidents.map((inc) => (
            <div
              key={inc.id}
              className={`glass-panel rounded-2xl p-6 border transition-all duration-200 ${
                inc.severity === "HIGH" || inc.severity === "CRITICAL"
                  ? "border-amber-500/30 hover:border-amber-500/50 glow-amber transition-colors duration-150"
                  : "border-slate-800 hover:border-slate-700 transition-colors duration-150"
              }`}
            >
              <div className="flex flex-col lg:flex-row lg:items-center justify-between gap-6">
                <div className="space-y-3">
                  <div className="flex items-center gap-3">
                    <span
                      className={`text-[10px] font-bold px-2.5 py-1 rounded-full uppercase tracking-wider ${
                        inc.severity === "HIGH"
                          ? "bg-amber-950 text-amber-300 border border-amber-800"
                          : "bg-sky-950 text-sky-300 border border-sky-800"
                      }`}
                    >
                      {inc.severity} SEVERITY
                    </span>
                    <span className="text-xs text-slate-500">
                      Rule: {inc.detection_rule || "THRESHOLD_BREACH"}
                    </span>
                  </div>

                  <h2 className="text-lg font-bold text-ink tracking-tight">
                    {inc.title}
                  </h2>

                  <p className="text-xs text-slate-300 leading-relaxed max-w-3xl">
                    {inc.ai_summary || inc.root_cause}
                  </p>
                </div>

                {/* Right: Stats & Inspect Button */}
                <div className="flex flex-row lg:flex-col items-end justify-between lg:justify-center gap-4 shrink-0 border-t lg:border-t-0 pt-4 lg:pt-0 border-slate-800">
                  <div className="text-right">
                    <span className="text-[10px] text-slate-500 uppercase block">Potential Revenue at Risk</span>
                    <span className="text-lg font-black text-amber-400">
                      ${Number(inc.revenue_at_risk).toFixed(2)} {inc.currency}
                    </span>
                    <span className="text-[11px] text-slate-400 block mt-0.5">
                      {inc.affected_payment_count} Affected Payment{inc.affected_payment_count > 1 ? "s" : ""}
                    </span>
                  </div>

                  <Link
                    href={`/incidents/${inc.id}`}
                    className="px-4 py-2 rounded-lg bg-cyan-500 hover:bg-cyan-400 text-onsolid text-xs font-bold transition-colors inline-flex items-center gap-1.5"
                  >
                    View Diagnostic Report
                    <ArrowRight className="w-3.5 h-3.5" />
                  </Link>
                </div>
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
