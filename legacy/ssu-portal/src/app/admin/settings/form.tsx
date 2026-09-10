"use client";

import { useState } from "react";
import { Button } from "@/components/ui/button";
import { CardBody, CardFooter } from "@/components/ui/card";
import { ChoiceRow } from "@/components/ui/field";
import type { SystemSettings } from "@/lib/types";

export function SettingsForm({ settings }: { settings: SystemSettings }) {
  const [maintenanceMode, setMaintenanceMode] = useState(settings.maintenanceMode);
  const [registrationOpen, setRegistrationOpen] = useState(settings.registrationOpen);
  const [applicationsOpen, setApplicationsOpen] = useState(settings.applicationsOpen);

  return (
    <>
      <CardBody className="space-y-3">
        <ChoiceRow
          label="Maintenance mode"
          description="Shows a banner on the public site. Use it during a bursary reconciliation or a data fix."
          checked={maintenanceMode}
        >
          <input
            type="checkbox"
            name="maintenanceMode"
            checked={maintenanceMode}
            onChange={(e) => setMaintenanceMode(e.target.checked)}
            className="mt-0.5 h-4 w-4 accent-brand-700"
          />
        </ChoiceRow>
        <ChoiceRow
          label="Course registration open"
          description="When off, every student sees registration as closed by the registrar, regardless of their fee balance."
          checked={registrationOpen}
        >
          <input
            type="checkbox"
            name="registrationOpen"
            checked={registrationOpen}
            onChange={(e) => setRegistrationOpen(e.target.checked)}
            className="mt-0.5 h-4 w-4 accent-brand-700"
          />
        </ChoiceRow>
        <ChoiceRow
          label="New applications open"
          description="When off, the Apply page stops accepting new applications, on top of the admission cycle's own dates."
          checked={applicationsOpen}
        >
          <input
            type="checkbox"
            name="applicationsOpen"
            checked={applicationsOpen}
            onChange={(e) => setApplicationsOpen(e.target.checked)}
            className="mt-0.5 h-4 w-4 accent-brand-700"
          />
        </ChoiceRow>
      </CardBody>
      <CardFooter>
        <Button type="submit" size="sm">
          Save settings
        </Button>
      </CardFooter>
    </>
  );
}
