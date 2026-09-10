/**
 * Formatting helpers.
 *
 * Locale-aware throughout, because a deployment serves Kampala and Juba and
 * an institution's own locale is configured per tenant. Nothing here hardcodes
 * a currency symbol or a date order.
 */

/**
 * Money from integer minor units.
 *
 * Minor units are always hundredths, whatever the currency — that is the
 * convention the ledger and `Money` in `core/schemas.py` hold to, and the
 * scale factor is therefore never in question. What *does* vary is how many
 * of those digits are worth showing: UGX has no subunit anybody transacts in,
 * so 177,700,000 minor units reads as "UGX 1,777,000" and not
 * "UGX 1,777,000.00".
 *
 * Getting this wrong is expensive in one specific direction. Treating UGX as
 * zero-decimal on the client showed every fee a hundred times too large —
 * a semester bill of UGX 1.8m rendered as UGX 178m — which is alarming rather
 * than merely untidy.
 */
export function money(
  amountMinor: number | null | undefined,
  currency = "UGX",
  locale = "en-UG",
  fractionDigits = minorUnitsFor(currency),
): string {
  if (amountMinor === null || amountMinor === undefined) return "—"
  const value = amountMinor / 100
  try {
    return new Intl.NumberFormat(locale, {
      style: "currency",
      currency,
      minimumFractionDigits: fractionDigits,
      maximumFractionDigits: fractionDigits,
    }).format(value)
  } catch {
    // An unknown currency code should not blank a fee statement.
    return `${currency} ${value.toLocaleString(locale, {
      minimumFractionDigits: fractionDigits,
      maximumFractionDigits: fractionDigits,
    })}`
  }
}

/**
 * How many decimal places of a currency are worth showing.
 *
 * Not a scale factor — see `money`. UGX, RWF and a few others have no
 * subunit in practice, and "UGX 1,500,000.00" is two digits of false
 * precision on every figure a bursary reads all day.
 */
export function minorUnitsFor(currency: string): number {
  const zeroDecimal = new Set([
    "UGX", "RWF", "BIF", "DJF", "GNF", "JPY", "KRW", "KMF", "PYG",
    "VND", "VUV", "XAF", "XOF", "XPF", "CLP", "ISK",
  ])
  return zeroDecimal.has(currency.toUpperCase()) ? 0 : 2
}

/** A compact figure for a stat tile: 12,400 -> "12.4k". */
export function compactNumber(value: number | null | undefined, locale = "en-UG"): string {
  if (value === null || value === undefined) return "—"
  return new Intl.NumberFormat(locale, { notation: "compact", maximumFractionDigits: 1 }).format(
    value,
  )
}

export function number(value: number | null | undefined, locale = "en-UG"): string {
  if (value === null || value === undefined) return "—"
  return new Intl.NumberFormat(locale).format(value)
}

export function percent(
  value: number | null | undefined,
  locale = "en-UG",
  fractionDigits = 1,
): string {
  if (value === null || value === undefined) return "—"
  return new Intl.NumberFormat(locale, {
    style: "percent",
    minimumFractionDigits: fractionDigits,
    maximumFractionDigits: fractionDigits,
  }).format(value / 100)
}

/** A date, in the institution's locale and timezone. */
export function date(
  value: string | Date | null | undefined,
  locale = "en-UG",
  timeZone = "Africa/Kampala",
): string {
  if (!value) return "—"
  const parsed = typeof value === "string" ? new Date(value) : value
  if (Number.isNaN(parsed.getTime())) return "—"
  return new Intl.DateTimeFormat(locale, {
    day: "numeric",
    month: "short",
    year: "numeric",
    timeZone,
  }).format(parsed)
}

export function dateTime(
  value: string | Date | null | undefined,
  locale = "en-UG",
  timeZone = "Africa/Kampala",
): string {
  if (!value) return "—"
  const parsed = typeof value === "string" ? new Date(value) : value
  if (Number.isNaN(parsed.getTime())) return "—"
  return new Intl.DateTimeFormat(locale, {
    day: "numeric",
    month: "short",
    year: "numeric",
    hour: "2-digit",
    minute: "2-digit",
    timeZone,
  }).format(parsed)
}

/**
 * "3 days ago", "in 2 hours".
 *
 * Used for deadlines and audit timestamps. Absolute dates are shown alongside
 * wherever the exact moment matters — "2 hours ago" is friendly and useless in
 * an audit trail.
 */
export function relativeTime(
  value: string | Date | null | undefined,
  locale = "en-UG",
): string {
  if (!value) return "—"
  const parsed = typeof value === "string" ? new Date(value) : value
  if (Number.isNaN(parsed.getTime())) return "—"

  const deltaSeconds = (parsed.getTime() - Date.now()) / 1000
  const formatter = new Intl.RelativeTimeFormat(locale, { numeric: "auto" })
  const units: Array<[Intl.RelativeTimeFormatUnit, number]> = [
    ["year", 31_536_000],
    ["month", 2_592_000],
    ["week", 604_800],
    ["day", 86_400],
    ["hour", 3_600],
    ["minute", 60],
  ]
  for (const [unit, seconds] of units) {
    if (Math.abs(deltaSeconds) >= seconds) {
      return formatter.format(Math.round(deltaSeconds / seconds), unit)
    }
  }
  return formatter.format(Math.round(deltaSeconds), "second")
}

/** A duration in minutes as "1h 45m" — used for examination timers. */
export function duration(minutes: number | null | undefined): string {
  if (minutes === null || minutes === undefined) return "—"
  const hours = Math.floor(minutes / 60)
  const rest = minutes % 60
  if (hours === 0) return `${rest}m`
  if (rest === 0) return `${hours}h`
  return `${hours}h ${rest}m`
}

/** Seconds remaining as "12:04" — the live countdown in an online examination. */
export function countdown(secondsRemaining: number): string {
  const clamped = Math.max(0, Math.floor(secondsRemaining))
  const hours = Math.floor(clamped / 3600)
  const minutes = Math.floor((clamped % 3600) / 60)
  const seconds = clamped % 60
  const pad = (n: number) => String(n).padStart(2, "0")
  return hours > 0
    ? `${hours}:${pad(minutes)}:${pad(seconds)}`
    : `${pad(minutes)}:${pad(seconds)}`
}

/** "Nakato, Sarah Grace" — the sort order a registry list uses. */
export function surnameFirst(person: {
  surname: string
  given_names: string
  other_names?: string | null
}): string {
  const rest = [person.given_names, person.other_names].filter(Boolean).join(" ")
  return `${person.surname}, ${rest}`
}

export function initials(name: string): string {
  return name
    .split(/\s+/)
    .filter(Boolean)
    .slice(0, 2)
    .map((part) => part[0]?.toUpperCase() ?? "")
    .join("")
}

/** Turn `results:senate_approve` into "Results — senate approve" for a UI label. */
export function humanisePermission(code: string): string {
  const [noun, verb] = code.split(":")
  const words = (value: string) => value.replace(/_/g, " ")
  return verb ? `${capitalise(words(noun ?? ""))} — ${words(verb)}` : capitalise(words(code))
}

export function humaniseStatus(value: string | null | undefined): string {
  if (!value) return "—"
  return capitalise(value.replace(/_/g, " "))
}

function capitalise(value: string): string {
  return value.charAt(0).toUpperCase() + value.slice(1)
}
