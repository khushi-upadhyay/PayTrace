import React from "react";
import { AlertCircle, AlertTriangle, HelpCircle, ImageOff, Tag, DollarSign } from "lucide-react";

interface ReviewFlagChipProps {
  flag: string;
}

export function ReviewFlagChip({ flag }: ReviewFlagChipProps) {
  switch (flag) {
    case "confirm_stock":
      return (
        <span className="inline-flex items-center gap-1 rounded-full bg-[#fffbeb] px-2 py-0.5 text-xs font-medium text-[#b45309] border border-[#fde68a]">
          <AlertTriangle className="h-3 w-3" />
          Confirm stock
        </span>
      );
    case "stock_unknown":
      return (
        <span className="inline-flex items-center gap-1 rounded-full bg-[#faf5ff] px-2 py-0.5 text-xs font-medium text-[#7e22ce] border border-[#e9d5ff]">
          <HelpCircle className="h-3 w-3" />
          Stock unknown
        </span>
      );
    case "missing_image":
      return (
        <span className="inline-flex items-center gap-1 rounded-full bg-[#fff1f2] px-2 py-0.5 text-xs font-medium text-[#be123c] border border-[#fecdd3]">
          <ImageOff className="h-3 w-3" />
          Missing image
        </span>
      );
    case "invalid_price":
      return (
        <span className="inline-flex items-center gap-1 rounded-full bg-[#fff1f2] px-2 py-0.5 text-xs font-medium text-[#be123c] border border-[#fecdd3]">
          <DollarSign className="h-3 w-3" />
          Invalid price
        </span>
      );
    case "missing_description":
      return (
        <span className="inline-flex items-center gap-1 rounded-full bg-[#f1f5f9] px-2 py-0.5 text-xs font-medium text-[#475569] border border-[#e2e8f0]">
          <AlertCircle className="h-3 w-3" />
          Missing description
        </span>
      );
    case "no_tags":
      return (
        <span className="inline-flex items-center gap-1 rounded-full bg-[#f1f5f9] px-2 py-0.5 text-xs font-medium text-[#475569] border border-[#e2e8f0]">
          <Tag className="h-3 w-3" />
          No tags
        </span>
      );
    default:
      return (
        <span className="inline-flex items-center gap-1 rounded-full bg-[#f1f5f9] px-2 py-0.5 text-xs font-medium text-[#475569] border border-[#e2e8f0]">
          {flag.replace(/_/g, " ")}
        </span>
      );
  }
}

