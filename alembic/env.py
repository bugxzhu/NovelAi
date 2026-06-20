from logging.config import fileConfig

from alembic import context

from app.config import settings
from app.memory.base import Base
from app.memory.session import _build_engine

# Ensure all models are imported so Base.metadata has every table registered
import app.memory.schema  # noqa: F401

config = context.config

# Interpret the config file for Python logging.
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# Set sqlalchemy.url from app settings (override any value in alembic.ini)
config.set_main_option("sqlalchemy.url", f"sqlite:///{settings.db_path}")

target_metadata = Base.metadata


def _include_object(object, name, type_, reflected, compare_to):
    """Skip sqlite-vec shadow tables under vec_chunks* during autogenerate.

    A vec0 virtual table (vec_chunks) is backed by several physical shadow
    tables (vec_chunks_rowids, vec_chunks_info, vec_chunks_chunks, etc.).
    SQLAlchemy introspects them as regular tables and would otherwise show up
    as "removed tables" in every autogenerate diff. They are managed entirely
    by the vec_chunks virtual table and must not appear in migrations.
    """
    if type_ == "table" and name.startswith("vec_chunks"):
        return False
    return True


def run_migrations_offline() -> None:
    """Run migrations in 'offline' mode (emit SQL to stdout)."""
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        render_as_batch=True,  # SQLite-friendly: batch mode for ALTER TABLE
        include_object=_include_object,
    )

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """Run migrations in 'online' mode (connect to DB and apply).

    Uses _build_engine from app.memory.session so the sqlite-vec extension
    (needed for vec0 virtual tables) is loaded on connect — same path as the
    runtime engine.
    """
    connectable = _build_engine(settings.db_path)

    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            render_as_batch=True,  # SQLite-friendly
            include_object=_include_object,
        )

        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
