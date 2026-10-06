from collections.abc import Callable, Iterator
from contextlib import AbstractContextManager
from functools import lru_cache

from sqlalchemy import Engine, create_engine
from sqlalchemy.orm import Session

from app.core.config import get_database_url


@lru_cache(maxsize=1)
def get_engine() -> Engine:
    """Create the engine lazily so API startup does not require a live database."""
    return create_engine(get_database_url(), pool_pre_ping=True)


def get_session() -> Iterator[Session]:
    """FastAPI dependency yielding one session per request. Tests override it."""
    with Session(get_engine()) as session:
        yield session


def get_session_factory() -> Callable[[], AbstractContextManager[Session]]:
    """FastAPI dependency for work that outlives the request, such as background processing.

    Each call of the returned factory opens a new session; tests override it.
    """
    return lambda: Session(get_engine())


def get_serializable_session_factory() -> Callable[[], AbstractContextManager[Session]]:
    """FastAPI dependency for review submission, whose transaction runs at SERIALIZABLE and is
    retried as a whole on a serialization failure. Tests override it."""
    engine = get_engine().execution_options(isolation_level="SERIALIZABLE")
    return lambda: Session(engine)
