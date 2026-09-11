import * as Icons from "lucide-react"
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

  const institution = await (await acmisPublic(APP)).public.institution().catch(() => null)

  return (
    /*
     * ## The sign-in screen
     *
     * The one page in the system a person meets before they have any context,
     * sometimes on a lab machine they do not own, sometimes on a phone in a
     * queue. So it does three things and stops: says whose system this is,
     * takes two fields, and tells you who to ask when it goes wrong.
     *
     * There is not a single line border on it. An outline round the card, an
     * outline round each field and an outline round the error is three
     * different rectangles competing to be the thing you look at, on a screen
     * with exactly one thing to do. Instead the card is *lifted* off the page
     * and the fields are *sunk* into it — depth in two directions from one
     * surface, which needs no strokes and leaves the eye nothing to resolve
     * but the heading and the button.
     *
     * The ground is tinted rather than white for that to work: an elevated
     * white card on a white page is a shadow with nothing casting it.
     */
    <div className="bg-muted/40 relative grid min-h-dvh place-items-center overflow-hidden px-4 py-10">
      {/* A single soft wash of the institution's own blue behind the card.
          Purely atmospheric, so it is `aria-hidden` and sits under everything;
          it also gives the shadow something to fall on. */}
      <div
        aria-hidden
        className="pointer-events-none absolute inset-x-0 top-0 -z-10 h-[26rem] bg-[radial-gradient(65%_100%_at_50%_0%,var(--primary)_0%,transparent_70%)] opacity-[0.10]"
      />

      <div className="w-full max-w-[22rem]">
        <div className="mb-7 text-center">
          {institution?.crest_url ? (
            // The crest gets the same lifted treatment as the card, so it
            // reads as part of the same object rather than pasted above it.
            // eslint-disable-next-line @next/next/no-img-element
            <img
              src={institution.crest_url}
              alt=""
              className="bg-card shadow-card mx-auto mb-4 size-16 rounded-2xl object-contain p-2.5"
            />
          ) : null}
          <h1 className="font-display text-balance text-[1.6rem] font-extrabold leading-tight tracking-tight">
            {institution?.name ?? "ACMIS"}
          </h1>
          <p className="eyebrow mt-2">{MODULE_NAME}</p>
        </div>

        <form
          action={submitSignIn}
          className="bg-card shadow-raised space-y-4 rounded-2xl p-6 sm:p-7"
        >
          <input type="hidden" name="next" value={next} />

          {error ? (
            // A filled tint, no outline. The icon and the colour together are
            // already two signals; a third rectangle is not a third signal.
            <p
              role="alert"
              className="bg-destructive/10 text-destructive flex items-start gap-2 rounded-lg px-3 py-2.5 text-sm"
            >
              <Icons.AlertCircle className="mt-0.5 size-4 shrink-0" aria-hidden />
              <span>
                {error === "missing"
                  ? "Enter your username and password."
                  : "That username or password is not correct."}
              </span>
            </p>
          ) : null}

          <div className="space-y-1.5">
            <label htmlFor="username" className="text-sm font-medium">
              Username
            </label>
            {/* The glyph is `pointer-events-none` and the input is padded to
                clear it, so the whole field stays one tap target — an icon
                that swallows a tap on a phone is worse than no icon. */}
            <div className="relative">
              <Icons.User
                aria-hidden
                className="text-muted-foreground pointer-events-none absolute left-3 top-1/2 size-4 -translate-y-1/2"
              />
              <input
                id="username"
                name="username"
                autoComplete="username"
                autoCapitalize="none"
                required
                className="field pl-9 pr-3"
                placeholder="Student or staff number"
              />
            </div>
          </div>

          <div className="space-y-1.5">
            <div className="flex items-baseline justify-between gap-3">
              <label htmlFor="password" className="text-sm font-medium">
                Password
              </label>
              <a
                href="/forgot-password"
                className="text-muted-foreground hover:text-foreground text-xs underline-offset-2 hover:underline"
              >
                Forgotten?
              </a>
            </div>
            <PasswordField id="password" name="password" autoComplete="current-password" required />
          </div>

          <button
            type="submit"
            className="bg-primary text-primary-foreground hover:bg-primary/90 shadow-card mt-1 inline-flex h-11 w-full items-center justify-center gap-2 rounded-lg text-sm font-medium transition-colors"
          >
            <Icons.LogIn className="size-4" aria-hidden />
            Sign in
          </button>
        </form>

        {institution?.support_email ? (
          <p className="text-muted-foreground mt-6 flex flex-wrap items-center justify-center gap-x-1.5 gap-y-1 text-center text-xs">
            <Icons.LifeBuoy className="size-3.5 shrink-0" aria-hidden />
            Trouble signing in? Contact{" "}
            <a
              className="text-foreground underline underline-offset-2"
              href={`mailto:${institution.support_email}`}
            >
              {institution.support_email}
            </a>
          </p>
        ) : null}
      </div>
    </div>
  )
}
