"use client";

import { useEffect, useState } from "react";
import { useParams } from "next/navigation";
import Link from "next/link";
import { api, IncidentItem, PaymentItem } from "@/lib/api";
import {
  AlertTriangle,
  ArrowLeft,
  ArrowRight,
  ShieldAlert,
  FileText,
  Loader2,
  DollarSign,
  Activity,
  CheckCircle2,
  Printer,
  Sparkles,
} from "lucide-react";

export default function IncidentDetailPage() {
  const params = useParams();
  const incidentId = params.id as string;

  const [incident, setIncident] = useState<IncidentItem | null>(null);
  const [report, setReport] = useState<any | null>(null);
  const [generatingReport, setGeneratingReport] = useState(false);
  const [loading, setLoading] = useState(true);

  const fetchIncident = async () => {
    try {
      setLoading(true);
      const data = await api.getIncident(incidentId);
      setIncident(data);
    } catch (err: any) {
      console.error("Failed to fetch incident:", err);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    if (incidentId) {
      fetchIncident();
    }
  }, [incidentId]);

  const handleGenerateReport = async () => {
    try {
      setGeneratingReport(true);
      const res = await api.generateIncidentReport(incidentId);
      setReport(res);
    } catch (err: any) {
      alert(`Report generation failed: ${err.message}`);
    } finally {
      setGeneratingReport(false);
    }
  };

  if (loading) {
    return (
      <div className="flex flex-col items-center justify-center min-h-[60vh] space-y-4">
        <Loader2 className="w-8 h-8 text-cyan-400 animate-spin" />
        <p className="text-sm text-slate-400">Loading incident diagnostic information...</p>
      </div>
    );
  }

  if (!incident) {
    return (
      <div className="glass-panel p-8 rounded-xl border border-rose-500/30 text-center space-y-4 max-w-xl mx-auto my-12">
        <AlertTriangle className="w-10 h-10 text-rose-400 mx-auto" />
        <h2 className="text-lg font-bold text-ink">Incident Not Found</h2>
        <Link href="/incidents" className="px-4 py-2 bg-slate-800 hover:bg-slate-700 text-ink text-xs font-semibold rounded-lg inline-block transition-colors duration-150">
          Back to Incidents
        </Link>
      </div>
    );
  }

  return (
    <div className="space-y-8 max-w-7xl mx-auto animate-fadeIn pb-16">
      {/* Back button */}
      <div className="flex items-center justify-between">
        <Link
          href="/incidents"
          className="inline-flex items-center gap-1.5 text-xs text-slate-400 hover:text-slate-200 transition-colors"
        >
          <ArrowLeft className="w-4 h-4" />
          Back to Incidents
        </Link>

        <button
          onClick={handleGenerateReport}
          disabled={generatingReport}
          className="px-4 py-2 rounded-lg bg-cyan-500 hover:bg-cyan-400 text-onsolid text-xs font-bold transition-all duration-150 shadow-md shadow-cyan-500/20 flex items-center gap-2 disabled:opacity-50"
        >
          {generatingReport ? (
            <Loader2 className="w-4 h-4 animate-spin" />
          ) : (
            <Sparkles className="w-4 h-4" />
          )}
          Generate Executive AI Report
        </button>
      </div>

      {/* Incident Header Card */}
      <div className="glass-panel rounded-2xl p-6 border border-slate-800 space-y-6">
        <div className="flex flex-col lg:flex-row lg:items-center justify-between gap-6 pb-6 border-b border-slate-800">
          <div>
            <div className="flex items-center gap-3">
              <span
                className={`text-[10px] font-bold px-2.5 py-1 rounded-full uppercase tracking-wider ${
                  incident.severity === "HIGH"
                    ? "bg-amber-950 text-amber-300 border border-amber-800"
                    : "bg-sky-950 text-sky-300 border border-sky-800"
                }`}
              >
                {incident.severity} SEVERITY
              </span>
              <span className="text-xs text-slate-400">
                Status: <span className="text-ink font-bold">{incident.status}</span>
              </span>
            </div>
            <h1 className="text-2xl font-extrabold text-ink tracking-tight mt-2">
              {incident.title}
            </h1>
            <p className="text-xs text-slate-400 mt-1">
              Triggered by deterministic detection rule: <span className="text-cyan-300">{incident.detection_rule || "THRESHOLD_BREACH"}</span>
            </p>
          </div>

          <div className="flex items-center gap-6">
            <div className="text-right">
              <span className="text-[10px] text-slate-500 uppercase block">Potential Revenue at Risk</span>
              <span className="text-2xl font-black text-amber-400">
                ${Number(incident.revenue_at_risk).toFixed(2)} {incident.currency}
              </span>
            </div>
            <div className="text-right pl-6 border-l border-slate-800">
              <span className="text-[10px] text-slate-500 uppercase block">Impacted Payments</span>
              <span className="text-2xl font-black text-ink">
                {incident.affected_payment_count}
              </span>
            </div>
          </div>
        </div>

        {/* Root Cause Card */}
        <div className="space-y-2">
          <span className="text-[10px] uppercase text-slate-400 tracking-wider">Diagnostic Root Cause</span>
          <div className="p-4 rounded-xl bg-slate-900/60 border border-slate-800 text-xs text-slate-200 leading-relaxed">
            {incident.root_cause || incident.ai_summary}
          </div>
        </div>

        {incident.recurrence && (
          <div className="space-y-2">
            <span className="text-[10px] uppercase text-slate-400 tracking-wider">Pattern Over Time</span>
            <div
              className={`p-4 rounded-xl border text-xs leading-relaxed ${
                incident.recurrence.pattern_label
                  ? "bg-rose-950/30 border-rose-800/60 text-rose-200"
                  : "bg-slate-900/60 border-slate-800 text-slate-300"
              }`}
            >
              {incident.recurrence.pattern_label ||
                `First seen this week — no recurrence yet in the last ${incident.recurrence.window_days} days.`}
              <span className="block mt-1 text-[10px] text-slate-500">
                {incident.recurrence.payments_in_window} matching payment
                {incident.recurrence.payments_in_window === 1 ? "" : "s"} across{" "}
                {incident.recurrence.distinct_days_seen} day
                {incident.recurrence.distinct_days_seen === 1 ? "" : "s"} in the last{" "}
                {incident.recurrence.window_days} days.
              </span>
            </div>
          </div>
        )}
      </div>

      {/* Generated Report View if available */}
      {report && (
        <div className="glass-panel rounded-2xl p-8 border border-cyan-500/30 glow-blue space-y-6 animate-scaleUp">
          <div className="flex items-center justify-between pb-4 border-b border-slate-800">
            <div className="flex items-center gap-2">
              <FileText className="w-5 h-5 text-cyan-400" />
              <h2 className="text-base font-bold text-ink">Executive Diagnostic Incident Report</h2>
            </div>
            <span className="text-xs text-slate-400">
              Generated: {new Date(report.generated_at).toLocaleString()}
            </span>
          </div>

          <div className="space-y-4">
            <div className="p-4 rounded-xl bg-cyan-950/30 border border-cyan-800/40 text-xs text-cyan-200 leading-relaxed">
              <strong>Executive Summary:</strong> {report.executive_summary}
            </div>

            <div className="space-y-2">
              <h4 className="text-xs font-bold text-ink uppercase tracking-wider">Detailed Findings:</h4>
              <ul className="space-y-1.5">
                {report.detailed_findings.map((finding: string, i: number) => (
                  <li key={i} className="text-xs text-slate-300 flex items-start gap-2 bg-slate-900/40 p-2.5 rounded border border-slate-800">
                    <span className="text-cyan-400 font-bold">•</span>
                    <span>{finding}</span>
                  </li>
                ))}
              </ul>
            </div>

            <div className="space-y-2">
              <h4 className="text-xs font-bold text-ink uppercase tracking-wider">Recommended Mitigations:</h4>
              <ul className="space-y-1.5">
                {report.recommended_mitigations.map((mitigation: string, i: number) => (
                  <li key={i} className="text-xs text-emerald-300 flex items-start gap-2 bg-emerald-950/30 p-2.5 rounded border border-emerald-800/50">
                    <CheckCircle2 className="w-4 h-4 text-emerald-400 shrink-0" />
                    <span>{mitigation}</span>
                  </li>
                ))}
              </ul>
            </div>
          </div>
        </div>
      )}

      {/* Affected Payments Ledger Table */}
      <div className="glass-panel rounded-2xl border border-slate-800 overflow-hidden space-y-0">
        <div className="p-5 border-b border-slate-800">
          <h3 className="text-sm font-bold text-ink">Affected Payment Journeys</h3>
          <p className="text-xs text-slate-400 mt-0.5">Transactions correlated directly to this incident threshold breach</p>
        </div>

        <div className="overflow-x-auto">
          <table className="w-full text-left text-xs">
            <thead className="bg-slate-900/60 border-b border-slate-800 text-slate-400 uppercase text-[10px]">
              <tr>
                <th className="px-5 py-3">PayTrace ID</th>
                <th className="px-5 py-3">Order ID</th>
                <th className="px-5 py-3">Amount</th>
                <th className="px-5 py-3">Status</th>
                <th className="px-5 py-3">Failure Reason</th>
                <th className="px-5 py-3 text-right">Inspect</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-800/80">
              {incident.affected_payments?.map((p: any) => (
                <tr key={p.id} className="hover:bg-slate-900/40 transition-colors">
                  <td className="px-5 py-3.5 text-cyan-400 font-medium">
                    {p.id.slice(0, 14)}...
                  </td>
                  <td className="px-5 py-3.5 text-slate-300">
                    {p.paypal_order_id || "N/A"}
                  </td>
                  <td className="px-5 py-3.5 font-bold text-ink">
                    ${Number(p.amount).toFixed(2)} {p.currency}
                  </td>
                  <td className="px-5 py-3.5">
                    <span
                      className={`inline-flex items-center px-2 py-0.5 rounded-full text-[10px] font-semibold tracking-wide ${
                        p.status === "CAPTURE_UNCERTAIN"
                          ? "bg-amber-950 text-amber-300 border border-amber-800 animate-pulse"
                          : "bg-rose-950 text-rose-300 border border-rose-800"
                      }`}
                    >
                      {p.status}
                    </span>
                  </td>
                  <td className="px-5 py-3.5 text-slate-400 max-w-sm truncate">
                    {p.failure_reason || "Encountered failure"}
                  </td>
                  <td className="px-5 py-3.5 text-right">
                    <Link
                      href={`/payments/${p.id}`}
                      className="px-2.5 py-1 rounded bg-cyan-950/80 hover:bg-cyan-900 border border-cyan-800 text-cyan-300 text-[11px] font-medium transition-colors inline-flex items-center gap-1"
                    >
                      Inspect Timeline
                      <ArrowRight className="w-3 h-3" />
                    </Link>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
}
