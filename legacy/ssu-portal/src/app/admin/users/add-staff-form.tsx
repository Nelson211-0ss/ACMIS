import { UserPlus } from "lucide-react";
import { Button } from "@/components/ui/button";
import { CardBody, CardFooter } from "@/components/ui/card";
import { Field, FieldGrid, Input, Select } from "@/components/ui/field";
import { STAFF_ROLE_LABELS, STAFF_ROLES } from "@/lib/permissions";
import type { StaffRole } from "@/lib/types";

/**
 * New staff account. Server component with a plain form — no client state to
 * hold, so nothing here needs to ship as JavaScript.
 *
 * `canGrantSuperAdmin` mirrors the check the action enforces; the action is
 * the one that actually decides, this only avoids offering a choice that
 * would be rejected.
 */
export function AddStaffForm({
  canGrantSuperAdmin,
  error,
}: {
  canGrantSuperAdmin: boolean;
  error?: string;
}) {
  const roles = STAFF_ROLES.filter(
    (r) => canGrantSuperAdmin || r !== "super_admin",
  );

  return (
    <>
      <CardBody className="space-y-4">
        {error ? (
          <p role="alert" className="text-[12.5px] font-medium text-red-700">
            {error}
          </p>
        ) : null}

        <FieldGrid>
          <Field label="Full name" name="name" required>
            <Input
              id="name"
              name="name"
              autoComplete="off"
              placeholder="Grace Lueth"
              required
              maxLength={80}
            />
          </Field>
          <Field
            label="Email"
            name="email"
            required
            hint="This is how they sign in, so it has to be unique."
          >
            <Input
              id="email"
              name="email"
              type="email"
              autoComplete="off"
              placeholder="grace.lueth@uoj.example.ss"
              required
              maxLength={120}
            />
          </Field>
        </FieldGrid>

        <Field
          label="Role"
          name="staffRole"
          required
          hint="What each role can do is set on the Roles & permissions page."
        >
          <Select id="staffRole" name="staffRole" defaultValue="viewer" required>
            {roles.map((role: StaffRole) => (
              <option key={role} value={role}>
                {STAFF_ROLE_LABELS[role]}
              </option>
            ))}
          </Select>
        </Field>
      </CardBody>
      <CardFooter>
        <Button type="submit" size="sm">
          <UserPlus className="h-4 w-4" aria-hidden />
          Add staff member
        </Button>
      </CardFooter>
    </>
  );
}
