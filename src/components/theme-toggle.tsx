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
        "relative inline-flex h-9 w-9 shrink-0 items-center justify-center overflow-hidden rounded transition-colors",
        TONES[tone],
        className,
      )}
    >
      <Moon
        aria-hidden
        className="absolute h-4 w-4 rotate-0 scale-100 opacity-100 transition-all duration-300 motion-reduce:transition-none dark:-rotate-90 dark:scale-0 dark:opacity-0"
      />
      <Sun
        aria-hidden
        className="absolute h-4 w-4 rotate-90 scale-0 opacity-0 transition-all duration-300 motion-reduce:transition-none dark:rotate-0 dark:scale-100 dark:opacity-100"
      />
    </button>
  );
}
