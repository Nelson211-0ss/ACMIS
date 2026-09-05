import type { Metadata } from "next";
import { notFound, redirect } from "next/navigation";
import { BookOpen, CheckCircle2 } from "lucide-react";
import { Card, CardBody, CardFooter, CardHeader } from "@/components/ui/card";
import { Badge, GradeBadge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/field";
import { EmptyState } from "@/components/ui/empty";
import { Table, TableWrap, Td, Th, Tr } from "@/components/ui/table";
import { currentStaff } from "@/lib/auth";
import { getCourse, getCourseRoster } from "@/lib/data/repo";
import { programmeById } from "@/lib/data/reference";
import { publishCourseResults, saveMarks } from "./actions";

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
              title="Publish to students"
              description={`${publishedCount} of ${roster.length} currently published`}
            />
            <CardFooter className="justify-between">
              <form action={publishCourseResults.bind(null, id)}>
                <input type="hidden" name="published" value="true" />
                <Button type="submit" size="sm">
                  Publish all entered marks
                </Button>
              </form>
              <form action={publishCourseResults.bind(null, id)}>
                <input type="hidden" name="published" value="false" />
                <Button type="submit" variant="secondary" size="sm">
                  Withdraw publication
                </Button>
              </form>
            </CardFooter>
          </Card>
        </>
      )}
    </div>
  );
}
