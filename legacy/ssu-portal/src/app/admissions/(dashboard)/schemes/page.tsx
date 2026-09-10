import type { Metadata } from "next";
import { Layers } from "lucide-react";
import { Card, CardBody, CardFooter, CardHeader } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Field, FieldGrid, Input, Textarea } from "@/components/ui/field";
import { Table, TableWrap, Td, Th, Tr } from "@/components/ui/table";
import { listSchemes } from "@/lib/data/repo";
import { FACULTIES, PROGRAMMES } from "@/lib/data/reference";
import { shortDate, ssp } from "@/lib/format";
import type { SchemeStatus } from "@/lib/types";
import { createSchemeAction, setSchemeStatusAction } from "./actions";

export const metadata: Metadata = { title: "Admission schemes" };

const STATUS_TONE: Record<SchemeStatus, "neutral" | "green" | "gold"> = {
  draft: "neutral",
  open: "green",
  closed: "gold",
};

/** The action a scheme in each status can move to next — one button, not a free-for-all matrix. */
const NEXT_ACTION: Record<SchemeStatus, { label: string; next: SchemeStatus } | null> = {
  draft: { label: "Publish", next: "open" },
  open: { label: "Close", next: "closed" },
  closed: { label: "Reopen", next: "open" },
};

export default async function AdmissionSchemesPage() {
  const schemes = await listSchemes();

  return (
    <div className="mx-auto max-w-4xl space-y-5">
      <div>
        <h1 className="text-[22px] font-semibold tracking-tight text-ink">
          Admission schemes
        </h1>
        <p className="mt-1 text-[13.5px] text-muted">
          A scheme is what an applicant sees and applies under on the Apply
          page — publish one when it should start accepting applications.
        </p>
      </div>

      <form action={createSchemeAction}>
        <Card>
          <CardHeader icon={Layers} title="New scheme" description="Created as a draft — publish it separately when ready." />
          <CardBody className="space-y-4">
            <FieldGrid>
              <Field label="Name" name="name" required>
                <Input id="name" name="name" placeholder="2027/2028 Undergraduate Intake" required />
              </Field>
              <Field label="Code" name="code" required>
                <Input id="code" name="code" placeholder="UG-2027" required />
              </Field>
            </FieldGrid>

            <Field label="Description" name="description">
              <Textarea id="description" name="description" placeholder="Shown on the scheme card applicants see." />
            </Field>

            <FieldGrid>
              <Field label="Opens" name="opensAt" required>
                <Input id="opensAt" name="opensAt" type="date" required />
              </Field>
              <Field label="Closes" name="closesAt" required>
                <Input id="closesAt" name="closesAt" type="date" required />
              </Field>
              <Field label="Decisions published by" name="resultsBy">
                <Input id="resultsBy" name="resultsBy" type="date" />
              </Field>
              <Field label="Semester begins" name="semesterStarts">
                <Input id="semesterStarts" name="semesterStarts" type="date" />
              </Field>
            </FieldGrid>

            <Field label="Application fee (SSP)" name="applicationFeeSSP" required>
              <Input id="applicationFeeSSP" name="applicationFeeSSP" type="number" min="0" step="500" defaultValue={15000} required />
            </Field>

            <fieldset>
              <legend className="mb-2 text-[13px] font-medium text-ink-soft">
                Programmes offered <span className="ml-1.5 text-[12px] font-normal text-faint">at least one</span>
              </legend>
              <div className="grid gap-x-4 gap-y-3 sm:grid-cols-2">
                {FACULTIES.map((faculty) => (
                  <div key={faculty.id}>
                    <p className="mb-1.5 text-[12px] font-semibold uppercase tracking-wide text-muted">
                      {faculty.name}
                    </p>
                    <div className="space-y-1">
                      {PROGRAMMES.filter((p) => p.facultyId === faculty.id).map((p) => (
                        <label key={p.id} className="flex items-center gap-2 text-[13px] text-ink-soft">
                          <input type="checkbox" name="programmeIds" value={p.id} className="h-4 w-4 accent-brand-700" />
                          {p.name}
                        </label>
                      ))}
                    </div>
                  </div>
                ))}
              </div>
            </fieldset>
          </CardBody>
          <CardFooter>
            <Button type="submit" size="sm">
              Create scheme
            </Button>
          </CardFooter>
        </Card>
      </form>

      <Card>
        <CardHeader icon={Layers} title="All schemes" description={`${schemes.length} total`} />
        <TableWrap>
          <Table>
            <thead>
              <tr>
                <Th>Scheme</Th>
                <Th>Programmes</Th>
                <Th>Closes</Th>
                <Th>Fee</Th>
                <Th>Status</Th>
                <Th />
              </tr>
            </thead>
            <tbody>
              {schemes.map((scheme) => {
                const nextAction = NEXT_ACTION[scheme.status];
                return (
                  <Tr key={scheme.id}>
                    <Td>
                      <span className="block font-medium text-ink">{scheme.name}</span>
                      <span className="nums block text-[12px] text-muted">{scheme.code}</span>
                    </Td>
                    <Td className="nums">{scheme.programmeIds.length}</Td>
                    <Td className="nums text-muted">{shortDate(scheme.closesAt)}</Td>
                    <Td className="nums">{ssp(scheme.applicationFeeSSP)}</Td>
                    <Td>
                      <Badge tone={STATUS_TONE[scheme.status]}>{scheme.status}</Badge>
                    </Td>
                    <Td>
                      {nextAction ? (
                        <form action={setSchemeStatusAction}>
                          <input type="hidden" name="id" value={scheme.id} />
                          <input type="hidden" name="status" value={nextAction.next} />
                          <button
                            type="submit"
                            className="rounded border border-line-strong bg-surface px-2.5 py-1.5 text-[12.5px] font-medium text-ink-soft transition-colors hover:bg-sunken"
                          >
                            {nextAction.label}
                          </button>
                        </form>
                      ) : null}
                    </Td>
                  </Tr>
                );
              })}
            </tbody>
          </Table>
        </TableWrap>
      </Card>
    </div>
  );
}
