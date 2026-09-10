"""Assessment, grading, boards and awards.

The most consequential module in the system. Everything here exists to make
one sentence defensible years later: *this mark is what the examiner entered,
it was moderated by these people, approved at these three levels on these
dates, and here is what changed and why.*

Two structural decisions carry that weight:

**The mark sheet is the unit of work, not the individual mark.** An examiner
submits a course's marks together, they are moderated together, and a board
approves them together. Approving marks one student at a time makes "who
approved this cohort's results" unanswerable and makes the double-marking
check impossible.

**Nothing is ever overwritten.** A component score is versioned, a corrected
mark is an amendment row with its predecessor intact, and a published result
can only change through an appeal that names its case. The audit trail records
the change; these tables preserve the values.
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
    # Imported for the annotation only. The mapper resolves "CourseOffering"
    # through SQLAlchemy's class registry, so assessment does not import
    # curriculum at runtime and the module graph stays acyclic.
    from acmis.modules.curriculum.models import CourseOffering


class GradingScale(TenantRecord):
    """A mark-to-grade-point mapping, valid for a range of cohorts.

    Versioned by effective date, and a student's transcript is computed under
    the scale in force when they took the course. Institutions change their
    scale — Uganda's public universities moved between 4.0- and 5.0-point
    scales — and recomputing a 2019 transcript under a 2027 scale produces a
    different classification for a graduate who has already been awarded one.
    """

    __tablename__ = "grading_scale"

    code: Mapped[str] = mapped_column(String(30), nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(160), nullable=False)
    #: 5.0 for most East African universities, 4.0 where the US convention is
    #: followed. Stored because classification boundaries are expressed in it.
    max_grade_point: Mapped[float] = mapped_column(Numeric(3, 1), nullable=False, default=5.0)
    pass_mark: Mapped[int] = mapped_column(Integer, nullable=False, default=50)
    #: Minimum grade point counted as a pass for progression, distinct from the
    #: pass mark: NCHE guidance sets normal progress at a GP of 2.0 and above.
    pass_grade_point: Mapped[float] = mapped_column(Numeric(3, 2), nullable=False, default=2.0)
    study_level: Mapped[str] = mapped_column(String(30), nullable=False, default="undergraduate")
    effective_from: Mapped[date] = mapped_column(Date, nullable=False)
    effective_to: Mapped[date | None] = mapped_column(Date)
    is_current: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, index=True)

    bands: Mapped[list[GradeBand]] = relationship(
        back_populates="scale",
        cascade="all, delete-orphan",
        lazy="selectin",
        order_by="GradeBand.lower_mark.desc()",
    )

    __table_args__ = (UniqueConstraint("code", "effective_from", name="uq_grading_scale_version"),)


class GradeBand(TenantRecord):
    """One band: 80-100 -> A -> 5.0.

    Bounds are inclusive-lower, inclusive-upper and the service layer asserts
    the set covers 0-100 with no gap and no overlap. A gap means a mark that
    produces no grade, discovered at the worst possible moment — while a board
    is sitting.
    """

    __tablename__ = "grade_band"

    scale_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("grading_scale.id", ondelete="CASCADE"), nullable=False, index=True
    )
    grade: Mapped[str] = mapped_column(String(5), nullable=False)
    lower_mark: Mapped[float] = mapped_column(Numeric(5, 2), nullable=False)
    upper_mark: Mapped[float] = mapped_column(Numeric(5, 2), nullable=False)
    grade_point: Mapped[float] = mapped_column(Numeric(3, 2), nullable=False)
    descriptor: Mapped[str | None] = mapped_column(String(60))
    is_pass: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    #: Excluded from the GPA divisor — an incomplete, a withheld result or an
    #: audited course. Not the same as a fail, which counts and pulls the
    #: average down.
    counts_in_gpa: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)

    scale: Mapped[GradingScale] = relationship(back_populates="bands")

    __table_args__ = (
        UniqueConstraint("scale_id", "grade", name="uq_grade_band_grade"),
        CheckConstraint("upper_mark >= lower_mark", name="band_ordered"),
        CheckConstraint("lower_mark >= 0 AND upper_mark <= 100", name="band_in_range"),
    )


class MarkSheetStatus(StrEnum):
    """The approval chain. Every transition is audited and irreversible
    except through an explicit `return`."""

    DRAFT = "draft"
    SUBMITTED = "submitted"
    #: Sent back to the examiner with comments.
    RETURNED = "returned"
    MODERATED = "moderated"
    BOARD_APPROVED = "board_approved"
    FACULTY_APPROVED = "faculty_approved"
    SENATE_APPROVED = "senate_approved"
    PUBLISHED = "published"


class MarkSheet(TenantRecord):
    """All the marks for one course offering, as one approvable unit."""

    __tablename__ = "mark_sheet"

    course_offering_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("course_offering.id", ondelete="RESTRICT"),
        nullable=False,
        unique=True,
        index=True,
    )
    semester_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("semester.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    assessment_scheme_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("assessment_scheme.id", ondelete="SET NULL")
    )
    grading_scale_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("grading_scale.id", ondelete="RESTRICT"), nullable=False
    )
    status: Mapped[str] = mapped_column(
        String(30), nullable=False, default=MarkSheetStatus.DRAFT, index=True
    )

    #: Denormalised for ABAC: the board and faculty rules compare these
    #: against the approver's own units.
    department_ids: Mapped[list[uuid.UUID]] = mapped_column(
        ARRAY(UUID(as_uuid=True)), nullable=False, default=list
    )
    faculty_ids: Mapped[list[uuid.UUID]] = mapped_column(
        ARRAY(UUID(as_uuid=True)), nullable=False, default=list
    )
    #: Everyone who has entered or edited a mark on this sheet. The
    #: separation-of-duties rule reads this to refuse self-approval, so it is
    #: appended to on every write and never cleared.
    entered_by_ids: Mapped[list[uuid.UUID]] = mapped_column(
        ARRAY(UUID(as_uuid=True)), nullable=False, default=list
    )
    #: Staff who have declared an interest — a relative in the cohort, or a
    #: candidate they also supervise. Blocks them from moderating or approving.
    conflicted_staff_ids: Mapped[list[uuid.UUID]] = mapped_column(
        ARRAY(UUID(as_uuid=True)), nullable=False, default=list
    )

    student_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    entered_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    missing_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    pass_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    fail_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    #: Distribution statistics, computed on submission. A board looks at these
    #: before it looks at any individual mark: a course with a 92% failure rate
    #: or a mean of 78 is a question about the assessment, not the students.
    mean_mark: Mapped[float | None] = mapped_column(Numeric(5, 2))
    median_mark: Mapped[float | None] = mapped_column(Numeric(5, 2))
    standard_deviation: Mapped[float | None] = mapped_column(Numeric(5, 2))
    grade_distribution: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)

    submitted_by_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    submitted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    moderated_by_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    moderated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    #: A moderator who scales the whole cohort must say by how much and why —
    #: a silent scaling is indistinguishable from tampering.
    moderation_adjustment: Mapped[float | None] = mapped_column(Numeric(5, 2))
    moderation_note: Mapped[str | None] = mapped_column(Text)
    board_approved_by_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    board_approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    faculty_approved_by_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    faculty_approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    senate_approved_by_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    senate_approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    senate_minute_reference: Mapped[str | None] = mapped_column(String(80))
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    return_comments: Mapped[str | None] = mapped_column(Text)
    due_on: Mapped[date | None] = mapped_column(Date, index=True)

    results: Mapped[list[CourseResult]] = relationship(
        back_populates="mark_sheet", cascade="all, delete-orphan"
    )
    #: Read only for the audit label ("CSC1101 mark sheet") and for policy
    #: attributes. `viewonly` because a mark sheet never re-points itself at a
    #: different offering.
    course_offering: Mapped[CourseOffering] = relationship(
        "CourseOffering", viewonly=True, lazy="joined"
    )

    __table_args__ = (Index("ix_mark_sheet_status_due", "status", "due_on"),)

    @property
    def is_editable(self) -> bool:
        return self.status in {MarkSheetStatus.DRAFT, MarkSheetStatus.RETURNED}


class CourseResult(TenantRecord):
    """One student's outcome in one course attempt.

    The row the transcript is built from. `credit_units` and `grade_point` are
    copied here rather than joined at read time — the same reason the whole
    module denormalises: a transcript printed in 2034 must show the weight and
    the grade point that applied in 2027, not today's.
    """

    __tablename__ = "course_result"

    mark_sheet_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("mark_sheet.id", ondelete="CASCADE"), index=True
    )
    student_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("student.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    student_programme_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("student_programme.id", ondelete="RESTRICT"), index=True
    )
    course_offering_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("course_offering.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    course_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("course.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    registration_course_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    semester_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("semester.id", ondelete="RESTRICT"), nullable=False, index=True
    )

    #: Frozen copies. See the class note.
    course_code: Mapped[str] = mapped_column(String(20), nullable=False)
    course_title: Mapped[str] = mapped_column(String(300), nullable=False)
    credit_units: Mapped[int] = mapped_column(Integer, nullable=False)

    coursework_mark: Mapped[float | None] = mapped_column(Numeric(5, 2))
    exam_mark: Mapped[float | None] = mapped_column(Numeric(5, 2))
    final_mark: Mapped[float | None] = mapped_column(Numeric(5, 2), index=True)
    grade: Mapped[str | None] = mapped_column(String(5), index=True)
    grade_point: Mapped[float | None] = mapped_column(Numeric(3, 2))
    quality_points: Mapped[float | None] = mapped_column(Numeric(7, 2))
    #: `pass`, `fail`, `retake`, `incomplete`, `absent`, `withheld`,
    #: `malpractice`, `exempt`, `audit`. Separate from the grade because
    #: several of these have no mark at all and the transcript must still say
    #: something truthful in the cell.
    outcome: Mapped[str] = mapped_column(String(20), nullable=False, default="pending", index=True)
    attempt_number: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    is_retake: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, index=True)
    #: True when a later attempt supersedes this one for classification. Both
    #: rows survive; the transcript shows the history and counts the best.
    is_superseded: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    counts_in_gpa: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)

    #: A student may see this only once true — `assessment.student-visibility`.
    released: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, index=True)
    released_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    #: Withheld for a fee block, a disciplinary case or a missing document.
    withheld: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    withheld_reason: Mapped[str | None] = mapped_column(String(300))

    #: An open appeal is what the appeals-exception policy requires before a
    #: published mark may be amended.
    appeal_case_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), index=True)
    appeal_status: Mapped[str | None] = mapped_column(String(20))
    #: Set when this row replaced an earlier one; the earlier row is kept.
    amended_from_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    amendment_reason: Mapped[str | None] = mapped_column(Text)

    mark_sheet: Mapped[MarkSheet | None] = relationship(back_populates="results")
    component_scores: Mapped[list[ComponentScore]] = relationship(
        back_populates="result", cascade="all, delete-orphan", lazy="selectin"
    )

    __table_args__ = (
        UniqueConstraint(
            "student_id", "course_offering_id", "attempt_number", name="uq_result_attempt"
        ),
        Index("ix_result_student_semester", "student_id", "semester_id"),
        Index("ix_result_transcript", "student_programme_id", "is_superseded", "counts_in_gpa"),
        CheckConstraint(
            "final_mark IS NULL OR (final_mark >= 0 AND final_mark <= 100)",
            name="final_mark_in_range",
        ),
    )


class ComponentScore(TenantRecord):
    """A score for one assessment component of one result.

    Kept alongside the computed final mark so a disputed total can be
    recomputed from its parts. The commonest examinations query is not "is this
    mark right" but "does 34 coursework and 61 exam really make 52", and it is
    unanswerable if only the total was stored.
    """

    __tablename__ = "assessment_component_score"

    result_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("course_result.id", ondelete="CASCADE"), nullable=False, index=True
    )
    component_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("assessment_component.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    component_code: Mapped[str] = mapped_column(String(20), nullable=False)
    raw_score: Mapped[float | None] = mapped_column(Numeric(6, 2))
    max_score: Mapped[float] = mapped_column(Numeric(6, 2), nullable=False, default=100)
    weight_percent: Mapped[float] = mapped_column(Numeric(5, 2), nullable=False)
    weighted_score: Mapped[float | None] = mapped_column(Numeric(6, 2))
    #: `absent`, `deferred`, `missing`, `malpractice`. A blank score and an
    #: absence are different facts with different consequences.
    exception: Mapped[str | None] = mapped_column(String(20))
    entered_by_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    entered_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    #: Incremented on every change, with the previous values kept in
    #: `revisions` — a mark edited three times before submission is three
    #: facts, and the third is not more true than the first without a record
    #: of the other two.
    revision: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    revisions: Mapped[list[dict[str, Any]]] = mapped_column(JSONB, nullable=False, default=list)

    result: Mapped[CourseResult] = relationship(back_populates="component_scores")

    __table_args__ = (UniqueConstraint("result_id", "component_id", name="uq_component_score"),)


class SemesterResult(TenantRecord):
    """A student's aggregate for one semester, and the progression decision.

    Computed, stored, and stamped with the rule set that produced it. Stored
    because the board needs a stable number to decide on and a student needs
    to be told a specific GPA; stamped because "why was I put on probation"
    must be answerable with the rules as they were, not as they are.
    """

    __tablename__ = "semester_result"

    student_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("student.id", ondelete="CASCADE"), nullable=False, index=True
    )
    student_programme_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("student_programme.id", ondelete="CASCADE"), nullable=False, index=True
    )
    semester_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("semester.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    year_of_study: Mapped[int] = mapped_column(Integer, nullable=False)

    credits_attempted: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    credits_earned: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    quality_points: Mapped[float] = mapped_column(Numeric(8, 2), nullable=False, default=0)
    gpa: Mapped[float | None] = mapped_column(Numeric(4, 2), index=True)
    #: Cumulative to the end of this semester. Both are kept so a transcript
    #: can print the running CGPA per semester, which is what a transcript
    #: actually shows.
    cumulative_credits_earned: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    cumulative_quality_points: Mapped[float] = mapped_column(
        Numeric(9, 2), nullable=False, default=0
    )
    cgpa: Mapped[float | None] = mapped_column(Numeric(4, 2), index=True)

    #: `normal`, `probation`, `retake`, `repeat_year`, `discontinue`,
    #: `complete`. Following the NCHE classification of normal, probationary
    #: and discontinued progress.
    progression: Mapped[str] = mapped_column(
        String(20), nullable=False, default="pending", index=True
    )
    failed_course_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    retake_course_ids: Mapped[list[uuid.UUID]] = mapped_column(
        ARRAY(UUID(as_uuid=True)), nullable=False, default=list
    )
    #: Consecutive semesters on probation. Most institutions discontinue on the
    #: second or third, so the counter has to persist across semesters.
    consecutive_probations: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    #: The exact progression rules used. See the class note.
    rules_snapshot: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)
    computed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    board_decision_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    is_published: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    __table_args__ = (
        UniqueConstraint("student_programme_id", "semester_id", name="uq_semester_result"),
    )


class BoardDecision(TenantRecord):
    """A minuted decision of a board of examiners.

    The board can override a computed progression — a student one credit short
    with a documented illness is passed by discretion — and that override must
    be attributable to a sitting, a minute and a set of names. This table is
    what makes the discretion legitimate rather than an unexplained edit.
    """

    __tablename__ = "board_decision"

    #: `department`, `faculty`, `senate`, `appeals`.
    board_level: Mapped[str] = mapped_column(String(20), nullable=False, index=True)
    unit_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("academic_unit.id", ondelete="RESTRICT"), index=True
    )
    semester_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("semester.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    sitting_date: Mapped[date] = mapped_column(Date, nullable=False)
    minute_reference: Mapped[str] = mapped_column(String(80), nullable=False)
    chair_staff_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    secretary_staff_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    members_present: Mapped[list[uuid.UUID]] = mapped_column(
        ARRAY(UUID(as_uuid=True)), nullable=False, default=list
    )
    #: External examiners present. Their attendance is an accreditation
    #: requirement for finalist boards in most systems.
    external_examiners: Mapped[list[str]] = mapped_column(
        ARRAY(String(200)), nullable=False, default=list
    )
    #: The specific student decisions taken:
    #: [{student_id, from, to, reason, discretion}]
    decisions: Mapped[list[dict[str, Any]]] = mapped_column(JSONB, nullable=False, default=list)
    mark_sheet_ids: Mapped[list[uuid.UUID]] = mapped_column(
        ARRAY(UUID(as_uuid=True)), nullable=False, default=list
    )
    resolutions: Mapped[str | None] = mapped_column(Text)
    minutes_attachment_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="draft")

    __table_args__ = (UniqueConstraint("board_level", "minute_reference", name="uq_board_minute"),)


class ResultsRelease(TenantRecord):
    """The act of making a semester's results visible to students.

    A single deliberate event, not a per-mark flag flipped as marks land.
    Students compare notes within minutes of a release, so a partial release
    produces a queue at the registry — and a release that can be reversed
    produces an argument no institution wins. Reversal is therefore an audited
    act with its own reason.
    """

    __tablename__ = "results_release"

    semester_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("semester.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    unit_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("academic_unit.id", ondelete="RESTRICT")
    )
    programme_ids: Mapped[list[uuid.UUID]] = mapped_column(
        ARRAY(UUID(as_uuid=True)), nullable=False, default=list
    )
    scope_description: Mapped[str] = mapped_column(String(300), nullable=False)
    mark_sheet_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    result_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    student_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="prepared", index=True)
    senate_minute_reference: Mapped[str | None] = mapped_column(String(80))
    released_by_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    released_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    reversed_by_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    reversed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    reversal_reason: Mapped[str | None] = mapped_column(Text)
    #: Whether students were notified, and on which channels.
    notification_summary: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, default=dict
    )


class AppealCase(TenantRecord):
    """A student's challenge to a result.

    The only lawful route to changing a published mark. `assessment.appeals-
    exception` requires an open case on the result before an amendment is
    permitted, which is why the case id lives on `CourseResult` and not only
    here.
    """

    __tablename__ = "appeal_case"

    case_number: Mapped[str] = mapped_column(String(40), unique=True, nullable=False)
    student_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("student.id", ondelete="CASCADE"), nullable=False, index=True
    )
    course_result_ids: Mapped[list[uuid.UUID]] = mapped_column(
        ARRAY(UUID(as_uuid=True)), nullable=False, default=list
    )
    #: `remarking`, `computation_error`, `missing_mark`, `procedural`,
    #: `special_circumstances`.
    grounds: Mapped[str] = mapped_column(String(40), nullable=False, index=True)
    submission: Mapped[str] = mapped_column(Text, nullable=False)
    #: Appeals are time-barred — typically 21 days from release — and a late
    #: appeal needs its own dispensation.
    lodged_on: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    deadline_on: Mapped[date | None] = mapped_column(Date)
    is_late: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    #: Most institutions charge for a remark and refund it if the appeal
    #: succeeds. The link is here so the refund is traceable to the outcome.
    fee_invoice_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="lodged", index=True)
    #: The remarker must not be the original examiner, checked in the service.
    remarker_staff_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    outcome: Mapped[str | None] = mapped_column(String(30))
    outcome_detail: Mapped[str | None] = mapped_column(Text)
    decided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    committee_minute_reference: Mapped[str | None] = mapped_column(String(80))
    evidence_attachment_ids: Mapped[list[uuid.UUID]] = mapped_column(
        ARRAY(UUID(as_uuid=True)), nullable=False, default=list
    )


class ExamSitting(TenantRecord):
    """A scheduled examination: when, where, who invigilates.

    Separate from the timetable slot because an examination has requirements a
    lecture does not: exam-capacity seating, invigilator ratios, and
    accommodations for candidates entitled to them. Those constraints are what
    the examinations office actually schedules against.
    """

    __tablename__ = "exam_sitting"

    course_offering_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("course_offering.id", ondelete="CASCADE"), nullable=False, index=True
    )
    semester_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("semester.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    sitting_date: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    starts_at: Mapped[str] = mapped_column(String(5), nullable=False)
    duration_minutes: Mapped[int] = mapped_column(Integer, nullable=False, default=180)
    #: `main`, `supplementary`, `special`, `deferred`.
    session: Mapped[str] = mapped_column(String(20), nullable=False, default="main")
    room_ids: Mapped[list[uuid.UUID]] = mapped_column(
        ARRAY(UUID(as_uuid=True)), nullable=False, default=list
    )
    candidate_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    invigilator_staff_ids: Mapped[list[uuid.UUID]] = mapped_column(
        ARRAY(UUID(as_uuid=True)), nullable=False, default=list
    )
    chief_invigilator_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    #: Candidates sitting elsewhere or with extra time. Held as a count here
    #: and detailed on the student record, which is where the entitlement lives.
    accommodation_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    paper_attachment_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="scheduled")
    incident_report: Mapped[str | None] = mapped_column(Text)

    __table_args__ = (
        UniqueConstraint("course_offering_id", "session", "sitting_date", name="uq_exam_sitting"),
    )


class AttendanceRecord(TenantRecord):
    """Attendance, where the institution requires it.

    A percentage per student per offering rather than one row per session:
    session-level attendance is 40 rows per student per course per semester and
    the only question anyone asks of it is whether the student met the
    threshold to sit the examination.
    """

    __tablename__ = "attendance_record"

    student_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("student.id", ondelete="CASCADE"), nullable=False, index=True
    )
    course_offering_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("course_offering.id", ondelete="CASCADE"), nullable=False, index=True
    )
    sessions_held: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    sessions_attended: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    percentage: Mapped[float | None] = mapped_column(Numeric(5, 2))
    meets_requirement: Mapped[bool | None] = mapped_column(Boolean, index=True)
    exempted: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    exemption_reason: Mapped[str | None] = mapped_column(String(300))
    updated_by_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))

    __table_args__ = (UniqueConstraint("student_id", "course_offering_id", name="uq_attendance"),)


class Award(TenantRecord):
    """A conferred qualification. The system's terminal output.

    Nothing in ACMIS is harder to undo. Conferment is Senate's act, gated on
    MFA, a zero fee balance and a completed graduation list, and revocation is
    a separate audited action that never deletes the row — a revoked degree
    must remain visible as revoked, or verification cannot answer honestly.
    """

    __tablename__ = "award"

    student_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("student.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    student_programme_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("student_programme.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    programme_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("programme.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    graduation_list_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), index=True)

    #: Frozen at conferment: the title and the student's name as printed.
    award_title: Mapped[str] = mapped_column(String(300), nullable=False)
    award_level: Mapped[str] = mapped_column(String(30), nullable=False)
    certificate_name: Mapped[str] = mapped_column(String(400), nullable=False)
    #: `First Class`, `Second Class (Upper)`, `Pass`, `Distinction`, `Merit`.
    classification: Mapped[str | None] = mapped_column(String(60), index=True)
    final_cgpa: Mapped[float | None] = mapped_column(Numeric(4, 2))
    credits_earned: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    #: The classification rules applied, so a disputed class can be checked.
    classification_snapshot: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, default=dict
    )

    #: Printed on the certificate and used for public verification. Random,
    #: not sequential: a sequential serial lets anyone enumerate every graduate
    #: through the public verification endpoint.
    serial_number: Mapped[str] = mapped_column(String(40), unique=True, nullable=False, index=True)
    #: Short code a student quotes to an employer. Also random.
    verification_code: Mapped[str] = mapped_column(String(20), unique=True, nullable=False)

    conferred_on: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    graduation_ceremony_date: Mapped[date | None] = mapped_column(Date)
    conferred_by_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    senate_minute_reference: Mapped[str | None] = mapped_column(String(80))
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="conferred", index=True)
    certificate_issued_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    certificate_collected_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    revocation_reason: Mapped[str | None] = mapped_column(Text)
    revoked_by_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    #: Reprints are tracked because a certificate is a bearer document and two
    #: in circulation is a problem the institution must be able to detect.
    reprint_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)


class GraduationList(TenantRecord):
    """The cohort presented to Senate for conferment."""

    __tablename__ = "graduation_list"

    name: Mapped[str] = mapped_column(String(200), nullable=False)
    ceremony_date: Mapped[date | None] = mapped_column(Date, index=True)
    academic_year_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("academic_year.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    unit_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("academic_unit.id", ondelete="RESTRICT")
    )
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="draft", index=True)
    candidate_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    #: Candidates the eligibility check rejected, with reasons. Kept on the
    #: list rather than discarded: "why is my name not on the list" is the
    #: single most common question a registry gets in graduation season.
    excluded: Mapped[list[dict[str, Any]]] = mapped_column(JSONB, nullable=False, default=list)
    prepared_by_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    submitted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    senate_approved_by_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    senate_approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    senate_minute_reference: Mapped[str | None] = mapped_column(String(80))
    conferred_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class Transcript(TenantRecord):
    """An issued transcript. A record of issuance, not of the content.

    The content is regenerated from the result rows on every issue, so a
    transcript cannot drift from the record it reports. What is stored is
    *that* one was issued, to whom, on whose authority and with what serial —
    because an employer verifying a transcript is verifying this row.
    """

    __tablename__ = "transcript"

    student_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("student.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    student_programme_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("student_programme.id", ondelete="RESTRICT")
    )
    #: `official`, `student_copy`, `interim`, `verification`.
    kind: Mapped[str] = mapped_column(String(20), nullable=False, default="official")
    serial_number: Mapped[str] = mapped_column(String(40), unique=True, nullable=False, index=True)
    verification_code: Mapped[str] = mapped_column(String(20), unique=True, nullable=False)
    purpose: Mapped[str | None] = mapped_column(String(200))
    #: Where it was sent. An official transcript issued to a named third party
    #: is watermarked with that party, which is how a leaked copy is traced.
    recipient_name: Mapped[str | None] = mapped_column(String(300))
    recipient_address: Mapped[str | None] = mapped_column(Text)
    issued_on: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    issued_by_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    fee_invoice_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    #: SHA-256 of the rendered PDF. Lets a presented document be checked
    #: against what was actually issued, not merely against the student's name.
    document_sha256: Mapped[str | None] = mapped_column(String(64))
    attachment_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="issued")
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
