import type {
  AdmissionScheme,
  Announcement,
  ApplicantAccount,
  Application,
  ApplicationStatus,
  AuditEntry,
  Course,
  DirectoryUser,
  FeeItem,
  FeePayment,
  PasswordResetToken,
  Payment,
  Result,
  ResultSubmission,
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
  APPLICANT_ACCOUNTS,
  APPLICATIONS,
  AUDIT_LOG,
  COURSES,
  CURRENT_YEAR,
  FEE_ITEMS,
  FEE_PAYMENTS,
  PASSWORD_RESETS,
  REGISTRATIONS,
  RESULTS,
  RESULT_SUBMISSIONS,
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

// --- Results sign-off --------------------------------------------------------

/** No row yet means nobody has submitted this offering — that is a draft. */
export async function getResultSubmission(
  courseId: string,
  academicYear = CURRENT_YEAR,
): Promise<ResultSubmission | null> {
  return (
    RESULT_SUBMISSIONS.find(
      (r) => r.courseId === courseId && r.academicYear === academicYear,
    ) ?? null
  );
}

/**
 * A lecturer sends a marked class up for sign-off.
 *
 * Nothing is published here — that is the head of department's call. This
 * only changes who the ball is with.
 */
export async function submitResultsForApproval(
  courseId: string,
  semester: 1 | 2,
  submittedBy: string,
  academicYear = CURRENT_YEAR,
): Promise<ResultSubmission> {
  const existing = await getResultSubmission(courseId, academicYear);
  if (existing) {
    existing.status = "pending_approval";
    existing.submittedBy = submittedBy;
    existing.submittedAt = new Date().toISOString();
    existing.decidedBy = undefined;
    existing.decidedAt = undefined;
    existing.note = undefined;
    return existing;
  }

  const submission: ResultSubmission = {
    courseId,
    academicYear,
    semester,
    status: "pending_approval",
    submittedBy,
    submittedAt: new Date().toISOString(),
  };
  RESULT_SUBMISSIONS.push(submission);
  return submission;
}

/**
 * The head of department decides.
 *
 * Approving is what actually makes marks visible to students — publishing is
 * a consequence of the decision rather than a separate button somebody could
 * press on its own.
 */
export async function decideResultSubmission(
  courseId: string,
  decidedBy: string,
  outcome: "approved" | "returned",
  note: string | undefined,
  academicYear = CURRENT_YEAR,
): Promise<ResultSubmission | null> {
  const submission = await getResultSubmission(courseId, academicYear);
  if (!submission || submission.status !== "pending_approval") return null;

  submission.status = outcome;
  submission.decidedBy = decidedBy;
  submission.decidedAt = new Date().toISOString();
  submission.note = note;

  await setCourseResultsPublished(
    courseId,
    academicYear,
    submission.semester,
    outcome === "approved",
  );
  return submission;
}

export interface PendingApprovalRow {
  submission: ResultSubmission;
  course: Course;
  submittedBy: StaffUser | null;
  marked: number;
  registered: number;
}

/** Everything waiting on a head of department, oldest submission first. */
export async function listPendingApprovals(
  academicYear = CURRENT_YEAR,
): Promise<PendingApprovalRow[]> {
  const rows: PendingApprovalRow[] = [];

  for (const submission of RESULT_SUBMISSIONS) {
    if (submission.status !== "pending_approval") continue;
    if (submission.academicYear !== academicYear) continue;

    const course = COURSES.find((c) => c.id === submission.courseId);
    if (!course) continue;

    const roster = await getCourseRoster(course.id, academicYear);
    rows.push({
      submission,
      course,
      submittedBy: submission.submittedBy
        ? (STAFF_USERS.find((s) => s.id === submission.submittedBy) ?? null)
        : null,
      marked: roster.filter((r) => r.result !== null).length,
      registered: roster.length,
    });
  }

  return rows.sort((a, b) =>
    (a.submission.submittedAt ?? "").localeCompare(b.submission.submittedAt ?? ""),
  );
}

// --- Bursary -----------------------------------------------------------------

export interface PendingPaymentRow {
  payment: FeePayment;
  student: Student | null;
}

/**
 * Bank deposit slips waiting on the bursary.
 *
 * Mobile money settles itself; a slip is a claim that money reached the
 * university's account, and until somebody checks the bank statement it is
 * only a claim. Before this existed the claim was recorded and then nothing
 * could ever act on it — the payment sat "pending" forever.
 */
export async function listPendingPayments(): Promise<PendingPaymentRow[]> {
  return FEE_PAYMENTS.filter((p) => p.status === "pending")
    .sort((a, b) => a.paidAt.localeCompare(b.paidAt))
    .map((payment) => ({
      payment,
      student: STUDENTS.find((s) => s.id === payment.studentId) ?? null,
    }));
}

/**
 * Clear or reject a slip. `confirmed` is what makes the money count toward a
 * balance — `getFeeSummary` only totals confirmed payments — so this is the
 * step that actually unblocks a student's results.
 */
export async function settlePayment(
  paymentId: string,
  outcome: "confirmed" | "failed",
): Promise<FeePayment | null> {
  const payment = FEE_PAYMENTS.find((p) => p.id === paymentId);
  if (!payment) return null;
  // Only a pending slip is the bursary's to decide; re-settling a closed one
  // would let a second click undo a decision already acted on.
  if (payment.status !== "pending") return null;
  payment.status = outcome;
  return payment;
}

/** A correction, waiver or scholarship against one student's account. */
export async function addFeeItem(input: {
  studentId: string;
  description: string;
  amountSSP: number;
  dueDate: string;
  blocking: boolean;
  semester: 1 | 2;
}): Promise<FeeItem> {
  const item: FeeItem = {
    id: nextId("fee"),
    studentId: input.studentId,
    academicYear: CURRENT_YEAR,
    semester: input.semester,
    description: input.description,
    amountSSP: input.amountSSP,
    dueDate: input.dueDate,
    blocking: input.blocking,
  };
  FEE_ITEMS.push(item);
  return item;
}

/** Every student with an outstanding balance, worst first. */
export async function listFeeBalances(): Promise<
  Array<{ student: Student; charged: number; paid: number; balance: number }>
> {
  const rows = await Promise.all(
    STUDENTS.map(async (student) => {
      const summary = await getFeeSummary(student.id);
      return {
        student,
        charged: summary.charged,
        paid: summary.paid,
        balance: summary.balance,
      };
    }),
  );
  return rows.sort((a, b) => b.balance - a.balance);
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

/**
 * Adds a staff account. Email is the natural key — a duplicate is rejected
 * rather than silently creating a second account someone could sign in to,
 * since the demo sign-in resolves an account by email.
 *
 * `lastActiveAt` is deliberately left unset: a new account has never signed
 * in, and stamping "now" would claim otherwise on the users table.
 */
export async function addStaff(input: {
  name: string;
  email: string;
  staffRole: StaffRole;
}): Promise<{ staff: StaffUser } | { error: string }> {
  const name = input.name.trim();
  const email = input.email.trim().toLowerCase();

  if (!name) return { error: "Enter the person's full name." };
  if (!/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email)) {
    return { error: "Enter a valid email address." };
  }
  if (STAFF_USERS.some((s) => s.email.toLowerCase() === email)) {
    return { error: `${email} already has a staff account.` };
  }

  const staff: StaffUser = {
    id: `staff-${Date.now().toString(36)}`,
    name,
    email,
    staffRole: input.staffRole,
    status: "active",
  };
  STAFF_USERS.push(staff);
  return { staff };
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
  patch: Partial<Omit<SystemSettings, "branding" | "appearance" | "rolePermissions">> & {
    branding?: Partial<SystemSettings["branding"]>;
    appearance?: Partial<SystemSettings["appearance"]>;
    rolePermissions?: SystemSettings["rolePermissions"];
  },
): Promise<SystemSettings> {
  Object.assign(SYSTEM_SETTINGS, {
    ...patch,
    branding: { ...SYSTEM_SETTINGS.branding, ...patch.branding },
    appearance: { ...SYSTEM_SETTINGS.appearance, ...patch.appearance },
    rolePermissions: patch.rolePermissions ?? SYSTEM_SETTINGS.rolePermissions,
  });
  return SYSTEM_SETTINGS;
}

/**
 * Who this deployment says it is. Every piece of chrome that used to read the
 * `institution` constant directly goes through here instead, so a super
 * administrator's edit reaches the wordmark, the page titles and the public
 * site without a redeploy.
 */
export async function getBranding(): Promise<SystemSettings["branding"]> {
  return SYSTEM_SETTINGS.branding;
}

export interface SeededAccount {
  name: string;
  email: string;
  /** "Super administrator", "Continuing student", "Applicant"… */
  role: string;
  group: "Students and applicants" | "Administration" | "Academic" | "Support";
  suspended: boolean;
}

const STAFF_GROUP: Record<StaffRole, SeededAccount["group"]> = {
  super_admin: "Administration",
  registrar: "Administration",
  bursar: "Administration",
  head_of_department: "Academic",
  lecturer: "Academic",
  it_support: "Support",
  viewer: "Support",
};

/**
 * Every account the seed created, for the sign-in screen to offer.
 *
 * Built from the store rather than a hand-kept list: there were 20 seeded
 * accounts and a hardcoded list of 9, so the other 11 could only be reached
 * by finding an email in the users table and guessing the shared password.
 * Deriving it means the two can never drift apart again.
 */
export async function listSeededAccounts(): Promise<SeededAccount[]> {
  const students: SeededAccount[] = STUDENTS.map((s) => ({
    name: `${s.firstName} ${s.lastName}`,
    email: s.email,
    role: s.status === "graduated" ? "Alumna / alumnus" : "Continuing student",
    group: "Students and applicants",
    suspended: s.status === "suspended",
  }));

  const applicants: SeededAccount[] = APPLICANT_ACCOUNTS.map((a) => {
    const application = APPLICATIONS.find((app) => app.applicantId === a.id);
    const person = application
      ? `${application.personal.firstName} ${application.personal.lastName}`.trim()
      : a.email;
    return {
      name: person || a.email,
      email: a.email,
      role: "Applicant",
      group: "Students and applicants" as const,
      suspended: a.status === "suspended",
    };
  });

  const staff: SeededAccount[] = STAFF_USERS.map((s) => ({
    name: s.name,
    email: s.email,
    role: s.staffRole,
    group: STAFF_GROUP[s.staffRole],
    suspended: s.status !== "active",
  }));

  return [...students, ...applicants, ...staff];
}

// --- Accounts and credentials ------------------------------------------------

export async function getApplicantAccount(
  id: string,
): Promise<ApplicantAccount | null> {
  return APPLICANT_ACCOUNTS.find((a) => a.id === id) ?? null;
}

/**
 * One person, whichever table they live in.
 *
 * Sign-in cannot know in advance whether an email belongs to a student, an
 * applicant or a staff member, so it asks once and gets back what kind of
 * subject it found along with the hash to check.
 */
export interface Credential {
  kind: "student" | "applicant" | "staff";
  id: string;
  email: string;
  passwordHash?: string;
  /** False for a suspended staff member or student — checked after the password. */
  active: boolean;
}

export async function findCredentialByEmail(
  email: string,
): Promise<Credential | null> {
  const target = email.trim().toLowerCase();

  const student = STUDENTS.find((s) => s.email.toLowerCase() === target);
  if (student) {
    return {
      kind: "student",
      id: student.id,
      email: student.email,
      passwordHash: student.passwordHash,
      active: student.status !== "suspended",
    };
  }

  const staff = STAFF_USERS.find((s) => s.email.toLowerCase() === target);
  if (staff) {
    return {
      kind: "staff",
      id: staff.id,
      email: staff.email,
      passwordHash: staff.passwordHash,
      active: staff.status === "active",
    };
  }

  const applicant = APPLICANT_ACCOUNTS.find((a) => a.email.toLowerCase() === target);
  if (applicant) {
    return {
      kind: "applicant",
      id: applicant.id,
      email: applicant.email,
      passwordHash: applicant.passwordHash,
      active: applicant.status === "active",
    };
  }

  return null;
}

/** Writes a new hash to whichever table the subject lives in. */
export async function setPasswordHash(
  kind: Credential["kind"],
  id: string,
  passwordHash: string,
): Promise<boolean> {
  if (kind === "student") {
    const student = STUDENTS.find((s) => s.id === id);
    if (!student) return false;
    student.passwordHash = passwordHash;
    return true;
  }
  if (kind === "staff") {
    const staff = STAFF_USERS.find((s) => s.id === id);
    if (!staff) return false;
    staff.passwordHash = passwordHash;
    return true;
  }
  const applicant = APPLICANT_ACCOUNTS.find((a) => a.id === id);
  if (!applicant) return false;
  applicant.passwordHash = passwordHash;
  return true;
}

/**
 * Creates an applicant login. Email is the natural key across all three
 * subject tables — a student must not be able to shadow their own record with
 * a second applicant account on the same address.
 */
export async function createApplicantAccount(
  email: string,
  passwordHash: string,
): Promise<{ account: ApplicantAccount } | { error: string }> {
  const target = email.trim().toLowerCase();
  if (!/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(target)) {
    return { error: "Enter a valid email address." };
  }
  if (await findCredentialByEmail(target)) {
    return { error: "An account already exists for that email address." };
  }

  const account: ApplicantAccount = {
    id: nextId("usr"),
    email: target,
    passwordHash,
    status: "active",
    createdAt: new Date().toISOString(),
  };
  APPLICANT_ACCOUNTS.push(account);
  return { account };
}

// --- Password resets ---------------------------------------------------------

export async function createPasswordReset(
  token: PasswordResetToken,
): Promise<void> {
  // One live reset per person: issuing a new link invalidates the old one, so
  // a forwarded or shoulder-surfed earlier email stops working.
  for (let i = PASSWORD_RESETS.length - 1; i >= 0; i--) {
    const existing = PASSWORD_RESETS[i];
    if (
      existing.subjectKind === token.subjectKind &&
      existing.subjectId === token.subjectId &&
      !existing.usedAt
    ) {
      PASSWORD_RESETS.splice(i, 1);
    }
  }
  PASSWORD_RESETS.push(token);
}

/** Unused, unexpired resets only — a spent or stale token is not a match. */
export async function findPasswordReset(
  tokenHash: string,
): Promise<PasswordResetToken | null> {
  const found = PASSWORD_RESETS.find((t) => t.tokenHash === tokenHash);
  if (!found) return null;
  if (found.usedAt) return null;
  if (new Date(found.expiresAt).getTime() < Date.now()) return null;
  return found;
}

export async function consumePasswordReset(tokenHash: string): Promise<void> {
  const found = PASSWORD_RESETS.find((t) => t.tokenHash === tokenHash);
  if (found) found.usedAt = new Date().toISOString();
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
