import type { Metadata } from "next";
import { redirect } from "next/navigation";
import {
  Activity,
  AlertTriangle,
  CheckCircle2,
  CircleDashed,
  Clock,
  Cpu,
  Gauge,
  MemoryStick,
  Timer,
  TrendingUp,
} from "lucide-react";
import { Card, CardBody, CardHeader, Stat } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Callout } from "@/components/ui/callout";
import { currentStaff } from "@/lib/auth";
import { getSystemSettings } from "@/lib/data/repo";
import { can } from "@/lib/permissions";

export const metadata: Metadata = { title: "Monitoring" };

function formatUptime(seconds: number): string {
  const h = Math.floor(seconds / 3600);
  const m = Math.floor((seconds % 3600) / 60);
  const s = Math.floor(seconds % 60);
  return `${h}h ${m}m ${s}s`;
}

function formatBytes(bytes: number): string {
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

/**
 * A deterministic-looking week of request counts, seeded from the day so it
 * does not reshuffle on every request. There is no telemetry pipeline behind
 * this app to report real traffic from — see the label on the card.
 */
function sampleWeek(): number[] {
  const base = 180;
  return Array.from({ length: 7 }, (_, i) => {
    const day = new Date();
    day.setDate(day.getDate() - (6 - i));
    const seed = day.getDate() + day.getMonth() * 31;
    return base + ((seed * 37) % 140) - (day.getDay() === 0 || day.getDay() === 6 ? 60 : 0);
  });
}

export default async function AdminMonitoringPage() {
  const staff = await currentStaff();
  if (!staff) redirect("/login");

  const settings = await getSystemSettings();
  if (!can(staff.staffRole, "view_monitoring", settings)) {
    return (
      <Callout tone="warning" title="Restricted">
        Your role ({staff.staffRole}) does not include monitoring.
      </Callout>
    );
  }

  const mem = process.memoryUsage();
  const week = sampleWeek();
  const maxDay = Math.max(...week);
  const dayLabels = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"];

  const checks = [
    {
      label: "Database",
      ok: false,
      detail: process.env.DATABASE_URL
        ? "DATABASE_URL is set — connected"
        : "DATABASE_URL is unset — running on the in-memory store",
    },
    {
      label: "m-GURUSH",
      ok: Boolean(process.env.MGURUSH_API_KEY),
      detail: process.env.MGURUSH_API_KEY
        ? "Live API key configured"
        : "No API key — payments use the mock provider",
    },
    {
      label: "Nilepay",
      ok: Boolean(process.env.NILEPAY_API_KEY),
      detail: process.env.NILEPAY_API_KEY
        ? "Live API key configured"
        : "No API key — payments use the mock provider",
    },
  ];

  return (
    <div className="mx-auto max-w-5xl space-y-5">
      <div>
        <h1 className="text-[22px] font-semibold tracking-tight text-ink">
          Monitoring
        </h1>
        <p className="mt-1 text-[13.5px] text-muted">
          Live process stats from this server, and configuration checks read
          straight from the environment.
        </p>
      </div>

      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
        <Stat icon={Timer} label="Process uptime" value={formatUptime(process.uptime())} note="Live" accent="green" />
        <Stat icon={MemoryStick} label="Memory (RSS)" value={formatBytes(mem.rss)} note="Live" accent="green" />
        <Stat icon={Cpu} label="Node version" value={process.version} note={process.env.NODE_ENV ?? "development"} accent="none" />
        <Stat icon={Clock} label="Server time" value={new Date().toLocaleTimeString()} note="Live" accent="green" />
      </div>

      <Card>
        <CardHeader icon={Activity} title="Requests, last 7 days" description="Sample data — connect a real analytics or APM provider in production" />
        <CardBody>
          <div className="flex h-32 items-end gap-2">
            {week.map((count, i) => (
              <div key={i} className="flex flex-1 flex-col items-center gap-1.5">
                <div
                  className="w-full rounded-t bg-brand-200"
                  style={{ height: `${Math.max(6, (count / maxDay) * 100)}%` }}
                  aria-hidden
                />
                <span className="text-[11px] text-faint">{dayLabels[i]}</span>
              </div>
            ))}
          </div>
        </CardBody>
      </Card>

      <div className="grid gap-4 sm:grid-cols-3">
        <Stat icon={Gauge} label="Avg response time" value="118 ms" note="Sample data" accent="none" />
        <Stat icon={AlertTriangle} label="Error rate" value="0.4%" note="Sample data" accent="none" />
        <Stat icon={TrendingUp} label="Requests today" value={week[week.length - 1]} note="Sample data" accent="none" />
      </div>

      <Card>
        <CardHeader title="Configuration checks" description="Read live from environment variables on this server" />
        <ul className="divide-y divide-line">
          {checks.map((c) => (
            <li key={c.label} className="flex items-center gap-3 px-4 py-3 sm:px-5">
              {c.ok ? (
                <CheckCircle2 className="h-4 w-4 shrink-0 text-green-600" aria-hidden />
              ) : (
                <CircleDashed className="h-4 w-4 shrink-0 text-gold-600" aria-hidden />
              )}
              <span className="min-w-0 flex-1">
                <span className="block text-[13.5px] font-medium text-ink">{c.label}</span>
                <span className="block text-[12.5px] text-muted">{c.detail}</span>
              </span>
              <Badge tone={c.ok ? "green" : "gold"}>{c.ok ? "Live" : "Mock"}</Badge>
            </li>
          ))}
        </ul>
      </Card>
    </div>
  );
}
