"""Genuinely public endpoints.

A short list, and each one is here for a reason that survives scrutiny:

* **Certificate and transcript verification.** An employer checking a
  certificate has no account and should not need one. It answers only what the
  presented serial already asserts, and it says so honestly when an award has
  been revoked.
* **The programme catalogue and open admission schemes.** Prospective students
  read these before they have any relationship with the institution.
* **Institution branding.** Each module app's sign-in page needs the crest and
  the name before anyone has authenticated.

No endpoint here takes a record id. Verification takes a serial the caller
already holds, and serials are random precisely so this endpoint cannot be
walked. Rate limiting still applies.
"""

from __future__ import annotations

import uuid
from datetime import UTC, date, datetime
from typing import Annotated

from fastapi import APIRouter, Depends, Path, Request, status
from pydantic import EmailStr, Field
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from acmis.core.deps import tenant_db, tenant_of
from acmis.core.errors import Conflict, ValidationFailed
from acmis.core.schemas import Schema
from acmis.modules.assessment import service as assessment

router = APIRouter(prefix="/public", tags=["public"])


class VerificationOut(Schema):
    found: bool
    valid: bool = False
    holder_name: str | None = None
    award_title: str | None = None
    classification: str | None = None
    conferred_on: str | None = None
    serial_number: str | None = None
    status: str | None = None
    revoked: bool = False
    revoked_on: str | None = None
    institution: str | None = None


@router.get("/verify/{serial}", response_model=VerificationOut)
def verify_award(
    request: Request,
    serial: Annotated[str, Path(min_length=6, max_length=40)],
    db: Session = Depends(tenant_db),
) -> VerificationOut:
    """Verify a certificate or transcript by its serial or verification code.

    Returns only what the serial already asserts: the holder's name as
    printed, the award, the class and the date. No contact details, no marks,
    no other record. A revoked award reports as revoked — a verification
    endpoint that quietly calls a revoked degree valid is worse than none.
    """
    tenant = tenant_of(request)
    payload = assessment.verify_serial(db, serial=serial.strip())
    return VerificationOut.model_construct(
        **payload, institution=tenant.name if payload.get("found") else None
    )


class PublicProgrammeOut(Schema):
    code: str
    name: str
    award_title: str
    award_abbreviation: str
    award_level: str
    duration_semesters: int
    delivery_modes: list[str]
    study_level: str
    description: str | None
    entry_requirements: str | None


@router.get("/programmes", response_model=list[PublicProgrammeOut])
def public_programmes(
    request: Request, db: Session = Depends(tenant_db)
) -> list[PublicProgrammeOut]:
    """The prospectus. Approved, active programmes only."""
    from acmis.modules.curriculum.models import ApprovalStatus, Programme

    tenant_of(request)
    rows = (
        db.execute(
            select(Programme)
            .where(
                Programme.status == ApprovalStatus.APPROVED,
                Programme.is_active.is_(True),
                Programme.deleted_at.is_(None),
            )
            .order_by(Programme.name)
        )
        .scalars()
        .all()
    )
    return [PublicProgrammeOut.model_validate(r) for r in rows]


class PublicSchemeOut(Schema):
    id: uuid.UUID
    code: str
    name: str
    description: str | None
    entry_scheme: str
    study_level: str
    opens_at: datetime
    closes_at: datetime
    late_closes_at: datetime | None
    application_fee_minor: int
    currency: str
    max_programme_choices: int


@router.get("/admission-schemes", response_model=list[PublicSchemeOut])
def public_schemes(request: Request, db: Session = Depends(tenant_db)) -> list[PublicSchemeOut]:
    """Open admission schemes, for the apply page."""
    from acmis.modules.admissions.models import AdmissionScheme, SchemeStatus

    tenant_of(request)
    rows = (
        db.execute(
            select(AdmissionScheme)
            .where(
                AdmissionScheme.status == SchemeStatus.OPEN,
                AdmissionScheme.deleted_at.is_(None),
            )
            .order_by(AdmissionScheme.closes_at)
        )
        .scalars()
        .all()
    )
    return [PublicSchemeOut.model_validate(r) for r in rows]


class InstitutionOut(Schema):
    slug: str
    name: str
    short_name: str
    city: str | None
    country_code: str
    currency: str
    locale: str
    timezone: str
    logo_url: str | None
    crest_url: str | None
    brand_primary: str | None
    brand_accent: str | None
    website: str | None
    support_email: str | None
    accreditation_number: str | None
    #: Which module apps this deployment has switched on, so an app can refuse
    #: to render a launcher tile for something the institution has not bought.
    enabled_modules: list[str]


@router.get("/institution", response_model=InstitutionOut)
def institution(request: Request) -> InstitutionOut:
    """Branding and locale, read before anyone has signed in.

    Served from the resolved tenant rather than a database read, so a sign-in
    page renders with the right crest on the first request without touching
    the tenant's own database.
    """
    from acmis.core.db import ControlSessionLocal
    from acmis.modules.tenancy.models import Tenant

    tenant = tenant_of(request)
    control = ControlSessionLocal()
    try:
        row = control.get(Tenant, tenant.id)
        return InstitutionOut(
            slug=tenant.slug,
            name=tenant.name,
            short_name=row.short_name if row else tenant.slug.upper(),
            city=row.city if row else None,
            country_code=row.country_code if row else "UG",
            currency=tenant.currency,
            locale=tenant.locale,
            timezone=tenant.timezone,
            logo_url=row.logo_url if row else None,
            crest_url=row.crest_url if row else None,
            brand_primary=row.brand_primary if row else None,
            brand_accent=row.brand_accent if row else None,
            website=row.website if row else None,
            support_email=row.support_email if row else None,
            accreditation_number=row.accreditation_number if row else None,
            enabled_modules=sorted(tenant.features),
        )
    finally:
        control.close()


class PublicIntakeOut(Schema):
    """One programme an applicant may choose under a scheme."""

    programme_intake_id: uuid.UUID
    programme_code: str
    programme_name: str
    award_title: str
    award_abbreviation: str
    duration_semesters: int
    #: What the faculty asks for. Published because an applicant choosing
    #: blind wastes their choice and the office's review.
    entry_requirements: str | None
    minimum_aggregate: float | None
    #: Last cycle's cut-off, where there was one. The single most useful number
    #: for deciding whether a choice is realistic, and the one applicants
    #: otherwise ask the office for by telephone, one at a time.
    previous_cutoff: float | None
    tuition_per_semester_minor: int
    approved_intake: int


@router.get("/admission-schemes/{scheme_id}/intakes", response_model=list[PublicIntakeOut])
def public_scheme_intakes(
    scheme_id: Annotated[uuid.UUID, Path()],
    request: Request,
    db: Session = Depends(tenant_db),
) -> list[PublicIntakeOut]:
    """The programmes on offer under one open scheme.

    Public, and limited to open schemes, because this is the list an applicant
    picks from before they have an account — and because `programme_intake_id`
    is required to start an application at all, so without it the apply
    journey cannot begin.

    Seat counts are published; applications received and offers issued are
    not. The approved intake is a fact about the institution's plan and helps
    an applicant judge a choice. A live count of who else has applied would
    turn the last week of a cycle into a stampede, and is the office's
    business besides.
    """
    from acmis.modules.admissions.models import AdmissionScheme, ProgrammeIntake, SchemeStatus
    from acmis.modules.curriculum.models import Programme

    tenant_of(request)

    rows = db.execute(
        select(ProgrammeIntake, Programme)
        .join(Programme, Programme.id == ProgrammeIntake.programme_id)
        .join(AdmissionScheme, AdmissionScheme.id == ProgrammeIntake.scheme_id)
        .where(
            ProgrammeIntake.scheme_id == scheme_id,
            AdmissionScheme.status == SchemeStatus.OPEN,
            AdmissionScheme.deleted_at.is_(None),
            ProgrammeIntake.deleted_at.is_(None),
            Programme.deleted_at.is_(None),
        )
        .order_by(Programme.name)
    ).all()

    return [
        PublicIntakeOut(
            programme_intake_id=intake.id,
            programme_code=programme.code,
            programme_name=programme.name,
            award_title=programme.award_title,
            award_abbreviation=programme.award_abbreviation,
            duration_semesters=programme.duration_semesters,
            entry_requirements=programme.entry_requirements,
            minimum_aggregate=float(intake.minimum_aggregate)
            if intake.minimum_aggregate is not None
            else None,
            previous_cutoff=float(intake.previous_cutoff)
            if intake.previous_cutoff is not None
            else None,
            tuition_per_semester_minor=intake.tuition_per_semester_minor,
            approved_intake=intake.approved_intake,
        )
        for intake, programme in rows
    ]


# ---------------------------------------------------------------------------
# Applicant self-registration
# ---------------------------------------------------------------------------


class ApplicantRegisterIn(Schema):
    """What a prospective student types to open an application account.

    Deliberately short. This is the form standing between a school leaver with
    one bar of signal and the ability to apply at all, so it asks only for what
    is needed to raise an account and to tell two applicants apart. Everything
    else — the rest of the bio-data, the results, the programme choices — is
    collected inside the application, where it can be saved a step at a time
    and come back to.

    `national_id` is optional on purpose: many applicants hold none when they
    apply, and requiring one here would exclude them from the system entirely
    rather than from one field.
    """

    surname: str = Field(min_length=2, max_length=100)
    given_names: str = Field(min_length=2, max_length=200)
    other_names: str | None = Field(default=None, max_length=200)
    date_of_birth: date
    sex: str = Field(pattern="^(female|male)$")
    nationality: str = Field(default="South Sudanese", min_length=2, max_length=60)
    country_code: str = Field(default="SS", min_length=2, max_length=2)
    #: State, county or district, as that country words it.
    district_of_origin: str | None = Field(default=None, max_length=80)
    email: EmailStr
    phone: str = Field(min_length=6, max_length=40)
    national_id: str | None = Field(default=None, max_length=60)
    guardian_name: str | None = Field(default=None, max_length=200)
    guardian_phone: str | None = Field(default=None, max_length=40)
    password: str = Field(min_length=1, max_length=200)


class ApplicantRegisteredOut(Schema):
    #: Doubles as the username. Shown once, and emailed, because an applicant
    #: who loses it cannot sign in and will telephone the registry.
    reference: str
    email: str
    display_name: str


@router.post(
    "/applicants",
    response_model=ApplicantRegisteredOut,
    status_code=status.HTTP_201_CREATED,
)
def register_applicant(
    payload: ApplicantRegisterIn,
    request: Request,
    db: Session = Depends(tenant_db),
) -> ApplicantRegisteredOut:
    """Open an application account.

    Unauthenticated by necessity: the whole point is that the person has no
    account yet. Three things guard it — the global rate limiter, the tenant
    having at least one open scheme, and the uniqueness check below.

    ## Why registration is gated on an open scheme

    An account that cannot apply to anything is a support call. More to the
    point, it is also a free write to a tenant database from the public
    internet; tying it to a cycle the institution has deliberately opened
    keeps that window shut for most of the year.

    ## On telling the caller the email is taken

    It does, and that is a considered choice rather than an oversight. The
    alternative — accepting the registration silently and emailing the
    existing account — is what a consumer product does to avoid confirming an
    address to a stranger. Here the cost of that discretion is an applicant
    who believes they have an account, waits for an email that explains they
    already had one, and misses a deadline that will not move. The address is
    also far less sensitive than the equivalent on a bank: knowing that
    somebody applied to this university is not a secret worth a missed intake.
    """
    from acmis.core.security import hash_password, password_problems
    from acmis.modules.admissions.models import AdmissionScheme, Applicant, SchemeStatus
    from acmis.modules.identity.models import AccountKind, AccountStatus, UserAccount

    tenant_of(request)

    problems = password_problems(
        payload.password,
        context=[payload.email, payload.surname, payload.given_names],
    )
    if problems:
        raise ValidationFailed(
            "That password is not strong enough.",
            details={"fields": {"password": problems}},
        )

    open_scheme = db.execute(
        select(AdmissionScheme.id).where(
            AdmissionScheme.status == SchemeStatus.OPEN,
            AdmissionScheme.deleted_at.is_(None),
        )
    ).first()
    if open_scheme is None:
        raise Conflict(
            "Applications are not open at the moment. Accounts can be created "
            "once an admission cycle opens."
        )

    email = payload.email.strip().lower()
    taken = db.execute(
        select(UserAccount.id).where(
            func.lower(UserAccount.email) == email,
            UserAccount.deleted_at.is_(None),
        )
    ).first()
    if taken is not None:
        raise Conflict(
            "An account already exists for that email address. Sign in "
            "instead, or use 'forgotten password' to get back into it."
        )

    applicant = Applicant(
        reference=_next_applicant_reference(db),
        surname=payload.surname.strip(),
        given_names=payload.given_names.strip(),
        other_names=(payload.other_names or "").strip() or None,
        date_of_birth=payload.date_of_birth,
        sex=payload.sex,
        nationality=payload.nationality.strip(),
        country_code=payload.country_code.upper(),
        district_of_origin=(payload.district_of_origin or "").strip() or None,
        email=email,
        phone=payload.phone.strip(),
        national_id=(payload.national_id or "").strip() or None,
        guardian_name=(payload.guardian_name or "").strip() or None,
        guardian_phone=(payload.guardian_phone or "").strip() or None,
    )
    db.add(applicant)
    db.flush()

    display_name = f"{payload.given_names.strip()} {payload.surname.strip()}"
    account = UserAccount(
        # The reference is the username, exactly as it is for staff numbers and
        # student numbers. One rule for signing in across the whole system.
        username=applicant.reference,
        email=email,
        kind=AccountKind.APPLICANT,
        # Active rather than pending: there is no verification mail in this
        # deployment yet, and an account nobody can sign into is worse than an
        # unverified address on a record the registry will check anyway when
        # the documents arrive. `email_verified_at` stays null, so a later
        # verification flow can find these and ask.
        status=AccountStatus.ACTIVE,
        display_name=display_name,
        password_hash=hash_password(payload.password),
        password_changed_at=datetime.now(tz=UTC),
        applicant_id=applicant.id,
    )
    db.add(account)
    db.flush()

    applicant.account_id = account.id
    db.commit()

    return ApplicantRegisteredOut(
        reference=applicant.reference,
        email=email,
        display_name=display_name,
    )


def _next_applicant_reference(db: Session) -> str:
    """`APL/<year>/<n>`, counting within the year.

    Derived from the highest existing reference for the year rather than from a
    row count, because applicants are never hard-deleted but a count would
    still drift the moment one was, and two applicants sharing a reference is
    a collision on the thing people quote down a telephone.
    """
    from acmis.modules.admissions.models import Applicant

    year = datetime.now(tz=UTC).year
    prefix = f"APL/{year}/"
    highest = db.execute(
        select(func.max(Applicant.reference)).where(Applicant.reference.like(f"{prefix}%"))
    ).scalar_one_or_none()
    nth = int(highest.rsplit("/", 1)[1]) + 1 if highest else 1
    return f"{prefix}{nth:04d}"
