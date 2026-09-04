import type { Metadata } from "next";
import { notFound } from "next/navigation";
import { getApplication } from "@/lib/data/repo";
import { saveEducation } from "../actions";
import { EducationForm } from "./form";
import { ReadOnlyNotice } from "../read-only";

export const metadata: Metadata = { title: "Secondary results" };

export default async function EducationStep({
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

  return (
    <EducationForm
      action={saveEducation.bind(null, id)}
      values={application.education}
      applicationId={id}
      updatedAt={application.updatedAt}
    />
  );
}
