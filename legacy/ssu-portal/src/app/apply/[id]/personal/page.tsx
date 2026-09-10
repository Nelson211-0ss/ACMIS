import type { Metadata } from "next";
import { notFound } from "next/navigation";
import { getApplication } from "@/lib/data/repo";
import { savePersonal } from "../actions";
import { PersonalForm } from "./form";
import { ReadOnlyNotice } from "../read-only";

export const metadata: Metadata = { title: "Personal details" };

export default async function PersonalStep({
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
    <PersonalForm
      action={savePersonal.bind(null, id)}
      values={application.personal}
      applicationId={id}
      updatedAt={application.updatedAt}
    />
  );
}
