import type { Metadata } from "next";
import { redirect } from "next/navigation";
import { GraduationCap, IdCard, LogOut, Smartphone } from "lucide-react";
import { Card, CardBody, CardFooter, CardHeader } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Callout } from "@/components/ui/callout";
import { currentStudent } from "@/lib/auth";
import { facultyById, programmeById } from "@/lib/data/reference";
import { Avatar } from "@/components/ui/avatar";
import { displayPhone, shortDate } from "@/lib/format";
import { institution } from "@/lib/institution";
import { signOut } from "@/app/login/actions";

export const metadata: Metadata = { title: "My profile" };

export default async function ProfilePage() {
  const student = await currentStudent();
  if (!student) redirect("/login");

  const programme = programmeById(student.programmeId);
  const faculty = programme ? facultyById(programme.facultyId) : undefined;
  const expectedGraduation = programme
    ? Number(student.admittedYear.slice(0, 4)) + programme.durationYears
    : null;

  return (
    <div className="mx-auto max-w-2xl space-y-5">
      <h1 className="text-[22px] font-semibold tracking-tight text-ink">
        My profile
      </h1>

      <Card>
        <CardBody className="flex items-center gap-4">
          <Avatar
            firstName={student.firstName}
            lastName={student.lastName}
            photoUrl={student.photoUrl}
            size="md"
          />
          <div className="min-w-0">
            <p className="truncate text-[17px] font-semibold text-ink">
              {student.firstName} {student.lastName}
            </p>
            <p className="nums mt-0.5 text-[13px] text-muted">
              {student.studentNumber}
            </p>
            <Badge tone={student.status === "active" ? "green" : "gold"} className="mt-2">
              {student.status === "active" ? "Registered student" : student.status}
            </Badge>
          </div>
        </CardBody>
      </Card>

      <Card>
        <CardHeader icon={GraduationCap} title="Academic record" />
        <CardBody>
          <dl className="divide-y divide-line text-[13.5px]">
            <Row label="Programme" value={programme?.name ?? "—"} />
            <Row label="Award" value={programme ? `${programme.award} degree` : "—"} />
            <Row label="Faculty" value={faculty?.name ?? "—"} />
            <Row
              label="Year and semester"
              value={`Year ${student.yearOfStudy}, Semester ${student.currentSemester}`}
            />
            <Row label="Academic year" value={institution.academicYear} />
            <Row label="Admitted" value={student.admittedYear} />
            <Row
              label="Expected completion"
              value={expectedGraduation ? String(expectedGraduation) : "—"}
            />
            <Row label="Academic advisor" value={student.advisorName} />
          </dl>
        </CardBody>
      </Card>

      <Card>
        <CardHeader
          icon={IdCard}
          title="Contact details"
          description="Changes are made at the registry, not here."
        />
        <CardBody className="space-y-4">
          <dl className="divide-y divide-line text-[13.5px]">
            <Row label="Email" value={student.email} />
            <Row label="Mobile" value={displayPhone(student.phone)} />
          </dl>
          <Callout tone="info">
            To correct your name, date of birth or contact details, take your
            student card to the registry in person. Corrections cannot be made
            online because they affect your certificate.
          </Callout>
        </CardBody>
      </Card>

      <Card>
        <CardHeader icon={Smartphone} title="Session" />
        <CardBody>
          <p className="text-[13px] text-muted">
            Signed in on this device. Sign out if you are using a shared phone
            or a computer laboratory machine.
          </p>
        </CardBody>
        <CardFooter>
          <form action={signOut}>
            <Button type="submit" variant="secondary" size="sm">
              <LogOut className="h-4 w-4" aria-hidden />
              Sign out
            </Button>
          </form>
        </CardFooter>
      </Card>

      <p className="pb-2 text-center text-[12px] text-faint">
        {institution.name} · {institution.city} · Portal build{" "}
        {shortDate(new Date().toISOString())}
      </p>
    </div>
  );
}

function Row({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex items-baseline justify-between gap-4 py-2.5 first:pt-0 last:pb-0">
      <dt className="shrink-0 text-muted">{label}</dt>
      <dd className="text-right font-medium text-ink">{value}</dd>
    </div>
  );
}
