"""Quality assurance.

The module answers one question in four ways: *is the teaching that was
promised actually happening, and is it any good?*

* `ClassSession` and `SessionAttendance` — did the class meet, who taught it,
  and who was there. Session-level, unlike `assessment.AttendanceRecord`,
  which holds the rolled-up percentage the examination gate reads. Both
  exist on purpose: the gate needs one number per student per course and
  reads it constantly; quality assurance needs the sessions, and asks rarely.
* `TeachingObservation` — a peer or a QA officer sat in and scored it.
* `CourseEvaluation` and its responses — what the students said, anonymously.
* `QualityAudit` — a periodic review of a unit or a programme against
  standards, with findings that have owners and dates.

The recurring design decision here is *anonymity*. Evaluation responses carry
no student identity at all, not even a hashed one, and the module refuses to
show any breakdown of a cohort small enough to identify the respondent. A
student who believes their lecturer can work out who wrote a comment does not
write one, and an evaluation nobody answers honestly is worse than none: it
produces confident numbers that are wrong.
"""

from __future__ import annotations

import uuid
from datetime import date, datetime
from enum import StrEnum
from typing import TYPE_CHECKING, Any

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import ARRAY, JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from acmis.core.models import TenantRecord

if TYPE_CHECKING:
    # Annotations only; the mapper resolves both by name through its own
    # registry, so quality does not import curriculum or people at runtime.
    from acmis.modules.curriculum.models import CourseOffering
    from acmis.modules.people.models import Staff

#: Below this many responses, no breakdown is shown — a "3 of 4 students
#: disagreed" on a class of four names the dissenter. The threshold is a
#: constant rather than a setting because it protects the respondent, and an
#: institution that could lower it would be asked to.
MIN_RESPONSES_TO_REPORT = 5


class AttendanceStatus(StrEnum):
    PRESENT = "present"
    ABSENT = "absent"
    LATE = "late"
    #: Absent with a reason the institution accepts, so it does not count
    #: against the examination-eligibility threshold.
    EXCUSED = "excused"


class ClassSession(TenantRecord):
    """One scheduled meeting of one course offering.

    Generated from the timetable for the semester and then *marked up* with
    what actually happened. The difference between the two is the point: a
    session planned and not held is a teaching-delivery failure, and it is
    invisible in any system that only records attendance for classes that
    took place.
    """

    __tablename__ = "class_session"

    course_offering_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("course_offering.id", ondelete="CASCADE"), nullable=False, index=True
    )
    semester_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("semester.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    timetable_slot_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("timetable_slot.id", ondelete="SET NULL")
    )
    #: `lecture`, `tutorial`, `practical`, `seminar`, `field`, `clinical`,
    #: `revision`.
    kind: Mapped[str] = mapped_column(String(20), nullable=False, default="lecture")
    session_date: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    starts_at: Mapped[str] = mapped_column(String(5), nullable=False)
    ends_at: Mapped[str] = mapped_column(String(5), nullable=False)
    week_number: Mapped[int | None] = mapped_column(Integer, index=True)
    room_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("room.id", ondelete="SET NULL"))
    #: Who was timetabled to teach it, and who actually did. A substitution is
    #: normal and fine; a substitution nobody recorded is how a course ends up
    #: taught by nobody in particular.
    scheduled_staff_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("staff.id", ondelete="SET NULL"), index=True
    )
    delivered_by_staff_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("staff.id", ondelete="SET NULL"), index=True
    )
    #: `planned`, `held`, `cancelled`, `rescheduled`, `not_held`.
    #: `not_held` is distinct from `cancelled`: cancelled was announced,
    #: not_held means the class simply did not happen.
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="planned", index=True)
    topic: Mapped[str | None] = mapped_column(String(300))
    #: Where the session sits against the approved course outline. A course
    #: three topics behind in week ten will not be finished, and that is worth
    #: knowing in week ten rather than at the examination.
    syllabus_reference: Mapped[str | None] = mapped_column(String(120))
    cancellation_reason: Mapped[str | None] = mapped_column(String(300))
    rescheduled_to_session_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    #: Stamped when the register is closed. An open register can still be
    #: edited; a closed one is the record.
    register_closed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    register_closed_by_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    expected_students: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    present_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    #: Cached percentage for the offering's attendance chart.
    attendance_percent: Mapped[float | None] = mapped_column(Numeric(5, 2))
    note: Mapped[str | None] = mapped_column(Text)

    attendances: Mapped[list[SessionAttendance]] = relationship(
        back_populates="session", cascade="all, delete-orphan"
    )
    #: The unit scope every rule in this module matches on lives on the
    #: offering, not here.
    course_offering: Mapped[CourseOffering] = relationship(
        "CourseOffering", viewonly=True, lazy="joined"
    )

    __table_args__ = (
        UniqueConstraint(
            "course_offering_id", "session_date", "starts_at", name="uq_class_session"
        ),
        Index("ix_class_session_delivery", "semester_id", "status"),
    )


class SessionAttendance(TenantRecord):
    """One student at one session.

    The only place the system holds a per-session mark. It rolls up into
    `assessment.AttendanceRecord`, which is what the examination gate reads —
    so this table can be queried freely without the gate paying for it.
    """

    __tablename__ = "session_attendance"

    session_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("class_session.id", ondelete="CASCADE"), nullable=False, index=True
    )
    student_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("student.id", ondelete="CASCADE"), nullable=False, index=True
    )
    course_offering_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("course_offering.id", ondelete="CASCADE"), nullable=False, index=True
    )
    status: Mapped[str] = mapped_column(
        String(20), nullable=False, default=AttendanceStatus.PRESENT, index=True
    )
    #: `roll_call`, `signature`, `card_scan`, `qr_code`, `biometric`,
    #: `self_service`, `import`. Recorded because the methods differ in how
    #: much they can be trusted: a self-service tap from off campus is not a
    #: roll call, and a dispute turns on which one it was.
    method: Mapped[str] = mapped_column(String(20), nullable=False, default="roll_call")
    marked_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    marked_by_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    minutes_late: Mapped[int | None] = mapped_column(Integer)
    #: An excusal needs a reason; without one, `excused` is just an absence
    #: somebody was kind about, and the threshold stops meaning anything.
    excuse_reason: Mapped[str | None] = mapped_column(String(300))
    excuse_attachment_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    excused_by_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    #: Set when a student challenges a mark. The correction is an edit with a
    #: trail, not a silent overwrite.
    disputed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    dispute_note: Mapped[str | None] = mapped_column(Text)
    resolved_by_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))

    session: Mapped[ClassSession] = relationship(back_populates="attendances")

    __table_args__ = (
        UniqueConstraint("session_id", "student_id", name="uq_session_attendance"),
        Index("ix_attendance_student_offering", "student_id", "course_offering_id", "status"),
    )


class StaffAttendance(TenantRecord):
    """A member of staff's presence, where the institution records it.

    Teaching delivery is captured on `ClassSession.delivered_by_staff_id` —
    that is the academically meaningful measure, and it is a by-product of
    marking a register. This table is for the separate, administrative
    question of duty attendance: a clinical supervisor on a ward rota, a
    part-time lecturer paid by the session, an officer on a shift.

    Deliberately not a general staff time clock. Clocking academics in and out
    measures presence rather than teaching, and it is teaching the institution
    is accountable for.
    """

    __tablename__ = "staff_attendance"

    staff_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("staff.id", ondelete="CASCADE"), nullable=False, index=True
    )
    attendance_date: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    #: `teaching`, `duty`, `clinical`, `invigilation`, `field`, `meeting`.
    kind: Mapped[str] = mapped_column(String(20), nullable=False, default="duty")
    class_session_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("class_session.id", ondelete="SET NULL"), index=True
    )
    exam_sitting_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    checked_in_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    checked_out_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    hours: Mapped[float | None] = mapped_column(Numeric(5, 2))
    status: Mapped[str] = mapped_column(
        String(20), nullable=False, default=AttendanceStatus.PRESENT, index=True
    )
    #: For a session-paid contract, whether this session has been passed to
    #: payroll. The link is what stops a part-timer being paid twice, or not
    #: at all.
    payable: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    payroll_period: Mapped[str | None] = mapped_column(String(20), index=True)
    absence_reason: Mapped[str | None] = mapped_column(String(300))
    leave_request_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    recorded_by_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    note: Mapped[str | None] = mapped_column(Text)

    staff: Mapped[Staff] = relationship("Staff", viewonly=True, lazy="joined")

    __table_args__ = (Index("ix_staff_attendance_period", "staff_id", "attendance_date"),)


class EvaluationInstrument(TenantRecord):
    """The questionnaire. Versioned, because the numbers must be comparable.

    A question reworded between semesters makes a trend meaningless, so an
    instrument in use is never edited: a new version is published and the old
    one is retired. This is the same reasoning as `CurriculumVersion`, for the
    same reason — a comparison across time needs a fixed instrument.
    """

    __tablename__ = "evaluation_instrument"

    code: Mapped[str] = mapped_column(String(40), nullable=False)
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    #: `course`, `teaching`, `programme`, `facilities`, `supervision`,
    #: `service`.
    scope: Mapped[str] = mapped_column(String(20), nullable=False, default="teaching")
    introduction: Mapped[str | None] = mapped_column(Text)
    #: [{code, text, kind: likert5|likert7|yes_no|numeric|free_text,
    #:   dimension, required}]. Held as data rather than rows because an
    #: instrument is authored and published as one document, and a question
    #: has no meaning outside its instrument.
    questions: Mapped[list[dict[str, Any]]] = mapped_column(JSONB, nullable=False, default=list)
    #: The named groups the questions roll up into — "organisation",
    #: "assessment and feedback", "the lecturer". Reporting is by dimension;
    #: nobody acts on a single question's mean.
    dimensions: Mapped[list[str]] = mapped_column(ARRAY(String(60)), nullable=False, default=list)
    is_published: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, index=True)
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    retired_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    __table_args__ = (UniqueConstraint("code", "version", name="uq_instrument_version"),)


class CourseEvaluation(TenantRecord):
    """One run of an instrument over one course offering.

    The `opens_at`/`closes_at` window, and `results_visible_from`, exist for
    one reason: evaluations that open before teaching ends measure a course
    that is not finished, and results visible to a lecturer before they
    submit marks are a conflict of interest nobody should have to navigate.
    """

    __tablename__ = "course_evaluation"

    instrument_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("evaluation_instrument.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    course_offering_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("course_offering.id", ondelete="CASCADE"), nullable=False, index=True
    )
    semester_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("semester.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    #: The member of staff being evaluated. A course taught by two lecturers
    #: gets two evaluations, because "the teaching was clear" has two answers
    #: and averaging them tells neither of them anything.
    staff_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("staff.id", ondelete="SET NULL"), index=True
    )
    opens_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    closes_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    #: Deliberately after the marking deadline.
    results_visible_from: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="scheduled", index=True)
    invited_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    response_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    #: {dimension: mean} plus per-question means, computed at close. Stored
    #: rather than computed on read so a closed evaluation's numbers never
    #: move, which is what makes them citable in a promotion case.
    summary: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)
    #: False while `response_count` is below the reporting threshold. The flag
    #: is stored so every reader gets the same answer.
    is_reportable: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    closed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    #: The lecturer's written response to what the students said. The step
    #: that makes an evaluation a conversation rather than a verdict, and the
    #: one an external reviewer looks for.
    staff_reflection: Mapped[str | None] = mapped_column(Text)
    reflection_submitted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    #: What the department undertook to do about it.
    action_plan: Mapped[str | None] = mapped_column(Text)

    course_offering: Mapped[CourseOffering] = relationship(
        "CourseOffering", viewonly=True, lazy="joined"
    )

    __table_args__ = (
        UniqueConstraint(
            "course_offering_id", "instrument_id", "staff_id", name="uq_course_evaluation"
        ),
        CheckConstraint("closes_at > opens_at", name="ck_evaluation_window"),
    )


class EvaluationResponse(TenantRecord):
    """One anonymous questionnaire return.

    There is no `student_id` here, and that is not an oversight. Anonymity is
    enforced by the schema rather than promised in a privacy notice: the
    invitation list is consumed by `EvaluationInvitation` to stop a student
    responding twice, and nothing links that row to this one. Not even a
    hashed identifier, because a hash over a known small population is
    reversible by anyone who can list it.
    """

    __tablename__ = "evaluation_response"

    evaluation_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("course_evaluation.id", ondelete="CASCADE"), nullable=False, index=True
    )
    submitted_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    #: {question_code: value}. Likert answers as integers, free text as
    #: strings.
    answers: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)
    #: Free-text comments, kept apart from the scored answers because they are
    #: released on a different rule: a comment can identify its author by
    #: content, so a department head reads them and a public report does not.
    comments: Mapped[str | None] = mapped_column(Text)
    #: Only ever coarse: year of study and mode of study, because a response
    #: tagged with anything finer identifies the respondent.
    year_of_study: Mapped[int | None] = mapped_column(Integer)
    study_mode: Mapped[str | None] = mapped_column(String(20))


class EvaluationInvitation(TenantRecord):
    """Who was asked, and whether they have answered.

    Exists only so that a student can be reminded once and can respond once.
    It records *that* they responded and never *what* they said — the two
    facts live in different tables with no key between them, which is what
    makes the anonymity real rather than procedural.
    """

    __tablename__ = "evaluation_invitation"

    evaluation_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("course_evaluation.id", ondelete="CASCADE"), nullable=False, index=True
    )
    student_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("student.id", ondelete="CASCADE"), nullable=False, index=True
    )
    invited_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    responded_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    reminders_sent: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    last_reminder_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    #: A student may decline; counted separately from silence, because a
    #: declined invitation is a considered answer and a silent one is not.
    declined_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    __table_args__ = (
        UniqueConstraint("evaluation_id", "student_id", name="uq_evaluation_invitation"),
    )


class TeachingObservation(TenantRecord):
    """A peer or QA officer sat in on a class and wrote it up.

    Developmental by default: an observation is for the person observed, and
    `is_developmental` decides whether it may be read by anyone deciding on
    their promotion. Blurring that line stops staff volunteering for
    observation, and an observation scheme nobody volunteers for observes
    nothing.
    """

    __tablename__ = "teaching_observation"

    staff_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("staff.id", ondelete="CASCADE"), nullable=False, index=True
    )
    observer_staff_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("staff.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    course_offering_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("course_offering.id", ondelete="SET NULL"), index=True
    )
    class_session_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("class_session.id", ondelete="SET NULL")
    )
    observed_on: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    #: `peer`, `quality_assurance`, `probation`, `promotion`, `external`.
    purpose: Mapped[str] = mapped_column(String(30), nullable=False, default="peer")
    #: [{criterion, score, max, comment}] against the observation rubric.
    rubric_scores: Mapped[list[dict[str, Any]]] = mapped_column(JSONB, nullable=False, default=list)
    overall_score: Mapped[float | None] = mapped_column(Numeric(5, 2))
    strengths: Mapped[str | None] = mapped_column(Text)
    areas_to_develop: Mapped[str | None] = mapped_column(Text)
    agreed_actions: Mapped[str | None] = mapped_column(Text)
    #: The observed member of staff's own comment. An observation they have
    #: not seen is not an observation, it is a report about them.
    observee_response: Mapped[str | None] = mapped_column(Text)
    acknowledged_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    #: True unless the observation was commissioned for a decision about the
    #: person. See the class note.
    is_developmental: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="draft", index=True)
    follow_up_due_on: Mapped[date | None] = mapped_column(Date)

    #: `foreign_keys` is required: there are two paths to `staff` from here —
    #: the observed and the observer — and SQLAlchemy will not guess which
    #: one "the staff member this observation is about" means.
    staff: Mapped[Staff] = relationship(
        "Staff", viewonly=True, lazy="joined", foreign_keys=[staff_id]
    )


class QualityAudit(TenantRecord):
    """A periodic review of a unit or a programme against standards.

    The shape a regulator expects: a scope, a standard, findings each with a
    severity and an owner, and dates by which they close. Findings are held as
    data on the audit rather than in their own table because they are authored
    and signed off as one document — but each carries an owner and a due date,
    because a finding with neither is a sentence in a report and nothing else.
    """

    __tablename__ = "quality_audit"

    reference: Mapped[str] = mapped_column(String(40), unique=True, nullable=False)
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    #: `internal`, `external`, `regulator`, `professional_body`,
    #: `self_assessment`.
    kind: Mapped[str] = mapped_column(String(30), nullable=False, default="internal", index=True)
    #: What was reviewed. One of these is set.
    unit_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("academic_unit.id", ondelete="SET NULL"), index=True
    )
    programme_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("programme.id", ondelete="SET NULL"), index=True
    )
    #: The standard audited against — the regulator's minimum standards, an
    #: ISO clause, a professional body's criteria.
    standard: Mapped[str | None] = mapped_column(String(200))
    period_from: Mapped[date | None] = mapped_column(Date)
    period_to: Mapped[date | None] = mapped_column(Date)
    conducted_on: Mapped[date | None] = mapped_column(Date, index=True)
    lead_auditor_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    panel_staff_ids: Mapped[list[uuid.UUID]] = mapped_column(
        ARRAY(UUID(as_uuid=True)), nullable=False, default=list
    )
    external_panel: Mapped[list[str]] = mapped_column(
        ARRAY(String(200)), nullable=False, default=list
    )
    #: [{code, severity: major|minor|observation|commendation, finding,
    #:   evidence, owner_staff_id, due_on, status, closed_on, closure_note}]
    findings: Mapped[list[dict[str, Any]]] = mapped_column(JSONB, nullable=False, default=list)
    #: Counted out of `findings` so an overdue-actions report does not have to
    #: unpack the document.
    major_findings: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    minor_findings: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    open_findings: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    overall_outcome: Mapped[str | None] = mapped_column(String(60))
    report_attachment_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="planned", index=True)
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    next_review_due_on: Mapped[date | None] = mapped_column(Date)

    __table_args__ = (Index("ix_quality_audit_open", "status", "next_review_due_on"),)


class QualityIndicator(TenantRecord):
    """One measured value of one indicator, for one period and one scope.

    A long, thin table on purpose. Indicators are added and retired
    constantly, and a wide table with a column per metric needs a migration
    every time somebody asks a new question of the same data.
    """

    __tablename__ = "quality_indicator"

    #: `staff_student_ratio`, `pass_rate`, `progression_rate`,
    #: `completion_rate`, `attendance_rate`, `teaching_delivery_rate`,
    #: `evaluation_mean`, `staff_with_doctorate_percent`,
    #: `graduate_employment_rate`.
    code: Mapped[str] = mapped_column(String(60), nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    unit_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("academic_unit.id", ondelete="CASCADE"), index=True
    )
    programme_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("programme.id", ondelete="CASCADE"), index=True
    )
    academic_year_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("academic_year.id", ondelete="CASCADE"), index=True
    )
    semester_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("semester.id", ondelete="CASCADE")
    )
    value: Mapped[float] = mapped_column(Numeric(12, 4), nullable=False)
    unit_of_measure: Mapped[str | None] = mapped_column(String(20))
    #: The regulator's or the institution's own threshold, stored beside the
    #: value so a historical breach stays a breach after the target moves.
    target: Mapped[float | None] = mapped_column(Numeric(12, 4))
    #: `above`, `at`, `below`, `unknown` — computed against `target` at write
    #: time for the same reason.
    performance: Mapped[str | None] = mapped_column(String(10), index=True)
    #: How the number was arrived at. An indicator whose derivation nobody
    #: recorded is argued about instead of acted on.
    method_note: Mapped[str | None] = mapped_column(Text)
    numerator: Mapped[float | None] = mapped_column(Numeric(12, 2))
    denominator: Mapped[float | None] = mapped_column(Numeric(12, 2))
    computed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    computed_by_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))

    __table_args__ = (
        Index("ix_indicator_scope", "code", "academic_year_id", "unit_id", "programme_id"),
    )
