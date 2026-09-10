import { cn } from "@/lib/cn";

/**
 * Flat vector student for the landing hero — a seated figure with a laptop.
 *
 * Inline SVG rather than a file in public/, for the same reasons as the Crest
 * in brand.tsx: no extra request on a 3G connection, and it stays sharp at any
 * density. Roughly 2KB gzipped inline, against ~40KB for a comparable PNG.
 *
 * Colours are literal rather than design tokens, deliberately. This only ever
 * sits on the hero gradient, which is dark in BOTH themes (--sidebar is the
 * one family that does not invert), so a fixed light-on-dark palette is
 * correct in both. Token colours would flip underneath it and break the
 * figure. The hues are still drawn from the palette: brand-300 shirt,
 * gold-500 accent.
 *
 * Deliberately geometric and unbranded — it depicts no real person.
 */
export function StudentIllustration({ className }: { className?: string }) {
  return (
    <svg
      viewBox="0 0 400 400"
      className={cn("h-full w-full", className)}
      role="img"
      aria-label="Illustration of a student sitting with a laptop"
    >
      {/* Stage. Lifts the figure off the gradient so the dark hair reads. */}
      <circle cx="200" cy="200" r="168" fill="#ffffff" fillOpacity="0.10" />
      <circle
        cx="200"
        cy="200"
        r="168"
        fill="none"
        stroke="#ffffff"
        strokeOpacity="0.16"
        strokeWidth="1.5"
      />
      <circle cx="200" cy="200" r="126" fill="#ffffff" fillOpacity="0.05" />

      {/* Floor shadow */}
      <ellipse cx="200" cy="338" rx="112" ry="15" fill="#000000" fillOpacity="0.20" />

      {/* Crossed legs */}
      <g fill="#c3ced9">
        <rect x="118" y="286" width="164" height="48" rx="24" />
        <rect
          x="120"
          y="298"
          width="112"
          height="34"
          rx="17"
          transform="rotate(-8 176 315)"
        />
        <rect
          x="168"
          y="298"
          width="112"
          height="34"
          rx="17"
          transform="rotate(8 224 315)"
        />
      </g>
      <ellipse cx="132" cy="325" rx="23" ry="13" fill="#28323d" />
      <ellipse cx="268" cy="325" rx="23" ry="13" fill="#28323d" />

      {/* Neck, tucked behind the torso */}
      <rect x="187" y="156" width="26" height="26" rx="10" fill="#96613f" />

      {/* Torso */}
      <rect x="154" y="172" width="92" height="122" rx="36" fill="#94bed8" />

      {/* Arms, angled in toward the laptop */}
      <g fill="#7fadcb">
        <rect
          x="141"
          y="194"
          width="26"
          height="94"
          rx="13"
          transform="rotate(11 154 241)"
        />
        <rect
          x="233"
          y="194"
          width="26"
          height="94"
          rx="13"
          transform="rotate(-11 246 241)"
        />
      </g>

      {/* Head. Dark circle behind a slightly lower face circle leaves the
          crescent that reads as hair — flat-illustration shorthand. */}
      <circle cx="200" cy="126" r="39" fill="#1e2a36" />
      <circle cx="166" cy="140" r="6.5" fill="#96613f" />
      <circle cx="234" cy="140" r="6.5" fill="#96613f" />
      <circle cx="200" cy="137" r="35" fill="#96613f" />
      <circle cx="188" cy="134" r="3.2" fill="#1e2a36" />
      <circle cx="212" cy="134" r="3.2" fill="#1e2a36" />
      <path
        d="M190 148c6 5 14 5 20 0"
        fill="none"
        stroke="#1e2a36"
        strokeWidth="2.4"
        strokeLinecap="round"
      />

      {/* Laptop */}
      <rect x="148" y="220" width="104" height="70" rx="8" fill="#eef3f7" />
      <rect x="156" y="228" width="88" height="54" rx="4" fill="#0e4c77" />
      <rect x="164" y="238" width="38" height="5" rx="2.5" fill="#94bed8" />
      <rect
        x="164"
        y="250"
        width="62"
        height="5"
        rx="2.5"
        fill="#ffffff"
        fillOpacity="0.55"
      />
      <rect
        x="164"
        y="262"
        width="50"
        height="5"
        rx="2.5"
        fill="#ffffff"
        fillOpacity="0.35"
      />
      <rect x="114" y="288" width="172" height="19" rx="9" fill="#d7e0e8" />
      <rect x="176" y="294" width="48" height="4" rx="2" fill="#b6c3ce" />

      {/* Hands, resting on the laptop edge */}
      <circle cx="150" cy="290" r="11" fill="#96613f" />
      <circle cx="250" cy="290" r="11" fill="#96613f" />

      {/* Notebook on the floor — the one gold note, same as everywhere else. */}
      <rect x="292" y="312" width="50" height="13" rx="4" fill="#e09b12" />
      <rect x="296" y="307" width="42" height="9" rx="3" fill="#f6dda8" />
    </svg>
  );
}
