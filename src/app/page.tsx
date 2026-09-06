import Image from "next/image";
import {
  ArrowRight,
  Building2,
  CalendarClock,
  GraduationCap,
  Layers,
  Phone,
  ShieldCheck,
  Smartphone,
  Users,
  Wallet,
} from "lucide-react";
import type { LucideIcon } from "lucide-react";
import { Wordmark } from "@/components/brand";
import { ThemeToggle } from "@/components/theme-toggle";
import { ButtonLink } from "@/components/ui/button";
import { Card, CardBody } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
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
  const seats = PROGRAMMES.reduce((n, p) => n + p.intake, 0);
  const cheapest = Math.min(...PROGRAMMES.map((p) => p.tuitionPerSemesterSSP));

  return (
    <div className="min-h-dvh">
      <header className="sticky top-0 z-20 rounded-b-sm border-b border-line bg-surface">
        <div className="mx-auto flex max-w-6xl items-center justify-between gap-4 px-4 py-3.5 sm:px-6">
          <Wordmark />
          <div className="flex shrink-0 items-center gap-2">
            <ThemeToggle />
            <ButtonLink href="/login" variant="secondary" size="sm">
              Sign in
            </ButtonLink>
          </div>
        </div>
      </header>

      {settings.maintenanceMode ? (
        <div className="border-b border-gold-200 bg-gold-100 px-4 py-2.5 text-center text-[13px] font-medium text-gold-700 sm:px-6">
          Scheduled maintenance is under way. Some pages may be unavailable or
          show stale data until it finishes.
        </div>
      ) : null}

      <FlagRule />

      <main id="main">
        {/* Hero. With a photo on file: full-bleed image behind the copy, with
            a scrim so the text stays legible — the one named exception to the
            no-gradient rule (see globals.css). Without one: the flat dot
            field, no exception needed. Two columns from `lg`: the pitch alone
            was capped at max-w-2xl, leaving the right half of a desktop hero
            empty. */}
        <section className="relative overflow-hidden border-b border-line bg-sidebar">
          <div className="absolute inset-0" aria-hidden>
            {heroPhoto ? (
              <>
                <Image
                  src={heroPhoto}
                  alt=""
                  fill
                  priority
                  sizes="100vw"
                  className="object-cover"
                />
                {/* Solid sidebar-navy behind the copy, fading out toward the
                    photo on the right — a reading aid, not decoration. */}
                <div className="absolute inset-0 bg-linear-to-r from-sidebar from-15% via-sidebar/85 via-50% to-sidebar/10" />
                {/* Keeps the bottom edge readable regardless of what sits
                    there in the photo. */}
                <div className="absolute inset-0 bg-linear-to-t from-sidebar/70 to-transparent" />
              </>
            ) : (
              <HeroPattern />
            )}
          </div>

          <div className="relative mx-auto grid max-w-6xl gap-10 px-4 py-14 sm:px-6 sm:py-20 lg:grid-cols-[minmax(0,1.15fr)_minmax(0,0.85fr)] lg:items-center lg:gap-12">
            <div>
              {open ? (
                <span className="inline-flex items-center gap-2 rounded-full border border-gold-500/40 bg-gold-500/10 px-3 py-1 text-[12.5px] font-medium text-gold-500">
                  <span className="h-1.5 w-1.5 rounded-full bg-gold-500" aria-hidden />
                  Applications open · close {relativeDays(admissionCycle.closes)}
                </span>
              ) : (
                <Badge tone="neutral">
                  Applications closed for {institution.academicYear}
                </Badge>
              )}

              <h1 className="mt-5 text-[32px] font-semibold leading-[1.12] tracking-tight text-white sm:text-[46px]">
                Apply, register and check your results
                <span className="block text-brand-300">from any phone.</span>
              </h1>

              <p className="mt-4 max-w-xl text-[15px] leading-relaxed text-sidebar-ink sm:text-base">
                One portal for {institution.name}. Submit an admission
                application for {institution.academicYear}, or sign in to
                register for courses, pay fees by mobile money and download your
                transcript.
              </p>

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

            {/* The dates an applicant plans around, lifted out of the timeline
                further down so they are answerable without scrolling. Frosted
                rather than the old flat 4%-white panel: with a photo behind
                it, a near-transparent panel would take on whatever is in the
                photo right there and could lose contrast; the blur keeps it
                readable regardless. */}
            <div
              className={
                heroPhoto
                  ? "rounded-lg border border-sidebar-line bg-sidebar/70 p-5 backdrop-blur-sm sm:p-6"
                  : "rounded-lg border border-sidebar-line bg-white/[0.04] p-5 sm:p-6"
              }
            >
              <p className="flex items-center gap-2 text-[11.5px] font-semibold uppercase tracking-wide text-sidebar-ink">
                <span className="h-3 w-[3px] rounded-full bg-flame-500" aria-hidden />
                {institution.academicYear} at a glance
              </p>
              <dl className="mt-4 space-y-3.5">
                <HeroFact
                  label="Applications close"
                  value={shortDate(admissionCycle.closes)}
                />
                <HeroFact
                  label="Decisions published"
                  value={shortDate(admissionCycle.resultsBy)}
                />
                <HeroFact
                  label="Semester begins"
                  value={shortDate(admissionCycle.semesterStarts)}
                />
                <HeroFact label="Tuition from" value={`${ssp(cheapest)} / semester`} />
              </dl>
            </div>
          </div>
        </section>

        {/* Scale of the offer, in the applicant's terms: how much is on offer
            and how many of us get a seat. Each stat is its own bordered card
            now rather than a bare number in a column — the same lift a Card
            gives everywhere else in the app. */}
        <section className="border-b border-line bg-surface">
          <div className="mx-auto grid max-w-6xl grid-cols-2 gap-3 px-4 py-8 sm:px-6 lg:grid-cols-4">
            <Stat icon={Layers} value={String(PROGRAMMES.length)} label="Programmes" />
            <Stat icon={Building2} value={String(FACULTIES.length)} label="Faculties" />
            <Stat
              icon={Users}
              value={seats.toLocaleString("en")}
              label={`Seats for ${institution.academicYear}`}
            />
            <Stat icon={Wallet} value={ssp(institution.applicationFeeSSP)} label="Application fee" />
          </div>
        </section>

        {/* Built-for-here notes. These are the actual design constraints, said plainly. */}
        <section className="border-y border-line bg-surface px-4 py-10 sm:px-6 sm:py-12">
          <div className="mx-auto max-w-6xl">
            <SectionHeading>Built for how you actually get online</SectionHeading>
            <div className="mt-5 grid gap-4 sm:grid-cols-3">
              <Feature
                icon={Smartphone}
                title="Built for a phone on 3G"
                body="Pages are rendered on the server and ship almost no JavaScript. One small self-hosted font, no heavy images."
              />
              <Feature
                icon={ShieldCheck}
                title="Your answers are not lost"
                body="Application forms keep a copy on your device. If the network drops mid-form, nothing you typed disappears."
              />
              <Feature
                icon={Phone}
                title="Pay the way you already pay"
                body="Mobile money from the phone in your hand, or a bank deposit slip cleared by the bursary in two days."
              />
            </div>
          </div>
        </section>

        {/* Admission cycle */}
        <section className="mx-auto max-w-6xl px-4 py-10 sm:px-6 sm:py-12">
          <SectionHeading icon={CalendarClock}>
            {institution.academicYear} admission cycle
          </SectionHeading>
          <ol className="mt-5 grid gap-3 sm:grid-cols-4">
            <Milestone step={1} label="Applications open" date={admissionCycle.opens} />
            <Milestone step={2} label="Applications close" date={admissionCycle.closes} />
            <Milestone step={3} label="Decisions published" date={admissionCycle.resultsBy} />
            <Milestone step={4} label="Semester begins" date={admissionCycle.semesterStarts} />
          </ol>
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

/**
 * The national flag reduced to a 3px rule: black, red, green, closed by the
 * gold of the star. Flat segments — the no-gradient rule holds here too.
 *
 * The first band is `--ink`, so it inverts to near-white on the black theme.
 * That is deliberate: a black band on a black page is not a band, and the
 * flag carries white separator stripes anyway.
 *
 * This is what flame red is for. It says "this is a South Sudanese
 * institution", never "something is wrong" — that stays clay red's job.
 */
function FlagRule() {
  return (
    <div className="flex h-[3px] w-full" aria-hidden>
      <span className="flex-1 bg-ink" />
      <span className="flex-1 bg-flame-500" />
      <span className="flex-1 bg-green-600" />
      <span className="w-10 shrink-0 bg-gold-500" />
    </div>
  );
}

/**
 * Flat dot field behind the hero copy, used when no photo is on file. A
 * single SVG `<pattern>` of one-pixel circles, tiled — no CSS gradient
 * function anywhere, so the HARD RULE holds: this is texture from repeating a
 * flat mark, not a blend between colours. Opacity is low enough that it never
 * competes with the AA-checked text sitting on top of it.
 */
function HeroPattern() {
  return (
    <svg
      className="h-full w-full text-white/[0.06]"
      aria-hidden
    >
      <defs>
        <pattern id="hero-dots" width="22" height="22" patternUnits="userSpaceOnUse">
          <circle cx="2" cy="2" r="1.6" fill="currentColor" />
        </pattern>
      </defs>
      <rect width="100%" height="100%" fill="url(#hero-dots)" />
    </svg>
  );
}

function SectionHeading({
  children,
  sub,
  icon: Icon,
}: {
  children: React.ReactNode;
  sub?: string;
  icon?: LucideIcon;
}) {
  return (
    <div>
      <h2 className="flex items-center gap-2 text-lg font-semibold text-ink">
        {Icon ? (
          <Icon className="h-[18px] w-[18px] shrink-0 text-brand-700" aria-hidden />
        ) : (
          <span className="h-4 w-[3px] shrink-0 rounded-full bg-flame-500" aria-hidden />
        )}
        {children}
      </h2>
      {sub ? <p className="mt-1 text-[13px] text-muted">{sub}</p> : null}
    </div>
  );
}

function HeroFact({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex items-baseline justify-between gap-3 border-b border-sidebar-line pb-3 last:border-0 last:pb-0">
      <dt className="text-[13px] text-sidebar-ink">{label}</dt>
      <dd className="nums shrink-0 text-[13.5px] font-semibold text-white">{value}</dd>
    </div>
  );
}

function Stat({
  icon: Icon,
  value,
  label,
}: {
  icon: LucideIcon;
  value: string;
  label: string;
}) {
  return (
    <div className="flex items-center gap-3 rounded-lg border border-line bg-canvas px-3.5 py-3.5 sm:px-4">
      <span className="flex h-10 w-10 shrink-0 items-center justify-center rounded-lg bg-brand-700">
        <Icon className="h-5 w-5 text-white" aria-hidden />
      </span>
      <div className="min-w-0">
        <p className="nums truncate text-[19px] font-semibold leading-tight tracking-tight text-ink">
          {value}
        </p>
        <p className="truncate text-[11.5px] text-muted">{label}</p>
      </div>
    </div>
  );
}

function Feature({
  icon: Icon,
  title,
  body,
}: {
  icon: LucideIcon;
  title: string;
  body: string;
}) {
  return (
    <Card interactive>
      <CardBody>
        <span className="flex h-11 w-11 items-center justify-center rounded-lg bg-brand-700">
          <Icon className="h-5 w-5 text-white" aria-hidden />
        </span>
        <h3 className="mt-3 text-[14.5px] font-semibold text-ink">{title}</h3>
        <p className="mt-1.5 text-[13px] leading-snug text-muted">{body}</p>
      </CardBody>
    </Card>
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
    <li className="overflow-hidden rounded-lg border border-line bg-surface">
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
