import { Loader2 } from "lucide-react";

/**
 * Shown instantly by Next's route-segment Suspense boundary (loading.tsx)
 * while a page's code chunk loads, so sidebar navigation never looks frozen.
 */
export function RouteLoading() {
  return (
    <div className="flex min-h-[60vh] w-full items-center justify-center" role="status" aria-label="Loading page">
      <Loader2 className="h-6 w-6 animate-spin text-paypal-blue" />
      <span className="sr-only">Loading...</span>
    </div>
  );
}
