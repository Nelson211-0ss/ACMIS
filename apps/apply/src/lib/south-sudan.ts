/**
 * Reference data for South Sudan.
 *
 * Kept in this app rather than in `@acmis/ui`, which is a design system and has
 * no business knowing what a county is. Kept out of the API for now because
 * none of it is per-institution: the states are the country's, and the subject
 * list is the examinations council's.
 *
 * The Ugandan demo tenant that ships with the repo does not use any of this —
 * its applicants hold UACE results and come from districts. That is a seeding
 * difference, not a conflict: the fields on `Applicant` are deliberately
 * generic (`district_of_origin`, `nationality`, `country_code`), and this file
 * is what fills them in for a South Sudanese deployment.
 */

/** The ten states and three administrative areas. */
export const STATES = [
  "Central Equatoria",
  "Eastern Equatoria",
  "Western Equatoria",
  "Jonglei",
  "Lakes",
  "Northern Bahr el Ghazal",
  "Unity",
  "Upper Nile",
  "Warrap",
  "Western Bahr el Ghazal",
  "Abyei Administrative Area",
  "Ruweng Administrative Area",
  "Greater Pibor Administrative Area",
] as const

export type State = (typeof STATES)[number]

/** Subjects examinable at the South Sudan Certificate of Secondary Education. */
export const SSCSE_SUBJECTS = [
  "English",
  "Mathematics",
  "Additional Mathematics",
  "Biology",
  "Chemistry",
  "Physics",
  "Geography",
  "History",
  "Agriculture",
  "Commerce",
  "Business Studies",
  "Computer Studies",
  "Christian Religious Education",
  "Islamic Religious Education",
  "Arabic",
  "Kiswahili",
  "Citizenship",
] as const

export type Subject = (typeof SSCSE_SUBJECTS)[number]

/**
 * A mobile number in the one shape the API should ever store.
 *
 * MTN, Zain and Digitel subscriber numbers are all nine digits beginning with
 * 9, so the check is exact rather than a length guess. Accepts the three forms
 * people actually type — `0920 123 456`, `+211 920 123 456`, `920123456` — and
 * returns `null` for anything else rather than storing a number nobody can
 * ring, which is how an offer goes unanswered.
 */
export function normalisePhone(input: string): string | null {
  const digits = input.replace(/\D/g, "")
  let local: string
  if (digits.startsWith("211")) local = digits.slice(3)
  else if (digits.startsWith("0")) local = digits.slice(1)
  else local = digits

  if (!/^9\d{8}$/.test(local)) return null
  return `+211${local}`
}

/** `+211920123456` → `0920 123 456`, which is how it is read aloud. */
export function formatPhone(stored: string): string {
  const local = stored.replace(/\D/g, "").replace(/^211/, "")
  if (!/^9\d{8}$/.test(local)) return stored
  return `0${local.slice(0, 3)} ${local.slice(3, 6)} ${local.slice(6)}`
}

/**
 * Whether a date of birth is plausible for an applicant.
 *
 * A range rather than a minimum: the floor catches a mistyped year on a
 * school leaver, and the ceiling is high enough not to turn away the mature
 * students a public university is meant to admit.
 */
export function ageProblem(dateOfBirth: string): string | null {
  const born = new Date(dateOfBirth)
  if (Number.isNaN(born.getTime())) return "Enter your date of birth."
  const years = (Date.now() - born.getTime()) / (365.25 * 86_400_000)
  if (years < 15) return "You must be at least 15 to apply."
  if (years > 70) return "That date of birth looks wrong — check the year."
  return null
}
