import { PanelsSkeleton } from "@acmis/ui/components/page-skeleton"

import { MODULE_KEY } from "@/lib/config"

export default function Loading() {
  return <PanelsSkeleton moduleKey={MODULE_KEY} count={3} columns={1} />
}
