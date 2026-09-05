import { notFound } from "next/navigation";
import { StepNav } from "@/components/step-nav";
import { ApplicationStatusBadge } from "@/components/ui/badge";
import { Progress } from "@/components/ui/progress";
import { getApplication, getScheme } from "@/lib/data/repo";
import { completedSteps, progressPercent } from "@/lib/application";

export default async function ApplicationLayout({
  children,
  params,
}: {
  children: React.ReactNode;
  params: Promise<{ id: string }>;
}) {
  const { id } = await params;
  const application = await getApplication(id);
  if (!application) notFound();

  const scheme = application.schemeId ? await getScheme(application.schemeId) : null;
  const readOnly = application.status !== "draft";

  return (
    <div className="space-y-5">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <h1 className="text-[20px] font-semibold tracking-tight text-ink">
            {readOnly ? "Your application" : "Application form"}
          </h1>
          <p className="mt-1 text-[13px] text-muted">
            <span className="nums">Reference {application.reference}</span>
            {scheme ? ` · ${scheme.name}` : ""}
          </p>
        </div>
        <ApplicationStatusBadge status={application.status} />
      </div>

      {!readOnly ? (
        <Progress
          value={progressPercent(application)}
          label="Application complete"
        />
      ) : null}

      <div className="lg:grid lg:grid-cols-[248px_minmax(0,1fr)] lg:gap-8">
        <div className="lg:sticky lg:top-20 lg:self-start">
          <StepNav
            applicationId={id}
            completed={completedSteps(application)}
            readOnly={readOnly}
          />
        </div>
        <div className="mt-5 min-w-0 lg:mt-0">{children}</div>
      </div>
    </div>
  );
}
