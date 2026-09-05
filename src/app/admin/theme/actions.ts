"use server";

import { revalidatePath } from "next/cache";
import { redirect } from "next/navigation";
import { currentStaff } from "@/lib/auth";
import { getSystemSettings, logAudit, updateSystemSettings } from "@/lib/data/repo";
import { can } from "@/lib/permissions";
import type { AccentKey } from "@/lib/types";

const MODES = ["system", "light", "dark"] as const;
const ACCENTS: AccentKey[] = ["nile", "forest", "amethyst", "slate"];

export async function saveAppearance(formData: FormData): Promise<void> {
  const actor = await currentStaff();
  if (!actor) redirect("/login");

  const settings = await getSystemSettings();
  if (!can(actor.staffRole, "manage_appearance", settings)) redirect("/admin");

  const defaultModeRaw = String(formData.get("defaultMode") ?? "system");
  const accentRaw = String(formData.get("accent") ?? "nile");
  const defaultMode = MODES.includes(defaultModeRaw as (typeof MODES)[number])
    ? (defaultModeRaw as (typeof MODES)[number])
    : "system";
  const accent = ACCENTS.includes(accentRaw as AccentKey) ? (accentRaw as AccentKey) : "nile";

  await updateSystemSettings({ appearance: { defaultMode, accent } });
  await logAudit(actor.name, `Set appearance to ${defaultMode} default, ${accent} accent`);

  // The accent and default-mode script are read in the root layout, so every
  // route needs to re-render with the new values.
  revalidatePath("/", "layout");
}
