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
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-[#0f172a]/50 p-4 backdrop-blur-xs">
      <div className="w-full max-w-md rounded-2xl bg-white shadow-2xl border border-[#e2e8f0] overflow-hidden flex flex-col">
        {/* Header */}
        <div className="flex items-center justify-between border-b border-[#f1f5f9] px-6 py-4">
          <div>
            <h2 className="text-base font-bold text-[#0f172a]">Batch Approval Results</h2>
            <p className="text-xs text-[#64748b]">Summary of reviewed draft products</p>
          </div>
          <button
            onClick={onClose}
            className="rounded-lg p-1 text-[#94a3b8] hover:bg-[#f1f5f9] hover:text-[#475569]"
          >
            <X className="h-5 w-5" />
          </button>
        </div>

        {/* Content */}
        <div className="p-6 space-y-4">
          <div className="grid grid-cols-2 gap-3">
            <div className="rounded-xl bg-[#ecfdf5] border border-[#a7f3d0] p-3.5">
              <div className="flex items-center gap-1.5 text-[#065f46] text-xs font-semibold">
                <CheckCircle className="h-4 w-4 text-[#059669]" />
                Approved
              </div>
              <div className="text-2xl font-bold text-[#047857] mt-1">{approvedCount}</div>
              <p className="text-[11px] text-[#059669] mt-0.5">Moved to Live store</p>
            </div>
            <div className="rounded-xl bg-[#fff1f2] border border-[#fecdd3] p-3.5">
              <div className="flex items-center gap-1.5 text-[#9f1239] text-xs font-semibold">
                <AlertTriangle className="h-4 w-4 text-[#e11d48]" />
                Rejected
              </div>
              <div className="text-2xl font-bold text-[#be123c] mt-1">{rejectedCount}</div>
              <p className="text-[11px] text-[#e11d48] mt-0.5">Kept in Draft</p>
            </div>
          </div>

          {rejectedCount > 0 && (
            <div>
              <h4 className="text-xs font-bold text-[#334155] uppercase tracking-wider mb-2">
                Rejection Reasons
              </h4>
              <div className="space-y-1.5 max-h-48 overflow-y-auto">
                {result.rejected.map((item, idx) => (
                  <div
                    key={idx}
                    className="flex items-center justify-between rounded-lg bg-[#f8fafc] px-3 py-2 text-xs border border-[#e2e8f0]"
                  >
                    <span className="font-mono text-[#475569] truncate max-w-[180px]">
                      {item.id}
                    </span>
                    <span className="rounded-md bg-[#ffe4e6] px-2 py-0.5 font-semibold text-[#9f1239]">
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

          <div className="rounded-lg bg-[#f8fafc] border border-[#e2e8f0] p-3 text-xs text-[#475569] flex items-start gap-2">
            <Info className="h-4 w-4 text-[#94a3b8] shrink-0 mt-0.5" />
            <span>
              Remaining draft products: <strong className="text-[#0f172a]">{result.still_draft_count}</strong>.
              You can edit invalid products directly to resolve issues and approve them.
            </span>
          </div>
        </div>

        {/* Footer */}
        <div className="border-t border-[#f1f5f9] px-6 py-3 flex justify-end bg-[#f8fafc]">
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

