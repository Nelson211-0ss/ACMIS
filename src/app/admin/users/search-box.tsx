"use client";

import { Search } from "lucide-react";
import { Input } from "@/components/ui/field";

/**
 * Filters the table by toggling row visibility directly via the DOM, rather
 * than holding the row list in React state. The table itself has to stay a
 * plain server-rendered component — see the comment on UsersTable for why —
 * so this can't filter by re-rendering `rows` as a client-side array.
 *
 * There is exactly one users table per page, so a plain `document.querySelector`
 * scoped by a data attribute is simpler than threading a ref through.
 */
export function UserSearchBox() {
  function onChange(query: string) {
    const q = query.trim().toLowerCase();
    const rows = document.querySelectorAll<HTMLElement>("[data-users-table] [data-search]");
    rows.forEach((row) => {
      const match = !q || (row.dataset.search ?? "").includes(q);
      row.hidden = !match;
    });
  }

  return (
    <div className="relative max-w-xs">
      <Search
        className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-faint"
        aria-hidden
      />
      <Input
        type="search"
        placeholder="Search by name or email"
        onChange={(e) => onChange(e.target.value)}
        className="h-10 pl-9"
        aria-label="Search users"
      />
    </div>
  );
}
