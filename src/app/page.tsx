import Image from "next/image";
import {
  ArrowRight,
  Building2,
  CalendarClock,
  CheckCircle2,
  GraduationCap,
  ShieldCheck,
  Wallet,
} from "lucide-react";
import type { LucideIcon } from "lucide-react";
import { Wordmark } from "@/components/brand";
import { StudentIllustration } from "@/components/student-illustration";
import { ThemeToggle } from "@/components/theme-toggle";
import { ButtonLink } from "@/components/ui/button";
import { admissionCycle, institution } from "@/lib/institution";
import { FACULTIES, PROGRAMMES } from "@/lib/data/reference";
import { getSystemSettings } from "@/lib/data/repo";
import { heroPhotoSrc } from "@/lib/hero-image";
import { relativeDays, shortDate, ssp } from "@/lib/format";

export default async function LandingPage() {
  const open = new Date(admissionCycle.closes).getTime() > Date.now();
  const settings = await getSystemSettings();
  const heroPhoto = heroPhotoSrc();

  // Derived from the same reference data the application form reads, so these
  // numbers cannot drift away from what an applicant actually sees on /apply.
  const cheapest = Math.min(...PROGRAMMES.map((p) => p.tuitionPerSemesterSSP));

  return (
    <div className="min-h-dvh">
      {settings.maintenanceMode ? (
        <div className="border-b border-gold-200 bg-gold-100 px-4 py-2.5 text-center text-[13px] font-medium text-gold-700 sm:px-6">
          Scheduled maintenance is under way. Some pages may be unavailable or
          show stale data until it finishes.
        </div>
      ) : null}

      {/* The nav sits directly on the hero gradient — no bar of its own, no
          divider — so the top of the page reads as one surface. Absolute
          rather than sticky for that reason: a sticky bar has to paint an
          opaque background the moment it leaves the hero, which is the seam
          this is meant to remove. */}
      <div className="relative">
        <header className="absolute inset-x-0 top-0 z-20">
          <div className="mx-auto flex max-w-6xl items-center justify-between gap-4 px-4 py-3.5 sm:px-6">
            <Wordmark tone="dark" />
            <div className="flex shrink-0 items-center gap-2">
              <ThemeToggle tone="dark" />
              <ButtonLink
                href="/login"
                size="sm"
                className="border-white/25 bg-transparent text-white hover:border-brand-300 hover:bg-white/5"
              >
                Sign in
              </ButtonLink>
            </div>
          </div>
        </header>

        <main id="main">
          {/* Hero. Diagonal gradient fill — the one named exception to the
              no-gradient rule; see globals.css. A photo, if one is on file,
              sits beside the copy as its own card rather than behind it, so
              legibility never depends on where a face happens to land. */}
          <section className="relative overflow-hidden border-b border-line pb-24 sm:pb-28">
            <div
              className="absolute inset-0 bg-linear-to-br from-sidebar via-sidebar-active to-sidebar-line"
              aria-hidden
            />

            <div className="relative mx-auto grid max-w-6xl gap-10 px-4 pt-24 sm:px-6 sm:pt-28 lg:grid-cols-[minmax(0,1.1fr)_minmax(0,0.9fr)] lg:items-center lg:gap-12">
            <div>
              {open ? (
                <span className="inline-flex items-center gap-2 rounded-full border border-gold-500/40 bg-gold-500/10 px-3 py-1 text-[12.5px] font-medium text-gold-500">
                  <span className="h-1.5 w-1.5 rounded-full bg-gold-500" aria-hidden />
                  Applications open · close {relativeDays(admissionCycle.closes)}
                </span>
              ) : null}

              <h1 className="mt-5 text-[32px] font-semibold leading-[1.12] tracking-tight text-white sm:text-[46px]">
                Apply, register and check your results
                <span className="block text-brand-300">from any phone.</span>
              </h1>

              <ul className="mt-5 space-y-2.5">
                <BulletLight>
                  Submit an admission application for {institution.academicYear}
                </BulletLight>
                <BulletLight>
                  Register for courses and pay fees by mobile money
                </BulletLight>
                <BulletLight>
                  Download your transcript once results are published
                </BulletLight>
              </ul>

              <div className="mt-7 flex flex-col gap-3 sm:flex-row">
                <ButtonLink href="/apply" variant="gold" size="lg">
                  Apply for admission
                  <ArrowRight className="h-4 w-4" aria-hidden />
                </ButtonLink>
                <ButtonLink
                  href="/login"
                  size="lg"
                  className="border-sidebar-line bg-transparent text-white hover:border-brand-300 hover:bg-white/5"
                >
                  <GraduationCap className="h-4 w-4" aria-hidden />
                  Continuing student sign-in
                </ButtonLink>
              </div>

              <p className="mt-5 text-[12.5px] text-sidebar-ink/80">
                Application fee {ssp(institution.applicationFeeSSP)} · paid by
                m-GURUSH, Nilepay or bank deposit slip
              </p>
            </div>

            {/* The built-in vector student, unless a real photo has been
                dropped at public/hero/student.<ext>, which then wins. */}
            <div className="mx-auto w-full max-w-md lg:mx-0">
              {heroPhoto === null ? (
                <StudentIllustration />
              ) : heroPhoto.endsWith(".svg") ? (
                // eslint-disable-next-line @next/next/no-img-element
                <img
                  src={heroPhoto}
                  alt=""
                  className="mx-auto h-auto w-full"
                />
              ) : (
                <div className="relative aspect-[4/5] overflow-hidden rounded-3xl border border-white/15 shadow-pop">
                  <Image
                    src={heroPhoto}
                    alt=""
                    fill
                    priority
                    sizes="(min-width: 1024px) 448px, 70vw"
                    className="object-cover"
                  />
                </div>
              )}
            </div>
          </div>
        </section>

        {/* Floating card, pulled up over the hero's bottom edge — same
            admission-cycle facts the old hero side-panel showed, now free of
            the hero background so it reads correctly under either theme. */}
        <div className="relative z-10 mx-auto -mt-16 max-w-4xl px-4 sm:-mt-20 sm:px-6">
          <div className="rounded-2xl border border-line bg-surface p-5 shadow-pop sm:p-6">
            <p className="flex items-center gap-2 text-[11.5px] font-semibold uppercase tracking-wide text-muted">
              <span className="h-3 w-[3px] rounded-full bg-flame-500" aria-hidden />
              {institution.academicYear} at a glance
            </p>
            <dl className="mt-4 grid grid-cols-2 gap-x-4 gap-y-3.5 sm:grid-cols-4">
              <GlanceFact label="Applications close" value={shortDate(admissionCycle.closes)} />
              <GlanceFact label="Decisions published" value={shortDate(admissionCycle.resultsBy)} />
              <GlanceFact label="Semester begins" value={shortDate(admissionCycle.semesterStarts)} />
              <GlanceFact label="Tuition from" value={`${ssp(cheapest)} / semester`} />
            </dl>
          </div>
        </div>

        {/* Built-for-here notes, paired with a preview of the actual student
            portal rather than a stock illustration — the timetable rows are
            illustrative examples, not a real student's data. */}
        <section className="mt-4 border-y border-line bg-surface px-4 py-14 sm:mt-6 sm:px-6 sm:py-16">
          <div className="mx-auto grid max-w-6xl items-center gap-10 lg:grid-cols-2 lg:gap-16">
            <DeviceMock />

            <div>
              <p className="text-[12px] font-semibold uppercase tracking-wide text-brand-700">
                Built for here
              </p>
              <h2 className="mt-2 text-[24px] font-semibold leading-tight tracking-tight text-ink sm:text-[28px]">
                Built for how you actually get online
              </h2>
              <p className="mt-3 text-[14.5px] leading-relaxed text-muted">
                Most students reach this portal on a shared phone and a 3G
                connection. Every design choice here works backwards from
                that, not from a fibre line in an office.
              </p>

              <p className="mt-6 text-[12.5px] font-semibold uppercase tracking-wide text-faint">
                Where it matters
              </p>
              <ul className="mt-3 space-y-3">
                <BulletDark>
                  Pages are rendered on the server and ship almost no
                  JavaScript — one small self-hosted font, no heavy images.
                </BulletDark>
                <BulletDark>
                  Application forms keep a copy on your device, so a dropped
                  connection never costs you an answer already typed.
                </BulletDark>
                <BulletDark>
                  Pay with mobile money from the phone in your hand, or a
                  bank deposit slip cleared by the bursary in two days.
                </BulletDark>
              </ul>
            </div>
          </div>
        </section>

        {/* What makes this portal different — the same three real reasons
            above, restated as the thing a first-time visitor scans for. */}
        <section className="mx-auto max-w-6xl px-4 py-14 text-center sm:px-6 sm:py-16">
          <h2 className="text-[24px] font-semibold tracking-tight text-ink sm:text-[28px]">
            What makes {institution.short} Portal different
          </h2>
          <p className="mx-auto mt-2 max-w-lg text-[14.5px] text-muted">
            Built specifically for {institution.name}, not adapted from a
            generic student-information system.
          </p>
          <div className="mt-8 grid gap-8 sm:grid-cols-3">
            <Differentiator
              icon={Building2}
              title="One form, every faculty"
              body={`${FACULTIES.length} faculties and ${PROGRAMMES.length} programmes, one application form and one fee.`}
            />
            <Differentiator
              icon={Wallet}
              title="Pay how South Sudan pays"
              body="Mobile money from the phone in your hand, or a bank deposit slip cleared in two days."
            />
            <Differentiator
              icon={ShieldCheck}
              title="Never lose your progress"
              body="Application forms keep a copy on your device the whole way through."
            />
          </div>
        </section>

        {/* Admission cycle */}
        <section className="border-t border-line bg-surface px-4 py-10 sm:px-6 sm:py-12">
          <div className="mx-auto max-w-6xl">
            <SectionHeading icon={CalendarClock}>
              {institution.academicYear} admission cycle
            </SectionHeading>
            <ol className="mt-5 grid gap-3 sm:grid-cols-4">
              <Milestone step={1} label="Applications open" date={admissionCycle.opens} />
              <Milestone step={2} label="Applications close" date={admissionCycle.closes} />
              <Milestone step={3} label="Decisions published" date={admissionCycle.resultsBy} />
              <Milestone step={4} label="Semester begins" date={admissionCycle.semesterStarts} />
            </ol>
          </div>
        </section>

        {/* Closing call to action. Everything above this line has been
            informational; this is the one place the page asks for the click a
            second time, right before the reader would otherwise leave. */}
        <section className="border-t border-line bg-brand-800">
          <div className="mx-auto flex max-w-6xl flex-col items-center gap-4 px-4 py-12 text-center sm:px-6">
            <span className="flex h-11 w-11 items-center justify-center rounded-full bg-gold-500">
              <GraduationCap className="h-5 w-5 text-brand-900" aria-hidden />
            </span>
            <h2 className="text-[22px] font-semibold tracking-tight text-white sm:text-[26px]">
              Ready to apply for {institution.academicYear}?
            </h2>
            <p className="max-w-md text-[14px] text-brand-100">
              It takes about fifteen minutes on your phone. You can save and
              come back any time before {shortDate(admissionCycle.closes)}.
            </p>
            <ButtonLink href="/apply" variant="gold" size="lg" className="mt-1">
              Apply for admission
              <ArrowRight className="h-4 w-4" aria-hidden />
            </ButtonLink>
          </div>
          </section>
        </main>
      </div>

      {/* Static, not sticky: on a page this long a pinned bar spends ~70px of a
          small screen on a phone number that is wanted once, at the end. */}
      <footer className="border-t border-line bg-surface">
        <div className="mx-auto flex max-w-6xl flex-col gap-3 px-4 py-6 text-[12.5px] text-muted sm:flex-row sm:items-center sm:justify-between sm:px-6">
          <p>
            {institution.name} · {institution.city}
          </p>
          <p>
            Admissions office:{" "}
            <a
              href={`tel:${institution.supportPhone.replace(/\s/g, "")}`}
              className="font-medium text-brand-700 underline underline-offset-2"
            >
              {institution.supportPhone}
            </a>
          </p>
        </div>
      </footer>
    </div>
  );
}

function SectionHeading({
  children,
  icon: Icon,
}: {
  children: React.ReactNode;
  icon?: LucideIcon;
}) {
  return (
    <h2 className="flex items-center gap-2 text-lg font-semibold text-ink">
      {Icon ? (
        <Icon className="h-[18px] w-[18px] shrink-0 text-brand-700" aria-hidden />
      ) : (
        <span className="h-4 w-[3px] shrink-0 rounded-full bg-flame-500" aria-hidden />
      )}
      {children}
    </h2>
  );
}

/** Bullet for the hero's dark gradient background. */
function BulletLight({ children }: { children: React.ReactNode }) {
  return (
    <li className="flex items-start gap-2.5 text-[14px] text-sidebar-ink sm:text-[14.5px]">
      <span className="mt-[7px] h-1.5 w-1.5 shrink-0 rounded-full bg-flame-500" aria-hidden />
      {children}
    </li>
  );
}

/** Same bullet, for a light surface. */
function BulletDark({ children }: { children: React.ReactNode }) {
  return (
    <li className="flex items-start gap-2.5 text-[13.5px] leading-relaxed text-ink-soft">
      <span className="mt-[7px] h-1.5 w-1.5 shrink-0 rounded-full bg-flame-500" aria-hidden />
      {children}
    </li>
  );
}

function GlanceFact({ label, value }: { label: string; value: string }) {
  return (
    <div>
      <dt className="text-[12px] text-muted">{label}</dt>
      <dd className="nums mt-0.5 text-[14px] font-semibold text-ink">{value}</dd>
    </div>
  );
}

/**
 * Stands in for the reference template's phone-and-payment-card illustration.
 * Built from this app's own tokens and its own real feature (the timetable),
 * with two illustrative rows rather than a real student's schedule — the
 * overlapping fee figure is real config, not a fabricated card number.
 */
function DeviceMock() {
  return (
    <div className="relative mx-auto w-full max-w-xs">
      <div className="rounded-[2rem] border border-line-strong bg-canvas p-3 shadow-pop">
        <div className="rounded-[1.4rem] border border-line bg-surface p-4">
          <p className="text-[11px] font-semibold uppercase tracking-wide text-faint">
            Today&apos;s timetable
          </p>
          <ul className="mt-3 space-y-2.5">
            <li className="rounded-lg border border-line bg-canvas px-3 py-2.5">
              <p className="text-[12.5px] font-medium text-ink">
                Data Structures &amp; Algorithms
              </p>
              <p className="nums mt-0.5 text-[11.5px] text-muted">
                Mon · 09:00–11:00 · LT2
              </p>
            </li>
            <li className="rounded-lg border border-line bg-canvas px-3 py-2.5">
              <p className="text-[12.5px] font-medium text-ink">Linear Algebra</p>
              <p className="nums mt-0.5 text-[11.5px] text-muted">
                Mon · 13:00–15:00 · Lab 1
              </p>
            </li>
          </ul>
        </div>
      </div>

      <div className="absolute -bottom-5 -right-3 w-40 rounded-xl border border-line bg-surface p-3.5 shadow-pop sm:-right-8 sm:w-44">
        <span className="flex h-8 w-8 items-center justify-center rounded-full bg-green-100">
          <CheckCircle2 className="h-4 w-4 text-green-700" aria-hidden />
        </span>
        <p className="mt-2 text-[11px] text-muted">One-time application fee</p>
        <p className="nums text-[15px] font-semibold text-ink">
          {ssp(institution.applicationFeeSSP)}
        </p>
      </div>
    </div>
  );
}

function Differentiator({
  icon: Icon,
  title,
  body,
}: {
  icon: LucideIcon;
  title: string;
  body: string;
}) {
  return (
    <div className="flex flex-col items-center">
      <span className="flex h-16 w-16 items-center justify-center rounded-full bg-brand-700">
        <Icon className="h-7 w-7 text-white" aria-hidden />
      </span>
      <h3 className="mt-4 text-[15px] font-semibold text-ink">{title}</h3>
      <p className="mt-1.5 text-[13.5px] leading-relaxed text-muted">{body}</p>
    </div>
  );
}

function Milestone({
  step,
  label,
  date,
}: {
  step: number;
  label: string;
  date: string;
}) {
  const past = new Date(date).getTime() < Date.now();
  return (
    <li className="overflow-hidden rounded-lg border border-line bg-canvas">
      <span className={`block h-1 w-full ${past ? "bg-green-600" : "bg-line-strong"}`} aria-hidden />
      <div className="p-3.5">
        <span
          className={`nums flex h-7 w-7 items-center justify-center rounded-full text-[12px] font-semibold ${
            past ? "bg-green-600 text-white" : "border border-line-strong text-muted"
          }`}
        >
          {step}
        </span>
        <p className="mt-2.5 text-[13.5px] font-medium text-ink">{label}</p>
        <p className="nums mt-0.5 text-[12.5px] text-muted">{shortDate(date)}</p>
      </div>
    </li>
  );
}
