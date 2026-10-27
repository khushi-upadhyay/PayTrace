"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { api, PaymentItem } from "@/lib/api";
import {
  CreditCard,
  Search,
  Filter,
  ArrowRight,
  Loader2,
  AlertTriangle,
  CheckCircle,
  HelpCircle,
  ChevronLeft,
  ChevronRight,
  ExternalLink,
} from "lucide-react";

export default function PaymentsPage() {
  const [payments, setPayments] = useState<PaymentItem[]>([]);
  const [total, setTotal] = useState(0);
  const [page, setPage] = useState(1);
  const [pageSize] = useState(15);
  const [search, setSearch] = useState("");
  const [statusFilter, setStatusFilter] = useState<string>("");
  const [sourceFilter, setSourceFilter] = useState<string>("");
  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState<string | null>(null);

  const fetchPayments = async () => {
    try {
      setLoading(true);
      setLoadError(null);
      const res = await api.getPayments({
        page,
        page_size: pageSize,
        search: search.trim() || undefined,
        status: statusFilter || undefined,
        source_mode: sourceFilter || undefined,
      });
      setPayments(res.items);
      setTotal(res.total);
    } catch (err: any) {
      console.error("Failed to fetch payments:", err);
      setLoadError(err.message || "Unable to load payment records.");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchPayments();
  }, [page, statusFilter, sourceFilter]);

  const handleSearchSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    setPage(1);
    fetchPayments();
  };

  const totalPages = Math.ceil(total / pageSize) || 1;

  return (
    <div className="space-y-6 max-w-7xl mx-auto animate-fadeIn">
      {/* Header */}
      <div className="flex flex-col md:flex-row md:items-center justify-between gap-4 pb-2">
        <div>
          <h1 className="font-display text-4xl font-bold tracking-tight text-black">
            Payment Ledger
          </h1>
          <p className="text-base text-black/70 mt-2">
            Searchable log of PayPal transactions, correlated event timelines, and failure statuses.
          </p>
        </div>
        <div className="text-xs text-slate-400 bg-slate-900 border border-slate-800 px-3 py-1.5 rounded-lg">
          Total Records: <span className="text-cyan-400 font-bold">{total}</span>
        </div>
      </div>

      {/* Filters & Search Toolbar */}
      <div className="glass-panel rounded-xl p-4 border border-slate-800 flex flex-col md:flex-row items-center justify-between gap-4">
        {/* Search Input */}
        <form onSubmit={handleSearchSubmit} className="flex-1 w-full md:w-auto relative">
          <Search className="w-4 h-4 text-slate-400 absolute left-3.5 top-1/2 -translate-y-1/2" />
          <input
            type="text"
            placeholder="Search by Payment ID, Order ID, Customer, or Failure Reason..."
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            className="w-full pl-10 pr-4 py-2 bg-slate-900/80 border border-slate-800 rounded-lg text-xs text-ink placeholder-slate-500 focus:outline-none focus:border-cyan-500 transition-colors"
          />
        </form>

        {/* Filter dropdowns */}
        <div className="flex items-center gap-3 w-full md:w-auto">
          {/* Status Filter */}
          <div className="flex items-center gap-1.5 text-xs text-slate-400">
            <Filter className="w-3.5 h-3.5 text-slate-400" />
            <select
              value={statusFilter}
              onChange={(e) => {
                setStatusFilter(e.target.value);
                setPage(1);
              }}
              className="bg-slate-900 border border-slate-800 text-slate-300 text-xs rounded-lg px-2.5 py-2 focus:outline-none focus:border-cyan-500"
            >
              <option value="">All Statuses</option>
              <option value="CAPTURED">CAPTURED</option>
              <option value="CAPTURE_UNCERTAIN">CAPTURE_UNCERTAIN</option>
              <option value="DENIED">DENIED</option>
              <option value="REFUNDED">REFUNDED</option>
              <option value="CREATED">CREATED</option>
            </select>
          </div>

          {/* Source Filter */}
          <select
            value={sourceFilter}
            onChange={(e) => {
              setSourceFilter(e.target.value);
              setPage(1);
            }}
            className="bg-slate-900 border border-slate-800 text-slate-300 text-xs rounded-lg px-2.5 py-2 focus:outline-none focus:border-cyan-500"
          >
            <option value="">All Sources</option>
            <option value="PAYPAL_SANDBOX">PayPal Sandbox</option>
            <option value="PAYPAL_LIVE">PayPal Live</option>
            <option value="SIMULATED">Simulated Demo</option>
          </select>
        </div>
      </div>

      {/* Table */}
      <div className="glass-panel rounded-xl border border-slate-800 overflow-hidden">
        {loading ? (
          <div className="flex flex-col items-center justify-center py-20 space-y-3">
            <Loader2 className="w-8 h-8 text-cyan-400 animate-spin" />
            <span className="text-xs text-slate-400">Loading ledger data...</span>
          </div>
        ) : loadError ? (
          <div className="text-center py-20 space-y-3">
            <AlertTriangle className="w-10 h-10 text-amber-400 mx-auto" />
            <p className="text-sm font-semibold text-slate-200">Payment records could not be loaded</p>
            <p className="text-xs text-slate-400">{loadError}</p>
            <button onClick={fetchPayments} className="px-4 py-2 bg-slate-800 hover:bg-slate-700 text-white rounded-lg text-xs font-semibold">
              Retry
            </button>
          </div>
        ) : payments.length === 0 ? (
          <div className="text-center py-20 space-y-3">
            <HelpCircle className="w-10 h-10 text-slate-500 mx-auto" />
            <p className="text-sm font-semibold text-slate-300">No payment records found</p>
            <p className="text-xs text-slate-500">Try adjusting your search criteria or resetting demo data.</p>
          </div>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-left text-xs">
              <thead className="bg-slate-900/60 border-b border-slate-800 text-slate-400 uppercase text-[10px]">
                <tr>
                  <th className="px-5 py-3">PayTrace ID</th>
                  <th className="px-5 py-3">PayPal Order ID</th>
                  <th className="px-5 py-3">Customer</th>
                  <th className="px-5 py-3">Amount</th>
                  <th className="px-5 py-3">Status</th>
                  <th className="px-5 py-3">Failure Reason</th>
                  <th className="px-5 py-3">Source</th>
                  <th className="px-5 py-3">Created</th>
                  <th className="px-5 py-3 text-right">Action</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-800/80">
                {payments.map((p) => (
                  <tr key={p.id} className="hover:bg-slate-900/40 transition-colors">
                    <td className="px-5 py-3.5 text-cyan-400 font-medium">
                      {p.id.slice(0, 10)}...
                    </td>
                    <td className="px-5 py-3.5 text-slate-300">
                      {p.paypal_order_id || "—"}
                    </td>
                    <td className="px-5 py-3.5 text-slate-300 text-[11px]">
                      {p.customer_ref}
                    </td>
                    <td className="px-5 py-3.5 font-semibold text-ink">
                      ${Number(p.amount).toFixed(2)} {p.currency}
                    </td>
                    <td className="px-5 py-3.5">
                      <span
                        className={`inline-flex items-center px-2 py-0.5 rounded-full text-[10px] font-semibold tracking-wide ${
                          p.status === "CAPTURED"
                            ? "bg-emerald-950 text-emerald-300 border border-emerald-800/60"
                            : p.status === "CAPTURE_UNCERTAIN"
                            ? "bg-amber-950 text-amber-300 border border-amber-800/60 animate-pulse"
                            : p.status === "DENIED" || p.status === "CAPTURE_FAILED"
                            ? "bg-rose-950 text-rose-300 border border-rose-800/60"
                            : p.status === "REFUNDED"
                            ? "bg-purple-950 text-purple-300 border border-purple-800/60"
                            : "bg-slate-800 text-slate-300"
                        }`}
                      >
                        {p.status}
                      </span>
                    </td>
                    <td className="px-5 py-3.5 text-slate-400 max-w-xs truncate">
                      {p.failure_reason || (p.status === "CAPTURED" ? "Normal settlement" : "—")}
                    </td>
                    <td className="px-5 py-3.5">
                      <span
                        className={`text-[10px] px-2 py-0.5 rounded border ${
                          p.source_mode === "SIMULATED"
                            ? "bg-slate-900 text-slate-400 border-slate-800"
                            : "bg-cyan-950 text-cyan-300 border-cyan-800/60"
                        }`}
                      >
                        {p.source_mode === "SIMULATED" ? "DEMO SIM" : "SANDBOX"}
                      </span>
                    </td>
                    <td className="px-5 py-3.5 text-slate-500 text-[11px]">
                      {new Date(p.created_at).toLocaleDateString()} {new Date(p.created_at).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}
                    </td>
                    <td className="px-5 py-3.5 text-right">
                      <Link
                        href={`/payments/${p.id}`}
                        className="px-2.5 py-1 rounded bg-cyan-950/80 hover:bg-cyan-900 border border-cyan-800/80 text-cyan-300 text-[11px] font-medium transition-colors inline-flex items-center gap-1"
                      >
                        Inspect
                        <ArrowRight className="w-3 h-3" />
                      </Link>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}

        {/* Pagination Bar */}
        <div className="p-4 border-t border-slate-800 flex items-center justify-between text-xs text-slate-400">
          <div>
            Showing Page <span className="text-ink font-bold">{page}</span> of{" "}
            <span className="text-ink font-bold">{totalPages}</span>
          </div>
          <div className="flex items-center gap-2">
            <button
              onClick={() => setPage((p) => Math.max(p - 1, 1))}
              disabled={page <= 1}
              className="p-1.5 rounded-lg bg-slate-900 border border-slate-800 hover:bg-slate-800 disabled:opacity-40 transition-colors"
            >
              <ChevronLeft className="w-4 h-4" />
            </button>
            <button
              onClick={() => setPage((p) => Math.min(p + 1, totalPages))}
              disabled={page >= totalPages}
              className="p-1.5 rounded-lg bg-slate-900 border border-slate-800 hover:bg-slate-800 disabled:opacity-40 transition-colors"
            >
              <ChevronRight className="w-4 h-4" />
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}
