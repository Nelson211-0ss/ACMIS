"""Automatic marking.

Pure functions over a question and a response. No database, no session, no
ambient state — which is what makes the marker testable, and testability is
not a nicety here: an off-by-one in partial credit silently misgrades a whole
cohort, and the only defence is a test suite that covers every question kind.

Every function returns `(marks_awarded, is_correct, note)`. The note explains
the award in the candidate's terms, because "you scored 1.5 of 3" invites a
query and "two of three correct options selected, one incorrect" answers it.
"""

from __future__ import annotations

import re
import unicodedata
from decimal import ROUND_HALF_UP, Decimal
from itertools import pairwise
from typing import Any

from acmis.modules.learning.models import QuestionKind

MarkResult = tuple[Decimal, bool | None, str]

#: What every marker function returns is a *fraction* of the question earned,
#: from 0 to 1 — Moodle's convention, adopted for the reason its own
#: documentation gives: a judgement about an answer should not be entangled
#: with how many marks the question happens to be worth in this paper. Marks
#: are `fraction x marks_available`, computed at the boundary in
#: `mark_response`, so re-weighting a question in a paper re-scores every
#: candidate correctly without anything being remarked.


def _dec(value: Any) -> Decimal:
    if value is None:
        return Decimal(0)
    if isinstance(value, Decimal):
        return value
    return Decimal(str(value))


def _round(value: Decimal) -> Decimal:
    return value.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def mark_response(
    *,
    kind: str,
    marks: Any,
    negative_marks: Any,
    answer_key: dict[str, Any],
    options: list[dict[str, Any]],
    answer: dict[str, Any],
    variables: dict[str, Any] | None = None,
) -> MarkResult:
    """Mark one response, returning marks. `(_, None, _)` means a human must.

    `variables` carries the instantiated values for a `calculated` question —
    the particular numbers this candidate was given.
    """
    available = _dec(marks)
    penalty = _dec(negative_marks)

    if not answer or _is_blank(answer):
        # Unanswered is zero, not negative. Negative marking exists to
        # discourage guessing, and penalising a blank punishes the honest
        # behaviour it is meant to encourage.
        return Decimal(0), False, "Not answered."

    if kind == QuestionKind.CALCULATED:
        return _mark_calculated(
            available=available,
            penalty=penalty,
            key=answer_key,
            variables=variables or {},
            answer=answer,
        )

    handlers: dict[str, Any] = {
        QuestionKind.MULTIPLE_CHOICE: _mark_single_choice,
        QuestionKind.TRUE_FALSE: _mark_single_choice,
        QuestionKind.MULTIPLE_RESPONSE: _mark_multiple_response,
        QuestionKind.SHORT_ANSWER: _mark_short_answer,
        QuestionKind.FILL_IN_BLANK: _mark_fill_in_blank,
        QuestionKind.NUMERIC: _mark_numeric,
        QuestionKind.MATCHING: _mark_matching,
        QuestionKind.ORDERING: _mark_ordering,
    }
    handler = handlers.get(kind)

    if handler is None:
        return Decimal(0), None, "Awaiting marking."

    result: MarkResult = handler(
        available=available, penalty=penalty, key=answer_key, options=options, answer=answer
    )
    return result


def _is_blank(answer: dict[str, Any]) -> bool:
    for value in answer.values():
        if value is None:
            continue
        if isinstance(value, str) and not value.strip():
            continue
        if isinstance(value, (list, dict)) and not value:
            continue
        return False
    return True


def _mark_single_choice(
    *,
    available: Decimal,
    penalty: Decimal,
    key: dict[str, Any],
    options: list[dict[str, Any]],
    answer: dict[str, Any],
) -> MarkResult:
    chosen = _labels(answer)
    correct = {str(o["label"]) for o in options if o.get("is_correct")}
    if not correct:
        correct = {str(label) for label in key.get("correct_labels", ())}

    if len(chosen) != 1:
        return Decimal(0), False, "Select exactly one option."
    label = next(iter(chosen))
    if label in correct:
        return _round(available), True, "Correct."

    feedback = next(
        (o.get("feedback") for o in options if str(o["label"]) == label and o.get("feedback")),
        None,
    )
    return (
        _round(-penalty) if penalty else Decimal(0),
        False,
        feedback or f"Incorrect. The correct answer is {', '.join(sorted(correct))}.",
    )


def _mark_multiple_response(
    *,
    available: Decimal,
    penalty: Decimal,
    key: dict[str, Any],
    options: list[dict[str, Any]],
    answer: dict[str, Any],
) -> MarkResult:
    """Partial credit, floored at zero.

    Credit for each correct option selected, an equal deduction for each
    incorrect one, floored at zero for the question. The deduction is what
    stops "select every option" from being an optimal strategy; the floor is
    what stops one badly-guessed question from eating marks earned elsewhere.

    `all_or_nothing` in the key switches to strict set equality, which some
    faculties require.
    """
    chosen = _labels(answer)
    correct = {str(o["label"]) for o in options if o.get("is_correct")}
    incorrect = {str(o["label"]) for o in options} - correct
    if not correct:
        return Decimal(0), None, "This question has no answer key; awaiting marking."

    if key.get("all_or_nothing"):
        exact = chosen == correct
        return (
            (_round(available), True, "Correct.")
            if exact
            else (
                _round(-penalty) if penalty else Decimal(0),
                False,
                f"Incorrect. The correct answers are {', '.join(sorted(correct))}.",
            )
        )

    hits = len(chosen & correct)
    misses = len(chosen & incorrect)
    per_option = available / Decimal(len(correct))
    raw = per_option * hits - per_option * misses
    awarded = _round(max(Decimal(0), raw))
    fully = chosen == correct
    return (
        awarded,
        fully,
        f"{hits} of {len(correct)} correct option(s) selected"
        + (f", {misses} incorrect." if misses else "."),
    )


#: Typography a phone keyboard produces on its own, folded to the ASCII the
#: lecturer typed. NFKC does not do this: it leaves U+2019 alone, so
#: "Boyle<U+2019>s law" and "Boyle's law" stay byte-different, and the
#: candidate loses the mark for having autocorrect switched on.
_TYPOGRAPHY = str.maketrans(
    {
        "\u2018": "'",
        "\u2019": "'",
        "\u201a": "'",
        "\u201b": "'",
        "\u2032": "'",
        "\u02bc": "'",
        "\u201c": '"',
        "\u201d": '"',
        "\u201e": '"',
        "\u2033": '"',
        "\u2013": "-",
        "\u2014": "-",
        "\u2212": "-",
        "\u2026": "...",
    }
)


def _normalise(text: str, *, ignore_case: bool, ignore_punctuation: bool) -> str:
    """Normalise a free-text answer before comparing.

    Unicode NFKC first, then the typographic fold above: a candidate typing on
    a phone produces curly quotes, en dashes and non-breaking spaces that are
    visually identical to the expected answer and byte-different from it.
    Marking those wrong measures the keyboard, not the candidate.
    """
    value = unicodedata.normalize("NFKC", text).translate(_TYPOGRAPHY).strip()
    value = re.sub(r"\s+", " ", value)
    if ignore_case:
        value = value.casefold()
    if ignore_punctuation:
        value = re.sub(r"[^\w\s]", "", value)
    return value


def _mark_short_answer(
    *,
    available: Decimal,
    penalty: Decimal,
    key: dict[str, Any],
    options: list[dict[str, Any]],
    answer: dict[str, Any],
) -> MarkResult:
    """Match free text against accepted answers.

    Exact-after-normalisation by default. A `pattern` key allows a regex for
    the cases that need it, and `max_edit_distance` allows a spelling
    tolerance — worth having for a long technical term where a single
    transposed letter is clearly not a wrong answer, and worth keeping off by
    default because it is easy to set so loosely that wrong answers pass.
    """
    given = str(answer.get("text", "") or "")
    if not given.strip():
        return Decimal(0), False, "Not answered."

    ignore_case = bool(key.get("ignore_case", True))
    ignore_punctuation = bool(key.get("ignore_punctuation", False))
    normalised = _normalise(given, ignore_case=ignore_case, ignore_punctuation=ignore_punctuation)

    if pattern := key.get("pattern"):
        try:
            if re.fullmatch(pattern, given.strip(), re.IGNORECASE if ignore_case else 0):
                return _round(available), True, "Correct."
        except re.error:
            return Decimal(0), None, "The answer key for this question is invalid."

    accepted = [
        _normalise(str(a), ignore_case=ignore_case, ignore_punctuation=ignore_punctuation)
        for a in key.get("accepted", ())
    ]
    if normalised in accepted:
        return _round(available), True, "Correct."

    tolerance = int(key.get("max_edit_distance", 0))
    if tolerance > 0:
        for candidate in accepted:
            if _edit_distance(normalised, candidate) <= tolerance:
                return (
                    _round(available),
                    True,
                    "Accepted, with a minor spelling variation.",
                )

    return (
        _round(-penalty) if penalty else Decimal(0),
        False,
        "Incorrect.",
    )


def _mark_fill_in_blank(
    *,
    available: Decimal,
    penalty: Decimal,
    key: dict[str, Any],
    options: list[dict[str, Any]],
    answer: dict[str, Any],
) -> MarkResult:
    """Several blanks, marked proportionally.

    Proportional rather than all-or-nothing: a sentence with four blanks and
    three right is not a wrong answer, and treating it as one measures
    something other than understanding.
    """
    blanks: dict[str, Any] = key.get("blanks", {})
    given: dict[str, Any] = answer.get("blanks", {}) or {}
    if not blanks:
        return Decimal(0), None, "This question has no answer key; awaiting marking."

    ignore_case = bool(key.get("ignore_case", True))
    hits = 0
    for position, accepted in blanks.items():
        candidate = _normalise(
            str(given.get(position, "") or ""), ignore_case=ignore_case, ignore_punctuation=False
        )
        allowed = [
            _normalise(str(a), ignore_case=ignore_case, ignore_punctuation=False)
            for a in (accepted if isinstance(accepted, list) else [accepted])
        ]
        if candidate and candidate in allowed:
            hits += 1

    awarded = _round(available * Decimal(hits) / Decimal(len(blanks)))
    return awarded, hits == len(blanks), f"{hits} of {len(blanks)} blank(s) correct."


def _mark_numeric(
    *,
    available: Decimal,
    penalty: Decimal,
    key: dict[str, Any],
    options: list[dict[str, Any]],
    answer: dict[str, Any],
) -> MarkResult:
    """Numeric with a tolerance.

    Tolerance is essential rather than a convenience: 9.81 and 9.8 are the
    same answer in physics, and a marker that rejects the second is measuring
    how many decimal places a candidate copied. Absolute or relative,
    whichever the key specifies.
    """
    raw = answer.get("value")
    if raw is None or (isinstance(raw, str) and not raw.strip()):
        return Decimal(0), False, "Not answered."
    try:
        given = Decimal(str(raw).replace(",", "").strip())
    except Exception:
        return Decimal(0), False, "That is not a number."

    expected = key.get("value")
    if expected is None:
        return Decimal(0), None, "This question has no answer key; awaiting marking."
    target = _dec(expected)

    absolute = key.get("tolerance")
    relative = key.get("relative_tolerance_percent")
    if absolute is not None:
        allowed = _dec(absolute)
    elif relative is not None:
        allowed = abs(target) * _dec(relative) / Decimal(100)
    else:
        allowed = Decimal(0)

    if abs(given - target) <= allowed:
        return _round(available), True, "Correct."
    return (
        _round(-penalty) if penalty else Decimal(0),
        False,
        f"Incorrect. The expected value is {target}" + (f" (± {allowed})." if allowed else "."),
    )


def _mark_matching(
    *,
    available: Decimal,
    penalty: Decimal,
    key: dict[str, Any],
    options: list[dict[str, Any]],
    answer: dict[str, Any],
) -> MarkResult:
    pairs: dict[str, Any] = key.get("pairs", {})
    given: dict[str, Any] = answer.get("pairs", {}) or {}
    if not pairs:
        return Decimal(0), None, "This question has no answer key; awaiting marking."
    hits = sum(1 for left, right in pairs.items() if str(given.get(left, "")) == str(right))
    awarded = _round(available * Decimal(hits) / Decimal(len(pairs)))
    return awarded, hits == len(pairs), f"{hits} of {len(pairs)} pair(s) matched."


def _mark_ordering(
    *,
    available: Decimal,
    penalty: Decimal,
    key: dict[str, Any],
    options: list[dict[str, Any]],
    answer: dict[str, Any],
) -> MarkResult:
    """Credit for adjacent pairs in the right order, not for exact position.

    Position-based marking makes one early mistake cascade — everything after
    it is "wrong" though the candidate's relative ordering was sound. Counting
    correctly-ordered adjacent pairs measures what the question asks.
    """
    expected: list[Any] = list(key.get("order", ()))
    given: list[Any] = list(answer.get("order", ()) or ())
    if not expected:
        return Decimal(0), None, "This question has no answer key; awaiting marking."
    if len(expected) < 2:
        exact = given == expected
        return (
            (_round(available), True, "Correct.")
            if exact
            else (Decimal(0), False, "Incorrect order.")
        )

    position = {str(item): index for index, item in enumerate(expected)}
    pairs = len(expected) - 1
    hits = 0
    for first, second in pairwise(given):
        a, b = position.get(str(first)), position.get(str(second))
        if a is not None and b is not None and a < b:
            hits += 1

    awarded = _round(available * Decimal(hits) / Decimal(pairs))
    return awarded, given == expected, f"{hits} of {pairs} adjacent pair(s) correctly ordered."


def _labels(answer: dict[str, Any]) -> set[str]:
    raw = answer.get("option_labels") or answer.get("labels") or ()
    if isinstance(raw, str):
        raw = [raw]
    return {str(label).strip() for label in raw if str(label).strip()}


def _edit_distance(a: str, b: str) -> int:
    """Levenshtein distance. Small strings only; used for spelling tolerance."""
    if a == b:
        return 0
    if not a:
        return len(b)
    if not b:
        return len(a)
    previous = list(range(len(b) + 1))
    for i, ca in enumerate(a, start=1):
        current = [i]
        for j, cb in enumerate(b, start=1):
            current.append(min(previous[j] + 1, current[j - 1] + 1, previous[j - 1] + (ca != cb)))
        previous = current
    return previous[-1]


# ---------------------------------------------------------------------------
# Item analysis
# ---------------------------------------------------------------------------


def facility_index(*, correct: int, answered: int) -> float | None:
    """Proportion who answered correctly. 0 is impossible, 1 is trivial.

    A question everyone gets right and a question nobody gets right both
    contribute nothing to distinguishing candidates. Below about 0.2 or above
    0.9 is worth a look — the first is often a badly-worded stem rather than a
    hard question.
    """
    if answered <= 0:
        return None
    return round(correct / answered, 3)


def discrimination_index(
    *, top_correct: int, top_total: int, bottom_correct: int, bottom_total: int
) -> float | None:
    """How well an item separates strong candidates from weak ones.

    The classic upper/lower-27% difference. A near-zero or negative value on a
    question the cohort found easy means the item is measuring something other
    than the subject — ambiguous wording, or an answer key that is wrong. It is
    the single most useful number for improving a question bank, and it is why
    `Question.times_answered` is tracked at all.
    """
    if top_total <= 0 or bottom_total <= 0:
        return None
    return round(top_correct / top_total - bottom_correct / bottom_total, 3)


def _mark_calculated(
    *,
    available: Decimal,
    penalty: Decimal,
    key: dict[str, Any],
    variables: dict[str, Any],
    answer: dict[str, Any],
) -> MarkResult:
    """Mark a parameterised question against the candidate's own numbers.

    The expected value is a formula over the variable set the candidate was
    given — `(a * b) / 2`, say. Evaluated through the same AST-restricted
    evaluator the policy engine uses, for exactly the same reason: the formula
    is data written by a lecturer through a web form, and `eval` on it would
    make every question author a remote-code-execution vector.
    """
    from acmis.core.abac.expressions import ConditionError, compile_condition

    formula = key.get("formula")
    if not formula:
        return Decimal(0), None, "This question has no formula; awaiting marking."

    raw = answer.get("value")
    if raw is None or (isinstance(raw, str) and not str(raw).strip()):
        return Decimal(0), False, "Not answered."
    try:
        given = Decimal(str(raw).replace(",", "").strip())
    except Exception:
        return Decimal(0), False, "That is not a number."

    try:
        condition = compile_condition(formula)
        # The variable set is passed as the `context` root, so a formula reads
        # `context.a * context.b` and cannot reach anything else.
        expected = condition.evaluate_value(context=variables)
    except ConditionError:
        return Decimal(0), None, "This question's formula is invalid; awaiting marking."

    try:
        target = _dec(expected)
    except Exception:
        return Decimal(0), None, "This question's formula did not produce a number."

    tolerance = key.get("tolerance")
    relative = key.get("relative_tolerance_percent")
    if tolerance is not None:
        allowed = _dec(tolerance)
    elif relative is not None:
        allowed = abs(target) * _dec(relative) / Decimal(100)
    else:
        allowed = abs(target) * Decimal("0.005")  # 0.5%, so 9.8 passes for 9.81

    if abs(given - target) <= allowed:
        return _round(available), True, "Correct."
    return (
        _round(-penalty) if penalty else Decimal(0),
        False,
        f"Incorrect. For your values the answer is {target}.",
    )


def apply_try_penalty(*, fraction: Decimal, tries_used: int, penalty_per_try: Decimal) -> Decimal:
    """Reduce a fraction by the cost of previous wrong tries.

    Moodle's interactive-with-tries arithmetic: a candidate who gets it right
    on the third try of three, at a third penalty each, earns a third of the
    marks. Floored at zero — a wrong answer costs the question's marks, never
    marks earned elsewhere.

    This is the mode worth having in a formative quiz: it rewards working out
    the right answer over guessing, which a single-try quiz cannot
    distinguish.
    """
    if tries_used <= 1 or penalty_per_try <= 0:
        return fraction
    reduced = fraction - penalty_per_try * Decimal(tries_used - 1)
    return max(Decimal(0), reduced)


def to_fraction(*, marks_awarded: Decimal, marks_available: Decimal) -> Decimal | None:
    """Marks back to a fraction, for storage alongside the mark."""
    if marks_available <= 0:
        return None
    return (marks_awarded / marks_available).quantize(Decimal("0.00001"), rounding=ROUND_HALF_UP)
