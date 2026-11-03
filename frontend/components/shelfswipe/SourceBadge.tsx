import React from "react";
import { Sparkles, Globe, PenTool } from "lucide-react";

interface SourceBadgeProps {
  source: string;
}

export function SourceBadge({ source }: SourceBadgeProps) {
  const norm = source.toLowerCase();
  if (norm === "channel3") {
    return (
      <span className="inline-flex items-center gap-1 rounded-md bg-blue-50 px-2 py-0.5 text-xs font-semibold text-blue-700 border border-blue-200">
        <Globe className="h-3 w-3" />
        Imported from Channel3
      </span>
    );
  }
  if (norm === "manual") {
    return (
      <span className="inline-flex items-center gap-1 rounded-md bg-emerald-50 px-2 py-0.5 text-xs font-semibold text-emerald-700 border border-emerald-200">
        <PenTool className="h-3 w-3" />
        Manual
      </span>
    );
  }
  return (
    <span className="inline-flex items-center gap-1 rounded-md bg-slate-100 px-2 py-0.5 text-xs font-semibold text-slate-700 border border-slate-200">
      <Sparkles className="h-3 w-3 text-amber-500" />
      Demo data
    </span>
  );
}

