"""Teaching, learning and online assessment operations."""

from __future__ import annotations

import random
import uuid
from datetime import date, datetime, timedelta
from decimal import Decimal
from statistics import mean, median, pstdev
from typing import Any

import structlog
from sqlalchemy import func, select
from sqlalchemy.orm import Session, selectinload

from acmis.core.abac import bulk_decide
from acmis.core.audit import AuditCategory, diff, emit
from acmis.core.errors import Conflict, Forbidden, NotFound, RuleViolation, ValidationFailed
from acmis.core.models import utcnow
from acmis.core.schemas import Capability
from acmis.core.security import constant_time_equals, hash_secret
from acmis.modules.learning import marking
from acmis.modules.learning.models import (
    AUTO_MARKED_KINDS,
    AssessmentItem,
    AssessmentKind,
    AssessmentStatus,
    Assignment,
    Attempt,
    AttemptResponse,
    AttemptStatus,
    CourseSpace,
    EngagementSnapshot,
    Material,
    MaterialView,
    OnlineAssessment,
    Question,
    QuestionBank,
    QuestionKind,
    Submission,
)

log = structlog.get_logger(__name__)


ASSESSMENT_ACTIONS = (
    "online_assessment:read",
    "online_assessment:update",
    "online_assessment:submit_for_review",
    "online_assessment:review",
    "online_assessment:open",
    "online_assessment:mark",
    "online_assessment:release",
    "online_assessment:push_marks",
)


def capabilities_for(ctx: Any, assessment: OnlineAssessment) -> list[Capability]:
    allowed = bulk_decide(
        engine=ctx.engine,
        actions=ASSESSMENT_ACTIONS,
        resource_type="online_assessment",
        resource=assessment,
    )
    return [Capability(action=a, allowed=v) for a, v in allowed.items()]


# ---------------------------------------------------------------------------
# Course spaces and materials
# ---------------------------------------------------------------------------


def ensure_space(
    session: Session, *, course_offering_id: uuid.UUID, actor_id: uuid.UUID
) -> CourseSpace:
    """Get or create the online space for an offering. Idempotent."""
    from acmis.modules.curriculum.models import CourseOffering

    existing = session.execute(
        select(CourseSpace).where(CourseSpace.course_offering_id == course_offering_id)
    ).scalar_one_or_none()
    if existing is not None:
        return existing

    offering = session.get(CourseOffering, course_offering_id)
    if offering is None or offering.deleted_at is not None:
        raise NotFound("That course offering does not exist.")

    space = CourseSpace(
        course_offering_id=course_offering_id,
        semester_id=offering.semester_id,
        department_ids=list(offering.department_ids or ()),
        faculty_ids=list(offering.faculty_ids or ()),
        created_by_id=actor_id,
    )
    session.add(space)
    session.flush()
    emit(
        "course_space:create",
        AuditCategory.CURRICULUM,
        resource_type="course_space",
        resource_id=space.id,
        resource_label=f"{offering.course.code} space" if offering.course else "course space",
        summary="Course space created",
    )
    return space


def publish_material(
    session: Session,
    *,
    space: CourseSpace,
    payload: dict[str, Any],
    actor_id: uuid.UUID,
) -> Material:
    if space.archived_at is not None:
        raise Conflict("This course space is archived and cannot take new material.")

    material = Material(space_id=space.id, created_by_id=actor_id, **payload)
    session.add(material)
    session.flush()
    emit(
        "material:create",
        AuditCategory.CURRICULUM,
        resource_type="material",
        resource_id=material.id,
        resource_label=material.title,
        summary=f"{material.kind} published"
        + (f" for week {material.week_number}" if material.week_number else ""),
        metadata={"published": material.is_published},
    )
    return material


def record_material_view(
    session: Session,
    *,
    material: Material,
    student_id: uuid.UUID,
    seconds: int = 0,
    downloaded: bool = False,
    completion_percent: int | None = None,
) -> MaterialView:
    """Record that a student opened a material.

    Aggregated per student per material, not one row per open. The question
    anyone asks is "has this student engaged with week 6", and a row per click
    on a 20,000-student institution is tens of millions of rows answering a
    question nobody asks.

    Not routed through the audit trail. A student reading their own course
    notes is not an access to somebody's record, and logging it there would
    bury the accesses that matter under millions of page views.
    """
    view = session.execute(
        select(MaterialView).where(
            MaterialView.material_id == material.id,
            MaterialView.student_id == student_id,
        )
    ).scalar_one_or_none()

    now = utcnow()
    if view is None:
        view = MaterialView(
            material_id=material.id,
            student_id=student_id,
            first_viewed_at=now,
            last_viewed_at=now,
            view_count=1,
            total_seconds=max(0, seconds),
            downloaded=downloaded,
            completion_percent=completion_percent,
        )
        session.add(view)
        material.unique_viewer_count += 1
    else:
        view.last_viewed_at = now
        view.view_count += 1
        view.total_seconds += max(0, seconds)
        view.downloaded = view.downloaded or downloaded
        if completion_percent is not None:
            view.completion_percent = max(view.completion_percent or 0, completion_percent)

    material.view_count += 1
    session.flush()
    return view


# ---------------------------------------------------------------------------
# Authoring
# ---------------------------------------------------------------------------


def create_question(
    session: Session, *, bank: QuestionBank, payload: dict[str, Any], actor_id: uuid.UUID
) -> Question:
    """Add a question to a bank, validating its answer key.

    The key is validated on the way in because an invalid one is only
    discovered otherwise when a candidate's answer cannot be marked — in the
    middle of an examination. `validate_answer_key` is the same function the
    review step runs over a whole paper.
    """
    options = payload.pop("options", []) or []
    question = Question(bank_id=bank.id, created_by_id=actor_id, **payload)
    session.add(question)
    session.flush()

    for index, option in enumerate(options):
        from acmis.modules.learning.models import QuestionOption

        session.add(
            QuestionOption(
                question_id=question.id,
                label=option.get("label") or chr(ord("A") + index),
                body=option["body"],
                is_correct=bool(option.get("is_correct", False)),
                feedback=option.get("feedback"),
                sequence=index,
                pin_position=bool(option.get("pin_position", False)),
                created_by_id=actor_id,
            )
        )
    session.flush()
    session.refresh(question)

    problems = validate_answer_key(question)
    if problems:
        raise ValidationFailed(
            "This question cannot be marked as written.",
            code="invalid_answer_key",
            details={"problems": problems},
        )

    bank.question_count = session.execute(
        select(func.count())
        .select_from(Question)
        .where(Question.bank_id == bank.id, Question.deleted_at.is_(None))
    ).scalar_one()

    emit(
        "question:create",
        AuditCategory.ASSESSMENT,
        resource_type="question",
        resource_id=question.id,
        resource_label=f"{question.kind}: {question.stem[:60]}",
        summary=f"Question added to bank {bank.code}",
        metadata={"kind": question.kind, "marks": float(question.marks)},
    )
    return question


def validate_answer_key(question: Question) -> list[str]:
    """Check that a question can actually be marked.

    Run when a question is saved and again over every question when a paper is
    submitted for review. The failures it catches are the ones that are
    invisible until a candidate hits them: a multiple-choice question with no
    correct option, a numeric with no expected value, a matching question with
    an empty map.
    """
    problems: list[str] = []
    key = question.answer_key or {}
    kind = question.kind

    if kind in {QuestionKind.MULTIPLE_CHOICE, QuestionKind.TRUE_FALSE}:
        correct = [o for o in question.options if o.is_correct]
        if len(question.options) < 2:
            problems.append("Needs at least two options.")
        if len(correct) != 1:
            problems.append(f"Needs exactly one correct option; {len(correct)} are marked correct.")
    elif kind == QuestionKind.MULTIPLE_RESPONSE:
        correct = [o for o in question.options if o.is_correct]
        if len(correct) < 2:
            problems.append(
                "A multiple-response question needs at least two correct options; "
                "use multiple choice for one."
            )
        if len(correct) == len(question.options):
            problems.append("Every option is marked correct, so the question tests nothing.")
    elif kind == QuestionKind.SHORT_ANSWER:
        if not key.get("accepted") and not key.get("pattern"):
            problems.append("Needs accepted answers or a pattern.")
        if int(key.get("max_edit_distance", 0)) > 3:
            problems.append(
                "An edit-distance tolerance above 3 will accept genuinely wrong answers."
            )
    elif kind == QuestionKind.NUMERIC:
        if key.get("value") is None:
            problems.append("Needs an expected value.")
        if key.get("tolerance") is None and key.get("relative_tolerance_percent") is None:
            problems.append(
                "Needs a tolerance. An exact numeric comparison marks 9.8 wrong when the "
                "answer is 9.81."
            )
    elif kind == QuestionKind.FILL_IN_BLANK:
        if not key.get("blanks"):
            problems.append("Needs a blanks map.")
    elif kind == QuestionKind.MATCHING:
        if not key.get("pairs"):
            problems.append("Needs a pairs map.")
    elif kind == QuestionKind.ORDERING:
        if len(key.get("order", ())) < 2:
            problems.append("Needs at least two items in the expected order.")
    elif kind in {QuestionKind.ESSAY, QuestionKind.FILE_UPLOAD, QuestionKind.CODE}:
        if not question.rubric:
            # A warning rather than a refusal: some faculties mark essays
            # holistically. But an unrubricked essay marked by three people
            # produces three different marks, so it is surfaced.
            problems.append(
                "No rubric. Human-marked questions without one produce inconsistent "
                "marking between markers."
            )

    if float(question.negative_marks or 0) > float(question.marks):
        problems.append("The negative mark exceeds the marks available.")
    return problems


def build_assessment(
    session: Session,
    *,
    space: CourseSpace,
    payload: dict[str, Any],
    actor_id: uuid.UUID,
) -> OnlineAssessment:
    assessment = OnlineAssessment(
        space_id=space.id,
        course_offering_id=space.course_offering_id,
        department_ids=list(space.department_ids or ()),
        faculty_ids=list(space.faculty_ids or ()),
        authored_by_id=actor_id,
        status=AssessmentStatus.DRAFT,
        created_by_id=actor_id,
        **payload,
    )
    session.add(assessment)
    session.flush()
    emit(
        "online_assessment:create",
        AuditCategory.ASSESSMENT,
        resource_type="online_assessment",
        resource_id=assessment.id,
        resource_label=assessment.title,
        summary=f"{assessment.kind} '{assessment.title}' drafted",
    )
    return assessment


def bank_has_open_paper(session: Session, *, bank_id: uuid.UUID) -> bool:
    """Is any question from this bank on a paper candidates can sit?

    Asked before a bank is exported. An export carries the answer keys, and a
    key that leaves the building while a paper is open is the one disclosure
    that invalidates a whole cohort's sitting — so the deny rule needs this
    fact, and a fact no code supplies is a rule that never fires.

    Both shapes of item count: a fixed item naming a question in this bank,
    and a pooled item drawing from the bank at large.
    """
    live = (AssessmentStatus.SCHEDULED, AssessmentStatus.OPEN)
    fixed = (
        select(func.count())
        .select_from(AssessmentItem)
        .join(OnlineAssessment, OnlineAssessment.id == AssessmentItem.assessment_id)
        .join(Question, Question.id == AssessmentItem.question_id)
        .where(Question.bank_id == bank_id, OnlineAssessment.status.in_(live))
    )
    pooled = (
        select(func.count())
        .select_from(AssessmentItem)
        .join(OnlineAssessment, OnlineAssessment.id == AssessmentItem.assessment_id)
        .where(AssessmentItem.bank_id == bank_id, OnlineAssessment.status.in_(live))
    )
    return bool(session.execute(fixed).scalar_one() or session.execute(pooled).scalar_one())


def recompute_total_marks(session: Session, *, assessment: OnlineAssessment) -> float:
    """The denominator every candidate's percentage is divided by.

    In Decimal, not float: a paper of thirteen 2.5-mark questions must total
    32.5, and a candidate who is told 79% when the arithmetic says 80% has a
    complaint that is expensive to answer.
    """
    total = Decimal(0)
    for item in assessment.items:
        if item.mode == "pooled":
            # A pooled item's marks are declared on the item, because which
            # questions get drawn is not known until a candidate starts.
            # `submit_for_review` refuses a pooled item that declares none.
            total += Decimal(str(item.marks_override or 0)) * item.draw_count
        elif item.marks_override is not None:
            total += Decimal(str(item.marks_override))
        elif item.question_id:
            question = session.get(Question, item.question_id)
            total += Decimal(str(question.marks)) if question else Decimal(0)
    assessment.total_marks = float(total)
    session.flush()
    return float(total)


def submit_for_review(
    session: Session, *, assessment: OnlineAssessment, actor_id: uuid.UUID
) -> OnlineAssessment:
    """Send a paper for a second pair of eyes.

    Everything checkable is checked here, because the failures are cheap now
    and expensive later: a typo in a stem is a complaint, a wrong answer key
    is an appeal, and a paper whose marks do not total what candidates were
    told is a re-sit.
    """
    if assessment.status not in {AssessmentStatus.DRAFT, AssessmentStatus.REVIEW}:
        raise Conflict(f"A {assessment.status} assessment cannot be submitted for review.")
    if not assessment.items:
        raise RuleViolation("This assessment has no questions.", rule="empty_assessment")

    problems: list[dict[str, Any]] = []
    for item in assessment.items:
        if item.mode == "fixed" and item.question_id:
            question = session.get(Question, item.question_id)
            if question is None or not question.is_active:
                problems.append(
                    {"sequence": item.sequence, "problem": "question is missing or retired"}
                )
                continue
            for problem in validate_answer_key(question):
                problems.append({"sequence": item.sequence, "problem": problem})
        elif item.mode == "pooled":
            if item.marks_override is None:
                problems.append(
                    {
                        "sequence": item.sequence,
                        "problem": "a pooled item must declare its marks — the drawn "
                        "questions are not known until a candidate starts",
                    }
                )
            available = _count_pool(session, item)
            if available < item.draw_count:
                problems.append(
                    {
                        "sequence": item.sequence,
                        "problem": f"the pool has {available} matching question(s) but "
                        f"{item.draw_count} are drawn",
                    }
                )

    if assessment.counts_for_credit and assessment.max_attempts > 1:
        problems.append(
            {
                "sequence": 0,
                "problem": "an assessment that counts toward the course result should "
                "allow one attempt",
            }
        )
    if assessment.counts_for_credit and assessment.score_visibility == "immediately":
        problems.append(
            {
                "sequence": 0,
                "problem": "showing scores immediately on an assessment that counts lets "
                "candidates compare answers before marking is complete",
            }
        )

    if problems:
        raise RuleViolation(
            "This assessment is not ready for review.",
            rule="assessment_not_ready",
            details={"problems": problems},
        )

    recompute_total_marks(session, assessment=assessment)
    before = {"status": assessment.status}
    assessment.status = AssessmentStatus.REVIEW
    session.flush()
    emit(
        "online_assessment:submit_for_review",
        AuditCategory.ASSESSMENT,
        resource_type="online_assessment",
        resource_id=assessment.id,
        resource_label=assessment.title,
        summary=f"Submitted for review: {len(assessment.items)} item(s), "
        f"{assessment.total_marks} marks",
        changes=diff(before, {"status": assessment.status}),
    )
    return assessment


def _count_pool(session: Session, item: AssessmentItem) -> int:
    stmt = (
        select(func.count())
        .select_from(Question)
        .where(
            Question.bank_id == item.bank_id,
            Question.is_active.is_(True),
            Question.deleted_at.is_(None),
        )
    )
    filters = item.draw_filters or {}
    if topic := filters.get("topic"):
        stmt = stmt.where(Question.topic == topic)
    if difficulty := filters.get("difficulty"):
        stmt = stmt.where(Question.difficulty == difficulty)
    if kind := filters.get("kind"):
        stmt = stmt.where(Question.kind == kind)
    if level := filters.get("cognitive_level"):
        stmt = stmt.where(Question.cognitive_level == level)
    return int(session.execute(stmt).scalar_one())


def review_assessment(
    session: Session,
    *,
    assessment: OnlineAssessment,
    approve: bool,
    comments: str | None,
    actor_id: uuid.UUID,
) -> OnlineAssessment:
    """Approve or return a paper. The reviewer cannot be the author.

    Same principle as a mark sheet: the person who wrote the questions is the
    last person able to spot that one of them is ambiguous.
    """
    if assessment.status != AssessmentStatus.REVIEW:
        raise Conflict("This assessment is not awaiting review.")
    if assessment.authored_by_id == actor_id:
        raise RuleViolation(
            "An assessment must be reviewed by someone other than its author.",
            rule="separation_of_duties",
        )

    before = {"status": assessment.status}
    assessment.reviewed_by_id = actor_id
    assessment.reviewed_at = utcnow()
    assessment.review_comments = comments
    assessment.status = AssessmentStatus.SCHEDULED if approve else AssessmentStatus.DRAFT
    session.flush()

    emit(
        "online_assessment:review",
        AuditCategory.ASSESSMENT,
        resource_type="online_assessment",
        resource_id=assessment.id,
        resource_label=assessment.title,
        summary="Approved for scheduling" if approve else f"Returned: {comments}",
        changes=diff(before, {"status": assessment.status}),
        severity="notice",
    )
    return assessment


# ---------------------------------------------------------------------------
# Sitting an assessment
# ---------------------------------------------------------------------------


def start_attempt(
    session: Session,
    *,
    assessment: OnlineAssessment,
    student_id: uuid.UUID,
    password: str | None,
    ip_address: str | None,
    user_agent: str | None,
) -> Attempt:
    """Open an attempt, drawing and freezing this candidate's paper.

    Several checks that each exist because of a specific failure:

    * **Registration.** A candidate must be registered for the offering. Marks
      with no registration behind them are marks nobody can place on a
      transcript.
    * **Window and attempts.** Checked server-side; a client-side timer is a
      suggestion.
    * **Password and address.** For an invigilated sitting, so a paper meant to
      be taken in a supervised laboratory cannot be sat from a hostel.
    * **Accommodations.** Extra time comes from the student's own record, so an
      entitlement granted once by the disability office applies to every
      assessment automatically rather than being remembered per paper.

    The drawn paper is frozen onto the attempt. A resumed attempt after a
    dropped connection must show the same questions in the same order — a
    reshuffle on resume looks, to a candidate, exactly like the system losing
    their answers.
    """
    from acmis.modules.students.models import RegistrationCourse, Student

    if not assessment.is_open_now():
        raise RuleViolation(
            "This assessment is not open."
            if assessment.status != AssessmentStatus.OPEN
            else "This assessment's window has closed.",
            rule="assessment_not_open",
        )

    registered = session.execute(
        select(func.count())
        .select_from(RegistrationCourse)
        .where(
            RegistrationCourse.student_id == student_id,
            RegistrationCourse.course_offering_id == assessment.course_offering_id,
            RegistrationCourse.dropped_at.is_(None),
            RegistrationCourse.withdrawn_at.is_(None),
            RegistrationCourse.deleted_at.is_(None),
        )
    ).scalar_one()
    if not registered and assessment.kind != AssessmentKind.PRACTICE:
        raise Forbidden("You are not registered for this course.")

    if assessment.access_password_hash and (
        not password
        or not constant_time_equals(hash_secret(password), assessment.access_password_hash)
    ):
        raise Forbidden("That access code is not correct.")

    if assessment.allowed_ip_ranges and ip_address:
        import ipaddress

        allowed = False
        try:
            address = ipaddress.ip_address(ip_address)
            allowed = any(
                address in ipaddress.ip_network(entry, strict=False)
                for entry in assessment.allowed_ip_ranges
            )
        except ValueError:
            allowed = False
        if not allowed:
            raise Forbidden("This assessment can only be sat from an approved location.")

    live = session.execute(
        select(Attempt).where(
            Attempt.assessment_id == assessment.id,
            Attempt.student_id == student_id,
            Attempt.status == AttemptStatus.IN_PROGRESS,
        )
    ).scalar_one_or_none()
    if live is not None:
        # Resume rather than start afresh, and count the resumption. A dropped
        # connection is common; losing the paper to it is not acceptable.
        live.resumption_count += 1
        live.last_activity_at = utcnow()
        live.integrity_events = [
            *(live.integrity_events or ()),
            {"kind": "resumed", "at": utcnow().isoformat(), "ip": ip_address},
        ]
        session.flush()
        return live

    used = session.execute(
        select(func.count())
        .select_from(Attempt)
        .where(
            Attempt.assessment_id == assessment.id,
            Attempt.student_id == student_id,
            Attempt.status != AttemptStatus.VOIDED,
        )
    ).scalar_one()
    if used >= assessment.max_attempts:
        raise RuleViolation(
            f"You have used all {assessment.max_attempts} permitted attempt(s).",
            rule="attempts_exhausted",
        )

    student = session.get(Student, student_id)
    extra_minutes = 0
    extra_reason: str | None = None
    if student is not None and student.exam_accommodations:
        extra_minutes, extra_reason = _accommodation_minutes(
            student.exam_accommodations, assessment.duration_minutes
        )

    now = utcnow()
    expires: datetime | None = None
    if assessment.duration_minutes:
        expires = now + timedelta(minutes=assessment.duration_minutes + extra_minutes)
        if assessment.closes_at and expires > assessment.closes_at:
            # A late starter gets what is left of the window, not the full
            # duration past the close. Extra time for an entitled candidate is
            # allowed to run past it — an accommodation that the close time
            # silently cancels is not an accommodation.
            expires = max(assessment.closes_at, now) if extra_minutes else assessment.closes_at

    paper = _draw_paper(session, assessment=assessment)
    attempt = Attempt(
        assessment_id=assessment.id,
        student_id=student_id,
        attempt_number=used + 1,
        status=AttemptStatus.IN_PROGRESS,
        started_at=now,
        expires_at=expires,
        last_activity_at=now,
        extra_time_minutes=extra_minutes,
        extra_time_reason=extra_reason,
        presented_paper=paper,
        counts_for_grade=assessment.kind != AssessmentKind.PRACTICE,
        ip_address=ip_address,
        user_agent=(user_agent or "")[:500] or None,
        created_by_id=student_id,
    )
    session.add(attempt)
    session.flush()

    for index, entry in enumerate(paper["questions"]):
        session.add(
            AttemptResponse(
                attempt_id=attempt.id,
                item_id=uuid.UUID(entry["item_id"]) if entry.get("item_id") else None,
                question_id=uuid.UUID(entry["question_id"]),
                question_revision=int(entry.get("revision", 1)),
                sequence=index,
                marks_available=entry["marks"],
                created_by_id=student_id,
            )
        )
    assessment.attempt_count += 1
    session.flush()

    emit(
        "assessment_attempt:start",
        AuditCategory.ASSESSMENT,
        resource_type="assessment_attempt",
        resource_id=attempt.id,
        resource_label=f"{assessment.title} attempt {attempt.attempt_number}",
        summary=(
            f"Attempt started, {len(paper['questions'])} question(s)"
            + (f", +{extra_minutes} min accommodation" if extra_minutes else "")
        ),
        metadata={"expires_at": expires.isoformat() if expires else None},
    )
    return attempt


def _accommodation_minutes(
    accommodations: str, duration_minutes: int | None
) -> tuple[int, str | None]:
    """Read extra time from the student's recorded accommodations.

    Parsed from the text the disability office wrote, looking for the two
    conventional forms: "25% extra time" and "+15 minutes". Deliberately
    conservative — an unparseable note grants nothing and is left for the
    examinations office to handle by hand, rather than guessing at an
    entitlement.
    """
    import re

    text = accommodations.lower()
    if match := re.search(r"(\d{1,3})\s*%\s*extra", text):
        percent = int(match.group(1))
        if duration_minutes:
            return round(duration_minutes * percent / 100), f"{percent}% extra time"
    if match := re.search(r"\+?\s*(\d{1,3})\s*(?:min|minutes)\s*extra", text):
        return int(match.group(1)), f"{match.group(1)} minutes extra time"
    return 0, None


def _draw_paper(session: Session, *, assessment: OnlineAssessment) -> dict[str, Any]:
    """Compose one candidate's paper and freeze it.

    Pooled items are drawn here. `random` rather than a cryptographic source
    on purpose: this is fair sampling, not a secret, and the drawn set is
    recorded anyway. What matters is that it is recorded — an undrawn record
    makes "which question was my question 4" unanswerable.
    """
    questions: list[dict[str, Any]] = []
    # A question must not appear twice on one paper — the response table
    # enforces one row per (attempt, question), and a candidate seeing the
    # same question twice is a visible defect regardless. Fixed items are
    # collected first so a pooled draw cannot pull one of them again, which is
    # exactly what happens when a pool's filter overlaps the fixed selection.
    used: set[uuid.UUID] = {
        item.question_id
        for item in assessment.items
        if item.mode == "fixed" and item.question_id is not None
    }

    for item in assessment.items:
        drawn: list[Question] = []
        if item.mode == "fixed" and item.question_id:
            question = session.get(Question, item.question_id)
            if question is not None:
                drawn = [question]
        else:
            stmt = select(Question).where(
                Question.bank_id == item.bank_id,
                Question.is_active.is_(True),
                Question.deleted_at.is_(None),
            )
            filters = item.draw_filters or {}
            if topic := filters.get("topic"):
                stmt = stmt.where(Question.topic == topic)
            if difficulty := filters.get("difficulty"):
                stmt = stmt.where(Question.difficulty == difficulty)
            if kind := filters.get("kind"):
                stmt = stmt.where(Question.kind == kind)
            if level := filters.get("cognitive_level"):
                stmt = stmt.where(Question.cognitive_level == level)
            pool = [
                question
                for question in session.execute(
                    stmt.options(selectinload(Question.options))
                ).scalars()
                if question.id not in used
            ]
            drawn = random.sample(pool, min(item.draw_count, len(pool)))
            if len(drawn) < item.draw_count:
                # Short draw. Logged rather than raised: a candidate mid-paper
                # must not be blocked by an authoring problem, and the review
                # step already refuses a paper whose pool is too small — this
                # only fires when questions were retired between review and
                # sitting.
                log.warning(
                    "assessment_pool_short",
                    assessment=str(assessment.id),
                    item=str(item.id),
                    wanted=item.draw_count,
                    available=len(pool),
                )

        for question in drawn:
            used.add(question.id)
            marks = float(item.marks_override or question.marks)
            option_order = [o.label for o in question.options]
            if assessment.shuffle_options and question.options:
                pinned = [o.label for o in question.options if o.pin_position]
                movable = [o.label for o in question.options if not o.pin_position]
                random.shuffle(movable)
                # Pinned options keep their place: "None of the above" shuffled
                # into position two is a broken question.
                option_order = movable + pinned
            questions.append(
                {
                    "item_id": str(item.id),
                    "question_id": str(question.id),
                    "revision": question.revision,
                    "marks": marks,
                    "section": item.section,
                    "option_order": option_order,
                }
            )

    if assessment.shuffle_questions:
        # Shuffle within a section, never across. Sections exist because the
        # paper has a structure — "Section A: theory" — and mixing them
        # destroys it.
        by_section: dict[str | None, list[dict[str, Any]]] = {}
        for entry in questions:
            by_section.setdefault(entry.get("section"), []).append(entry)
        questions = []
        for section in sorted(by_section, key=lambda s: (s is None, s or "")):
            group = by_section[section]
            random.shuffle(group)
            questions.extend(group)

    return {
        "drawn_at": utcnow().isoformat(),
        "shuffled": assessment.shuffle_questions,
        "questions": questions,
    }


def save_response(
    session: Session,
    *,
    attempt: Attempt,
    question_id: uuid.UUID,
    answer: dict[str, Any],
    seconds_spent: int = 0,
    flagged: bool = False,
) -> AttemptResponse:
    """Save one answer, immediately.

    Saved as given rather than at submission. A power cut in the third hour of
    an examination must not cost a candidate their paper, and in the
    environments this system is built for that is not hypothetical.
    """
    if attempt.status != AttemptStatus.IN_PROGRESS:
        raise Conflict("This attempt is no longer open.")

    now = utcnow()
    if attempt.expires_at and now > attempt.expires_at:
        # Expire on the way in rather than refusing silently, so the candidate
        # gets a clear answer and the attempt is marked from what was saved.
        expire_attempt(session, attempt=attempt)
        raise Conflict("Your time for this assessment has ended.")

    response = session.execute(
        select(AttemptResponse).where(
            AttemptResponse.attempt_id == attempt.id,
            AttemptResponse.question_id == question_id,
        )
    ).scalar_one_or_none()
    if response is None:
        raise NotFound("That question is not part of this attempt.")

    response.answer = answer
    response.answered_at = now
    response.seconds_spent += max(0, seconds_spent)
    response.flagged = flagged
    attempt.last_activity_at = now
    session.flush()
    return response


def record_integrity_event(
    session: Session, *, attempt: Attempt, kind: str, detail: dict[str, Any] | None = None
) -> None:
    """Record a signal. Never a verdict.

    A focus loss in Gulu and a candidate opening another tab are
    indistinguishable from the server. So these are recorded for an
    invigilator to read and weigh, and nothing in the system acts on them: a
    platform that auto-fails on a dropped connection will fail honest students
    in exactly the places where connectivity is worst.
    """
    attempt.integrity_events = [
        *(attempt.integrity_events or ()),
        {"kind": kind, "at": utcnow().isoformat(), **(detail or {})},
    ]
    if kind == "focus_loss":
        attempt.focus_loss_count += 1
    session.flush()


def submit_attempt(
    session: Session, *, attempt: Attempt, actor_id: uuid.UUID, auto_mark: bool = True
) -> Attempt:
    if attempt.status != AttemptStatus.IN_PROGRESS:
        raise Conflict("This attempt has already been submitted.")

    attempt.status = AttemptStatus.SUBMITTED
    attempt.submitted_at = utcnow()
    session.flush()

    assessment = session.get(OnlineAssessment, attempt.assessment_id)
    if assessment is not None:
        assessment.submitted_count += 1

    if auto_mark:
        auto_mark_attempt(session, attempt=attempt)

    emit(
        "assessment_attempt:submit",
        AuditCategory.ASSESSMENT,
        resource_type="assessment_attempt",
        resource_id=attempt.id,
        summary=(
            f"Submitted; auto-marked {attempt.auto_score} of "
            f"{assessment.total_marks if assessment else '?'}"
        ),
        metadata={
            "answered": sum(1 for r in attempt.responses if r.answered_at),
            "focus_losses": attempt.focus_loss_count,
        },
    )
    return attempt


def expire_attempt(session: Session, *, attempt: Attempt) -> Attempt:
    """Close an attempt whose time ran out, keeping what was answered.

    Marked, not discarded. A candidate who ran out of time has still answered
    eight questions, and throwing them away would be indefensible.
    """
    if attempt.status != AttemptStatus.IN_PROGRESS:
        return attempt
    attempt.status = AttemptStatus.EXPIRED
    attempt.submitted_at = utcnow()
    session.flush()
    auto_mark_attempt(session, attempt=attempt)
    emit(
        "assessment_attempt:expire",
        AuditCategory.ASSESSMENT,
        resource_type="assessment_attempt",
        resource_id=attempt.id,
        summary="Time expired; answers given have been marked",
        severity="notice",
    )
    return attempt


def auto_mark_attempt(session: Session, *, attempt: Attempt) -> Attempt:
    """Mark every objective response. Leaves the rest for a human.

    A partially auto-marked attempt is the normal case for a mixed paper, and
    `pending_manual_marking` on the assessment is what the marking queue reads.
    """
    total = Decimal(0)
    pending = 0

    responses = (
        session.execute(
            select(AttemptResponse)
            .options(selectinload(AttemptResponse.attempt))
            .where(AttemptResponse.attempt_id == attempt.id)
        )
        .scalars()
        .all()
    )

    for response in responses:
        question = session.execute(
            select(Question)
            .options(selectinload(Question.options))
            .where(Question.id == response.question_id)
        ).scalar_one_or_none()
        if question is None:
            continue

        if question.kind not in AUTO_MARKED_KINDS:
            pending += 1
            continue

        awarded, is_correct, note = marking.mark_response(
            kind=question.kind,
            marks=response.marks_available or question.marks,
            negative_marks=question.negative_marks,
            answer_key=question.answer_key or {},
            options=[
                {
                    "label": o.label,
                    "body": o.body,
                    "is_correct": o.is_correct,
                    "feedback": o.feedback,
                }
                for o in question.options
            ],
            answer=response.answer or {},
        )
        response.marks_awarded = float(awarded)
        response.is_correct = is_correct
        response.marked_by = "auto"
        response.marker_comment = note
        total += awarded

        question.times_answered += 1
        if is_correct:
            # Facility is recomputed properly in `refresh_item_statistics`;
            # this keeps the running count that feeds it.
            pass

    attempt.auto_score = float(max(Decimal(0), total))
    attempt.manual_score = attempt.manual_score or None
    _finalise_attempt_score(session, attempt=attempt, pending_manual=pending)

    assessment = session.get(OnlineAssessment, attempt.assessment_id)
    if assessment is not None:
        assessment.pending_manual_marking = session.execute(
            select(func.count())
            .select_from(AttemptResponse)
            .join(Attempt, AttemptResponse.attempt_id == Attempt.id)
            .where(
                Attempt.assessment_id == assessment.id,
                Attempt.status.in_([AttemptStatus.SUBMITTED, AttemptStatus.EXPIRED]),
                AttemptResponse.marks_awarded.is_(None),
            )
        ).scalar_one()
    session.flush()
    return attempt


def _finalise_attempt_score(session: Session, *, attempt: Attempt, pending_manual: int) -> None:
    """Total an attempt, but only call it marked when nothing is pending.

    An attempt with an essay still to mark has a provisional total and stays
    `submitted`. Calling it `marked` would let it be released with a third of
    the paper unmarked, which is the mistake that produces a cohort of
    surprisingly low scores.
    """
    manual = Decimal(str(attempt.manual_score or 0))
    auto = Decimal(str(attempt.auto_score or 0))
    attempt.total_score = float(auto + manual)

    assessment = session.get(OnlineAssessment, attempt.assessment_id)
    if assessment and assessment.total_marks:
        attempt.percentage = round(
            float(Decimal(str(attempt.total_score)) / Decimal(str(assessment.total_marks)) * 100),
            2,
        )

    fully_marked = pending_manual == 0 and attempt.status in {
        AttemptStatus.SUBMITTED,
        AttemptStatus.EXPIRED,
    }
    if fully_marked:
        attempt.status = AttemptStatus.MARKED
        attempt.marked_at = utcnow()
    session.flush()


def mark_response_manually(
    session: Session,
    *,
    response: AttemptResponse,
    marks: float,
    comment: str | None,
    rubric_scores: list[dict[str, Any]] | None,
    actor_id: uuid.UUID,
) -> AttemptResponse:
    """Award marks for an essay, upload or code answer.

    Refuses a mark above what the question is worth. Obvious, and worth
    enforcing: a marker working through 200 scripts and typing 15 into a
    10-mark box produces a score above 100% that then propagates into a
    component score and a GPA.
    """
    available = Decimal(str(response.marks_available or 0))
    awarded = Decimal(str(marks))
    if awarded < 0 or awarded > available:
        raise ValidationFailed(
            f"The mark must be between 0 and {available}.",
            code="mark_out_of_range",
        )

    before = {"marks_awarded": float(response.marks_awarded or 0)}
    response.marks_awarded = float(awarded)
    response.marked_by = "manual"
    response.marked_by_id = actor_id
    response.marker_comment = comment
    response.rubric_scores = list(rubric_scores or ())
    response.is_correct = None if available == 0 else awarded >= available / 2
    session.flush()

    attempt = session.get(Attempt, response.attempt_id)
    if attempt is not None:
        manual_total = session.execute(
            select(func.coalesce(func.sum(AttemptResponse.marks_awarded), 0)).where(
                AttemptResponse.attempt_id == attempt.id,
                AttemptResponse.marked_by == "manual",
            )
        ).scalar_one()
        attempt.manual_score = float(manual_total or 0)
        attempt.marked_by_id = actor_id
        pending = session.execute(
            select(func.count())
            .select_from(AttemptResponse)
            .where(
                AttemptResponse.attempt_id == attempt.id,
                AttemptResponse.marks_awarded.is_(None),
            )
        ).scalar_one()
        _finalise_attempt_score(session, attempt=attempt, pending_manual=int(pending))

    emit(
        "assessment_response:mark",
        AuditCategory.ASSESSMENT,
        resource_type="assessment_attempt",
        resource_id=response.attempt_id,
        summary=f"Marked {awarded} of {available}",
        changes=diff(before, {"marks_awarded": float(awarded)}),
        metadata={"question_id": str(response.question_id), "comment": comment},
    )
    return response


def release_assessment(
    session: Session, *, assessment: OnlineAssessment, actor_id: uuid.UUID
) -> OnlineAssessment:
    """Make scores visible to candidates, after computing the statistics.

    Refuses while anything is unmarked. Releasing a paper with essays
    outstanding shows candidates a score that is a third of what they earned,
    and no amount of subsequent explanation undoes the first impression.
    """
    if assessment.pending_manual_marking > 0:
        raise RuleViolation(
            f"{assessment.pending_manual_marking} answer(s) still need marking.",
            rule="marking_incomplete",
        )

    attempts = (
        session.execute(
            select(Attempt).where(
                Attempt.assessment_id == assessment.id,
                Attempt.status == AttemptStatus.MARKED,
                Attempt.counts_for_grade.is_(True),
            )
        )
        .scalars()
        .all()
    )

    _apply_attempt_grading(session, assessment=assessment, attempts=list(attempts))

    scores = [
        float(a.total_score) for a in attempts if a.total_score is not None and a.counts_for_grade
    ]
    if scores:
        assessment.mean_score = round(mean(scores), 2)
        assessment.median_score = round(median(scores), 2)
        assessment.standard_deviation = round(pstdev(scores), 2) if len(scores) > 1 else 0.0

    refresh_item_statistics(session, assessment=assessment)

    before = {"status": assessment.status}
    assessment.status = AssessmentStatus.RELEASED
    assessment.released_by_id = actor_id
    assessment.released_at = utcnow()
    session.flush()

    emit(
        "online_assessment:release",
        AuditCategory.ASSESSMENT,
        resource_type="online_assessment",
        resource_id=assessment.id,
        resource_label=assessment.title,
        summary=(
            f"Released to {len(attempts)} candidate(s); mean {assessment.mean_score}"
            f" of {assessment.total_marks}"
        ),
        changes=diff(before, {"status": assessment.status}),
        severity="notice",
    )
    return assessment


def _apply_attempt_grading(
    session: Session, *, assessment: OnlineAssessment, attempts: list[Attempt]
) -> None:
    """Decide which attempt counts, under the assessment's own rule.

    `best`, `latest`, `first` or `average`. Marked on the attempt rather than
    computed at read time so that a candidate looking at their own history
    can see which of their three attempts is the one that counts.
    """
    by_student: dict[uuid.UUID, list[Attempt]] = {}
    for attempt in attempts:
        by_student.setdefault(attempt.student_id, []).append(attempt)

    for student_attempts in by_student.values():
        if len(student_attempts) == 1:
            student_attempts[0].counts_for_grade = True
            continue

        mode = assessment.attempt_grading
        if mode == "latest":
            keeper = max(student_attempts, key=lambda a: a.attempt_number)
        elif mode == "first":
            keeper = min(student_attempts, key=lambda a: a.attempt_number)
        elif mode == "average":
            # Every attempt counts, and the push step averages them.
            for attempt in student_attempts:
                attempt.counts_for_grade = True
            continue
        else:
            keeper = max(
                student_attempts,
                key=lambda a: (float(a.total_score or 0), a.attempt_number),
            )
        for attempt in student_attempts:
            attempt.counts_for_grade = attempt.id == keeper.id
    session.flush()


def refresh_item_statistics(session: Session, *, assessment: OnlineAssessment) -> None:
    """Recompute facility and discrimination for every question used.

    The upper/lower-27% split. What makes this worth doing: a question with
    high facility and near-zero discrimination is measuring nothing, and one
    with *negative* discrimination — strong candidates getting it wrong more
    often than weak ones — almost always has an incorrect answer key. That is a
    finding a lecturer can act on, and it is invisible without the arithmetic.
    """
    attempts = (
        session.execute(
            select(Attempt)
            .where(
                Attempt.assessment_id == assessment.id,
                Attempt.status == AttemptStatus.MARKED,
            )
            .order_by(Attempt.total_score.desc().nullslast())
        )
        .scalars()
        .all()
    )
    if len(attempts) < 8:
        # Below about eight candidates the split is noise, and publishing a
        # discrimination index computed from three scripts invites bad
        # decisions about good questions.
        return

    cut = max(1, round(len(attempts) * 0.27))
    top_ids = {a.id for a in attempts[:cut]}
    bottom_ids = {a.id for a in attempts[-cut:]}

    responses = (
        session.execute(
            select(AttemptResponse)
            .join(Attempt, AttemptResponse.attempt_id == Attempt.id)
            .where(Attempt.assessment_id == assessment.id, Attempt.status == AttemptStatus.MARKED)
        )
        .scalars()
        .all()
    )

    per_question: dict[uuid.UUID, dict[str, int]] = {}
    for response in responses:
        bucket = per_question.setdefault(
            response.question_id,
            {
                "answered": 0,
                "correct": 0,
                "top": 0,
                "top_correct": 0,
                "bottom": 0,
                "bottom_correct": 0,
            },
        )
        if response.marks_awarded is None:
            continue
        bucket["answered"] += 1
        correct = bool(response.is_correct)
        bucket["correct"] += int(correct)
        if response.attempt_id in top_ids:
            bucket["top"] += 1
            bucket["top_correct"] += int(correct)
        elif response.attempt_id in bottom_ids:
            bucket["bottom"] += 1
            bucket["bottom_correct"] += int(correct)

    for question_id, stats in per_question.items():
        question = session.get(Question, question_id)
        if question is None:
            continue
        question.facility_index = marking.facility_index(
            correct=stats["correct"], answered=stats["answered"]
        )
        question.discrimination_index = marking.discrimination_index(
            top_correct=stats["top_correct"],
            top_total=stats["top"],
            bottom_correct=stats["bottom_correct"],
            bottom_total=stats["bottom"],
        )
        question.times_used += 1
    session.flush()


def push_to_mark_sheet(
    session: Session, *, assessment: OnlineAssessment, actor_id: uuid.UUID
) -> dict[str, Any]:
    """Write released scores into the course's mark sheet as a component score.

    The one seam between this module and the academic record, and it is
    deliberately narrow:

    * It writes a **component** score, never a final mark and never a grade.
      The final mark is computed by `assessment` from all components under the
      course's approved scheme.
    * It refuses a mark sheet that has left `draft`. Once marks are submitted
      for moderation, an online test cannot silently change them — the
      approval chain owns them from that point.
    * It requires the assessment to be `released`, so nothing reaches the
      academic record before the candidates have seen it.

    The effect is that every mark on a transcript has been through moderation,
    a department board, a faculty board and Senate, whether a human typed it
    or a quiz computed it. An LMS that writes straight to the record bypasses
    all four, and most conveniently at 2am the night before a board sits.
    """
    from acmis.modules.assessment.models import ComponentScore, CourseResult, MarkSheet

    if assessment.status != AssessmentStatus.RELEASED:
        raise Conflict("Only a released assessment can be pushed to the mark sheet.")
    if not assessment.assessment_component_id:
        raise RuleViolation(
            "This assessment is not linked to a component of the course's assessment "
            "scheme, so it has nowhere to be recorded.",
            rule="no_component_link",
        )

    sheet = session.execute(
        select(MarkSheet).where(MarkSheet.course_offering_id == assessment.course_offering_id)
    ).scalar_one_or_none()
    if sheet is None:
        raise RuleViolation(
            "No mark sheet exists for this course offering yet.",
            rule="no_mark_sheet",
        )
    if not sheet.is_editable:
        raise RuleViolation(
            f"The mark sheet is {sheet.status}; marks can no longer be written to it. "
            "Corrections after submission go through moderation.",
            rule="mark_sheet_locked",
        )

    from acmis.modules.curriculum.models import AssessmentComponent

    component = session.get(AssessmentComponent, assessment.assessment_component_id)
    if component is None:
        raise NotFound("The linked assessment component no longer exists.")

    attempts = (
        session.execute(
            select(Attempt).where(
                Attempt.assessment_id == assessment.id,
                Attempt.status == AttemptStatus.MARKED,
                Attempt.counts_for_grade.is_(True),
            )
        )
        .scalars()
        .all()
    )

    by_student: dict[uuid.UUID, list[Attempt]] = {}
    for attempt in attempts:
        by_student.setdefault(attempt.student_id, []).append(attempt)

    written = 0
    skipped: list[dict[str, Any]] = []
    correlation = uuid.uuid4()

    for student_id, student_attempts in by_student.items():
        if assessment.attempt_grading == "average" and len(student_attempts) > 1:
            raw = mean(float(a.total_score or 0.0) for a in student_attempts)
        else:
            raw = float(student_attempts[0].total_score or 0.0)

        result = session.execute(
            select(CourseResult).where(
                CourseResult.mark_sheet_id == sheet.id,
                CourseResult.student_id == student_id,
            )
        ).scalar_one_or_none()
        if result is None:
            skipped.append({"student_id": str(student_id), "reason": "not on the mark sheet"})
            continue

        # Rescale to the component's own maximum. A 40-mark quiz feeding a
        # component marked out of 20 must be halved, not truncated.
        scaled = (
            raw / float(assessment.total_marks) * float(component.max_mark)
            if assessment.total_marks
            else 0.0
        )
        weighted = round(scaled / float(component.max_mark) * float(component.weight_percent), 2)

        score = session.execute(
            select(ComponentScore).where(
                ComponentScore.result_id == result.id,
                ComponentScore.component_id == component.id,
            )
        ).scalar_one_or_none()
        if score is None:
            score = ComponentScore(
                result_id=result.id,
                component_id=component.id,
                component_code=component.code,
                max_score=component.max_mark,
                weight_percent=component.weight_percent,
                created_by_id=actor_id,
            )
            session.add(score)
        elif score.raw_score is not None and float(score.raw_score) != round(scaled, 2):
            score.revisions = [
                *(score.revisions or ()),
                {
                    "revision": score.revision,
                    "raw_score": float(score.raw_score),
                    "changed_at": utcnow().isoformat(),
                    "changed_by": str(actor_id),
                    "source": f"online_assessment:{assessment.id}",
                },
            ]
            score.revision += 1

        score.raw_score = round(scaled, 2)
        score.weighted_score = weighted
        score.entered_by_id = actor_id
        score.entered_at = utcnow()
        written += 1

    # The pushing member of staff joins the sheet's entrants, which means the
    # separation-of-duties rule will refuse to let them approve it. That is the
    # intended consequence: pushing marks is entering marks.
    if actor_id not in (sheet.entered_by_ids or ()):
        sheet.entered_by_ids = [*(sheet.entered_by_ids or ()), actor_id]

    assessment.pushed_to_mark_sheet_at = utcnow()
    session.flush()

    from acmis.modules.assessment import service as assessment_service

    assessment_service._refresh_sheet_statistics(session, sheet=sheet)

    emit(
        "online_assessment:push_marks",
        AuditCategory.ASSESSMENT,
        resource_type="online_assessment",
        resource_id=assessment.id,
        resource_label=assessment.title,
        summary=(
            f"{written} score(s) written to component {component.code} on the "
            f"mark sheet; {len(skipped)} skipped"
        ),
        metadata={"component": component.code, "skipped": skipped[:50]},
        correlation_id=correlation,
        severity="notice",
    )
    return {"written": written, "skipped": skipped, "component": component.code}


# ---------------------------------------------------------------------------
# Assignments
# ---------------------------------------------------------------------------


def submit_assignment(
    session: Session,
    *,
    assignment: Assignment,
    student_id: uuid.UUID,
    attachment_ids: list[uuid.UUID],
    text_response: str | None,
    actor_id: uuid.UUID,
) -> Submission:
    """Submit work, applying the late penalty transparently.

    The raw score and the penalty are stored separately, and both are shown. A
    student is entitled to see that they earned 72 and lost 10 for being two
    days late, rather than being told they scored 62.
    """
    now = utcnow()
    if assignment.status != "published":
        raise Conflict("This assignment is not open for submission.")
    if assignment.opens_at and now < assignment.opens_at:
        raise Conflict("This assignment has not opened yet.")

    deadline = assignment.accept_until or assignment.due_at
    if now > deadline:
        raise RuleViolation(
            f"Submissions closed on {deadline:%d %B %Y at %H:%M}.",
            rule="submission_closed",
            waivable_by=["results:enter"],
        )

    days_late = 0
    penalty = 0.0
    if now > assignment.due_at:
        days_late = max(1, (now - assignment.due_at).days + 1)
        penalty = min(100.0, days_late * float(assignment.late_penalty_percent_per_day or 0))

    existing = (
        session.execute(
            select(Submission)
            .where(
                Submission.assignment_id == assignment.id,
                Submission.student_id == student_id,
            )
            .order_by(Submission.attempt_number.desc())
        )
        .scalars()
        .first()
    )
    attempt_number = (existing.attempt_number + 1) if existing else 1

    submission = Submission(
        assignment_id=assignment.id,
        student_id=student_id,
        attempt_number=attempt_number,
        submitted_at=now,
        attachment_ids=list(attachment_ids),
        text_response=text_response,
        days_late=days_late,
        penalty_percent=penalty,
        status="submitted",
        created_by_id=actor_id,
    )
    session.add(submission)
    session.flush()

    emit(
        "assignment_submission:create",
        AuditCategory.ASSESSMENT,
        resource_type="assignment_submission",
        resource_id=submission.id,
        resource_label=assignment.title,
        summary=(
            f"Submitted (attempt {attempt_number})"
            + (f", {days_late} day(s) late, {penalty:g}% penalty" if days_late else "")
        ),
    )
    return submission


def mark_submission(
    session: Session,
    *,
    submission: Submission,
    raw_score: float,
    rubric_scores: list[dict[str, Any]] | None,
    feedback: str | None,
    actor_id: uuid.UUID,
    is_second_marker: bool = False,
) -> Submission:
    assignment = session.get(Assignment, submission.assignment_id)
    if assignment is None:  # pragma: no cover
        raise NotFound()
    if raw_score < 0 or raw_score > float(assignment.total_marks):
        raise ValidationFailed(
            f"The mark must be between 0 and {assignment.total_marks}.",
            code="mark_out_of_range",
        )

    if is_second_marker:
        if submission.marked_by_id == actor_id:
            raise RuleViolation(
                "A second marker must be someone other than the first.",
                rule="separation_of_duties",
            )
        submission.second_marked_by_id = actor_id
        submission.second_score = raw_score
        first = float(submission.raw_score or 0)
        divergence = abs(first - raw_score) / float(assignment.total_marks) * 100
        if divergence > 10:
            # Beyond a 10-point divergence the two markers are not measuring
            # the same thing, and a third has to reconcile. Averaging a wide
            # disagreement hides it.
            submission.status = "reconciliation_required"
        else:
            submission.reconciled_score = round((first + raw_score) / 2, 2)
            submission.status = "marked"
    else:
        submission.raw_score = raw_score
        submission.marked_by_id = actor_id
        submission.marked_at = utcnow()
        submission.rubric_scores = list(rubric_scores or ())
        submission.feedback = feedback
        submission.status = "second_marking" if assignment.double_marking else "marked"

    effective = (
        submission.reconciled_score
        if submission.reconciled_score is not None
        else submission.raw_score
    )
    if effective is not None:
        submission.final_score = round(
            float(effective) * (1 - float(submission.penalty_percent or 0) / 100), 2
        )
        submission.percentage = round(
            submission.final_score / float(assignment.total_marks) * 100, 2
        )
    session.flush()

    emit(
        "assignment_submission:mark",
        AuditCategory.ASSESSMENT,
        resource_type="assignment_submission",
        resource_id=submission.id,
        summary=(
            f"{'Second-marked' if is_second_marker else 'Marked'} {raw_score} of "
            f"{assignment.total_marks}"
            + (f"; penalty {submission.penalty_percent:g}%" if submission.penalty_percent else "")
        ),
        metadata={"status": submission.status},
    )
    return submission


# ---------------------------------------------------------------------------
# Engagement
# ---------------------------------------------------------------------------


def capture_engagement(
    session: Session, *, course_offering_id: uuid.UUID, week_number: int
) -> dict[str, int]:
    """Snapshot every registered student's engagement in one course.

    Run weekly. The point is timing: by the time a first test confirms a
    student is struggling it is week eight, and a student who has opened no
    material and attempted no practice quiz by week four is identifiable in
    week four.

    `risk_band` is a prompt for a conversation, never an action. Nothing in
    the system reads it to decide anything — a platform that acts on an
    engagement heuristic will act wrongly on the student with one shared
    laptop and no data bundle.
    """
    from acmis.modules.students.models import RegistrationCourse

    space = session.execute(
        select(CourseSpace).where(CourseSpace.course_offering_id == course_offering_id)
    ).scalar_one_or_none()
    if space is None:
        return {"captured": 0}

    material_ids = [m.id for m in space.materials if m.deleted_at is None and m.is_published]
    assessments = [
        a
        for a in space.assessments
        if a.deleted_at is None
        and a.status
        in {
            AssessmentStatus.OPEN,
            AssessmentStatus.CLOSED,
            AssessmentStatus.MARKED,
            AssessmentStatus.RELEASED,
        }
    ]

    students = list(
        session.execute(
            select(RegistrationCourse.student_id).where(
                RegistrationCourse.course_offering_id == course_offering_id,
                RegistrationCourse.dropped_at.is_(None),
                RegistrationCourse.deleted_at.is_(None),
            )
        ).scalars()
    )

    today = date.today()
    captured = 0
    for student_id in students:
        views = (
            session.execute(
                select(MaterialView).where(
                    MaterialView.student_id == student_id,
                    MaterialView.material_id.in_(material_ids or [uuid.UUID(int=0)]),
                )
            )
            .scalars()
            .all()
        )
        attempts = (
            session.execute(
                select(Attempt).where(
                    Attempt.student_id == student_id,
                    Attempt.assessment_id.in_([a.id for a in assessments] or [uuid.UUID(int=0)]),
                    Attempt.status != AttemptStatus.VOIDED,
                )
            )
            .scalars()
            .all()
        )

        percentages = [float(a.percentage) for a in attempts if a.percentage is not None]
        last_activity = max(
            [v.last_viewed_at for v in views] + [a.started_at for a in attempts],
            default=None,
        )
        days_idle = (today - last_activity.date()).days if last_activity is not None else None

        row = session.execute(
            select(EngagementSnapshot).where(
                EngagementSnapshot.student_id == student_id,
                EngagementSnapshot.course_offering_id == course_offering_id,
                EngagementSnapshot.week_number == week_number,
            )
        ).scalar_one_or_none()
        if row is None:
            row = EngagementSnapshot(
                student_id=student_id,
                course_offering_id=course_offering_id,
                week_number=week_number,
                captured_on=today,
            )
            session.add(row)

        row.captured_on = today
        row.materials_available = len(material_ids)
        row.materials_viewed = len(views)
        row.minutes_on_material = sum(v.total_seconds for v in views) // 60
        row.assessments_available = len(assessments)
        row.assessments_attempted = len({a.assessment_id for a in attempts})
        row.mean_assessment_percent = round(mean(percentages), 2) if percentages else None
        row.days_since_last_activity = days_idle
        row.risk_band = _risk_band(
            materials_available=len(material_ids),
            materials_viewed=len(views),
            assessments_available=len(assessments),
            assessments_attempted=len({a.assessment_id for a in attempts}),
            mean_percent=row.mean_assessment_percent,
            days_idle=days_idle,
        )
        captured += 1

    session.flush()
    log.info(
        "engagement_captured",
        offering=str(course_offering_id),
        week=week_number,
        students=captured,
    )
    return {"captured": captured}


def _risk_band(
    *,
    materials_available: int,
    materials_viewed: int,
    assessments_available: int,
    assessments_attempted: int,
    mean_percent: float | None,
    days_idle: int | None,
) -> str:
    """A crude four-band heuristic, and deliberately crude.

    Simple thresholds a lecturer can understand and argue with, rather than a
    score nobody can explain. The bands are a prompt to look, and the person
    looking is the one who decides.
    """
    if materials_available == 0 and assessments_available == 0:
        return "engaged"

    material_ratio = materials_viewed / materials_available if materials_available else 1.0
    assessment_ratio = (
        assessments_attempted / assessments_available if assessments_available else 1.0
    )

    if days_idle is None or days_idle > 21:
        return "disengaged"
    if material_ratio < 0.25 or assessment_ratio < 0.25:
        return "at_risk"
    if material_ratio < 0.6 or (mean_percent is not None and mean_percent < 45):
        return "slipping"
    return "engaged"
