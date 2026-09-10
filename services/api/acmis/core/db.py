"""Database access for a database-per-tenant deployment.

Two planes:

* **Control plane** — one database (`acmis_control`) holding the tenant
  registry, platform staff, API clients and the platform audit stream. One
  engine, created at import time, lives for the life of the process.
* **Tenant plane** — one database per university. Engines are built lazily on
  first use and kept in an LRU registry, because a deployment may know about
  300 tenants while only 40 are awake at 09:00 on a Monday.

Why database-per-tenant at all, when a shared schema with a `tenant_id` column
is cheaper to operate? Because of what this data is. A student's transcript is
the evidence in a degree-award dispute that may be litigated years later; a
missing `WHERE tenant_id = ?` in one query is a cross-university data breach
and, worse, a *silent* one. Here the isolation is enforced by the connection,
not by developer discipline: there is no query you can write in tenant A's
session that can see tenant B's rows. It also means a university can be handed
a dump of exactly its own data on exit, restored to a point in time without
touching anyone else, and migrated to its own cluster when it outgrows the
shared one — all things a regulator or a vice-chancellor eventually asks for.

The cost is real and paid here: migrations must fan out (see
`acmis.modules.tenancy.provisioning`), connection counts multiply, and
cross-tenant reporting must go through the aggregation job rather than a
`GROUP BY`. Those are operational problems with known solutions. A leak
between two universities' student records is not.
"""

from __future__ import annotations

import threading
from collections import OrderedDict
from collections.abc import Iterator
from contextlib import contextmanager
from typing import Any

import structlog
from sqlalchemy import Engine, create_engine, event, text
from sqlalchemy.orm import Session, sessionmaker

from acmis.core.config import settings

log = structlog.get_logger(__name__)


# ---------------------------------------------------------------------------
# Control plane
# ---------------------------------------------------------------------------

control_engine: Engine = create_engine(
    str(settings.control_database_url),
    pool_pre_ping=True,
    pool_size=10,
    max_overflow=10,
    pool_recycle=settings.tenant_pool_recycle_seconds,
    echo=settings.sql_echo,
    future=True,
)

ControlSessionLocal = sessionmaker(
    bind=control_engine, autoflush=False, autocommit=False, expire_on_commit=False
)


def control_session() -> Iterator[Session]:
    """FastAPI dependency yielding a control-plane session."""
    session = ControlSessionLocal()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


@contextmanager
def control_session_ctx() -> Iterator[Session]:
    """Same as `control_session` for use outside a request (jobs, CLI)."""
    session = ControlSessionLocal()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


# ---------------------------------------------------------------------------
# Tenant plane
# ---------------------------------------------------------------------------


class TenantEngineRegistry:
    """LRU cache of tenant engines.

    Thread-safe because uvicorn runs sync endpoints in a threadpool: two
    requests for the same cold tenant can arrive on different threads at the
    same time, and building two engines would silently double that tenant's
    connection budget.

    Eviction disposes the engine, which closes its idle connections. An engine
    evicted while a request still holds a checked-out connection stays alive
    until that connection is returned — `dispose()` does not sever in-flight
    work.
    """

    def __init__(self, max_size: int) -> None:
        self._max_size = max_size
        self._engines: OrderedDict[str, Engine] = OrderedDict()
        self._lock = threading.RLock()

    def get(self, key: str, dsn: str) -> Engine:
        with self._lock:
            engine = self._engines.get(key)
            if engine is not None:
                self._engines.move_to_end(key)
                return engine

            engine = create_engine(
                dsn,
                pool_pre_ping=True,
                pool_size=settings.tenant_pool_size,
                max_overflow=settings.tenant_pool_max_overflow,
                pool_recycle=settings.tenant_pool_recycle_seconds,
                echo=settings.sql_echo,
                future=True,
                connect_args={"application_name": f"acmis:{key}"},
            )
            _install_statement_guard(engine, key)
            self._engines[key] = engine
            self._engines.move_to_end(key)

            while len(self._engines) > self._max_size:
                evicted_key, evicted = self._engines.popitem(last=False)
                log.info("tenant_engine_evicted", tenant=evicted_key)
                evicted.dispose()

            log.info("tenant_engine_opened", tenant=key, live=len(self._engines))
            return engine

    def forget(self, key: str) -> None:
        """Drop an engine — used when a tenant is suspended or its DSN rotates."""
        with self._lock:
            engine = self._engines.pop(key, None)
        if engine is not None:
            engine.dispose()
            log.info("tenant_engine_closed", tenant=key)

    def dispose_all(self) -> None:
        with self._lock:
            engines = list(self._engines.values())
            self._engines.clear()
        for engine in engines:
            engine.dispose()

    @property
    def live(self) -> int:
        with self._lock:
            return len(self._engines)


_registry = TenantEngineRegistry(settings.tenant_engine_cache_size)


def _install_statement_guard(engine: Engine, tenant_key: str) -> None:
    """Stamp every connection with the tenant it belongs to.

    Two purposes. `SET application_name` puts the tenant slug in
    `pg_stat_activity`, so a DBA looking at a stuck query knows whose it is.
    The session-level `acmis.tenant` GUC is readable from SQL, which lets audit
    triggers and row-level policies inside the tenant database assert they are
    running where they think they are.
    """

    @event.listens_for(engine, "connect")
    def _on_connect(dbapi_conn: Any, _record: Any) -> None:  # pragma: no cover - driver hook
        # `set_config` for both, not `SET`: Postgres's `SET` is a utility
        # statement and takes no bind parameters, so `SET application_name =
        # %s` is a syntax error. Going through `set_config` keeps the value
        # parameterised, which matters because the tenant slug reaches here
        # from a Host header.
        with dbapi_conn.cursor() as cur:
            cur.execute(
                "SELECT set_config('application_name', %s, false)",
                (f"acmis:{tenant_key}",),
            )
            cur.execute("SELECT set_config('acmis.tenant', %s, false)", (tenant_key,))


def tenant_engine(*, key: str, dsn: str) -> Engine:
    return _registry.get(key, dsn)


def forget_tenant_engine(key: str) -> None:
    _registry.forget(key)


def live_tenant_engines() -> int:
    return _registry.live


def dispose_all_engines() -> None:
    _registry.dispose_all()
    control_engine.dispose()


@contextmanager
def tenant_session_ctx(*, key: str, dsn: str) -> Iterator[Session]:
    """Open a tenant session outside a request (jobs, migrations, seeding)."""
    engine = tenant_engine(key=key, dsn=dsn)
    session = Session(bind=engine, autoflush=False, expire_on_commit=False)
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def database_exists(dsn: str) -> bool:
    """Cheap existence probe used by provisioning and health checks."""
    admin_dsn, _, database = dsn.rpartition("/")
    engine = create_engine(f"{admin_dsn}/postgres", isolation_level="AUTOCOMMIT")
    try:
        with engine.connect() as conn:
            found = conn.execute(
                text("SELECT 1 FROM pg_database WHERE datname = :name"), {"name": database}
            ).scalar()
        return bool(found)
    finally:
        engine.dispose()
