import type { Metadata } from "next";
import { notFound } from "next/navigation";
import { getApplication, getScheme } from "@/lib/data/repo";
import { programmesByFacultyForScheme } from "@/lib/data/reference";
import { saveChoices } from "../actions";
import { ProgrammeForm } from "./form";
import { ReadOnlyNotice } from "../read-only";

export const metadata: Metadata = { title: "Programme choices" };

export default async function ProgrammeStep({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  const { id } = await params;
  const application = await getApplication(id);
  if (!application) notFound();

  if (application.status !== "draft") {
    return <ReadOnlyNotice applicationId={id} />;
  }

  const scheme = application.schemeId ? await getScheme(application.schemeId) : null;

  return (
    <ProgrammeForm
      action={saveChoices.bind(null, id)}
      grouped={programmesByFacultyForScheme(scheme)}
      subjects={application.education.subjects}
      initial={[...application.choices]
        .sort((a, b) => a.rank - b.rank)
        .map((c) => c.programmeId)}
      applicationId={id}
    />
  );
}
