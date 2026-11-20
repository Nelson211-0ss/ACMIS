import { createMiddleware } from "@acmis/auth/middleware"

/**
 * `/sign-up` is public for the obvious reason: the person using it has no
 * account, and gating account creation behind a session is a closed door with
 * a sign on it saying "use the door".
 */
export default createMiddleware({
  publicPaths: ["/sign-in", "/sign-up", "/not-permitted"],
})

// Inlined rather than imported from @acmis/auth: Next parses this export
// statically at build time and rejects any identifier it cannot resolve, so a
// shared constant fails the build with "Unknown identifier at config.matcher".
export const config = {
  matcher: [
    "/((?!_next/static|_next/image|favicon.ico|.*\\.(?:svg|png|jpg|jpeg|gif|webp|woff2?)$).*)",
  ],
}
