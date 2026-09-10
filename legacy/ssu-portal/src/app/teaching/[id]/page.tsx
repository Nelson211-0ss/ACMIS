import type { Metadata } from "next";
import { notFound, redirect } from "next/navigation";
import { BookOpen, CheckCircle2 } from "lucide-react";
import { Card, CardBody, CardFooter, CardHeader } from "@/components/ui/card";
import { Badge, GradeBadge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Callout } from "@/components/ui/callout";
import { Input } from "@/components/ui/field";
import { EmptyState } from "@/components/ui/empty";
import { Table, TableWrap, Td, Th, Tr } from "@/components/ui/table";
import { currentStaff } from "@/lib/auth";
import { getCourse, getCourseRoster, getResultSubmission } from "@/lib/data/repo";
import { programmeById } from "@/lib/data/reference";
import { saveMarks, submitCourseResults } from "./actions";

export const metadata: Metadata = { title: "Course roster" };

export default async function TeachingCoursePage({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  const staff = await currentStaff();
  if (!staff) redirect("/login");

  const { id } = await params;
  const course = await getCourse(id);
  if (!course) notFound();
  if (staff.staffRole !== "super_admin" && course.lecturerStaffId !== staff.id) {
    redirect("/teaching");
  }

  const roster = await getCourseRoster(id);
  const programme = programmeById(course.programmeId);
  const publishedCount = roster.filter((r) => r.result?.published).length;
  const marked = roster.filter((r) => r.result !== null).length;
  const submission = await getResultSubmission(id);

  return (
    <div className="space-y-5">
      <div>
        <h1 className="text-[20px] font-semibold tracking-tight text-ink">
          {course.code} — {course.title}
        </h1>
        <p className="mt-1 text-[13px] text-muted">
          {programme?.name ?? "—"} · Year {course.year}, Semester {course.semester} ·{" "}
          {course.creditHours} credit hours
        </p>
      </div>

      {roster.length === 0 ? (
        <Card>
          <CardBody>
            <EmptyState icon={BookOpen} title="No one registered yet">
              Students who register for this course this term will appear here.
            </EmptyState>
          </CardBody>
        </Card>
      ) : (
        <>
          <form action={saveMarks.bind(null, id)}>
            <Card>
              <CardHeader
                icon={BookOpen}
                title="Roster and marks"
                description={`${roster.length} student${roster.length === 1 ? "" : "s"} registered · coursework out of 40, exam out of 60`}
              />
              <TableWrap>
                <Table>
                  <thead>
                    <tr>
                      <Th>Student</Th>
                      <Th className="text-right">Coursework /40</Th>
                      <Th className="text-right">Exam /60</Th>
                      <Th className="text-right">Total</Th>
                      <Th>Grade</Th>
                      <Th>Status</Th>
                    </tr>
                  </thead>
                  <tbody>
                    {roster.map(({ student, result }) => (
                      <Tr key={student.id}>
                        <Td>
                          <span className="block font-medium text-ink">
                            {student.firstName} {student.lastName}
                          </span>
                          <span className="nums block text-[12px] text-muted">
                            {student.studentNumber}
                          </span>
                        </Td>
                        <Td className="text-right">
                          <Input
                            type="number"
                            min={0}
                            max={40}
                            name={`coursework-${student.id}`}
                            defaultValue={result?.coursework}
                            className="ml-auto h-9 w-20 text-right"
                          />
                        </Td>
                        <Td className="text-right">
                          <Input
                            type="number"
                            min={0}
                            max={60}
                            name={`exam-${student.id}`}
                            defaultValue={result?.exam}
                            className="ml-auto h-9 w-20 text-right"
                          />
                        </Td>
                        <Td className="nums text-right font-semibold text-ink">
                          {result?.total ?? "—"}
                        </Td>
                        <Td>
                          {result ? <GradeBadge grade={result.grade} /> : <span className="text-muted">—</span>}
                        </Td>
                        <Td>
                          {result ? (
                            <Badge tone={result.published ? "green" : "gold"}>
                              {result.published ? "published" : "draft"}
                            </Badge>
                          ) : (
                            <Badge tone="neutral">not entered</Badge>
                          )}
                        </Td>
                      </Tr>
                    ))}
                  </tbody>
                </Table>
              </TableWrap>
              <CardFooter>
                <Button type="submit" size="sm">
                  Save marks
                </Button>
              </CardFooter>
            </Card>
          </form>

          <Card>
            <CardHeader
              icon={CheckCircle2}
              title="Send for approval"
              description={
                submission?.status === "pending_approval"
                  ? "With the head of department. You cannot edit marks that are under review."
                  : submission?.status === "approved"
                    ? `Approved and visible to students — ${publishedCount} of ${roster.length} published.`
                    : `${marked} of ${roster.length} students marked. The head of department publishes once they have signed off.`
              }
            />

            {submission?.status === "returned" && submission.note ? (
              <CardBody>
                <Callout tone="warning" title="Sent back for a correction">
                  {submission.note}
                </Callout>
              </CardBody>
            ) : null}

            <CardFooter className="justify-between">
              {submission?.status === "pending_approval" ? (
                <Badge tone="gold">Awaiting sign-off</Badge>
              ) : submission?.status === "approved" ? (
                <Badge tone="green">Approved and published</Badge>
              ) : (
                <form action={submitCourseResults.bind(null, id)}>
                  <Button type="submit" size="sm" disabled={marked < roster.length}>
                    Submit {roster.length} marks for approval
                  </Button>
                </form>
              )}
            </CardFooter>
          </Card>
        </>
      )}
    </div>
  );
}
