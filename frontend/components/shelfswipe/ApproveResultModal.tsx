"use client";

import React from "react";
import { X, CheckCircle, AlertTriangle, Info } from "lucide-react";
import { ApproveResponse } from "@/lib/shelfswipe-api";

interface ApproveResultModalProps {
  result: ApproveResponse;
  onClose: () => void;
}

export function ApproveResultModal({ result, onClose }: ApproveResultModalProps) {
  const approvedCount = result.approved.length;
  const rejectedCount = result.rejected.length;

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-slate-900/50 p-4 backdrop-blur-xs">
      <div className="w-full max-w-md rounded-2xl bg-white shadow-2xl border border-slate-200 overflow-hidden flex flex-col">
        {/* Header */}
        <div className="flex items-center justify-between border-b border-slate-100 px-6 py-4">
          <div>
            <h2 className="text-base font-bold text-slate-900">Batch Approval Results</h2>
            <p className="text-xs text-slate-500">Summary of reviewed draft products</p>
          </div>
          <button
            onClick={onClose}
            className="rounded-lg p-1 text-slate-400 hover:bg-slate-100 hover:text-slate-600"
          >
            <X className="h-5 w-5" />
          </button>
        </div>

        {/* Content */}
        <div className="p-6 space-y-4">
          <div className="grid grid-cols-2 gap-3">
            <div className="rounded-xl bg-emerald-50 border border-emerald-200 p-3.5">
              <div className="flex items-center gap-1.5 text-emerald-800 text-xs font-semibold">
                <CheckCircle className="h-4 w-4 text-emerald-600" />
                Approved
              </div>
              <div className="text-2xl font-bold text-emerald-700 mt-1">{approvedCount}</div>
              <p className="text-[11px] text-emerald-600 mt-0.5">Moved to Live store</p>
            </div>
            <div className="rounded-xl bg-rose-50 border border-rose-200 p-3.5">
              <div className="flex items-center gap-1.5 text-rose-800 text-xs font-semibold">
                <AlertTriangle className="h-4 w-4 text-rose-600" />
                Rejected
              </div>
              <div className="text-2xl font-bold text-rose-700 mt-1">{rejectedCount}</div>
              <p className="text-[11px] text-rose-600 mt-0.5">Kept in Draft</p>
            </div>
          </div>

          {rejectedCount > 0 && (
            <div>
              <h4 className="text-xs font-bold text-slate-700 uppercase tracking-wider mb-2">
                Rejection Reasons
              </h4>
              <div className="space-y-1.5 max-h-48 overflow-y-auto">
                {result.rejected.map((item, idx) => (
                  <div
                    key={idx}
                    className="flex items-center justify-between rounded-lg bg-slate-50 px-3 py-2 text-xs border border-slate-200"
                  >
                    <span className="font-mono text-slate-600 truncate max-w-[180px]">
                      {item.id}
                    </span>
                    <span className="rounded-md bg-rose-100 px-2 py-0.5 font-semibold text-rose-800">
                      {item.reason === "invalid_price"
                        ? "Invalid Price ($0)"
                        : item.reason === "already_live"
                        ? "Already Live"
                        : item.reason}
                    </span>
                  </div>
                ))}
              </div>
            </div>
          )}

          <div className="rounded-lg bg-slate-50 border border-slate-200 p-3 text-xs text-slate-600 flex items-start gap-2">
            <Info className="h-4 w-4 text-slate-400 shrink-0 mt-0.5" />
            <span>
              Remaining draft products: <strong className="text-slate-900">{result.still_draft_count}</strong>.
              You can edit invalid products directly to resolve issues and approve them.
            </span>
          </div>
        </div>

        {/* Footer */}
        <div className="border-t border-slate-100 px-6 py-3 flex justify-end bg-slate-50">
          <button
            type="button"
            onClick={onClose}
            className="rounded-lg bg-paypal-navy px-4 py-2 text-xs font-semibold text-white hover:bg-opacity-90"
          >
            Done
          </button>
        </div>
      </div>
    </div>
  );
}

