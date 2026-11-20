"use server"

import { redirect } from "next/navigation"

import { ApiError, TransportError } from "@acmis/api-client"
import { acmisPublic, signIn } from "@acmis/auth/server"

import { APP } from "@/lib/config"
import { ageProblem, normalisePhone } from "@/lib/south-sudan"

/**
 * Creating an application account.
 *
 * ## Why this returns state instead of redirecting on failure
 *
 * The rest of ACMIS answers a failed form with `redirect("?error=…")`, which
 * is fine for sign-in: two fields, retyped in four seconds. This form has
 * thirteen, and it is filled in by somebody who may be on a borrowed phone
 * with one bar of signal. Throwing their answers away because the guardian's
 * phone number was mistyped is how an application is abandoned rather than
 * corrected, so every value comes back with the error beside the field that
 * caused it.
 *
 * ## Why it signs them in afterwards
 *
 * The alternative is to show the new reference and send them to sign in with
 * it, which is a second chance to lose them — and the reference is a string
 * like `APL/2026/0007` that nobody can retype from memory. They are signed in
 * directly, and the reference is shown on the dashboard where it can be read
 * at leisure. It is also emailed, by the same path that mails everything else.
 */

export interface SignUpState {
  /** A single sentence shown above the form. */
  error?: string
  /** Keyed by field name, so the message renders next to the input. */
  fieldErrors?: Record<string, string[]>
  /** Everything the person typed, so nothing is lost on a failed submit. */
  values?: Record<string, string>
}

const TEXT_FIELDS = [
  "surname",
  "given_names",
  "other_names",
  "date_of_birth",
  "sex",
  "district_of_origin",
  "email",
  "phone",
  "national_id",
  "guardian_name",
  "guardian_phone",
] as const

export async function registerApplicant(
  _previous: SignUpState,
  formData: FormData,
): Promise<SignUpState> {
  const values: Record<string, string> = {}
  for (const field of TEXT_FIELDS) {
    values[field] = String(formData.get(field) ?? "").trim()
  }
  const password = String(formData.get("password") ?? "")
  const confirm = String(formData.get("confirm_password") ?? "")

  const fieldErrors: Record<string, string[]> = {}
  const require = (field: string, message: string) => {
    if (!values[field]) fieldErrors[field] = [message]
  }

  require("surname", "Enter your family name.")
  require("given_names", "Enter your given names.")
  require("date_of_birth", "Enter your date of birth.")
  require("sex", "Select an option.")
  require("email", "Enter an email address we can reach you on.")
  require("phone", "Enter your mobile number.")

  if (values.date_of_birth) {
    const problem = ageProblem(values.date_of_birth)
    if (problem) fieldErrors.date_of_birth = [problem]
  }

  // Normalised here rather than trusted to the API, because the shape the API
  // stores has to be the shape an offer is later texted to.
  let phone = ""
  if (values.phone) {
    const normalised = normalisePhone(values.phone)
    if (!normalised) {
      fieldErrors.phone = ["Enter a valid mobile number, for example 0920 123 456."]
    } else {
      phone = normalised
    }
  }

  let guardianPhone: string | undefined
  if (values.guardian_phone) {
    const normalised = normalisePhone(values.guardian_phone)
    if (!normalised) {
      fieldErrors.guardian_phone = ["Enter a valid mobile number, for example 0920 123 456."]
    } else {
      guardianPhone = normalised
    }
  }

  if (!password) {
    fieldErrors.password = ["Choose a password."]
  } else if (password !== confirm) {
    // On the confirm field, not the password field: the first one is almost
    // always the one they meant.
    fieldErrors.confirm_password = ["The two passwords are not the same."]
  }

  if (Object.keys(fieldErrors).length > 0) {
    return { fieldErrors, values }
  }

  const client = await acmisPublic(APP)
  let reference: string
  try {
    const created = await client.public.registerApplicant({
      surname: values.surname ?? "",
      given_names: values.given_names ?? "",
      other_names: (values.other_names ?? "") || undefined,
      date_of_birth: values.date_of_birth ?? "",
      sex: (values.sex ?? "") as "female" | "male",
      nationality: "South Sudanese",
      country_code: "SS",
      district_of_origin: (values.district_of_origin ?? "") || undefined,
      email: (values.email ?? "").toLowerCase(),
      phone,
      national_id: (values.national_id ?? "") || undefined,
      guardian_name: (values.guardian_name ?? "") || undefined,
      guardian_phone: guardianPhone,
      password,
    })
    reference = created.reference
  } catch (error) {
    if (error instanceof ApiError) {
      // The API's field errors are already written for a reader; passing them
      // through beats inventing a second vocabulary for the same rule.
      const fields = error.fieldErrors
      if (Object.keys(fields).length > 0) {
        return { fieldErrors: fields, values }
      }
      return { error: error.message, values }
    }
    if (error instanceof TransportError) {
      return {
        error:
          "We could not reach the admissions service just now. Your details have " +
          "not been lost — try again in a moment.",
        values,
      }
    }
    throw error
  }

  const signedIn = await signIn(APP, reference, password)
  if (!signedIn.ok) {
    // The account exists; only the automatic sign-in failed. Say so plainly
    // and give them the reference, or they will register a second time.
    return {
      error:
        `Your account was created — your application number is ${reference}. ` +
        "Please sign in with it below.",
      values,
    }
  }

  redirect("/?welcome=1")
}
