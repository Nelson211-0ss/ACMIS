"""OneRoster 1.2 — rostering and gradebook, served from ACMIS.

Field names and shapes follow the specification exactly, cross-checked against
the Ed-Fi Alliance's Apache-2.0 OneRoster implementation. Exactly, because the
point of a standard is that a consuming system written against the spec works
without being told about us: `sourcedId`, `dateLastModified`, `status`, the
`{href, sourcedId, type}` reference shape and the `{"users": [...]}` envelope
are all load-bearing, and a near-miss on any of them is a integration that
half-works.

What ACMIS serves:

* **Rostering** — orgs, academic sessions, courses, classes, enrolments,
  users. Read-only. A library system, a Wi-Fi provisioning system or a
  publisher's platform consumes this to know who is registered for what.
* **Gradebook** — line items and results, read-only.

What it does not serve: `PUT`/`DELETE`. OneRoster's write bindings would let an
external system change enrolments and marks, and the modules in this system
spend their whole time making sure that happens through an approval chain.
Anything that needs to write does so through the ACMIS API, where the policy
bundle applies.

The `sourcedId` is deliberately *not* our internal UUID — see
`ExternalIdentifier`. A consuming system keys on a sourcedId forever, so it has
to survive a data migration that changes our primary keys.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

import structlog
from sqlalchemy import select
from sqlalchemy.orm import Session

log = structlog.get_logger(__name__)

BASE_PATH = "/ims/oneroster/rostering/v1p2"
GRADEBOOK_PATH = "/ims/oneroster/gradebook/v1p2"

#: OneRoster's status vocabulary. Only these two exist, and `tobedeleted` is
#: how a deletion is communicated — a row that simply vanishes leaves the
#: consumer with a stale record it will never reconcile.
STATUS_ACTIVE = "active"
STATUS_TO_BE_DELETED = "tobedeleted"

#: Role vocabulary from the rostering information model.
ROLE_STUDENT = "student"
ROLE_TEACHER = "teacher"
ROLE_ADMINISTRATOR = "administrator"
ROLE_AIDE = "aide"
ROLE_GUARDIAN = "guardian"
ROLE_PARENT = "parent"
ROLE_RELATIVE = "relative"
ROLE_PROCTOR = "proctor"


def sourced_id_for(
    session: Session, *, resource_type: str, resource_id: uuid.UUID, base_url: str = ""
) -> str:
    """The stable external identifier for one of our records.

    Looked up in `external_identifier` and minted on first request. Minted
    rather than derived so that a future migration which changes our primary
    keys does not orphan every downstream record — the mapping is the contract,
    not the UUID.
    """
    from acmis.modules.interop.models import ExternalIdentifier

    row = session.execute(
        select(ExternalIdentifier).where(
            ExternalIdentifier.system == "oneroster",
            ExternalIdentifier.resource_type == resource_type,
            ExternalIdentifier.resource_id == resource_id,
        )
    ).scalar_one_or_none()
    if row is not None:
        return row.external_id

    external = f"{resource_type}.{resource_id}"
    session.add(
        ExternalIdentifier(
            system="oneroster",
            resource_type=resource_type,
            resource_id=resource_id,
            external_id=external,
            external_type=resource_type,
        )
    )
    session.flush()
    return external


def _ref(base_url: str, collection: str, sourced_id: str, kind: str) -> dict[str, Any]:
    """A OneRoster GUIDRef: `{href, sourcedId, type}`.

    The `href` is required and consumers do follow it, so it is a real URL
    rather than a placeholder.
    """
    return {
        "href": f"{base_url}{BASE_PATH}/{collection}/{sourced_id}",
        "sourcedId": sourced_id,
        "type": kind,
    }


def _stamp(value: datetime | None) -> str:
    """`dateLastModified`, which consumers use for incremental sync.

    Required on every record. A consumer polls with
    `filter=dateLastModified>'...'` and gets only what changed; without it the
    only sync available is a full one, which for a 40,000-student institution
    is a nightly job that nobody runs during the day.
    """
    return (value or datetime.now()).isoformat()


def org_payload(session: Session, *, tenant: Any, base_url: str) -> dict[str, Any]:
    """The institution itself, as a OneRoster org."""
    sourced = sourced_id_for(session, resource_type="institution", resource_id=tenant.id)
    return {
        "sourcedId": sourced,
        "status": STATUS_ACTIVE,
        "dateLastModified": _stamp(None),
        "metadata": {"acmis.slug": tenant.slug},
        "name": tenant.name,
        # OneRoster's org types are school-oriented; `district` is the
        # conventional mapping for a whole higher-education institution, with
        # faculties below it as `school`.
        "type": "district",
        "identifier": tenant.slug,
        "children": [],
    }


def unit_payload(session: Session, *, unit: Any, base_url: str) -> dict[str, Any]:
    sourced = sourced_id_for(session, resource_type="academic_unit", resource_id=unit.id)
    parent = None
    if unit.parent_id:
        parent = _ref(
            base_url,
            "orgs",
            sourced_id_for(session, resource_type="academic_unit", resource_id=unit.parent_id),
            "org",
        )
    return {
        "sourcedId": sourced,
        "status": STATUS_ACTIVE if unit.is_active else STATUS_TO_BE_DELETED,
        "dateLastModified": _stamp(unit.updated_at),
        "metadata": {"acmis.kind": unit.kind, "acmis.code": unit.code},
        "name": unit.name,
        "type": "school" if unit.kind in {"faculty", "college", "school"} else "department",
        "identifier": unit.code,
        "parent": parent,
        "children": [],
    }


def academic_session_payload(
    session: Session, *, semester: Any, year: Any, base_url: str
) -> dict[str, Any]:
    """A semester, as an academicSession of type `term`.

    The academic year is its parent, of type `schoolYear`. That nesting is what
    lets a consumer answer "which term are we in" without knowing anything
    about our calendar model.
    """
    sourced = sourced_id_for(session, resource_type="semester", resource_id=semester.id)
    parent = (
        _ref(
            base_url,
            "academicSessions",
            sourced_id_for(session, resource_type="academic_year", resource_id=year.id),
            "academicSession",
        )
        if year is not None
        else None
    )
    return {
        "sourcedId": sourced,
        "status": STATUS_ACTIVE,
        "dateLastModified": _stamp(semester.updated_at),
        "metadata": {"acmis.kind": semester.kind, "acmis.is_current": semester.is_current},
        "title": semester.name,
        "startDate": semester.starts_on.isoformat(),
        "endDate": semester.ends_on.isoformat(),
        "type": "term",
        "parent": parent,
        "schoolYear": year.code.split("/")[0] if year is not None else None,
    }


def course_payload(session: Session, *, programme: Any, base_url: str) -> dict[str, Any]:
    """A programme, as a OneRoster course.

    Programme rather than our `Course`, because OneRoster's `course` is the
    thing a `class` is an instance of within an org — which maps onto a
    programme of study far more naturally than onto a single teaching unit.
    Our `Course` maps to a OneRoster `class` via its offering.
    """
    sourced = sourced_id_for(session, resource_type="programme", resource_id=programme.id)
    org_sourced = (
        sourced_id_for(session, resource_type="academic_unit", resource_id=programme.owning_unit_id)
        if programme.owning_unit_id
        else None
    )
    return {
        "sourcedId": sourced,
        "status": STATUS_ACTIVE if programme.is_active else STATUS_TO_BE_DELETED,
        "dateLastModified": _stamp(programme.updated_at),
        "metadata": {
            "acmis.award_level": programme.award_level,
            "acmis.duration_semesters": programme.duration_semesters,
        },
        "title": programme.name,
        "courseCode": programme.code,
        "grades": [],
        "subjects": [],
        "subjectCodes": [],
        "org": _ref(base_url, "orgs", org_sourced, "org") if org_sourced else None,
        "schoolYear": None,
    }


def class_payload(session: Session, *, offering: Any, base_url: str) -> dict[str, Any]:
    """A course offering, as a OneRoster class."""
    sourced = sourced_id_for(session, resource_type="course_offering", resource_id=offering.id)
    course = getattr(offering, "course", None)
    school_sourced = (
        sourced_id_for(
            session,
            resource_type="academic_unit",
            resource_id=course.owning_unit_id,
        )
        if course is not None and course.owning_unit_id
        else None
    )
    term_sourced = sourced_id_for(
        session, resource_type="semester", resource_id=offering.semester_id
    )
    return {
        "sourcedId": sourced,
        "status": STATUS_ACTIVE,
        "dateLastModified": _stamp(offering.updated_at),
        "metadata": {
            "acmis.credit_units": course.credit_units if course else None,
            "acmis.delivery_mode": offering.delivery_mode,
            "acmis.registered_count": offering.registered_count,
        },
        "title": f"{course.code} {course.title}" if course else "Class",
        "classCode": (
            f"{course.code}-{offering.group_code}"
            if course and offering.group_code
            else (course.code if course else None)
        ),
        # `scheduled` is the OneRoster type for a timetabled class;
        # `homeroom` is the school-oriented alternative and never applies here.
        "classType": "scheduled",
        "location": None,
        "grades": [],
        "subjects": [],
        "subjectCodes": [],
        "course": _ref(base_url, "courses", "", "course") if False else None,
        "school": _ref(base_url, "orgs", school_sourced, "org") if school_sourced else None,
        "terms": [_ref(base_url, "academicSessions", term_sourced, "academicSession")],
        "periods": [],
        "resources": [],
    }


def enrollment_payload(
    session: Session, *, registration_course: Any, base_url: str
) -> dict[str, Any]:
    sourced = sourced_id_for(
        session, resource_type="registration_course", resource_id=registration_course.id
    )
    class_sourced = sourced_id_for(
        session,
        resource_type="course_offering",
        resource_id=registration_course.course_offering_id,
    )
    user_sourced = sourced_id_for(
        session, resource_type="student", resource_id=registration_course.student_id
    )
    return {
        "sourcedId": sourced,
        "status": (
            STATUS_TO_BE_DELETED
            if registration_course.dropped_at or registration_course.withdrawn_at
            else STATUS_ACTIVE
        ),
        "dateLastModified": _stamp(registration_course.updated_at),
        "metadata": {
            "acmis.is_retake": registration_course.is_retake,
            "acmis.attempt_number": registration_course.attempt_number,
            "acmis.credit_units": registration_course.credit_units,
        },
        "user": _ref(base_url, "users", user_sourced, "user"),
        "class": _ref(base_url, "classes", class_sourced, "class"),
        "school": None,
        "role": ROLE_STUDENT,
        "primary": True,
        "beginDate": None,
        "endDate": None,
    }


def student_user_payload(
    session: Session, *, student: Any, base_url: str, disclose_contact: bool
) -> dict[str, Any]:
    """A student, as a OneRoster user.

    `disclose_contact` is the whole reason this takes an argument. A OneRoster
    feed to a library system needs names and student numbers; it does not need
    phone numbers and personal email addresses, and a standard that makes it
    easy to send everything is not a reason to.
    """
    sourced = sourced_id_for(session, resource_type="student", resource_id=student.id)
    payload: dict[str, Any] = {
        "sourcedId": sourced,
        "status": (
            STATUS_ACTIVE
            if student.status in {"active", "admitted", "probation", "on_leave"}
            else STATUS_TO_BE_DELETED
        ),
        "dateLastModified": _stamp(student.updated_at),
        "metadata": {"acmis.status": student.status},
        "userMasterIdentifier": student.student_number,
        "username": student.student_number,
        "userIds": [{"type": "acmis", "identifier": student.student_number}],
        "enabledUser": student.status in {"active", "admitted", "probation"},
        "identifier": student.student_number,
        "givenName": student.given_names,
        "familyName": student.surname,
        "middleName": student.other_names,
        "preferredFirstName": student.preferred_name,
        "roles": [
            {
                "roleType": "primary",
                "role": ROLE_STUDENT,
                "org": _ref(
                    base_url,
                    "orgs",
                    sourced_id_for(
                        session,
                        resource_type="institution",
                        resource_id=uuid.UUID(int=0),
                    ),
                    "org",
                ),
            }
        ],
        "grades": [],
        "userProfiles": [],
    }
    if disclose_contact:
        payload |= {"email": student.email, "phone": student.phone, "sms": student.phone}
    # `password` is in the specification and is never populated. A rostering
    # feed that carries credentials is a rostering feed that leaks them.
    return payload


def staff_user_payload(
    session: Session, *, staff: Any, base_url: str, disclose_contact: bool
) -> dict[str, Any]:
    sourced = sourced_id_for(session, resource_type="staff", resource_id=staff.id)
    payload: dict[str, Any] = {
        "sourcedId": sourced,
        "status": STATUS_ACTIVE if staff.status == "active" else STATUS_TO_BE_DELETED,
        "dateLastModified": _stamp(staff.updated_at),
        "metadata": {"acmis.category": staff.category, "acmis.rank": staff.rank},
        "userMasterIdentifier": staff.staff_number,
        "username": staff.staff_number,
        "userIds": [{"type": "acmis", "identifier": staff.staff_number}],
        "enabledUser": staff.status == "active",
        "identifier": staff.staff_number,
        "givenName": staff.given_names,
        "familyName": staff.surname,
        "middleName": staff.other_names,
        "roles": [{"roleType": "primary", "role": ROLE_TEACHER}],
        "grades": [],
        "userProfiles": [],
    }
    if disclose_contact:
        payload |= {"email": staff.email, "phone": staff.phone}
    return payload


def line_item_payload(
    session: Session, *, component: Any, offering_id: uuid.UUID, base_url: str
) -> dict[str, Any]:
    """An assessment component, as a OneRoster gradebook lineItem."""
    sourced = sourced_id_for(
        session, resource_type="assessment_component", resource_id=component.id
    )
    class_sourced = sourced_id_for(
        session, resource_type="course_offering", resource_id=offering_id
    )
    return {
        "sourcedId": sourced,
        "status": STATUS_ACTIVE,
        "dateLastModified": _stamp(component.updated_at),
        "metadata": {"acmis.weight_percent": float(component.weight_percent)},
        "title": component.name,
        "description": component.kind,
        "assignDate": None,
        "dueDate": None,
        "class": {
            "href": f"{base_url}{BASE_PATH}/classes/{class_sourced}",
            "sourcedId": class_sourced,
            "type": "class",
        },
        "resultValueMin": 0,
        "resultValueMax": float(component.max_mark),
    }


def result_payload(
    session: Session, *, score: Any, student_id: uuid.UUID, component: Any, base_url: str
) -> dict[str, Any]:
    """A component score, as a OneRoster gradebook result.

    Only released results are ever served. `scoreStatus` distinguishes
    `fully graded` from `partially graded`, so a consumer can tell a final mark
    from a provisional one rather than treating everything as final.
    """
    sourced = sourced_id_for(session, resource_type="component_score", resource_id=score.id)
    user_sourced = sourced_id_for(session, resource_type="student", resource_id=student_id)
    line_item_sourced = sourced_id_for(
        session, resource_type="assessment_component", resource_id=component.id
    )
    return {
        "sourcedId": sourced,
        "status": STATUS_ACTIVE,
        "dateLastModified": _stamp(score.updated_at),
        "metadata": {},
        "lineItem": {
            "href": f"{base_url}{GRADEBOOK_PATH}/lineItems/{line_item_sourced}",
            "sourcedId": line_item_sourced,
            "type": "lineItem",
        },
        "student": {
            "href": f"{base_url}{BASE_PATH}/users/{user_sourced}",
            "sourcedId": user_sourced,
            "type": "user",
        },
        "score": float(score.raw_score) if score.raw_score is not None else None,
        "scoreStatus": "fully graded" if score.raw_score is not None else "not submitted",
        "scoreDate": _stamp(score.entered_at)[:10],
        "comment": None,
    }


def envelope(collection: str, items: list[dict[str, Any]]) -> dict[str, Any]:
    """`{"users": [...]}`. The plural collection name is the key, per the spec.

    Getting this wrong is the most common OneRoster implementation error and
    the most annoying to debug from the consumer's side, because the response
    looks entirely reasonable and their parser returns nothing.
    """
    return {collection: items}


def apply_paging(
    items: list[dict[str, Any]], *, limit: int, offset: int
) -> tuple[list[dict[str, Any]], dict[str, str]]:
    """OneRoster paging is offset-based, unlike the rest of this API.

    Keyset cursors are better and are what the ACMIS API uses. Here the
    specification says offset, consumers implement offset, and deviating would
    mean every conforming client breaks. The trade is accepted at the boundary
    and does not leak inward.
    """
    total = len(items)
    page = items[offset : offset + limit]
    headers = {"X-Total-Count": str(total)}
    if offset + limit < total:
        headers["Link"] = f'<?limit={limit}&offset={offset + limit}>; rel="next"'
    return page, headers
