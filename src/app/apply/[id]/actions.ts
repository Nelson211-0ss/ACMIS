"use server";

import { revalidatePath } from "next/cache";
import { redirect } from "next/navigation";
import { z } from "zod";
import {
  addDocument,
  attachPayment,
  getApplication,
  getScheme,
  removeDocument,
  updateApplication,
} from "@/lib/data/repo";
import {
  ACCEPTED_DOCUMENT_TYPES,
  MAX_DOCUMENT_BYTES,
  choicesSchema,
  educationSchema,
  personalSchema,
} from "@/lib/application";
import { confirmPayment, initiatePayment, methodName } from "@/lib/data/payments";
import { institution } from "@/lib/institution";
import { fileSize, ssp } from "@/lib/format";
import type { DocumentKind, PaymentMethod, ProgrammeChoice } from "@/lib/types";

/**
 * Shared shape for every step's result.
 *
 * `errors` is keyed by field name so the form can put each message beside its
 * own input rather than dumping a list at the top, which is what makes long
 * forms on small screens frustrating to correct.
 */
export type StepState =
  | { ok: true; message?: string }
  | { ok: false; message?: string; errors?: Record<string, string> }
  | undefined;

/** Collapse a Zod error into { fieldName: firstMessage }. */
function fieldErrors(error: z.ZodError): Record<string, string> {
  const out: Record<string, string> = {};
  for (const issue of error.issues) {
    const key = issue.path.join(".") || "form";
    if (!(key in out)) out[key] = issue.message;
  }
  return out;
}

/** Refuse to edit anything that has already gone to the admissions board. */
async function requireDraft(id: string) {
  const application = await getApplication(id);
  if (!application) return { error: "That application could not be found." as const };
  if (application.status !== "draft") {
    return { error: "This application has been submitted and can no longer be changed." as const };
  }
  return { application };
}

// --- Step 1: personal details ----------------------------------------------

export async function savePersonal(
  id: string,
  _prev: StepState,
  formData: FormData,
): Promise<StepState> {
  const guard = await requireDraft(id);
  if ("error" in guard) return { ok: false, message: guard.error };

  const parsed = personalSchema.safeParse(Object.fromEntries(formData));
  if (!parsed.success) {
    return {
      ok: false,
      message: "Check the highlighted fields.",
      errors: fieldErrors(parsed.error),
    };
  }

  await updateApplication(id, { personal: parsed.data });
  revalidatePath(`/apply/${id}`, "layout");
  redirect(`/apply/${id}/education`);
}

// --- Step 2: SSCSE results -------------------------------------------------

export async function saveEducation(
  id: string,
  _prev: StepState,
  formData: FormData,
): Promise<StepState> {
  const guard = await requireDraft(id);
  if ("error" in guard) return { ok: false, message: guard.error };

  // Subject rows post as parallel repeated fields; zip them back into objects
  // and drop rows the applicant left entirely blank.
  const subjects = formData.getAll("subject").map(String);
  const marks = formData.getAll("mark").map(String);
  const rows = subjects
    .map((subject, i) => ({ subject, mark: marks[i] ?? "" }))
    .filter((r) => r.subject !== "" || r.mark !== "");

  const parsed = educationSchema.safeParse({
    secondarySchool: formData.get("secondarySchool"),
    schoolState: formData.get("schoolState"),
    indexNumber: formData.get("indexNumber"),
    yearCompleted: formData.get("yearCompleted"),
    subjects: rows,
  });

  if (!parsed.success) {
    return {
      ok: false,
      message: "Check the highlighted fields.",
      errors: fieldErrors(parsed.error),
    };
  }

  await updateApplication(id, { education: parsed.data });
  revalidatePath(`/apply/${id}`, "layout");
  redirect(`/apply/${id}/programme`);
}

// --- Step 3: programme choices ---------------------------------------------

export async function saveChoices(
  id: string,
  _prev: StepState,
  formData: FormData,
): Promise<StepState> {
  const guard = await requireDraft(id);
  if ("error" in guard) return { ok: false, message: guard.error };

  // Ranks come from three separate selects, so blanks in the middle are
  // possible; compact them before validating.
  const raw = [
    formData.get("choice1"),
    formData.get("choice2"),
    formData.get("choice3"),
  ]
    .map((v) => String(v ?? "").trim())
    .filter((v) => v !== "");

  const parsed = choicesSchema.safeParse(raw);
  if (!parsed.success) {
    return {
      ok: false,
      message: parsed.error.issues[0]?.message ?? "Check your programme choices.",
    };
  }

  const choices: ProgrammeChoice[] = parsed.data.map((programmeId, i) => ({
    rank: (i + 1) as 1 | 2 | 3,
    programmeId,
  }));

  await updateApplication(id, { choices });
  revalidatePath(`/apply/${id}`, "layout");
  redirect(`/apply/${id}/documents`);
}

// --- Step 4: documents -----------------------------------------------------

const DOCUMENT_KINDS: DocumentKind[] = [
  "sscse_certificate",
  "sscse_transcript",
  "national_id",
  "passport_photo",
  "birth_certificate",
  "payment_slip",
];

/**
 * Record an uploaded document.
 *
 * NOTE: only metadata is stored. There is no object store wired up in this
 * build, so the bytes are read to measure and validate them and then dropped.
 * Before going live, stream the file to S3-compatible storage here and keep the
 * returned key on the document record — see README "What is not built yet".
 */
export async function uploadDocument(
  id: string,
  _prev: StepState,
  formData: FormData,
): Promise<StepState> {
  const guard = await requireDraft(id);
  if ("error" in guard) return { ok: false, message: guard.error };

  const kind = String(formData.get("kind") ?? "") as DocumentKind;
  if (!DOCUMENT_KINDS.includes(kind)) {
    return { ok: false, message: "Unknown document type." };
  }

  const file = formData.get("file");
  if (!(file instanceof File) || file.size === 0) {
    return { ok: false, message: "Choose a file to upload." };
  }

  if (file.size > MAX_DOCUMENT_BYTES) {
    return {
      ok: false,
      message: `${fileSize(file.size)} is too large. The limit is ${fileSize(MAX_DOCUMENT_BYTES)} — take the photo again at a lower resolution.`,
    };
  }

  if (!ACCEPTED_DOCUMENT_TYPES.includes(file.type as (typeof ACCEPTED_DOCUMENT_TYPES)[number])) {
    return {
      ok: false,
      message: "Upload a PDF or a photograph (JPG, PNG or WebP).",
    };
  }

  await addDocument(id, {
    kind,
    fileName: file.name,
    sizeBytes: file.size,
  });

  revalidatePath(`/apply/${id}`, "layout");
  return { ok: true, message: `${file.name} uploaded.` };
}

export async function deleteDocument(id: string, formData: FormData): Promise<void> {
  const guard = await requireDraft(id);
  if ("error" in guard) return;

  const documentId = String(formData.get("documentId") ?? "");
  await removeDocument(id, documentId);
  revalidatePath(`/apply/${id}`, "layout");
}

// --- Step 5: application fee ----------------------------------------------

const METHODS: PaymentMethod[] = ["mgurush", "nilepay", "bank_slip"];

export async function payApplicationFee(
  id: string,
  _prev: StepState,
  formData: FormData,
): Promise<StepState> {
  const guard = await requireDraft(id);
  if ("error" in guard) return { ok: false, message: guard.error };

  if (guard.application.payment?.status === "confirmed") {
    return { ok: false, message: "The application fee has already been paid." };
  }

  const method = String(formData.get("method") ?? "") as PaymentMethod;
  if (!METHODS.includes(method)) {
    return { ok: false, message: "Choose how you want to pay." };
  }

  // The amount is decided server-side by the application's own scheme, never
  // trusted from the form — the fee shown to the applicant is informational.
  const scheme = guard.application.schemeId ? await getScheme(guard.application.schemeId) : null;
  const amountSSP = scheme?.applicationFeeSSP ?? institution.applicationFeeSSP;

  const initiated = await initiatePayment({
    method,
    amountSSP,
    phone: String(formData.get("phone") ?? ""),
    slipReference: String(formData.get("slip") ?? ""),
  });

  if (!initiated.ok) return { ok: false, message: initiated.error };

  // Mobile money settles instantly in the mock provider. A bank slip stays
  // pending until the bursary clears it, which is enough to submit.
  const settled =
    method === "bank_slip" ? initiated.payment : await confirmPayment(initiated.payment);

  await attachPayment(id, settled);
  revalidatePath(`/apply/${id}`, "layout");

  return {
    ok: true,
    message:
      method === "bank_slip"
        ? `Slip ${settled.reference} recorded. You can submit now; the bursary will confirm the deposit within two working days.`
        : `${ssp(settled.amountSSP)} received by ${methodName(method)}. Reference ${settled.reference}.`,
  };
}
