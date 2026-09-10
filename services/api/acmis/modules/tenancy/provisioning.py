"""Creating and migrating tenant databases.

The operational cost of database-per-tenant lives here, and it is worth stating
plainly: onboarding a university means creating a database, running the tenant
migration tree against it and seeding its reference data, and every subsequent
schema change means doing the migration part again for every tenant. That fan-
out is the price of the isolation guarantee in `core.db`.

Three things make it tolerable at a few hundred tenants:

* **Idempotence.** Every step can be re-run. A fan-out that fails on tenant 47
  is resumed, not restarted.
* **Recorded state.** `Tenant.schema_revision` and the `tenant_migration` rows
  make "which universities are behind" answerable without connecting to all of
  them.
* **Bounded concurrency.** Migrations run a few at a time. Two hundred
  simultaneous `ALTER TABLE`s against one cluster is an outage.
"""

from __future__ import annotations

import re
import uuid
from collections.abc import Iterable, Sequence
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Any

import structlog
from alembic.config import Config
from slugify import slugify
from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session

from acmis.core.config import settings
from acmis.core.db import control_session_ctx, forget_tenant_engine
from acmis.core.errors import ProvisioningError, ValidationFailed
from acmis.core.models import utcnow
from acmis.modules.tenancy.models import Tenant, TenantMigration, TenantStatus
from alembic import command

log = structlog.get_logger(__name__)

#: Postgres identifiers are 63 bytes and unquoted names fold to lower case.
#: Validated with a strict pattern because this value is interpolated into
#: `CREATE DATABASE`, which takes no parameters — the one place in the codebase
#: where a name reaches SQL as text rather than as a bound parameter.
_DB_NAME = re.compile(r"^[a-z][a-z0-9_]{2,62}$")

RESERVED_SLUGS = frozenset(
    {
        "admin",
        "api",
        "www",
        "app",
        "static",
        "assets",
        "acmis",
        "platform",
        "support",
        "status",
        "docs",
        "login",
        "auth",
        "public",
        "test",
        "sandbox",
    }
)


@dataclass(slots=True)
class ProvisionRequest:
    name: str
    short_name: str
    slug: str | None = None
    country_code: str = "UG"
    city: str | None = None
    currency: str = "UGX"
    locale: str = "en-UG"
    timezone: str = "Africa/Kampala"
    regulator_code: str | None = None
    plan_code: str | None = None
    region: str = "eu-west-1"
    enabled_features: Sequence[str] = ()
    primary_hostname: str | None = None
    #: Seed the reference data — an academic year, a grading scale, the system
    #: roles. A tenant without them cannot be signed into, so it defaults on.
    seed_reference_data: bool = True


def normalise_slug(value: str) -> str:
    slug = slugify(value, max_length=40, separator="")[:40]
    if len(slug) < 3:
        raise ValidationFailed(
            "The institution's short identifier must be at least 3 characters.",
            code="slug_too_short",
        )
    if slug in RESERVED_SLUGS:
        raise ValidationFailed(
            f"'{slug}' is reserved. Choose another identifier.", code="slug_reserved"
        )
    return slug


def database_name_for(slug: str) -> str:
    name = f"{settings.tenant_database_prefix}{slug}".lower()[:63]
    if not _DB_NAME.match(name):
        raise ProvisioningError(f"derived database name {name!r} is not a safe identifier")
    return name


def create_database(database: str) -> bool:
    """`CREATE DATABASE`. Returns False if it already existed.

    Runs on its own AUTOCOMMIT connection to the maintenance database, because
    `CREATE DATABASE` cannot run inside a transaction block. The name has
    already passed `_DB_NAME`; it is interpolated because Postgres does not
    accept a parameter in this position.
    """
    if not _DB_NAME.match(database):
        raise ProvisioningError(f"refusing to create database with unsafe name {database!r}")

    admin_dsn = settings.tenant_dsn("postgres")
    engine = create_engine(admin_dsn, isolation_level="AUTOCOMMIT")
    try:
        with engine.connect() as conn:
            exists = conn.execute(
                text("SELECT 1 FROM pg_database WHERE datname = :n"), {"n": database}
            ).scalar()
            if exists:
                log.info("tenant_database_exists", database=database)
                return False
            conn.execute(
                text(
                    f'CREATE DATABASE "{database}" '
                    "ENCODING 'UTF8' LC_COLLATE 'en_US.UTF-8' LC_CTYPE 'en_US.UTF-8' "
                    "TEMPLATE template0"
                )
            )
        install_extensions(database)
        log.info("tenant_database_created", database=database)
        return True
    except Exception as exc:  # pragma: no cover - depends on cluster config
        raise ProvisioningError(f"could not create database {database}: {exc}") from exc
    finally:
        engine.dispose()


#: Extensions every tenant database needs, and what each is for.
#:
#: Installed per database rather than relied upon from `template1`, because
#: `create_database` deliberately uses `template0` — a clean template, so a
#: tenant never inherits whatever somebody left in `template1`. The cost of
#: that choice is exactly this: the extensions have to be installed here.
#: Forgetting one produces a database where student search silently falls back
#: to a sequential scan, or an index that will not build.
REQUIRED_EXTENSIONS = (
    # `gen_random_uuid()` for the append-only audit purge function.
    "pgcrypto",
    # Trigram indexes for name search across students, staff and applicants.
    "pg_trgm",
    # GIN opclasses for scalar types, so a composite GIN over a uuid and a
    # uuid[] is possible at all.
    "btree_gin",
    # Accent-insensitive search: "Byaruhanga" and "Byaruhanga" with a
    # combining mark must match.
    "unaccent",
)


def install_extensions(database: str) -> None:
    """Install the required extensions into one tenant database. Idempotent."""
    engine = create_engine(settings.tenant_dsn(database), isolation_level="AUTOCOMMIT")
    try:
        with engine.connect() as conn:
            for extension in REQUIRED_EXTENSIONS:
                conn.execute(text(f'CREATE EXTENSION IF NOT EXISTS "{extension}"'))
        log.info("tenant_extensions_installed", database=database)
    finally:
        engine.dispose()


def drop_database(database: str, *, confirm_slug: str) -> None:
    """Destroy a tenant database. Guarded twice, deliberately.

    Called only from the archival purge, after the contractual retention date,
    and it requires the caller to name the tenant slug that the database is
    derived from. Nothing about this operation should be convenient.
    """
    expected = database_name_for(normalise_slug(confirm_slug))
    if expected != database:
        raise ProvisioningError(
            "refusing to drop: the confirmation slug does not match the database name"
        )
    forget_tenant_engine(confirm_slug)
    engine = create_engine(settings.tenant_dsn("postgres"), isolation_level="AUTOCOMMIT")
    try:
        with engine.connect() as conn:
            conn.execute(text(f'DROP DATABASE IF EXISTS "{database}" WITH (FORCE)'))
        log.warning("tenant_database_dropped", database=database)
    finally:
        engine.dispose()


def _alembic_config(*, dsn: str, tree: str) -> Config:
    root = Path(__file__).resolve().parents[3]
    config = Config(str(root / "alembic.ini"))
    config.set_main_option("script_location", str(root / "alembic" / tree))
    config.set_main_option("sqlalchemy.url", dsn)
    return config


def migrate_tenant(
    *, tenant_id: uuid.UUID, slug: str, database: str, revision: str = "head"
) -> str:
    """Run the tenant migration tree against one database.

    Each run is recorded before it starts and updated when it finishes, so a
    crash mid-migration leaves a `running` row rather than silence. That row is
    what the resume logic looks for.
    """
    dsn = settings.tenant_dsn(database)
    started = utcnow()

    with control_session_ctx() as control:
        tenant = control.get(Tenant, tenant_id)
        from_revision = tenant.schema_revision if tenant else None
        run = TenantMigration(
            tenant_id=tenant_id,
            from_revision=from_revision,
            to_revision=revision,
            status="running",
            started_at=started,
        )
        control.add(run)
        control.flush()
        run_id = run.id

    try:
        command.upgrade(_alembic_config(dsn=dsn, tree="tenant"), revision)
        applied = current_revision(dsn)
    except Exception as exc:
        with control_session_ctx() as control:
            row = control.get(TenantMigration, run_id)
            if row is not None:
                row.status = "failed"
                row.finished_at = utcnow()
                row.error = str(exc)[:4000]
            tenant = control.get(Tenant, tenant_id)
            if tenant is not None and tenant.status == TenantStatus.PROVISIONING:
                tenant.status = TenantStatus.FAILED
        log.error("tenant_migration_failed", tenant=slug, error=str(exc))
        raise ProvisioningError(f"migration failed for {slug}: {exc}") from exc

    finished = utcnow()
    with control_session_ctx() as control:
        row = control.get(TenantMigration, run_id)
        if row is not None:
            row.status = "succeeded"
            row.finished_at = finished
            row.duration_ms = int((finished - started).total_seconds() * 1000)
        tenant = control.get(Tenant, tenant_id)
        if tenant is not None:
            tenant.schema_revision = applied
            tenant.schema_migrated_at = finished
    log.info("tenant_migrated", tenant=slug, revision=applied)
    return applied or revision


def current_revision(dsn: str) -> str | None:
    engine = create_engine(dsn)
    try:
        with engine.connect() as conn:
            return conn.execute(text("SELECT version_num FROM alembic_version")).scalar()
    except Exception:
        return None
    finally:
        engine.dispose()


def provision(request: ProvisionRequest, *, actor_id: uuid.UUID | None = None) -> Tenant:
    """Onboard a university, end to end.

    Order matters. The control-plane row is written first with status
    `provisioning`, so a failure part-way leaves a visible, resumable record
    instead of an orphaned database nothing knows about. The tenant only
    becomes `active` once its schema and seed data are in place — until then
    the resolver refuses requests for it with "still being set up" rather than
    letting a half-built database serve traffic.
    """
    slug = normalise_slug(request.slug or request.short_name or request.name)
    database = database_name_for(slug)

    with control_session_ctx() as control:
        if control.query(Tenant).filter(Tenant.slug == slug).first():
            raise ValidationFailed(
                f"An institution with the identifier '{slug}' already exists.",
                code="tenant_exists",
            )
        tenant = Tenant(
            slug=slug,
            name=request.name,
            short_name=request.short_name,
            status=TenantStatus.PROVISIONING,
            database_name=database,
            region=request.region,
            country_code=request.country_code,
            city=request.city,
            locale=request.locale,
            timezone=request.timezone,
            currency=request.currency,
            regulator_code=request.regulator_code,
            enabled_features=list(request.enabled_features),
        )
        control.add(tenant)
        control.flush()
        tenant_id = tenant.id

        if request.primary_hostname:
            from acmis.modules.tenancy.models import TenantDomain

            control.add(
                TenantDomain(
                    tenant_id=tenant_id,
                    hostname=request.primary_hostname.lower(),
                    is_primary=True,
                )
            )

    log.info("tenant_registered", tenant=slug, database=database)

    create_database(database)
    # Idempotent, and re-run on an existing database so a tenant created
    # before an extension was added to the list picks it up.
    install_extensions(database)
    migrate_tenant(tenant_id=tenant_id, slug=slug, database=database)

    if request.seed_reference_data:
        from acmis.modules.tenancy.seed import seed_tenant

        seed_tenant(slug=slug, dsn=settings.tenant_dsn(database), tenant_name=request.name)

    with control_session_ctx() as control:
        provisioned = control.get(Tenant, tenant_id)
        if provisioned is None:  # pragma: no cover
            raise ProvisioningError("tenant vanished during provisioning")
        tenant = provisioned
        tenant.status = TenantStatus.ACTIVE
        tenant.onboarded_at = utcnow()
        if request.plan_code:
            _attach_plan(control, tenant, request.plan_code)
        control.flush()
        control.refresh(tenant)
        control.expunge(tenant)

    from acmis.core import tenant_resolver

    tenant_resolver.invalidate(slug=slug)
    log.info("tenant_provisioned", tenant=slug)
    return tenant


def _attach_plan(control: Session, tenant: Tenant, plan_code: str) -> None:
    from acmis.modules.tenancy.models import Plan, Subscription

    plan = control.query(Plan).filter(Plan.code == plan_code).first()
    if plan is None:
        log.warning("plan_not_found", plan=plan_code)
        return
    control.add(
        Subscription(
            tenant_id=tenant.id,
            plan_id=plan.id,
            status="trialing",
            started_on=date.today(),
        )
    )
    # The plan is what turns modules on. Anything already enabled on the
    # tenant stays enabled: a bespoke arrangement should not be silently
    # removed by attaching a standard plan.
    tenant.enabled_features = sorted(set(tenant.enabled_features) | set(plan.included_modules))


def migrate_all(
    *, revision: str = "head", concurrency: int = 4, only: Iterable[str] | None = None
) -> dict[str, Any]:
    """Fan a migration out across every active tenant.

    Bounded concurrency, and failures are collected rather than raised: one
    university with a lock held by a long-running report must not stop the
    other 199 from being migrated. The report says which ones to retry.
    """
    with control_session_ctx() as control:
        query = control.query(Tenant).filter(
            Tenant.status.in_([TenantStatus.ACTIVE, TenantStatus.READ_ONLY])
        )
        if only:
            query = query.filter(Tenant.slug.in_(list(only)))
        targets = [(t.id, t.slug, t.database_name) for t in query.all()]

    succeeded: list[str] = []
    failed: dict[str, str] = {}

    with ThreadPoolExecutor(max_workers=max(1, concurrency)) as pool:
        futures = {
            pool.submit(
                migrate_tenant,
                tenant_id=tenant_id,
                slug=slug,
                database=database,
                revision=revision,
            ): slug
            for tenant_id, slug, database in targets
        }
        for future in as_completed(futures):
            slug = futures[future]
            try:
                future.result()
                succeeded.append(slug)
            except Exception as exc:
                failed[slug] = str(exc)[:500]

    log.info("migrate_all_complete", succeeded=len(succeeded), failed=len(failed))
    return {
        "revision": revision,
        "total": len(targets),
        "succeeded": sorted(succeeded),
        "failed": failed,
    }


def migration_status() -> list[dict[str, Any]]:
    """Which tenants are on which revision. The fan-out's dashboard."""
    with control_session_ctx() as control:
        rows = control.query(Tenant).order_by(Tenant.slug).all()
        return [
            {
                "slug": t.slug,
                "name": t.name,
                "status": t.status,
                "schema_revision": t.schema_revision,
                "migrated_at": t.schema_migrated_at.isoformat() if t.schema_migrated_at else None,
                "region": t.region,
            }
            for t in rows
        ]
