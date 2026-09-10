"""The marking engine: pure arithmetic, and therefore testable exactly.

Everything here is a rule a candidate can appeal against, so each test states
the rule rather than the implementation. A "correct" that comes out as 0.99 of
the marks, or a blank answer that scores below zero, is an appeal the
institution loses.
"""

from __future__ import annotations

from decimal import Decimal

import pytest

from acmis.modules.learning.marking import (
    apply_try_penalty,
    discrimination_index,
    facility_index,
    mark_response,
    to_fraction,
)

OPTIONS = [
    {"label": "A", "is_correct": False, "feedback": "That is the median."},
    {"label": "B", "is_correct": True},
    {"label": "C", "is_correct": False},
    {"label": "D", "is_correct": False},
]


def _mark(kind: str, answer: dict[str, object], **over: object) -> tuple[Decimal, bool | None, str]:
    parameters: dict[str, object] = {
        "kind": kind,
        "marks": 4,
        "negative_marks": 0,
        "answer_key": {},
        "options": [],
        "answer": answer,
    }
    parameters.update(over)
    return mark_response(**parameters)  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# Blank answers
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "answer",
    [{}, {"text": ""}, {"text": "   "}, {"value": None}, {"option_labels": []}, {"pairs": {}}],
)
def test_a_blank_answer_scores_zero_never_negative(answer: dict[str, object]) -> None:
    """Negative marking discourages guessing; it must not punish abstaining."""
    awarded, correct, _ = _mark("multiple_choice", answer, negative_marks=2, options=OPTIONS)
    assert awarded == Decimal(0)
    assert correct is False


# ---------------------------------------------------------------------------
# Selected-response
# ---------------------------------------------------------------------------


def test_a_right_choice_earns_the_whole_mark() -> None:
    awarded, correct, _ = _mark("multiple_choice", {"option_labels": ["B"]}, options=OPTIONS)
    assert (awarded, correct) == (Decimal("4.00"), True)


def test_a_wrong_choice_returns_the_author_s_feedback() -> None:
    """Feedback per distractor is the pedagogical point of a quiz.

    A candidate who chose the median instead of the mean should be told that,
    not "incorrect".
    """
    awarded, correct, feedback = _mark("multiple_choice", {"option_labels": ["A"]}, options=OPTIONS)
    assert (awarded, correct) == (Decimal(0), False)
    assert feedback == "That is the median."


def test_negative_marking_deducts_only_on_a_wrong_answer() -> None:
    awarded, _, _ = _mark(
        "multiple_choice", {"option_labels": ["C"]}, options=OPTIONS, negative_marks=1
    )
    assert awarded == Decimal("-1.00")


def test_selecting_two_options_on_a_single_choice_is_refused() -> None:
    awarded, correct, feedback = _mark(
        "multiple_choice", {"option_labels": ["A", "B"]}, options=OPTIONS
    )
    assert (awarded, correct) == (Decimal(0), False)
    assert "exactly one" in feedback


def test_multiple_response_gives_partial_credit_floored_at_zero() -> None:
    """Credit per correct option, an equal deduction per incorrect one.

    The deduction is what stops "select everything" from being optimal; the
    floor is what stops one bad guess from eating marks earned elsewhere.
    """
    options = [
        {"label": "A", "is_correct": True},
        {"label": "B", "is_correct": True},
        {"label": "C", "is_correct": False},
        {"label": "D", "is_correct": False},
    ]
    both, fully, _ = _mark("multiple_response", {"option_labels": ["A", "B"]}, options=options)
    assert (both, fully) == (Decimal("4.00"), True)

    one_each, fully, _ = _mark("multiple_response", {"option_labels": ["A", "C"]}, options=options)
    assert (one_each, fully) == (Decimal(0), False)

    everything, fully, _ = _mark(
        "multiple_response", {"option_labels": ["A", "B", "C", "D"]}, options=options
    )
    assert everything == Decimal(0), "selecting every option must not score"

    half, fully, _ = _mark("multiple_response", {"option_labels": ["A"]}, options=options)
    assert (half, fully) == (Decimal("2.00"), False)


# ---------------------------------------------------------------------------
# Free text and numbers
# ---------------------------------------------------------------------------


def test_short_answer_ignores_case_and_unicode_confusables() -> None:
    """A phone keyboard produces curly quotes and non-breaking spaces.

    They are visually identical to the expected answer, so marking them wrong
    measures the candidate's keyboard rather than their knowledge.
    """
    key = {"accepted": ["Boyle's law"]}
    # Written as escapes so this source stays ASCII while the test still
    # exercises the real characters: U+2019 is the apostrophe iOS substitutes
    # for a typed one, and U+00A0 the space a paste from a PDF carries.
    smart_quote = "Boyle\u2019s law"
    pasted_space = "Boyle's law\u00a0"
    for given in ["Boyle's law", "boyle's LAW", smart_quote, pasted_space]:
        awarded, correct, _ = _mark("short_answer", {"text": given}, answer_key=key)
        assert (awarded, correct) == (Decimal("4.00"), True), given


def test_spelling_tolerance_is_off_unless_asked_for() -> None:
    _, correct, _ = _mark(
        "short_answer", {"text": "normalisaton"}, answer_key={"accepted": ["normalisation"]}
    )
    assert correct is False

    lenient, correct, feedback = _mark(
        "short_answer",
        {"text": "normalisaton"},
        answer_key={"accepted": ["normalisation"], "max_edit_distance": 2},
    )
    assert (lenient, correct) == (Decimal("4.00"), True)
    assert "spelling" in feedback


def test_a_broken_regex_in_a_key_asks_for_a_human_rather_than_failing() -> None:
    awarded, correct, feedback = _mark(
        "short_answer", {"text": "anything"}, answer_key={"pattern": "([unclosed"}
    )
    assert correct is None, "an invalid key must queue for marking, not mark wrong"
    assert awarded == Decimal(0)
    assert "invalid" in feedback


def test_numeric_tolerance_accepts_the_same_answer_to_fewer_places() -> None:
    key = {"value": "9.81", "tolerance": "0.02"}
    for given in ["9.81", "9.8", "9.83", 9.8]:
        _, correct, _ = _mark("numeric", {"value": given}, answer_key=key)
        assert correct is True, given
    _, correct, _ = _mark("numeric", {"value": "9.5"}, answer_key=key)
    assert correct is False


def test_numeric_accepts_thousands_separators() -> None:
    _, correct, _ = _mark("numeric", {"value": "1,250"}, answer_key={"value": 1250})
    assert correct is True


def test_a_calculated_question_is_marked_against_the_candidate_s_own_numbers() -> None:
    """Every candidate gets different values, so the key is a formula.

    Evaluated through the policy engine's AST-restricted evaluator — a formula
    is data typed by a lecturer, and `eval` on it would make every question
    author a remote-code-execution vector.
    """
    key = {"formula": "context.base * context.height / 2", "tolerance": "0.01"}
    variables = {"base": 7, "height": 4}
    _, correct, _ = _mark("calculated", {"value": "14"}, answer_key=key, variables=variables)
    assert correct is True

    _, correct, _ = _mark("calculated", {"value": "28"}, answer_key=key, variables=variables)
    assert correct is False


def test_a_calculated_formula_cannot_reach_outside_its_variables() -> None:
    awarded, correct, feedback = _mark(
        "calculated",
        {"value": "1"},
        answer_key={"formula": "__import__('os').getpid()"},
        variables={},
    )
    assert correct is None and awarded == Decimal(0)
    assert "invalid" in feedback


def test_matching_gives_credit_per_pair() -> None:
    key = {"pairs": {"Kampala": "Uganda", "Nairobi": "Kenya", "Kigali": "Rwanda"}}
    awarded, fully, _ = _mark(
        "matching",
        {"pairs": {"Kampala": "Uganda", "Nairobi": "Kenya", "Kigali": "Tanzania"}},
        answer_key=key,
    )
    assert (awarded, fully) == (Decimal("2.67"), False)


# ---------------------------------------------------------------------------
# Human marking
# ---------------------------------------------------------------------------


def test_an_essay_is_queued_for_a_human() -> None:
    """`None` for "correct" is the signal that a person must decide."""
    awarded, correct, _ = _mark("essay", {"text": "Normalisation removes redundancy."})
    assert correct is None
    assert awarded == Decimal(0)


def test_a_question_with_no_key_is_queued_rather_than_marked_wrong() -> None:
    _, correct, _ = _mark("numeric", {"value": "3"}, answer_key={})
    assert correct is None


# ---------------------------------------------------------------------------
# Fractions, tries and item analysis
# ---------------------------------------------------------------------------


def test_try_penalty_matches_the_interactive_mode() -> None:
    """Right on the third of three tries, at a third penalty each, earns a third."""
    third = apply_try_penalty(fraction=Decimal(1), tries_used=3, penalty_per_try=Decimal("0.3333"))
    assert third == Decimal("0.3334")
    assert apply_try_penalty(fraction=Decimal(1), tries_used=1, penalty_per_try=Decimal("0.5")) == 1
    assert apply_try_penalty(
        fraction=Decimal(1), tries_used=9, penalty_per_try=Decimal("0.5")
    ) == Decimal(0), "a penalty must never make a question cost marks earned elsewhere"


def test_fraction_storage_is_the_canonical_grade() -> None:
    assert to_fraction(marks_awarded=Decimal(3), marks_available=Decimal(4)) == Decimal("0.75000")
    assert to_fraction(marks_awarded=Decimal(1), marks_available=Decimal(0)) is None


def test_item_analysis_flags_a_question_nobody_can_answer() -> None:
    assert facility_index(correct=0, answered=120) == 0.0
    assert facility_index(correct=60, answered=120) == 0.5
    assert facility_index(correct=0, answered=0) is None


def test_discrimination_separates_the_strong_from_the_weak() -> None:
    """Positive when the strongest candidates do better on the item.

    A negative index on a question the whole cohort sat is the signal that the
    key is wrong — worth surfacing, because the alternative is an appeal.
    """
    assert (
        discrimination_index(top_correct=27, top_total=27, bottom_correct=0, bottom_total=27) == 1.0
    )
    assert (
        discrimination_index(top_correct=0, top_total=27, bottom_correct=27, bottom_total=27)
        == -1.0
    ), "a negative index is the signal that the answer key is wrong"
    assert (
        discrimination_index(top_correct=0, top_total=0, bottom_correct=0, bottom_total=0) is None
    )
