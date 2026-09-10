import type { AcmisClient, RequestOptions } from "./core/client"
import type {
  AcquisitionRow,
  BallotReceipt,
  CandidateRow,
  ElectionPetitionRow,
  ElectionResultRow,
  ElectionRow,
  ReceiptCheck,
  TurnoutSnapshot,
  VoterEntitlement,
  ApiClientRecord,
  AttendanceRow,
  BlockState,
  CalendarEventRow,
  CardVerification,
  CatalogueAvailability,
  CatalogueCopyRow,
  CatalogueRecordRow,
  ClassSessionRow,
  CourseEvaluationRow,
  DeliveryReport,
  DunningNoticeRow,
  EResourceRow,
  EvaluationInstrumentRow,
  EvaluationResults,
  ExamCardRow,
  MyExamCardRow,
  IdCardRow,
  InstitutionTransferRow,
  LatePaymentRuleRow,
  LibraryClearance,
  LibraryFineRow,
  LibraryMemberRow,
  LoanRow,
  MyAttendanceRow,
  MyLibraryRecord,
  ObservationRow,
  PaymentPlanRow,
  PenaltyChargeRow,
  QualityAuditRow,
  QualityIndicatorRow,
  SpecialExamRow,
  TimeOffStanding,
  Instant,
  ApiKeyRecord,
  Application,
  AdmissionScheme,
  Attempt,
  AuditEvent,
  Award,
  BulkResult,
  Capability,
  Course,
  CourseResult,
  CourseSpace,
  EngagementRow,
  Institution,
  Invoice,
  LeaveRequest,
  MarkSheet,
  Material,
  OnlineAssessment,
  Page,
  Payment,
  PolicyOverlay,
  PolicySimulation,
  PresentedQuestion,
  Programme,
  RecordEnvelope,
  MyRegistration,
  MyTimetable,
  Registration,
  Semester,
  Staff,
  Student,
  StudentStatement,
  TokenResponse,
  Uuid,
  WhoAmI,
} from "./types"

/**
 * The typed API surface, grouped by module.
 *
 * Thin by design: each method is a URL, a shape and nothing else. Business
 * decisions live in the API — the client's job is to not be a second place
 * where a rule could be implemented slightly differently.
 */

/**
 * Shared list parameters.
 *
 * A type alias rather than an interface deliberately: only aliases get
 * TypeScript's implicit index signature, and without it every
 * `PageQuery & { status?: string }` fails to satisfy the client's
 * `Record<string, unknown>` query type.
 */
export type PageQuery = {
  limit?: number
  cursor?: string
  with_total?: boolean
}

export const api = (client: AcmisClient) => ({
  auth: {
    login: (username: string, password: string) =>
      client.post<TokenResponse>("/api/v1/auth/login", { username, password }),
    refresh: () => client.post<TokenResponse>("/api/v1/auth/refresh"),
    logout: () => client.post<void>("/api/v1/auth/logout"),
    whoami: (options?: RequestOptions) =>
      client.get<WhoAmI>("/api/v1/auth/whoami", options),
    changePassword: (body: { current_password?: string; new_password: string }) =>
      client.post<void>("/api/v1/auth/change-password", body),
    forgotPassword: (email: string) =>
      client.post<{ message: string }>("/api/v1/auth/forgot-password", { email }),
    resetPassword: (token: string, new_password: string) =>
      client.post<void>("/api/v1/auth/reset-password", { token, new_password }),
    verifyMfa: (code: string) =>
      client.post<TokenResponse>("/api/v1/auth/mfa/verify", { code }),
  },

  /**
   * Authorization introspection. `capabilities` is what lets a UI render only
   * the buttons the actor can actually use, without re-implementing the policy
   * bundle in TypeScript.
   */
  authz: {
    capabilities: (body: {
      resource_type: string
      resource_id?: Uuid
      actions: string[]
      attributes?: Record<string, unknown>
    }) => client.post<Capability[]>("/api/v1/authz/capabilities", body),
    simulate: (body: {
      action: string
      resource_type: string
      subject?: Record<string, unknown>
      resource?: Record<string, unknown>
      environment?: Record<string, unknown>
    }) => client.post<PolicySimulation>("/api/v1/authz/simulate", body),
    describe: () =>
      client.get<
        Array<{ resource_type: string; attributes: string[]; protected_fields: string[] }>
      >("/api/v1/authz/describe"),
    bundle: (includeConditions = false) =>
      client.get<{
        version: string
        policy_count: number
        rule_count: number
        lint: string[]
        policies: Array<Record<string, unknown>>
      }>("/api/v1/authz/bundle", { query: { include_conditions: includeConditions } }),
  },

  reference: {
    units: (kind?: string) =>
      client.get<
        Array<{
          id: Uuid
          code: string
          name: string
          kind: string
          parent_id: Uuid | null
          ancestor_ids: Uuid[]
          depth: number
          is_active: boolean
        }>
      >("/api/v1/reference/units", { query: { kind } }),
    academicYears: () =>
      client.get<
        Array<{
          id: Uuid
          code: string
          name: string
          is_current: boolean
          semesters: Semester[]
        }>
      >("/api/v1/reference/academic-years"),
    currentSemester: () =>
      client.get<Semester | null>("/api/v1/reference/semesters/current"),
    campuses: () =>
      client.get<Array<{ id: Uuid; code: string; name: string; is_main: boolean }>>(
        "/api/v1/reference/campuses",
      ),
    notifications: (query: PageQuery & { unread_only?: boolean } = {}) =>
      client.get<
        Page<{
          id: Uuid
          category: string
          subject: string
          body: string
          action_url: string | null
          is_urgent: boolean
          read_at: string | null
          created_at: string
        }>
      >("/api/v1/reference/notifications", { query }),
    markNotificationRead: (id: Uuid) =>
      client.post<void>(`/api/v1/reference/notifications/${id}/read`),
  },

  admissions: {
    schemes: (query: PageQuery & { status?: string } = {}) =>
      client.get<Page<AdmissionScheme>>("/api/v1/admissions/schemes", { query }),
    createScheme: (body: Record<string, unknown>) =>
      client.post<AdmissionScheme>("/api/v1/admissions/schemes", body),
    publishScheme: (id: Uuid) =>
      client.post<AdmissionScheme>(`/api/v1/admissions/schemes/${id}/publish`),
    schemeStatistics: (id: Uuid) =>
      client.get<{
        scheme: { id: string; code: string; status: string }
        by_status: Record<string, number>
        total: number
        intakes: Array<{
          programme_intake_id: string
          programme_id: string
          approved_intake: number
          applications_received: number
          offers_issued: number
          offers_accepted: number
          enrolled: number
          cutoff_score: number | null
          competition_ratio: number | null
        }>
      }>(`/api/v1/admissions/schemes/${id}/statistics`),
    applications: (
      query: PageQuery & {
        scheme_id?: Uuid
        status?: string
        faculty_id?: Uuid
        search?: string
      } = {},
    ) => client.get<Page<Application>>("/api/v1/admissions/applications", { query }),
    application: (id: Uuid) =>
      client.get<RecordEnvelope<Application & Record<string, unknown>>>(
        `/api/v1/admissions/applications/${id}`,
      ),
    startApplication: (body: { scheme_id: Uuid; programme_intake_ids: Uuid[] }) =>
      client.post<Application>("/api/v1/admissions/applications", body),
    updateApplication: (id: Uuid, body: Record<string, unknown>) =>
      client.patch<Application>(`/api/v1/admissions/applications/${id}`, body),
    submitApplication: (id: Uuid) =>
      client.post<Application>(`/api/v1/admissions/applications/${id}/submit`),
    scoreApplication: (
      id: Uuid,
      body: { interview_score?: number; entrance_exam_score?: number },
    ) => client.post<Application>(`/api/v1/admissions/applications/${id}/score`, body),
    generateSelectionList: (body: Record<string, unknown>) =>
      client.post<Record<string, unknown>>("/api/v1/admissions/selection-lists", body),
    approveSelectionList: (id: Uuid, reason: string) =>
      client.post<Record<string, unknown>>(
        `/api/v1/admissions/selection-lists/${id}/approve`,
        { reason },
      ),
    issueOffers: (id: Uuid) =>
      client.post<{ issued: number; refused: Array<Record<string, string>> }>(
        `/api/v1/admissions/selection-lists/${id}/issue-offers`,
      ),
    respondToOffer: (id: Uuid, accept: boolean, decline_reason?: string) =>
      client.post<Record<string, unknown>>(`/api/v1/admissions/offers/${id}/respond`, {
        accept,
        decline_reason,
      }),
    enrol: (offerId: Uuid, body: { semester_id: Uuid; student_number?: string }) =>
      client.post<{
        student_id: string
        student_number: string
        invoice_number: string
        created: boolean
      }>(`/api/v1/admissions/offers/${offerId}/enrol`, body),
  },

  students: {
    list: (
      query: PageQuery & {
        status?: string
        programme_id?: Uuid
        faculty_id?: Uuid
        year_of_study?: number
        search?: string
      } = {},
    ) => client.get<Page<Student>>("/api/v1/students", { query }),
    get: (id: Uuid) =>
      client.get<RecordEnvelope<Student>>(`/api/v1/students/${id}`),
    myRecord: () => client.get<RecordEnvelope<Student>>("/api/v1/students/me/record"),
    /** Every semester this student has registered for, newest first. */
    myRegistrations: () =>
      client.get<MyRegistration[]>("/api/v1/students/me/registrations"),
    /** This semester's classes and examinations, from the registration. */
    myTimetable: () => client.get<MyTimetable>("/api/v1/students/me/timetable"),
    update: (id: Uuid, body: Partial<Student>) =>
      client.patch<Student>(`/api/v1/students/${id}`, body),
    placeHold: (id: Uuid, body: { kind: string; reason: string }) =>
      client.post<Student>(`/api/v1/students/${id}/holds`, body),
    clearHold: (id: Uuid, kind: string, reason: string) =>
      client.delete<Student>(`/api/v1/students/${id}/holds/${kind}`, {
        body: { reason },
      } as RequestOptions),
    requestStatusChange: (id: Uuid, body: Record<string, unknown>) =>
      client.post<Record<string, unknown>>(
        `/api/v1/students/${id}/status-changes`,
        body,
      ),
    approveStatusChange: (
      changeId: Uuid,
      body: { reason: string; minute_reference?: string },
    ) =>
      client.post<Record<string, unknown>>(
        `/api/v1/students/status-changes/${changeId}/approve`,
        body,
      ),
    openRegistration: (studentId: Uuid, semesterId: Uuid) =>
      client.post<Registration>(
        `/api/v1/students/${studentId}/registrations`,
        undefined,
        { query: { semester_id: semesterId } },
      ),
    setRegistrationCourses: (registrationId: Uuid, courseOfferingIds: Uuid[]) =>
      client.put<Registration>(
        `/api/v1/students/registrations/${registrationId}/courses`,
        { course_offering_ids: courseOfferingIds },
      ),
    submitRegistration: (registrationId: Uuid) =>
      client.post<Registration>(
        `/api/v1/students/registrations/${registrationId}/submit`,
      ),
    clearance: (studentId: Uuid, purpose = "graduation") =>
      client.get<
        Array<{
          id: Uuid
          office: string
          status: string
          obligation_note: string | null
          outstanding_amount_minor: number | null
        }>
      >(`/api/v1/students/${studentId}/clearance`, { query: { purpose } }),
  },

  curriculum: {
    programmes: (
      query: PageQuery & { status?: string; unit_id?: Uuid; active_only?: boolean } = {},
    ) =>
      client.get<Page<Programme>>("/api/v1/curriculum/programmes", { query }),
    createProgramme: (body: Record<string, unknown>) =>
      client.post<Programme>("/api/v1/curriculum/programmes", body),
    createVersion: (body: Record<string, unknown>) =>
      client.post<Record<string, unknown>>("/api/v1/curriculum/versions", body),
    transitionVersion: (
      id: Uuid,
      action: "submit" | "recommend" | "approve" | "reject" | "return",
      body: { reason: string; minute_reference?: string },
    ) =>
      client.post<Record<string, unknown>>(
        `/api/v1/curriculum/versions/${id}/${action}`,
        body,
      ),
    courses: (query: PageQuery & { unit_id?: Uuid; level?: number; search?: string } = {}) =>
      client.get<Page<Course>>("/api/v1/curriculum/courses", { query }),
    createCourse: (body: Record<string, unknown>) =>
      client.post<Course>("/api/v1/curriculum/courses", body),
    addCurriculumCourse: (versionId: Uuid, body: Record<string, unknown>) =>
      client.post<{ id: string; total_credit_units: number }>(
        `/api/v1/curriculum/versions/${versionId}/courses`,
        body,
      ),
    createOffering: (body: Record<string, unknown>) =>
      client.post<Record<string, unknown>>("/api/v1/curriculum/offerings", body),
    allocateTeaching: (offeringId: Uuid, body: Record<string, unknown>) =>
      client.post<{ id: string }>(
        `/api/v1/curriculum/offerings/${offeringId}/allocations`,
        body,
      ),
    createTimetableSlot: (body: Record<string, unknown>) =>
      client.post<{ id: string }>("/api/v1/curriculum/timetable", body),
  },

  calendar: {
    events: (
      query: {
        academic_year_id?: Uuid
        semester_id?: Uuid
        from_date?: string
        to_date?: string
        kind?: string
      } = {},
    ) => client.get<CalendarEventRow[]>("/api/v1/reference/calendar", { query }),
    create: (body: Record<string, unknown>) =>
      client.post<CalendarEventRow>("/api/v1/reference/calendar", body),
    publish: (id: Uuid, minuteReference?: string) =>
      client.post<CalendarEventRow>(`/api/v1/reference/calendar/${id}/publish`, {
        minute_reference: minuteReference,
      }),
    /** Read by the class-session generator: the days the campus is shut. */
    suspendedDates: (academicYearId: Uuid) =>
      client.get<string[]>("/api/v1/reference/calendar/suspended-dates", {
        query: { academic_year_id: academicYearId },
      }),
  },

  learning: {
    openSpace: (courseOfferingId: Uuid) =>
      client.post<CourseSpace>("/api/v1/learning/spaces", undefined, {
        query: { course_offering_id: courseOfferingId },
      }),
    materials: (spaceId: Uuid) =>
      client.get<Material[]>(`/api/v1/learning/spaces/${spaceId}/materials`),
    publishMaterial: (spaceId: Uuid, body: Record<string, unknown>) =>
      client.post<Material>(`/api/v1/learning/spaces/${spaceId}/materials`, body),
    recordView: (
      materialId: Uuid,
      body: { seconds?: number; downloaded?: boolean; completion_percent?: number },
    ) => client.post<void>(`/api/v1/learning/materials/${materialId}/view`, body),
    createBank: (body: Record<string, unknown>) =>
      client.post<Record<string, unknown>>("/api/v1/learning/banks", body),
    addQuestion: (bankId: Uuid, body: Record<string, unknown>) =>
      client.post<Record<string, unknown>>(
        `/api/v1/learning/banks/${bankId}/questions`,
        body,
      ),
    questions: (
      bankId: Uuid,
      query: PageQuery & { topic?: string; kind?: string; include_answers?: boolean } = {},
    ) =>
      client.get<Page<Record<string, unknown>>>(
        `/api/v1/learning/banks/${bankId}/questions`,
        { query },
      ),
    assessment: (id: Uuid) =>
      client.get<RecordEnvelope<OnlineAssessment>>(
        `/api/v1/learning/assessments/${id}`,
      ),
    spaceAssessments: (spaceId: Uuid) =>
      client.get<OnlineAssessment[]>(`/api/v1/learning/spaces/${spaceId}/assessments`),
    myAttempts: () =>
      client.get<
        Array<{
          id: Uuid
          assessment_id: Uuid
          assessment_title: string
          assessment_kind: string
          attempt_number: number
          status: string
          started_at: Instant
          submitted_at: Instant | null
          expires_at: Instant | null
          total_marks: number
          score_visible: boolean
          total_score: number | null
          percentage: number | null
        }>
      >("/api/v1/learning/me/attempts"),
    createAssessment: (spaceId: Uuid, body: Record<string, unknown>) =>
      client.post<OnlineAssessment>(
        `/api/v1/learning/spaces/${spaceId}/assessments`,
        body,
      ),
    addItem: (assessmentId: Uuid, body: Record<string, unknown>) =>
      client.post<{ id: string; total_marks: number }>(
        `/api/v1/learning/assessments/${assessmentId}/items`,
        body,
      ),
    submitForReview: (id: Uuid) =>
      client.post<OnlineAssessment>(
        `/api/v1/learning/assessments/${id}/submit-for-review`,
      ),
    review: (id: Uuid, approve: boolean, comments?: string) =>
      client.post<OnlineAssessment>(`/api/v1/learning/assessments/${id}/review`, {
        approve,
        comments,
      }),
    open: (id: Uuid) =>
      client.post<OnlineAssessment>(`/api/v1/learning/assessments/${id}/open`),
    startAttempt: (assessmentId: Uuid, password?: string) =>
      client.post<Attempt>(`/api/v1/learning/assessments/${assessmentId}/attempts`, {
        password,
      }),
    paper: (attemptId: Uuid) =>
      client.get<PresentedQuestion[]>(`/api/v1/learning/attempts/${attemptId}/paper`),
    saveAnswer: (
      attemptId: Uuid,
      body: {
        question_id: Uuid
        answer: Record<string, unknown>
        seconds_spent?: number
        flagged?: boolean
      },
    ) => client.put<void>(`/api/v1/learning/attempts/${attemptId}/answers`, body),
    reportIntegrityEvent: (
      attemptId: Uuid,
      body: { kind: string; detail?: Record<string, unknown> },
    ) => client.post<void>(`/api/v1/learning/attempts/${attemptId}/integrity`, body),
    submitAttempt: (attemptId: Uuid) =>
      client.post<Attempt>(`/api/v1/learning/attempts/${attemptId}/submit`),
    markingQueue: (assessmentId: Uuid) =>
      client.get<
        Array<{
          response_id: Uuid
          attempt_id: Uuid
          question_id: Uuid
          question_kind: string
          question_stem: string
          marks_available: number
          answer: Record<string, unknown>
          rubric: Array<Record<string, unknown>>
          student_reference: string | null
        }>
      >(`/api/v1/learning/assessments/${assessmentId}/marking-queue`),
    markResponse: (
      responseId: Uuid,
      body: { marks: number; comment?: string; rubric_scores?: Array<Record<string, unknown>> },
    ) =>
      client.post<{ response_id: string; marks_awarded: number }>(
        `/api/v1/learning/responses/${responseId}/mark`,
        body,
      ),
    release: (id: Uuid) =>
      client.post<OnlineAssessment>(`/api/v1/learning/assessments/${id}/release`),
    pushMarks: (id: Uuid) =>
      client.post<{ written: number; skipped: Array<Record<string, unknown>>; component: string }>(
        `/api/v1/learning/assessments/${id}/push-marks`,
      ),
    submitAssignment: (
      assignmentId: Uuid,
      body: { attachment_ids?: Uuid[]; text_response?: string },
    ) =>
      client.post<Record<string, unknown>>(
        `/api/v1/learning/assignments/${assignmentId}/submissions`,
        body,
      ),
    markSubmission: (submissionId: Uuid, body: Record<string, unknown>) =>
      client.post<Record<string, unknown>>(
        `/api/v1/learning/submissions/${submissionId}/mark`,
        body,
      ),
    engagement: (offeringId: Uuid, week?: number) =>
      client.get<EngagementRow[]>(`/api/v1/learning/offerings/${offeringId}/engagement`, {
        query: { week_number: week },
      }),
    captureEngagement: (offeringId: Uuid, week: number) =>
      client.post<{ captured: number }>(
        `/api/v1/learning/offerings/${offeringId}/engagement/capture`,
        undefined,
        { query: { week_number: week } },
      ),
  },

  assessment: {
    markSheets: (
      query: PageQuery & { semester_id?: Uuid; status?: string; mine_only?: boolean } = {},
    ) => client.get<Page<MarkSheet>>("/api/v1/assessment/mark-sheets", { query }),
    generateMarkSheet: (courseOfferingId: Uuid) =>
      client.post<MarkSheet>("/api/v1/assessment/mark-sheets", undefined, {
        query: { course_offering_id: courseOfferingId },
      }),
    markSheet: (id: Uuid) =>
      client.get<RecordEnvelope<MarkSheet>>(`/api/v1/assessment/mark-sheets/${id}`),
    markSheetResults: (id: Uuid) =>
      client.get<CourseResult[]>(`/api/v1/assessment/mark-sheets/${id}/results`),
    enterMarks: (
      id: Uuid,
      entries: Array<{
        student_id: Uuid
        components: Record<string, number | null>
        exception?: string
      }>,
    ) => client.post<BulkResult>(`/api/v1/assessment/mark-sheets/${id}/marks`, { entries }),
    transition: (
      id: Uuid,
      action:
        | "submit"
        | "moderate"
        | "approve"
        | "faculty_approve"
        | "senate_approve"
        | "return",
      body: { note?: string; minute_reference?: string; adjustment?: number } = {},
    ) => client.post<MarkSheet>(`/api/v1/assessment/mark-sheets/${id}/${action}`, body),
    release: (body: {
      semester_id: Uuid
      programme_ids?: Uuid[]
      scope_description: string
      minute_reference?: string
    }) =>
      client.post<{
        id: string
        mark_sheets: number
        results: number
        students: number
        released_at: string | null
      }>("/api/v1/assessment/releases", body),
    myResults: (semesterId?: Uuid) =>
      client.get<CourseResult[]>("/api/v1/assessment/me/results", {
        query: { semester_id: semesterId },
      }),
    transcript: (studentId: Uuid) =>
      client.get<Record<string, unknown>>(
        `/api/v1/assessment/students/${studentId}/transcript`,
      ),
    issueTranscript: (studentId: Uuid, body: Record<string, unknown>) =>
      client.post<Record<string, unknown>>(
        `/api/v1/assessment/students/${studentId}/transcript/issue`,
        body,
      ),
    conferAward: (studentId: Uuid, body: Record<string, unknown>) =>
      client.post<Award>(`/api/v1/assessment/students/${studentId}/award`, body),
    computeSemesterResults: (semesterId: Uuid, programmeId?: Uuid) =>
      client.post<{
        computed: number
        requiring_board_confirmation: Array<Record<string, unknown>>
      }>("/api/v1/assessment/semester-results/compute", undefined, {
        query: { semester_id: semesterId, programme_id: programmeId },
      }),
  },

  finance: {
    statement: (studentId: Uuid) =>
      client.get<StudentStatement>(`/api/v1/finance/students/${studentId}/statement`),
    myStatement: () => client.get<StudentStatement>("/api/v1/finance/me/statement"),
    invoices: (
      query: PageQuery & { student_id?: Uuid; status?: string; overdue_only?: boolean } = {},
    ) => client.get<Page<Invoice>>("/api/v1/finance/invoices", { query }),
    raiseSemesterInvoice: (body: { student_id: Uuid; semester_id: Uuid }) =>
      client.post<Invoice>("/api/v1/finance/invoices/semester", body),
    recordPayment: (body: Record<string, unknown>) =>
      client.post<Payment>("/api/v1/finance/payments", body),
    unmatchedPayments: (query: PageQuery = {}) =>
      client.get<Page<Payment>>("/api/v1/finance/payments/unmatched", { query }),
    matchPayment: (paymentId: Uuid, studentId: Uuid) =>
      client.post<Payment>(`/api/v1/finance/payments/${paymentId}/match`, {
        student_id: studentId,
      }),
    reversePayment: (paymentId: Uuid, reason: string) =>
      client.post<Payment>(`/api/v1/finance/payments/${paymentId}/reverse`, { reason }),
    raiseWaiver: (body: Record<string, unknown>) =>
      client.post<Record<string, unknown>>("/api/v1/finance/waivers", body),
    releaseWaiver: (waiverId: Uuid, reason: string) =>
      client.post<Record<string, unknown>>(
        `/api/v1/finance/waivers/${waiverId}/release`,
        { reason },
      ),
    feeStructures: (query: PageQuery & { academic_year_id?: Uuid } = {}) =>
      client.get<Page<Record<string, unknown>>>("/api/v1/finance/fee-structures", { query }),
    trialBalance: (periodCode: string) =>
      client.get<{
        period_code: string
        accounts: Array<{ account_code: string; balance_minor: number; entries: number }>
        total_minor: number
        balanced: boolean
      }>(`/api/v1/finance/trial-balance/${periodCode}`),
    /** The institution's published late-payment terms. */
    latePaymentRules: (query: { academic_year_id?: Uuid } = {}) =>
      client.get<LatePaymentRuleRow[]>("/api/v1/finance/late-payment-rules", { query }),
    createLatePaymentRule: (body: Record<string, unknown>) =>
      client.post<LatePaymentRuleRow>("/api/v1/finance/late-payment-rules", body),
    approveLatePaymentRule: (id: Uuid) =>
      client.post<LatePaymentRuleRow>(`/api/v1/finance/late-payment-rules/${id}/approve`),
    /** Surcharges applied, with the arithmetic that produced them. */
    penalties: (query: PageQuery & { student_id?: Uuid } = {}) =>
      client.get<Page<PenaltyChargeRow>>("/api/v1/finance/penalties", { query }),
    reversePenalty: (id: Uuid, reason: string) =>
      client.post<PenaltyChargeRow>(`/api/v1/finance/penalties/${id}/reverse`, { reason }),
    requestPaymentPlan: (body: {
      invoice_id: Uuid
      instalments?: number
      student_id?: Uuid
      reason?: string
      first_due_on?: string
      deposit_minor?: number
      interval_days?: number
    }) => client.post<PaymentPlanRow>("/api/v1/finance/payment-plans", body),
    paymentPlans: (query: PageQuery & { student_id?: Uuid; status?: string } = {}) =>
      client.get<Page<PaymentPlanRow>>("/api/v1/finance/payment-plans", { query }),
    approvePaymentPlan: (id: Uuid, body: { reason: string; missed_allowance?: number }) =>
      client.post<PaymentPlanRow>(`/api/v1/finance/payment-plans/${id}/approve`, body),
    reminders: (query: PageQuery & { student_id?: Uuid } = {}) =>
      client.get<Page<DunningNoticeRow>>("/api/v1/finance/reminders", { query }),
    /** What is blocked, under which rule, and what would lift it. */
    blocks: (studentId: Uuid) =>
      client.get<BlockState>(`/api/v1/finance/blocks/${studentId}`),
    runLatePayment: (dryRun = true) =>
      client.post<Record<string, unknown>>("/api/v1/finance/jobs/late-payment", {
        dry_run: dryRun,
      }),
  },

  people: {
    list: (query: PageQuery & { unit_id?: Uuid; category?: string; search?: string } = {}) =>
      client.get<Page<Staff>>("/api/v1/people", { query }),
    get: (id: Uuid) => client.get<RecordEnvelope<Staff>>(`/api/v1/people/${id}`),
    update: (id: Uuid, body: Partial<Staff>) =>
      client.patch<Staff>(`/api/v1/people/${id}`, body),
    requestLeave: (body: Record<string, unknown>) =>
      client.post<LeaveRequest>("/api/v1/people/leave", body),
    decideLeave: (
      id: Uuid,
      body: { approve: boolean; stage?: "supervisor" | "hr"; note?: string },
    ) => client.post<LeaveRequest>(`/api/v1/people/leave/${id}/decide`, body),
    workload: (semesterId: Uuid, unitId?: Uuid) =>
      client.get<Array<Record<string, unknown>>>("/api/v1/people/workload", {
        query: { semester_id: semesterId, unit_id: unitId },
      }),
    recomputeWorkload: (semesterId: Uuid) =>
      client.post<{ staff_updated: number }>(
        "/api/v1/people/workload/recompute",
        undefined,
        { query: { semester_id: semesterId } },
      ),
  },

  governance: {
    audit: (
      query: PageQuery & {
        actor_id?: Uuid
        resource_type?: string
        resource_id?: string
        student_id?: Uuid
        category?: string
        outcome?: string
        action?: string
        since?: string
        until?: string
      } = {},
    ) => client.get<Page<AuditEvent>>("/api/v1/governance/audit", { query }),
    myAudit: (query: PageQuery = {}) =>
      client.get<Page<AuditEvent>>("/api/v1/governance/audit/me", { query }),
    denialSummary: (hours = 24) =>
      client.get<{
        window_hours: number
        by_actor: Array<{
          actor_id: string | null
          actor_label: string | null
          denials: number
          distinct_resources: number
          looks_like_enumeration: boolean
        }>
        by_policy: Array<{ policy: string; action: string; denials: number }>
      }>("/api/v1/governance/audit/denials", { query: { hours } }),
    accessLog: (query: PageQuery & { student_id?: Uuid; actor_id?: Uuid } = {}) =>
      client.get<Page<Record<string, unknown>>>("/api/v1/governance/access-log", { query }),
    policies: () => client.get<PolicyOverlay[]>("/api/v1/governance/policies"),
    createPolicy: (body: Record<string, unknown>) =>
      client.post<PolicyOverlay>("/api/v1/governance/policies", body),
    setPolicyEnabled: (id: Uuid, enabled: boolean, reason: string) =>
      client.post<PolicyOverlay>(`/api/v1/governance/policies/${id}/enable`, {
        enabled,
        reason,
      }),
    reports: (kind?: string) =>
      client.get<Array<Record<string, unknown>>>("/api/v1/governance/reports", {
        query: { kind },
      }),
    runReport: (id: Uuid, body: Record<string, unknown>) =>
      client.post<{ run_id: string; status: string }>(
        `/api/v1/governance/reports/${id}/run`,
        body,
      ),
    statutoryReturns: () =>
      client.get<Array<Record<string, unknown>>>("/api/v1/governance/statutory-returns"),
  },

  developers: {
    clients: (query: PageQuery & { mine_only?: boolean } = {}) =>
      client.get<Page<ApiClientRecord>>("/api/v1/developers/clients", { query }),
    registerClient: (body: Record<string, unknown>) =>
      client.post<ApiClientRecord>("/api/v1/developers/clients", body),
    grantScopes: (id: Uuid, body: { granted_scopes: string[]; approve: boolean; reason: string }) =>
      client.post<ApiClientRecord>(`/api/v1/developers/clients/${id}/scopes`, body),
    createKey: (clientId: Uuid, body: { name: string; scopes?: string[]; ttl_days?: number }) =>
      client.post<ApiKeyRecord & { secret: string; warning: string }>(
        `/api/v1/developers/clients/${clientId}/keys`,
        body,
      ),
    rotateKey: (keyId: Uuid) =>
      client.post<ApiKeyRecord & { secret: string }>(
        `/api/v1/developers/keys/${keyId}/rotate`,
      ),
    revokeKey: (keyId: Uuid, reason: string) =>
      client.post<ApiKeyRecord>(`/api/v1/developers/keys/${keyId}/revoke`, { reason }),
    createWebhook: (clientId: Uuid, body: { name: string; url: string; event_types: string[] }) =>
      client.post<Record<string, unknown> & { signing_secret: string }>(
        `/api/v1/developers/clients/${clientId}/webhooks`,
        body,
      ),
    deliveries: (webhookId: Uuid, query: PageQuery & { failed_only?: boolean } = {}) =>
      client.get<Page<Record<string, unknown>>>(
        `/api/v1/developers/webhooks/${webhookId}/deliveries`,
        { query },
      ),
    logs: (clientId: Uuid, query: PageQuery & { errors_only?: boolean } = {}) =>
      client.get<Page<Record<string, unknown>>>(
        `/api/v1/developers/clients/${clientId}/logs`,
        { query },
      ),
    usage: (clientId: Uuid, days = 7) =>
      client.get<{ window_days: number; paths: Array<Record<string, unknown>> }>(
        `/api/v1/developers/clients/${clientId}/usage`,
        { query: { days } },
      ),
    eventTypes: () =>
      client.get<Array<{ type: string; description: string }>>(
        "/api/v1/developers/event-types",
      ),
  },

  /** The genuinely public endpoints. No token required. */
  public: {
    institution: () => client.get<Institution>("/api/v1/public/institution"),
    programmes: () =>
      client.get<Array<Record<string, unknown>>>("/api/v1/public/programmes"),
    admissionSchemes: () =>
      client.get<AdmissionScheme[]>("/api/v1/public/admission-schemes"),
    verify: (serial: string) =>
      client.get<{
        found: boolean
        valid: boolean
        holder_name: string | null
        award_title: string | null
        classification: string | null
        conferred_on: string | null
        serial_number: string | null
        revoked: boolean
        institution: string | null
      }>(`/api/v1/public/verify/${encodeURIComponent(serial)}`),
  },


  /**
   * The library.
   *
   * The split in this namespace mirrors the one in the policy bundle: the
   * catalogue is readable by any member, and circulation is not. Who borrowed
   * what is among the most sensitive data a university holds.
   */
  library: {
    search: (
      query: PageQuery & {
        q?: string
        material_kind?: string
        course_id?: Uuid
        classification?: string
      } = {},
    ) => client.get<Page<CatalogueRecordRow>>("/api/v1/library/records", { query }),
    createRecord: (body: Record<string, unknown>) =>
      client.post<CatalogueRecordRow>("/api/v1/library/records", body),
    record: (recordId: Uuid) =>
      client.get<CatalogueRecordRow>(`/api/v1/library/records/${recordId}`),
    availability: (recordId: Uuid) =>
      client.get<CatalogueAvailability>(
        `/api/v1/library/records/${recordId}/availability`,
      ),
    copies: (recordId: Uuid) =>
      client.get<CatalogueCopyRow[]>(`/api/v1/library/records/${recordId}/copies`),
    addCopy: (recordId: Uuid, body: Record<string, unknown>) =>
      client.post<CatalogueCopyRow>(
        `/api/v1/library/records/${recordId}/copies`,
        body,
      ),
    members: (query: PageQuery & { q?: string; with_debt?: boolean } = {}) =>
      client.get<Page<LibraryMemberRow>>("/api/v1/library/members", { query }),
    createMember: (body: Record<string, unknown>) =>
      client.post<LibraryMemberRow>("/api/v1/library/members", body),
    /** The reader's own record: what is out, what is due, what is owed. */
    myMembership: () => client.get<MyLibraryRecord>("/api/v1/library/me/membership"),
    /** Two scans: a book and a card. */
    issue: (body: { barcode: string; membership_number: string; due_on?: string }) =>
      client.post<LoanRow>("/api/v1/library/loans", body),
    return: (body: { barcode: string; condition?: string }) =>
      client.post<{
        loan_id: Uuid
        returned_on: string | null
        copy_status: string
        on_hold_shelf: boolean
        fine: { amount_minor: number; days_overdue: number | null; reason: string } | null
      }>("/api/v1/library/loans/return", body),
    renew: (loanId: Uuid) => client.post<LoanRow>(`/api/v1/library/loans/${loanId}/renew`),
    declareLost: (loanId: Uuid, body: { reason: string; replacement_minor?: number }) =>
      client.post<{ fine_id: Uuid; amount_minor: number }>(
        `/api/v1/library/loans/${loanId}/declare-lost`,
        body,
      ),
    loans: (query: PageQuery & { member_id?: Uuid; overdue_only?: boolean } = {}) =>
      client.get<Page<LoanRow>>("/api/v1/library/loans", { query }),
    reserve: (recordId: Uuid) =>
      client.post<Record<string, unknown>>(
        `/api/v1/library/records/${recordId}/reservations`,
      ),
    cancelReservation: (reservationId: Uuid) =>
      client.post<Record<string, unknown>>(
        `/api/v1/library/reservations/${reservationId}/cancel`,
      ),
    fines: (query: PageQuery & { member_id?: Uuid; unpaid_only?: boolean } = {}) =>
      client.get<Page<LibraryFineRow>>("/api/v1/library/fines", { query }),
    waiveFine: (fineId: Uuid, reason: string) =>
      client.post<LibraryFineRow>(`/api/v1/library/fines/${fineId}/waive`, { reason }),
    acquisitions: (query: PageQuery & { status?: string; mine_only?: boolean } = {}) =>
      client.get<Page<AcquisitionRow>>("/api/v1/library/acquisitions", { query }),
    requestAcquisition: (body: Record<string, unknown>) =>
      client.post<AcquisitionRow>("/api/v1/library/acquisitions", body),
    eResources: (query: { expiring_days?: number } = {}) =>
      client.get<EResourceRow[]>("/api/v1/library/e-resources", { query }),
    branches: () => client.get<Array<Record<string, unknown>>>("/api/v1/library/branches"),
    clearance: (studentId: Uuid) =>
      client.get<LibraryClearance>(`/api/v1/library/clearance/${studentId}`),
    runOverdue: () =>
      client.post<Record<string, number>>("/api/v1/library/jobs/accrue-overdue"),
  },

  /** Quality assurance: delivery, attendance, evaluations, observations, audits. */
  quality: {
    generateSessions: (offeringId: Uuid, body: Record<string, unknown>) =>
      client.post<{ created: number }>(
        `/api/v1/quality/offerings/${offeringId}/sessions`,
        body,
      ),
    sessions: (offeringId: Uuid, query: PageQuery & { status?: string } = {}) =>
      client.get<Page<ClassSessionRow>>(
        `/api/v1/quality/offerings/${offeringId}/sessions`,
        { query },
      ),
    markRegister: (sessionId: Uuid, body: Record<string, unknown>) =>
      client.post<Record<string, unknown>>(
        `/api/v1/quality/sessions/${sessionId}/register`,
        body,
      ),
    closeRegister: (sessionId: Uuid) =>
      client.post<ClassSessionRow>(`/api/v1/quality/sessions/${sessionId}/close`),
    cancelSession: (sessionId: Uuid, body: { reason: string; announced?: boolean }) =>
      client.post<ClassSessionRow>(
        `/api/v1/quality/sessions/${sessionId}/cancel`,
        body,
      ),
    checkIn: (sessionId: Uuid) =>
      client.post<void>(`/api/v1/quality/sessions/${sessionId}/check-in`),
    offeringAttendance: (offeringId: Uuid) =>
      client.get<AttendanceRow[]>(`/api/v1/quality/offerings/${offeringId}/attendance`),
    myAttendance: () => client.get<MyAttendanceRow[]>("/api/v1/quality/me/attendance"),
    disputeAttendance: (attendanceId: Uuid, reason: string) =>
      client.post<Record<string, unknown>>(
        `/api/v1/quality/attendance/${attendanceId}/dispute`,
        { reason },
      ),
    resolveDispute: (attendanceId: Uuid, body: { status: string; reason: string }) =>
      client.post<Record<string, unknown>>(
        `/api/v1/quality/attendance/${attendanceId}/resolve`,
        body,
      ),
    /** Is the teaching that was promised actually happening? */
    delivery: (semesterId: Uuid) =>
      client.get<DeliveryReport>("/api/v1/quality/delivery", {
        query: { semester_id: semesterId },
      }),
    instruments: (query: { published_only?: boolean } = {}) =>
      client.get<EvaluationInstrumentRow[]>("/api/v1/quality/instruments", { query }),
    createInstrument: (body: Record<string, unknown>) =>
      client.post<EvaluationInstrumentRow>("/api/v1/quality/instruments", body),
    publishInstrument: (id: Uuid) =>
      client.post<EvaluationInstrumentRow>(
        `/api/v1/quality/instruments/${id}/publish`,
      ),
    evaluations: (
      query: PageQuery & {
        semester_id?: Uuid
        course_offering_id?: Uuid
        status?: string
        mine_only?: boolean
      } = {},
    ) => client.get<Page<CourseEvaluationRow>>("/api/v1/quality/evaluations", { query }),
    createEvaluation: (body: Record<string, unknown>) =>
      client.post<CourseEvaluationRow>("/api/v1/quality/evaluations", body),
    openEvaluation: (id: Uuid, studentIds: Uuid[]) =>
      client.post<CourseEvaluationRow>(`/api/v1/quality/evaluations/${id}/open`, {
        student_ids: studentIds,
      }),
    /** Returns nothing at all — not even an id. See the endpoint's note. */
    submitResponse: (id: Uuid, body: Record<string, unknown>) =>
      client.post<void>(`/api/v1/quality/evaluations/${id}/responses`, body),
    myEvaluations: () =>
      client.get<
        Array<{
          evaluation_id: Uuid
          instrument_id: Uuid
          course_offering_id: Uuid
          opens_at: Instant
          closes_at: Instant
          answered: boolean
          declined: boolean
        }>
      >("/api/v1/quality/me/evaluations"),
    closeEvaluation: (id: Uuid) =>
      client.post<CourseEvaluationRow>(`/api/v1/quality/evaluations/${id}/close`),
    results: (id: Uuid, query: { include_comments?: boolean } = {}) =>
      client.get<EvaluationResults>(`/api/v1/quality/evaluations/${id}/results`, {
        query,
      }),
    reflect: (id: Uuid, body: { reflection: string; action_plan?: string }) =>
      client.post<CourseEvaluationRow>(`/api/v1/quality/evaluations/${id}/reflect`, body),
    observations: (query: PageQuery & { staff_id?: Uuid; mine_only?: boolean } = {}) =>
      client.get<Page<ObservationRow>>("/api/v1/quality/observations", { query }),
    createObservation: (body: Record<string, unknown>) =>
      client.post<ObservationRow>("/api/v1/quality/observations", body),
    submitObservation: (id: Uuid) =>
      client.post<ObservationRow>(`/api/v1/quality/observations/${id}/submit`),
    acknowledgeObservation: (id: Uuid, response?: string) =>
      client.post<ObservationRow>(`/api/v1/quality/observations/${id}/acknowledge`, {
        response,
      }),
    audits: (query: PageQuery & { status?: string; open_findings_only?: boolean } = {}) =>
      client.get<Page<QualityAuditRow>>("/api/v1/quality/audits", { query }),
    createAudit: (body: Record<string, unknown>) =>
      client.post<QualityAuditRow>("/api/v1/quality/audits", body),
    closeFinding: (auditId: Uuid, body: { finding_code: string; reason: string }) =>
      client.post<QualityAuditRow>(
        `/api/v1/quality/audits/${auditId}/close-finding`,
        body,
      ),
    indicators: (
      query: PageQuery & { code?: string; unit_id?: Uuid; below_target_only?: boolean } = {},
    ) => client.get<Page<QualityIndicatorRow>>("/api/v1/quality/indicators", { query }),
    recordIndicator: (body: Record<string, unknown>) =>
      client.post<QualityIndicatorRow>("/api/v1/quality/indicators", body),
    reportingThreshold: () =>
      client.get<{ minimum_responses: number; reason: string }>(
        "/api/v1/quality/reporting-threshold",
      ),
  },

  /**
   * Student elections.
   *
   * There is no method here that reads a ballot, and there is no endpoint for
   * one either. The count is what an election needs; the ability to read a
   * single ballot is the ability to be leaned on for it.
   */
  elections: {
    list: (query: PageQuery & { status?: string } = {}) =>
      client.get<Page<ElectionRow>>("/api/v1/elections", { query }),
    get: (id: Uuid) => client.get<ElectionRow>(`/api/v1/elections/${id}`),
    create: (body: Record<string, unknown>) =>
      client.post<ElectionRow>("/api/v1/elections", body),
    publish: (id: Uuid, minuteReference?: string) =>
      client.post<ElectionRow>(`/api/v1/elections/${id}/publish`, {
        minute_reference: minuteReference,
      }),
    candidates: (id: Uuid, query: { approved_only?: boolean } = {}) =>
      client.get<CandidateRow[]>(`/api/v1/elections/${id}/candidates`, { query }),
    nominate: (body: Record<string, unknown>) =>
      client.post<CandidateRow>("/api/v1/elections/nominations", body),
    vet: (candidateId: Uuid, body: { approve: boolean; reason?: string }) =>
      client.post<CandidateRow>(`/api/v1/elections/candidates/${candidateId}/vet`, body),
    withdraw: (candidateId: Uuid, reason?: string) =>
      client.post<CandidateRow>(
        `/api/v1/elections/candidates/${candidateId}/withdraw`,
        { reason },
      ),
    buildRoll: (id: Uuid) =>
      client.post<Record<string, number>>(`/api/v1/elections/${id}/roll`),
    drawBallotOrder: (id: Uuid, seed: number) =>
      client.post<Record<string, number>>(`/api/v1/elections/${id}/ballot-order`, { seed }),
    startCampaign: (id: Uuid) =>
      client.post<ElectionRow>(`/api/v1/elections/${id}/campaign`),
    openPoll: (id: Uuid) => client.post<ElectionRow>(`/api/v1/elections/${id}/open`),
    closePoll: (id: Uuid) => client.post<ElectionRow>(`/api/v1/elections/${id}/close`),
    /** What this voter may do, and why not if they may not. */
    myEntitlement: (id: Uuid) =>
      client.get<VoterEntitlement>(`/api/v1/elections/${id}/me`),
    vote: (id: Uuid, choices: Record<string, Uuid[]>, via = "portal") =>
      client.post<BallotReceipt>(`/api/v1/elections/${id}/vote`, { choices, via }),
    /** Confirms a ballot is counted. Never returns the choice. */
    verifyReceipt: (token: string) =>
      client.get<ReceiptCheck>(`/api/v1/elections/receipts/${encodeURIComponent(token)}`),
    turnout: (id: Uuid) => client.get<TurnoutSnapshot>(`/api/v1/elections/${id}/turnout`),
    count: (id: Uuid) =>
      client.get<Array<Record<string, unknown>>>(`/api/v1/elections/${id}/count`),
    declare: (id: Uuid, tieBreakNotes: Record<string, string> = {}) =>
      client.post<ElectionResultRow[]>(`/api/v1/elections/${id}/declare`, {
        tie_break_notes: tieBreakNotes,
      }),
    results: (id: Uuid) =>
      client.get<ElectionResultRow[]>(`/api/v1/elections/${id}/results`),
    petitions: (id: Uuid) =>
      client.get<ElectionPetitionRow[]>(`/api/v1/elections/${id}/petitions`),
    filePetition: (body: Record<string, unknown>) =>
      client.post<ElectionPetitionRow>("/api/v1/elections/petitions", body),
  },

  /** Life-cycle events: special examinations, cards, transfers, time off. */
  lifecycle: {
    lodgeSpecialExam: (body: Record<string, unknown>) =>
      client.post<SpecialExamRow>("/api/v1/lifecycle/special-exams", body),
    specialExams: (
      query: PageQuery & { status?: string; semester_id?: Uuid; mine_only?: boolean } = {},
    ) => client.get<Page<SpecialExamRow>>("/api/v1/lifecycle/special-exams", { query }),
    specialExam: (id: Uuid) =>
      client.get<RecordEnvelope<SpecialExamRow>>(
        `/api/v1/lifecycle/special-exams/${id}`,
      ),
    verifyEvidence: (id: Uuid) =>
      client.post<SpecialExamRow>(
        `/api/v1/lifecycle/special-exams/${id}/verify-evidence`,
      ),
    recommendSpecialExam: (id: Uuid, note?: string) =>
      client.post<SpecialExamRow>(`/api/v1/lifecycle/special-exams/${id}/recommend`, {
        note,
      }),
    decideSpecialExam: (
      id: Uuid,
      body: { grant: boolean; kind?: string; note?: string; minute_reference?: string },
    ) => client.post<SpecialExamRow>(`/api/v1/lifecycle/special-exams/${id}/decide`, body),
    issueIdCard: (body: Record<string, unknown>) =>
      client.post<IdCardRow>("/api/v1/lifecycle/id-cards", body),
    myIdCards: () => client.get<IdCardRow[]>("/api/v1/lifecycle/me/id-cards"),
    reportCardLost: (cardId: Uuid, stolen = false) =>
      client.post<IdCardRow>(`/api/v1/lifecycle/id-cards/${cardId}/report-lost`, {
        stolen,
      }),
    verifyIdCard: (code: string) =>
      client.get<CardVerification>("/api/v1/lifecycle/id-cards/verify", {
        query: { code },
      }),
    issueExamCard: (body: {
      registration_id: Uuid
      session?: string
      override_reason?: string
    }) => client.post<ExamCardRow>("/api/v1/lifecycle/exam-cards", body),
    myExamCards: () => client.get<MyExamCardRow[]>("/api/v1/lifecycle/me/exam-cards"),
    verifyExamCard: (code: string) =>
      client.get<CardVerification>("/api/v1/lifecycle/exam-cards/verify", {
        query: { code },
      }),
    revokeExamCard: (cardId: Uuid, reason: string) =>
      client.post<ExamCardRow>(`/api/v1/lifecycle/exam-cards/${cardId}/revoke`, {
        reason,
      }),
    myTimeOff: () => client.get<TimeOffStanding>("/api/v1/lifecycle/me/time-off"),
    lodgeTransfer: (body: Record<string, unknown>) =>
      client.post<InstitutionTransferRow>("/api/v1/lifecycle/transfers", body),
    transfers: (query: PageQuery & { direction?: string; status?: string } = {}) =>
      client.get<Page<InstitutionTransferRow>>("/api/v1/lifecycle/transfers", { query }),
    /** A student's own transfers out. `transfers` is staff-only. */
    myTransfers: () =>
      client.get<InstitutionTransferRow[]>("/api/v1/lifecycle/me/transfers"),
    assessTransfer: (
      id: Uuid,
      body: {
        assessment: Array<Record<string, unknown>>
        total_programme_credits?: number
      },
    ) => client.post<InstitutionTransferRow>(`/api/v1/lifecycle/transfers/${id}/assess`, body),
    approveTransfer: (id: Uuid, body: { minute_reference?: string; note?: string } = {}) =>
      client.post<InstitutionTransferRow>(
        `/api/v1/lifecycle/transfers/${id}/approve`,
        body,
      ),
    issueTransferPapers: (id: Uuid) =>
      client.post<InstitutionTransferRow>(
        `/api/v1/lifecycle/transfers/${id}/issue-papers`,
      ),
  },

  /** Control plane. Only reachable with a platform token. */
  platform: {
    login: (email: string, password: string) =>
      client.post<{ access_token: string; permissions: string[]; mfa_enrolled: boolean }>(
        "/api/v1/platform/login",
        { email, password },
      ),
    tenants: (query: PageQuery & { status?: string } = {}) =>
      client.get<Page<Record<string, unknown>>>("/api/v1/platform/tenants", { query }),
    provisionTenant: (body: Record<string, unknown>) =>
      client.post<Record<string, unknown>>("/api/v1/platform/tenants", body),
    setTenantStatus: (id: Uuid, status: string, reason: string) =>
      client.post<Record<string, unknown>>(`/api/v1/platform/tenants/${id}/status`, {
        status,
        reason,
      }),
    migrationStatus: () =>
      client.get<Array<Record<string, unknown>>>(
        "/api/v1/platform/tenants/migration-status",
      ),
    migrateAll: (body: { revision?: string; concurrency?: number; only?: string[] }) =>
      client.post<Record<string, unknown>>("/api/v1/platform/tenants/migrate", body),
    fleet: () => client.get<Array<Record<string, unknown>>>("/api/v1/platform/fleet"),
    reloadPolicies: () =>
      client.post<{ policies: number; rules: number; bundle_version: string }>(
        "/api/v1/platform/policies/reload",
      ),
  },
})

export type Api = ReturnType<typeof api>
