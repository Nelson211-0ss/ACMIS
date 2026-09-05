"use server";

import { revalidatePath } from "next/cache";
import { redirect } from "next/navigation";
import { currentSession, startSession } from "@/lib/auth";
import {
  createApplication,
  getApplication,
  getScheme,
  getSystemSettings,
  setApplicationStatus,
} from "@/lib/data/repo";
import { canSubmit, nextIncompleteStep } from "@/lib/application";

/**
 * Start an application under a specific scheme.
 *
 * An applicant account is created implicitly if there is no session, because
 * requiring registration before someone can even see the form loses
 * applicants — they can be asked to set a password after submitting.
 */
export async function startApplication(schemeId: string): Promise<void> {
  const settings = await getSystemSettings();
  const scheme = await getScheme(schemeId);
  const schemeClosed =
    !scheme || scheme.status !== "open" || new Date(scheme.closesAt).getTime() < Date.now();
  // The scheme card that calls this is already hidden once it is closed;
  // this is the check that matters if someone posts directly, or a scheme
  // closes in the moment between page load and click.
  if (!settings.applicationsOpen || schemeClosed) redirect("/apply");

  let session = await currentSession();
  if (!session || session.role !== "applicant") {
    session = { role: "applicant", subjectId: "usr-applicant" };
    await startSession(session);
  }

  const application = await createApplication(session.subjectId, scheme.id);
  revalidatePath("/apply");
  redirect(`/apply/${application.id}/personal`);
}

/** Jump back into a draft at the first step that is not finished. */
export async function continueApplication(formData: FormData): Promise<void> {
  const id = String(formData.get("id") ?? "");
  const application = await getApplication(id);
  if (!application) redirect("/apply");
  redirect(`/apply/${id}/${nextIncompleteStep(application)}`);
}

export type SubmitState = { error: string } | undefined;

/**
 * Submit for review.
 *
 * The completeness check runs here as well as in the UI: the review page's
 * button being enabled is a convenience, not a guarantee, and a draft can go
 * stale between render and submit.
 */
export async function submitApplication(
  _prev: SubmitState,
  formData: FormData,
): Promise<SubmitState> {
  const id = String(formData.get("id") ?? "");
  const application = await getApplication(id);
  if (!application) return { error: "That application could not be found." };

  const { ok, blocking } = canSubmit(application);
  if (!ok) {
    if (application.status !== "draft") {
      return { error: "This application has already been submitted." };
    }
    return {
      error: `Finish these sections first: ${blocking.join(", ")}.`,
    };
  }

  await setApplicationStatus(id, "submitted");
  revalidatePath("/apply");
  revalidatePath(`/apply/${id}/review`);
  redirect(`/apply/${id}/review?submitted=1`);
}
