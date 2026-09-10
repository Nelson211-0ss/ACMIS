import type { Metadata } from "next";
import Link from "next/link";
import { redirect } from "next/navigation";
import { ArrowUpRight, BookOpen } from "lucide-react";
import { Card, CardBody, CardHeader } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { EmptyState } from "@/components/ui/empty";
import { currentStaff } from "@/lib/auth";
import { getCourseRoster, getCoursesForLecturer } from "@/lib/data/repo";
import { programmeById } from "@/lib/data/reference";

export const metadata: Metadata = { title: "My courses" };

export default async function TeachingPage() {
  const staff = await currentStaff();
  if (!staff) redirect("/login");

  const courses = await getCoursesForLecturer(staff.id);
  const rows = await Promise.all(
    courses.map(async (course) => {
      const roster = await getCourseRoster(course.id);
      const published = roster.filter((r) => r.result?.published).length;
      return { course, roster, published };
    }),
  );

  return (
    <div className="space-y-5">
      <div>
        <h1 className="text-[22px] font-semibold tracking-tight text-ink">
          My courses
        </h1>
        <p className="mt-1 text-[13.5px] text-muted">
          Enter marks for your current roster, then publish when the class is ready.
        </p>
      </div>

      {rows.length === 0 ? (
        <Card>
          <CardBody>
            <EmptyState icon={BookOpen} title="No courses assigned">
              Nothing is linked to your account yet. Ask the registrar to
              assign you as the lecturer on a course.
            </EmptyState>
          </CardBody>
        </Card>
      ) : (
        <div className="space-y-3">
          {rows.map(({ course, roster, published }) => {
            const programme = programmeById(course.programmeId);
            return (
              <Link key={course.id} href={`/teaching/${course.id}`}>
                <Card interactive>
                  <CardHeader
                    icon={BookOpen}
                    title={`${course.code} — ${course.title}`}
                    description={`${programme?.name ?? "—"} · Year ${course.year}, Semester ${course.semester}`}
                    action={<ArrowUpRight className="h-4 w-4 shrink-0 text-faint" aria-hidden />}
                  />
                  <CardBody className="flex flex-wrap items-center gap-x-5 gap-y-2 text-[13px]">
                    <span className="text-muted">
                      <span className="nums font-semibold text-ink">{roster.length}</span>{" "}
                      registered this term
                    </span>
                    {roster.length > 0 ? (
                      <Badge tone={published === roster.length ? "green" : "gold"}>
                        {published} of {roster.length} published
                      </Badge>
                    ) : null}
                  </CardBody>
                </Card>
              </Link>
            );
          })}
        </div>
      )}
    </div>
  );
}
