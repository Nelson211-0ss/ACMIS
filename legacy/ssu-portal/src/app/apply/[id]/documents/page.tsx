import type { Metadata } from "next";
import { notFound } from "next/navigation";
import { ButtonLink } from "@/components/ui/button";
import { getApplication } from "@/lib/data/repo";
import { REQUIRED_DOCUMENTS } from "@/lib/application";
import { deleteDocument, uploadDocument } from "../actions";
import { DocumentsForm } from "./form";
import { ReadOnlyNotice } from "../read-only";

export const metadata: Metadata = { title: "Documents" };

export default async function DocumentsStep({
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

  const allRequiredPresent = REQUIRED_DOCUMENTS.filter((d) => d.required).every(
    (d) => application.documents.some((u) => u.kind === d.kind),
  );

  return (
    <div className="space-y-5">
      <DocumentsForm
        uploadAction={uploadDocument.bind(null, id)}
        deleteAction={deleteDocument.bind(null, id)}
        documents={application.documents}
      />

      <div className="flex justify-end">
        <ButtonLink
          href={`/apply/${id}/payment`}
          variant={allRequiredPresent ? "primary" : "secondary"}
        >
          Continue to the application fee
        </ButtonLink>
      </div>
    </div>
  );
}
