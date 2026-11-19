"use client"

import { ErrorState } from "@acmis/ui/components/error-state"

import { MODULE_KEY, MODULE_NAME } from "@/lib/config"

/**
 * Where an uncaught throw anywhere in this app lands.
 *
 * Before this file existed it landed on the framework's own page: white, no
 * crest, no module, no way back. A registry clerk who hit one had nothing to
 * tell support and nowhere to click.
 *
 * It is deliberately thin. Everything it needs comes from `lib/config.ts` at
 * compile time, so the page renders even when the API — the usual reason for
 * being here — is the thing that is down.
 */
export default function AppError({
  error,
  reset,
}: {
  error: Error & { digest?: string }
  reset: () => void
}) {
  return <ErrorState error={error} reset={reset} moduleKey={MODULE_KEY} moduleName={MODULE_NAME} />
}
