import { notFound, redirect } from "next/navigation";
import { getApplication } from "@/lib/data/repo";
import { nextIncompleteStep } from "@/lib/application";

/** Bare `/apply/[id]` drops the applicant at the first unfinished step. */
export default async function ApplicationIndex({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  const { id } = await params;
  const application = await getApplication(id);
  if (!application) notFound();

  redirect(`/apply/${id}/${nextIncompleteStep(application)}`);
}
