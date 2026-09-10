"use client";

import { useState } from "react";
import { Check } from "lucide-react";
import { Button } from "@/components/ui/button";
import { CardBody, CardFooter } from "@/components/ui/card";
import { ChoiceRow } from "@/components/ui/field";
import { cn } from "@/lib/cn";
import { ACCENT_PALETTES } from "@/lib/theme";
import type { AccentKey, SystemSettings } from "@/lib/types";

const MODES: Array<{ value: SystemSettings["appearance"]["defaultMode"]; label: string; description: string }> = [
  { value: "system", label: "Follow visitor's device", description: "Default. Matches whatever light/dark preference the browser reports." },
  { value: "light", label: "Always light", description: "New visitors start in light mode until they choose otherwise themselves." },
  { value: "dark", label: "Always dark", description: "New visitors start in dark mode until they choose otherwise themselves." },
];

const ACCENTS = Object.keys(ACCENT_PALETTES) as AccentKey[];

export function AppearanceForm({ settings }: { settings: SystemSettings }) {
  const [defaultMode, setDefaultMode] = useState(settings.appearance.defaultMode);
  const [accent, setAccent] = useState(settings.appearance.accent);

  return (
    <>
      <CardBody className="space-y-5">
        <fieldset>
          <legend className="mb-2 text-[13px] font-medium text-ink-soft">
            Default appearance for new visitors
          </legend>
          <div className="space-y-2">
            {MODES.map((m) => (
              <ChoiceRow
                key={m.value}
                label={m.label}
                description={m.description}
                checked={defaultMode === m.value}
              >
                <input
                  type="radio"
                  name="defaultMode"
                  value={m.value}
                  checked={defaultMode === m.value}
                  onChange={() => setDefaultMode(m.value)}
                  className="mt-0.5 h-4 w-4 accent-brand-700"
                />
              </ChoiceRow>
            ))}
          </div>
        </fieldset>

        <fieldset>
          <legend className="mb-2 text-[13px] font-medium text-ink-soft">
            Accent colour
          </legend>
          <div className="grid grid-cols-2 gap-2 sm:grid-cols-4">
            {ACCENTS.map((key) => {
              const palette = ACCENT_PALETTES[key];
              const active = accent === key;
              return (
                <label
                  key={key}
                  className={cn(
                    "flex cursor-pointer flex-col items-center gap-2 rounded border px-3 py-3 text-center transition-colors",
                    active
                      ? "border-brand-500 bg-brand-50"
                      : "border-line-strong bg-surface hover:border-brand-300",
                  )}
                >
                  <input
                    type="radio"
                    name="accent"
                    value={key}
                    checked={active}
                    onChange={() => setAccent(key)}
                    className="sr-only"
                  />
                  <span
                    className="relative flex h-8 w-8 items-center justify-center rounded-full"
                    style={{ backgroundColor: palette.light[700] }}
                    aria-hidden
                  >
                    {active ? <Check className="h-4 w-4 text-white" /> : null}
                  </span>
                  <span className="text-[12px] font-medium text-ink">{palette.label}</span>
                </label>
              );
            })}
          </div>
        </fieldset>
      </CardBody>
      <CardFooter>
        <Button type="submit" size="sm">
          Save appearance
        </Button>
      </CardFooter>
    </>
  );
}
