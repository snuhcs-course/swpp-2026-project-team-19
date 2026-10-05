from collections.abc import Iterator
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
