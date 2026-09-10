"use client"

import { createContext, useContext, type ReactNode } from "react"

import type { Capability, WhoAmI } from "@acmis/api-client"

/**
 * Client-side capability helpers.
 *
 * These decide what to *render*, never what is allowed. The API decides that,
 * on every request, against the policy bundle. Hiding a button the user cannot
 * use is a courtesy; a system whose security depends on the button being
 * hidden has no security.
 *
 * Capabilities come from the server — either on a `RecordEnvelope` or from
 * `/authz/capabilities` — so the UI and the API agree without the UI
 * containing a second, drifting copy of the rules.
 */

const UserContext = createContext<WhoAmI | null>(null)

export function UserProvider({
  user,
  children,
}: {
  user: WhoAmI
  children: ReactNode
}) {
  return <UserContext.Provider value={user}>{children}</UserContext.Provider>
}

export function useUser(): WhoAmI {
  const user = useContext(UserContext)
  if (!user) {
    throw new Error("useUser must be used inside a <UserProvider>.")
  }
  return user
}

export function useOptionalUser(): WhoAmI | null {
  return useContext(UserContext)
}

/** Does this actor hold any of these permission codes? */
export function useHasPermission(...codes: string[]): boolean {
  const user = useOptionalUser()
  if (!user) return false
  return codes.some((code) => user.permissions.includes(code))
}

/** Renders children only if the actor holds one of the permissions. */
export function IfPermitted({
  permissions,
  children,
  fallback = null,
}: {
  permissions: string | string[]
  children: ReactNode
  fallback?: ReactNode
}) {
  const wanted = Array.isArray(permissions) ? permissions : [permissions]
  const allowed = useHasPermission(...wanted)
  return <>{allowed ? children : fallback}</>
}

export function capabilityMap(capabilities: Capability[]): Record<string, boolean> {
  return Object.fromEntries(capabilities.map((c) => [c.action, c.allowed]))
}

/**
 * Renders children only when the server said this action is allowed on this
 * record. Note the default: an action the server did not mention is treated as
 * *not* allowed, matching the API's deny-by-default.
 */
export function IfCapable({
  capabilities,
  action,
  children,
  fallback = null,
}: {
  capabilities: Capability[]
  action: string
  children: ReactNode
  fallback?: ReactNode
}) {
  const allowed = capabilities.find((c) => c.action === action)?.allowed ?? false
  return <>{allowed ? children : fallback}</>
}

/**
 * Renders a note that a field exists but is withheld.
 *
 * Deliberate: telling a reader "restricted" is much better than an empty cell,
 * which reads as "not recorded". The API names masked fields for exactly this
 * — naming *that* a field exists is safe; its value is not disclosed.
 */
export function MaskedField({
  masked,
  field,
  children,
}: {
  masked: string[]
  field: string
  children: ReactNode
}) {
  if (masked.includes(field)) {
    return (
      <span
        className="text-muted-foreground inline-flex items-center gap-1 text-sm italic"
        title="You do not have permission to view this field."
      >
        Restricted
      </span>
    )
  }
  return <>{children}</>
}
