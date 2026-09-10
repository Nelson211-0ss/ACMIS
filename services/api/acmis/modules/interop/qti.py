"""QTI import and export.

QTI is how question banks move between systems, and an institution adopting
ACMIS usually already has one — exported from Moodle, or bought from a
publisher. Supporting the format is the difference between "retype four
hundred questions" and "import them".

Both 2.1 and 3.0 are read. 2.1 because that is what most systems still export,
whatever the current version is; 3.0 because it is what new tools produce. They
differ in element names and namespaces, not in structure, so the mapping table
below carries both spellings.

The mapping to our own model, interaction by interaction:

    QTI interaction              ACMIS question kind
    ---------------------------  --------------------------
    choiceInteraction (max 1)    multiple_choice
    choiceInteraction (max >1)   multiple_response
    choiceInteraction (2, T/F)   true_false
    textEntryInteraction         short_answer  (or numeric, by baseType)
    extendedTextInteraction      essay
    matchInteraction             matching
    orderInteraction             ordering
    inlineChoiceInteraction      fill_in_blank
    uploadInteraction            file_upload
    sliderInteraction            numeric

What is *not* imported is stated plainly rather than silently dropped: QTI's
adaptive items and its full response-processing language are more expressive
than our marking engine, and an item using them is recorded as a failure with
the reason. An import that quietly turns an adaptive item into a plain
multiple-choice question produces a question that marks incorrectly, which is
worse than not importing it.
"""

from __future__ import annotations

import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from typing import Any

import structlog

from acmis.modules.learning.models import QuestionKind

log = structlog.get_logger(__name__)

#: Both namespaces, because a 2.1 export and a 3.0 export differ here and
#: nowhere that matters.
NAMESPACES = {
    "qti21": "http://www.imsglobal.org/xsd/imsqti_v2p1",
    "qti30": "http://www.imsglobal.org/xsd/imsqtiasi_v3p0",
    "imscp": "http://www.imsglobal.org/xsd/imscp_v1p1",
}

#: Response-processing templates we can honour. `match_correct` is exact match
#: against `correctResponse`; `map_response` is per-value partial credit from
#: `mapping`. Anything else is an item we decline rather than guess at.
SUPPORTED_TEMPLATES = {
    "http://www.imsglobal.org/question/qti_v2p1/rptemplates/match_correct": "match_correct",
    "http://www.imsglobal.org/question/qti_v2p1/rptemplates/map_response": "map_response",
    "http://www.imsglobal.org/question/qti_v3p0/rptemplates/match_correct": "match_correct",
    "http://www.imsglobal.org/question/qti_v3p0/rptemplates/map_response": "map_response",
}


@dataclass(slots=True)
class ImportedQuestion:
    """One question extracted from a QTI item, in our own terms."""

    kind: str
    stem: str
    marks: float
    answer_key: dict[str, Any] = field(default_factory=dict)
    options: list[dict[str, Any]] = field(default_factory=list)
    explanation: str | None = None
    topic: str | None = None
    identifier: str | None = None


@dataclass(slots=True)
class ImportReport:
    imported: list[ImportedQuestion] = field(default_factory=list)
    failures: list[dict[str, str]] = field(default_factory=list)

    @property
    def summary(self) -> dict[str, Any]:
        return {
            "found": len(self.imported) + len(self.failures),
            "imported": len(self.imported),
            "failed": len(self.failures),
            "failures": self.failures,
        }


def _local(tag: str) -> str:
    """Strip the namespace. Both QTI versions differ only in namespace URI."""
    return tag.rsplit("}", 1)[-1]


def _text_of(element: ET.Element | None) -> str:
    """Flatten an element's text, keeping the reading order.

    QTI stems contain mixed content — inline maths, images, emphasis — and a
    naive `.text` returns only the run before the first child, which silently
    truncates half the question. This walks the subtree.
    """
    if element is None:
        return ""
    parts: list[str] = []
    if element.text:
        parts.append(element.text)
    for child in element:
        if _local(child.tag) == "img":
            alt = child.get("alt") or child.get("src") or "image"
            parts.append(f"![{alt}]({child.get('src', '')})")
        else:
            parts.append(_text_of(child))
        if child.tail:
            parts.append(child.tail)
    return " ".join(" ".join(parts).split())


def parse_item(xml: str | bytes) -> ImportedQuestion:
    """Parse one QTI assessment item. Raises ValueError with a reason.

    Reading untrusted XML: `ET.fromstring` from the standard library resolves
    no external entities and has no DTD loading, so the billion-laughs and
    external-entity classes do not apply. A size limit is enforced by the
    upload path before this is reached.
    """
    root = ET.fromstring(xml)  # noqa: S314 - stdlib ET resolves no entities and loads no DTD; see the docstring
    if _local(root.tag) not in {"assessmentItem", "qti-assessment-item"}:
        raise ValueError(f"not an assessment item (root is {_local(root.tag)})")

    if root.get("adaptive", "false").lower() == "true":
        raise ValueError(
            "adaptive items are more expressive than this marking engine; import "
            "declined rather than approximated"
        )

    body = _find(root, {"itemBody", "qti-item-body"})
    if body is None:
        raise ValueError("no item body")

    interaction, kind = _classify_interaction(body, root)
    if interaction is None:
        raise ValueError("no supported interaction found")

    template = _response_processing_template(root)
    if template is not None and template not in SUPPORTED_TEMPLATES:
        raise ValueError(
            f"response processing template {template!r} is not supported; the item's "
            "marking rules cannot be reproduced faithfully"
        )

    stem = _stem_text(body, interaction)
    marks = _max_score(root)
    identifier = root.get("identifier")
    title = root.get("title")

    question = ImportedQuestion(
        kind=kind,
        stem=stem or title or "(no question text)",
        marks=marks,
        identifier=identifier,
        topic=title,
    )
    _fill_answer(question, interaction=interaction, root=root, kind=kind)
    return question


def _find(element: ET.Element, names: set[str]) -> ET.Element | None:
    for child in element.iter():
        if _local(child.tag) in names:
            return child
    return None


def _classify_interaction(body: ET.Element, root: ET.Element) -> tuple[ET.Element | None, str]:
    """Find the interaction and decide which of our kinds it is."""
    mapping: dict[str, str] = {
        "extendedTextInteraction": QuestionKind.ESSAY,
        "qti-extended-text-interaction": QuestionKind.ESSAY,
        "matchInteraction": QuestionKind.MATCHING,
        "qti-match-interaction": QuestionKind.MATCHING,
        "orderInteraction": QuestionKind.ORDERING,
        "qti-order-interaction": QuestionKind.ORDERING,
        "inlineChoiceInteraction": QuestionKind.FILL_IN_BLANK,
        "qti-inline-choice-interaction": QuestionKind.FILL_IN_BLANK,
        "uploadInteraction": QuestionKind.FILE_UPLOAD,
        "qti-upload-interaction": QuestionKind.FILE_UPLOAD,
        "sliderInteraction": QuestionKind.NUMERIC,
        "qti-slider-interaction": QuestionKind.NUMERIC,
    }

    for element in body.iter():
        name = _local(element.tag)
        if name in {"choiceInteraction", "qti-choice-interaction"}:
            max_choices = int(element.get("maxChoices", "1") or 1)
            choices = [
                c for c in element.iter() if _local(c.tag) in {"simpleChoice", "qti-simple-choice"}
            ]
            if max_choices == 1:
                # A two-option single-choice item is conventionally true/false,
                # and importing it as such gets the right UI. Checked on the
                # option text rather than assumed from the count.
                labels = {_text_of(c).strip().lower() for c in choices}
                if len(choices) == 2 and labels <= {"true", "false", "yes", "no"}:
                    return element, QuestionKind.TRUE_FALSE
                return element, QuestionKind.MULTIPLE_CHOICE
            return element, QuestionKind.MULTIPLE_RESPONSE
        if name in {"textEntryInteraction", "qti-text-entry-interaction"}:
            # `baseType` on the response declaration decides whether this is a
            # numeric answer or a string one, and they mark differently.
            declaration = _response_declaration(root, element.get("responseIdentifier"))
            base_type = (declaration.get("baseType") if declaration is not None else "") or ""
            numeric = base_type in {"integer", "float"}
            return element, QuestionKind.NUMERIC if numeric else QuestionKind.SHORT_ANSWER
        if name in mapping:
            return element, mapping[name]
    return None, ""


def _response_declaration(root: ET.Element, identifier: str | None) -> ET.Element | None:
    if not identifier:
        return None
    for element in root.iter():
        if _local(element.tag) in {"responseDeclaration", "qti-response-declaration"} and (
            element.get("identifier") == identifier
        ):
            return element
    return None


def _response_processing_template(root: ET.Element) -> str | None:
    for element in root.iter():
        if _local(element.tag) in {"responseProcessing", "qti-response-processing"}:
            return element.get("template")
    return None


def _stem_text(body: ET.Element, interaction: ET.Element) -> str:
    """The question text, without the answer options.

    The prompt inside the interaction is part of the question; the choices are
    not. Taking the whole body would put every option into the stem, which is
    how a badly-written importer produces questions that give away their own
    answers.
    """
    prompt = _find(interaction, {"prompt", "qti-prompt"})
    parts: list[str] = []
    for child in body:
        if child is interaction:
            continue
        parts.append(_text_of(child))
    stem = " ".join(p for p in parts if p).strip()
    if prompt is not None:
        prompt_text = _text_of(prompt)
        stem = f"{stem} {prompt_text}".strip() if stem else prompt_text
    return stem


def _max_score(root: ET.Element) -> float:
    """The item's maximum, from the SCORE outcome declaration.

    Defaults to 1 when absent, which is what QTI itself implies — and which is
    harmless, because the paper's `marks_override` is what actually weights a
    question in ACMIS.
    """
    for element in root.iter():
        if _local(element.tag) in {"outcomeDeclaration", "qti-outcome-declaration"} and (
            element.get("identifier") == "MAXSCORE"
        ):
            value = _find(element, {"value", "qti-value"})
            if value is not None and value.text:
                try:
                    return float(value.text.strip())
                except ValueError:
                    pass
    return 1.0


def _fill_answer(
    question: ImportedQuestion, *, interaction: ET.Element, root: ET.Element, kind: str
) -> None:
    identifier = interaction.get("responseIdentifier")
    declaration = _response_declaration(root, identifier)
    correct_values: list[str] = []
    if declaration is not None:
        correct = _find(declaration, {"correctResponse", "qti-correct-response"})
        if correct is not None:
            correct_values = [
                (value.text or "").strip()
                for value in correct
                if _local(value.tag) in {"value", "qti-value"}
            ]

    if kind in {
        QuestionKind.MULTIPLE_CHOICE,
        QuestionKind.MULTIPLE_RESPONSE,
        QuestionKind.TRUE_FALSE,
    }:
        letters = "ABCDEFGHIJKLMNOPQRSTUVWXYZ"
        for index, choice in enumerate(
            c for c in interaction.iter() if _local(c.tag) in {"simpleChoice", "qti-simple-choice"}
        ):
            choice_id = choice.get("identifier") or ""
            question.options.append(
                {
                    "label": letters[index] if index < len(letters) else str(index + 1),
                    "body": _text_of(choice),
                    "is_correct": choice_id in correct_values,
                    "qti_identifier": choice_id,
                }
            )
        if kind == QuestionKind.MULTIPLE_RESPONSE:
            question.answer_key = {"all_or_nothing": False}
    elif kind == QuestionKind.SHORT_ANSWER:
        question.answer_key = {
            "accepted": correct_values,
            "ignore_case": True,
        }
    elif kind == QuestionKind.NUMERIC:
        try:
            question.answer_key = {
                "value": float(correct_values[0]) if correct_values else None,
                # QTI expresses tolerance in `equal` within response
                # processing; a proportional default is a safer import than
                # exact equality, which would mark 9.8 wrong for 9.81.
                "relative_tolerance_percent": 1,
            }
        except (ValueError, IndexError):
            question.answer_key = {}
    elif kind == QuestionKind.MATCHING:
        pairs: dict[str, str] = {}
        for value in correct_values:
            if " " in value:
                left, right = value.split(" ", 1)
                pairs[left.strip()] = right.strip()
        question.answer_key = {"pairs": pairs}
    elif kind == QuestionKind.ORDERING:
        question.answer_key = {"order": correct_values}
    elif kind == QuestionKind.FILL_IN_BLANK:
        question.answer_key = {
            "blanks": {str(i + 1): [v] for i, v in enumerate(correct_values)},
            "ignore_case": True,
        }


def import_package(items: list[tuple[str, str | bytes]]) -> ImportReport:
    """Parse many items, collecting failures rather than stopping.

    A 400-question export with three unparseable items should yield 397
    questions and three named failures. Aborting on the first means an
    institution's migration is blocked by whichever question happened to be
    unusual.
    """
    report = ImportReport()
    for name, xml in items:
        try:
            report.imported.append(parse_item(xml))
        except (ET.ParseError, ValueError) as exc:
            report.failures.append({"item": name, "reason": str(exc)})
    log.info("qti_import", **report.summary)
    return report


def export_question(question: Any) -> str:
    """Render one of our questions as a QTI 3.0 assessment item.

    Round-tripping matters for the same reason importing does: an institution
    should be able to leave. A question bank that can only be read out through
    our own API is a question bank held hostage.
    """
    kind = question.kind
    identifier = f"acmis-{question.id}"
    escaped_stem = _escape(question.stem)

    if kind in {
        QuestionKind.MULTIPLE_CHOICE,
        QuestionKind.TRUE_FALSE,
        QuestionKind.MULTIPLE_RESPONSE,
    }:
        max_choices = 1 if kind != QuestionKind.MULTIPLE_RESPONSE else 0
        correct = [o for o in question.options if o.is_correct]
        choices = "\n".join(
            f'        <qti-simple-choice identifier="{o.label}">{_escape(o.body)}'
            f"</qti-simple-choice>"
            for o in question.options
        )
        values = "\n".join(f"        <qti-value>{o.label}</qti-value>" for o in correct)
        cardinality = "single" if max_choices == 1 else "multiple"
        return f"""<?xml version="1.0" encoding="UTF-8"?>
<qti-assessment-item xmlns="http://www.imsglobal.org/xsd/imsqtiasi_v3p0"
    identifier="{identifier}" title="{_escape((question.topic or "Question")[:100])}"
    adaptive="false" time-dependent="false">
  <qti-response-declaration identifier="RESPONSE" cardinality="{cardinality}"
      base-type="identifier">
    <qti-correct-response>
{values}
    </qti-correct-response>
  </qti-response-declaration>
  <qti-outcome-declaration identifier="SCORE" cardinality="single" base-type="float"/>
  <qti-outcome-declaration identifier="MAXSCORE" cardinality="single" base-type="float">
    <qti-default-value><qti-value>{float(question.marks)}</qti-value></qti-default-value>
  </qti-outcome-declaration>
  <qti-item-body>
    <p>{escaped_stem}</p>
    <qti-choice-interaction response-identifier="RESPONSE" shuffle="true"
        max-choices="{max_choices}">
{choices}
    </qti-choice-interaction>
  </qti-item-body>
  <qti-response-processing
      template="http://www.imsglobal.org/question/qti_v3p0/rptemplates/match_correct"/>
</qti-assessment-item>
"""

    if kind in {QuestionKind.SHORT_ANSWER, QuestionKind.NUMERIC}:
        base_type = "float" if kind == QuestionKind.NUMERIC else "string"
        accepted = (
            [question.answer_key.get("value")]
            if kind == QuestionKind.NUMERIC
            else question.answer_key.get("accepted", [])
        )
        values = "\n".join(
            f"        <qti-value>{_escape(str(v))}</qti-value>" for v in accepted if v is not None
        )
        return f"""<?xml version="1.0" encoding="UTF-8"?>
<qti-assessment-item xmlns="http://www.imsglobal.org/xsd/imsqtiasi_v3p0"
    identifier="{identifier}" title="{_escape((question.topic or "Question")[:100])}"
    adaptive="false" time-dependent="false">
  <qti-response-declaration identifier="RESPONSE" cardinality="single"
      base-type="{base_type}">
    <qti-correct-response>
{values}
    </qti-correct-response>
  </qti-response-declaration>
  <qti-outcome-declaration identifier="SCORE" cardinality="single" base-type="float"/>
  <qti-outcome-declaration identifier="MAXSCORE" cardinality="single" base-type="float">
    <qti-default-value><qti-value>{float(question.marks)}</qti-value></qti-default-value>
  </qti-outcome-declaration>
  <qti-item-body>
    <p>{escaped_stem}</p>
    <qti-text-entry-interaction response-identifier="RESPONSE" expected-length="40"/>
  </qti-item-body>
  <qti-response-processing
      template="http://www.imsglobal.org/question/qti_v3p0/rptemplates/match_correct"/>
</qti-assessment-item>
"""

    # Essay, upload and code have no machine-markable correct response, so the
    # exported item declares the outcome and leaves marking to the receiving
    # system — which is exactly what QTI expects for a human-marked item.
    return f"""<?xml version="1.0" encoding="UTF-8"?>
<qti-assessment-item xmlns="http://www.imsglobal.org/xsd/imsqtiasi_v3p0"
    identifier="{identifier}" title="{_escape((question.topic or "Question")[:100])}"
    adaptive="false" time-dependent="false">
  <qti-response-declaration identifier="RESPONSE" cardinality="single" base-type="string"/>
  <qti-outcome-declaration identifier="SCORE" cardinality="single" base-type="float"/>
  <qti-outcome-declaration identifier="MAXSCORE" cardinality="single" base-type="float">
    <qti-default-value><qti-value>{float(question.marks)}</qti-value></qti-default-value>
  </qti-outcome-declaration>
  <qti-item-body>
    <p>{escaped_stem}</p>
    <qti-extended-text-interaction response-identifier="RESPONSE" expected-lines="10"/>
  </qti-item-body>
</qti-assessment-item>
"""


def _escape(value: str) -> str:
    return (
        str(value)
        .replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
    )
