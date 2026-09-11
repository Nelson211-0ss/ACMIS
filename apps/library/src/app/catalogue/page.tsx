import * as Icons from "lucide-react"

import type { CatalogueRecordRow } from "@acmis/api-client"
import { acmis, requireUser } from "@acmis/auth/server"
import { DataTable, Pagination, type Column } from "@acmis/ui/components/data-table"
import { EmptyState } from "@acmis/ui/components/empty-state"
import { PageHeader } from "@acmis/ui/components/page-header"
import { StatusBadge } from "@acmis/ui/components/status-badge"

import { LibraryShell } from "@/components/shell"
import { APP } from "@/lib/config"

export const metadata = { title: "Catalogue" }

/**
 * Catalogue search.
 *
 * One box, not a form of fields. A reader looking for a half-remembered book
 * does not know whether the phrase they have is in the title, the author or
 * the subject heading, and making them choose is how a search returns nothing.
 */
export default async function CataloguePage({
  searchParams,
}: {
  searchParams: Promise<{ q?: string; material_kind?: string; cursor?: string }>
}) {
  const { q, material_kind, cursor } = await searchParams
  const user = await requireUser(APP)
  const client = await acmis(APP)

  const [institution, page] = await Promise.all([
    client.public.institution().catch(() => null),
    client.library.search({ q, material_kind, cursor, limit: 25, with_total: true }),
  ])

  const columns: Array<Column<CatalogueRecordRow>> = [
    {
      key: "title",
      header: "Title",
      render: (row) => (
        <div>
          <div className="font-medium">{row.title}</div>
          {row.statement_of_responsibility ? (
            <div className="text-muted-foreground text-xs">{row.statement_of_responsibility}</div>
          ) : null}
        </div>
      ),
    },
    {
      key: "edition",
      header: "Edition",
      secondary: true,
      render: (row) => row.edition ?? "—",
    },
    {
      key: "published",
      header: "Published",
      numeric: true,
      secondary: true,
      render: (row) => row.published_year ?? "—",
    },
    {
      key: "class",
      header: "Call number",
      secondary: true,
      render: (row) =>
        row.classification ? <span className="font-mono text-xs">{row.classification}</span> : "—",
    },
    {
      key: "kind",
      header: "Kind",
      render: (row) => (
        <StatusBadge tone="neutral" dot={false}>
          {row.material_kind.replace(/_/g, " ")}
        </StatusBadge>
      ),
    },
  ]

  return (
    <LibraryShell user={user} institution={institution} currentPath="/catalogue">
      <PageHeader
        icon={<Icons.Search />}
        title="Catalogue"
        description="Everything the library holds, searchable by title, author or ISBN in one box. What is on the shelf now is on each record."
      />

      <form className="flex flex-wrap items-end gap-3" method="get">
        <div className="space-y-1">
          <label htmlFor="q" className="text-muted-foreground text-xs font-medium">
            Search
          </label>
          <input
            id="q"
            name="q"
            defaultValue={q}
            placeholder="Title, author or ISBN"
            className="border-input bg-background w-72 rounded-md border px-2.5 py-1.5 text-base sm:text-sm"
          />
        </div>
        <div className="space-y-1">
          <label htmlFor="material_kind" className="text-muted-foreground text-xs font-medium">
            Kind
          </label>
          <select
            id="material_kind"
            name="material_kind"
            defaultValue={material_kind ?? ""}
            className="border-input bg-background rounded-md border px-2.5 py-1.5 text-base sm:text-sm"
          >
            <option value="">Anything</option>
            {["book", "journal", "thesis", "e_book", "e_journal", "audio", "video"].map((value) => (
              <option key={value} value={value}>
                {value.replace(/_/g, " ")}
              </option>
            ))}
          </select>
        </div>
        <button
          type="submit"
          className="bg-primary text-primary-foreground h-9 rounded-md px-4 text-sm font-medium"
        >
          Search
        </button>
      </form>

      <DataTable
        caption="Catalogue records matching the search"
        columns={columns}
        rows={page.items}
        rowKey={(row) => row.id}
        onRowHref={(row) => `/catalogue/${row.id}`}
        mobileCard={(row) => (
          <div className="space-y-1">
            <div className="font-medium">{row.title}</div>
            <div className="text-muted-foreground text-xs">
              {row.statement_of_responsibility ?? "—"}
              {row.published_year ? ` · ${row.published_year}` : ""}
            </div>
            {row.classification ? (
              <div className="font-mono text-xs">{row.classification}</div>
            ) : null}
          </div>
        )}
        empty={
          <EmptyState
            icon={<Icons.SearchX />}
            title={q ? `Nothing matches “${q}”` : "Search the catalogue"}
            reason={
              q
                ? "Try fewer words, or the author's surname on its own. An ISBN has to be exact."
                : "Search by title, author or ISBN."
            }
          />
        }
      />

      <Pagination
        meta={page.meta}
        onNext={
          page.meta.next_cursor
            ? `/catalogue?${new URLSearchParams({
                ...(q ? { q } : {}),
                ...(material_kind ? { material_kind } : {}),
                cursor: page.meta.next_cursor,
              })}`
            : undefined
        }
      />
    </LibraryShell>
  )
}
