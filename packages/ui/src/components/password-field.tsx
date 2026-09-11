"use client"

import * as React from "react"
import { Eye, EyeOff } from "lucide-react"

import { cn } from "@acmis/ui/lib/utils"

export interface PasswordFieldProps extends Omit<React.ComponentProps<"input">, "type"> {
  /** Shown under the field. Use for a rule, not for an error. */
  hint?: string
}

/**
 * A password input with a reveal toggle.
 *
 * Worth having rather than leaving the browser to it. The people signing in
 * here are typing `Kampala-Demo-2026!` on a phone keyboard, in a lecture
 * theatre, one-handed — and the alternative to letting them look at what they
 * typed is a lockout after three attempts and a queue at the IT desk. NIST
 * has recommended offering this since SP 800-63B precisely because hiding the
 * password makes people choose shorter ones.
 *
 * Details that matter:
 *
 * * `autoComplete` is preserved when revealed, so password managers keep
 *   working — switching to `type="text"` without it makes a manager stop
 *   offering to fill the field.
 * * The toggle is a `button` with `aria-pressed`, so a screen reader
 *   announces the state rather than just "eye".
 * * It is `tabIndex={-1}`: someone tabbing from the password field expects to
 *   reach the submit button, not a decoration.
 * * The field resets to hidden on blur-to-submit by nature — nothing persists
 *   the revealed state, so a shared machine never shows the next person's
 *   typing.
 * * 44px of touch target on small screens, and `text-base` so iOS does not
 *   zoom the page on focus.
 */
export function PasswordField({ className, hint, id, ...props }: PasswordFieldProps) {
  const [revealed, setRevealed] = React.useState(false)
  const hintId = hint && id ? `${id}-hint` : undefined

  return (
    <div className="space-y-1.5">
      <div className="relative">
        <input
          {...props}
          id={id}
          type={revealed ? "text" : "password"}
          aria-describedby={hintId}
          // A revealed password must not be corrected or capitalised by the
          // keyboard, and must never be offered to a spell-checker service.
          autoCapitalize="none"
          autoCorrect="off"
          spellCheck={false}
          data-slot="password-input"
          className={cn(
            // `field` is the shared filled-input style; see `globals.css`.
            "field",
            // `.field` sets no horizontal padding — see the note on it in
            // `globals.css`. `pr-12` is room for the toggle, and enough of it
            // that the button never sits on top of the last characters typed.
            "pl-3 pr-12",
            className,
          )}
        />
        <button
          type="button"
          onClick={() => setRevealed((shown) => !shown)}
          aria-pressed={revealed}
          aria-label={revealed ? "Hide password" : "Show password"}
          title={revealed ? "Hide password" : "Show password"}
          tabIndex={-1}
          className="text-muted-foreground hover:text-foreground focus-visible:ring-ring absolute inset-y-0 right-0 grid w-11 place-items-center rounded-r-lg focus-visible:outline-none focus-visible:ring-2"
        >
          {revealed ? (
            <EyeOff className="size-4" aria-hidden />
          ) : (
            <Eye className="size-4" aria-hidden />
          )}
        </button>
      </div>
      {hint ? (
        <p id={hintId} className="text-muted-foreground text-xs">
          {hint}
        </p>
      ) : null}
    </div>
  )
}
