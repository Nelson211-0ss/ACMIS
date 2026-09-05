// ---------------------------------------------------------------------------
// Domain types. Deliberately plain — no ORM types leak into the UI, so the
// mock repository and a future Prisma client are interchangeable.
// ---------------------------------------------------------------------------

export type Id = string;

// --- Reference data ---------------------------------------------------------

export interface Faculty {
  id: Id;
  name: string;
  /** Short code used in student numbers, e.g. "ENG" -> UOJ/ENG/2026/0142 */
  code: string;
}

export interface Programme {
  id: Id;
  facultyId: Id;
  name: string;
  code: string;
  /** Years to completion. Medicine is 6, most degrees 4. */
  durationYears: number;
  award: "Bachelor" | "Diploma" | "Certificate" | "Masters";
  /** Minimum aggregate SSCSE mark required to be considered. */
  minimumAggregate: number;
  /** Seats available this cycle. Drives the competitiveness hint. */
  intake: number;
  tuitionPerSemesterSSP: number;
  /** Subjects an applicant must have sat at SSCSE to be eligible. */
  requiredSubjects: string[];
}

/**
 * A running admission cycle the admissions office publishes — "2026/2027
 * Undergraduate Intake", say. Applicants only ever see `open` schemes; a
 * scheme is prepared as `draft` ahead of time and only appears on the Apply
 * page once published, and stops taking new applications once `closed`.
 * Applications already under review are unaffected by a scheme closing.
 */
export type SchemeStatus = "draft" | "open" | "closed";

export interface AdmissionScheme {
  id: Id;
  name: string;
  /** Short reference, e.g. "UG-2026". */
  code: string;
  description: string;
  /** Which programmes an applicant may rank under this scheme. */
  programmeIds: Id[];
  opensAt: string;
  closesAt: string;
  resultsBy: string;
  semesterStarts: string;
  applicationFeeSSP: number;
  status: SchemeStatus;
  createdAt: string;
}

// --- Applicants and applications -------------------------------------------

export type ApplicationStatus =
  | "draft"
  | "submitted"
  | "under_review"
  | "interview"
  | "admitted"
  | "waitlisted"
  | "rejected";

export type Sex = "female" | "male";

export interface PersonalDetails {
  firstName: string;
  middleName?: string;
  lastName: string;
  dateOfBirth: string; // ISO date
  sex: Sex | "";
  nationality: string;
  /** State of origin — all ten states plus the three administrative areas. */
  stateOfOrigin: string;
  county: string;
  phone: string;
  email: string;
  /** National ID or nationality certificate number. Optional: many applicants
   *  from rural counties will not hold one at the time of applying. */
  nationalId?: string;
  disability?: string;
  guardianName: string;
  guardianPhone: string;
}

/** One row of the South Sudan Certificate of Secondary Education. */
export interface SubjectResult {
  subject: string;
  mark: number; // out of 100
}

export interface EducationDetails {
  secondarySchool: string;
  schoolState: string;
  /** SSCSE index number. */
  indexNumber: string;
  yearCompleted: string;
  subjects: SubjectResult[];
}

export type DocumentKind =
  | "sscse_certificate"
  | "sscse_transcript"
  | "national_id"
  | "passport_photo"
  | "birth_certificate"
  | "payment_slip";

export interface UploadedDocument {
  id: Id;
  kind: DocumentKind;
  fileName: string;
  sizeBytes: number;
  uploadedAt: string;
  status: "pending" | "verified" | "rejected";
  note?: string;
}

export interface ProgrammeChoice {
  /** 1 = first choice. Applicants rank up to three. */
  rank: 1 | 2 | 3;
  programmeId: Id;
}

export interface Application {
  id: Id;
  reference: string; // human-quotable, e.g. APP-2026-004821
  applicantId: Id;
  /** Which admission scheme this was opened under. Unset on applications
   *  created before schemes existed — those see every programme, unscoped. */
  schemeId?: Id;
  status: ApplicationStatus;
  createdAt: string;
  updatedAt: string;
  submittedAt?: string;
  personal: PersonalDetails;
  education: EducationDetails;
  choices: ProgrammeChoice[];
  documents: UploadedDocument[];
  payment?: Payment;
  /** Set when status is admitted / rejected / waitlisted. */
  decision?: {
    programmeId?: Id;
    decidedAt: string;
    message: string;
  };
}

// --- Payments ---------------------------------------------------------------

export type PaymentMethod = "mgurush" | "nilepay" | "bank_slip";

export type PaymentStatus = "unpaid" | "pending" | "confirmed" | "failed";

export interface Payment {
  id: Id;
  method: PaymentMethod;
  amountSSP: number;
  status: PaymentStatus;
  /** Provider transaction id, or the bank slip number for manual deposits. */
  reference?: string;
  phone?: string;
  createdAt: string;
  confirmedAt?: string;
}

// --- Enrolled students -----------------------------------------------------

export interface Student {
  id: Id;
  /** e.g. UOJ/ENG/2024/0142 */
  studentNumber: string;
  firstName: string;
  lastName: string;
  email: string;
  phone: string;
  /** Passport photo, if one was digitised. Unset records fall back to initials. */
  photoUrl?: string;
  programmeId: Id;
  yearOfStudy: number;
  currentSemester: 1 | 2;
  status: "active" | "suspended" | "graduated" | "deferred";
  admittedYear: string;
  advisorName: string;
}

export interface Course {
  id: Id;
  code: string; // CSC 211
  title: string;
  creditHours: number;
  programmeId: Id;
  year: number;
  semester: 1 | 2;
  /** Compulsory courses are pre-selected and cannot be dropped. */
  compulsory: boolean;
  lecturer: string;
  /** Course ids that must be passed first. */
  prerequisites: Id[];
}

export type RegistrationState = "open" | "registered" | "locked";

export interface CourseRegistration {
  studentId: Id;
  courseId: Id;
  academicYear: string;
  semester: 1 | 2;
  registeredAt: string;
}

export type LetterGrade = "A" | "B+" | "B" | "C+" | "C" | "D" | "E" | "F";

export interface Result {
  studentId: Id;
  courseId: Id;
  academicYear: string;
  semester: 1 | 2;
  /** Coursework out of 40, exam out of 60 — the common UoJ split. */
  coursework: number;
  exam: number;
  total: number;
  grade: LetterGrade;
  points: number; // 4.0 scale
  published: boolean;
}

export interface FeeItem {
  id: Id;
  studentId: Id;
  academicYear: string;
  semester: 1 | 2;
  description: string;
  amountSSP: number;
  dueDate: string;
  /** Tuition is blocking: results are withheld while it is outstanding. */
  blocking: boolean;
}

export interface FeePayment {
  id: Id;
  studentId: Id;
  amountSSP: number;
  method: PaymentMethod;
  reference: string;
  paidAt: string;
  status: PaymentStatus;
}

export interface TimetableSlot {
  id: Id;
  courseId: Id;
  day: "Mon" | "Tue" | "Wed" | "Thu" | "Fri" | "Sat";
  startsAt: string; // "08:00"
  endsAt: string; // "10:00"
  venue: string;
  kind: "lecture" | "tutorial" | "lab" | "exam";
}

export interface Announcement {
  id: Id;
  title: string;
  body: string;
  postedAt: string;
  audience: "all" | "applicants" | "students";
  priority: "normal" | "important";
}

// --- Staff, roles and system administration ---------------------------------

/**
 * Fixed set of staff roles. Real deployments will want a role editor rather
 * than a hard-coded union, but four roles covers every seat the university
 * actually has an opinion about, and adding a fifth is a one-line change in
 * three places (this union, ROLE_LABELS, and the seed's default permissions).
 */
export type StaffRole = "super_admin" | "registrar" | "bursar" | "viewer";

export interface StaffUser {
  id: Id;
  name: string;
  email: string;
  staffRole: StaffRole;
  status: "active" | "suspended";
  lastActiveAt?: string;
}

/** One row of the unified directory shown on the admin Users page. */
export interface DirectoryUser {
  id: Id;
  name: string;
  email: string;
  kind: "student" | "applicant" | "staff";
  /** e.g. "Computer Science · Year 2", "Registrar", "Applicant" */
  roleLabel: string;
  statusLabel: string;
  statusTone: "green" | "gold" | "red" | "neutral";
  /** Only students and staff can be suspended from here; see comment on the Users page. */
  mutable: boolean;
}

export type Permission =
  | "manage_users"
  | "manage_roles"
  | "manage_settings"
  | "manage_appearance"
  | "manage_announcements"
  | "manage_admissions"
  | "view_monitoring"
  | "view_audit_log";

export type AccentKey = "nile" | "forest" | "amethyst" | "slate";

export interface SystemSettings {
  maintenanceMode: boolean;
  registrationOpen: boolean;
  applicationsOpen: boolean;
  appearance: {
    defaultMode: "system" | "light" | "dark";
    accent: AccentKey;
  };
  rolePermissions: Record<StaffRole, Permission[]>;
}

export interface AuditEntry {
  id: Id;
  at: string;
  actor: string;
  action: string;
  target?: string;
}
