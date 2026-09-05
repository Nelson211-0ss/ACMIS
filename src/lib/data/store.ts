import type {
  AdmissionScheme,
  Announcement,
  Application,
  AuditEntry,
  Course,
  CourseRegistration,
  FeeItem,
  FeePayment,
  Result,
  Student,
  StaffUser,
  SystemSettings,
  TimetableSlot,
} from "../types";
import { PROGRAMMES } from "./reference";
import { gradeFor } from "../format";

/**
 * In-memory store, seeded on module load.
 *
 * This exists so the whole portal is clickable with `npm run dev` and no
 * database. It is NOT persistence: mutations live as long as the Node process,
 * and each `next dev` recompile may reset them. The repository in `repo.ts` is
 * the only thing that touches this object, so swapping in Prisma means
 * rewriting that one file. See README "Swapping in Postgres".
 */

const YEAR = "2026/2027";
const PREV_YEAR = "2025/2026";

// --- Courses ---------------------------------------------------------------
// Computer Science, years 1–2. Enough to make registration and results real.

export const COURSES: Course[] = [
  // Year 1, Semester 1
  { id: "c-csc111", code: "CSC 111", title: "Introduction to Computer Science", creditHours: 3, programmeId: "prog-csc", year: 1, semester: 1, compulsory: true, lecturer: "Dr. Peter Lado", lecturerStaffId: "staff-4", prerequisites: [] },
  { id: "c-mat111", code: "MAT 111", title: "Calculus I", creditHours: 4, programmeId: "prog-csc", year: 1, semester: 1, compulsory: true, lecturer: "Prof. Mary Aluel", prerequisites: [] },
  { id: "c-eng111", code: "ENG 111", title: "Academic Writing in English", creditHours: 2, programmeId: "prog-csc", year: 1, semester: 1, compulsory: true, lecturer: "Ms. Rebecca Ayen", prerequisites: [] },
  { id: "c-phy111", code: "PHY 111", title: "Physics for Computing", creditHours: 3, programmeId: "prog-csc", year: 1, semester: 1, compulsory: false, lecturer: "Dr. James Wani", prerequisites: [] },

  // Year 1, Semester 2
  { id: "c-csc121", code: "CSC 121", title: "Programming Fundamentals", creditHours: 4, programmeId: "prog-csc", year: 1, semester: 2, compulsory: true, lecturer: "Dr. Peter Lado", lecturerStaffId: "staff-4", prerequisites: ["c-csc111"] },
  { id: "c-mat121", code: "MAT 121", title: "Discrete Mathematics", creditHours: 3, programmeId: "prog-csc", year: 1, semester: 2, compulsory: true, lecturer: "Prof. Mary Aluel", prerequisites: ["c-mat111"] },
  { id: "c-csc122", code: "CSC 122", title: "Computer Organisation", creditHours: 3, programmeId: "prog-csc", year: 1, semester: 2, compulsory: true, lecturer: "Mr. Simon Tut", prerequisites: ["c-csc111"] },
  { id: "c-cit121", code: "CIT 121", title: "Citizenship and Ethics", creditHours: 2, programmeId: "prog-csc", year: 1, semester: 2, compulsory: true, lecturer: "Dr. Grace Nyandeng", prerequisites: [] },

  // Year 2, Semester 1 — the current registration window
  { id: "c-csc211", code: "CSC 211", title: "Data Structures and Algorithms", creditHours: 4, programmeId: "prog-csc", year: 2, semester: 1, compulsory: true, lecturer: "Dr. Peter Lado", lecturerStaffId: "staff-4", prerequisites: ["c-csc121"] },
  { id: "c-csc212", code: "CSC 212", title: "Object-Oriented Programming", creditHours: 4, programmeId: "prog-csc", year: 2, semester: 1, compulsory: true, lecturer: "Mr. Simon Tut", prerequisites: ["c-csc121"] },
  { id: "c-csc213", code: "CSC 213", title: "Database Systems", creditHours: 3, programmeId: "prog-csc", year: 2, semester: 1, compulsory: true, lecturer: "Ms. Nyakuma Bol", prerequisites: ["c-csc121"] },
  { id: "c-mat211", code: "MAT 211", title: "Linear Algebra", creditHours: 3, programmeId: "prog-csc", year: 2, semester: 1, compulsory: true, lecturer: "Prof. Mary Aluel", prerequisites: ["c-mat121"] },
  { id: "c-csc214", code: "CSC 214", title: "Web Technologies", creditHours: 3, programmeId: "prog-csc", year: 2, semester: 1, compulsory: false, lecturer: "Ms. Nyakuma Bol", prerequisites: ["c-csc121"] },
  { id: "c-sta211", code: "STA 211", title: "Probability and Statistics", creditHours: 3, programmeId: "prog-csc", year: 2, semester: 1, compulsory: false, lecturer: "Dr. Emmanuel Kur", prerequisites: ["c-mat111"] },
  { id: "c-csc215", code: "CSC 215", title: "Operating Systems", creditHours: 3, programmeId: "prog-csc", year: 2, semester: 1, compulsory: false, lecturer: "Mr. Simon Tut", prerequisites: ["c-csc122"] },
];

// --- Students --------------------------------------------------------------

export const STUDENTS: Student[] = [
  {
    id: "stu-1",
    studentNumber: "UOJ/SCI/2024/0142",
    firstName: "Achol",
    lastName: "Majok",
    email: "achol.majok@student.example.ss",
    phone: "+211920114477",
    // photoUrl: "/students/stu-1.jpg",  ← drop a file in public/students to use it
    programmeId: "prog-csc",
    yearOfStudy: 2,
    currentSemester: 1,
    status: "active",
    admittedYear: "2024/2025",
    advisorName: "Dr. Peter Lado",
  },
];

// --- Prior results (year 1, both semesters, published) ---------------------

function seedResult(
  courseId: string,
  academicYear: string,
  semester: 1 | 2,
  coursework: number,
  exam: number,
): Result {
  const total = coursework + exam;
  const { grade, points } = gradeFor(total);
  return {
    studentId: "stu-1",
    courseId,
    academicYear,
    semester,
    coursework,
    exam,
    total,
    grade,
    points,
    published: true,
  };
}

export const RESULTS: Result[] = [
  seedResult("c-csc111", PREV_YEAR, 1, 34, 48),
  seedResult("c-mat111", PREV_YEAR, 1, 30, 41),
  seedResult("c-eng111", PREV_YEAR, 1, 32, 45),
  seedResult("c-phy111", PREV_YEAR, 1, 26, 38),
  seedResult("c-csc121", PREV_YEAR, 2, 36, 51),
  seedResult("c-mat121", PREV_YEAR, 2, 29, 44),
  seedResult("c-csc122", PREV_YEAR, 2, 31, 40),
  seedResult("c-cit121", PREV_YEAR, 2, 35, 47),
];

// --- Current registration (compulsory courses pre-registered) -------------

export const REGISTRATIONS: CourseRegistration[] = [
  "c-csc211",
  "c-csc212",
  "c-csc213",
  "c-mat211",
].map((courseId) => ({
  studentId: "stu-1",
  courseId,
  academicYear: YEAR,
  semester: 1 as const,
  registeredAt: "2026-09-28T08:14:00.000Z",
}));

// --- Fees ------------------------------------------------------------------

export const FEE_ITEMS: FeeItem[] = [
  { id: "fee-1", studentId: "stu-1", academicYear: YEAR, semester: 1, description: "Tuition — Semester 1", amountSSP: 260_000, dueDate: "2026-10-15", blocking: true },
  { id: "fee-2", studentId: "stu-1", academicYear: YEAR, semester: 1, description: "Registration and examination", amountSSP: 35_000, dueDate: "2026-10-05", blocking: true },
  { id: "fee-3", studentId: "stu-1", academicYear: YEAR, semester: 1, description: "Library and computer laboratory", amountSSP: 18_000, dueDate: "2026-10-15", blocking: false },
  { id: "fee-4", studentId: "stu-1", academicYear: YEAR, semester: 1, description: "Students' union subscription", amountSSP: 5_000, dueDate: "2026-11-01", blocking: false },
];

// Seeded so the blocking charges (tuition + examination = 295,000) are exactly
// cleared. That leaves registration open and results visible — the ordinary
// state — while the non-blocking library and union fees stay outstanding so the
// Finance page still has a live balance to pay against.
export const FEE_PAYMENTS: FeePayment[] = [
  { id: "pay-1", studentId: "stu-1", amountSSP: 160_000, method: "mgurush", reference: "MG7K4Q281D", paidAt: "2026-09-22T10:31:00.000Z", status: "confirmed" },
  { id: "pay-2", studentId: "stu-1", amountSSP: 100_000, method: "mgurush", reference: "MG9B2X0473", paidAt: "2026-09-26T08:15:00.000Z", status: "confirmed" },
  { id: "pay-3", studentId: "stu-1", amountSSP: 35_000, method: "bank_slip", reference: "IVB-0092447", paidAt: "2026-09-30T14:02:00.000Z", status: "confirmed" },
];

// --- Timetable -------------------------------------------------------------

export const TIMETABLE: TimetableSlot[] = [
  { id: "t-1", courseId: "c-csc211", day: "Mon", startsAt: "08:00", endsAt: "10:00", venue: "Lecture Hall B2", kind: "lecture" },
  { id: "t-2", courseId: "c-mat211", day: "Mon", startsAt: "10:30", endsAt: "12:00", venue: "Lecture Hall A1", kind: "lecture" },
  { id: "t-3", courseId: "c-csc212", day: "Tue", startsAt: "08:00", endsAt: "10:00", venue: "Lecture Hall B2", kind: "lecture" },
  { id: "t-4", courseId: "c-csc213", day: "Tue", startsAt: "14:00", endsAt: "16:00", venue: "Computer Lab 1", kind: "lab" },
  { id: "t-5", courseId: "c-csc211", day: "Wed", startsAt: "10:30", endsAt: "12:00", venue: "Computer Lab 2", kind: "tutorial" },
  { id: "t-6", courseId: "c-mat211", day: "Thu", startsAt: "08:00", endsAt: "09:30", venue: "Lecture Hall A1", kind: "tutorial" },
  { id: "t-7", courseId: "c-csc213", day: "Thu", startsAt: "11:00", endsAt: "13:00", venue: "Lecture Hall C3", kind: "lecture" },
  { id: "t-8", courseId: "c-csc212", day: "Fri", startsAt: "09:00", endsAt: "11:00", venue: "Computer Lab 1", kind: "lab" },
];

// --- Announcements ---------------------------------------------------------

export const ANNOUNCEMENTS: Announcement[] = [
  {
    id: "ann-1",
    title: "Semester 1 registration closes 10 October",
    body: "All continuing students must complete course registration before 10 October 2026. Registration will not be reopened for late submissions without a written waiver from the Dean.",
    postedAt: "2026-09-25T07:00:00.000Z",
    audience: "students",
    priority: "important",
  },
  {
    id: "ann-2",
    title: "Tuition may now be paid by m-GURUSH",
    body: "Fees can be paid directly from the Finance page using m-GURUSH or Nilepay. Bank deposit slips are still accepted and are cleared within two working days.",
    postedAt: "2026-09-18T09:30:00.000Z",
    audience: "all",
    priority: "normal",
  },
  {
    id: "ann-3",
    title: "2026/2027 admission results published 20 September",
    body: "Applicants will be notified by SMS and can check the decision on their application status page. Do not pay any fee to a person promising admission.",
    postedAt: "2026-09-10T12:00:00.000Z",
    audience: "applicants",
    priority: "important",
  },
];

// --- Applications ----------------------------------------------------------

export const APPLICATIONS: Application[] = [
  {
    id: "app-1",
    reference: "APP-2026-004821",
    applicantId: "usr-applicant",
    schemeId: "scheme-2026",
    status: "under_review",
    createdAt: "2026-07-04T08:20:00.000Z",
    updatedAt: "2026-07-11T16:45:00.000Z",
    submittedAt: "2026-07-11T16:45:00.000Z",
    personal: {
      firstName: "Emmanuel",
      middleName: "Ladu",
      lastName: "Wani",
      dateOfBirth: "2007-03-14",
      sex: "male",
      nationality: "South Sudanese",
      stateOfOrigin: "Central Equatoria",
      county: "Juba",
      phone: "+211921556677",
      email: "emmanuel.wani@example.ss",
      nationalId: "SSD-2007-3348271",
      guardianName: "Josephine Ladu",
      guardianPhone: "+211920334455",
    },
    education: {
      secondarySchool: "Juba Day Secondary School",
      schoolState: "Central Equatoria",
      indexNumber: "CE/0231/2025/0117",
      yearCompleted: "2025",
      subjects: [
        { subject: "English", mark: 74 },
        { subject: "Mathematics", mark: 81 },
        { subject: "Physics", mark: 77 },
        { subject: "Chemistry", mark: 69 },
        { subject: "Biology", mark: 66 },
        { subject: "Geography", mark: 72 },
        { subject: "Computer Studies", mark: 85 },
        { subject: "Citizenship", mark: 70 },
      ],
    },
    choices: [
      { rank: 1, programmeId: "prog-csc" },
      { rank: 2, programmeId: "prog-eee" },
      { rank: 3, programmeId: "prog-sta" },
    ],
    documents: [
      { id: "doc-1", kind: "sscse_certificate", fileName: "sscse-certificate.pdf", sizeBytes: 412_003, uploadedAt: "2026-07-08T10:12:00.000Z", status: "verified" },
      { id: "doc-2", kind: "sscse_transcript", fileName: "sscse-marksheet.pdf", sizeBytes: 288_440, uploadedAt: "2026-07-08T10:14:00.000Z", status: "verified" },
      { id: "doc-3", kind: "passport_photo", fileName: "photo.jpg", sizeBytes: 96_210, uploadedAt: "2026-07-08T10:15:00.000Z", status: "verified" },
      { id: "doc-4", kind: "national_id", fileName: "national-id.jpg", sizeBytes: 154_882, uploadedAt: "2026-07-09T07:40:00.000Z", status: "pending" },
    ],
    payment: {
      id: "appay-1",
      method: "mgurush",
      amountSSP: 15_000,
      status: "confirmed",
      reference: "MG3P8N1147",
      phone: "+211921556677",
      createdAt: "2026-07-11T16:30:00.000Z",
      confirmedAt: "2026-07-11T16:33:00.000Z",
    },
  },
];

// --- Admission schemes ------------------------------------------------------

const ALL_PROGRAMME_IDS = PROGRAMMES.map((p) => p.id);

export const ADMISSION_SCHEMES: AdmissionScheme[] = [
  {
    id: "scheme-2025",
    name: "2025/2026 Undergraduate Intake",
    code: "UG-2025",
    description: "The previous undergraduate admission cycle, now closed.",
    programmeIds: ALL_PROGRAMME_IDS,
    opensAt: "2025-06-01",
    closesAt: "2025-08-31",
    resultsBy: "2025-09-20",
    semesterStarts: "2025-10-05",
    applicationFeeSSP: 15_000,
    status: "closed",
    createdAt: "2025-05-01T08:00:00.000Z",
  },
  {
    id: "scheme-2026",
    name: "2026/2027 Undergraduate Intake",
    code: "UG-2026",
    description: "Full-time Bachelor's programmes across all seven faculties.",
    programmeIds: ALL_PROGRAMME_IDS,
    opensAt: "2026-08-01",
    closesAt: "2026-12-15",
    resultsBy: "2027-01-10",
    semesterStarts: "2027-01-20",
    applicationFeeSSP: 15_000,
    status: "open",
    createdAt: "2026-07-20T09:00:00.000Z",
  },
  {
    id: "scheme-diploma-2027",
    name: "January 2027 Diploma Bridging Intake",
    code: "DIP-2027J",
    description: "A shorter diploma route into Computer Science or Economics, for candidates just below the Bachelor's cut-off.",
    programmeIds: ["prog-csc", "prog-eco"],
    opensAt: "2027-01-05",
    closesAt: "2027-01-25",
    resultsBy: "2027-02-05",
    semesterStarts: "2027-02-15",
    applicationFeeSSP: 8_000,
    status: "draft",
    createdAt: "2026-09-01T10:00:00.000Z",
  },
];

/** Monotonic counter behind generated application references. */
let referenceCounter = 4821;
export function nextReference(): string {
  referenceCounter += 1;
  return `APP-2026-${String(referenceCounter).padStart(6, "0")}`;
}

let idCounter = 1000;
export function nextId(prefix: string): string {
  idCounter += 1;
  return `${prefix}-${idCounter}`;
}

export const CURRENT_YEAR = YEAR;
export const PREVIOUS_YEAR = PREV_YEAR;

// --- Staff, roles and system administration ---------------------------------

export const STAFF_USERS: StaffUser[] = [
  {
    id: "staff-1",
    name: "Grace Lueth",
    email: "grace.lueth@uoj.example.ss",
    staffRole: "super_admin",
    status: "active",
    lastActiveAt: "2026-09-04T08:10:00.000Z",
  },
  {
    id: "staff-2",
    name: "Daniel Kuek",
    email: "daniel.kuek@uoj.example.ss",
    staffRole: "registrar",
    status: "active",
    lastActiveAt: "2026-09-03T14:22:00.000Z",
  },
  {
    id: "staff-3",
    name: "Aluel Deng",
    email: "aluel.deng@uoj.example.ss",
    staffRole: "bursar",
    status: "active",
    lastActiveAt: "2026-09-02T09:05:00.000Z",
  },
  {
    id: "staff-4",
    // The same Dr. Peter Lado already seeded as the student's academic
    // advisor and as the named lecturer on his three courses below — one
    // person, one record, instead of a second unrelated "Lado" appearing.
    name: "Dr. Peter Lado",
    email: "peter.lado@uoj.example.ss",
    staffRole: "lecturer",
    status: "active",
    lastActiveAt: "2026-09-04T11:30:00.000Z",
  },
];

/**
 * Single mutable settings object rather than one row per key. A real
 * deployment would still keep this shape — it is one document a super admin
 * edits as a whole, not a scatter of independent flags — and would persist it
 * the same way a Prisma `SystemSettings` singleton row would.
 */
export const SYSTEM_SETTINGS: SystemSettings = {
  maintenanceMode: false,
  registrationOpen: true,
  applicationsOpen: true,
  appearance: {
    defaultMode: "system",
    accent: "nile",
  },
  rolePermissions: {
    super_admin: [
      "manage_users",
      "manage_roles",
      "manage_settings",
      "manage_appearance",
      "manage_announcements",
      "manage_admissions",
      "manage_results",
      "view_monitoring",
      "view_audit_log",
    ],
    // The registrar's office runs admissions in real life, so it's the
    // default here too.
    registrar: ["manage_users", "manage_announcements", "manage_admissions", "view_audit_log"],
    bursar: ["view_monitoring", "view_audit_log"],
    // A lecturer's only business here is entering marks for their own courses.
    lecturer: ["manage_results"],
    viewer: ["view_monitoring"],
  },
};

export const AUDIT_LOG: AuditEntry[] = [
  {
    id: "aud-1",
    at: "2026-09-01T07:55:00.000Z",
    actor: "Grace Lueth",
    action: "Signed in",
  },
  {
    id: "aud-2",
    at: "2026-08-20T11:12:00.000Z",
    actor: "Grace Lueth",
    action: "Published 2026/2027 admission decisions",
  },
  {
    id: "aud-3",
    at: "2026-08-15T09:40:00.000Z",
    actor: "Daniel Kuek",
    action: "Marked registration open for Semester 1",
  },
];
