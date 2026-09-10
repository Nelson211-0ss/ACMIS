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
from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Depends, Path, Request
from sqlalchemy import select
from sqlalchemy.orm import Session

from acmis.core.deps import tenant_db, tenant_of
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
