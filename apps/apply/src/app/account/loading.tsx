import { RecordSkeleton } from "@acmis/ui/components/page-skeleton"

import { MODULE_KEY } from "@/lib/config"

export default function Loading() {
  return <RecordSkeleton moduleKey={MODULE_KEY} fields={4} aside={false} />
}
