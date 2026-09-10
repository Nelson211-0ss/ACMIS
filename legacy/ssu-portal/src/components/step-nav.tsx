"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { Check, Lock } from "lucide-react";
import { cn } from "@/lib/cn";
import { STEPS, type StepSlug } from "@/lib/application";

/**
 * Wizard navigation.
 *
 * Steps are never locked: an applicant may fill them in any order, and hiding
 * later steps behind earlier ones just makes people abandon the form when they
 * cannot find the marksheet they need for step 2.
 *
 * On a phone this is a horizontally scrolling strip of numbered pills; from
 * `lg` it becomes a vertical list with hints.
 *
 * The active step is marked by a tinted fill and a ring, not by an accent bar
 * down its edge — the state reads from the whole row rather than a stripe
 * beside it, which also keeps the row aligned with every other list in the app.
 */
export function StepNav({
  applicationId,
  completed,
  readOnly,
}: {
  applicationId: string;
  completed: StepSlug[];
  /** Submitted applications show the strip but cannot be edited. */
  readOnly?: boolean;
}) {
  const pathname = usePathname();
  const done = new Set(completed);
  const currentIndex = STEPS.findIndex((s) => pathname.endsWith(`/${s.slug}`));
  const doneCount = STEPS.filter((s) => done.has(s.slug)).length;

  return (
    <>
      {/* Phone: scrolling pills */}
      <nav aria-label="Application steps" className="lg:hidden">
        <ol className="scroll-thin -mx-4 flex gap-2 overflow-x-auto px-4 pb-1">
          {STEPS.map((step, i) => {
            const active = i === currentIndex;
            const complete = done.has(step.slug);
            return (
              <li key={step.slug} className="shrink-0">
                <Link
                  href={`/apply/${applicationId}/${step.slug}`}
                  aria-current={active ? "step" : undefined}
                  className={cn(
                    "flex items-center gap-2 rounded-full border px-3.5 py-2 text-[12.5px] font-medium transition-colors",
                    active
                      ? "border-brand-700 bg-brand-700 text-white"
                      : complete
                        ? "border-green-600/30 bg-green-100 text-green-700"
                        : "border-line-strong bg-surface text-muted hover:bg-sunken",
                  )}
                >
                  {complete && !active ? (
                    <Check className="h-3.5 w-3.5" aria-hidden />
                  ) : (
                    <span className="nums">{i + 1}</span>
                  )}
                  <span className="whitespace-nowrap">{step.label}</span>
                </Link>
              </li>
            );
          })}
        </ol>
      </nav>

      {/* Desktop: vertical list */}
      <nav aria-label="Application steps" className="hidden lg:block">
        <div className="rounded-xl border border-line bg-surface p-2">
          <p className="px-2.5 pb-2 pt-1.5 text-[11.5px] font-semibold uppercase tracking-wide text-faint">
            <span className="nums">
              {doneCount} of {STEPS.length}
            </span>{" "}
            steps done
          </p>

          <ol className="space-y-0.5">
            {STEPS.map((step, i) => {
              const active = i === currentIndex;
              const complete = done.has(step.slug);
              return (
                <li key={step.slug}>
                  <Link
                    href={`/apply/${applicationId}/${step.slug}`}
                    aria-current={active ? "step" : undefined}
                    className={cn(
                      "flex items-start gap-3 rounded-lg px-2.5 py-2.5 transition-colors",
                      active
                        ? "bg-brand-50 ring-1 ring-brand-200"
                        : "hover:bg-sunken",
                    )}
                  >
                    <span
                      className={cn(
                        "mt-px flex h-6 w-6 shrink-0 items-center justify-center rounded-full border text-[11px] font-semibold transition-colors",
                        complete
                          ? "border-green-600 bg-green-600 text-white"
                          : active
                            ? "border-brand-700 bg-brand-700 text-white"
                            : "border-line-strong bg-surface text-muted",
                      )}
                    >
                      {complete ? (
                        <Check className="h-3.5 w-3.5" aria-hidden />
                      ) : (
                        <span className="nums">{i + 1}</span>
                      )}
                    </span>
                    <span className="min-w-0">
                      <span
                        className={cn(
                          "block text-[13.5px] leading-snug",
                          active ? "font-semibold text-brand-800" : "font-medium text-ink",
                        )}
                      >
                        {step.label}
                      </span>
                      <span className="mt-0.5 block text-[12px] leading-snug text-muted">
                        {step.hint}
                      </span>
                    </span>
                  </Link>
                </li>
              );
            })}
          </ol>
        </div>

        {readOnly ? (
          <p className="mt-3 flex items-start gap-2 rounded-lg border border-line bg-sunken px-3 py-2.5 text-[12px] leading-snug text-muted">
            <Lock className="mt-0.5 h-3.5 w-3.5 shrink-0" aria-hidden />
            This application has been submitted and can no longer be edited.
          </p>
        ) : null}
      </nav>
    </>
  );
}
