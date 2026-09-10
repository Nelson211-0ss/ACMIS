/**
 * Hand-written domain types.
 *
 * These mirror the API's response models. `pnpm sdk:generate` writes a full
 * `src/generated/schema.ts` from the live OpenAPI document, which is the
 * authority — these are the shapes the apps import day to day, kept small and
 * readable, and `tests/test_types_match_openapi` in the API repo asserts the
 * two agree.
 */

export type Uuid = string
/** ISO 8601 instant. */
export type Instant = string
/** ISO 8601 date, no time. */
export type IsoDate = string

export interface PageMeta {
  limit: number
  next_cursor: string | null
  previous_cursor: string | null
  total: number | null
  has_more: boolean
}

export interface Page<T> {
  items: T[]
  meta: PageMeta
}

/**
 * What the signed-in actor may do with a record, decided server-side.
 *
 * Returned alongside the record so a UI never has to re-implement the policy
 * bundle in TypeScript to decide whether to render an Approve button. The
 * server already knows; this is it saying so.
 */
export interface Capability {
  action: string
  allowed: boolean
  reason: string | null
}

export interface RecordEnvelope<T> {
  data: T
  capabilities: Capability[]
  /**
   * Fields withheld by the field-level mask. Named so the UI can render
   * "restricted" rather than an empty cell that looks like missing data —
   * naming *that a field exists* is deliberate and safe; its value is not
   * disclosed.
   */
  masked_fields: string[]
}

export interface BulkResult {
  total: number
  succeeded: number
  failed: number
  errors: Array<Record<string, unknown>>
  correlation_id: Uuid | null
}

/** Integer minor units and an explicit currency. Never a float — see `Money` in the API. */
export interface Money {
  amount_minor: number
  currency: string
}

// --- identity ---------------------------------------------------------------

export type PrincipalKind = "staff" | "student" | "applicant" | "service" | "platform"

export interface WhoAmI {
  id: Uuid
  kind: PrincipalKind
  display_name: string
  email: string | null
  tenant_slug: string
  tenant_name: string
  roles: string[]
  permissions: string[]
  faculty_ids: Uuid[]
  department_ids: Uuid[]
  student_id: Uuid | null
  staff_id: Uuid | null
  applicant_id: Uuid | null
  mfa_satisfied: boolean
  is_impersonated: boolean
  /** Which module apps to show in the launcher, decided server-side. */
  modules: string[]
}

export interface TokenResponse {
  access_token: string
  token_type: string
  expires_in: number
  refresh_token: string | null
  must_change_password: boolean
  mfa_required: boolean
}

export interface Institution {
  slug: string
  name: string
  short_name: string
  city: string | null
  country_code: string
  currency: string
  locale: string
  timezone: string
  logo_url: string | null
  crest_url: string | null
  brand_primary: string | null
  brand_accent: string | null
  website: string | null
  support_email: string | null
  accreditation_number: string | null
  enabled_modules: string[]
}

// --- admissions -------------------------------------------------------------

export type ApplicationStatus =
  | "draft"
  | "submitted"
  | "awaiting_fee"
  | "under_review"
  | "incomplete"
  | "interview"
  | "recommended"
  | "admitted"
  | "waitlisted"
  | "rejected"
  | "offer_accepted"
  | "offer_declined"
  | "enrolled"
  | "withdrawn"

export interface AdmissionScheme {
  id: Uuid
  code: string
  name: string
  description: string | null
  entry_scheme: string
  study_level: string
  opens_at: Instant
  closes_at: Instant
  late_closes_at: Instant | null
  results_due_on: IsoDate | null
  acceptance_deadline_on: IsoDate | null
  application_fee_minor: number
  currency: string
  max_programme_choices: number
  requires_interview: boolean
  status: "draft" | "open" | "closed" | "completed"
}

export interface Application {
  id: Uuid
  number: string
  applicant_id: Uuid
  scheme_id: Uuid
  status: ApplicationStatus
  submitted_at: Instant | null
  is_late: boolean
  fee_settled_at: Instant | null
  aggregate_score: number | null
  final_score: number | null
  waitlist_position: number | null
  decided_at: Instant | null
  decision_reason: string | null
  flags: string[]
  created_at: Instant
  updated_at: Instant
}

// --- students ---------------------------------------------------------------

export type StudentStatus =
  | "admitted"
  | "active"
  | "on_leave"
  | "probation"
  | "suspended"
  | "withdrawn"
  | "discontinued"
  | "completed"
  | "graduated"
  | "deceased"

export interface ProgrammeAttachment {
  id: Uuid
  programme_id: Uuid
  curriculum_version_id: Uuid
  entry_route: string
  sponsorship: string
  sponsor_name: string | null
  current_year_of_study: number
  current_semester_number: number
  cgpa: number | null
  credits_earned: number
  credits_required: number
  outstanding_retakes: number
  progression_status: string
  is_primary: boolean
  started_on: IsoDate
  expected_completion_on: IsoDate | null
}

export interface Hold {
  kind: string
  reason: string
  placed_by?: string
  placed_at?: string
  cleared_at?: string | null
}

export interface Student {
  id: Uuid
  student_number: string
  surname: string
  given_names: string
  other_names: string | null
  date_of_birth: IsoDate
  sex: string
  nationality: string
  district_of_origin: string | null
  email: string
  phone: string
  status: StudentStatus
  admitted_on: IsoDate
  residence: string | null
  /** Absent — not null — when masked. See `RecordEnvelope.masked_fields`. */
  national_id?: string | null
  bank_account_number?: string | null
  disability?: string | null
  disability_detail?: string | null
  medical_conditions?: string | null
  next_of_kin_name?: string | null
  next_of_kin_phone?: string | null
  holds: Hold[]
  programmes: ProgrammeAttachment[]
  created_at: Instant
  updated_at: Instant
}

export interface Registration {
  id: Uuid
  student_id: Uuid
  semester_id: Uuid
  status: string
  total_credits: number
  retake_credits: number
  submitted_at: Instant | null
  approved_at: Instant | null
  is_late: boolean
  exam_card_issued_at: Instant | null
  courses: Array<{
    id: Uuid
    course_offering_id: Uuid
    credit_units: number
    category: string
    is_retake: boolean
    attempt_number: number
    is_audit: boolean
  }>
}

/** The student's own week, and the examinations at the end of it. */
export interface MyTimetable {
  semester_id: Uuid | null
  semester_name: string | null
  classes: Array<{
    course_offering_id: Uuid
    code: string
    title: string
    /** 1 = Monday, to match ISO and the printed timetable. */
    day_of_week: number
    starts_at: string
    ends_at: string
    session_kind: string
    room: string | null
    is_online: boolean
    meeting_url: string | null
  }>
  exams: Array<{
    course_offering_id: Uuid
    code: string
    title: string
    sitting_date: IsoDate
    starts_at: string
    duration_minutes: number
    session: string
    rooms: string[]
    status: string
  }>
}

/** A student's own registration, with the courses named rather than keyed. */
export interface MyRegistration extends Omit<Registration, "courses"> {
  semester_name: string | null
  courses: Array<Registration["courses"][number] & { code: string; title: string }>
}

// --- curriculum -------------------------------------------------------------

export type ApprovalStatus =
  | "draft"
  | "submitted"
  | "returned"
  | "recommended"
  | "approved"
  | "rejected"
  | "retired"

export interface Programme {
  id: Uuid
  code: string
  name: string
  short_name: string | null
  award_title: string
  award_abbreviation: string
  award_level: string
  owning_unit_id: Uuid
  duration_semesters: number
  delivery_modes: string[]
  study_level: string
  accreditation_number: string | null
  accredited_until: IsoDate | null
  status: ApprovalStatus
  is_active: boolean
}

export interface Course {
  id: Uuid
  code: string
  title: string
  owning_unit_id: Uuid
  credit_units: number
  lecture_hours: number
  tutorial_hours: number
  practical_hours: number
  level: number
  assessment_mode: string
  counts_toward_gpa: boolean
  status: ApprovalStatus
  is_active: boolean
}

export interface AcademicUnit {
  id: Uuid
  code: string
  name: string
  kind: string
  parent_id: Uuid | null
  ancestor_ids: Uuid[]
  depth: number
  head_staff_id: Uuid | null
  campus_id: Uuid | null
  is_active: boolean
}

export interface Semester {
  id: Uuid
  academic_year_id: Uuid
  kind: string
  name: string
  sequence: number
  starts_on: IsoDate
  ends_on: IsoDate
  registration_opens_on: IsoDate | null
  registration_closes_on: IsoDate | null
  add_drop_closes_on: IsoDate | null
  withdrawal_deadline_on: IsoDate | null
  teaching_starts_on: IsoDate | null
  teaching_ends_on: IsoDate | null
  exams_start_on: IsoDate | null
  exams_end_on: IsoDate | null
  results_due_on: IsoDate | null
  is_current: boolean
  locked_at: Instant | null
}

// --- assessment -------------------------------------------------------------

export type MarkSheetStatus =
  | "draft"
  | "submitted"
  | "returned"
  | "moderated"
  | "board_approved"
  | "faculty_approved"
  | "senate_approved"
  | "published"

export interface MarkSheet {
  id: Uuid
  course_offering_id: Uuid
  semester_id: Uuid
  status: MarkSheetStatus
  student_count: number
  entered_count: number
  missing_count: number
  pass_count: number
  fail_count: number
  mean_mark: number | null
  median_mark: number | null
  standard_deviation: number | null
  grade_distribution: Record<string, number>
  submitted_at: Instant | null
  moderated_at: Instant | null
  moderation_adjustment: number | null
  board_approved_at: Instant | null
  faculty_approved_at: Instant | null
  senate_approved_at: Instant | null
  published_at: Instant | null
  due_on: IsoDate | null
  return_comments: string | null
}

export interface CourseResult {
  id: Uuid
  student_id: Uuid
  course_code: string
  course_title: string
  credit_units: number
  coursework_mark: number | null
  exam_mark: number | null
  final_mark: number | null
  grade: string | null
  grade_point: number | null
  outcome: string
  attempt_number: number
  is_retake: boolean
  is_superseded: boolean
  released: boolean
  withheld: boolean
}

export interface Award {
  id: Uuid
  student_id: Uuid
  award_title: string
  award_level: string
  certificate_name: string
  classification: string | null
  final_cgpa: number | null
  credits_earned: number
  serial_number: string
  verification_code: string
  conferred_on: IsoDate
  status: string
  senate_minute_reference: string | null
  revoked_at: Instant | null
}

// --- learning ---------------------------------------------------------------

export type QuestionKind =
  | "multiple_choice"
  | "multiple_response"
  | "true_false"
  | "short_answer"
  | "numeric"
  | "matching"
  | "ordering"
  | "fill_in_blank"
  | "essay"
  | "file_upload"
  | "code"
  | "calculated"

export type AssessmentBehaviour =
  | "deferred_feedback"
  | "immediate_feedback"
  | "interactive_with_tries"
  | "adaptive"
  | "manual"

export type AssessmentStatus =
  | "draft"
  | "review"
  | "scheduled"
  | "open"
  | "closed"
  | "marking"
  | "marked"
  | "released"

export interface CourseSpace {
  id: Uuid
  course_offering_id: Uuid
  semester_id: Uuid
  welcome_message: string | null
  syllabus_outline: Array<Record<string, unknown>>
  is_published: boolean
  published_at: Instant | null
  archived_at: Instant | null
}

export interface Material {
  id: Uuid
  space_id: Uuid
  kind: string
  title: string
  description: string | null
  week_number: number | null
  topic: string | null
  sequence: number
  attachment_id: Uuid | null
  external_url: string | null
  duration_seconds: number | null
  is_published: boolean
  available_from: Instant | null
  available_until: Instant | null
  allow_download: boolean
  view_count: number
  unique_viewer_count: number
}

export interface OnlineAssessment {
  id: Uuid
  space_id: Uuid
  course_offering_id: Uuid
  kind: "practice" | "quiz" | "test" | "assignment" | "examination"
  title: string
  instructions: string | null
  assessment_component_id: Uuid | null
  total_marks: number
  pass_mark_percent: number | null
  opens_at: Instant | null
  closes_at: Instant | null
  duration_minutes: number | null
  max_attempts: number
  attempt_grading: string
  behaviour: AssessmentBehaviour
  tries_per_question: number
  shuffle_questions: boolean
  score_visibility: string
  status: AssessmentStatus
  authored_by_id: Uuid | null
  reviewed_by_id: Uuid | null
  reviewed_at: Instant | null
  review_comments: string | null
  released_at: Instant | null
  pushed_to_mark_sheet_at: Instant | null
  attempt_count: number
  submitted_count: number
  mean_score: number | null
  median_score: number | null
  standard_deviation: number | null
  pending_manual_marking: number
}

export interface PresentedQuestion {
  question_id: Uuid
  sequence: number
  kind: QuestionKind
  stem: string
  marks: number
  section: string | null
  options: Array<{ label: string; body: string }>
  variables: Record<string, unknown>
  answer: Record<string, unknown>
  flagged: boolean
}

export interface Attempt {
  id: Uuid
  assessment_id: Uuid
  attempt_number: number
  status: "in_progress" | "submitted" | "expired" | "abandoned" | "marked" | "voided"
  started_at: Instant
  expires_at: Instant | null
  submitted_at: Instant | null
  extra_time_minutes: number
  total_score: number | null
  percentage: number | null
  marked_at: Instant | null
}

export interface EngagementRow {
  student_id: Uuid
  week_number: number
  materials_available: number
  materials_viewed: number
  minutes_on_material: number
  assessments_available: number
  assessments_attempted: number
  mean_assessment_percent: number | null
  days_since_last_activity: number | null
  risk_band: "engaged" | "slipping" | "at_risk" | "disengaged" | null
}

// --- finance ----------------------------------------------------------------

export interface Invoice {
  id: Uuid
  number: string
  student_id: Uuid | null
  applicant_id: Uuid | null
  semester_id: Uuid | null
  kind: string
  currency: string
  subtotal_minor: number
  total_minor: number
  paid_minor: number
  waived_minor: number
  balance_minor: number
  sponsor_portion_minor: number
  status: string
  issued_on: IsoDate | null
  due_on: IsoDate | null
}

export interface Payment {
  id: Uuid
  reference: string
  receipt_number: string | null
  student_id: Uuid | null
  method: string
  provider: string | null
  currency: string
  amount_minor: number
  allocated_minor: number
  status: "pending" | "settled" | "failed" | "unmatched" | "reversed" | "refunded"
  value_date: IsoDate | null
  settled_at: Instant | null
  payer_name: string | null
  payer_narrative: string | null
}

export interface StudentStatement {
  currency: string
  balance_minor: number
  total_invoiced_minor: number
  total_paid_minor: number
  total_waived_minor: number
  as_at: Instant | null
  invoices: Array<{
    id: Uuid
    number: string
    kind: string
    status: string
    issued_on: IsoDate | null
    due_on: IsoDate | null
    total_minor: number
    paid_minor: number
    waived_minor: number
    balance_minor: number
    sponsor_portion_minor: number
  }>
  payments: Array<{
    id: Uuid
    reference: string
    receipt_number: string | null
    method: string
    status: string
    amount_minor: number
    allocated_minor: number
    value_date: IsoDate | null
  }>
}

// --- people -----------------------------------------------------------------

export interface Staff {
  id: Uuid
  staff_number: string
  title: string | null
  surname: string
  given_names: string
  display_title: string | null
  email: string
  phone: string
  category: string
  rank: string | null
  has_doctorate: boolean
  highest_qualification: string | null
  specialisation: string | null
  primary_unit_id: Uuid | null
  status: string
  first_appointed_on: IsoDate | null
  contract_ends_on: IsoDate | null
  salary_scale?: string | null
  national_id?: string | null
  bank_account_number?: string | null
}

export interface LeaveRequest {
  id: Uuid
  staff_id: Uuid
  leave_type: string
  starts_on: IsoDate
  ends_on: IsoDate
  working_days: number
  reason: string | null
  cover_staff_id: Uuid | null
  status: string
  supervisor_approved_at: Instant | null
  hr_approved_at: Instant | null
  rejection_reason: string | null
}

// --- governance -------------------------------------------------------------

export interface AuditEvent {
  id: Uuid
  occurred_at: Instant
  request_id: Uuid | null
  correlation_id: Uuid | null
  actor_id: Uuid | null
  actor_kind: string
  actor_label: string | null
  actor_roles: string[]
  impersonator_id: Uuid | null
  module: string | null
  action: string
  category: string
  outcome: "success" | "failure" | "denied"
  severity: string
  resource_type: string
  resource_id: string | null
  resource_label: string | null
  summary: string | null
  changes: Array<{ field: string; old: unknown; new: unknown }>
  event_metadata: Record<string, unknown>
  decision_policy_id: string | null
  decision_rule_id: string | null
  policy_bundle_version: string | null
  ip_address: string | null
  http_method: string | null
  http_path: string | null
}

export interface PolicyOverlay {
  id: Uuid
  policy_id: string
  description: string
  document: Record<string, unknown>
  enabled: boolean
  priority: number
  revision: number
  authored_by_id: Uuid | null
  approved_by_id: Uuid | null
  approved_at: Instant | null
  change_reason: string | null
  last_simulation: Record<string, unknown>
}

export interface PolicySimulation {
  allowed: boolean
  deciding_policy: string | null
  deciding_rule: string | null
  reason: string
  obligations: string[]
  masked_fields: string[]
  writable_fields: string[] | null
  denied_by_default: boolean
  bundle_version: string
  trace: Array<{
    policy: string
    rule: string
    effect: string
    matched: boolean
    error: string | null
  }>
}

// --- developers -------------------------------------------------------------

export interface ApiClientRecord {
  id: Uuid
  client_id: string
  name: string
  description: string | null
  owner_id: Uuid
  owner_email: string
  support_email: string | null
  environment: "sandbox" | "live"
  client_kind: string
  requested_scopes: string[]
  granted_scopes: string[]
  allowed_ip_ranges: string[]
  rate_limit_per_minute: number
  status: string
  last_used_at: Instant | null
}

export interface ApiKeyRecord {
  id: Uuid
  client_id: Uuid
  name: string
  prefix: string
  environment: string
  scopes: string[]
  expires_at: Instant | null
  last_used_at: Instant | null
  use_count: number
  revoked_at: Instant | null
  /** Present exactly once, in the create/rotate response. Never again. */
  secret?: string
}

// ---------------------------------------------------------------------------
// Library
// ---------------------------------------------------------------------------

export interface CatalogueRecordRow {
  id: Uuid
  material_kind: string
  title: string
  subtitle: string | null
  statement_of_responsibility: string | null
  authors: string[]
  edition: string | null
  publisher: string | null
  published_year: number | null
  isbn: string | null
  issn: string | null
  classification: string | null
  subjects: string[]
  summary: string | null
  online_url: string | null
  course_ids: Uuid[]
}

export interface CatalogueAvailability {
  record_id: Uuid
  copies: number
  available: number
  on_loan: number
  reference_only: number
  reservations: number
  /** The date the first copy is due back. What turns "all out" into something a reader can act on. */
  earliest_due: string | null
}

export interface CatalogueCopyRow {
  id: Uuid
  record_id: Uuid
  library_id: Uuid
  accession_number: string
  barcode: string
  call_number: string | null
  shelf_location: string | null
  loan_class: string
  status: string
  condition: string
  times_issued: number
}

export interface LibraryMemberRow {
  id: Uuid
  membership_number: string
  student_id: Uuid | null
  staff_id: Uuid | null
  full_name: string | null
  borrower_category: string
  status: string
  expires_on: string | null
  outstanding_fines_minor: number
  items_on_loan: number
}

export interface LoanRow {
  id: Uuid
  copy_id: Uuid
  member_id: Uuid
  library_id: Uuid
  issued_at: Instant
  due_on: string
  original_due_on: string
  returned_on: string | null
  renewals: number
  status: string
  fine_per_day_minor: number
  /** What the desk needs on the row: the shelf label, and the number to ring. */
  accession_number: string | null
  title: string | null
  membership_number: string | null
}

export interface LibraryFineRow {
  id: Uuid
  member_id: Uuid
  loan_id: Uuid | null
  reason: string
  amount_minor: number
  /** Present for an overdue: the arithmetic, so it can be shown rather than asserted. */
  days_overdue: number | null
  rate_per_day_minor: number | null
  status: string
  raised_on: string
}

export interface MyLibraryRecord {
  member: {
    membership_number: string
    borrower_category: string
    status: string
    expires_on: string | null
    items_on_loan: number
    outstanding_fines_minor: number
  } | null
  loans: Array<{
    loan_id: Uuid
    title: string
    accession_number: string
    due_on: string
    overdue: boolean
    renewals: number
  }>
  reservations: Array<{
    reservation_id: Uuid
    title: string
    status: string
    queue_position: number
    collect_by: string | null
  }>
  fines: Array<{
    fine_id: Uuid
    reason: string
    amount_minor: number
    days_overdue: number | null
    raised_on: string
  }>
}

export interface AcquisitionRow {
  id: Uuid
  reference: string
  title: string
  authors: string | null
  isbn: string | null
  copies_requested: number
  course_id: Uuid | null
  status: string
  requested_on: string
  estimated_unit_price_minor: number | null
}

export interface EResourceRow {
  id: Uuid
  name: string
  provider: string
  kind: string
  access_url: string | null
  authentication_method: string | null
  expires_on: string
  concurrent_users: number | null
  is_active: boolean
}

export interface LibraryClearance {
  member: { id: Uuid; membership_number: string; status: string } | null
  clear: boolean
  items_out: number
  outstanding_minor: number
  items: Array<{
    loan_id: Uuid
    title: string
    accession_number: string
    due_on: string
    overdue: boolean
  }>
}

// ---------------------------------------------------------------------------
// Quality assurance
// ---------------------------------------------------------------------------

export interface ClassSessionRow {
  id: Uuid
  course_offering_id: Uuid
  semester_id: Uuid
  kind: string
  session_date: string
  starts_at: string
  ends_at: string
  week_number: number | null
  room_id: Uuid | null
  scheduled_staff_id: Uuid | null
  delivered_by_staff_id: Uuid | null
  status: string
  topic: string | null
  expected_students: number
  present_count: number
  attendance_percent: number | null
  register_closed_at: Instant | null
}

export interface DeliveryReport {
  semester_id: Uuid
  sessions_planned: number
  sessions_held: number
  /** Classes that simply did not happen, as distinct from announced cancellations. */
  unannounced_absences: number
  offerings: Array<{
    course_offering_id: Uuid
    planned: number
    held: number
    cancelled: number
    not_held: number
    still_to_come: number
    delivery_percent: number | null
  }>
}

export interface AttendanceRow {
  student_id: Uuid
  sessions_held: number
  sessions_attended: number
  excused: number
  percentage: number | null
}

export interface MyAttendanceRow {
  course_offering_id: Uuid
  course_code: string
  course_title: string
  sessions: number
  attended: number
  excused: number
  percentage: number | null
  by_status: Record<string, number>
}

export interface EvaluationInstrumentRow {
  id: Uuid
  code: string
  version: number
  name: string
  scope: string
  introduction: string | null
  questions: Array<Record<string, unknown>>
  dimensions: string[]
  is_published: boolean
}

export interface CourseEvaluationRow {
  id: Uuid
  instrument_id: Uuid
  course_offering_id: Uuid
  semester_id: Uuid
  staff_id: Uuid | null
  opens_at: Instant
  closes_at: Instant
  results_visible_from: Instant | null
  status: string
  invited_count: number
  response_count: number
  /** False below the reporting threshold: a breakdown of four responses names the dissenter. */
  is_reportable: boolean
}

export interface EvaluationResults {
  evaluation_id: Uuid
  status: string
  responses?: number
  invited?: number
  response_rate?: number | null
  questions?: Record<string, number>
  dimensions?: Record<string, number>
  overall?: number | null
  reporting_threshold?: number
  comments?: Array<string | null>
}

export interface ObservationRow {
  id: Uuid
  staff_id: Uuid
  observer_staff_id: Uuid
  course_offering_id: Uuid | null
  observed_on: string
  purpose: string
  rubric_scores: Array<Record<string, unknown>>
  overall_score: number | null
  strengths: string | null
  areas_to_develop: string | null
  agreed_actions: string | null
  observee_response: string | null
  is_developmental: boolean
  status: string
  follow_up_due_on: string | null
}

export interface QualityAuditRow {
  id: Uuid
  reference: string
  title: string
  kind: string
  unit_id: Uuid | null
  programme_id: Uuid | null
  standard: string | null
  conducted_on: string | null
  findings: Array<Record<string, unknown>>
  major_findings: number
  minor_findings: number
  open_findings: number
  overall_outcome: string | null
  status: string
  next_review_due_on: string | null
}

export interface QualityIndicatorRow {
  id: Uuid
  code: string
  name: string
  unit_id: Uuid | null
  programme_id: Uuid | null
  academic_year_id: Uuid | null
  value: number
  target: number | null
  performance: string | null
  numerator: number | null
  denominator: number | null
  computed_at: Instant
}

// ---------------------------------------------------------------------------
// Life-cycle events
// ---------------------------------------------------------------------------

export interface SpecialExamRow {
  id: Uuid
  reference: string
  student_id: Uuid
  course_offering_id: Uuid
  semester_id: Uuid
  /** `special` is uncapped; `supplementary` is capped at the pass mark. */
  kind: string
  ground: string
  narrative: string
  missed_on: string | null
  evidence_attachment_ids: Uuid[]
  evidence_verified_at: Instant | null
  fee_minor: number | null
  status: string
  submitted_at: Instant
  recommended_at: Instant | null
  decided_at: Instant | null
  decision_note: string | null
  minute_reference: string | null
  exam_sitting_id: Uuid | null
  mark_recorded: boolean
}

export interface IdCardRow {
  id: Uuid
  student_id: Uuid
  serial: string
  barcode: string | null
  campus_id: Uuid | null
  issued_on: string
  expires_on: string | null
  reason: string
  status: string
  reported_lost_on: string | null
  replacement_fee_minor: number | null
  collected_at: Instant | null
}

export interface CardVerification {
  valid: boolean
  reason: string | null
  serial?: string
  verification_code?: string
  student_number: string | null
  full_name: string | null
  student_status?: string | null
  photo_attachment_id?: string | null
  session?: string
  papers?: string[]
  issued_with_override?: boolean
}

export interface ExamCardRow {
  id: Uuid
  student_id: Uuid
  registration_id: Uuid
  semester_id: Uuid
  verification_code: string
  session: string
  issued_at: Instant
  valid_until: string | null
  course_offering_ids: Uuid[]
  /** The gates as they stood at issue. A card printed before a payment was reversed has to be explainable. */
  clearance_snapshot: Record<string, unknown>
  override_reason: string | null
  status: string
}

/** The candidate's own card: the papers and the semester spelled out. */
export interface MyExamCardRow extends ExamCardRow {
  semester_name: string | null
  papers: Array<{ course_offering_id: Uuid; code: string; title: string }>
}

export interface TimeOffStanding {
  dead_semesters: number
  dead_years: number
  leaves_of_absence: number
  semesters_enrolled: number
  semesters_permitted: number
  dead_semesters_permitted: number
  standing: "within" | "final_chance" | "exceeded"
  reason: string | null
  programme_id: Uuid | null
}

export interface InstitutionTransferRow {
  id: Uuid
  reference: string
  direction: "incoming" | "outgoing"
  student_id: Uuid | null
  applicant_id: Uuid | null
  other_institution_name: string
  other_institution_country: string
  other_programme_name: string | null
  programme_id: Uuid | null
  entry_year_of_study: number | null
  credit_assessment: Array<Record<string, unknown>>
  credits_claimed: number
  credits_awarded: number
  credit_transfer_cap_percent: number | null
  status: string
  requested_at: Instant
  approved_at: Instant | null
  transcript_issued_at: Instant | null
  senate_minute_reference: string | null
}

// ---------------------------------------------------------------------------
// The academic calendar and late payment
// ---------------------------------------------------------------------------

export interface CalendarEventRow {
  id: Uuid
  academic_year_id: Uuid
  semester_id: Uuid | null
  kind: string
  title: string
  description: string | null
  starts_on: string
  ends_on: string
  starts_at: string | null
  ends_at: string | null
  location: string | null
  unit_ids: Uuid[]
  audience: string
  suspends_teaching: boolean
  is_published: boolean
  minute_reference: string | null
}

export interface LatePaymentRuleRow {
  id: Uuid
  code: string
  name: string
  academic_year_id: Uuid
  programme_id: Uuid | null
  sponsorship: string | null
  grace_days: number
  charge_basis: string
  charge_percent: number | null
  charge_flat_minor: number | null
  recurrence: string
  max_charges: number | null
  charge_cap_minor: number | null
  blocks_registration_after_days: number | null
  blocks_exam_card_after_days: number | null
  blocks_results_after_days: number | null
  is_waivable: boolean
  status: string
}

export interface PenaltyChargeRow {
  id: Uuid
  student_id: Uuid
  invoice_id: Uuid
  charged_on: string
  days_overdue: number
  balance_at_charge_minor: number
  percent_applied: number | null
  amount_minor: number
  sequence: number
  status: string
  applied_automatically: boolean
  reversal_reason: string | null
}

export interface PaymentPlanRow {
  id: Uuid
  reference: string
  student_id: Uuid
  invoice_id: Uuid | null
  total_minor: number
  deposit_minor: number
  instalment_count: number
  status: string
  reason: string | null
  requested_at: Instant
  approved_at: Instant | null
  missed_count: number
  instalments: Array<{
    id: Uuid
    sequence: number
    due_on: string
    amount_minor: number
    paid_minor: number
    status: string
    settled_on: string | null
  }>
}

export interface DunningNoticeRow {
  id: Uuid
  student_id: Uuid
  invoice_id: Uuid | null
  level: number
  channel: string
  sent_on: string
  balance_minor: number
  days_overdue: number
  consequence_stated: string | null
  sent_to_sponsor: boolean
}

export interface BlockState {
  student_id: Uuid
  blocked: boolean
  /** True when an agreed instalment plan is suspending the blocks. */
  protected_by_plan: boolean
  blocks: Array<{
    gate: string
    invoice: string
    days_overdue: number
    rule: string
    waivable: boolean
    clears_when: string
  }>
}

// ---------------------------------------------------------------------------
// Student elections
// ---------------------------------------------------------------------------

export interface ElectionPositionRow {
  id: Uuid
  code: string
  title: string
  description: string | null
  sequence: number
  seats: number
  /** How many a voter may choose. Usually equal to `seats`. */
  max_choices: number
  reserved_for: string | null
  is_referendum: boolean
  question: string | null
}

export interface ElectionRow {
  id: Uuid
  reference: string
  title: string
  kind: string
  description: string | null
  status:
    | "draft"
    | "nominations"
    | "vetting"
    | "campaign"
    | "voting"
    | "counting"
    | "declared"
    | "annulled"
  nominations_open_at: Instant | null
  nominations_close_at: Instant | null
  voting_opens_at: Instant | null
  voting_closes_at: Instant | null
  quorum_percent: number | null
  eligible_count: number
  ballots_cast: number
  turnout_percent: number | null
  declared_at: Instant | null
  positions: ElectionPositionRow[]
}

export interface CandidateRow {
  id: Uuid
  position_id: Uuid
  student_id: Uuid | null
  option_label: string | null
  ballot_name: string
  /** Drawn by lot, not alphabetical — the top of a ballot paper is an advantage. */
  ballot_order: number
  slogan: string | null
  manifesto: string | null
  status: string
  nominated_at: Instant
  eligibility_checks: Array<Record<string, unknown>>
  disqualification_reason: string | null
  votes: number
  is_elected: boolean
}

export interface VoterEntitlement {
  on_roll: boolean
  eligible: boolean
  /** Why not, so the voter knows what to appeal rather than just being refused. */
  reason: string | null
  has_voted: boolean
  voted_at?: Instant | null
  position_ids: string[]
}

export interface BallotReceipt {
  /** One per position. The voter's own copy; never stored against their name. */
  receipts: Record<string, string>
  cast_at: Instant
  positions: number
}

export interface ReceiptCheck {
  found: boolean
  position?: string | null
  cast_at?: Instant
  counted?: boolean
  /** Whether the ballot was a deliberate abstention — never the choice itself. */
  abstention?: boolean
}

export interface ElectionResultRow {
  id: Uuid
  election_id: Uuid
  position_id: Uuid
  eligible_count: number
  ballots_cast: number
  abstentions: number
  spoilt: number
  turnout_percent: number | null
  tally: Array<{
    candidate_id: Uuid
    ballot_name: string
    votes: number
    share_percent: number | null
    elected: boolean
  }>
  quorum_met: boolean | null
  declared_at: Instant
  tie_break_note: string | null
}

export interface TurnoutSnapshot {
  eligible: number
  cast: number
  turnout_percent: number | null
  quorum_percent: number | null
  quorum_met: boolean | null
  by_hour: Array<{ hour: string; cast: number }>
  /** Ballots from the busiest single device. The shape fraud actually takes. */
  most_from_one_device: number
}

export interface ElectionPetitionRow {
  id: Uuid
  reference: string
  election_id: Uuid
  position_id: Uuid | null
  ground: string
  submission: string
  filed_on: string
  status: string
  heard_on: string | null
  determination: string | null
  remedy: string | null
}
