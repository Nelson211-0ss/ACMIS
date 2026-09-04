import type { LetterGrade } from "./types";

/** SSP amounts, grouped, no decimals — nobody quotes piastres. */
export function ssp(amount: number): string {
  return `SSP ${amount.toLocaleString("en-US", { maximumFractionDigits: 0 })}`;
}

export function shortDate(iso: string): string {
  return new Date(iso).toLocaleDateString("en-GB", {
    day: "numeric",
    month: "short",
    year: "numeric",
  });
}

export function longDate(iso: string): string {
  return new Date(iso).toLocaleDateString("en-GB", {
    weekday: "long",
    day: "numeric",
    month: "long",
    year: "numeric",
  });
}

export function relativeDays(iso: string): string {
  const days = Math.round(
    (new Date(iso).getTime() - Date.now()) / 86_400_000,
  );
  if (days === 0) return "today";
  if (days === 1) return "tomorrow";
  if (days === -1) return "yesterday";
  return days > 0 ? `in ${days} days` : `${Math.abs(days)} days ago`;
}

export function initials(first: string, last: string): string {
  return `${first.charAt(0)}${last.charAt(0)}`.toUpperCase();
}

export function fileSize(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${Math.round(bytes / 1024)} KB`;
  return `${(bytes / 1024 / 1024).toFixed(1)} MB`;
}

// --- Grading ---------------------------------------------------------------

/**
 * Mark-to-grade mapping on the scale used across South Sudanese universities:
 * coursework out of 40 plus final exam out of 60, graded A–F on a 4.0 scale.
 */
const GRADE_BANDS: ReadonlyArray<{
  min: number;
  grade: LetterGrade;
  points: number;
}> = [
  { min: 80, grade: "A", points: 4.0 },
  { min: 75, grade: "B+", points: 3.5 },
  { min: 70, grade: "B", points: 3.0 },
  { min: 65, grade: "C+", points: 2.5 },
  { min: 60, grade: "C", points: 2.0 },
  { min: 50, grade: "D", points: 1.5 },
  { min: 40, grade: "E", points: 1.0 },
  { min: 0, grade: "F", points: 0.0 },
];

export function gradeFor(total: number): { grade: LetterGrade; points: number } {
  const band = GRADE_BANDS.find((b) => total >= b.min) ?? GRADE_BANDS.at(-1)!;
  return { grade: band.grade, points: band.points };
}

/** Credit-weighted GPA. Returns null when there is nothing to average. */
export function gpa(
  entries: ReadonlyArray<{ points: number; creditHours: number }>,
): number | null {
  const credits = entries.reduce((sum, e) => sum + e.creditHours, 0);
  if (credits === 0) return null;
  const weighted = entries.reduce((sum, e) => sum + e.points * e.creditHours, 0);
  return Math.round((weighted / credits) * 100) / 100;
}

/** Degree classification from a final CGPA. */
export function classification(cgpa: number): string {
  if (cgpa >= 3.6) return "First Class";
  if (cgpa >= 3.0) return "Second Class, Upper";
  if (cgpa >= 2.4) return "Second Class, Lower";
  if (cgpa >= 2.0) return "Pass";
  return "Below pass";
}

export function isPass(grade: LetterGrade): boolean {
  return grade !== "F" && grade !== "E";
}

// --- Phone numbers ---------------------------------------------------------

/**
 * Normalise a South Sudanese mobile number to +211XXXXXXXXX.
 * Accepts 0920..., 211920..., +211 920 ..., and spaced variants, because
 * students type all of them.
 */
export function normalisePhone(input: string): string | null {
  const digits = input.replace(/[^\d]/g, "");
  let local: string;
  if (digits.startsWith("211")) local = digits.slice(3);
  else if (digits.startsWith("0")) local = digits.slice(1);
  else local = digits;
  // MTN, Zain and Digitel subscriber numbers are all 9 digits after the code.
  if (!/^9\d{8}$/.test(local)) return null;
  return `+211${local}`;
}

export function displayPhone(e164: string): string {
  const m = /^\+211(\d{3})(\d{3})(\d{3})$/.exec(e164);
  return m ? `+211 ${m[1]} ${m[2]} ${m[3]}` : e164;
}
