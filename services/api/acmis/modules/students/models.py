"""The student life-cycle and bio-data portal.

Three layers, and the distinction between them is the whole design:

* `Student` — the person and their identity. One row for life.
* `StudentProgramme` — their attachment to a curriculum version. Usually one,
  more than one for a student who transfers or who returns for a second award.
* `Enrolment` / `Registration` — what they did in one semester. `Enrolment` is
  "I am here this semester"; `Registration` is "these are the courses". Both
  exist because they are separately gated: a student can enrol (and be counted
  in the statutory return) while their course registration is still blocked on
  a fee, and the two events are audited separately because the questions
  "were they a student that semester" and "were they registered for that exam"
  have different answers and different consequences.
"""

from __future__ import annotations

import uuid
from datetime import date, datetime
from enum import StrEnum
from typing import TYPE_CHECKING, Any

from sqlalchemy import (
    BigInteger,
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
    # For the annotation only. The mapper resolves "CourseOffering" through
    # SQLAlchemy's own class registry, so students does not import curriculum
    # at runtime and the module import graph stays acyclic.
    from acmis.modules.curriculum.models import CourseOffering


class StudentStatus(StrEnum):
    ADMITTED = "admitted"
    ACTIVE = "active"
    #: Approved absence. Stops the progression clock; the student returns to
    #: the curriculum version they entered on.
    ON_LEAVE = "on_leave"
    #: Below the CGPA threshold. Still active, but load-capped and reviewed.
    PROBATION = "probation"
    SUSPENDED = "suspended"
    #: Withdrew voluntarily.
    WITHDRAWN = "withdrawn"
    #: Academically dismissed.
    DISCONTINUED = "discontinued"
    #: Coursework done, award not yet conferred. Its own state because a
    #: completed student is not an active one and must drop out of the
    #: enrolment return, but is not yet a graduate either.
    COMPLETED = "completed"
    GRADUATED = "graduated"
    DECEASED = "deceased"


class Student(TenantRecord):
    """The person. Bio-data, contact, identity — not their academic progress."""

    __tablename__ = "student"

    #: The institutional student number, e.g. 26/U/1234/PS. Printed on every
    #: document and quoted by the student for the rest of their life, so its
    #: format is configured per institution and it never changes once issued.
    student_number: Mapped[str] = mapped_column(String(30), unique=True, nullable=False, index=True)
    #: Regulator-assigned national student identifier, where one exists.
    national_student_id: Mapped[str | None] = mapped_column(String(40), index=True)
    applicant_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), index=True)
    account_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), index=True)

    surname: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    given_names: Mapped[str] = mapped_column(String(200), nullable=False)
    other_names: Mapped[str | None] = mapped_column(String(200))
    #: The name as it will be printed on the certificate. Captured separately
    #: and confirmed by the student before graduation, because that is the
    #: last chance to correct a spelling and a reprint is a formal process.
    certificate_name: Mapped[str | None] = mapped_column(String(400))
    preferred_name: Mapped[str | None] = mapped_column(String(100))

    date_of_birth: Mapped[date] = mapped_column(Date, nullable=False)
    sex: Mapped[str] = mapped_column(String(20), nullable=False)
    marital_status: Mapped[str | None] = mapped_column(String(20))
    nationality: Mapped[str] = mapped_column(String(60), nullable=False)
    country_code: Mapped[str] = mapped_column(String(2), nullable=False, default="UG")
    district_of_origin: Mapped[str | None] = mapped_column(String(80), index=True)
    religion: Mapped[str | None] = mapped_column(String(60))
    blood_group: Mapped[str | None] = mapped_column(String(10))

    #: Institutional address, which the student maintains themselves.
    email: Mapped[str] = mapped_column(String(200), nullable=False, index=True)
    personal_email: Mapped[str | None] = mapped_column(String(200))
    phone: Mapped[str] = mapped_column(String(40), nullable=False)
    alternate_phone: Mapped[str | None] = mapped_column(String(40))
    postal_address: Mapped[str | None] = mapped_column(Text)
    residential_address: Mapped[str | None] = mapped_column(Text)
    #: Hall of residence or "non-resident". Drives the warden's scoped access.
    residence: Mapped[str | None] = mapped_column(String(120))
    room_number: Mapped[str | None] = mapped_column(String(30))

    national_id: Mapped[str | None] = mapped_column(String(60))
    passport_number: Mapped[str | None] = mapped_column(String(60))
    #: Special-category, masked by default everywhere.
    disability: Mapped[str | None] = mapped_column(String(200))
    disability_detail: Mapped[str | None] = mapped_column(Text)
    #: Examination adjustments the student is entitled to — extra time, a
    #: scribe, a separate room. Read by the examinations office because the
    #: sitting has to be arranged, and by nobody else.
    exam_accommodations: Mapped[str | None] = mapped_column(Text)
    medical_conditions: Mapped[str | None] = mapped_column(Text)
    medical_notes: Mapped[str | None] = mapped_column(Text)

    next_of_kin_name: Mapped[str | None] = mapped_column(String(200))
    next_of_kin_relationship: Mapped[str | None] = mapped_column(String(60))
    next_of_kin_phone: Mapped[str | None] = mapped_column(String(40))
    next_of_kin_address: Mapped[str | None] = mapped_column(Text)
    emergency_contact_name: Mapped[str | None] = mapped_column(String(200))
    emergency_contact_phone: Mapped[str | None] = mapped_column(String(40))

    #: For stipend and refund payments.
    bank_name: Mapped[str | None] = mapped_column(String(120))
    bank_account_name: Mapped[str | None] = mapped_column(String(200))
    bank_account_number: Mapped[str | None] = mapped_column(String(60))
    mobile_money_number: Mapped[str | None] = mapped_column(String(40))

    photo_attachment_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    #: A biometric template reference — the *reference*, never the template.
    #: Several institutions use fingerprint attendance for examinations; the
    #: biometric itself belongs in a system built for it, not in the SIS.
    biometric_reference: Mapped[str | None] = mapped_column(String(120))

    status: Mapped[str] = mapped_column(
        String(20), nullable=False, default=StudentStatus.ADMITTED, index=True
    )
    admitted_on: Mapped[date] = mapped_column(Date, nullable=False)
    completed_on: Mapped[date | None] = mapped_column(Date)
    graduated_on: Mapped[date | None] = mapped_column(Date)
    exited_on: Mapped[date | None] = mapped_column(Date)

    #: Denormalised for ABAC unit-scoping and for the dashboards. Rebuilt by
    #: `students.service.refresh_unit_denormalisation` whenever a programme
    #: attachment changes.
    faculty_ids: Mapped[list[uuid.UUID]] = mapped_column(
        ARRAY(UUID(as_uuid=True)), nullable=False, default=list
    )
    department_ids: Mapped[list[uuid.UUID]] = mapped_column(
        ARRAY(UUID(as_uuid=True)), nullable=False, default=list
    )
    programme_ids: Mapped[list[uuid.UUID]] = mapped_column(
        ARRAY(UUID(as_uuid=True)), nullable=False, default=list
    )
    #: Blocks that stop registration, examination or graduation. Held as a
    #: JSONB list of {kind, reason, placed_by, placed_at, cleared_at} so a
    #: library fine and a disciplinary hold can coexist and each be cleared by
    #: the office that placed it.
    holds: Mapped[list[dict[str, Any]]] = mapped_column(JSONB, nullable=False, default=list)

    programmes: Mapped[list[StudentProgramme]] = relationship(
        back_populates="student", cascade="all, delete-orphan", lazy="selectin"
    )

    __table_args__ = (
        Index("ix_student_name", "surname", "given_names"),
        Index("ix_student_faculties", "faculty_ids", postgresql_using="gin"),
        Index("ix_student_status_admitted", "status", "admitted_on"),
    )

    @property
    def full_name(self) -> str:
        return " ".join(p for p in (self.given_names, self.other_names, self.surname) if p)

    @property
    def active_holds(self) -> list[dict[str, Any]]:
        return [h for h in self.holds if not h.get("cleared_at")]


class StudentProgramme(TenantRecord):
    """A student's attachment to a curriculum version.

    `curriculum_version_id` is the load-bearing column: it is what makes the
    transcript computable years later under the rules the student entered on.
    """

    __tablename__ = "student_programme"

    student_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("student.id", ondelete="CASCADE"), nullable=False, index=True
    )
    programme_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("programme.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    curriculum_version_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("curriculum_version.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    campus_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("campus.id"))
    delivery_mode: Mapped[str] = mapped_column(String(20), nullable=False, default="full_time")
    entry_academic_year_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("academic_year.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    #: `direct`, `mature_age`, `diploma_entry`, `transfer`, `readmission`.
    entry_route: Mapped[str] = mapped_column(String(30), nullable=False, default="direct")
    #: Credits recognised from prior study. Counts toward the award but is
    #: excluded from the GPA, since the marks were awarded elsewhere.
    transferred_credits: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    sponsorship: Mapped[str] = mapped_column(String(30), nullable=False, default="private")
    sponsor_name: Mapped[str | None] = mapped_column(String(200))
    sponsor_reference: Mapped[str | None] = mapped_column(String(80))

    current_year_of_study: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    current_semester_number: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    #: Latest computed figures. Derived data, cached here because every list
    #: view and every progression check reads them and recomputing from the
    #: mark rows on each request does not scale past a few thousand students.
    #: The authoritative source is always the `course_result` rows.
    cgpa: Mapped[float | None] = mapped_column(Numeric(4, 2), index=True)
    credits_earned: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    credits_required: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    outstanding_retakes: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    progression_status: Mapped[str] = mapped_column(
        String(20), nullable=False, default="normal", index=True
    )
    computed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    is_primary: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    started_on: Mapped[date] = mapped_column(Date, nullable=False)
    #: The regulator's maximum registration period. A student past it must be
    #: discontinued or granted an extension, and the governance module reports
    #: on those still enrolled beyond it.
    expected_completion_on: Mapped[date | None] = mapped_column(Date, index=True)
    maximum_completion_on: Mapped[date | None] = mapped_column(Date)
    ended_on: Mapped[date | None] = mapped_column(Date)
    outcome: Mapped[str | None] = mapped_column(String(30))

    student: Mapped[Student] = relationship(back_populates="programmes")

    __table_args__ = (
        Index(
            "uq_student_primary_programme",
            "student_id",
            unique=True,
            postgresql_where=is_primary.is_(True),
        ),
        CheckConstraint("current_year_of_study BETWEEN 1 AND 12", name="year_sane"),
    )


class Enrolment(TenantRecord):
    """ "I am a student here this semester."

    Distinct from registration, and the statutory return counts *this*. A
    student who enrols and then fails to register for courses is still an
    enrolled student for reporting purposes and still owes fees, which is
    exactly the population an institution needs to be able to find.
    """

    __tablename__ = "enrolment"

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
    semester_number: Mapped[int] = mapped_column(Integer, nullable=False)
    #: `normal`, `retake_only`, `dead_year`, `extension`.
    enrolment_type: Mapped[str] = mapped_column(String(20), nullable=False, default="normal")
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="enrolled", index=True)
    enrolled_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    #: True once the student has produced an enrolment card; some institutions
    #: require a physical step and it is the thing students queue for.
    card_issued_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    is_late: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    approved_by_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))

    __table_args__ = (
        UniqueConstraint("student_programme_id", "semester_id", name="uq_enrolment_semester"),
    )


class Registration(TenantRecord):
    """The courses a student is taking this semester.

    A header row with `registration_course` children so the whole basket is
    approved or refused as one thing. Registering courses one at a time makes
    "does this load satisfy the credit rules" unanswerable at the moment of
    each decision, and the credit cap is exactly what registration exists to
    enforce.
    """

    __tablename__ = "registration"

    student_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("student.id", ondelete="CASCADE"), nullable=False, index=True
    )
    enrolment_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("enrolment.id", ondelete="CASCADE"), nullable=False, index=True
    )
    semester_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("semester.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="draft", index=True)
    total_credits: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    retake_credits: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    submitted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    approved_by_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    is_late: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    #: Which rules were bypassed and on whose authority. A registration that
    #: broke the credit cap or the fee threshold must carry the reason with it,
    #: because it will be queried when the student's results are boarded.
    overrides: Mapped[list[dict[str, Any]]] = mapped_column(JSONB, nullable=False, default=list)
    #: Examination card, issued once registration is approved and fees clear.
    exam_card_issued_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    courses: Mapped[list[RegistrationCourse]] = relationship(
        back_populates="registration", cascade="all, delete-orphan", lazy="selectin"
    )

    __table_args__ = (UniqueConstraint("enrolment_id", name="uq_registration_enrolment"),)


class RegistrationCourse(TenantRecord):
    """One course on one registration.

    `attempt_number` and `is_retake` are why this is not a join table. A
    retake is a distinct attempt with its own mark, and the transcript has to
    show both the failed attempt and the improved one — a university that
    overwrites the first attempt cannot answer an appeal about the second.
    """

    __tablename__ = "registration_course"

    registration_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("registration.id", ondelete="CASCADE"), nullable=False, index=True
    )
    course_offering_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("course_offering.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    student_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False, index=True)
    credit_units: Mapped[int] = mapped_column(Integer, nullable=False)
    category: Mapped[str] = mapped_column(String(30), nullable=False, default="core")
    is_retake: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, index=True)
    #: 1 for a first sitting. Institutions cap attempts, and the cap is the
    #: rule that triggers discontinuation.
    attempt_number: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    #: Taken for interest, not for credit. Excluded from GPA and from the
    #: credit total.
    is_audit: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    #: A dropped course inside the add/drop window leaves no academic trace; a
    #: withdrawal after it appears on the transcript as W. Two different
    #: things, hence two timestamps.
    dropped_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    withdrawn_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    prerequisite_waived_by_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    prerequisite_waiver_reason: Mapped[str | None] = mapped_column(String(500))

    registration: Mapped[Registration] = relationship(back_populates="courses")

    __table_args__ = (
        UniqueConstraint("registration_id", "course_offering_id", name="uq_registration_course"),
        Index("ix_registration_course_student", "student_id", "course_offering_id"),
    )


class StatusChange(TenantRecord):
    """Every transition in a student's standing, with its paperwork.

    A student's status is the single most consequential field in the system —
    it decides whether they may sit examinations, whether they owe fees and
    whether they appear in the enrolment return — so it is never simply
    updated. The change is requested, approved by someone else, dated, and
    keeps the evidence. `students.service` writes `Student.status` only
    through an approved row here.
    """

    __tablename__ = "student_status_change"

    student_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("student.id", ondelete="CASCADE"), nullable=False, index=True
    )
    student_programme_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("student_programme.id", ondelete="CASCADE")
    )
    #: `leave_of_absence`, `withdrawal`, `suspension`, `discontinuation`,
    #: `reinstatement`, `programme_transfer`, `completion`, `deceased`.
    kind: Mapped[str] = mapped_column(String(30), nullable=False, index=True)
    from_status: Mapped[str] = mapped_column(String(20), nullable=False)
    to_status: Mapped[str] = mapped_column(String(20), nullable=False)
    effective_from: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    effective_to: Mapped[date | None] = mapped_column(Date)
    reason: Mapped[str] = mapped_column(Text, nullable=False)
    #: Medical letter, sponsor's letter, minute of the disciplinary committee.
    evidence_attachment_ids: Mapped[list[uuid.UUID]] = mapped_column(
        ARRAY(UUID(as_uuid=True)), nullable=False, default=list
    )
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="requested")
    requested_by_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    requested_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    approved_by_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    rejection_reason: Mapped[str | None] = mapped_column(Text)
    #: Senate or committee minute this decision came from.
    minute_reference: Mapped[str | None] = mapped_column(String(80))


class ProgrammeTransfer(TenantRecord):
    """Moving between programmes, with credit mapping.

    The hard part is not the move, it is `credit_mapping`: which of the
    completed courses count on the new curriculum. Recorded per transfer,
    because it is a judgement made by an academic committee and it determines
    the student's remaining requirements and their fee.
    """

    __tablename__ = "programme_transfer"

    student_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("student.id", ondelete="CASCADE"), nullable=False, index=True
    )
    from_student_programme_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("student_programme.id", ondelete="RESTRICT"), nullable=False
    )
    to_programme_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("programme.id", ondelete="RESTRICT"), nullable=False
    )
    to_curriculum_version_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("curriculum_version.id", ondelete="RESTRICT"), nullable=False
    )
    effective_semester_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("semester.id", ondelete="RESTRICT"), nullable=False
    )
    reason: Mapped[str] = mapped_column(Text, nullable=False)
    #: [{from_course_id, to_course_id, credits, decision}]
    credit_mapping: Mapped[list[dict[str, Any]]] = mapped_column(
        JSONB, nullable=False, default=list
    )
    credits_carried: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    entry_year_of_study: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="requested")
    requested_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    #: Both faculties must agree; a single approval is not enough because the
    #: receiving faculty holds the seat and the releasing one holds the record.
    releasing_approved_by_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    receiving_approved_by_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    fee_implication_minor: Mapped[int | None] = mapped_column(BigInteger)


class DisciplinaryCase(TenantRecord):
    """A disciplinary matter. Special-category throughout.

    Kept in the student module rather than a separate system because the
    sanction has academic consequences — a suspension changes a status, an
    examination malpractice finding voids a result — and those consequences
    have to be traceable to the finding that caused them.
    """

    __tablename__ = "disciplinary_case"

    case_number: Mapped[str] = mapped_column(String(40), unique=True, nullable=False)
    student_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("student.id", ondelete="CASCADE"), nullable=False, index=True
    )
    #: `examination_malpractice`, `plagiarism`, `misconduct`, `property`,
    #: `harassment`, `fees_fraud`.
    category: Mapped[str] = mapped_column(String(40), nullable=False, index=True)
    reported_on: Mapped[date] = mapped_column(Date, nullable=False)
    reported_by_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    allegation: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="reported", index=True)
    #: The committee's finding and sanction, and the appeal window that runs
    #: from the date of notification.
    finding: Mapped[str | None] = mapped_column(Text)
    sanction: Mapped[str | None] = mapped_column(String(200))
    sanction_effective_from: Mapped[date | None] = mapped_column(Date)
    sanction_effective_to: Mapped[date | None] = mapped_column(Date)
    #: Results voided by the finding, if any.
    affected_course_result_ids: Mapped[list[uuid.UUID]] = mapped_column(
        ARRAY(UUID(as_uuid=True)), nullable=False, default=list
    )
    decided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    committee_minute_reference: Mapped[str | None] = mapped_column(String(80))
    appeal_deadline_on: Mapped[date | None] = mapped_column(Date)
    appeal_outcome: Mapped[str | None] = mapped_column(Text)
    #: Staff who must not see this case — the respondent's own department head
    #: where they are implicated.
    restricted_from_staff_ids: Mapped[list[uuid.UUID]] = mapped_column(
        ARRAY(UUID(as_uuid=True)), nullable=False, default=list
    )


class Clearance(TenantRecord):
    """Sign-off from every office a leaving student owes something to.

    One row per office per student, because that is how the process actually
    runs: the library, the bursar, the hall and the department each sign
    independently, and graduation waits on the last one. A single boolean on
    the student cannot tell a finalist *which* desk is holding them up, which
    is the only thing they want to know.
    """

    __tablename__ = "clearance"

    student_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("student.id", ondelete="CASCADE"), nullable=False, index=True
    )
    #: `graduation`, `withdrawal`, `transfer`, `leave`.
    purpose: Mapped[str] = mapped_column(String(30), nullable=False, index=True)
    #: `library`, `finance`, `hall`, `department`, `sports`, `laboratory`.
    office: Mapped[str] = mapped_column(String(40), nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="pending", index=True)
    obligation_note: Mapped[str | None] = mapped_column(Text)
    outstanding_amount_minor: Mapped[int | None] = mapped_column(BigInteger)
    cleared_by_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    cleared_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    __table_args__ = (
        UniqueConstraint("student_id", "purpose", "office", name="uq_clearance_office"),
    )


class SpecialExamRequest(TenantRecord):
    """A candidate who missed an examination, and what is done about it.

    The commonest and most contested request in a registry's postbag: a
    student was ill, bereaved or in hospital on the day of the paper. The
    decision has to distinguish three cases, because they carry different
    marks:

    * a *special* examination — the absence was excused, so the paper is sat
      later and marked as a **first attempt**, uncapped;
    * a *supplementary* examination — the paper was sat and failed, so the
      retake mark is **capped at the pass mark**;
    * a refusal — the absence was not excused, so the recorded mark stands.

    Conflating the first two is the mistake that matters: a student who was in
    hospital and is then capped at 50 has been penalised for being ill, and
    that is the appeal an institution loses.
    """

    __tablename__ = "special_exam_request"

    reference: Mapped[str] = mapped_column(String(40), unique=True, nullable=False, index=True)
    student_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("student.id", ondelete="CASCADE"), nullable=False, index=True
    )
    course_offering_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("course_offering.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    semester_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("semester.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    #: `special` (missed with cause, uncapped) or `supplementary` (sat and
    #: failed, capped). The kind is requested and may be changed by the
    #: approver — a student asking for a special exam having simply not turned
    #: up is granted a supplementary at best.
    kind: Mapped[str] = mapped_column(String(20), nullable=False, default="special", index=True)
    #: `illness`, `bereavement`, `hospitalisation`, `accident`,
    #: `national_duty`, `institutional_error`, `other`.
    ground: Mapped[str] = mapped_column(String(30), nullable=False)
    narrative: Mapped[str] = mapped_column(Text, nullable=False)
    missed_on: Mapped[date | None] = mapped_column(Date)
    #: Medical certificate, burial programme, police report. A request with no
    #: evidence can still be lodged — the student may be producing it — but
    #: `students.service` refuses to *approve* one, because an unevidenced
    #: special examination is indistinguishable from a favour.
    evidence_attachment_ids: Mapped[list[uuid.UUID]] = mapped_column(
        ARRAY(UUID(as_uuid=True)), nullable=False, default=list
    )
    evidence_verified_by_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    evidence_verified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    #: The institution's own fee for sitting one, where it charges. Raised as
    #: an invoice line, so it goes through the ledger like every other charge.
    fee_minor: Mapped[int | None] = mapped_column(BigInteger)
    fee_invoice_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="submitted", index=True)
    submitted_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    #: Head of department recommends, the examinations board decides. Two
    #: signatures because the department knows the circumstances and the board
    #: owns the consistency of the decision across the faculty.
    recommended_by_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    recommended_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    decided_by_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    decided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    decision_note: Mapped[str | None] = mapped_column(Text)
    minute_reference: Mapped[str | None] = mapped_column(String(80))
    #: Where the granted paper is sat. Written back when the sitting is
    #: scheduled, so a granted request that never got a date is findable.
    exam_sitting_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), index=True)
    #: True once the resulting mark has been written to a mark sheet. Prevents
    #: a second bite: one grant, one mark.
    mark_recorded: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    #: Read for the unit scope: which department decides this request is a
    #: property of the offering, not of the request.
    course_offering: Mapped[CourseOffering] = relationship(
        "CourseOffering", viewonly=True, lazy="joined"
    )

    __table_args__ = (
        UniqueConstraint(
            "student_id", "course_offering_id", "kind", name="uq_special_exam_request"
        ),
        Index("ix_special_exam_queue", "status", "semester_id"),
    )


class StudentIdCard(TenantRecord):
    """The campus identity card.

    Modelled as issuances rather than as a field on the student, because the
    history is the point: a card reported lost must stop working, and "which
    card is live" has to be answerable at a turnstile and at an examination
    hall door. A replaced card is superseded, never edited — an edited card
    number destroys the audit trail of who held what.
    """

    __tablename__ = "student_id_card"

    student_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("student.id", ondelete="CASCADE"), nullable=False, index=True
    )
    #: Printed on the card. Not the student number: a reissue gets a new
    #: serial while the student number stays, which is what lets a lost card
    #: be blocked without blocking the student.
    serial: Mapped[str] = mapped_column(String(40), unique=True, nullable=False, index=True)
    #: What a reader scans. Held separately from the serial because the
    #: encoded value is often longer and may be re-encoded on the same card.
    barcode: Mapped[str | None] = mapped_column(String(60), unique=True, index=True)
    rfid_uid: Mapped[str | None] = mapped_column(String(60), unique=True)
    photo_attachment_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    campus_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("campus.id", ondelete="SET NULL")
    )
    issued_on: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    expires_on: Mapped[date | None] = mapped_column(Date, index=True)
    #: `initial`, `replacement`, `renewal`, `programme_change`.
    reason: Mapped[str] = mapped_column(String(30), nullable=False, default="initial")
    #: `active`, `lost`, `stolen`, `damaged`, `expired`, `superseded`,
    #: `revoked`. Only one `active` card per student, enforced in the service.
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="active", index=True)
    reported_lost_on: Mapped[date | None] = mapped_column(Date)
    #: A replacement is usually charged for; the charge goes through finance
    #: like any other, and this is the link back to it.
    replacement_fee_minor: Mapped[int | None] = mapped_column(BigInteger)
    fee_invoice_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    supersedes_card_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    issued_by_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    collected_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    __table_args__ = (Index("ix_id_card_live", "student_id", "status"),)


class ExamCard(TenantRecord):
    """Permission to sit, for one student in one semester.

    Issued against a registration, and only when the gates are open: the
    registration is approved, the fee threshold is met, and attendance (where
    the institution requires it) is satisfied. The gates are recorded on the
    card rather than merely checked, because at the hall door the question is
    not "is this student cleared" but "was this card validly issued, and for
    which papers" — and a card printed before a fee was reversed has to be
    explainable months later.
    """

    __tablename__ = "exam_card"

    student_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("student.id", ondelete="CASCADE"), nullable=False, index=True
    )
    registration_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("registration.id", ondelete="CASCADE"), nullable=False, index=True
    )
    semester_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("semester.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    #: Short, human-readable, and printed as a barcode. Verified at the door
    #: and by a public endpoint, which is why it is unguessable rather than
    #: sequential.
    verification_code: Mapped[str] = mapped_column(
        String(40), unique=True, nullable=False, index=True
    )
    #: `main`, `supplementary`, `special`.
    session: Mapped[str] = mapped_column(String(20), nullable=False, default="main")
    issued_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    issued_by_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    valid_until: Mapped[date | None] = mapped_column(Date)
    #: The papers this card admits the candidate to. Denormalised from the
    #: registration at issue, because a course dropped after issue must not
    #: silently appear on a card already in the student's hand.
    course_offering_ids: Mapped[list[uuid.UUID]] = mapped_column(
        ARRAY(UUID(as_uuid=True)), nullable=False, default=list
    )
    #: The state of each gate at the moment of issue:
    #: {fee_percentage_paid, required_percentage, attendance_ok, overrides}.
    clearance_snapshot: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)
    #: Who authorised issuing despite an unmet gate, and why.
    override_reason: Mapped[str | None] = mapped_column(Text)
    overridden_by_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    #: `issued`, `revoked`, `expired`, `superseded`.
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="issued", index=True)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    revoked_reason: Mapped[str | None] = mapped_column(Text)

    __table_args__ = (
        UniqueConstraint("registration_id", "session", name="uq_exam_card_registration"),
    )


class InstitutionTransfer(TenantRecord):
    """A transfer between universities, in either direction.

    Distinct from `ProgrammeTransfer`, which moves a student between our own
    programmes. Here one side of the record belongs to somebody else, so the
    two directions are genuinely different problems:

    * *incoming* — credit is claimed from another institution and has to be
      assessed course by course against our curriculum, with a cap on how much
      may be carried (a degree awarded mostly on someone else's teaching is
      not ours to award);
    * *outgoing* — nothing is assessed, but a transcript and a letter of good
      standing are produced, the student is cleared, and their status becomes
      `transferred_out` rather than `withdrawn`. The distinction matters to
      the student, who is not dropping out.
    """

    __tablename__ = "institution_transfer"

    reference: Mapped[str] = mapped_column(String(40), unique=True, nullable=False)
    #: `incoming` or `outgoing`.
    direction: Mapped[str] = mapped_column(String(10), nullable=False, index=True)
    student_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("student.id", ondelete="CASCADE"), index=True
    )
    #: Set for an incoming transfer that has not yet been admitted: the
    #: applicant exists before the student does.
    applicant_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), index=True)
    other_institution_name: Mapped[str] = mapped_column(String(200), nullable=False)
    other_institution_country: Mapped[str] = mapped_column(String(2), nullable=False, default="UG")
    #: The regulator's register number, where there is one. An unaccredited
    #: source institution is the reason to refuse credit, and it is checkable.
    other_institution_regulator_code: Mapped[str | None] = mapped_column(String(40))
    other_programme_name: Mapped[str | None] = mapped_column(String(200))
    #: Incoming: the programme joined here. Outgoing: the one left.
    programme_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("programme.id", ondelete="SET NULL")
    )
    curriculum_version_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("curriculum_version.id", ondelete="SET NULL")
    )
    effective_semester_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("semester.id", ondelete="SET NULL")
    )
    entry_year_of_study: Mapped[int | None] = mapped_column(Integer)
    #: [{external_code, external_title, external_credits, external_grade,
    #:   course_id, credits_awarded, decision, assessor_id}] — the assessment,
    #: course by course, with who made each call.
    credit_assessment: Mapped[list[dict[str, Any]]] = mapped_column(
        JSONB, nullable=False, default=list
    )
    credits_claimed: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    credits_awarded: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    #: The cap the decision was measured against, copied from the curriculum
    #: version so the record stands up after the rule changes.
    credit_transfer_cap_percent: Mapped[int | None] = mapped_column(Integer)
    #: Documents from the other institution, plus our own letters out.
    evidence_attachment_ids: Mapped[list[uuid.UUID]] = mapped_column(
        ARRAY(UUID(as_uuid=True)), nullable=False, default=list
    )
    transcript_issued_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    letter_issued_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="requested", index=True)
    requested_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    assessed_by_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    assessed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    approved_by_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    senate_minute_reference: Mapped[str | None] = mapped_column(String(80))
    decision_note: Mapped[str | None] = mapped_column(Text)

    __table_args__ = (
        CheckConstraint("direction IN ('incoming', 'outgoing')", name="ck_transfer_direction"),
        Index("ix_institution_transfer_queue", "direction", "status"),
    )
