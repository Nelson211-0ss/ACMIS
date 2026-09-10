"""Reference data every new tenant needs before anyone can sign in.

Called by `provisioning.provision`. Idempotent throughout — provisioning can
be resumed, and a tenant part-way through setup must not end up with two
grading scales or duplicate roles.

What is seeded is the *skeleton*, not content: permissions and roles (because
policies name them), a grading scale (because a mark cannot be graded without
one), an academic year and its semesters (because every module gates on
dates), and a main campus. Programmes, courses and people are the
institution's own and are loaded by them or by the demo script.
"""

from __future__ import annotations

from datetime import date
from typing import Any

import structlog
from sqlalchemy import select
from sqlalchemy.orm import Session

from acmis.core.db import tenant_session_ctx
from acmis.core.models import utcnow
from acmis.modules.assessment.models import GradeBand, GradingScale
from acmis.modules.identity.models import Permission, Role
from acmis.modules.registry import configure as _configure_mappers
from acmis.modules.shared.models import (
    AcademicUnit,
    AcademicYear,
    Campus,
    Semester,
    SystemSetting,
    UnitKind,
)

log = structlog.get_logger(__name__)


# ---------------------------------------------------------------------------
# Permissions
# ---------------------------------------------------------------------------
#
# Every code the shipped policy bundle reads, and nothing it does not. The
# `conflicts_with` column is what makes separation of duties refusable at the
# point of *granting* a role rather than discovered at the point of use — see
# `identity.service._permission_conflicts`.

PERMISSIONS: tuple[dict[str, Any], ...] = (
    # --- identity ----------------------------------------------------------
    {
        "code": "identity:admin",
        "module": "identity",
        "name": "Administer accounts and roles",
        "high_risk": True,
    },
    {
        "code": "identity:reset_student",
        "module": "identity",
        "name": "Reset a student's password at the counter",
    },
    # --- admissions --------------------------------------------------------
    {"code": "admissions:process", "module": "admissions", "name": "Process applications"},
    {
        "code": "admissions:review",
        "module": "admissions",
        "name": "Review applications for own faculty",
    },
    {
        "code": "admissions:manage_scheme",
        "module": "admissions",
        "name": "Create and publish admission schemes",
        "high_risk": True,
    },
    {
        "code": "admissions:approve_selection",
        "module": "admissions",
        "name": "Approve selection lists and issue offers",
        "high_risk": True,
        # The person who prepares a merit list must not be the person who
        # approves it. 4,000 applicants learn their outcome from that approval.
        "conflicts_with": ["admissions:process"],
    },
    {
        "code": "admissions:read_sensitive",
        "module": "admissions",
        "name": "Read applicant special-category data",
        "high_risk": True,
    },
    {
        "code": "admissions:override_intake",
        "module": "admissions",
        "name": "Admit beyond the approved intake",
        "high_risk": True,
    },
    # --- students ----------------------------------------------------------
    {"code": "student:manage", "module": "students", "name": "Maintain student records"},
    {
        "code": "student:read_unit",
        "module": "students",
        "name": "Read students in own faculty or department",
    },
    {
        "code": "student:approve_status",
        "module": "students",
        "name": "Approve status changes, leave and withdrawal",
        "high_risk": True,
        "conflicts_with": ["student:manage"],
    },
    {
        "code": "registration:override_deadline",
        "module": "students",
        "name": "Register a student after the deadline",
        "high_risk": True,
    },
    {
        "code": "registration:override_finance",
        "module": "students",
        "name": "Register a student despite a fee block",
        "high_risk": True,
    },
    {
        "code": "welfare:support",
        "module": "students",
        "name": "Read disability and welfare records",
        "high_risk": True,
    },
    {
        "code": "welfare:medical",
        "module": "students",
        "name": "Read medical records",
        "high_risk": True,
    },
    {
        "code": "discipline:investigate",
        "module": "students",
        "name": "Investigate disciplinary cases",
    },
    {
        "code": "discipline:chair",
        "module": "students",
        "name": "Chair the disciplinary committee",
        "high_risk": True,
        "conflicts_with": ["discipline:investigate"],
    },
    # --- curriculum --------------------------------------------------------
    {"code": "curriculum:author", "module": "curriculum", "name": "Draft programmes and courses"},
    {
        "code": "curriculum:recommend",
        "module": "curriculum",
        "name": "Recommend curricula at faculty board",
    },
    {
        "code": "curriculum:approve",
        "module": "curriculum",
        "name": "Approve curricula at Senate",
        "high_risk": True,
        # Whoever wrote the programme must not be the one who approves it.
        "conflicts_with": ["curriculum:author"],
    },
    {
        "code": "curriculum:waive_prerequisite",
        "module": "curriculum",
        "name": "Waive a course prerequisite",
    },
    {"code": "timetable:manage", "module": "curriculum", "name": "Manage the timetable"},
    {
        "code": "timetable:override_clash",
        "module": "curriculum",
        "name": "Schedule despite a clash",
    },
    # --- finance -----------------------------------------------------------
    {"code": "finance:receipt", "module": "finance", "name": "Receipt payments"},
    {"code": "finance:post", "module": "finance", "name": "Raise invoices and post journals"},
    {
        "code": "finance:approve",
        "module": "finance",
        "name": "Approve invoices, refunds and fee structures",
        "high_risk": True,
        # Four eyes on money: the raiser cannot be the releaser.
        "conflicts_with": ["finance:post", "finance:receipt"],
    },
    {"code": "finance:waive", "module": "finance", "name": "Raise a fee waiver"},
    {
        "code": "finance:waive_unlimited",
        "module": "finance",
        "name": "Release a waiver of any amount",
        "high_risk": True,
    },
    {
        "code": "finance:override_block",
        "module": "finance",
        "name": "Override a fee block on examinations or graduation",
        "high_risk": True,
    },
    {
        "code": "finance:reopen_period",
        "module": "finance",
        "name": "Reopen a closed accounting period",
        "high_risk": True,
    },
    {
        "code": "finance:read_statement",
        "module": "finance",
        "name": "Read a student's financial statement",
    },
    # --- people ------------------------------------------------------------
    {"code": "people:admin", "module": "people", "name": "Administer staff records"},
    {
        "code": "people:manage_unit",
        "module": "people",
        "name": "Manage staff in own unit: leave and workload",
    },
    {
        "code": "people:approve",
        "module": "people",
        "name": "Approve appointments and promotions",
        "high_risk": True,
        "conflicts_with": ["people:admin"],
    },
    {
        "code": "people:payroll",
        "module": "people",
        "name": "Read salary information",
        "high_risk": True,
    },
    # --- assessment --------------------------------------------------------
    {"code": "results:enter", "module": "assessment", "name": "Enter marks for own courses"},
    {"code": "results:moderate", "module": "assessment", "name": "Moderate submitted marks"},
    {
        "code": "results:board_approve",
        "module": "assessment",
        "name": "Approve marks at department board",
        "high_risk": True,
        # The single most important conflict in the system: an examiner who
        # approves their own marks makes the award indefensible.
        "conflicts_with": ["results:enter"],
    },
    {
        "code": "results:faculty_approve",
        "module": "assessment",
        "name": "Approve marks at faculty board",
        "high_risk": True,
        "conflicts_with": ["results:enter"],
    },
    {
        "code": "results:senate_approve",
        "module": "assessment",
        "name": "Approve and release results at Senate",
        "high_risk": True,
        "conflicts_with": ["results:enter", "results:moderate"],
    },
    {
        "code": "results:amend_on_appeal",
        "module": "assessment",
        "name": "Amend a published result under an appeal",
        "high_risk": True,
    },
    {"code": "award:prepare", "module": "assessment", "name": "Prepare graduation lists"},
    {
        "code": "award:confer",
        "module": "assessment",
        "name": "Confer awards",
        "high_risk": True,
        "conflicts_with": ["award:prepare"],
    },
    {
        "code": "transcript:issue",
        "module": "assessment",
        "name": "Issue official transcripts",
        "high_risk": True,
    },
    # --- governance --------------------------------------------------------
    {
        "code": "audit:read",
        "module": "governance",
        "name": "Read the audit trail",
        "high_risk": True,
    },
    {
        "code": "governance:oversight",
        "module": "governance",
        "name": "Institutional oversight and access review",
        "high_risk": True,
    },
    {
        "code": "policy:admin",
        "module": "governance",
        "name": "Author authorization policies",
        "high_risk": True,
        # Whoever can rewrite the rules must not also be the one being audited
        # against them.
        "conflicts_with": ["audit:read"],
    },
    {"code": "reporting:run", "module": "governance", "name": "Run reports"},
    {
        "code": "reporting:submit_statutory",
        "module": "governance",
        "name": "Submit statutory returns",
        "high_risk": True,
    },
    {"code": "export:run", "module": "governance", "name": "Export datasets", "high_risk": True},
    {
        "code": "export:bulk_personal",
        "module": "governance",
        "name": "Export large volumes of personal data",
        "high_risk": True,
    },
    # --- learning and online assessment ------------------------------------
    {
        "code": "learning:teach",
        "module": "learning",
        "name": "Publish material and author assessments for own courses",
    },
    {
        "code": "learning:review_paper",
        "module": "learning",
        "name": "Review an assessment paper before it is sat",
        "high_risk": True,
        # Whoever wrote the questions is the last person able to spot that one of
        # them is ambiguous or that an answer key is wrong.
        "conflicts_with": ["learning:teach"],
    },
    {
        "code": "learning:invigilate",
        "module": "learning",
        "name": "Monitor live attempts and review integrity signals",
    },
    {
        "code": "learning:void_attempt",
        "module": "learning",
        "name": "Void an attempt on a malpractice finding",
        "high_risk": True,
    },
    {
        "code": "learning:manage_banks",
        "module": "learning",
        "name": "Administer departmental question banks",
    },
    {
        "code": "learning:read_engagement",
        "module": "learning",
        "name": "Read student engagement data for pastoral support",
    },
    {
        "code": "interop:manage_tools",
        "module": "learning",
        "name": "Register and grant scopes to external LTI tools",
        "high_risk": True,
    },
    # --- library -----------------------------------------------------------
    #
    # Split three ways because a library splits its desk three ways: issuing
    # books, cataloguing them, and buying them are different jobs done by
    # different people, and a circulation assistant who can also withdraw
    # stock from the catalogue is a control nobody meant to grant.
    {
        "code": "library:circulate",
        "module": "library",
        "name": "Issue, receive and renew loans; manage membership",
    },
    {
        "code": "library:catalogue",
        "module": "library",
        "name": "Catalogue stock and take stock",
    },
    {
        "code": "library:acquisitions",
        "module": "library",
        "name": "Order stock and manage e-resource subscriptions",
    },
    {
        "code": "library:admin",
        "module": "library",
        "name": "Administer the library, including waiving fines",
        "high_risk": True,
    },
    # --- elections ---------------------------------------------------------
    #
    # Three grants, because an election has three jobs and giving one person
    # all of them is the first thing a petition alleges: the office that sets
    # the rules, the officer who runs the poll, and the observers who watch.
    {
        "code": "elections:administer",
        "module": "elections",
        "name": "Set up elections: positions, dates, eligibility rules",
    },
    {
        "code": "elections:conduct",
        "module": "elections",
        "name": "Conduct a poll: build the roll, open, close, count, declare",
        "high_risk": True,
    },
    {
        "code": "elections:observe",
        "module": "elections",
        "name": "Observe an election: read everything except a ballot",
    },
    # --- quality assurance -------------------------------------------------
    {
        "code": "quality:review",
        "module": "quality",
        "name": "Read teaching delivery, evaluations and audits",
    },
    {
        "code": "quality:admin",
        "module": "quality",
        "name": "Run evaluations and audits, and read individual responses",
        # High risk because it is the only grant that can read an anonymous
        # evaluation response. Held by the quality office and audited on read.
        "high_risk": True,
    },
    # --- developers --------------------------------------------------------
    {"code": "developer:manage", "module": "developers", "name": "Manage own API clients"},
    {
        "code": "developer:admin",
        "module": "developers",
        "name": "Administer all integrations",
        "high_risk": True,
    },
)


# ---------------------------------------------------------------------------
# Roles
# ---------------------------------------------------------------------------
#
# The offices a university actually has. `requires_scope` is set wherever the
# role is meaningless without saying *which* unit — assigning "Head of
# Department" unscoped would grant department authority over every department.

ROLES: tuple[dict[str, Any], ...] = (
    {
        "code": "system_administrator",
        "name": "System Administrator",
        "permissions": ["identity:admin", "identity:reset_student", "developer:admin"],
        "description": "Manages accounts and integrations. Deliberately holds no "
        "academic or financial authority.",
    },
    {
        "code": "academic_registrar",
        "name": "Academic Registrar",
        "permissions": [
            "student:manage",
            "student:read_unit",
            "award:prepare",
            "transcript:issue",
            "registration:override_deadline",
            "reporting:run",
            "identity:reset_student",
        ],
    },
    {
        "code": "deputy_registrar_records",
        "name": "Deputy Registrar (Records)",
        "permissions": [
            "student:manage",
            "student:read_unit",
            "student:approve_status",
            "transcript:issue",
        ],
    },
    {
        "code": "admissions_officer",
        "name": "Admissions Officer",
        "permissions": ["admissions:process", "admissions:read_sensitive", "reporting:run"],
    },
    {
        "code": "head_of_admissions",
        "name": "Head of Admissions",
        "permissions": [
            "admissions:manage_scheme",
            "admissions:approve_selection",
            "admissions:read_sensitive",
            "reporting:run",
        ],
    },
    {
        "code": "faculty_dean",
        "name": "Dean",
        "requires_scope": True,
        "permissions": [
            "admissions:review",
            "student:read_unit",
            "curriculum:recommend",
            "results:faculty_approve",
            "people:manage_unit",
            "reporting:run",
        ],
    },
    {
        "code": "head_of_department",
        "name": "Head of Department",
        "requires_scope": True,
        "permissions": [
            "student:read_unit",
            "curriculum:author",
            "results:board_approve",
            "results:moderate",
            "people:manage_unit",
            "learning:manage_banks",
            "learning:review_paper",
            "learning:read_engagement",
        ],
    },
    {
        "code": "lecturer",
        "name": "Lecturer",
        "permissions": [
            "results:enter",
            "student:read_unit",
            "learning:teach",
            "learning:read_engagement",
        ],
        "description": "Enters marks for the courses they are allocated to teach, and "
        "no others — the teaching allocation is what grants it.",
    },
    {
        "code": "examinations_officer",
        "name": "Examinations Officer",
        "permissions": [
            "results:moderate",
            "timetable:manage",
            "reporting:run",
            "learning:review_paper",
            "learning:invigilate",
        ],
    },
    {
        "code": "instructional_designer",
        "name": "Instructional Designer",
        "permissions": ["learning:manage_banks", "learning:teach", "curriculum:author"],
        "description": "Builds course spaces and question banks with departments. "
        "Cannot approve a curriculum or a paper they helped write.",
    },
    {
        "code": "integration_administrator",
        "name": "Integration Administrator",
        "permissions": ["interop:manage_tools", "developer:admin"],
        "description": "Registers external tools and grants their scopes. Holds no "
        "academic authority, so a tool can never be granted more than "
        "its own owner has.",
    },
    {
        "code": "senate_secretary",
        "name": "Secretary to Senate",
        "permissions": ["results:senate_approve", "award:confer", "curriculum:approve"],
        "max_holders": 2,
    },
    {
        "code": "bursar",
        "name": "Bursar",
        "permissions": [
            "finance:approve",
            "finance:waive_unlimited",
            "finance:override_block",
            "finance:read_statement",
            "finance:reopen_period",
            "reporting:run",
        ],
    },
    {
        "code": "accountant",
        "name": "Accountant",
        "permissions": ["finance:post", "finance:read_statement", "finance:waive", "reporting:run"],
    },
    {
        "code": "cashier",
        "name": "Cashier",
        "permissions": ["finance:receipt", "finance:read_statement"],
    },
    {
        "code": "human_resources_officer",
        "name": "Human Resources Officer",
        "permissions": ["people:admin", "people:manage_unit"],
    },
    {
        "code": "human_resources_director",
        "name": "Director of Human Resources",
        "permissions": ["people:approve", "people:payroll", "people:manage_unit"],
    },
    {
        "code": "internal_auditor",
        "name": "Internal Auditor",
        "permissions": ["audit:read", "governance:oversight", "reporting:run"],
        "description": "Reads everything about who did what, and can change nothing.",
    },
    {
        "code": "quality_assurance_officer",
        "name": "Quality Assurance Officer",
        "permissions": [
            "quality:review",
            "quality:admin",
            "reporting:run",
            "reporting:submit_statutory",
            "export:run",
        ],
        "description": "Runs evaluations, observations and audits. Reads teaching "
        "delivery across the institution and holds no academic authority over it.",
    },
    {
        "code": "returning_officer",
        "name": "Returning Officer",
        "permissions": ["elections:conduct", "elections:observe"],
        "description": "Runs the poll and declares the result. Cannot set the rules "
        "and cannot stand — both are checked, because both are what a petition "
        "alleges first.",
        "max_holders": 1,
    },
    {
        "code": "guild_administrator",
        "name": "Guild Administrator",
        "permissions": ["elections:administer", "welfare:support"],
        "description": "Sets an election up before it is published. Deliberately "
        "cannot conduct the poll: the office that writes the rules is not the "
        "office that runs the count.",
    },
    {
        "code": "election_observer",
        "name": "Election Observer",
        "permissions": ["elections:observe"],
        "description": "Nominated by the candidates. Reads the roll, the candidates "
        "and the count, and changes nothing.",
    },
    {
        "code": "university_librarian",
        "name": "University Librarian",
        "permissions": [
            "library:admin",
            "library:catalogue",
            "library:circulate",
            "library:acquisitions",
        ],
        "description": "Heads the library. The only role that may waive a library "
        "fine, which is why it is separate from the circulation desk.",
    },
    {
        "code": "librarian",
        "name": "Librarian",
        "permissions": ["library:catalogue", "library:circulate", "library:acquisitions"],
        "description": "Catalogues and orders stock, and works the desk. Cannot waive "
        "a fine or write off a loss.",
    },
    {
        "code": "library_assistant",
        "name": "Library Assistant",
        "permissions": ["library:circulate"],
        "description": "Issues and receives books. Deliberately the narrowest role in "
        "the system: it is the busiest desk and the one most often shared.",
    },
    {
        "code": "data_protection_officer",
        "name": "Data Protection Officer",
        "permissions": ["governance:oversight", "audit:read", "welfare:support"],
    },
    {
        "code": "dean_of_students",
        "name": "Dean of Students",
        "permissions": [
            "welfare:support",
            "discipline:investigate",
            "student:read_unit",
            "learning:read_engagement",
        ],
    },
    {"code": "university_nurse", "name": "University Nurse", "permissions": ["welfare:medical"]},
    {"code": "developer", "name": "Developer", "permissions": ["developer:manage"]},
    {
        "code": "policy_administrator",
        "name": "Policy Administrator",
        "permissions": ["policy:admin"],
        "max_holders": 2,
        "description": "Authors this institution's own authorization rules on top of the "
        "shipped bundle. Cannot remove a shipped prohibition.",
    },
)


# ---------------------------------------------------------------------------
# Grading scale
# ---------------------------------------------------------------------------
#
# The 5.0-point scale used by Ugandan public universities, with normal
# progress at a grade point of 2.0 and above per NCHE guidance. An institution
# on a 4.0 scale replaces this row and its bands; nothing else changes,
# because every transcript is computed under the scale in force on its dates.

GRADE_BANDS: tuple[tuple[str, float, float, float, bool], ...] = (
    ("A", 80, 100, 5.0, True),
    ("B+", 75, 79.99, 4.5, True),
    ("B", 70, 74.99, 4.0, True),
    ("C+", 65, 69.99, 3.5, True),
    ("C", 60, 64.99, 3.0, True),
    ("D+", 55, 59.99, 2.5, True),
    ("D", 50, 54.99, 2.0, True),
    ("E", 45, 49.99, 1.5, False),
    ("E-", 40, 44.99, 1.0, False),
    ("F", 0, 39.99, 0.0, False),
)


def seed_tenant(*, slug: str, dsn: str, tenant_name: str) -> dict[str, int]:
    """Seed one tenant database. Safe to re-run."""
    # Resolves every cross-module relationship before the first query; see
    # `acmis.modules.registry`.
    _configure_mappers()
    counts = {"permissions": 0, "roles": 0, "grade_bands": 0, "settings": 0}
    with tenant_session_ctx(key=slug, dsn=dsn) as session:
        counts["permissions"] = _seed_permissions(session)
        counts["roles"] = _seed_roles(session)
        counts["grade_bands"] = _seed_grading_scale(session)
        _seed_calendar(session)
        _seed_campus(session, tenant_name=tenant_name)
        counts["settings"] = _seed_settings(session, tenant_name=tenant_name)
    log.info("tenant_seeded", tenant=slug, **counts)
    return counts


def _seed_permissions(session: Session) -> int:
    existing = {code for (code,) in session.execute(select(Permission.code)).all()}
    added = 0
    for entry in PERMISSIONS:
        if entry["code"] in existing:
            continue
        session.add(
            Permission(
                code=entry["code"],
                module=entry["module"],
                name=entry["name"],
                description=entry.get("description"),
                is_high_risk=bool(entry.get("high_risk", False)),
                conflicts_with=list(entry.get("conflicts_with", ())),
            )
        )
        added += 1
    session.flush()
    return added


def _seed_roles(session: Session) -> int:
    """Create the shipped roles, and reconcile the ones already there.

    Reconciling matters: a release that adds a permission to a shipped role
    reaches an existing tenant only if seeding *updates* it. Creating and then
    skipping — which is what this did — meant the library and quality-office
    permissions existed in the catalogue, the roles existed, and the roles
    granted nothing. Nobody could open either module, and the roles looked
    correct in every listing.

    Missing grants are added; extra ones are left alone. An institution that
    has widened a shipped role has made a decision, and a seeder that silently
    narrowed it again on the next deploy would take a permission away from
    somebody mid-semester.
    """
    existing = {role.code: role for role in session.execute(select(Role)).scalars()}
    added = 0
    reconciled = 0
    for entry in ROLES:
        role = existing.get(str(entry["code"]))
        if role is None:
            session.add(
                Role(
                    code=entry["code"],
                    name=entry["name"],
                    description=entry.get("description"),
                    permission_codes=list(entry["permissions"]),
                    is_system=True,
                    requires_scope=bool(entry.get("requires_scope", False)),
                    max_holders=entry.get("max_holders"),
                )
            )
            added += 1
            continue

        shipped = list(entry["permissions"])
        missing = [code for code in shipped if code not in role.permission_codes]
        if missing:
            role.permission_codes = [*role.permission_codes, *missing]
            reconciled += 1
            log.info(
                "role_permissions_reconciled",
                role=role.code,
                added=missing,
            )
        # The description is documentation and safe to refresh; the name is
        # not — an institution renames "Bursar" to "Director of Finance" and
        # that rename should stick.
        if entry.get("description") and role.description != entry.get("description"):
            role.description = str(entry["description"])
    session.flush()
    return added + reconciled


def _seed_grading_scale(session: Session) -> int:
    existing = session.execute(
        select(GradingScale).where(GradingScale.code == "UG-5.0")
    ).scalar_one_or_none()
    if existing is not None:
        return 0

    scale = GradingScale(
        code="UG-5.0",
        name="Undergraduate 5.0-point scale",
        max_grade_point=5.0,
        pass_mark=50,
        pass_grade_point=2.0,
        study_level="undergraduate",
        # Deliberately far back: a scale must cover the dates of every result
        # that will ever be computed under it, including historical records
        # loaded during a migration from a legacy system.
        effective_from=date(2000, 1, 1),
        is_current=True,
    )
    session.add(scale)
    session.flush()

    for grade, lower, upper, points, is_pass in GRADE_BANDS:
        session.add(
            GradeBand(
                scale_id=scale.id,
                grade=grade,
                lower_mark=lower,
                upper_mark=upper,
                grade_point=points,
                is_pass=is_pass,
                counts_in_gpa=True,
            )
        )
    session.flush()
    return len(GRADE_BANDS)


def _seed_calendar(session: Session) -> None:
    """One academic year with two semesters and a recess term.

    The window dates are the ones every module gates on, and they are set to a
    plausible East African shape — August start, registration closing three
    weeks in, examinations at the end. An institution edits them; what matters
    is that they exist, because a semester with null windows makes every
    registration rule unevaluable.
    """
    today = date.today()
    start_year = today.year if today.month >= 6 else today.year - 1
    code = f"{start_year}/{start_year + 1}"

    year = session.execute(
        select(AcademicYear).where(AcademicYear.code == code)
    ).scalar_one_or_none()
    if year is not None:
        return

    year = AcademicYear(
        code=code,
        name=f"Academic Year {code}",
        starts_on=date(start_year, 8, 1),
        ends_on=date(start_year + 1, 7, 31),
        is_current=True,
    )
    session.add(year)
    session.flush()

    semesters = (
        ("semester_1", "Semester I", 1, date(start_year, 8, 15), date(start_year, 12, 20)),
        ("semester_2", "Semester II", 2, date(start_year + 1, 1, 15), date(start_year + 1, 5, 30)),
        ("recess", "Recess Term", 3, date(start_year + 1, 6, 10), date(start_year + 1, 7, 25)),
    )
    for kind, name, sequence, starts, ends in semesters:
        session.add(
            Semester(
                academic_year_id=year.id,
                kind=kind,
                name=f"{name} {code}",
                sequence=sequence,
                starts_on=starts,
                ends_on=ends,
                enrolment_opens_on=starts,
                enrolment_closes_on=_offset(starts, 21),
                registration_opens_on=starts,
                registration_closes_on=_offset(starts, 21),
                add_drop_closes_on=_offset(starts, 28),
                withdrawal_deadline_on=_offset(starts, 56),
                teaching_starts_on=starts,
                teaching_ends_on=_offset(ends, -21),
                exams_start_on=_offset(ends, -14),
                exams_end_on=ends,
                results_due_on=_offset(ends, 21),
                is_current=(kind == "semester_1"),
            )
        )
    session.flush()


def _offset(value: date, days: int) -> date:
    from datetime import timedelta

    return value + timedelta(days=days)


def _seed_campus(session: Session, *, tenant_name: str) -> None:
    existing = session.execute(select(Campus).where(Campus.is_main.is_(True))).scalar_one_or_none()
    if existing is not None:
        return
    campus = Campus(code="MAIN", name=f"{tenant_name} Main Campus", is_main=True)
    session.add(campus)
    session.flush()

    root = session.execute(
        select(AcademicUnit).where(AcademicUnit.kind == UnitKind.UNIVERSITY)
    ).scalar_one_or_none()
    if root is None:
        session.add(
            AcademicUnit(
                code="UNIV",
                name=tenant_name,
                kind=UnitKind.UNIVERSITY,
                ancestor_ids=[],
                depth=0,
                campus_id=campus.id,
            )
        )
        session.flush()


def _seed_settings(session: Session, *, tenant_name: str) -> int:
    """Institution defaults. Every one of these is asked about in week one."""
    defaults: tuple[tuple[str, dict[str, Any], str], ...] = (
        (
            "student_number_template",
            {"value": "{yy:02d}/U/{serial:04d}/{code}"},
            "How student numbers are built. Changing it does not renumber existing "
            "students — a student number is quoted for life.",
        ),
        (
            "registration.threshold_percent",
            {"value": 60},
            "Percentage of the student's own share of semester fees required before "
            "course registration.",
        ),
        (
            "examination.threshold_percent",
            {"value": 100},
            "Percentage required before an examination card is issued.",
        ),
        (
            "appeals.window_days",
            {"value": 21},
            "Days after a results release within which a student may appeal.",
        ),
        (
            "data_request_days",
            {"value": 30},
            "Statutory deadline for a subject access or correction request.",
        ),
        (
            "clearance.offices",
            {"value": ["library", "finance", "hall", "department", "laboratory"]},
            "Offices that must sign off before a student graduates or withdraws.",
        ),
        (
            "require_support_approval",
            {"value": False},
            "When true, a platform support session inside this institution needs "
            "approval from the institution's own administrator.",
        ),
        (
            "transcript.footer",
            {"value": f"Issued by the Academic Registrar, {tenant_name}."},
            "Printed at the foot of every official transcript.",
        ),
    )
    added = 0
    for key, value, description in defaults:
        existing = session.execute(
            select(SystemSetting).where(
                SystemSetting.key == key, SystemSetting.scope_type == "institution"
            )
        ).scalar_one_or_none()
        if existing is not None:
            continue
        session.add(
            SystemSetting(
                key=key,
                scope_type="institution",
                value=value,
                description=description,
                updated_at=utcnow(),
            )
        )
        added += 1
    session.flush()
    return added


def seed_control_plane(control: Session) -> dict[str, int]:
    """Plans and the first platform administrator.

    The bootstrap administrator's password comes from
    `ACMIS_BOOTSTRAP_PASSWORD` and the account is created with
    `must change` semantics in mind — an installation whose first credential
    is a known default is an installation with no credential at all.
    """
    import os

    from acmis.core.security import hash_password
    from acmis.modules.tenancy.models import Plan, PlatformUser

    plans = (
        {
            "code": "essentials",
            "name": "Essentials",
            "description": "Admissions, student records and assessment. For a single-"
            "faculty institution getting off spreadsheets.",
            "included_modules": [
                "admissions",
                "students",
                "curriculum",
                "assessment",
                "learning",
            ],
            "price_per_student_minor": 350,
            "max_students": 3000,
            "support_tier": "standard",
        },
        {
            "code": "institution",
            "name": "Institution",
            "description": "Every academic and financial module, with the developer "
            "portal. The normal choice for a chartered university.",
            "included_modules": [
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
            "price_per_student_minor": 620,
            "max_students": 40000,
            "support_tier": "priority",
        },
        {
            "code": "national",
            "name": "National",
            "description": "Everything, plus statutory reporting for a regulator and "
            "a dedicated database cluster.",
            "included_modules": [
                "admissions",
                "students",
                "curriculum",
                "assessment",
                "learning",
                "finance",
                "people",
                "governance",
                "developers",
                "statutory",
            ],
            "price_per_student_minor": 890,
            "max_students": None,
            "support_tier": "dedicated",
        },
    )

    added = 0
    for entry in plans:
        existing = control.execute(
            select(Plan).where(Plan.code == entry["code"])
        ).scalar_one_or_none()
        if existing is None:
            control.add(Plan(currency="USD", **entry))
            added += 1

    users = 0
    email = os.environ.get("ACMIS_BOOTSTRAP_EMAIL", "platform@acmis.local")
    existing_user = control.execute(
        select(PlatformUser).where(PlatformUser.email == email)
    ).scalar_one_or_none()
    if existing_user is None:
        password = os.environ.get("ACMIS_BOOTSTRAP_PASSWORD")
        if not password:
            log.warning(
                "bootstrap_password_missing",
                message="Set ACMIS_BOOTSTRAP_PASSWORD to create the first platform "
                "administrator. Skipping.",
            )
        else:
            control.add(
                PlatformUser(
                    email=email,
                    full_name="Platform Administrator",
                    password_hash=hash_password(password),
                    status="active",
                    permissions=["platform:admin", "platform:support"],
                )
            )
            users += 1

    control.flush()
    return {"plans": added, "platform_users": users}
