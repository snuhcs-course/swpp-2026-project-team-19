"""Two owner applications from the same user that overlap on real connections (spec 3.11.2).

Both requests pass the service's duplicate check before either creates its row: the fake NTS check
waits until both requests reach it, and the service ends its read transaction before that call.
Only the partial unique indexes on pending applications then keep one of the two, and the loser
must answer `409 OWNER_APPLICATION_EXISTS` with the winner's id, as a sequential duplicate does.

Unlike the other API tests, these requests run on their own connections and really commit, so that
they can overlap; the rows are deleted afterwards.
"""

import threading
from datetime import date, datetime, timezone

import pytest
from sqlalchemy import select, text
from sqlalchemy.orm import Session

from app.adapters.business_verification import BusinessCheck
from app.core.errors import ApiError
from app.core.security import Principal
from app.models import BarOwnerApplication, BusinessStatus, OwnerApplicationStatus
from app.schemas.owner_application import ExistingBarApplicationInput, NewBarApplicationInput
from app.services.business_check import RecentBusinessChecks
from app.services.owner_applications import submit_application
from app.services.request_limits import BUSINESS_VERIFICATION, InMemoryDailyLimiter
from tests.factories import make_bar, make_user

SUBJECT = "concurrent-applicant"
NOW = datetime(2026, 11, 10, 3, tzinfo=timezone.utc)
FIELDS = {
    "businessRegistrationNumber": "1234567891",
    "representativeName": "김사장",
    "openingDate": "2020-03-02",
    "contactPhone": "010-1234-5678",
}


class BarrierVerifier:
    """Answers a match once every request has reached the NTS check."""

    def __init__(self, parties: int) -> None:
        self.barrier = threading.Barrier(parties, timeout=10)

    def verify(self, number: str, name: str, opened: date) -> BusinessCheck:
        self.barrier.wait()
        return BusinessCheck(True, BusinessStatus.ACTIVE)


@pytest.fixture
def committed(db_engine):
    """A committed applicant and bar: (applicant id, bar id). Everything is deleted afterwards."""
    with Session(db_engine) as session:
        applicant = make_user(session, SUBJECT)
        bar = make_bar(session, "Concurrent Claim Bar")
        session.commit()
        ids = applicant.id, bar.id
    try:
        yield ids
    finally:
        with db_engine.begin() as conn:
            conn.execute(text("DELETE FROM bar_owner_applications WHERE applicant_user_id = :id"), {"id": ids[0]})
            conn.execute(text("DELETE FROM users WHERE id = :id"), {"id": ids[0]})
            conn.execute(text("DELETE FROM bars WHERE id = :id"), {"id": ids[1]})


def submit_together(db_engine, requests) -> tuple[list, InMemoryDailyLimiter]:
    """Submit each request on its own connection at the same time; the results in request order."""
    verifier = BarrierVerifier(len(requests))
    limiter = InMemoryDailyLimiter()
    recent = RecentBusinessChecks()
    principal = Principal(kind="supabase", subject=SUBJECT, claims={})
    outcome: list = [None] * len(requests)

    def submit(index, request):
        with Session(db_engine) as session:
            try:
                application = submit_application(
                    session, principal, request, verifier=verifier, limiter=limiter, recent=recent, now=NOW
                )
                outcome[index] = application.id
            except Exception as error:  # noqa: BLE001 - recorded for the assertions below
                outcome[index] = error

    threads = [threading.Thread(target=submit, args=(i, request)) for i, request in enumerate(requests)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=30)
    return outcome, limiter


def pending_ids(db_engine, applicant_id) -> list:
    with Session(db_engine) as session:
        return session.scalars(
            select(BarOwnerApplication.id).where(
                BarOwnerApplication.applicant_user_id == applicant_id,
                BarOwnerApplication.status == OwnerApplicationStatus.PENDING,
            )
        ).all()


def new_bar_request(name: str) -> NewBarApplicationInput:
    return NewBarApplicationInput.model_validate(
        {"applicationType": "new_bar", "proposedBar": {"name": name, "address": "서울특별시 관악구 신림로 2"}, **FIELDS}
    )


def assert_one_wins(outcome, db_engine, applicant_id) -> None:
    created = [result for result in outcome if not isinstance(result, Exception)]
    refused = [result for result in outcome if isinstance(result, Exception)]
    assert len(created) == 1, outcome
    [error] = refused
    assert isinstance(error, ApiError), error
    assert (error.status_code, error.code) == (409, "OWNER_APPLICATION_EXISTS")
    assert error.details == {"applicationId": str(created[0])}
    assert pending_ids(db_engine, applicant_id) == created


def test_two_new_bar_applications_with_one_business_number_keep_one(db_engine, committed):
    applicant_id, _ = committed
    # Different proposed bars: the business number alone makes them the same application.
    outcome, limiter = submit_together(db_engine, [new_bar_request("신림 몰트 하우스"), new_bar_request("신림 몰트 2호점")])

    assert_one_wins(outcome, db_engine, applicant_id)
    # Both called NTS, so both are counted (3.11.2, step 4).
    assert limiter.used(SUBJECT, BUSINESS_VERIFICATION, NOW) == 2


def test_two_existing_bar_applications_for_one_bar_keep_one(db_engine, committed):
    applicant_id, bar_id = committed
    request = ExistingBarApplicationInput.model_validate(
        {"applicationType": "existing_bar", "barId": str(bar_id), **FIELDS}
    )

    outcome, _ = submit_together(db_engine, [request, request])

    assert_one_wins(outcome, db_engine, applicant_id)


def test_new_bar_applications_with_different_business_numbers_both_succeed(db_engine, committed):
    applicant_id, _ = committed
    other = new_bar_request("신림 몰트 2호점").model_copy(update={"businessRegistrationNumber": "1234567800"})

    outcome, _ = submit_together(db_engine, [new_bar_request("신림 몰트 하우스"), other])

    assert not any(isinstance(result, Exception) for result in outcome), outcome
    assert sorted(pending_ids(db_engine, applicant_id)) == sorted(outcome)
