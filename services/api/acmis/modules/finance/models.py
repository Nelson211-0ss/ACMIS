"""Finance and administration: fees, invoices, receipts, sponsorship, ledger.

Double-entry, in a student information system, on purpose. The alternative —
a `balance` column on the student that every process increments — is what
produces the single most common failure in university finance systems: a
balance nobody can explain, because the arithmetic that produced it was
distributed across fifteen code paths and two of them ran twice.

Here every movement is a `LedgerEntry` pair. A student's balance is a SUM over
their entries and is never stored as the authority; `StudentAccount.balance_minor`
is a cache with a `recomputed_at`, and the reconciliation job asserts the two
agree. When they disagree, the entries win and the cache is rebuilt — which is
the property that makes the number defensible to an auditor.

All money is integer minor units. See `core.schemas.Money` for why.
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


class FeeStructure(TenantRecord):
    """The published fee schedule for a cohort.

    Versioned by cohort and academic year and *frozen once published*, because
    a student's fee for the year they entered is a contractual commitment in
    most jurisdictions and re-reading it from a mutable table means the
    institution cannot say what it charged.
    """

    __tablename__ = "fee_structure"

    code: Mapped[str] = mapped_column(String(40), nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    academic_year_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("academic_year.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    programme_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("programme.id", ondelete="CASCADE"), index=True
    )
    #: Applies to students who entered in this year, so a fee rise affects new
    #: intakes only — which is what "cohort-based fees" means and what most
    #: institutions promise their students.
    cohort_year_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("academic_year.id", ondelete="RESTRICT")
    )
    year_of_study: Mapped[int | None] = mapped_column(Integer)
    sponsorship: Mapped[str | None] = mapped_column(String(30), index=True)
    delivery_mode: Mapped[str | None] = mapped_column(String(20))
    #: International students pay a different schedule almost everywhere.
    nationality_group: Mapped[str | None] = mapped_column(String(30))
    campus_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("campus.id"))
    currency: Mapped[str] = mapped_column(String(3), nullable=False, default="UGX")

    status: Mapped[str] = mapped_column(String(20), nullable=False, default="draft", index=True)
    approved_by_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    #: Minimum percentage of the semester's fees required before course
    #: registration and before an examination card. The lever the institution
    #: actually uses; enforced by `finance.tuition-blocks`.
    registration_threshold_percent: Mapped[int] = mapped_column(Integer, nullable=False, default=60)
    exam_threshold_percent: Mapped[int] = mapped_column(Integer, nullable=False, default=100)

    items: Mapped[list[FeeItem]] = relationship(
        back_populates="structure", cascade="all, delete-orphan", lazy="selectin"
    )

    __table_args__ = (
        UniqueConstraint(
            "code",
            "academic_year_id",
            "programme_id",
            "sponsorship",
            name="uq_fee_structure_scope",
        ),
    )


class FeeItem(TenantRecord):
    """One chargeable line: tuition, functional fees, examination, guild."""

    __tablename__ = "fee_item"

    structure_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("fee_structure.id", ondelete="CASCADE"), nullable=False, index=True
    )
    code: Mapped[str] = mapped_column(String(40), nullable=False)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    #: `tuition`, `functional`, `examination`, `registration`, `guild`,
    #: `accommodation`, `library`, `identity_card`, `graduation`, `retake`.
    category: Mapped[str] = mapped_column(String(30), nullable=False, index=True)
    amount_minor: Mapped[int] = mapped_column(BigInteger, nullable=False)
    #: `per_semester`, `per_year`, `once`, `per_credit_unit`, `per_retake`.
    #: `per_credit_unit` is how retake and part-time fees are actually
    #: computed, so it cannot be a flat amount.
    basis: Mapped[str] = mapped_column(String(30), nullable=False, default="per_semester")
    is_mandatory: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    #: Levied only in a specific semester (graduation fee in the final one).
    semester_kind: Mapped[str | None] = mapped_column(String(20))
    #: Which sponsor pays this line. Government sponsorship typically covers
    #: tuition but not the guild fee, and getting this wrong produces the
    #: single most common student complaint in a public university.
    payable_by: Mapped[str] = mapped_column(String(20), nullable=False, default="student")
    gl_account_code: Mapped[str | None] = mapped_column(String(40))
    is_refundable: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    structure: Mapped[FeeStructure] = relationship(back_populates="items")

    __table_args__ = (
        UniqueConstraint("structure_id", "code", name="uq_fee_item_code"),
        CheckConstraint("amount_minor >= 0", name="fee_non_negative"),
    )


class StudentAccount(TenantRecord):
    """A student's running account. The balance here is a *cache*.

    `balance_minor` is negative when the institution owes the student (an
    overpayment awaiting refund), positive when the student owes. Signed rather
    than two columns, because a single signed number is the only version that
    survives the arithmetic without special cases.
    """

    __tablename__ = "student_account"

    student_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("student.id", ondelete="CASCADE"), nullable=False, unique=True, index=True
    )
    currency: Mapped[str] = mapped_column(String(3), nullable=False, default="UGX")
    balance_minor: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)
    total_invoiced_minor: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)
    total_paid_minor: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)
    total_waived_minor: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)
    #: When the cache was last rebuilt from the ledger. A stale cache is a
    #: reconciliation alert, not a rounding error.
    recomputed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    #: Set by the bursar to stop a student's account being blocked while a
    #: sponsor's payment is in transit — common and otherwise unfair.
    credit_hold_until: Mapped[date | None] = mapped_column(Date)
    notes: Mapped[str | None] = mapped_column(Text)


class Invoice(TenantRecord):
    """A demand for payment.

    Issued per semester per student, plus one-off invoices for application
    fees, retakes and transcripts. Immutable once `issued`: a correction is a
    credit note, never an edit, which is the only way the ledger and the
    student's copy of the invoice can agree afterwards.
    """

    __tablename__ = "invoice"

    number: Mapped[str] = mapped_column(String(40), unique=True, nullable=False, index=True)
    student_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("student.id", ondelete="CASCADE"), index=True
    )
    #: An application fee invoice belongs to an applicant, who is not yet a
    #: student. Exactly one of the two is set.
    applicant_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), index=True)
    semester_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("semester.id", ondelete="RESTRICT"), index=True
    )
    fee_structure_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("fee_structure.id", ondelete="RESTRICT")
    )
    #: `semester_fees`, `application`, `retake`, `transcript`, `graduation`,
    #: `accommodation`, `penalty`, `other`.
    kind: Mapped[str] = mapped_column(String(30), nullable=False, default="semester_fees")
    currency: Mapped[str] = mapped_column(String(3), nullable=False, default="UGX")

    subtotal_minor: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)
    discount_minor: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)
    waived_minor: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)
    total_minor: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)
    paid_minor: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)
    #: Cached; the ledger is authoritative.
    balance_minor: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)
    #: How much the sponsor is invoiced for, split out because a sponsored
    #: student's account must show only what *they* owe or the block rules
    #: punish them for their sponsor's lateness.
    sponsor_portion_minor: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)
    sponsorship_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), index=True)

    status: Mapped[str] = mapped_column(String(20), nullable=False, default="draft", index=True)
    issued_on: Mapped[date | None] = mapped_column(Date, index=True)
    due_on: Mapped[date | None] = mapped_column(Date, index=True)
    #: Instalment plan, where the institution allows one.
    instalments: Mapped[list[dict[str, Any]]] = mapped_column(JSONB, nullable=False, default=list)
    cancelled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    cancellation_reason: Mapped[str | None] = mapped_column(String(500))
    #: Set when a credit note supersedes this invoice.
    credit_note_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    #: Accounting period. A closed period rejects new postings —
    #: `finance.four-eyes/no-backdating`.
    period_code: Mapped[str | None] = mapped_column(String(20), index=True)

    lines: Mapped[list[InvoiceLine]] = relationship(
        back_populates="invoice", cascade="all, delete-orphan", lazy="selectin"
    )

    __table_args__ = (
        CheckConstraint(
            "(student_id IS NOT NULL) <> (applicant_id IS NOT NULL)",
            name="invoice_has_one_owner",
        ),
        Index("ix_invoice_student_status", "student_id", "status"),
        Index("ix_invoice_overdue", "due_on", "status"),
    )


class InvoiceLine(TenantRecord):
    __tablename__ = "invoice_line"

    invoice_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("invoice.id", ondelete="CASCADE"), nullable=False, index=True
    )
    fee_item_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("fee_item.id", ondelete="SET NULL")
    )
    #: Copied from the fee item at issue time. Denormalised deliberately: the
    #: fee structure may be superseded, and an invoice must still read exactly
    #: as it did when it was issued.
    code: Mapped[str] = mapped_column(String(40), nullable=False)
    description: Mapped[str] = mapped_column(String(300), nullable=False)
    category: Mapped[str] = mapped_column(String(30), nullable=False)
    quantity: Mapped[float] = mapped_column(Numeric(8, 2), nullable=False, default=1)
    unit_amount_minor: Mapped[int] = mapped_column(BigInteger, nullable=False)
    amount_minor: Mapped[int] = mapped_column(BigInteger, nullable=False)
    waived_minor: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)
    payable_by: Mapped[str] = mapped_column(String(20), nullable=False, default="student")
    gl_account_code: Mapped[str | None] = mapped_column(String(40))

    invoice: Mapped[Invoice] = relationship(back_populates="lines")


class PaymentStatus(StrEnum):
    #: The student pressed pay; the provider has not answered yet.
    PENDING = "pending"
    SETTLED = "settled"
    FAILED = "failed"
    #: Money arrived that we cannot attribute to a student. Its own state
    #: because an unidentified deposit is a real, common, and separately-worked
    #: problem in every university bursary, and hiding it as "failed" means it
    #: never gets resolved.
    UNMATCHED = "unmatched"
    REVERSED = "reversed"
    REFUNDED = "refunded"


class Payment(TenantRecord):
    """Money received.

    Not linked directly to an invoice. A student pays a round number at a bank
    and it settles against whatever they owe, oldest first — so allocation is
    its own table. Tying a payment to one invoice makes the very common case
    (one deposit covering last semester's arrears and part of this one)
    unrepresentable.
    """

    __tablename__ = "payment"

    reference: Mapped[str] = mapped_column(String(40), unique=True, nullable=False, index=True)
    student_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("student.id", ondelete="SET NULL"), index=True
    )
    applicant_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), index=True)
    #: `mobile_money`, `bank_transfer`, `bank_deposit`, `card`, `cash`,
    #: `cheque`, `sponsor_transfer`, `journal`.
    method: Mapped[str] = mapped_column(String(30), nullable=False, index=True)
    provider: Mapped[str | None] = mapped_column(String(40))
    #: The provider's own id. Unique where present — the idempotency key that
    #: stops a retried webhook crediting a student twice.
    provider_reference: Mapped[str | None] = mapped_column(String(120), index=True)
    #: What the payer typed. Often a mistyped student number, which is exactly
    #: why unmatched payments exist and are kept.
    payer_narrative: Mapped[str | None] = mapped_column(String(300))
    payer_name: Mapped[str | None] = mapped_column(String(200))
    payer_phone: Mapped[str | None] = mapped_column(String(40))

    currency: Mapped[str] = mapped_column(String(3), nullable=False, default="UGX")
    amount_minor: Mapped[int] = mapped_column(BigInteger, nullable=False)
    #: Provider charge, where the institution absorbs it.
    fee_minor: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)
    allocated_minor: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)

    status: Mapped[str] = mapped_column(
        String(20), nullable=False, default=PaymentStatus.PENDING, index=True
    )
    #: When the money moved, per the payer's record — not when we heard about
    #: it. A deposit made on the deadline and reported the next morning was
    #: made on time, and this is the column that proves it.
    value_date: Mapped[date | None] = mapped_column(Date, index=True)
    settled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    received_by_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    #: Reversal needs a second person — `finance.four-eyes`.
    raised_by_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    reversed_by_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    reversed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    reversal_reason: Mapped[str | None] = mapped_column(String(500))
    receipt_number: Mapped[str | None] = mapped_column(String(40), unique=True)
    bank_reconciliation_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), index=True)
    period_code: Mapped[str | None] = mapped_column(String(20), index=True)
    provider_payload: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)

    allocations: Mapped[list[PaymentAllocation]] = relationship(
        back_populates="payment", cascade="all, delete-orphan", lazy="selectin"
    )

    __table_args__ = (
        UniqueConstraint("provider", "provider_reference", name="uq_payment_provider_ref"),
        CheckConstraint("amount_minor > 0", name="payment_positive"),
        Index(
            "ix_payment_unmatched", "status", "value_date", postgresql_where=status == "unmatched"
        ),
    )


class PaymentAllocation(TenantRecord):
    """How much of a payment settled which invoice."""

    __tablename__ = "payment_allocation"

    payment_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("payment.id", ondelete="CASCADE"), nullable=False, index=True
    )
    invoice_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("invoice.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    amount_minor: Mapped[int] = mapped_column(BigInteger, nullable=False)
    allocated_by_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    #: True when the allocation was chosen by the oldest-debt-first rule rather
    #: than by a cashier, so a disputed allocation can be identified.
    is_automatic: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    reversed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    payment: Mapped[Payment] = relationship(back_populates="allocations")

    __table_args__ = (CheckConstraint("amount_minor > 0", name="allocation_positive"),)


class LedgerEntry(TenantRecord):
    """One side of one double-entry movement. Append-only.

    Never updated and never deleted. A mistake is corrected by a contra entry,
    which is why `reverses_entry_id` exists and `deleted_at` is never set on
    this table. `transaction_id` groups the sides of a movement; the service
    layer asserts each group sums to zero before commit, which is the check
    that catches a half-written transaction.
    """

    __tablename__ = "ledger_entry"

    transaction_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), nullable=False, index=True
    )
    sequence: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    posted_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)
    value_date: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    period_code: Mapped[str] = mapped_column(String(20), nullable=False, index=True)

    student_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("student.id", ondelete="RESTRICT"), index=True
    )
    account_code: Mapped[str] = mapped_column(String(40), nullable=False, index=True)
    #: Positive debit, negative credit — one signed column rather than two, so
    #: "does this transaction balance" is `SUM(amount_minor) = 0` and not a
    #: comparison between two nullable columns.
    amount_minor: Mapped[int] = mapped_column(BigInteger, nullable=False)
    currency: Mapped[str] = mapped_column(String(3), nullable=False, default="UGX")
    narrative: Mapped[str] = mapped_column(String(300), nullable=False)

    #: What caused this: an invoice, a payment, a waiver, a refund.
    source_type: Mapped[str] = mapped_column(String(30), nullable=False, index=True)
    source_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), index=True)
    reverses_entry_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    posted_by_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))

    __table_args__ = (
        UniqueConstraint("transaction_id", "sequence", name="uq_ledger_transaction_leg"),
        Index("ix_ledger_student_time", "student_id", "posted_at"),
        Index("ix_ledger_account_period", "account_code", "period_code"),
        CheckConstraint("amount_minor <> 0", name="ledger_entry_non_zero"),
    )


class Sponsorship(TenantRecord):
    """A third party paying some or all of a student's fees.

    Government scholarship, district bursary, employer, embassy, NGO. The
    coverage rules are data because every sponsor's are different — "tuition
    only", "80% capped at 2,000,000 per semester", "everything except the
    guild fee" — and encoding them in code means a release per sponsor.
    """

    __tablename__ = "sponsorship"

    reference: Mapped[str] = mapped_column(String(40), unique=True, nullable=False)
    student_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("student.id", ondelete="CASCADE"), nullable=False, index=True
    )
    sponsor_name: Mapped[str] = mapped_column(String(200), nullable=False, index=True)
    #: `government`, `district_quota`, `employer`, `embassy`, `ngo`, `family`.
    sponsor_kind: Mapped[str] = mapped_column(String(30), nullable=False, index=True)
    contact_name: Mapped[str | None] = mapped_column(String(200))
    contact_email: Mapped[str | None] = mapped_column(String(200))
    contact_phone: Mapped[str | None] = mapped_column(String(40))
    award_letter_attachment_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))

    #: e.g. {"categories": ["tuition"], "percent": 100, "cap_minor": 2000000}
    coverage: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)
    #: Total the sponsor has committed across the whole award, where capped.
    total_committed_minor: Mapped[int | None] = mapped_column(BigInteger)
    total_disbursed_minor: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)

    starts_on: Mapped[date] = mapped_column(Date, nullable=False)
    ends_on: Mapped[date | None] = mapped_column(Date)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="active", index=True)
    #: Sponsors withdraw when a student's performance drops. Recorded because
    #: the student then owes the balance and must be told why.
    withdrawn_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    withdrawal_reason: Mapped[str | None] = mapped_column(Text)
    #: Minimum CGPA the sponsor requires. Checked by the progression job, which
    #: is how a sponsor is told before they pay for a failing semester.
    minimum_cgpa: Mapped[float | None] = mapped_column(Numeric(4, 2))
    approved_by_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class Waiver(TenantRecord):
    """Fees forgiven. Two-person authorisation, always.

    The most abusable operation in the module, so it carries a raiser, a
    releaser who must be someone else, a ceiling per releaser, a mandatory
    reason and a documentary reference. `finance.four-eyes` enforces the first
    three; the last two are required by the schema.
    """

    __tablename__ = "waiver"

    reference: Mapped[str] = mapped_column(String(40), unique=True, nullable=False)
    student_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("student.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    invoice_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("invoice.id", ondelete="RESTRICT"), index=True
    )
    #: `hardship`, `bereavement`, `staff_dependant`, `scholarship`,
    #: `institutional_error`, `disability_support`, `sports_bursary`.
    category: Mapped[str] = mapped_column(String(40), nullable=False, index=True)
    amount_minor: Mapped[int] = mapped_column(BigInteger, nullable=False)
    currency: Mapped[str] = mapped_column(String(3), nullable=False, default="UGX")
    reason: Mapped[str] = mapped_column(Text, nullable=False)
    evidence_reference: Mapped[str | None] = mapped_column(String(120))
    evidence_attachment_ids: Mapped[list[uuid.UUID]] = mapped_column(
        ARRAY(UUID(as_uuid=True)), nullable=False, default=list
    )
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="raised", index=True)
    raised_by_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    raised_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    released_by_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    released_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    rejected_reason: Mapped[str | None] = mapped_column(Text)
    period_code: Mapped[str | None] = mapped_column(String(20))

    __table_args__ = (CheckConstraint("amount_minor > 0", name="waiver_positive"),)


class Refund(TenantRecord):
    """Money going back out. Same two-person rule as a waiver."""

    __tablename__ = "refund"

    reference: Mapped[str] = mapped_column(String(40), unique=True, nullable=False)
    student_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("student.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    payment_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("payment.id", ondelete="RESTRICT")
    )
    amount_minor: Mapped[int] = mapped_column(BigInteger, nullable=False)
    currency: Mapped[str] = mapped_column(String(3), nullable=False, default="UGX")
    reason: Mapped[str] = mapped_column(Text, nullable=False)
    method: Mapped[str] = mapped_column(String(30), nullable=False, default="bank_transfer")
    #: Snapshot of the destination at approval time. Kept because a student's
    #: bank details change and a refund must be traceable to the account it
    #: was actually sent to.
    destination: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="raised", index=True)
    raised_by_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    raised_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    released_by_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    released_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    paid_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    period_code: Mapped[str | None] = mapped_column(String(20))


class AccountingPeriod(TenantRecord):
    """An open or closed month. Closing is what stops silent backdating."""

    __tablename__ = "accounting_period"

    code: Mapped[str] = mapped_column(String(20), unique=True, nullable=False, index=True)
    starts_on: Mapped[date] = mapped_column(Date, nullable=False)
    ends_on: Mapped[date] = mapped_column(Date, nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="open", index=True)
    closed_by_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    closed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    reopened_by_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    reopen_reason: Mapped[str | None] = mapped_column(Text)


class BankReconciliation(TenantRecord):
    """A bank statement matched against recorded payments.

    Where unmatched deposits are worked. `unmatched_count` reaching zero is
    the definition of a reconciled day, and it is the number a bursar is
    actually measured on.
    """

    __tablename__ = "bank_reconciliation"

    reference: Mapped[str] = mapped_column(String(40), unique=True, nullable=False)
    bank_account: Mapped[str] = mapped_column(String(120), nullable=False)
    statement_date: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    opening_balance_minor: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)
    closing_balance_minor: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)
    statement_total_minor: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)
    matched_total_minor: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)
    matched_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    unmatched_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="open", index=True)
    statement_attachment_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    reconciled_by_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    reconciled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    #: Raiser and releaser again: reconciliation sign-off is a control.
    approved_by_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))


class LatePaymentRule(TenantRecord):
    """The institution's terms for paying late. Data, not code.

    Every university has a version of "10% surcharge after the second week of
    the semester, capped at 200,000, waivable by the bursar" — and it changes
    by decision of a finance committee rather than by a release. Held per
    academic year and optionally per programme or sponsorship, because
    government-sponsored students are usually exempt and international
    students often have different terms.

    Two kinds of consequence, and they are separate on purpose: a *charge*
    (money added to the invoice) and a *block* (registration or examination
    refused). An institution that only charges collects less; one that only
    blocks collects nothing and loses the student.
    """

    __tablename__ = "late_payment_rule"

    code: Mapped[str] = mapped_column(String(40), nullable=False)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    academic_year_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("academic_year.id", ondelete="CASCADE"), nullable=False, index=True
    )
    programme_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("programme.id", ondelete="CASCADE"), index=True
    )
    sponsorship: Mapped[str | None] = mapped_column(String(30), index=True)
    #: What the surcharge applies to: `semester_fees`, `tuition`, `all`.
    applies_to_invoice_kind: Mapped[str] = mapped_column(
        String(30), nullable=False, default="semester_fees"
    )
    #: Days after `Invoice.due_on` before anything happens. A grace period is
    #: not generosity: bank transfers take days to appear, and charging a
    #: student for the bank's float is a charge that gets waived anyway.
    grace_days: Mapped[int] = mapped_column(Integer, nullable=False, default=7)
    #: `percentage` of the outstanding balance, or a `flat` amount. Percentage
    #: is fairer and flat is simpler; institutions use both.
    charge_basis: Mapped[str] = mapped_column(String(20), nullable=False, default="percentage")
    charge_percent: Mapped[float | None] = mapped_column(Numeric(5, 2))
    charge_flat_minor: Mapped[int | None] = mapped_column(BigInteger)
    #: `once`, `weekly`, `monthly`, `per_semester`. A recurring surcharge on a
    #: balance a student cannot pay compounds into a debt nobody collects, so
    #: `once` is the default and the cap below is not optional in practice.
    recurrence: Mapped[str] = mapped_column(String(20), nullable=False, default="once")
    max_charges: Mapped[int | None] = mapped_column(Integer)
    charge_cap_minor: Mapped[int | None] = mapped_column(BigInteger)
    #: Consequences, in escalation order. Each is a number of days past due.
    blocks_registration_after_days: Mapped[int | None] = mapped_column(Integer)
    blocks_exam_card_after_days: Mapped[int | None] = mapped_column(Integer)
    blocks_results_after_days: Mapped[int | None] = mapped_column(Integer)
    #: A hardship case is why `finance:override_block` exists; this says
    #: whether *this* rule may be overridden at all, because some are
    #: statutory.
    is_waivable: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    #: Which fee item the surcharge is posted as, so it lands in the right
    #: revenue account instead of being mixed into tuition.
    charge_fee_item_code: Mapped[str | None] = mapped_column(String(40))
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="draft", index=True)
    approved_by_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    effective_from: Mapped[date | None] = mapped_column(Date)
    effective_to: Mapped[date | None] = mapped_column(Date)

    __table_args__ = (
        UniqueConstraint("academic_year_id", "code", name="uq_late_payment_rule_code"),
        CheckConstraint("charge_basis IN ('percentage', 'flat')", name="ck_late_charge_basis"),
    )


class PenaltyCharge(TenantRecord):
    """A late-payment surcharge that was actually applied.

    A row per application rather than a running field on the invoice, because
    the questions asked of it are "when was this charged, under which rule,
    and by whose authority" — and because a surcharge is the most commonly
    disputed line on a student's statement. Reversing one leaves the original
    row and adds a reversal, exactly as the ledger does.
    """

    __tablename__ = "penalty_charge"

    student_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("student.id", ondelete="CASCADE"), nullable=False, index=True
    )
    invoice_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("invoice.id", ondelete="CASCADE"), nullable=False, index=True
    )
    rule_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("late_payment_rule.id", ondelete="SET NULL")
    )
    #: The invoice line this charge became. The money exists once, on the
    #: invoice; this row is the explanation.
    invoice_line_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    charged_on: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    #: The arithmetic, so it can be shown rather than asserted.
    days_overdue: Mapped[int] = mapped_column(Integer, nullable=False)
    balance_at_charge_minor: Mapped[int] = mapped_column(BigInteger, nullable=False)
    percent_applied: Mapped[float | None] = mapped_column(Numeric(5, 2))
    amount_minor: Mapped[int] = mapped_column(BigInteger, nullable=False)
    #: Which application this is, for a recurring rule.
    sequence: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    #: `applied`, `reversed`, `waived`.
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="applied", index=True)
    #: Applied by the nightly job, or by a person. Both happen, and which one
    #: matters when a student says they were charged in error.
    applied_by_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    applied_automatically: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    reversed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    reversed_by_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    reversal_reason: Mapped[str | None] = mapped_column(Text)

    __table_args__ = (
        UniqueConstraint("invoice_id", "rule_id", "sequence", name="uq_penalty_sequence"),
    )


class PaymentPlan(TenantRecord):
    """An agreement to pay in instalments.

    The institution's alternative to blocking a student who cannot pay in one
    go, and the reason to model it is that an agreed plan changes what
    "overdue" means: a student paying to schedule is *not* late, and must not
    be surcharged or blocked by a job that only reads `Invoice.due_on`.

    So the plan is the authority, and `finance.service` checks it before
    applying any penalty. A plan the student has stopped paying loses that
    protection — which is what `status = 'defaulted'` is for.
    """

    __tablename__ = "payment_plan"

    reference: Mapped[str] = mapped_column(String(40), unique=True, nullable=False)
    student_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("student.id", ondelete="CASCADE"), nullable=False, index=True
    )
    invoice_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("invoice.id", ondelete="CASCADE"), index=True
    )
    semester_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("semester.id", ondelete="SET NULL"), index=True
    )
    total_minor: Mapped[int] = mapped_column(BigInteger, nullable=False)
    #: Some institutions require money on the table before agreeing a plan.
    deposit_minor: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)
    instalment_count: Mapped[int] = mapped_column(Integer, nullable=False, default=2)
    #: `requested`, `active`, `completed`, `defaulted`, `cancelled`,
    #: `declined`.
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="requested", index=True)
    reason: Mapped[str | None] = mapped_column(Text)
    requested_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    #: Agreeing a plan is forgoing the institution's right to block, so it is
    #: an approval, not a self-service action.
    approved_by_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    decline_reason: Mapped[str | None] = mapped_column(Text)
    #: How many instalments may be missed before the plan defaults. Zero
    #: means the first miss ends it.
    missed_allowance: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    missed_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    defaulted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    #: Signed agreement, or the sponsor's letter behind it.
    agreement_attachment_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))

    instalments: Mapped[list[PaymentPlanInstalment]] = relationship(
        back_populates="plan", cascade="all, delete-orphan", lazy="selectin"
    )

    __table_args__ = (CheckConstraint("instalment_count >= 1", name="ck_plan_instalments"),)


class PaymentPlanInstalment(TenantRecord):
    """One scheduled payment on a plan.

    Settled by allocating a payment to it rather than by editing an amount:
    the money is in the ledger, and this row records what was expected and
    when, so "did they keep to the plan" is answerable without reconstructing
    it from receipts.
    """

    __tablename__ = "payment_plan_instalment"

    plan_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("payment_plan.id", ondelete="CASCADE"), nullable=False, index=True
    )
    sequence: Mapped[int] = mapped_column(Integer, nullable=False)
    due_on: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    amount_minor: Mapped[int] = mapped_column(BigInteger, nullable=False)
    paid_minor: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)
    #: `pending`, `paid`, `part_paid`, `missed`, `waived`.
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="pending", index=True)
    settled_on: Mapped[date | None] = mapped_column(Date)
    #: The payments that satisfied it. A list because a student pays an
    #: instalment in two goes more often than not.
    payment_ids: Mapped[list[uuid.UUID]] = mapped_column(
        ARRAY(UUID(as_uuid=True)), nullable=False, default=list
    )

    plan: Mapped[PaymentPlan] = relationship(back_populates="instalments")

    __table_args__ = (UniqueConstraint("plan_id", "sequence", name="uq_instalment_sequence"),)


class DunningNotice(TenantRecord):
    """A reminder that was sent about an unpaid balance.

    Recorded, not merely sent. Two reasons, and both are practical: a student
    who says "nobody told me" is answered from here, and an escalation ladder
    with no memory emails the same person every night — which trains them to
    filter it, and then the one notice that mattered is unread.
    """

    __tablename__ = "dunning_notice"

    student_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("student.id", ondelete="CASCADE"), nullable=False, index=True
    )
    invoice_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("invoice.id", ondelete="CASCADE"), index=True
    )
    #: 1 = a reminder, 2 = a warning, 3 = notice of blocking, 4 = referral.
    #: Escalation is a level rather than a free-text subject so that "how many
    #: students are at level 3" is answerable.
    level: Mapped[int] = mapped_column(Integer, nullable=False, default=1, index=True)
    #: `email`, `sms`, `portal`, `letter`, `phone`.
    channel: Mapped[str] = mapped_column(String(20), nullable=False, default="email")
    sent_on: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    sent_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    balance_minor: Mapped[int] = mapped_column(BigInteger, nullable=False)
    days_overdue: Mapped[int] = mapped_column(Integer, nullable=False)
    #: What the student was told would happen next, so the threat and the
    #: eventual action can be compared.
    consequence_stated: Mapped[str | None] = mapped_column(String(300))
    #: Also sent to the sponsor or the guarantor, where there is one. A
    #: government-sponsored student's arrears are the sponsor's problem, and
    #: chasing the student for them is both futile and unkind.
    sent_to_sponsor: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    recipient: Mapped[str | None] = mapped_column(String(200))
    delivered: Mapped[bool | None] = mapped_column(Boolean)
    delivery_note: Mapped[str | None] = mapped_column(String(300))
    #: Set when the student responds — pays, agrees a plan, or disputes.
    responded_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    response_note: Mapped[str | None] = mapped_column(Text)
    sent_by_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))

    __table_args__ = (Index("ix_dunning_ladder", "student_id", "level", "sent_on"),)
