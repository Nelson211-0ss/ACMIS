import { createMiddleware } from "@acmis/auth/middleware"

export default createMiddleware({
  publicPaths: ["/sign-in", "/not-permitted"],
})

// Inlined rather than imported from @acmis/auth: Next parses this export
// statically at build time and rejects any identifier it cannot resolve, so a
// shared constant fails the build with "Unknown identifier at config.matcher".
export const config = {
  matcher: [
    "/((?!_next/static|_next/image|favicon.ico|.*\\.(?:svg|png|jpg|jpeg|gif|webp|woff2?)$).*)",
  ],
}
