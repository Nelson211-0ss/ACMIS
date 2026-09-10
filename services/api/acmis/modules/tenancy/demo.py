"""A fully-populated demonstration institution.

Not a test fixture. This builds a university you can sign into and walk end to
end: faculties, programmes with approved curricula, courses and offerings,
staff on real teaching allocations, students enrolled and registered, fee
structures and invoices, a question bank, an online test that has been sat and
marked, and a mark sheet part-way through the approval chain.

Two properties it holds deliberately:

**Idempotent.** Re-running adds nothing and destroys nothing. The demo tenant
is meant to persist across restarts and re-seeds, so anything already present
is left exactly as it is — including data somebody has since changed by hand.

**Internally consistent.** Every student is enrolled on a semester that exists,
registered for offerings that exist, invoiced against a published fee
structure, and their marks sit on a sheet whose examiner is someone other than
its approver. A demo that violates its own rules teaches the wrong thing about
the system, and half the value here is showing the separation of duties
actually biting.

Passwords are the same for every seeded account and are printed at the end.
They go through the same Argon2 path as any other password — this is seed data
for a walkable demo, not a credential, and a deployment seeds no accounts at
all.
"""

from __future__ import annotations

import random
import uuid
from datetime import date, timedelta
from decimal import Decimal
from typing import Any

import structlog
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from acmis.core.audit import AuditWriter, attach_writer, detach_writer
from acmis.core.context import (
    RequestContext,
    TenantContext,
    service_principal,
    use_context,
)
from acmis.core.db import tenant_session_ctx
from acmis.core.errors import Conflict, RuleViolation
from acmis.core.models import utcnow
from acmis.core.security import hash_password
from acmis.modules.admissions.models import (
    AdmissionScheme,
    Applicant,
    Application,
    ApplicationStatus,
    ProgrammeIntake,
    Qualification,
    QualificationSubject,
    SchemeStatus,
)
from acmis.modules.assessment.models import (
    CourseResult,
    MarkSheet,
    MarkSheetStatus,
)
from acmis.modules.curriculum.models import (
    ApprovalStatus,
    AssessmentComponent,
    AssessmentScheme,
    Course,
    CourseOffering,
    CurriculumCourse,
    CurriculumVersion,
    Prerequisite,
    Programme,
    TeachingAllocation,
    TimetableSlot,
)
from acmis.modules.finance import latepayment as latepayment_service
from acmis.modules.finance.models import (
    FeeItem,
    FeeStructure,
    LatePaymentRule,
    Payment,
    PaymentPlan,
)
from acmis.modules.identity.models import (
    AccountKind,
    AccountStatus,
    Role,
    RoleAssignment,
    UserAccount,
)
from acmis.modules.learning.models import (
    AssessmentItem,
    AssessmentStatus,
    Attempt,
    AttemptResponse,
    Behaviour,
    CourseSpace,
    Material,
    OnlineAssessment,
    Question,
    QuestionBank,
    QuestionKind,
    QuestionOption,
)
from acmis.modules.library import service as library_service
from acmis.modules.library.models import (
    AcquisitionRequest,
    CatalogueCopy,
    CatalogueRecord,
    CopyStatus,
    EResourceSubscription,
    Library,
    LibraryFine,
    LibraryMember,
    Loan,
    LoanPolicy,
    LoanStatus,
)
from acmis.modules.people.models import (
    Appointment,
    Staff,
    StaffCategory,
    StaffQualification,
)
from acmis.modules.quality import service as quality_service
from acmis.modules.quality.models import (
    CourseEvaluation,
    EvaluationInstrument,
    QualityAudit,
    QualityIndicator,
    TeachingObservation,
)
from acmis.modules.registry import configure as configure_mappers
from acmis.modules.shared.models import (
    AcademicUnit,
    AcademicYear,
    Building,
    CalendarEvent,
    Campus,
    Room,
    Semester,
    UnitKind,
)
from acmis.modules.students import lifecycle as lifecycle_service
from acmis.modules.students.models import (
    Enrolment,
    ExamCard,
    InstitutionTransfer,
    Registration,
    RegistrationCourse,
    SpecialExamRequest,
    StatusChange,
    Student,
    StudentIdCard,
    StudentProgramme,
    StudentStatus,
)

log = structlog.get_logger(__name__)

# Seed data for a walkable demonstration, not a credential. It goes through
# the same Argon2 path as any other password, and a real deployment seeds no
# accounts at all — see `seed_control_plane`, which refuses to invent one
# without `ACMIS_BOOTSTRAP_PASSWORD`.
DEMO_PASSWORD = "Kampala-Demo-2026!"  # noqa: S105

#: Deterministic, so two runs produce the same people and a screenshot taken
#: today still matches the data next week. `random` rather than `secrets` on
#: purpose: this is reproducible sample data, and reproducibility is the
#: requirement. Nothing generated here is a secret.
RANDOM = random.Random(20260909)  # noqa: S311

SURNAMES = [
    "Nakato",
    "Okello",
    "Mubiru",
    "Atim",
    "Kirabo",
    "Ssemakula",
    "Achieng",
    "Byaruhanga",
    "Nabirye",
    "Tumwine",
    "Aciro",
    "Kyagulanyi",
    "Namusoke",
    "Odongo",
    "Kabuye",
    "Amongin",
    "Wasswa",
    "Nalwoga",
    "Ochieng",
    "Birungi",
    "Mugisha",
    "Adong",
    "Katende",
    "Nampijja",
    "Owor",
    "Ssentongo",
    "Akello",
    "Lubega",
    "Nakimuli",
    "Opio",
]
GIVEN_NAMES = [
    "Sarah Grace",
    "Joseph",
    "Patience",
    "Emmanuel",
    "Rebecca",
    "Daniel",
    "Prossy",
    "Isaac",
    "Winnie",
    "Moses",
    "Esther",
    "Brian",
    "Immaculate",
    "Godfrey",
    "Faith",
    "Simon Peter",
    "Harriet",
    "Timothy",
    "Joan",
    "Aggrey",
    "Miriam",
    "Denis",
    "Sylvia",
    "Fred",
    "Doreen",
    "Charles",
    "Ruth",
    "Solomon",
    "Betty",
    "Alex",
]
DISTRICTS = [
    "Kampala",
    "Wakiso",
    "Gulu",
    "Mbarara",
    "Jinja",
    "Lira",
    "Arua",
    "Mbale",
    "Masaka",
    "Fort Portal",
    "Soroti",
    "Hoima",
]


def seed_demo(*, slug: str, dsn: str, tenant_name: str) -> dict[str, Any]:
    """Populate the demonstration institution. Safe to re-run.

    Runs under a named service principal with an audit writer attached, so
    every seeded change is recorded in the institution's own audit trail
    exactly as an interactive one would be. Two reasons: the governance module
    needs a populated trail to demonstrate anything, and an unattributed
    change is precisely what this system exists to prevent — a seeder that
    exempts itself is teaching the wrong lesson.
    """
    summary: dict[str, Any] = {}
    with tenant_session_ctx(key=slug, dsn=dsn) as session:
        context = RequestContext(
            request_id=uuid.uuid4(),
            principal=service_principal("demo-seeder"),
            tenant=TenantContext(
                id=uuid.uuid5(uuid.NAMESPACE_URL, f"acmis:tenant:{slug}"),
                slug=slug,
                name=tenant_name,
                database="",
                dsn=dsn,
            ),
            method="CLI",
            path="acmis.cli demo",
            module="seeder",
        )
        with use_context(context) as ctx:
            writer = AuditWriter(session, ctx)
            attach_writer(ctx, writer)
            try:
                summary = _build(session, tenant_name=tenant_name)
                writer.flush()
            finally:
                detach_writer(ctx)

    log.info("demo_seeded", tenant=slug, **summary)
    return summary


def _build(session: Session, *, tenant_name: str) -> dict[str, Any]:
    """The seed itself. Split out so the audit context wraps all of it."""
    if True:
        units = _units(session, tenant_name=tenant_name)
        year, semesters = _calendar(session)
        current = next(s for s in semesters if s.is_current)

        programmes = _programmes(session, units=units, year=year)
        courses = _courses(session, units=units)
        versions = _curricula(session, programmes=programmes, courses=courses, year=year)
        schemes = _assessment_schemes(session, courses=courses, versions=versions)
        offerings = _offerings(session, courses=courses, semester=current, schemes=schemes)

        staff = _staff(session, units=units)
        _allocate_teaching(session, offerings=offerings, staff=staff)

        fees = _fee_structures(session, programmes=programmes, year=year)
        students = _students(
            session,
            programmes=programmes,
            versions=versions,
            year=year,
            semester=current,
            units=units,
        )
        _register(session, students=students, offerings=offerings, semester=current)
        _invoice(session, students=students, semester=current, fees=fees)

        accounts = _accounts(session, staff=staff, students=students)

        spaces = _course_spaces(session, offerings=offerings, semester=current)
        bank = _question_bank(session, courses=courses, units=units)
        online = _online_test(
            session,
            spaces=spaces,
            bank=bank,
            schemes=schemes,
            offerings=offerings,
            staff=staff,
        )
        _sit_test(session, assessment=online, students=students)

        sheets = _mark_sheets(
            session, offerings=offerings, semester=current, students=students, staff=staff
        )

        applicants = _admissions(session, programmes=programmes, year=year, semester=current)

        # The additions: the calendar people read, the library, quality
        # assurance, the life-cycle queues and late payment.
        calendar_events = _calendar_events(session, year=year, semester=current)
        suspended = {
            row.starts_on
            for row in session.execute(
                select(CalendarEvent).where(
                    CalendarEvent.academic_year_id == year.id,
                    CalendarEvent.suspends_teaching.is_(True),
                )
            ).scalars()
        }
        library = _library(session, courses=courses, students=students, staff=staff)
        quality = _quality(
            session,
            offerings=offerings,
            semester=current,
            students=students,
            staff=staff,
            suspended=suspended,
        )
        events = _lifecycle(
            session,
            students=students,
            offerings=offerings,
            semester=current,
            staff=staff,
            programmes=programmes,
        )
        late = _late_payment(session, year=year, students=students)
        rooms = _timetable(session, offerings=offerings, semester=current, staff=staff)
        polls = _elections(session, students=students, staff=staff, year=year, units=units)
        # Last, deliberately: it fills in whatever the spread above left the
        # designated student short of.
        showcase = _showcase(
            session,
            students=students,
            offerings=offerings,
            semester=current,
            staff=staff,
        )

        return {
            "units": len(units),
            "programmes": len(programmes),
            "courses": len(courses),
            "offerings": len(offerings),
            "staff": len(staff),
            "students": len(students),
            "accounts": accounts,
            "course_spaces": len(spaces),
            "questions": bank.question_count,
            "online_assessment": online.title,
            "mark_sheets": len(sheets),
            "applicants": applicants,
            "calendar_events": calendar_events,
            **library,
            **quality,
            **events,
            **late,
            **rooms,
            **polls,
            **showcase,
        }


# ---------------------------------------------------------------------------
# Structure
# ---------------------------------------------------------------------------


def _units(session: Session, *, tenant_name: str) -> dict[str, AcademicUnit]:
    """A three-level tree: university, colleges, departments.

    Three levels because that is the shape most East African public
    universities have, and because it exercises the ancestry denormalisation
    that every unit-scoped policy depends on.
    """
    campus = session.execute(select(Campus).where(Campus.is_main.is_(True))).scalar_one()
    root = session.execute(
        select(AcademicUnit).where(AcademicUnit.kind == UnitKind.UNIVERSITY)
    ).scalar_one()

    wanted: list[tuple[str, str, str, str | None]] = [
        ("COCIS", "College of Computing and Information Sciences", UnitKind.COLLEGE, None),
        ("CEDAT", "College of Engineering, Design, Art and Technology", UnitKind.COLLEGE, None),
        ("CHS", "College of Health Sciences", UnitKind.COLLEGE, None),
        ("CS", "Department of Computer Science", UnitKind.DEPARTMENT, "COCIS"),
        ("IS", "Department of Information Systems", UnitKind.DEPARTMENT, "COCIS"),
        ("CIV", "Department of Civil Engineering", UnitKind.DEPARTMENT, "CEDAT"),
        ("NUR", "Department of Nursing", UnitKind.DEPARTMENT, "CHS"),
    ]

    units: dict[str, AcademicUnit] = {"UNIV": root}
    for code, name, kind, parent_code in wanted:
        existing = session.execute(
            select(AcademicUnit).where(AcademicUnit.code == code)
        ).scalar_one_or_none()
        if existing is not None:
            units[code] = existing
            continue
        parent = units[parent_code] if parent_code else root
        unit = AcademicUnit(
            code=code,
            name=name,
            kind=kind,
            parent_id=parent.id,
            ancestor_ids=[*(parent.ancestor_ids or []), parent.id],
            depth=parent.depth + 1,
            campus_id=campus.id,
            established_on=date(1970, 1, 1),
        )
        session.add(unit)
        session.flush()
        units[code] = unit
    return units


def _calendar(session: Session) -> tuple[AcademicYear, list[Semester]]:
    year = session.execute(
        select(AcademicYear).where(AcademicYear.is_current.is_(True))
    ).scalar_one()
    semesters = (
        session.execute(
            select(Semester).where(Semester.academic_year_id == year.id).order_by(Semester.sequence)
        )
        .scalars()
        .all()
    )
    return year, list(semesters)


def _programmes(
    session: Session, *, units: dict[str, AcademicUnit], year: AcademicYear
) -> dict[str, Programme]:
    wanted = [
        (
            "BSCS",
            "Bachelor of Science in Computer Science",
            "Bachelor of Science in Computer Science",
            "BSc (CS)",
            "bachelors",
            "CS",
            8,
        ),
        (
            "BIST",
            "Bachelor of Information Systems and Technology",
            "Bachelor of Information Systems and Technology",
            "BIST",
            "bachelors",
            "IS",
            8,
        ),
        (
            "BSCE",
            "Bachelor of Science in Civil Engineering",
            "Bachelor of Science in Civil Engineering",
            "BSc (Civ Eng)",
            "bachelors",
            "CIV",
            10,
        ),
        (
            "BNS",
            "Bachelor of Nursing Science",
            "Bachelor of Nursing Science",
            "BNS",
            "bachelors",
            "NUR",
            8,
        ),
        (
            "MSCS",
            "Master of Science in Computer Science",
            "Master of Science in Computer Science",
            "MSc (CS)",
            "masters",
            "CS",
            4,
        ),
    ]

    programmes: dict[str, Programme] = {}
    for code, name, award_title, abbrev, level, unit_code, duration in wanted:
        existing = session.execute(
            select(Programme).where(Programme.code == code)
        ).scalar_one_or_none()
        if existing is not None:
            programmes[code] = existing
            continue
        unit = units[unit_code]
        programme = Programme(
            code=code,
            name=name,
            award_title=award_title,
            award_abbreviation=abbrev,
            award_level=level,
            owning_unit_id=unit.id,
            faculty_ids=list(unit.ancestor_ids or []),
            department_ids=[unit.id],
            duration_semesters=duration,
            delivery_modes=["full_time", "evening"] if level == "bachelors" else ["part_time"],
            study_level="undergraduate" if level == "bachelors" else "postgraduate",
            status=ApprovalStatus.APPROVED,
            is_active=True,
            accreditation_number=f"NCHE/{code}/2023",
            # One programme deliberately expires soon, so the curriculum
            # dashboard's accreditation warning has something real to show.
            accredited_until=date(2027, 1, 31) if code == "BNS" else date(2030, 6, 30),
            nqf_level=7 if level == "bachelors" else 9,
            description=f"{name}, offered by the {unit.name}.",
            entry_requirements="Two principal passes at A level, or an equivalent diploma.",
        )
        session.add(programme)
        session.flush()
        programmes[code] = programme
    return programmes


def _courses(session: Session, *, units: dict[str, AcademicUnit]) -> dict[str, Course]:
    wanted = [
        ("CSC1100", "Computer Literacy", "CS", 3, 30, 15, 0, 1),
        ("CSC1101", "Structured Programming", "CS", 4, 45, 15, 30, 1),
        ("CSC1200", "Discrete Mathematics", "CS", 3, 45, 15, 0, 1),
        ("CSC2100", "Data Structures and Algorithms", "CS", 4, 45, 15, 30, 2),
        ("CSC2200", "Database Systems", "CS", 4, 45, 15, 30, 2),
        ("CSC3100", "Operating Systems", "CS", 4, 45, 15, 30, 3),
        ("IST1101", "Foundations of Information Systems", "IS", 3, 45, 0, 0, 1),
        ("IST2201", "Systems Analysis and Design", "IS", 4, 45, 15, 15, 2),
        ("CIV1101", "Engineering Drawing", "CIV", 3, 15, 0, 90, 1),
        ("NUR1101", "Anatomy and Physiology", "NUR", 4, 45, 15, 30, 1),
    ]

    courses: dict[str, Course] = {}
    for code, title, unit_code, credits, lectures, tutorials, practicals, level in wanted:
        existing = session.execute(select(Course).where(Course.code == code)).scalar_one_or_none()
        if existing is not None:
            courses[code] = existing
            continue
        unit = units[unit_code]
        course = Course(
            code=code,
            title=title,
            owning_unit_id=unit.id,
            department_ids=[unit.id],
            faculty_ids=list(unit.ancestor_ids or []),
            credit_units=credits,
            lecture_hours=lectures,
            tutorial_hours=tutorials,
            practical_hours=practicals,
            level=level,
            description=f"{title}.",
            learning_outcomes=[
                f"Explain the core principles of {title.lower()}.",
                f"Apply {title.lower()} to a practical problem.",
            ],
            assessment_mode="written_exam",
            counts_toward_gpa=True,
            status=ApprovalStatus.APPROVED,
            is_active=True,
        )
        session.add(course)
        session.flush()
        courses[code] = course

    # One real prerequisite chain, so the registration check has something to
    # enforce rather than passing vacuously.
    _prerequisite(session, courses["CSC2100"], courses["CSC1101"])
    _prerequisite(session, courses["CSC3100"], courses["CSC2100"])
    return courses


def _prerequisite(session: Session, course: Course, required: Course) -> None:
    existing = session.execute(
        select(Prerequisite).where(
            Prerequisite.course_id == course.id,
            Prerequisite.required_course_id == required.id,
        )
    ).scalar_one_or_none()
    if existing is None:
        session.add(
            Prerequisite(
                course_id=course.id,
                required_course_id=required.id,
                kind="prerequisite",
                minimum_grade="D",
                is_waivable=True,
            )
        )
        session.flush()


def _curricula(
    session: Session,
    *,
    programmes: dict[str, Programme],
    courses: dict[str, Course],
    year: AcademicYear,
) -> dict[str, CurriculumVersion]:
    """An approved curriculum version per programme, with its course structure.

    Approved, because a student cannot be attached to anything else — see
    `admissions.service.enrol`, which refuses a programme with no approved
    version rather than guessing.
    """
    structure = {
        "BSCS": [
            ("CSC1100", 1, "semester_1", "core"),
            ("CSC1101", 1, "semester_1", "core"),
            ("CSC1200", 1, "semester_2", "core"),
            ("CSC2100", 2, "semester_1", "core"),
            ("CSC2200", 2, "semester_2", "core"),
            ("CSC3100", 3, "semester_1", "core"),
        ],
        "BIST": [
            ("IST1101", 1, "semester_1", "core"),
            ("CSC1100", 1, "semester_1", "university_required"),
            ("CSC1101", 1, "semester_2", "core"),
            ("IST2201", 2, "semester_1", "core"),
            ("CSC2200", 2, "semester_2", "core"),
        ],
        "BSCE": [("CIV1101", 1, "semester_1", "core")],
        "BNS": [("NUR1101", 1, "semester_1", "core")],
        "MSCS": [("CSC2200", 1, "semester_1", "core")],
    }

    versions: dict[str, CurriculumVersion] = {}
    for code, programme in programmes.items():
        existing = session.execute(
            select(CurriculumVersion).where(
                CurriculumVersion.programme_id == programme.id,
                CurriculumVersion.version_label == "2024",
            )
        ).scalar_one_or_none()
        if existing is not None:
            versions[code] = existing
            continue

        version = CurriculumVersion(
            programme_id=programme.id,
            version_label="2024",
            cohort_from="2024/2025",
            min_credits_per_semester=15,
            max_credits_per_semester=24,
            max_credits_with_retakes=27,
            # The NCHE-derived defaults, written out explicitly so the demo
            # shows what a version actually carries rather than relying on the
            # code's fallbacks.
            progression_rules={
                "pass_grade_point": 2.0,
                "probation_cgpa": 2.0,
                "discontinue_after_probations": 2,
                "max_retakes_per_course": 3,
                "retake_counts": "best",
                "carry_forward_failures": True,
                "repeat_year_if_failed_credits_over": 12,
                "minimum_credits_for_progression": 15,
            },
            classification_rules={
                "bands": [
                    {"class": "First Class Honours", "min_cgpa": 4.40},
                    {"class": "Second Class Honours (Upper Division)", "min_cgpa": 3.60},
                    {"class": "Second Class Honours (Lower Division)", "min_cgpa": 2.80},
                    {"class": "Pass", "min_cgpa": 2.00},
                ],
                "requires_no_outstanding_retakes": True,
            },
            learning_outcomes=[
                "Design and implement software to a professional standard.",
                "Reason about the correctness and efficiency of an algorithm.",
            ],
            status=ApprovalStatus.APPROVED,
            submitted_at=utcnow() - timedelta(days=400),
            recommended_at=utcnow() - timedelta(days=380),
            approved_at=utcnow() - timedelta(days=365),
            senate_minute_reference="SEN/2024/07/14",
        )
        session.add(version)
        session.flush()

        total = 0
        for course_code, study_year, semester_kind, category in structure.get(code, []):
            course = courses[course_code]
            session.add(
                CurriculumCourse(
                    version_id=version.id,
                    course_id=course.id,
                    year_of_study=study_year,
                    semester_kind=semester_kind,
                    category=category,
                    is_required_for_progression=category != "elective",
                )
            )
            total += course.credit_units
        version.total_credit_units = total
        session.flush()
        versions[code] = version
    return versions


def _assessment_schemes(
    session: Session,
    *,
    courses: dict[str, Course],
    versions: dict[str, CurriculumVersion],
) -> dict[str, AssessmentScheme]:
    """A 40/60 coursework-to-examination split, which is the regional norm.

    Components rather than one mark, because a disputed total is checked
    against its parts — "does 34 coursework and 61 exam really make 52" is the
    commonest examinations query and unanswerable if only the total is stored.
    """
    schemes: dict[str, AssessmentScheme] = {}
    for code, course in courses.items():
        existing = session.execute(
            select(AssessmentScheme).where(AssessmentScheme.course_id == course.id)
        ).scalar_one_or_none()
        if existing is not None:
            schemes[code] = existing
            continue

        scheme = AssessmentScheme(
            course_id=course.id,
            pass_mark=50,
            # Nursing requires the examination to be passed on its own, which
            # is true of clinical programmes and gives the rule something real
            # to do in the demo.
            exam_must_be_passed=code.startswith("NUR"),
            minimum_exam_mark=40 if code.startswith("NUR") else None,
            status=ApprovalStatus.APPROVED,
        )
        session.add(scheme)
        session.flush()

        components = [
            ("CW1", "Coursework assignment", "coursework", 15, 100),
            ("TEST", "Mid-semester test", "test", 25, 100),
            ("EXAM", "Final examination", "final_exam", 60, 100),
        ]
        for index, (comp_code, name, kind, weight, maximum) in enumerate(components, start=1):
            session.add(
                AssessmentComponent(
                    scheme_id=scheme.id,
                    code=comp_code,
                    name=name,
                    kind=kind,
                    weight_percent=weight,
                    max_mark=maximum,
                    sequence=index,
                )
            )
        session.flush()
        schemes[code] = scheme
    return schemes


def _offerings(
    session: Session,
    *,
    courses: dict[str, Course],
    semester: Semester,
    schemes: dict[str, AssessmentScheme],
) -> dict[str, CourseOffering]:
    offerings: dict[str, CourseOffering] = {}
    for code, course in courses.items():
        existing = session.execute(
            select(CourseOffering).where(
                CourseOffering.course_id == course.id,
                CourseOffering.semester_id == semester.id,
            )
        ).scalar_one_or_none()
        if existing is not None:
            offerings[code] = existing
            continue
        offering = CourseOffering(
            course_id=course.id,
            semester_id=semester.id,
            delivery_mode="full_time",
            assessment_scheme_id=schemes[code].id,
            department_ids=list(course.department_ids or []),
            faculty_ids=list(course.faculty_ids or []),
            capacity=200,
            is_open=True,
        )
        session.add(offering)
        session.flush()
        offerings[code] = offering
    return offerings


# ---------------------------------------------------------------------------
# People
# ---------------------------------------------------------------------------


def _staff(session: Session, *, units: dict[str, AcademicUnit]) -> dict[str, Staff]:
    """Staff covering every role the demo needs to exercise.

    Deliberately includes distinct people for examiner, moderator, board chair
    and Senate secretary, because the separation-of-duties rules refuse the
    same person twice — a demo with one super-user shows none of that.
    """
    wanted = [
        (
            "STF/001",
            "Prof.",
            "Okello",
            "Joseph",
            "CS",
            StaffCategory.ACADEMIC,
            "Professor",
            True,
            "Distributed systems",
        ),
        (
            "STF/002",
            "Dr.",
            "Nakato",
            "Sarah Grace",
            "CS",
            StaffCategory.ACADEMIC,
            "Senior Lecturer",
            True,
            "Algorithms",
        ),
        (
            "STF/003",
            "Mr.",
            "Mubiru",
            "Emmanuel",
            "CS",
            StaffCategory.ACADEMIC,
            "Lecturer",
            False,
            "Programming languages",
        ),
        (
            "STF/004",
            "Dr.",
            "Atim",
            "Patience",
            "IS",
            StaffCategory.ACADEMIC,
            "Senior Lecturer",
            True,
            "Information systems",
        ),
        (
            "STF/005",
            "Dr.",
            "Byaruhanga",
            "Daniel",
            "CIV",
            StaffCategory.ACADEMIC,
            "Lecturer",
            True,
            "Structural engineering",
        ),
        (
            "STF/006",
            "Ms.",
            "Achieng",
            "Rebecca",
            "NUR",
            StaffCategory.ACADEMIC,
            "Assistant Lecturer",
            False,
            "Adult nursing",
        ),
        (
            "STF/007",
            "Mr.",
            "Ssemakula",
            "Moses",
            "UNIV",
            StaffCategory.ADMINISTRATIVE,
            "Academic Registrar",
            False,
            None,
        ),
        (
            "STF/008",
            "Mrs.",
            "Kirabo",
            "Winnie",
            "UNIV",
            StaffCategory.ADMINISTRATIVE,
            "Deputy Registrar (Records)",
            False,
            None,
        ),
        (
            "STF/009",
            "Mr.",
            "Tumwine",
            "Isaac",
            "UNIV",
            StaffCategory.ADMINISTRATIVE,
            "Bursar",
            False,
            None,
        ),
        (
            "STF/010",
            "Ms.",
            "Nabirye",
            "Esther",
            "UNIV",
            StaffCategory.ADMINISTRATIVE,
            "Accountant",
            False,
            None,
        ),
        (
            "STF/011",
            "Mr.",
            "Odongo",
            "Godfrey",
            "UNIV",
            StaffCategory.ADMINISTRATIVE,
            "Head of Admissions",
            False,
            None,
        ),
        (
            "STF/012",
            "Ms.",
            "Amongin",
            "Faith",
            "UNIV",
            StaffCategory.ADMINISTRATIVE,
            "Admissions Officer",
            False,
            None,
        ),
        (
            "STF/013",
            "Dr.",
            "Kabuye",
            "Simon Peter",
            "UNIV",
            StaffCategory.ADMINISTRATIVE,
            "Secretary to Senate",
            False,
            None,
        ),
        (
            "STF/014",
            "Mr.",
            "Wasswa",
            "Timothy",
            "UNIV",
            StaffCategory.ADMINISTRATIVE,
            "Internal Auditor",
            False,
            None,
        ),
        (
            "STF/015",
            "Ms.",
            "Nalwoga",
            "Joan",
            "UNIV",
            StaffCategory.ADMINISTRATIVE,
            "Systems Administrator",
            False,
            None,
        ),
        (
            "STF/016",
            "Mr.",
            "Ochieng",
            "Aggrey",
            "UNIV",
            StaffCategory.ADMINISTRATIVE,
            "Examinations Officer",
            False,
            None,
        ),
        (
            "STF/017",
            "Dr.",
            "Birungi",
            "Miriam",
            "COCIS",
            StaffCategory.ACADEMIC,
            "Associate Professor",
            True,
            "Human-computer interaction",
        ),
        (
            "STF/018",
            "Ms.",
            "Mugisha",
            "Sylvia",
            "UNIV",
            StaffCategory.ADMINISTRATIVE,
            "Human Resources Officer",
            False,
            None,
        ),
        # The library, split three ways because the permissions are: the
        # librarian who may waive a fine, the cataloguer who orders stock, and
        # the assistant who works the desk and can do neither.
        (
            "STF/019",
            "Mr.",
            "Kiggundu",
            "Patrick",
            "UNIV",
            StaffCategory.ADMINISTRATIVE,
            "University Librarian",
            False,
            None,
        ),
        (
            "STF/020",
            "Ms.",
            "Namatovu",
            "Grace",
            "UNIV",
            StaffCategory.ADMINISTRATIVE,
            "Librarian",
            False,
            None,
        ),
        (
            "STF/021",
            "Mr.",
            "Opio",
            "Denis",
            "UNIV",
            StaffCategory.SUPPORT,
            "Library Assistant",
            False,
            None,
        ),
        # The quality office. Holds no academic authority over the teaching it
        # reviews, which is the point of it being a separate office.
        (
            "STF/022",
            "Dr.",
            "Akello",
            "Christine",
            "UNIV",
            StaffCategory.ADMINISTRATIVE,
            "Quality Assurance Officer",
            False,
            None,
        ),
    ]

    staff: dict[str, Staff] = {}
    for (
        number,
        title,
        surname,
        given,
        unit_code,
        category,
        rank,
        doctorate,
        specialisation,
    ) in wanted:
        existing = session.execute(
            select(Staff).where(Staff.staff_number == number)
        ).scalar_one_or_none()
        if existing is not None:
            staff[number] = existing
            continue
        unit = units[unit_code]
        person = Staff(
            staff_number=number,
            title=title,
            surname=surname,
            given_names=given,
            display_title=f"{title} {given[0]}. {surname}" + (", PhD" if doctorate else ""),
            date_of_birth=date(1975 + (int(number[-2:]) % 15), 3, 12),
            sex="female" if title in {"Ms.", "Mrs."} else "male",
            nationality="Ugandan",
            email=f"{given.split()[0].lower()}.{surname.lower()}@demo.acmis.local",
            phone=f"+2567{int(number[-3:]):08d}",
            category=category,
            rank=rank,
            salary_scale="M5" if category == StaffCategory.ACADEMIC else "M6",
            highest_qualification="PhD" if doctorate else "MSc",
            has_doctorate=doctorate,
            specialisation=specialisation,
            primary_unit_id=unit.id,
            faculty_ids=list(unit.ancestor_ids or []),
            department_ids=[unit.id],
            status="active",
            first_appointed_on=date(2015, 8, 1),
            # One contract expiring soon, so the HR dashboard's warning is real.
            contract_ends_on=date(2026, 11, 30) if number == "STF/003" else None,
        )
        session.add(person)
        session.flush()

        session.add(
            Appointment(
                staff_id=person.id,
                unit_id=unit.id,
                title=rank or "Officer",
                rank=rank,
                kind="permanent",
                fte=Decimal("1.0"),
                is_primary=True,
                administrative_office=(rank if category == StaffCategory.ADMINISTRATIVE else None),
                starts_on=date(2015, 8, 1),
                salary_scale="M5" if category == StaffCategory.ACADEMIC else "M6",
                gross_salary_minor=4_500_000_00,
                status="active",
                approved_at=utcnow() - timedelta(days=3000),
            )
        )
        if doctorate:
            session.add(
                StaffQualification(
                    staff_id=person.id,
                    level="doctorate",
                    title="Doctor of Philosophy",
                    discipline=specialisation or "Computing",
                    institution_name="Makerere University",
                    country_code="UG",
                    year_awarded=2012,
                    verified_at=utcnow() - timedelta(days=2000),
                )
            )
        session.flush()
        staff[number] = person
    return staff


def _allocate_teaching(
    session: Session,
    *,
    offerings: dict[str, CourseOffering],
    staff: dict[str, Staff],
) -> None:
    """Who teaches what.

    This is what grants mark entry — `assessment.mark-entry` compares the
    offering against the examiner's allocations and nothing else. An
    unallocated offering has nobody who can enter its marks, deliberately.
    """
    plan = {
        "CSC1100": ("STF/003", "lecturer"),
        "CSC1101": ("STF/003", "coordinator"),
        "CSC1200": ("STF/002", "lecturer"),
        "CSC2100": ("STF/002", "coordinator"),
        "CSC2200": ("STF/001", "coordinator"),
        "CSC3100": ("STF/001", "lecturer"),
        "IST1101": ("STF/004", "coordinator"),
        "IST2201": ("STF/004", "lecturer"),
        "CIV1101": ("STF/005", "coordinator"),
        "NUR1101": ("STF/006", "coordinator"),
    }
    for code, (staff_number, role) in plan.items():
        offering = offerings[code]
        person = staff[staff_number]
        existing = session.execute(
            select(TeachingAllocation).where(
                TeachingAllocation.offering_id == offering.id,
                TeachingAllocation.staff_id == person.id,
                TeachingAllocation.role == role,
            )
        ).scalar_one_or_none()
        if existing is not None:
            continue
        session.add(
            TeachingAllocation(
                offering_id=offering.id,
                staff_id=person.id,
                role=role,
                contact_hours=Decimal("45"),
                load_share_percent=Decimal("100"),
                can_enter_marks=True,
                starts_on=date.today() - timedelta(days=60),
            )
        )
    session.flush()


def _students(
    session: Session,
    *,
    programmes: dict[str, Programme],
    versions: dict[str, CurriculumVersion],
    year: AcademicYear,
    semester: Semester,
    units: dict[str, AcademicUnit],
) -> list[Student]:
    """Sixty students across the programmes, in a realistic spread of standing.

    Includes students on probation and on approved leave, because a
    population that is uniformly healthy exercises none of the progression or
    blocking rules.
    """
    existing = session.execute(select(Student)).scalars().all()
    if len(existing) >= 60:
        return list(existing)

    students: list[Student] = list(existing)
    spread = [("BSCS", 24), ("BIST", 16), ("BSCE", 10), ("BNS", 8), ("MSCS", 2)]
    serial = len(existing)

    for programme_code, count in spread:
        programme = programmes[programme_code]
        version = versions[programme_code]
        for _ in range(count):
            serial += 1
            surname = SURNAMES[serial % len(SURNAMES)]
            given = GIVEN_NAMES[(serial * 7) % len(GIVEN_NAMES)]
            entry_year = 2024 if serial % 3 else 2025
            number = f"{entry_year % 100:02d}/U/{serial:04d}/{programme_code[:3]}"

            if session.execute(
                select(Student).where(Student.student_number == number)
            ).scalar_one_or_none():
                continue

            # A realistic distribution: most active, a few on probation, one
            # or two on leave. Deterministic, so the numbers on a dashboard
            # are stable between runs.
            standing = (
                StudentStatus.PROBATION
                if serial % 11 == 0
                else StudentStatus.ON_LEAVE
                if serial % 29 == 0
                else StudentStatus.ACTIVE
            )
            cgpa = (
                Decimal("1.80")
                if standing == StudentStatus.PROBATION
                else Decimal(str(round(RANDOM.uniform(2.4, 4.7), 2)))
            )

            student = Student(
                student_number=number,
                surname=surname,
                given_names=given,
                certificate_name=f"{given} {surname}",
                date_of_birth=date(entry_year - 19, ((serial % 12) + 1), ((serial % 27) + 1)),
                sex="female" if serial % 2 == 0 else "male",
                nationality="Ugandan",
                district_of_origin=DISTRICTS[serial % len(DISTRICTS)],
                email=f"{given.split()[0].lower()}.{surname.lower()}{serial}@students.demo.acmis.local",
                phone=f"+2567{serial:08d}",
                national_id=f"CM{entry_year}{serial:07d}UG",
                next_of_kin_name=f"{SURNAMES[(serial * 3) % len(SURNAMES)]} family",
                next_of_kin_phone=f"+2567{serial + 1000:08d}",
                # A couple of students carry an examination accommodation, so
                # the extra-time path in the attempt runner is exercised.
                exam_accommodations="25% extra time" if serial % 17 == 0 else None,
                status=standing,
                admitted_on=date(entry_year, 8, 20),
                faculty_ids=list(programme.faculty_ids or []),
                department_ids=list(programme.department_ids or []),
                programme_ids=[programme.id],
                # One student with a library hold, so the blocking rules and
                # the hold banner have something real to show.
                holds=(
                    [
                        {
                            "kind": "library",
                            "reason": "Two overdue volumes from the main library.",
                            "placed_at": (utcnow() - timedelta(days=9)).isoformat(),
                            "cleared_at": None,
                        }
                    ]
                    if serial % 23 == 0
                    else []
                ),
            )
            session.add(student)
            session.flush()

            study_year = 2 if entry_year == 2024 else 1
            attachment = StudentProgramme(
                student_id=student.id,
                programme_id=programme.id,
                curriculum_version_id=version.id,
                entry_academic_year_id=year.id,
                entry_route="direct",
                sponsorship="government" if serial % 4 == 0 else "private",
                sponsor_name="Government of Uganda" if serial % 4 == 0 else None,
                current_year_of_study=study_year,
                current_semester_number=(study_year - 1) * 2 + 1,
                cgpa=cgpa,
                credits_earned=(study_year - 1) * 34,
                credits_required=version.total_credit_units,
                outstanding_retakes=1 if standing == StudentStatus.PROBATION else 0,
                progression_status=(
                    "probation" if standing == StudentStatus.PROBATION else "normal"
                ),
                computed_at=utcnow() - timedelta(days=30),
                is_primary=True,
                started_on=date(entry_year, 8, 20),
                expected_completion_on=date(entry_year + programme.duration_semesters // 2, 7, 31),
                maximum_completion_on=date(entry_year + 7, 7, 31),
            )
            session.add(attachment)
            session.flush()

            if standing != StudentStatus.ON_LEAVE:
                session.add(
                    Enrolment(
                        student_id=student.id,
                        student_programme_id=attachment.id,
                        semester_id=semester.id,
                        year_of_study=study_year,
                        semester_number=attachment.current_semester_number,
                        enrolment_type="normal",
                        status="enrolled",
                        enrolled_at=utcnow() - timedelta(days=40),
                    )
                )
                session.flush()

            students.append(student)
    return students


def _accounts(session: Session, *, staff: dict[str, Staff], students: list[Student]) -> int:
    """Sign-in accounts, with the roles their office actually holds.

    The role map is where the demo earns its keep: the examiner, the
    moderator, the board chair and the Senate secretary are four different
    people, so the separation-of-duties rules refuse the wrong one and the
    approve button genuinely disappears.
    """
    roles = {role.code: role for role in session.execute(select(Role)).scalars()}

    staff_roles: dict[str, list[tuple[str, str | None]]] = {
        "STF/001": [("head_of_department", "CS")],
        "STF/002": [("lecturer", None), ("examinations_officer", None)],
        "STF/003": [("lecturer", None)],
        "STF/004": [("head_of_department", "IS")],
        "STF/005": [("lecturer", None)],
        "STF/006": [("lecturer", None)],
        "STF/007": [("academic_registrar", None)],
        "STF/008": [("deputy_registrar_records", None)],
        "STF/009": [("bursar", None)],
        "STF/010": [("accountant", None)],
        "STF/011": [("head_of_admissions", None)],
        "STF/012": [("admissions_officer", None)],
        "STF/013": [("senate_secretary", None)],
        "STF/014": [("internal_auditor", None)],
        "STF/015": [("system_administrator", None), ("developer", None)],
        "STF/016": [("examinations_officer", None)],
        "STF/017": [("faculty_dean", "COCIS")],
        "STF/018": [("human_resources_officer", None)],
        "STF/019": [("university_librarian", None)],
        "STF/020": [("librarian", None)],
        "STF/021": [("library_assistant", None)],
        "STF/022": [("quality_assurance_officer", None)],
    }

    units = {unit.code: unit for unit in session.execute(select(AcademicUnit)).scalars()}
    created = 0
    password_hash = hash_password(DEMO_PASSWORD)

    for number, person in staff.items():
        existing = session.execute(
            select(UserAccount).where(UserAccount.username == number)
        ).scalar_one_or_none()
        if existing is not None:
            continue
        account = UserAccount(
            username=number,
            email=person.email,
            email_verified_at=utcnow(),
            phone=person.phone,
            kind=AccountKind.STAFF,
            status=AccountStatus.ACTIVE,
            display_name=person.display_title or f"{person.given_names} {person.surname}",
            password_hash=password_hash,
            password_changed_at=utcnow(),
            staff_id=person.id,
        )
        session.add(account)
        session.flush()
        created += 1

        for role_code, scope_code in staff_roles.get(number, []):
            role = roles.get(role_code)
            if role is None:
                continue
            scope_unit = units.get(scope_code) if scope_code else None
            session.add(
                RoleAssignment(
                    account_id=account.id,
                    role_id=role.id,
                    scope_type=(
                        "department"
                        if scope_unit and scope_unit.kind == UnitKind.DEPARTMENT
                        else "faculty"
                        if scope_unit
                        else None
                    ),
                    scope_id=scope_unit.id if scope_unit else None,
                    starts_on=date(2024, 1, 1),
                    # Requested and approved by different people, which is what
                    # `identity.separation-of-duties` requires.
                    requested_by_id=account.id if False else uuid.uuid4(),
                    approved_by_id=uuid.uuid4(),
                    approved_at=utcnow(),
                    reason="Seeded for the demonstration institution.",
                )
            )
        session.flush()

    student_role = roles.get("lecturer")  # placeholder; students hold no role
    for student in students:
        existing = session.execute(
            select(UserAccount).where(UserAccount.username == student.student_number)
        ).scalar_one_or_none()
        if existing is not None:
            continue
        session.add(
            UserAccount(
                username=student.student_number,
                email=student.email,
                email_verified_at=utcnow(),
                phone=student.phone,
                kind=AccountKind.STUDENT,
                status=AccountStatus.ACTIVE,
                display_name=f"{student.given_names} {student.surname}",
                password_hash=password_hash,
                password_changed_at=utcnow(),
                student_id=student.id,
            )
        )
        created += 1
    session.flush()
    _ = student_role
    return created


# ---------------------------------------------------------------------------
# Registration, fees, and teaching
# ---------------------------------------------------------------------------


def _register(
    session: Session,
    *,
    students: list[Student],
    offerings: dict[str, CourseOffering],
    semester: Semester,
) -> None:
    """Register each enrolled student for their curriculum's courses.

    Registered against the *curriculum version* they are attached to, not
    against a general catalogue — which is the whole point of versioning, and
    means a 2024-cohort student and a 2025-cohort student on the same
    programme can legitimately have different course lists.
    """
    for student in students:
        enrolment = session.execute(
            select(Enrolment).where(
                Enrolment.student_id == student.id,
                Enrolment.semester_id == semester.id,
            )
        ).scalar_one_or_none()
        if enrolment is None:
            continue

        existing = session.execute(
            select(Registration).where(Registration.enrolment_id == enrolment.id)
        ).scalar_one_or_none()
        if existing is not None:
            continue

        attachment = session.get(StudentProgramme, enrolment.student_programme_id)
        if attachment is None:
            continue
        structure = (
            session.execute(
                select(CurriculumCourse).where(
                    CurriculumCourse.version_id == attachment.curriculum_version_id,
                    CurriculumCourse.year_of_study == enrolment.year_of_study,
                    CurriculumCourse.semester_kind == semester.kind,
                )
            )
            .scalars()
            .all()
        )
        if not structure:
            # Fall back to year one, so a student in a year the demo has not
            # laid out still has something to register rather than an empty
            # basket that looks like a bug.
            structure = (
                session.execute(
                    select(CurriculumCourse).where(
                        CurriculumCourse.version_id == attachment.curriculum_version_id,
                        CurriculumCourse.year_of_study == 1,
                    )
                )
                .scalars()
                .all()
            )

        by_course = {offering.course_id: offering for offering in offerings.values()}
        registration = Registration(
            student_id=student.id,
            enrolment_id=enrolment.id,
            semester_id=semester.id,
            status="approved",
            submitted_at=utcnow() - timedelta(days=35),
            approved_at=utcnow() - timedelta(days=34),
            exam_card_issued_at=utcnow() - timedelta(days=20),
        )
        session.add(registration)
        session.flush()

        total = 0
        for entry in structure:
            offering = by_course.get(entry.course_id)
            if offering is None:
                continue
            course = session.get(Course, entry.course_id)
            credits = entry.credit_units_override or (course.credit_units if course else 3)
            session.add(
                RegistrationCourse(
                    registration_id=registration.id,
                    course_offering_id=offering.id,
                    student_id=student.id,
                    credit_units=credits,
                    category=entry.category,
                    is_retake=False,
                    attempt_number=1,
                )
            )
            offering.registered_count += 1
            total += credits
        registration.total_credits = total
        session.flush()


def _fee_structures(
    session: Session, *, programmes: dict[str, Programme], year: AcademicYear
) -> dict[str, FeeStructure]:
    """A published fee schedule per programme, with a sponsored variant.

    Two structures for the same programme — private and government — because
    the sponsor split is where fee logic actually gets interesting: a
    government-sponsored student's own balance must show only what *they* owe,
    or the registration block punishes them for the ministry's lateness.
    """
    structures: dict[str, FeeStructure] = {}
    for code, programme in programmes.items():
        for sponsorship, tuition in (("private", 1_500_000_00), ("government", 0)):
            key = f"{code}-{sponsorship}"
            existing = session.execute(
                select(FeeStructure).where(
                    FeeStructure.code == key,
                    FeeStructure.academic_year_id == year.id,
                )
            ).scalar_one_or_none()
            if existing is not None:
                structures[key] = existing
                continue

            structure = FeeStructure(
                code=key,
                name=f"{programme.code} — {sponsorship} sponsorship, {year.code}",
                academic_year_id=year.id,
                programme_id=programme.id,
                cohort_year_id=year.id,
                sponsorship=sponsorship,
                currency="UGX",
                status="published",
                approved_at=utcnow() - timedelta(days=200),
                published_at=utcnow() - timedelta(days=190),
                registration_threshold_percent=60,
                exam_threshold_percent=100,
            )
            session.add(structure)
            session.flush()

            items = [
                ("TUITION", "Tuition", "tuition", tuition, "per_semester", "student"),
                ("FUNC", "Functional fees", "functional", 180_000_00, "per_semester", "student"),
                ("EXAM", "Examination fee", "examination", 60_000_00, "per_semester", "student"),
                ("GUILD", "Guild fee", "guild", 20_000_00, "per_year", "student"),
                ("ID", "Identity card", "identity_card", 15_000_00, "once", "student"),
            ]
            for item_code, name, category, amount, basis, payable_by in items:
                session.add(
                    FeeItem(
                        structure_id=structure.id,
                        code=item_code,
                        name=name,
                        category=category,
                        amount_minor=amount,
                        basis=basis,
                        is_mandatory=True,
                        # Government sponsorship covers tuition and nothing
                        # else, which is the arrangement in practice and the
                        # source of most student fee complaints.
                        payable_by="sponsor"
                        if sponsorship == "government" and category == "tuition"
                        else payable_by,
                        gl_account_code="4000-tuition-income"
                        if category == "tuition"
                        else "4100-other-fee-income",
                    )
                )
            session.flush()
            structures[key] = structure
    return structures


def _invoice(
    session: Session,
    *,
    students: list[Student],
    semester: Semester,
    fees: dict[str, FeeStructure],
) -> None:
    """Invoice every registered student, and receipt part of it.

    Goes through `finance.service` rather than writing rows directly, so the
    ledger entries, the sponsor split and the balance cache are all produced
    by the same code the application uses. A demo that inserts invoices by
    hand shows a ledger that the real code would never have written.
    """
    from acmis.modules.finance import service as finance

    actor = uuid.uuid5(uuid.NAMESPACE_URL, "acmis:demo:seeder")

    for index, student in enumerate(students):
        attachment = session.execute(
            select(StudentProgramme).where(
                StudentProgramme.student_id == student.id,
                StudentProgramme.is_primary.is_(True),
            )
        ).scalar_one_or_none()
        if attachment is None:
            continue

        invoice = finance.raise_semester_invoice(
            session,
            student=student,
            student_programme=attachment,
            semester_id=semester.id,
            actor_id=actor,
        )

        # A spread of payment behaviour: most have paid enough to register,
        # some have cleared, a few have paid nothing. Anything else makes the
        # fee-threshold rules untestable.
        share = [Decimal("1.0"), Decimal("0.7"), Decimal("0.0"), Decimal("0.45")][index % 4]
        student_due = invoice.total_minor - invoice.sponsor_portion_minor
        amount = int(student_due * share)
        if amount <= 0:
            continue

        # Idempotent on the provider reference, which is the natural key for a
        # receipt. Without this a re-run posted every student's fees again:
        # `total_paid_minor` climbed on each seed until it overflowed the
        # column, which is how the 32-bit money columns were found.
        reference = f"DEMO-{student.student_number}-{semester.id.hex[:6]}"
        already = (
            session.execute(
                select(Payment).where(
                    Payment.provider_reference == reference, Payment.deleted_at.is_(None)
                )
            )
            .scalars()
            .first()
        )
        if already is not None:
            continue

        finance.record_payment(
            session,
            student_id=student.id,
            applicant_id=None,
            amount_minor=amount,
            currency=invoice.currency,
            method="mobile_money" if index % 2 else "bank_deposit",
            provider="mgurush" if index % 2 else None,
            provider_reference=reference,
            payer_narrative=f"{student.student_number} fees",
            payer_name=f"{student.given_names} {student.surname}",
            value_date=date.today() - timedelta(days=25 - (index % 20)),
            actor_id=actor,
        )

    # One unmatched deposit, so the bursary's queue is not empty and the
    # unapplied-receipts path has something in it.
    if not session.execute(select(Payment).where(Payment.status == "unmatched")).scalars().first():
        finance.record_payment(
            session,
            student_id=None,
            applicant_id=None,
            amount_minor=450_000_00,
            currency="UGX",
            method="bank_deposit",
            provider=None,
            provider_reference="DEMO-UNMATCHED-001",
            payer_narrative="school fees 24U1234PS",
            payer_name="Nakato S",
            value_date=date.today() - timedelta(days=3),
            actor_id=actor,
        )


# ---------------------------------------------------------------------------
# Teaching, learning and online assessment
# ---------------------------------------------------------------------------


def _course_spaces(
    session: Session, *, offerings: dict[str, CourseOffering], semester: Semester
) -> dict[str, CourseSpace]:
    """A published space per offering, with a few weeks of material."""
    spaces: dict[str, CourseSpace] = {}
    for code, offering in offerings.items():
        existing = session.execute(
            select(CourseSpace).where(CourseSpace.course_offering_id == offering.id)
        ).scalar_one_or_none()
        if existing is not None:
            spaces[code] = existing
            continue

        space = CourseSpace(
            course_offering_id=offering.id,
            semester_id=semester.id,
            department_ids=list(offering.department_ids or []),
            faculty_ids=list(offering.faculty_ids or []),
            welcome_message=(
                "Notes are posted after each lecture. Practice quizzes do not "
                "count toward your final mark; the mid-semester test does."
            ),
            syllabus_outline=[
                {"week": week, "topic": f"Week {week} topic", "reading": "Chapter " + str(week)}
                for week in range(1, 13)
            ],
            is_published=True,
            published_at=utcnow() - timedelta(days=50),
        )
        session.add(space)
        session.flush()

        for week in range(1, 7):
            session.add(
                Material(
                    space_id=space.id,
                    kind="notes" if week % 2 else "slides",
                    title=f"Week {week}: lecture notes",
                    description=f"Notes and worked examples for week {week}.",
                    week_number=week,
                    sequence=1,
                    is_published=True,
                    available_from=utcnow() - timedelta(days=50 - week * 7),
                    allow_download=True,
                )
            )
        # Two scheduled items, so the availability window is visible in the UI
        # rather than being a claim in a comment.
        for week in (8, 9):
            session.add(
                Material(
                    space_id=space.id,
                    kind="notes",
                    title=f"Week {week}: lecture notes",
                    description="Scheduled — becomes visible in week " + str(week),
                    week_number=week,
                    sequence=1,
                    is_published=True,
                    available_from=utcnow() + timedelta(days=(week - 6) * 7),
                    allow_download=True,
                )
            )
        session.add(
            Material(
                space_id=space.id,
                kind="past_paper",
                title="Past examination paper, 2024/2025",
                description="View only.",
                sequence=99,
                is_published=True,
                allow_download=False,
            )
        )
        session.flush()
        spaces[code] = space
    return spaces


def _question_bank(
    session: Session, *, courses: dict[str, Course], units: dict[str, AcademicUnit]
) -> QuestionBank:
    """A departmental question bank covering every auto-marked kind.

    Every kind, so the marker is exercised end to end rather than on multiple
    choice alone — the partial-credit, tolerance and ordering paths are where
    marking bugs hide.
    """
    existing = session.execute(
        select(QuestionBank).where(QuestionBank.code == "CSC1101-BANK")
    ).scalar_one_or_none()
    if existing is not None:
        return existing

    unit = units["CS"]
    bank = QuestionBank(
        code="CSC1101-BANK",
        name="Structured Programming — question bank",
        description=(
            "Departmental property rather than one lecturer's: the commonest way "
            "an institution loses years of assessment material is a lecturer "
            "leaving with it on a laptop."
        ),
        course_id=courses["CSC1101"].id,
        owning_unit_id=unit.id,
        department_ids=[unit.id],
        faculty_ids=list(unit.ancestor_ids or []),
        is_shared=True,
    )
    session.add(bank)
    session.flush()

    def add(
        kind: str,
        stem: str,
        marks: float,
        *,
        options: list[tuple[str, str, bool]] | None = None,
        answer_key: dict[str, Any] | None = None,
        variables: list[dict[str, Any]] | None = None,
        topic: str = "Fundamentals",
        level: str = "understand",
        explanation: str | None = None,
        rubric: list[dict[str, Any]] | None = None,
    ) -> None:
        question = Question(
            bank_id=bank.id,
            kind=kind,
            stem=stem,
            marks=Decimal(str(marks)),
            answer_key=answer_key or {},
            variable_sets=variables or [],
            explanation=explanation,
            rubric=rubric or [],
            topic=topic,
            cognitive_level=level,
            difficulty="medium",
            learning_outcome="Reason about program behaviour.",
        )
        session.add(question)
        session.flush()
        for index, (label, body, correct) in enumerate(options or []):
            session.add(
                QuestionOption(
                    question_id=question.id,
                    label=label,
                    body=body,
                    is_correct=correct,
                    sequence=index,
                    feedback=None if correct else "Consider what the loop does on its last pass.",
                )
            )
        session.flush()

    add(
        QuestionKind.MULTIPLE_CHOICE,
        "What is the time complexity of appending one element to a dynamic array, amortised?",
        2,
        options=[
            ("A", "O(1)", True),
            ("B", "O(log n)", False),
            ("C", "O(n)", False),
            ("D", "O(n log n)", False),
        ],
        topic="Complexity",
        level="understand",
        explanation="Doubling the capacity spreads the copy cost across the appends.",
    )
    add(
        QuestionKind.TRUE_FALSE,
        "In C, an array name used in an expression decays to a pointer to its first element.",
        1,
        options=[("A", "True", True), ("B", "False", False)],
        topic="Pointers",
        level="remember",
    )
    add(
        QuestionKind.MULTIPLE_RESPONSE,
        "Which of these are call-by-value languages by default? Select all that apply.",
        3,
        options=[
            ("A", "C", True),
            ("B", "Java (for primitives)", True),
            ("C", "Fortran 77", False),
            ("D", "Pascal (var parameters)", False),
        ],
        answer_key={"all_or_nothing": False},
        topic="Semantics",
        level="analyse",
    )
    add(
        QuestionKind.SHORT_ANSWER,
        "Name the data structure that gives last-in, first-out access.",
        2,
        answer_key={
            "accepted": ["stack", "a stack", "the stack"],
            "ignore_case": True,
            "max_edit_distance": 1,
        },
        topic="Data structures",
        level="remember",
    )
    add(
        QuestionKind.NUMERIC,
        "How many comparisons does a binary search need, at worst, over 1000 sorted items?",
        2,
        answer_key={"value": 10, "tolerance": 0},
        topic="Complexity",
        level="apply",
        explanation="ceil(log2(1000)) = 10.",
    )
    add(
        QuestionKind.CALCULATED,
        "An array holds {n} elements. How many comparisons does a linear search need at worst?",
        2,
        answer_key={"formula": "context.n", "tolerance": 0},
        variables=[{"n": 64}, {"n": 128}, {"n": 250}, {"n": 512}],
        topic="Complexity",
        level="apply",
    )
    add(
        QuestionKind.ORDERING,
        "Put these complexity classes in increasing order of growth.",
        4,
        options=[
            ("A", "O(1)", False),
            ("B", "O(log n)", False),
            ("C", "O(n)", False),
            ("D", "O(n^2)", False),
        ],
        answer_key={"order": ["A", "B", "C", "D"]},
        topic="Complexity",
        level="understand",
    )
    add(
        QuestionKind.ESSAY,
        "Explain why a recursive function needs a base case, and what happens without one.",
        8,
        rubric=[
            {"criterion": "Identifies unbounded recursion", "marks": 3},
            {"criterion": "Explains stack exhaustion", "marks": 3},
            {"criterion": "Uses a correct example", "marks": 2},
        ],
        topic="Recursion",
        level="evaluate",
    )

    bank.question_count = int(
        session.execute(
            select(func_count()).select_from(Question).where(Question.bank_id == bank.id)
        ).scalar_one()
    )
    session.flush()
    return bank


def func_count() -> Any:
    """`func.count()`, imported lazily to keep the module's import list short."""
    from sqlalchemy import func

    return func.count()


def _online_test(
    session: Session,
    *,
    spaces: dict[str, CourseSpace],
    bank: QuestionBank,
    schemes: dict[str, AssessmentScheme],
    offerings: dict[str, CourseOffering],
    staff: dict[str, Staff],
) -> OnlineAssessment:
    """A mid-semester test that has been authored, reviewed and opened.

    Reviewed by someone other than its author, because that is the rule and
    because a demo where the author reviewed their own paper would show the
    check not working.

    Mixes fixed and pooled items so every candidate gets a different but
    equivalent paper — the thing that makes a leaked question set worth much
    less.
    """
    existing = session.execute(
        select(OnlineAssessment).where(OnlineAssessment.title == "CSC1101 mid-semester test")
    ).scalar_one_or_none()
    if existing is not None:
        return existing

    space = spaces["CSC1101"]
    scheme = schemes["CSC1101"]
    component = session.execute(
        select(AssessmentComponent).where(
            AssessmentComponent.scheme_id == scheme.id,
            AssessmentComponent.code == "TEST",
        )
    ).scalar_one()

    author = staff["STF/003"]
    reviewer = staff["STF/002"]

    assessment = OnlineAssessment(
        space_id=space.id,
        course_offering_id=space.course_offering_id,
        kind="test",
        title="CSC1101 mid-semester test",
        instructions=(
            "Answer every question. Your answers save as you give them, so a "
            "dropped connection will not lose your work. The clock runs on the "
            "server."
        ),
        assessment_component_id=component.id,
        pass_mark_percent=50,
        opens_at=utcnow() - timedelta(days=5),
        closes_at=utcnow() + timedelta(days=9),
        duration_minutes=45,
        max_attempts=1,
        attempt_grading="best",
        behaviour=Behaviour.DEFERRED_FEEDBACK,
        tries_per_question=1,
        shuffle_questions=True,
        shuffle_options=True,
        allow_backtracking=True,
        score_visibility="on_release",
        show_correct_answers=False,
        status=AssessmentStatus.OPEN,
        authored_by_id=author.id,
        reviewed_by_id=reviewer.id,
        reviewed_at=utcnow() - timedelta(days=6),
        review_comments="Answer keys checked. Question 3 reworded for clarity.",
        department_ids=list(space.department_ids or []),
        faculty_ids=list(space.faculty_ids or []),
    )
    session.add(assessment)
    session.flush()

    questions = (
        session.execute(
            select(Question).where(Question.bank_id == bank.id).order_by(Question.created_at)
        )
        .scalars()
        .all()
    )

    total = Decimal(0)
    # Four fixed items, then a pooled draw — so the paper exercises both modes
    # and the frozen-per-candidate record has something to freeze.
    # The first four objective questions are fixed; the pooled draw below
    # takes from the rest, so the pool and the fixed selection do not overlap.
    for index, question in enumerate(questions[:4], start=1):
        session.add(
            AssessmentItem(
                assessment_id=assessment.id,
                sequence=index,
                section="Section A: objective",
                mode="fixed",
                question_id=question.id,
                is_mandatory=True,
            )
        )
        total += Decimal(str(question.marks))

    session.add(
        AssessmentItem(
            assessment_id=assessment.id,
            sequence=5,
            section="Section B: applied",
            mode="pooled",
            bank_id=bank.id,
            draw_count=2,
            # No topic filter: the fixed items above already took the
            # complexity questions, and a pool that overlaps them would draw
            # from a set of one.
            draw_filters={},
            marks_override=Decimal("2"),
            is_mandatory=True,
        )
    )
    total += Decimal("4")

    assessment.total_marks = float(total)
    session.flush()
    return assessment


def _sit_test(session: Session, *, assessment: OnlineAssessment, students: list[Student]) -> None:
    """Have some students sit the test, and mark what can be marked.

    Goes through `learning.service` so the drawn paper, the saved answers and
    the auto-marking are all produced by the real code paths — including the
    essay left for a human, which is what puts a marking queue on the
    lecturer's dashboard.
    """
    from acmis.modules.learning import service as learning

    already = (
        session.execute(select(Attempt).where(Attempt.assessment_id == assessment.id))
        .scalars()
        .first()
    )
    if already is not None:
        return

    # The students registered for this offering, which is what the API checks.
    registered = (
        session.execute(
            select(RegistrationCourse.student_id).where(
                RegistrationCourse.course_offering_id == assessment.course_offering_id
            )
        )
        .scalars()
        .all()
    )
    candidates = [s for s in students if s.id in set(registered)][:12]

    for index, student in enumerate(candidates):
        attempt = learning.start_attempt(
            session,
            assessment=assessment,
            student_id=student.id,
            password=None,
            ip_address="10.10.0.5",
            user_agent="ACMIS demo seeder",
        )

        # Answer with a deliberate spread of ability, so the distribution and
        # the item statistics are meaningful rather than uniform.
        ability = [0.9, 0.75, 0.6, 0.45, 0.3][index % 5]
        for response in session.execute(
            select(AttemptResponse).where(AttemptResponse.attempt_id == attempt.id)
        ).scalars():
            question = session.get(Question, response.question_id)
            if question is None:
                continue
            correct = RANDOM.random() < ability
            answer = _answer_for(question, response, correct=correct)
            if answer is not None:
                learning.save_response(
                    session,
                    attempt=attempt,
                    question_id=question.id,
                    answer=answer,
                    seconds_spent=RANDOM.randint(20, 180),
                )

        # Two candidates are left in progress, so the portal's "resume" path
        # and the invigilator's live view both have something to show.
        if index < len(candidates) - 2:
            learning.submit_attempt(session, attempt=attempt, actor_id=student.id, auto_mark=True)


def _answer_for(
    question: Question, response: AttemptResponse, *, correct: bool
) -> dict[str, Any] | None:
    """Produce a plausible answer for one question, right or wrong."""
    options = list(question.options)
    right = [o.label for o in options if o.is_correct]
    wrong = [o.label for o in options if not o.is_correct]

    if question.kind in {QuestionKind.MULTIPLE_CHOICE, QuestionKind.TRUE_FALSE}:
        if correct and right:
            return {"option_labels": [right[0]]}
        return {"option_labels": [wrong[0]]} if wrong else None

    if question.kind == QuestionKind.MULTIPLE_RESPONSE:
        if correct and right:
            return {"option_labels": right}
        # A partially-correct answer, which is what exercises partial credit.
        return {"option_labels": [*right[:1], *wrong[:1]]} if right or wrong else None

    if question.kind == QuestionKind.SHORT_ANSWER:
        accepted = question.answer_key.get("accepted") or []
        return {"text": accepted[0] if correct and accepted else "queue"}

    if question.kind == QuestionKind.NUMERIC:
        expected = question.answer_key.get("value")
        if expected is None:
            return None
        return {"value": expected if correct else float(expected) + 3}

    if question.kind == QuestionKind.CALCULATED:
        variables = response.variables or {}
        n = variables.get("n")
        if n is None:
            return None
        return {"value": n if correct else int(n) // 2}

    if question.kind == QuestionKind.ORDERING:
        order = list(question.answer_key.get("order") or [])
        if not order:
            return None
        if correct:
            return {"order": order}
        swapped = order[:]
        if len(swapped) >= 2:
            swapped[0], swapped[1] = swapped[1], swapped[0]
        return {"order": swapped}

    if question.kind == QuestionKind.ESSAY:
        # Left for a human marker, which is the point: it puts a real marking
        # queue on the lecturer's dashboard.
        return {
            "text": (
                "A base case terminates the recursion. Without one the function "
                "calls itself indefinitely and the call stack is exhausted, "
                "raising a stack overflow."
            )
        }

    return None


# ---------------------------------------------------------------------------
# Mark sheets and admissions
# ---------------------------------------------------------------------------


#: The approval chain in order, with the status each transition leaves behind.
#: Used to work out what an existing sheet still owes, so a re-seed converges
#: on the target stage instead of freezing wherever the first run stopped.
_SHEET_CHAIN: tuple[tuple[str, str], ...] = (
    ("submit", "submitted"),
    ("moderate", "moderated"),
    ("approve", "board_approved"),
    ("faculty_approve", "faculty_approved"),
    ("senate_approve", "senate_approved"),
)


def _advance_sheet(
    session: Session,
    *,
    sheet: MarkSheet,
    transitions: list[str],
    actors: dict[str, uuid.UUID],
) -> None:
    """Walk an existing sheet forward to its intended stage. Never backward."""
    from acmis.modules.assessment import service as assessment_service

    statuses = [status for _, status in _SHEET_CHAIN]
    current = str(sheet.status)
    if current not in ("draft", *statuses):
        # `returned` or `published`: both are states a re-seed must not touch.
        return
    reached = -1 if current == "draft" else statuses.index(current)
    for index in range(reached + 1, len(transitions)):
        action = _SHEET_CHAIN[index][0]
        try:
            assessment_service.transition_sheet(
                session,
                sheet=sheet,
                action=action,
                actor_id=actors[action],
                note="Moderated; no scaling required." if action == "moderate" else None,
                minute_reference="SEN/2026/09/03" if action == "senate_approve" else None,
            )
        except (RuleViolation, Conflict) as exc:
            # A sheet with an unmarked candidate cannot be submitted. That is
            # the rule working, so it is left where it is.
            log.debug("demo_sheet_not_advanced", sheet=str(sheet.id), error=str(exc))
            return


def _mark_sheets(
    session: Session,
    *,
    offerings: dict[str, CourseOffering],
    semester: Semester,
    students: list[Student],
    staff: dict[str, Staff],
) -> list[MarkSheet]:
    """Mark sheets at several stages of the approval chain.

    Spread across the chain on purpose. One sheet in draft with marks
    outstanding, one submitted, one moderated, one Senate-approved and
    published — so the assessment dashboard shows a real pipeline and the
    separation-of-duties rules can be seen refusing the wrong approver on the
    ones that are still moving.
    """
    from acmis.modules.assessment import service as assessment_service

    stages: dict[str, list[str]] = {
        "CSC1101": [],  # draft, marks part-entered
        "CSC2100": ["submit", "moderate"],  # awaiting the board
        "IST1101": ["submit", "moderate", "approve"],  # awaiting the faculty
        # Two sheets carried all the way through, on two different
        # programmes. One was not enough: with only the Nursing sheet
        # released, no computing student had a visible result, so the portal's
        # results page was empty for 50 of the 60 seeded students and looked
        # broken rather than pending.
        "CSC1100": [
            "submit",
            "moderate",
            "approve",
            "faculty_approve",
            "senate_approve",
        ],
        "NUR1101": [
            "submit",
            "moderate",
            "approve",
            "faculty_approve",
            "senate_approve",
        ],
    }

    examiner = {
        "CSC1101": staff["STF/003"],
        "CSC1100": staff["STF/003"],
        "CSC2100": staff["STF/002"],
        "IST1101": staff["STF/004"],
        "NUR1101": staff["STF/006"],
    }
    # Deliberately different people at each level, which is what the rules
    # require and what a single-super-user demo would hide.
    moderator = staff["STF/016"]
    board_chair = staff["STF/001"]
    dean = staff["STF/017"]
    senate = staff["STF/013"]

    sheets: list[MarkSheet] = []
    for code, transitions in stages.items():
        offering = offerings.get(code)
        examiner_for_code = examiner.get(code)
        if offering is None or examiner_for_code is None:
            # A course removed from the list above should not break the seed.
            log.debug("demo_mark_sheet_skipped", course=code)
            continue

        existing = session.execute(
            select(MarkSheet).where(MarkSheet.course_offering_id == offering.id)
        ).scalar_one_or_none()
        if existing is not None:
            # Idempotent, but converging rather than merely skipping: when the
            # target stage above moves — as it did when a second sheet was
            # carried to Senate so computing students had a visible result —
            # an existing sheet is walked the rest of the way rather than left
            # where an earlier run happened to stop.
            _advance_sheet(
                session,
                sheet=existing,
                transitions=transitions,
                actors={
                    "submit": examiner_for_code.id,
                    "moderate": moderator.id,
                    "approve": board_chair.id,
                    "faculty_approve": dean.id,
                    "senate_approve": senate.id,
                },
            )
            sheets.append(existing)
            continue

        sheet = assessment_service.generate_mark_sheet(
            session, course_offering_id=offering.id, actor_id=examiner_for_code.id
        )
        sheet.due_on = semester.results_due_on or (date.today() + timedelta(days=21))

        results = (
            session.execute(select(CourseResult).where(CourseResult.mark_sheet_id == sheet.id))
            .scalars()
            .all()
        )
        if not results:
            sheets.append(sheet)
            continue

        # A sheet still in draft keeps two candidates unmarked, so the
        # "cannot submit while anyone is unmarked" rule has something to
        # refuse in the demo.
        leave_unmarked = 2 if not transitions else 0
        entries: list[dict[str, Any]] = []
        for index, result in enumerate(results):
            if index < leave_unmarked:
                continue
            if index % 19 == 0:
                entries.append({"student_id": result.student_id, "exception": "absent"})
                continue
            ability = RANDOM.uniform(0.35, 0.95)
            entries.append(
                {
                    "student_id": result.student_id,
                    "components": {
                        "CW1": round(100 * min(1.0, ability + RANDOM.uniform(-0.1, 0.1)), 1),
                        "TEST": round(100 * min(1.0, ability + RANDOM.uniform(-0.15, 0.1)), 1),
                        "EXAM": round(100 * min(1.0, ability + RANDOM.uniform(-0.2, 0.05)), 1),
                    },
                }
            )

        assessment_service.enter_marks(
            session, sheet=sheet, entries=entries, actor_id=examiner_for_code.id
        )

        actor_for = {
            "submit": examiner_for_code.id,
            "moderate": moderator.id,
            "approve": board_chair.id,
            "faculty_approve": dean.id,
            "senate_approve": senate.id,
        }
        for action in transitions:
            assessment_service.transition_sheet(
                session,
                sheet=sheet,
                action=action,
                actor_id=actor_for[action],
                note="Moderated; no scaling required." if action == "moderate" else None,
                minute_reference="SEN/2026/09/03" if action == "senate_approve" else None,
            )

        sheets.append(sheet)

    # Release the Senate-approved sheet, so students have visible results and
    # the portal's results page is not empty.
    approved = [s for s in sheets if s.status == MarkSheetStatus.SENATE_APPROVED]
    if approved:
        assessment_service.release_results(
            session,
            semester_id=semester.id,
            programme_ids=None,
            scope_description="Semester I 2026/2027: Computer Literacy and Anatomy and Physiology",
            minute_reference="SEN/2026/09/03",
            actor_id=senate.id,
        )

    # Compute progression for the students whose results are now released, so
    # CGPA and standing on the dashboards are real rather than seeded numbers.
    for student in students[:20]:
        attachment = session.execute(
            select(StudentProgramme).where(
                StudentProgramme.student_id == student.id,
                StudentProgramme.is_primary.is_(True),
            )
        ).scalar_one_or_none()
        if attachment is None:
            continue
        try:
            assessment_service.compute_semester_result(
                session,
                student_programme=attachment,
                semester_id=semester.id,
                actor_id=senate.id,
            )
        except Exception as exc:  # a student with no results yet is fine
            log.debug("demo_progression_skipped", student=student.student_number, error=str(exc))

    return sheets


def _admissions(
    session: Session,
    *,
    programmes: dict[str, Programme],
    year: AcademicYear,
    semester: Semester,
) -> int:
    """An open admission scheme with applications at every stage.

    Applications with real qualifications attached, so the eligibility check
    has something to decide and the selection list has something to rank. A
    scheme with no applications shows none of the module.
    """
    scheme = session.execute(
        select(AdmissionScheme).where(AdmissionScheme.code == "UG-2027")
    ).scalar_one_or_none()

    if scheme is None:
        scheme = AdmissionScheme(
            code="UG-2027",
            name="Undergraduate intake 2027/2028",
            description=(
                "Direct entry for holders of the Uganda Advanced Certificate of Education."
            ),
            academic_year_id=year.id,
            entry_semester_id=semester.id,
            entry_scheme="private",
            study_level="undergraduate",
            opens_at=utcnow() - timedelta(days=30),
            closes_at=utcnow() + timedelta(days=45),
            late_closes_at=utcnow() + timedelta(days=60),
            results_due_on=date.today() + timedelta(days=90),
            acceptance_deadline_on=date.today() + timedelta(days=120),
            application_fee_minor=50_000_00,
            late_fee_minor=25_000_00,
            currency="UGX",
            requires_fee_before_review=True,
            max_programme_choices=6,
            # Weights as data, copied onto each application when it is scored —
            # so a score stays explainable after the weights change.
            scoring_weights={"aggregate": 0.7, "interview": 0.3},
            requires_interview=False,
            status=SchemeStatus.OPEN,
            published_at=utcnow() - timedelta(days=30),
        )
        session.add(scheme)
        session.flush()

    intakes: dict[str, ProgrammeIntake] = {}
    for code, seats, minimum in (("BSCS", 120, 14.0), ("BIST", 90, 12.0), ("BNS", 40, 15.0)):
        programme = programmes[code]
        existing = session.execute(
            select(ProgrammeIntake).where(
                ProgrammeIntake.scheme_id == scheme.id,
                ProgrammeIntake.programme_id == programme.id,
            )
        ).scalar_one_or_none()
        if existing is not None:
            intakes[code] = existing
            continue
        intake = ProgrammeIntake(
            scheme_id=scheme.id,
            programme_id=programme.id,
            approved_intake=seats,
            minimum_aggregate=Decimal(str(minimum)),
            previous_cutoff=Decimal(str(minimum + 2)),
            tuition_per_semester_minor=1_500_000_00,
            required_subjects={"subjects": {"MAT": 2.0, "PHY": 1.0}}
            if code != "BNS"
            else {"subjects": {"BIO": 2.0, "CHE": 1.0}},
        )
        session.add(intake)
        session.flush()
        intakes[code] = intake

    if (
        session.execute(select(Application).where(Application.scheme_id == scheme.id))
        .scalars()
        .first()
    ):
        return int(session.execute(select(func_count()).select_from(Applicant)).scalar_one())

    from acmis.modules.admissions import service as admissions_service

    actor = uuid.uuid5(uuid.NAMESPACE_URL, "acmis:demo:seeder")
    statuses = [
        ApplicationStatus.SUBMITTED,
        ApplicationStatus.AWAITING_FEE,
        ApplicationStatus.UNDER_REVIEW,
        ApplicationStatus.UNDER_REVIEW,
        ApplicationStatus.ADMITTED,
        ApplicationStatus.WAITLISTED,
        ApplicationStatus.REJECTED,
    ]

    for index in range(28):
        surname = SURNAMES[(index * 5) % len(SURNAMES)]
        given = GIVEN_NAMES[(index * 11) % len(GIVEN_NAMES)]
        reference = f"APL/2027/{index + 1:04d}"

        applicant = Applicant(
            reference=reference,
            surname=surname,
            given_names=given,
            date_of_birth=date(2007, ((index % 12) + 1), ((index % 27) + 1)),
            sex="female" if index % 2 else "male",
            nationality="Ugandan",
            district_of_origin=DISTRICTS[index % len(DISTRICTS)],
            email=f"{given.split()[0].lower()}.{surname.lower()}{index}@applicants.demo.local",
            phone=f"+2567{index + 500000:08d}",
            national_id=f"CF2007{index:07d}UG",
            guardian_name=f"{surname} guardian",
            guardian_phone=f"+2567{index + 600000:08d}",
        )
        session.add(applicant)
        session.flush()

        # A UACE result set, which is what the eligibility rules read.
        aggregate = round(RANDOM.uniform(9.0, 20.0), 1)
        qualification = Qualification(
            applicant_id=applicant.id,
            kind="uace",
            awarding_body="Uganda National Examinations Board",
            institution_name=f"{DISTRICTS[index % len(DISTRICTS)]} Secondary School",
            index_number=f"U0{index:04d}/500",
            year_completed=2026,
            aggregate=Decimal(str(aggregate)),
        )
        session.add(qualification)
        session.flush()
        for subject, points in (("MAT", 3.0), ("PHY", 2.0), ("BIO", 2.0), ("CHE", 2.0)):
            session.add(
                QualificationSubject(
                    qualification_id=qualification.id,
                    subject_code=subject,
                    subject_name=subject.title(),
                    level="principal",
                    grade="B",
                    points=Decimal(str(points)),
                )
            )
        session.flush()

        choice_codes = ["BSCS", "BIST"] if index % 3 else ["BNS", "BSCS"]
        application = admissions_service.start_application(
            session,
            applicant_id=applicant.id,
            scheme_id=scheme.id,
            programme_intake_ids=[intakes[c].id for c in choice_codes if c in intakes],
            actor_id=actor,
        )

        target = statuses[index % len(statuses)]
        try:
            admissions_service.submit_application(session, application=application, actor_id=actor)
        except Exception as exc:
            # An applicant who meets no requirement is legitimately refused —
            # that is the eligibility rule working, not a seeding failure — so
            # the run continues with the next applicant.
            log.debug("demo_application_refused", reference=reference, error=str(exc))
            continue

        if target in {
            ApplicationStatus.UNDER_REVIEW,
            ApplicationStatus.ADMITTED,
            ApplicationStatus.WAITLISTED,
            ApplicationStatus.REJECTED,
        }:
            application.fee_settled_at = utcnow() - timedelta(days=10)
            admissions_service.score_application(
                session,
                application=application,
                interview_score=None,
                entrance_exam_score=None,
                actor_id=actor,
            )
            if target != ApplicationStatus.UNDER_REVIEW:
                application.status = target
                application.decided_at = utcnow() - timedelta(days=2)
                application.decision_reason = {
                    ApplicationStatus.ADMITTED: "Admitted on merit.",
                    ApplicationStatus.WAITLISTED: "Placed on the waiting list.",
                    ApplicationStatus.REJECTED: "Not competitive for the seats available.",
                }[target]
        session.flush()

    return int(session.execute(select(func_count()).select_from(Applicant)).scalar_one())


# ---------------------------------------------------------------------------
# The academic calendar people read
# ---------------------------------------------------------------------------


def _calendar_events(session: Session, *, year: AcademicYear, semester: Semester) -> int:
    """The dates a student or a lecturer actually looks up.

    Includes two public holidays inside the teaching window, because that is
    what makes the class-session generator worth having: without them a
    semester's registers include days the campus was shut and every course
    looks two weeks behind.
    """
    wanted: list[dict[str, Any]] = [
        {
            "kind": "orientation",
            "title": "Freshers' orientation week",
            "starts_on": semester.starts_on,
            "ends_on": semester.starts_on + timedelta(days=4),
            "audience": "students",
            "location": "Main Hall",
        },
        {
            "kind": "registration",
            "title": "Course registration closes",
            "starts_on": semester.registration_closes_on or semester.starts_on,
            "ends_on": semester.registration_closes_on or semester.starts_on,
            "audience": "students",
            "description": (
                "After this date a registration needs the deputy registrar's "
                "approval and is marked late."
            ),
        },
        {
            "kind": "holiday",
            "title": "Independence Day",
            "starts_on": date(semester.starts_on.year, 10, 9),
            "ends_on": date(semester.starts_on.year, 10, 9),
            "audience": "all",
            "suspends_teaching": True,
        },
        {
            "kind": "holiday",
            "title": "Eid al-Fitr (observed)",
            "starts_on": semester.starts_on + timedelta(days=30),
            "ends_on": semester.starts_on + timedelta(days=30),
            "audience": "all",
            "suspends_teaching": True,
        },
        {
            "kind": "examination",
            "title": "End-of-semester examinations",
            "starts_on": semester.exams_start_on or semester.ends_on,
            "ends_on": semester.exams_end_on or semester.ends_on,
            "audience": "all",
            "description": "Examination cards must be collected before the first paper.",
        },
        {
            "kind": "governance",
            "title": "Senate meeting: results approval",
            "starts_on": (semester.results_due_on or semester.ends_on) + timedelta(days=14),
            "ends_on": (semester.results_due_on or semester.ends_on) + timedelta(days=14),
            "audience": "staff",
            "location": "Senate Chamber",
        },
        {
            "kind": "graduation",
            "title": "76th Graduation Ceremony",
            "starts_on": date(semester.starts_on.year + 1, 1, 23),
            "ends_on": date(semester.starts_on.year + 1, 1, 24),
            "audience": "all",
            "location": "Freedom Square",
        },
    ]

    existing = {
        row.title
        for row in session.execute(
            select(CalendarEvent).where(CalendarEvent.academic_year_id == year.id)
        ).scalars()
    }
    created = 0
    for entry in wanted:
        if entry["title"] in existing:
            continue
        session.add(
            CalendarEvent(
                academic_year_id=year.id,
                semester_id=semester.id if entry["kind"] != "graduation" else None,
                is_published=True,
                published_at=utcnow(),
                minute_reference="SEN/2026/04",
                **entry,
            )
        )
        created += 1
    session.flush()
    return created


# ---------------------------------------------------------------------------
# The library
# ---------------------------------------------------------------------------


def _library(
    session: Session,
    *,
    courses: dict[str, Course],
    students: list[Student],
    staff: dict[str, Staff],
) -> dict[str, Any]:
    """A small but complete library: policies, stock, members, loans, fines.

    Deliberately includes an overdue loan and the fine it accrued, because
    the overdue queue and the fines list are the two screens a circulation
    desk lives on and an empty one demonstrates nothing.
    """
    campus = session.execute(select(Campus).where(Campus.is_main.is_(True))).scalar_one()
    branch = session.execute(select(Library).where(Library.code == "MAIN")).scalars().first()
    if branch is None:
        branch = Library(
            code="MAIN",
            name="Main Library",
            campus_id=campus.id,
            location_note="Ground and first floors, Administration Block",
            email="library@kit.ac.ug",
            opening_hours={
                "mon": ["08:00", "22:00"],
                "tue": ["08:00", "22:00"],
                "wed": ["08:00", "22:00"],
                "thu": ["08:00", "22:00"],
                "fri": ["08:00", "20:00"],
                "sat": ["09:00", "17:00"],
                "sun": ["14:00", "18:00"],
            },
        )
        session.add(branch)
        session.flush()

    # Loan policies. The numbers are the ones most East African universities
    # settle on, and they differ per category for a reason: a postgraduate
    # reading for a dissertation needs a book for a month.
    policies = [
        ("undergraduate", "normal", 14, 3, 1, 50_000, 1_000_000, 2),
        ("undergraduate", "short_loan", 1, 1, 0, 200_000, 400_000, 0),
        ("postgraduate", "normal", 28, 6, 2, 50_000, 2_000_000, 3),
        ("staff", "normal", 90, 10, 3, 0, None, 7),
        ("external", "normal", 7, 1, 0, 100_000, 500_000, 0),
    ]
    for category, loan_class, days, copies, renewals, rate, cap, grace in policies:
        exists = (
            session.execute(
                select(LoanPolicy).where(
                    LoanPolicy.borrower_category == category,
                    LoanPolicy.loan_class == loan_class,
                    LoanPolicy.library_id == branch.id,
                )
            )
            .scalars()
            .first()
        )
        if exists is not None:
            continue
        session.add(
            LoanPolicy(
                library_id=branch.id,
                borrower_category=category,
                loan_class=loan_class,
                loan_days=days,
                max_copies=copies,
                max_renewals=renewals,
                fine_per_day_minor=rate,
                fine_cap_minor=cap,
                borrowing_block_debt_minor=20_000_00 if rate else None,
                grace_days=grace,
            )
        )
    session.flush()

    titles: list[tuple[str, str, str, int, str, str, list[str], str | None, int]] = [
        (
            "Database System Concepts",
            "Silberschatz, Korth and Sudarshan",
            "978-0078022159",
            2019,
            "7th",
            "005.74 SIL",
            ["Databases", "Relational model", "SQL"],
            "CSC1101",
            4,
        ),
        (
            "Introduction to Algorithms",
            "Cormen, Leiserson, Rivest and Stein",
            "978-0262046305",
            2022,
            "4th",
            "005.1 COR",
            ["Algorithms", "Data structures"],
            "CSC1102",
            3,
        ),
        (
            "Structure and Interpretation of Computer Programs",
            "Abelson and Sussman",
            "978-0262510875",
            1996,
            "2nd",
            "005.13 ABE",
            ["Programming", "Lisp"],
            None,
            2,
        ),
        (
            "Uganda's Constitution and Governance",
            "Kanyeihamba, G. W.",
            "978-9970250035",
            2010,
            "3rd",
            "342.6761 KAN",
            ["Constitutional law", "Uganda"],
            None,
            2,
        ),
        (
            "Research Methods for Business Students",
            "Saunders, Lewis and Thornhill",
            "978-1292402727",
            2023,
            "9th",
            "650.072 SAU",
            ["Research methods", "Dissertations"],
            None,
            5,
        ),
    ]

    accession = 4500
    records: list[CatalogueRecord] = []
    for (
        title,
        authors,
        isbn,
        year_published,
        edition,
        call_number,
        subjects,
        course_code,
        copy_count,
    ) in titles:
        record = (
            session.execute(select(CatalogueRecord).where(CatalogueRecord.title == title))
            .scalars()
            .first()
        )
        if record is None:
            course = courses.get(course_code) if course_code else None
            record = CatalogueRecord(
                material_kind="book",
                title=title,
                statement_of_responsibility=authors,
                authors=[authors],
                edition=edition,
                publisher="Pearson" if "Saunders" in authors else "MIT Press",
                place_of_publication="Harlow" if "Saunders" in authors else "Cambridge, MA",
                published_year=year_published,
                isbn=isbn.replace("-", ""),
                classification=call_number.split()[0],
                author_mark=call_number.split()[-1],
                subjects=subjects,
                course_ids=[course.id] if course is not None else [],
            )
            session.add(record)
            session.flush()

            for index in range(copy_count):
                accession += 1
                # One copy of each set is short loan: the reserve copy that
                # never leaves the reading room overnight, which is how a
                # library serves 60 students from four copies.
                loan_class = "short_loan" if index == 0 and copy_count > 2 else "normal"
                session.add(
                    CatalogueCopy(
                        record_id=record.id,
                        library_id=branch.id,
                        accession_number=f"{accession:06d}",
                        barcode=f"KIT{accession:06d}",
                        call_number=call_number,
                        shelf_location=f"Floor 1, Bay {call_number.split('.')[0]}",
                        loan_class=loan_class,
                        status=CopyStatus.AVAILABLE,
                        condition="good",
                        acquired_on=date(year_published + 1, 3, 14),
                        price_minor=RANDOM.choice([180_000_00, 240_000_00, 320_000_00]),
                        supplier="Aristoc Booklex",
                    )
                )
            session.flush()
        records.append(record)

    # Members: every student who has borrowed, plus the teaching staff.
    borrowers = students[:12]
    members: list[LibraryMember] = []
    for student in borrowers:
        members.append(
            library_service.ensure_member(
                session,
                student_id=student.id,
                borrower_category="undergraduate",
                membership_number=f"LIB/{student.student_number.replace('/', '')}",
                home_library_id=branch.id,
            )
        )
    for code in ("STF/003", "STF/002"):
        person = staff.get(code)
        if person is not None:
            members.append(
                library_service.ensure_member(
                    session,
                    staff_id=person.id,
                    borrower_category="staff",
                    membership_number=f"LIB/{code.replace('/', '')}",
                    home_library_id=branch.id,
                )
            )

    # Loans: some current, one overdue and fined, one already returned.
    issued = 0
    overdue_fine = 0
    available_copies = (
        session.execute(
            select(CatalogueCopy)
            .where(
                CatalogueCopy.status == CopyStatus.AVAILABLE,
                CatalogueCopy.loan_class == "normal",
            )
            .order_by(CatalogueCopy.accession_number)
        )
        .scalars()
        .all()
    )

    for index, member in enumerate(members[:6]):
        if index >= len(available_copies):
            break
        # Idempotent per member, not merely per copy. Keyed on the copy alone,
        # a re-run issued another book to everyone and emptied the shelf —
        # which left the catalogue browsable but nothing borrowable, the one
        # state a library demonstration must not be in.
        already = session.execute(
            select(func.count()).where(
                Loan.member_id == member.id,
                Loan.status.in_((LoanStatus.OPEN, LoanStatus.OVERDUE)),
                Loan.deleted_at.is_(None),
            )
        ).scalar_one()
        if already:
            continue
        copy = available_copies[index]
        try:
            loan = library_service.issue(session, copy=copy, member=member, actor_id=None)
        except (RuleViolation, Conflict):
            continue
        issued += 1
        # The third loan went out five weeks ago and is a fortnight overdue.
        if index == 2:
            loan.issued_at = utcnow() - timedelta(days=35)
            loan.due_on = date.today() - timedelta(days=14)
            loan.original_due_on = loan.due_on
            session.flush()

    accrued = library_service.accrue_overdue(session)
    overdue_fine = accrued["total_minor"]

    # A subscription about to lapse, which is the acquisitions librarian's
    # working screen.
    if (
        session.execute(select(EResourceSubscription).where(EResourceSubscription.name == "JSTOR"))
        .scalars()
        .first()
        is None
    ):
        session.add_all(
            [
                EResourceSubscription(
                    name="JSTOR",
                    provider="ITHAKA",
                    kind="database",
                    access_url="https://www.jstor.org",
                    authentication_method="ip_range",
                    starts_on=date(2026, 1, 1),
                    expires_on=date.today() + timedelta(days=45),
                    concurrent_users=None,
                    annual_cost_minor=18_500_000_00,
                    renewal_decision_due_on=date.today() + timedelta(days=15),
                    usage_statistics={"searches": 41_233, "downloads": 8_912, "turnaways": 0},
                ),
                EResourceSubscription(
                    name="IEEE Xplore",
                    provider="IEEE",
                    kind="database",
                    access_url="https://ieeexplore.ieee.org",
                    authentication_method="ip_range",
                    starts_on=date(2026, 1, 1),
                    expires_on=date(2026, 12, 31),
                    concurrent_users=25,
                    annual_cost_minor=42_000_000_00,
                    # Turnaways are the number that justifies more seats, and
                    # a non-zero one is the point of recording them.
                    usage_statistics={"searches": 22_104, "downloads": 6_401, "turnaways": 318},
                ),
            ]
        )
        session.flush()

    # An acquisition request still not on the shelf: the question the table
    # exists to answer.
    if (
        session.execute(
            select(AcquisitionRequest).where(AcquisitionRequest.title.like("Clean Architecture%"))
        )
        .scalars()
        .first()
        is None
    ):
        lecturer = staff.get("STF/003")
        session.add(
            AcquisitionRequest(
                reference=f"ACQ/{date.today().year}/0001",
                title="Clean Architecture: A Craftsman's Guide to Software Structure",
                authors="Martin, Robert C.",
                isbn="9780134494166",
                publisher="Pearson",
                copies_requested=6,
                requested_by_id=lecturer.id if lecturer is not None else None,
                course_id=courses["CSC1102"].id if "CSC1102" in courses else None,
                expected_cohort=60,
                justification=(
                    "On the reading list for CSC1102 from next semester; the cohort "
                    "has grown from 24 to 60 and the two copies we hold are "
                    "permanently out."
                ),
                status="ordered",
                requested_on=date.today() - timedelta(days=52),
                estimated_unit_price_minor=290_000_00,
                approved_budget_minor=1_740_000_00,
                ordered_on=date.today() - timedelta(days=31),
                supplier="Aristoc Booklex",
                order_reference="PO/2026/0447",
            )
        )
        session.flush()

    return {
        "records": len(records),
        "members": len(members),
        "loans": issued,
        "overdue_fines_minor": overdue_fine,
    }


# ---------------------------------------------------------------------------
# Quality assurance
# ---------------------------------------------------------------------------


def _quality(
    session: Session,
    *,
    offerings: dict[str, CourseOffering],
    semester: Semester,
    students: list[Student],
    staff: dict[str, Staff],
    suspended: set[date],
) -> dict[str, Any]:
    """Registers, an evaluation, an observation and a set of indicators.

    Two deliberate imperfections in the data, because a perfect demonstration
    teaches nothing: one course has a session that was never held, and one
    student is below the attendance threshold. Those are the two things a head
    of department opens this module to find.
    """
    offering = offerings.get("CSC1101")
    if offering is None:
        return {}

    lecturer = staff.get("STF/003")
    teaching_from = semester.teaching_starts_on or semester.starts_on
    teaching_to = min(
        semester.teaching_ends_on or semester.ends_on,
        teaching_from + timedelta(weeks=8),
    )

    sessions = quality_service.generate_sessions(
        session,
        course_offering_id=offering.id,
        semester_id=semester.id,
        slots=[
            {
                "weekday": 1,
                "starts_at": "08:00",
                "ends_at": "10:00",
                "kind": "lecture",
                "staff_id": lecturer.id if lecturer is not None else None,
            },
            {
                "weekday": 3,
                "starts_at": "14:00",
                "ends_at": "16:00",
                "kind": "tutorial",
                "staff_id": lecturer.id if lecturer is not None else None,
            },
        ],
        teaching_from=teaching_from,
        teaching_to=teaching_to,
        suspended_dates=suspended,
        actor_id=lecturer.id if lecturer is not None else None,
    )

    registered = [
        row.student_id
        for row in session.execute(
            select(RegistrationCourse).where(
                RegistrationCourse.course_offering_id == offering.id,
                RegistrationCourse.deleted_at.is_(None),
            )
        ).scalars()
    ]
    cohort = [s for s in students if s.id in set(registered)][:40]
    if not cohort:
        cohort = students[:40]

    past = [
        row
        for row in sorted(sessions, key=lambda s: s.session_date)
        if row.session_date <= date.today()
    ]
    marked = 0
    for index, class_session in enumerate(past):
        # One session simply did not happen — the delivery failure a head of
        # department is looking for.
        if index == 3:
            quality_service.cancel_session(
                session,
                class_session=class_session,
                reason="Lecturer at a conference; no cover arranged.",
                actor_id=lecturer.id if lecturer is not None else None,
                announced=False,
            )
            continue

        entries: list[dict[str, Any]] = []
        for position, student in enumerate(cohort):
            # One student attends about half the time: the case the
            # examination gate exists for.
            if position == 0:
                status = "present" if index % 2 == 0 else "absent"
            elif position == 1 and index == 2:
                status = "excused"
            else:
                status = RANDOM.choices(["present", "present", "present", "late", "absent"], k=1)[0]
            entry: dict[str, Any] = {"student_id": student.id, "status": status}
            if status == "late":
                entry["minutes_late"] = RANDOM.choice([5, 10, 20])
            if status == "excused":
                entry["excuse_reason"] = "Medical appointment; letter on file."
            entries.append(entry)

        quality_service.mark_register(
            session,
            class_session=class_session,
            entries=entries,
            actor_id=lecturer.id if lecturer is not None else None,
        )
        quality_service.close_register(
            session,
            class_session=class_session,
            actor_id=lecturer.id if lecturer is not None else None,
        )
        marked += 1

    # An evaluation instrument, run, answered anonymously and closed.
    instrument = (
        session.execute(select(EvaluationInstrument).where(EvaluationInstrument.code == "TEACH"))
        .scalars()
        .first()
    )
    if instrument is None:
        instrument = EvaluationInstrument(
            code="TEACH",
            version=1,
            name="Teaching and course evaluation",
            scope="teaching",
            introduction=(
                "Your answers are anonymous. Nothing here is linked to you, and the "
                "results are not shown to your lecturer until after marks are "
                "submitted."
            ),
            questions=[
                {
                    "code": "q1",
                    "text": "The course outline was followed.",
                    "kind": "likert5",
                    "dimension": "organisation",
                    "required": True,
                },
                {
                    "code": "q2",
                    "text": "Classes started and finished on time.",
                    "kind": "likert5",
                    "dimension": "organisation",
                    "required": True,
                },
                {
                    "code": "q3",
                    "text": "Explanations were clear.",
                    "kind": "likert5",
                    "dimension": "the lecturer",
                    "required": True,
                },
                {
                    "code": "q4",
                    "text": "Feedback on my work was useful and timely.",
                    "kind": "likert5",
                    "dimension": "assessment and feedback",
                    "required": True,
                },
                {
                    "code": "q5",
                    "text": "What would you change about this course?",
                    "kind": "free_text",
                    "dimension": None,
                    "required": False,
                },
            ],
            dimensions=["organisation", "the lecturer", "assessment and feedback"],
            is_published=True,
            published_at=utcnow(),
        )
        session.add(instrument)
        session.flush()

    evaluation = (
        session.execute(
            select(CourseEvaluation).where(
                CourseEvaluation.course_offering_id == offering.id,
                CourseEvaluation.instrument_id == instrument.id,
            )
        )
        .scalars()
        .first()
    )
    responses = 0
    if evaluation is None:
        # Opened with a live window, answered, then closed and backdated. The
        # seeder cannot answer a closed evaluation — `submit_response` refuses,
        # correctly — so it plays the run through in order rather than writing
        # the end state directly. What lands in the database is what a real
        # run would have left behind.
        evaluation = CourseEvaluation(
            instrument_id=instrument.id,
            course_offering_id=offering.id,
            semester_id=semester.id,
            staff_id=lecturer.id if lecturer is not None else None,
            opens_at=utcnow() - timedelta(days=21),
            closes_at=utcnow() + timedelta(hours=1),
            # After the marking deadline, deliberately.
            results_visible_from=utcnow() - timedelta(days=1),
            status="scheduled",
        )
        session.add(evaluation)
        session.flush()

        quality_service.open_evaluation(
            session,
            evaluation=evaluation,
            student_ids=[s.id for s in cohort],
            actor_id=None,
        )
        # A realistic response rate: about a third, which is what an
        # institution actually gets without chasing.
        comments = [
            "More worked examples in the tutorials would help.",
            "The pace was fine but the room was too small.",
            "Excellent lecturer. The 8am slot is brutal.",
            None,
            "Feedback on assignment 1 came back after assignment 2 was due.",
            None,
            "Please put the slides up before the lecture, not after.",
        ]
        for index, student in enumerate(cohort[:14]):
            quality_service.submit_response(
                session,
                evaluation=evaluation,
                student_id=student.id,
                answers={
                    "q1": RANDOM.choice([3, 4, 4, 5]),
                    "q2": RANDOM.choice([2, 3, 4, 4]),
                    "q3": RANDOM.choice([3, 4, 5, 5]),
                    "q4": RANDOM.choice([2, 2, 3, 4]),
                },
                comments=comments[index % len(comments)],
                year_of_study=1,
                study_mode="full_time",
            )
            responses += 1
        quality_service.close_evaluation(session, evaluation=evaluation, actor_id=None)
        # The window as it really was: closed a week ago.
        evaluation.closes_at = utcnow() - timedelta(days=7)
        session.flush()

    # A peer observation, acknowledged by the person observed.
    observer = staff.get("STF/002")
    if (
        lecturer is not None
        and observer is not None
        and session.execute(
            select(TeachingObservation).where(TeachingObservation.staff_id == lecturer.id)
        )
        .scalars()
        .first()
        is None
    ):
        observation = TeachingObservation(
            staff_id=lecturer.id,
            observer_staff_id=observer.id,
            course_offering_id=offering.id,
            observed_on=date.today() - timedelta(days=18),
            purpose="peer",
            rubric_scores=[
                {"criterion": "Planning and preparation", "score": 4, "max": 5},
                {"criterion": "Clarity of explanation", "score": 5, "max": 5},
                {"criterion": "Student engagement", "score": 3, "max": 5},
                {"criterion": "Use of assessment for learning", "score": 3, "max": 5},
            ],
            strengths=(
                "Explanations were exceptionally clear; the normalisation example "
                "built up in stages and the class followed it."
            ),
            areas_to_develop=(
                "The back third of the theatre was disengaged for the last twenty "
                "minutes. Consider a paired exercise at the hour mark."
            ),
            agreed_actions="Try think-pair-share in week 8 and review together.",
            is_developmental=True,
            status="draft",
            follow_up_due_on=date.today() + timedelta(days=30),
        )
        session.add(observation)
        session.flush()
        quality_service.submit_observation(session, observation=observation, actor_id=observer.id)
        quality_service.acknowledge_observation(
            session,
            observation=observation,
            response=(
                "Agreed about the back of the room. I had not noticed and will try "
                "the paired exercise."
            ),
            actor_id=lecturer.id,
        )

    # Indicators, including one below target — the only end of the list
    # anybody acts on.
    year_id = semester.academic_year_id
    indicators = [
        ("staff_student_ratio", "Staff-student ratio", 21.4, 20.0, False),
        ("pass_rate", "Pass rate", 82.6, 80.0, True),
        ("progression_rate", "Progression rate", 88.1, 85.0, True),
        ("attendance_rate", "Class attendance rate", 71.3, 75.0, True),
        ("teaching_delivery_rate", "Teaching delivery rate", 93.8, 95.0, True),
        ("staff_with_doctorate_percent", "Staff holding a doctorate", 44.4, 40.0, True),
    ]
    recorded = 0
    for code, name, value, target, higher_better in indicators:
        exists = (
            session.execute(
                select(QualityIndicator).where(
                    QualityIndicator.code == code,
                    QualityIndicator.academic_year_id == year_id,
                )
            )
            .scalars()
            .first()
        )
        if exists is not None:
            continue
        quality_service.record_indicator(
            session,
            code=code,
            name=name,
            value=value,
            target=target,
            academic_year_id=year_id,
            higher_is_better=higher_better,
            method_note=(
                "Computed from the semester's registers and results; see the "
                "quality office's method note QA/M/2026/03."
            ),
        )
        recorded += 1

    # An internal audit with an open finding.
    if (
        session.execute(
            select(QualityAudit).where(QualityAudit.title.like("Annual programme review%"))
        )
        .scalars()
        .first()
        is None
    ):
        head = staff.get("STF/001")
        session.add(
            QualityAudit(
                reference=f"QA/{date.today().year}/0001",
                title="Annual programme review: BSc Computer Science",
                kind="internal",
                standard="NCHE Minimum Standards 2014, sections 3 and 5",
                period_from=date(date.today().year - 1, 8, 1),
                period_to=date(date.today().year, 7, 31),
                conducted_on=date.today() - timedelta(days=25),
                lead_auditor_id=None,
                findings=[
                    {
                        "code": "F1",
                        "severity": "minor",
                        "finding": (
                            "Two of eleven course outlines were not published to "
                            "students by the end of week one."
                        ),
                        "evidence": "Course spaces CSC1103, CSC1105.",
                        "owner_staff_id": str(head.id) if head is not None else None,
                        "due_on": (date.today() + timedelta(days=45)).isoformat(),
                        "status": "open",
                    },
                    {
                        "code": "F2",
                        "severity": "observation",
                        "finding": (
                            "Attendance is recorded but not reviewed at department "
                            "meetings, so the students below the threshold are found "
                            "only at examination clearance."
                        ),
                        "evidence": "Minutes of departmental meetings, semester one.",
                        "owner_staff_id": str(head.id) if head is not None else None,
                        "due_on": (date.today() + timedelta(days=90)).isoformat(),
                        "status": "open",
                    },
                    {
                        "code": "F3",
                        "severity": "commendation",
                        "finding": (
                            "Marking turnaround averaged nine days against a fourteen-day target."
                        ),
                        "evidence": "Mark sheet submission dates.",
                        "status": "closed",
                    },
                ],
                major_findings=0,
                minor_findings=1,
                open_findings=2,
                overall_outcome="Satisfactory with minor findings",
                status="published",
                published_at=utcnow(),
                next_review_due_on=date.today() + timedelta(days=340),
            )
        )
        session.flush()

    return {
        "class_sessions": len(sessions),
        "registers_marked": marked,
        "evaluation_responses": responses,
        "indicators": recorded,
    }


# ---------------------------------------------------------------------------
# Life-cycle events and late payment
# ---------------------------------------------------------------------------


def _lifecycle(
    session: Session,
    *,
    students: list[Student],
    offerings: dict[str, CourseOffering],
    semester: Semester,
    staff: dict[str, Staff],
    programmes: dict[str, Programme],
) -> dict[str, Any]:
    """One of each: a special exam request, cards, a transfer, a dead year.

    Each is left at a *different* stage of its approval chain, because the
    queues are what these screens show and a set of finished records
    demonstrates none of them.
    """
    registrar = staff.get("STF/007")
    head = staff.get("STF/001")
    counts: dict[str, Any] = {}

    # Identity cards for the first cohort, and one reported lost.
    cards = 0
    for student in students[:20]:
        exists = (
            session.execute(select(StudentIdCard).where(StudentIdCard.student_id == student.id))
            .scalars()
            .first()
        )
        if exists is not None:
            continue
        lifecycle_service.issue_id_card(
            session,
            student=student,
            actor_id=registrar.id if registrar is not None else None,
            reason="initial",
            expires_on=date(date.today().year + 3, 8, 31),
        )
        cards += 1
    if cards:
        lost = (
            session.execute(
                select(StudentIdCard).where(
                    StudentIdCard.student_id == students[4].id,
                    StudentIdCard.status == "active",
                )
            )
            .scalars()
            .first()
        )
        if lost is not None:
            lifecycle_service.report_card_lost(session, card=lost, actor_id=None, stolen=False)
            lifecycle_service.issue_id_card(
                session,
                student=students[4],
                actor_id=registrar.id if registrar is not None else None,
                reason="replacement",
                expires_on=date(date.today().year + 3, 8, 31),
                replacement_fee_minor=20_000_00,
            )
    counts["id_cards"] = cards

    # Examination cards against approved registrations.
    from acmis.modules.finance import service as finance_service

    issued = 0
    approved_registrations = (
        session.execute(
            select(Registration)
            .where(
                Registration.status == "approved",
                Registration.semester_id == semester.id,
                Registration.deleted_at.is_(None),
            )
            # Ordered, because `LIMIT` without it returns whichever rows
            # Postgres finds first — so two runs of the seeder act on
            # different registrations and the demonstration is not
            # reproducible.
            .order_by(Registration.created_at, Registration.id)
            .limit(25)
        )
        .scalars()
        .all()
    )
    for registration in approved_registrations:
        card_exists = (
            session.execute(select(ExamCard).where(ExamCard.registration_id == registration.id))
            .scalars()
            .first()
        )
        if card_exists is not None:
            continue
        percentage, required = finance_service.fee_percentage_paid(
            session,
            student_id=registration.student_id,
            semester_id=registration.semester_id,
        )
        try:
            lifecycle_service.issue_exam_card(
                session,
                registration=registration,
                actor_id=registrar.id if registrar is not None else None,
                fee_percentage_paid=percentage,
                required_percentage=float(required),
                attendance_ok=None,
                session_name="main",
            )
            issued += 1
        except (RuleViolation, Conflict):
            # Not cleared to sit. Left as it is on purpose: the students who
            # cannot get a card are the population the registry works on.
            continue
    counts["exam_cards"] = issued

    # Special examination requests, one at each stage of the chain.
    offering = offerings.get("CSC1101")
    requests = 0
    if offering is not None and len(students) > 8:
        stages: list[tuple[Student, str, str, str]] = [
            (
                students[5],
                "illness",
                "submitted",
                "Admitted to Mulago with malaria on the morning of the paper; "
                "discharge summary to follow.",
            ),
            (
                students[6],
                "bereavement",
                "recommended",
                "Death of a parent three days before the paper; burial programme attached.",
            ),
            (
                students[7],
                "hospitalisation",
                "granted",
                "Road traffic accident on the Entebbe road; two weeks in hospital.",
            ),
        ]
        for student, ground, target_status, narrative in stages:
            request_exists = (
                session.execute(
                    select(SpecialExamRequest).where(
                        SpecialExamRequest.student_id == student.id,
                        SpecialExamRequest.course_offering_id == offering.id,
                    )
                )
                .scalars()
                .first()
            )
            if request_exists is not None:
                continue
            request = lifecycle_service.lodge_special_exam_request(
                session,
                student=student,
                course_offering_id=offering.id,
                semester_id=semester.id,
                kind="special",
                ground=ground,
                narrative=narrative,
                missed_on=date.today() - timedelta(days=21),
                # The first has nothing on file yet, which is exactly why the
                # deny rule exists: it cannot be granted in that state.
                evidence_attachment_ids=[] if target_status == "submitted" else [uuid.uuid4()],
                actor_id=None,
                fee_minor=30_000_00,
            )
            requests += 1
            if target_status in ("recommended", "granted"):
                lifecycle_service.verify_evidence(
                    session,
                    request=request,
                    actor_id=head.id if head is not None else None,
                )
                lifecycle_service.recommend_special_exam(
                    session,
                    request=request,
                    actor_id=head.id if head is not None else None,
                    note="Circumstances verified; recommend a special examination.",
                )
            if target_status == "granted":
                lifecycle_service.decide_special_exam(
                    session,
                    request=request,
                    grant=True,
                    actor_id=staff["STF/016"].id if "STF/016" in staff else None,
                    note="Granted as a special examination, uncapped.",
                    minute_reference="EXB/2026/11",
                )
    counts["special_exam_requests"] = requests

    # An incoming transfer awaiting credit assessment, and an outgoing one
    # already completed.
    transfers = 0
    if (
        session.execute(
            select(InstitutionTransfer).where(
                InstitutionTransfer.other_institution_name.like("Gulu University%")
            )
        )
        .scalars()
        .first()
        is None
    ):
        programme = programmes.get("BSCS") or next(iter(programmes.values()))
        lifecycle_service.lodge_institution_transfer(
            session,
            direction="incoming",
            other_institution_name="Gulu University",
            other_institution_regulator_code="NCHE/PU/003",
            other_programme_name="BSc Computer Science",
            programme_id=programme.id,
            effective_semester_id=semester.id,
            entry_year_of_study=2,
            credits_claimed=42,
            credit_transfer_cap_percent=40,
            evidence_attachment_ids=[uuid.uuid4()],
            actor_id=None,
            applicant_id=uuid.uuid4(),
        )
        transfers += 1
    if (
        len(students) > 9
        and session.execute(
            select(InstitutionTransfer).where(InstitutionTransfer.direction == "outgoing")
        )
        .scalars()
        .first()
        is None
    ):
        outgoing = lifecycle_service.lodge_institution_transfer(
            session,
            direction="outgoing",
            other_institution_name="Makerere University",
            student_id=students[9].id,
            programme_id=(programmes.get("BSCS") or next(iter(programmes.values()))).id,
            actor_id=None,
        )
        lifecycle_service.approve_transfer(
            session,
            transfer=outgoing,
            actor_id=registrar.id if registrar is not None else None,
            minute_reference="SEN/2026/06",
            note="No objection; the student is in good standing and owes nothing.",
        )
        lifecycle_service.issue_outgoing_papers(
            session,
            transfer=outgoing,
            actor_id=registrar.id if registrar is not None else None,
        )
        transfers += 1
    counts["institution_transfers"] = transfers

    # A dead semester, approved, so the duration counters have something to
    # count.
    if len(students) > 11:
        student = students[11]
        dead_exists = (
            session.execute(
                select(StatusChange).where(
                    StatusChange.student_id == student.id,
                    StatusChange.kind == "dead_semester",
                )
            )
            .scalars()
            .first()
        )
        if dead_exists is None:
            session.add(
                StatusChange(
                    student_id=student.id,
                    kind="dead_semester",
                    from_status=StudentStatus.ACTIVE,
                    to_status=StudentStatus.ACTIVE,
                    effective_from=semester.starts_on,
                    effective_to=semester.ends_on,
                    reason=(
                        "Family circumstances; the student is the sole earner "
                        "following a bereavement and asks to defer one semester."
                    ),
                    status="approved",
                    requested_at=utcnow() - timedelta(days=60),
                    approved_by_id=registrar.id if registrar is not None else None,
                    approved_at=utcnow() - timedelta(days=54),
                    minute_reference="FAC/2026/22",
                )
            )
            session.flush()
            counts["dead_semesters"] = 1

    return counts


def _late_payment(
    session: Session, *, year: AcademicYear, students: list[Student]
) -> dict[str, Any]:
    """Approved terms, a real surcharge, and a plan somebody is keeping to.

    The plan matters most: without one in the data, nothing demonstrates that
    an agreed plan suspends both the surcharge and the block, which is the
    whole design position.
    """
    from acmis.modules.finance.models import Invoice

    rule = (
        session.execute(
            select(LatePaymentRule).where(
                LatePaymentRule.academic_year_id == year.id, LatePaymentRule.code == "LATE-STD"
            )
        )
        .scalars()
        .first()
    )
    if rule is None:
        rule = LatePaymentRule(
            code="LATE-STD",
            name="Standard late payment terms",
            academic_year_id=year.id,
            applies_to_invoice_kind="semester_fees",
            grace_days=7,
            charge_basis="percentage",
            charge_percent=5.0,
            recurrence="once",
            charge_cap_minor=200_000_00,
            blocks_registration_after_days=21,
            blocks_exam_card_after_days=35,
            blocks_results_after_days=60,
            is_waivable=True,
            charge_fee_item_code="LATE-FEE",
            status="approved",
            approved_at=utcnow(),
            effective_from=year.starts_on,
        )
        session.add(rule)
        session.flush()

    # Push two invoices into arrears so the run has something to do. Dated
    # rather than faked: the surcharge is then computed by the same code the
    # nightly job uses.
    arrears = (
        session.execute(
            select(Invoice)
            .where(
                Invoice.kind == "semester_fees",
                Invoice.balance_minor > 0,
                Invoice.deleted_at.is_(None),
            )
            # Same reason, and it matters more here: an unordered pick meant
            # each run backdated different invoices and agreed a plan on a
            # different student, so the surcharge run never twice did the
            # same thing.
            .order_by(Invoice.number)
            .limit(3)
        )
        .scalars()
        .all()
    )
    for index, invoice in enumerate(arrears):
        invoice.due_on = date.today() - timedelta(days=[30, 45, 12][index % 3])
        invoice.status = "overdue"
    session.flush()

    plans = 0
    if len(arrears) > 2:
        # The third student agreed a plan and is keeping to it, so the run
        # must leave them alone.
        protected = arrears[2]
        if (
            protected.student_id is not None
            and session.execute(select(PaymentPlan).where(PaymentPlan.invoice_id == protected.id))
            .scalars()
            .first()
            is None
        ):
            plan = latepayment_service.request_plan(
                session,
                student_id=protected.student_id,
                invoice=protected,
                instalments=3,
                actor_id=None,
                reason=(
                    "Sponsor's disbursement delayed; the student can pay in three "
                    "instalments over the semester."
                ),
            )
            latepayment_service.approve_plan(
                session,
                plan=plan,
                actor_id=None,
                reason="Sponsor letter seen. Agreed.",
                missed_allowance=1,
            )
            plans += 1

    applied = latepayment_service.apply_surcharges(session, actor_id=None, dry_run=False)
    reminders = latepayment_service.send_reminders(session, actor_id=None)
    return {
        "late_payment_rules": 1,
        "payment_plans": plans,
        "surcharges": applied["charged"],
        "surcharge_total_minor": applied["total_minor"],
        "skipped_under_plan": applied["skipped_under_plan"],
        "reminders": reminders["sent"],
    }


# ---------------------------------------------------------------------------
# Rooms, the weekly timetable and the examination timetable
# ---------------------------------------------------------------------------


def _timetable(
    session: Session,
    *,
    offerings: dict[str, CourseOffering],
    semester: Semester,
    staff: dict[str, Staff],
) -> dict[str, Any]:
    """Somewhere to teach, a week that fits, and dated examinations.

    Every slot gets its own day-and-time pair, which is not an accident: the
    three clashes the timetable checks for — a room twice-booked, a lecturer
    in two places, a cohort with two required courses at once — cannot arise
    if no two sessions share a time. A demonstration timetable that clashes
    with itself teaches nothing except that the checks were not run.

    Examination sittings are dated inside the semester's examination window
    rather than "in three weeks", so the countdown on the portal's calendar is
    against a real date and the exam card's validity means something.
    """
    from acmis.modules.assessment.models import ExamSitting

    campus = session.execute(select(Campus).where(Campus.is_main.is_(True))).scalar_one()

    buildings: dict[str, Building] = {}
    for code, name in (
        ("BLKA", "Main Teaching Block"),
        ("BLKB", "Science and Computing Block"),
    ):
        existing = (
            session.execute(
                select(Building).where(Building.campus_id == campus.id, Building.code == code)
            )
            .scalars()
            .first()
        )
        if existing is None:
            existing = Building(campus_id=campus.id, code=code, name=name)
            session.add(existing)
            session.flush()
        buildings[code] = existing

    #: `exam_capacity` is well under `capacity` throughout: examination seating
    #: needs a metre between candidates, so a 200-seat theatre seats about 80.
    wanted_rooms: list[tuple[str, str, str, str, int, int]] = [
        ("BLKA", "LT1", "Lecture Theatre 1", "lecture", 250, 100),
        ("BLKA", "LT2", "Lecture Theatre 2", "lecture", 180, 70),
        ("BLKA", "SR1", "Seminar Room 1", "seminar", 40, 20),
        ("BLKB", "LAB1", "Computer Laboratory 1", "laboratory", 60, 30),
        ("BLKB", "LAB2", "Computer Laboratory 2", "laboratory", 60, 30),
        ("BLKB", "SR2", "Seminar Room 2", "seminar", 45, 22),
        ("BLKA", "HALL", "Great Hall", "examination", 600, 320),
    ]
    rooms: dict[str, Room] = {}
    for building_code, code, name, kind, capacity, exam_capacity in wanted_rooms:
        building = buildings[building_code]
        existing_room = (
            session.execute(select(Room).where(Room.building_id == building.id, Room.code == code))
            .scalars()
            .first()
        )
        if existing_room is None:
            existing_room = Room(
                building_id=building.id,
                code=code,
                name=name,
                kind=kind,
                capacity=capacity,
                exam_capacity=exam_capacity,
                has_projector=kind in ("lecture", "seminar"),
                is_accessible=code != "LAB2",
                is_bookable=True,
            )
            session.add(existing_room)
            session.flush()
        rooms[code] = existing_room

    # Kept apart: a practical belongs in a laboratory and a lecture does not,
    # and a round-robin over one pooled list puts a 200-seat lecture in a
    # 60-seat lab — which is the sort of plan that cannot actually be taught.
    lecture_rooms = [rooms[code] for code in ("LT1", "LT2", "SR1", "SR2")]
    lab_rooms = [rooms[code] for code in ("LAB1", "LAB2")]

    # A distinct (day, time) for every session in the week, so nothing clashes.
    times = [("08:00", "10:00"), ("10:00", "12:00"), ("14:00", "16:00"), ("16:00", "18:00")]
    grid = [(day, start, end) for day in range(1, 6) for start, end in times]

    slots = 0
    index = 0
    for code in sorted(offerings):
        offering = offerings[code]
        allocation = (
            session.execute(
                select(TeachingAllocation).where(
                    TeachingAllocation.offering_id == offering.id,
                    TeachingAllocation.role.in_(("lecturer", "coordinator")),
                    TeachingAllocation.deleted_at.is_(None),
                )
            )
            .scalars()
            .first()
        )
        course = session.get(Course, offering.course_id)
        kinds = ["lecture"]
        if course is not None and course.practical_hours:
            kinds.append("practical")
        elif course is not None and course.tutorial_hours:
            kinds.append("tutorial")

        for session_kind in kinds:
            if index >= len(grid):
                break
            day, start, end = grid[index]
            index += 1
            existing_slot = (
                session.execute(
                    select(TimetableSlot).where(
                        TimetableSlot.offering_id == offering.id,
                        TimetableSlot.session_kind == session_kind,
                        TimetableSlot.deleted_at.is_(None),
                    )
                )
                .scalars()
                .first()
            )
            if existing_slot is not None:
                continue
            room = (
                lab_rooms[index % len(lab_rooms)]
                if session_kind == "practical"
                else lecture_rooms[index % len(lecture_rooms)]
            )
            session.add(
                TimetableSlot(
                    offering_id=offering.id,
                    room_id=room.id,
                    staff_id=allocation.staff_id if allocation is not None else None,
                    day_of_week=day,
                    starts_at=start,
                    ends_at=end,
                    session_kind=session_kind,
                    # Weeks 1-13. A fortnightly practical would list only the
                    # weeks it runs, which is why this is a list and not a flag.
                    week_pattern=list(range(1, 14)),
                    is_online=False,
                )
            )
            slots += 1
    session.flush()

    # Examinations: one paper a day per course, inside the published window.
    invigilators = [
        person.id
        for code in ("STF/004", "STF/005", "STF/006", "STF/008")
        if (person := staff.get(code)) is not None
    ]
    chief = staff.get("STF/016")
    starts_on = semester.exams_start_on or (semester.ends_on - timedelta(days=14))
    sittings = 0
    for offset, code in enumerate(sorted(offerings)):
        offering = offerings[code]
        existing_sitting = (
            session.execute(
                select(ExamSitting).where(
                    ExamSitting.course_offering_id == offering.id,
                    ExamSitting.session == "main",
                )
            )
            .scalars()
            .first()
        )
        if existing_sitting is not None:
            continue
        # Skip Sundays: nobody sits a paper on a Sunday here.
        sitting_date = starts_on + timedelta(days=offset + offset // 6)
        while sitting_date.weekday() == 6:
            sitting_date += timedelta(days=1)
        candidates = int(
            session.execute(
                select(func.count()).where(
                    RegistrationCourse.course_offering_id == offering.id,
                    RegistrationCourse.deleted_at.is_(None),
                )
            ).scalar_one()
        )
        session.add(
            ExamSitting(
                course_offering_id=offering.id,
                semester_id=semester.id,
                sitting_date=sitting_date,
                starts_at="09:00" if offset % 2 == 0 else "14:00",
                duration_minutes=180,
                session="main",
                room_ids=[rooms["HALL"].id],
                candidate_count=candidates,
                invigilator_staff_ids=invigilators[: 1 + candidates // 40],
                chief_invigilator_id=chief.id if chief is not None else None,
                accommodation_count=0,
                status="scheduled",
            )
        )
        sittings += 1
    session.flush()

    return {"rooms": len(rooms), "timetable_slots": slots, "exam_sittings": sittings}


# ---------------------------------------------------------------------------
# Guild elections
# ---------------------------------------------------------------------------


#: The student designated as the walkable "complete record". Every seeded
#: module leaves at least one row against this number, so a demonstration can
#: be given from one login rather than from six. Chosen rather than computed
#: because it has to be quotable: it goes in the CLI output and in the docs.
SHOWCASE_STUDENT_NUMBER = "25/U/0003/BSC"


def _elections(
    session: Session,
    *,
    students: list[Student],
    staff: dict[str, Staff],
    year: AcademicYear,
    units: dict[str, AcademicUnit],
) -> dict[str, Any]:
    """Two elections: one declared, one open for voting.

    Two, because one cannot show both halves of the design. The declared one
    demonstrates a count, a tie-break and a published result; the open one
    leaves a real ballot for whoever is being shown the system to cast. The
    showcase student votes in the first and not the second, so they have a
    voting record *and* something to do.

    Played through the service in order — nominate, vet, draw, open, vote,
    close, declare — rather than written as an end state. A hand-written
    result would not have receipts, and the receipts are the interesting part.
    """
    from acmis.modules.elections import service as elections_service
    from acmis.modules.elections.models import (
        Candidate,
        Election,
        ElectionPosition,
        ElectionStatus,
        VoterRoll,
    )

    officer = staff.get("STF/007")
    observers = [p.id for p in (staff.get("STF/001"), staff.get("STF/002")) if p is not None]
    counts: dict[str, Any] = {"elections": 0, "candidates": 0, "ballots": 0}

    # Candidates are drawn from students in good standing with a CGPA that
    # clears the constitutional minimum, because `vet_candidate` runs the
    # checks for real and refuses a nomination that fails one.
    def eligible_candidates(count: int, *, skip: set[uuid.UUID]) -> list[Student]:
        chosen: list[Student] = []
        for student in students:
            if student.id in skip or student.status != StudentStatus.ACTIVE:
                continue
            attachment = (
                session.execute(
                    select(StudentProgramme).where(
                        StudentProgramme.student_id == student.id,
                        StudentProgramme.is_primary.is_(True),
                    )
                )
                .scalars()
                .first()
            )
            if attachment is None or attachment.cgpa is None or float(attachment.cgpa) < 2.5:
                continue
            chosen.append(student)
            if len(chosen) == count:
                break
        return chosen

    showcase = next(
        (s for s in students if s.student_number == SHOWCASE_STUDENT_NUMBER),
        students[2] if len(students) > 2 else None,
    )

    def make(
        *,
        reference: str,
        title: str,
        kind: str,
        description: str,
        quorum: int | None,
        positions: list[dict[str, Any]],
    ) -> Election | None:
        existing = (
            session.execute(select(Election).where(Election.reference == reference))
            .scalars()
            .first()
        )
        if existing is not None:
            return None
        election = Election(
            reference=reference,
            title=title,
            kind=kind,
            academic_year_id=year.id,
            description=description,
            returning_officer_id=officer.id if officer is not None else None,
            observer_staff_ids=observers,
            nominations_open_at=utcnow() - timedelta(days=40),
            nominations_close_at=utcnow() - timedelta(days=33),
            campaign_starts_at=utcnow() - timedelta(days=28),
            status=ElectionStatus.VETTING,
            quorum_percent=quorum,
        )
        session.add(election)
        session.flush()
        for spec in positions:
            session.add(ElectionPosition(election_id=election.id, **spec))
        session.flush()
        session.refresh(election)
        counts["elections"] += 1
        return election

    # --- the declared guild election ---------------------------------------

    guild = make(
        reference="ELE/2026/001",
        title="Guild Elections 2026/2027",
        kind="guild",
        description=(
            "Election of the Guild President and Vice President, and a referendum "
            "on the guild subscription, held under the Guild Constitution 2019."
        ),
        quorum=30,
        positions=[
            {
                "code": "GP",
                "title": "Guild President",
                "description": "Head of the students' guild for one academic year.",
                "sequence": 1,
                "seats": 1,
                "max_choices": 1,
                "eligibility_rules": {
                    "min_cgpa": 2.5,
                    "no_disciplinary_finding": True,
                    "min_nominators": 5,
                },
            },
            {
                "code": "GVP",
                "title": "Guild Vice President",
                "description": "Reserved seat under article 14(2) of the constitution.",
                "sequence": 2,
                "seats": 1,
                "max_choices": 1,
                "reserved_for": "female",
                "eligibility_rules": {"min_cgpa": 2.5, "min_nominators": 5},
            },
            {
                "code": "REF-SUB",
                "title": "Referendum: guild subscription",
                "sequence": 3,
                "seats": 1,
                "max_choices": 1,
                "is_referendum": True,
                "question": (
                    "Should the annual guild subscription rise from UGX 20,000 to "
                    "UGX 30,000, the increase being ring-fenced for the students' "
                    "welfare fund?"
                ),
            },
        ],
    )

    if guild is not None:
        by_code = {position.code: position for position in guild.positions}
        taken: set[uuid.UUID] = {showcase.id} if showcase is not None else set()

        slogans = [
            ("A guild that answers", "Weekly open surgeries in every hall, minutes published."),
            ("Fix the basics", "Water in the halls, lights in the reading rooms, buses that run."),
            ("Nothing about us without us", "A student on every board that decides our fees."),
        ]
        for index, student in enumerate(eligible_candidates(3, skip=taken)):
            taken.add(student.id)
            slogan, manifesto = slogans[index % len(slogans)]
            session.add(
                Candidate(
                    position_id=by_code["GP"].id,
                    student_id=student.id,
                    ballot_name=f"{student.given_names.split()[0]} {student.surname}",
                    slogan=slogan,
                    manifesto=manifesto,
                    nominator_student_ids=[s.id for s in students[30:38]],
                    nomination_fee_minor=100_000_00,
                    status="nominated",
                    nominated_at=utcnow() - timedelta(days=35),
                )
            )
        women = [
            student for student in eligible_candidates(24, skip=taken) if student.sex == "female"
        ][:2]
        for student in women:
            taken.add(student.id)
            session.add(
                Candidate(
                    position_id=by_code["GVP"].id,
                    student_id=student.id,
                    ballot_name=f"{student.given_names.split()[0]} {student.surname}",
                    slogan="Welfare first",
                    manifesto="A hardship fund with published criteria, run by students.",
                    nominator_student_ids=[s.id for s in students[38:45]],
                    nomination_fee_minor=100_000_00,
                    status="nominated",
                    nominated_at=utcnow() - timedelta(days=35),
                )
            )
        for label in ("Yes", "No"):
            session.add(
                Candidate(
                    position_id=by_code["REF-SUB"].id,
                    option_label=label,
                    ballot_name=label,
                    status="nominated",
                    nominated_at=utcnow() - timedelta(days=35),
                )
            )
        session.flush()
        session.refresh(guild)

        # One nomination refused, with the reason on the record — the state a
        # petition is actually about.
        refused = eligible_candidates(1, skip=taken)
        if refused:
            late = Candidate(
                position_id=by_code["GP"].id,
                student_id=refused[0].id,
                ballot_name=f"{refused[0].given_names.split()[0]} {refused[0].surname}",
                nominator_student_ids=[students[45].id] if len(students) > 45 else [],
                status="nominated",
                nominated_at=utcnow() - timedelta(days=32),
            )
            session.add(late)
            session.flush()
            elections_service.vet_candidate(
                session,
                candidate=late,
                actor_id=officer.id if officer is not None else None,
                approve=False,
                reason=(
                    "Nomination lodged after the close of nominations and with two "
                    "seconders rather than the five article 12(3) requires."
                ),
            )

        for position in guild.positions:
            for candidate in position.candidates:
                if candidate.status != "nominated":
                    continue
                elections_service.vet_candidate(
                    session,
                    candidate=candidate,
                    actor_id=officer.id if officer is not None else None,
                    approve=True,
                )
                counts["candidates"] += 1

        elections_service.draw_ballot_order(
            session,
            election=guild,
            actor_id=officer.id if officer is not None else None,
            seed=4471,
        )
        guild.status = ElectionStatus.CAMPAIGN
        session.flush()
        elections_service.build_roll(
            session, election=guild, actor_id=officer.id if officer is not None else None
        )
        # The window is opened live and backdated after the ballots are in.
        # `cast_ballot` refuses a vote after `voting_closes_at`, correctly, so
        # a poll written as already closed cannot be voted in — the seeder
        # plays it through in real time and moves the dates afterwards.
        guild.voting_opens_at = utcnow() - timedelta(days=21)
        guild.voting_closes_at = utcnow() + timedelta(hours=1)
        elections_service.open_poll(
            session, election=guild, actor_id=officer.id if officer is not None else None
        )

        approved_by_position = {
            position.id: [c for c in position.candidates if c.status == "approved"]
            for position in guild.positions
        }
        voters = [students[0]] if students else []
        if showcase is not None:
            voters.append(showcase)
        voters += [s for s in students[1:40] if s.id != (showcase.id if showcase else None)]

        cast = 0
        for index, student in enumerate({s.id: s for s in voters}.values()):
            roll_row = (
                session.execute(
                    select(VoterRoll).where(
                        VoterRoll.election_id == guild.id,
                        VoterRoll.student_id == student.id,
                    )
                )
                .scalars()
                .first()
            )
            if roll_row is None or not roll_row.is_eligible or roll_row.voted_at is not None:
                continue
            choices: dict[uuid.UUID, list[uuid.UUID]] = {}
            for position_id in roll_row.position_ids:
                field = approved_by_position.get(position_id, [])
                if not field:
                    continue
                # Every fifth voter abstains on the referendum: a blank ballot
                # is a real outcome and the count has to distinguish it.
                if index % 5 == 4 and len(field) == 2 and field[0].option_label:
                    choices[position_id] = []
                else:
                    choices[position_id] = [field[index % len(field)].id]
            if not choices:
                continue
            elections_service.cast_ballot(
                session,
                election=guild,
                student_id=student.id,
                choices=choices,
                ip_address=f"10.20.{index // 250}.{index % 250}",
                via="portal" if index % 7 else "booth",
            )
            cast += 1
        counts["ballots"] += cast

        elections_service.close_poll(
            session, election=guild, actor_id=officer.id if officer is not None else None
        )
        guild.voting_closes_at = utcnow() - timedelta(days=20)
        guild.opened_at = utcnow() - timedelta(days=21)
        guild.closed_at = utcnow() - timedelta(days=20)
        session.flush()
        try:
            elections_service.declare(
                session,
                election=guild,
                actor_id=officer.id if officer is not None else None,
            )
        except RuleViolation as exc:
            # A tie on a last seat. Declared with the tie-break recorded,
            # which is what the constitution requires and what the deny rule
            # exists to force.
            positions_tied = list((exc.details or {}).get("positions", []))
            notes = {
                str(position.id): (
                    "Tie broken by lot before the observers, "
                    "as article 21(4) provides. Drawn 9 March 2026."
                )
                for position in guild.positions
                if position.title in positions_tied
            }
            elections_service.declare(
                session,
                election=guild,
                actor_id=officer.id if officer is not None else None,
                tie_break_notes=notes,
            )

    # --- the open by-election ----------------------------------------------

    college = units.get("COCIS")
    by_election = make(
        reference="ELE/2026/002",
        title="College of Computing Representative By-Election",
        kind="by_election",
        description=(
            "Two seats on the Guild Representative Council for the College of "
            "Computing and Information Sciences, following the resignation of "
            "both incumbents."
        ),
        quorum=20,
        positions=[
            {
                "code": "GRC-COCIS",
                "title": "Representative, College of Computing",
                "description": "Two seats. Vote for up to two candidates.",
                "sequence": 1,
                "seats": 2,
                "max_choices": 2,
                "electorate_faculty_ids": [college.id] if college is not None else [],
                "eligibility_rules": {"min_cgpa": 2.5, "min_nominators": 3},
            }
        ],
    )

    if by_election is not None:
        position = by_election.positions[0]
        skip = {showcase.id} if showcase is not None else set()
        skip |= {
            row.student_id
            for row in session.execute(
                select(Candidate).where(Candidate.student_id.is_not(None))
            ).scalars()
            if row.student_id is not None
        }
        pitches = [
            ("Reading rooms open till midnight", "Negotiated with the college, costed, ready."),
            ("Laboratory slots that exist", "A published rota for the two computer labs."),
            ("Print credit, not print queues", "Move the college printing to a card system."),
            ("Represent, then report", "A written report to every class, every month."),
        ]
        for index, student in enumerate(eligible_candidates(4, skip=skip)):
            if college is not None and college.id not in (student.faculty_ids or []):
                continue
            slogan, manifesto = pitches[index % len(pitches)]
            session.add(
                Candidate(
                    position_id=position.id,
                    student_id=student.id,
                    ballot_name=f"{student.given_names.split()[0]} {student.surname}",
                    slogan=slogan,
                    manifesto=manifesto,
                    nominator_student_ids=[s.id for s in students[20:25]],
                    nomination_fee_minor=20_000_00,
                    status="nominated",
                    nominated_at=utcnow() - timedelta(days=6),
                )
            )
        session.flush()
        session.refresh(by_election)

        for candidate in by_election.positions[0].candidates:
            if candidate.status != "nominated":
                continue
            elections_service.vet_candidate(
                session,
                candidate=candidate,
                actor_id=officer.id if officer is not None else None,
                approve=True,
            )
            counts["candidates"] += 1

        elections_service.draw_ballot_order(
            session,
            election=by_election,
            actor_id=officer.id if officer is not None else None,
            seed=1109,
        )
        by_election.status = ElectionStatus.CAMPAIGN
        session.flush()
        elections_service.build_roll(
            session,
            election=by_election,
            actor_id=officer.id if officer is not None else None,
        )
        by_election.voting_opens_at = utcnow() - timedelta(hours=6)
        by_election.voting_closes_at = utcnow() + timedelta(days=2)
        elections_service.open_poll(
            session,
            election=by_election,
            actor_id=officer.id if officer is not None else None,
        )

        # Part-way through, so turnout is real and the showcase student still
        # has a ballot to cast.
        field = [c for c in by_election.positions[0].candidates if c.status == "approved"]
        cast = 0
        if field:
            for index, student in enumerate(students[6:30]):
                if showcase is not None and student.id == showcase.id:
                    continue
                roll_row = (
                    session.execute(
                        select(VoterRoll).where(
                            VoterRoll.election_id == by_election.id,
                            VoterRoll.student_id == student.id,
                        )
                    )
                    .scalars()
                    .first()
                )
                if roll_row is None or not roll_row.is_eligible or roll_row.voted_at is not None:
                    continue
                if not roll_row.position_ids:
                    continue
                picked = [field[index % len(field)].id]
                if index % 3 == 0 and len(field) > 1:
                    picked.append(field[(index + 1) % len(field)].id)
                elections_service.cast_ballot(
                    session,
                    election=by_election,
                    student_id=student.id,
                    choices={roll_row.position_ids[0]: picked},
                    ip_address=f"10.30.0.{index % 250}",
                    via="portal",
                )
                cast += 1
        counts["ballots"] += cast

    return counts


# ---------------------------------------------------------------------------
# One student with everything
# ---------------------------------------------------------------------------


def _showcase(
    session: Session,
    *,
    students: list[Student],
    offerings: dict[str, CourseOffering],
    semester: Semester,
    staff: dict[str, Staff],
) -> dict[str, Any]:
    """Fill in whatever the designated student is still missing.

    The other seeders spread their records across the population on purpose —
    a demonstration needs queues, and a queue needs students at different
    stages. The cost is that no single login shows the whole system, which is
    exactly what someone being given a demonstration wants. This runs last and
    closes the gaps for one named student, so the tour can be given from one
    account.

    Everything here goes through the same services as an interactive change,
    so nothing lands in a state the API would refuse to produce.
    """
    from acmis.modules.students import service as students_service
    from acmis.modules.students.models import DisciplinaryCase

    student = next(
        (s for s in students if s.student_number == SHOWCASE_STUDENT_NUMBER),
        None,
    )
    if student is None:
        return {}

    registrar = staff.get("STF/007")
    head = staff.get("STF/001")
    dean = staff.get("STF/016")
    added: list[str] = []

    # --- an examination card ------------------------------------------------
    registration = (
        session.execute(
            select(Registration).where(
                Registration.student_id == student.id,
                Registration.semester_id == semester.id,
                Registration.deleted_at.is_(None),
            )
        )
        .scalars()
        .first()
    )
    if registration is not None:
        card = (
            session.execute(select(ExamCard).where(ExamCard.registration_id == registration.id))
            .scalars()
            .first()
        )
        if card is None:
            from acmis.modules.finance import service as finance_service

            percentage, required = finance_service.fee_percentage_paid(
                session, student_id=student.id, semester_id=semester.id
            )
            try:
                lifecycle_service.issue_exam_card(
                    session,
                    registration=registration,
                    actor_id=registrar.id if registrar is not None else None,
                    fee_percentage_paid=percentage,
                    required_percentage=float(required),
                    attendance_ok=None,
                    session_name="main",
                    override_reason=(
                        "Issued on the dean's authority pending the balance; the "
                        "sponsor's disbursement is confirmed in writing."
                    ),
                )
                added.append("exam_card")
            except (RuleViolation, Conflict):
                pass

    # --- an identity card ---------------------------------------------------
    if (
        session.execute(select(StudentIdCard).where(StudentIdCard.student_id == student.id))
        .scalars()
        .first()
        is None
    ):
        lifecycle_service.issue_id_card(
            session,
            student=student,
            actor_id=registrar.id if registrar is not None else None,
            reason="initial",
            expires_on=date(date.today().year + 3, 8, 31),
        )
        added.append("id_card")

    # --- a special examination, granted -------------------------------------
    offering = offerings.get("CSC1100")
    if offering is not None and (
        session.execute(
            select(SpecialExamRequest).where(
                SpecialExamRequest.student_id == student.id,
                SpecialExamRequest.course_offering_id == offering.id,
            )
        )
        .scalars()
        .first()
        is None
    ):
        request = lifecycle_service.lodge_special_exam_request(
            session,
            student=student,
            course_offering_id=offering.id,
            semester_id=semester.id,
            kind="special",
            ground="illness",
            narrative=(
                "Typhoid, confirmed at the university clinic on the morning of the "
                "paper. Admitted for four days; the clinic's letter and the "
                "discharge summary are both on file with the faculty office."
            ),
            missed_on=date.today() - timedelta(days=25),
            evidence_attachment_ids=[uuid.uuid4()],
            actor_id=None,
            fee_minor=30_000_00,
        )
        lifecycle_service.verify_evidence(
            session, request=request, actor_id=head.id if head is not None else None
        )
        lifecycle_service.recommend_special_exam(
            session,
            request=request,
            actor_id=head.id if head is not None else None,
            note="Clinic letter seen and confirmed. Recommend a special examination.",
        )
        lifecycle_service.decide_special_exam(
            session,
            request=request,
            grant=True,
            actor_id=dean.id if dean is not None else None,
            note="Granted as a special examination, uncapped, in the next sitting.",
            minute_reference="EXB/2026/14",
        )
        added.append("special_exam")

    # --- a dead semester already served -------------------------------------
    if (
        session.execute(
            select(StatusChange).where(
                StatusChange.student_id == student.id,
                StatusChange.kind == "dead_semester",
            )
        )
        .scalars()
        .first()
        is None
    ):
        session.add(
            StatusChange(
                student_id=student.id,
                kind="dead_semester",
                from_status=StudentStatus.ACTIVE,
                to_status=StudentStatus.ACTIVE,
                effective_from=semester.starts_on - timedelta(days=210),
                effective_to=semester.starts_on - timedelta(days=90),
                reason=(
                    "Deferred one semester to care for a parent after surgery. "
                    "Requested before the semester opened, as the regulations require."
                ),
                status="approved",
                requested_at=utcnow() - timedelta(days=300),
                approved_by_id=registrar.id if registrar is not None else None,
                approved_at=utcnow() - timedelta(days=294),
                minute_reference="FAC/2026/04",
            )
        )
        session.flush()
        added.append("dead_semester")

    # --- a disciplinary matter, dismissed -----------------------------------
    #
    # Dismissed rather than upheld on purpose. An upheld finding would bar
    # this student from standing for the guild, and the point of the record is
    # to show that a dismissed allegation is *kept* — a system that deletes
    # them cannot answer "was this ever investigated".
    if (
        session.execute(select(DisciplinaryCase).where(DisciplinaryCase.student_id == student.id))
        .scalars()
        .first()
        is None
    ):
        session.add(
            DisciplinaryCase(
                case_number="DISC/2026/018",
                student_id=student.id,
                category="examination_malpractice",
                reported_on=date.today() - timedelta(days=120),
                reported_by_id=head.id if head is not None else None,
                allegation=(
                    "An invigilator reported unauthorised material at the desk "
                    "during the Computer Literacy test."
                ),
                status="dismissed",
                finding=(
                    "The material was a course handout distributed by the lecturer "
                    "and permitted under the rubric. No case to answer."
                ),
                decided_at=utcnow() - timedelta(days=96),
                committee_minute_reference="DC/2026/07",
                appeal_deadline_on=date.today() - timedelta(days=82),
            )
        )
        session.flush()
        added.append("disciplinary_case")

    # --- a receipt on the account -------------------------------------------
    #
    # A part payment, not a settlement. The invoice stays in arrears, which is
    # what makes the surcharge, the reminder and the block on this account
    # real — and a statement with charges and no receipts looks like a broken
    # integration rather than a student who owes money.
    from acmis.modules.finance import service as finance
    from acmis.modules.finance.models import Invoice as FeeInvoice

    invoice = (
        session.execute(
            select(FeeInvoice)
            .where(
                FeeInvoice.student_id == student.id,
                FeeInvoice.kind == "semester_fees",
                FeeInvoice.deleted_at.is_(None),
            )
            .order_by(FeeInvoice.number)
        )
        .scalars()
        .first()
    )
    if (
        invoice is not None
        and not session.execute(
            select(Payment).where(Payment.provider_reference == "DEMO-SHOWCASE-A")
        )
        .scalars()
        .first()
    ):
        for suffix, share, method in (
            ("A", 0.35, "mobile_money"),
            ("B", 0.15, "bank_deposit"),
        ):
            due = invoice.total_minor - invoice.sponsor_portion_minor
            amount = int(due * share)
            if amount <= 0:
                continue
            finance.record_payment(
                session,
                student_id=student.id,
                applicant_id=None,
                amount_minor=amount,
                currency=invoice.currency,
                method=method,
                provider="mgurush" if method == "mobile_money" else None,
                provider_reference=f"DEMO-SHOWCASE-{suffix}",
                payer_narrative=f"{student.student_number} fees",
                payer_name=f"{student.given_names} {student.surname}",
                value_date=date.today() - timedelta(days=40 if suffix == "A" else 12),
                actor_id=registrar.id if registrar is not None else uuid.uuid4(),
            )
        added.append("payments")

    # --- a graduation clearance checklist -----------------------------------
    created = students_service.ensure_clearance_checklist(
        session,
        student=student,
        purpose="graduation",
        offices=["library", "finance", "hall", "department", "laboratory"],
        actor_id=registrar.id if registrar is not None else uuid.uuid4(),
    )
    if created:
        added.append("clearance")

    # --- a library fine and a reservation -----------------------------------
    member = (
        session.execute(
            select(LibraryMember).where(
                LibraryMember.student_id == student.id, LibraryMember.deleted_at.is_(None)
            )
        )
        .scalars()
        .first()
    )
    if member is not None:
        if (
            session.execute(select(LibraryFine).where(LibraryFine.member_id == member.id))
            .scalars()
            .first()
            is None
        ):
            loan = (
                session.execute(
                    select(Loan)
                    .where(Loan.member_id == member.id, Loan.deleted_at.is_(None))
                    .order_by(Loan.issued_at)
                )
                .scalars()
                .first()
            )
            library_service.raise_fine(
                session,
                member=member,
                reason="overdue",
                amount_minor=300_000,
                actor_id=None,
                loan=loan,
                days_overdue=6,
                rate_per_day_minor=50_000,
                note="Accrued by the nightly job; the volume has since been returned.",
            )
            added.append("library_fine")

        record = (
            session.execute(
                select(CatalogueRecord)
                .where(CatalogueRecord.deleted_at.is_(None))
                .order_by(CatalogueRecord.title)
            )
            .scalars()
            .first()
        )
        if record is not None and member.status == "active":
            try:
                library_service.reserve(session, record=record, member=member)
                added.append("library_reservation")
            except (RuleViolation, Conflict):
                pass

    return {"showcase_student": student.student_number, "showcase_added": added}


def sample_logins(*, slug: str, dsn: str, per_programme: int = 2) -> list[tuple[str, str]]:
    """A few real student logins, read back from the database.

    Read rather than described, because a described pattern drifts from the
    truth and then wastes somebody's afternoon. The seeded numbers are gapped
    (they are allocated across programmes, as a real registry allocates them)
    and the suffix follows the programme — BSC, BIS, BNS, MSC — so
    "24/U/0060/BSC" looks plausible, does not exist, and produces the same
    "username or password is not correct" as a wrong password, by design.
    """
    # Cross-module relationships are resolved by name; see
    # `acmis.modules.registry`.
    configure_mappers()
    out: list[tuple[str, str]] = []
    with tenant_session_ctx(key=slug, dsn=dsn) as session:
        rows = session.execute(
            select(UserAccount.username, Student.surname, Student.given_names)
            .join(Student, Student.id == UserAccount.student_id)
            .where(UserAccount.kind == "student", UserAccount.deleted_at.is_(None))
            .order_by(UserAccount.username)
        ).all()
    seen: dict[str, int] = {}
    for username, surname, given in rows:
        suffix = username.rsplit("/", 1)[-1]
        if seen.get(suffix, 0) >= per_programme:
            continue
        seen[suffix] = seen.get(suffix, 0) + 1
        out.append((str(username), f"{given} {surname}"))
    return out
