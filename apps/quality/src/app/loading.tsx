import { OverviewSkeleton } from "@acmis/ui/components/page-skeleton"

import { MODULE_KEY } from "@/lib/config"

export default function Loading() {
  return <OverviewSkeleton moduleKey={MODULE_KEY} tiles={4} panels={2} />
}
