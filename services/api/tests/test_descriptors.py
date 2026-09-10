"""The descriptor registry is the contract between the domain and the policies.

A descriptor that reaches for a model attribute which does not exist is the
worst kind of bug in this system. It does not raise: the extractors reach
across relationships with `getattr(obj, "assessment", None)`, so a missing
relationship publishes `None`, every rule conditioning on it silently fails to
match, and the result reads as "denied by default" — sending people to search
the policy files for a fault that is in a model.

That happened for real. `assessment_attempt` reached `attempt.assessment` for
its unit scope, that relationship did not exist, and so no marking rule could
ever match: nobody could mark an essay. The tests here read the extractors
statically and check every attribute against the mapper, so the next one fails
here rather than in production as a mystery denial.
"""

from __future__ import annotations

import ast
from pathlib import Path
from typing import Any

import pytest
from sqlalchemy import inspect as sa_inspect
from sqlalchemy.orm import class_mapper, configure_mappers

from acmis.core.abac import resources
from acmis.modules import descriptors as descriptors_module

SOURCE = Path(descriptors_module.__file__)
TREE = ast.parse(SOURCE.read_text())


def _registered() -> dict[str, ast.FunctionDef]:
    """Every `@resources.register("x")`-decorated extractor, by resource type."""
    found: dict[str, ast.FunctionDef] = {}
    for node in ast.walk(TREE):
        if not isinstance(node, ast.FunctionDef):
            continue
        for decorator in node.decorator_list:
            if (
                isinstance(decorator, ast.Call)
                and isinstance(decorator.func, ast.Attribute)
                and decorator.func.attr == "register"
                and decorator.args
                and isinstance(decorator.args[0], ast.Constant)
            ):
                found[str(decorator.args[0].value)] = node
    return found


EXTRACTORS = _registered()


def _returned_keys(fn: ast.FunctionDef) -> tuple[set[str], bool]:
    keys: set[str] = set()
    spreads = False
    for node in ast.walk(fn):
        if not isinstance(node, ast.Return) or not isinstance(node.value, ast.Dict):
            continue
        for key in node.value.keys:
            if key is None:
                spreads = True
            elif isinstance(key, ast.Constant) and isinstance(key.value, str):
                keys.add(str(key.value))
    return keys, spreads


def _model_for(fn: ast.FunctionDef) -> Any | None:
    """The mapped class the extractor is annotated to take.

    Annotations look like `stu.Student` or `learn.Attempt` — module aliases
    imported at the top of the descriptors module, so they resolve through it.
    """
    if not fn.args.args or fn.args.args[0].annotation is None:
        return None
    annotation = fn.args.args[0].annotation
    if not (isinstance(annotation, ast.Attribute) and isinstance(annotation.value, ast.Name)):
        return None
    module = getattr(descriptors_module, annotation.value.id, None)
    return getattr(module, annotation.attr, None)


def _attributes_read(fn: ast.FunctionDef) -> set[tuple[str, ...]]:
    """Attribute paths read off the extractor's parameter.

    `a.assessment.course_offering_id` yields `("assessment", "course_offering_id")`;
    `getattr(x, "assessment", None)` yields `("assessment",)` when `x` is the
    parameter. Anything reached through a local name is followed one hop by
    resolving that name's assignment, which is how every extractor here is
    written.
    """
    parameter = fn.args.args[0].arg
    # local name -> the path it was assigned from, e.g. sheet = getattr(r, "mark_sheet", None)
    aliases: dict[str, tuple[str, ...]] = {}
    for node in ast.walk(fn):
        if isinstance(node, ast.Assign) and len(node.targets) == 1:
            target = node.targets[0]
            if not isinstance(target, ast.Name):
                continue
            path = _path_of(node.value, parameter, aliases)
            if path:
                aliases[target.id] = path

    found: set[tuple[str, ...]] = set()
    for node in ast.walk(fn):
        path = _path_of(node, parameter, aliases)
        if path:
            found.add(path)
    return found


def _path_of(
    node: ast.AST, parameter: str, aliases: dict[str, tuple[str, ...]]
) -> tuple[str, ...] | None:
    """Resolve one expression to an attribute path rooted at the parameter."""
    if isinstance(node, ast.Name):
        if node.id == parameter:
            return ()
        return aliases.get(node.id)
    if isinstance(node, ast.Attribute):
        base = _path_of(node.value, parameter, aliases)
        return None if base is None else (*base, node.attr)
    if (
        isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id == "getattr"
        and len(node.args) >= 2
        and isinstance(node.args[1], ast.Constant)
    ):
        base = _path_of(node.args[0], parameter, aliases)
        return None if base is None else (*base, str(node.args[1].value))
    return None


def _has_attribute(model: Any, name: str) -> bool:
    """Is `name` reachable on this mapped class?

    Columns, relationships, association proxies and plain Python properties all
    count — a descriptor is entitled to read any of them.
    """
    if hasattr(model, name):
        return True
    mapper = class_mapper(model)
    return name in mapper.attrs or name in mapper.all_orm_descriptors


def _related_class(model: Any, name: str) -> Any | None:
    relationships = sa_inspect(model).relationships
    if name in relationships:
        return relationships[name].mapper.class_
    return None


@pytest.fixture(scope="module", autouse=True)
def _mappers_configured() -> None:
    # Relationships are resolved lazily, so a `back_populates` naming an
    # attribute that does not exist only fails once the mappers are configured.
    configure_mappers()


def test_registry_and_source_agree() -> None:
    assert set(EXTRACTORS) == set(resources.known_types()), (
        "a descriptor is registered outside acmis/modules/descriptors.py; these "
        "tests read that file statically and would not see it"
    )


@pytest.mark.parametrize("resource_type", sorted(EXTRACTORS))
def test_extractor_reads_only_real_model_attributes(resource_type: str) -> None:
    """Every attribute the extractor reaches for exists on the model."""
    fn = EXTRACTORS[resource_type]
    model = _model_for(fn)
    if model is None or not hasattr(model, "__mapper__"):
        pytest.skip(f"{resource_type} takes no annotated mapped class")

    for path in sorted(_attributes_read(fn)):
        current: Any = model
        walked: list[str] = []
        for step in path:
            if current is None or not hasattr(current, "__mapper__"):
                break  # left the mapped graph; nothing more to check
            assert _has_attribute(current, step), (
                f"{resource_type}: descriptor reads "
                f"`{'.'.join([*walked, step])}` but {current.__name__} has no such "
                "attribute — the policy will see None and every rule reading it "
                "will silently fail to match"
            )
            walked.append(step)
            current = _related_class(current, step)


@pytest.mark.parametrize("resource_type", sorted(EXTRACTORS))
def test_returned_keys_are_declared(resource_type: str) -> None:
    """Nothing is published that the descriptor does not declare.

    An undeclared attribute is invisible to the bundle checks, so a rule with a
    typo in its name is not caught.
    """
    declared = resources.published_attributes()[resource_type]
    returned, _ = _returned_keys(EXTRACTORS[resource_type])
    undeclared = returned - set(declared)
    assert not undeclared, f"{resource_type} publishes {sorted(undeclared)} without declaring them"
