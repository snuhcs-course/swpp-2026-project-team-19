# AI-generated with Claude Code/Claude Opus 5.5 (Haeul Yang, 2026-10-20). Reviewed by Haeul Yang.
"""Record the SQL a request runs, to check that the number of queries does not grow with the data."""

from collections.abc import Iterator
from contextlib import contextmanager

from sqlalchemy import event
from sqlalchemy.orm import Session


@contextmanager
def recorded_statements(db_session: Session) -> Iterator[list[str]]:
    """Statements run on the test connection inside the block; `client` requests use it too."""
    statements: list[str] = []

    def record(conn, cursor, statement, parameters, context, executemany):
        statements.append(statement)

    connection = db_session.connection()
    event.listen(connection, "before_cursor_execute", record)
    try:
        yield statements
    finally:
        event.remove(connection, "before_cursor_execute", record)
