import { ListSkeleton } from "@acmis/ui/components/page-skeleton"

import { MODULE_KEY } from "@/lib/config"

export default function Loading() {
  return <ListSkeleton moduleKey={MODULE_KEY} rows={15} columns={5} />
}
