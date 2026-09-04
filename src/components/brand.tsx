import Link from "next/link";
import { institution } from "@/lib/institution";
import { cn } from "@/lib/cn";

/**
 * Wordmark. An inline SVG crest rather than an image file — it is under 400
 * bytes, needs no request, and stays sharp on every screen density.
 *
 * The mark is an open book under a five-pointed star: the star from the
 * national flag, the book for the institution. Flat fills, no gradient.
 */
export function Crest({ className }: { className?: string }) {
  return (
    <svg
      viewBox="0 0 32 32"
      className={cn("h-8 w-8", className)}
      role="img"
      aria-label={`${institution.short} crest`}
    >
      <rect width="32" height="32" rx="7" fill="var(--brand-700)" />
      <path
        d="M16 6.2l1.62 3.42 3.68.5-2.7 2.55.68 3.68L16 14.6l-3.28 1.75.68-3.68-2.7-2.55 3.68-.5z"
        fill="var(--gold-500)"
      />
      <path
        d="M6.6 19.4c3.1-1.15 6.2-1.15 9.4 0 3.2-1.15 6.3-1.15 9.4 0v5.3c-3.1-1.15-6.2-1.15-9.4 0-3.2-1.15-6.3-1.15-9.4 0z"
        fill="#fff"
        fillOpacity="0.92"
      />
      <path d="M16 19.4v5.3" stroke="var(--brand-700)" strokeWidth="1.1" />
    </svg>
  );
}

export function Wordmark({
  href = "/",
  tone = "light",
  className,
}: {
  href?: string;
  /** `dark` inverts the type for use on the navy sidebar. */
  tone?: "light" | "dark";
  className?: string;
}) {
  return (
    <Link
      href={href}
      className={cn("flex items-center gap-2.5 min-w-0", className)}
    >
      <Crest className="shrink-0" />
      <span className="min-w-0 leading-tight">
        <span
          className={cn(
            "block truncate text-[14.5px] font-semibold",
            tone === "dark" ? "text-sidebar-ink-strong" : "text-ink",
          )}
        >
          {institution.name}
        </span>
        <span
          className={cn(
            "block truncate text-[11.5px]",
            tone === "dark" ? "text-sidebar-ink" : "text-muted",
          )}
        >
          Student &amp; Admissions Portal
        </span>
      </span>
    </Link>
  );
}
