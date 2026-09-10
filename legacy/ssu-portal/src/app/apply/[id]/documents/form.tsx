"use client";

import { useActionState, useRef, useState } from "react";
import { Check, FileUp, Paperclip, Trash2 } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Callout } from "@/components/ui/callout";
import { Badge } from "@/components/ui/badge";
import { MAX_DOCUMENT_BYTES, REQUIRED_DOCUMENTS } from "@/lib/application";
import { fileSize, shortDate } from "@/lib/format";
import type { UploadedDocument } from "@/lib/types";
import type { StepState } from "../actions";

/**
 * One upload control per document kind.
 *
 * Separate forms rather than one multi-file form: on a slow connection a
 * single 4 MB post that fails takes every other file with it, and an applicant
 * photographing documents one at a time wants each one confirmed as it lands.
 */
export function DocumentsForm({
  uploadAction,
  deleteAction,
  documents,
}: {
  uploadAction: (prev: StepState, formData: FormData) => Promise<StepState>;
  deleteAction: (formData: FormData) => void;
  documents: UploadedDocument[];
}) {
  const [state, formAction] = useActionState<StepState, FormData>(
    uploadAction,
    undefined,
  );

  const missing = REQUIRED_DOCUMENTS.filter(
    (d) => d.required && !documents.some((u) => u.kind === d.kind),
  );

  return (
    <div className="space-y-4">
      {state?.ok === false && state.message ? (
        <Callout tone="error">{state.message}</Callout>
      ) : null}
      {state?.ok === true && state.message ? (
        <Callout tone="success">{state.message}</Callout>
      ) : null}

      <Callout tone="info" title="Photographs are fine">
        You do not need a scanner. Lay the document flat in good light and take
        a photograph with your phone. Keep each file under{" "}
        {fileSize(MAX_DOCUMENT_BYTES)} so it uploads on a slow connection.
      </Callout>

      <ul className="space-y-3">
        {REQUIRED_DOCUMENTS.map((spec) => (
          <DocumentSlot
            key={spec.kind}
            spec={spec}
            existing={documents.find((d) => d.kind === spec.kind)}
            formAction={formAction}
            deleteAction={deleteAction}
          />
        ))}
      </ul>

      {missing.length > 0 ? (
        <Callout tone="warning" title="Still needed">
          {missing.map((m) => m.label).join(", ")}. You cannot submit until
          these are uploaded.
        </Callout>
      ) : (
        <Callout tone="success" title="All required documents uploaded">
          The admissions office will verify them after you submit.
        </Callout>
      )}
    </div>
  );
}

function DocumentSlot({
  spec,
  existing,
  formAction,
  deleteAction,
}: {
  spec: (typeof REQUIRED_DOCUMENTS)[number];
  existing?: UploadedDocument;
  formAction: (formData: FormData) => void;
  deleteAction: (formData: FormData) => void;
}) {
  const inputRef = useRef<HTMLInputElement>(null);
  const formRef = useRef<HTMLFormElement>(null);
  const [tooBig, setTooBig] = useState<string | null>(null);

  return (
    <li className="rounded-lg border border-line bg-surface">
      <div className="flex flex-wrap items-start justify-between gap-3 px-4 py-3.5">
        <div className="min-w-0">
          <div className="flex flex-wrap items-center gap-2">
            <h3 className="text-[14px] font-semibold text-ink">{spec.label}</h3>
            {spec.required ? (
              <Badge tone="neutral">required</Badge>
            ) : (
              <Badge tone="neutral">optional</Badge>
            )}
            {existing ? (
              <Badge tone={existing.status === "verified" ? "green" : "gold"}>
                {existing.status === "verified" ? (
                  <>
                    <Check className="h-3 w-3" aria-hidden />
                    verified
                  </>
                ) : (
                  "awaiting checking"
                )}
              </Badge>
            ) : null}
          </div>
          <p className="mt-1 text-[12.5px] leading-snug text-muted">{spec.hint}</p>

          {existing ? (
            <p className="mt-2 flex items-center gap-1.5 text-[12.5px] text-ink-soft">
              <Paperclip className="h-3.5 w-3.5 shrink-0 text-muted" aria-hidden />
              <span className="truncate font-medium">{existing.fileName}</span>
              <span className="nums shrink-0 text-muted">
                {fileSize(existing.sizeBytes)} · {shortDate(existing.uploadedAt)}
              </span>
            </p>
          ) : null}

          {tooBig ? (
            <p role="alert" className="mt-2 text-[12.5px] font-medium text-red-700">
              {tooBig}
            </p>
          ) : null}
        </div>

        <div className="flex shrink-0 items-center gap-2">
          {existing ? (
            <form action={deleteAction}>
              <input type="hidden" name="documentId" value={existing.id} />
              <Button
                type="submit"
                variant="ghost"
                size="sm"
                aria-label={`Remove ${spec.label}`}
              >
                <Trash2 className="h-4 w-4" aria-hidden />
              </Button>
            </form>
          ) : null}

          <form ref={formRef} action={formAction}>
            <input type="hidden" name="kind" value={spec.kind} />
            <input
              ref={inputRef}
              type="file"
              name="file"
              accept="image/jpeg,image/png,image/webp,application/pdf"
              className="sr-only"
              onChange={(e) => {
                const file = e.target.files?.[0];
                if (!file) return;
                // Check the size before spending the upload on a doomed post.
                if (file.size > MAX_DOCUMENT_BYTES) {
                  setTooBig(
                    `${fileSize(file.size)} is too large. The limit is ${fileSize(MAX_DOCUMENT_BYTES)}.`,
                  );
                  e.target.value = "";
                  return;
                }
                setTooBig(null);
                formRef.current?.requestSubmit();
              }}
            />
            <Button
              type="button"
              variant={existing ? "secondary" : "primary"}
              size="sm"
              onClick={() => inputRef.current?.click()}
            >
              <FileUp className="h-4 w-4" aria-hidden />
              {existing ? "Replace" : "Upload"}
            </Button>
          </form>
        </div>
      </div>
    </li>
  );
}
