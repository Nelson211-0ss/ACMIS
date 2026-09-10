"""Alembic environment for the control-plane database.

Autogenerate is restricted to `ControlBase.metadata`. Without the filter it
would see every tenant table imported into the process and try to create them
here — the mistake that puts `student` in the platform database.
"""

from __future__ import annotations

from logging.config import fileConfig

from sqlalchemy import engine_from_config, pool

from acmis.core.config import settings
from acmis.core.models import ControlBase

# Importing the models registers them on the metadata.
from acmis.modules.tenancy import models as _tenancy  # noqa: F401
from alembic import context

config = context.config
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = ControlBase.metadata
config.set_main_option("sqlalchemy.url", str(settings.control_database_url))


def include_object(obj, name, type_, reflected, compare_to):
    """Only manage tables declared on `ControlBase`."""
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
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    with connectable.connect() as connection:
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
