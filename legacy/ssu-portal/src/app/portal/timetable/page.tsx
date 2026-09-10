import type { Metadata } from "next";
import { redirect } from "next/navigation";
import { CalendarDays } from "lucide-react";
import { Card, CardHeader } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { EmptyState } from "@/components/ui/empty";
import { ButtonLink } from "@/components/ui/button";
import { currentStudent } from "@/lib/auth";
import { getTimetable, type TimetableRow } from "@/lib/data/repo";
import { institution } from "@/lib/institution";

export const metadata: Metadata = { title: "Timetable" };

const DAYS = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat"] as const;
const FULL_DAY: Record<(typeof DAYS)[number], string> = {
  Mon: "Monday",
  Tue: "Tuesday",
  Wed: "Wednesday",
  Thu: "Thursday",
  Fri: "Friday",
  Sat: "Saturday",
};

const KIND_TONE = {
  lecture: "brand",
  tutorial: "neutral",
  lab: "gold",
  exam: "red",
} as const;

export default async function TimetablePage() {
  const student = await currentStudent();
  if (!student) redirect("/login");

  const slots = await getTimetable(student.id);

  const byDay = DAYS.map((day) => ({
    day,
    slots: slots.filter((s) => s.day === day),
  })).filter((d) => d.slots.length > 0);

  const todayIndex = new Date().getDay(); // 1 = Mon
  const today = DAYS[todayIndex - 1];

  return (
    <div className="mx-auto max-w-4xl space-y-5">
      <div>
        <h1 className="text-[22px] font-semibold tracking-tight text-ink">
          Timetable
        </h1>
        <p className="mt-1 text-[13.5px] text-muted">
          {institution.academicYear} · Semester {student.currentSemester}. Only
          courses you have registered for are shown.
        </p>
      </div>

      {byDay.length === 0 ? (
        <Card>
          <EmptyState
            icon={CalendarDays}
            title="Nothing scheduled"
            action={
              <ButtonLink href="/portal/registration" size="sm">
                Register for courses
              </ButtonLink>
            }
          >
            Your timetable is built from your registered courses. Register
            first, and your sessions will appear here.
          </EmptyState>
        </Card>
      ) : (
        /* A day-per-card list rather than a grid: a 6×10 grid is unreadable on
           a 360px screen, and this reads identically on phone and desktop. */
        <div className="space-y-4">
          {byDay.map(({ day, slots: daySlots }) => (
            <Card key={day}>
              <CardHeader
                title={FULL_DAY[day]}
                description={`${daySlots.length} session${daySlots.length === 1 ? "" : "s"}`}
                action={day === today ? <Badge tone="gold">Today</Badge> : null}
              />
              <ul className="divide-y divide-line">
                {daySlots.map((slot) => (
                  <SlotRow key={slot.id} slot={slot} />
                ))}
              </ul>
            </Card>
          ))}
        </div>
      )}
    </div>
  );
}

function SlotRow({ slot }: { slot: TimetableRow }) {
  return (
    <li className="flex items-start gap-3.5 px-4 py-3.5 sm:px-5">
      <span className="w-[54px] shrink-0">
        <span className="nums block text-[13.5px] font-semibold text-brand-700">
          {slot.startsAt}
        </span>
        <span className="nums block text-[12px] text-faint">{slot.endsAt}</span>
      </span>
      <span className="min-w-0 flex-1">
        <span className="nums block text-[12.5px] font-semibold text-muted">
          {slot.course.code}
        </span>
        <span className="block text-[13.5px] font-medium leading-snug text-ink">
          {slot.course.title}
        </span>
        <span className="mt-0.5 block text-[12.5px] text-muted">
          {slot.venue} · {slot.course.lecturer}
        </span>
      </span>
      <Badge tone={KIND_TONE[slot.kind]}>{slot.kind}</Badge>
    </li>
  );
}
