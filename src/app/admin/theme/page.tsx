import type { Metadata } from "next";
import { redirect } from "next/navigation";
import { Palette } from "lucide-react";
import { Card, CardHeader } from "@/components/ui/card";
import { Callout } from "@/components/ui/callout";
import { currentStaff } from "@/lib/auth";
import { getSystemSettings } from "@/lib/data/repo";
import { can } from "@/lib/permissions";
import { saveAppearance } from "./actions";
import { AppearanceForm } from "./form";

export const metadata: Metadata = { title: "Appearance" };

export default async function AdminThemePage() {
  const staff = await currentStaff();
  if (!staff) redirect("/login");

  const settings = await getSystemSettings();
  if (!can(staff.staffRole, "manage_appearance", settings)) {
    return (
      <Callout tone="warning" title="Restricted">
        Your role ({staff.staffRole}) does not include appearance settings.
      </Callout>
    );
  }

  return (
    <div className="mx-auto max-w-2xl space-y-5">
      <div>
        <h1 className="text-[22px] font-semibold tracking-tight text-ink">
          Appearance
        </h1>
        <p className="mt-1 text-[13.5px] text-muted">
          Every visitor who has already chosen light or dark keeps their own
          choice — this only sets what a first-time visitor sees, and the
          accent colour used across every button, link and icon chip.
        </p>
      </div>

      <form action={saveAppearance}>
        <Card>
          <CardHeader icon={Palette} title="Site-wide appearance" />
          <AppearanceForm settings={settings} />
        </Card>
      </form>
    </div>
  );
}
