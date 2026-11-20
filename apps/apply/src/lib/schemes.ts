import type { PublicAdmissionScheme } from "@acmis/api-client"

/**
 * Whether a cycle can actually be applied to right now.
 *
 * Being listed is not the same question. A scheme stays open until somebody in
 * the admissions office closes it, so one whose late deadline passed last week
 * is still listed while `start_application` refuses it with "Applications
 * closed on …". Offering it anyway sends an applicant through a programme
 * chooser to a dead end, which is the worst place to be told.
 *
 * Deliberately applied in the journey rather than to `/public/admission-schemes`
 * itself. That endpoint reports what the institution has marked open, and two
 * screens here need the full list for a different reason entirely — to put a
 * name to the scheme an existing application was made under, which does not
 * stop being true when the cycle closes.
 */
export function isOpenNow(scheme: PublicAdmissionScheme, now: Date = new Date()): boolean {
  // No status check: `/public/admission-schemes` already returns only schemes
  // the institution has marked open, and its payload carries no `status` field
  // to test. An earlier version of this read `scheme.status !== "open"` against
  // the full `AdmissionScheme` type, which the endpoint does not return — the
  // field was `undefined` on every row, every cycle was filtered out, and the
  // apply journey offered nothing at all while looking perfectly healthy.
  const deadline = scheme.late_closes_at ?? scheme.closes_at
  return new Date(deadline).getTime() >= now.getTime()
}

/** Those that can be applied to, soonest deadline first. */
export function openNow(
  schemes: PublicAdmissionScheme[],
  now: Date = new Date(),
): PublicAdmissionScheme[] {
  return schemes
    .filter((scheme) => isOpenNow(scheme, now))
    .sort((a, b) =>
      (a.late_closes_at ?? a.closes_at).localeCompare(b.late_closes_at ?? b.closes_at),
    )
}
