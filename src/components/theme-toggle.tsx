"use client";

import { Moon, Sun } from "lucide-react";
import { cn } from "@/lib/cn";
import { THEME_KEY } from "@/lib/theme";

const TONES = {
  /** On a white surface: the landing header, the desktop context strip. */
  light: "text-muted hover:bg-sunken hover:text-ink",
  /** On the navy rail and phone header. */
  dark: "text-sidebar-ink hover:bg-sidebar-active hover:text-sidebar-ink-strong",
} as const;

/**
 * Light/dark switch.
 *
 * Which icon shows is decided by CSS off the same `.dark` class the button
 * writes, not by React state — so the server and client markup are identical
 * and there is nothing to hydrate or mismatch.
 */
export function ThemeToggle({
  tone = "light",
  className,
}: {
  tone?: keyof typeof TONES;
  className?: string;
}) {
  function toggle() {
    const root = document.documentElement;
    const next = !root.classList.contains("dark");
    root.classList.toggle("dark", next);
    try {
      localStorage.setItem(THEME_KEY, next ? "dark" : "light");
    } catch {
      // Private browsing with storage blocked: the choice lasts this page only.
    }
  }

  return (
    <button
      type="button"
      onClick={toggle}
      title="Switch between light and dark"
      aria-label="Switch between light and dark"
      className={cn(
        "inline-flex h-9 w-9 shrink-0 items-center justify-center rounded transition-colors",
        TONES[tone],
        className,
      )}
    >
      <Moon className="h-4 w-4 dark:hidden" aria-hidden />
      <Sun className="hidden h-4 w-4 dark:block" aria-hidden />
    </button>
  );
}
