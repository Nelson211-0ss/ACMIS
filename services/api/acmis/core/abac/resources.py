"""Resource descriptors: turning a domain object into policy attributes.

A policy condition reads `resource.department_id`, `resource.status`,
`resource.is_locked`. Something has to decide what those mean for a
`CourseResult` versus a `FeeInvoice`, and the wrong place to decide it is
inside each endpoint — that is how two endpoints on the same table end up
exposing different attributes and one of them quietly stops matching a rule.

So every authorizable type registers exactly one descriptor. The descriptor is
the contract between the domain and the policy bundle, and the policy linter
checks the bundle only reads attributes some descriptor actually publishes.
"""

from __future__ import annotations

import uuid
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from typing import Any

_ATTR_ERROR = "resource descriptor for {t!r} is not registered"


@dataclass(frozen=True, slots=True)
class ResourceDescriptor:
    resource_type: str
    #: Attribute names this type publishes. Used by the linter and by the
    #: `/authz/describe` endpoint that the developer portal documents.
    attributes: frozenset[str]
    extractor: Callable[[Any], dict[str, Any]]
    #: Fields that may never leave the API unmasked without an explicit permit
    #: naming them. Belt-and-braces on top of `mask_fields`: forgetting to mask
    #: is a mistake, and the expensive mistakes cluster in a knowable set of
    #: fields.
    protected_fields: frozenset[str] = field(default_factory=frozenset)
    label: Callable[[Any], str] | None = None


_registry: dict[str, ResourceDescriptor] = {}


def register(
    resource_type: str,
    *,
    attributes: frozenset[str] | set[str] | tuple[str, ...],
    protected_fields: frozenset[str] | set[str] | tuple[str, ...] = (),
    label: Callable[[Any], str] | None = None,
) -> Callable[[Callable[[Any], dict[str, Any]]], Callable[[Any], dict[str, Any]]]:
    def decorate(fn: Callable[[Any], dict[str, Any]]) -> Callable[[Any], dict[str, Any]]:
        _registry[resource_type] = ResourceDescriptor(
            resource_type=resource_type,
            attributes=frozenset(attributes),
            extractor=fn,
            protected_fields=frozenset(protected_fields),
            label=label,
        )
        return fn

    return decorate


def describe(resource_type: str, obj: Any) -> dict[str, Any]:
    """Extract policy attributes from a domain object.

    A `None` object yields `{}` — the "class-level" decision, asked before a
    record exists (may this actor create a course result at all?). It deny-fails
    any rule that conditions on a record's own attributes, which is right: you
    cannot decide "the examiner owns this course" before you know which course.
    """
    descriptor = _registry.get(resource_type)
    if descriptor is None:
        raise KeyError(_ATTR_ERROR.format(t=resource_type))
    if obj is None:
        return {}
    if isinstance(obj, Mapping):
        return {k: _plain(v) for k, v in obj.items()}
    return {k: _plain(v) for k, v in descriptor.extractor(obj).items()}


def label_for(resource_type: str, obj: Any) -> str | None:
    descriptor = _registry.get(resource_type)
    if descriptor is None or descriptor.label is None or obj is None:
        return None
    try:
        return descriptor.label(obj)
    except Exception:  # a label is for humans; never fail a request over one
        return None


def protected_fields(resource_type: str) -> frozenset[str]:
    descriptor = _registry.get(resource_type)
    return descriptor.protected_fields if descriptor else frozenset()


def known_types() -> tuple[str, ...]:
    return tuple(sorted(_registry))


def published_attributes() -> dict[str, frozenset[str]]:
    return {t: d.attributes for t, d in _registry.items()}


def _plain(value: Any) -> Any:
    if isinstance(value, uuid.UUID):
        return str(value)
    if isinstance(value, (set, frozenset)):
        return sorted(_plain(v) for v in value)
    if isinstance(value, (list, tuple)):
        return [_plain(v) for v in value]
    if hasattr(value, "value") and hasattr(value, "name"):  # enum
        return str(value.value)
    return value
