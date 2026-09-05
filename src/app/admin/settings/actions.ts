"use server";

import { revalidatePath } from "next/cache";
import { redirect } from "next/navigation";
import { currentStaff } from "@/lib/auth";
import { getSystemSettings, logAudit, updateSystemSettings } from "@/lib/data/repo";
import { can } from "@/lib/permissions";

export async function saveSystemSettings(formData: FormData): Promise<void> {
  const actor = await currentStaff();
  if (!actor) redirect("/login");

  const settings = await getSystemSettings();
  if (!can(actor.staffRole, "manage_settings", settings)) redirect("/admin");

  const maintenanceMode = formData.has("maintenanceMode");
  const registrationOpen = formData.has("registrationOpen");
  const applicationsOpen = formData.has("applicationsOpen");

  await updateSystemSettings({ maintenanceMode, registrationOpen, applicationsOpen });

  const changes = [
    `maintenance ${maintenanceMode ? "on" : "off"}`,
    `registration ${registrationOpen ? "open" : "closed"}`,
    `applications ${applicationsOpen ? "open" : "closed"}`,
  ].join(", ");
  await logAudit(actor.name, `Updated system settings (${changes})`);

  // Every page that reads these settings — the landing page, /apply, and
  // /portal/registration — needs to see the new value on next load.
  revalidatePath("/", "layout");
}
