"""Database engine and session lifecycle helpers.

Scripts can create their own session factory, while FastAPI initializes one
singleton engine during app startup and reuses its connection pool per request.
"""

from __future__ import annotations

from collections.abc import Generator
from contextlib import contextmanager

from sqlalchemy import create_engine
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker


_engine: Engine | None = None
_session_factory: sessionmaker[Session] | None = None


def make_engine(database_url: str):
    """Create a SQLAlchemy engine with stale-connection protection enabled."""

    return create_engine(database_url, future=True, pool_pre_ping=True)


def make_session_factory(database_url: str) -> sessionmaker[Session]:
    """Create an independent session factory for one-off scripts."""

    return sessionmaker(bind=make_engine(database_url), autoflush=False, future=True)


def init_engine(database_url: str) -> Engine:
    """Initialize the process-wide engine used by FastAPI."""

    global _engine, _session_factory
    if _engine is None:
        _engine = make_engine(database_url)
        _session_factory = sessionmaker(bind=_engine, autoflush=False, future=True)
    return _engine


def dispose_engine() -> None:
    """Close the process-wide engine, usually during FastAPI shutdown."""

    global _engine, _session_factory
    if _engine is not None:
        _engine.dispose()
    _engine = None
    _session_factory = None


def get_session_factory() -> sessionmaker[Session]:
    """Return the initialized FastAPI session factory."""

    if _session_factory is None:
        raise RuntimeError("Database engine is not initialized.")
    return _session_factory


@contextmanager
def session_scope() -> Generator[Session, None, None]:
    """Yield one SQLAlchemy session and close it when the caller is done."""

    session_factory = get_session_factory()
    with session_factory() as session:
        yield session


def get_session() -> Generator[Session, None, None]:
    """FastAPI dependency that provides one DB session per request."""

    with session_scope() as session:
        yield session
