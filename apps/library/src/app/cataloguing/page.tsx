import * as Icons from "lucide-react"

import { acmis, requireUser } from "@acmis/auth/server"
import { PageHeader } from "@acmis/ui/components/page-header"

import { LibraryShell } from "@/components/shell"
import { APP } from "@/lib/config"

import { CatalogueForm } from "./form"

export const metadata = { title: "Cataloguing" }

/**
 * Adding stock to the catalogue.
 *
 * The field names follow MARC 21 semantics closely enough that a record
 * imported from a national union catalogue loses nothing, and loosely enough
 * that a cataloguer who has never seen MARC can fill the form in. Anything
 * MARC carries that nothing here queries is kept in `marc_fields` rather than
 * dropped — a migration that silently loses fields is one nobody trusts
 * again.
 */
export default async function CataloguingPage() {
  const user = await requireUser(APP)
  const client = await acmis(APP)

  const [institution, branches] = await Promise.all([
    client.public.institution().catch(() => null),
    client.library.branches().catch(() => []),
  ])

  return (
    <LibraryShell user={user} institution={institution} currentPath="/cataloguing">
      <PageHeader
        title="Cataloguing"
        description="A record is the work; a copy is the thing on the shelf. Keeping them apart is what lets the library answer both “do you have this” and “where is accession 004512”."
      />

      <div className="grid gap-6 lg:grid-cols-[minmax(0,1fr)_20rem]">
        <CatalogueForm
          branches={
            (branches as Array<{ id: string; code: string; name: string }>).map((b) => ({
              id: b.id,
              label: `${b.code} — ${b.name}`,
            }))
          }
        />

        <aside className="text-muted-foreground space-y-4 text-sm">
          <div className="bg-muted/40 rounded-lg border p-4">
            <h2 className="text-foreground flex items-center gap-2 text-sm font-semibold">
              <Icons.Info className="size-4" aria-hidden />
              Call numbers
            </h2>
            <p className="mt-2 text-xs">
              The classification goes on the record and the full call number on the
              copy, because branches shelve differently. A relabelled book keeps its
              accession number, which is what a stock-take reconciles against.
            </p>
          </div>
          <div className="bg-muted/40 rounded-lg border p-4">
            <h2 className="text-foreground flex items-center gap-2 text-sm font-semibold">
              <Icons.BookLock className="size-4" aria-hidden />
              Loan class
            </h2>
            <p className="mt-2 text-xs">
              One copy of a set on short loan is how a library serves sixty students
              from four copies. Reference stock never leaves the reading room, and the
              desk cannot issue it by mistake.
            </p>
          </div>
        </aside>
      </div>
    </LibraryShell>
  )
}
