"use server";

import { revalidatePath } from "next/cache";
import { redirect } from "next/navigation";
import { currentStaff } from "@/lib/auth";
import {
  createAnnouncement,
  deleteAnnouncement,
  getSystemSettings,
  logAudit,
} from "@/lib/data/repo";
import { can } from "@/lib/permissions";
import type { Announcement } from "@/lib/types";

async function requireManageAnnouncements() {
  const staff = await currentStaff();
  if (!staff) redirect("/login");
  const settings = await getSystemSettings();
  if (!can(staff.staffRole, "manage_announcements", settings)) redirect("/admin");
  return staff;
}

export async function postAnnouncement(formData: FormData): Promise<void> {
  const actor = await requireManageAnnouncements();

  const title = String(formData.get("title") ?? "").trim();
  const body = String(formData.get("body") ?? "").trim();
  const audience = String(formData.get("audience") ?? "all") as Announcement["audience"];
  const priority = String(formData.get("priority") ?? "normal") as Announcement["priority"];
  if (!title || !body) redirect("/admin/announcements");

  const announcement = await createAnnouncement({ title, body, audience, priority });
  await logAudit(actor.name, "Posted an announcement", announcement.title);
  revalidatePath("/admin/announcements");
  revalidatePath("/portal");
  revalidatePath("/apply");
}

export async function removeAnnouncement(formData: FormData): Promise<void> {
  const actor = await requireManageAnnouncements();
  const id = String(formData.get("id") ?? "");

  await deleteAnnouncement(id);
  await logAudit(actor.name, "Deleted an announcement", id);
  revalidatePath("/admin/announcements");
  revalidatePath("/portal");
  revalidatePath("/apply");
}
