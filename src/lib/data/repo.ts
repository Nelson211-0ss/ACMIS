import type {
  Announcement,
  Application,
  ApplicationStatus,
  Course,
  FeeItem,
  FeePayment,
  Payment,
  Result,
  Student,
  TimetableSlot,
  UploadedDocument,
} from "../types";
import { gpa } from "../format";
import {
  ANNOUNCEMENTS,
  APPLICATIONS,
  COURSES,
  CURRENT_YEAR,
  FEE_ITEMS,
  FEE_PAYMENTS,
  REGISTRATIONS,
  RESULTS,
  STUDENTS,
  TIMETABLE,
  nextId,
  nextReference,
} from "./store";

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

// --- Applications ----------------------------------------------------------

export async function getApplication(id: string): Promise<Application | null> {
  return APPLICATIONS.find((a) => a.id === id) ?? null;
}

export async function getApplicationsFor(applicantId: string): Promise<Application[]> {
  return APPLICATIONS.filter((a) => a.applicantId === applicantId).sort((a, b) =>
    b.updatedAt.localeCompare(a.updatedAt),
  );
}

export async function createApplication(applicantId: string): Promise<Application> {
  const now = new Date().toISOString();
  const application: Application = {
    id: nextId("app"),
    reference: nextReference(),
    applicantId,
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
