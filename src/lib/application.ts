import { z } from "zod";
import type {
  Application,
  DocumentKind,
  Programme,
  SubjectResult,
} from "./types";
import { normalisePhone } from "./format";
import { programmeById } from "./data/reference";
import { STATES, SSCSE_SUBJECTS } from "./data/reference";

// ---------------------------------------------------------------------------
// Wizard steps. One list drives the step navigation, the progress meter and
// the "can I submit yet" check, so they can never disagree.
// ---------------------------------------------------------------------------

export const STEPS = [
  { slug: "personal", label: "Personal details", hint: "Who you are and how we reach you" },
  { slug: "education", label: "Secondary results", hint: "Your SSCSE subjects and marks" },
  { slug: "programme", label: "Programme choices", hint: "Rank up to three programmes" },
  { slug: "documents", label: "Documents", hint: "Certificate, transcript, photo, ID" },
  { slug: "payment", label: "Application fee", hint: "Pay by mobile money or bank slip" },
  { slug: "review", label: "Review and submit", hint: "Check everything, then submit" },
] as const;

export type StepSlug = (typeof STEPS)[number]["slug"];

// ---------------------------------------------------------------------------
// Validation
// ---------------------------------------------------------------------------

const ssPhone = z.string().transform((v, ctx) => {
  const normalised = normalisePhone(v);
  if (!normalised) {
    ctx.addIssue({
      code: z.ZodIssueCode.custom,
      message: "Enter a valid mobile number, for example 0920 123 456.",
    });
    return z.NEVER;
  }
  return normalised;
});

export const personalSchema = z.object({
  firstName: z.string().trim().min(2, "Enter your first name."),
  middleName: z.string().trim().optional(),
  lastName: z.string().trim().min(2, "Enter your family name."),
  dateOfBirth: z
    .string()
    .min(1, "Enter your date of birth.")
    .refine((v) => {
      const age = (Date.now() - new Date(v).getTime()) / (365.25 * 86_400_000);
      return age >= 15 && age <= 60;
    }, "Date of birth looks wrong — check the year."),
  sex: z.enum(["female", "male"], { message: "Select an option." }),
  nationality: z.string().trim().min(2, "Enter your nationality."),
  stateOfOrigin: z.enum(STATES, { message: "Select your state of origin." }),
  county: z.string().trim().min(2, "Enter your county."),
  phone: ssPhone,
  email: z.string().trim().toLowerCase().email("Enter a valid email address."),
  // Optional on purpose: many applicants from rural counties hold no national
  // ID when they apply, and blocking them here would exclude them entirely.
  nationalId: z.string().trim().optional(),
  disability: z.string().trim().optional(),
  guardianName: z.string().trim().min(2, "Enter a parent or guardian's name."),
  guardianPhone: ssPhone,
});

export const subjectResultSchema = z.object({
  subject: z.enum(SSCSE_SUBJECTS, { message: "Select a subject." }),
  mark: z.coerce
    .number()
    .int("Marks are whole numbers.")
    .min(0, "Marks cannot be negative.")
    .max(100, "Marks are out of 100."),
});

export const educationSchema = z.object({
  secondarySchool: z.string().trim().min(3, "Enter the name of your school."),
  schoolState: z.enum(STATES, { message: "Select the state where you sat SSCSE." }),
  indexNumber: z.string().trim().min(4, "Enter your SSCSE index number."),
  yearCompleted: z
    .string()
    .regex(/^\d{4}$/, "Enter a four-digit year.")
    .refine((v) => {
      const year = Number(v);
      return year >= 2005 && year <= new Date().getFullYear();
    }, "Year looks wrong."),
  subjects: z
    .array(subjectResultSchema)
    .min(6, "Enter at least six subjects.")
    .max(12, "Enter no more than twelve subjects.")
    .refine(
      (rows) => new Set(rows.map((r) => r.subject)).size === rows.length,
      "Each subject can only be entered once.",
    )
    .refine(
      (rows) => rows.some((r) => r.subject === "English"),
      "English is required for every programme.",
    ),
});

export const choicesSchema = z
  .array(z.string().min(1))
  .min(1, "Choose at least one programme.")
  .max(3, "You may rank at most three programmes.")
  .refine((ids) => new Set(ids).size === ids.length, "Choose three different programmes.")
  .refine((ids) => ids.every((id) => programmeById(id)), "One of the programmes is unknown.");

// ---------------------------------------------------------------------------
// Documents
// ---------------------------------------------------------------------------

export const REQUIRED_DOCUMENTS: ReadonlyArray<{
  kind: DocumentKind;
  label: string;
  hint: string;
  required: boolean;
}> = [
  {
    kind: "sscse_certificate",
    label: "SSCSE certificate",
    hint: "A clear photo or scan of the certificate itself.",
    required: true,
  },
  {
    kind: "sscse_transcript",
    label: "SSCSE marksheet",
    hint: "The statement of results showing each subject mark.",
    required: true,
  },
  {
    kind: "passport_photo",
    label: "Passport photograph",
    hint: "Plain background, face clearly visible.",
    required: true,
  },
  {
    kind: "national_id",
    label: "National ID or nationality certificate",
    hint: "Optional if you do not yet hold one — say so in your covering note.",
    required: false,
  },
  {
    kind: "birth_certificate",
    label: "Birth certificate",
    hint: "Optional. Helps if your ID is unavailable.",
    required: false,
  },
];

/** 4 MB. Deliberately generous for phone cameras, but capped for 2G uploads. */
export const MAX_DOCUMENT_BYTES = 4 * 1024 * 1024;

export const ACCEPTED_DOCUMENT_TYPES = [
  "application/pdf",
  "image/jpeg",
  "image/png",
  "image/webp",
] as const;

// ---------------------------------------------------------------------------
// Eligibility
// ---------------------------------------------------------------------------

/** Best-six aggregate, the convention used for admission scoring. */
export function aggregate(subjects: SubjectResult[]): number {
  if (subjects.length === 0) return 0;
  const best = [...subjects].sort((a, b) => b.mark - a.mark).slice(0, 6);
  return Math.round(best.reduce((sum, s) => sum + s.mark, 0) / best.length);
}

export interface Eligibility {
  eligible: boolean;
  aggregate: number;
  /** Reasons the applicant does not qualify. Empty when eligible. */
  reasons: string[];
  /** How far above or below the cut-off, in aggregate points. */
  margin: number;
}

/**
 * Check an applicant's SSCSE record against a programme's stated requirements.
 *
 * This is advisory, shown to the applicant while they choose. It does not gate
 * submission — a marginal candidate may still apply, and the admissions board
 * makes the actual decision.
 */
export function checkEligibility(
  programme: Programme,
  subjects: SubjectResult[],
): Eligibility {
  const agg = aggregate(subjects);
  const reasons: string[] = [];

  const sat = new Set(subjects.map((s) => s.subject));
  const missing = programme.requiredSubjects.filter((s) => !sat.has(s));
  if (missing.length > 0) {
    reasons.push(
      `${programme.name} requires ${missing.join(", ")}, which ${missing.length === 1 ? "is" : "are"} not in your results.`,
    );
  }

  // A required subject sat but failed still bars entry.
  const weak = programme.requiredSubjects
    .map((name) => subjects.find((s) => s.subject === name))
    .filter((s): s is SubjectResult => s !== undefined && s.mark < 50);
  if (weak.length > 0) {
    reasons.push(
      `A mark of at least 50 is needed in ${weak.map((s) => s.subject).join(", ")}.`,
    );
  }

  if (subjects.length > 0 && agg < programme.minimumAggregate) {
    reasons.push(
      `Your aggregate of ${agg} is below the ${programme.minimumAggregate} required.`,
    );
  }

  return {
    eligible: reasons.length === 0 && subjects.length > 0,
    aggregate: agg,
    reasons,
    margin: agg - programme.minimumAggregate,
  };
}

// ---------------------------------------------------------------------------
// Step completion — the single source of truth for progress and submission
// ---------------------------------------------------------------------------

export function isStepComplete(app: Application, step: StepSlug): boolean {
  switch (step) {
    case "personal":
      return personalSchema.safeParse(app.personal).success;
    case "education":
      return educationSchema.safeParse(app.education).success;
    case "programme":
      return choicesSchema.safeParse(app.choices.map((c) => c.programmeId)).success;
    case "documents":
      return REQUIRED_DOCUMENTS.filter((d) => d.required).every((d) =>
        app.documents.some((u) => u.kind === d.kind),
      );
    case "payment":
      return app.payment?.status === "confirmed" || app.payment?.status === "pending";
    case "review":
      return app.status !== "draft";
  }
}

/** Steps that must be complete before the application can be submitted. */
const SUBMITTABLE_STEPS: StepSlug[] = [
  "personal",
  "education",
  "programme",
  "documents",
  "payment",
];

export function completedSteps(app: Application): StepSlug[] {
  return SUBMITTABLE_STEPS.filter((s) => isStepComplete(app, s));
}

export function progressPercent(app: Application): number {
  return Math.round(
    (completedSteps(app).length / SUBMITTABLE_STEPS.length) * 100,
  );
}

export function canSubmit(app: Application): { ok: boolean; blocking: string[] } {
  const blocking = SUBMITTABLE_STEPS.filter((s) => !isStepComplete(app, s)).map(
    (s) => STEPS.find((step) => step.slug === s)!.label,
  );
  return { ok: blocking.length === 0 && app.status === "draft", blocking };
}

/** The next incomplete step, used for the "continue where you left off" link. */
export function nextIncompleteStep(app: Application): StepSlug {
  return SUBMITTABLE_STEPS.find((s) => !isStepComplete(app, s)) ?? "review";
}
