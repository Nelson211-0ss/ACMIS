import type { Metadata } from "next";
import Link from "next/link";
import { redirect } from "next/navigation";
import { Calculator, GraduationCap, Printer } from "lucide-react";
import { Card, CardBody, CardHeader, Stat } from "@/components/ui/card";
import { Badge, GradeBadge } from "@/components/ui/badge";
import { Callout } from "@/components/ui/callout";
import { EmptyState } from "@/components/ui/empty";
import { Table, TableWrap, Td, Th, Tr } from "@/components/ui/table";
import { currentStudent } from "@/lib/auth";
import { getCgpa, getFeeSummary, getResultsBySemester } from "@/lib/data/repo";
import { classification, isPass, ssp } from "@/lib/format";
import { programmeById } from "@/lib/data/reference";

export const metadata: Metadata = { title: "Results" };

export default async function ResultsPage() {
  const student = await currentStudent();
  if (!student) redirect("/login");

  const [semesters, cgpa, fees] = await Promise.all([
    getResultsBySemester(student.id),
    getCgpa(student.id),
    getFeeSummary(student.id),
  ]);

  const programme = programmeById(student.programmeId);
  const withheld = fees.blockingBalance > 0;

  const totalCredits = semesters.reduce((sum, s) => sum + s.creditHours, 0);
  const failed = semesters.flatMap((s) => s.rows).filter((r) => !isPass(r.grade));

  return (
    <div className="mx-auto max-w-4xl space-y-5">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <h1 className="text-[22px] font-semibold tracking-tight text-ink">
            Results &amp; transcript
          </h1>
          <p className="mt-1 text-[13.5px] text-muted">
            {programme?.name} · {student.studentNumber}
          </p>
        </div>
        <button
          type="button"
          disabled
          title="Official transcripts are issued by the registrar"
          className="no-print inline-flex h-9 items-center gap-1.5 rounded border border-line-strong bg-surface px-3 text-[13px] font-medium text-muted opacity-60"
        >
          <Printer className="h-4 w-4" aria-hidden />
          Official transcript
        </button>
      </div>

      {withheld ? (
        <Callout tone="error" title="Some results are withheld">
          <p>
            {ssp(fees.blockingBalance)} of tuition is outstanding. Marks already
            published are shown below, but no new results will be released and
            no transcript can be issued until the balance is cleared.
          </p>
          <Link
            href="/portal/finance"
            className="mt-2 inline-block font-semibold underline underline-offset-2"
          >
            Clear the balance
          </Link>
        </Callout>
      ) : null}

      <div className="grid gap-3 sm:grid-cols-3">
        <Stat
          label="Cumulative GPA"
          value={cgpa === null ? "—" : cgpa.toFixed(2)}
          note={cgpa === null ? "Nothing published yet" : classification(cgpa)}
          accent="gold"
        />
        <Stat
          label="Credits earned"
          value={totalCredits}
          note={`Across ${semesters.length} semester${semesters.length === 1 ? "" : "s"}`}
          accent="brand"
        />
        <Stat
          label="Courses to retake"
          value={failed.length}
          note={failed.length === 0 ? "Nothing outstanding" : failed.map((f) => f.course.code).join(", ")}
          accent={failed.length === 0 ? "green" : "red"}
        />
      </div>

      {semesters.length === 0 ? (
        <Card>
          <EmptyState icon={GraduationCap} title="No results published yet">
            Marks appear here once the examinations board has approved and
            released them, usually four weeks after the last paper.
          </EmptyState>
        </Card>
      ) : (
        semesters.map((semester) => (
          <Card key={`${semester.academicYear}-${semester.semester}`}>
            <CardHeader
              title={`${semester.academicYear} · Semester ${semester.semester}`}
              description={`${semester.creditHours} credit hours · ${semester.rows.length} courses`}
              action={
                semester.gpa === null ? null : (
                  <Badge tone={semester.gpa >= 3 ? "green" : semester.gpa >= 2 ? "gold" : "red"}>
                    GPA {semester.gpa.toFixed(2)}
                  </Badge>
                )
              }
            />
            <TableWrap>
              <Table>
                <thead>
                  <tr>
                    <Th>Course</Th>
                    <Th className="text-right">CH</Th>
                    <Th className="text-right">Coursework /40</Th>
                    <Th className="text-right">Exam /60</Th>
                    <Th className="text-right">Total</Th>
                    <Th className="text-right">Grade</Th>
                  </tr>
                </thead>
                <tbody>
                  {semester.rows.map((row) => (
                    <Tr key={row.courseId}>
                      <Td>
                        <span className="nums block text-[13px] font-semibold text-brand-700">
                          {row.course.code}
                        </span>
                        <span className="block text-[13px] leading-snug text-ink">
                          {row.course.title}
                        </span>
                      </Td>
                      <Td className="nums text-right text-muted">
                        {row.course.creditHours}
                      </Td>
                      <Td className="nums text-right text-muted">{row.coursework}</Td>
                      <Td className="nums text-right text-muted">{row.exam}</Td>
                      <Td className="nums text-right font-semibold">{row.total}</Td>
                      <Td className="text-right">
                        <GradeBadge grade={row.grade} />
                      </Td>
                    </Tr>
                  ))}
                </tbody>
              </Table>
            </TableWrap>
          </Card>
        ))
      )}

      <Card>
        <CardHeader icon={Calculator} title="How marks are calculated" />
        <CardBody>
          <p className="text-[13px] leading-relaxed text-muted">
            Each course is marked out of 100: coursework and continuous
            assessment contribute 40, the final examination 60. Grade points are
            awarded on a 4.0 scale and averaged by credit hour. A grade of E or
            F is a fail and the course must be retaken.
          </p>
          <TableWrap className="mt-4">
            <Table>
              <thead>
                <tr>
                  <Th>Mark</Th>
                  <Th>Grade</Th>
                  <Th className="text-right">Points</Th>
                </tr>
              </thead>
              <tbody>
                {[
                  ["80 – 100", "A", "4.0"],
                  ["75 – 79", "B+", "3.5"],
                  ["70 – 74", "B", "3.0"],
                  ["65 – 69", "C+", "2.5"],
                  ["60 – 64", "C", "2.0"],
                  ["50 – 59", "D", "1.5"],
                  ["40 – 49", "E", "1.0"],
                  ["0 – 39", "F", "0.0"],
                ].map(([mark, grade, points]) => (
                  <Tr key={grade}>
                    <Td className="nums text-muted">{mark}</Td>
                    <Td className="font-semibold">{grade}</Td>
                    <Td className="nums text-right text-muted">{points}</Td>
                  </Tr>
                ))}
              </tbody>
            </Table>
          </TableWrap>
        </CardBody>
      </Card>
    </div>
  );
}
