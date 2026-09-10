"""Teaching, learning materials and online assessment.

Two halves that share a course offering:

**Delivery** — the notes, slides, recordings and reading a lecturer publishes,
and the record of which students opened them. Attendance in a lecture theatre
and engagement with material are different measures, and the second is the one
that predicts a failing student early enough to do something about it.

**Online assessment** — question banks, tests built from them, timed attempts,
automatic marking of everything objective, and manual marking of everything
that is not.

The seam with `assessment` is the important design decision here, and it runs
one way only: a released online test writes its score into an
`assessment_component_score` on the student's `course_result` through
`learning.service.push_to_mark_sheet`. It never writes a final mark, never
touches a grade, and cannot reach a mark sheet that has left `draft`. The
consequence is that the approval chain — moderation, department board, faculty
board, Senate — still governs every mark that reaches a transcript, whether a
human typed it or a quiz computed it. An LMS that writes directly to the
academic record bypasses the entire governance structure of the institution,
and does so most conveniently at 2am the night before a board sits.
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
    Numeric,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import ARRAY, JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from acmis.core.models import TenantBase, TenantRecord, utcnow

# ---------------------------------------------------------------------------
# Delivery: the course space and its materials
# ---------------------------------------------------------------------------


class CourseSpace(TenantRecord):
    """The online space for one course offering.

    One per offering rather than one per course, because the material a
    lecturer publishes belongs to the cohort they taught it to. Last year's
    slides stay attached to last year's offering, which is what lets a student
    who retakes a course see both versions and a board see what was actually
    taught.
    """

    __tablename__ = "course_space"

    course_offering_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("course_offering.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
        index=True,
    )
    semester_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("semester.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    #: Denormalised for ABAC, as everywhere else.
    department_ids: Mapped[list[uuid.UUID]] = mapped_column(
        ARRAY(UUID(as_uuid=True)), nullable=False, default=list
    )
    faculty_ids: Mapped[list[uuid.UUID]] = mapped_column(
        ARRAY(UUID(as_uuid=True)), nullable=False, default=list
    )

    welcome_message: Mapped[str | None] = mapped_column(Text)
    #: The lecturer's own plan for the semester, week by week. Kept as data so
    #: the space can show "week 6 of 15" rather than an undifferentiated pile
    #: of files, which is how course spaces become unusable by week four.
    syllabus_outline: Mapped[list[dict[str, Any]]] = mapped_column(
        JSONB, nullable=False, default=list
    )
    #: Students see nothing until the space is published. A lecturer preparing
    #: material mid-semester should not have half-written notes appear.
    is_published: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, index=True)
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    #: Locked at the end of the semester: material stays readable, nothing new
    #: is added, and no attempt can be started.
    archived_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    materials: Mapped[list[Material]] = relationship(
        back_populates="space", cascade="all, delete-orphan"
    )
    assessments: Mapped[list[OnlineAssessment]] = relationship(
        back_populates="space", cascade="all, delete-orphan"
    )


class MaterialKind(StrEnum):
    NOTES = "notes"
    SLIDES = "slides"
    READING = "reading"
    #: A lecture recording. Held in object storage, streamed; the row carries
    #: only the key and the duration.
    RECORDING = "recording"
    VIDEO_LINK = "video_link"
    LINK = "link"
    DATASET = "dataset"
    PAST_PAPER = "past_paper"
    ANNOUNCEMENT = "announcement"


class Material(TenantRecord):
    """One published item in a course space."""

    __tablename__ = "material"

    space_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("course_space.id", ondelete="CASCADE"), nullable=False, index=True
    )
    kind: Mapped[str] = mapped_column(String(30), nullable=False, index=True)
    title: Mapped[str] = mapped_column(String(300), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    #: Which week of the semester this belongs to. The organising principle of
    #: the space; null means "general".
    week_number: Mapped[int | None] = mapped_column(Integer, index=True)
    topic: Mapped[str | None] = mapped_column(String(200))
    sequence: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    attachment_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    external_url: Mapped[str | None] = mapped_column(String(1000))
    #: For a recording, so a student on a metered connection knows what they
    #: are about to download.
    duration_seconds: Mapped[int | None] = mapped_column(Integer)
    size_bytes: Mapped[int | None] = mapped_column(Integer)

    is_published: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, index=True)
    #: Scheduled release. Lecturers prepare a semester's material in August and
    #: want week 7 to appear in week 7, not on day one.
    available_from: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    available_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    #: Requires the student to be registered *and* fee-cleared. Off by default:
    #: withholding lecture notes over a fee balance is a decision an
    #: institution should have to make deliberately.
    requires_fee_clearance: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    #: Downloadable, or view-only in the browser. Past papers and licensed
    #: readings are commonly the latter.
    allow_download: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)

    view_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    unique_viewer_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    space: Mapped[CourseSpace] = relationship(back_populates="materials")

    __table_args__ = (Index("ix_material_space_week", "space_id", "week_number", "sequence"),)

    @property
    def is_available(self) -> bool:
        if not self.is_published:
            return False
        now = utcnow()
        if self.available_from and now < self.available_from:
            return False
        return not (self.available_until and now > self.available_until)


class MaterialView(TenantBase):
    """That a student opened a material, and for how long. Append-only.

    Aggregated per student per material rather than one row per open: the
    question anyone asks is "has this student engaged with week 6", not "did
    they click at 14:32". `total_seconds` is what makes an early-warning
    report possible — a student who has opened nothing by week five is the one
    to contact, and by the time the first test confirms it, it is week eight.
    """

    __tablename__ = "material_view"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    material_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("material.id", ondelete="CASCADE"), nullable=False, index=True
    )
    student_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False, index=True)
    #: Read for the policy's unit scope: engagement data is protected per
    #: offering, and a view row knows only its material.
    material: Mapped[Material] = relationship(viewonly=True, lazy="joined")
    first_viewed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utcnow
    )
    last_viewed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utcnow
    )
    view_count: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    total_seconds: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    downloaded: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    #: For a recording: how far through they got, as a percentage.
    completion_percent: Mapped[int | None] = mapped_column(Integer)

    __table_args__ = (
        UniqueConstraint("material_id", "student_id", name="uq_material_view"),
        Index("ix_material_view_student", "student_id", "last_viewed_at"),
    )


# ---------------------------------------------------------------------------
# Question banks
# ---------------------------------------------------------------------------


class QuestionKind(StrEnum):
    #: Objective, machine-marked.
    MULTIPLE_CHOICE = "multiple_choice"
    #: More than one correct option; partial credit is configurable.
    MULTIPLE_RESPONSE = "multiple_response"
    TRUE_FALSE = "true_false"
    #: Free text matched against accepted answers, optionally fuzzily.
    SHORT_ANSWER = "short_answer"
    #: Numeric with a tolerance. A physics answer of 9.81 should accept 9.8.
    NUMERIC = "numeric"
    MATCHING = "matching"
    ORDERING = "ordering"
    FILL_IN_BLANK = "fill_in_blank"
    #: Human-marked, against a rubric.
    ESSAY = "essay"
    FILE_UPLOAD = "file_upload"
    #: Code submitted and run against test cases.
    CODE = "code"
    #: Moodle's "calculated" type: a stem with `{a}`/`{b}` placeholders and a
    #: formula answer, instantiated per candidate from a dataset of values.
    #: Borrowed because it solves the problem no shuffling can — every
    #: candidate gets the same question with different numbers, so an answer
    #: passed between them is wrong.
    CALCULATED = "calculated"


#: Kinds the marker can settle without a human. Everything else queues for
#: manual marking, and a test containing any of them cannot auto-release.
AUTO_MARKED_KINDS = frozenset(
    {
        QuestionKind.MULTIPLE_CHOICE,
        QuestionKind.MULTIPLE_RESPONSE,
        QuestionKind.TRUE_FALSE,
        QuestionKind.SHORT_ANSWER,
        QuestionKind.NUMERIC,
        QuestionKind.MATCHING,
        QuestionKind.ORDERING,
        QuestionKind.FILL_IN_BLANK,
        QuestionKind.CALCULATED,
    }
)


class QuestionBank(TenantRecord):
    """A reusable collection of questions, owned by a department.

    Owned by the department rather than the lecturer, so a question bank
    survives staff turnover — the commonest way an institution loses years of
    assessment material is a lecturer leaving with it on a laptop. Sharing is
    explicit: `is_shared` opens it to the whole department, which is what
    makes a bank worth building.
    """

    __tablename__ = "question_bank"

    code: Mapped[str] = mapped_column(String(40), nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    course_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("course.id", ondelete="SET NULL"), index=True
    )
    owning_unit_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("academic_unit.id", ondelete="SET NULL"), index=True
    )
    department_ids: Mapped[list[uuid.UUID]] = mapped_column(
        ARRAY(UUID(as_uuid=True)), nullable=False, default=list
    )
    faculty_ids: Mapped[list[uuid.UUID]] = mapped_column(
        ARRAY(UUID(as_uuid=True)), nullable=False, default=list
    )
    is_shared: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    question_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    questions: Mapped[list[Question]] = relationship(
        back_populates="bank", cascade="all, delete-orphan"
    )

    __table_args__ = (UniqueConstraint("code", name="uq_question_bank_code"),)


class Question(TenantRecord):
    """One question. Versioned, never edited in place once used.

    `revision` and `superseded_by_id` exist for a specific reason: a question
    used in a test that has already been sat cannot change, or the marks
    already awarded stop being explainable. Editing such a question creates a
    new revision and points the old one at it; the sat test keeps referencing
    the revision the candidates actually saw.

    `answer_key` is JSONB rather than columns because the shape genuinely
    differs per kind — a numeric tolerance, a set of accepted strings, a
    matching map, an ordering. Columns for all of them would be a table where
    nine of twelve are always null.
    """

    __tablename__ = "question"

    bank_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("question_bank.id", ondelete="CASCADE"), nullable=False, index=True
    )
    kind: Mapped[str] = mapped_column(String(30), nullable=False, index=True)
    #: The question as the candidate sees it. Markdown, with LaTeX for
    #: mathematics — a chemistry or engineering paper is unusable in plain text.
    stem: Mapped[str] = mapped_column(Text, nullable=False)
    #: An image, diagram or audio clip the question refers to.
    attachment_ids: Mapped[list[uuid.UUID]] = mapped_column(
        ARRAY(UUID(as_uuid=True)), nullable=False, default=list
    )
    marks: Mapped[float] = mapped_column(Numeric(6, 2), nullable=False, default=1)
    #: Deducted for a wrong answer. Zero by default: negative marking changes
    #: what a test measures and should be a deliberate choice.
    negative_marks: Mapped[float] = mapped_column(Numeric(6, 2), nullable=False, default=0)

    #: Kind-specific. See the class note.
    answer_key: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)
    #: For a `calculated` question: the variable sets to instantiate from, e.g.
    #: [{"a": 3, "b": 4}, {"a": 5, "b": 12}]. One set is drawn per candidate
    #: and recorded on their response, so their particular numbers — and
    #: therefore their particular correct answer — are reproducible.
    variable_sets: Mapped[list[dict[str, Any]]] = mapped_column(JSONB, nullable=False, default=list)
    #: Shown after the attempt closes, so a test is a teaching instrument and
    #: not only a measuring one.
    explanation: Mapped[str | None] = mapped_column(Text)
    #: Marking guidance for a human marker. Criteria and marks per criterion.
    rubric: Mapped[list[dict[str, Any]]] = mapped_column(JSONB, nullable=False, default=list)

    #: Curriculum alignment: which learning outcome this question tests. What
    #: makes an accreditation self-assessment answerable with evidence rather
    #: than assertion.
    learning_outcome: Mapped[str | None] = mapped_column(String(300))
    topic: Mapped[str | None] = mapped_column(String(200), index=True)
    #: `remember`, `understand`, `apply`, `analyse`, `evaluate`, `create` —
    #: Bloom's levels, so a paper can be checked for balance rather than being
    #: twelve recall questions with a nominal "analysis" label.
    cognitive_level: Mapped[str | None] = mapped_column(String(20), index=True)
    difficulty: Mapped[str] = mapped_column(String(20), nullable=False, default="medium")

    #: Item statistics, recomputed after each use. `facility` is the proportion
    #: who got it right; `discrimination` is how well it separates strong
    #: candidates from weak. A question with high facility and near-zero
    #: discrimination is measuring nothing and should be retired.
    times_used: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    times_answered: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    facility_index: Mapped[float | None] = mapped_column(Numeric(4, 3))
    discrimination_index: Mapped[float | None] = mapped_column(Numeric(4, 3))

    revision: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    superseded_by_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    #: Frozen once the question has been sat. Enforced in the service.
    is_locked: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, index=True)

    bank: Mapped[QuestionBank] = relationship(back_populates="questions")
    options: Mapped[list[QuestionOption]] = relationship(
        back_populates="question",
        cascade="all, delete-orphan",
        lazy="selectin",
        order_by="QuestionOption.sequence",
    )

    __table_args__ = (
        CheckConstraint("marks > 0", name="question_marks_positive"),
        Index("ix_question_bank_kind", "bank_id", "kind", "is_active"),
    )

    @property
    def is_auto_marked(self) -> bool:
        return self.kind in AUTO_MARKED_KINDS


class QuestionOption(TenantRecord):
    """A choice for a selection question.

    `is_correct` lives here rather than in `answer_key` so a partial-credit
    calculation over a multiple-response question is a straightforward set
    comparison, and so an option can carry its own feedback — telling a
    candidate *why* the distractor they picked was wrong is the whole
    pedagogical value of an online test.
    """

    __tablename__ = "question_option"

    question_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("question.id", ondelete="CASCADE"), nullable=False, index=True
    )
    label: Mapped[str] = mapped_column(String(10), nullable=False)
    body: Mapped[str] = mapped_column(Text, nullable=False)
    is_correct: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    feedback: Mapped[str | None] = mapped_column(Text)
    sequence: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    #: Excluded from shuffling. "None of the above" must stay last.
    pin_position: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    question: Mapped[Question] = relationship(back_populates="options")

    __table_args__ = (UniqueConstraint("question_id", "label", name="uq_question_option_label"),)


# ---------------------------------------------------------------------------
# Online assessments
# ---------------------------------------------------------------------------


class AssessmentKind(StrEnum):
    #: Formative. Unlimited attempts, immediate feedback, no marks that count.
    PRACTICE = "practice"
    QUIZ = "quiz"
    TEST = "test"
    ASSIGNMENT = "assignment"
    #: Counts toward the course result. Everything about it is stricter.
    EXAMINATION = "examination"


class Behaviour(StrEnum):
    """How a candidate interacts with a question. Moodle's "question behaviour".

    Adopted wholesale from Moodle's question engine, which has had two decades
    and tens of millions of sittings to find the edges. The distinction it
    draws — between *what a question is* and *how the candidate interacts with
    it* — is the one most home-grown quiz tools miss, and missing it means a
    formative practice quiz and a final examination need separate code paths
    for the same question types.

    * `deferred_feedback` — answer everything, submit once, see nothing until
      after. The classic examination.
    * `immediate_feedback` — check each answer as you go, one try each. A
      revision quiz.
    * `interactive_with_tries` — several tries per question, each wrong try
      costing a fraction of the marks, with a hint between. The most
      pedagogically useful mode and the reason `try_penalty_fraction` exists.
    * `adaptive` — like interactive but with no fixed try limit.
    * `manual` — nothing is auto-marked; every answer goes to a human.
    """

    DEFERRED_FEEDBACK = "deferred_feedback"
    IMMEDIATE_FEEDBACK = "immediate_feedback"
    INTERACTIVE_WITH_TRIES = "interactive_with_tries"
    ADAPTIVE = "adaptive"
    MANUAL = "manual"


class AssessmentStatus(StrEnum):
    DRAFT = "draft"
    #: Reviewed by a second member of staff before candidates see it. A typo in
    #: a question stem is a complaint; a wrong answer key is an appeal.
    REVIEW = "review"
    SCHEDULED = "scheduled"
    OPEN = "open"
    CLOSED = "closed"
    MARKING = "marking"
    MARKED = "marked"
    #: Results visible to candidates.
    RELEASED = "released"


class OnlineAssessment(TenantRecord):
    """A test, quiz, assignment or online examination."""

    __tablename__ = "online_assessment"

    space_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("course_space.id", ondelete="CASCADE"), nullable=False, index=True
    )
    course_offering_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("course_offering.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    kind: Mapped[str] = mapped_column(String(20), nullable=False, index=True)
    title: Mapped[str] = mapped_column(String(300), nullable=False)
    instructions: Mapped[str | None] = mapped_column(Text)

    #: Which component of the course's assessment scheme this feeds. Null for
    #: practice. This is the *only* route by which an online score reaches the
    #: academic record, and it lands as a component score on a draft mark
    #: sheet — never as a final mark, and never past the approval chain.
    assessment_component_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("assessment_component.id", ondelete="SET NULL"), index=True
    )
    total_marks: Mapped[float] = mapped_column(Numeric(7, 2), nullable=False, default=0)
    pass_mark_percent: Mapped[int | None] = mapped_column(Integer)

    # --- availability ------------------------------------------------------
    opens_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), index=True)
    closes_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), index=True)
    #: Minutes. Counted from the candidate's own start, so a late starter gets
    #: the full duration but cannot run past `closes_at`.
    duration_minutes: Mapped[int | None] = mapped_column(Integer)
    #: How many times a candidate may sit it. `1` for anything that counts.
    max_attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    #: `best`, `latest`, `average`, `first` — which attempt's score counts.
    attempt_grading: Mapped[str] = mapped_column(String(20), nullable=False, default="best")
    #: How the candidate interacts with each question. See `Behaviour`.
    behaviour: Mapped[str] = mapped_column(
        String(30), nullable=False, default=Behaviour.DEFERRED_FEEDBACK
    )
    #: For `interactive_with_tries`: how many tries per question, and what
    #: fraction of the marks each wrong try costs. Moodle's default is three
    #: tries at a third each, which is a reasonable place to start.
    tries_per_question: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    try_penalty_fraction: Mapped[float] = mapped_column(Numeric(4, 3), nullable=False, default=0)

    # --- integrity ---------------------------------------------------------
    #: Shuffling makes casual copying between adjacent candidates useless. It
    #: is not security — a determined attempt defeats it — but it is cheap and
    #: it removes the most common opportunistic cheating in a computer lab.
    shuffle_questions: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    shuffle_options: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    #: One question per screen, no going back. Used for tests where later
    #: questions would give away earlier ones.
    one_question_per_page: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    allow_backtracking: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    #: A password handed out in the invigilated room, so a remote candidate
    #: cannot sit an exam meant to be taken under supervision.
    access_password_hash: Mapped[str | None] = mapped_column(String(64))
    #: CIDR ranges the attempt must originate from — the campus laboratory.
    allowed_ip_ranges: Mapped[list[str]] = mapped_column(
        ARRAY(String(60)), nullable=False, default=list
    )
    #: Records tab-switches and focus loss. Recorded as *signals*, never
    #: treated as proof: a dropped connection in Gulu and a candidate opening
    #: another tab look identical from the server, and a system that
    #: auto-fails on the difference will fail honest students.
    monitor_focus_loss: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    max_focus_losses: Mapped[int | None] = mapped_column(Integer)
    require_webcam: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    # --- feedback ----------------------------------------------------------
    #: When candidates see their score: `never`, `immediately`, `after_close`,
    #: `on_release`. Anything that counts should be `on_release`, so marking
    #: and moderation happen before anyone compares notes.
    score_visibility: Mapped[str] = mapped_column(String(20), nullable=False, default="on_release")
    show_correct_answers: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    show_explanations: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    status: Mapped[str] = mapped_column(
        String(20), nullable=False, default=AssessmentStatus.DRAFT, index=True
    )
    #: Reviewer must differ from the author. Same principle as a mark sheet.
    authored_by_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    reviewed_by_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    review_comments: Mapped[str | None] = mapped_column(Text)
    released_by_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    released_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    pushed_to_mark_sheet_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    #: Cohort statistics, computed at marking. Same purpose as on a mark sheet:
    #: a mean of 31 is a question about the paper before it is a question about
    #: the students.
    attempt_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    submitted_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    mean_score: Mapped[float | None] = mapped_column(Numeric(6, 2))
    median_score: Mapped[float | None] = mapped_column(Numeric(6, 2))
    standard_deviation: Mapped[float | None] = mapped_column(Numeric(6, 2))
    #: Attempts still awaiting a human marker.
    pending_manual_marking: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    department_ids: Mapped[list[uuid.UUID]] = mapped_column(
        ARRAY(UUID(as_uuid=True)), nullable=False, default=list
    )
    faculty_ids: Mapped[list[uuid.UUID]] = mapped_column(
        ARRAY(UUID(as_uuid=True)), nullable=False, default=list
    )

    space: Mapped[CourseSpace] = relationship(back_populates="assessments")
    items: Mapped[list[AssessmentItem]] = relationship(
        back_populates="assessment",
        cascade="all, delete-orphan",
        order_by="AssessmentItem.sequence",
    )
    attempts: Mapped[list[Attempt]] = relationship(
        back_populates="assessment", cascade="all, delete-orphan"
    )

    __table_args__ = (
        CheckConstraint("max_attempts >= 1", name="attempts_at_least_one"),
        Index("ix_online_assessment_window", "status", "opens_at", "closes_at"),
    )

    @property
    def counts_for_credit(self) -> bool:
        return self.kind != AssessmentKind.PRACTICE and (self.assessment_component_id is not None)

    def is_open_now(self) -> bool:
        if self.status not in {AssessmentStatus.OPEN, AssessmentStatus.SCHEDULED}:
            return False
        now = utcnow()
        if self.opens_at and now < self.opens_at:
            return False
        return not (self.closes_at and now > self.closes_at)


class AssessmentItem(TenantRecord):
    """A question's place in an assessment, or a random draw from a bank.

    Two modes, and the second is what makes online testing at scale viable:
    a *fixed* item references one question, while a *pooled* item says "draw
    three questions on Normalisation, medium difficulty, from bank X". Every
    candidate then gets a different but equivalent paper, which removes most of
    the value of a leaked question set.

    The draw is recorded per attempt (see `AttemptResponse.question_id`), so a
    candidate's paper is exactly reproducible when they query their mark.
    """

    __tablename__ = "assessment_item"

    assessment_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("online_assessment.id", ondelete="CASCADE"), nullable=False, index=True
    )
    sequence: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    section: Mapped[str | None] = mapped_column(String(80))
    #: `fixed` or `pooled`.
    mode: Mapped[str] = mapped_column(String(20), nullable=False, default="fixed")

    question_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("question.id", ondelete="RESTRICT"), index=True
    )
    #: Pooled: where to draw from and how many.
    bank_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("question_bank.id", ondelete="RESTRICT")
    )
    draw_count: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    draw_filters: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)
    #: Overrides the question's own mark for this paper.
    marks_override: Mapped[float | None] = mapped_column(Numeric(6, 2))
    is_mandatory: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)

    assessment: Mapped[OnlineAssessment] = relationship(back_populates="items")

    __table_args__ = (
        CheckConstraint(
            "(mode = 'fixed' AND question_id IS NOT NULL) OR "
            "(mode = 'pooled' AND bank_id IS NOT NULL)",
            name="item_has_a_source",
        ),
        CheckConstraint("draw_count >= 1", name="draw_at_least_one"),
    )


class AttemptStatus(StrEnum):
    IN_PROGRESS = "in_progress"
    SUBMITTED = "submitted"
    #: The clock ran out. Answers already saved are kept and marked — a
    #: candidate who ran out of time has still answered eight questions, and
    #: discarding them would be indefensible.
    EXPIRED = "expired"
    #: The connection dropped and the attempt was never resumed or submitted.
    #: Distinct from expired because it is the institution's fault as often as
    #: the candidate's, and the two are handled differently.
    ABANDONED = "abandoned"
    MARKED = "marked"
    VOIDED = "voided"


class Attempt(TenantRecord):
    """One candidate's sitting of one assessment.

    Answers are saved as they are given (see `AttemptResponse`), not at
    submission. A power cut in the third hour of an examination must not cost a
    candidate their paper — which, in the environments this system is built
    for, is not a hypothetical.
    """

    __tablename__ = "assessment_attempt"

    assessment_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("online_assessment.id", ondelete="CASCADE"), nullable=False, index=True
    )
    student_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("student.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    attempt_number: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    status: Mapped[str] = mapped_column(
        String(20), nullable=False, default=AttemptStatus.IN_PROGRESS, index=True
    )

    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    #: Computed at start from the duration and the assessment's close time. The
    #: server's deadline, not the browser's — a client-side timer is a
    #: suggestion.
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), index=True)
    submitted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_activity_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    #: Extra time granted to a candidate entitled to it. Read from the
    #: student's `exam_accommodations`, applied here, and visible to the
    #: examinations office.
    extra_time_minutes: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    extra_time_reason: Mapped[str | None] = mapped_column(String(300))

    #: The paper this candidate actually saw: the drawn question ids in their
    #: presented order, with the option order per question. Without it a
    #: shuffled, pooled paper cannot be reconstructed, and "question 4" means
    #: nothing when a candidate queries their mark.
    presented_paper: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)

    auto_score: Mapped[float | None] = mapped_column(Numeric(7, 2))
    manual_score: Mapped[float | None] = mapped_column(Numeric(7, 2))
    total_score: Mapped[float | None] = mapped_column(Numeric(7, 2), index=True)
    percentage: Mapped[float | None] = mapped_column(Numeric(5, 2))
    marked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    marked_by_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    #: Counts toward the course result. False for a superseded attempt under
    #: `attempt_grading`, and for practice.
    counts_for_grade: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)

    ip_address: Mapped[str | None] = mapped_column(String(60))
    user_agent: Mapped[str | None] = mapped_column(String(500))
    #: Integrity signals: focus losses, paste events, resumptions, IP changes.
    #: Signals, not verdicts. An invigilator reads them; nothing here decides.
    integrity_events: Mapped[list[dict[str, Any]]] = mapped_column(
        JSONB, nullable=False, default=list
    )
    focus_loss_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    resumption_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    #: Set when a member of staff reviews the signals and forms a view. Free
    #: text, because "flagged" without a human's judgement is worse than
    #: nothing.
    integrity_review: Mapped[str | None] = mapped_column(Text)
    integrity_reviewed_by_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    voided_reason: Mapped[str | None] = mapped_column(Text)

    #: Every unit-scoped policy on an attempt or a response reads the
    #: offering, the department and the faculty — none of which are columns
    #: here. The resource descriptor reaches them through this.
    assessment: Mapped[OnlineAssessment] = relationship(back_populates="attempts")
    responses: Mapped[list[AttemptResponse]] = relationship(
        back_populates="attempt", cascade="all, delete-orphan"
    )

    __table_args__ = (
        UniqueConstraint("assessment_id", "student_id", "attempt_number", name="uq_attempt_number"),
        Index("ix_attempt_live", "status", "expires_at"),
    )

    @property
    def is_live(self) -> bool:
        return self.status == AttemptStatus.IN_PROGRESS


class AttemptResponse(TenantRecord):
    """One answer, saved as the candidate gives it.

    `question_id` is stored per response rather than derived from the
    assessment, because a pooled item means every candidate saw a different
    question. Together with `Attempt.presented_paper` this makes a sat paper
    exactly reproducible — which is what "here is the question you answered
    and here is what you wrote" requires.
    """

    __tablename__ = "assessment_response"

    attempt_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("assessment_attempt.id", ondelete="CASCADE"), nullable=False, index=True
    )
    item_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("assessment_item.id", ondelete="SET NULL")
    )
    question_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("question.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    #: The revision the candidate saw. A question edited afterwards does not
    #: change what they were asked.
    question_revision: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    sequence: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    #: Kind-specific: {"option_labels": ["B"]}, {"text": "..."},
    #: {"value": 9.81}, {"pairs": {...}}, {"attachment_id": "..."}.
    answer: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)
    answered_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    #: Time spent on this question. Used for item analysis and, occasionally,
    #: to support a candidate's claim that the platform was slow.
    seconds_spent: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    #: The candidate marked it for review before submitting.
    flagged: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    #: The variable set this candidate's `calculated` question was
    #: instantiated with. Without it their correct answer is unknowable after
    #: the fact.
    variables: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)

    marks_available: Mapped[float] = mapped_column(Numeric(6, 2), nullable=False, default=0)
    #: The canonical result, in Moodle's terms: a *fraction* of the question
    #: earned, from 0 to 1 (negative for a penalised wrong answer). `marks_
    #: awarded` is `fraction x marks_available`, stored alongside because
    #: every report and every mark sheet wants marks rather than fractions.
    #:
    #: Storing the fraction is what makes a regrade after a marks change
    #: arithmetic rather than remarking: change the question's weight in a
    #: paper and every candidate's mark follows, because the *judgement* about
    #: their answer was never entangled with the weight.
    fraction: Mapped[float | None] = mapped_column(Numeric(6, 5))
    marks_awarded: Mapped[float | None] = mapped_column(Numeric(6, 2))
    #: For `interactive_with_tries`: how many tries were used, and the
    #: cumulative penalty. Kept per response because a candidate who got it on
    #: the third try earned less than one who got it first time, and the
    #: transcript of their attempt has to show why.
    tries_used: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    penalty_fraction: Mapped[float] = mapped_column(Numeric(4, 3), nullable=False, default=0)
    #: Every try, kept in order: what was answered, what fraction it earned.
    #: The record that answers "I clicked the right answer and it said wrong".
    try_history: Mapped[list[dict[str, Any]]] = mapped_column(JSONB, nullable=False, default=list)
    is_correct: Mapped[bool | None] = mapped_column(Boolean)
    #: `auto` or `manual`. Which marked it, and therefore who to ask about it.
    marked_by: Mapped[str | None] = mapped_column(String(10))
    marked_by_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    marker_comment: Mapped[str | None] = mapped_column(Text)
    #: Rubric criteria scores for an essay: [{criterion, marks, comment}].
    rubric_scores: Mapped[list[dict[str, Any]]] = mapped_column(JSONB, nullable=False, default=list)
    #: Set when a candidate disputes this one answer. Narrower than a formal
    #: appeal and resolved by the marker, which is where most disputes end.
    queried_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    query_note: Mapped[str | None] = mapped_column(Text)
    query_resolution: Mapped[str | None] = mapped_column(Text)

    attempt: Mapped[Attempt] = relationship(back_populates="responses")

    __table_args__ = (
        UniqueConstraint("attempt_id", "question_id", name="uq_response_question"),
        Index("ix_response_marking_queue", "question_id", "marks_awarded"),
    )


class Assignment(TenantRecord):
    """Work submitted as a file rather than answered in the browser.

    A separate table from `OnlineAssessment` because the lifecycle differs in
    ways that matter: submission is a file with a deadline and a late penalty,
    marking is always human, and plagiarism screening applies. Modelling it as
    a one-question quiz would lose all three.
    """

    __tablename__ = "assignment"

    space_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("course_space.id", ondelete="CASCADE"), nullable=False, index=True
    )
    course_offering_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("course_offering.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    assessment_component_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("assessment_component.id", ondelete="SET NULL")
    )
    title: Mapped[str] = mapped_column(String(300), nullable=False)
    brief: Mapped[str] = mapped_column(Text, nullable=False)
    attachment_ids: Mapped[list[uuid.UUID]] = mapped_column(
        ARRAY(UUID(as_uuid=True)), nullable=False, default=list
    )
    total_marks: Mapped[float] = mapped_column(Numeric(7, 2), nullable=False, default=100)
    rubric: Mapped[list[dict[str, Any]]] = mapped_column(JSONB, nullable=False, default=list)

    opens_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    due_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)
    #: Submissions accepted until here, with a penalty. Modelled because every
    #: institution does it informally anyway, and an unmodelled late window
    #: means the penalty is applied inconsistently by hand.
    accept_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    late_penalty_percent_per_day: Mapped[float] = mapped_column(
        Numeric(5, 2), nullable=False, default=0
    )
    #: `individual` or `group`.
    submission_mode: Mapped[str] = mapped_column(String(20), nullable=False, default="individual")
    max_file_count: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    allowed_extensions: Mapped[list[str]] = mapped_column(
        ARRAY(String(10)), nullable=False, default=list
    )
    max_file_bytes: Mapped[int] = mapped_column(Integer, nullable=False, default=10 * 1024 * 1024)
    #: Similarity screening. A score, never a verdict: a high figure on a
    #: methods section that quotes a standard protocol is expected, and a
    #: system that treats the number as a finding produces unjust accusations.
    similarity_check: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    similarity_threshold_percent: Mapped[int | None] = mapped_column(Integer)
    #: Anonymous marking: the marker does not see who wrote it. The single
    #: most effective structural measure against marking bias.
    blind_marking: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    #: Two markers, with a third resolving a disagreement beyond a tolerance.
    double_marking: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    status: Mapped[str] = mapped_column(String(20), nullable=False, default="draft", index=True)
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    released_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    pushed_to_mark_sheet_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    department_ids: Mapped[list[uuid.UUID]] = mapped_column(
        ARRAY(UUID(as_uuid=True)), nullable=False, default=list
    )
    faculty_ids: Mapped[list[uuid.UUID]] = mapped_column(
        ARRAY(UUID(as_uuid=True)), nullable=False, default=list
    )

    submissions: Mapped[list[Submission]] = relationship(
        back_populates="assignment", cascade="all, delete-orphan"
    )


class Submission(TenantRecord):
    """A student's submitted work, and its marking."""

    __tablename__ = "assignment_submission"

    assignment_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("assignment.id", ondelete="CASCADE"), nullable=False, index=True
    )
    student_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("student.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    #: For group work: every member, so a mark applies to all of them and the
    #: audit trail shows who submitted on the group's behalf.
    group_member_ids: Mapped[list[uuid.UUID]] = mapped_column(
        ARRAY(UUID(as_uuid=True)), nullable=False, default=list
    )
    attempt_number: Mapped[int] = mapped_column(Integer, nullable=False, default=1)

    submitted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    attachment_ids: Mapped[list[uuid.UUID]] = mapped_column(
        ARRAY(UUID(as_uuid=True)), nullable=False, default=list
    )
    text_response: Mapped[str | None] = mapped_column(Text)
    #: Days late, and the penalty applied. Both stored: a student is entitled
    #: to see the raw mark and the deduction separately.
    days_late: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    penalty_percent: Mapped[float] = mapped_column(Numeric(5, 2), nullable=False, default=0)

    status: Mapped[str] = mapped_column(String(20), nullable=False, default="draft", index=True)
    raw_score: Mapped[float | None] = mapped_column(Numeric(7, 2))
    final_score: Mapped[float | None] = mapped_column(Numeric(7, 2))
    percentage: Mapped[float | None] = mapped_column(Numeric(5, 2))
    rubric_scores: Mapped[list[dict[str, Any]]] = mapped_column(JSONB, nullable=False, default=list)
    feedback: Mapped[str | None] = mapped_column(Text)
    feedback_attachment_ids: Mapped[list[uuid.UUID]] = mapped_column(
        ARRAY(UUID(as_uuid=True)), nullable=False, default=list
    )
    marked_by_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    marked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    #: Second marker, where double marking applies, with their independent
    #: score kept separately so the divergence is visible.
    second_marked_by_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    second_score: Mapped[float | None] = mapped_column(Numeric(7, 2))
    reconciled_score: Mapped[float | None] = mapped_column(Numeric(7, 2))
    reconciled_by_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))

    similarity_percent: Mapped[float | None] = mapped_column(Numeric(5, 2))
    similarity_report_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    released_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    assignment: Mapped[Assignment] = relationship(back_populates="submissions")

    __table_args__ = (
        UniqueConstraint(
            "assignment_id", "student_id", "attempt_number", name="uq_submission_attempt"
        ),
        Index("ix_submission_marking_queue", "assignment_id", "status"),
    )


class EngagementSnapshot(TenantBase):
    """A student's engagement in one course, computed weekly.

    The early-warning signal. By the time a first test confirms a student is
    struggling it is week eight; a student who has opened no material and
    attempted no practice quiz by week four is identifiable in week four. Kept
    as snapshots rather than recomputed on demand so a trend is visible and so
    the report is cheap enough to run for every student every week.
    """

    __tablename__ = "engagement_snapshot"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    student_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False, index=True)
    course_offering_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), nullable=False, index=True
    )
    week_number: Mapped[int] = mapped_column(Integer, nullable=False)
    captured_on: Mapped[date] = mapped_column(Date, nullable=False, index=True)

    materials_available: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    materials_viewed: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    minutes_on_material: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    assessments_available: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    assessments_attempted: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    mean_assessment_percent: Mapped[float | None] = mapped_column(Numeric(5, 2))
    assignments_due: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    assignments_submitted: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    days_since_last_activity: Mapped[int | None] = mapped_column(Integer)
    #: `engaged`, `slipping`, `at_risk`, `disengaged`. A prompt for a
    #: conversation, not a decision — nothing in the system acts on it.
    risk_band: Mapped[str | None] = mapped_column(String(20), index=True)

    __table_args__ = (
        UniqueConstraint(
            "student_id", "course_offering_id", "week_number", name="uq_engagement_week"
        ),
        Index("ix_engagement_risk", "course_offering_id", "risk_band", "captured_on"),
    )
