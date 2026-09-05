import type {
  AdmissionScheme,
  Announcement,
  Application,
  ApplicationStatus,
  AuditEntry,
  Course,
  DirectoryUser,
  FeeItem,
  FeePayment,
  Payment,
  Result,
  SchemeStatus,
  StaffRole,
  StaffUser,
  Student,
  SystemSettings,
  TimetableSlot,
  UploadedDocument,
} from "../types";
import { gpa, gradeFor } from "../format";
import {
  ADMISSION_SCHEMES,
  ANNOUNCEMENTS,
  APPLICATIONS,
  AUDIT_LOG,
  COURSES,
  CURRENT_YEAR,
  FEE_ITEMS,
  FEE_PAYMENTS,
  REGISTRATIONS,
  RESULTS,
  STAFF_USERS,
  STUDENTS,
  SYSTEM_SETTINGS,
  TIMETABLE,
  nextId,
  nextReference,
} from "./store";

/** The academic year in progress — re-exported so callers needn't reach past this seam into ./store. */
export { CURRENT_YEAR } from "./store";

/**
 * The one seam between the UI and storage.
 *
 * Every function is async and returns plain domain types, so replacing the
 * bodies with Prisma queries requires no change above this file. Nothing else
 * in the app imports `./store`.
 */

// --- Students --------------------------------------------------------------

export async function getStudent(id: string): Promise<Student | null> {
  return STUDENTS.find((s) => s.id === id) ?? null;
}

export async function getStudentByEmail(email: string): Promise<Student | null> {
  const target = email.trim().toLowerCase();
  return STUDENTS.find((s) => s.email.toLowerCase() === target) ?? null;
}

// --- Courses and registration ---------------------------------------------

export async function getCourse(id: string): Promise<Course | null> {
  return COURSES.find((c) => c.id === id) ?? null;
}

/** Course codes for a list of ids, for messages like "requires CSC 121". */
export async function getCourseCodes(ids: string[]): Promise<string[]> {
  return ids.map((id) => COURSES.find((c) => c.id === id)?.code ?? id);
}

/** Courses on offer for a student's current year and semester. */
export async function getAvailableCourses(student: Student): Promise<Course[]> {
  return COURSES.filter(
    (c) =>
      c.programmeId === student.programmeId &&
      c.year === student.yearOfStudy &&
      c.semester === student.currentSemester,
  );
}

export async function getRegisteredCourseIds(
  studentId: string,
  academicYear = CURRENT_YEAR,
): Promise<string[]> {
  return REGISTRATIONS.filter(
    (r) => r.studentId === studentId && r.academicYear === academicYear,
  ).map((r) => r.courseId);
}

/** Course ids the student has passed, used to check prerequisites. */
export async function getPassedCourseIds(studentId: string): Promise<string[]> {
  return RESULTS.filter(
    (r) => r.studentId === studentId && r.published && r.grade !== "F" && r.grade !== "E",
  ).map((r) => r.courseId);
}

/**
 * Replace a student's registration for the current semester.
 *
 * Compulsory courses are forced in regardless of what was submitted, and
 * anything whose prerequisites are unmet is rejected rather than silently
 * dropped — the caller surfaces the reasons.
 */
export async function setRegistration(
  student: Student,
  courseIds: string[],
): Promise<{ registered: string[]; rejected: Array<{ courseId: string; reason: string }> }> {
  const available = await getAvailableCourses(student);
  const passed = new Set(await getPassedCourseIds(student.id));

  const compulsory = available.filter((c) => c.compulsory).map((c) => c.id);
  const wanted = new Set([...courseIds, ...compulsory]);

  const registered: string[] = [];
  const rejected: Array<{ courseId: string; reason: string }> = [];

  for (const course of available) {
    if (!wanted.has(course.id)) continue;
    const missing = course.prerequisites.filter((p) => !passed.has(p));
    if (missing.length > 0) {
      const names = missing
        .map((id) => COURSES.find((c) => c.id === id)?.code ?? id)
        .join(", ");
      rejected.push({ courseId: course.id, reason: `Requires a pass in ${names}` });
      continue;
    }
    registered.push(course.id);
  }

  // Swap in the new set for this year/semester only.
  for (let i = REGISTRATIONS.length - 1; i >= 0; i--) {
    const r = REGISTRATIONS[i];
    if (
      r.studentId === student.id &&
      r.academicYear === CURRENT_YEAR &&
      r.semester === student.currentSemester
    ) {
      REGISTRATIONS.splice(i, 1);
    }
  }
  const now = new Date().toISOString();
  for (const courseId of registered) {
    REGISTRATIONS.push({
      studentId: student.id,
      courseId,
      academicYear: CURRENT_YEAR,
      semester: student.currentSemester,
      registeredAt: now,
    });
  }

  return { registered, rejected };
}

// --- Results ---------------------------------------------------------------

export interface ResultRow extends Result {
  course: Course;
}

export interface SemesterResults {
  academicYear: string;
  semester: 1 | 2;
  rows: ResultRow[];
  gpa: number | null;
  creditHours: number;
}

/** Published results grouped by semester, newest first. */
export async function getResultsBySemester(
  studentId: string,
): Promise<SemesterResults[]> {
  const rows: ResultRow[] = RESULTS.filter(
    (r) => r.studentId === studentId && r.published,
  )
    .map((r) => {
      const course = COURSES.find((c) => c.id === r.courseId);
      return course ? { ...r, course } : null;
    })
    .filter((r): r is ResultRow => r !== null);

  const groups = new Map<string, ResultRow[]>();
  for (const row of rows) {
    const key = `${row.academicYear}|${row.semester}`;
    const bucket = groups.get(key);
    if (bucket) bucket.push(row);
    else groups.set(key, [row]);
  }

  return [...groups.entries()]
    .map(([key, groupRows]) => {
      const [academicYear, semester] = key.split("|");
      return {
        academicYear,
        semester: Number(semester) as 1 | 2,
        rows: groupRows,
        gpa: gpa(
          groupRows.map((r) => ({ points: r.points, creditHours: r.course.creditHours })),
        ),
        creditHours: groupRows.reduce((sum, r) => sum + r.course.creditHours, 0),
      };
    })
    .sort((a, b) =>
      a.academicYear === b.academicYear
        ? b.semester - a.semester
        : b.academicYear.localeCompare(a.academicYear),
    );
}

/** Cumulative GPA across every published result. */
export async function getCgpa(studentId: string): Promise<number | null> {
  const semesters = await getResultsBySemester(studentId);
  return gpa(
    semesters.flatMap((s) =>
      s.rows.map((r) => ({ points: r.points, creditHours: r.course.creditHours })),
    ),
  );
}

// --- Teaching (lecturer) -----------------------------------------------------

export async function getCoursesForLecturer(staffId: string): Promise<Course[]> {
  return COURSES.filter((c) => c.lecturerStaffId === staffId);
}

export interface RosterRow {
  student: Student;
  result: Result | null;
}

/**
 * Students currently registered in one course, each paired with their result
 * for that offering if marks have been entered yet (published or not).
 */
export async function getCourseRoster(
  courseId: string,
  academicYear = CURRENT_YEAR,
): Promise<RosterRow[]> {
  const course = COURSES.find((c) => c.id === courseId);
  const semester = course?.semester ?? 1;

  return REGISTRATIONS.filter(
    (r) => r.courseId === courseId && r.academicYear === academicYear,
  )
    .map((r) => STUDENTS.find((s) => s.id === r.studentId))
    .filter((s): s is Student => s !== undefined)
    .map((student) => ({
      student,
      result:
        RESULTS.find(
          (r) =>
            r.studentId === student.id &&
            r.courseId === courseId &&
            r.academicYear === academicYear &&
            r.semester === semester,
        ) ?? null,
    }));
}

/**
 * Create or update one student's marks for a course offering.
 *
 * Editing an already-published result keeps it published — a correction
 * shouldn't have to go through "publish" again. Only a brand new entry starts
 * as an unpublished draft, invisible to the student until the lecturer
 * publishes the class.
 */
export async function upsertResult(input: {
  studentId: string;
  courseId: string;
  academicYear: string;
  semester: 1 | 2;
  coursework: number;
  exam: number;
}): Promise<Result> {
  const total = input.coursework + input.exam;
  const { grade, points } = gradeFor(total);
  const existing = RESULTS.find(
    (r) =>
      r.studentId === input.studentId &&
      r.courseId === input.courseId &&
      r.academicYear === input.academicYear &&
      r.semester === input.semester,
  );
  if (existing) {
    existing.coursework = input.coursework;
    existing.exam = input.exam;
    existing.total = total;
    existing.grade = grade;
    existing.points = points;
    return existing;
  }
  const created: Result = { ...input, total, grade, points, published: false };
  RESULTS.push(created);
  return created;
}

/** Publish or withdraw every entered result for one course offering at once. */
export async function setCourseResultsPublished(
  courseId: string,
  academicYear: string,
  semester: 1 | 2,
  published: boolean,
): Promise<number> {
  let count = 0;
  for (const r of RESULTS) {
    if (r.courseId === courseId && r.academicYear === academicYear && r.semester === semester) {
      r.published = published;
      count += 1;
    }
  }
  return count;
}

// --- Fees ------------------------------------------------------------------

export interface FeeSummary {
  items: FeeItem[];
  payments: FeePayment[];
  charged: number;
  paid: number;
  balance: number;
  /** Blocking balance withholds results and registration. */
  blockingBalance: number;
  nextDue: FeeItem | null;
}

export async function getFeeSummary(studentId: string): Promise<FeeSummary> {
  const items = FEE_ITEMS.filter(
    (f) => f.studentId === studentId && f.academicYear === CURRENT_YEAR,
  );
  const payments = FEE_PAYMENTS.filter(
    (p) => p.studentId === studentId && p.status === "confirmed",
  ).sort((a, b) => b.paidAt.localeCompare(a.paidAt));

  const charged = items.reduce((sum, f) => sum + f.amountSSP, 0);
  const paid = payments.reduce((sum, p) => sum + p.amountSSP, 0);
  const balance = Math.max(0, charged - paid);

  // Payments are applied to blocking charges first — that is how the bursary
  // actually allocates them, and it decides whether results stay withheld.
  const blockingCharged = items
    .filter((f) => f.blocking)
    .reduce((sum, f) => sum + f.amountSSP, 0);
  const blockingBalance = Math.max(0, blockingCharged - paid);

  const nextDue =
    items
      .filter((f) => f.blocking)
      .sort((a, b) => a.dueDate.localeCompare(b.dueDate))[0] ?? null;

  return { items, payments, charged, paid, balance, blockingBalance, nextDue };
}

export async function recordFeePayment(
  studentId: string,
  amountSSP: number,
  method: FeePayment["method"],
  reference: string,
): Promise<FeePayment> {
  const payment: FeePayment = {
    id: nextId("pay"),
    studentId,
    amountSSP,
    method,
    reference,
    paidAt: new Date().toISOString(),
    // Mobile money confirms in seconds; a bank slip needs a human to clear it.
    status: method === "bank_slip" ? "pending" : "confirmed",
  };
  FEE_PAYMENTS.push(payment);
  return payment;
}

// --- Timetable -------------------------------------------------------------

export interface TimetableRow extends TimetableSlot {
  course: Course;
}

export async function getTimetable(studentId: string): Promise<TimetableRow[]> {
  const registered = new Set(await getRegisteredCourseIds(studentId));
  return TIMETABLE.filter((slot) => registered.has(slot.courseId))
    .map((slot) => {
      const course = COURSES.find((c) => c.id === slot.courseId);
      return course ? { ...slot, course } : null;
    })
    .filter((r): r is TimetableRow => r !== null)
    .sort((a, b) => a.startsAt.localeCompare(b.startsAt));
}

// --- Announcements ---------------------------------------------------------

export async function getAnnouncements(
  audience: "applicants" | "students",
): Promise<Announcement[]> {
  return ANNOUNCEMENTS.filter(
    (a) => a.audience === "all" || a.audience === audience,
  ).sort((a, b) => b.postedAt.localeCompare(a.postedAt));
}

/** Every announcement, newest first — the admin view, unfiltered by audience. */
export async function listAnnouncements(): Promise<Announcement[]> {
  return [...ANNOUNCEMENTS].sort((a, b) => b.postedAt.localeCompare(a.postedAt));
}

export async function createAnnouncement(
  input: Pick<Announcement, "title" | "body" | "audience" | "priority">,
): Promise<Announcement> {
  const announcement: Announcement = {
    id: nextId("ann"),
    postedAt: new Date().toISOString(),
    ...input,
  };
  ANNOUNCEMENTS.unshift(announcement);
  return announcement;
}

export async function deleteAnnouncement(id: string): Promise<void> {
  const index = ANNOUNCEMENTS.findIndex((a) => a.id === id);
  if (index !== -1) ANNOUNCEMENTS.splice(index, 1);
}

// --- Applications ----------------------------------------------------------

export async function getApplication(id: string): Promise<Application | null> {
  return APPLICATIONS.find((a) => a.id === id) ?? null;
}

export async function getApplicationsFor(applicantId: string): Promise<Application[]> {
  return APPLICATIONS.filter((a) => a.applicantId === applicantId).sort((a, b) =>
    b.updatedAt.localeCompare(a.updatedAt),
  );
}

export async function createApplication(
  applicantId: string,
  schemeId?: string,
): Promise<Application> {
  const now = new Date().toISOString();
  const application: Application = {
    id: nextId("app"),
    reference: nextReference(),
    applicantId,
    schemeId,
    status: "draft",
    createdAt: now,
    updatedAt: now,
    personal: {
      firstName: "",
      lastName: "",
      dateOfBirth: "",
      sex: "",
      nationality: "South Sudanese",
      stateOfOrigin: "",
      county: "",
      phone: "",
      email: "",
      guardianName: "",
      guardianPhone: "",
    },
    education: {
      secondarySchool: "",
      schoolState: "",
      indexNumber: "",
      yearCompleted: "",
      subjects: [],
    },
    choices: [],
    documents: [],
  };
  APPLICATIONS.push(application);
  return application;
}

export async function updateApplication(
  id: string,
  patch: Partial<Omit<Application, "id" | "applicantId" | "reference">>,
): Promise<Application | null> {
  const index = APPLICATIONS.findIndex((a) => a.id === id);
  if (index === -1) return null;
  const updated: Application = {
    ...APPLICATIONS[index],
    ...patch,
    updatedAt: new Date().toISOString(),
  };
  APPLICATIONS[index] = updated;
  return updated;
}

export async function addDocument(
  applicationId: string,
  doc: Omit<UploadedDocument, "id" | "uploadedAt" | "status">,
): Promise<UploadedDocument | null> {
  const application = APPLICATIONS.find((a) => a.id === applicationId);
  if (!application) return null;
  const uploaded: UploadedDocument = {
    ...doc,
    id: nextId("doc"),
    uploadedAt: new Date().toISOString(),
    status: "pending",
  };
  // One file per document kind — re-uploading replaces the previous copy.
  application.documents = [
    ...application.documents.filter((d) => d.kind !== doc.kind),
    uploaded,
  ];
  application.updatedAt = uploaded.uploadedAt;
  return uploaded;
}

export async function removeDocument(
  applicationId: string,
  documentId: string,
): Promise<boolean> {
  const application = APPLICATIONS.find((a) => a.id === applicationId);
  if (!application) return false;
  const before = application.documents.length;
  application.documents = application.documents.filter((d) => d.id !== documentId);
  application.updatedAt = new Date().toISOString();
  return application.documents.length < before;
}

export async function attachPayment(
  applicationId: string,
  payment: Payment,
): Promise<Application | null> {
  const application = APPLICATIONS.find((a) => a.id === applicationId);
  if (!application) return null;
  application.payment = payment;
  application.updatedAt = new Date().toISOString();
  return application;
}

export async function setApplicationStatus(
  applicationId: string,
  status: ApplicationStatus,
): Promise<Application | null> {
  const application = APPLICATIONS.find((a) => a.id === applicationId);
  if (!application) return null;
  application.status = status;
  application.updatedAt = new Date().toISOString();
  if (status === "submitted") application.submittedAt = application.updatedAt;
  return application;
}

// --- Admin overview ---------------------------------------------------------

export interface AdminOverview {
  totalStudents: number;
  totalApplicants: number;
  pendingApplications: number;
  outstandingFeesSSP: number;
}

export async function getAdminOverview(): Promise<AdminOverview> {
  const applicantIds = new Set(APPLICATIONS.map((a) => a.applicantId));
  const pendingApplications = APPLICATIONS.filter((a) =>
    ["submitted", "under_review", "interview"].includes(a.status),
  ).length;

  const charged = FEE_ITEMS.filter((f) => f.academicYear === CURRENT_YEAR).reduce(
    (sum, f) => sum + f.amountSSP,
    0,
  );
  const paid = FEE_PAYMENTS.filter((p) => p.status === "confirmed").reduce(
    (sum, p) => sum + p.amountSSP,
    0,
  );

  return {
    totalStudents: STUDENTS.length,
    totalApplicants: applicantIds.size,
    pendingApplications,
    outstandingFeesSSP: Math.max(0, charged - paid),
  };
}

// --- Staff --------------------------------------------------------------

export async function getStaff(id: string): Promise<StaffUser | null> {
  return STAFF_USERS.find((s) => s.id === id) ?? null;
}

export async function getStaffByEmail(email: string): Promise<StaffUser | null> {
  const target = email.trim().toLowerCase();
  return STAFF_USERS.find((s) => s.email.toLowerCase() === target) ?? null;
}

export async function listStaff(): Promise<StaffUser[]> {
  return STAFF_USERS;
}

export async function setStaffRole(id: string, staffRole: StaffRole): Promise<StaffUser | null> {
  const staff = STAFF_USERS.find((s) => s.id === id);
  if (!staff) return null;
  staff.staffRole = staffRole;
  return staff;
}

export async function setStaffStatus(
  id: string,
  status: StaffUser["status"],
): Promise<StaffUser | null> {
  const staff = STAFF_USERS.find((s) => s.id === id);
  if (!staff) return null;
  staff.status = status;
  return staff;
}

export async function setStudentStatus(
  id: string,
  status: Student["status"],
): Promise<Student | null> {
  const student = STUDENTS.find((s) => s.id === id);
  if (!student) return null;
  student.status = status;
  return student;
}

/**
 * Everyone the university has a record of, in one list: students, staff, and
 * applicants (derived from applications, since there is no separate
 * applicant table — see the Users page for why applicant rows are read-only).
 */
export async function listAllUsers(): Promise<DirectoryUser[]> {
  const students: DirectoryUser[] = STUDENTS.map((s) => ({
    id: s.id,
    name: `${s.firstName} ${s.lastName}`,
    email: s.email,
    kind: "student",
    roleLabel: s.studentNumber,
    statusLabel: s.status,
    statusTone: s.status === "active" ? "green" : s.status === "graduated" ? "neutral" : "gold",
    mutable: true,
  }));

  const staff: DirectoryUser[] = STAFF_USERS.map((s) => ({
    id: s.id,
    name: s.name,
    email: s.email,
    kind: "staff",
    roleLabel: s.staffRole,
    statusLabel: s.status,
    statusTone: s.status === "active" ? "green" : "red",
    mutable: true,
  }));

  const seenApplicants = new Set<string>();
  const applicants: DirectoryUser[] = [];
  for (const app of APPLICATIONS) {
    if (seenApplicants.has(app.applicantId)) continue;
    seenApplicants.add(app.applicantId);
    applicants.push({
      id: app.applicantId,
      name: `${app.personal.firstName} ${app.personal.lastName}`,
      email: app.personal.email,
      kind: "applicant",
      roleLabel: "Applicant",
      statusLabel: app.status.replace("_", " "),
      statusTone:
        app.status === "admitted"
          ? "green"
          : app.status === "rejected"
            ? "red"
            : app.status === "waitlisted" || app.status === "interview"
              ? "gold"
              : "neutral",
      // No account-status field exists for applicants (only their application
      // has a status), so there is nothing here for the admin to mutate yet.
      mutable: false,
    });
  }

  return [...staff, ...students, ...applicants];
}

// --- System settings ------------------------------------------------------

export async function getSystemSettings(): Promise<SystemSettings> {
  return SYSTEM_SETTINGS;
}

export async function updateSystemSettings(
  patch: Partial<Omit<SystemSettings, "appearance" | "rolePermissions">> & {
    appearance?: Partial<SystemSettings["appearance"]>;
    rolePermissions?: SystemSettings["rolePermissions"];
  },
): Promise<SystemSettings> {
  Object.assign(SYSTEM_SETTINGS, {
    ...patch,
    appearance: { ...SYSTEM_SETTINGS.appearance, ...patch.appearance },
    rolePermissions: patch.rolePermissions ?? SYSTEM_SETTINGS.rolePermissions,
  });
  return SYSTEM_SETTINGS;
}

// --- Audit log --------------------------------------------------------------

export async function getAuditLog(): Promise<AuditEntry[]> {
  // Sorted by timestamp rather than reversing insertion order: the seed data
  // above isn't in chronological order, so a plain reverse would put it out
  // of sequence relative to entries logged later.
  return [...AUDIT_LOG].sort((a, b) => b.at.localeCompare(a.at));
}

export async function logAudit(
  actor: string,
  action: string,
  target?: string,
): Promise<void> {
  AUDIT_LOG.push({
    id: nextId("aud"),
    at: new Date().toISOString(),
    actor,
    action,
    target,
  });
}

// --- Admission schemes ------------------------------------------------------

export async function listSchemes(): Promise<AdmissionScheme[]> {
  return [...ADMISSION_SCHEMES].sort((a, b) => b.createdAt.localeCompare(a.createdAt));
}

export async function getScheme(id: string): Promise<AdmissionScheme | null> {
  return ADMISSION_SCHEMES.find((s) => s.id === id) ?? null;
}

/** What an applicant sees on the Apply page: published, and not past its own closing date. */
export async function listOpenSchemes(): Promise<AdmissionScheme[]> {
  const now = Date.now();
  return ADMISSION_SCHEMES.filter(
    (s) => s.status === "open" && new Date(s.closesAt).getTime() >= now,
  ).sort((a, b) => a.closesAt.localeCompare(b.closesAt));
}

export async function createScheme(
  input: Omit<AdmissionScheme, "id" | "createdAt" | "status">,
): Promise<AdmissionScheme> {
  const scheme: AdmissionScheme = {
    ...input,
    id: nextId("scheme"),
    status: "draft",
    createdAt: new Date().toISOString(),
  };
  ADMISSION_SCHEMES.push(scheme);
  return scheme;
}

export async function setSchemeStatus(
  id: string,
  status: SchemeStatus,
): Promise<AdmissionScheme | null> {
  const scheme = ADMISSION_SCHEMES.find((s) => s.id === id);
  if (!scheme) return null;
  scheme.status = status;
  return scheme;
}

// --- Admissions review -------------------------------------------------------

/** Everything the admissions office has to act on — drafts are the applicant's own business until submitted. */
export async function listApplicationsForReview(): Promise<Application[]> {
  return [...APPLICATIONS]
    .filter((a) => a.status !== "draft")
    .sort((a, b) => (b.submittedAt ?? "").localeCompare(a.submittedAt ?? ""));
}

export async function setDocumentStatus(
  applicationId: string,
  documentId: string,
  status: UploadedDocument["status"],
): Promise<Application | null> {
  const application = APPLICATIONS.find((a) => a.id === applicationId);
  if (!application) return null;
  const doc = application.documents.find((d) => d.id === documentId);
  if (!doc) return null;
  doc.status = status;
  return application;
}

export async function recordDecision(
  applicationId: string,
  status: ApplicationStatus,
  message: string,
  programmeId?: string,
): Promise<Application | null> {
  const application = APPLICATIONS.find((a) => a.id === applicationId);
  if (!application) return null;
  application.status = status;
  application.updatedAt = new Date().toISOString();
  application.decision = { programmeId, decidedAt: application.updatedAt, message };
  return application;
}
