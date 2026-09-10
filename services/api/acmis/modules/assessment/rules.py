"""Academic regulations, applied.

GPA, progression and classification, computed from rule sets held as data on
the curriculum version rather than written into this file. That separation is
the point of the module: a 2024 graduate is classified under the 2024 rules,
which have to be *retrievable*, not merely remembered.

The rule shapes below are the contract. `progression_rules` on a
`CurriculumVersion`:

    {
      "pass_grade_point": 2.0,
      "probation_cgpa": 2.0,
      "discontinue_after_probations": 2,
      "max_retakes_per_course": 3,
      "retake_counts": "best",            # or "latest"
      "carry_forward_failures": true,
      "repeat_year_if_failed_credits_over": 12,
      "minimum_credits_for_progression": 15
    }

`classification_rules`:

    {
      "bands": [
        {"class": "First Class Honours",         "min_cgpa": 4.40},
        {"class": "Second Class Honours (Upper)","min_cgpa": 3.60},
        {"class": "Second Class Honours (Lower)","min_cgpa": 2.80},
        {"class": "Pass",                        "min_cgpa": 2.00}
      ],
      "requires_no_outstanding_retakes": true,
      "cap_after_retake": "Pass",       # a retaken finalist cannot take a First
      "use_final_two_years_only": false
    }

The defaults encode the National Council for Higher Education's guidance for
Ugandan undergraduate programmes — a 5.0 scale, normal progress at a grade
point of 2.0 and above, probationary progress below it, and retakes carried
forward — because that is the regulator most of the intended deployments
answer to. They are defaults, not truths: every value is overridable per
curriculum version, and an institution on a 4.0 scale changes four numbers.
"""

from __future__ import annotations

import uuid
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from decimal import ROUND_HALF_UP, Decimal
from typing import Any, Protocol

__all__ = [
    "DEFAULT_CLASSIFICATION_RULES",
    "DEFAULT_PROGRESSION_RULES",
    "GpaResult",
    "ProgressionOutcome",
    "cap_mark",
    "classify",
    "compute_gpa",
    "decide_progression",
    "grade_for_mark",
    "retake_selection",
    "study_duration",
    "validate_credit_load",
]

DEFAULT_PROGRESSION_RULES: dict[str, Any] = {
    "pass_grade_point": 2.0,
    "probation_cgpa": 2.0,
    "discontinue_after_probations": 2,
    "max_retakes_per_course": 3,
    "retake_counts": "best",
    "carry_forward_failures": True,
    "repeat_year_if_failed_credits_over": 12,
    "minimum_credits_for_progression": 15,
    #: A supplementary examination is a second attempt at a paper the
    #: candidate sat and failed, so the mark is capped at the pass mark: a
    #: student who fails and retakes must not out-rank one who passed first
    #: time. A *special* examination is not capped — see the note on
    #: `cap_mark`, because conflating the two is the mistake that produces
    #: the appeals an institution loses.
    "supplementary_mark_cap": 50.0,
    #: Dead semesters and dead years are permitted, and bounded. Uncapped,
    #: they become an indefinite enrolment that consumes a place, keeps a
    #: student on the statutory return, and eventually collides with the
    #: maximum duration below with no way back.
    "max_dead_semesters": 2,
    "max_dead_years": 1,
    #: The regulator's usual formulation: a programme must be completed within
    #: twice its normal duration. Held as a multiplier rather than a number of
    #: years so it survives a three-year and a five-year programme.
    "max_duration_multiplier": 2.0,
}

DEFAULT_CLASSIFICATION_RULES: dict[str, Any] = {
    "bands": [
        {"class": "First Class Honours", "min_cgpa": 4.40},
        {"class": "Second Class Honours (Upper Division)", "min_cgpa": 3.60},
        {"class": "Second Class Honours (Lower Division)", "min_cgpa": 2.80},
        {"class": "Pass", "min_cgpa": 2.00},
    ],
    "requires_no_outstanding_retakes": True,
    "cap_after_retake": None,
    "use_final_two_years_only": False,
}


class Band(Protocol):
    """The shape `grade_for_mark` needs from a `GradeBand` row."""

    grade: str
    lower_mark: Any
    upper_mark: Any
    grade_point: Any
    is_pass: bool
    counts_in_gpa: bool


class Attempt(Protocol):
    """The shape the GPA and progression functions need from a `CourseResult`.

    A Protocol rather than the ORM class so these functions are testable
    against plain objects, and so nothing in this file can accidentally issue
    a query. Every input is passed in; there is no ambient state.
    """

    id: uuid.UUID
    course_id: uuid.UUID
    credit_units: int
    grade_point: Any
    final_mark: Any
    outcome: str
    attempt_number: int
    counts_in_gpa: bool
    is_superseded: bool


def _dec(value: Any) -> Decimal:
    """Everything arithmetic goes through Decimal.

    Not floats. A CGPA is compared against a classification boundary, and
    `4.3999999999999995 >= 4.40` is False — which is a graduate given a Second
    when they earned a First, on a rounding artefact. Decimal makes the
    comparison mean what it says.
    """
    if value is None:
        return Decimal(0)
    if isinstance(value, Decimal):
        return value
    return Decimal(str(value))


def _round2(value: Decimal) -> Decimal:
    """Half-up to two places.

    Half-up, not Python's default banker's rounding: a student told their CGPA
    is 3.605 expects 3.61, and every published classification table in the
    region is computed half-up. Matching the convention the institution
    already prints matters more than statistical neutrality.
    """
    return value.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def grade_for_mark(mark: Any, bands: Sequence[Band]) -> Band | None:
    """The band containing `mark`. `None` if the scale has a gap.

    Returning None rather than guessing: a mark with no band is a
    misconfigured grading scale, and silently assigning the nearest grade
    hides it until a board is sitting in front of the mark sheet.
    """
    if mark is None:
        return None
    value = _dec(mark)
    for band in bands:
        if _dec(band.lower_mark) <= value <= _dec(band.upper_mark):
            return band
    return None


@dataclass(slots=True)
class GpaResult:
    credits_attempted: int
    credits_earned: int
    quality_points: Decimal
    gpa: Decimal | None
    #: Attempts excluded from the divisor, and why. Surfaced rather than
    #: silently dropped: "why is my GPA computed over 15 credits when I took
    #: 18" is the second most common student query after the marks themselves.
    excluded: list[dict[str, Any]] = field(default_factory=list)

    @property
    def gpa_float(self) -> float | None:
        return float(self.gpa) if self.gpa is not None else None


def compute_gpa(attempts: Iterable[Attempt]) -> GpaResult:
    """Credit-weighted GPA over the attempts given.

    Quality points are credits x grade point, summed, divided by the credits
    that count. Which credits count is the whole subtlety:

    * A **fail counts**. It contributes zero quality points over its full
      credit weight, which is what makes a fail hurt the average — excluding
      it would make failing a course indistinguishable from never taking it.
    * An **audited, exempt, transferred or withheld** attempt does not count,
      in either the numerator or the divisor. No mark was earned here.
    * An **absence** counts as a zero. An unexcused absence from an
      examination is a fail; a deferred sitting is `incomplete` and excluded
      until it is sat.
    * A **superseded** attempt does not count — see `retake_selection`.
    """
    attempted = 0
    earned = 0
    quality = Decimal(0)
    divisor = 0
    excluded: list[dict[str, Any]] = []

    for attempt in attempts:
        credits = int(attempt.credit_units or 0)
        outcome = attempt.outcome

        if attempt.is_superseded:
            excluded.append(
                {"course_id": str(attempt.course_id), "reason": "superseded_by_later_attempt"}
            )
            continue
        if not attempt.counts_in_gpa or outcome in {
            "audit",
            "exempt",
            "withheld",
            "incomplete",
            "pending",
            "transferred",
        }:
            excluded.append({"course_id": str(attempt.course_id), "reason": outcome})
            continue

        attempted += credits
        divisor += credits
        if outcome == "absent":
            # Zero quality points over the full weight — an absence is a fail.
            continue
        points = _dec(attempt.grade_point)
        quality += points * credits
        if outcome in {"pass", "exempt_pass"} or points >= Decimal("2.0"):
            earned += credits

    gpa = _round2(quality / divisor) if divisor else None
    return GpaResult(
        credits_attempted=attempted,
        credits_earned=earned,
        quality_points=_round2(quality),
        gpa=gpa,
        excluded=excluded,
    )


def retake_selection(
    attempts: Sequence[Attempt], *, rules: dict[str, Any] | None = None
) -> list[Attempt]:
    """Which attempt at each course counts, marking the rest superseded.

    `retake_counts: "best"` keeps the highest grade point per course;
    `"latest"` keeps the most recent attempt whatever it scored. Institutions
    differ, and the choice materially changes a classification — a student who
    retakes and does worse is helped by "best" and harmed by "latest", and
    both policies exist in the region.

    Returns the attempts that count. It does not mutate: the caller sets
    `is_superseded` on the others, so the decision is visible in the diff
    rather than buried in this function.
    """
    rules = {**DEFAULT_PROGRESSION_RULES, **(rules or {})}
    mode = rules.get("retake_counts", "best")

    by_course: dict[uuid.UUID, list[Attempt]] = {}
    for attempt in attempts:
        by_course.setdefault(attempt.course_id, []).append(attempt)

    counted: list[Attempt] = []
    for course_attempts in by_course.values():
        if len(course_attempts) == 1:
            counted.append(course_attempts[0])
            continue
        if mode == "latest":
            counted.append(max(course_attempts, key=lambda a: a.attempt_number))
        else:
            counted.append(
                max(
                    course_attempts,
                    key=lambda a: (_dec(a.grade_point), a.attempt_number),
                )
            )
    return counted


@dataclass(slots=True)
class ProgressionOutcome:
    #: `normal`, `probation`, `retake`, `repeat_year`, `discontinue`, `complete`
    status: str
    reasons: list[str]
    retake_course_ids: list[uuid.UUID]
    failed_credits: int
    consecutive_probations: int
    #: True when the outcome is severe enough that a board must confirm it. A
    #: discontinuation is never applied by a nightly job on its own — a student
    #: is not dismissed by a cron entry.
    requires_board_confirmation: bool = False


def decide_progression(
    *,
    semester_gpa: Decimal | None,
    cgpa: Decimal | None,
    failed: Sequence[Attempt],
    credits_earned_this_semester: int,
    previous_consecutive_probations: int,
    is_final_semester: bool,
    outstanding_retakes: int,
    rules: dict[str, Any] | None = None,
) -> ProgressionOutcome:
    """Classify a semester's progress.

    Following the NCHE framing — normal, probationary or discontinued — with
    retake and repeat-year outcomes in between, which is how institutions
    actually operate the guidance.

    Nothing here writes anything. A `discontinue` outcome sets
    `requires_board_confirmation`, and it is the board's minuted decision that
    changes a student's status. The computation is advice; the authority is a
    person.
    """
    rules = {**DEFAULT_PROGRESSION_RULES, **(rules or {})}
    reasons: list[str] = []
    failed_credits = sum(int(a.credit_units or 0) for a in failed)
    retake_ids = [a.course_id for a in failed]
    probations = previous_consecutive_probations

    pass_gp = _dec(rules["pass_grade_point"])
    probation_cgpa = _dec(rules["probation_cgpa"])

    below_threshold = cgpa is not None and cgpa < probation_cgpa
    semester_below = semester_gpa is not None and semester_gpa < pass_gp

    if below_threshold or semester_below:
        probations += 1
        if below_threshold:
            reasons.append(f"CGPA {cgpa} is below the {probation_cgpa} threshold")
        if semester_below:
            reasons.append(f"Semester GPA {semester_gpa} is below {pass_gp}")
    else:
        probations = 0

    limit = int(rules["discontinue_after_probations"])
    if probations >= limit:
        reasons.append(
            f"{probations} consecutive semesters on probation reaches the limit of {limit}"
        )
        return ProgressionOutcome(
            status="discontinue",
            reasons=reasons,
            retake_course_ids=retake_ids,
            failed_credits=failed_credits,
            consecutive_probations=probations,
            requires_board_confirmation=True,
        )

    repeat_over = rules.get("repeat_year_if_failed_credits_over")
    if repeat_over is not None and failed_credits > int(repeat_over):
        reasons.append(
            f"{failed_credits} failed credit units exceeds the {repeat_over} "
            "unit limit for carrying failures forward"
        )
        return ProgressionOutcome(
            status="repeat_year",
            reasons=reasons,
            retake_course_ids=retake_ids,
            failed_credits=failed_credits,
            consecutive_probations=probations,
            requires_board_confirmation=True,
        )

    if is_final_semester and not failed and outstanding_retakes == 0:
        return ProgressionOutcome(
            status="complete",
            reasons=["All programme requirements met"],
            retake_course_ids=[],
            failed_credits=0,
            consecutive_probations=probations,
            requires_board_confirmation=True,
        )

    if probations > 0:
        return ProgressionOutcome(
            status="probation",
            reasons=reasons,
            retake_course_ids=retake_ids,
            failed_credits=failed_credits,
            consecutive_probations=probations,
        )

    minimum = int(rules.get("minimum_credits_for_progression", 0))
    if minimum and credits_earned_this_semester < minimum:
        reasons.append(
            f"{credits_earned_this_semester} credit units earned is below the "
            f"{minimum} required to progress"
        )
        return ProgressionOutcome(
            status="retake",
            reasons=reasons,
            retake_course_ids=retake_ids,
            failed_credits=failed_credits,
            consecutive_probations=probations,
        )

    if failed:
        return ProgressionOutcome(
            status="retake",
            reasons=[f"{len(failed)} course(s) to be retaken"],
            retake_course_ids=retake_ids,
            failed_credits=failed_credits,
            consecutive_probations=probations,
        )

    return ProgressionOutcome(
        status="normal",
        reasons=["Normal progress"],
        retake_course_ids=[],
        failed_credits=0,
        consecutive_probations=0,
    )


def classify(
    *,
    cgpa: Decimal | None,
    outstanding_retakes: int,
    had_retakes: bool,
    rules: dict[str, Any] | None = None,
) -> tuple[str | None, list[str]]:
    """Degree classification. Returns (class, notes).

    Two institution-specific twists that are common enough to be first-class
    options here:

    `requires_no_outstanding_retakes` — a student cannot be classified while a
    course is unresolved. Almost universal, and the reason a graduation list
    excludes people who look eligible on CGPA alone.

    `cap_after_retake` — some institutions cap the classification of a student
    who has retaken anything, so a retake cannot be used to buy a First. It is
    contentious, so it is off by default and named explicitly when on.
    """
    rules = {**DEFAULT_CLASSIFICATION_RULES, **(rules or {})}
    notes: list[str] = []

    if cgpa is None:
        return None, ["No CGPA computed; classification not possible"]

    if rules.get("requires_no_outstanding_retakes") and outstanding_retakes > 0:
        return None, [
            f"{outstanding_retakes} outstanding retake(s) must be cleared before "
            "the award can be classified"
        ]

    bands = sorted(
        rules.get("bands", DEFAULT_CLASSIFICATION_RULES["bands"]),
        key=lambda b: _dec(b["min_cgpa"]),
        reverse=True,
    )
    awarded: str | None = None
    for band in bands:
        if cgpa >= _dec(band["min_cgpa"]):
            awarded = str(band["class"])
            break

    if awarded is None:
        return None, [f"CGPA {cgpa} is below the minimum for any classification"]

    cap = rules.get("cap_after_retake")
    if cap and had_retakes:
        capped_index = next((i for i, b in enumerate(bands) if b["class"] == cap), None)
        awarded_index = next((i for i, b in enumerate(bands) if b["class"] == awarded), None)
        if capped_index is not None and awarded_index is not None and awarded_index < capped_index:
            notes.append(
                f"Classification capped at {cap} because the programme was completed with retakes"
            )
            awarded = cap

    return awarded, notes


def validate_credit_load(
    *,
    total_credits: int,
    retake_credits: int,
    min_credits: int,
    max_credits: int,
    max_credits_with_retakes: int,
    is_finalist: bool,
) -> list[str]:
    """Check a semester registration against the credit rules.

    Returns the problems, empty if the load is valid. Separated from the
    endpoint so the frontend can call the same check as the student builds
    their basket, and get the same answer — a registration screen that says
    "valid" and then fails on submit is the single most complained-about
    feature of every registration system.
    """
    problems: list[str] = []
    ceiling = max_credits_with_retakes if retake_credits > 0 else max_credits

    if total_credits > ceiling:
        problems.append(
            f"{total_credits} credit units exceeds the maximum of {ceiling} "
            + ("(including the retake allowance)" if retake_credits else "")
        )
    if total_credits < min_credits and not is_finalist:
        # Finalists are exempt: a student needing one course to graduate cannot
        # meet a 15-unit minimum, and refusing their registration would strand
        # them a semester short of an award they have earned.
        problems.append(
            f"{total_credits} credit units is below the minimum of {min_credits} "
            "for a full-time semester"
        )
    if retake_credits > total_credits:
        problems.append("Retake credits cannot exceed the total registered credits")
    return problems


def cap_mark(
    mark: float | Decimal | None,
    *,
    attempt_kind: str,
    rules: Mapping[str, Any],
) -> tuple[Decimal | None, bool]:
    """Apply the retake cap, and say whether it bit.

    The distinction this function exists to hold:

    * `first` — a first sitting. Uncapped.
    * `special` — the candidate missed the paper for a reason the institution
      accepted, and sat it later. **Uncapped**, because they are not retaking
      anything; this is their first attempt, taken late. Capping it penalises
      a student for having been in hospital.
    * `supplementary` — the candidate sat the paper, failed, and sat it again.
      Capped at the pass mark, because otherwise failing and retaking beats
      passing first time.
    * `retake` — a repeated course, capped the same way.

    Returns the mark to record and whether the cap was applied, so the mark
    sheet can show "50 (capped)". A capped mark shown without the flag is a
    mark the student disputes, every time.
    """
    if mark is None:
        return None, False
    value = Decimal(str(mark))
    if attempt_kind in {"first", "special"}:
        return value, False
    cap = rules.get("supplementary_mark_cap")
    if cap is None:
        return value, False
    ceiling = Decimal(str(cap))
    if value <= ceiling:
        return value, False
    return ceiling, True


@dataclass(frozen=True, slots=True)
class DurationVerdict:
    """Whether a student may still be here, and how much room is left."""

    semesters_used: int
    semesters_permitted: int
    dead_semesters_used: int
    dead_semesters_permitted: int
    #: `within`, `final_chance`, `exceeded`.
    standing: str
    reason: str | None = None


def study_duration(
    *,
    normal_semesters: int,
    semesters_enrolled: int,
    dead_semesters: int,
    rules: Mapping[str, Any],
) -> DurationVerdict:
    """How a student stands against the maximum permitted duration.

    Two limits, checked together because they interact: the number of dead
    semesters a student may take, and the total time they have to finish. A
    student is normally stopped by the first and only ever notices the second,
    so both are reported.

    Dead semesters count toward the permitted total: an institution that
    excludes them has no maximum duration at all, since any student can extend
    indefinitely by taking dead years. What they do *not* count toward is
    progression — a dead semester is not a failed one.
    """
    multiplier = Decimal(str(rules.get("max_duration_multiplier", 2.0)))
    permitted = int((Decimal(normal_semesters) * multiplier).to_integral_value())
    dead_permitted = int(rules.get("max_dead_semesters", 2))

    if dead_semesters > dead_permitted:
        return DurationVerdict(
            semesters_used=semesters_enrolled,
            semesters_permitted=permitted,
            dead_semesters_used=dead_semesters,
            dead_semesters_permitted=dead_permitted,
            standing="exceeded",
            reason=(
                f"{dead_semesters} dead semesters taken; {dead_permitted} are permitted "
                "on this programme"
            ),
        )
    if semesters_enrolled > permitted:
        return DurationVerdict(
            semesters_used=semesters_enrolled,
            semesters_permitted=permitted,
            dead_semesters_used=dead_semesters,
            dead_semesters_permitted=dead_permitted,
            standing="exceeded",
            reason=(
                f"{semesters_enrolled} semesters used of {permitted} permitted "
                f"({normal_semesters} normal x {multiplier})"
            ),
        )
    if semesters_enrolled >= permitted or dead_semesters >= dead_permitted:
        return DurationVerdict(
            semesters_used=semesters_enrolled,
            semesters_permitted=permitted,
            dead_semesters_used=dead_semesters,
            dead_semesters_permitted=dead_permitted,
            standing="final_chance",
            reason="This is the last semester available on this programme.",
        )
    return DurationVerdict(
        semesters_used=semesters_enrolled,
        semesters_permitted=permitted,
        dead_semesters_used=dead_semesters,
        dead_semesters_permitted=dead_permitted,
        standing="within",
    )
