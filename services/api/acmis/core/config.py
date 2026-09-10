"""Runtime configuration.

Everything the process needs to boot comes from the environment. Nothing here
is tenant-specific: a tenant's database URL, branding and feature flags live in
the control-plane database (see `acmis.modules.tenancy`), because tenants are
onboarded at runtime and a deployment must not be redeployed to add a
university.
"""

from __future__ import annotations

from functools import lru_cache
from typing import Literal

from pydantic import AnyUrl, Field, PostgresDsn, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

Environment = Literal["local", "test", "staging", "production"]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env", env_prefix="ACMIS_", extra="ignore", case_sensitive=False
    )

    environment: Environment = "local"
    debug: bool = False
    service_name: str = "acmis-api"

    # --- HTTP ---------------------------------------------------------------
    api_prefix: str = "/api/v1"
    #: Origins allowed to call the API with credentials. Every module app is a
    #: distinct origin in development, which is why this is a list and not one
    #: value. In production these are subdomains of the tenant's host.
    cors_origins: list[str] = Field(
        default_factory=lambda: [f"http://localhost:{p}" for p in range(3000, 3010)]
    )
    #: Host that serves the control plane UI (tenant provisioning, plan admin).
    control_plane_host: str = "admin.acmis.local"
    #: Suffix used to derive a tenant slug from a Host header:
    #: `juba.acmis.ac.ug` -> `juba`.
    tenant_host_suffix: str = "acmis.local"

    # --- Control-plane database --------------------------------------------
    #: Holds tenants, platform users, API clients, plans and the *platform*
    #: audit stream. Never holds student data.
    control_database_url: PostgresDsn = Field(
        default="postgresql+psycopg://acmis:acmis@localhost:5432/acmis_control"  # type: ignore[assignment]
    )

    # --- Tenant databases ---------------------------------------------------
    #: Template used to build a tenant DSN when the tenant record stores only a
    #: database name. `{database}` is substituted. Keeping a template means a
    #: fleet of 200 tenant databases on one cluster needs one secret, not 200.
    tenant_database_url_template: str = "postgresql+psycopg://acmis:acmis@localhost:5432/{database}"
    tenant_database_prefix: str = "acmis_t_"
    #: Per-tenant pool. Deliberately small: with database-per-tenant the pool
    #: count multiplies by the number of *active* tenants, not the number of
    #: registered ones, and idle engines are evicted (see core.db).
    tenant_pool_size: int = 5
    tenant_pool_max_overflow: int = 5
    tenant_pool_recycle_seconds: int = 1800
    #: How many tenant engines to keep hot. Beyond this the least-recently-used
    #: engine is disposed. 64 x (5 + 5) = 640 worst-case connections, which is
    #: why this and Postgres `max_connections` must be sized together.
    tenant_engine_cache_size: int = 64
    sql_echo: bool = False

    # --- Identity -----------------------------------------------------------

    # while this default is still in place, which is the real control.
    jwt_secret: str = "dev-only-insecure-change-me"  # noqa: S105
    jwt_algorithm: str = "HS256"
    access_token_ttl_seconds: int = 15 * 60
    refresh_token_ttl_seconds: int = 14 * 24 * 3600
    #: Argon2id parameters. Tuned so a single hash costs ~100ms on the target
    #: hardware; raise `argon2_time_cost` rather than lowering it.
    argon2_time_cost: int = 3
    argon2_memory_cost_kib: int = 65536
    argon2_parallelism: int = 2
    password_min_length: int = 12
    max_failed_logins: int = 8
    lockout_seconds: int = 900

    # --- Authorization ------------------------------------------------------
    #: Directory of ABAC policy bundles (YAML). Tenant overlays are loaded from
    #: the tenant database on top of these.
    policy_dir: str = "acmis/policies"
    #: When true a `deny` decision includes the policy id that produced it.
    #: Helpful in staging, an information leak in production.
    explain_denials: bool = False

    # --- Audit --------------------------------------------------------------
    #: Every mutating request writes an audit record. When this is false the
    #: process refuses to start outside `local`, because an ACMIS deployment
    #: without an audit trail cannot support a degree-award appeal.
    audit_enabled: bool = True
    audit_retention_days: int = 3653  # ten years — academic records outlive staff
    #: Field names whose values are redacted before they reach the audit trail.
    audit_redact_fields: tuple[str, ...] = (
        "password",
        "new_password",
        "current_password",
        "token",
        "refresh_token",
        "client_secret",
        "api_key",
        "secret",
        "authorization",
        "national_id",
        "bank_account",
    )

    # --- Infrastructure -----------------------------------------------------
    redis_url: AnyUrl = Field(default="redis://localhost:6379/0")  # type: ignore[assignment]
    s3_endpoint_url: str | None = None
    s3_bucket: str = "acmis-documents"
    s3_region: str = "eu-west-1"
    s3_access_key: str | None = None
    s3_secret_key: str | None = None
    max_upload_bytes: int = 10 * 1024 * 1024

    # --- Outbound -----------------------------------------------------------
    smtp_host: str | None = None
    smtp_port: int = 587
    smtp_user: str | None = None
    smtp_password: str | None = None
    mail_from: str = "no-reply@acmis.local"
    sms_provider: Literal["none", "africastalking", "twilio"] = "none"
    sms_api_key: str | None = None

    # --- Rate limiting ------------------------------------------------------
    rate_limit_enabled: bool = True
    rate_limit_per_minute: int = 300
    rate_limit_burst: int = 60

    @field_validator("cors_origins", mode="before")
    @classmethod
    def _split_origins(cls, v: object) -> object:
        if isinstance(v, str):
            return [o.strip() for o in v.split(",") if o.strip()]
        return v

    @property
    def is_production(self) -> bool:
        return self.environment == "production"

    def tenant_dsn(self, database: str) -> str:
        """Build a tenant DSN from a database name, or pass a full DSN through."""
        if "://" in database:
            return database
        return self.tenant_database_url_template.format(database=database)


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    settings = Settings()
    if settings.is_production:
        if settings.jwt_secret.startswith("dev-only"):
            raise RuntimeError("ACMIS_JWT_SECRET must be set in production")
        if not settings.audit_enabled:
            raise RuntimeError("audit cannot be disabled in production")
        if settings.explain_denials:
            raise RuntimeError("explain_denials leaks policy structure; disable in production")
    return settings


settings = get_settings()
