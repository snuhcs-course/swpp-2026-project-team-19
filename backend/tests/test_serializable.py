"""run_serializable: one transaction per attempt, retried only on write conflicts."""

from contextlib import contextmanager

import pytest
from sqlalchemy import text
from sqlalchemy.exc import OperationalError

from app.core.errors import ApiError
from app.services import serializable
from app.services.serializable import CATALOG_UNIQUE_CONSTRAINTS, MAX_ATTEMPTS, run_serializable, write_conflict

CONFLICT = write_conflict("잠시 후 다시 시도해 주세요.")


class _Diagnostic:
    def __init__(self, constraint_name: str | None) -> None:
        self.constraint_name = constraint_name


class _DatabaseError(Exception):
    def __init__(self, sqlstate: str, constraint: str | None = None) -> None:
        self.sqlstate = sqlstate
        self.diag = _Diagnostic(constraint)


def db_error(sqlstate: str, constraint: str | None = None) -> OperationalError:
    return OperationalError("UPDATE ...", {}, _DatabaseError(sqlstate, constraint))


class FakeSession:
    def __init__(self, log: list[str]) -> None:
        self.log = log

    def commit(self) -> None:
        self.log.append("commit")

    def rollback(self) -> None:
        self.log.append("rollback")


@pytest.fixture
def log(monkeypatch) -> list[str]:
    entries: list[str] = []
    monkeypatch.setattr(serializable, "sleep", lambda seconds: entries.append("sleep"))
    return entries


def factory(log: list[str]):
    @contextmanager
    def open_session():
        log.append("open")
        yield FakeSession(log)

    return open_session


def failing(*errors: BaseException):
    """work that raises each error in turn, then returns "done"."""
    pending = list(errors)

    def work(session):
        if pending:
            raise pending.pop(0)
        return "done"

    return work


def test_the_result_is_committed(log):
    assert run_serializable(factory(log), failing(), label="test", conflict=CONFLICT) == "done"
    assert log == ["open", "commit"]


@pytest.mark.parametrize(
    "error",
    [
        db_error("40001"),
        db_error("40P01"),
        *(db_error("23505", constraint) for constraint in sorted(CATALOG_UNIQUE_CONSTRAINTS)),
    ],
    ids=["serialization failure", "deadlock", *(f"duplicate {c}" for c in sorted(CATALOG_UNIQUE_CONSTRAINTS))],
)
def test_a_write_conflict_is_retried_in_a_new_session(log, error):
    result = run_serializable(factory(log), failing(error), label="test", conflict=CONFLICT)

    assert result == "done"
    assert log == ["open", "rollback", "sleep", "open", "commit"]


def test_conflicts_on_every_attempt_raise_the_callers_error(log):
    work = failing(*(db_error("40001") for _ in range(MAX_ATTEMPTS)))

    with pytest.raises(ApiError) as caught:
        run_serializable(factory(log), work, label="test", conflict=CONFLICT)

    assert caught.value is CONFLICT
    assert (caught.value.status_code, caught.value.code) == (503, "TEMPORARY_WRITE_CONFLICT")
    assert log.count("open") == MAX_ATTEMPTS
    assert log.count("sleep") == MAX_ATTEMPTS - 1


@pytest.mark.parametrize(
    "error",
    [
        db_error("23505", "uq_menu_board_entries_menu_board_id_sort_order"),
        db_error("23503"),
        ApiError(409, "MENU_OUTDATED", "outdated"),
    ],
    ids=["duplicate outside the catalog", "other database error", "api error"],
)
def test_other_errors_are_rolled_back_and_raised_without_a_retry(log, error):
    with pytest.raises(type(error)):
        run_serializable(factory(log), failing(error), label="test", conflict=CONFLICT)

    assert log == ["open", "rollback"]


def test_the_catalog_constraints_exist_under_these_names(db_session):
    """A renamed constraint would silently stop being retried."""
    names = set(
        db_session.scalars(
            text("SELECT conname FROM pg_constraint WHERE contype = 'u' AND conname = ANY(:names)"),
            {"names": list(CATALOG_UNIQUE_CONSTRAINTS)},
        )
    )

    assert names == CATALOG_UNIQUE_CONSTRAINTS
