"""Admissions and enrolment: from an enquiry to a registered student.

The module ends where `students` begins — at enrolment. An admitted applicant
becomes a `Student` exactly once, in `admissions.service.enrol`, and after that
this module never writes to them again. Keeping that seam sharp is what stops
two modules disagreeing about who is enrolled.
"""

from __future__ import annotations

import uuid
from datetime import date, datetime
from enum import StrEnum
from typing import Any

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


class SchemeStatus(StrEnum):
    DRAFT = "draft"
    OPEN = "open"
    CLOSED = "closed"
    #: Selection done, offers out. Applications already in review are
    #: unaffected by the scheme closing, which is why these are separate.
    COMPLETED = "completed"


class AdmissionScheme(TenantRecord):
    """One intake round, e.g. "2026/2027 Government Sponsorship".

    An institution runs several concurrently and they have genuinely different
    rules: private sponsorship, government sponsorship, mature-age entry,
    diploma-holders' entry and postgraduate all differ in fee, deadline,
    weighting and who selects. Hence a scheme rather than a global "admissions
    window".
    """

    __tablename__ = "admission_scheme"

    code: Mapped[str] = mapped_column(String(40), unique=True, nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    academic_year_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("academic_year.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    entry_semester_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("semester.id", ondelete="SET NULL")
    )
    #: `government`, `private`, `mature_age`, `diploma_entry`, `postgraduate`,
    #: `international`. Drives which eligibility rule set applies.
    entry_scheme: Mapped[str] = mapped_column(String(30), nullable=False, index=True)
    study_level: Mapped[str] = mapped_column(String(30), nullable=False, default="undergraduate")

    opens_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    closes_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    #: Late applications are accepted until here, at a higher fee. Modelled
    #: because every institution does it and pretending otherwise means the
    #: registry works around the system with paper forms.
    late_closes_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    results_due_on: Mapped[date | None] = mapped_column(Date)
    acceptance_deadline_on: Mapped[date | None] = mapped_column(Date)

    application_fee_minor: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)
    late_fee_minor: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)
    currency: Mapped[str] = mapped_column(String(3), nullable=False, default="UGX")
    #: Applications are only visible to selectors once the fee has settled.
    #: Without this the office spends the cycle reviewing unpaid applications.
    requires_fee_before_review: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)

    max_programme_choices: Mapped[int] = mapped_column(Integer, nullable=False, default=6)
    #: Weighting for the aggregate score, e.g.
    #: {"best_two_principal": 0.5, "subsidiary": 0.2, "interview": 0.3}.
    #: Held as data because it changes per scheme per year and hard-coding it
    #: means a release every August.
    scoring_weights: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)
    requires_interview: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    requires_entrance_exam: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    status: Mapped[str] = mapped_column(
        String(20), nullable=False, default=SchemeStatus.DRAFT, index=True
    )
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    published_by_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))

    intakes: Mapped[list[ProgrammeIntake]] = relationship(
        back_populates="scheme", cascade="all, delete-orphan"
    )

    __table_args__ = (CheckConstraint("closes_at > opens_at", name="scheme_window_ordered"),)


class ProgrammeIntake(TenantRecord):
    """Seats in one programme under one scheme.

    `approved_intake` is the number the academic board signed off and is the
    ceiling the `admissions.intake-capacity` policy enforces. `offers_issued`
    is deliberately allowed to exceed `filled` — institutions over-offer for
    expected declines — but exceeding the *approved* figure needs the override
    grant, so the over-admission has a name attached to it.
    """

    __tablename__ = "programme_intake"

    scheme_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("admission_scheme.id", ondelete="CASCADE"), nullable=False, index=True
    )
    programme_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("programme.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    campus_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("campus.id"))
    approved_intake: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    #: Places held back for a statutory quota — district quota, sports, or the
    #: disability allocation many national universities are required to keep.
    reserved_seats: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)
    minimum_aggregate: Mapped[float | None] = mapped_column(Numeric(6, 2))
    #: Last year's lowest admitted score. Shown to applicants as a guide, which
    #: measurably reduces hopeless applications and the fee refunds that follow.
    previous_cutoff: Mapped[float | None] = mapped_column(Numeric(6, 2))
    tuition_per_semester_minor: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)
    #: Subject codes an applicant must have sat, and the grade needed.
    required_subjects: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)

    applications_received: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    offers_issued: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    offers_accepted: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    enrolled_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    cutoff_score: Mapped[float | None] = mapped_column(Numeric(6, 2))

    scheme: Mapped[AdmissionScheme] = relationship(back_populates="intakes")

    __table_args__ = (
        UniqueConstraint("scheme_id", "programme_id", "campus_id", name="uq_programme_intake"),
        CheckConstraint("approved_intake >= 0", name="intake_non_negative"),
    )


class Applicant(TenantRecord):
    """A person applying. Survives across cycles.

    Separate from `Application` because reapplying is normal — a candidate who
    missed the cut-off for Medicine applies again next year — and the second
    application should find the first, along with the verified documents
    already on file. Also survives *into* the student record: `student_id` is
    what makes "which cohort did this graduate apply in" answerable years later.
    """

    __tablename__ = "applicant"

    reference: Mapped[str] = mapped_column(String(30), unique=True, nullable=False, index=True)
    surname: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    given_names: Mapped[str] = mapped_column(String(200), nullable=False)
    other_names: Mapped[str | None] = mapped_column(String(200))
    date_of_birth: Mapped[date] = mapped_column(Date, nullable=False)
    #: Free text, not an enum. An enum here forces the registry to file a
    #: person into a box the institution's own forms do not use, and the field
    #: exists for statutory reporting, which asks for the categories the
    #: regulator defines that year.
    sex: Mapped[str] = mapped_column(String(20), nullable=False)
    marital_status: Mapped[str | None] = mapped_column(String(20))
    nationality: Mapped[str] = mapped_column(String(60), nullable=False, default="Ugandan")
    country_code: Mapped[str] = mapped_column(String(2), nullable=False, default="UG")
    #: District/state of origin. Drives district-quota selection, which is a
    #: statutory obligation for public universities in several countries.
    district_of_origin: Mapped[str | None] = mapped_column(String(80), index=True)
    home_address: Mapped[str | None] = mapped_column(Text)

    email: Mapped[str] = mapped_column(String(200), nullable=False, index=True)
    phone: Mapped[str] = mapped_column(String(40), nullable=False)
    alternate_phone: Mapped[str | None] = mapped_column(String(40))

    national_id: Mapped[str | None] = mapped_column(String(60))
    passport_number: Mapped[str | None] = mapped_column(String(60))
    #: Special-category. Masked by default and readable only with
    #: `admissions:read_sensitive` or `welfare:support`.
    disability: Mapped[str | None] = mapped_column(String(200))
    disability_detail: Mapped[str | None] = mapped_column(Text)
    refugee_status: Mapped[str | None] = mapped_column(String(60))

    guardian_name: Mapped[str | None] = mapped_column(String(200))
    guardian_relationship: Mapped[str | None] = mapped_column(String(60))
    guardian_phone: Mapped[str | None] = mapped_column(String(40))
    guardian_email: Mapped[str | None] = mapped_column(String(200))
    guardian_occupation: Mapped[str | None] = mapped_column(String(120))

    account_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), index=True)
    student_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), index=True)
    #: Set when the registry confirms two applicant records are one person.
    merged_into_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))

    __table_args__ = (
        Index("ix_applicant_name_dob", "surname", "given_names", "date_of_birth"),
        Index("ix_applicant_identity", "national_id", postgresql_where=national_id.isnot(None)),
    )

    @property
    def full_name(self) -> str:
        return " ".join(p for p in (self.given_names, self.other_names, self.surname) if p)


class ApplicationStatus(StrEnum):
    DRAFT = "draft"
    SUBMITTED = "submitted"
    #: Fee settled and documents present. Only these reach a selector.
    AWAITING_FEE = "awaiting_fee"
    UNDER_REVIEW = "under_review"
    INCOMPLETE = "incomplete"
    INTERVIEW = "interview"
    RECOMMENDED = "recommended"
    ADMITTED = "admitted"
    WAITLISTED = "waitlisted"
    REJECTED = "rejected"
    OFFER_ACCEPTED = "offer_accepted"
    OFFER_DECLINED = "offer_declined"
    ENROLLED = "enrolled"
    WITHDRAWN = "withdrawn"


class Application(TenantRecord):
    """One applicant's bid in one scheme, with ranked programme choices."""

    __tablename__ = "application"

    number: Mapped[str] = mapped_column(String(30), unique=True, nullable=False, index=True)
    applicant_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("applicant.id", ondelete="CASCADE"), nullable=False, index=True
    )
    scheme_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("admission_scheme.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    status: Mapped[str] = mapped_column(
        String(30), nullable=False, default=ApplicationStatus.DRAFT, index=True
    )

    submitted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    is_late: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    fee_invoice_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), index=True)
    fee_settled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    #: Computed from the applicant's qualifications under the scheme's weights.
    #: Stored, not derived on read: the weights change between cycles and a
    #: score recomputed under next year's rules is not the score the applicant
    #: was selected on, which is precisely what an admissions appeal disputes.
    aggregate_score: Mapped[float | None] = mapped_column(Numeric(8, 3), index=True)
    interview_score: Mapped[float | None] = mapped_column(Numeric(6, 2))
    entrance_exam_score: Mapped[float | None] = mapped_column(Numeric(6, 2))
    final_score: Mapped[float | None] = mapped_column(Numeric(8, 3), index=True)
    scored_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    #: The exact weights used, copied at scoring time. See above.
    scoring_snapshot: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)

    #: The choice that was actually admitted. Null until a decision.
    admitted_choice_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    decided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    decided_by_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    decision_reason: Mapped[str | None] = mapped_column(Text)
    #: A candidate on a waiting list needs an ordinal, and it must be stable
    #: enough to publish.
    waitlist_position: Mapped[int | None] = mapped_column(Integer)

    accepted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    declined_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    decline_reason: Mapped[str | None] = mapped_column(String(300))
    enrolled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    #: Denormalised so unit-scoped ABAC rules can decide without loading every
    #: choice row: a dean reviews applications whose choices touch their
    #: faculty.
    faculty_ids: Mapped[list[uuid.UUID]] = mapped_column(
        ARRAY(UUID(as_uuid=True)), nullable=False, default=list
    )

    review_notes: Mapped[str | None] = mapped_column(Text)
    flags: Mapped[list[str]] = mapped_column(ARRAY(String(40)), nullable=False, default=list)

    applicant: Mapped[Applicant] = relationship(lazy="joined")
    choices: Mapped[list[ApplicationChoice]] = relationship(
        back_populates="application",
        cascade="all, delete-orphan",
        lazy="selectin",
        order_by="ApplicationChoice.rank",
    )
    qualifications: Mapped[list[Qualification]] = relationship(
        back_populates="application", cascade="all, delete-orphan", lazy="selectin"
    )

    __table_args__ = (
        UniqueConstraint("applicant_id", "scheme_id", name="uq_application_applicant_scheme"),
        Index("ix_application_scheme_status", "scheme_id", "status"),
        Index("ix_application_ranking", "scheme_id", "final_score"),
        Index("ix_application_faculties", "faculty_ids", postgresql_using="gin"),
    )


class ApplicationChoice(TenantRecord):
    """A ranked programme preference."""

    __tablename__ = "application_choice"

    application_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("application.id", ondelete="CASCADE"), nullable=False, index=True
    )
    programme_intake_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("programme_intake.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    rank: Mapped[int] = mapped_column(Integer, nullable=False)
    #: Whether the applicant meets the intake's stated subject requirements.
    #: Computed on submission so a selector filters on it instead of
    #: re-deriving it for 12,000 applications.
    is_eligible: Mapped[bool | None] = mapped_column(Boolean, index=True)
    ineligibility_reasons: Mapped[list[str]] = mapped_column(
        ARRAY(String(200)), nullable=False, default=list
    )
    score: Mapped[float | None] = mapped_column(Numeric(8, 3))
    outcome: Mapped[str | None] = mapped_column(String(30), index=True)

    application: Mapped[Application] = relationship(back_populates="choices")

    __table_args__ = (
        UniqueConstraint("application_id", "rank", name="uq_choice_rank"),
        UniqueConstraint("application_id", "programme_intake_id", name="uq_choice_programme"),
        CheckConstraint("rank >= 1 AND rank <= 12", name="rank_sane"),
    )


class Qualification(TenantRecord):
    """A prior qualification and its subject grades.

    Grades as rows rather than a JSON blob, because selection queries filter on
    them — "everyone with at least a C in Biology" is the whole job of an
    admissions office in July, and it must be indexable.
    """

    __tablename__ = "qualification"

    application_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("application.id", ondelete="CASCADE"), index=True
    )
    applicant_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("applicant.id", ondelete="CASCADE"), nullable=False, index=True
    )
    #: `uace`, `uce`, `sscse`, `kcse`, `diploma`, `degree`, `ib`, `a_level`.
    kind: Mapped[str] = mapped_column(String(30), nullable=False, index=True)
    awarding_body: Mapped[str | None] = mapped_column(String(200))
    institution_name: Mapped[str] = mapped_column(String(300), nullable=False)
    index_number: Mapped[str | None] = mapped_column(String(60), index=True)
    year_completed: Mapped[int] = mapped_column(Integer, nullable=False)
    #: For a prior degree/diploma: the classification and GPA, which is what
    #: diploma-entry and postgraduate schemes select on.
    classification: Mapped[str | None] = mapped_column(String(60))
    gpa: Mapped[float | None] = mapped_column(Numeric(4, 2))
    #: Aggregate/points as the awarding body computed it.
    aggregate: Mapped[float | None] = mapped_column(Numeric(6, 2))
    #: Verified against the examinations board, where an API exists. Until it
    #: is, a selection based on this is provisional.
    verified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    verified_by_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    verification_source: Mapped[str | None] = mapped_column(String(60))

    application: Mapped[Application | None] = relationship(back_populates="qualifications")
    subjects: Mapped[list[QualificationSubject]] = relationship(
        back_populates="qualification", cascade="all, delete-orphan", lazy="selectin"
    )


class QualificationSubject(TenantRecord):
    __tablename__ = "qualification_subject"

    qualification_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("qualification.id", ondelete="CASCADE"), nullable=False, index=True
    )
    subject_code: Mapped[str] = mapped_column(String(20), nullable=False, index=True)
    subject_name: Mapped[str] = mapped_column(String(120), nullable=False)
    #: `principal`, `subsidiary`, `general_paper`, `core`, `elective`.
    level: Mapped[str | None] = mapped_column(String(20))
    grade: Mapped[str] = mapped_column(String(10), nullable=False)
    #: The grade converted to points under the awarding body's scale, so
    #: cross-system comparison is possible at all.
    points: Mapped[float | None] = mapped_column(Numeric(5, 2))
    mark: Mapped[float | None] = mapped_column(Numeric(5, 2))

    qualification: Mapped[Qualification] = relationship(back_populates="subjects")

    __table_args__ = (UniqueConstraint("qualification_id", "subject_code", name="uq_qual_subject"),)


class SelectionList(TenantRecord):
    """A batch of decisions, approved as a unit.

    Admissions decisions are made in a meeting and published together, not one
    at a time. Batching them is also what makes the approval meaningful: the
    head of admissions approves *this list*, and the audit trail records the
    list, its composition and the cut-off it implies.
    """

    __tablename__ = "selection_list"

    scheme_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("admission_scheme.id", ondelete="CASCADE"), nullable=False, index=True
    )
    programme_intake_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("programme_intake.id", ondelete="CASCADE"), index=True
    )
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    round_number: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="draft", index=True)
    method: Mapped[str] = mapped_column(String(30), nullable=False, default="merit")
    cutoff_score: Mapped[float | None] = mapped_column(Numeric(8, 3))
    admitted_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    waitlisted_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    rejected_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    prepared_by_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    #: Approver must differ from preparer — `identity.separation-of-duties`.
    approved_by_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    notes: Mapped[str | None] = mapped_column(Text)
    #: How the list was produced, kept so a disputed selection can be replayed.
    generation_snapshot: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)


class Offer(TenantRecord):
    """An admission offer, and the applicant's response."""

    __tablename__ = "offer"

    application_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("application.id", ondelete="CASCADE"), nullable=False, index=True
    )
    programme_intake_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("programme_intake.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    selection_list_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("selection_list.id", ondelete="SET NULL"), index=True
    )
    #: The intake's approved number and offers already issued are what the
    #: over-offer guard compares; neither is a column here.
    programme_intake: Mapped[ProgrammeIntake] = relationship(viewonly=True, lazy="joined")
    reference: Mapped[str] = mapped_column(String(40), unique=True, nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="issued", index=True)
    #: `unconditional`, or conditional on a pending result or a document.
    condition: Mapped[str | None] = mapped_column(Text)
    sponsorship: Mapped[str] = mapped_column(String(30), nullable=False, default="private")
    tuition_per_semester_minor: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)
    issued_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    respond_by: Mapped[date] = mapped_column(Date, nullable=False)
    responded_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    #: Acceptance usually requires a deposit; the offer is not firm until it
    #: settles, and this is the link to the invoice that proves it.
    acceptance_invoice_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    withdrawn_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    withdrawal_reason: Mapped[str | None] = mapped_column(String(500))
    #: The generated admission letter.
    letter_attachment_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))

    application: Mapped[Application] = relationship(lazy="joined")


class ApplicationEvent(TenantRecord):
    """The application's own history, in the applicant's language.

    Distinct from the audit trail, which is written for auditors. This is what
    an applicant sees on their status page, and what a counter clerk reads
    aloud on the phone. The audit trail records that a field changed; this
    records "your application was moved to interview".
    """

    __tablename__ = "application_event"

    application_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("application.id", ondelete="CASCADE"), nullable=False, index=True
    )
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    kind: Mapped[str] = mapped_column(String(40), nullable=False)
    from_status: Mapped[str | None] = mapped_column(String(30))
    to_status: Mapped[str | None] = mapped_column(String(30))
    message: Mapped[str] = mapped_column(Text, nullable=False)
    #: False for internal notes the applicant must not see.
    visible_to_applicant: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    actor_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))

    __table_args__ = (Index("ix_application_event_time", "application_id", "occurred_at"),)
