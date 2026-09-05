import type { Metadata } from "next";
import Link from "next/link";
import { redirect } from "next/navigation";
import {
  ArrowUpRight,
  BellRing,
  BookOpen,
  CalendarDays,
  GraduationCap,
  Megaphone,
  Wallet,
} from "lucide-react";
import { Card, CardBody, CardFooter, CardHeader, Stat } from "@/components/ui/card";
import { Avatar } from "@/components/ui/avatar";
import { Badge } from "@/components/ui/badge";
import { ButtonLink } from "@/components/ui/button";
import { Callout } from "@/components/ui/callout";
import { GpaMeter } from "@/components/ui/progress";
import { EmptyState } from "@/components/ui/empty";
import { currentStudent } from "@/lib/auth";
import { programmeById } from "@/lib/data/reference";
import {
  getAnnouncements,
  getAvailableCourses,
  getCgpa,
  getFeeSummary,
  getRegisteredCourseIds,
  getTimetable,
} from "@/lib/data/repo";
import { relativeDays, shortDate, ssp } from "@/lib/format";
import { institution } from "@/lib/institution";

export const metadata: Metadata = { title: "Dashboard" };

const DAY_ORDER = ["Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"] as const;

export default async function DashboardPage() {
  const student = await currentStudent();
  if (!student) redirect("/login");

  const [programme, cgpa, fees, registered, available, timetable, announcements] =
    await Promise.all([
      programmeById(student.programmeId),
      getCgpa(student.id),
      getFeeSummary(student.id),
      getRegisteredCourseIds(student.id),
      getAvailableCourses(student),
      getTimetable(student.id),
      getAnnouncements("students"),
    ]);

  const compulsoryCount = available.filter((c) => c.compulsory).length;
  const registeredCredits = available
    .filter((c) => registered.includes(c.id))
    .reduce((sum, c) => sum + c.creditHours, 0);

  const today = DAY_ORDER[new Date().getDay()];
  const todaysClasses = timetable.filter((slot) => slot.day === today);

  return (
    <div className="mx-auto max-w-5xl space-y-5">
      <div className="flex items-center gap-4">
        <Avatar
          firstName={student.firstName}
          lastName={student.lastName}
          photoUrl={student.photoUrl}
          size="lg"
        />
        <div className="min-w-0">
          <h1 className="text-[22px] font-semibold tracking-tight text-ink">
            Good to see you, {student.firstName}
          </h1>
          <p className="mt-1 text-[13.5px] text-muted lg:hidden">
            {programme?.name} · Year {student.yearOfStudy}, Semester{" "}
            {student.currentSemester}
          </p>
          {/* The strip above already carries programme and year on desktop, so
              the student number is the more useful line to show there. */}
          <p className="nums mt-1 hidden text-[13px] text-muted lg:block">
            {student.studentNumber}
          </p>
        </div>
      </div>

      {/* Fees gate first: it is the one thing that can block everything else. */}
      {fees.blockingBalance > 0 ? (
        <Callout tone="warning" title="Tuition outstanding">
          <p>
            {ssp(fees.blockingBalance)} remains on your account. Results are
            withheld and you cannot sit examinations until the balance is
            cleared.
            {fees.nextDue ? (
              <>
                {" "}
                Next instalment is due {relativeDays(fees.nextDue.dueDate)} on{" "}
                {shortDate(fees.nextDue.dueDate)}.
              </>
            ) : null}
          </p>
          <Link
            href="/portal/finance"
            className="mt-2 inline-flex items-center gap-1 font-semibold underline underline-offset-2"
          >
            Pay by mobile money
            <ArrowUpRight className="h-3.5 w-3.5" aria-hidden />
          </Link>
        </Callout>
      ) : null}

      <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
        <Stat
          icon={GraduationCap}
          label="Cumulative GPA"
          value={cgpa === null ? "—" : cgpa.toFixed(2)}
          note={cgpa === null ? "No published results yet" : "Across all semesters"}
          accent="gold"
        />
        <Stat
          icon={BookOpen}
          label="Registered credits"
          value={registeredCredits}
          note={`${registered.length} of ${available.length} courses on offer`}
          accent="brand"
        />
        <Stat
          icon={Wallet}
          label="Fee balance"
          value={fees.balance === 0 ? "Cleared" : ssp(fees.balance)}
          note={`${ssp(fees.paid)} paid of ${ssp(fees.charged)}`}
          accent={fees.balance === 0 ? "green" : "red"}
        />
        <Stat
          icon={CalendarDays}
          label="Academic year"
          value={institution.academicYear}
          note={`Semester ${student.currentSemester}`}
          accent="none"
        />
      </div>

      <div className="grid gap-5 lg:grid-cols-5">
        {/* Today's timetable */}
        <Card className="lg:col-span-3">
          <CardHeader
            icon={CalendarDays}
            title="Today's classes"
            description={
              todaysClasses.length > 0
                ? `${today} · ${todaysClasses.length} session${todaysClasses.length === 1 ? "" : "s"}`
                : undefined
            }
            action={
              <Link
                href="/portal/timetable"
                className="text-[13px] font-medium text-brand-700 underline decoration-brand-300 underline-offset-2 hover:decoration-brand-700"
              >
                Full week
              </Link>
            }
          />
          {todaysClasses.length === 0 ? (
            <EmptyState icon={CalendarDays} title="Nothing scheduled today">
              Your next class will appear here. Check the full week to plan
              ahead.
            </EmptyState>
          ) : (
            <ul className="divide-y divide-line">
              {todaysClasses.map((slot) => (
                <li key={slot.id} className="flex items-start gap-3.5 px-4 py-3 sm:px-5">
                  <span className="nums w-[52px] shrink-0 text-[13px] font-semibold text-brand-700">
                    {slot.startsAt}
                  </span>
                  <span className="min-w-0 flex-1">
                    <span className="block text-[13.5px] font-medium leading-snug text-ink">
                      {slot.course.code} — {slot.course.title}
                    </span>
                    <span className="mt-0.5 block text-[12.5px] text-muted">
                      {slot.venue} · until {slot.endsAt}
                    </span>
                  </span>
                  <Badge tone={slot.kind === "lecture" ? "brand" : "neutral"}>
                    {slot.kind}
                  </Badge>
                </li>
              ))}
            </ul>
          )}
        </Card>

        {/* Standing */}
        <Card className="lg:col-span-2">
          <CardHeader icon={GraduationCap} title="Academic standing" />
          <CardBody className="space-y-4">
            <div>
              <p className="mb-1.5 text-[12.5px] font-medium text-muted">
                Cumulative GPA
              </p>
              {cgpa === null ? (
                <p className="text-[13px] text-muted">No published results yet.</p>
              ) : (
                <GpaMeter value={cgpa} />
              )}
            </div>
            <dl className="space-y-2 border-t border-line pt-3.5 text-[13px]">
              <Row label="Programme" value={programme?.name ?? "—"} />
              <Row label="Student number" value={student.studentNumber} nums />
              <Row label="Academic advisor" value={student.advisorName} />
              <Row
                label="Expected completion"
                value={
                  programme
                    ? `${Number(student.admittedYear.slice(0, 4)) + programme.durationYears}`
                    : "—"
                }
                nums
              />
            </dl>
          </CardBody>
          <CardFooter>
            <ButtonLink href="/portal/results" variant="secondary" size="sm">
              View results
            </ButtonLink>
          </CardFooter>
        </Card>
      </div>

      {/* Registration nudge */}
      {registered.length < compulsoryCount ? (
        <Card>
          <CardHeader
            icon={BookOpen}
            title="Course registration is incomplete"
            description={`You have registered ${registered.length} of ${compulsoryCount} compulsory courses for this semester.`}
          />
          <CardFooter>
            <ButtonLink href="/portal/registration" size="sm">
              <BookOpen className="h-4 w-4" aria-hidden />
              Complete registration
            </ButtonLink>
          </CardFooter>
        </Card>
      ) : null}

      {/* Announcements */}
      <Card>
        <CardHeader
          icon={Megaphone}
          title="Notices"
          description="From the registrar and the bursary"
        />
        {announcements.length === 0 ? (
          <EmptyState icon={Megaphone} title="No notices">
            Announcements from the university will appear here.
          </EmptyState>
        ) : (
          <ul className="divide-y divide-line">
            {announcements.map((a) => (
              <li key={a.id} className="px-4 py-3.5 sm:px-5">
                <div className="flex items-start gap-2.5">
                  {a.priority === "important" ? (
                    <BellRing
                      className="mt-0.5 h-4 w-4 shrink-0 text-gold-600"
                      aria-hidden
                    />
                  ) : (
                    <Megaphone
                      className="mt-0.5 h-4 w-4 shrink-0 text-muted"
                      aria-hidden
                    />
                  )}
                  <div className="min-w-0">
                    <p className="text-[13.5px] font-semibold leading-snug text-ink">
                      {a.title}
                    </p>
                    <p className="mt-1 text-[13px] leading-snug text-muted">
                      {a.body}
                    </p>
                    <p className="nums mt-1.5 text-[12px] text-faint">
                      {shortDate(a.postedAt)}
                    </p>
                  </div>
                </div>
              </li>
            ))}
          </ul>
        )}
      </Card>
    </div>
  );
}

function Row({
  label,
  value,
  nums,
}: {
  label: string;
  value: string;
  nums?: boolean;
}) {
  return (
    <div className="flex items-baseline justify-between gap-3">
      <dt className="shrink-0 text-muted">{label}</dt>
      <dd
        className={`text-right font-medium text-ink ${nums ? "nums" : ""}`}
      >
        {value}
      </dd>
    </div>
  );
}
