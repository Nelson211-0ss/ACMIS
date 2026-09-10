"""The library module.

Modelled on the shape every integrated library system settles on, because the
distinction it rests on is real and everything breaks without it:

* a **catalogue record** is the *work* — "Database System Concepts, 7th
  edition". It is what a reader searches for and what a reservation queues
  against.
* a **copy** is the physical thing on the shelf, with its own barcode and its
  own condition. It is what is issued, lost and paid for.

Fold them together and the library can no longer answer either of its two
questions: "do you have this book" (a record question) and "where is
accession 004512" (a copy question). Fold them together and a reservation
queue is meaningless, because a reader does not want *that* copy, they want
the book.

Circulation is deliberately conservative: a loan row is never edited to
record a return, it is closed by stamping `returned_on`. The history of who
held what is the only evidence in a dispute about a lost book, and an
overwritten loan row destroys it.
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
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import ARRAY, JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from acmis.core.models import TenantRecord


class CopyStatus(StrEnum):
    AVAILABLE = "available"
    ON_LOAN = "on_loan"
    #: Held at the desk for the reader whose reservation came up.
    ON_HOLD_SHELF = "on_hold_shelf"
    IN_TRANSIT = "in_transit"
    #: Reference or short-loan stock that never leaves the reading room.
    REFERENCE_ONLY = "reference_only"
    BINDING = "binding"
    MISSING = "missing"
    LOST = "lost"
    WITHDRAWN = "withdrawn"


class LoanStatus(StrEnum):
    OPEN = "open"
    RETURNED = "returned"
    OVERDUE = "overdue"
    #: Declared lost, charged for, and written off the shelf.
    LOST = "lost"
    #: Closed by a librarian without a return — usually because the copy was
    #: found on the shelf and the loan was a desk error.
    CANCELLED = "cancelled"


class Library(TenantRecord):
    """One library, or one branch of it.

    A branch rather than a campus, because a large campus has more than one
    (a main library and a law library) with different opening hours and
    different loan rules, and stock moves between them.
    """

    __tablename__ = "library"

    code: Mapped[str] = mapped_column(String(20), unique=True, nullable=False)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    campus_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("campus.id", ondelete="SET NULL"), index=True
    )
    location_note: Mapped[str | None] = mapped_column(String(300))
    email: Mapped[str | None] = mapped_column(String(200))
    phone: Mapped[str | None] = mapped_column(String(40))
    #: {"mon": ["08:00", "22:00"], ...}. Read by the desk and printed; not
    #: enforced, because a librarian working late must still be able to issue.
    opening_hours: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)


class LoanPolicy(TenantRecord):
    """The loan rules for one borrower category and one loan class.

    Data, not code. Every library has its own table of "undergraduates get 3
    books for 14 days, postgraduates 6 for 28, staff 10 for a semester, short
    loan is overnight" — and it changes by decision of a library committee,
    not by a release.
    """

    __tablename__ = "loan_policy"

    library_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("library.id", ondelete="CASCADE"), index=True
    )
    #: `undergraduate`, `postgraduate`, `staff`, `external`, `alumni`.
    borrower_category: Mapped[str] = mapped_column(String(30), nullable=False, index=True)
    #: `normal`, `short_loan`, `reserve`, `reference`, `audio_visual`,
    #: `thesis`, `journal`.
    loan_class: Mapped[str] = mapped_column(String(30), nullable=False, default="normal")
    loan_days: Mapped[int] = mapped_column(Integer, nullable=False, default=14)
    max_copies: Mapped[int] = mapped_column(Integer, nullable=False, default=3)
    max_renewals: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    #: Per day, in minor units. Zero means this class carries no fine, which
    #: some institutions prefer for undergraduates.
    fine_per_day_minor: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)
    #: A fine that can grow without limit is a fine nobody pays; the cap is
    #: what keeps the debt collectable.
    fine_cap_minor: Mapped[int | None] = mapped_column(BigInteger)
    #: A reader owing more than this cannot borrow again.
    borrowing_block_debt_minor: Mapped[int | None] = mapped_column(BigInteger)
    #: Days of grace before a fine starts to accrue.
    grace_days: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    reservations_allowed: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    #: Whether an item on loan to this reader may be recalled for a
    #: reservation. Recalling from staff is politically fraught, and most
    #: libraries turn it off for them.
    recallable: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)

    __table_args__ = (
        UniqueConstraint("library_id", "borrower_category", "loan_class", name="uq_loan_policy"),
        CheckConstraint("loan_days > 0", name="ck_loan_days_positive"),
    )


class CatalogueRecord(TenantRecord):
    """A work in the catalogue. What a reader searches for.

    Field names follow MARC 21 semantics loosely enough to be readable and
    closely enough to import a MARC record without losing anything that
    matters: `title`/`statement_of_responsibility` (245), `edition` (250),
    `publisher`/`published_year` (264), `classification` (082 Dewey or 050
    LC), `subjects` (650). Full MARC is kept in `marc_fields` for the fields
    nobody queries but a migration must not drop.
    """

    __tablename__ = "catalogue_record"

    #: `book`, `journal`, `thesis`, `report`, `map`, `audio`, `video`,
    #: `software`, `manuscript`, `e_book`, `e_journal`.
    material_kind: Mapped[str] = mapped_column(
        String(20), nullable=False, default="book", index=True
    )
    title: Mapped[str] = mapped_column(String(400), nullable=False)
    subtitle: Mapped[str | None] = mapped_column(String(400))
    statement_of_responsibility: Mapped[str | None] = mapped_column(String(400))
    #: Normalised for searching and for the "other works by" link. The full
    #: statement above is what gets printed.
    authors: Mapped[list[str]] = mapped_column(ARRAY(String(200)), nullable=False, default=list)
    edition: Mapped[str | None] = mapped_column(String(60))
    publisher: Mapped[str | None] = mapped_column(String(200))
    place_of_publication: Mapped[str | None] = mapped_column(String(120))
    published_year: Mapped[int | None] = mapped_column(Integer, index=True)
    #: ISBN-13 without hyphens where known. Not unique: two records may
    #: legitimately share one (a reissue), and a bad ISBN on an old record
    #: must not block cataloguing a new book.
    isbn: Mapped[str | None] = mapped_column(String(20), index=True)
    issn: Mapped[str | None] = mapped_column(String(12), index=True)
    doi: Mapped[str | None] = mapped_column(String(120))
    language: Mapped[str] = mapped_column(String(3), nullable=False, default="eng")
    #: Dewey or Library of Congress, as the institution has chosen. Drives
    #: shelf order, so it is indexed for a shelf-list report.
    classification: Mapped[str | None] = mapped_column(String(40), index=True)
    #: The Cutter number or author mark that completes the call number.
    author_mark: Mapped[str | None] = mapped_column(String(20))
    subjects: Mapped[list[str]] = mapped_column(ARRAY(String(120)), nullable=False, default=list)
    summary: Mapped[str | None] = mapped_column(Text)
    #: Courses this work is on the reading list for. The single most useful
    #: link in an academic library: it drives "reserve" status, and it tells
    #: acquisitions which titles a growing cohort will exhaust.
    course_ids: Mapped[list[uuid.UUID]] = mapped_column(
        ARRAY(UUID(as_uuid=True)), nullable=False, default=list
    )
    #: A digital object: an e-book file, or a link out to a licensed platform.
    online_url: Mapped[str | None] = mapped_column(String(600))
    attachment_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    cover_attachment_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    #: Everything MARC carries that nothing here queries.
    marc_fields: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)
    #: A thesis deposited here, linked back to the award it belongs to. An
    #: institutional repository is a library function, and the link is what
    #: makes a graduate's thesis findable from their record.
    student_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("student.id", ondelete="SET NULL"), index=True
    )
    is_searchable: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, index=True)
    copies: Mapped[list[CatalogueCopy]] = relationship(
        back_populates="record", cascade="all, delete-orphan"
    )

    __table_args__ = (Index("ix_catalogue_title", "title"),)


class CatalogueCopy(TenantRecord):
    """One physical (or one licensed concurrent) copy.

    `accession_number` is the library's own permanent number for the item and
    is what is written inside the front cover; `barcode` is what a scanner
    reads and may be replaced when a label peels off. Keeping both means a
    relabelled book is still the same accession, which is what a stock-take
    reconciles against.
    """

    __tablename__ = "catalogue_copy"

    record_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("catalogue_record.id", ondelete="CASCADE"), nullable=False, index=True
    )
    library_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("library.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    accession_number: Mapped[str] = mapped_column(String(40), unique=True, nullable=False)
    barcode: Mapped[str] = mapped_column(String(60), unique=True, nullable=False, index=True)
    #: The full call number as shelved, including the author mark. Held on the
    #: copy rather than the record because branches shelve differently.
    call_number: Mapped[str | None] = mapped_column(String(80), index=True)
    shelf_location: Mapped[str | None] = mapped_column(String(80))
    loan_class: Mapped[str] = mapped_column(String(30), nullable=False, default="normal")
    status: Mapped[str] = mapped_column(
        String(20), nullable=False, default=CopyStatus.AVAILABLE, index=True
    )
    #: `new`, `good`, `fair`, `poor`, `damaged`. Recorded on return, and it is
    #: what a damage charge has to be justified against.
    condition: Mapped[str] = mapped_column(String(20), nullable=False, default="good")
    acquired_on: Mapped[date | None] = mapped_column(Date)
    #: What it cost, which is what a replacement charge is based on. A lost
    #: book charged at a guessed price is a charge that gets waived.
    price_minor: Mapped[int | None] = mapped_column(BigInteger)
    supplier: Mapped[str | None] = mapped_column(String(200))
    #: Set when a stock-take last saw it. A copy nobody has seen for two
    #: stock-takes is missing whatever its status says.
    last_seen_on: Mapped[date | None] = mapped_column(Date)
    withdrawn_on: Mapped[date | None] = mapped_column(Date)
    withdrawal_reason: Mapped[str | None] = mapped_column(String(300))
    times_issued: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    record: Mapped[CatalogueRecord] = relationship(back_populates="copies")

    __table_args__ = (Index("ix_copy_shelf", "library_id", "status", "call_number"),)


class LibraryMember(TenantRecord):
    """A borrower.

    A membership rather than a direct use of `Student`/`Staff`, because a
    library lends to people the academic system does not know — visiting
    researchers, alumni, staff of a partner institution — and because
    borrowing rights end on a different date from studying (a finalist keeps
    their books through the vacation and is cleared at graduation).
    """

    __tablename__ = "library_member"

    membership_number: Mapped[str] = mapped_column(
        String(40), unique=True, nullable=False, index=True
    )
    student_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("student.id", ondelete="CASCADE"), index=True
    )
    staff_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("staff.id", ondelete="CASCADE"), index=True
    )
    #: Only for a member who is neither: an external reader.
    full_name: Mapped[str | None] = mapped_column(String(200))
    email: Mapped[str | None] = mapped_column(String(200))
    phone: Mapped[str | None] = mapped_column(String(40))
    borrower_category: Mapped[str] = mapped_column(String(30), nullable=False, index=True)
    home_library_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("library.id", ondelete="SET NULL")
    )
    joined_on: Mapped[date] = mapped_column(Date, nullable=False)
    expires_on: Mapped[date | None] = mapped_column(Date, index=True)
    #: `active`, `suspended`, `expired`, `closed`. A suspension is the
    #: library's own sanction and is separate from a fee block.
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="active", index=True)
    suspension_reason: Mapped[str | None] = mapped_column(String(300))
    #: Cached from the open fines, recomputed on write. The desk needs a
    #: yes/no in the time it takes to scan a card, and summing fines per
    #: issue is the query that makes a busy desk slow.
    outstanding_fines_minor: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)
    fines_recomputed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    items_on_loan: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    #: Set at graduation clearance. A member with no outstanding items and no
    #: fines can be cleared; the library's `clearance` row points at this.
    cleared_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    notes: Mapped[str | None] = mapped_column(Text)

    __table_args__ = (
        CheckConstraint(
            "student_id IS NOT NULL OR staff_id IS NOT NULL OR full_name IS NOT NULL",
            name="ck_member_identified",
        ),
        Index("ix_member_person", "student_id", "staff_id"),
    )


class Loan(TenantRecord):
    """One issue of one copy to one member.

    Never edited to record a return: `returned_on` is stamped and the row
    closes. The loan history is the evidence in every dispute about a missing
    book, and a library that overwrites it cannot say who had the thing.
    """

    __tablename__ = "library_loan"

    copy_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("catalogue_copy.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    member_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("library_member.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    library_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("library.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    issued_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    issued_by_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    due_on: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    #: Original due date, kept when a renewal or a recall moves `due_on`. A
    #: reader who was recalled early and fined needs to see both.
    original_due_on: Mapped[date] = mapped_column(Date, nullable=False)
    returned_on: Mapped[date | None] = mapped_column(Date, index=True)
    returned_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    received_by_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    renewals: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    #: Set when a reservation forces an early return.
    recalled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    status: Mapped[str] = mapped_column(
        String(20), nullable=False, default=LoanStatus.OPEN, index=True
    )
    #: The condition the copy came back in, and the charge if it is worse than
    #: it went out in.
    return_condition: Mapped[str | None] = mapped_column(String(20))
    #: Denormalised for the overdue report, which is run daily over every open
    #: loan and cannot afford to join to the policy each time.
    fine_per_day_minor: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)
    #: How many notices have gone out. Drives escalation, and stops a reader
    #: being emailed every night by a job that has no memory.
    notices_sent: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    last_notice_on: Mapped[date | None] = mapped_column(Date)
    note: Mapped[str | None] = mapped_column(Text)

    #: "A reader sees their own loans" is one policy rule rather than a join
    #: the engine cannot perform, so the borrower's identity is reachable.
    member: Mapped[LibraryMember] = relationship(viewonly=True, lazy="joined")
    copy: Mapped[CatalogueCopy] = relationship(viewonly=True, lazy="joined")

    __table_args__ = (
        Index("ix_loan_open", "status", "due_on"),
        Index("ix_loan_member_open", "member_id", "status"),
    )


class Reservation(TenantRecord):
    """A hold on a work, queued in order of request.

    Against the *record*, not a copy: a reader wants the book, and whichever
    copy comes back first satisfies them. `queue_position` is recomputed on
    every change rather than stored as a gap-filled sequence, because a queue
    with holes in it cannot be explained to the person standing at the desk.
    """

    __tablename__ = "library_reservation"

    record_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("catalogue_record.id", ondelete="CASCADE"), nullable=False, index=True
    )
    member_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("library_member.id", ondelete="CASCADE"), nullable=False, index=True
    )
    library_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("library.id", ondelete="SET NULL")
    )
    requested_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    queue_position: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    #: `waiting`, `ready`, `collected`, `expired`, `cancelled`.
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="waiting", index=True)
    #: The copy put aside once one came back, and how long it is held before
    #: the next reader in the queue gets it.
    allocated_copy_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("catalogue_copy.id", ondelete="SET NULL")
    )
    allocated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    collect_by: Mapped[date | None] = mapped_column(Date, index=True)
    collected_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    cancelled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    notified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    member: Mapped[LibraryMember] = relationship(viewonly=True, lazy="joined")
    record: Mapped[CatalogueRecord] = relationship(viewonly=True, lazy="joined")

    __table_args__ = (
        UniqueConstraint("record_id", "member_id", "status", name="uq_reservation_once"),
    )


class LibraryFine(TenantRecord):
    """A charge: an overdue, a loss, or damage.

    Raised here and settled through finance. The library owns *why* the money
    is owed; the ledger owns the money — which is what stops the library
    becoming a second, unreconciled cash system. `invoice_id` is the link, and
    a fine with a paid invoice is closed by the finance module, not here.
    """

    __tablename__ = "library_fine"

    member_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("library_member.id", ondelete="CASCADE"), nullable=False, index=True
    )
    loan_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("library_loan.id", ondelete="SET NULL"), index=True
    )
    copy_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("catalogue_copy.id", ondelete="SET NULL")
    )
    #: `overdue`, `loss`, `damage`, `processing`, `recall_overdue`.
    reason: Mapped[str] = mapped_column(String(30), nullable=False, index=True)
    amount_minor: Mapped[int] = mapped_column(BigInteger, nullable=False)
    #: For an overdue: the days charged and the rate, so the arithmetic can be
    #: shown. "You owe 14,000" is disputed; "14 days at 1,000" is paid.
    days_overdue: Mapped[int | None] = mapped_column(Integer)
    rate_per_day_minor: Mapped[int | None] = mapped_column(BigInteger)
    #: `raised`, `invoiced`, `paid`, `waived`, `written_off`.
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="raised", index=True)
    raised_on: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    raised_by_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    invoice_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), index=True)
    settled_on: Mapped[date | None] = mapped_column(Date)
    #: A waiver needs a reason and a second signature, exactly like a fee
    #: waiver: it is money the institution has decided not to collect.
    waived_by_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    waiver_reason: Mapped[str | None] = mapped_column(Text)
    note: Mapped[str | None] = mapped_column(Text)

    member: Mapped[LibraryMember] = relationship(viewonly=True, lazy="joined")


class AcquisitionRequest(TenantRecord):
    """A request to buy something, and its progress to the shelf.

    Starts with a lecturer wanting a title on their reading list and ends with
    an accession number. Worth modelling rather than doing by email because
    the useful question — "which requested titles are still not on the shelf
    two months into the semester" — is unanswerable from an inbox.
    """

    __tablename__ = "acquisition_request"

    reference: Mapped[str] = mapped_column(String(40), unique=True, nullable=False)
    title: Mapped[str] = mapped_column(String(400), nullable=False)
    authors: Mapped[str | None] = mapped_column(String(400))
    isbn: Mapped[str | None] = mapped_column(String(20))
    publisher: Mapped[str | None] = mapped_column(String(200))
    edition: Mapped[str | None] = mapped_column(String(60))
    copies_requested: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    #: Who wants it and for what. A request tied to a course and a cohort size
    #: is the one that gets funded.
    requested_by_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    requesting_unit_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("academic_unit.id", ondelete="SET NULL")
    )
    course_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("course.id", ondelete="SET NULL"), index=True
    )
    expected_cohort: Mapped[int | None] = mapped_column(Integer)
    justification: Mapped[str | None] = mapped_column(Text)
    #: `requested`, `approved`, `ordered`, `received`, `catalogued`,
    #: `declined`, `cancelled`.
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="requested", index=True)
    requested_on: Mapped[date] = mapped_column(Date, nullable=False)
    estimated_unit_price_minor: Mapped[int | None] = mapped_column(BigInteger)
    approved_budget_minor: Mapped[int | None] = mapped_column(BigInteger)
    approved_by_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    approved_on: Mapped[date | None] = mapped_column(Date)
    decline_reason: Mapped[str | None] = mapped_column(Text)
    supplier: Mapped[str | None] = mapped_column(String(200))
    order_reference: Mapped[str | None] = mapped_column(String(60))
    ordered_on: Mapped[date | None] = mapped_column(Date)
    received_on: Mapped[date | None] = mapped_column(Date)
    copies_received: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    #: Filled in once the received copies are catalogued, which closes the
    #: loop from "we should buy this" to "it is on the shelf".
    record_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("catalogue_record.id", ondelete="SET NULL")
    )


class EResourceSubscription(TenantRecord):
    """A licensed database or e-journal package.

    Tracked because the two facts that matter are administrative, not
    bibliographic: when the licence lapses, and how many concurrent users it
    allows. A subscription that quietly expires mid-semester is discovered by
    students, which is the worst way to discover it.
    """

    __tablename__ = "e_resource_subscription"

    name: Mapped[str] = mapped_column(String(200), nullable=False)
    provider: Mapped[str] = mapped_column(String(200), nullable=False)
    #: `database`, `e_journal_package`, `e_book_collection`, `streaming`,
    #: `dataset`, `software`.
    kind: Mapped[str] = mapped_column(String(30), nullable=False, default="database")
    access_url: Mapped[str | None] = mapped_column(String(600))
    #: `ip_range`, `shibboleth`, `openathens`, `referrer`, `username`, `proxy`.
    authentication_method: Mapped[str | None] = mapped_column(String(30))
    starts_on: Mapped[date] = mapped_column(Date, nullable=False)
    expires_on: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    concurrent_users: Mapped[int | None] = mapped_column(Integer)
    annual_cost_minor: Mapped[int | None] = mapped_column(BigInteger)
    #: Empty means the whole institution has access.
    unit_ids: Mapped[list[uuid.UUID]] = mapped_column(
        ARRAY(UUID(as_uuid=True)), nullable=False, default=list
    )
    #: COUNTER usage, as reported by the provider: searches, downloads,
    #: turnaways. Turnaways are the number that justifies more seats.
    usage_statistics: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, index=True)
    renewal_decision_due_on: Mapped[date | None] = mapped_column(Date)
    notes: Mapped[str | None] = mapped_column(Text)


class StockTake(TenantRecord):
    """A shelf audit: what the catalogue says against what is on the shelf.

    Run over a classification range rather than a whole library, because that
    is how it is physically done — one section at a time, over weeks. The
    output is a list of copies not seen, which become `missing` and then
    `lost`.
    """

    __tablename__ = "library_stock_take"

    reference: Mapped[str] = mapped_column(String(40), unique=True, nullable=False)
    library_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("library.id", ondelete="CASCADE"), nullable=False, index=True
    )
    #: The shelf range walked, as call numbers.
    classification_from: Mapped[str | None] = mapped_column(String(40))
    classification_to: Mapped[str | None] = mapped_column(String(40))
    started_on: Mapped[date] = mapped_column(Date, nullable=False)
    completed_on: Mapped[date | None] = mapped_column(Date)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="open", index=True)
    expected_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    seen_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    #: Copies expected in the range and not scanned. Written at completion so
    #: the report is reproducible after the copies' statuses change.
    missing_copy_ids: Mapped[list[uuid.UUID]] = mapped_column(
        ARRAY(UUID(as_uuid=True)), nullable=False, default=list
    )
    #: Scanned but shelved out of range or belonging to another branch.
    misplaced_copy_ids: Mapped[list[uuid.UUID]] = mapped_column(
        ARRAY(UUID(as_uuid=True)), nullable=False, default=list
    )
    conducted_by_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    note: Mapped[str | None] = mapped_column(Text)
