import * as Icons from "lucide-react"

import { attempt } from "@acmis/api-client"
import { acmis, requireUser } from "@acmis/auth/server"
import { PageHeader } from "@acmis/ui/components/page-header"

import { ApplyShell } from "@/components/shell"
import { APP } from "@/lib/config"

export const metadata = { title: "My details" }

/**
 * The account, as opposed to the application.
 *
 * Deliberately thin, and deliberately read-only. What the institution holds
 * about an applicant is checked against documents at enrolment, so letting
 * somebody edit their own date of birth here would create a record that
 * disagrees with the certificate it will be checked against. Corrections go
 * through the admissions office, and the page says so rather than offering a
 * field that would be ignored.
 */
export default async function AccountPage() {
  const user = await requireUser(APP)
  const client = await acmis(APP)
  const institution = (await attempt(client.public.institution())).data

  return (
    <ApplyShell user={user} institution={institution} currentPath="/account">
      <PageHeader
        icon={<Icons.User />}
        title="My details"
        description="What this account holds. Your application number is also your username — keep it somewhere safe."
      />

      <section className="bg-card shadow-card rounded-lg p-4">
        <dl className="grid gap-x-6 gap-y-3 sm:grid-cols-2">
          <div>
            <dt className="eyebrow">Name</dt>
            <dd className="mt-0.5 text-sm">{user.display_name}</dd>
          </div>
          <div>
            <dt className="eyebrow">Application number</dt>
            <dd className="mt-0.5 font-mono text-sm">{user.username ?? "—"}</dd>
          </div>
          <div>
            <dt className="eyebrow">Email</dt>
            <dd className="mt-0.5 text-sm">{user.email ?? "—"}</dd>
          </div>
          <div>
            <dt className="eyebrow">Institution</dt>
            <dd className="mt-0.5 text-sm">{institution?.name ?? user.tenant_name}</dd>
          </div>
        </dl>
      </section>

      <section className="bg-card shadow-card rounded-lg p-4">
        <h2 className="text-base">Something here is wrong</h2>
        <p className="text-muted-foreground mt-2 max-w-2xl text-sm leading-relaxed">
          Names and dates of birth are checked against your certificate when you enrol, so they are
          corrected by the admissions office rather than here — a record that disagrees with your
          documents causes trouble later.
          {institution?.support_email ? (
            <>
              {" "}
              Write to{" "}
              <a
                className="text-foreground underline underline-offset-2"
                href={`mailto:${institution.support_email}`}
              >
                {institution.support_email}
              </a>{" "}
              quoting your application number.
            </>
          ) : (
            " Contact the admissions office quoting your application number."
          )}
        </p>
      </section>
    </ApplyShell>
  )
}
