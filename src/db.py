"""Database connection and session management."""

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from src.config import DATABASE_URL, SQLITE_URL
from src.models import Base


def get_engine(url: str | None = None, echo: bool = False):
    """Create a SQLAlchemy engine.

    Falls back to SQLite if no URL provided and the default Postgres isn't reachable.
    """
    target_url = url or DATABASE_URL
    try:
        engine = create_engine(target_url, echo=echo)
        with engine.connect() as conn:
            conn.exec_driver_sql("SELECT 1")
        return engine
    except Exception:
        if url is not None:
            raise
        # Fallback to SQLite for local dev
        return create_engine(SQLITE_URL, echo=echo)


def get_engine_simple(url: str | None = None, echo: bool = False):
    """Create a SQLAlchemy engine without connection testing."""
    return create_engine(url or DATABASE_URL, echo=echo)


def create_tables(engine=None):
    """Create all tables from the ORM models."""
    if engine is None:
        engine = get_engine()
    Base.metadata.create_all(engine)
    return engine


def get_session_factory(engine=None) -> sessionmaker[Session]:
    """Return a session factory bound to the given engine."""
    if engine is None:
        engine = get_engine()
    return sessionmaker(bind=engine)
