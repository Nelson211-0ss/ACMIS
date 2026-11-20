import type { NextConfig } from "next"

const config: NextConfig = {
  reactStrictMode: true,
  // The workspace packages ship TypeScript source, not a build. Transpiling
  // them here means no build step between editing a shared component and
  // seeing it in every app.
  transpilePackages: ["@acmis/ui", "@acmis/auth", "@acmis/api-client"],
  experimental: {
    // Server Actions post to the app's own origin. In production each module
    // is a distinct host, so the allow-list is derived from the deployment.
    serverActions: {
      allowedOrigins: process.env.ACMIS_ALLOWED_ORIGINS?.split(",") ?? undefined,
    },
  },
  // Every app is behind an authenticated BFF and serves no third-party
  // scripts, so a strict frame policy costs nothing and closes clickjacking.
  async headers() {
    return [
      {
        source: "/:path*",
        headers: [
          { key: "x-content-type-options", value: "nosniff" },
          { key: "referrer-policy", value: "strict-origin-when-cross-origin" },
          { key: "x-frame-options", value: "DENY" },
        ],
      },
    ]
  },
  output: "standalone",
}

export default config
