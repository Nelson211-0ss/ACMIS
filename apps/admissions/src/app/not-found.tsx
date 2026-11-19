import { NotFoundState } from "@acmis/ui/components/error-state"

import { MODULE_KEY, MODULE_NAME } from "@/lib/config"

/**
 * A mistyped address, or a record route calling `notFound()`.
 *
 * Fetches nothing, for the same reason `error.tsx` fetches nothing: this page
 * has to work when the rest does not.
 */
export default function NotFound() {
  return <NotFoundState moduleKey={MODULE_KEY} moduleName={MODULE_NAME} />
}
