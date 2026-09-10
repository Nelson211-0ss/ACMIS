import Link from "next/link";
import { getBranding } from "@/lib/data/repo";
import { cn } from "@/lib/cn";

/**
 * Wordmark and crest. Both read the live branding a super administrator set on
 * the Settings page rather than the build-time `institution` constant, so
 * renaming the university or uploading a logo takes effect everywhere the
 * chrome appears without a redeploy.
 *
 * Async server components: every call site is a server component (checked),
 * and the alternative — threading branding through as props — would touch
 * eight layouts to say the same thing.
 */

/**
 * The uploaded logo if there is one, otherwise the built-in mark: an open book
 * under a five-pointed star, the star from the national flag and the book for
 * the institution. Inline SVG, under 400 bytes, no request, flat fills.
 */
export async function Crest({ className }: { className?: string }) {
  const branding = await getBranding();

  if (branding.logo) {
    return (
      // eslint-disable-next-line @next/next/no-img-element
      <img
        src={branding.logo}
        alt={`${branding.short} logo`}
        className={cn("h-8 w-8 rounded-md object-contain", className)}
      />
    );
  }

  return (
    <svg
      viewBox="0 0 32 32"
      className={cn("h-8 w-8", className)}
      role="img"
      aria-label={`${branding.short} crest`}
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

export async function Wordmark({
  href = "/",
  tone = "light",
  className,
}: {
  href?: string;
  /** `dark` inverts the type for use on the navy sidebar. */
  tone?: "light" | "dark";
  className?: string;
}) {
  const branding = await getBranding();

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
          {branding.name}
        </span>
        {/* Hidden below `sm`. On a 360px screen the institution's own name is
            the thing worth the width, and leaving the strapline in meant both
            lines truncated to fit beside the theme toggle and sign-in button —
            two half-readable lines instead of one whole one. */}
        <span
          className={cn(
            "hidden truncate text-[11.5px] sm:block",
            tone === "dark" ? "text-sidebar-ink" : "text-muted",
          )}
        >
          Student &amp; Admissions Portal
        </span>
      </span>
    </Link>
  );
}
