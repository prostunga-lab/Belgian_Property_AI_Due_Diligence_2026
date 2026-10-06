from alembic import context

from app import config
from app.models import Base, engine

target_metadata = Base.metadata


def run_migrations_online() -> None:
    with engine.connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata, render_as_batch=config.DB_URL.startswith("sqlite"))
        with context.begin_transaction():
            context.run_migrations()


run_migrations_online()
