"""Imports every model module, completing SQLAlchemy's class registry.

A relationship that crosses a module boundary names its target as a string —
`relationship("CourseOffering")` — so that, say, `assessment` does not import
`curriculum` at runtime and the module import graph stays acyclic. SQLAlchemy
resolves that name through its own class registry, which contains exactly the
mapped classes that have been *imported*.

That makes correctness depend on import order, and the failure is nasty: a
script that imports one module gets

    InvalidRequestError: expression 'CourseOffering' failed to locate a name

on the first query, while the running application — which imports everything
— works perfectly. Importing this module removes the dependency on order.

Every composition root does so: the application, the CLI, both Alembic
environments, and the test fixtures. `test_architecture.py` asserts they all
still do, because the day one of them stops is the day a cron job starts
failing on a machine nobody is watching.
"""

from __future__ import annotations

from acmis.modules.admissions import models as admissions
from acmis.modules.assessment import models as assessment
from acmis.modules.curriculum import models as curriculum
from acmis.modules.developers import models as developers
from acmis.modules.elections import models as elections
from acmis.modules.finance import models as finance
from acmis.modules.governance import models as governance
from acmis.modules.identity import models as identity
from acmis.modules.interop import models as interop
from acmis.modules.learning import models as learning
from acmis.modules.library import models as library
from acmis.modules.people import models as people
from acmis.modules.quality import models as quality
from acmis.modules.shared import models as shared
from acmis.modules.students import models as students
from acmis.modules.tenancy import models as tenancy

#: Every model module, in dependency-free order. Exported so a caller can be
#: explicit — `from acmis.modules.registry import MODEL_MODULES` — rather than
#: importing this module for its side effect alone, which linters delete.
MODEL_MODULES = (
    shared,
    identity,
    tenancy,
    admissions,
    students,
    curriculum,
    finance,
    people,
    assessment,
    learning,
    library,
    quality,
    governance,
    interop,
    developers,
    elections,
)


def configure() -> None:
    """Resolve every mapper now, rather than on the first query.

    Called at start-up. A cross-module relationship naming a class that was
    never imported fails here — at boot, with the mapper named — instead of
    inside the first request that happens to traverse it.
    """
    from sqlalchemy.orm import configure_mappers

    configure_mappers()


__all__ = ["MODEL_MODULES", "configure"]
