"""Every authorizable resource's policy attributes, in one file.

One file rather than one per module, deliberately. This is the contract
between the domain and the policy bundle: a policy that reads
`resource.department_ids` only works if the descriptor publishes it, and the
mistake that produces — a rule that looks right and never matches — is
invisible unless the two can be compared side by side. `tests/test_policies.py`
asserts that every attribute the bundle reads is published by some descriptor
here, which is the check that makes the pairing enforceable rather than
aspirational.

Importing this module registers all of them. `acmis.main` imports it at
startup, before the first request, so a missing descriptor is a boot failure
and not a 500 on the endpoint nobody exercised in staging.
"""

from __future__ import annotations

from typing import Any

from acmis.core.abac import resources
from acmis.core.models import utcnow
from acmis.modules.admissions import models as adm
from acmis.modules.assessment import models as asmt
from acmis.modules.curriculum import models as curr
from acmis.modules.developers import models as dev
from acmis.modules.elections import models as elect
from acmis.modules.finance import models as fin
from acmis.modules.governance import models as gov
from acmis.modules.identity import models as ident
from acmis.modules.interop import models as interop
from acmis.modules.learning import models as learn
from acmis.modules.library import models as lib
from acmis.modules.people import models as ppl
from acmis.modules.quality import models as qa
from acmis.modules.shared import models as shared
from acmis.modules.students import models as stu

# ---------------------------------------------------------------------------
# Identity
# ---------------------------------------------------------------------------


@resources.register(
    "user_account",
    attributes={"id", "user_id", "kind", "status", "staff_id", "student_id", "applicant_id"},
    protected_fields={"password_hash", "mfa_secret", "mfa_recovery_hashes"},
    label=lambda a: f"{a.display_name} <{a.email}>",
)
def _user_account(a: ident.UserAccount) -> dict[str, Any]:
    return {
        "id": a.id,
        # Aliased as `user_id` too: `identity.separation-of-duties` compares
        # `resource.user_id == subject.id`, and it reads better than `id` when
        # the resource under discussion is a person's account.
        "user_id": a.id,
        "kind": a.kind,
        "status": a.status,
        "staff_id": a.staff_id,
        "student_id": a.student_id,
        "applicant_id": a.applicant_id,
    }


@resources.register(
    "role_assignment",
    attributes={"id", "user_id", "role_code", "scope_type", "scope_id", "requested_by_id"},
    label=lambda r: f"{r.role.code if r.role else 'role'} assignment",
)
def _role_assignment(r: ident.RoleAssignment) -> dict[str, Any]:
    return {
        "id": r.id,
        "user_id": r.account_id,
        "role_code": r.role.code if r.role else None,
        "scope_type": r.scope_type,
        "scope_id": r.scope_id,
        "requested_by_id": r.requested_by_id,
    }


@resources.register("role", attributes={"id", "code", "is_system"})
def _role(r: ident.Role) -> dict[str, Any]:
    return {"id": r.id, "code": r.code, "is_system": r.is_system}


# ---------------------------------------------------------------------------
# Admissions
# ---------------------------------------------------------------------------


@resources.register(
    "application",
    attributes={
        "id",
        "applicant_id",
        "status",
        "scheme_id",
        "faculty_ids",
        "is_late",
        "fee_settled",
        "final_score",
        "programme_intake_ids",
    },
    protected_fields={"disability_detail", "refugee_status", "national_id"},
    label=lambda a: a.number,
)
def _application(a: adm.Application) -> dict[str, Any]:
    return {
        "id": a.id,
        "applicant_id": a.applicant_id,
        "status": a.status,
        "scheme_id": a.scheme_id,
        "faculty_ids": a.faculty_ids,
        "is_late": a.is_late,
        "fee_settled": a.fee_settled_at is not None,
        "final_score": float(a.final_score) if a.final_score is not None else None,
        "programme_intake_ids": [c.programme_intake_id for c in (a.choices or ())],
    }


@resources.register(
    "applicant",
    attributes={"id", "applicant_id", "student_id"},
    protected_fields={"disability_detail", "refugee_status", "national_id"},
    label=lambda a: f"{a.full_name} ({a.reference})",
)
def _applicant(a: adm.Applicant) -> dict[str, Any]:
    return {"id": a.id, "applicant_id": a.id, "student_id": a.student_id}


@resources.register(
    "application_document",
    attributes={"id", "applicant_id", "application_id", "status", "purpose"},
)
def _application_document(d: Any) -> dict[str, Any]:
    return {
        "id": getattr(d, "id", None),
        "applicant_id": getattr(d, "owner_id", None),
        "application_id": getattr(d, "owner_id", None),
        "status": "verified" if getattr(d, "is_verified", False) else "unverified",
        "purpose": getattr(d, "purpose", None),
    }


@resources.register(
    "application_choice",
    attributes={"id", "application_id", "applicant_id", "status", "rank", "is_eligible"},
)
def _application_choice(c: adm.ApplicationChoice) -> dict[str, Any]:
    return {
        "id": c.id,
        "application_id": c.application_id,
        "applicant_id": c.application.applicant_id if c.application else None,
        "status": c.application.status if c.application else None,
        "rank": c.rank,
        "is_eligible": c.is_eligible,
    }


@resources.register(
    "admission_scheme",
    attributes={"id", "status", "entry_scheme", "study_level"},
    label=lambda s: f"{s.code} — {s.name}",
)
def _admission_scheme(s: adm.AdmissionScheme) -> dict[str, Any]:
    return {
        "id": s.id,
        "status": s.status,
        "entry_scheme": s.entry_scheme,
        "study_level": s.study_level,
    }


@resources.register(
    "programme_intake",
    attributes={
        "id",
        "programme_id",
        "faculty_ids",
        "approved_intake",
        "offers_issued",
        "enrolled_count",
        "status",
    },
)
def _programme_intake(i: adm.ProgrammeIntake) -> dict[str, Any]:
    return {
        "id": i.id,
        "programme_id": i.programme_id,
        "faculty_ids": [],
        "approved_intake": i.approved_intake,
        "offers_issued": i.offers_issued,
        "enrolled_count": i.enrolled_count,
        "status": i.scheme.status if i.scheme else None,
    }


@resources.register(
    "selection_list",
    attributes={"id", "status", "scheme_id", "requested_by_id", "prepared_by_id"},
    label=lambda s: s.name,
)
def _selection_list(s: adm.SelectionList) -> dict[str, Any]:
    return {
        "id": s.id,
        "status": s.status,
        "scheme_id": s.scheme_id,
        # Aliased: `identity.separation-of-duties/no-self-approval` speaks
        # about whoever raised a thing, whatever the domain calls them.
        "requested_by_id": s.prepared_by_id,
        "prepared_by_id": s.prepared_by_id,
    }


@resources.register(
    "offer",
    attributes={
        "id",
        "application_id",
        "applicant_id",
        "status",
        "approved_intake",
        "offers_issued",
        "programme_intake_id",
    },
    label=lambda o: o.reference,
)
def _offer(o: adm.Offer) -> dict[str, Any]:
    intake = getattr(o, "programme_intake", None)
    return {
        "id": o.id,
        "application_id": o.application_id,
        "applicant_id": o.application.applicant_id if o.application else None,
        "status": o.status,
        "programme_intake_id": o.programme_intake_id,
        "approved_intake": getattr(intake, "approved_intake", None),
        "offers_issued": getattr(intake, "offers_issued", None),
    }


# ---------------------------------------------------------------------------
# Students
# ---------------------------------------------------------------------------


@resources.register(
    "student",
    attributes={
        "id",
        "student_id",
        "status",
        "faculty_ids",
        "department_ids",
        "programme_ids",
        "has_holds",
        "outstanding_balance_minor",
    },
    protected_fields={
        "national_id",
        "bank_account_number",
        "disability_detail",
        "medical_notes",
        "medical_conditions",
        "biometric_reference",
    },
    label=lambda s: f"{s.full_name} ({s.student_number})",
)
def _student(s: stu.Student) -> dict[str, Any]:
    return {
        "id": s.id,
        "student_id": s.id,
        "status": s.status,
        "faculty_ids": s.faculty_ids,
        "department_ids": s.department_ids,
        "programme_ids": s.programme_ids,
        "has_holds": bool(s.active_holds),
    }


@resources.register(
    "enrolment",
    attributes={"id", "student_id", "semester_id", "status", "faculty_ids", "department_ids"},
)
def _enrolment(e: stu.Enrolment) -> dict[str, Any]:
    return {
        "id": e.id,
        "student_id": e.student_id,
        "semester_id": e.semester_id,
        "status": e.status,
        "faculty_ids": [],
        "department_ids": [],
    }


@resources.register(
    "registration",
    attributes={
        "id",
        "student_id",
        "semester_id",
        "status",
        "window_state",
        "fee_cleared",
        "total_credits",
        "retake_credits",
        "faculty_ids",
        "department_ids",
    },
)
def _registration(r: stu.Registration) -> dict[str, Any]:
    return {
        "id": r.id,
        "student_id": r.student_id,
        "semester_id": r.semester_id,
        "status": r.status,
        # Supplied by the service layer, which knows the semester's dates and
        # the student's ledger. Left absent here rather than guessed: an
        # unpopulated attribute can only fail a permit, never grant one.
        "total_credits": r.total_credits,
        "retake_credits": r.retake_credits,
    }


@resources.register(
    "student_status_change",
    attributes={"id", "student_id", "kind", "status", "requested_by_id", "to_status"},
)
def _status_change(c: stu.StatusChange) -> dict[str, Any]:
    return {
        "id": c.id,
        "student_id": c.student_id,
        "kind": c.kind,
        "status": c.status,
        "requested_by_id": c.requested_by_id,
        "to_status": c.to_status,
    }


@resources.register(
    "programme_transfer",
    attributes={"id", "student_id", "status", "requested_by_id"},
)
def _programme_transfer(t: stu.ProgrammeTransfer) -> dict[str, Any]:
    return {
        "id": t.id,
        "student_id": t.student_id,
        "status": t.status,
        "requested_by_id": t.created_by_id,
    }


@resources.register(
    "leave_of_absence",
    attributes={"id", "student_id", "status", "requested_by_id"},
)
def _leave_of_absence(c: stu.StatusChange) -> dict[str, Any]:
    return _status_change(c)


@resources.register("withdrawal", attributes={"id", "student_id", "status", "requested_by_id"})
def _withdrawal(c: stu.StatusChange) -> dict[str, Any]:
    return _status_change(c)


@resources.register(
    "disciplinary_case",
    attributes={"id", "student_id", "category", "status", "restricted_from_staff_ids"},
    protected_fields={"allegation", "finding"},
    label=lambda c: c.case_number,
)
def _disciplinary_case(c: stu.DisciplinaryCase) -> dict[str, Any]:
    return {
        "id": c.id,
        "student_id": c.student_id,
        "category": c.category,
        "status": c.status,
        "restricted_from_staff_ids": c.restricted_from_staff_ids,
    }


@resources.register("clearance", attributes={"id", "student_id", "purpose", "office", "status"})
def _clearance(c: stu.Clearance) -> dict[str, Any]:
    return {
        "id": c.id,
        "student_id": c.student_id,
        "purpose": c.purpose,
        "office": c.office,
        "status": c.status,
    }


# ---------------------------------------------------------------------------
# Curriculum
# ---------------------------------------------------------------------------


@resources.register(
    "programme",
    attributes={"id", "status", "faculty_ids", "department_ids", "is_active", "study_level"},
    label=lambda p: f"{p.code} — {p.name}",
)
def _programme(p: curr.Programme) -> dict[str, Any]:
    return {
        "id": p.id,
        "status": p.status,
        "faculty_ids": p.faculty_ids,
        "department_ids": p.department_ids,
        "is_active": p.is_active,
        "study_level": p.study_level,
    }


@resources.register(
    "curriculum_version",
    attributes={"id", "programme_id", "status", "faculty_ids", "department_ids"},
    label=lambda v: f"{v.programme.code if v.programme else ''} {v.version_label}",
)
def _curriculum_version(v: curr.CurriculumVersion) -> dict[str, Any]:
    return {
        "id": v.id,
        "programme_id": v.programme_id,
        "status": v.status,
        "faculty_ids": v.programme.faculty_ids if v.programme else [],
        "department_ids": v.programme.department_ids if v.programme else [],
    }


@resources.register(
    "course",
    attributes={
        "id",
        "status",
        "faculty_ids",
        "department_ids",
        "is_active",
        "active_registrations",
        "credit_units",
    },
    label=lambda c: f"{c.code} — {c.title}",
)
def _course(c: curr.Course) -> dict[str, Any]:
    return {
        "id": c.id,
        "status": c.status,
        "faculty_ids": c.faculty_ids,
        "department_ids": c.department_ids,
        "is_active": c.is_active,
        "credit_units": c.credit_units,
        # Counted by the service before a retire decision; absent otherwise.
    }


@resources.register(
    "course_offering",
    attributes={
        "id",
        "course_offering_id",
        "course_id",
        "semester_id",
        "faculty_ids",
        "department_ids",
        "is_open",
        "status",
    },
)
def _course_offering(o: curr.CourseOffering) -> dict[str, Any]:
    return {
        "id": o.id,
        "course_offering_id": o.id,
        "course_id": o.course_id,
        "semester_id": o.semester_id,
        "faculty_ids": o.faculty_ids,
        "department_ids": o.department_ids,
        "is_open": o.is_open,
        "status": "approved",
    }


@resources.register(
    "prerequisite", attributes={"id", "course_id", "status", "department_ids", "faculty_ids"}
)
def _prerequisite(p: curr.Prerequisite) -> dict[str, Any]:
    return {"id": p.id, "course_id": p.course_id, "status": "approved"}


@resources.register(
    "assessment_scheme",
    attributes={"id", "course_id", "status", "department_ids", "faculty_ids"},
)
def _assessment_scheme(s: curr.AssessmentScheme) -> dict[str, Any]:
    return {"id": s.id, "course_id": s.course_id, "status": s.status}


@resources.register(
    "timetable_slot",
    attributes={"id", "offering_id", "room_id", "staff_id", "faculty_ids", "department_ids"},
)
def _timetable_slot(t: curr.TimetableSlot) -> dict[str, Any]:
    return {"id": t.id, "offering_id": t.offering_id, "room_id": t.room_id, "staff_id": t.staff_id}


@resources.register("room", attributes={"id", "is_bookable", "capacity"})
def _room(r: Any) -> dict[str, Any]:
    return {"id": r.id, "is_bookable": r.is_bookable, "capacity": r.capacity}


# ---------------------------------------------------------------------------
# Finance
# ---------------------------------------------------------------------------


@resources.register(
    "invoice",
    attributes={
        "id",
        "student_id",
        "applicant_id",
        "status",
        "period_status",
        "period_code",
        "balance_minor",
        "raised_by_id",
    },
    label=lambda i: i.number,
)
def _invoice(i: fin.Invoice) -> dict[str, Any]:
    return {
        "id": i.id,
        "student_id": i.student_id,
        "applicant_id": i.applicant_id,
        "status": i.status,
        "period_code": i.period_code,
        "balance_minor": i.balance_minor,
        "raised_by_id": i.created_by_id,
    }


@resources.register(
    "payment",
    attributes={
        "id",
        "student_id",
        "status",
        "amount_minor",
        "raised_by_id",
        "period_status",
        "period_code",
    },
    label=lambda p: p.reference,
)
def _payment(p: fin.Payment) -> dict[str, Any]:
    return {
        "id": p.id,
        "student_id": p.student_id,
        "status": p.status,
        "amount_minor": p.amount_minor,
        "raised_by_id": p.raised_by_id or p.received_by_id,
        "period_code": p.period_code,
    }


@resources.register(
    "fee_structure", attributes={"id", "status", "programme_id", "academic_year_id"}
)
def _fee_structure(f: fin.FeeStructure) -> dict[str, Any]:
    return {
        "id": f.id,
        "status": f.status,
        "programme_id": f.programme_id,
        "academic_year_id": f.academic_year_id,
    }


@resources.register("student_ledger", attributes={"id", "student_id", "balance_minor"})
def _student_ledger(a: fin.StudentAccount) -> dict[str, Any]:
    return {"id": a.id, "student_id": a.student_id, "balance_minor": a.balance_minor}


@resources.register(
    "sponsorship",
    attributes={"id", "student_id", "status", "sponsor_kind"},
    label=lambda s: f"{s.sponsor_name} ({s.reference})",
)
def _sponsorship(s: fin.Sponsorship) -> dict[str, Any]:
    return {
        "id": s.id,
        "student_id": s.student_id,
        "status": s.status,
        "sponsor_kind": s.sponsor_kind,
    }


@resources.register(
    "waiver",
    attributes={"id", "student_id", "status", "amount_minor", "raised_by_id", "category"},
    label=lambda w: w.reference,
)
def _waiver(w: fin.Waiver) -> dict[str, Any]:
    return {
        "id": w.id,
        "student_id": w.student_id,
        "status": w.status,
        "amount_minor": w.amount_minor,
        "raised_by_id": w.raised_by_id,
        "category": w.category,
    }


@resources.register(
    "refund",
    attributes={"id", "student_id", "status", "amount_minor", "raised_by_id"},
    label=lambda r: r.reference,
)
def _refund(r: fin.Refund) -> dict[str, Any]:
    return {
        "id": r.id,
        "student_id": r.student_id,
        "status": r.status,
        "amount_minor": r.amount_minor,
        "raised_by_id": r.raised_by_id,
    }


@resources.register(
    "journal_entry",
    attributes={"id", "student_id", "period_code", "period_status", "raised_by_id"},
)
def _journal_entry(e: fin.LedgerEntry) -> dict[str, Any]:
    return {
        "id": e.id,
        "student_id": e.student_id,
        "period_code": e.period_code,
        "raised_by_id": e.posted_by_id,
    }


@resources.register(
    "bank_reconciliation",
    attributes={"id", "status", "raised_by_id", "period_code", "period_status"},
)
def _bank_reconciliation(b: fin.BankReconciliation) -> dict[str, Any]:
    return {"id": b.id, "status": b.status, "raised_by_id": b.reconciled_by_id}


# ---------------------------------------------------------------------------
# People
# ---------------------------------------------------------------------------


@resources.register(
    "staff",
    attributes={"id", "staff_id", "status", "faculty_ids", "department_ids", "category"},
    protected_fields={
        "salary_scale",
        "national_id",
        "bank_account_number",
        "medical_notes",
    },
    label=lambda s: f"{s.full_name} ({s.staff_number})",
)
def _staff(s: ppl.Staff) -> dict[str, Any]:
    return {
        "id": s.id,
        "staff_id": s.id,
        "status": s.status,
        "faculty_ids": s.faculty_ids,
        "department_ids": s.department_ids,
        "category": s.category,
    }


@resources.register(
    "appointment",
    attributes={"id", "staff_id", "status", "faculty_ids", "department_ids", "requested_by_id"},
    protected_fields={"gross_salary_minor", "salary_scale"},
)
def _appointment(a: ppl.Appointment) -> dict[str, Any]:
    return {
        "id": a.id,
        "staff_id": a.staff_id,
        "status": a.status,
        "requested_by_id": a.proposed_by_id,
    }


@resources.register(
    "leave_request",
    attributes={"id", "staff_id", "status", "leave_type", "faculty_ids", "department_ids"},
)
def _leave_request(r: ppl.LeaveRequest) -> dict[str, Any]:
    staff = getattr(r, "staff", None)
    return {
        "id": r.id,
        "staff_id": r.staff_id,
        "status": r.status,
        "leave_type": r.leave_type,
        "faculty_ids": getattr(staff, "faculty_ids", []) or [],
        "department_ids": getattr(staff, "department_ids", []) or [],
    }


@resources.register(
    "workload",
    attributes={"id", "staff_id", "status", "semester_id", "faculty_ids", "department_ids"},
)
def _workload(w: ppl.Workload) -> dict[str, Any]:
    return {"id": w.id, "staff_id": w.staff_id, "status": w.status, "semester_id": w.semester_id}


@resources.register(
    "contract",
    attributes={"id", "staff_id", "status", "requested_by_id"},
    protected_fields={"gross_salary_minor"},
)
def _contract(a: ppl.Appointment) -> dict[str, Any]:
    return _appointment(a)


@resources.register("establishment_post", attributes={"id", "unit_id", "status", "requested_by_id"})
def _establishment_post(p: ppl.EstablishmentPost) -> dict[str, Any]:
    return {"id": p.id, "unit_id": p.unit_id, "status": p.status}


@resources.register("qualification", attributes={"id", "staff_id", "verified"})
def _staff_qualification(q: ppl.StaffQualification) -> dict[str, Any]:
    return {"id": q.id, "staff_id": q.staff_id, "verified": q.verified_at is not None}


@resources.register("payslip", attributes={"id", "staff_id"})
def _payslip(payload: Any) -> dict[str, Any]:
    return dict(payload)


@resources.register("promotion", attributes={"id", "staff_id", "status", "requested_by_id"})
def _promotion(d: ppl.StaffDevelopment) -> dict[str, Any]:
    return {"id": d.id, "staff_id": d.staff_id, "status": d.status}


# ---------------------------------------------------------------------------
# Assessment
# ---------------------------------------------------------------------------


@resources.register(
    "mark_sheet",
    attributes={
        "id",
        "course_offering_id",
        "semester_id",
        "status",
        "department_ids",
        "faculty_ids",
        "entered_by_ids",
        "conflicted_staff_ids",
        "is_locked",
        "released",
        "withheld",
        "appeal_case_id",
        "appeal_status",
    },
    label=lambda m: (
        f"{m.course_offering.course.code} mark sheet"
        if m.course_offering and m.course_offering.course
        else "mark sheet"
    ),
)
def _mark_sheet(m: asmt.MarkSheet) -> dict[str, Any]:
    return {
        "id": m.id,
        "course_offering_id": m.course_offering_id,
        "semester_id": m.semester_id,
        "status": m.status,
        "department_ids": m.department_ids,
        "faculty_ids": m.faculty_ids,
        "entered_by_ids": m.entered_by_ids,
        "conflicted_staff_ids": m.conflicted_staff_ids,
        "is_locked": not m.is_editable,
        "released": m.published_at is not None,
    }


@resources.register(
    "course_result",
    attributes={
        "id",
        "student_id",
        "course_offering_id",
        "course_id",
        #: Supplied by the release endpoints, which decide over a semester
        #: rather than over one result row.
        "semester_id",
        "status",
        "released",
        "withheld",
        "appeal_case_id",
        "appeal_status",
        "department_ids",
        "faculty_ids",
        "entered_by_ids",
        "conflicted_staff_ids",
        "outcome",
    },
    label=lambda r: f"{r.course_code} result",
)
def _course_result(r: asmt.CourseResult) -> dict[str, Any]:
    sheet = getattr(r, "mark_sheet", None)
    return {
        "id": r.id,
        "student_id": r.student_id,
        "course_offering_id": r.course_offering_id,
        "course_id": r.course_id,
        "status": getattr(sheet, "status", None),
        "released": r.released,
        "withheld": r.withheld,
        "appeal_case_id": r.appeal_case_id,
        "appeal_status": r.appeal_status,
        "outcome": r.outcome,
        "department_ids": getattr(sheet, "department_ids", []) or [],
        "faculty_ids": getattr(sheet, "faculty_ids", []) or [],
        "entered_by_ids": getattr(sheet, "entered_by_ids", []) or [],
        "conflicted_staff_ids": getattr(sheet, "conflicted_staff_ids", []) or [],
    }


@resources.register(
    "assessment_component_score",
    attributes={
        "id",
        "result_id",
        "student_id",
        "status",
        "course_offering_id",
        "department_ids",
        "faculty_ids",
        "entered_by_ids",
        "released",
    },
)
def _component_score(s: asmt.ComponentScore) -> dict[str, Any]:
    result = getattr(s, "result", None)
    base = _course_result(result) if result is not None else {}
    return {**base, "id": s.id, "result_id": s.result_id}


@resources.register(
    "board_decision",
    attributes={
        "id",
        "board_level",
        "semester_id",
        "status",
        "department_ids",
        "faculty_ids",
        "conflicted_staff_ids",
        "requested_by_id",
    },
    label=lambda b: b.minute_reference,
)
def _board_decision(b: asmt.BoardDecision) -> dict[str, Any]:
    return {
        "id": b.id,
        "board_level": b.board_level,
        "semester_id": b.semester_id,
        "status": b.status,
        "requested_by_id": b.created_by_id,
    }


@resources.register(
    "results_release",
    attributes={"id", "semester_id", "status", "released", "faculty_ids"},
)
def _results_release(r: asmt.ResultsRelease) -> dict[str, Any]:
    return {
        "id": r.id,
        "semester_id": r.semester_id,
        "status": r.status,
        "released": r.released_at is not None,
    }


@resources.register(
    "award",
    attributes={
        "id",
        "student_id",
        "status",
        "classification",
        "outstanding_balance_minor",
        "requested_by_id",
    },
    label=lambda a: f"{a.award_title} ({a.serial_number})",
)
def _award(a: asmt.Award) -> dict[str, Any]:
    return {
        "id": a.id,
        "student_id": a.student_id,
        "status": a.status,
        "classification": a.classification,
        # `outstanding_balance_minor` is supplied by the conferment service
        # from the student's ledger; `finance.tuition-blocks` reads it.
    }


@resources.register(
    "graduation_list",
    attributes={"id", "status", "faculty_ids", "requested_by_id", "prepared_by_id"},
    label=lambda g: g.name,
)
def _graduation_list(g: asmt.GraduationList) -> dict[str, Any]:
    return {
        "id": g.id,
        "status": g.status,
        "prepared_by_id": g.prepared_by_id,
        "requested_by_id": g.prepared_by_id,
    }


@resources.register(
    "transcript",
    attributes={"id", "student_id", "status", "withheld", "released"},
    label=lambda t: t.serial_number,
)
def _transcript(t: asmt.Transcript) -> dict[str, Any]:
    return {"id": t.id, "student_id": t.student_id, "status": t.status, "released": True}


@resources.register(
    "exam_sitting",
    attributes={
        "id",
        "course_offering_id",
        "semester_id",
        "status",
        "faculty_ids",
        "department_ids",
    },
)
def _exam_sitting(e: asmt.ExamSitting) -> dict[str, Any]:
    return {
        "id": e.id,
        "course_offering_id": e.course_offering_id,
        "semester_id": e.semester_id,
        "status": e.status,
    }


# ---------------------------------------------------------------------------
# Governance
# ---------------------------------------------------------------------------


@resources.register(
    "audit_event",
    attributes={"id", "subject_student_id", "subject_staff_id", "category", "actor_id"},
)
def _audit_event(e: gov.AuditEvent) -> dict[str, Any]:
    return {
        "id": e.id,
        "subject_student_id": e.subject_student_id,
        "subject_staff_id": e.subject_staff_id,
        "category": e.category,
        "actor_id": e.actor_id,
    }


@resources.register(
    "access_log", attributes={"id", "subject_student_id", "subject_staff_id", "actor_id"}
)
def _access_log(e: gov.AccessLog) -> dict[str, Any]:
    return {
        "id": e.id,
        "subject_student_id": e.subject_student_id,
        "subject_staff_id": e.subject_staff_id,
        "actor_id": e.actor_id,
    }


@resources.register(
    "policy",
    attributes={"id", "policy_id", "enabled", "priority", "authored_by_id", "requested_by_id"},
    label=lambda p: p.policy_id,
)
def _policy(p: gov.PolicyOverlay) -> dict[str, Any]:
    return {
        "id": p.id,
        "policy_id": p.policy_id,
        "enabled": p.enabled,
        "priority": p.priority,
        "authored_by_id": p.authored_by_id,
        "requested_by_id": p.authored_by_id,
    }


@resources.register(
    "report",
    attributes={"id", "kind", "module", "contains_personal_data", "required_permission"},
    label=lambda r: r.name,
)
def _report(r: gov.ReportDefinition) -> dict[str, Any]:
    return {
        "id": r.id,
        "kind": r.kind,
        "module": r.module,
        "contains_personal_data": r.contains_personal_data,
        "required_permission": r.required_permission,
    }


@resources.register(
    "report_run",
    attributes={
        "id",
        "definition_id",
        "status",
        "requested_by_id",
        "row_estimate",
        "contains_personal_data",
    },
)
def _report_run(r: gov.ReportRun) -> dict[str, Any]:
    definition = getattr(r, "definition", None)
    return {
        "id": r.id,
        "definition_id": r.definition_id,
        "status": r.status,
        "requested_by_id": r.requested_by_id,
        "row_estimate": r.row_count,
        "contains_personal_data": getattr(definition, "contains_personal_data", True),
    }


@resources.register(
    "dataset_export",
    attributes={"id", "contains_personal_data", "row_estimate", "requested_by_id"},
)
def _dataset_export(payload: Any) -> dict[str, Any]:
    return dict(payload)


@resources.register(
    "statutory_return",
    attributes={"id", "status", "regulator", "requested_by_id", "prepared_by_id"},
    label=lambda s: f"{s.code} {s.period_label}",
)
def _statutory_return(s: gov.StatutoryReturn) -> dict[str, Any]:
    return {
        "id": s.id,
        "status": s.status,
        "regulator": s.regulator,
        "prepared_by_id": s.prepared_by_id,
        "requested_by_id": s.prepared_by_id,
    }


# ---------------------------------------------------------------------------
# Developers
# ---------------------------------------------------------------------------


@resources.register(
    "api_client",
    attributes={"id", "owner_id", "status", "environment", "required_plan"},
    protected_fields={"granted_scopes"},
    label=lambda c: f"{c.name} ({c.client_id})",
)
def _api_client(c: dev.ApiClient) -> dict[str, Any]:
    return {
        "id": c.id,
        "owner_id": c.owner_id,
        "status": c.status,
        "environment": c.environment,
    }


@resources.register(
    "api_key",
    attributes={"id", "owner_id", "client_id", "environment", "revoked"},
    protected_fields={"key_hash"},
    label=lambda k: f"{k.name} ({k.prefix}…)",
)
def _api_key(k: dev.ApiKey) -> dict[str, Any]:
    client = getattr(k, "client", None)
    return {
        "id": k.id,
        "client_id": k.client_id,
        "owner_id": getattr(client, "owner_id", None),
        "environment": k.environment,
        "revoked": k.revoked_at is not None,
    }


@resources.register(
    "webhook",
    attributes={"id", "owner_id", "client_id", "is_active"},
    label=lambda w: w.name,
)
def _webhook(w: dev.Webhook) -> dict[str, Any]:
    client = getattr(w, "client", None)
    return {
        "id": w.id,
        "client_id": w.client_id,
        "owner_id": getattr(client, "owner_id", None),
        "is_active": w.is_active,
    }


@resources.register("webhook_delivery", attributes={"id", "owner_id", "webhook_id", "succeeded"})
def _webhook_delivery(d: dev.WebhookDelivery) -> dict[str, Any]:
    return {"id": d.id, "webhook_id": d.webhook_id, "succeeded": d.succeeded}


@resources.register("integration_log", attributes={"id", "owner_id", "client_id", "status_code"})
def _integration_log(entry: dev.IntegrationLog) -> dict[str, Any]:
    return {"id": entry.id, "client_id": entry.client_id, "status_code": entry.status_code}


@resources.register("sandbox_dataset", attributes={"id", "owner_id", "client_id", "status"})
def _sandbox_dataset(d: dev.SandboxDataset) -> dict[str, Any]:
    return {"id": d.id, "client_id": d.client_id, "status": d.status}


# ---------------------------------------------------------------------------
# Platform / control plane
# ---------------------------------------------------------------------------


@resources.register("tenant", attributes={"id", "slug", "status", "region"})
def _tenant(t: Any) -> dict[str, Any]:
    return {"id": t.id, "slug": t.slug, "status": t.status, "region": t.region}


@resources.register("plan", attributes={"id", "code", "is_active"})
def _plan(p: Any) -> dict[str, Any]:
    return {"id": p.id, "code": p.code, "is_active": p.is_active}


@resources.register("platform_user", attributes={"id", "user_id", "status"})
def _platform_user(u: Any) -> dict[str, Any]:
    return {"id": u.id, "user_id": u.id, "status": u.status}


@resources.register(
    "impersonation", attributes={"id", "tenant_id", "platform_user_id", "approved_by_id"}
)
def _impersonation(s: Any) -> dict[str, Any]:
    return {
        "id": s.id,
        "tenant_id": s.tenant_id,
        "platform_user_id": s.platform_user_id,
        "approved_by_id": s.approved_by_id,
    }


@resources.register("institution", attributes={"id", "slug", "status"})
def _institution(t: Any) -> dict[str, Any]:
    return _tenant(t)


@resources.register("notification", attributes={"id", "recipient_id", "category"})
def _notification(n: Any) -> dict[str, Any]:
    return {"id": n.id, "recipient_id": n.recipient_id, "category": n.category}


@resources.register("region", attributes={"id", "code"})
def _region(payload: Any) -> dict[str, Any]:
    return dict(payload)


@resources.register("auth", attributes={"id"})
def _auth(payload: Any) -> dict[str, Any]:
    """The pseudo-resource for session actions (`auth:whoami`, `auth:logout`).

    Registered so those actions go through the same `authorize()` path as
    everything else rather than being special-cased past it — a bypass for
    "harmless" actions is how the next not-quite-harmless one gets added.
    """
    return dict(payload or {})


@resources.register("export", attributes={"id", "contains_personal_data", "row_estimate"})
def _export(payload: Any) -> dict[str, Any]:
    return dict(payload)


# ---------------------------------------------------------------------------
# Learning and online assessment
# ---------------------------------------------------------------------------
#
# Several of these publish attributes the row does not carry —
# `is_registered`, `is_available`, `score_visible`, `mark_sheet_status`. They
# are supplied by the service layer at the point of the decision, because each
# depends on something outside the row: the caller's registrations, the clock,
# the assessment's release state, the mark sheet's position in the approval
# chain. Left absent they can only ever fail a permit, never grant one.


@resources.register(
    "course_space",
    attributes={
        "id",
        "course_offering_id",
        "semester_id",
        "department_ids",
        "faculty_ids",
        "is_published",
        "is_registered",
        "is_available",
    },
)
def _course_space(s: learn.CourseSpace) -> dict[str, Any]:
    return {
        "id": s.id,
        "course_offering_id": s.course_offering_id,
        "semester_id": s.semester_id,
        "department_ids": s.department_ids,
        "faculty_ids": s.faculty_ids,
        "is_published": s.is_published,
    }


@resources.register(
    "material",
    attributes={
        "id",
        "space_id",
        "course_offering_id",
        "kind",
        "is_published",
        "is_available",
        "is_registered",
        "allow_download",
        "week_number",
        "department_ids",
        "faculty_ids",
        "requires_fee_clearance",
    },
    label=lambda m: m.title,
)
def _material(m: learn.Material) -> dict[str, Any]:
    space = getattr(m, "space", None)
    return {
        "id": m.id,
        "space_id": m.space_id,
        "course_offering_id": getattr(space, "course_offering_id", None),
        "kind": m.kind,
        "is_published": m.is_published,
        "is_available": m.is_available,
        "allow_download": m.allow_download,
        "week_number": m.week_number,
        "requires_fee_clearance": m.requires_fee_clearance,
        "department_ids": getattr(space, "department_ids", []) or [],
        "faculty_ids": getattr(space, "faculty_ids", []) or [],
    }


@resources.register(
    "question_bank",
    attributes={
        "id",
        "course_id",
        "department_ids",
        "faculty_ids",
        "is_shared",
        "owning_unit_id",
        #: Supplied by the export endpoint, not by this extractor: it is a
        #: query across the assessment tables rather than a column here.
        "has_open_assessment",
    },
    label=lambda b: f"{b.code} — {b.name}",
)
def _question_bank(b: learn.QuestionBank) -> dict[str, Any]:
    return {
        "id": b.id,
        "course_id": b.course_id,
        "owning_unit_id": b.owning_unit_id,
        "department_ids": b.department_ids,
        "faculty_ids": b.faculty_ids,
        "is_shared": b.is_shared,
    }


@resources.register(
    "question",
    attributes={
        "id",
        "bank_id",
        "kind",
        "is_locked",
        "is_active",
        "department_ids",
        "faculty_ids",
        "is_shared",
        "assessment_status",
    },
    protected_fields={"answer_key", "explanation", "rubric"},
    label=lambda q: f"{q.kind}: {q.stem[:60]}",
)
def _question(q: learn.Question) -> dict[str, Any]:
    bank = getattr(q, "bank", None)
    return {
        "id": q.id,
        "bank_id": q.bank_id,
        "kind": q.kind,
        "is_locked": q.is_locked,
        "is_active": q.is_active,
        "is_shared": getattr(bank, "is_shared", False),
        "department_ids": getattr(bank, "department_ids", []) or [],
        "faculty_ids": getattr(bank, "faculty_ids", []) or [],
    }


@resources.register(
    "online_assessment",
    attributes={
        "id",
        "space_id",
        "course_offering_id",
        "kind",
        "status",
        "department_ids",
        "faculty_ids",
        "authored_by_id",
        "reviewed_by_id",
        "is_open",
        "is_registered",
        "mark_sheet_status",
        "counts_for_credit",
        "requested_by_id",
    },
    label=lambda a: a.title,
)
def _online_assessment(a: learn.OnlineAssessment) -> dict[str, Any]:
    return {
        "id": a.id,
        "space_id": a.space_id,
        "course_offering_id": a.course_offering_id,
        "kind": a.kind,
        "status": a.status,
        "department_ids": a.department_ids,
        "faculty_ids": a.faculty_ids,
        "authored_by_id": a.authored_by_id,
        "reviewed_by_id": a.reviewed_by_id,
        "requested_by_id": a.authored_by_id,
        "is_open": a.is_open_now(),
        "counts_for_credit": a.counts_for_credit,
    }


@resources.register(
    "assessment_item",
    attributes={
        "id",
        "assessment_id",
        "course_offering_id",
        "status",
        "department_ids",
        "faculty_ids",
    },
)
def _assessment_item(i: learn.AssessmentItem) -> dict[str, Any]:
    assessment = getattr(i, "assessment", None)
    return {
        "id": i.id,
        "assessment_id": i.assessment_id,
        "course_offering_id": getattr(assessment, "course_offering_id", None),
        "status": getattr(assessment, "status", None),
        "department_ids": getattr(assessment, "department_ids", []) or [],
        "faculty_ids": getattr(assessment, "faculty_ids", []) or [],
    }


@resources.register(
    "assessment_attempt",
    attributes={
        "id",
        "assessment_id",
        "student_id",
        "course_offering_id",
        "status",
        "department_ids",
        "faculty_ids",
        "score_visible",
        "counts_for_grade",
        "marked_by_id",
    },
)
def _attempt(a: learn.Attempt) -> dict[str, Any]:
    # `a.assessment` rather than a defensive `getattr`: the unit scope is what
    # every marking rule matches on, and a silent `None` here does not fail
    # loudly — it denies the whole marking queue and looks like a policy
    # problem.
    assessment = a.assessment
    return {
        "id": a.id,
        "assessment_id": a.assessment_id,
        "student_id": a.student_id,
        "course_offering_id": assessment.course_offering_id,
        "status": a.status,
        "counts_for_grade": a.counts_for_grade,
        "marked_by_id": a.marked_by_id,
        "department_ids": assessment.department_ids or [],
        "faculty_ids": assessment.faculty_ids or [],
    }


@resources.register(
    "assessment_response",
    attributes={
        "id",
        "attempt_id",
        "student_id",
        "question_id",
        "course_offering_id",
        "status",
        "marked_by_id",
        "department_ids",
        "faculty_ids",
    },
)
def _attempt_response(r: learn.AttemptResponse) -> dict[str, Any]:
    attempt = getattr(r, "attempt", None)
    base = _attempt(attempt) if attempt is not None else {}
    return {
        **base,
        "id": r.id,
        "attempt_id": r.attempt_id,
        "question_id": r.question_id,
        "marked_by_id": r.marked_by_id,
    }


@resources.register(
    "assignment",
    attributes={
        "id",
        "space_id",
        "course_offering_id",
        "status",
        "department_ids",
        "faculty_ids",
        "is_registered",
        "mark_sheet_status",
        "blind_marking",
    },
    label=lambda a: a.title,
)
def _assignment(a: learn.Assignment) -> dict[str, Any]:
    return {
        "id": a.id,
        "space_id": a.space_id,
        "course_offering_id": a.course_offering_id,
        "status": a.status,
        "department_ids": a.department_ids,
        "faculty_ids": a.faculty_ids,
        "blind_marking": a.blind_marking,
    }


@resources.register(
    "assignment_submission",
    attributes={
        "id",
        "assignment_id",
        "student_id",
        "course_offering_id",
        "status",
        "marked_by_id",
        #: Both supplied by the endpoint: registration is a query, and score
        #: visibility depends on the assignment's release state.
        "score_visible",
        "is_registered",
        "department_ids",
        "faculty_ids",
    },
)
def _submission(s: learn.Submission) -> dict[str, Any]:
    assignment = getattr(s, "assignment", None)
    return {
        "id": s.id,
        "assignment_id": s.assignment_id,
        "student_id": s.student_id,
        "course_offering_id": getattr(assignment, "course_offering_id", None),
        "status": s.status,
        "marked_by_id": s.marked_by_id,
        "department_ids": getattr(assignment, "department_ids", []) or [],
        "faculty_ids": getattr(assignment, "faculty_ids", []) or [],
    }


@resources.register(
    "engagement_snapshot",
    attributes={"id", "student_id", "course_offering_id", "risk_band", "week_number"},
    protected_fields={"minutes_on_material", "days_since_last_activity"},
)
def _engagement(e: learn.EngagementSnapshot) -> dict[str, Any]:
    return {
        "id": e.id,
        "student_id": e.student_id,
        "course_offering_id": e.course_offering_id,
        "risk_band": e.risk_band,
        "week_number": e.week_number,
    }


@resources.register(
    "material_view", attributes={"id", "student_id", "material_id", "course_offering_id"}
)
def _material_view(v: learn.MaterialView) -> dict[str, Any]:
    # The offering is what `learning.engagement-privacy` scopes on, and it is
    # two hops away — a view knows its material, and the material its space.
    material = v.material
    space = material.space if material is not None else None
    return {
        "id": v.id,
        "student_id": v.student_id,
        "material_id": v.material_id,
        "course_offering_id": space.course_offering_id if space is not None else None,
    }


@resources.register(
    "academic_unit",
    attributes={
        "id",
        "code",
        "kind",
        "parent_id",
        "ancestor_ids",
        "head_staff_id",
        "is_active",
        "faculty_ids",
        "department_ids",
    },
    label=lambda u: f"{u.code} — {u.name}",
)
def _academic_unit(u: shared.AcademicUnit) -> dict[str, Any]:
    # A unit is its own scope. Publishing `faculty_ids`/`department_ids` lets
    # the unit-reach rules treat a unit like any other unit-scoped record
    # instead of needing a special case.
    return {
        "id": u.id,
        "code": u.code,
        "kind": u.kind,
        "parent_id": u.parent_id,
        "ancestor_ids": u.ancestor_ids or [],
        "head_staff_id": u.head_staff_id,
        "is_active": u.is_active,
        "faculty_ids": [u.id, *(u.ancestor_ids or ())] if u.kind == "faculty" else [],
        "department_ids": [u.id] if u.kind == "department" else [],
    }


@resources.register(
    "data_request",
    attributes={
        "id",
        "kind",
        "status",
        "subject_student_id",
        "subject_staff_id",
        "requested_by_id",
    },
    protected_fields={"subject_name"},
    label=lambda r: r.reference,
)
def _data_request(r: gov.DataRequest) -> dict[str, Any]:
    return {
        "id": r.id,
        "kind": r.kind,
        "status": r.status,
        "subject_student_id": r.subject_student_id,
        "subject_staff_id": r.subject_staff_id,
        "requested_by_id": r.created_by_id,
    }


@resources.register(
    "semester_result",
    attributes={"id", "student_id", "semester_id", "progression", "released"},
)
def _semester_result(r: asmt.SemesterResult) -> dict[str, Any]:
    return {
        "id": r.id,
        "student_id": r.student_id,
        "semester_id": r.semester_id,
        "progression": r.progression,
        "released": r.is_published,
    }


@resources.register(
    "lti_tool",
    attributes={"id", "status", "issuer", "client_id", "owner_id"},
    label=lambda t: t.name,
)
def _lti_tool(t: interop.LtiTool) -> dict[str, Any]:
    return {
        "id": t.id,
        "status": t.status,
        "issuer": t.issuer,
        "client_id": t.client_id,
        "owner_id": t.created_by_id,
    }


# ---------------------------------------------------------------------------
# Student life-cycle: special examinations, cards, transfers
# ---------------------------------------------------------------------------


@resources.register(
    "special_exam_request",
    attributes={
        "id",
        "student_id",
        "course_offering_id",
        "semester_id",
        "kind",
        "ground",
        "status",
        "has_evidence",
        "evidence_verified",
        "department_ids",
        "faculty_ids",
        "requested_by_id",
    },
    protected_fields={"narrative", "evidence_attachment_ids"},
    label=lambda r: f"{r.kind} examination request {r.reference}",
)
def _special_exam_request(r: stu.SpecialExamRequest) -> dict[str, Any]:
    offering = r.course_offering
    return {
        "id": r.id,
        "student_id": r.student_id,
        "course_offering_id": r.course_offering_id,
        "semester_id": r.semester_id,
        "kind": r.kind,
        "ground": r.ground,
        "status": r.status,
        # The grounds are medical or bereavement more often than not, so the
        # narrative is protected and only the *presence* of evidence is
        # published — enough for the rule that refuses an unevidenced grant,
        # without putting a diagnosis into a policy decision.
        "has_evidence": bool(r.evidence_attachment_ids),
        "evidence_verified": r.evidence_verified_at is not None,
        "department_ids": getattr(offering, "department_ids", []) or [],
        "faculty_ids": getattr(offering, "faculty_ids", []) or [],
        "requested_by_id": r.created_by_id,
    }


@resources.register(
    "student_id_card",
    attributes={"id", "student_id", "status", "reason", "campus_id", "requested_by_id"},
    protected_fields={"photo_attachment_id", "rfid_uid"},
    label=lambda c: f"identity card {c.serial}",
)
def _student_id_card(c: stu.StudentIdCard) -> dict[str, Any]:
    return {
        "id": c.id,
        "student_id": c.student_id,
        "status": c.status,
        "reason": c.reason,
        "campus_id": c.campus_id,
        "requested_by_id": c.created_by_id,
    }


@resources.register(
    "exam_card",
    attributes={
        "id",
        "student_id",
        "registration_id",
        "semester_id",
        "session",
        "status",
        "fee_percentage_paid",
        "required_percentage",
        "attendance_ok",
    },
    label=lambda c: f"examination card {c.verification_code}",
)
def _exam_card(c: stu.ExamCard) -> dict[str, Any]:
    snapshot = c.clearance_snapshot or {}
    return {
        "id": c.id,
        "student_id": c.student_id,
        "registration_id": c.registration_id,
        "semester_id": c.semester_id,
        "session": c.session,
        "status": c.status,
        # Read from the snapshot rather than recomputed: the policy question
        # about an *issued* card is whether it was validly issued, which is a
        # question about the gates as they stood then.
        "fee_percentage_paid": snapshot.get("fee_percentage_paid"),
        "required_percentage": snapshot.get("required_percentage"),
        "attendance_ok": snapshot.get("attendance_ok"),
    }


@resources.register(
    "institution_transfer",
    attributes={
        "id",
        "direction",
        "student_id",
        "applicant_id",
        "programme_id",
        "status",
        "credits_claimed",
        "credits_awarded",
        "credit_transfer_cap_percent",
        "requested_by_id",
    },
    label=lambda t: f"{t.direction} transfer {t.reference}",
)
def _institution_transfer(t: stu.InstitutionTransfer) -> dict[str, Any]:
    return {
        "id": t.id,
        "direction": t.direction,
        "student_id": t.student_id,
        "applicant_id": t.applicant_id,
        "programme_id": t.programme_id,
        "status": t.status,
        "credits_claimed": t.credits_claimed,
        "credits_awarded": t.credits_awarded,
        "credit_transfer_cap_percent": t.credit_transfer_cap_percent,
        "requested_by_id": t.created_by_id,
    }


@resources.register(
    "calendar_event",
    attributes={
        "id",
        "kind",
        "audience",
        "is_published",
        "academic_year_id",
        "semester_id",
        "unit_ids",
        "faculty_ids",
        "department_ids",
    },
    label=lambda e: e.title,
)
def _calendar_event(e: shared.CalendarEvent) -> dict[str, Any]:
    return {
        "id": e.id,
        "kind": e.kind,
        "audience": e.audience,
        "is_published": e.is_published,
        "academic_year_id": e.academic_year_id,
        "semester_id": e.semester_id,
        "unit_ids": e.unit_ids or [],
        # A calendar event is scoped by unit without knowing which of those
        # units are faculties; publishing the same list under both names lets
        # the unit-reach rules match it without a special case.
        "faculty_ids": e.unit_ids or [],
        "department_ids": e.unit_ids or [],
    }


# ---------------------------------------------------------------------------
# Library
# ---------------------------------------------------------------------------


@resources.register(
    "catalogue_record",
    attributes={"id", "material_kind", "is_searchable", "student_id", "library_id"},
    label=lambda r: r.title,
)
def _catalogue_record(r: lib.CatalogueRecord) -> dict[str, Any]:
    return {
        "id": r.id,
        "material_kind": r.material_kind,
        "is_searchable": r.is_searchable,
        # Set for a deposited thesis, which is the one catalogue record that
        # belongs to somebody: an embargoed thesis is read by its author and
        # the library, not by the whole reading room.
        "student_id": r.student_id,
        "library_id": None,
    }


@resources.register(
    "catalogue_copy",
    attributes={"id", "record_id", "library_id", "status", "loan_class"},
    label=lambda c: f"copy {c.accession_number}",
)
def _catalogue_copy(c: lib.CatalogueCopy) -> dict[str, Any]:
    return {
        "id": c.id,
        "record_id": c.record_id,
        "library_id": c.library_id,
        "status": c.status,
        "loan_class": c.loan_class,
    }


@resources.register(
    "library_member",
    attributes={
        "id",
        "student_id",
        "staff_id",
        "borrower_category",
        "status",
        "outstanding_fines_minor",
        "items_on_loan",
    },
    protected_fields={"notes", "suspension_reason"},
    label=lambda m: f"member {m.membership_number}",
)
def _library_member(m: lib.LibraryMember) -> dict[str, Any]:
    return {
        "id": m.id,
        "student_id": m.student_id,
        "staff_id": m.staff_id,
        "borrower_category": m.borrower_category,
        "status": m.status,
        "outstanding_fines_minor": m.outstanding_fines_minor,
        "items_on_loan": m.items_on_loan,
    }


@resources.register(
    "library_loan",
    attributes={
        "id",
        "member_id",
        "student_id",
        "staff_id",
        "copy_id",
        "library_id",
        "status",
        "is_overdue",
        "renewals",
    },
    label=lambda loan: f"loan of copy {loan.copy_id}",
)
def _library_loan(loan: lib.Loan) -> dict[str, Any]:
    member = loan.member
    return {
        "id": loan.id,
        "member_id": loan.member_id,
        # The borrower's own identity, so "a reader sees their own loans" is
        # one rule rather than a join the policy engine cannot do.
        "student_id": getattr(member, "student_id", None),
        "staff_id": getattr(member, "staff_id", None),
        "copy_id": loan.copy_id,
        "library_id": loan.library_id,
        "status": loan.status,
        "is_overdue": loan.status == lib.LoanStatus.OVERDUE,
        "renewals": loan.renewals,
    }


@resources.register(
    "library_reservation",
    attributes={"id", "member_id", "student_id", "staff_id", "record_id", "status"},
)
def _library_reservation(r: lib.Reservation) -> dict[str, Any]:
    member = r.member
    return {
        "id": r.id,
        "member_id": r.member_id,
        "student_id": getattr(member, "student_id", None),
        "staff_id": getattr(member, "staff_id", None),
        "record_id": r.record_id,
        "status": r.status,
    }


@resources.register(
    "library_fine",
    attributes={
        "id",
        "member_id",
        "student_id",
        "staff_id",
        "reason",
        "status",
        "amount_minor",
        "raised_by_id",
    },
)
def _library_fine(f: lib.LibraryFine) -> dict[str, Any]:
    member = f.member
    return {
        "id": f.id,
        "member_id": f.member_id,
        "student_id": getattr(member, "student_id", None),
        "staff_id": getattr(member, "staff_id", None),
        "reason": f.reason,
        "status": f.status,
        "amount_minor": f.amount_minor,
        # A waiver is a four-eyes decision, exactly like a fee waiver, so the
        # raiser has to be visible to the rule that refuses self-release.
        "raised_by_id": f.raised_by_id,
    }


@resources.register(
    "acquisition_request",
    attributes={"id", "status", "requested_by_id", "course_id", "department_ids", "faculty_ids"},
    label=lambda a: a.title,
)
def _acquisition_request(a: lib.AcquisitionRequest) -> dict[str, Any]:
    return {
        "id": a.id,
        "status": a.status,
        "requested_by_id": a.requested_by_id,
        "course_id": a.course_id,
        "department_ids": [a.requesting_unit_id] if a.requesting_unit_id else [],
        "faculty_ids": [],
    }


@resources.register(
    "e_resource_subscription",
    attributes={"id", "kind", "is_active", "unit_ids"},
    label=lambda s: s.name,
)
def _e_resource(s: lib.EResourceSubscription) -> dict[str, Any]:
    return {"id": s.id, "kind": s.kind, "is_active": s.is_active, "unit_ids": s.unit_ids or []}


@resources.register(
    "library_stock_take",
    attributes={"id", "library_id", "status"},
    label=lambda s: f"stock-take {s.reference}",
)
def _stock_take(s: lib.StockTake) -> dict[str, Any]:
    return {"id": s.id, "library_id": s.library_id, "status": s.status}


# ---------------------------------------------------------------------------
# Quality assurance
# ---------------------------------------------------------------------------


@resources.register(
    "class_session",
    attributes={
        "id",
        "course_offering_id",
        "semester_id",
        "status",
        "register_closed",
        "delivered_by_staff_id",
        "scheduled_staff_id",
        "department_ids",
        "faculty_ids",
    },
)
def _class_session(s: qa.ClassSession) -> dict[str, Any]:
    offering = s.course_offering
    return {
        "id": s.id,
        "course_offering_id": s.course_offering_id,
        "semester_id": s.semester_id,
        "status": s.status,
        # A closed register is corrected only through the dispute path, which
        # the database also enforces; the policy refuses the write earlier so
        # the caller gets a reason rather than a constraint error.
        "register_closed": s.register_closed_at is not None,
        "delivered_by_staff_id": s.delivered_by_staff_id,
        "scheduled_staff_id": s.scheduled_staff_id,
        "department_ids": getattr(offering, "department_ids", []) or [],
        "faculty_ids": getattr(offering, "faculty_ids", []) or [],
    }


@resources.register(
    "session_attendance",
    attributes={
        "id",
        "session_id",
        "student_id",
        "course_offering_id",
        "status",
        "register_closed",
        "department_ids",
        "faculty_ids",
    },
)
def _session_attendance(a: qa.SessionAttendance) -> dict[str, Any]:
    session = a.session
    base = _class_session(session) if session is not None else {}
    return {
        **base,
        "id": a.id,
        "session_id": a.session_id,
        "student_id": a.student_id,
        "course_offering_id": a.course_offering_id,
        "status": a.status,
    }


@resources.register(
    "staff_attendance",
    attributes={"id", "staff_id", "kind", "status", "payable", "department_ids", "faculty_ids"},
)
def _staff_attendance(a: qa.StaffAttendance) -> dict[str, Any]:
    staff = a.staff
    return {
        "id": a.id,
        "staff_id": a.staff_id,
        "kind": a.kind,
        "status": a.status,
        "payable": a.payable,
        "department_ids": getattr(staff, "department_ids", []) or [],
        "faculty_ids": getattr(staff, "faculty_ids", []) or [],
    }


@resources.register(
    "evaluation_instrument",
    attributes={"id", "scope", "is_published"},
    label=lambda i: f"{i.name} v{i.version}",
)
def _evaluation_instrument(i: qa.EvaluationInstrument) -> dict[str, Any]:
    return {"id": i.id, "scope": i.scope, "is_published": i.is_published}


@resources.register(
    "course_evaluation",
    attributes={
        "id",
        "course_offering_id",
        "semester_id",
        "staff_id",
        "status",
        "is_reportable",
        "results_visible",
        "is_open",
        "department_ids",
        "faculty_ids",
    },
)
def _course_evaluation(e: qa.CourseEvaluation) -> dict[str, Any]:
    offering = e.course_offering
    now = utcnow()
    return {
        "id": e.id,
        "course_offering_id": e.course_offering_id,
        "semester_id": e.semester_id,
        "staff_id": e.staff_id,
        "status": e.status,
        # Below the reporting threshold nothing is shown to anybody: a
        # breakdown of four responses names the dissenter.
        "is_reportable": e.is_reportable,
        # And even a reportable evaluation stays sealed until after the
        # marking deadline, so a lecturer never reads their students'
        # opinions while holding their marks.
        "results_visible": (e.results_visible_from is not None and e.results_visible_from <= now),
        "is_open": e.opens_at <= now <= e.closes_at,
        "department_ids": getattr(offering, "department_ids", []) or [],
        "faculty_ids": getattr(offering, "faculty_ids", []) or [],
    }


@resources.register(
    "evaluation_response",
    attributes={"id", "evaluation_id"},
)
def _evaluation_response(r: qa.EvaluationResponse) -> dict[str, Any]:
    # Nothing identifying, because there is nothing identifying to publish.
    # A response carries no student id at all — see the model's note.
    return {"id": r.id, "evaluation_id": r.evaluation_id}


@resources.register(
    "evaluation_invitation",
    attributes={"id", "evaluation_id", "student_id", "responded"},
)
def _evaluation_invitation(i: qa.EvaluationInvitation) -> dict[str, Any]:
    # `student_id` is published so a student can be shown their own
    # outstanding invitations. It is never published *alongside* a response —
    # the two tables have no key between them, and
    # `quality.evaluation-anonymity` refuses the query that would read them
    # together.
    return {
        "id": i.id,
        "evaluation_id": i.evaluation_id,
        "student_id": i.student_id,
        "responded": i.responded_at is not None,
    }


@resources.register(
    "teaching_observation",
    attributes={
        "id",
        "staff_id",
        "observer_staff_id",
        "purpose",
        "status",
        "is_developmental",
        "department_ids",
        "faculty_ids",
    },
    protected_fields={"areas_to_develop", "rubric_scores", "observee_response"},
)
def _teaching_observation(o: qa.TeachingObservation) -> dict[str, Any]:
    staff = o.staff
    return {
        "id": o.id,
        "staff_id": o.staff_id,
        "observer_staff_id": o.observer_staff_id,
        "purpose": o.purpose,
        "status": o.status,
        # A developmental observation belongs to the person observed. One
        # commissioned for a promotion decision does not, and the flag is
        # what keeps the two apart.
        "is_developmental": o.is_developmental,
        "department_ids": getattr(staff, "department_ids", []) or [],
        "faculty_ids": getattr(staff, "faculty_ids", []) or [],
    }


@resources.register(
    "quality_audit",
    attributes={"id", "kind", "unit_id", "programme_id", "status", "department_ids", "faculty_ids"},
    label=lambda a: f"{a.reference} {a.title}",
)
def _quality_audit(a: qa.QualityAudit) -> dict[str, Any]:
    return {
        "id": a.id,
        "kind": a.kind,
        "unit_id": a.unit_id,
        "programme_id": a.programme_id,
        "status": a.status,
        "department_ids": [a.unit_id] if a.unit_id else [],
        "faculty_ids": [a.unit_id] if a.unit_id else [],
    }


@resources.register(
    "quality_indicator",
    attributes={"id", "code", "unit_id", "programme_id", "performance"},
    label=lambda i: i.name,
)
def _quality_indicator(i: qa.QualityIndicator) -> dict[str, Any]:
    return {
        "id": i.id,
        "code": i.code,
        "unit_id": i.unit_id,
        "programme_id": i.programme_id,
        "performance": i.performance,
    }


# ---------------------------------------------------------------------------
# Late payment
# ---------------------------------------------------------------------------


@resources.register(
    "late_payment_rule",
    attributes={"id", "status", "academic_year_id", "programme_id", "is_waivable"},
    label=lambda r: r.name,
)
def _late_payment_rule(r: fin.LatePaymentRule) -> dict[str, Any]:
    return {
        "id": r.id,
        "status": r.status,
        "academic_year_id": r.academic_year_id,
        "programme_id": r.programme_id,
        "is_waivable": r.is_waivable,
    }


@resources.register(
    "penalty_charge",
    attributes={"id", "student_id", "invoice_id", "status", "amount_minor", "applied_by_id"},
)
def _penalty_charge(c: fin.PenaltyCharge) -> dict[str, Any]:
    return {
        "id": c.id,
        "student_id": c.student_id,
        "invoice_id": c.invoice_id,
        "status": c.status,
        "amount_minor": c.amount_minor,
        "applied_by_id": c.applied_by_id,
    }


@resources.register(
    "payment_plan",
    attributes={"id", "student_id", "invoice_id", "status", "total_minor", "requested_by_id"},
    label=lambda p: f"payment plan {p.reference}",
)
def _payment_plan(p: fin.PaymentPlan) -> dict[str, Any]:
    return {
        "id": p.id,
        "student_id": p.student_id,
        "invoice_id": p.invoice_id,
        "status": p.status,
        "total_minor": p.total_minor,
        "requested_by_id": p.created_by_id,
    }


@resources.register(
    "dunning_notice",
    attributes={"id", "student_id", "invoice_id", "level"},
)
def _dunning_notice(n: fin.DunningNotice) -> dict[str, Any]:
    return {
        "id": n.id,
        "student_id": n.student_id,
        "invoice_id": n.invoice_id,
        "level": n.level,
    }


# ---------------------------------------------------------------------------
# Elections
# ---------------------------------------------------------------------------


@resources.register(
    "election",
    attributes={
        "id",
        "kind",
        "status",
        "is_published",
        "returning_officer_id",
        "observer_staff_ids",
        "academic_year_id",
    },
    label=lambda e: f"{e.reference} {e.title}",
)
def _election(e: elect.Election) -> dict[str, Any]:
    return {
        "id": e.id,
        "kind": e.kind,
        "status": e.status,
        # Everything past `draft` is visible to the electorate: an election
        # the students cannot see is not an election.
        "is_published": e.status != elect.ElectionStatus.DRAFT,
        "returning_officer_id": e.returning_officer_id,
        "observer_staff_ids": e.observer_staff_ids or [],
        "academic_year_id": e.academic_year_id,
    }


@resources.register(
    "election_position",
    attributes={"id", "election_id", "status", "is_referendum", "seats"},
    label=lambda p: p.title,
)
def _election_position(p: elect.ElectionPosition) -> dict[str, Any]:
    election = p.election
    return {
        "id": p.id,
        "election_id": p.election_id,
        "status": getattr(election, "status", None),
        "is_referendum": p.is_referendum,
        "seats": p.seats,
    }


@resources.register(
    "election_candidate",
    attributes={"id", "position_id", "student_id", "status", "requested_by_id"},
    label=lambda c: c.ballot_name,
)
def _election_candidate(c: elect.Candidate) -> dict[str, Any]:
    return {
        "id": c.id,
        "position_id": c.position_id,
        "student_id": c.student_id,
        "status": c.status,
        # A candidate withdraws their own nomination; nobody else may.
        "requested_by_id": c.created_by_id,
    }


@resources.register(
    "election_ballot",
    attributes={"id", "election_id", "position_id"},
)
def _election_ballot(b: elect.Ballot) -> dict[str, Any]:
    # Nothing identifying, because there is nothing identifying to publish. A
    # ballot has no voter — see the model's note. Registered so the policy
    # linter can see the type and so the rules that *refuse* reads of it have
    # something to target.
    return {"id": b.id, "election_id": b.election_id, "position_id": b.position_id}


@resources.register(
    "election_voter_roll",
    attributes={"id", "election_id", "student_id", "is_eligible", "has_voted"},
)
def _election_voter_roll(r: elect.VoterRoll) -> dict[str, Any]:
    return {
        "id": r.id,
        "election_id": r.election_id,
        "student_id": r.student_id,
        "is_eligible": r.is_eligible,
        "has_voted": r.voted_at is not None,
    }


@resources.register(
    "election_result",
    attributes={"id", "election_id", "position_id", "is_declared"},
)
def _election_result(r: elect.ElectionResult) -> dict[str, Any]:
    return {
        "id": r.id,
        "election_id": r.election_id,
        "position_id": r.position_id,
        # A written result is a declared result: nothing lands in this table
        # before the returning officer declares.
        "is_declared": True,
    }


@resources.register(
    "election_petition",
    attributes={"id", "election_id", "student_id", "status", "requested_by_id"},
    label=lambda p: p.reference,
)
def _election_petition(p: elect.ElectionPetition) -> dict[str, Any]:
    return {
        "id": p.id,
        "election_id": p.election_id,
        "student_id": p.petitioner_student_id,
        "status": p.status,
        "requested_by_id": p.created_by_id,
    }
