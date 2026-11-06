import { RefreshCw } from "lucide-react";

/** The single Refresh button used on every page, so its size and colours never drift apart. */
export function RefreshButton({ onClick, loading = false }: { onClick: () => void; loading?: boolean }) {
  return (
    <button
      type="button"
      onClick={onClick}
      disabled={loading}
      className="inline-flex shrink-0 items-center gap-1.5 self-start rounded-lg border border-neutral-300 bg-white px-2.5 py-1.5 text-xs font-semibold text-black hover:bg-neutral-100 disabled:opacity-50"
    >
      <RefreshCw className={`h-3.5 w-3.5 ${loading ? "animate-spin" : ""}`} />
      Refresh
    </button>
  );
}
