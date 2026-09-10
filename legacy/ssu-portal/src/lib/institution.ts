/**
 * Single source of truth for institution identity.
 *
 * Every student-facing string comes from here, so one deployment can serve
 * Juba, Upper Nile, Bahr el Ghazal or Rumbek by changing environment variables
 * instead of forking the codebase. When this grows into real multi-tenancy,
 * replace the module body with a per-request lookup keyed on hostname — the
 * call sites do not change.
 */
export const institution = {
  name: process.env.NEXT_PUBLIC_INSTITUTION_NAME ?? "University of Juba",
  short: process.env.NEXT_PUBLIC_INSTITUTION_SHORT ?? "UoJ",
  city: process.env.NEXT_PUBLIC_INSTITUTION_CITY ?? "Juba, Central Equatoria",
  academicYear: process.env.NEXT_PUBLIC_ACADEMIC_YEAR ?? "2026/2027",
  applicationFeeSSP: Number(process.env.NEXT_PUBLIC_APPLICATION_FEE_SSP ?? 15000),
  supportEmail: "admissions@example.ss",
  supportPhone: "+211 920 000 000",
} as const;

/** Application cycle deadlines, shown on the apply landing page. */
export const admissionCycle = {
  opens: "2026-06-01",
  closes: "2026-08-31",
  resultsBy: "2026-09-20",
  semesterStarts: "2026-10-05",
} as const;
