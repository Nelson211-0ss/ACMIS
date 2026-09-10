"""Tenant resolution, which decides which database a request reaches.

The precedence here is a security boundary, not a convenience: a token issued
for one institution must not be redirectable at another's data by anything the
caller controls. And the host parser must be strict, because a loose one
silently resolves `127.0.0.1:8000` to a tenant called "127".
"""

from __future__ import annotations

import pytest

from acmis.core.tenant_resolver import slug_from_host


@pytest.mark.parametrize(
    ("host", "expected"),
    [
        # The suffix comes from settings; the default deployment domain is
        # `acmis.local`, so these are the shapes that name a tenant.
        ("makerere.acmis.local", "makerere"),
        ("MAKERERE.acmis.local", "makerere"),
        ("kyambogo.acmis.local:443", "kyambogo"),
        # Not a tenant: the apex, the control plane, a bare host or an address.
        ("acmis.local", None),
        ("admin.acmis.local", None),
        ("makerere.acmis.ac.ug", None),
        ("localhost", None),
        ("localhost:3000", None),
        ("127.0.0.1", None),
        ("127.0.0.1:8000", None),
        ("[::1]:8000", None),
        ("", None),
    ],
)
def test_slug_is_derived_only_from_a_real_subdomain(host: str, expected: str | None) -> None:
    """`127.0.0.1:8000` once yielded the tenant slug "127".

    Everything then resolved to a tenant that did not exist, so every request
    in development came back `tenant_not_resolved` — with the real cause two
    layers away from the error.
    """
    assert slug_from_host(host) == expected
