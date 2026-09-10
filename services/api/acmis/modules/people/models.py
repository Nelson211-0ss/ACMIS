"""Faculty and staff management.

An HR module in an academic system, not a general-purpose HRIS. It stops at
the point where payroll begins: it holds the appointment, the grade and the
salary scale (because promotion and workload decisions need them), and it
records *that* a payslip exists — but the payroll run itself belongs in the
institution's finance system, and pretending otherwise is how a student
records system ends up owning the staff salary bill.

What it does own, and what a general HRIS gets wrong: academic workload,
teaching allocation, qualifications for accreditation returns, and the
supervision load of postgraduate students.
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


class StaffCategory(StrEnum):
    ACADEMIC = "academic"
    #: Laboratory technicians, librarians, IT — support the academic function
    #: but do not teach. Kept distinct because accreditation returns count
    #: academic staff and only academic staff.
    ACADEMIC_SUPPORT = "academic_support"
    ADMINISTRATIVE = "administrative"
    #: Paid per contact hour. The largest population in many faculties and the
    #: one whose mark-entry authority causes the most trouble, since it lapses
    #: at the end of the contract.
    PART_TIME = "part_time"
    VISITING = "visiting"
    EXTERNAL_EXAMINER = "external_examiner"
    SUPPORT = "support"


class Staff(TenantRecord):
    """A member of staff. Bio-data and current standing."""

    __tablename__ = "staff"

    staff_number: Mapped[str] = mapped_column(String(30), unique=True, nullable=False, index=True)
    account_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), index=True)
    #: A staff member who is also a student here. Populated so the assessment
    #: separation-of-duties rules can see the conflict.
    student_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), index=True)

    title: Mapped[str | None] = mapped_column(String(30))
    surname: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    given_names: Mapped[str] = mapped_column(String(200), nullable=False)
    other_names: Mapped[str | None] = mapped_column(String(200))
    #: How the name appears in the prospectus and on a transcript signature
    #: block, e.g. "Prof. J. A. Okello, PhD".
    display_title: Mapped[str | None] = mapped_column(String(300))

    date_of_birth: Mapped[date | None] = mapped_column(Date)
    sex: Mapped[str | None] = mapped_column(String(20))
    nationality: Mapped[str] = mapped_column(String(60), nullable=False, default="Ugandan")
    national_id: Mapped[str | None] = mapped_column(String(60))
    passport_number: Mapped[str | None] = mapped_column(String(60))
    #: Required for a non-national appointment; its expiry is a compliance
    #: date the governance module reports on.
    work_permit_number: Mapped[str | None] = mapped_column(String(60))
    work_permit_expires_on: Mapped[date | None] = mapped_column(Date, index=True)

    email: Mapped[str] = mapped_column(String(200), nullable=False, index=True)
    personal_email: Mapped[str | None] = mapped_column(String(200))
    phone: Mapped[str] = mapped_column(String(40), nullable=False)
    office_extension: Mapped[str | None] = mapped_column(String(20))
    postal_address: Mapped[str | None] = mapped_column(Text)
    office_room_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("room.id"))

    next_of_kin_name: Mapped[str | None] = mapped_column(String(200))
    next_of_kin_phone: Mapped[str | None] = mapped_column(String(40))
    #: Special-category; behind `people:payroll` or the individual themselves.
    medical_notes: Mapped[str | None] = mapped_column(Text)
    disability: Mapped[str | None] = mapped_column(String(200))

    category: Mapped[str] = mapped_column(String(30), nullable=False, index=True)
    #: The academic rank as the institution names it: Professor, Associate
    #: Professor, Senior Lecturer, Lecturer, Assistant Lecturer, Teaching
    #: Assistant. Free text because the ladder differs by country.
    rank: Mapped[str | None] = mapped_column(String(60), index=True)
    #: Public-university salary scales, e.g. "M5". Behind the payroll grant.
    salary_scale: Mapped[str | None] = mapped_column(String(20))
    highest_qualification: Mapped[str | None] = mapped_column(String(60))
    #: PhD-holding academic staff as a proportion of the total is a headline
    #: accreditation metric, which is why it is a queryable column.
    has_doctorate: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, index=True)
    specialisation: Mapped[str | None] = mapped_column(String(300))
    orcid: Mapped[str | None] = mapped_column(String(40))
    biography: Mapped[str | None] = mapped_column(Text)
    photo_attachment_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))

    primary_unit_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("academic_unit.id", ondelete="SET NULL"), index=True
    )
    #: Denormalised reach for ABAC, from primary and secondary appointments.
    faculty_ids: Mapped[list[uuid.UUID]] = mapped_column(
        ARRAY(UUID(as_uuid=True)), nullable=False, default=list
    )
    department_ids: Mapped[list[uuid.UUID]] = mapped_column(
        ARRAY(UUID(as_uuid=True)), nullable=False, default=list
    )

    status: Mapped[str] = mapped_column(String(20), nullable=False, default="active", index=True)
    first_appointed_on: Mapped[date | None] = mapped_column(Date)
    #: Contract end. A lapsed contract must revoke mark-entry authority, which
    #: the teaching-allocation date bounds are what actually do.
    contract_ends_on: Mapped[date | None] = mapped_column(Date, index=True)
    retirement_date: Mapped[date | None] = mapped_column(Date)
    exited_on: Mapped[date | None] = mapped_column(Date)
    exit_reason: Mapped[str | None] = mapped_column(String(200))

    bank_name: Mapped[str | None] = mapped_column(String(120))
    bank_account_number: Mapped[str | None] = mapped_column(String(60))
    tin_number: Mapped[str | None] = mapped_column(String(40))
    nssf_number: Mapped[str | None] = mapped_column(String(40))

    appointments: Mapped[list[Appointment]] = relationship(
        back_populates="staff", cascade="all, delete-orphan", lazy="selectin"
    )
    qualifications: Mapped[list[StaffQualification]] = relationship(
        back_populates="staff", cascade="all, delete-orphan"
    )

    __table_args__ = (
        Index("ix_staff_name", "surname", "given_names"),
        Index("ix_staff_departments", "department_ids", postgresql_using="gin"),
    )

    @property
    def full_name(self) -> str:
        return " ".join(p for p in (self.title, self.given_names, self.surname) if p)


class EstablishmentPost(TenantRecord):
    """An approved, funded position in the staff establishment.

    Universities are constrained by an approved establishment, not by budget
    alone: a department may have money and still not be permitted to appoint,
    because the post does not exist. Modelling posts separately from people is
    what makes "how many approved lecturer posts are vacant in Chemistry"
    answerable, which is the question every faculty board asks.
    """

    __tablename__ = "establishment_post"

    code: Mapped[str] = mapped_column(String(30), unique=True, nullable=False)
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    unit_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("academic_unit.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    category: Mapped[str] = mapped_column(String(30), nullable=False)
    rank: Mapped[str | None] = mapped_column(String(60))
    salary_scale: Mapped[str | None] = mapped_column(String(20))
    approved_count: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    filled_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    is_funded: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    approved_by_council_on: Mapped[date | None] = mapped_column(Date)
    council_minute_reference: Mapped[str | None] = mapped_column(String(80))
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="active")

    __table_args__ = (
        CheckConstraint("filled_count <= approved_count", name="post_not_overfilled"),
    )


class Appointment(TenantRecord):
    """One person holding one post in one unit for a period.

    A staff member has several over a career, and often several at once — a
    professor with a primary appointment in Physics and a joint one in
    Engineering. The `is_primary` partial unique index enforces exactly one
    primary at a time, since that is what drives their reporting line and
    their default unit.
    """

    __tablename__ = "appointment"

    staff_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("staff.id", ondelete="CASCADE"), nullable=False, index=True
    )
    post_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("establishment_post.id", ondelete="SET NULL"), index=True
    )
    unit_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("academic_unit.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    rank: Mapped[str | None] = mapped_column(String(60))
    #: `permanent`, `contract`, `probation`, `part_time`, `visiting`, `acting`.
    kind: Mapped[str] = mapped_column(String(30), nullable=False, default="contract")
    fte: Mapped[float] = mapped_column(Numeric(4, 3), nullable=False, default=1.0)
    is_primary: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    #: An administrative office held alongside an academic appointment: Dean,
    #: Head of Department, Deputy Vice-Chancellor. This is what grants the
    #: unit-scoped role, and its end date is what revokes it.
    administrative_office: Mapped[str | None] = mapped_column(String(120), index=True)

    starts_on: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    ends_on: Mapped[date | None] = mapped_column(Date, index=True)
    probation_ends_on: Mapped[date | None] = mapped_column(Date)
    salary_scale: Mapped[str | None] = mapped_column(String(20))
    #: Behind `people:payroll` — masked for every line manager.
    gross_salary_minor: Mapped[int | None] = mapped_column(BigInteger)
    currency: Mapped[str] = mapped_column(String(3), nullable=False, default="UGX")

    status: Mapped[str] = mapped_column(String(20), nullable=False, default="proposed", index=True)
    proposed_by_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    approved_by_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    council_minute_reference: Mapped[str | None] = mapped_column(String(80))
    contract_attachment_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    termination_reason: Mapped[str | None] = mapped_column(String(300))

    staff: Mapped[Staff] = relationship(back_populates="appointments")

    __table_args__ = (
        Index(
            "uq_appointment_primary", "staff_id", unique=True, postgresql_where=is_primary.is_(True)
        ),
        CheckConstraint("fte > 0 AND fte <= 2", name="fte_sane"),
        CheckConstraint("ends_on IS NULL OR ends_on > starts_on", name="appointment_ordered"),
    )


class StaffQualification(TenantRecord):
    """A degree or professional qualification, verified.

    Verification is not paperwork for its own sake: accreditation bodies audit
    staff qualifications, and an unverified doctorate on an accreditation
    return is the kind of finding that suspends a programme.
    """

    __tablename__ = "staff_qualification"

    staff_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("staff.id", ondelete="CASCADE"), nullable=False, index=True
    )
    level: Mapped[str] = mapped_column(String(40), nullable=False, index=True)
    title: Mapped[str] = mapped_column(String(300), nullable=False)
    discipline: Mapped[str | None] = mapped_column(String(200))
    institution_name: Mapped[str] = mapped_column(String(300), nullable=False)
    country_code: Mapped[str | None] = mapped_column(String(2))
    year_awarded: Mapped[int] = mapped_column(Integer, nullable=False)
    classification: Mapped[str | None] = mapped_column(String(60))
    certificate_attachment_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    verified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    verified_by_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    #: Foreign qualifications need national equivalence before they count.
    equivalence_reference: Mapped[str | None] = mapped_column(String(80))

    staff: Mapped[Staff] = relationship(back_populates="qualifications")


class Workload(TenantRecord):
    """A member of staff's total load for one semester.

    Teaching, supervision, administration and research in one row, because the
    complaint a workload system exists to answer is always comparative: "I am
    teaching four courses and supervising nine masters students while my
    colleague teaches one". Totals are cached and recomputed from the
    allocation and supervision rows.
    """

    __tablename__ = "workload"

    staff_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("staff.id", ondelete="CASCADE"), nullable=False, index=True
    )
    semester_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("semester.id", ondelete="CASCADE"), nullable=False, index=True
    )
    teaching_hours: Mapped[float] = mapped_column(Numeric(6, 2), nullable=False, default=0)
    #: Credit units taught, which is the unit most institutions norm against.
    credit_units_taught: Mapped[float] = mapped_column(Numeric(6, 2), nullable=False, default=0)
    course_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    student_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    supervision_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    administrative_hours: Mapped[float] = mapped_column(Numeric(6, 2), nullable=False, default=0)
    research_hours: Mapped[float] = mapped_column(Numeric(6, 2), nullable=False, default=0)
    total_load_hours: Mapped[float] = mapped_column(Numeric(7, 2), nullable=False, default=0)
    #: The institution's norm for this rank and category. Over-norm load is
    #: what triggers a part-time appointment or a load transfer.
    norm_hours: Mapped[float | None] = mapped_column(Numeric(6, 2))
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="draft")
    approved_by_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    notes: Mapped[str | None] = mapped_column(Text)

    __table_args__ = (
        UniqueConstraint("staff_id", "semester_id", name="uq_workload_staff_semester"),
    )

    @property
    def is_over_norm(self) -> bool:
        return self.norm_hours is not None and float(self.total_load_hours) > float(self.norm_hours)


class Supervision(TenantRecord):
    """Postgraduate supervision.

    Its own table because supervision has a lifecycle teaching does not: a
    supervisor is appointed, may be changed mid-candidature, and the load
    persists across semesters until the thesis is examined. Also because
    supervision *capacity* is regulated — most institutions cap the number of
    doctoral candidates one supervisor may hold.
    """

    __tablename__ = "supervision"

    staff_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("staff.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    student_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False, index=True)
    role: Mapped[str] = mapped_column(String(30), nullable=False, default="principal")
    thesis_title: Mapped[str | None] = mapped_column(Text)
    starts_on: Mapped[date] = mapped_column(Date, nullable=False)
    ends_on: Mapped[date | None] = mapped_column(Date)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="active", index=True)
    #: Progress reports are a regulatory requirement for doctoral candidates.
    last_report_on: Mapped[date | None] = mapped_column(Date)
    next_report_due_on: Mapped[date | None] = mapped_column(Date, index=True)
    handover_from_staff_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))

    __table_args__ = (UniqueConstraint("staff_id", "student_id", "role", name="uq_supervision"),)


class LeaveType(StrEnum):
    ANNUAL = "annual"
    SICK = "sick"
    MATERNITY = "maternity"
    PATERNITY = "paternity"
    #: Distinctly academic and long: a semester or a year, during which
    #: teaching must be reallocated. The reallocation is why leave lives in
    #: this module and not only in an HR system.
    SABBATICAL = "sabbatical"
    STUDY = "study"
    COMPASSIONATE = "compassionate"
    UNPAID = "unpaid"


class LeaveRequest(TenantRecord):
    """A leave application and its approval chain."""

    __tablename__ = "leave_request"

    staff_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("staff.id", ondelete="CASCADE"), nullable=False, index=True
    )
    #: The unit scope every line-management rule matches on lives on the staff
    #: row, not here.
    staff: Mapped[Staff] = relationship(viewonly=True, lazy="joined")
    leave_type: Mapped[str] = mapped_column(String(30), nullable=False, index=True)
    starts_on: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    ends_on: Mapped[date] = mapped_column(Date, nullable=False)
    working_days: Mapped[float] = mapped_column(Numeric(5, 1), nullable=False)
    reason: Mapped[str | None] = mapped_column(Text)
    #: Who covers the teaching. A leave request that does not say is refused
    #: by the service layer during a teaching semester, because unallocated
    #: courses are the observable consequence of approved leave.
    cover_staff_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    cover_arrangements: Mapped[str | None] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="submitted", index=True)
    #: Supervisor first, then HR. Both recorded; neither may be the applicant.
    supervisor_approved_by_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    supervisor_approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    hr_approved_by_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    hr_approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    rejection_reason: Mapped[str | None] = mapped_column(Text)
    cancelled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    evidence_attachment_ids: Mapped[list[uuid.UUID]] = mapped_column(
        ARRAY(UUID(as_uuid=True)), nullable=False, default=list
    )

    __table_args__ = (
        CheckConstraint("ends_on >= starts_on", name="leave_ordered"),
        Index("ix_leave_overlap", "staff_id", "starts_on", "ends_on"),
    )


class LeaveBalance(TenantRecord):
    """Entitlement and consumption per leave type per year."""

    __tablename__ = "leave_balance"

    staff_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("staff.id", ondelete="CASCADE"), nullable=False, index=True
    )
    year: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    leave_type: Mapped[str] = mapped_column(String(30), nullable=False)
    entitlement_days: Mapped[float] = mapped_column(Numeric(5, 1), nullable=False, default=0)
    #: Days permitted to roll over from last year, which most institutions cap.
    carried_forward_days: Mapped[float] = mapped_column(Numeric(5, 1), nullable=False, default=0)
    taken_days: Mapped[float] = mapped_column(Numeric(5, 1), nullable=False, default=0)
    #: Approved but not yet taken. Held separately so a second request cannot
    #: be approved against days already committed.
    committed_days: Mapped[float] = mapped_column(Numeric(5, 1), nullable=False, default=0)

    __table_args__ = (UniqueConstraint("staff_id", "year", "leave_type", name="uq_leave_balance"),)

    @property
    def available_days(self) -> float:
        return float(
            self.entitlement_days
            + self.carried_forward_days
            - self.taken_days
            - self.committed_days
        )


class StaffDevelopment(TenantRecord):
    """Training, conferences, promotion applications and appraisals.

    One table with a `kind`, because these are all "something that happened to
    this person's career", they all carry evidence, and every institution wants
    a different subset of them on the promotion form.
    """

    __tablename__ = "staff_development"

    staff_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("staff.id", ondelete="CASCADE"), nullable=False, index=True
    )
    #: `training`, `conference`, `publication`, `appraisal`, `promotion`,
    #: `award`, `grant`.
    kind: Mapped[str] = mapped_column(String(30), nullable=False, index=True)
    title: Mapped[str] = mapped_column(String(400), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    occurred_on: Mapped[date | None] = mapped_column(Date, index=True)
    #: For an appraisal or promotion: the outcome and the score.
    outcome: Mapped[str | None] = mapped_column(String(120))
    score: Mapped[float | None] = mapped_column(Numeric(6, 2))
    #: For a publication: the DOI and citation, used in accreditation returns.
    citation: Mapped[str | None] = mapped_column(Text)
    doi: Mapped[str | None] = mapped_column(String(120))
    funder: Mapped[str | None] = mapped_column(String(200))
    amount_minor: Mapped[int | None] = mapped_column(BigInteger)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="recorded")
    verified_by_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    attachment_ids: Mapped[list[uuid.UUID]] = mapped_column(
        ARRAY(UUID(as_uuid=True)), nullable=False, default=list
    )
    details: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)
