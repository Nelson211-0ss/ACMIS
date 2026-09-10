"""Reference data every other module depends on.

The organisational tree, the academic calendar, physical estate, uploaded
files and notifications. It lives in one module because half the system joins
to it and the alternative is each module keeping its own idea of what a
"faculty" is.
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
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import ARRAY, JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from acmis.core.models import TenantBase, TenantRecord


class UnitKind(StrEnum):
    """One table for the whole tree, not four.

    Universities disagree about their own shape: Makerere has colleges
    containing schools containing departments, a smaller institution has
    faculties containing departments, and a polytechnic has neither. Modelling
    each level as its own table means the one that reorganises breaks the
    schema. A self-referencing tree with a `kind` absorbs all three, and the
    ABAC policies compare against `subject.faculty_ids` / `department_ids`
    populated from the ancestry rather than from a fixed level.
    """

    UNIVERSITY = "university"
    COLLEGE = "college"
    FACULTY = "faculty"
    SCHOOL = "school"
    INSTITUTE = "institute"
    DEPARTMENT = "department"
    CENTRE = "centre"
    DIRECTORATE = "directorate"


class AcademicUnit(TenantRecord):
    """A node in the organisational tree."""

    __tablename__ = "academic_unit"

    code: Mapped[str] = mapped_column(String(20), nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    kind: Mapped[str] = mapped_column(String(20), nullable=False, index=True)
    parent_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("academic_unit.id", ondelete="RESTRICT"), index=True
    )
    #: Materialised ancestry, root first. Denormalised because "every student
    #: in this college" is asked constantly and a recursive CTE per request is
    #: not free; maintained in one place (`shared.service.reparent`).
    ancestor_ids: Mapped[list[uuid.UUID]] = mapped_column(
        ARRAY(UUID(as_uuid=True)), nullable=False, default=list
    )
    depth: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    head_staff_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    deputy_staff_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    campus_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("campus.id", ondelete="SET NULL"), index=True
    )
    email: Mapped[str | None] = mapped_column(String(200))
    phone: Mapped[str | None] = mapped_column(String(40))
    established_on: Mapped[date | None] = mapped_column(Date)
    #: A dissolved unit keeps its rows — a graduate's transcript names the
    #: faculty that taught them, whether or not it still exists.
    dissolved_on: Mapped[date | None] = mapped_column(Date)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, index=True)

    parent: Mapped[AcademicUnit | None] = relationship(remote_side="AcademicUnit.id")

    __table_args__ = (
        UniqueConstraint("code", name="uq_academic_unit_code"),
        Index("ix_academic_unit_ancestors", "ancestor_ids", postgresql_using="gin"),
        CheckConstraint("depth >= 0 AND depth < 8", name="depth_sane"),
    )


class Campus(TenantRecord):
    __tablename__ = "campus"

    code: Mapped[str] = mapped_column(String(20), unique=True, nullable=False)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    city: Mapped[str | None] = mapped_column(String(120))
    region: Mapped[str | None] = mapped_column(String(120))
    country_code: Mapped[str] = mapped_column(String(2), nullable=False, default="UG")
    timezone: Mapped[str] = mapped_column(String(40), nullable=False, default="Africa/Kampala")
    is_main: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)


class Building(TenantRecord):
    __tablename__ = "building"

    campus_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("campus.id", ondelete="CASCADE"), nullable=False, index=True
    )
    code: Mapped[str] = mapped_column(String(20), nullable=False)
    name: Mapped[str] = mapped_column(String(200), nullable=False)

    __table_args__ = (UniqueConstraint("campus_id", "code", name="uq_building_campus_code"),)


class Room(TenantRecord):
    """A teachable or examinable space.

    `exam_capacity` is separate from `capacity` and always lower: examination
    seating needs a metre between candidates, so a 200-seat lecture theatre
    seats about 80 for an exam. Timetabling that uses one number for both
    produces a plan that cannot actually be sat.
    """

    __tablename__ = "room"

    building_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("building.id", ondelete="CASCADE"), nullable=False, index=True
    )
    code: Mapped[str] = mapped_column(String(30), nullable=False)
    name: Mapped[str | None] = mapped_column(String(200))
    kind: Mapped[str] = mapped_column(String(30), nullable=False, default="lecture")
    capacity: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    exam_capacity: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    has_projector: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    is_accessible: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    is_bookable: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    features: Mapped[list[str]] = mapped_column(ARRAY(String(40)), nullable=False, default=list)

    __table_args__ = (
        UniqueConstraint("building_id", "code", name="uq_room_building_code"),
        CheckConstraint("exam_capacity <= capacity", name="exam_capacity_fits"),
    )


class AcademicYear(TenantRecord):
    """e.g. 2026/2027."""

    __tablename__ = "academic_year"

    code: Mapped[str] = mapped_column(String(20), unique=True, nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(60), nullable=False)
    starts_on: Mapped[date] = mapped_column(Date, nullable=False)
    ends_on: Mapped[date] = mapped_column(Date, nullable=False)
    is_current: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, index=True)
    #: Set when every result for the year is Senate-approved and the ledger is
    #: closed. A closed year rejects writes everywhere, which is the mechanism
    #: that stops a transcript changing after it has been issued.
    closed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    semesters: Mapped[list[Semester]] = relationship(
        back_populates="year", cascade="all, delete-orphan", lazy="selectin"
    )

    __table_args__ = (
        CheckConstraint("ends_on > starts_on", name="year_ordered"),
        Index(
            "uq_academic_year_current",
            "is_current",
            unique=True,
            postgresql_where=is_current.is_(True),
        ),
    )


class SemesterKind(StrEnum):
    SEMESTER_ONE = "semester_1"
    SEMESTER_TWO = "semester_2"
    #: Retakes and accelerated courses. Counts for credit but not for
    #: progression, which is why it is a kind and not just a third semester.
    RECESS = "recess"
    TRIMESTER_THREE = "trimester_3"


class Semester(TenantRecord):
    """A teaching period, with the dates every other module gates on.

    The five windows are separate because they genuinely differ and staff argue
    about each one: registration closes weeks before teaching ends, adding a
    course closes earlier than dropping one, and the results-entry window opens
    only after the last examination.
    """

    __tablename__ = "semester"

    academic_year_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("academic_year.id", ondelete="CASCADE"), nullable=False, index=True
    )
    kind: Mapped[str] = mapped_column(String(20), nullable=False)
    name: Mapped[str] = mapped_column(String(60), nullable=False)
    sequence: Mapped[int] = mapped_column(Integer, nullable=False, default=1)

    starts_on: Mapped[date] = mapped_column(Date, nullable=False)
    ends_on: Mapped[date] = mapped_column(Date, nullable=False)
    enrolment_opens_on: Mapped[date | None] = mapped_column(Date)
    enrolment_closes_on: Mapped[date | None] = mapped_column(Date)
    registration_opens_on: Mapped[date | None] = mapped_column(Date)
    registration_closes_on: Mapped[date | None] = mapped_column(Date)
    add_drop_closes_on: Mapped[date | None] = mapped_column(Date)
    withdrawal_deadline_on: Mapped[date | None] = mapped_column(Date)
    teaching_starts_on: Mapped[date | None] = mapped_column(Date)
    teaching_ends_on: Mapped[date | None] = mapped_column(Date)
    exams_start_on: Mapped[date | None] = mapped_column(Date)
    exams_end_on: Mapped[date | None] = mapped_column(Date)
    results_due_on: Mapped[date | None] = mapped_column(Date)

    is_current: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, index=True)
    #: Locked once results are released. Reopening is an audited act.
    locked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    year: Mapped[AcademicYear] = relationship(back_populates="semesters")

    __table_args__ = (
        UniqueConstraint("academic_year_id", "kind", name="uq_semester_year_kind"),
        CheckConstraint("ends_on > starts_on", name="semester_ordered"),
    )

    @property
    def registration_open(self) -> bool:
        today = date.today()
        opens = self.registration_opens_on or self.starts_on
        closes = self.registration_closes_on or self.ends_on
        return opens <= today <= closes and self.locked_at is None


class Attachment(TenantRecord):
    """Metadata for a file in object storage.

    The bytes never touch Postgres. What is stored here is the key, the
    declared and *sniffed* content types, and a SHA-256 of the content —
    checked on download, because a certificate scan that has been silently
    swapped in storage is exactly the kind of thing this system must be able to
    detect.
    """

    __tablename__ = "attachment"

    storage_key: Mapped[str] = mapped_column(String(500), unique=True, nullable=False)
    bucket: Mapped[str] = mapped_column(String(120), nullable=False)
    file_name: Mapped[str] = mapped_column(String(400), nullable=False)
    content_type: Mapped[str] = mapped_column(String(120), nullable=False)
    #: What libmagic saw. A `.pdf` that sniffs as `text/html` is a stored-XSS
    #: attempt, not a certificate.
    detected_content_type: Mapped[str | None] = mapped_column(String(120))
    size_bytes: Mapped[int] = mapped_column(Integer, nullable=False)
    sha256: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    #: Loose polymorphic link. No FK: attachments belong to twelve different
    #: tables across five modules, and a nullable FK per owner type is worse
    #: than a typed pair the service layer validates.
    owner_type: Mapped[str] = mapped_column(String(60), nullable=False, index=True)
    owner_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False, index=True)
    purpose: Mapped[str] = mapped_column(String(60), nullable=False)
    is_verified: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    verified_by_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    verified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    #: Set when the antivirus scan clears. Nothing is served to a browser until
    #: it is: a university's document store is a convenient malware host.
    scanned_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    scan_result: Mapped[str | None] = mapped_column(String(40))

    __table_args__ = (Index("ix_attachment_owner", "owner_type", "owner_id"),)


class Notification(TenantRecord):
    """One message to one recipient, across every channel it was sent on.

    Delivery state per channel, not one status: an SMS to a village and an
    email to the same student succeed and fail independently, and "did the
    student find out their results were released" is answerable only if you
    kept both.
    """

    __tablename__ = "notification"

    recipient_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False, index=True)
    recipient_kind: Mapped[str] = mapped_column(String(20), nullable=False)
    category: Mapped[str] = mapped_column(String(40), nullable=False, index=True)
    subject: Mapped[str] = mapped_column(String(300), nullable=False)
    body: Mapped[str] = mapped_column(Text, nullable=False)
    #: Deep link into the module app that owns the subject of the message.
    action_url: Mapped[str | None] = mapped_column(String(500))
    channels: Mapped[list[str]] = mapped_column(ARRAY(String(20)), nullable=False, default=list)
    delivery: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)
    read_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    #: A results release or a fee deadline must not be silently dropped, so a
    #: failed send is retried and this records how often.
    attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    is_urgent: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    __table_args__ = (Index("ix_notification_inbox", "recipient_id", "read_at", "created_at"),)


class SystemSetting(TenantBase):
    """Institution-configurable knobs, one row per key.

    A key/value table rather than a wide singleton row: universities keep
    adding settings, and a wide table means a migration in 200 databases every
    time one of them wants a new checkbox. `scope` lets a setting be overridden
    per faculty, which is how "who may enter marks late" differs between
    Medicine and Law in the same institution.
    """

    __tablename__ = "system_setting"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    key: Mapped[str] = mapped_column(String(120), nullable=False, index=True)
    scope_type: Mapped[str] = mapped_column(String(30), nullable=False, default="institution")
    scope_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    value: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)
    description: Mapped[str | None] = mapped_column(Text)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_by_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))

    __table_args__ = (
        UniqueConstraint("key", "scope_type", "scope_id", name="uq_system_setting_scope"),
    )


class CalendarEvent(TenantRecord):
    """A dated entry in the published academic calendar.

    `Semester` already carries the dates the *system* enforces — when
    registration opens, when the examination window runs. This is for the
    dates people need to *see*: orientation, the graduation ceremony, Senate
    sittings, public holidays that suspend teaching, a faculty's field-work
    week.

    Kept separate from the semester's own fields deliberately. Those are gates
    the code reads and there is exactly one of each; these are announcements,
    there are dozens, they are scoped to an audience, and a wrong one is an
    inconvenience rather than a student unable to register.
    """

    __tablename__ = "calendar_event"

    academic_year_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("academic_year.id", ondelete="CASCADE"), nullable=False, index=True
    )
    semester_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("semester.id", ondelete="CASCADE"), index=True
    )
    #: `teaching`, `registration`, `examination`, `results`, `graduation`,
    #: `holiday`, `recess`, `governance`, `orientation`, `fees`, `other`.
    kind: Mapped[str] = mapped_column(String(30), nullable=False, index=True)
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    starts_on: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    #: Inclusive. Equal to `starts_on` for a single-day event.
    ends_on: Mapped[date] = mapped_column(Date, nullable=False)
    starts_at: Mapped[str | None] = mapped_column(String(5))
    ends_at: Mapped[str | None] = mapped_column(String(5))
    location: Mapped[str | None] = mapped_column(String(200))
    #: Empty means the whole institution. Otherwise the units it applies to —
    #: a faculty's own field-work week is not everybody's.
    unit_ids: Mapped[list[uuid.UUID]] = mapped_column(
        ARRAY(UUID(as_uuid=True)), nullable=False, default=list
    )
    campus_ids: Mapped[list[uuid.UUID]] = mapped_column(
        ARRAY(UUID(as_uuid=True)), nullable=False, default=list
    )
    #: `all`, `students`, `staff`, `applicants`, `public`. Drives who sees it,
    #: and whether it appears on the public site before anyone signs in.
    audience: Mapped[str] = mapped_column(String(20), nullable=False, default="all", index=True)
    #: A holiday or recess suspends teaching; a scheduler that ignores this
    #: books lectures nobody attends.
    suspends_teaching: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    is_published: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, index=True)
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    #: The Senate minute that approved the calendar. An institution's calendar
    #: is an approved document, and a date changed without one is a dispute.
    minute_reference: Mapped[str | None] = mapped_column(String(80))

    __table_args__ = (
        CheckConstraint("ends_on >= starts_on", name="ck_calendar_event_range"),
        Index("ix_calendar_event_window", "academic_year_id", "starts_on", "ends_on"),
    )
