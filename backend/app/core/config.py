import os

from sqlalchemy.engine import URL

# libpq sslmode values. RDS accepts SSL; `require` makes the connection fail rather than
# fall back to plain text.
SSL_MODES = ("disable", "allow", "prefer", "require", "verify-ca", "verify-full")


def get_database_url() -> URL:
    """Build the PostgreSQL URL from environment variables when DB access is needed."""
    required = ("POSTGRES_HOST", "POSTGRES_USER", "POSTGRES_PASSWORD", "POSTGRES_DATABASE")
    missing = [name for name in required if not os.getenv(name)]
    if missing:
        names = ", ".join(missing)
        raise RuntimeError(f"Missing required database environment variables: {names}")

    sslmode = os.getenv("POSTGRES_SSLMODE")
    if sslmode and sslmode not in SSL_MODES:
        raise RuntimeError(f"POSTGRES_SSLMODE must be one of {', '.join(SSL_MODES)}, got {sslmode!r}")

    return URL.create(
        drivername="postgresql+psycopg",
        username=os.environ["POSTGRES_USER"],
        password=os.environ["POSTGRES_PASSWORD"],
        host=os.environ["POSTGRES_HOST"],
        port=int(os.getenv("POSTGRES_PORT", "5432")),
        database=os.environ["POSTGRES_DATABASE"],
        # Unset keeps libpq's default (prefer).
        query={"sslmode": sslmode} if sslmode else {},
    )
