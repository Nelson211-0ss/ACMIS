"""The library: catalogue, circulation, fines and acquisitions."""

from __future__ import annotations

import uuid
from datetime import date, datetime, timedelta
from typing import Annotated, Any

from fastapi import APIRouter, Query, status
from pydantic import Field
from sqlalchemy import func, or_, select

from acmis.core.abac import authorize
from acmis.core.audit import AuditCategory, emit
from acmis.core.deps import AnyContext, PageQuery, StaffContext, StudentContext
from acmis.core.errors import NotFound, RuleViolation
from acmis.core.pagination import keyset_page
from acmis.core.schemas import Page, Reason, Schema
from acmis.modules.library import service
from acmis.modules.library.models import (
    AcquisitionRequest,
    CatalogueCopy,
    CatalogueRecord,
    CopyStatus,
    EResourceSubscription,
    Library,
    LibraryFine,
    LibraryMember,
    Loan,
    LoanStatus,
    Reservation,
)
from acmis.routers._common import get_or_404

router = APIRouter(prefix="/library", tags=["library"])


# ---------------------------------------------------------------------------
# Catalogue
# ---------------------------------------------------------------------------


class RecordOut(Schema):
    id: uuid.UUID
    material_kind: str
    title: str
    subtitle: str | None
    statement_of_responsibility: str | None
    authors: list[str]
    edition: str | None
    publisher: str | None
    published_year: int | None
    isbn: str | None
    issn: str | None
    classification: str | None
    subjects: list[str]
    summary: str | None
    online_url: str | None
    course_ids: list[uuid.UUID]


class RecordIn(Schema):
    material_kind: Annotated[str, Field(max_length=20)] = "book"
    title: Annotated[str, Field(max_length=400)]
    subtitle: Annotated[str | None, Field(max_length=400)] = None
    statement_of_responsibility: Annotated[str | None, Field(max_length=400)] = None
    authors: list[str] = Field(default_factory=list)
    edition: Annotated[str | None, Field(max_length=60)] = None
    publisher: Annotated[str | None, Field(max_length=200)] = None
    place_of_publication: Annotated[str | None, Field(max_length=120)] = None
    published_year: Annotated[int | None, Field(ge=1400, le=2200)] = None
    isbn: Annotated[str | None, Field(max_length=20)] = None
    issn: Annotated[str | None, Field(max_length=12)] = None
    language: Annotated[str, Field(max_length=3)] = "eng"
    classification: Annotated[str | None, Field(max_length=40)] = None
    author_mark: Annotated[str | None, Field(max_length=20)] = None
    subjects: list[str] = Field(default_factory=list)
    summary: str | None = None
    online_url: Annotated[str | None, Field(max_length=600)] = None
    course_ids: list[uuid.UUID] = Field(default_factory=list)


class AvailabilityOut(Schema):
    record_id: uuid.UUID
    copies: int
    available: int
    on_loan: int
    reference_only: int
    reservations: int
    earliest_due: date | None


@router.get("/records", response_model=Page[RecordOut])
def search_catalogue(
    ctx: AnyContext,
    page: PageQuery,
    q: Annotated[str | None, Query(max_length=200)] = None,
    material_kind: str | None = None,
    course_id: uuid.UUID | None = None,
    classification: Annotated[str | None, Query(max_length=40)] = None,
) -> Page[RecordOut]:
    """Search the catalogue.

    Readable by anyone signed in: what the library holds is information the
    institution wants known. Who borrowed it is not — see the circulation
    endpoints, which are scoped far more tightly.
    """
    authorize(
        engine=ctx.engine,
        action="catalogue_record:search",
        resource_type="catalogue_record",
        resource={"id": None, "is_searchable": True, "material_kind": material_kind},
    )
    stmt = select(CatalogueRecord).where(
        CatalogueRecord.deleted_at.is_(None), CatalogueRecord.is_searchable.is_(True)
    )
    if material_kind:
        stmt = stmt.where(CatalogueRecord.material_kind == material_kind)
    if classification:
        stmt = stmt.where(CatalogueRecord.classification.like(f"{classification}%"))
    if course_id:
        stmt = stmt.where(CatalogueRecord.course_ids.overlap([course_id]))
    if q:
        term = f"%{q.lower()}%"
        # Title, author and ISBN in one box. A reader searching a library
        # catalogue does not know which field their half-remembered phrase is
        # in, and making them choose is how a search returns nothing.
        stmt = stmt.where(
            or_(
                func.lower(CatalogueRecord.title).like(term),
                func.lower(CatalogueRecord.subtitle).like(term),
                func.lower(CatalogueRecord.statement_of_responsibility).like(term),
                func.lower(func.array_to_string(CatalogueRecord.authors, " ")).like(term),
                CatalogueRecord.isbn == q.replace("-", ""),
            )
        )
    found = keyset_page(
        ctx.db, stmt, page=page, key=CatalogueRecord.title, ident=CatalogueRecord.id
    )
    return Page.of(
        [RecordOut.model_validate(row) for row in found.rows],
        limit=page.limit,
        next_cursor=found.next_cursor,
        total=found.total,
    )


@router.post("/records", response_model=RecordOut, status_code=status.HTTP_201_CREATED)
def create_record(payload: RecordIn, ctx: StaffContext) -> RecordOut:
    authorize(
        engine=ctx.engine,
        action="catalogue_record:create",
        resource_type="catalogue_record",
        resource={"id": None, "is_searchable": True, "material_kind": payload.material_kind},
        category=AuditCategory.LIBRARY,
    )
    record = CatalogueRecord(**payload.model_dump(), created_by_id=ctx.principal.id)
    ctx.db.add(record)
    ctx.db.flush()
    emit(
        "catalogue_record:create",
        AuditCategory.LIBRARY,
        resource_type="catalogue_record",
        resource_id=record.id,
        resource_label=record.title,
        summary=f"Catalogued: {record.title}",
    )
    return RecordOut.model_validate(record)


@router.get("/records/{record_id}", response_model=RecordOut)
def get_record(record_id: uuid.UUID, ctx: AnyContext) -> RecordOut:
    """One catalogue record.

    Its own endpoint rather than something the caller filters out of a search:
    a record is reached from a search *or* from a copy's barcode at the desk,
    and the second has no search to filter.
    """
    record = get_or_404(ctx, CatalogueRecord, record_id)
    authorize(
        engine=ctx.engine,
        action="catalogue_record:read",
        resource_type="catalogue_record",
        resource=record,
    )
    return RecordOut.model_validate(record)


@router.get("/records/{record_id}/availability", response_model=AvailabilityOut)
def availability(record_id: uuid.UUID, ctx: AnyContext) -> AvailabilityOut:
    """Can I get this book, and if not, when?

    The two questions a reader actually has. `earliest_due` is what turns "all
    copies out" into something they can act on.
    """
    record = get_or_404(ctx, CatalogueRecord, record_id)
    authorize(
        engine=ctx.engine,
        action="catalogue_record:read",
        resource_type="catalogue_record",
        resource=record,
    )
    rows = ctx.db.execute(
        select(CatalogueCopy.status, func.count())
        .where(CatalogueCopy.record_id == record.id, CatalogueCopy.deleted_at.is_(None))
        .group_by(CatalogueCopy.status)
    ).all()
    counts = {str(state): int(total) for state, total in rows}
    earliest = ctx.db.execute(
        select(func.min(Loan.due_on))
        .join(CatalogueCopy, CatalogueCopy.id == Loan.copy_id)
        .where(
            CatalogueCopy.record_id == record.id,
            Loan.status.in_((LoanStatus.OPEN, LoanStatus.OVERDUE)),
            Loan.deleted_at.is_(None),
        )
    ).scalar_one_or_none()
    reservations = int(
        ctx.db.execute(
            select(func.count()).where(
                Reservation.record_id == record.id,
                Reservation.status == "waiting",
                Reservation.deleted_at.is_(None),
            )
        ).scalar_one()
    )
    return AvailabilityOut(
        record_id=record.id,
        copies=sum(counts.values()),
        available=counts.get(str(CopyStatus.AVAILABLE), 0),
        on_loan=counts.get(str(CopyStatus.ON_LOAN), 0),
        reference_only=counts.get(str(CopyStatus.REFERENCE_ONLY), 0),
        reservations=reservations,
        earliest_due=earliest,
    )


class CopyOut(Schema):
    id: uuid.UUID
    record_id: uuid.UUID
    library_id: uuid.UUID
    accession_number: str
    barcode: str
    call_number: str | None
    shelf_location: str | None
    loan_class: str
    status: str
    condition: str
    times_issued: int


class CopyIn(Schema):
    library_id: uuid.UUID
    accession_number: Annotated[str, Field(max_length=40)]
    barcode: Annotated[str, Field(max_length=60)]
    call_number: Annotated[str | None, Field(max_length=80)] = None
    shelf_location: Annotated[str | None, Field(max_length=80)] = None
    loan_class: Annotated[str, Field(max_length=30)] = "normal"
    condition: Annotated[str, Field(max_length=20)] = "good"
    acquired_on: date | None = None
    price_minor: Annotated[int | None, Field(ge=0)] = None
    supplier: Annotated[str | None, Field(max_length=200)] = None


@router.get("/records/{record_id}/copies", response_model=list[CopyOut])
def list_copies(record_id: uuid.UUID, ctx: AnyContext) -> list[CopyOut]:
    record = get_or_404(ctx, CatalogueRecord, record_id)
    authorize(
        engine=ctx.engine,
        action="catalogue_copy:list",
        resource_type="catalogue_record",
        resource=record,
    )
    rows = (
        ctx.db.execute(
            select(CatalogueCopy)
            .where(CatalogueCopy.record_id == record.id, CatalogueCopy.deleted_at.is_(None))
            .order_by(CatalogueCopy.accession_number)
        )
        .scalars()
        .all()
    )
    return [CopyOut.model_validate(row) for row in rows]


@router.post(
    "/records/{record_id}/copies", response_model=CopyOut, status_code=status.HTTP_201_CREATED
)
def add_copy(record_id: uuid.UUID, payload: CopyIn, ctx: StaffContext) -> CopyOut:
    record = get_or_404(ctx, CatalogueRecord, record_id)
    authorize(
        engine=ctx.engine,
        action="catalogue_copy:create",
        resource_type="catalogue_copy",
        resource={
            "id": None,
            "record_id": str(record.id),
            "library_id": str(payload.library_id),
            "status": CopyStatus.AVAILABLE,
            "loan_class": payload.loan_class,
        },
        category=AuditCategory.LIBRARY,
    )
    copy = CatalogueCopy(
        record_id=record.id,
        status=(
            CopyStatus.REFERENCE_ONLY if payload.loan_class == "reference" else CopyStatus.AVAILABLE
        ),
        created_by_id=ctx.principal.id,
        **payload.model_dump(),
    )
    ctx.db.add(copy)
    ctx.db.flush()
    emit(
        "catalogue_copy:create",
        AuditCategory.LIBRARY,
        resource_type="catalogue_copy",
        resource_id=copy.id,
        resource_label=copy.accession_number,
        summary=f"Accessioned {copy.accession_number} of {record.title}",
    )
    return CopyOut.model_validate(copy)


# ---------------------------------------------------------------------------
# Membership
# ---------------------------------------------------------------------------


class MemberOut(Schema):
    id: uuid.UUID
    membership_number: str
    student_id: uuid.UUID | None
    staff_id: uuid.UUID | None
    full_name: str | None
    borrower_category: str
    status: str
    expires_on: date | None
    outstanding_fines_minor: int
    items_on_loan: int


class MemberIn(Schema):
    student_id: uuid.UUID | None = None
    staff_id: uuid.UUID | None = None
    full_name: Annotated[str | None, Field(max_length=200)] = None
    email: Annotated[str | None, Field(max_length=200)] = None
    borrower_category: Annotated[str, Field(max_length=30)] = "undergraduate"
    home_library_id: uuid.UUID | None = None
    expires_on: date | None = None


@router.get("/members", response_model=Page[MemberOut])
def list_members(
    ctx: StaffContext,
    page: PageQuery,
    q: Annotated[str | None, Query(max_length=100)] = None,
    with_debt: bool = False,
) -> Page[MemberOut]:
    decision = authorize(
        engine=ctx.engine,
        action="library_member:list",
        resource_type="library_member",
        resource={"id": None, "status": "active"},
        category=AuditCategory.LIBRARY,
    )
    stmt = select(LibraryMember).where(LibraryMember.deleted_at.is_(None))
    if with_debt:
        stmt = stmt.where(LibraryMember.outstanding_fines_minor > 0)
    if q:
        term = f"%{q.lower()}%"
        stmt = stmt.where(
            or_(
                func.lower(LibraryMember.membership_number).like(term),
                func.lower(LibraryMember.full_name).like(term),
            )
        )
    found = keyset_page(
        ctx.db,
        stmt,
        page=page,
        key=LibraryMember.membership_number,
        ident=LibraryMember.id,
    )
    items = [
        MemberOut.model_construct(**decision.filter(MemberOut.model_validate(row).model_dump()))
        for row in found.rows
    ]
    return Page.of(items, limit=page.limit, next_cursor=found.next_cursor, total=found.total)


@router.post("/members", response_model=MemberOut, status_code=status.HTTP_201_CREATED)
def create_member(payload: MemberIn, ctx: StaffContext) -> MemberOut:
    authorize(
        engine=ctx.engine,
        action="library_member:create",
        resource_type="library_member",
        resource={
            "id": None,
            "student_id": str(payload.student_id) if payload.student_id else None,
            "staff_id": str(payload.staff_id) if payload.staff_id else None,
            "borrower_category": payload.borrower_category,
            "status": "active",
        },
        category=AuditCategory.LIBRARY,
    )
    if payload.student_id or payload.staff_id:
        member = service.ensure_member(
            ctx.db,
            student_id=payload.student_id,
            staff_id=payload.staff_id,
            borrower_category=payload.borrower_category,
            home_library_id=payload.home_library_id,
            expires_on=payload.expires_on,
        )
    else:
        if not payload.full_name:
            raise RuleViolation("An external reader needs a name.", rule="member_identity")
        member = LibraryMember(
            membership_number=f"EXT/{uuid.uuid4().hex[:8].upper()}",
            full_name=payload.full_name,
            email=payload.email,
            borrower_category=payload.borrower_category or "external",
            home_library_id=payload.home_library_id,
            joined_on=date.today(),
            expires_on=payload.expires_on,
            created_by_id=ctx.principal.id,
        )
        ctx.db.add(member)
        ctx.db.flush()
    return MemberOut.model_validate(member)


@router.get("/me/membership", response_model=dict)
def my_membership(ctx: AnyContext) -> dict[str, Any]:
    """A reader's own borrowing summary: what is out, what is due, what is owed."""
    stmt = select(LibraryMember).where(LibraryMember.deleted_at.is_(None))
    if ctx.principal.student_id is not None:
        stmt = stmt.where(LibraryMember.student_id == ctx.principal.student_id)
    elif ctx.principal.staff_id is not None:
        stmt = stmt.where(LibraryMember.staff_id == ctx.principal.staff_id)
    else:
        raise NotFound()
    member = ctx.db.execute(stmt).scalars().first()
    if member is None:
        return {"member": None, "loans": [], "reservations": [], "fines": []}

    authorize(
        engine=ctx.engine,
        action="library_member:read",
        resource_type="library_member",
        resource=member,
        category=AuditCategory.LIBRARY,
    )
    service.recompute_member(ctx.db, member=member)
    loans = ctx.db.execute(
        select(Loan, CatalogueCopy, CatalogueRecord)
        .join(CatalogueCopy, CatalogueCopy.id == Loan.copy_id)
        .join(CatalogueRecord, CatalogueRecord.id == CatalogueCopy.record_id)
        .where(
            Loan.member_id == member.id,
            Loan.status.in_((LoanStatus.OPEN, LoanStatus.OVERDUE)),
            Loan.deleted_at.is_(None),
        )
        .order_by(Loan.due_on)
    ).all()
    reservations = ctx.db.execute(
        select(Reservation, CatalogueRecord)
        .join(CatalogueRecord, CatalogueRecord.id == Reservation.record_id)
        .where(
            Reservation.member_id == member.id,
            Reservation.status.in_(("waiting", "ready")),
            Reservation.deleted_at.is_(None),
        )
        .order_by(Reservation.queue_position)
    ).all()
    fines = (
        ctx.db.execute(
            select(LibraryFine)
            .where(
                LibraryFine.member_id == member.id,
                LibraryFine.status.in_(("raised", "invoiced")),
                LibraryFine.deleted_at.is_(None),
            )
            .order_by(LibraryFine.raised_on.desc())
        )
        .scalars()
        .all()
    )
    return {
        "member": {
            "membership_number": member.membership_number,
            "borrower_category": member.borrower_category,
            "status": member.status,
            "expires_on": member.expires_on.isoformat() if member.expires_on else None,
            "items_on_loan": member.items_on_loan,
            "outstanding_fines_minor": member.outstanding_fines_minor,
        },
        "loans": [
            {
                "loan_id": str(loan.id),
                "title": record.title,
                "accession_number": copy.accession_number,
                "due_on": loan.due_on.isoformat(),
                "overdue": loan.due_on < date.today(),
                "renewals": loan.renewals,
            }
            for loan, copy, record in loans
        ],
        "reservations": [
            {
                "reservation_id": str(row.id),
                "title": record.title,
                "status": row.status,
                "queue_position": row.queue_position,
                "collect_by": row.collect_by.isoformat() if row.collect_by else None,
            }
            for row, record in reservations
        ],
        "fines": [
            {
                "fine_id": str(fine.id),
                "reason": fine.reason,
                "amount_minor": fine.amount_minor,
                "days_overdue": fine.days_overdue,
                "raised_on": fine.raised_on.isoformat(),
            }
            for fine in fines
        ],
    }


# ---------------------------------------------------------------------------
# Circulation
# ---------------------------------------------------------------------------


class LoanOut(Schema):
    id: uuid.UUID
    copy_id: uuid.UUID
    member_id: uuid.UUID
    library_id: uuid.UUID
    issued_at: datetime
    due_on: date
    original_due_on: date
    returned_on: date | None
    renewals: int
    status: str
    fine_per_day_minor: int
    #: Denormalised into the response, not stored. A desk looking at an
    #: overdue list needs the title on the shelf label and the number to ring
    #: — an identifier tells them nothing they can act on, and sending them
    #: to a second screen per row is how a queue forms at the counter.
    accession_number: str | None = None
    title: str | None = None
    membership_number: str | None = None


def _loan_out(loan: Loan) -> LoanOut:
    """A loan with the title, the accession and the borrower's number.

    The relationships are `lazy="joined"`, so this costs no extra query — the
    copy, its record and the member arrive with the loan.
    """
    copy = loan.copy
    record = copy.record if copy is not None else None
    member = loan.member
    return LoanOut.model_validate(
        {
            **{
                field: getattr(loan, field)
                for field in (
                    "id",
                    "copy_id",
                    "member_id",
                    "library_id",
                    "issued_at",
                    "due_on",
                    "original_due_on",
                    "returned_on",
                    "renewals",
                    "status",
                    "fine_per_day_minor",
                )
            },
            "accession_number": copy.accession_number if copy is not None else None,
            "title": record.title if record is not None else None,
            "membership_number": member.membership_number if member is not None else None,
        }
    )


class IssueIn(Schema):
    #: Scanned, not typed. Barcodes because that is what the desk has in its
    #: hand: a book and a card.
    barcode: Annotated[str, Field(max_length=60)]
    membership_number: Annotated[str, Field(max_length=40)]
    due_on: date | None = None


@router.post("/loans", response_model=LoanOut, status_code=status.HTTP_201_CREATED)
def issue_loan(payload: IssueIn, ctx: StaffContext) -> LoanOut:
    """Issue a copy. Two scans and nothing else."""
    copy = (
        ctx.db.execute(
            select(CatalogueCopy).where(
                CatalogueCopy.barcode == payload.barcode, CatalogueCopy.deleted_at.is_(None)
            )
        )
        .scalars()
        .first()
    )
    if copy is None:
        raise NotFound()
    member = (
        ctx.db.execute(
            select(LibraryMember).where(
                LibraryMember.membership_number == payload.membership_number,
                LibraryMember.deleted_at.is_(None),
            )
        )
        .scalars()
        .first()
    )
    if member is None:
        raise NotFound()

    authorize(
        engine=ctx.engine,
        action="library_loan:issue",
        resource_type="library_loan",
        resource={
            "id": None,
            "member_id": str(member.id),
            "student_id": str(member.student_id) if member.student_id else None,
            "staff_id": str(member.staff_id) if member.staff_id else None,
            "copy_id": str(copy.id),
            "library_id": str(copy.library_id),
            "status": "open",
            "is_overdue": False,
            "renewals": 0,
        },
        category=AuditCategory.LIBRARY,
    )
    loan = service.issue(
        ctx.db, copy=copy, member=member, actor_id=ctx.principal.id, due_on=payload.due_on
    )
    return _loan_out(loan)


class ReturnIn(Schema):
    barcode: Annotated[str, Field(max_length=60)]
    condition: Annotated[str | None, Field(max_length=20)] = None


@router.post("/loans/return", response_model=dict)
def return_loan(payload: ReturnIn, ctx: StaffContext) -> dict[str, Any]:
    """Take a copy back. One scan.

    Returns what the desk needs to say out loud: any charge, and whether the
    copy is to go on the hold shelf rather than back to the stacks.
    """
    copy = (
        ctx.db.execute(
            select(CatalogueCopy).where(
                CatalogueCopy.barcode == payload.barcode, CatalogueCopy.deleted_at.is_(None)
            )
        )
        .scalars()
        .first()
    )
    if copy is None:
        raise NotFound()
    loan = (
        ctx.db.execute(
            select(Loan)
            .where(
                Loan.copy_id == copy.id,
                Loan.status.in_((LoanStatus.OPEN, LoanStatus.OVERDUE)),
                Loan.deleted_at.is_(None),
            )
            .order_by(Loan.issued_at.desc())
        )
        .scalars()
        .first()
    )
    if loan is None:
        raise RuleViolation(
            "This copy is not on loan. Check the shelf before marking it missing.",
            rule="not_on_loan",
        )

    authorize(
        engine=ctx.engine,
        action="library_loan:return",
        resource_type="library_loan",
        resource=loan,
        category=AuditCategory.LIBRARY,
    )
    service.receive(ctx.db, loan=loan, actor_id=ctx.principal.id, condition=payload.condition)
    fine = (
        ctx.db.execute(
            select(LibraryFine)
            .where(LibraryFine.loan_id == loan.id, LibraryFine.deleted_at.is_(None))
            .order_by(LibraryFine.created_at.desc())
        )
        .scalars()
        .first()
    )
    return {
        "loan_id": str(loan.id),
        "returned_on": loan.returned_on.isoformat() if loan.returned_on else None,
        "copy_status": copy.status,
        "on_hold_shelf": copy.status == CopyStatus.ON_HOLD_SHELF,
        "fine": (
            {
                "amount_minor": fine.amount_minor,
                "days_overdue": fine.days_overdue,
                "reason": fine.reason,
            }
            if fine is not None and fine.reason == "overdue"
            else None
        ),
    }


@router.post("/loans/{loan_id}/renew", response_model=LoanOut)
def renew_loan(loan_id: uuid.UUID, ctx: AnyContext) -> LoanOut:
    """Extend a loan. The self-service path, and most renewal traffic."""
    loan = get_or_404(ctx, Loan, loan_id)
    authorize(
        engine=ctx.engine,
        action="library_loan:renew",
        resource_type="library_loan",
        resource=loan,
        category=AuditCategory.LIBRARY,
    )
    return _loan_out(service.renew(ctx.db, loan=loan, actor_id=ctx.principal.id))


class DeclareLostIn(Reason):
    replacement_minor: Annotated[int | None, Field(ge=0)] = None


@router.post("/loans/{loan_id}/declare-lost", response_model=dict)
def declare_lost(loan_id: uuid.UUID, payload: DeclareLostIn, ctx: StaffContext) -> dict[str, Any]:
    loan = get_or_404(ctx, Loan, loan_id)
    authorize(
        engine=ctx.engine,
        action="library_loan:declare_lost",
        resource_type="library_loan",
        resource=loan,
        category=AuditCategory.LIBRARY,
    )
    fine = service.declare_lost(
        ctx.db,
        loan=loan,
        actor_id=ctx.principal.id,
        replacement_minor=payload.replacement_minor,
    )
    return {"fine_id": str(fine.id), "amount_minor": fine.amount_minor}


@router.get("/loans", response_model=Page[LoanOut])
def list_loans(
    ctx: StaffContext,
    page: PageQuery,
    member_id: uuid.UUID | None = None,
    overdue_only: bool = False,
) -> Page[LoanOut]:
    """The circulation list. Desk work only — see `library.reading-privacy`."""
    # `student_id` and `staff_id` are published as `None` rather than left
    # out. Left out, `owns(resource.student_id, subject.student_id)` used to
    # be asked of two absent values — and the rule meant to show a reader
    # their own loans returned the whole circulation register instead.
    # `owns()` now refuses that, and stating the keys keeps the decision
    # legible in a trace.
    authorize(
        engine=ctx.engine,
        action="library_loan:list",
        resource_type="library_loan",
        resource={
            "id": None,
            "member_id": str(member_id) if member_id else None,
            "student_id": None,
            "staff_id": None,
            "copy_id": None,
            "library_id": None,
            "status": "open",
            "is_overdue": overdue_only,
            "renewals": 0,
        },
        category=AuditCategory.LIBRARY,
        audit_reads=True,
    )
    stmt = select(Loan).where(Loan.deleted_at.is_(None))
    if member_id:
        stmt = stmt.where(Loan.member_id == member_id)
    if overdue_only:
        stmt = stmt.where(Loan.status == LoanStatus.OVERDUE)
    found = keyset_page(ctx.db, stmt, page=page, key=Loan.due_on, ident=Loan.id)
    return Page.of(
        [_loan_out(row) for row in found.rows],
        limit=page.limit,
        next_cursor=found.next_cursor,
        total=found.total,
    )


class ReservationOut(Schema):
    id: uuid.UUID
    record_id: uuid.UUID
    member_id: uuid.UUID
    status: str
    queue_position: int
    collect_by: date | None
    requested_at: datetime


@router.post(
    "/records/{record_id}/reservations",
    response_model=ReservationOut,
    status_code=status.HTTP_201_CREATED,
)
def reserve_record(record_id: uuid.UUID, ctx: StudentContext) -> ReservationOut:
    """Join the queue for a title."""
    record = get_or_404(ctx, CatalogueRecord, record_id)
    member = (
        ctx.db.execute(
            select(LibraryMember).where(
                LibraryMember.student_id == ctx.student_id, LibraryMember.deleted_at.is_(None)
            )
        )
        .scalars()
        .first()
    )
    if member is None:
        member = service.ensure_member(ctx.db, student_id=ctx.student_id)

    authorize(
        engine=ctx.engine,
        action="library_reservation:create",
        resource_type="library_reservation",
        resource={
            "id": None,
            "member_id": str(member.id),
            "student_id": str(member.student_id) if member.student_id else None,
            "staff_id": None,
            "record_id": str(record.id),
            "status": "waiting",
        },
        category=AuditCategory.LIBRARY,
    )
    return ReservationOut.model_validate(service.reserve(ctx.db, record=record, member=member))


@router.post("/reservations/{reservation_id}/cancel", response_model=ReservationOut)
def cancel_reservation(reservation_id: uuid.UUID, ctx: AnyContext) -> ReservationOut:
    reservation = get_or_404(ctx, Reservation, reservation_id)
    authorize(
        engine=ctx.engine,
        action="library_reservation:cancel",
        resource_type="library_reservation",
        resource=reservation,
        category=AuditCategory.LIBRARY,
    )
    reservation.status = "cancelled"
    reservation.cancelled_at = ctx.db.execute(select(func.now())).scalar_one()
    ctx.db.flush()
    return ReservationOut.model_validate(reservation)


# ---------------------------------------------------------------------------
# Fines
# ---------------------------------------------------------------------------


class FineOut(Schema):
    id: uuid.UUID
    member_id: uuid.UUID
    loan_id: uuid.UUID | None
    reason: str
    amount_minor: int
    days_overdue: int | None
    rate_per_day_minor: int | None
    status: str
    raised_on: date


@router.get("/fines", response_model=Page[FineOut])
def list_fines(
    ctx: StaffContext,
    page: PageQuery,
    member_id: uuid.UUID | None = None,
    unpaid_only: bool = True,
) -> Page[FineOut]:
    authorize(
        engine=ctx.engine,
        action="library_fine:list",
        resource_type="library_fine",
        resource={
            "id": None,
            "member_id": str(member_id) if member_id else None,
            "reason": "overdue",
            "status": "raised",
            "amount_minor": 0,
            "raised_by_id": None,
        },
        category=AuditCategory.LIBRARY,
    )
    stmt = select(LibraryFine).where(LibraryFine.deleted_at.is_(None))
    if member_id:
        stmt = stmt.where(LibraryFine.member_id == member_id)
    if unpaid_only:
        stmt = stmt.where(LibraryFine.status.in_(("raised", "invoiced")))
    found = keyset_page(
        ctx.db, stmt, page=page, key=LibraryFine.raised_on, ident=LibraryFine.id, descending=True
    )
    return Page.of(
        [FineOut.model_validate(row) for row in found.rows],
        limit=page.limit,
        next_cursor=found.next_cursor,
        total=found.total,
    )


@router.post("/fines/{fine_id}/waive", response_model=FineOut)
def waive_fine(fine_id: uuid.UUID, payload: Reason, ctx: StaffContext) -> FineOut:
    """Forgive a charge. Money the institution has decided not to collect."""
    fine = get_or_404(ctx, LibraryFine, fine_id)
    authorize(
        engine=ctx.engine,
        action="library_fine:waive",
        resource_type="library_fine",
        resource=fine,
        category=AuditCategory.LIBRARY,
    )
    return FineOut.model_validate(
        service.waive_fine(ctx.db, fine=fine, actor_id=ctx.principal.id, reason=payload.reason)
    )


# ---------------------------------------------------------------------------
# Acquisitions and e-resources
# ---------------------------------------------------------------------------


class AcquisitionOut(Schema):
    id: uuid.UUID
    reference: str
    title: str
    authors: str | None
    isbn: str | None
    copies_requested: int
    course_id: uuid.UUID | None
    status: str
    requested_on: date
    estimated_unit_price_minor: int | None


class AcquisitionIn(Schema):
    title: Annotated[str, Field(max_length=400)]
    authors: Annotated[str | None, Field(max_length=400)] = None
    isbn: Annotated[str | None, Field(max_length=20)] = None
    publisher: Annotated[str | None, Field(max_length=200)] = None
    edition: Annotated[str | None, Field(max_length=60)] = None
    copies_requested: Annotated[int, Field(ge=1, le=500)] = 1
    requesting_unit_id: uuid.UUID | None = None
    course_id: uuid.UUID | None = None
    expected_cohort: Annotated[int | None, Field(ge=1)] = None
    justification: str | None = None
    estimated_unit_price_minor: Annotated[int | None, Field(ge=0)] = None


@router.post("/acquisitions", response_model=AcquisitionOut, status_code=status.HTTP_201_CREATED)
def request_acquisition(payload: AcquisitionIn, ctx: StaffContext) -> AcquisitionOut:
    """Ask the library to buy something."""
    authorize(
        engine=ctx.engine,
        action="acquisition_request:create",
        resource_type="acquisition_request",
        resource={
            "id": None,
            "status": "requested",
            "requested_by_id": str(ctx.principal.id),
            "course_id": str(payload.course_id) if payload.course_id else None,
            "department_ids": [str(d) for d in ctx.principal.department_ids],
            "faculty_ids": [str(f) for f in ctx.principal.faculty_ids],
        },
        category=AuditCategory.LIBRARY,
    )
    sequence = (
        int(
            ctx.db.execute(
                select(func.count()).where(AcquisitionRequest.deleted_at.is_(None))
            ).scalar_one()
        )
        + 1
    )
    request = AcquisitionRequest(
        reference=f"ACQ/{date.today().year}/{sequence:04d}",
        requested_by_id=ctx.principal.id,
        requested_on=date.today(),
        status="requested",
        created_by_id=ctx.principal.id,
        **payload.model_dump(),
    )
    ctx.db.add(request)
    ctx.db.flush()
    emit(
        "acquisition_request:create",
        AuditCategory.LIBRARY,
        resource_type="acquisition_request",
        resource_id=request.id,
        resource_label=request.reference,
        summary=f"Requested {payload.copies_requested} copy(ies) of {payload.title}",
    )
    return AcquisitionOut.model_validate(request)


@router.get("/acquisitions", response_model=Page[AcquisitionOut])
def list_acquisitions(
    ctx: StaffContext,
    page: PageQuery,
    status_filter: Annotated[str | None, Query(alias="status")] = None,
    mine_only: bool = False,
) -> Page[AcquisitionOut]:
    """Which requested titles are still not on the shelf.

    The question this table exists to answer, and the reason it is not an
    email thread.
    """
    authorize(
        engine=ctx.engine,
        action="acquisition_request:list",
        resource_type="acquisition_request",
        resource={
            "id": None,
            "status": status_filter,
            "requested_by_id": str(ctx.principal.id),
            "course_id": None,
            "department_ids": [str(d) for d in ctx.principal.department_ids],
            "faculty_ids": [str(f) for f in ctx.principal.faculty_ids],
        },
        category=AuditCategory.LIBRARY,
    )
    stmt = select(AcquisitionRequest).where(AcquisitionRequest.deleted_at.is_(None))
    if status_filter:
        stmt = stmt.where(AcquisitionRequest.status == status_filter)
    if mine_only:
        stmt = stmt.where(AcquisitionRequest.requested_by_id == ctx.principal.id)
    found = keyset_page(
        ctx.db,
        stmt,
        page=page,
        key=AcquisitionRequest.requested_on,
        ident=AcquisitionRequest.id,
        descending=True,
    )
    return Page.of(
        [AcquisitionOut.model_validate(row) for row in found.rows],
        limit=page.limit,
        next_cursor=found.next_cursor,
        total=found.total,
    )


class EResourceOut(Schema):
    id: uuid.UUID
    name: str
    provider: str
    kind: str
    access_url: str | None
    authentication_method: str | None
    expires_on: date
    concurrent_users: int | None
    is_active: bool


@router.get("/e-resources", response_model=list[EResourceOut])
def list_e_resources(ctx: AnyContext, expiring_days: int | None = None) -> list[EResourceOut]:
    """Subscribed databases and e-journals.

    `expiring_days` is what the acquisitions librarian opens this for: a
    subscription that lapses mid-semester is discovered by students, which is
    the worst way to discover it.
    """
    authorize(
        engine=ctx.engine,
        action="e_resource_subscription:list",
        resource_type="e_resource_subscription",
        resource={"id": None, "kind": "database", "is_active": True, "unit_ids": []},
    )
    stmt = select(EResourceSubscription).where(
        EResourceSubscription.deleted_at.is_(None),
        EResourceSubscription.is_active.is_(True),
    )
    if expiring_days is not None:
        cutoff = date.today() + timedelta(days=expiring_days)
        stmt = stmt.where(EResourceSubscription.expires_on <= cutoff)
    rows = ctx.db.execute(stmt.order_by(EResourceSubscription.expires_on)).scalars().all()
    return [EResourceOut.model_validate(row) for row in rows]


class LibraryOut(Schema):
    id: uuid.UUID
    code: str
    name: str
    campus_id: uuid.UUID | None
    location_note: str | None
    opening_hours: dict[str, Any]
    is_active: bool


@router.get("/branches", response_model=list[LibraryOut])
def list_branches(ctx: AnyContext) -> list[LibraryOut]:
    rows = (
        ctx.db.execute(
            select(Library)
            .where(Library.deleted_at.is_(None), Library.is_active.is_(True))
            .order_by(Library.code)
        )
        .scalars()
        .all()
    )
    return [LibraryOut.model_validate(row) for row in rows]


@router.get("/clearance/{student_id}", response_model=dict)
def library_clearance(student_id: uuid.UUID, ctx: StaffContext) -> dict[str, Any]:
    """What the library is owed by a leaving student.

    Shaped so the student can act on it — which books, how much — rather than
    just "not cleared".
    """
    authorize(
        engine=ctx.engine,
        action="library_member:read",
        resource_type="library_member",
        resource={
            "id": None,
            "student_id": str(student_id),
            "staff_id": None,
            "borrower_category": "undergraduate",
            "status": "active",
            "outstanding_fines_minor": 0,
            "items_on_loan": 0,
        },
        category=AuditCategory.LIBRARY,
    )
    return service.clearance_state(ctx.db, student_id=student_id)


@router.post("/jobs/accrue-overdue", response_model=dict)
def run_overdue_accrual(ctx: StaffContext) -> dict[str, int]:
    """The nightly overdue run, exposed so it can be triggered and tested."""
    authorize(
        engine=ctx.engine,
        action="library_fine:create",
        resource_type="library_fine",
        resource={
            "id": None,
            "member_id": None,
            "reason": "overdue",
            "status": "raised",
            "amount_minor": 0,
            "raised_by_id": None,
        },
        category=AuditCategory.LIBRARY,
    )
    accrued = service.accrue_overdue(ctx.db)
    expired = service.expire_hold_shelf(ctx.db)
    return {**accrued, "holds_expired": expired}
