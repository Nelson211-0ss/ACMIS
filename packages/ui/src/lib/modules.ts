/**
 * The module registry.
 *
 * One definition per app, shared by the launcher, the chrome and each app's own
 * layout. Kept here rather than in each app because the launcher has to render
 * tiles for apps it is not, and duplicating the list is how the icon in the
 * launcher stops matching the icon in the app.
 *
 * `accent` matches a `[data-module]` block in `globals.css`. Fills and buttons
 * stay Senate Blue in every app; the accent appears only in chrome — the rail
 * edge, the module chip, the active nav marker — so a "Save" button never
 * changes colour as staff move between apps.
 */

export interface ModuleDefinition {
  key: string
  name: string
  /** One line, as it reads on a launcher tile. */
  description: string
  /** Dev-server port, and the path segment in production. */
  port: number
  /** lucide-react icon name, resolved by the launcher. */
  icon: string
  /** Any of these permissions makes the module visible. */
  permissions: string[]
  /** Which kinds of principal ever see it. */
  audience: Array<"staff" | "student" | "applicant" | "platform">
}

export const MODULES: readonly ModuleDefinition[] = [
  {
    key: "shell",
    name: "ACMIS",
    description: "Sign in and move between the modules you have access to.",
    port: 3000,
    icon: "LayoutGrid",
    permissions: [],
    audience: ["staff", "student", "applicant", "platform"],
  },
  {
    key: "admissions",
    name: "Admissions",
    description:
      "Admission schemes, applications, selection lists, offers and enrolment.",
    port: 3001,
    icon: "UserPlus",
    permissions: [
      "admissions:process",
      "admissions:review",
      "admissions:manage_scheme",
      "admissions:approve_selection",
    ],
    audience: ["staff"],
  },
  {
    key: "students",
    name: "Student Records",
    description:
      "The student record and its life-cycle: bio-data, enrolment, registration, holds.",
    port: 3002,
    icon: "Users",
    permissions: ["student:manage", "student:read_unit", "student:approve_status"],
    audience: ["staff"],
  },
  {
    key: "curriculum",
    name: "Curriculum",
    description:
      "Programmes, curriculum versions, courses, offerings and the timetable.",
    port: 3003,
    icon: "BookOpen",
    permissions: [
      "curriculum:author",
      "curriculum:recommend",
      "curriculum:approve",
      "timetable:manage",
    ],
    audience: ["staff"],
  },
  {
    key: "learning",
    name: "Teaching & Learning",
    description:
      "Course spaces, notes and recordings, question banks and online assessment.",
    port: 3004,
    icon: "GraduationCap",
    permissions: [
      "learning:teach",
      "learning:manage_banks",
      "learning:review_paper",
      "learning:invigilate",
    ],
    audience: ["staff"],
  },
  {
    key: "assessment",
    name: "Assessment",
    description:
      "Mark sheets, moderation, boards of examiners, results release and awards.",
    port: 3005,
    icon: "ClipboardCheck",
    permissions: [
      "results:enter",
      "results:moderate",
      "results:board_approve",
      "results:senate_approve",
      "award:prepare",
      "award:confer",
      "transcript:issue",
    ],
    audience: ["staff"],
  },
  {
    key: "finance",
    name: "Finance",
    description:
      "Fee structures, invoices, receipts, sponsorship, waivers and the student ledger.",
    port: 3006,
    icon: "Landmark",
    permissions: [
      "finance:receipt",
      "finance:post",
      "finance:approve",
      "finance:read_statement",
    ],
    audience: ["staff"],
  },
  {
    key: "people",
    name: "Faculty & Staff",
    description: "Staff records, appointments, workload, leave and development.",
    port: 3007,
    icon: "Briefcase",
    permissions: ["people:admin", "people:manage_unit", "people:approve", "people:payroll"],
    audience: ["staff"],
  },
  {
    key: "governance",
    name: "Governance & Audit",
    description:
      "The audit trail, access review, authorization policies, reporting and returns.",
    port: 3008,
    icon: "ShieldCheck",
    permissions: [
      "audit:read",
      "governance:oversight",
      "policy:admin",
      "reporting:run",
      "reporting:submit_statutory",
    ],
    audience: ["staff"],
  },
  {
    key: "developers",
    name: "Developers",
    description:
      "API clients, keys, webhooks, LTI tools, the sandbox and the API reference.",
    port: 3009,
    icon: "Terminal",
    permissions: ["developer:manage", "developer:admin", "interop:manage_tools"],
    audience: ["staff"],
  },
  {
    key: "library",
    name: "Library",
    description:
      "The catalogue, circulation, reservations, fines, acquisitions and e-resources.",
    port: 3011,
    icon: "Library",
    permissions: [
      "library:circulate",
      "library:catalogue",
      "library:acquisitions",
      "library:admin",
    ],
    audience: ["staff"],
  },
  {
    key: "quality",
    name: "Quality Assurance",
    description:
      "Teaching delivery, attendance, course evaluations, observations and audits.",
    port: 3012,
    icon: "BadgeCheck",
    permissions: ["quality:review", "quality:admin"],
    audience: ["staff"],
  },
  {
    key: "portal",
    name: "Student Portal",
    description:
      "Your record, registration, fees, results, course notes and online tests.",
    port: 3010,
    icon: "User",
    permissions: [],
    audience: ["student"],
  },
] as const

export function moduleByKey(key: string): ModuleDefinition | undefined {
  return MODULES.find((m) => m.key === key)
}

/**
 * The URL of another module app.
 *
 * In development each app is a separate dev server on its own port. In
 * production they sit behind one host at a path prefix, so the launcher's
 * links work without every app knowing the deployment topology.
 */
export function moduleUrl(key: string, baseUrl?: string): string {
  const definition = moduleByKey(key)
  if (!definition) return "/"
  if (baseUrl) return `${baseUrl.replace(/\/$/, "")}/${key}`
  if (process.env.NEXT_PUBLIC_ACMIS_ENV === "local") {
    return `http://localhost:${definition.port}`
  }
  return `/${key}`
}

/**
 * Which modules this actor should see.
 *
 * `/auth/whoami` already computes this server-side from permissions *and* the
 * tenant's plan, and that answer wins — a module the institution has not
 * bought must not appear because the user happens to hold a permission. This
 * function only orders and enriches it.
 */
export function visibleModules(
  allowed: string[],
  kind: string,
): ModuleDefinition[] {
  return MODULES.filter(
    (m) =>
      m.key !== "shell" &&
      allowed.includes(m.key) &&
      m.audience.includes(kind as ModuleDefinition["audience"][number]),
  )
}
