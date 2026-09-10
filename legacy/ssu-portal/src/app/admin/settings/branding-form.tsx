import { Button } from "@/components/ui/button";
import { CardBody, CardFooter } from "@/components/ui/card";
import { Field, Input } from "@/components/ui/field";
import type { SystemSettings } from "@/lib/types";

/** Kept in step with MAX_LOGO_BYTES in actions.ts. */
const MAX_LOGO_KB = 256;

/**
 * Plain server component — no "use client", no local state.
 *
 * A live client-side logo preview was tried here first (FileReader, a
 * `useState` size check) and it introduced the same dev-mode bug already
 * documented on the Users table: with a Client Component in the tree, the
 * save action ran and even rendered as if it had worked, but the mutation
 * never reached the copy of the in-memory store that later requests read
 * from — the institution's name would revert the moment you navigated away.
 * A plain server-rendered form, matching AddStaffForm, does not have that
 * problem. The size and file-type check the preview gave you for free now
 * happens after submit instead of before — the server already validates
 * both and reports back with the `error` prop.
 */
export function BrandingForm({
  branding,
  error,
}: {
  branding: SystemSettings["branding"];
  error?: string;
}) {
  return (
    <>
      <CardBody className="space-y-4">
        {error ? (
          <p role="alert" className="text-[12.5px] font-medium text-red-700">
            {error}
          </p>
        ) : null}

        <Field
          label="Institution name"
          name="name"
          required
          hint="Shown in the wordmark, on every page title and across the public site."
        >
          <Input id="name" name="name" defaultValue={branding.name} required maxLength={90} />
        </Field>
        <Field
          label="Short name"
          name="short"
          required
          hint="Used where space is tight — browser tabs and the sign-in pages."
        >
          <Input id="short" name="short" defaultValue={branding.short} required maxLength={16} />
        </Field>
        <Field
          label="City"
          name="city"
          required
          hint="Appears in the footer and on the public site."
        >
          <Input id="city" name="city" defaultValue={branding.city} required maxLength={60} />
        </Field>

        <div>
          <label
            htmlFor="logo"
            className="block text-[13px] font-medium text-ink-soft"
          >
            Logo
          </label>
          <p className="mt-0.5 text-[12.5px] text-muted">
            PNG, JPG, WebP or SVG, up to {MAX_LOGO_KB}KB. Leave empty to keep
            the current mark. A square image works best.
          </p>

          <div className="mt-2.5 flex items-center gap-3">
            <span className="flex h-14 w-14 shrink-0 items-center justify-center overflow-hidden rounded-lg border border-line bg-sunken">
              {branding.logo ? (
                // eslint-disable-next-line @next/next/no-img-element
                <img
                  src={branding.logo}
                  alt="Current logo"
                  className="h-full w-full object-contain"
                />
              ) : (
                <span className="text-[11px] text-faint">None</span>
              )}
            </span>
            <input
              id="logo"
              type="file"
              name="logo"
              accept="image/png,image/jpeg,image/webp,image/svg+xml"
              className="block w-full text-[12.5px] text-muted file:mr-3 file:rounded file:border file:border-line-strong file:bg-surface file:px-3 file:py-1.5 file:text-[12.5px] file:font-medium file:text-ink hover:file:bg-sunken"
            />
          </div>

          {branding.logo ? (
            <label className="mt-3 flex items-center gap-2 text-[12.5px] text-ink-soft">
              <input
                type="checkbox"
                name="removeLogo"
                className="h-4 w-4 accent-brand-700"
              />
              Remove the uploaded logo and go back to the built-in crest
            </label>
          ) : null}
        </div>
      </CardBody>
      <CardFooter>
        <Button type="submit" size="sm">
          Save identity
        </Button>
      </CardFooter>
    </>
  );
}
