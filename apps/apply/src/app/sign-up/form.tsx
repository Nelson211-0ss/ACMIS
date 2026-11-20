"use client"

import * as Icons from "lucide-react"
import { useActionState } from "react"

import { PasswordField } from "@acmis/ui/components/password-field"

import { registerApplicant, type SignUpState } from "./actions"
import { STATES } from "@/lib/south-sudan"

/**
 * The account form.
 *
 * Grouped into five short blocks rather than run as one column of thirteen
 * inputs. The grouping is the only thing that makes the length tolerable on a
 * phone: a person can see that they have finished "About you" and that what
 * remains is four more fields, instead of scrolling into an apparently endless
 * form with no sense of how much is left.
 *
 * Required fields are marked, and optional ones say "optional" in words rather
 * than by the absence of an asterisk — the absence of a mark is not a signal
 * anybody reads.
 */

function FieldError({ messages }: { messages?: string[] }) {
  if (!messages?.length) return null
  return (
    <p className="text-destructive flex items-start gap-1.5 text-xs">
      <Icons.AlertCircle className="mt-px size-3.5 shrink-0" aria-hidden />
      <span>{messages.join(" ")}</span>
    </p>
  )
}

function Group({
  title,
  hint,
  children,
}: {
  title: string
  hint?: string
  children: React.ReactNode
}) {
  return (
    <fieldset className="space-y-3">
      <legend className="space-y-0.5">
        <span className="text-title block text-sm">{title}</span>
        {hint ? <span className="text-muted-foreground block text-xs">{hint}</span> : null}
      </legend>
      {children}
    </fieldset>
  )
}

export function SignUpForm() {
  const [state, action, pending] = useActionState<SignUpState, FormData>(registerApplicant, {})
  const v = state.values ?? {}
  const e = state.fieldErrors ?? {}

  const invalid = (name: string) =>
    e[name] ? { "aria-invalid": true as const, "aria-describedby": `${name}-error` } : {}

  return (
    <form action={action} className="bg-card shadow-raised space-y-7 rounded-2xl p-6 sm:p-7">
      {state.error ? (
        <p
          role="alert"
          className="bg-destructive/10 text-destructive flex items-start gap-2 rounded-lg px-3 py-2.5 text-sm"
        >
          <Icons.AlertCircle className="mt-0.5 size-4 shrink-0" aria-hidden />
          <span>{state.error}</span>
        </p>
      ) : null}

      <Group title="Your name" hint="Exactly as it appears on your certificate.">
        <div className="grid gap-3 sm:grid-cols-2">
          <div className="space-y-1.5">
            <label htmlFor="given_names" className="text-sm font-medium">
              Given names
            </label>
            <input
              id="given_names"
              name="given_names"
              defaultValue={v.given_names}
              required
              autoComplete="given-name"
              className="field px-3"
              {...invalid("given_names")}
            />
            <div id="given_names-error">
              <FieldError messages={e.given_names} />
            </div>
          </div>
          <div className="space-y-1.5">
            <label htmlFor="surname" className="text-sm font-medium">
              Family name
            </label>
            <input
              id="surname"
              name="surname"
              defaultValue={v.surname}
              required
              autoComplete="family-name"
              className="field px-3"
              {...invalid("surname")}
            />
            <div id="surname-error">
              <FieldError messages={e.surname} />
            </div>
          </div>
        </div>
        <div className="space-y-1.5">
          <label htmlFor="other_names" className="text-sm font-medium">
            Other names <span className="text-muted-foreground font-normal">(optional)</span>
          </label>
          <input
            id="other_names"
            name="other_names"
            defaultValue={v.other_names}
            className="field px-3"
          />
        </div>
      </Group>

      <Group title="About you">
        <div className="grid gap-3 sm:grid-cols-2">
          <div className="space-y-1.5">
            <label htmlFor="date_of_birth" className="text-sm font-medium">
              Date of birth
            </label>
            <input
              id="date_of_birth"
              name="date_of_birth"
              type="date"
              defaultValue={v.date_of_birth}
              required
              className="field px-3"
              {...invalid("date_of_birth")}
            />
            <div id="date_of_birth-error">
              <FieldError messages={e.date_of_birth} />
            </div>
          </div>
          <div className="space-y-1.5">
            <label htmlFor="sex" className="text-sm font-medium">
              Sex
            </label>
            <select
              id="sex"
              name="sex"
              defaultValue={v.sex ?? ""}
              required
              className="field px-3"
              {...invalid("sex")}
            >
              <option value="" disabled>
                Select…
              </option>
              <option value="female">Female</option>
              <option value="male">Male</option>
            </select>
            <div id="sex-error">
              <FieldError messages={e.sex} />
            </div>
          </div>
        </div>
        <div className="grid gap-3 sm:grid-cols-2">
          <div className="space-y-1.5">
            <label htmlFor="district_of_origin" className="text-sm font-medium">
              State of origin <span className="text-muted-foreground font-normal">(optional)</span>
            </label>
            <select
              id="district_of_origin"
              name="district_of_origin"
              defaultValue={v.district_of_origin ?? ""}
              className="field px-3"
            >
              <option value="">Select…</option>
              {STATES.map((state) => (
                <option key={state} value={state}>
                  {state}
                </option>
              ))}
            </select>
          </div>
          <div className="space-y-1.5">
            <label htmlFor="national_id" className="text-sm font-medium">
              National ID <span className="text-muted-foreground font-normal">(optional)</span>
            </label>
            <input
              id="national_id"
              name="national_id"
              defaultValue={v.national_id}
              className="field px-3"
            />
            {/* Said out loud, because an applicant who has none will otherwise
                assume the form is not for them and stop here. */}
            <p className="text-muted-foreground text-xs">
              Leave this blank if you do not have one yet. It will not affect your application.
            </p>
          </div>
        </div>
      </Group>

      <Group title="How we reach you" hint="An offer is sent to both of these.">
        <div className="space-y-1.5">
          <label htmlFor="email" className="text-sm font-medium">
            Email
          </label>
          <input
            id="email"
            name="email"
            type="email"
            inputMode="email"
            autoCapitalize="none"
            defaultValue={v.email}
            required
            autoComplete="email"
            className="field px-3"
            {...invalid("email")}
          />
          <div id="email-error">
            <FieldError messages={e.email} />
          </div>
        </div>
        <div className="space-y-1.5">
          <label htmlFor="phone" className="text-sm font-medium">
            Mobile number
          </label>
          <input
            id="phone"
            name="phone"
            type="tel"
            inputMode="tel"
            placeholder="0920 123 456"
            defaultValue={v.phone}
            required
            autoComplete="tel"
            className="field px-3"
            {...invalid("phone")}
          />
          <div id="phone-error">
            <FieldError messages={e.phone} />
          </div>
        </div>
      </Group>

      <Group
        title="Parent or guardian"
        hint="Optional, but it is who we contact if we cannot reach you."
      >
        <div className="grid gap-3 sm:grid-cols-2">
          <div className="space-y-1.5">
            <label htmlFor="guardian_name" className="text-sm font-medium">
              Their name
            </label>
            <input
              id="guardian_name"
              name="guardian_name"
              defaultValue={v.guardian_name}
              className="field px-3"
            />
          </div>
          <div className="space-y-1.5">
            <label htmlFor="guardian_phone" className="text-sm font-medium">
              Their mobile number
            </label>
            <input
              id="guardian_phone"
              name="guardian_phone"
              type="tel"
              inputMode="tel"
              placeholder="0920 123 456"
              defaultValue={v.guardian_phone}
              className="field px-3"
              {...invalid("guardian_phone")}
            />
            <div id="guardian_phone-error">
              <FieldError messages={e.guardian_phone} />
            </div>
          </div>
        </div>
      </Group>

      <Group
        title="Your password"
        hint="You will need it every time you come back to your application."
      >
        <div className="space-y-1.5">
          <label htmlFor="password" className="text-sm font-medium">
            Password
          </label>
          <PasswordField id="password" name="password" autoComplete="new-password" required />
          <div id="password-error">
            <FieldError messages={e.password} />
          </div>
        </div>
        <div className="space-y-1.5">
          <label htmlFor="confirm_password" className="text-sm font-medium">
            Password again
          </label>
          <PasswordField
            id="confirm_password"
            name="confirm_password"
            autoComplete="new-password"
            required
          />
          <div id="confirm_password-error">
            <FieldError messages={e.confirm_password} />
          </div>
        </div>
      </Group>

      <button
        type="submit"
        disabled={pending}
        className="bg-primary text-primary-foreground hover:bg-primary/90 shadow-card inline-flex h-11 w-full items-center justify-center gap-2 rounded-lg text-sm font-medium transition-colors disabled:opacity-70"
      >
        {pending ? (
          <Icons.Loader2 className="size-4 animate-spin" aria-hidden />
        ) : (
          <Icons.UserPlus className="size-4" aria-hidden />
        )}
        {pending ? "Creating your account…" : "Create my application account"}
      </button>

      <p className="text-muted-foreground text-center text-xs">
        Already started?{" "}
        <a href="/sign-in" className="text-foreground underline">
          Sign in
        </a>
      </p>
    </form>
  )
}
