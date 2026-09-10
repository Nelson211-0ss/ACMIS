"""Alembic environment for a tenant database.

The URL is supplied by the caller — `provisioning.migrate_tenant` sets it per
tenant, and the CLI takes `-x url=...`. There is deliberately no default: a
tenant migration with a fallback URL is a migration applied to whichever
database the fallback happened to name.
"""

from __future__ import annotations

from logging.config import fileConfig

from sqlalchemy import engine_from_config, pool

from acmis.core.models import TenantBase

# Importing every tenant module registers its tables on the metadata. All of
# them, explicitly: a module missing from this list is a set of tables that
# quietly never gets created.
from acmis.modules.admissions import models as _admissions  # noqa: F401
from acmis.modules.assessment import models as _assessment  # noqa: F401
from acmis.modules.curriculum import models as _curriculum  # noqa: F401
from acmis.modules.developers import models as _developers  # noqa: F401
from acmis.modules.elections import models as _elections  # noqa: F401
from acmis.modules.finance import models as _finance  # noqa: F401
from acmis.modules.governance import models as _governance  # noqa: F401
from acmis.modules.identity import models as _identity  # noqa: F401
from acmis.modules.interop import models as _interop  # noqa: F401
from acmis.modules.learning import models as _learning  # noqa: F401
from acmis.modules.library import models as _library  # noqa: F401
from acmis.modules.people import models as _people  # noqa: F401
from acmis.modules.quality import models as _quality  # noqa: F401
from acmis.modules.shared import models as _shared  # noqa: F401
from acmis.modules.students import models as _students  # noqa: F401
from alembic import context

config = context.config
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = TenantBase.metadata

_url = context.get_x_argument(as_dictionary=True).get("url")
if _url:
    config.set_main_option("sqlalchemy.url", _url)


def include_object(obj, name, type_, reflected, compare_to):
    if type_ == "table":
        return name in target_metadata.tables
    return True


def run_migrations_offline() -> None:
    context.configure(
        url=config.get_main_option("sqlalchemy.url"),
        target_metadata=target_metadata,
        literal_binds=True,
        include_object=include_object,
        compare_type=True,
        compare_server_default=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    connectable = config.attributes.get("connection")
    if connectable is not None:
        # Reused connection, for the in-process fan-out.
        context.configure(
            connection=connectable,
            target_metadata=target_metadata,
            include_object=include_object,
            compare_type=True,
        )
        with context.begin_transaction():
            context.run_migrations()
        return

    engine = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    with engine.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            include_object=include_object,
            compare_type=True,
            compare_server_default=True,
        )
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
