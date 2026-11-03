"""The bar owner tables enforce the rules of docs/schema_guide.md 5.3 to 5.5 in the database."""

from datetime import datetime, timezone

import pytest
from alembic.autogenerate import compare_metadata
from alembic.migration import MigrationContext
from sqlalchemy.exc import IntegrityError

from app.db.base import Base
from app.models import (
    BarOwner,
    BusinessStatus,
    BusinessVerificationResult,
    OwnerApplicationStatus,
    OwnerApplicationType,
)
from tests.factories import make_application, make_application_menu_image, make_bar, make_owner, make_user

NOW = datetime(2026, 10, 28, 3, tzinfo=timezone.utc)


# compare_metadata warns about the extracted_items/products foreign key cycle, which is not ours.
@pytest.mark.filterwarnings("ignore:Cannot correctly sort tables")
def test_migrations_match_the_models(db_session):
    """Covers every table, so a model changed without a migration (or the reverse) fails here."""
    context = MigrationContext.configure(db_session.connection(), opts={"compare_type": True})

    assert compare_metadata(context, Base.metadata) == []


def test_defaults_and_both_application_types(db_session):
    applicant = make_user(db_session)
    existing = make_application(db_session, applicant, make_bar(db_session))
    new = make_application(db_session, applicant)
    db_session.refresh(existing)

    assert existing.status == OwnerApplicationStatus.PENDING
    assert existing.created_at is not None and existing.updated_at is not None
    assert new.application_type == OwnerApplicationType.NEW_BAR
    assert new.bar_id is None


@pytest.mark.parametrize(
    "change",
    [
        pytest.param({"bar_id": None}, id="existing_bar without a bar"),
        pytest.param({"proposed_bar_name": "Proposed"}, id="existing_bar with a proposed bar"),
        pytest.param({"business_registration_number": "12345-6789"}, id="business number not 10 digits"),
        pytest.param({"rejection_reason": "No"}, id="rejection reason while pending"),
        pytest.param({"reviewed_at": NOW}, id="reviewed while pending"),
        pytest.param({"business_status": BusinessStatus.ACTIVE}, id="business status without a match"),
    ],
)
def test_check_constraints_reject_inconsistent_existing_bar_rows(db_session, change):
    application = make_application(db_session, make_user(db_session), make_bar(db_session))

    for name, value in change.items():
        setattr(application, name, value)
    with pytest.raises(IntegrityError):
        db_session.flush()


@pytest.mark.parametrize(
    "change",
    [
        pytest.param({"proposed_address": None}, id="new_bar without an address"),
        pytest.param({"bar_id": "bar"}, id="pending new_bar with a bar"),
    ],
)
def test_check_constraints_reject_inconsistent_new_bar_rows(db_session, change):
    application = make_application(db_session, make_user(db_session))

    for name, value in change.items():
        setattr(application, name, make_bar(db_session).id if value == "bar" else value)
    with pytest.raises(IntegrityError):
        db_session.flush()


@pytest.mark.parametrize("column", ["rejection_reason", "reviewed_by_user_id"])
def test_rejected_rows_need_a_reason_and_a_reviewer(db_session, column):
    operator = make_user(db_session, "operator-subject")
    rejected = make_application(
        db_session,
        make_user(db_session),
        make_bar(db_session),
        status=OwnerApplicationStatus.REJECTED,
        reviewer=operator,
    )

    setattr(rejected, column, None)
    with pytest.raises(IntegrityError):
        db_session.flush()


def test_matched_rows_keep_a_business_status(db_session):
    application = make_application(db_session, make_user(db_session), make_bar(db_session))

    application.business_verification_result = BusinessVerificationResult.MATCHED
    application.business_status = BusinessStatus.CLOSED
    db_session.flush()


def test_an_approved_new_bar_application_holds_the_created_bar(db_session):
    operator = make_user(db_session, "operator-subject")
    application = make_application(
        db_session,
        make_user(db_session),
        make_bar(db_session),
        application_type=OwnerApplicationType.NEW_BAR,
        status=OwnerApplicationStatus.APPROVED,
        reviewer=operator,
    )

    assert application.bar_id is not None


def test_one_pending_application_per_user_and_bar(db_session):
    applicant, operator, bar = make_user(db_session), make_user(db_session, "operator-subject"), make_bar(db_session)
    make_application(db_session, applicant, bar, status=OwnerApplicationStatus.REJECTED, reviewer=operator)
    make_application(db_session, applicant, bar, status=OwnerApplicationStatus.CANCELED)
    make_application(db_session, applicant, bar)
    make_application(db_session, make_user(db_session, "other-subject"), bar)

    with pytest.raises(IntegrityError):
        make_application(db_session, applicant, bar)


def test_one_pending_new_bar_application_per_user_and_business_number(db_session):
    applicant = make_user(db_session)
    make_application(db_session, applicant, status=OwnerApplicationStatus.CANCELED)
    make_application(db_session, applicant)
    make_application(db_session, applicant, business_registration_number="1234567800")
    make_application(db_session, make_user(db_session, "other-subject"))

    with pytest.raises(IntegrityError):
        make_application(db_session, applicant)


def test_a_bar_has_at_most_one_current_owner(db_session):
    operator, bar = make_user(db_session, "operator-subject"), make_bar(db_session)
    first = make_owner(db_session, make_user(db_session), bar, operator)
    first.revoked_at, first.revoked_by_user_id = NOW, operator.id
    make_owner(db_session, make_user(db_session, "second-subject"), bar, operator)

    with pytest.raises(IntegrityError):
        make_owner(db_session, make_user(db_session, "third-subject"), bar, operator)


def test_revoking_records_who_revoked(db_session):
    operator = make_user(db_session, "operator-subject")
    owner = make_owner(db_session, make_user(db_session), make_bar(db_session), operator)

    owner.revoked_at = NOW
    with pytest.raises(IntegrityError):
        db_session.flush()


def test_an_application_grants_ownership_once(db_session):
    operator, bar = make_user(db_session, "operator-subject"), make_bar(db_session)
    owner = make_owner(db_session, make_user(db_session), bar, operator)
    owner.revoked_at, owner.revoked_by_user_id = NOW, operator.id
    db_session.add(BarOwner(bar_id=bar.id, user_id=owner.user_id, application_id=owner.application_id))

    with pytest.raises(IntegrityError):
        db_session.flush()


def test_application_menu_images_keep_one_row_per_order(db_session):
    application = make_application(db_session, make_user(db_session))
    image = make_application_menu_image(db_session, application)
    make_application_menu_image(db_session, application, image_order=2)
    make_application_menu_image(db_session, make_application(db_session, make_user(db_session, "other-subject")))
    db_session.refresh(image)

    assert image.uploaded_at is not None
    with pytest.raises(IntegrityError):
        make_application_menu_image(db_session, application)
