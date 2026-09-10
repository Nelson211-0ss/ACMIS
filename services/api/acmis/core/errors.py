"""Domain errors and their HTTP shape.

Every error the API returns has a stable machine-readable `code`. Nine
frontend apps and any number of third-party integrations branch on these, and
matching on a human-readable message is how an integration breaks when someone
fixes a typo.
"""

from __future__ import annotations

from typing import Any

from fastapi import status

#: Starlette renamed this constant; pinning the number keeps both versions
#: working and the meaning is fixed by RFC 4918 regardless of the spelling.
UNPROCESSABLE_CONTENT = 422


class ACMISError(Exception):
    """Base for everything the API raises deliberately."""

    status_code: int = status.HTTP_400_BAD_REQUEST
    code: str = "acmis_error"
    message: str = "Request could not be completed."

    def __init__(
        self,
        message: str | None = None,
        *,
        code: str | None = None,
        details: dict[str, Any] | None = None,
    ) -> None:
        self.message = message or self.message
        self.code = code or self.code
        self.details = details or {}
        super().__init__(self.message)

    def to_payload(self) -> dict[str, Any]:
        payload: dict[str, Any] = {"code": self.code, "message": self.message}
        if self.details:
            payload["details"] = self.details
        return payload


class NotFound(ACMISError):
    status_code = status.HTTP_404_NOT_FOUND
    code = "not_found"
    message = "The requested record does not exist."


class Conflict(ACMISError):
    status_code = status.HTTP_409_CONFLICT
    code = "conflict"
    message = "The record was changed by someone else."


class ValidationFailed(ACMISError):
    status_code = UNPROCESSABLE_CONTENT
    code = "validation_failed"
    message = "Some fields are invalid."


class Unauthenticated(ACMISError):
    status_code = status.HTTP_401_UNAUTHORIZED
    code = "unauthenticated"
    message = "Sign in to continue."


class Forbidden(ACMISError):
    """Authorization denial.

    Deliberately says nothing about *why*, and nothing about whether the record
    exists. "You may not view results for student 21/U/1234" confirms that
    student exists to anyone who can guess a number; `explain_denials` adds the
    deciding policy id, and is refused in production.
    """

    status_code = status.HTTP_403_FORBIDDEN
    code = "forbidden"
    message = "You do not have permission to do that."


class TenantNotResolved(ACMISError):
    status_code = status.HTTP_400_BAD_REQUEST
    code = "tenant_not_resolved"
    message = "Could not determine which institution this request is for."


class TenantSuspended(ACMISError):
    status_code = status.HTTP_403_FORBIDDEN
    code = "tenant_suspended"
    message = "This institution's ACMIS subscription is not active."


class FeatureDisabled(ACMISError):
    status_code = status.HTTP_403_FORBIDDEN
    code = "feature_disabled"
    message = "This module is not enabled for your institution."


class RuleViolation(ACMISError):
    """An academic or financial regulation refused the action.

    Distinct from `ValidationFailed`: the payload was well-formed, but the
    institution's rules say no — registering 24 credit units against an
    18-unit cap, awarding a degree to a student with an unresolved retake,
    admitting past a programme's approved intake. The UI shows these
    differently, because the fix is an approval or a waiver, not a corrected
    field.
    """

    status_code = UNPROCESSABLE_CONTENT
    code = "rule_violation"
    message = "This action is not allowed by the institution's rules."

    def __init__(
        self,
        message: str | None = None,
        *,
        rule: str | None = None,
        code: str | None = None,
        details: dict[str, Any] | None = None,
        waivable_by: list[str] | None = None,
    ) -> None:
        merged = dict(details or {})
        if rule:
            merged["rule"] = rule
        if waivable_by:
            merged["waivable_by"] = waivable_by
        super().__init__(message, code=code, details=merged)


class RateLimited(ACMISError):
    status_code = status.HTTP_429_TOO_MANY_REQUESTS
    code = "rate_limited"
    message = "Too many requests. Try again shortly."


class ProvisioningError(ACMISError):
    status_code = status.HTTP_500_INTERNAL_SERVER_ERROR
    code = "provisioning_failed"
    message = "The institution could not be provisioned."


class UpstreamError(ACMISError):
    status_code = status.HTTP_502_BAD_GATEWAY
    code = "upstream_failed"
    message = "A dependency of this action is unavailable."
