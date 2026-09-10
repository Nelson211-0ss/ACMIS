"""Guild and student-union elections.

A voting system has one property no other module here needs, and everything in
this file exists to hold it: **the ballot must be secret and the count must be
verifiable, at the same time.** Those pull in opposite directions, and the
design that satisfies both is well established:

* an **eligibility roll** records who may vote, and is marked when they do —
  so nobody votes twice and turnout is knowable;
* a **ballot** records the choice, and carries no voter identity at all;
* the two live in separate tables with no key between them, exactly as
  `quality.EvaluationResponse` does, so the link cannot be reconstructed even
  by someone with the whole database;
* every ballot is given a **receipt token** the voter keeps, so they can
  confirm their own vote was counted without revealing it to anyone else.

What this deliberately does *not* attempt is end-to-end verifiable
cryptographic voting. A guild election run on the institution's own
infrastructure, with a returning officer and observers from each camp, is not
the threat model that needs homomorphic tallying — and a scheme nobody in the
room can explain is not more trustworthy, it is less. What it does have is the
property an election is actually disputed on: a count anyone can re-run from
the ballots, and a roll that shows exactly who was entitled to vote.
"""

from __future__ import annotations

import uuid
from datetime import date, datetime
from enum import StrEnum
from typing import Any

from sqlalchemy import (
    BigInteger,
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

from acmis.core.models import TenantRecord


class ElectionStatus(StrEnum):
    #: Being set up. Positions and dates can still change.
    DRAFT = "draft"
    #: Published: the electorate can see it and nominations are open.
    NOMINATIONS = "nominations"
    #: Nominations closed, candidates being vetted.
    VETTING = "vetting"
    #: The final list is published and campaigning runs.
    CAMPAIGN = "campaign"
    #: The poll is open.
    VOTING = "voting"
    #: Closed, being counted.
    COUNTING = "counting"
    #: Results declared.
    DECLARED = "declared"
    #: Abandoned, or annulled after a petition.
    ANNULLED = "annulled"


class Election(TenantRecord):
    """One election event: a guild election, a faculty by-election, a referendum."""

    __tablename__ = "election"

    reference: Mapped[str] = mapped_column(String(40), unique=True, nullable=False)
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    #: `guild`, `faculty`, `class`, `referendum`, `by_election`.
    kind: Mapped[str] = mapped_column(String(20), nullable=False, default="guild", index=True)
    academic_year_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("academic_year.id", ondelete="SET NULL"), index=True
    )
    description: Mapped[str | None] = mapped_column(Text)

    #: The returning officer owns the conduct of the poll and is the only
    #: person who may open it, close it and declare the result. Named on the
    #: record because a disputed election turns on who did what.
    returning_officer_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    #: Observers nominated by the candidates. They may read the roll and the
    #: tally and change nothing, which is the whole point of an observer.
    observer_staff_ids: Mapped[list[uuid.UUID]] = mapped_column(
        ARRAY(UUID(as_uuid=True)), nullable=False, default=list
    )

    nominations_open_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    nominations_close_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    campaign_starts_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    voting_opens_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    voting_closes_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    status: Mapped[str] = mapped_column(
        String(20), nullable=False, default=ElectionStatus.DRAFT, index=True
    )
    #: Turnout below this makes the result advisory rather than binding. Most
    #: guild constitutions set one, and an election that fails it and is
    #: declared anyway is the commonest ground for a petition.
    quorum_percent: Mapped[int | None] = mapped_column(Integer)

    eligible_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    ballots_cast: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    turnout_percent: Mapped[float | None] = mapped_column(Numeric(5, 2))

    #: Stamped when the poll opens and closes, by the returning officer. Not
    #: the same as the scheduled times: a poll extended by an hour because of
    #: a power cut is legitimate and has to be visible.
    opened_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    opened_by_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    closed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    closed_by_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    declared_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    declared_by_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    annulled_reason: Mapped[str | None] = mapped_column(Text)

    positions: Mapped[list[ElectionPosition]] = relationship(
        back_populates="election", cascade="all, delete-orphan", lazy="selectin"
    )

    __table_args__ = (Index("ix_election_live", "status", "voting_closes_at"),)


class ElectionPosition(TenantRecord):
    """A seat, or a referendum question.

    `seats` is why this is not a simple one-winner model: a faculty
    representative election fills three seats from one ballot, and the count
    takes the top three. A referendum is the same shape with a Yes/No
    candidate list, which is why questions live here rather than in a separate
    table.
    """

    __tablename__ = "election_position"

    election_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("election.id", ondelete="CASCADE"), nullable=False, index=True
    )
    code: Mapped[str] = mapped_column(String(40), nullable=False)
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    sequence: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    #: How many are elected to this position.
    seats: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    #: How many a voter may choose. Usually equal to `seats`; a "vote for up
    #: to two of five" ballot sets it lower than the field.
    max_choices: Mapped[int] = mapped_column(Integer, nullable=False, default=1)

    #: Who may stand and who may vote for this position. Empty means the whole
    #: electorate — a guild president is elected by everyone, a faculty
    #: representative only by that faculty, and a class representative only by
    #: that class.
    electorate_faculty_ids: Mapped[list[uuid.UUID]] = mapped_column(
        ARRAY(UUID(as_uuid=True)), nullable=False, default=list
    )
    electorate_programme_ids: Mapped[list[uuid.UUID]] = mapped_column(
        ARRAY(UUID(as_uuid=True)), nullable=False, default=list
    )
    electorate_year_of_study: Mapped[int | None] = mapped_column(Integer)
    #: `open`, `female`, `male`, `international`, `disability`, `postgraduate`.
    #: Reserved seats are common in East African guild constitutions and a
    #: system that cannot express them cannot run the election.
    reserved_for: Mapped[str | None] = mapped_column(String(30))

    #: What a candidate must satisfy: a minimum CGPA, no disciplinary finding,
    #: fees cleared. Held as data because every constitution words it
    #: differently, and checked when a nomination is vetted.
    eligibility_rules: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)

    #: A referendum question renders as a Yes/No/Abstain ballot rather than a
    #: list of people.
    is_referendum: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    question: Mapped[str | None] = mapped_column(Text)

    election: Mapped[Election] = relationship(back_populates="positions")
    candidates: Mapped[list[Candidate]] = relationship(
        back_populates="position", cascade="all, delete-orphan", lazy="selectin"
    )

    __table_args__ = (
        UniqueConstraint("election_id", "code", name="uq_election_position_code"),
        CheckConstraint("seats >= 1", name="ck_position_seats"),
        CheckConstraint("max_choices >= 1", name="ck_position_choices"),
    )


class Candidate(TenantRecord):
    """A nomination, and its progress to the ballot paper.

    Vetting is recorded rather than merely done: a candidate refused the
    ballot will ask why, and "the committee decided" is not an answer that
    survives a petition. `disqualification_reason` is the field that answers
    it.
    """

    __tablename__ = "election_candidate"

    position_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("election_position.id", ondelete="CASCADE"), nullable=False, index=True
    )
    student_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("student.id", ondelete="CASCADE"), index=True
    )
    #: A referendum's options are candidates with no student behind them.
    option_label: Mapped[str | None] = mapped_column(String(60))

    #: What appears on the ballot paper. Separate from the student's name
    #: because candidates campaign under a known form of it.
    ballot_name: Mapped[str] = mapped_column(String(200), nullable=False)
    #: Where they appear on the paper. Drawn by lot at the close of vetting,
    #: because alphabetical order measurably advantages the top of the list.
    ballot_order: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    slogan: Mapped[str | None] = mapped_column(String(200))
    manifesto: Mapped[str | None] = mapped_column(Text)
    photo_attachment_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))

    #: Most constitutions require a number of seconders from the electorate.
    nominator_student_ids: Mapped[list[uuid.UUID]] = mapped_column(
        ARRAY(UUID(as_uuid=True)), nullable=False, default=list
    )
    nomination_fee_minor: Mapped[int | None] = mapped_column(BigInteger)
    nomination_fee_invoice_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))

    #: `nominated`, `vetting`, `approved`, `disqualified`, `withdrawn`.
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="nominated", index=True)
    nominated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    vetted_by_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    vetted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    #: The checks and what each returned, so a refusal can be explained and
    #: an appeal can be answered from the record.
    eligibility_checks: Mapped[list[dict[str, Any]]] = mapped_column(
        JSONB, nullable=False, default=list
    )
    disqualification_reason: Mapped[str | None] = mapped_column(Text)
    withdrawn_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    #: Written at the declaration. Stored rather than derived so a declared
    #: result never moves, which is what makes it citable.
    votes: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    is_elected: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    position: Mapped[ElectionPosition] = relationship(back_populates="candidates")

    __table_args__ = (
        UniqueConstraint("position_id", "student_id", name="uq_candidate_once"),
        Index("ix_candidate_ballot", "position_id", "ballot_order"),
    )


class VoterRoll(TenantRecord):
    """Who may vote, and whether they have.

    Half of the arrangement that makes the ballot secret. This table knows the
    voter and *that* they voted; it does not know what they chose. `Ballot`
    knows the choice and nothing about the voter. Nothing joins them.

    Built when the poll opens rather than read live from enrolment, because
    the electorate must be fixed before voting starts: a roll that changes
    under a running poll cannot be audited, and "were they entitled to vote"
    becomes unanswerable after the fact.
    """

    __tablename__ = "election_voter_roll"

    election_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("election.id", ondelete="CASCADE"), nullable=False, index=True
    )
    student_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("student.id", ondelete="CASCADE"), nullable=False, index=True
    )
    #: The positions this voter is entitled to vote on, resolved from their
    #: faculty, programme and year when the roll was built.
    position_ids: Mapped[list[uuid.UUID]] = mapped_column(
        ARRAY(UUID(as_uuid=True)), nullable=False, default=list
    )
    #: Copied at roll time so the entitlement can be explained later without
    #: depending on a record that has since changed.
    faculty_ids: Mapped[list[uuid.UUID]] = mapped_column(
        ARRAY(UUID(as_uuid=True)), nullable=False, default=list
    )
    programme_ids: Mapped[list[uuid.UUID]] = mapped_column(
        ARRAY(UUID(as_uuid=True)), nullable=False, default=list
    )
    year_of_study: Mapped[int | None] = mapped_column(Integer)

    #: Excluded and why — suspended, fees not cleared where the constitution
    #: requires it, a disciplinary finding. Recorded so an exclusion can be
    #: challenged before the poll rather than discovered at the booth.
    is_eligible: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, index=True)
    ineligible_reason: Mapped[str | None] = mapped_column(String(300))

    voted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), index=True)
    #: `portal`, `booth`, `assisted`. An assisted vote — for a voter with a
    #: visual impairment — is recorded as such because the constitution
    #: usually requires the returning officer to note it.
    voted_via: Mapped[str | None] = mapped_column(String(20))
    #: The device the vote came from, kept for the duration of the poll only
    #: and never joined to a ballot. It answers "were three hundred votes cast
    #: from one machine", which is the shape of the fraud that actually
    #: happens.
    voted_ip_hash: Mapped[str | None] = mapped_column(String(64))

    __table_args__ = (UniqueConstraint("election_id", "student_id", name="uq_voter_roll_once"),)


class Ballot(TenantRecord):
    """One cast ballot. Carries no voter identity, by construction.

    There is no `student_id` here and there must never be one. The roll marks
    that a voter has voted; this records what was chosen. The two are written
    in the same transaction and share nothing — no key, no timestamp precise
    enough to correlate (`cast_at` is deliberately truncated to the minute),
    and no sequence number.

    `receipt_token` is the voter's own copy. It lets them confirm their ballot
    is in the count without revealing its content to anybody, and it is the
    only thing that ties a person to a ballot — held by that person alone, in
    their hand, and never stored against their name.
    """

    __tablename__ = "election_ballot"

    election_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("election.id", ondelete="CASCADE"), nullable=False, index=True
    )
    position_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("election_position.id", ondelete="CASCADE"), nullable=False, index=True
    )
    #: The candidates chosen. A list because a multi-seat position takes more
    #: than one, and empty because a deliberate abstention is a valid ballot
    #: and must be counted as turnout.
    candidate_ids: Mapped[list[uuid.UUID]] = mapped_column(
        ARRAY(UUID(as_uuid=True)), nullable=False, default=list
    )
    is_abstention: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    #: A ballot with more choices than the position allows. Kept rather than
    #: rejected at the booth so the count can report spoilt papers, which is
    #: a number observers ask for.
    is_spoilt: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    #: Truncated to the minute. A microsecond timestamp on both the roll and
    #: the ballot would let anyone with both tables line them up, which is
    #: exactly the correlation the split exists to prevent.
    cast_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    #: Shown once to the voter and stored here so a count can be verified
    #: against a voter's own receipt. Unguessable, and not derived from
    #: anything about the voter.
    receipt_token: Mapped[str] = mapped_column(String(40), unique=True, nullable=False, index=True)

    __table_args__ = (Index("ix_ballot_count", "election_id", "position_id"),)


class ElectionResult(TenantRecord):
    """The declared result for one position. Written once, at declaration.

    Stored rather than computed on read for the same reason a mark sheet is:
    a result that changes when somebody re-runs the query is not a result. The
    ballots remain, so anyone can recount and compare — which is the check
    that matters.
    """

    __tablename__ = "election_result"

    election_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("election.id", ondelete="CASCADE"), nullable=False, index=True
    )
    position_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("election_position.id", ondelete="CASCADE"), nullable=False, index=True
    )
    eligible_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    ballots_cast: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    abstentions: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    spoilt: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    turnout_percent: Mapped[float | None] = mapped_column(Numeric(5, 2))
    #: [{candidate_id, ballot_name, votes, share_percent, elected}]
    tally: Mapped[list[dict[str, Any]]] = mapped_column(JSONB, nullable=False, default=list)
    #: True when the position met the election's quorum. A result below quorum
    #: is declared and marked, not hidden: the electorate is entitled to know
    #: both the numbers and that they fell short.
    quorum_met: Mapped[bool | None] = mapped_column(Boolean)
    declared_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    declared_by_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    #: A tie broken by lot, in the presence of observers, is recorded here.
    tie_break_note: Mapped[str | None] = mapped_column(Text)

    __table_args__ = (UniqueConstraint("election_id", "position_id", name="uq_result_position"),)


class ElectionPetition(TenantRecord):
    """A challenge to the conduct or the result.

    Modelled because it is the normal end of a contested guild election, not
    an exception. A petition that arrives by letter and is settled in a
    meeting leaves no record of what was alleged or what was decided, and the
    next cohort inherits the argument.
    """

    __tablename__ = "election_petition"

    reference: Mapped[str] = mapped_column(String(40), unique=True, nullable=False)
    election_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("election.id", ondelete="CASCADE"), nullable=False, index=True
    )
    position_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("election_position.id", ondelete="SET NULL")
    )
    petitioner_student_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("student.id", ondelete="SET NULL"), index=True
    )
    #: `conduct`, `eligibility`, `count`, `campaign_finance`, `intimidation`.
    ground: Mapped[str] = mapped_column(String(30), nullable=False)
    submission: Mapped[str] = mapped_column(Text, nullable=False)
    evidence_attachment_ids: Mapped[list[uuid.UUID]] = mapped_column(
        ARRAY(UUID(as_uuid=True)), nullable=False, default=list
    )
    filed_on: Mapped[date] = mapped_column(Date, nullable=False)
    #: `filed`, `heard`, `upheld`, `dismissed`, `withdrawn`.
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="filed", index=True)
    heard_on: Mapped[date | None] = mapped_column(Date)
    panel_staff_ids: Mapped[list[uuid.UUID]] = mapped_column(
        ARRAY(UUID(as_uuid=True)), nullable=False, default=list
    )
    determination: Mapped[str | None] = mapped_column(Text)
    #: `none`, `recount`, `rerun_position`, `annul_election`, `disqualify`.
    remedy: Mapped[str | None] = mapped_column(String(30))
    decided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
