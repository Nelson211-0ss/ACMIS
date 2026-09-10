/**
 * The session cookie each module app holds.
 *
 * Every app is a backend-for-frontend: the browser never sees an API token.
 * The access token and refresh token live in an encrypted, HttpOnly cookie
 * that only the Next.js server can read, and the browser holds nothing but an
 * opaque string.
 *
 * Why not `localStorage`, which would be simpler: a token in `localStorage` is
 * readable by any script that gets onto the page, and ACMIS renders
 * institution-supplied content — announcements, course material, an
 * LTI-embedded tool. One XSS in any of that is every signed-in registrar's
 * session. An HttpOnly cookie survives that class of bug entirely.
 *
 * The cookie is encrypted (JWE), not merely signed: it carries the API tokens
 * themselves, and a signed-but-readable cookie hands them to anyone who can
 * read a request log.
 */

import { EncryptJWT, jwtDecrypt } from "jose"

export interface SessionData {
  accessToken: string
  refreshToken: string | null
  /** Seconds since epoch when the access token expires. */
  accessExpiresAt: number
  tenantSlug: string
  /** Denormalised so the chrome renders without an API round trip per page. */
  displayName: string
  kind: string
  /** Whether this session has cleared a second factor. */
  mfaSatisfied: boolean
  mustChangePassword: boolean
}

export const SESSION_COOKIE = "acmis_session"

/** Fourteen days, matching the API's refresh-token lifetime. */
const MAX_AGE_SECONDS = 14 * 24 * 60 * 60

function keyFrom(secret: string): Uint8Array {
  // A 256-bit key derived from the configured secret. `A256GCM` needs exactly
  // 32 bytes, and silently truncating a short secret would produce a weak key
  // that still appears to work.
  const bytes = new TextEncoder().encode(secret)
  if (bytes.length < 32) {
    throw new Error(
      "ACMIS_SESSION_SECRET must be at least 32 bytes. Generate one with " +
        "`openssl rand -base64 32`.",
    )
  }
  return bytes.slice(0, 32)
}

export async function sealSession(
  data: SessionData,
  secret: string,
): Promise<string> {
  return new EncryptJWT({ ...data } as unknown as Record<string, unknown>)
    .setProtectedHeader({ alg: "dir", enc: "A256GCM" })
    .setIssuedAt()
    .setExpirationTime(`${MAX_AGE_SECONDS}s`)
    .encrypt(keyFrom(secret))
}

export async function openSession(
  token: string,
  secret: string,
): Promise<SessionData | null> {
  try {
    const { payload } = await jwtDecrypt(token, keyFrom(secret))
    return payload as unknown as SessionData
  } catch {
    // A cookie that will not decrypt is a rotated secret or a tampered value.
    // Either way the answer is "no session", never an error page — the user
    // should land on sign-in, not on a stack trace.
    return null
  }
}

export function cookieOptions(isProduction: boolean) {
  return {
    httpOnly: true,
    secure: isProduction,
    // `lax` rather than `strict`: an LTI launch and a payment-provider
    // callback both return to the app via a cross-site POST, and `strict`
    // drops the session on exactly those journeys.
    sameSite: "lax" as const,
    path: "/",
    maxAge: MAX_AGE_SECONDS,
  }
}

/**
 * True when the access token is close enough to expiry to refresh.
 *
 * A minute of slack, so a request that starts valid does not arrive expired
 * after a slow round trip.
 */
export function needsRefresh(session: SessionData, skewSeconds = 60): boolean {
  return session.accessExpiresAt - skewSeconds <= Math.floor(Date.now() / 1000)
}
