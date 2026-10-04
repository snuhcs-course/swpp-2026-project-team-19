from functools import lru_cache

from sqlalchemy import Engine, create_engine

from app.core.config import get_database_url


@lru_cache(maxsize=1)
def get_engine() -> Engine:
    """Create the engine lazily so API startup does not require a live database."""
    return create_engine(get_database_url(), pool_pre_ping=True)
