"""Student life-cycle operations."""

from __future__ import annotations

import uuid
from datetime import date
from typing import Any

import structlog
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from acmis.core.abac import bulk_decide
from acmis.core.audit import AuditCategory, diff, emit
from acmis.core.errors import Conflict, NotFound, RuleViolation, ValidationFailed
from acmis.core.models import utcnow
from acmis.core.schemas import Capability
from acmis.modules.assessment.rules import validate_credit_load
from acmis.modules.students.models import (
    Clearance,
    Enrolment,
    Registration,
    RegistrationCourse,
    StatusChange,
    Student,
    StudentProgramme,
    StudentStatus,
)

log = structlog.get_logger(__name__)

STUDENT_ACTIONS = (
    "student:read",
    "student:update",
    "student:read_medical",
    "student:read_disciplinary",
    "registration:create",
    "registration:approve",
    "transcript:issue",
    "student_status_change:create",
)


def capabilities_for(ctx: Any, student: Student) -> list[Capability]:
    allowed = bulk_decide(
        engine=ctx.engine,
        actions=STUDENT_ACTIONS,
        resource_type="student",
        resource=student,
    )
    return [Capability(action=a, allowed=v) for a, v in allowed.items()]


# ---------------------------------------------------------------------------
# Student numbers
# ---------------------------------------------------------------------------


def generate_student_number(
    session: Session, *, programme_code: str, entry_year: int, template: str | None = None
) -> str:
    """Build the institutional student number.

    Format is configurable because it is the one identifier a graduate quotes
    for the rest of their life and every institution's is different — Makerere
    uses `26/U/1234/PS`, others `BSC/2026/0142`. The default follows the
    common East African shape.

    The serial is derived from a count within the year. Two concurrent
    enrolments can compute the same one; the unique index rejects the second
    and the caller retries, which is correct — the alternative is a sequence
    per institution per year, which is a lot of DDL for a number generated a
    few thousand times a year.
    """
    short_year = entry_year % 100
    used = session.execute(
        select(func.count())
        .select_from(Student)
        .where(func.extract("year", Student.admitted_on) == entry_year)
    ).scalar_one()
    serial = used + 1
    pattern = template or "{yy:02d}/U/{serial:04d}/{code}"
    return pattern.format(
        yy=short_year,
        year=entry_year,
        serial=serial,
        code=programme_code[:3].upper(),
        programme=programme_code.upper(),
    )


def create_from_admission(
    session: Session,
    *,
    applicant: Any,
    programme: Any,
    version: Any,
    intake: Any,
    semester_id: uuid.UUID,
    student_number: str | None,
    sponsorship: str,
    actor_id: uuid.UUID,
) -> tuple[Student, StudentProgramme, Enrolment]:
    """Create the student, their programme attachment and their first enrolment.

    Called only from `admissions.service.enrol`, inside that transaction. The
    bio-data is copied from the applicant rather than referenced: an applicant
    record is a snapshot of a person at the point of applying, and a student
    record is maintained thereafter — sharing one row would mean a student
    correcting their address silently rewrites the application they were
    admitted on.
    """
    from acmis.modules.shared.models import Semester

    semester = session.get(Semester, semester_id)
    if semester is None:
        raise NotFound("That semester does not exist.")

    entry_year = semester.starts_on.year
    number = student_number or generate_student_number(
        session, programme_code=programme.code, entry_year=entry_year
    )

    student = Student(
        student_number=number,
        applicant_id=applicant.id,
        surname=applicant.surname,
        given_names=applicant.given_names,
        other_names=applicant.other_names,
        certificate_name=applicant.full_name,
        date_of_birth=applicant.date_of_birth,
        sex=applicant.sex,
        marital_status=applicant.marital_status,
        nationality=applicant.nationality,
        country_code=applicant.country_code,
        district_of_origin=applicant.district_of_origin,
        email=applicant.email,
        personal_email=applicant.email,
        phone=applicant.phone,
        alternate_phone=applicant.alternate_phone,
        postal_address=applicant.home_address,
        national_id=applicant.national_id,
        passport_number=applicant.passport_number,
        disability=applicant.disability,
        disability_detail=applicant.disability_detail,
        next_of_kin_name=applicant.guardian_name,
        next_of_kin_relationship=applicant.guardian_relationship,
        next_of_kin_phone=applicant.guardian_phone,
        status=StudentStatus.ADMITTED,
        admitted_on=date.today(),
        faculty_ids=list(programme.faculty_ids or ()),
        department_ids=list(programme.department_ids or ()),
        programme_ids=[programme.id],
        created_by_id=actor_id,
    )
    session.add(student)
    session.flush()

    duration = int(programme.duration_semesters or 8)
    student_programme = StudentProgramme(
        student_id=student.id,
        programme_id=programme.id,
        curriculum_version_id=version.id,
        campus_id=intake.campus_id,
        entry_academic_year_id=semester.academic_year_id,
        entry_route="direct",
        sponsorship=sponsorship,
        current_year_of_study=1,
        current_semester_number=1,
        credits_required=int(version.total_credit_units or 0),
        is_primary=True,
        started_on=date.today(),
        expected_completion_on=_add_semesters(semester.ends_on, duration - 1),
        # The regulator's maximum registration period — typically the nominal
        # duration plus half again. Students past it must be discontinued or
        # granted an extension, and the governance module reports on them.
        maximum_completion_on=_add_semesters(semester.ends_on, int(duration * 1.5)),
        created_by_id=actor_id,
    )
    session.add(student_programme)
    session.flush()

    enrolment = Enrolment(
        student_id=student.id,
        student_programme_id=student_programme.id,
        semester_id=semester_id,
        year_of_study=1,
        semester_number=1,
        enrolment_type="normal",
        status="enrolled",
        enrolled_at=utcnow(),
        approved_by_id=actor_id,
        created_by_id=actor_id,
    )
    session.add(enrolment)
    student.status = StudentStatus.ACTIVE
    session.flush()

    return student, student_programme, enrolment


def _add_semesters(from_date: date, semesters: int) -> date:
    """Approximate a semester as six months. Good enough for a target date.

    Only used for expected and maximum completion dates, which drive reporting
    and warnings rather than any hard gate — the hard gate is a board decision.
    """
    month = from_date.month + 6 * semesters
    year = from_date.year + (month - 1) // 12
    return date(year, ((month - 1) % 12) + 1, min(from_date.day, 28))


# ---------------------------------------------------------------------------
# Bio-data
# ---------------------------------------------------------------------------


def update_student(
    session: Session,
    *,
    student: Student,
    changes: dict[str, Any],
    actor_id: uuid.UUID,
) -> Student:
    """Apply a field-level update, auditing what actually changed.

    Which fields the caller may write was already decided by ABAC and enforced
    by `enforce_writable` — a student may change their phone number, not their
    programme. This function records the before and after of each field that
    moved, which is what makes a later "who changed my sponsor" answerable.
    """
    tracked = {k: getattr(student, k, None) for k in changes}
    for field, value in changes.items():
        if hasattr(student, field):
            setattr(student, field, value)
    student.updated_by_id = actor_id
    session.flush()

    changed = diff(tracked, {k: getattr(student, k, None) for k in changes})
    if changed:
        emit(
            "student:update",
            AuditCategory.STUDENT_RECORD,
            resource_type="student",
            resource_id=student.id,
            resource_label=f"{student.full_name} ({student.student_number})",
            summary=f"{len(changed)} field(s) updated",
            changes=changed,
            metadata={"fields": [c.field for c in changed]},
        )
    return student


def place_hold(
    session: Session,
    *,
    student: Student,
    kind: str,
    reason: str,
    actor_id: uuid.UUID,
) -> Student:
    """Add a hold that blocks registration, examination or graduation.

    Holds are a list rather than a boolean so each office clears its own. A
    finalist blocked by both the library and the bursar needs to know which
    desk to visit, and a single flag cleared by whoever gets there first is
    how an unpaid student graduates.
    """
    student.holds = [
        *student.holds,
        {
            "kind": kind,
            "reason": reason,
            "placed_by": str(actor_id),
            "placed_at": utcnow().isoformat(),
            "cleared_at": None,
        },
    ]
    emit(
        "student:place_hold",
        AuditCategory.STUDENT_RECORD,
        resource_type="student",
        resource_id=student.id,
        resource_label=student.student_number,
        summary=f"{kind} hold placed: {reason}",
        severity="notice",
    )
    return student


def clear_hold(
    session: Session, *, student: Student, kind: str, actor_id: uuid.UUID, note: str
) -> Student:
    holds = []
    cleared = 0
    for hold in student.holds:
        if hold.get("kind") == kind and not hold.get("cleared_at"):
            hold = {
                **hold,
                "cleared_at": utcnow().isoformat(),
                "cleared_by": str(actor_id),
                "clearance_note": note,
            }
            cleared += 1
        holds.append(hold)
    student.holds = holds
    if cleared:
        emit(
            "student:clear_hold",
            AuditCategory.STUDENT_RECORD,
            resource_type="student",
            resource_id=student.id,
            resource_label=student.student_number,
            summary=f"{kind} hold cleared: {note}",
            severity="notice",
        )
    return student


# ---------------------------------------------------------------------------
# Status changes
# ---------------------------------------------------------------------------


def request_status_change(
    session: Session,
    *,
    student: Student,
    kind: str,
    to_status: str,
    effective_from: date,
    effective_to: date | None,
    reason: str,
    evidence_attachment_ids: list[uuid.UUID] | None,
    actor_id: uuid.UUID,
) -> StatusChange:
    """Raise a status change for approval. Never applies it.

    A student's status decides whether they may sit examinations, whether they
    owe fees and whether they appear in the enrolment return, so it is only
    ever changed through an approved row here — see `approve_status_change`.
    """
    if to_status not in set(StudentStatus):
        raise ValidationFailed(f"'{to_status}' is not a valid student status.")
    if to_status == student.status:
        raise Conflict(f"This student is already {to_status}.")
    if kind in {"leave_of_absence", "withdrawal"} and not reason.strip():
        raise ValidationFailed("A reason is required.")

    change = StatusChange(
        student_id=student.id,
        student_programme_id=next((p.id for p in student.programmes if p.is_primary), None),
        kind=kind,
        from_status=student.status,
        to_status=to_status,
        effective_from=effective_from,
        effective_to=effective_to,
        reason=reason,
        evidence_attachment_ids=list(evidence_attachment_ids or ()),
        status="requested",
        requested_by_id=actor_id,
        requested_at=utcnow(),
        created_by_id=actor_id,
    )
    session.add(change)
    session.flush()

    emit(
        "student_status_change:create",
        AuditCategory.STUDENT_RECORD,
        resource_type="student_status_change",
        resource_id=change.id,
        resource_label=f"{student.student_number}: {kind}",
        summary=f"{kind} requested: {student.status} -> {to_status}",
        metadata={"reason": reason, "effective_from": effective_from.isoformat()},
        severity="notice",
    )
    return change


def approve_status_change(
    session: Session, *, change: StatusChange, actor_id: uuid.UUID, minute_reference: str | None
) -> StatusChange:
    """Approve and apply a status change.

    The self-approval refusal is repeated from the policy bundle for the same
    reason as in admissions: discontinuing a student is not recoverable by an
    apology, and it should not depend on one layer being configured right.
    """
    if change.status != "requested":
        raise Conflict("This request has already been decided.")
    if change.requested_by_id == actor_id:
        raise RuleViolation(
            "A status change must be approved by someone other than the person who requested it.",
            rule="separation_of_duties",
        )

    student = session.get(Student, change.student_id)
    if student is None:  # pragma: no cover
        raise NotFound()

    before = {"status": student.status}
    change.status = "approved"
    change.approved_by_id = actor_id
    change.approved_at = utcnow()
    change.minute_reference = minute_reference

    student.status = change.to_status
    if (
        change.to_status == StudentStatus.WITHDRAWN
        or change.to_status == StudentStatus.DISCONTINUED
    ):
        student.exited_on = change.effective_from
    elif change.to_status == StudentStatus.COMPLETED:
        student.completed_on = change.effective_from
    student.updated_by_id = actor_id
    session.flush()

    emit(
        "student_status_change:approve",
        AuditCategory.STUDENT_RECORD,
        resource_type="student",
        resource_id=student.id,
        resource_label=f"{student.full_name} ({student.student_number})",
        summary=f"{change.kind} approved: {before['status']} -> {student.status}",
        changes=diff(before, {"status": student.status}),
        metadata={
            "change_id": str(change.id),
            "minute_reference": minute_reference,
            "effective_from": change.effective_from.isoformat(),
            "reason": change.reason,
        },
        severity="warning",
    )
    return change


# ---------------------------------------------------------------------------
# Registration
# ---------------------------------------------------------------------------


def create_registration(
    session: Session,
    *,
    student: Student,
    semester_id: uuid.UUID,
    actor_id: uuid.UUID,
) -> Registration:
    enrolment = session.execute(
        select(Enrolment).where(
            Enrolment.student_id == student.id,
            Enrolment.semester_id == semester_id,
            Enrolment.deleted_at.is_(None),
        )
    ).scalar_one_or_none()
    if enrolment is None:
        raise RuleViolation(
            "You must enrol for the semester before registering for courses.",
            rule="enrolment_required",
        )

    existing = session.execute(
        select(Registration).where(
            Registration.enrolment_id == enrolment.id, Registration.deleted_at.is_(None)
        )
    ).scalar_one_or_none()
    if existing is not None:
        return existing

    registration = Registration(
        student_id=student.id,
        enrolment_id=enrolment.id,
        semester_id=semester_id,
        status="draft",
        created_by_id=actor_id,
    )
    session.add(registration)
    session.flush()
    return registration


def set_registration_courses(
    session: Session,
    *,
    registration: Registration,
    offering_ids: list[uuid.UUID],
    actor_id: uuid.UUID,
) -> Registration:
    """Replace the course basket, checking prerequisites and the credit cap.

    Validated as a whole. Adding courses one at a time makes "is this load
    legal" unanswerable at each step, and the credit cap is the main thing
    registration exists to enforce.
    """
    from acmis.modules.assessment.models import CourseResult
    from acmis.modules.curriculum.models import (
        CourseOffering,
        CurriculumCourse,
        CurriculumVersion,
    )

    if registration.status not in {"draft", "returned"}:
        raise Conflict("This registration has been submitted and cannot be edited.")

    student_programme = session.execute(
        select(StudentProgramme).where(
            StudentProgramme.student_id == registration.student_id,
            StudentProgramme.is_primary.is_(True),
            StudentProgramme.deleted_at.is_(None),
        )
    ).scalar_one_or_none()
    if student_programme is None:
        raise RuleViolation("This student has no active programme attachment.")
    version = session.get(CurriculumVersion, student_programme.curriculum_version_id)
    if version is None:  # pragma: no cover
        raise NotFound()

    passed_courses = set(
        session.execute(
            select(CourseResult.course_id).where(
                CourseResult.student_id == registration.student_id,
                CourseResult.outcome == "pass",
            )
        ).scalars()
    )
    attempt_counts: dict[uuid.UUID, int] = {}
    for course_id, attempts in session.execute(
        select(CourseResult.course_id, func.count())
        .where(CourseResult.student_id == registration.student_id)
        .group_by(CourseResult.course_id)
    ).all():
        attempt_counts[course_id] = int(attempts)

    for existing in list(registration.courses):
        session.delete(existing)
    session.flush()

    problems: list[dict[str, Any]] = []
    total_credits = 0
    retake_credits = 0

    for offering_id in offering_ids:
        offering = session.get(CourseOffering, offering_id)
        if offering is None or offering.deleted_at is not None:
            problems.append({"offering_id": str(offering_id), "reason": "not_offered"})
            continue
        if not offering.is_open:
            problems.append({"offering_id": str(offering_id), "reason": "registration_closed"})
            continue
        if offering.semester_id != registration.semester_id:
            problems.append({"offering_id": str(offering_id), "reason": "wrong_semester"})
            continue

        structure = session.execute(
            select(CurriculumCourse).where(
                CurriculumCourse.version_id == version.id,
                CurriculumCourse.course_id == offering.course_id,
                CurriculumCourse.deleted_at.is_(None),
            )
        ).scalar_one_or_none()

        credits = (
            structure.credit_units_override
            if structure and structure.credit_units_override
            else offering.course.credit_units
        )
        is_retake = offering.course_id in attempt_counts and (
            offering.course_id not in passed_courses
        )

        unmet = _unmet_prerequisites(
            session, course_id=offering.course_id, passed=passed_courses, version_id=version.id
        )
        if unmet:
            problems.append(
                {
                    "offering_id": str(offering_id),
                    "course_code": offering.course.code,
                    "reason": "prerequisites_not_met",
                    "missing": unmet,
                }
            )
            continue

        attempts = attempt_counts.get(offering.course_id, 0)
        max_attempts = int((version.progression_rules or {}).get("max_retakes_per_course", 3))
        if is_retake and attempts >= max_attempts:
            problems.append(
                {
                    "offering_id": str(offering_id),
                    "course_code": offering.course.code,
                    "reason": "attempt_limit_reached",
                    "attempts": attempts,
                }
            )
            continue

        session.add(
            RegistrationCourse(
                registration_id=registration.id,
                course_offering_id=offering_id,
                student_id=registration.student_id,
                credit_units=credits,
                category=structure.category if structure else "elective",
                is_retake=is_retake,
                attempt_number=attempts + 1,
                created_by_id=actor_id,
            )
        )
        total_credits += credits
        if is_retake:
            retake_credits += credits

    is_finalist = student_programme.current_year_of_study * 2 >= int(
        version.programme.duration_semesters if version.programme else 8
    )
    load_problems = validate_credit_load(
        total_credits=total_credits,
        retake_credits=retake_credits,
        min_credits=version.min_credits_per_semester,
        max_credits=version.max_credits_per_semester,
        max_credits_with_retakes=version.max_credits_with_retakes,
        is_finalist=is_finalist,
    )

    registration.total_credits = total_credits
    registration.retake_credits = retake_credits
    registration.updated_by_id = actor_id
    session.flush()

    if problems or load_problems:
        raise RuleViolation(
            "This course selection cannot be registered.",
            rule="registration_invalid",
            details={"courses": problems, "load": load_problems},
            waivable_by=["registration:override_deadline", "curriculum:waive_prerequisite"],
        )

    emit(
        "registration:update",
        AuditCategory.ENROLMENT,
        resource_type="registration",
        resource_id=registration.id,
        summary=f"{len(offering_ids)} course(s), {total_credits} credit units",
        metadata={"retake_credits": retake_credits},
    )
    return registration


def _unmet_prerequisites(
    session: Session, *, course_id: uuid.UUID, passed: set[uuid.UUID], version_id: uuid.UUID
) -> list[str]:
    """Which prerequisites are not satisfied.

    Alternative groups are OR-ed: any one member satisfies the group.
    Ungrouped rows are each mandatory. Antirequisites invert — holding the
    other course is what *fails* the check.
    """
    from acmis.modules.curriculum.models import Course, Prerequisite

    rows = (
        session.execute(
            select(Prerequisite).where(
                Prerequisite.course_id == course_id,
                Prerequisite.deleted_at.is_(None),
                (Prerequisite.version_id.is_(None)) | (Prerequisite.version_id == version_id),
            )
        )
        .scalars()
        .all()
    )

    missing: list[str] = []
    groups: dict[str, list[Prerequisite]] = {}
    for row in rows:
        if row.kind == "antirequisite":
            if row.required_course_id in passed:
                other = session.get(Course, row.required_course_id)
                missing.append(f"cannot be taken with {other.code if other else 'another course'}")
            continue
        if row.kind == "corequisite":
            continue  # satisfied by being registered alongside; checked in the basket
        if row.alternative_group:
            groups.setdefault(row.alternative_group, []).append(row)
        elif row.required_course_id not in passed:
            other = session.get(Course, row.required_course_id)
            missing.append(other.code if other else str(row.required_course_id))

    for members in groups.values():
        if not any(m.required_course_id in passed for m in members):
            codes = []
            for member in members:
                other = session.get(Course, member.required_course_id)
                codes.append(other.code if other else "?")
            missing.append(f"one of {', '.join(codes)}")

    return missing


def submit_registration(
    session: Session, *, registration: Registration, actor_id: uuid.UUID
) -> Registration:
    if registration.status not in {"draft", "returned"}:
        raise Conflict("This registration has already been submitted.")
    if not registration.courses:
        raise RuleViolation(
            "Add at least one course before submitting.", rule="no_courses_registered"
        )

    before = {"status": registration.status}
    registration.status = "submitted"
    registration.submitted_at = utcnow()
    registration.updated_by_id = actor_id
    session.flush()

    emit(
        "registration:submit",
        AuditCategory.ENROLMENT,
        resource_type="registration",
        resource_id=registration.id,
        summary=(
            f"Submitted: {len(registration.courses)} course(s), "
            f"{registration.total_credits} credit units"
        ),
        changes=diff(before, {"status": registration.status}),
        severity="notice",
    )
    return registration


def registration_context(session: Session, *, registration: Registration) -> dict[str, Any]:
    """The attributes the registration policies need beyond the row itself.

    `window_state` and `fee_cleared` are not columns — one comes from the
    semester's dates and the other from the student's ledger. Supplied to the
    decision explicitly rather than guessed by the descriptor, because an
    absent attribute can only fail a permit while a *wrong* one could grant.
    """
    from acmis.modules.finance import service as finance
    from acmis.modules.shared.models import Semester

    semester = session.get(Semester, registration.semester_id)
    today = date.today()
    window = "closed"
    if semester is not None:
        opens = semester.registration_opens_on or semester.starts_on
        closes = semester.registration_closes_on or semester.ends_on
        if semester.locked_at is not None:
            window = "locked"
        elif opens <= today <= closes:
            window = "open"
        elif today < opens:
            window = "not_yet_open"

    return {
        "window_state": window,
        "fee_cleared": finance.registration_threshold_met(
            session, student_id=registration.student_id, semester_id=registration.semester_id
        ),
    }


def ensure_clearance_checklist(
    session: Session, *, student: Student, purpose: str, offices: list[str], actor_id: uuid.UUID
) -> list[Clearance]:
    """Create the sign-off rows a leaving student needs.

    One per office, so a finalist can be told which desk is holding them up
    rather than just "not cleared".
    """
    existing = {
        (c.purpose, c.office)
        for c in session.execute(
            select(Clearance).where(
                Clearance.student_id == student.id,
                Clearance.purpose == purpose,
                Clearance.deleted_at.is_(None),
            )
        ).scalars()
    }
    created: list[Clearance] = []
    for office in offices:
        if (purpose, office) in existing:
            continue
        row = Clearance(
            student_id=student.id,
            purpose=purpose,
            office=office,
            status="pending",
            created_by_id=actor_id,
        )
        session.add(row)
        created.append(row)
    session.flush()
    return created
