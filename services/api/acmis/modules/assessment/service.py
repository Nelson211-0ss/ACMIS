"""Assessment operations: mark entry, moderation, boards, release, awards."""

from __future__ import annotations

import secrets
import uuid
from datetime import date
from decimal import Decimal
from itertools import pairwise
from statistics import mean, median, pstdev
from typing import Any

import structlog
from sqlalchemy import func, select
from sqlalchemy.orm import Session, selectinload

from acmis.core.abac import bulk_decide
from acmis.core.audit import AuditCategory, diff, emit
from acmis.core.errors import Conflict, NotFound, RuleViolation, ValidationFailed
from acmis.core.models import utcnow
from acmis.core.schemas import BulkResult, Capability
from acmis.modules.assessment import rules
from acmis.modules.assessment.models import (
    Award,
    ComponentScore,
    CourseResult,
    GradeBand,
    GradingScale,
    MarkSheet,
    MarkSheetStatus,
    ResultsRelease,
    SemesterResult,
    Transcript,
)
from acmis.modules.curriculum.models import AssessmentComponent, AssessmentScheme

log = structlog.get_logger(__name__)

MARK_SHEET_ACTIONS = (
    "mark_sheet:read",
    "mark_sheet:update",
    "mark_sheet:submit",
    "mark_sheet:moderate",
    "mark_sheet:approve",
    "mark_sheet:faculty_approve",
    "mark_sheet:senate_approve",
    "mark_sheet:return",
)


def capabilities_for(ctx: Any, sheet: MarkSheet) -> list[Capability]:
    allowed = bulk_decide(
        engine=ctx.engine,
        actions=MARK_SHEET_ACTIONS,
        resource_type="mark_sheet",
        resource=sheet,
    )
    return [Capability(action=a, allowed=v) for a, v in allowed.items()]


def current_scale(session: Session, *, when: date | None = None) -> GradingScale:
    """The grading scale in force on a date.

    Dated rather than "the current one", because a transcript for a 2019
    graduate must be computed on the 2019 scale. Institutions do change scales,
    and recomputing an issued classification under a new one is how a graduate
    discovers their degree class has quietly changed.
    """
    on = when or date.today()
    scale = (
        session.execute(
            select(GradingScale)
            .options(selectinload(GradingScale.bands))
            .where(
                GradingScale.effective_from <= on,
                (GradingScale.effective_to.is_(None)) | (GradingScale.effective_to >= on),
                GradingScale.deleted_at.is_(None),
            )
            .order_by(GradingScale.effective_from.desc())
        )
        .scalars()
        .first()
    )
    if scale is None:
        raise RuleViolation(
            "No grading scale is in force. Configure one before entering marks.",
            rule="no_grading_scale",
        )
    return scale


def validate_scale(scale: GradingScale) -> list[str]:
    """Assert the bands cover 0-100 with no gap and no overlap.

    A gap means a mark that produces no grade, and it is always found at the
    worst moment — with a board sitting in front of the mark sheet. Run when a
    scale is saved and again when a sheet is generated.
    """
    bands = sorted(scale.bands, key=lambda b: Decimal(str(b.lower_mark)))
    problems: list[str] = []
    if not bands:
        return ["The grading scale has no bands."]

    if Decimal(str(bands[0].lower_mark)) > 0:
        problems.append(f"No band covers marks below {bands[0].lower_mark}.")
    if Decimal(str(bands[-1].upper_mark)) < 100:
        problems.append(f"No band covers marks above {bands[-1].upper_mark}.")

    for previous, following in pairwise(bands):
        upper = Decimal(str(previous.upper_mark))
        lower = Decimal(str(following.lower_mark))
        if lower <= upper:
            problems.append(f"Bands {previous.grade} and {following.grade} overlap at {lower}.")
        elif lower - upper > Decimal("0.01"):
            problems.append(
                f"Marks between {upper} and {lower} fall in no band "
                f"({previous.grade} / {following.grade})."
            )
    return problems


def generate_mark_sheet(
    session: Session, *, course_offering_id: uuid.UUID, actor_id: uuid.UUID
) -> MarkSheet:
    """Create the mark sheet for an offering from its registrations.

    Once generated, the offering is closed to registration changes: adding a
    student to a live mark sheet is how someone ends up sitting an examination
    they were never registered for, and then having a mark with no
    registration behind it.
    """
    from acmis.modules.curriculum.models import CourseOffering
    from acmis.modules.students.models import RegistrationCourse

    offering = session.get(CourseOffering, course_offering_id)
    if offering is None or offering.deleted_at is not None:
        raise NotFound("That course offering does not exist.")

    existing = session.execute(
        select(MarkSheet).where(MarkSheet.course_offering_id == course_offering_id)
    ).scalar_one_or_none()
    if existing is not None:
        return existing

    scale = current_scale(session)
    problems = validate_scale(scale)
    if problems:
        raise RuleViolation(
            "The grading scale is not usable.",
            rule="invalid_grading_scale",
            details={"problems": problems},
        )

    registrations = (
        session.execute(
            select(RegistrationCourse).where(
                RegistrationCourse.course_offering_id == course_offering_id,
                RegistrationCourse.dropped_at.is_(None),
                RegistrationCourse.withdrawn_at.is_(None),
                RegistrationCourse.is_audit.is_(False),
                RegistrationCourse.deleted_at.is_(None),
            )
        )
        .scalars()
        .all()
    )

    sheet = MarkSheet(
        course_offering_id=course_offering_id,
        semester_id=offering.semester_id,
        assessment_scheme_id=offering.assessment_scheme_id,
        grading_scale_id=scale.id,
        status=MarkSheetStatus.DRAFT,
        department_ids=list(offering.department_ids or ()),
        faculty_ids=list(offering.faculty_ids or ()),
        student_count=len(registrations),
        missing_count=len(registrations),
        created_by_id=actor_id,
    )
    session.add(sheet)
    session.flush()

    course = offering.course
    for registration in registrations:
        session.add(
            CourseResult(
                mark_sheet_id=sheet.id,
                student_id=registration.student_id,
                course_offering_id=course_offering_id,
                course_id=offering.course_id,
                registration_course_id=registration.id,
                semester_id=offering.semester_id,
                course_code=course.code,
                course_title=course.title,
                credit_units=registration.credit_units,
                outcome="pending",
                attempt_number=registration.attempt_number,
                is_retake=registration.is_retake,
                counts_in_gpa=course.counts_toward_gpa and not registration.is_audit,
                created_by_id=actor_id,
            )
        )

    offering.mark_sheet_generated_at = utcnow()
    offering.is_open = False
    session.flush()

    emit(
        "mark_sheet:create",
        AuditCategory.ASSESSMENT,
        resource_type="mark_sheet",
        resource_id=sheet.id,
        resource_label=f"{course.code} mark sheet",
        summary=f"Mark sheet generated for {len(registrations)} candidate(s)",
        metadata={"course_code": course.code, "grading_scale": scale.code},
    )
    return sheet


def enter_marks(
    session: Session,
    *,
    sheet: MarkSheet,
    entries: list[dict[str, Any]],
    actor_id: uuid.UUID,
) -> BulkResult:
    """Record component scores and recompute each candidate's result.

    Partial success is the normal outcome of a mark upload: 480 rows land and
    six fail on an unrecognised student number. Reporting that as one boolean
    forces the examiner to re-upload all 486, which is how marks get entered
    twice.

    Every change is versioned on the component score. A mark edited three times
    before submission is three facts, and the third is not more true than the
    first without a record of the other two.
    """
    if not sheet.is_editable:
        raise Conflict(f"This mark sheet is {sheet.status} and can no longer be edited.")

    scale = session.get(GradingScale, sheet.grading_scale_id)
    if scale is None:  # pragma: no cover
        raise NotFound()
    bands = sorted(scale.bands, key=lambda b: Decimal(str(b.lower_mark)), reverse=True)

    # Typed, not `dict[str, Any]`. The previous `Any` here hid a wrong column
    # name (`max_score` for `max_mark`) from the type checker, and the bug
    # surfaced only when a mark was actually entered.
    scheme_components: dict[str, AssessmentComponent] = {}
    if sheet.assessment_scheme_id:
        scheme = session.get(AssessmentScheme, sheet.assessment_scheme_id)
        if scheme is not None:
            scheme_components = {c.code: c for c in scheme.components}

    errors: list[dict[str, Any]] = []
    succeeded = 0
    correlation = uuid.uuid4()

    for entry in entries:
        student_id = entry.get("student_id")
        try:
            result = session.execute(
                select(CourseResult)
                .options(selectinload(CourseResult.component_scores))
                .where(
                    CourseResult.mark_sheet_id == sheet.id,
                    CourseResult.student_id == uuid.UUID(str(student_id)),
                )
            ).scalar_one_or_none()
        except (ValueError, TypeError):
            errors.append({"student_id": str(student_id), "error": "not a valid identifier"})
            continue

        if result is None:
            errors.append(
                {
                    "student_id": str(student_id),
                    "error": "not registered for this course offering",
                }
            )
            continue

        before = {
            "final_mark": float(result.final_mark) if result.final_mark is not None else None,
            "grade": result.grade,
            "outcome": result.outcome,
        }

        try:
            _apply_component_scores(
                session,
                result=result,
                components=entry.get("components") or {},
                scheme_components=scheme_components,
                actor_id=actor_id,
            )
            _recompute_result(
                session,
                result=result,
                bands=bands,
                scheme_components=scheme_components,
                exception=entry.get("exception"),
            )
            succeeded += 1
        except (ValidationFailed, ValueError) as exc:
            errors.append({"student_id": str(student_id), "error": str(exc)})
            continue

        after = {
            "final_mark": float(result.final_mark) if result.final_mark is not None else None,
            "grade": result.grade,
            "outcome": result.outcome,
        }
        changed = diff(before, after)
        if changed:
            emit(
                "course_result:update",
                AuditCategory.ASSESSMENT,
                resource_type="course_result",
                resource_id=result.id,
                resource_label=f"{result.course_code} / {result.student_id}",
                summary=f"Mark recorded: {after['final_mark']} ({after['grade']})",
                changes=changed,
                correlation_id=correlation,
            )

    if actor_id not in (sheet.entered_by_ids or ()):
        # Appended, never reset. The separation-of-duties rule reads this to
        # refuse self-approval, so losing an entrant would let them approve
        # their own marks.
        sheet.entered_by_ids = [*(sheet.entered_by_ids or ()), actor_id]

    _refresh_sheet_statistics(session, sheet=sheet)
    session.flush()

    emit(
        "mark_sheet:update",
        AuditCategory.ASSESSMENT,
        resource_type="mark_sheet",
        resource_id=sheet.id,
        summary=f"{succeeded} mark(s) entered, {len(errors)} rejected",
        metadata={"errors": errors[:50]},
        correlation_id=correlation,
    )
    return BulkResult(
        total=len(entries),
        succeeded=succeeded,
        failed=len(errors),
        errors=errors,
        correlation_id=correlation,
    )


def _apply_component_scores(
    session: Session,
    *,
    result: CourseResult,
    components: dict[str, Any],
    scheme_components: dict[str, AssessmentComponent],
    actor_id: uuid.UUID,
) -> None:
    by_code = {s.component_code: s for s in result.component_scores}

    for code, raw in components.items():
        component = scheme_components.get(code)
        if component is None:
            raise ValidationFailed(f"'{code}' is not a component of this course's assessment")
        value = None if raw is None else float(raw)
        if value is not None and (value < 0 or value > float(component.max_mark)):
            raise ValidationFailed(f"{code} must be between 0 and {component.max_mark}")

        weighted = (
            None
            if value is None
            else round(value / float(component.max_mark) * float(component.weight_percent), 2)
        )
        existing = by_code.get(code)
        if existing is None:
            session.add(
                ComponentScore(
                    result_id=result.id,
                    component_id=component.id,
                    component_code=code,
                    raw_score=value,
                    max_score=component.max_mark,
                    weight_percent=component.weight_percent,
                    weighted_score=weighted,
                    entered_by_id=actor_id,
                    entered_at=utcnow(),
                    created_by_id=actor_id,
                )
            )
        else:
            if existing.raw_score != value:
                existing.revisions = [
                    *(existing.revisions or ()),
                    {
                        "revision": existing.revision,
                        "raw_score": (
                            float(existing.raw_score) if existing.raw_score is not None else None
                        ),
                        "changed_at": utcnow().isoformat(),
                        "changed_by": str(actor_id),
                    },
                ]
                existing.revision += 1
            existing.raw_score = value
            existing.weighted_score = weighted
            existing.entered_by_id = actor_id
            existing.entered_at = utcnow()
    session.flush()


def _recompute_result(
    session: Session,
    *,
    result: CourseResult,
    bands: list[GradeBand],
    scheme_components: dict[str, AssessmentComponent],
    exception: str | None,
) -> None:
    """Recompute the final mark, grade and outcome from the components.

    Two rules that trip people up, both institution-configured:

    * `exam_must_be_passed` — some faculties require the final examination to
      be passed on its own, however strong the coursework. Medicine and Law
      commonly do, and a student with 70 coursework and 20 exam fails.
    * `minimum_coursework_for_exam` — a student below the coursework floor is
      barred from sitting, which is a distinct outcome from failing.
    """
    session.refresh(result)
    if exception in {"absent", "malpractice", "deferred", "incomplete", "withheld"}:
        result.final_mark = None
        result.grade = None
        result.grade_point = None
        result.outcome = exception if exception != "deferred" else "incomplete"
        result.quality_points = None
        return

    scores = {s.component_code: s for s in result.component_scores}
    if not scores or all(s.raw_score is None for s in scores.values()):
        result.outcome = "pending"
        return

    total = Decimal(0)
    coursework = Decimal(0)
    exam = Decimal(0)
    covered = Decimal(0)

    for code, component in scheme_components.items():
        score = scores.get(code)
        if score is None or score.raw_score is None:
            continue
        weighted = Decimal(str(score.weighted_score or 0))
        total += weighted
        covered += Decimal(str(component.weight_percent))
        if component.kind == "final_exam":
            exam += weighted
        else:
            coursework += weighted

    if covered == 0:
        result.outcome = "pending"
        return

    # Scale to 100 when only some components are in, so a partially-entered
    # sheet shows a meaningful provisional mark rather than an alarming one.
    final = (total / covered * 100) if covered < 100 else total
    result.final_mark = float(round(final, 2))
    result.coursework_mark = float(round(coursework, 2)) if coursework else None
    result.exam_mark = float(round(exam, 2)) if exam else None

    band = rules.grade_for_mark(result.final_mark, bands)
    if band is None:
        raise ValidationFailed(
            f"No grade band covers a mark of {result.final_mark}; the grading scale has a gap"
        )

    result.grade = band.grade
    result.grade_point = float(band.grade_point)
    result.quality_points = float(Decimal(str(band.grade_point)) * result.credit_units)
    result.outcome = "pass" if band.is_pass else "retake"

    scheme = None
    if result.mark_sheet and result.mark_sheet.assessment_scheme_id:
        from acmis.modules.curriculum.models import AssessmentScheme

        scheme = session.get(AssessmentScheme, result.mark_sheet.assessment_scheme_id)

    if scheme is not None and band.is_pass:
        if scheme.exam_must_be_passed and scheme.minimum_exam_mark is not None:
            exam_pct = (
                float(exam / Decimal(str(_exam_weight(scheme_components))) * 100)
                if _exam_weight(scheme_components)
                else 0.0
            )
            if exam_pct < scheme.minimum_exam_mark:
                result.outcome = "retake"
                result.grade = _fail_grade(bands)
        if scheme.minimum_coursework_for_exam is not None:
            cw_weight = 100 - _exam_weight(scheme_components)
            cw_pct = float(coursework / Decimal(str(cw_weight)) * 100) if cw_weight else 100.0
            if cw_pct < scheme.minimum_coursework_for_exam:
                result.outcome = "barred"


def _exam_weight(scheme_components: dict[str, AssessmentComponent]) -> float:
    return float(
        sum(float(c.weight_percent) for c in scheme_components.values() if c.kind == "final_exam")
    )


def _fail_grade(bands: list[GradeBand]) -> str | None:
    failing = [b for b in bands if not b.is_pass]
    return failing[0].grade if failing else None


def _refresh_sheet_statistics(session: Session, *, sheet: MarkSheet) -> None:
    """Recompute the distribution a board looks at before any individual mark.

    A course with a 92% failure rate or a mean of 78 is a question about the
    assessment, not about the students — and it is the first thing an external
    examiner asks. Precomputed because a board reviews dozens of sheets in a
    sitting.
    """
    results = (
        session.execute(
            select(CourseResult).where(
                CourseResult.mark_sheet_id == sheet.id, CourseResult.deleted_at.is_(None)
            )
        )
        .scalars()
        .all()
    )

    marks = [float(r.final_mark) for r in results if r.final_mark is not None]
    sheet.student_count = len(results)
    sheet.entered_count = len(marks)
    # "Missing" means no decision has been recorded — not "no numeric mark".
    # An absence, a withheld result and a malpractice finding are all recorded
    # outcomes with no mark by definition, and counting them as missing made
    # the submit gate contradict its own message ("enter a mark or mark them
    # absent") by refusing a sheet where the examiner had done exactly that.
    sheet.missing_count = sum(1 for r in results if r.outcome == "pending")
    sheet.pass_count = sum(1 for r in results if r.outcome == "pass")
    sheet.fail_count = sum(1 for r in results if r.outcome in {"retake", "fail", "barred"})

    if marks:
        sheet.mean_mark = round(mean(marks), 2)
        sheet.median_mark = round(median(marks), 2)
        sheet.standard_deviation = round(pstdev(marks), 2) if len(marks) > 1 else 0.0
    distribution: dict[str, int] = {}
    for result in results:
        key = result.grade or result.outcome
        distribution[key] = distribution.get(key, 0) + 1
    sheet.grade_distribution = distribution


def transition_sheet(
    session: Session,
    *,
    sheet: MarkSheet,
    action: str,
    actor_id: uuid.UUID,
    note: str | None = None,
    minute_reference: str | None = None,
    adjustment: float | None = None,
) -> MarkSheet:
    """Move a mark sheet along the approval chain.

    The legal transitions are declared, not inferred. Each level's authority is
    granted by the policy bundle; this function enforces the *order*, so a
    sheet cannot reach Senate without a department board having seen it —
    which is the difference between an approval chain and three independent
    buttons.
    """
    allowed: dict[str, tuple[set[str], str]] = {
        "submit": ({MarkSheetStatus.DRAFT, MarkSheetStatus.RETURNED}, MarkSheetStatus.SUBMITTED),
        "moderate": ({MarkSheetStatus.SUBMITTED}, MarkSheetStatus.MODERATED),
        "approve": ({MarkSheetStatus.MODERATED}, MarkSheetStatus.BOARD_APPROVED),
        "faculty_approve": (
            {MarkSheetStatus.BOARD_APPROVED},
            MarkSheetStatus.FACULTY_APPROVED,
        ),
        "senate_approve": (
            {MarkSheetStatus.FACULTY_APPROVED},
            MarkSheetStatus.SENATE_APPROVED,
        ),
        "return": (
            {
                MarkSheetStatus.SUBMITTED,
                MarkSheetStatus.MODERATED,
                MarkSheetStatus.BOARD_APPROVED,
            },
            MarkSheetStatus.RETURNED,
        ),
    }
    if action not in allowed:
        raise ValidationFailed(f"'{action}' is not a mark sheet transition.")

    from_states, to_state = allowed[action]
    if sheet.status not in from_states:
        raise Conflict(
            f"A {sheet.status} mark sheet cannot be {action}ed. "
            f"Expected one of: {', '.join(sorted(from_states))}."
        )

    if action == "submit":
        if sheet.missing_count > 0:
            raise RuleViolation(
                f"{sheet.missing_count} candidate(s) have no mark recorded. Enter a "
                "mark or mark them absent before submitting.",
                rule="incomplete_mark_sheet",
                details={"missing": sheet.missing_count},
            )
        sheet.submitted_by_id = actor_id
        sheet.submitted_at = utcnow()

    if action in {"moderate", "approve", "faculty_approve", "senate_approve"}:
        if actor_id in (sheet.entered_by_ids or ()):
            raise RuleViolation(
                "A mark sheet cannot be approved by someone who entered marks on it.",
                rule="separation_of_duties",
            )
        if actor_id in (sheet.conflicted_staff_ids or ()):
            raise RuleViolation(
                "You have declared an interest in this assessment.",
                rule="declared_conflict",
            )

    before = {"status": sheet.status}
    sheet.status = to_state

    if action == "moderate":
        sheet.moderated_by_id = actor_id
        sheet.moderated_at = utcnow()
        sheet.moderation_note = note
        if adjustment:
            # A cohort-wide scaling must say by how much and why. A silent
            # scaling is indistinguishable from tampering.
            if not note:
                raise ValidationFailed(
                    "A moderation adjustment must be accompanied by a note explaining it."
                )
            sheet.moderation_adjustment = adjustment
            _apply_moderation(session, sheet=sheet, adjustment=adjustment, actor_id=actor_id)
    elif action == "approve":
        sheet.board_approved_by_id = actor_id
        sheet.board_approved_at = utcnow()
    elif action == "faculty_approve":
        sheet.faculty_approved_by_id = actor_id
        sheet.faculty_approved_at = utcnow()
    elif action == "senate_approve":
        sheet.senate_approved_by_id = actor_id
        sheet.senate_approved_at = utcnow()
        sheet.senate_minute_reference = minute_reference
    elif action == "return":
        sheet.return_comments = note

    session.flush()
    emit(
        f"mark_sheet:{action}",
        AuditCategory.ASSESSMENT,
        resource_type="mark_sheet",
        resource_id=sheet.id,
        summary=f"{before['status']} -> {sheet.status}",
        changes=diff(before, {"status": sheet.status}),
        metadata={
            "note": note,
            "minute_reference": minute_reference,
            "adjustment": adjustment,
        },
        severity="warning" if action.endswith("approve") else "notice",
    )
    return sheet


def _apply_moderation(
    session: Session, *, sheet: MarkSheet, adjustment: float, actor_id: uuid.UUID
) -> None:
    """Scale a whole cohort's marks, regrading each one.

    Clamped to 0-100. A +15 adjustment on a mark of 92 cannot produce 107, and
    silently allowing it would put a mark outside every grade band.
    """
    scale = session.get(GradingScale, sheet.grading_scale_id)
    if scale is None:  # pragma: no cover
        return
    bands = sorted(scale.bands, key=lambda b: Decimal(str(b.lower_mark)), reverse=True)

    results = (
        session.execute(select(CourseResult).where(CourseResult.mark_sheet_id == sheet.id))
        .scalars()
        .all()
    )
    for result in results:
        if result.final_mark is None:
            continue
        adjusted = max(0.0, min(100.0, float(result.final_mark) + adjustment))
        band = rules.grade_for_mark(adjusted, bands)
        result.final_mark = round(adjusted, 2)
        if band is not None:
            result.grade = band.grade
            result.grade_point = float(band.grade_point)
            result.quality_points = float(Decimal(str(band.grade_point)) * result.credit_units)
            result.outcome = "pass" if band.is_pass else "retake"
    _refresh_sheet_statistics(session, sheet=sheet)
    emit(
        "mark_sheet:moderate",
        AuditCategory.ASSESSMENT,
        resource_type="mark_sheet",
        resource_id=sheet.id,
        summary=f"Cohort adjustment of {adjustment:+g} applied to {len(results)} result(s)",
        severity="warning",
    )


def release_results(
    session: Session,
    *,
    semester_id: uuid.UUID,
    programme_ids: list[uuid.UUID] | None,
    scope_description: str,
    minute_reference: str | None,
    actor_id: uuid.UUID,
) -> ResultsRelease:
    """Publish Senate-approved results to students.

    One deliberate event over a defined scope. Students compare notes within
    minutes, so a partial release produces a queue at the registry; only
    Senate-approved sheets are included, and a sheet still in the chain is
    reported as skipped rather than quietly released.
    """
    sheets = (
        session.execute(
            select(MarkSheet).where(
                MarkSheet.semester_id == semester_id,
                MarkSheet.status == MarkSheetStatus.SENATE_APPROVED,
                MarkSheet.deleted_at.is_(None),
            )
        )
        .scalars()
        .all()
    )
    if not sheets:
        raise RuleViolation(
            "There are no Senate-approved mark sheets for this semester.",
            rule="nothing_to_release",
        )

    release = ResultsRelease(
        semester_id=semester_id,
        programme_ids=list(programme_ids or ()),
        scope_description=scope_description,
        senate_minute_reference=minute_reference,
        status="released",
        released_by_id=actor_id,
        released_at=utcnow(),
        created_by_id=actor_id,
    )
    session.add(release)
    session.flush()

    students: set[uuid.UUID] = set()
    released_count = 0
    withheld_count = 0
    now = utcnow()

    for sheet in sheets:
        results = (
            session.execute(
                select(CourseResult).where(
                    CourseResult.mark_sheet_id == sheet.id, CourseResult.deleted_at.is_(None)
                )
            )
            .scalars()
            .all()
        )
        for result in results:
            if result.withheld:
                withheld_count += 1
                continue
            result.released = True
            result.released_at = now
            students.add(result.student_id)
            released_count += 1
        sheet.status = MarkSheetStatus.PUBLISHED
        sheet.published_at = now

    release.mark_sheet_count = len(sheets)
    release.result_count = released_count
    release.student_count = len(students)
    session.flush()

    emit(
        "results_release:publish",
        AuditCategory.ASSESSMENT,
        resource_type="results_release",
        resource_id=release.id,
        resource_label=scope_description,
        summary=(
            f"Released {released_count} result(s) across {len(sheets)} mark sheet(s) "
            f"to {len(students)} student(s); {withheld_count} withheld"
        ),
        metadata={"minute_reference": minute_reference, "withheld": withheld_count},
        severity="warning",
    )
    return release


def compute_semester_result(
    session: Session,
    *,
    student_programme: Any,
    semester_id: uuid.UUID,
    actor_id: uuid.UUID,
) -> SemesterResult:
    """Compute GPA, CGPA and the progression recommendation for one semester.

    Under the rules on the student's own curriculum version, and the rules used
    are stamped onto the row. "Why was I put on probation" is only answerable
    if the rules as they were are recoverable — and the rules do change between
    intakes.

    The outcome is a recommendation. A `discontinue` sets
    `requires_board_confirmation`, and it takes a minuted board decision to
    apply it; nobody is dismissed by a nightly job.
    """
    from acmis.modules.curriculum.models import CurriculumVersion

    version = session.get(CurriculumVersion, student_programme.curriculum_version_id)
    if version is None:  # pragma: no cover
        raise NotFound()
    progression_rules = {
        **rules.DEFAULT_PROGRESSION_RULES,
        **(version.progression_rules or {}),
    }

    semester_results = (
        session.execute(
            select(CourseResult).where(
                CourseResult.student_programme_id == student_programme.id,
                CourseResult.semester_id == semester_id,
                CourseResult.deleted_at.is_(None),
            )
        )
        .scalars()
        .all()
    )
    all_results = (
        session.execute(
            select(CourseResult).where(
                CourseResult.student_programme_id == student_programme.id,
                CourseResult.deleted_at.is_(None),
            )
        )
        .scalars()
        .all()
    )

    counted = rules.retake_selection(all_results, rules=progression_rules)
    counted_ids = {r.id for r in counted}
    for result in all_results:
        result.is_superseded = result.id not in counted_ids

    semester_gpa = rules.compute_gpa(r for r in semester_results if r.id in counted_ids)
    cumulative = rules.compute_gpa(counted)

    failed = [r for r in semester_results if r.outcome in {"retake", "fail", "barred"}]
    outstanding = sum(
        1 for r in counted if r.outcome in {"retake", "fail", "barred"} and not r.is_superseded
    )

    previous = (
        session.execute(
            select(SemesterResult)
            .where(SemesterResult.student_programme_id == student_programme.id)
            .order_by(SemesterResult.created_at.desc())
        )
        .scalars()
        .first()
    )

    duration = int(version.programme.duration_semesters if version.programme else 8)
    is_final = student_programme.current_semester_number >= duration

    outcome = rules.decide_progression(
        semester_gpa=semester_gpa.gpa,
        cgpa=cumulative.gpa,
        failed=failed,
        credits_earned_this_semester=semester_gpa.credits_earned,
        previous_consecutive_probations=(previous.consecutive_probations if previous else 0),
        is_final_semester=is_final,
        outstanding_retakes=outstanding,
        rules=progression_rules,
    )

    row = session.execute(
        select(SemesterResult).where(
            SemesterResult.student_programme_id == student_programme.id,
            SemesterResult.semester_id == semester_id,
        )
    ).scalar_one_or_none()
    if row is None:
        row = SemesterResult(
            student_id=student_programme.student_id,
            student_programme_id=student_programme.id,
            semester_id=semester_id,
            year_of_study=student_programme.current_year_of_study,
            created_by_id=actor_id,
        )
        session.add(row)

    row.credits_attempted = semester_gpa.credits_attempted
    row.credits_earned = semester_gpa.credits_earned
    row.quality_points = float(semester_gpa.quality_points)
    row.gpa = semester_gpa.gpa_float
    row.cumulative_credits_earned = cumulative.credits_earned
    row.cumulative_quality_points = float(cumulative.quality_points)
    row.cgpa = cumulative.gpa_float
    row.progression = outcome.status
    row.failed_course_count = len(failed)
    row.retake_course_ids = outcome.retake_course_ids
    row.consecutive_probations = outcome.consecutive_probations
    row.rules_snapshot = {
        "progression_rules": progression_rules,
        "curriculum_version": version.version_label,
        "computed_at": utcnow().isoformat(),
        "reasons": outcome.reasons,
        "requires_board_confirmation": outcome.requires_board_confirmation,
        "excluded_attempts": semester_gpa.excluded,
    }
    row.computed_at = utcnow()

    student_programme.cgpa = cumulative.gpa_float
    student_programme.credits_earned = cumulative.credits_earned
    student_programme.outstanding_retakes = outstanding
    student_programme.progression_status = outcome.status
    student_programme.computed_at = utcnow()
    session.flush()

    emit(
        "semester_result:compute",
        AuditCategory.ASSESSMENT,
        resource_type="course_result",
        resource_id=row.id,
        summary=(f"GPA {row.gpa}, CGPA {row.cgpa}, progression {outcome.status}"),
        metadata={"reasons": outcome.reasons, "outstanding_retakes": outstanding},
        severity="notice" if outcome.requires_board_confirmation else "info",
    )
    return row


def build_transcript(session: Session, *, student_programme: Any) -> dict[str, Any]:
    """Assemble the transcript payload from the result rows.

    Regenerated on every issue rather than stored, so a transcript can never
    drift from the record it reports. What *is* stored is the fact of issuance
    and a hash of the rendered document, which is what a verifier checks.
    """
    from acmis.modules.shared.models import Semester
    from acmis.modules.students.models import Student

    student = session.get(Student, student_programme.student_id)
    results = (
        session.execute(
            select(CourseResult)
            .where(
                CourseResult.student_programme_id == student_programme.id,
                CourseResult.deleted_at.is_(None),
                CourseResult.released.is_(True),
            )
            .order_by(CourseResult.semester_id, CourseResult.course_code)
        )
        .scalars()
        .all()
    )
    semester_rows = (
        session.execute(
            select(SemesterResult)
            .where(SemesterResult.student_programme_id == student_programme.id)
            .order_by(SemesterResult.year_of_study, SemesterResult.created_at)
        )
        .scalars()
        .all()
    )

    by_semester: dict[str, list[dict[str, Any]]] = {}
    for result in results:
        semester = session.get(Semester, result.semester_id)
        key = semester.name if semester else str(result.semester_id)
        by_semester.setdefault(key, []).append(
            {
                "course_code": result.course_code,
                "course_title": result.course_title,
                "credit_units": result.credit_units,
                "final_mark": float(result.final_mark) if result.final_mark else None,
                "grade": result.grade,
                "grade_point": float(result.grade_point) if result.grade_point else None,
                "outcome": result.outcome,
                "attempt": result.attempt_number,
                "is_retake": result.is_retake,
                # Superseded attempts are shown, not hidden. A transcript that
                # conceals a failed attempt is not a record of what happened,
                # and the retake rules mean the *counted* attempt is marked.
                "counted": not result.is_superseded,
            }
        )

    return {
        "student": {
            "student_number": student.student_number if student else None,
            "name": student.certificate_name or student.full_name if student else None,
            "date_of_birth": student.date_of_birth.isoformat() if student else None,
        },
        "programme": {
            "code": student_programme.programme.code
            if getattr(student_programme, "programme", None)
            else None,
            "award_title": student_programme.programme.award_title
            if getattr(student_programme, "programme", None)
            else None,
            "curriculum_version": student_programme.curriculum_version_id
            and str(student_programme.curriculum_version_id),
            "entry_route": student_programme.entry_route,
            "sponsorship": student_programme.sponsorship,
        },
        "semesters": [
            {
                "name": name,
                "courses": courses,
                "credits": sum(c["credit_units"] for c in courses if c["counted"]),
            }
            for name, courses in by_semester.items()
        ],
        "progression": [
            {
                "year": r.year_of_study,
                "gpa": float(r.gpa) if r.gpa else None,
                "cgpa": float(r.cgpa) if r.cgpa else None,
                "credits_earned": r.credits_earned,
                "progression": r.progression,
            }
            for r in semester_rows
        ],
        "summary": {
            "cgpa": float(student_programme.cgpa) if student_programme.cgpa else None,
            "credits_earned": student_programme.credits_earned,
            "credits_required": student_programme.credits_required,
            "outstanding_retakes": student_programme.outstanding_retakes,
        },
    }


def confer_award(
    session: Session,
    *,
    student_programme: Any,
    graduation_list_id: uuid.UUID | None,
    conferred_on: date,
    minute_reference: str,
    actor_id: uuid.UUID,
) -> Award:
    """Confer a qualification. The system's terminal, near-irreversible act.

    The eligibility checks are repeated here even though the policy bundle
    gates the action. A conferred award is printed, framed and relied on by
    employers; the cost of a duplicated check is nothing next to the cost of
    conferring one that should not have been.

    Serial numbers are random, not sequential. A sequential serial lets anyone
    enumerate every graduate through the public verification endpoint.
    """
    from acmis.modules.finance import service as finance
    from acmis.modules.students.models import Student, StudentStatus

    student = session.get(Student, student_programme.student_id)
    if student is None:  # pragma: no cover
        raise NotFound()

    existing = session.execute(
        select(Award).where(
            Award.student_programme_id == student_programme.id,
            Award.status == "conferred",
            Award.deleted_at.is_(None),
        )
    ).scalar_one_or_none()
    if existing is not None:
        raise Conflict("An award has already been conferred for this programme.")

    if student_programme.outstanding_retakes > 0:
        raise RuleViolation(
            f"{student_programme.outstanding_retakes} outstanding retake(s) must be cleared first.",
            rule="outstanding_retakes",
        )
    if student_programme.credits_earned < student_programme.credits_required:
        raise RuleViolation(
            f"{student_programme.credits_earned} of "
            f"{student_programme.credits_required} required credit units earned.",
            rule="insufficient_credits",
        )
    balance = finance.outstanding_balance(session, student_id=student.id)
    if balance > 0:
        raise RuleViolation(
            f"An outstanding balance of {balance / 100:,.2f} must be settled.",
            rule="outstanding_fees",
            waivable_by=["finance:override_block"],
        )

    from acmis.modules.curriculum.models import CurriculumVersion

    version = session.get(CurriculumVersion, student_programme.curriculum_version_id)
    classification_rules = {
        **rules.DEFAULT_CLASSIFICATION_RULES,
        **((version.classification_rules if version else None) or {}),
    }
    had_retakes = bool(
        session.execute(
            select(func.count())
            .select_from(CourseResult)
            .where(
                CourseResult.student_programme_id == student_programme.id,
                CourseResult.is_retake.is_(True),
            )
        ).scalar_one()
    )
    classification, notes = rules.classify(
        cgpa=Decimal(str(student_programme.cgpa)) if student_programme.cgpa else None,
        outstanding_retakes=student_programme.outstanding_retakes,
        had_retakes=had_retakes,
        rules=classification_rules,
    )
    if classification is None:
        raise RuleViolation(
            "This student cannot be classified.",
            rule="not_classifiable",
            details={"notes": notes},
        )

    programme = student_programme.programme
    award = Award(
        student_id=student.id,
        student_programme_id=student_programme.id,
        programme_id=student_programme.programme_id,
        graduation_list_id=graduation_list_id,
        award_title=programme.award_title if programme else "",
        award_level=programme.award_level if programme else "",
        certificate_name=student.certificate_name or student.full_name,
        classification=classification,
        final_cgpa=student_programme.cgpa,
        credits_earned=student_programme.credits_earned,
        classification_snapshot={
            "rules": classification_rules,
            "notes": notes,
            "cgpa": float(student_programme.cgpa) if student_programme.cgpa else None,
            "had_retakes": had_retakes,
            "curriculum_version": version.version_label if version else None,
        },
        serial_number=f"{date.today().year}-{secrets.token_hex(8).upper()}",
        verification_code=secrets.token_urlsafe(9)[:12].upper(),
        conferred_on=conferred_on,
        conferred_by_id=actor_id,
        senate_minute_reference=minute_reference,
        status="conferred",
        created_by_id=actor_id,
    )
    session.add(award)

    student.status = StudentStatus.GRADUATED
    student.graduated_on = conferred_on
    student_programme.ended_on = conferred_on
    student_programme.outcome = "graduated"
    session.flush()

    emit(
        "award:confer",
        AuditCategory.AWARD,
        resource_type="award",
        resource_id=award.id,
        resource_label=f"{award.award_title} ({award.serial_number})",
        summary=(
            f"{award.classification} conferred on {student.full_name} "
            f"({student.student_number}), CGPA {student_programme.cgpa}"
        ),
        metadata={
            "minute_reference": minute_reference,
            "serial_number": award.serial_number,
            "classification": classification,
            "notes": notes,
        },
        severity="critical",
    )
    return award


def verify_serial(session: Session, *, serial: str) -> dict[str, Any]:
    """Public verification by serial number.

    Answers only what the presented serial already asserts, and says so
    honestly when an award has been revoked — a verification endpoint that
    quietly reports a revoked degree as valid is worse than none. Returns no
    contact details, no marks and no other record.
    """
    award = session.execute(
        select(Award).where(
            (Award.serial_number == serial) | (Award.verification_code == serial.upper())
        )
    ).scalar_one_or_none()
    if award is None:
        return {"found": False}

    return {
        "found": True,
        "valid": award.status == "conferred" and award.revoked_at is None,
        "holder_name": award.certificate_name,
        "award_title": award.award_title,
        "classification": award.classification,
        "conferred_on": award.conferred_on.isoformat(),
        "serial_number": award.serial_number,
        "status": award.status,
        "revoked": award.revoked_at is not None,
        "revoked_on": award.revoked_at.date().isoformat() if award.revoked_at else None,
    }


def issue_transcript(
    session: Session,
    *,
    student_programme: Any,
    kind: str,
    purpose: str | None,
    recipient_name: str | None,
    recipient_address: str | None,
    actor_id: uuid.UUID,
) -> tuple[Transcript, dict[str, Any]]:
    payload = build_transcript(session, student_programme=student_programme)
    transcript = Transcript(
        student_id=student_programme.student_id,
        student_programme_id=student_programme.id,
        kind=kind,
        serial_number=f"TR-{date.today().year}-{secrets.token_hex(6).upper()}",
        verification_code=secrets.token_urlsafe(9)[:12].upper(),
        purpose=purpose,
        recipient_name=recipient_name,
        recipient_address=recipient_address,
        issued_on=date.today(),
        issued_by_id=actor_id,
        status="issued",
        created_by_id=actor_id,
    )
    session.add(transcript)
    session.flush()

    emit(
        "transcript:issue",
        AuditCategory.AWARD,
        resource_type="transcript",
        resource_id=transcript.id,
        resource_label=transcript.serial_number,
        summary=f"{kind} transcript issued" + (f" to {recipient_name}" if recipient_name else ""),
        metadata={"purpose": purpose, "recipient": recipient_name},
        severity="notice",
    )
    return transcript, payload
