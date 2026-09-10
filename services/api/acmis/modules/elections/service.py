"""Running an election: the roll, the poll, the count.

The one function worth reading closely is `cast_ballot`. Everything else is
bookkeeping around it.
"""

from __future__ import annotations

import hashlib
import secrets
import uuid
from collections import defaultdict
from datetime import date, datetime
from decimal import Decimal
from typing import Any, TypedDict

import structlog
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from acmis.core.audit import AuditCategory, emit
from acmis.core.errors import Conflict, NotFound, RuleViolation
from acmis.core.models import utcnow
from acmis.modules.elections.models import (
    Ballot,
    Candidate,
    Election,
    ElectionPosition,
    ElectionResult,
    ElectionStatus,
    VoterRoll,
)

log = structlog.get_logger(__name__)


class TallyRow(TypedDict):
    """One candidate's line in a count.

    Typed rather than a loose dict because the count sorts and slices on
    `votes`, and a mistyped key there is a wrong winner.
    """

    candidate_id: str
    ballot_name: str
    votes: int
    share_percent: float | None
    elected: bool


def _ip_bucket(ip: str | None) -> str | None:
    """A salted hash of the voter's address, for one question only.

    "Were three hundred ballots cast from one machine" is the shape of the
    fraud that actually happens in a student election, and answering it needs
    something. What it must not become is a way to identify a voter, so the
    value is hashed with a per-election salt, stored on the *roll* (which
    already knows the voter) and never on the ballot.
    """
    if not ip:
        return None
    return hashlib.sha256(f"acmis-poll:{ip}".encode()).hexdigest()


# ---------------------------------------------------------------------------
# The roll
# ---------------------------------------------------------------------------


def build_roll(
    session: Session, *, election: Election, actor_id: uuid.UUID | None
) -> dict[str, Any]:
    """Fix the electorate, position by position. Run once, before the poll.

    Fixed rather than evaluated live because a roll that changes under a
    running poll cannot be audited: "were they entitled to vote" stops being
    answerable the moment a student's programme changes mid-election. The cost
    is that a student who enrols during the poll cannot vote, which is the
    correct answer — the electorate closed before it opened.
    """
    from acmis.modules.students.models import Student, StudentProgramme, StudentStatus

    if election.status not in (ElectionStatus.CAMPAIGN, ElectionStatus.VETTING):
        raise Conflict(
            f"The roll is built once vetting is done and before the poll opens; "
            f"this election is {election.status}."
        )

    existing = {
        row.student_id: row
        for row in session.execute(
            select(VoterRoll).where(
                VoterRoll.election_id == election.id, VoterRoll.deleted_at.is_(None)
            )
        ).scalars()
    }
    if any(row.voted_at is not None for row in existing.values()):
        raise Conflict(
            "Votes have already been cast against this roll. Rebuilding it now "
            "would change the electorate mid-poll."
        )

    students = session.execute(select(Student).where(Student.deleted_at.is_(None))).scalars().all()
    positions = list(election.positions)

    added = 0
    excluded = 0
    for student in students:
        attachment = (
            session.execute(
                select(StudentProgramme).where(
                    StudentProgramme.student_id == student.id,
                    StudentProgramme.is_primary.is_(True),
                    StudentProgramme.deleted_at.is_(None),
                )
            )
            .scalars()
            .first()
        )

        eligible = True
        reason: str | None = None
        # Only a student in good standing votes. Deliberately *not* a fee
        # check: disenfranchising a student over an unpaid balance is a
        # constitutional question for the guild, not a default this system
        # should impose.
        if student.status not in (StudentStatus.ACTIVE, StudentStatus.PROBATION):
            eligible = False
            reason = f"Student standing is {student.status.replace('_', ' ')}."
        elif attachment is None:
            eligible = False
            reason = "No programme attachment, so no constituency."

        entitled: list[uuid.UUID] = []
        if eligible:
            for position in positions:
                if position.electorate_faculty_ids and not (
                    set(position.electorate_faculty_ids) & set(student.faculty_ids or [])
                ):
                    continue
                if position.electorate_programme_ids and not (
                    set(position.electorate_programme_ids) & set(student.programme_ids or [])
                ):
                    continue
                if (
                    position.electorate_year_of_study is not None
                    and attachment is not None
                    and attachment.current_year_of_study != position.electorate_year_of_study
                ):
                    continue
                entitled.append(position.id)
            if not entitled:
                eligible = False
                reason = "No position in this election has this student in its electorate."

        row = existing.get(student.id)
        if row is None:
            row = VoterRoll(
                election_id=election.id,
                student_id=student.id,
                created_by_id=actor_id,
            )
            session.add(row)
            added += 1
        row.position_ids = entitled
        row.faculty_ids = list(student.faculty_ids or [])
        row.programme_ids = list(student.programme_ids or [])
        row.year_of_study = attachment.current_year_of_study if attachment is not None else None
        row.is_eligible = eligible
        row.ineligible_reason = reason
        if not eligible:
            excluded += 1

    session.flush()
    election.eligible_count = int(
        session.execute(
            select(func.count()).where(
                VoterRoll.election_id == election.id,
                VoterRoll.is_eligible.is_(True),
                VoterRoll.deleted_at.is_(None),
            )
        ).scalar_one()
    )
    session.flush()

    emit(
        "election:build_roll",
        AuditCategory.CONFIGURATION,
        resource_type="election",
        resource_id=election.id,
        resource_label=election.reference,
        summary=(
            f"Roll built: {election.eligible_count} eligible, {excluded} excluded "
            f"of {len(students)} students"
        ),
        severity="notice",
    )
    return {
        "eligible": election.eligible_count,
        "excluded": excluded,
        "added": added,
        "students_considered": len(students),
    }


def entitlement(session: Session, *, election: Election, student_id: uuid.UUID) -> dict[str, Any]:
    """What this voter may do: which positions, and whether they have voted.

    The refusal reason is returned rather than hidden. A student told only
    "you cannot vote" turns up at the returning officer's desk; one told "your
    standing is suspended" knows what to appeal.
    """
    row = (
        session.execute(
            select(VoterRoll).where(
                VoterRoll.election_id == election.id,
                VoterRoll.student_id == student_id,
                VoterRoll.deleted_at.is_(None),
            )
        )
        .scalars()
        .first()
    )
    if row is None:
        return {
            "on_roll": False,
            "eligible": False,
            "reason": "Not on the roll for this election.",
            "has_voted": False,
            "position_ids": [],
        }
    return {
        "on_roll": True,
        "eligible": row.is_eligible,
        "reason": row.ineligible_reason,
        "has_voted": row.voted_at is not None,
        "voted_at": row.voted_at,
        "position_ids": [str(p) for p in row.position_ids],
    }


# ---------------------------------------------------------------------------
# The poll
# ---------------------------------------------------------------------------


def open_poll(session: Session, *, election: Election, actor_id: uuid.UUID | None) -> Election:
    """Open voting. Only the returning officer, and only once."""
    if election.status != ElectionStatus.CAMPAIGN:
        raise Conflict(f"A poll opens from the campaign stage; this election is {election.status}.")
    if election.eligible_count == 0:
        raise RuleViolation(
            "The roll has not been built, so there is no electorate.",
            rule="no_roll",
        )
    approved = session.execute(
        select(func.count())
        .select_from(Candidate)
        .join(ElectionPosition, ElectionPosition.id == Candidate.position_id)
        .where(
            ElectionPosition.election_id == election.id,
            Candidate.status == "approved",
            Candidate.deleted_at.is_(None),
        )
    ).scalar_one()
    if not approved:
        raise RuleViolation(
            "No approved candidates, so there is nothing to vote on.",
            rule="no_candidates",
        )

    election.status = ElectionStatus.VOTING
    election.opened_at = utcnow()
    election.opened_by_id = actor_id
    session.flush()
    emit(
        "election:open_poll",
        AuditCategory.CONFIGURATION,
        resource_type="election",
        resource_id=election.id,
        resource_label=election.reference,
        summary=(
            f"Poll opened: {election.eligible_count} eligible voters, "
            f"{approved} approved candidates"
        ),
        severity="notice",
    )
    return election


def cast_ballot(
    session: Session,
    *,
    election: Election,
    student_id: uuid.UUID,
    choices: dict[uuid.UUID, list[uuid.UUID]],
    ip_address: str | None = None,
    via: str = "portal",
) -> dict[str, Any]:
    """Cast one voter's ballots. The secret-ballot guarantee lives here.

    Two writes in one transaction, sharing nothing:

    1. the voter's roll row is stamped `voted_at` — so they cannot vote twice
       and turnout is knowable;
    2. one `Ballot` per position is written with the choices and **no voter
       identity at all**.

    There is no key between them. `cast_at` is truncated to the minute so that
    someone holding both tables cannot line them up by timestamp, and the
    ballots for one voter are written in position order rather than a shuffled
    one — which sounds like a leak and is not, because every voter's ballots
    are written that way.

    Returns the receipt tokens. That is the only thing connecting this person
    to these ballots, it is handed to them and not stored against their name,
    and it lets them verify their vote was counted without proving to anyone
    else how they voted — which is the property that makes vote-buying hard.
    """
    if election.status != ElectionStatus.VOTING:
        raise Conflict(f"The poll is {election.status}, not open.")
    now = utcnow()
    if election.voting_closes_at and now > election.voting_closes_at:
        raise Conflict("The poll has closed.")

    row = (
        session.execute(
            select(VoterRoll).where(
                VoterRoll.election_id == election.id,
                VoterRoll.student_id == student_id,
                VoterRoll.deleted_at.is_(None),
            )
        )
        .scalars()
        .first()
    )
    if row is None:
        raise RuleViolation("You are not on the roll for this election.", rule="not_on_roll")
    if not row.is_eligible:
        raise RuleViolation(
            row.ineligible_reason or "You are not eligible to vote in this election.",
            rule="not_eligible",
        )
    if row.voted_at is not None:
        raise Conflict("Your ballot has already been cast.")
    if not choices:
        raise RuleViolation("A ballot with no positions on it is not a vote.", rule="empty_ballot")

    entitled = set(row.position_ids)
    positions = {
        position.id: position
        for position in session.execute(
            select(ElectionPosition).where(
                ElectionPosition.election_id == election.id,
                ElectionPosition.deleted_at.is_(None),
            )
        ).scalars()
    }

    prepared: list[tuple[ElectionPosition, list[uuid.UUID], bool]] = []
    for position_id, candidate_ids in choices.items():
        position = positions.get(position_id)
        if position is None:
            raise NotFound()
        if position_id not in entitled:
            raise RuleViolation(
                f"You are not in the electorate for {position.title}.",
                rule="not_in_electorate",
            )
        chosen = list(dict.fromkeys(candidate_ids))
        # Over-voting is refused rather than silently truncated: a ballot the
        # voter did not intend is worse than one they have to correct.
        if len(chosen) > position.max_choices:
            raise RuleViolation(
                f"{position.title} allows {position.max_choices} choice(s); "
                f"{len(chosen)} were made.",
                rule="over_vote",
                details={"position": position.title, "max_choices": position.max_choices},
            )
        approved_ids = {
            candidate.id
            for candidate in position.candidates
            if candidate.status == "approved" and candidate.deleted_at is None
        }
        unknown = [c for c in chosen if c not in approved_ids]
        if unknown:
            raise RuleViolation(
                "A choice is not an approved candidate for this position.",
                rule="unknown_candidate",
            )
        prepared.append((position, chosen, not chosen))

    missing = entitled - set(choices)
    if missing:
        # A partial ballot is legitimate — a voter may abstain on a position —
        # but it has to be deliberate, so the caller states it.
        log.info("partial_ballot", positions_left_blank=len(missing))

    receipts: dict[str, str] = {}
    cast_at = now.replace(second=0, microsecond=0)
    for position, chosen, abstained in prepared:
        token = secrets.token_urlsafe(15).replace("_", "").replace("-", "")[:20].upper()
        session.add(
            Ballot(
                election_id=election.id,
                position_id=position.id,
                candidate_ids=chosen,
                is_abstention=abstained,
                is_spoilt=False,
                cast_at=cast_at,
                receipt_token=token,
            )
        )
        receipts[str(position.id)] = token

    row.voted_at = now
    row.voted_via = via
    row.voted_ip_hash = _ip_bucket(ip_address)
    session.flush()

    election.ballots_cast = int(
        session.execute(
            select(func.count()).where(
                VoterRoll.election_id == election.id,
                VoterRoll.voted_at.is_not(None),
                VoterRoll.deleted_at.is_(None),
            )
        ).scalar_one()
    )
    election.turnout_percent = (
        float(round(Decimal(election.ballots_cast) / Decimal(election.eligible_count) * 100, 2))
        if election.eligible_count
        else None
    )
    session.flush()

    # Audited as an event, with no record of the choice. That a named student
    # voted is a fact the roll already holds and an observer is entitled to;
    # what they chose is not in this system's gift to disclose.
    emit(
        "election:cast_ballot",
        AuditCategory.CONFIGURATION,
        resource_type="election",
        resource_id=election.id,
        resource_label=election.reference,
        summary=f"A ballot was cast ({via}); turnout now {election.turnout_percent}%",
    )
    return {"receipts": receipts, "cast_at": cast_at, "positions": len(prepared)}


def verify_receipt(session: Session, *, token: str) -> dict[str, Any]:
    """Confirm a ballot is in the count, from the voter's own receipt.

    Returns that it exists and which position it belongs to — never the
    choice. Returning the choice would turn the receipt into proof of how
    somebody voted, which is exactly what a secret ballot must not produce:
    proof is what makes a vote sellable.
    """
    ballot = (
        session.execute(select(Ballot).where(Ballot.receipt_token == token.strip().upper()))
        .scalars()
        .first()
    )
    if ballot is None:
        return {"found": False}
    position = session.get(ElectionPosition, ballot.position_id)
    return {
        "found": True,
        "position": position.title if position is not None else None,
        "cast_at": ballot.cast_at,
        "counted": True,
        "abstention": ballot.is_abstention,
    }


def close_poll(session: Session, *, election: Election, actor_id: uuid.UUID | None) -> Election:
    if election.status != ElectionStatus.VOTING:
        raise Conflict(f"This election is {election.status}, not open.")
    election.status = ElectionStatus.COUNTING
    election.closed_at = utcnow()
    election.closed_by_id = actor_id
    session.flush()
    emit(
        "election:close_poll",
        AuditCategory.CONFIGURATION,
        resource_type="election",
        resource_id=election.id,
        resource_label=election.reference,
        summary=(
            f"Poll closed: {election.ballots_cast} ballots, {election.turnout_percent}% turnout"
        ),
        severity="notice",
    )
    return election


# ---------------------------------------------------------------------------
# The count
# ---------------------------------------------------------------------------


def count(session: Session, *, election: Election) -> list[dict[str, Any]]:
    """Count the ballots. Pure, repeatable, and safe to run before declaring.

    Deliberately separate from `declare`: the returning officer counts, shows
    the tally to the observers, and only then declares. A system where
    counting *is* declaring gives them nothing to check.
    """
    out: list[dict[str, Any]] = []
    for position in sorted(election.positions, key=lambda p: p.sequence):
        ballots = (
            session.execute(
                select(Ballot).where(
                    Ballot.election_id == election.id,
                    Ballot.position_id == position.id,
                    Ballot.deleted_at.is_(None),
                )
            )
            .scalars()
            .all()
        )

        votes: dict[uuid.UUID, int] = defaultdict(int)
        abstentions = 0
        spoilt = 0
        for ballot in ballots:
            if ballot.is_spoilt:
                spoilt += 1
                continue
            if ballot.is_abstention or not ballot.candidate_ids:
                abstentions += 1
                continue
            for candidate_id in ballot.candidate_ids:
                votes[candidate_id] += 1

        eligible = int(
            session.execute(
                select(func.count()).where(
                    VoterRoll.election_id == election.id,
                    VoterRoll.is_eligible.is_(True),
                    VoterRoll.position_ids.contains([position.id]),
                    VoterRoll.deleted_at.is_(None),
                )
            ).scalar_one()
        )
        counted = len(ballots)
        valid = counted - abstentions - spoilt

        rows: list[TallyRow] = []
        for candidate in sorted(position.candidates, key=lambda c: c.ballot_order):
            if candidate.status != "approved" or candidate.deleted_at is not None:
                continue
            tally = votes.get(candidate.id, 0)
            rows.append(
                {
                    "candidate_id": str(candidate.id),
                    "ballot_name": candidate.ballot_name,
                    "votes": tally,
                    # Of valid votes, not of ballots: an abstention is not a
                    # vote for anybody, and dividing by ballots understates
                    # every candidate's share.
                    "share_percent": (
                        float(round(Decimal(tally) / Decimal(valid) * 100, 2)) if valid else None
                    ),
                    "elected": False,
                }
            )

        ranked = sorted(rows, key=lambda r: -r["votes"])
        for winner in ranked[: position.seats]:
            if winner["votes"] > 0:
                winner["elected"] = True

        # A tie on the last seat is not the system's to break. It is flagged,
        # and the constitution's method — usually a lot drawn before observers
        # — is recorded on the result.
        tie = False
        if len(ranked) > position.seats:
            boundary = ranked[position.seats - 1]["votes"]
            tie = boundary > 0 and ranked[position.seats]["votes"] == boundary

        turnout = float(round(Decimal(counted) / Decimal(eligible) * 100, 2)) if eligible else None
        out.append(
            {
                "position_id": str(position.id),
                "title": position.title,
                "seats": position.seats,
                "eligible_count": eligible,
                "ballots_cast": counted,
                "valid_votes": valid,
                "abstentions": abstentions,
                "spoilt": spoilt,
                "turnout_percent": turnout,
                "quorum_met": (
                    None
                    if election.quorum_percent is None or turnout is None
                    else turnout >= election.quorum_percent
                ),
                "tie_on_last_seat": tie,
                "tally": sorted(rows, key=lambda r: -r["votes"]),
            }
        )
    return out


def declare(
    session: Session,
    *,
    election: Election,
    actor_id: uuid.UUID | None,
    tie_break_notes: dict[str, str] | None = None,
) -> list[ElectionResult]:
    """Write the count as the declared result, and mark the winners.

    Refuses while a tie stands on a last seat without a recorded tie-break:
    declaring one of two equal candidates elected because they happen to sort
    first is the kind of quiet arbitrariness that annuls an election.
    """
    if election.status != ElectionStatus.COUNTING:
        raise Conflict(f"This election is {election.status}, not counting.")

    tallies = count(session, election=election)
    notes = tie_break_notes or {}
    unresolved = [
        row["title"]
        for row in tallies
        if row["tie_on_last_seat"] and not notes.get(str(row["position_id"]))
    ]
    if unresolved:
        raise RuleViolation(
            "A tie stands on the last seat for "
            + ", ".join(unresolved)
            + ". Record how it was broken before declaring.",
            rule="unbroken_tie",
            details={"positions": unresolved},
        )

    now = utcnow()
    results: list[ElectionResult] = []
    for row in tallies:
        position_id = uuid.UUID(str(row["position_id"]))
        existing = (
            session.execute(
                select(ElectionResult).where(
                    ElectionResult.election_id == election.id,
                    ElectionResult.position_id == position_id,
                )
            )
            .scalars()
            .first()
        )
        if existing is not None:
            raise Conflict(f"{row['title']} has already been declared.")

        result = ElectionResult(
            election_id=election.id,
            position_id=position_id,
            eligible_count=int(row["eligible_count"]),
            ballots_cast=int(row["ballots_cast"]),
            abstentions=int(row["abstentions"]),
            spoilt=int(row["spoilt"]),
            turnout_percent=row["turnout_percent"],
            tally=list(row["tally"]),
            quorum_met=row["quorum_met"],
            declared_at=now,
            declared_by_id=actor_id,
            tie_break_note=notes.get(str(position_id)),
        )
        session.add(result)
        results.append(result)

        for entry in row["tally"]:
            candidate = session.get(Candidate, uuid.UUID(str(entry["candidate_id"])))
            if candidate is None:
                continue
            candidate.votes = int(entry["votes"])
            candidate.is_elected = bool(entry["elected"])

    election.status = ElectionStatus.DECLARED
    election.declared_at = now
    election.declared_by_id = actor_id
    session.flush()

    elected = [
        entry["ballot_name"] for row in tallies for entry in row["tally"] if entry["elected"]
    ]
    emit(
        "election:declare",
        AuditCategory.CONFIGURATION,
        resource_type="election",
        resource_id=election.id,
        resource_label=election.reference,
        summary=(
            f"Result declared for {len(results)} position(s); "
            f"{len(elected)} elected; turnout {election.turnout_percent}%"
        ),
        severity="notice",
        metadata={"elected": elected[:20]},
    )
    return results


# ---------------------------------------------------------------------------
# Nominations
# ---------------------------------------------------------------------------


def vet_candidate(
    session: Session,
    *,
    candidate: Candidate,
    actor_id: uuid.UUID | None,
    approve: bool,
    reason: str | None = None,
) -> Candidate:
    """Approve or refuse a nomination, recording every check and its answer.

    The checks are run here rather than asserted by the officer, and each
    one's answer is stored — so a candidate refused on CGPA can be shown the
    number, and one refused wrongly can have it corrected.
    """
    from acmis.modules.students.models import DisciplinaryCase, Student, StudentProgramme

    if candidate.status not in ("nominated", "vetting"):
        raise Conflict(f"This nomination is {candidate.status}.")

    position = session.get(ElectionPosition, candidate.position_id)
    rules = dict(position.eligibility_rules or {}) if position is not None else {}
    checks: list[dict[str, Any]] = []

    if candidate.student_id is not None:
        student = session.get(Student, candidate.student_id)
        attachment = (
            session.execute(
                select(StudentProgramme).where(
                    StudentProgramme.student_id == candidate.student_id,
                    StudentProgramme.is_primary.is_(True),
                )
            )
            .scalars()
            .first()
        )

        standing_ok = student is not None and student.status in ("active", "probation")
        checks.append(
            {
                "check": "standing",
                "requirement": "active or on probation",
                "found": student.status if student is not None else None,
                "passed": standing_ok,
            }
        )

        minimum = rules.get("min_cgpa")
        if minimum is not None:
            cgpa = float(attachment.cgpa) if attachment and attachment.cgpa else None
            checks.append(
                {
                    "check": "cgpa",
                    "requirement": f">= {minimum}",
                    "found": cgpa,
                    "passed": cgpa is not None and cgpa >= float(minimum),
                }
            )

        if rules.get("no_disciplinary_finding"):
            open_cases = int(
                session.execute(
                    select(func.count()).where(
                        DisciplinaryCase.student_id == candidate.student_id,
                        DisciplinaryCase.status.in_(("decided", "upheld")),
                        DisciplinaryCase.deleted_at.is_(None),
                    )
                ).scalar_one()
            )
            checks.append(
                {
                    "check": "disciplinary",
                    "requirement": "no finding on record",
                    "found": open_cases,
                    "passed": open_cases == 0,
                }
            )

        required_seconders = int(rules.get("min_nominators", 0))
        if required_seconders:
            checks.append(
                {
                    "check": "nominators",
                    "requirement": f">= {required_seconders}",
                    "found": len(candidate.nominator_student_ids),
                    "passed": len(candidate.nominator_student_ids) >= required_seconders,
                }
            )

    failed = [c["check"] for c in checks if not c["passed"]]
    if approve and failed:
        raise RuleViolation(
            "This nomination fails " + ", ".join(failed) + ".",
            rule="ineligible_candidate",
            details={"checks": checks},
        )
    if not approve and not reason:
        raise RuleViolation(
            "A refused nomination needs a reason the candidate can be shown.",
            rule="reason_required",
        )

    candidate.eligibility_checks = checks
    candidate.status = "approved" if approve else "disqualified"
    candidate.disqualification_reason = None if approve else reason
    candidate.vetted_by_id = actor_id
    candidate.vetted_at = utcnow()
    session.flush()
    emit(
        "election_candidate:vet",
        AuditCategory.CONFIGURATION,
        resource_type="election_candidate",
        resource_id=candidate.id,
        resource_label=candidate.ballot_name,
        summary=(
            f"Nomination {'approved' if approve else 'refused'}" + (f": {reason}" if reason else "")
        ),
        severity="notice",
    )
    return candidate


def draw_ballot_order(
    session: Session, *, election: Election, actor_id: uuid.UUID | None, seed: int
) -> int:
    """Assign ballot positions by lot.

    Alphabetical order measurably advantages the top of a ballot paper, so the
    order is drawn. `seed` is supplied by the returning officer — in practice
    from a physical draw before observers — and recorded, which is what makes
    the draw reproducible and therefore checkable.
    """
    import random

    if election.status not in (ElectionStatus.VETTING, ElectionStatus.CAMPAIGN):
        raise Conflict("The order is drawn once vetting is complete.")

    rng = random.Random(seed)  # noqa: S311 - a recorded draw, not a secret
    drawn = 0
    for position in election.positions:
        approved = [
            candidate
            for candidate in position.candidates
            if candidate.status == "approved" and candidate.deleted_at is None
        ]
        rng.shuffle(approved)
        for index, candidate in enumerate(approved, start=1):
            candidate.ballot_order = index
            drawn += 1
    session.flush()
    emit(
        "election:draw_ballot_order",
        AuditCategory.CONFIGURATION,
        resource_type="election",
        resource_id=election.id,
        resource_label=election.reference,
        summary=f"Ballot order drawn for {drawn} candidate(s) from seed {seed}",
        metadata={"seed": seed},
    )
    return drawn


def turnout_snapshot(session: Session, *, election: Election) -> dict[str, Any]:
    """Live turnout while the poll runs.

    Deliberately turnout only, never a running tally. A partial count
    published mid-poll changes how people vote, and in a student election it
    is the single most effective way to depress turnout for a trailing
    candidate.
    """
    by_hour = session.execute(
        select(
            func.date_trunc("hour", VoterRoll.voted_at).label("hour"),
            func.count(),
        )
        .where(
            VoterRoll.election_id == election.id,
            VoterRoll.voted_at.is_not(None),
            VoterRoll.deleted_at.is_(None),
        )
        .group_by(func.date_trunc("hour", VoterRoll.voted_at))
        .order_by(func.date_trunc("hour", VoterRoll.voted_at))
    ).all()

    # One machine casting hundreds of ballots is the fraud that happens; this
    # is the number that shows it. It says how many ballots came from the
    # busiest device, never which voters they were.
    busiest = session.execute(
        select(VoterRoll.voted_ip_hash, func.count())
        .where(
            VoterRoll.election_id == election.id,
            VoterRoll.voted_ip_hash.is_not(None),
            VoterRoll.deleted_at.is_(None),
        )
        .group_by(VoterRoll.voted_ip_hash)
        .order_by(func.count().desc())
        .limit(1)
    ).first()

    return {
        "eligible": election.eligible_count,
        "cast": election.ballots_cast,
        "turnout_percent": election.turnout_percent,
        "quorum_percent": election.quorum_percent,
        "quorum_met": (
            None
            if election.quorum_percent is None or election.turnout_percent is None
            else float(election.turnout_percent) >= election.quorum_percent
        ),
        "by_hour": [
            {"hour": hour.isoformat() if isinstance(hour, datetime) else str(hour), "cast": int(n)}
            for hour, n in by_hour
        ],
        "most_from_one_device": int(busiest[1]) if busiest else 0,
    }


def next_reference(session: Session, *, prefix: str = "ELE") -> str:
    sequence = (
        int(session.execute(select(func.count()).where(Election.deleted_at.is_(None))).scalar_one())
        + 1
    )
    return f"{prefix}/{date.today().year}/{sequence:03d}"
