import Link from "next/link";

/** PayTrace mark: a navy badge with a "P" and a light-blue trace line. */
export function LogoMark({ className = "h-9 w-9" }: { className?: string }) {
  return (
    <svg viewBox="0 0 40 40" className={className} aria-hidden="true">
      <rect width="40" height="40" rx="11" fill="#1e2d8a" />
      <path d="M13 9h8.5a6.5 6.5 0 0 1 0 13H17.8V31H13V9Zm4.8 4.3v5h3.4a2.5 2.5 0 0 0 0-5h-3.4Z" fill="#fff" fillRule="evenodd" />
      <path d="M21 31c3.5 0 4.5-3.5 7-3.5s3 2 5 2" fill="none" stroke="#85cbf9" strokeWidth="2.4" strokeLinecap="round" />
    </svg>
  );
}

/** PayTrace logo: mark plus wordmark. `tone="light"` is for use on the navy bar. */
export function Logo({
  size = "md",
  href = "/",
  tone = "dark",
  markOnly = false,
}: {
  size?: "md" | "lg";
  href?: string;
  tone?: "dark" | "light";
  markOnly?: boolean;
}) {
  const text = size === "lg" ? "text-4xl" : "text-2xl";
  const mark = size === "lg" ? "h-11 w-11" : "h-9 w-9";
  return (
    <Link href={href} className="inline-flex items-center gap-2.5" aria-label="PayTrace home">
      <LogoMark className={mark} />
      {!markOnly && (
        <span className={`font-display ${text} font-bold tracking-tight ${tone === "light" ? "text-white" : "text-black"}`}>
          PayTrace
        </span>
      )}
    </Link>
  );
}
