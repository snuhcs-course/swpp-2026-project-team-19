"""bar_photos enforces the rules of docs/schema_guide.md 5.8 in the database, whatever the API lets through.

The test session runs inside an outer transaction, so its commits never reach the deferred position
check; `SET CONSTRAINTS ... IMMEDIATE` runs the check that a real commit would.
"""

import pytest
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError

from tests.factories import make_bar, make_bar_photo


def _check_positions(session) -> None:
    session.flush()
    session.execute(text("SET CONSTRAINTS uq_bar_photos_sort_order IMMEDIATE"))


def test_a_new_photo_gets_its_upload_time_and_may_have_no_uploader(db_session):
    photo = make_bar_photo(db_session, make_bar(db_session))
    db_session.refresh(photo)

    assert photo.created_at is not None
    assert photo.uploaded_by_user_id is None


def test_the_same_file_cannot_be_added_twice_to_a_bar(db_session):
    bar = make_bar(db_session)
    make_bar_photo(db_session, bar, 1, content_sha256="a" * 64)

    with pytest.raises(IntegrityError):
        make_bar_photo(db_session, bar, 2, content_sha256="a" * 64)


def test_two_bars_may_have_the_same_file(db_session):
    make_bar_photo(db_session, make_bar(db_session, "One"), content_sha256="a" * 64)
    make_bar_photo(db_session, make_bar(db_session, "Two"), content_sha256="a" * 64)

    _check_positions(db_session)


def test_two_photos_of_a_bar_cannot_share_a_position(db_session):
    bar = make_bar(db_session)
    make_bar_photo(db_session, bar, 1)
    make_bar_photo(db_session, bar, 1, content_sha256="b" * 64)

    with pytest.raises(IntegrityError):
        _check_positions(db_session)


def test_positions_can_be_swapped_in_one_transaction(db_session):
    bar = make_bar(db_session)
    first, second = make_bar_photo(db_session, bar, 1), make_bar_photo(db_session, bar, 2)

    first.sort_order = 2
    db_session.flush()
    second.sort_order = 1
    _check_positions(db_session)
