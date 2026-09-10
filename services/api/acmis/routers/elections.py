"""Student elections: standing, voting, counting, declaring."""

from __future__ import annotations

import uuid
from datetime import date, datetime
from typing import Annotated, Any

from fastapi import APIRouter, Query, Request, status
from pydantic import Field
from sqlalchemy import func, select

from acmis.core.abac import authorize
from acmis.core.audit import AuditCategory, emit
from acmis.core.deps import AnyContext, PageQuery, StaffContext, StudentContext
from acmis.core.errors import RuleViolation
from acmis.core.models import utcnow
from acmis.core.pagination import keyset_page
from acmis.core.schemas import Page, Reason, Schema
from acmis.modules.elections import service
from acmis.modules.elections.models import (
    Candidate,
    Election,
    ElectionPetition,
    ElectionPosition,
    ElectionResult,
    ElectionStatus,
)
from acmis.routers._common import get_or_404

router = APIRouter(prefix="/elections", tags=["elections"])


# ---------------------------------------------------------------------------
# Elections and positions
# ---------------------------------------------------------------------------


class PositionOut(Schema):
    id: uuid.UUID
    code: str
    title: str
    description: str | None
    sequence: int
    seats: int
    max_choices: int
    reserved_for: str | None
    is_referendum: bool
    question: str | None


class ElectionOut(Schema):
    id: uuid.UUID
    reference: str
    title: str
    kind: str
    description: str | None
    status: str
    nominations_open_at: datetime | None
    nominations_close_at: datetime | None
    voting_opens_at: datetime | None
    voting_closes_at: datetime | None
    quorum_percent: int | None
    eligible_count: int
    ballots_cast: int
    turnout_percent: float | None
    declared_at: datetime | None
    positions: list[PositionOut]


class PositionIn(Schema):
    code: Annotated[str, Field(max_length=40)]
    title: Annotated[str, Field(max_length=200)]
    description: str | None = None
    sequence: Annotated[int, Field(ge=0, le=100)] = 0
    seats: Annotated[int, Field(ge=1, le=50)] = 1
    max_choices: Annotated[int, Field(ge=1, le=50)] = 1
    electorate_faculty_ids: list[uuid.UUID] = Field(default_factory=list)
    electorate_programme_ids: list[uuid.UUID] = Field(default_factory=list)
    electorate_year_of_study: Annotated[int | None, Field(ge=1, le=12)] = None
    reserved_for: Annotated[str | None, Field(max_length=30)] = None
    #: The constitution's conditions, as data: `min_cgpa`,
    #: `no_disciplinary_finding`, `min_nominators`.
    eligibility_rules: dict[str, Any] = Field(default_factory=dict)
    is_referendum: bool = False
    question: str | None = None


class ElectionIn(Schema):
    title: Annotated[str, Field(max_length=200)]
    kind: Annotated[str, Field(pattern="^(guild|faculty|class|referendum|by_election)$")] = "guild"
    description: str | None = None
    academic_year_id: uuid.UUID | None = None
    returning_officer_id: uuid.UUID | None = None
    nominations_open_at: datetime | None = None
    nominations_close_at: datetime | None = None
    campaign_starts_at: datetime | None = None
    voting_opens_at: datetime | None = None
    voting_closes_at: datetime | None = None
    quorum_percent: Annotated[int | None, Field(ge=0, le=100)] = None
    positions: Annotated[list[PositionIn], Field(min_length=1, max_length=60)]


@router.post("", response_model=ElectionOut, status_code=status.HTTP_201_CREATED)
def create_election(payload: ElectionIn, ctx: StaffContext) -> ElectionOut:
    """Set an election up. Positions and the constitution's rules come with it.

    Positions are created here rather than one at a time, because an election
    with half its seats defined is not a state anybody wants published — and
    the electorate for each seat is part of what the guild is agreeing to.
    """
    authorize(
        engine=ctx.engine,
        action="election:create",
        resource_type="election",
        resource={
            "id": None,
            "kind": payload.kind,
            "status": ElectionStatus.DRAFT,
            "is_published": False,
            "returning_officer_id": str(payload.returning_officer_id)
            if payload.returning_officer_id
            else None,
            "observer_staff_ids": [],
            "academic_year_id": str(payload.academic_year_id) if payload.academic_year_id else None,
        },
        category=AuditCategory.CONFIGURATION,
    )
    if (
        payload.voting_closes_at
        and payload.voting_opens_at
        and payload.voting_closes_at <= payload.voting_opens_at
    ):
        raise RuleViolation("A poll cannot close before it opens.", rule="poll_window")

    election = Election(
        reference=service.next_reference(ctx.db),
        status=ElectionStatus.DRAFT,
        created_by_id=ctx.principal.id,
        **payload.model_dump(exclude={"positions"}),
    )
    ctx.db.add(election)
    ctx.db.flush()
    for entry in payload.positions:
        if entry.max_choices > entry.seats and not entry.is_referendum:
            raise RuleViolation(
                f"{entry.title}: a voter cannot have more choices ({entry.max_choices}) "
                f"than there are seats ({entry.seats}).",
                rule="choices_exceed_seats",
            )
        ctx.db.add(
            ElectionPosition(
                election_id=election.id,
                created_by_id=ctx.principal.id,
                **entry.model_dump(),
            )
        )
    ctx.db.flush()
    emit(
        "election:create",
        AuditCategory.CONFIGURATION,
        resource_type="election",
        resource_id=election.id,
        resource_label=election.reference,
        summary=f"{payload.kind} election drafted with {len(payload.positions)} position(s)",
    )
    ctx.db.refresh(election)
    return ElectionOut.model_validate(election)


@router.get("", response_model=Page[ElectionOut])
def list_elections(
    ctx: AnyContext,
    page: PageQuery,
    status_filter: Annotated[str | None, Query(alias="status")] = None,
) -> Page[ElectionOut]:
    authorize(
        engine=ctx.engine,
        action="election:list",
        resource_type="election",
        resource={
            "id": None,
            "kind": "guild",
            "status": status_filter,
            "is_published": True,
            "returning_officer_id": None,
            "observer_staff_ids": [],
            "academic_year_id": None,
        },
    )
    stmt = select(Election).where(Election.deleted_at.is_(None))
    if status_filter:
        stmt = stmt.where(Election.status == status_filter)
    # A student never sees a draft: an election that has not been published is
    # a proposal, and publishing it is the guild's decision to announce.
    if ctx.principal.kind in ("student", "applicant"):
        stmt = stmt.where(Election.status != ElectionStatus.DRAFT)
    found = keyset_page(
        ctx.db,
        stmt,
        page=page,
        key=Election.created_at,
        ident=Election.id,
        descending=True,
    )
    return Page.of(
        [ElectionOut.model_validate(row) for row in found.rows],
        limit=page.limit,
        next_cursor=found.next_cursor,
        total=found.total,
    )


@router.get("/{election_id}", response_model=ElectionOut)
def get_election(election_id: uuid.UUID, ctx: AnyContext) -> ElectionOut:
    election = get_or_404(ctx, Election, election_id)
    authorize(
        engine=ctx.engine,
        action="election:read",
        resource_type="election",
        resource=election,
    )
    return ElectionOut.model_validate(election)


class PublishIn(Schema):
    minute_reference: Annotated[str | None, Field(max_length=80)] = None


@router.post("/{election_id}/publish", response_model=ElectionOut)
def publish_election(
    election_id: uuid.UUID, ctx: StaffContext, payload: PublishIn | None = None
) -> ElectionOut:
    """Announce the election and open nominations."""
    election = get_or_404(ctx, Election, election_id)
    authorize(
        engine=ctx.engine,
        action="election:publish",
        resource_type="election",
        resource=election,
        category=AuditCategory.CONFIGURATION,
    )
    if election.status != ElectionStatus.DRAFT:
        raise RuleViolation(
            f"This election is already {election.status}.", rule="already_published"
        )
    if not election.returning_officer_id:
        raise RuleViolation(
            "An election needs a returning officer before it is announced. A "
            "disputed result turns on who conducted the poll.",
            rule="no_returning_officer",
        )
    election.status = ElectionStatus.NOMINATIONS
    ctx.db.flush()
    emit(
        "election:publish",
        AuditCategory.CONFIGURATION,
        resource_type="election",
        resource_id=election.id,
        resource_label=election.reference,
        summary="Election announced; nominations open",
        severity="notice",
    )
    return ElectionOut.model_validate(election)


# ---------------------------------------------------------------------------
# Nominations
# ---------------------------------------------------------------------------


class CandidateOut(Schema):
    id: uuid.UUID
    position_id: uuid.UUID
    student_id: uuid.UUID | None
    option_label: str | None
    ballot_name: str
    ballot_order: int
    slogan: str | None
    manifesto: str | None
    status: str
    nominated_at: datetime
    eligibility_checks: list[dict[str, Any]]
    disqualification_reason: str | None
    votes: int
    is_elected: bool


class NominationIn(Schema):
    position_id: uuid.UUID
    ballot_name: Annotated[str, Field(max_length=200)]
    slogan: Annotated[str | None, Field(max_length=200)] = None
    manifesto: Annotated[str | None, Field(max_length=8000)] = None
    nominator_student_ids: list[uuid.UUID] = Field(default_factory=list)
    #: Set by the guild office when lodging a referendum option or standing in
    #: for a candidate who filed on paper.
    student_id: uuid.UUID | None = None
    option_label: Annotated[str | None, Field(max_length=60)] = None


@router.post("/nominations", response_model=CandidateOut, status_code=status.HTTP_201_CREATED)
def lodge_nomination(payload: NominationIn, ctx: AnyContext) -> CandidateOut:
    """Stand for a position.

    Self-service on purpose: the alternative is a queue at the guild office
    during the two days nominations are open, which is how a field ends up
    smaller than the electorate wanted.
    """
    position = get_or_404(ctx, ElectionPosition, payload.position_id)
    election = position.election
    student_id = payload.student_id or ctx.principal.student_id

    authorize(
        engine=ctx.engine,
        action="election_candidate:create",
        resource_type="election_candidate",
        resource={
            "id": None,
            "position_id": str(position.id),
            "student_id": str(student_id) if student_id else None,
            "status": election.status,
            "requested_by_id": str(ctx.principal.id),
        },
        category=AuditCategory.CONFIGURATION,
    )
    if election.status != ElectionStatus.NOMINATIONS:
        raise RuleViolation(
            f"Nominations for this election are {election.status}.",
            rule="nominations_closed",
        )
    if student_id is None and not payload.option_label:
        raise RuleViolation(
            "A nomination is for a student, or a referendum option.",
            rule="nomination_subject",
        )

    existing = (
        ctx.db.execute(
            select(Candidate).where(
                Candidate.position_id == position.id,
                Candidate.student_id == student_id,
                Candidate.deleted_at.is_(None),
            )
        )
        .scalars()
        .first()
    )
    if existing is not None:
        raise RuleViolation(
            f"A nomination for this position already stands ({existing.status}).",
            rule="already_nominated",
        )

    candidate = Candidate(
        position_id=position.id,
        student_id=student_id,
        option_label=payload.option_label,
        ballot_name=payload.ballot_name,
        slogan=payload.slogan,
        manifesto=payload.manifesto,
        nominator_student_ids=payload.nominator_student_ids,
        status="nominated",
        nominated_at=utcnow(),
        created_by_id=ctx.principal.id,
    )
    ctx.db.add(candidate)
    ctx.db.flush()
    emit(
        "election_candidate:create",
        AuditCategory.CONFIGURATION,
        resource_type="election_candidate",
        resource_id=candidate.id,
        resource_label=candidate.ballot_name,
        summary=f"Nomination lodged for {position.title}",
    )
    return CandidateOut.model_validate(candidate)


@router.get("/{election_id}/candidates", response_model=list[CandidateOut])
def list_candidates(
    election_id: uuid.UUID, ctx: AnyContext, approved_only: bool = False
) -> list[CandidateOut]:
    """The field, in ballot order."""
    election = get_or_404(ctx, Election, election_id)
    authorize(
        engine=ctx.engine,
        action="election_candidate:list",
        resource_type="election",
        resource=election,
    )
    stmt = (
        select(Candidate)
        .join(ElectionPosition, ElectionPosition.id == Candidate.position_id)
        .where(
            ElectionPosition.election_id == election.id,
            Candidate.deleted_at.is_(None),
        )
        .order_by(ElectionPosition.sequence, Candidate.ballot_order, Candidate.ballot_name)
    )
    if approved_only or ctx.principal.kind == "student":
        # A student sees the ballot paper, not the rejected nominations: a
        # refusal is between the candidate and the returning officer.
        stmt = stmt.where(Candidate.status == "approved")
    return [CandidateOut.model_validate(row) for row in ctx.db.execute(stmt).scalars().all()]


class VetIn(Schema):
    approve: bool
    reason: Annotated[str | None, Field(max_length=2000)] = None


@router.post("/candidates/{candidate_id}/vet", response_model=CandidateOut)
def vet_nomination(candidate_id: uuid.UUID, payload: VetIn, ctx: StaffContext) -> CandidateOut:
    """Approve or refuse a nomination, recording every check and its answer."""
    candidate = get_or_404(ctx, Candidate, candidate_id)
    authorize(
        engine=ctx.engine,
        action="election_candidate:vet",
        resource_type="election_candidate",
        resource=candidate,
        category=AuditCategory.CONFIGURATION,
    )
    return CandidateOut.model_validate(
        service.vet_candidate(
            ctx.db,
            candidate=candidate,
            actor_id=ctx.principal.id,
            approve=payload.approve,
            reason=payload.reason,
        )
    )


@router.post("/candidates/{candidate_id}/withdraw", response_model=CandidateOut)
def withdraw_nomination(
    candidate_id: uuid.UUID, ctx: AnyContext, payload: Reason | None = None
) -> CandidateOut:
    candidate = get_or_404(ctx, Candidate, candidate_id)
    authorize(
        engine=ctx.engine,
        action="election_candidate:withdraw",
        resource_type="election_candidate",
        resource=candidate,
        category=AuditCategory.CONFIGURATION,
    )
    candidate.status = "withdrawn"
    candidate.withdrawn_at = utcnow()
    ctx.db.flush()
    emit(
        "election_candidate:withdraw",
        AuditCategory.CONFIGURATION,
        resource_type="election_candidate",
        resource_id=candidate.id,
        resource_label=candidate.ballot_name,
        summary="Nomination withdrawn",
        severity="notice",
    )
    return CandidateOut.model_validate(candidate)


# ---------------------------------------------------------------------------
# Conducting the poll
# ---------------------------------------------------------------------------


@router.post("/{election_id}/roll", response_model=dict)
def build_roll(election_id: uuid.UUID, ctx: StaffContext) -> dict[str, Any]:
    """Fix the electorate. Once, before the poll opens."""
    election = get_or_404(ctx, Election, election_id)
    authorize(
        engine=ctx.engine,
        action="election_voter_roll:create",
        resource_type="election",
        resource=election,
        category=AuditCategory.CONFIGURATION,
    )
    return service.build_roll(ctx.db, election=election, actor_id=ctx.principal.id)


class DrawIn(Schema):
    #: From a physical draw before observers. Recorded, so the draw is
    #: reproducible and therefore checkable.
    seed: Annotated[int, Field(ge=0, le=999_999)]


@router.post("/{election_id}/ballot-order", response_model=dict)
def draw_ballot_order(election_id: uuid.UUID, payload: DrawIn, ctx: StaffContext) -> dict[str, Any]:
    """Assign ballot positions by lot rather than alphabetically."""
    election = get_or_404(ctx, Election, election_id)
    authorize(
        engine=ctx.engine,
        action="election:draw_ballot_order",
        resource_type="election",
        resource=election,
        category=AuditCategory.CONFIGURATION,
    )
    drawn = service.draw_ballot_order(
        ctx.db, election=election, actor_id=ctx.principal.id, seed=payload.seed
    )
    return {"candidates_ordered": drawn, "seed": payload.seed}


@router.post("/{election_id}/campaign", response_model=ElectionOut)
def start_campaign(election_id: uuid.UUID, ctx: StaffContext) -> ElectionOut:
    """Close nominations and publish the final ballot paper."""
    election = get_or_404(ctx, Election, election_id)
    authorize(
        engine=ctx.engine,
        action="election:update",
        resource_type="election",
        resource=election,
        category=AuditCategory.CONFIGURATION,
    )
    if election.status not in (ElectionStatus.NOMINATIONS, ElectionStatus.VETTING):
        raise RuleViolation(f"This election is {election.status}.", rule="wrong_stage")
    election.status = ElectionStatus.CAMPAIGN
    ctx.db.flush()
    emit(
        "election:start_campaign",
        AuditCategory.CONFIGURATION,
        resource_type="election",
        resource_id=election.id,
        resource_label=election.reference,
        summary="Nominations closed; the ballot paper is final",
        severity="notice",
    )
    return ElectionOut.model_validate(election)


@router.post("/{election_id}/open", response_model=ElectionOut)
def open_poll(election_id: uuid.UUID, ctx: StaffContext) -> ElectionOut:
    election = get_or_404(ctx, Election, election_id)
    authorize(
        engine=ctx.engine,
        action="election:open_poll",
        resource_type="election",
        resource=election,
        category=AuditCategory.CONFIGURATION,
    )
    return ElectionOut.model_validate(
        service.open_poll(ctx.db, election=election, actor_id=ctx.principal.id)
    )


@router.post("/{election_id}/close", response_model=ElectionOut)
def close_poll(election_id: uuid.UUID, ctx: StaffContext) -> ElectionOut:
    election = get_or_404(ctx, Election, election_id)
    authorize(
        engine=ctx.engine,
        action="election:close_poll",
        resource_type="election",
        resource=election,
        category=AuditCategory.CONFIGURATION,
    )
    return ElectionOut.model_validate(
        service.close_poll(ctx.db, election=election, actor_id=ctx.principal.id)
    )


# ---------------------------------------------------------------------------
# Voting
# ---------------------------------------------------------------------------


@router.get("/{election_id}/me", response_model=dict)
def my_entitlement(election_id: uuid.UUID, ctx: StudentContext) -> dict[str, Any]:
    """What this voter may do, and whether they have voted.

    The refusal reason comes back too. A student told only "you cannot vote"
    turns up at the returning officer's desk; one told "your standing is
    suspended" knows what to appeal.
    """
    election = get_or_404(ctx, Election, election_id)
    authorize(
        engine=ctx.engine,
        action="election:read_entitlement",
        resource_type="election",
        resource=election,
    )
    return service.entitlement(ctx.db, election=election, student_id=ctx.student_id)


class VoteIn(Schema):
    #: {position_id: [candidate_id, ...]}. An empty list is a deliberate
    #: abstention on that position and counts as turnout.
    choices: dict[uuid.UUID, list[uuid.UUID]]
    #: `portal`, `booth`, `assisted`. An assisted vote — for a voter with a
    #: visual impairment — is noted because the constitution usually requires
    #: the returning officer to record it.
    via: Annotated[str, Field(pattern="^(portal|booth|assisted)$")] = "portal"


@router.post("/{election_id}/vote", response_model=dict)
def cast_vote(
    election_id: uuid.UUID, payload: VoteIn, request: Request, ctx: StudentContext
) -> dict[str, Any]:
    """Cast a ballot.

    Returns the receipt tokens and nothing else. They are the voter's own
    copy: they prove the ballot is in the count without revealing what it
    said, and they are not stored against the voter's name anywhere.
    """
    election = get_or_404(ctx, Election, election_id)
    authorize(
        engine=ctx.engine,
        action="election:vote",
        resource_type="election",
        resource=election,
        category=AuditCategory.CONFIGURATION,
    )
    return service.cast_ballot(
        ctx.db,
        election=election,
        student_id=ctx.student_id,
        choices=payload.choices,
        ip_address=ctx.context.ip_address,
        via=payload.via,
    )


@router.get("/receipts/{token}", response_model=dict)
def verify_receipt(token: str, ctx: AnyContext) -> dict[str, Any]:
    """Confirm a ballot is in the count, from its receipt.

    Says that it exists and which position it belongs to — never the choice.
    Returning the choice would make the receipt proof of how somebody voted,
    and proof is what makes a vote sellable.
    """
    authorize(
        engine=ctx.engine,
        action="election:verify_receipt",
        resource_type="election",
        resource={
            "id": None,
            "kind": "guild",
            "status": "voting",
            "is_published": True,
            "returning_officer_id": None,
            "observer_staff_ids": [],
            "academic_year_id": None,
        },
    )
    return service.verify_receipt(ctx.db, token=token)


@router.get("/{election_id}/turnout", response_model=dict)
def turnout(election_id: uuid.UUID, ctx: AnyContext) -> dict[str, Any]:
    """Live turnout. Never a running tally — see the policy's note."""
    election = get_or_404(ctx, Election, election_id)
    authorize(
        engine=ctx.engine,
        action="election:read",
        resource_type="election",
        resource=election,
    )
    return service.turnout_snapshot(ctx.db, election=election)


# ---------------------------------------------------------------------------
# The count
# ---------------------------------------------------------------------------


@router.get("/{election_id}/count", response_model=list[dict[str, Any]])
def count_ballots(election_id: uuid.UUID, ctx: StaffContext) -> list[dict[str, Any]]:
    """Count without declaring.

    Separate on purpose: the returning officer counts, shows the tally to the
    observers, and only then declares. A system where counting *is* declaring
    gives them nothing to check.
    """
    election = get_or_404(ctx, Election, election_id)
    authorize(
        engine=ctx.engine,
        action="election:count",
        resource_type="election",
        resource=election,
        category=AuditCategory.CONFIGURATION,
        audit_reads=True,
    )
    return service.count(ctx.db, election=election)


class DeclareIn(Schema):
    #: {position_id: "how the tie was broken"}. Required where a tie stands
    #: on a last seat — declaring one of two equal candidates because they
    #: sort first is the kind of quiet arbitrariness that annuls an election.
    tie_break_notes: dict[str, str] = Field(default_factory=dict)


class ResultOut(Schema):
    id: uuid.UUID
    election_id: uuid.UUID
    position_id: uuid.UUID
    eligible_count: int
    ballots_cast: int
    abstentions: int
    spoilt: int
    turnout_percent: float | None
    tally: list[dict[str, Any]]
    quorum_met: bool | None
    declared_at: datetime
    tie_break_note: str | None


@router.post("/{election_id}/declare", response_model=list[ResultOut])
def declare_result(
    election_id: uuid.UUID, ctx: StaffContext, payload: DeclareIn | None = None
) -> list[ResultOut]:
    election = get_or_404(ctx, Election, election_id)
    authorize(
        engine=ctx.engine,
        action="election:declare",
        resource_type="election",
        resource=election,
        category=AuditCategory.CONFIGURATION,
    )
    results = service.declare(
        ctx.db,
        election=election,
        actor_id=ctx.principal.id,
        tie_break_notes=(payload or DeclareIn()).tie_break_notes,
    )
    return [ResultOut.model_validate(row) for row in results]


@router.get("/{election_id}/results", response_model=list[ResultOut])
def get_results(election_id: uuid.UUID, ctx: AnyContext) -> list[ResultOut]:
    """The declared result. Public to the electorate once declared."""
    election = get_or_404(ctx, Election, election_id)
    rows = (
        ctx.db.execute(
            select(ElectionResult)
            .join(ElectionPosition, ElectionPosition.id == ElectionResult.position_id)
            .where(
                ElectionResult.election_id == election.id,
                ElectionResult.deleted_at.is_(None),
            )
            .order_by(ElectionPosition.sequence)
        )
        .scalars()
        .all()
    )
    for row in rows:
        authorize(
            engine=ctx.engine,
            action="election_result:read",
            resource_type="election_result",
            resource=row,
        )
    return [ResultOut.model_validate(row) for row in rows]


# ---------------------------------------------------------------------------
# Petitions
# ---------------------------------------------------------------------------


class PetitionOut(Schema):
    id: uuid.UUID
    reference: str
    election_id: uuid.UUID
    position_id: uuid.UUID | None
    ground: str
    submission: str
    filed_on: date
    status: str
    heard_on: date | None
    determination: str | None
    remedy: str | None


class PetitionIn(Schema):
    election_id: uuid.UUID
    position_id: uuid.UUID | None = None
    ground: Annotated[
        str,
        Field(pattern="^(conduct|eligibility|count|campaign_finance|intimidation)$"),
    ]
    submission: Annotated[str, Field(min_length=30, max_length=8000)]
    evidence_attachment_ids: list[uuid.UUID] = Field(default_factory=list)


@router.post("/petitions", response_model=PetitionOut, status_code=status.HTTP_201_CREATED)
def file_petition(payload: PetitionIn, ctx: AnyContext) -> PetitionOut:
    """Challenge the conduct or the result.

    The normal end of a contested guild election, not an exception. A petition
    settled in a meeting leaves no record of what was alleged or decided, and
    the next cohort inherits the argument.
    """
    election = get_or_404(ctx, Election, payload.election_id)
    authorize(
        engine=ctx.engine,
        action="election_petition:create",
        resource_type="election_petition",
        resource={
            "id": None,
            "election_id": str(election.id),
            "student_id": str(ctx.principal.student_id) if ctx.principal.student_id else None,
            "status": "filed",
            "requested_by_id": str(ctx.principal.id),
        },
        category=AuditCategory.CONFIGURATION,
    )
    sequence = (
        int(
            ctx.db.execute(
                select(func.count()).where(ElectionPetition.deleted_at.is_(None))
            ).scalar_one()
        )
        + 1
    )
    petition = ElectionPetition(
        reference=f"PET/{date.today().year}/{sequence:03d}",
        petitioner_student_id=ctx.principal.student_id,
        filed_on=date.today(),
        status="filed",
        created_by_id=ctx.principal.id,
        **payload.model_dump(),
    )
    ctx.db.add(petition)
    ctx.db.flush()
    emit(
        "election_petition:create",
        AuditCategory.CONFIGURATION,
        resource_type="election_petition",
        resource_id=petition.id,
        resource_label=petition.reference,
        summary=f"Petition filed on grounds of {payload.ground}",
        severity="notice",
    )
    return PetitionOut.model_validate(petition)


@router.get("/{election_id}/petitions", response_model=list[PetitionOut])
def list_petitions(election_id: uuid.UUID, ctx: AnyContext) -> list[PetitionOut]:
    election = get_or_404(ctx, Election, election_id)
    rows = (
        ctx.db.execute(
            select(ElectionPetition)
            .where(
                ElectionPetition.election_id == election.id,
                ElectionPetition.deleted_at.is_(None),
            )
            .order_by(ElectionPetition.filed_on.desc())
        )
        .scalars()
        .all()
    )
    for row in rows:
        authorize(
            engine=ctx.engine,
            action="election_petition:read",
            resource_type="election_petition",
            resource=row,
        )
    return [PetitionOut.model_validate(row) for row in rows]
