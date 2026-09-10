"""Course planning and curriculum management.

The central design decision: a `Programme` is a stable identity, and a
`CurriculumVersion` is the actual content — the courses, the credit weights,
the progression rules — valid for the cohorts that entered while it was
current. A student is attached to a *version*, not to a programme, and their
transcript is computed under the version they entered on.

Without that, a curriculum revision quietly rewrites the requirements of every
student mid-degree. With it, the 2024 cohort graduates under the 2024 rules
while the 2027 intake follows the revised ones, in the same tables, which is
what actually happens in a university and what most systems model badly.
"""

from __future__ import annotations

import uuid
from datetime import date, datetime
from enum import StrEnum
from typing import Any

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


class ApprovalStatus(StrEnum):
    """The academic governance chain, shared by programmes and versions."""

    DRAFT = "draft"
    SUBMITTED = "submitted"
    RETURNED = "returned"
    RECOMMENDED = "recommended"
    APPROVED = "approved"
    REJECTED = "rejected"
    RETIRED = "retired"


class AwardLevel(StrEnum):
    CERTIFICATE = "certificate"
    DIPLOMA = "diploma"
    HIGHER_DIPLOMA = "higher_diploma"
    BACHELORS = "bachelors"
    POSTGRADUATE_DIPLOMA = "postgraduate_diploma"
    MASTERS = "masters"
    DOCTORATE = "doctorate"


class Programme(TenantRecord):
    """A course of study leading to an award — the stable identity."""

    __tablename__ = "programme"

    code: Mapped[str] = mapped_column(String(30), unique=True, nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(300), nullable=False)
    short_name: Mapped[str | None] = mapped_column(String(60))
    #: As it must be printed on the certificate, which is not always the same
    #: as the name the marketing prospectus uses.
    award_title: Mapped[str] = mapped_column(String(300), nullable=False)
    award_abbreviation: Mapped[str] = mapped_column(String(30), nullable=False)
    award_level: Mapped[str] = mapped_column(String(30), nullable=False, index=True)

    owning_unit_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("academic_unit.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    #: Denormalised ancestry of the owning unit, so unit-scoped ABAC rules can
    #: decide without a recursive join on every request.
    faculty_ids: Mapped[list[uuid.UUID]] = mapped_column(
        ARRAY(UUID(as_uuid=True)), nullable=False, default=list
    )
    department_ids: Mapped[list[uuid.UUID]] = mapped_column(
        ARRAY(UUID(as_uuid=True)), nullable=False, default=list
    )
    #: Departments that teach into it but do not own it. A joint honours
    #: programme has several, and each needs read access to its own students.
    contributing_unit_ids: Mapped[list[uuid.UUID]] = mapped_column(
        ARRAY(UUID(as_uuid=True)), nullable=False, default=list
    )

    duration_semesters: Mapped[int] = mapped_column(Integer, nullable=False)
    #: `full_time`, `part_time`, `evening`, `distance`, `blended`. The same
    #: programme is often offered in several, with different fees and
    #: timetables but one curriculum.
    delivery_modes: Mapped[list[str]] = mapped_column(
        ARRAY(String(20)), nullable=False, default=list
    )
    campus_ids: Mapped[list[uuid.UUID]] = mapped_column(
        ARRAY(UUID(as_uuid=True)), nullable=False, default=list
    )
    study_level: Mapped[str] = mapped_column(String(30), nullable=False, default="undergraduate")

    #: Regulator accreditation, and when it lapses. A programme whose
    #: accreditation has expired must not admit — the governance module reports
    #: on exactly this, because admitting onto a lapsed accreditation
    #: invalidates the award.
    accreditation_number: Mapped[str | None] = mapped_column(String(60))
    accredited_until: Mapped[date | None] = mapped_column(Date, index=True)
    #: National qualifications framework level, for credit transfer.
    nqf_level: Mapped[int | None] = mapped_column(Integer)

    status: Mapped[str] = mapped_column(
        String(20), nullable=False, default=ApprovalStatus.DRAFT, index=True
    )
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, index=True)
    #: A retired programme still has students finishing on it, so it is never
    #: deleted and never made inactive until the last one graduates.
    retired_on: Mapped[date | None] = mapped_column(Date)

    description: Mapped[str | None] = mapped_column(Text)
    entry_requirements: Mapped[str | None] = mapped_column(Text)
    career_prospects: Mapped[str | None] = mapped_column(Text)

    versions: Mapped[list[CurriculumVersion]] = relationship(
        back_populates="programme", cascade="all, delete-orphan"
    )

    __table_args__ = (
        Index("ix_programme_faculties", "faculty_ids", postgresql_using="gin"),
        CheckConstraint("duration_semesters BETWEEN 1 AND 24", name="duration_sane"),
    )


class CurriculumVersion(TenantRecord):
    """The content of a programme, valid for a range of cohorts.

    `cohort_from`/`cohort_to` are academic-year codes rather than dates,
    because "who follows this version" is decided by the year a student
    entered, not by a calendar boundary. A student who takes two years of leave
    stays on the version they entered under.
    """

    __tablename__ = "curriculum_version"

    programme_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("programme.id", ondelete="CASCADE"), nullable=False, index=True
    )
    version_label: Mapped[str] = mapped_column(String(30), nullable=False)
    cohort_from: Mapped[str] = mapped_column(String(20), nullable=False, index=True)
    cohort_to: Mapped[str | None] = mapped_column(String(20), index=True)

    total_credit_units: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    #: Per-semester load bounds. The maximum is what the registration module
    #: enforces; the minimum is what makes a student part-time and changes
    #: their fee and their progression clock.
    min_credits_per_semester: Mapped[int] = mapped_column(Integer, nullable=False, default=15)
    max_credits_per_semester: Mapped[int] = mapped_column(Integer, nullable=False, default=24)
    #: Extra headroom granted to a finalist clearing retakes, which is the
    #: reason the cap is breached in practice.
    max_credits_with_retakes: Mapped[int] = mapped_column(Integer, nullable=False, default=27)

    #: Progression and classification rules as data. Held here rather than in
    #: code because they differ per institution and per version, and because a
    #: 2024 graduate must be classified under the 2024 rules — which is
    #: impossible if the rules only exist as the current release's Python.
    #: Interpreted by `assessment.rules`; the shape is documented there.
    progression_rules: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)
    classification_rules: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, default=dict
    )
    grading_scale_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))

    #: Programme learning outcomes, for accreditation self-assessment.
    learning_outcomes: Mapped[list[str]] = mapped_column(ARRAY(Text), nullable=False, default=list)

    status: Mapped[str] = mapped_column(
        String(20), nullable=False, default=ApprovalStatus.DRAFT, index=True
    )
    submitted_by_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    submitted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    recommended_by_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    recommended_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    #: Senate. Must differ from `submitted_by_id`.
    approved_by_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    senate_minute_reference: Mapped[str | None] = mapped_column(String(80))
    return_comments: Mapped[str | None] = mapped_column(Text)

    programme: Mapped[Programme] = relationship(back_populates="versions")
    structure: Mapped[list[CurriculumCourse]] = relationship(
        back_populates="version", cascade="all, delete-orphan"
    )

    __table_args__ = (
        UniqueConstraint("programme_id", "version_label", name="uq_curriculum_version"),
        CheckConstraint(
            "max_credits_per_semester >= min_credits_per_semester", name="credit_bounds_ordered"
        ),
    )


class Course(TenantRecord):
    """A teachable unit, e.g. CSC1101 Structured Programming.

    Owned by a department and reusable across programmes: one Calculus course
    serves Engineering, Physics and Economics, and modelling it per programme
    is how a university ends up with four Calculus courses that drift apart.
    """

    __tablename__ = "course"

    code: Mapped[str] = mapped_column(String(20), unique=True, nullable=False, index=True)
    title: Mapped[str] = mapped_column(String(300), nullable=False)
    owning_unit_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("academic_unit.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    department_ids: Mapped[list[uuid.UUID]] = mapped_column(
        ARRAY(UUID(as_uuid=True)), nullable=False, default=list
    )
    faculty_ids: Mapped[list[uuid.UUID]] = mapped_column(
        ARRAY(UUID(as_uuid=True)), nullable=False, default=list
    )

    credit_units: Mapped[int] = mapped_column(Integer, nullable=False)
    #: Contact hours by type. The NCHE credit-unit definition is arithmetic
    #: over these (1 CU = 15 lecture hours, or 30 tutorial, or 45 practical),
    #: so storing the components lets the system check a declared credit
    #: weight against the hours actually timetabled.
    lecture_hours: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    tutorial_hours: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    practical_hours: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    field_hours: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    #: Notional total including private study, for NQF credit mapping.
    notional_hours: Mapped[int | None] = mapped_column(Integer)

    level: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    description: Mapped[str | None] = mapped_column(Text)
    learning_outcomes: Mapped[list[str]] = mapped_column(ARRAY(Text), nullable=False, default=list)
    syllabus: Mapped[str | None] = mapped_column(Text)
    reading_list: Mapped[list[dict[str, Any]]] = mapped_column(JSONB, nullable=False, default=list)
    #: `written_exam`, `practical`, `dissertation`, `clinical`, `portfolio`.
    #: Drives which examination arrangements the assessment module offers.
    assessment_mode: Mapped[str] = mapped_column(String(30), nullable=False, default="written_exam")
    #: `false` for a course graded pass/fail — an industrial placement, say.
    #: Excluded from GPA, which is a rule the transcript computation must know.
    counts_toward_gpa: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)

    status: Mapped[str] = mapped_column(
        String(20), nullable=False, default=ApprovalStatus.DRAFT, index=True
    )
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, index=True)
    retired_on: Mapped[date | None] = mapped_column(Date)
    #: When a course is renumbered, the old row stays and points here, so a
    #: transcript printed from a 2019 record still resolves the course title.
    superseded_by_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))

    __table_args__ = (
        CheckConstraint("credit_units BETWEEN 1 AND 30", name="credit_units_sane"),
        Index("ix_course_departments", "department_ids", postgresql_using="gin"),
    )


class CourseCategory(StrEnum):
    CORE = "core"
    #: Chosen from a named group; the group's rules say how many.
    ELECTIVE = "elective"
    #: Required by the university of every student regardless of programme.
    UNIVERSITY_REQUIRED = "university_required"
    #: Taught by another department into this programme.
    SERVICE = "service"
    AUDIT = "audit"


class CurriculumCourse(TenantRecord):
    """A course's place in a curriculum version.

    The same course can appear in many versions with different weight, year
    and category, which is why the credit weight lives here as an override and
    not only on the course.
    """

    __tablename__ = "curriculum_course"

    version_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("curriculum_version.id", ondelete="CASCADE"), nullable=False, index=True
    )
    course_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("course.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    year_of_study: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    semester_kind: Mapped[str] = mapped_column(String(20), nullable=False)
    category: Mapped[str] = mapped_column(
        String(30), nullable=False, default=CourseCategory.CORE, index=True
    )
    #: Overrides `course.credit_units` for this programme, which happens when a
    #: shared course is taught at reduced depth to a non-specialist cohort.
    credit_units_override: Mapped[int | None] = mapped_column(Integer)
    #: Elective grouping: "choose 2 of the 5 courses in group B".
    elective_group: Mapped[str | None] = mapped_column(String(40))
    elective_group_choose: Mapped[int | None] = mapped_column(Integer)
    is_required_for_progression: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)

    version: Mapped[CurriculumVersion] = relationship(back_populates="structure")
    course: Mapped[Course] = relationship(lazy="joined")

    __table_args__ = (
        UniqueConstraint("version_id", "course_id", name="uq_curriculum_course"),
        Index("ix_curriculum_course_plan", "version_id", "year_of_study", "semester_kind"),
    )


class Prerequisite(TenantRecord):
    """A course dependency.

    `kind` distinguishes the three that behave differently at registration
    time: a prerequisite must be *passed* first, a co-requisite must be taken
    *alongside*, and an antirequisite may not be taken at all if the other has
    been (two overlapping statistics courses). `minimum_grade` supports the
    common "must have passed with at least a C" clinical requirement.
    """

    __tablename__ = "prerequisite"

    course_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("course.id", ondelete="CASCADE"), nullable=False, index=True
    )
    required_course_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("course.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    kind: Mapped[str] = mapped_column(String(20), nullable=False, default="prerequisite")
    minimum_grade: Mapped[str | None] = mapped_column(String(10))
    #: Courses in the same group are alternatives: any one satisfies the
    #: requirement. Null means this row is mandatory on its own.
    alternative_group: Mapped[str | None] = mapped_column(String(20))
    #: Scoped to one programme version when only that programme requires it.
    version_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("curriculum_version.id", ondelete="CASCADE")
    )
    is_waivable: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)

    __table_args__ = (
        UniqueConstraint(
            "course_id", "required_course_id", "kind", "version_id", name="uq_prerequisite"
        ),
        CheckConstraint("course_id != required_course_id", name="no_self_prerequisite"),
    )


class AssessmentScheme(TenantRecord):
    """How a course is assessed: the components and their weights.

    Per course *and* per curriculum version, because the same course is often
    assessed differently for different programmes, and because changing the
    coursework/exam split mid-cohort is the kind of thing that ends up in a
    student appeal. Component weights must total 100, checked in the service
    layer against this row's children.
    """

    __tablename__ = "assessment_scheme"

    course_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("course.id", ondelete="CASCADE"), nullable=False, index=True
    )
    version_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("curriculum_version.id", ondelete="CASCADE"), index=True
    )
    #: Overall pass mark for the course, as a percentage.
    pass_mark: Mapped[int] = mapped_column(Integer, nullable=False, default=50)
    #: Some faculties require the final examination to be passed on its own,
    #: however good the coursework. Medicine and Law commonly do.
    exam_must_be_passed: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    minimum_exam_mark: Mapped[int | None] = mapped_column(Integer)
    #: A student below this coursework mark is barred from the examination.
    minimum_coursework_for_exam: Mapped[int | None] = mapped_column(Integer)
    attendance_requirement_percent: Mapped[int | None] = mapped_column(Integer)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default=ApprovalStatus.DRAFT)

    components: Mapped[list[AssessmentComponent]] = relationship(
        back_populates="scheme", cascade="all, delete-orphan", lazy="selectin"
    )

    __table_args__ = (
        UniqueConstraint("course_id", "version_id", name="uq_assessment_scheme"),
        CheckConstraint("pass_mark BETWEEN 0 AND 100", name="pass_mark_sane"),
    )


class AssessmentComponent(TenantRecord):
    __tablename__ = "assessment_component"

    scheme_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("assessment_scheme.id", ondelete="CASCADE"), nullable=False, index=True
    )
    code: Mapped[str] = mapped_column(String(20), nullable=False)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    #: `coursework`, `test`, `practical`, `final_exam`, `project`, `clinical`.
    kind: Mapped[str] = mapped_column(String(30), nullable=False)
    weight_percent: Mapped[float] = mapped_column(Numeric(5, 2), nullable=False)
    max_mark: Mapped[float] = mapped_column(Numeric(6, 2), nullable=False, default=100)
    sequence: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    is_mandatory: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)

    scheme: Mapped[AssessmentScheme] = relationship(back_populates="components")

    __table_args__ = (
        UniqueConstraint("scheme_id", "code", name="uq_assessment_component"),
        CheckConstraint("weight_percent > 0 AND weight_percent <= 100", name="weight_sane"),
    )


class CourseOffering(TenantRecord):
    """A course actually running, in one semester, for one cohort.

    This is the row everything operational hangs off: teaching allocation,
    registration, the mark sheet, the timetable. Separating it from `Course`
    is what lets the same course run twice in a year on two campuses with
    different lecturers and different mark sheets.
    """

    __tablename__ = "course_offering"

    course_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("course.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    semester_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("semester.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    campus_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("campus.id"), index=True)
    #: A large first-year course is split into parallel groups with different
    #: lecturers; each group is its own offering so its mark sheet is its own.
    group_code: Mapped[str | None] = mapped_column(String(20))
    delivery_mode: Mapped[str] = mapped_column(String(20), nullable=False, default="full_time")
    assessment_scheme_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("assessment_scheme.id", ondelete="SET NULL")
    )

    #: Denormalised for ABAC and for the teaching dashboards.
    department_ids: Mapped[list[uuid.UUID]] = mapped_column(
        ARRAY(UUID(as_uuid=True)), nullable=False, default=list
    )
    faculty_ids: Mapped[list[uuid.UUID]] = mapped_column(
        ARRAY(UUID(as_uuid=True)), nullable=False, default=list
    )

    capacity: Mapped[int | None] = mapped_column(Integer)
    registered_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    #: Closed for registration — capacity reached or the window shut.
    is_open: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    #: Set when the mark sheet is generated; the offering is then frozen for
    #: registration changes, because adding a student to a live mark sheet is
    #: how a student ends up sitting an exam they are not registered for.
    mark_sheet_generated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    course: Mapped[Course] = relationship(lazy="joined")
    allocations: Mapped[list[TeachingAllocation]] = relationship(
        back_populates="offering", cascade="all, delete-orphan", lazy="selectin"
    )

    __table_args__ = (
        UniqueConstraint(
            "course_id", "semester_id", "campus_id", "group_code", name="uq_course_offering"
        ),
        # GIN over the array alone, not `(semester_id, department_ids)`: a GIN
        # index needs an operator class for every column, and `uuid` has none
        # — Postgres refuses the composite outright. Migration a7b8c9d0e1f2
        # replaced it, and this declaration has to match or every autogenerate
        # tries to put the broken index back.
        Index("ix_offering_departments", "department_ids", postgresql_using="gin"),
    )


class TeachingAllocation(TenantRecord):
    """Who teaches an offering, and in what capacity.

    Load-bearing for authorization: `assessment.mark-entry` grants mark entry
    to the staff assigned here and to nobody else, so the teaching allocation
    is what confers the authority. Which means an unallocated offering has
    nobody who can enter its marks — deliberately, because the alternative
    (anyone in the department may) is how marks get entered by the wrong person.
    """

    __tablename__ = "teaching_allocation"

    offering_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("course_offering.id", ondelete="CASCADE"), nullable=False, index=True
    )
    staff_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False, index=True)
    #: `coordinator`, `lecturer`, `tutor`, `lab_demonstrator`, `examiner`,
    #: `external_examiner`. Only the first three may enter marks; the external
    #: examiner moderates and cannot enter.
    role: Mapped[str] = mapped_column(String(30), nullable=False, default="lecturer")
    contact_hours: Mapped[float | None] = mapped_column(Numeric(6, 2))
    #: Share of the course's teaching, for workload accounting.
    load_share_percent: Mapped[float | None] = mapped_column(Numeric(5, 2))
    can_enter_marks: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    allocated_by_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    starts_on: Mapped[date | None] = mapped_column(Date)
    ends_on: Mapped[date | None] = mapped_column(Date)

    offering: Mapped[CourseOffering] = relationship(back_populates="allocations")

    __table_args__ = (
        UniqueConstraint("offering_id", "staff_id", "role", name="uq_teaching_allocation"),
    )


class TimetableSlot(TenantRecord):
    """A scheduled session.

    Clash detection is a service concern rather than a constraint, because the
    three things that clash are different: a room double-booked, a lecturer in
    two places, and a cohort with two required courses at once. The last is the
    one students actually complain about and the one a naive unique index
    misses entirely.
    """

    __tablename__ = "timetable_slot"

    offering_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("course_offering.id", ondelete="CASCADE"), nullable=False, index=True
    )
    room_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("room.id", ondelete="SET NULL"), index=True
    )
    staff_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), index=True)
    #: 1 = Monday.
    day_of_week: Mapped[int] = mapped_column(Integer, nullable=False)
    starts_at: Mapped[str] = mapped_column(String(5), nullable=False)
    ends_at: Mapped[str] = mapped_column(String(5), nullable=False)
    session_kind: Mapped[str] = mapped_column(String(20), nullable=False, default="lecture")
    #: For a fortnightly practical: which weeks of the semester it runs.
    week_pattern: Mapped[list[int]] = mapped_column(ARRAY(Integer), nullable=False, default=list)
    is_online: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    meeting_url: Mapped[str | None] = mapped_column(String(500))

    __table_args__ = (
        CheckConstraint("day_of_week BETWEEN 1 AND 7", name="day_sane"),
        Index("ix_timetable_room_day", "room_id", "day_of_week", "starts_at"),
        Index("ix_timetable_staff_day", "staff_id", "day_of_week", "starts_at"),
    )
