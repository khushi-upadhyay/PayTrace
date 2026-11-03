import React from "react";
import { AlertCircle, AlertTriangle, HelpCircle, ImageOff, Tag, DollarSign } from "lucide-react";

interface ReviewFlagChipProps {
  flag: string;
}

export function ReviewFlagChip({ flag }: ReviewFlagChipProps) {
  switch (flag) {
    case "confirm_stock":
      return (
        <span className="inline-flex items-center gap-1 rounded-full bg-amber-50 px-2 py-0.5 text-xs font-medium text-amber-700 border border-amber-200">
          <AlertTriangle className="h-3 w-3" />
          Confirm stock
        </span>
      );
    case "stock_unknown":
      return (
        <span className="inline-flex items-center gap-1 rounded-full bg-purple-50 px-2 py-0.5 text-xs font-medium text-purple-700 border border-purple-200">
          <HelpCircle className="h-3 w-3" />
          Stock unknown
        </span>
      );
    case "missing_image":
      return (
        <span className="inline-flex items-center gap-1 rounded-full bg-rose-50 px-2 py-0.5 text-xs font-medium text-rose-700 border border-rose-200">
          <ImageOff className="h-3 w-3" />
          Missing image
        </span>
      );
    case "invalid_price":
      return (
        <span className="inline-flex items-center gap-1 rounded-full bg-rose-50 px-2 py-0.5 text-xs font-medium text-rose-700 border border-rose-200">
          <DollarSign className="h-3 w-3" />
          Invalid price
        </span>
      );
    case "missing_description":
      return (
        <span className="inline-flex items-center gap-1 rounded-full bg-slate-100 px-2 py-0.5 text-xs font-medium text-slate-600 border border-slate-200">
          <AlertCircle className="h-3 w-3" />
          Missing description
        </span>
      );
    case "no_tags":
      return (
        <span className="inline-flex items-center gap-1 rounded-full bg-slate-100 px-2 py-0.5 text-xs font-medium text-slate-600 border border-slate-200">
          <Tag className="h-3 w-3" />
          No tags
        </span>
      );
    default:
      return (
        <span className="inline-flex items-center gap-1 rounded-full bg-slate-100 px-2 py-0.5 text-xs font-medium text-slate-600 border border-slate-200">
          {flag.replace(/_/g, " ")}
        </span>
      );
  }
}

