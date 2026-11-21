"""SQLAlchemy database configuration, session factory, and schema helpers."""

from __future__ import annotations

import os
from collections.abc import Generator
from pathlib import Path

from dotenv import load_dotenv
from sqlalchemy import Engine, create_engine, event
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

_BACKEND_DIR = Path(__file__).resolve().parents[2]
load_dotenv(_BACKEND_DIR / ".env")

DEFAULT_SQLITE_URL = f"sqlite:///{(_BACKEND_DIR / 'awsense.db').as_posix()}"


def get_database_url() -> str:
    """Return the configured database URL, falling back to local SQLite."""
    return os.getenv("DATABASE_URL") or DEFAULT_SQLITE_URL


class Base(DeclarativeBase):
    """Base declarative class for all ORM entities."""


def build_engine(database_url: str | None = None) -> Engine:
    """Create a SQLAlchemy engine configured for PostgreSQL or SQLite."""
    url = database_url or get_database_url()
    echo = os.getenv("SQL_ECHO", "false").lower() == "true"

    connect_args: dict[str, object] = {}
    if url.startswith("sqlite"):
        connect_args["check_same_thread"] = False

    db_engine = create_engine(
        url,
        echo=echo,
        pool_pre_ping=not url.startswith("sqlite"),
        connect_args=connect_args,
    )

    if url.startswith("sqlite"):
        @event.listens_for(db_engine, "connect")
        def _set_sqlite_pragma(dbapi_connection: object, _: object) -> None:
            cursor = dbapi_connection.cursor()  # type: ignore[attr-defined]
            cursor.execute("PRAGMA foreign_keys=ON")
            cursor.close()

    return db_engine


engine: Engine = build_engine()
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


def create_tables(target_engine: Engine | None = None) -> None:
    """Create all ORM tables on the target database engine."""
    # Import entities before create_all so all table definitions are registered on Base.
    import app.models.entities  # noqa: F401

    Base.metadata.create_all(bind=target_engine or engine)


def get_db() -> Generator[Session, None, None]:
    """Yield a scoped database session for request handlers."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
