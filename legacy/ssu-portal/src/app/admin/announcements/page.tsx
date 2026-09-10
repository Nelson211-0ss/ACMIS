import type { Metadata } from "next";
import { redirect } from "next/navigation";
import { Megaphone, Trash2 } from "lucide-react";
import { Card, CardBody, CardFooter, CardHeader } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Callout } from "@/components/ui/callout";
import { EmptyState } from "@/components/ui/empty";
import { Field, FieldGrid, Select, Textarea, Input } from "@/components/ui/field";
import { currentStaff } from "@/lib/auth";
import { getSystemSettings, listAnnouncements } from "@/lib/data/repo";
import { can } from "@/lib/permissions";
import { formatDateTime } from "@/lib/format";
import { postAnnouncement, removeAnnouncement } from "./actions";

export const metadata: Metadata = { title: "Announcements" };

export default async function AdminAnnouncementsPage() {
  const staff = await currentStaff();
  if (!staff) redirect("/login");

  const settings = await getSystemSettings();
  if (!can(staff.staffRole, "manage_announcements", settings)) {
    return (
      <Callout tone="warning" title="Restricted">
        Your role ({staff.staffRole}) does not include announcements.
      </Callout>
    );
  }

  const announcements = await listAnnouncements();

  return (
    <div className="mx-auto max-w-3xl space-y-5">
      <div>
        <h1 className="text-[22px] font-semibold tracking-tight text-ink">
          Announcements
        </h1>
        <p className="mt-1 text-[13.5px] text-muted">
          Posted here, they appear immediately on the student dashboard and the
          apply pages — this is the same feed, not a preview of one.
        </p>
      </div>

      <form action={postAnnouncement}>
        <Card>
          <CardHeader icon={Megaphone} title="Post a notice" />
          <CardBody className="space-y-4">
            <Field label="Title" name="title" required>
              <Input id="title" name="title" required />
            </Field>
            <Field label="Message" name="body" required>
              <Textarea id="body" name="body" required />
            </Field>
            <FieldGrid>
              <Field label="Audience" name="audience" required>
                <Select id="audience" name="audience" defaultValue="all">
                  <option value="all">Everyone</option>
                  <option value="students">Students only</option>
                  <option value="applicants">Applicants only</option>
                </Select>
              </Field>
              <Field label="Priority" name="priority" required>
                <Select id="priority" name="priority" defaultValue="normal">
                  <option value="normal">Normal</option>
                  <option value="important">Important</option>
                </Select>
              </Field>
            </FieldGrid>
          </CardBody>
          <CardFooter>
            <Button type="submit" size="sm">
              Post
            </Button>
          </CardFooter>
        </Card>
      </form>

      <Card>
        <CardHeader title="Posted notices" description={`${announcements.length} total`} />
        {announcements.length === 0 ? (
          <EmptyState icon={Megaphone} title="Nothing posted yet" />
        ) : (
          <ul className="divide-y divide-line">
            {announcements.map((a) => (
              <li key={a.id} className="flex items-start gap-3 px-4 py-3.5 sm:px-5">
                <div className="min-w-0 flex-1">
                  <div className="flex flex-wrap items-center gap-2">
                    <p className="text-[13.5px] font-semibold text-ink">{a.title}</p>
                    <Badge tone={a.priority === "important" ? "gold" : "neutral"}>
                      {a.priority}
                    </Badge>
                    <Badge tone="neutral">{a.audience}</Badge>
                  </div>
                  <p className="mt-1 text-[13px] leading-snug text-muted">{a.body}</p>
                  <p className="nums mt-1.5 text-[12px] text-faint">{formatDateTime(a.postedAt)}</p>
                </div>
                <form action={removeAnnouncement}>
                  <input type="hidden" name="id" value={a.id} />
                  <button
                    type="submit"
                    aria-label="Delete announcement"
                    className="flex h-8 w-8 shrink-0 items-center justify-center rounded text-muted transition-colors hover:bg-red-100 hover:text-red-700"
                  >
                    <Trash2 className="h-4 w-4" aria-hidden />
                  </button>
                </form>
              </li>
            ))}
          </ul>
        )}
      </Card>
    </div>
  );
}
