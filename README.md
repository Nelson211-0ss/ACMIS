# SSU Portal

A student portal and admissions application portal for South Sudanese
universities. One deployment serves any institution — Juba, Upper Nile, Bahr el
Ghazal, Rumbek — by changing environment variables.

```powershell
npm install
npm run dev        # http://localhost:3000
```

No database or API keys are needed to run it. Sign in on `/login` with either
seeded account:

| Account | Lands on | Shows |
| --- | --- | --- |
| Achol Majok — continuing student | `/portal` | Dashboard, registration, results, fees, timetable |
| Emmanuel Wani — applicant | `/apply` | A submitted application, plus a new blank one |

---

## Recommended stack, and why

**Next.js 15 (App Router) · TypeScript · Tailwind CSS v4**

The deciding constraint is not developer preference, it is that most students
will use this on an Android phone over a 2G or 3G connection that drops.

- **Server Components** mean pages arrive as HTML. The interactive parts —
  course checkboxes, subject rows, payment method pickers — are the only things
  that ship JavaScript. First-load JS is ~103 KB shared plus 0–6 KB per route.
- **Server Actions** let every form post and validate without a client-side
  data-fetching layer. Validation lives in one place (`src/lib/application.ts`)
  and runs on the server, so a form still works when client JS fails to load.
- **`output: "standalone"`** produces a self-contained server that runs on a
  cheap VPS. This matters: Vercel bills egress in USD on a card, which is
  awkward from Juba. Host it in a Nairobi or Kampala region instead and latency
  stays under 100 ms.
- **One self-hosted font.** Inter, three weights (400/500/600, no bold, no
  italic), Latin subset only — about 72 KB total, fetched once from
  `src/app/fonts/` via `next/font/local` and cached forever, not loaded live
  from a third party on every visit. Files came from Cloudflare's cdnjs
  mirror of Fontsource; see `src/app/fonts.ts` and `src/app/fonts/LICENSE.md`.
- **Tailwind v4** needs no config file and compiles the design tokens straight
  from CSS.

Alternatives weighed: Laravel + Inertia is an excellent fit and has a deeper
hiring pool in East Africa, but adds PHP ops; SvelteKit ships less JS but has a
thinner local talent pool; plain Django templates are cheap to host but weaker
for the interactive registration and wizard screens.

## Colour theme — "Nile Academic"

Defined once as tokens at the top of `src/app/globals.css`. **No gradients
anywhere** — depth comes from flat fills, one hairline border token and a single
soft shadow. If a surface needs to sit forward, its fill or border changes; two
colours are never blended.

| Role | Token | Light | Meaning |
| --- | --- | --- | --- |
| Primary | `brand-700` | `#0E4C77` | Nile blue. Institutional trust; carries all structure |
| Accent | `gold-500` | `#E09B12` | The star on the national flag. Achievement, earned progress |
| Success | `green-600` | `#17795E` | Passes, cleared balances |
| Error | `red-600` | `#BD3128` | Errors and overdue fees only — reserved, so it means something |
| Canvas | `canvas` | `#F7F8F6` | Warm paper, not cold SaaS grey |
| Text | `ink` | `#0C1B2A` | 14.9:1 on canvas |

`brand-700` on white is 8.5:1; every badge pairs its colour with an icon or a
letter so colour is never the only signal. Dark mode redefines the same tokens.
The navigation rail keeps its own `--sidebar-*` tokens because the brand ramp
inverts in dark mode and a rail must stay dark in both themes.

## Built for the conditions

- **Offline-tolerant forms.** `src/components/offline-form.tsx` mirrors every
  keystroke into `localStorage`. A draft is restored only when it is newer than
  the server's copy, and submitting while offline is refused with an
  explanation rather than silently discarding twenty minutes of typing.
- **Mobile-first.** Phones get a fixed bottom tab bar; desktop gets the navy
  rail. Tables scroll inside their own box so the page never scrolls sideways.
  Controls are 44 px tall with 16 px text, so iOS does not zoom on focus.
- **Mobile money.** m-GURUSH, Nilepay and bank deposit slips —
  `src/lib/data/payments.ts`. Part payment is the default assumption, because
  families clear tuition in instalments.
- **Local reality in the domain model.** SSCSE index numbers and best-six
  aggregates; all ten states plus the three administrative areas; national ID
  optional, because many applicants from rural counties hold none when they
  apply and requiring one would exclude them.

## Layout

```
src/
  app/
    page.tsx              landing
    login/                mock sign-in
    apply/                APPLICATION PORTAL
      page.tsx            my applications + entry requirements
      [id]/
        personal/ education/ programme/ documents/ payment/ review/
    portal/               STUDENT PORTAL
      page.tsx            dashboard
      registration/ results/ finance/ timetable/ profile/
  components/
    ui/                   button, card, field, badge, table, callout, progress
    offline-form.tsx      draft autosave + connectivity
    portal-nav.tsx        sidebar + bottom tabs
    step-nav.tsx          wizard steps
  lib/
    application.ts        validation, eligibility, step completion
    data/repo.ts          THE ONLY SEAM TO STORAGE
    data/store.ts         in-memory seed
    format.ts             SSP, dates, grading, phone normalisation
    institution.ts        per-institution config
```

## Swapping in Postgres

`src/lib/data/repo.ts` is the only file that touches storage. Every function is
already `async` and returns plain domain types from `src/lib/types.ts`; no ORM
type reaches a component. To move to a real database, rewrite the bodies in that
one file and delete `store.ts`. Nothing above it changes.

Note that `store.ts` is **not persistence** — mutations live as long as the Node
process and a `next dev` recompile can reset them.

## Replacing mock auth

`src/lib/auth.ts` sets an unsigned cookie and **checks no password**. It exists
so the portal is walkable end to end. Before this touches a real student record,
replace it with Auth.js; keep `currentSession`, `currentStudent` and the
`signIn`/`signOut` actions working and no page needs editing.

## What is not built yet

Named honestly, because each is a real gap rather than polish:

1. **Real authentication.** See above. This is the blocker for any pilot.
2. **File storage.** `uploadDocument` validates size and MIME type, then keeps
   only metadata — the bytes are dropped. Stream to S3-compatible storage and
   persist the key on the document record.
3. **Live payment providers.** The mock settles instantly. Real m-GURUSH and
   Nilepay confirm by webhook, so payments must sit at `pending` until it
   arrives. `initiatePayment` deliberately **throws** if an API key is set,
   rather than faking success — a misconfigured deploy must not tell a student
   their fee is paid.
4. **The staff side.** There is no admissions officer view: no queue, no
   document verification, no decision recording, no mark entry. Applications can
   be submitted but nothing can be decided.
5. **SMS.** The UI promises an SMS on submission and decision. Nothing sends
   one yet.
6. **Transcript PDF.** The button is present and disabled.

## Commands

```powershell
npm run dev         # dev server
npm run build       # production build
npm start           # serve the build
npm run typecheck   # tsc --noEmit
npm run lint
```
