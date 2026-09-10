import type { Metadata } from "next";
import { redirect } from "next/navigation";
import { Building2, Settings } from "lucide-react";
import { Card, CardHeader } from "@/components/ui/card";
import { Callout } from "@/components/ui/callout";
import { currentStaff } from "@/lib/auth";
import { getSystemSettings } from "@/lib/data/repo";
import { can } from "@/lib/permissions";
import { saveBranding, saveSystemSettings } from "./actions";
import { BrandingForm } from "./branding-form";
import { SettingsForm } from "./form";

export const metadata: Metadata = { title: "System settings" };

export default async function AdminSettingsPage({
  searchParams,
}: {
  searchParams: Promise<{ error?: string }>;
}) {
  const { error } = await searchParams;
  const staff = await currentStaff();
  if (!staff) redirect("/login");

  const settings = await getSystemSettings();
  if (!can(staff.staffRole, "manage_settings", settings)) {
    return (
      <Callout tone="warning" title="Restricted">
        Your role ({staff.staffRole}) does not include system settings.
      </Callout>
    );
  }

  return (
    <div className="mx-auto max-w-2xl space-y-5">
      <div>
        <h1 className="text-[22px] font-semibold tracking-tight text-ink">
          System settings
        </h1>
        <p className="mt-1 text-[13.5px] text-muted">
          These take effect the moment you save — no redeploy, no restart.
        </p>
      </div>

      <form action={saveBranding}>
        <Card>
          <CardHeader
            icon={Building2}
            title="Institution identity"
            description="What this deployment calls itself. One build serves any university — this is where it becomes yours."
          />
          <BrandingForm branding={settings.branding} error={error} />
        </Card>
      </form>

      <form action={saveSystemSettings}>
        <Card>
          <CardHeader icon={Settings} title="Controls" />
          <SettingsForm settings={settings} />
        </Card>
      </form>
    </div>
  );
}
