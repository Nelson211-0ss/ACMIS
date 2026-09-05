import Link from "next/link";
import {
  ArrowRight,
  CalendarClock,
  GraduationCap,
  Phone,
  ShieldCheck,
  Smartphone,
} from "lucide-react";
import { Wordmark } from "@/components/brand";
import { ThemeToggle } from "@/components/theme-toggle";
import { ButtonLink } from "@/components/ui/button";
import { Card, CardBody } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { admissionCycle, institution } from "@/lib/institution";
import { PROGRAMMES } from "@/lib/data/reference";
import { getSystemSettings } from "@/lib/data/repo";
import { relativeDays, shortDate, ssp } from "@/lib/format";

export default async function LandingPage() {
  const open = new Date(admissionCycle.closes).getTime() > Date.now();
  const settings = await getSystemSettings();

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

      <main id="main">
        {/* Hero. Solid navy panel — flat fill, no gradient. */}
        <section className="border-b border-line bg-sidebar">
          <div className="mx-auto max-w-6xl px-4 py-12 sm:px-6 sm:py-16">
            <div className="max-w-2xl">
              {open ? (
                <span className="inline-flex items-center gap-2 rounded-full border border-gold-500/40 bg-gold-500/10 px-3 py-1 text-[12.5px] font-medium text-gold-500">
                  <span className="h-1.5 w-1.5 rounded-full bg-gold-500" aria-hidden />
                  Applications open · close {relativeDays(admissionCycle.closes)}
                </span>
              ) : (
                <Badge tone="neutral">Applications closed for {institution.academicYear}</Badge>
              )}

              <h1 className="mt-5 text-[30px] font-semibold leading-[1.15] tracking-tight text-white sm:text-[42px]">
                Apply, register and check your results
                <span className="block text-brand-300">from any phone.</span>
              </h1>

              <p className="mt-4 text-[15px] leading-relaxed text-sidebar-ink sm:text-base">
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
          </div>
        </section>

        {/* Built-for-here notes. These are the actual design constraints, said plainly. */}
        <section className="mx-auto max-w-6xl px-4 py-10 sm:px-6 sm:py-12">
          <div className="grid gap-4 sm:grid-cols-3">
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
        </section>

        {/* Admission cycle */}
        <section className="border-y border-line bg-surface">
          <div className="mx-auto max-w-6xl px-4 py-10 sm:px-6">
            <h2 className="flex items-center gap-2 text-lg font-semibold text-ink">
              <CalendarClock className="h-[18px] w-[18px] text-brand-700" aria-hidden />
              {institution.academicYear} admission cycle
            </h2>
            <ol className="mt-5 grid gap-3 sm:grid-cols-4">
              <Milestone step="1" label="Applications open" date={admissionCycle.opens} />
              <Milestone step="2" label="Applications close" date={admissionCycle.closes} />
              <Milestone step="3" label="Decisions published" date={admissionCycle.resultsBy} />
              <Milestone step="4" label="Semester begins" date={admissionCycle.semesterStarts} />
            </ol>
          </div>
        </section>

        {/* Programmes */}
        <section className="mx-auto max-w-6xl px-4 py-10 sm:px-6 sm:py-12">
          <div className="flex flex-wrap items-baseline justify-between gap-3">
            <h2 className="text-lg font-semibold text-ink">Programmes on offer</h2>
            <Link
              href="/apply"
              className="text-[13.5px] font-medium text-brand-700 underline decoration-brand-300 underline-offset-2 hover:decoration-brand-700"
            >
              See entry requirements
            </Link>
          </div>

          <ul className="mt-5 grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
            {PROGRAMMES.slice(0, 9).map((p) => (
              <li key={p.id}>
                <Card className="h-full">
                  <CardBody className="flex h-full flex-col">
                    <div className="flex items-start justify-between gap-3">
                      <h3 className="text-[14.5px] font-semibold leading-snug text-ink">
                        {p.name}
                      </h3>
                      <Badge tone="neutral" className="shrink-0">
                        {p.code}
                      </Badge>
                    </div>
                    <dl className="mt-3 space-y-1 text-[12.5px] text-muted">
                      <div className="flex justify-between gap-3">
                        <dt>Duration</dt>
                        <dd className="nums font-medium text-ink-soft">
                          {p.durationYears} years
                        </dd>
                      </div>
                      <div className="flex justify-between gap-3">
                        <dt>Minimum aggregate</dt>
                        <dd className="nums font-medium text-ink-soft">
                          {p.minimumAggregate}
                        </dd>
                      </div>
                      <div className="flex justify-between gap-3">
                        <dt>Tuition / semester</dt>
                        <dd className="nums font-medium text-ink-soft">
                          {ssp(p.tuitionPerSemesterSSP)}
                        </dd>
                      </div>
                    </dl>
                  </CardBody>
                </Card>
              </li>
            ))}
          </ul>
        </section>
      </main>

      <footer className="sticky bottom-0 z-20 rounded-t-sm border-t border-line bg-surface">
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

function Feature({
  icon: Icon,
  title,
  body,
}: {
  icon: typeof Smartphone;
  title: string;
  body: string;
}) {
  return (
    <Card>
      <CardBody>
        <span className="flex h-9 w-9 items-center justify-center rounded border border-brand-200 bg-brand-50">
          <Icon className="h-[18px] w-[18px] text-brand-700" aria-hidden />
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
  step: string;
  label: string;
  date: string;
}) {
  const past = new Date(date).getTime() < Date.now();
  return (
    <li className="relative rounded border border-line bg-canvas px-3.5 py-3 pl-4">
      <span
        className={`absolute inset-y-0 left-0 w-[3px] ${past ? "bg-green-600" : "bg-line-strong"}`}
        aria-hidden
      />
      <p className="text-[11.5px] font-semibold uppercase tracking-wide text-faint">
        Step {step}
      </p>
      <p className="mt-0.5 text-[13.5px] font-medium text-ink">{label}</p>
      <p className="nums mt-0.5 text-[12.5px] text-muted">{shortDate(date)}</p>
    </li>
  );
}
