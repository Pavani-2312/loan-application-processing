"""
src/repository/database.py

Engine creation, WAL mode configuration, and session factory.
Per docs/02_Architecture.md §6: relies on SQLite WAL mode + optimistic locking.
No in-process write lock is used — that was explicitly removed in review.
"""
from __future__ import annotations

from pathlib import Path

from sqlalchemy import Engine, create_engine, event, text
from sqlalchemy.orm import Session, sessionmaker

from src.repository.models import Base


def _configure_wal(dbapi_connection, connection_record) -> None:  # noqa: ARG001
    """Enable WAL mode and foreign keys on every new connection."""
    cursor = dbapi_connection.cursor()
    cursor.execute("PRAGMA journal_mode=WAL")
    cursor.execute("PRAGMA foreign_keys=ON")
    cursor.close()


def create_db_engine(db_path: str | Path) -> Engine:
    """Create and configure the SQLAlchemy engine for the given SQLite path."""
    engine = create_engine(
        f"sqlite:///{db_path}",
        connect_args={"check_same_thread": False},
        echo=False,
    )
    event.listen(engine, "connect", _configure_wal)
    return engine


def init_db(engine: Engine) -> None:
    """Create all tables if they don't exist yet (idempotent)."""
    Base.metadata.create_all(engine)


def get_session_factory(engine: Engine) -> sessionmaker[Session]:
    return sessionmaker(bind=engine, autoflush=False, autocommit=False)
