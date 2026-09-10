"""Reference data: organisational units, the academic calendar, estate."""

from __future__ import annotations

import uuid
from datetime import date, datetime, timedelta
from typing import Annotated, Any

from fastapi import APIRouter, status
from pydantic import Field
from sqlalchemy import select

from acmis.core.abac import authorize
from acmis.core.audit import AuditCategory, emit
from acmis.core.deps import AnyContext, PageQuery, StaffContext
from acmis.core.errors import RuleViolation
from acmis.core.models import utcnow
from acmis.core.pagination import keyset_page
from acmis.core.schemas import Page, Schema
from acmis.modules.shared.models import (
    AcademicUnit,
    AcademicYear,
    CalendarEvent,
    Campus,
    Notification,
    Room,
    Semester,
    SystemSetting,
)
from acmis.routers._common import get_or_404

router = APIRouter(prefix="/reference", tags=["reference"])


class UnitOut(Schema):
    id: uuid.UUID
    code: str
    name: str
    kind: str
    parent_id: uuid.UUID | None
    ancestor_ids: list[uuid.UUID]
    depth: int
    head_staff_id: uuid.UUID | None
    campus_id: uuid.UUID | None
    is_active: bool


class UnitIn(Schema):
    code: Annotated[str, Field(max_length=20)]
    name: Annotated[str, Field(max_length=200)]
    kind: str
    parent_id: uuid.UUID | None = None
    campus_id: uuid.UUID | None = None
    head_staff_id: uuid.UUID | None = None
    email: str | None = None
    established_on: date | None = None


@router.get("/units", response_model=list[UnitOut])
def list_units(ctx: AnyContext, kind: str | None = None) -> list[UnitOut]:
    stmt = select(AcademicUnit).where(AcademicUnit.deleted_at.is_(None))
    if kind:
        stmt = stmt.where(AcademicUnit.kind == kind)
    rows = ctx.db.execute(stmt.order_by(AcademicUnit.depth, AcademicUnit.code)).scalars().all()
    return [UnitOut.model_validate(r) for r in rows]


@router.post("/units", response_model=UnitOut, status_code=status.HTTP_201_CREATED)
def create_unit(payload: UnitIn, ctx: StaffContext) -> UnitOut:
    """Add a node to the organisational tree.

    The ancestry is materialised here rather than walked on read: "every
    student in this college" is asked constantly, and every unit-scoped
    authorization decision compares against it. A recursive CTE per decision
    is not affordable.
    """
    authorize(
        engine=ctx.engine,
        action="academic_unit:create",
        resource_type="institution",
        resource={"id": None, "slug": ctx.tenant.slug, "status": "active"},
        category=AuditCategory.CONFIGURATION,
    )

    ancestors: list[uuid.UUID] = []
    depth = 0
    if payload.parent_id:
        parent = get_or_404(ctx, AcademicUnit, payload.parent_id)
        ancestors = [*(parent.ancestor_ids or ()), parent.id]
        depth = parent.depth + 1
        if depth >= 8:
            raise RuleViolation(
                "The organisational tree is limited to eight levels.",
                rule="unit_tree_too_deep",
            )

    unit = AcademicUnit(
        **payload.model_dump(),
        ancestor_ids=ancestors,
        depth=depth,
        created_by_id=ctx.principal.id,
    )
    ctx.db.add(unit)
    ctx.db.flush()
    emit(
        "academic_unit:create",
        AuditCategory.CONFIGURATION,
        resource_type="institution",
        resource_id=unit.id,
        resource_label=f"{unit.code} — {unit.name}",
        summary=f"Created {unit.kind} {unit.code}",
    )
    return UnitOut.model_validate(unit)


class SemesterOut(Schema):
    id: uuid.UUID
    academic_year_id: uuid.UUID
    kind: str
    name: str
    sequence: int
    starts_on: date
    ends_on: date
    registration_opens_on: date | None
    registration_closes_on: date | None
    add_drop_closes_on: date | None
    withdrawal_deadline_on: date | None
    teaching_starts_on: date | None
    teaching_ends_on: date | None
    exams_start_on: date | None
    exams_end_on: date | None
    results_due_on: date | None
    is_current: bool
    locked_at: datetime | None


class AcademicYearOut(Schema):
    id: uuid.UUID
    code: str
    name: str
    starts_on: date
    ends_on: date
    is_current: bool
    closed_at: datetime | None
    semesters: list[SemesterOut] = Field(default_factory=list)


@router.get("/academic-years", response_model=list[AcademicYearOut])
def list_academic_years(ctx: AnyContext) -> list[AcademicYearOut]:
    rows = (
        ctx.db.execute(
            select(AcademicYear)
            .where(AcademicYear.deleted_at.is_(None))
            .order_by(AcademicYear.starts_on.desc())
        )
        .scalars()
        .all()
    )
    return [AcademicYearOut.model_validate(r) for r in rows]


@router.get("/semesters/current", response_model=SemesterOut | None)
def current_semester(ctx: AnyContext) -> SemesterOut | None:
    """The semester in progress.

    Every module asks this — registration windows, mark-sheet deadlines, fee
    invoices — so it is one endpoint rather than each app deriving it from the
    calendar and disagreeing at the boundaries.
    """
    row = (
        ctx.db.execute(
            select(Semester).where(Semester.is_current.is_(True), Semester.deleted_at.is_(None))
        )
        .scalars()
        .first()
    )
    return SemesterOut.model_validate(row) if row else None


class CampusOut(Schema):
    id: uuid.UUID
    code: str
    name: str
    city: str | None
    country_code: str
    is_main: bool
    is_active: bool


@router.get("/campuses", response_model=list[CampusOut])
def list_campuses(ctx: AnyContext) -> list[CampusOut]:
    rows = (
        ctx.db.execute(select(Campus).where(Campus.deleted_at.is_(None)).order_by(Campus.name))
        .scalars()
        .all()
    )
    return [CampusOut.model_validate(r) for r in rows]


class RoomOut(Schema):
    id: uuid.UUID
    building_id: uuid.UUID
    code: str
    name: str | None
    kind: str
    capacity: int
    exam_capacity: int
    is_accessible: bool
    is_bookable: bool
    features: list[str]


@router.get("/rooms", response_model=Page[RoomOut])
def list_rooms(
    ctx: StaffContext,
    page: PageQuery,
    min_capacity: int | None = None,
    for_exams: bool = False,
) -> Page[RoomOut]:
    """Bookable spaces.

    `for_exams` filters on `exam_capacity`, which is always lower than the
    teaching capacity — examination seating needs a metre between candidates,
    so a 200-seat theatre seats about 80. Scheduling against one number
    produces a plan that cannot be sat.
    """
    stmt = select(Room).where(Room.deleted_at.is_(None), Room.is_bookable.is_(True))
    if min_capacity:
        column = Room.exam_capacity if for_exams else Room.capacity
        stmt = stmt.where(column >= min_capacity)
    found = keyset_page(ctx.db, stmt, page=page, key=Room.code, ident=Room.id)
    return Page.of(
        [RoomOut.model_validate(r) for r in found.rows],
        limit=page.limit,
        next_cursor=found.next_cursor,
        total=found.total,
    )


class NotificationOut(Schema):
    id: uuid.UUID
    category: str
    subject: str
    body: str
    action_url: str | None
    is_urgent: bool
    read_at: datetime | None
    created_at: datetime


@router.get("/notifications", response_model=Page[NotificationOut])
def my_notifications(
    ctx: AnyContext,
    page: PageQuery,
    unread_only: bool = False,
) -> Page[NotificationOut]:
    stmt = select(Notification).where(
        Notification.recipient_id == ctx.principal.id, Notification.deleted_at.is_(None)
    )
    if unread_only:
        stmt = stmt.where(Notification.read_at.is_(None))
    found = keyset_page(
        ctx.db,
        stmt,
        page=page,
        key=Notification.created_at,
        ident=Notification.id,
        descending=True,
    )
    return Page.of(
        [NotificationOut.model_validate(r) for r in found.rows],
        limit=page.limit,
        next_cursor=found.next_cursor,
        total=found.total,
    )


@router.post("/notifications/{notification_id}/read", status_code=status.HTTP_204_NO_CONTENT)
def mark_read(notification_id: uuid.UUID, ctx: AnyContext) -> None:
    from acmis.core.models import utcnow

    row = get_or_404(ctx, Notification, notification_id)
    if row.recipient_id != ctx.principal.id:
        # Not a 403 with an explanation: whose notification this is, is not
        # something the caller needs told.
        from acmis.core.errors import NotFound

        raise NotFound()
    row.read_at = row.read_at or utcnow()


class SettingOut(Schema):
    key: str
    scope_type: str
    scope_id: uuid.UUID | None
    value: dict[str, Any]
    description: str | None
    updated_at: datetime


@router.get("/settings", response_model=list[SettingOut])
def list_settings(ctx: StaffContext, prefix: str | None = None) -> list[SettingOut]:
    authorize(
        engine=ctx.engine,
        action="institution:read_settings",
        resource_type="institution",
        resource={"id": str(ctx.tenant.id), "slug": ctx.tenant.slug, "status": "active"},
        category=AuditCategory.CONFIGURATION,
    )
    stmt = select(SystemSetting)
    if prefix:
        stmt = stmt.where(SystemSetting.key.like(f"{prefix}%"))
    rows = ctx.db.execute(stmt.order_by(SystemSetting.key)).scalars().all()
    return [SettingOut.model_validate(r) for r in rows]


# ---------------------------------------------------------------------------
# The published academic calendar
# ---------------------------------------------------------------------------


class CalendarEventOut(Schema):
    id: uuid.UUID
    academic_year_id: uuid.UUID
    semester_id: uuid.UUID | None
    kind: str
    title: str
    description: str | None
    starts_on: date
    ends_on: date
    starts_at: str | None
    ends_at: str | None
    location: str | None
    unit_ids: list[uuid.UUID]
    audience: str
    suspends_teaching: bool
    is_published: bool
    minute_reference: str | None


class CalendarEventIn(Schema):
    academic_year_id: uuid.UUID
    semester_id: uuid.UUID | None = None
    kind: Annotated[
        str,
        Field(
            pattern="^(teaching|registration|examination|results|graduation|holiday"
            "|recess|governance|orientation|fees|other)$"
        ),
    ]
    title: Annotated[str, Field(max_length=200)]
    description: str | None = None
    starts_on: date
    ends_on: date
    starts_at: Annotated[str | None, Field(max_length=5)] = None
    ends_at: Annotated[str | None, Field(max_length=5)] = None
    location: Annotated[str | None, Field(max_length=200)] = None
    unit_ids: list[uuid.UUID] = Field(default_factory=list)
    campus_ids: list[uuid.UUID] = Field(default_factory=list)
    audience: Annotated[str, Field(pattern="^(all|students|staff|applicants|public)$")] = "all"
    #: A holiday or recess suspends teaching. A scheduler that ignores this
    #: books lectures nobody attends.
    suspends_teaching: bool = False


@router.get("/calendar", response_model=list[CalendarEventOut])
def list_calendar(
    ctx: AnyContext,
    academic_year_id: uuid.UUID | None = None,
    semester_id: uuid.UUID | None = None,
    from_date: date | None = None,
    to_date: date | None = None,
    kind: str | None = None,
) -> list[CalendarEventOut]:
    """The academic calendar.

    `Semester` carries the dates the *system* enforces — when registration
    opens, when the examination window runs. This is what people need to
    *see*: orientation, the graduation ceremony, the public holidays that
    suspend teaching.
    """
    authorize(
        engine=ctx.engine,
        action="calendar_event:list",
        resource_type="calendar_event",
        resource={
            "id": None,
            "kind": kind,
            "audience": "all",
            "is_published": True,
            "academic_year_id": str(academic_year_id) if academic_year_id else None,
            "semester_id": str(semester_id) if semester_id else None,
            "unit_ids": [],
            "faculty_ids": [],
            "department_ids": [],
        },
    )
    stmt = select(CalendarEvent).where(CalendarEvent.deleted_at.is_(None))
    if academic_year_id:
        stmt = stmt.where(CalendarEvent.academic_year_id == academic_year_id)
    if semester_id:
        stmt = stmt.where(CalendarEvent.semester_id == semester_id)
    if kind:
        stmt = stmt.where(CalendarEvent.kind == kind)
    # Overlap, not containment: a recess spanning the window asked for is
    # exactly the entry the caller most needs to see.
    if from_date:
        stmt = stmt.where(CalendarEvent.ends_on >= from_date)
    if to_date:
        stmt = stmt.where(CalendarEvent.starts_on <= to_date)
    if ctx.principal.kind in ("student", "applicant"):
        stmt = stmt.where(CalendarEvent.is_published.is_(True))

    rows = (
        ctx.db.execute(stmt.order_by(CalendarEvent.starts_on, CalendarEvent.title)).scalars().all()
    )
    return [CalendarEventOut.model_validate(row) for row in rows]


@router.post("/calendar", response_model=CalendarEventOut, status_code=status.HTTP_201_CREATED)
def create_calendar_event(payload: CalendarEventIn, ctx: StaffContext) -> CalendarEventOut:
    authorize(
        engine=ctx.engine,
        action="calendar_event:create",
        resource_type="calendar_event",
        resource={
            "id": None,
            "kind": payload.kind,
            "audience": payload.audience,
            "is_published": False,
            "academic_year_id": str(payload.academic_year_id),
            "semester_id": str(payload.semester_id) if payload.semester_id else None,
            "unit_ids": [str(u) for u in payload.unit_ids],
            "faculty_ids": [str(u) for u in payload.unit_ids],
            "department_ids": [str(u) for u in payload.unit_ids],
        },
        category=AuditCategory.CONFIGURATION,
    )
    if payload.ends_on < payload.starts_on:
        raise RuleViolation("An event cannot end before it starts.", rule="calendar_range")
    event = CalendarEvent(created_by_id=ctx.principal.id, **payload.model_dump())
    ctx.db.add(event)
    ctx.db.flush()
    emit(
        "calendar_event:create",
        AuditCategory.CONFIGURATION,
        resource_type="calendar_event",
        resource_id=event.id,
        resource_label=event.title,
        summary=f"Calendar entry drafted: {event.title} ({event.starts_on:%d %b %Y})",
    )
    return CalendarEventOut.model_validate(event)


class PublishCalendarIn(Schema):
    minute_reference: Annotated[str | None, Field(max_length=80)] = None


@router.post("/calendar/{event_id}/publish", response_model=CalendarEventOut)
def publish_calendar_event(
    event_id: uuid.UUID, ctx: StaffContext, payload: PublishCalendarIn | None = None
) -> CalendarEventOut:
    """Publish a calendar entry.

    A separate grant from drafting it: an institution's calendar is an
    approved document, and a date changed quietly after publication is a
    dispute with every student affected.
    """
    event = get_or_404(ctx, CalendarEvent, event_id)
    authorize(
        engine=ctx.engine,
        action="calendar_event:publish",
        resource_type="calendar_event",
        resource=event,
        category=AuditCategory.CONFIGURATION,
    )
    event.is_published = True
    event.published_at = utcnow()
    event.minute_reference = (payload or PublishCalendarIn()).minute_reference
    ctx.db.flush()
    emit(
        "calendar_event:publish",
        AuditCategory.CONFIGURATION,
        resource_type="calendar_event",
        resource_id=event.id,
        resource_label=event.title,
        summary="Calendar entry published",
        severity="notice",
    )
    return CalendarEventOut.model_validate(event)


@router.get("/calendar/suspended-dates", response_model=list[date])
def suspended_dates(ctx: AnyContext, academic_year_id: uuid.UUID) -> list[date]:
    """Every date on which teaching is suspended.

    Read by the class-session generator. Without it a semester's registers
    include days the campus was shut, and every course looks two weeks behind.
    """
    authorize(
        engine=ctx.engine,
        action="calendar_event:list",
        resource_type="calendar_event",
        resource={
            "id": None,
            "kind": "holiday",
            "audience": "all",
            "is_published": True,
            "academic_year_id": str(academic_year_id),
            "semester_id": None,
            "unit_ids": [],
            "faculty_ids": [],
            "department_ids": [],
        },
    )
    rows = (
        ctx.db.execute(
            select(CalendarEvent).where(
                CalendarEvent.academic_year_id == academic_year_id,
                CalendarEvent.suspends_teaching.is_(True),
                CalendarEvent.deleted_at.is_(None),
            )
        )
        .scalars()
        .all()
    )
    out: list[date] = []
    for event in rows:
        cursor = event.starts_on
        while cursor <= event.ends_on:
            out.append(cursor)
            cursor += timedelta(days=1)
    return sorted(set(out))
