"""Operator commands.

    python -m acmis.cli control-migrate         # migrate the control plane
    python -m acmis.cli control-seed            # plans + bootstrap admin
    python -m acmis.cli provision <slug> <name> # onboard a university
    python -m acmis.cli demo                    # provision + populate the demo
    python -m acmis.cli migrate-all             # fan out to every tenant
    python -m acmis.cli status                  # which tenant is on which revision

Deliberately not `click` or `typer`: this is six commands run by an operator on
a server, and `argparse` is in the standard library. A dependency earns its
place by doing something the standard library cannot.
"""

from __future__ import annotations

import argparse
import sys
from typing import Any

import structlog

from acmis.core.config import settings
from acmis.core.db import control_session_ctx
from acmis.core.logging import configure_logging
from acmis.modules.registry import configure as configure_mappers

log = structlog.get_logger(__name__)

#: The demonstration institution. Persistent by design: `demo` re-runs are
#: additive and never destroy anything, so a walkthrough survives a re-seed.
DEMO_SLUG = "demo"
DEMO_NAME = "Kampala Institute of Technology"
#: Everything the demonstration institution has bought. Named once because it
#: is also reconciled onto an existing tenant: a module added to the platform
#: after the demo was provisioned would otherwise stay invisible in the
#: launcher, which reads as a broken build rather than an unbought feature.
DEMO_FEATURES = [
    "admissions",
    "students",
    "curriculum",
    "assessment",
    "learning",
    "finance",
    "people",
    "governance",
    "developers",
    "library",
    "quality",
]


# Every command touches the ORM, so the registry is completed once, here.
configure_mappers()


def control_migrate(_args: argparse.Namespace) -> int:
    from alembic.config import Config

    from alembic import command

    config = Config("alembic.ini")
    config.set_main_option("script_location", "alembic/control")
    config.set_main_option("sqlalchemy.url", str(settings.control_database_url))
    command.upgrade(config, "head")
    print("Control plane migrated.")
    return 0


def control_seed(_args: argparse.Namespace) -> int:
    from acmis.modules.tenancy.seed import seed_control_plane

    with control_session_ctx() as control:
        result = seed_control_plane(control)
    print(f"Plans added: {result['plans']}, platform users added: {result['platform_users']}")
    if result["platform_users"] == 0:
        print(
            "No platform administrator was created. Set ACMIS_BOOTSTRAP_PASSWORD "
            "and re-run if you need one."
        )
    return 0


def provision(args: argparse.Namespace) -> int:
    from acmis.modules.tenancy.provisioning import ProvisionRequest
    from acmis.modules.tenancy.provisioning import provision as run

    tenant = run(
        ProvisionRequest(
            name=args.name,
            short_name=args.short or args.slug.upper(),
            slug=args.slug,
            plan_code=args.plan,
            city=args.city,
            primary_hostname=args.hostname,
            enabled_features=[
                "admissions",
                "students",
                "curriculum",
                "assessment",
                "learning",
                "finance",
                "people",
                "governance",
                "developers",
            ],
        )
    )
    print(f"Provisioned {tenant.slug} ({tenant.name}) -> database {tenant.database_name}")
    return 0


def demo(args: argparse.Namespace) -> int:
    """Provision the demonstration institution and populate it.

    Idempotent end to end: provisioning skips an existing tenant, migration is
    a no-op when the schema is current, and the demo data adds only what is
    missing. Nothing is ever dropped — the tenant is meant to persist.
    """
    from acmis.modules.tenancy.demo import DEMO_PASSWORD, seed_demo
    from acmis.modules.tenancy.models import Tenant
    from acmis.modules.tenancy.provisioning import (
        ProvisionRequest,
        create_database,
        migrate_tenant,
    )
    from acmis.modules.tenancy.provisioning import (
        provision as run,
    )
    from acmis.modules.tenancy.seed import seed_control_plane, seed_tenant

    with control_session_ctx() as control:
        seed_control_plane(control)
        existing = control.query(Tenant).filter(Tenant.slug == DEMO_SLUG).first()
        tenant_id = existing.id if existing else None
        database = existing.database_name if existing else None

    if tenant_id is None:
        tenant = run(
            ProvisionRequest(
                name=DEMO_NAME,
                short_name="KIT",
                slug=DEMO_SLUG,
                city="Kampala",
                plan_code="institution",
                primary_hostname=f"{DEMO_SLUG}.{settings.tenant_host_suffix}",
                enabled_features=DEMO_FEATURES,
            )
        )
        tenant_id, database = tenant.id, tenant.database_name
        print(f"Provisioned {DEMO_SLUG} -> {database}")
    else:
        print(f"Tenant '{DEMO_SLUG}' already exists ({database}); leaving it in place.")
        assert database is not None
        with control_session_ctx() as control:
            row = control.query(Tenant).filter(Tenant.slug == DEMO_SLUG).first()
            if row is not None:
                added = sorted(set(DEMO_FEATURES) - set(row.enabled_features or []))
                if added:
                    row.enabled_features = sorted(
                        set(row.enabled_features or []) | set(DEMO_FEATURES)
                    )
                    control.commit()
                    print(f"  Enabled newly-available modules: {', '.join(added)}")
        # Resume rather than assume. A tenant row can exist without its
        # database if a previous run died between the two — which is exactly
        # the case `provisioning` records `provisioning`/`failed` status for,
        # and the point of recording it is being able to pick up here.
        if create_database(database):
            print(f"  Database {database} was missing; created it.")
        migrate_tenant(tenant_id=tenant_id, slug=DEMO_SLUG, database=database)
        seed_tenant(slug=DEMO_SLUG, dsn=settings.tenant_dsn(database), tenant_name=DEMO_NAME)

    assert database is not None
    summary = seed_demo(slug=DEMO_SLUG, dsn=settings.tenant_dsn(database), tenant_name=DEMO_NAME)

    print("\nDemonstration institution ready.")
    print(f"  Institution : {DEMO_NAME} ({DEMO_SLUG})")
    print(f"  Database    : {database}")
    for key, value in summary.items():
        print(f"  {key:<18}: {value}")
    print("\nSign in with any of these, password:", DEMO_PASSWORD)
    print("  STF/007  Academic Registrar   — student records, transcripts")
    print("  STF/003  Lecturer             — course space, marks for CSC1100/CSC1101")
    print("  STF/016  Examinations Officer — moderation")
    print("  STF/001  Head of Department   — department board approval")
    print("  STF/017  Dean                 — faculty board approval")
    print("  STF/013  Secretary to Senate  — Senate approval, awards")
    print("  STF/009  Bursar               — finance, waivers")
    print("  STF/011  Head of Admissions   — selection lists, offers")
    print("  STF/014  Internal Auditor     — audit trail, access review")
    print("  STF/015  Systems Admin        — accounts, integrations")
    print("  STF/019  University Librarian — circulation, fines, acquisitions")
    print("  STF/021  Library Assistant    — the desk only; cannot waive a fine")
    print("  STF/022  Quality Assurance    — delivery, evaluations, audits")
    # Read back from the database rather than described. A described pattern
    # drifts: the seeded numbers are gapped and the suffix follows the
    # programme, so an invented "24/U/0060/BSC" looks right, does not exist,
    # and is refused with the same message as a wrong password.
    from acmis.modules.tenancy.demo import sample_logins

    print("\n  Students (student portal). Numbers are gapped and the suffix is the")
    print("  programme, so only these shapes exist:")
    for username, name in sample_logins(slug=DEMO_SLUG, dsn=settings.tenant_dsn(database)):
        print(f"    {username:<16} {name}")
    print(f"  ...and {summary.get('students', 0)} students in total.")
    showcase = summary.get("showcase_student")
    if showcase:
        print(f"\n  One student carries a record from every module: {showcase}")
        print("    registration, released results, an invoice in arrears, an")
        print("    examination card, a campus ID, library loan and fine, attendance,")
        print("    a granted special examination, a served dead semester, a dismissed")
        print("    disciplinary case, graduation clearance, a vote in the declared")
        print("    guild election — and a ballot still to cast in the open one.")
    print(
        "\nThe roles are deliberately held by different people: the examiner "
        "cannot\napprove their own marks, and the approve button is absent rather "
        "than\ndisabled. That is the separation of duties working."
    )
    return 0


def migrate_all(args: argparse.Namespace) -> int:
    from acmis.modules.tenancy.provisioning import migrate_all as run

    result = run(revision=args.revision, concurrency=args.concurrency)
    print(
        f"Migrated {len(result['succeeded'])} of {result['total']} tenants to {result['revision']}."
    )
    for slug, error in result["failed"].items():
        print(f"  FAILED {slug}: {error}", file=sys.stderr)
    return 1 if result["failed"] else 0


def status(_args: argparse.Namespace) -> int:
    from acmis.modules.tenancy.provisioning import migration_status

    rows = migration_status()
    if not rows:
        print("No tenants registered.")
        return 0
    width = max(len(row["slug"]) for row in rows)
    print(f"{'SLUG':<{width}}  {'STATUS':<12}  {'REVISION':<16}  NAME")
    for row in rows:
        print(
            f"{row['slug']:<{width}}  {row['status']:<12}  "
            f"{(row['schema_revision'] or '-'):<16}  {row['name']}"
        )
    return 0


def main(argv: list[str] | None = None) -> int:
    configure_logging()
    parser = argparse.ArgumentParser(prog="acmis", description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)

    subparsers.add_parser("control-migrate", help="migrate the control plane").set_defaults(
        handler=control_migrate
    )
    subparsers.add_parser(
        "control-seed", help="seed plans and the bootstrap administrator"
    ).set_defaults(handler=control_seed)

    p = subparsers.add_parser("provision", help="onboard a university")
    p.add_argument("slug")
    p.add_argument("name")
    p.add_argument("--short")
    p.add_argument("--city")
    p.add_argument("--plan", default="institution")
    p.add_argument("--hostname")
    p.set_defaults(handler=provision)

    subparsers.add_parser(
        "demo", help="provision and populate the demonstration institution"
    ).set_defaults(handler=demo)

    p = subparsers.add_parser("migrate-all", help="fan a migration across every tenant")
    p.add_argument("--revision", default="head")
    p.add_argument("--concurrency", type=int, default=4)
    p.set_defaults(handler=migrate_all)

    subparsers.add_parser("status", help="which tenant is on which revision").set_defaults(
        handler=status
    )

    args = parser.parse_args(argv)
    handler: Any = args.handler
    return int(handler(args))


if __name__ == "__main__":
    raise SystemExit(main())
