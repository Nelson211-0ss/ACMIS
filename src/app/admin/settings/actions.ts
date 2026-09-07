"use server";

import { revalidatePath } from "next/cache";
import { redirect } from "next/navigation";
import { currentStaff } from "@/lib/auth";
import { getSystemSettings, logAudit, updateSystemSettings } from "@/lib/data/repo";
import { can } from "@/lib/permissions";

/** Kept in step with MAX_LOGO_KB in branding-form.tsx. */
const MAX_LOGO_BYTES = 256 * 1024;

const ALLOWED_LOGO_TYPES = [
  "image/png",
  "image/jpeg",
  "image/webp",
  "image/svg+xml",
];

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

/**
 * Institution identity: the name shown across the whole system, and an
 * optional logo replacing the built-in crest.
 *
 * The logo is stored as a data URI on the settings object rather than written
 * to public/ — see the note on SystemSettings["branding"]. That caps how big
 * it can sensibly be, hence the 256KB ceiling, which is also plenty for a
 * crest at the sizes the chrome actually renders it (32-56px).
 */
export async function saveBranding(formData: FormData): Promise<void> {
  const actor = await currentStaff();
  if (!actor) redirect("/login");

  const settings = await getSystemSettings();
  if (!can(actor.staffRole, "manage_settings", settings)) redirect("/admin");

  const name = String(formData.get("name") ?? "").trim();
  const short = String(formData.get("short") ?? "").trim();
  const city = String(formData.get("city") ?? "").trim();

  if (!name || !short || !city) {
    redirect("/admin/settings?error=" + encodeURIComponent("Name, short name and city are all required."));
  }

  const patch: { name: string; short: string; city: string; logo?: string } = {
    name,
    short,
    city,
  };

  const file = formData.get("logo");
  if (file instanceof File && file.size > 0) {
    if (!ALLOWED_LOGO_TYPES.includes(file.type)) {
      redirect("/admin/settings?error=" + encodeURIComponent("Logo must be a PNG, JPG, WebP or SVG."));
    }
    if (file.size > MAX_LOGO_BYTES) {
      redirect("/admin/settings?error=" + encodeURIComponent("Logo must be 256KB or smaller."));
    }
    const base64 = Buffer.from(await file.arrayBuffer()).toString("base64");
    patch.logo = `data:${file.type};base64,${base64}`;
  } else if (formData.has("removeLogo")) {
    patch.logo = undefined;
  }

  await updateSystemSettings({ branding: patch });

  const logoNote = patch.logo
    ? ", uploaded a new logo"
    : formData.has("removeLogo")
      ? ", removed the logo"
      : "";
  await logAudit(actor.name, `Updated institution identity (${name}${logoNote})`);

  // The wordmark, page titles and public site all read branding, so the whole
  // tree needs to see the new value.
  revalidatePath("/", "layout");
}
