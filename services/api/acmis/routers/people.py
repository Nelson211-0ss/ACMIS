"""Faculty and staff management endpoints."""

from __future__ import annotations

import uuid
from datetime import date, datetime
from typing import Annotated, Any

from fastapi import APIRouter, Query, status
from pydantic import Field
from sqlalchemy import func, select

from acmis.core.abac import authorize, enforce_writable
from acmis.core.audit import AuditCategory, diff, emit
from acmis.core.deps import PageQuery, StaffContext
from acmis.core.errors import Conflict, RuleViolation
from acmis.core.models import utcnow
from acmis.core.pagination import keyset_page
from acmis.core.schemas import Page, RecordEnvelope, Schema
from acmis.modules.people.models import (
    LeaveBalance,
    LeaveRequest,
    Staff,
    Workload,
)
from acmis.routers._common import get_or_404

router = APIRouter(prefix="/people", tags=["people"])


class StaffOut(Schema):
    id: uuid.UUID
    staff_number: str
    title: str | None
    surname: str
    given_names: str
    display_title: str | None
    email: str
    phone: str
    category: str
    rank: str | None
    has_doctorate: bool
    highest_qualification: str | None
    specialisation: str | None
    primary_unit_id: uuid.UUID | None
    status: str
    first_appointed_on: date | None
    contract_ends_on: date | None
    #: Behind `people:payroll`; masked for every line manager.
    salary_scale: str | None = None
    national_id: str | None = None
    bank_account_number: str | None = None
    medical_notes: str | None = None


@router.get("", response_model=Page[StaffOut])
def list_staff(
    ctx: StaffContext,
    page: PageQuery,
    unit_id: uuid.UUID | None = None,
    category: str | None = None,
    search: Annotated[str | None, Query(max_length=80)] = None,
) -> Page[StaffOut]:
    decision = authorize(
        engine=ctx.engine,
        action="staff:list",
        resource_type="staff",
        resource={"id": None, "status": "active"},
        category=AuditCategory.PEOPLE,
    )
    stmt = select(Staff).where(Staff.deleted_at.is_(None))
    if unit_id:
        stmt = stmt.where(Staff.primary_unit_id == unit_id)
    if category:
        stmt = stmt.where(Staff.category == category)
    if search:
        term = f"%{search.lower()}%"
        stmt = stmt.where(
            func.lower(Staff.surname).like(term)
            | func.lower(Staff.given_names).like(term)
            | func.lower(Staff.staff_number).like(term)
        )

    reach = ctx.principal.department_ids | ctx.principal.faculty_ids
    if reach and "people:admin" not in ctx.principal.permissions:
        stmt = stmt.where(
            Staff.department_ids.overlap(sorted(reach)) | Staff.faculty_ids.overlap(sorted(reach))
        )

    found = keyset_page(
        ctx.db,
        stmt,
        page=page,
        # One expression rather than two columns, so the cursor predicate can
        # mirror the ordering exactly.
        key=func.concat_ws(" ", Staff.surname, Staff.given_names),
        ident=Staff.id,
    )
    items = [
        StaffOut.model_construct(**decision.filter(StaffOut.model_validate(r).model_dump()))
        for r in found.rows
    ]
    return Page.of(items, limit=page.limit, next_cursor=found.next_cursor, total=found.total)


@router.get("/{staff_id}", response_model=RecordEnvelope[StaffOut])
def get_staff(staff_id: uuid.UUID, ctx: StaffContext) -> RecordEnvelope[StaffOut]:
    staff = get_or_404(ctx, Staff, staff_id)
    decision = authorize(
        engine=ctx.engine,
        action="staff:read",
        resource_type="staff",
        resource=staff,
        category=AuditCategory.PEOPLE,
    )
    payload = StaffOut.model_validate(staff).model_dump()
    return RecordEnvelope(
        data=StaffOut.model_construct(**decision.filter(payload)),
        masked_fields=sorted(decision.masked_fields),
    )


class StaffUpdateIn(Schema):
    phone: str | None = None
    personal_email: str | None = None
    postal_address: str | None = None
    next_of_kin_name: str | None = None
    next_of_kin_phone: str | None = None
    biography: str | None = None
    orcid: str | None = None
    specialisation: str | None = None
    #: HR-owned. A staff member sending these gets a 422 naming them.
    rank: str | None = None
    salary_scale: str | None = None
    category: str | None = None


@router.patch("/{staff_id}", response_model=StaffOut)
def update_staff(staff_id: uuid.UUID, payload: StaffUpdateIn, ctx: StaffContext) -> StaffOut:
    staff = get_or_404(ctx, Staff, staff_id)
    decision = authorize(
        engine=ctx.engine,
        action="staff:update",
        resource_type="staff",
        resource=staff,
        category=AuditCategory.PEOPLE,
    )
    changes = payload.model_dump(exclude_unset=True, exclude_none=True)
    enforce_writable(decision, changes)

    tracked = {k: getattr(staff, k, None) for k in changes}
    for field, value in changes.items():
        setattr(staff, field, value)
    staff.updated_by_id = ctx.principal.id
    ctx.db.flush()

    changed = diff(tracked, {k: getattr(staff, k, None) for k in changes})
    if changed:
        emit(
            "staff:update",
            AuditCategory.PEOPLE,
            resource_type="staff",
            resource_id=staff.id,
            resource_label=f"{staff.full_name} ({staff.staff_number})",
            summary=f"{len(changed)} field(s) updated",
            changes=changed,
        )
    return StaffOut.model_validate(staff)


class LeaveRequestIn(Schema):
    staff_id: uuid.UUID
    leave_type: str
    starts_on: date
    ends_on: date
    working_days: Annotated[float, Field(gt=0, le=400)]
    reason: str | None = None
    cover_staff_id: uuid.UUID | None = None
    cover_arrangements: str | None = None


class LeaveRequestOut(Schema):
    id: uuid.UUID
    staff_id: uuid.UUID
    leave_type: str
    starts_on: date
    ends_on: date
    working_days: float
    reason: str | None
    cover_staff_id: uuid.UUID | None
    status: str
    supervisor_approved_at: datetime | None
    hr_approved_at: datetime | None
    rejection_reason: str | None


@router.post("/leave", response_model=LeaveRequestOut, status_code=status.HTTP_201_CREATED)
def request_leave(payload: LeaveRequestIn, ctx: StaffContext) -> LeaveRequestOut:
    """Apply for leave, checking the balance and the teaching cover.

    Cover is required during a teaching semester because unallocated courses
    are the observable consequence of approved leave — a sabbatical granted
    with no cover is discovered by students in week one.
    """
    staff = get_or_404(ctx, Staff, payload.staff_id)
    authorize(
        engine=ctx.engine,
        action="leave_request:create",
        resource_type="leave_request",
        resource={
            "id": None,
            "staff_id": str(staff.id),
            "status": "submitted",
            "leave_type": payload.leave_type,
        },
        category=AuditCategory.PEOPLE,
    )

    balance = ctx.db.execute(
        select(LeaveBalance).where(
            LeaveBalance.staff_id == staff.id,
            LeaveBalance.year == payload.starts_on.year,
            LeaveBalance.leave_type == payload.leave_type,
        )
    ).scalar_one_or_none()
    if balance is not None and payload.working_days > balance.available_days:
        raise RuleViolation(
            f"{payload.working_days:g} days requested but only "
            f"{balance.available_days:g} available.",
            rule="insufficient_leave_balance",
            waivable_by=["people:approve"],
        )

    if payload.leave_type in {"sabbatical", "study"} and not (
        payload.cover_staff_id or payload.cover_arrangements
    ):
        raise RuleViolation(
            "Long leave needs teaching cover arrangements before it can be considered.",
            rule="cover_required",
        )

    request = LeaveRequest(
        **payload.model_dump(), status="submitted", created_by_id=ctx.principal.id
    )
    ctx.db.add(request)
    ctx.db.flush()
    if balance is not None:
        # Committed, not taken. A second request must not be approved against
        # days already promised to the first.
        balance.committed_days = float(balance.committed_days) + payload.working_days

    emit(
        "leave_request:create",
        AuditCategory.PEOPLE,
        resource_type="leave_request",
        resource_id=request.id,
        summary=(
            f"{payload.leave_type} leave requested: "
            f"{payload.starts_on:%d %b} - {payload.ends_on:%d %b %Y}"
        ),
    )
    return LeaveRequestOut.model_validate(request)


class LeaveDecisionIn(Schema):
    approve: bool
    stage: Annotated[str, Field(pattern="^(supervisor|hr)$")] = "supervisor"
    note: str | None = None


@router.post("/leave/{request_id}/decide", response_model=LeaveRequestOut)
def decide_leave(
    request_id: uuid.UUID, payload: LeaveDecisionIn, ctx: StaffContext
) -> LeaveRequestOut:
    request = get_or_404(ctx, LeaveRequest, request_id)
    authorize(
        engine=ctx.engine,
        action="leave_request:approve" if payload.approve else "leave_request:reject",
        resource_type="leave_request",
        resource=request,
        category=AuditCategory.PEOPLE,
    )
    if request.staff_id == ctx.principal.staff_id:
        raise RuleViolation(
            "Your own leave must be decided by your supervisor.",
            rule="no_self_approval",
        )
    if request.status in {"approved", "rejected", "cancelled"}:
        raise Conflict("This request has already been decided.")

    before = {"status": request.status}
    now = utcnow()
    if not payload.approve:
        request.status = "rejected"
        request.rejection_reason = payload.note
        balance = ctx.db.execute(
            select(LeaveBalance).where(
                LeaveBalance.staff_id == request.staff_id,
                LeaveBalance.year == request.starts_on.year,
                LeaveBalance.leave_type == request.leave_type,
            )
        ).scalar_one_or_none()
        if balance is not None:
            balance.committed_days = max(
                0.0, float(balance.committed_days) - float(request.working_days)
            )
    elif payload.stage == "supervisor":
        request.supervisor_approved_by_id = ctx.principal.id
        request.supervisor_approved_at = now
        request.status = "supervisor_approved"
    else:
        if request.supervisor_approved_at is None:
            raise Conflict("The supervisor has not approved this request yet.")
        request.hr_approved_by_id = ctx.principal.id
        request.hr_approved_at = now
        request.status = "approved"
        balance = ctx.db.execute(
            select(LeaveBalance).where(
                LeaveBalance.staff_id == request.staff_id,
                LeaveBalance.year == request.starts_on.year,
                LeaveBalance.leave_type == request.leave_type,
            )
        ).scalar_one_or_none()
        if balance is not None:
            balance.committed_days = max(
                0.0, float(balance.committed_days) - float(request.working_days)
            )
            balance.taken_days = float(balance.taken_days) + float(request.working_days)

    ctx.db.flush()
    emit(
        f"leave_request:{'approve' if payload.approve else 'reject'}",
        AuditCategory.PEOPLE,
        resource_type="leave_request",
        resource_id=request.id,
        summary=f"{before['status']} -> {request.status} ({payload.stage})",
        changes=diff(before, {"status": request.status}),
        metadata={"note": payload.note},
        severity="notice",
    )
    return LeaveRequestOut.model_validate(request)


class WorkloadOut(Schema):
    id: uuid.UUID
    staff_id: uuid.UUID
    semester_id: uuid.UUID
    teaching_hours: float
    credit_units_taught: float
    course_count: int
    student_count: int
    supervision_count: int
    total_load_hours: float
    norm_hours: float | None
    status: str


@router.get("/workload", response_model=list[WorkloadOut])
def list_workload(
    ctx: StaffContext, semester_id: uuid.UUID, unit_id: uuid.UUID | None = None
) -> list[WorkloadOut]:
    """Teaching load for a semester, for the comparison the module exists for.

    The complaint a workload system answers is always comparative — "I am
    teaching four courses while my colleague teaches one" — so this returns the
    unit, not one person.
    """
    authorize(
        engine=ctx.engine,
        action="workload:list",
        resource_type="workload",
        resource={"id": None, "semester_id": str(semester_id), "status": "draft"},
        category=AuditCategory.PEOPLE,
    )
    stmt = select(Workload).where(
        Workload.semester_id == semester_id, Workload.deleted_at.is_(None)
    )
    if unit_id:
        stmt = stmt.join(Staff, Staff.id == Workload.staff_id).where(
            Staff.primary_unit_id == unit_id
        )
    rows = ctx.db.execute(stmt.order_by(Workload.total_load_hours.desc())).scalars().all()
    return [WorkloadOut.model_validate(r) for r in rows]


@router.post("/workload/recompute", response_model=dict)
def recompute_workload(ctx: StaffContext, semester_id: uuid.UUID) -> dict[str, Any]:
    """Rebuild workload rows from teaching allocations and supervision.

    Derived data, recomputed rather than maintained incrementally: allocations
    change all semester, and an incrementally-updated total drifts from the
    allocations it is supposed to summarise.
    """
    from acmis.modules.curriculum.models import CourseOffering, TeachingAllocation
    from acmis.modules.people.models import Supervision

    authorize(
        engine=ctx.engine,
        action="workload:assign",
        resource_type="workload",
        resource={"id": None, "semester_id": str(semester_id), "status": "draft"},
        category=AuditCategory.PEOPLE,
    )

    rows = ctx.db.execute(
        select(TeachingAllocation, CourseOffering)
        .join(CourseOffering, TeachingAllocation.offering_id == CourseOffering.id)
        .where(
            CourseOffering.semester_id == semester_id,
            TeachingAllocation.deleted_at.is_(None),
        )
    ).all()

    aggregate: dict[uuid.UUID, dict[str, float]] = {}
    for allocation, offering in rows:
        bucket = aggregate.setdefault(
            allocation.staff_id,
            {"hours": 0.0, "credits": 0.0, "courses": 0.0, "students": 0.0},
        )
        share = float(allocation.load_share_percent or 100) / 100
        bucket["hours"] += float(allocation.contact_hours or 0)
        bucket["credits"] += float(offering.course.credit_units) * share
        bucket["courses"] += 1
        bucket["students"] += offering.registered_count

    supervision_counts: dict[uuid.UUID, int] = dict(
        ctx.db.execute(
            select(Supervision.staff_id, func.count())
            .where(Supervision.status == "active", Supervision.deleted_at.is_(None))
            .group_by(Supervision.staff_id)
        ).tuples()
    )

    written = 0
    for staff_id, values in aggregate.items():
        row = ctx.db.execute(
            select(Workload).where(
                Workload.staff_id == staff_id, Workload.semester_id == semester_id
            )
        ).scalar_one_or_none()
        if row is None:
            row = Workload(
                staff_id=staff_id, semester_id=semester_id, created_by_id=ctx.principal.id
            )
            ctx.db.add(row)
        row.teaching_hours = values["hours"]
        row.credit_units_taught = values["credits"]
        row.course_count = int(values["courses"])
        row.student_count = int(values["students"])
        row.supervision_count = int(supervision_counts.get(staff_id, 0))
        # Supervision is weighted at 5 hours per candidate per semester, which
        # is the figure most institutional workload policies in the region use.
        row.total_load_hours = (
            values["hours"] + row.supervision_count * 5 + float(row.administrative_hours or 0)
        )
        written += 1

    ctx.db.flush()
    emit(
        "workload:assign",
        AuditCategory.PEOPLE,
        resource_type="workload",
        summary=f"Recomputed workload for {written} staff member(s)",
        metadata={"semester_id": str(semester_id)},
    )
    return {"staff_updated": written}
