import { redirect } from "next/navigation"

import { acmisPublic, readSession, signIn } from "@acmis/auth/server"
import { PasswordField } from "@acmis/ui/components/password-field"

import { APP, MODULE_NAME } from "@/lib/config"

/**
 * Sign-in.
 *
 * A Server Action, not a client fetch: the credentials go straight to the
 * Next.js server, which calls the API and seals the tokens into an HttpOnly
 * cookie. The browser never holds an API token, so an XSS anywhere in the app
 * — including in institution-supplied content — cannot lift one.
 */

export const metadata = { title: "Sign in" }

async function submitSignIn(formData: FormData) {
  "use server"

  const username = String(formData.get("username") ?? "").trim()
  const password = String(formData.get("password") ?? "")
  const next = String(formData.get("next") ?? "/")

  if (!username || !password) {
    redirect(`/sign-in?error=missing&next=${encodeURIComponent(next)}`)
  }

  // The whole dance lives in `@acmis/auth`: log in, read the account with the
  // token just issued, and seal the session. The API answers every credential
  // failure identically — wrong password, no such account and locked account
  // are indistinguishable — so this endpoint cannot be used to discover
  // whether an account exists.
  const result = await signIn(APP, username, password)
  if (!result.ok) {
    redirect(`/sign-in?error=${result.reason}&next=${encodeURIComponent(next)}`)
  }

  // Only a relative path, never a URL from the query string — an
  // attacker-supplied `next=https://elsewhere` would make sign-in an open
  // redirect straight after authentication.
  redirect(next.startsWith("/") ? next : "/")
}

export default async function SignInPage({
  searchParams,
}: {
  searchParams: Promise<{ error?: string; next?: string }>
}) {
  const { error, next = "/" } = await searchParams
  if (await readSession()) redirect(next.startsWith("/") ? next : "/")

  const institution = await (await acmisPublic(APP)).public
    .institution()
    .catch(() => null)

  return (
    <div className="grid min-h-dvh place-items-center px-4 py-10">
      <div className="w-full max-w-sm">
        <div className="mb-8 text-center">
          {institution?.crest_url ? (
            // eslint-disable-next-line @next/next/no-img-element
            <img
              src={institution.crest_url}
              alt=""
              className="mx-auto mb-3 size-14 object-contain"
            />
          ) : null}
          <h1 className="text-2xl font-semibold tracking-tight">
            {institution?.name ?? "ACMIS"}
          </h1>
          <p className="text-muted-foreground mt-1 text-sm">{MODULE_NAME}</p>
        </div>

        <form action={submitSignIn} className="bg-card space-y-4 rounded-lg border p-6">
          <input type="hidden" name="next" value={next} />

          {error ? (
            <p
              role="alert"
              className="border-destructive/30 bg-destructive/10 text-destructive rounded-md border px-3 py-2 text-sm"
            >
              {error === "missing"
                ? "Enter your username and password."
                : "That username or password is not correct."}
            </p>
          ) : null}

          <div className="space-y-1.5">
            <label htmlFor="username" className="text-sm font-medium">
              Username
            </label>
            <input
              id="username"
              name="username"
              autoComplete="username"
              autoCapitalize="none"
              required
              className="border-input bg-background focus-visible:ring-ring w-full rounded-md border px-3 py-2 text-sm focus-visible:ring-2 focus-visible:outline-none"
              placeholder="Student number or staff number"
            />
          </div>

          <div className="space-y-1.5">
            <div className="flex items-baseline justify-between">
              <label htmlFor="password" className="text-sm font-medium">
                Password
              </label>
              <a
                href="/forgot-password"
                className="text-muted-foreground hover:text-foreground text-xs"
              >
                Forgotten?
              </a>
            </div>
            <PasswordField
              id="password"
              name="password"
              autoComplete="current-password"
              required
            />
          </div>

          <button
            type="submit"
            className="bg-primary text-primary-foreground hover:bg-primary/90 w-full rounded-md px-3 py-2 text-sm font-medium"
          >
            Sign in
          </button>
        </form>

        {institution?.support_email ? (
          <p className="text-muted-foreground mt-6 text-center text-xs">
            Trouble signing in? Contact{" "}
            <a className="underline" href={`mailto:${institution.support_email}`}>
              {institution.support_email}
            </a>
          </p>
        ) : null}
      </div>
    </div>
  )
}
