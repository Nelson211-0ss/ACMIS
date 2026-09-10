"""Attribute-based access control for ACMIS.

    from acmis.core.abac import authorize, resources

    decision = authorize(
        engine=engine,
        action="result:enter",
        resource_type="course_result",
        resource=result,
    )
    return decision.filter(serialise(result))

Read in this order: `policy.py` for what a rule is, `expressions.py` for the
condition language and why it is not Rego, `engine.py` for how disagreement is
settled, `enforcement.py` for the one function endpoints call.
"""

from acmis.core.abac.enforcement import (
    LOGGED_READ_ACTIONS,
    authorize,
    bulk_decide,
    decide,
    enforce_writable,
)
from acmis.core.abac.engine import Decision, PolicyEngine, RuleTrace
from acmis.core.abac.policy import Combining, Effect, Policy, Rule, Target
from acmis.core.abac.registry import registry

__all__ = [
    "LOGGED_READ_ACTIONS",
    "Combining",
    "Decision",
    "Effect",
    "Policy",
    "PolicyEngine",
    "Rule",
    "RuleTrace",
    "Target",
    "authorize",
    "bulk_decide",
    "decide",
    "enforce_writable",
    "registry",
]
