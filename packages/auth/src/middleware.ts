import { NextResponse, type NextRequest } from "next/server"

import { SESSION_COOKIE } from "./session"

/**
 * Edge middleware shared by every module app.
 *
 * It does two things and deliberately not a third:
 *
 * 1. Assigns a request id if the client did not send one, so a browser
 *    request, the app's server render and the API's audit trail can all be
 *    correlated from one value.
 * 2. Redirects an unauthenticated request away from a protected path, with the
 *    original path in `?next=`, so signing in returns the user where they were
 *    going rather than to a dashboard.
 *
 * What it does *not* do is decode or validate the session. The cookie is
 * encrypted and validating it needs the secret; doing that at the edge would
 * put the secret in the edge runtime and duplicate a decision the server
 * layout makes properly anyway. Middleware checks only that a cookie is
 * *present* — a cheap filter, not an authorization boundary.
 */

export interface MiddlewareOptions {
  /** Paths reachable without a session. Prefix-matched. */
  publicPaths?: string[]
  loginPath?: string
}

const ALWAYS_PUBLIC = [
  "/_next",
  "/favicon",
  "/icon",
  "/apple-icon",
  "/robots.txt",
  "/sitemap.xml",
  "/health",
]

export function createMiddleware(options: MiddlewareOptions = {}) {
  const loginPath = options.loginPath ?? "/sign-in"
  const publicPaths = [...ALWAYS_PUBLIC, loginPath, ...(options.publicPaths ?? [])]

  return function middleware(request: NextRequest) {
    const { pathname } = request.nextUrl

    const requestId = request.headers.get("x-request-id") ?? crypto.randomUUID()
    const forwarded = new Headers(request.headers)
    forwarded.set("x-request-id", requestId)

    const isPublic = publicPaths.some(
      (path) => pathname === path || pathname.startsWith(`${path}/`) || pathname.startsWith(path),
    )
    if (isPublic) {
      const response = NextResponse.next({ request: { headers: forwarded } })
      response.headers.set("x-request-id", requestId)
      return response
    }

    if (!request.cookies.has(SESSION_COOKIE)) {
      const url = request.nextUrl.clone()
      url.pathname = loginPath
      // Only the path and query, never an absolute URL from the request — an
      // attacker-supplied `next=https://elsewhere` would make sign-in an open
      // redirect.
      url.searchParams.set("next", `${pathname}${request.nextUrl.search}`)
      const response = NextResponse.redirect(url)
      response.headers.set("x-request-id", requestId)
      return response
    }

    const response = NextResponse.next({ request: { headers: forwarded } })
    response.headers.set("x-request-id", requestId)
    return response
  }
}

/**
 * The matcher every app uses: everything except static assets.
 *
 * Exported for reference only — **do not import this into an app's
 * `middleware.ts`**. Next reads `export const config` statically at build
 * time and refuses an identifier it cannot resolve there, so each app inlines
 * the literal. Keep this and the copies in step.
 */
export const defaultMatcher = [
  "/((?!_next/static|_next/image|favicon.ico|.*\\.(?:svg|png|jpg|jpeg|gif|webp|woff2?)$).*)",
]
