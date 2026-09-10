import { existsSync } from "node:fs";
import path from "node:path";

const CANDIDATES = [
  "student.jpg",
  "student.jpeg",
  "student.png",
  "student.webp",
  "student.svg",
];

/**
 * The landing-page hero photo is optional, same philosophy as a student's
 * profile photo in Avatar: no file is the normal starting state, not an error.
 * Drop one at public/hero/student.<ext> and the hero swaps the built-in
 * StudentIllustration for it — no code change.
 *
 * `.svg` is accepted but rendered through a plain <img> at the call site,
 * not next/image: the optimiser refuses SVG unless `dangerouslyAllowSVG` is
 * set, and a vector needs no resizing pass anyway.
 *
 * This does run at request time, but "/" is a static route (no per-request
 * data), so Next bakes the result into the page at `next build` like
 * everything else here. A dropped-in photo needs the same rebuild any other
 * change to this page would — dev mode (`next dev`) re-evaluates it live.
 */
export function heroPhotoSrc(): string | null {
  for (const name of CANDIDATES) {
    if (existsSync(path.join(process.cwd(), "public", "hero", name))) {
      return `/hero/${name}`;
    }
  }
  return null;
}
