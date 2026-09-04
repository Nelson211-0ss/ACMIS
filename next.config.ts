import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  // `standalone` lets this run on any cheap VPS with `node .next/standalone/server.js`.
  // Deliberate: Vercel egress and card-only billing are awkward from South Sudan,
  // so self-hosting on a Nairobi/Kampala-region VPS keeps latency and payment sane.
  output: "standalone",

  // Bandwidth budget. Every kilobyte here is a second of load time on 2G.
  compress: true,
  productionBrowserSourceMaps: false,
  poweredByHeader: false,

  images: {
    // AVIF first — roughly half the bytes of JPEG at equal quality.
    formats: ["image/avif", "image/webp"],
    // Only the widths the layouts actually use; no speculative 3840px variants.
    deviceSizes: [360, 414, 640, 828, 1080, 1280],
    imageSizes: [48, 64, 96, 128, 256],
  },

  experimental: {
    // Pull only the icon modules we import instead of the whole lucide barrel.
    optimizePackageImports: ["lucide-react"],
  },
};

export default nextConfig;
