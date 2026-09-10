"""Structural rules the codebase keeps, checked rather than remembered.

The modules here are deliberately *connected*: admissions creates a student
record, assessment reads registrations, learning pushes marks onto a mark
sheet. So "no module imports another" would be the wrong rule to enforce — it
is not the rule this design follows.

The rules it does follow, and that erode silently without a test, are: the
module-level import graph stays acyclic, model modules stay importable in any
order, the middleware order the security model assumes is the order installed,
and no router is defined without being mounted.
"""

from __future__ import annotations

import ast
from collections import defaultdict
from pathlib import Path

import pytest

API_ROOT = Path(__file__).resolve().parent.parent / "acmis"
MODULES_ROOT = API_ROOT / "modules"

MODULES = sorted(
    p.name for p in MODULES_ROOT.iterdir() if p.is_dir() and (p / "__init__.py").exists()
)


def _module_level_imports(path: Path) -> set[str]:
    """Only imports executed at import time.

    A function-local import is the sanctioned way to use another module where a
    module-level one would close a cycle, so it is deliberately not counted.
    """
    tree = ast.parse(path.read_text())

    def _lines(node: ast.AST) -> set[int]:
        return {child.lineno for child in ast.walk(node) if hasattr(child, "lineno")}

    deferred: set[int] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef):
            deferred |= _lines(node)
        elif isinstance(node, ast.If):
            test = node.test
            if isinstance(test, ast.Name) and test.id == "TYPE_CHECKING":
                # Evaluated by the type checker, never at runtime.
                deferred |= _lines(node)

    found: set[str] = set()
    for node in ast.walk(tree):
        if not isinstance(node, ast.Import | ast.ImportFrom) or node.lineno in deferred:
            continue
        if isinstance(node, ast.ImportFrom) and node.module:
            found.add(node.module)
        elif isinstance(node, ast.Import):
            found |= {alias.name for alias in node.names}
    return found


def _module_graph() -> dict[str, set[str]]:
    graph: dict[str, set[str]] = defaultdict(set)
    for module in MODULES:
        for path in sorted((MODULES_ROOT / module).rglob("*.py")):
            for imported in _module_level_imports(path):
                if not imported.startswith("acmis.modules."):
                    continue
                other = imported.split(".")[2]
                if other != module:
                    graph[module].add(other)
    return dict(graph)


def test_the_module_import_graph_is_acyclic() -> None:
    """No two modules import each other at import time.

    Cross-module use is expected — admissions enrols a student, learning writes
    to a mark sheet. What must not happen is a *cycle* at import time: the
    module that would close one uses a function-local import instead, which is
    why `students.service` imports assessment inside a function.
    """
    graph = _module_graph()
    state: dict[str, int] = {}
    cycles: list[list[str]] = []

    def visit(node: str, path: list[str]) -> None:
        state[node] = 1
        for neighbour in sorted(graph.get(node, ())):
            if state.get(neighbour, 0) == 1:
                cycles.append([*path, node, neighbour])
            elif state.get(neighbour, 0) == 0:
                visit(neighbour, [*path, node])
        state[node] = 2

    for module in MODULES:
        if state.get(module, 0) == 0:
            visit(module, [])

    assert not cycles, (
        "modules import each other at import time; break the cycle with a "
        f"function-local import in the dependent direction: {cycles}"
    )


#: Files allowed to import most of the codebase, and why.
#:
#: * `modules/descriptors.py` maps every domain object to policy attributes.
#: * `modules/registry.py` exists to complete SQLAlchemy's class registry, so
#:   importing everything is its whole job.
#: * `modules/tenancy/demo.py` builds a whole institution's worth of data.
#:
#: Anything else importing this widely is a sign that logic has drifted out of
#: a module into a shared file.
WIDE_BY_DESIGN = {
    "modules/descriptors.py",
    "modules/registry.py",
    "modules/tenancy/demo.py",
}


def test_only_the_registries_know_every_module() -> None:
    """Three files see the whole codebase, on purpose. Nothing else may."""
    breadth = {
        path.relative_to(API_ROOT).as_posix(): len(
            {
                imported.split(".")[2]
                for imported in _module_level_imports(path)
                if imported.startswith("acmis.modules.")
            }
        )
        for path in sorted(API_ROOT.rglob("*.py"))
    }
    wide = {name: count for name, count in breadth.items() if count >= 6}
    assert set(wide) <= WIDE_BY_DESIGN, (
        f"these files import most of the codebase at import time: {wide}"
    )


@pytest.mark.parametrize("module", MODULES)
def test_model_modules_import_no_other_module_at_runtime(module: str) -> None:
    """Model modules stay importable in any order.

    A cross-module relationship names its target as a string and lets
    SQLAlchemy's registry resolve it, so start-up has no cycle to untangle.
    The annotation may still be imported under `TYPE_CHECKING`.
    """
    path = MODULES_ROOT / module / "models.py"
    if not path.exists():
        pytest.skip(f"{module} has no models module")
    offences = sorted(
        imported
        for imported in _module_level_imports(path)
        if imported.startswith("acmis.modules.") and imported.split(".")[2] != module
    )
    assert not offences, (
        f"{module}/models.py imports {offences} at runtime; name the class as a "
        'string in the relationship ("CourseOffering") and import it under '
        "TYPE_CHECKING for the annotation"
    )


# ---------------------------------------------------------------------------
# The application itself
# ---------------------------------------------------------------------------


def test_middleware_order_is_the_one_the_security_model_assumes() -> None:
    """Outermost first: security headers, request context, errors, tenant, rate limit.

    Order is load-bearing, not cosmetic. The request id must exist before the
    first log line, or a failed request cannot be found in the logs — which is
    exactly the request someone needs to find. The error middleware must sit
    outside tenant resolution so that "unknown institution" is answered as a
    clean 400 rather than a traceback. And the rate limiter is innermost, so it
    is not spent on requests the outer layers reject.
    """
    from acmis.main import app

    installed = [getattr(m.cls, "__name__", type(m.cls).__name__) for m in app.user_middleware]
    expected = [
        "SecurityHeadersMiddleware",
        "RequestContextMiddleware",
        "ErrorMiddleware",
        "TenantMiddleware",
        "RateLimitMiddleware",
    ]
    assert [name for name in installed if name in expected] == expected, installed
    assert len(installed) == len(set(installed)), f"middleware installed twice: {installed}"


def _paths_of(router: object, prefix: str = "") -> set[str]:
    """Every concrete path a router serves, including through sub-routers.

    Recursive because this FastAPI version includes routers lazily: a
    sub-router appears as a wrapper holding the original, not as a set of
    routes copied into the parent.
    """
    found: set[str] = set()
    for route in getattr(router, "routes", ()):
        original = getattr(route, "original_router", None)
        if original is not None:
            context = getattr(route, "include_context", None)
            found |= _paths_of(original, prefix + getattr(context, "prefix", ""))
        elif hasattr(route, "path"):
            found.add(prefix + route.path)
    return found


def test_every_router_is_mounted() -> None:
    """A router nobody mounts is dead code that reads as a live feature.

    Checked against each router's own declared prefix rather than its filename
    — `routers/shared.py` deliberately serves `/reference`, because what it
    holds is reference data.
    """
    import importlib

    from acmis.main import app

    modules = sorted(
        path.stem for path in (API_ROOT / "routers").glob("*.py") if not path.stem.startswith("_")
    )
    assert modules, "no router modules found"

    # Read from the schema rather than `app.routes`: this FastAPI version
    # includes routers lazily, so `app.routes` holds wrappers, not endpoints.
    mounted = set(app.openapi()["paths"])
    assert len(mounted) > 100, "the API mounted almost nothing"

    unmounted: list[str] = []
    for name in modules:
        router = getattr(importlib.import_module(f"acmis.routers.{name}"), "router", None)
        if router is None:
            continue
        if router.prefix:
            if not any(router.prefix in path for path in mounted):
                unmounted.append(name)
        elif not _paths_of(router) & mounted:
            # Mounted at a root of its own — the standards paths, whose shapes
            # the specifications dictate, and the public endpoints.
            unmounted.append(name)

    assert not unmounted, f"router modules defined but never mounted: {unmounted}"


def test_the_openapi_schema_builds() -> None:
    """Every response model resolves.

    A schema that cannot be generated means a broken annotation somewhere, and
    the developer portal is served from this document.
    """
    from acmis.main import app

    schema = app.openapi()
    assert schema["info"]["title"]
    assert len(schema["paths"]) > 100
