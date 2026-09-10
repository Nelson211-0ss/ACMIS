import { cookies, headers } from "next/headers"
import { redirect } from "next/navigation"

import { AcmisClient, ApiError, api, type WhoAmI } from "@acmis/api-client"

import {
  SESSION_COOKIE,
  cookieOptions,
  needsRefresh,
  openSession,
  sealSession,
  type SessionData,
} from "./session"

/**
 * Server-side session and API access for a module app.
 *
 * Everything here runs on the Next.js server. Nothing in this file may be
 * imported into a client component — it reads cookies and holds tokens, and a
 * bundler that follows the import into the browser would ship both.
 */

export interface AppConfig {
  /** Which module this app is, sent as `X-ACMIS-Module` and audited. */
  module: string
  /** Where the browser is sent when there is no session. */
  loginPath?: string
}

function env(name: string, fallback?: string): string {
  const value = process.env[name] ?? fallback
  if (!value) {
    throw new Error(`${name} is not set. See .env.example.`)
  }
  return value
}

/** The API base URL. Server-to-server, so it may be an internal address. */
function apiBaseUrl(): string {
  return env("ACMIS_API_INTERNAL_URL", process.env.ACMIS_API_URL ?? "http://localhost:8000")
}

function sessionSecret(): string {
  return env("ACMIS_SESSION_SECRET")
}

/**
 * The tenant for this request.
 *
 * In production the API resolves it from the Host header and ignores anything
 * we send. In development nine dev servers share `localhost`, so the tenant
 * comes from `ACMIS_DEV_TENANT` and travels as a header the API only honours
 * outside production.
 */
export async function currentTenantSlug(): Promise<string> {
  const host = (await headers()).get("host") ?? ""
  const suffix = process.env.ACMIS_TENANT_HOST_SUFFIX ?? "acmis.local"
  const hostname = host.split(":")[0] ?? ""
  if (hostname.endsWith(`.${suffix}`)) {
    const label = hostname.slice(0, -(suffix.length + 1))
    return label.split(".").pop() ?? ""
  }
  return process.env.ACMIS_DEV_TENANT ?? "demo"
}

export async function readSession(): Promise<SessionData | null> {
  const raw = (await cookies()).get(SESSION_COOKIE)?.value
  if (!raw) return null
  return openSession(raw, sessionSecret())
}

export async function writeSession(data: SessionData): Promise<void> {
  const sealed = await sealSession(data, sessionSecret())
  ;(await cookies()).set(
    SESSION_COOKIE,
    sealed,
    cookieOptions(process.env.NODE_ENV === "production"),
  )
}

export async function clearSession(): Promise<void> {
  ;(await cookies()).delete(SESSION_COOKIE)
}

/** An unauthenticated client, for the public endpoints and the sign-in page. */
export async function publicClient(config: AppConfig): Promise<AcmisClient> {
  return new AcmisClient({
    baseUrl: apiBaseUrl(),
    tenant: await currentTenantSlug(),
    module: config.module,
    requestId: (await headers()).get("x-request-id") ?? undefined,
  })
}

/**
 * An authenticated client, refreshing the access token if it has expired.
 *
 * The refresh happens here rather than in a React component because it writes
 * a cookie, and a cookie write during render is not available in every Next.js
 * rendering context. Callers that hit this in a context where cookies are
 * read-only get the un-refreshed client and a 401, which the layout turns into
 * a redirect to sign-in — correct, if slightly slower than a silent refresh.
 */
export async function authedClient(config: AppConfig): Promise<AcmisClient> {
  const session = await readSession()
  if (!session) {
    redirect(config.loginPath ?? "/sign-in")
  }

  let token = session.accessToken
  if (needsRefresh(session) && session.refreshToken) {
    try {
      const refreshed = await api(
        new AcmisClient({
          baseUrl: apiBaseUrl(),
          tenant: session.tenantSlug,
          module: config.module,
        }),
      ).auth.refresh()
      token = refreshed.access_token
      await writeSession({
        ...session,
        accessToken: refreshed.access_token,
        accessExpiresAt: Math.floor(Date.now() / 1000) + refreshed.expires_in,
      })
    } catch {
      // The refresh token has been revoked, the account suspended, or the
      // session signed out elsewhere. All three mean sign in again.
      await clearSession()
      redirect(config.loginPath ?? "/sign-in")
    }
  }

  return new AcmisClient({
    baseUrl: apiBaseUrl(),
    tenant: session.tenantSlug,
    module: config.module,
    token,
    requestId: (await headers()).get("x-request-id") ?? undefined,
  })
}

/** The typed API, authenticated. What most server components use. */
export async function acmis(config: AppConfig) {
  return api(await authedClient(config))
}

export async function acmisPublic(config: AppConfig) {
  return api(await publicClient(config))
}


/**
 * Sign in, and seal the session.
 *
 * One function rather than the same six lines in thirteen sign-in pages —
 * and the reason is a bug those thirteen copies all had. `whoami` needs the
 * bearer token, and the client returned by `acmisPublic` has none: the token
 * has only just been issued. Calling it on the public client returns 401,
 * every app reported "that username or password is not correct", and nobody
 * could sign in anywhere. The token has to be threaded from the login
 * response into the call that reads the account, which is exactly the kind of
 * thing that belongs in one place.
 *
 * Returns the reason on failure rather than throwing, so the caller can
 * redirect with a message. Credential failures are deliberately
 * indistinguishable from one another — see the API's own note.
 */
export async function signIn(
  config: AppConfig,
  username: string,
  password: string,
): Promise<{ ok: true; mustChangePassword: boolean } | { ok: false; reason: "rejected" }> {
  const client = await publicClient(config)
  try {
    const token = await api(client).auth.login(username, password)
    // The same client, now carrying the token it was just handed.
    const me = await api(client.withToken(token.access_token)).auth.whoami()

    await writeSession({
      accessToken: token.access_token,
      refreshToken: token.refresh_token,
      accessExpiresAt: Math.floor(Date.now() / 1000) + token.expires_in,
      tenantSlug: me.tenant_slug,
      displayName: me.display_name,
      kind: me.kind,
      mfaSatisfied: me.mfa_satisfied,
      mustChangePassword: token.must_change_password,
    })
    return { ok: true, mustChangePassword: token.must_change_password }
  } catch (error) {
    if (error instanceof ApiError) {
      // Logged server-side, never returned: the caller gets one
      // indistinguishable "rejected" so the endpoint cannot be used to
      // discover whether an account exists, while an operator can still see
      // why sign-in is failing.
      console.error(
        `[acmis] sign-in refused: ${error.status} ${error.code} ${error.message}`,
        error.details,
      )
      return { ok: false, reason: "rejected" }
    }
    throw error
  }
}

/**
 * Who is signed in, and what they may see.
 *
 * Fetched fresh rather than read from the cookie: roles and permissions change,
 * and a cookie written at sign-in would let a revoked grant persist for a
 * fortnight. The cost is one cached request per render.
 */
export async function requireUser(config: AppConfig): Promise<WhoAmI> {
  const client = await acmis(config)
  try {
    return await client.auth.whoami({ next: { revalidate: 30 } })
  } catch (error) {
    if (error instanceof ApiError && (error.isUnauthenticated || error.isForbidden)) {
      await clearSession()
      redirect(config.loginPath ?? "/sign-in")
    }
    throw error
  }
}

/**
 * Require a permission before rendering a page.
 *
 * A convenience for the coarse case — "this page is for the finance office" —
 * and *not* the authorization boundary. The API decides every actual
 * operation; this stops a user from reaching a page whose every request would
 * fail, which is a better experience than a screen of permission errors.
 */
export async function requirePermission(
  config: AppConfig,
  permission: string | string[],
): Promise<WhoAmI> {
  const user = await requireUser(config)
  const wanted = Array.isArray(permission) ? permission : [permission]
  if (!wanted.some((p) => user.permissions.includes(p))) {
    redirect("/not-permitted")
  }
  return user
}

export type { SessionData }
