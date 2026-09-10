"""Shared fixtures.

Everything here runs without a database. The tests that need one live behind
the `postgres` marker and are skipped unless `ACMIS_TEST_DSN` is set — a unit
suite that cannot run on a laptop with no Docker running is a unit suite people
stop running.
"""

from __future__ import annotations

import os
from collections.abc import Iterator
from pathlib import Path

import pytest

from acmis.core.abac.engine import PolicyEngine
from acmis.core.abac.loader import build_engine, load_builtin_policies

POLICY_DIR = Path(__file__).resolve().parent.parent / "acmis" / "policies"


@pytest.fixture(scope="session")
def engine() -> PolicyEngine:
    """The real, shipped policy bundle. Not a fixture bundle.

    A test bundle would pass while the shipped one denies the registrar, which
    is exactly the class of bug these tests exist to catch.
    """
    return build_engine(load_builtin_policies(str(POLICY_DIR)))


@pytest.fixture
def dsn() -> Iterator[str]:
    value = os.environ.get("ACMIS_TEST_DSN")
    if not value:
        pytest.skip("ACMIS_TEST_DSN is not set")
    yield value
