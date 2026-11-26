"""The daily menu photo limit per user (I5-A2, spec 4.1). No database: the upload runs on a fake
session, so these tests also run where POSTGRES_TEST_DATABASE is not set."""

import inspect
import io
from datetime import UTC, date, datetime
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError
from sqlalchemy.exc import IntegrityError

from app.adapters.extraction import MockMenuExtractor
from app.api import deps
from app.api.permissions import require_active_bar_manager
from app.api.routes import menu_imports
from app.core.errors import ApiError
from app.core.security import Principal, get_current_user
from app.db.session import get_session, get_session_factory
from app.main import app
from app.models import Bar, BarStatus, ImportMode, ImportStatus, MenuImport
from app.schemas.request_limit import RequestLimitResetInput
from app.services import menu_import_processing, menu_import_upload
from app.services.menu_import_upload import MAX_IMAGES, ImageUpload, create_menu_import
from app.services.request_limits import (
    BUSINESS_VERIFICATION,
    MENU_IMPORT_PHOTOS,
    MENU_IMPORT_PHOTOS_DAILY_LIMIT,
    InMemoryDailyLimiter,
    UnitsAcquisition,
    acquire_menu_photos,
    menu_photo_daily_limit,
)

OWNER, OTHER = "owner-subject", "other-subject"
# 2026-11-26 12:00 KST, one second before midnight KST, and midnight.
NOON = datetime(2026, 11, 26, 3, tzinfo=UTC)
BEFORE_MIDNIGHT = datetime(2026, 11, 26, 14, 59, 59, tzinfo=UTC)
AT_MIDNIGHT = datetime(2026, 11, 26, 15, tzinfo=UTC)
TODAY = date(2026, 11, 26)
JPEG = b"\xff\xd8\xff\xe0" + b"menu photo"


def used(limiter, subject=OWNER, now=NOON):
    return limiter.used(subject, MENU_IMPORT_PHOTOS, now)


# ---- the setting ----


def test_the_limit_is_30_photos_unless_the_setting_says_otherwise(monkeypatch):
    monkeypatch.delenv("MENU_PHOTO_DAILY_LIMIT", raising=False)
    assert menu_photo_daily_limit() == MENU_IMPORT_PHOTOS_DAILY_LIMIT == 30
    assert InMemoryDailyLimiter().limit_for(MENU_IMPORT_PHOTOS) == 30

    monkeypatch.setenv("MENU_PHOTO_DAILY_LIMIT", "45")
    assert menu_photo_daily_limit() == 45 and InMemoryDailyLimiter().limit_for(MENU_IMPORT_PHOTOS) == 45
    assert InMemoryDailyLimiter().limit_for(BUSINESS_VERIFICATION) == 30  # the other kinds keep theirs
    assert InMemoryDailyLimiter(daily_limit=3).limit_for(MENU_IMPORT_PHOTOS) == 3


@pytest.mark.parametrize("value", ["0", "-5", "many", "2.5"])
def test_an_invalid_limit_stops_the_server_at_start_up(monkeypatch, value):
    monkeypatch.setenv("MENU_PHOTO_DAILY_LIMIT", value)

    with pytest.raises(RuntimeError, match="MENU_PHOTO_DAILY_LIMIT must be a positive integer"):
        with TestClient(app):
            pass


# ---- counting photos ----


def test_photos_are_counted_all_or_none():
    limiter = InMemoryDailyLimiter(daily_limit=30)

    assert limiter.acquire_units(OWNER, MENU_IMPORT_PHOTOS, 15, NOON) == UnitsAcquisition(TODAY, True, 15, 30)
    assert limiter.acquire_units(OWNER, MENU_IMPORT_PHOTOS, 10, NOON) == UnitsAcquisition(TODAY, True, 5, 30)
    # 5 left and 8 asked for: none of the 8 is counted
    assert limiter.acquire_units(OWNER, MENU_IMPORT_PHOTOS, 8, NOON) == UnitsAcquisition(TODAY, False, 5, 30)
    assert used(limiter) == 25
    assert limiter.acquire_units(OWNER, MENU_IMPORT_PHOTOS, 5, NOON) == UnitsAcquisition(TODAY, True, 0, 30)
    assert limiter.acquire_units(OWNER, MENU_IMPORT_PHOTOS, 1, NOON) == UnitsAcquisition(TODAY, False, 0, 30)
    # another user, and another kind for the same user, have their own counts
    assert limiter.acquire_units(OTHER, MENU_IMPORT_PHOTOS, 30, NOON).counted
    assert limiter.acquire(OWNER, BUSINESS_VERIFICATION, NOON).counted


def test_an_upload_must_ask_for_at_least_one_photo():
    with pytest.raises(ValueError, match="at least 1"):
        InMemoryDailyLimiter().acquire_units(OWNER, MENU_IMPORT_PHOTOS, 0, NOON)


def test_photos_given_back_can_be_used_again_but_not_after_the_day_is_over():
    limiter = InMemoryDailyLimiter(daily_limit=30)
    limiter.acquire_units(OWNER, MENU_IMPORT_PHOTOS, 20, BEFORE_MIDNIGHT)

    limiter.release_units(OWNER, MENU_IMPORT_PHOTOS, TODAY, 8)
    assert used(limiter, now=BEFORE_MIDNIGHT) == 12
    limiter.release_units(OWNER, MENU_IMPORT_PHOTOS, TODAY, 12)
    assert used(limiter, now=BEFORE_MIDNIGHT) == 0

    limiter.acquire_units(OWNER, MENU_IMPORT_PHOTOS, 4, AT_MIDNIGHT)
    limiter.release_units(OWNER, MENU_IMPORT_PHOTOS, TODAY, 4)  # yesterday's units: nothing to refund today
    assert used(limiter, now=AT_MIDNIGHT) == 4


def test_the_count_starts_over_at_midnight_kst():
    limiter = InMemoryDailyLimiter(daily_limit=30)
    assert acquire_menu_photos(limiter, OWNER, 30, BEFORE_MIDNIGHT) == TODAY

    with pytest.raises(ApiError) as refused:
        acquire_menu_photos(limiter, OWNER, 1, BEFORE_MIDNIGHT)
    assert refused.value.details["retryAfter"] == "2026-11-26T15:00:00Z"

    assert acquire_menu_photos(limiter, OWNER, 30, AT_MIDNIGHT) == date(2026, 11, 27)


def test_an_operator_reset_clears_the_photo_count_of_one_user_or_one_kind():
    limiter = InMemoryDailyLimiter(daily_limit=30)
    for subject in (OWNER, OTHER):
        limiter.acquire_units(subject, MENU_IMPORT_PHOTOS, 30, NOON)
    limiter.acquire(OWNER, BUSINESS_VERIFICATION, NOON)

    assert limiter.reset(OWNER, MENU_IMPORT_PHOTOS, NOON) == 1
    assert (used(limiter), used(limiter, OTHER)) == (0, 30)
    assert limiter.used(OWNER, BUSINESS_VERIFICATION, NOON) == 1  # the other kind is left alone
    assert acquire_menu_photos(limiter, OWNER, 15, NOON) == TODAY

    assert limiter.reset(None, MENU_IMPORT_PHOTOS, NOON) == 2 and used(limiter, OTHER) == 0


def test_the_reset_api_takes_the_photo_kind():
    assert RequestLimitResetInput(kind="menu_import_photos").kind == MENU_IMPORT_PHOTOS
    with pytest.raises(ValidationError):
        RequestLimitResetInput(kind="menu_photos")


def test_a_pdf_counts_one_photo_per_page():
    # The upload does not take PDFs yet; when it does, it passes the page count here.
    limiter, pages = InMemoryDailyLimiter(daily_limit=30), 12
    acquire_menu_photos(limiter, OWNER, pages, NOON)
    acquire_menu_photos(limiter, OWNER, pages, NOON)

    assert used(limiter) == 24
    with pytest.raises(ApiError) as refused:
        acquire_menu_photos(limiter, OWNER, pages, NOON)
    assert (refused.value.details["remaining"], refused.value.details["requested"]) == (6, 12)


# ---- the refusal ----


def test_an_upload_over_what_is_left_is_refused_whole_and_told_how_many_fit():
    limiter = InMemoryDailyLimiter(daily_limit=30)
    acquire_menu_photos(limiter, OWNER, 25, NOON)

    with pytest.raises(ApiError) as refused:
        acquire_menu_photos(limiter, OWNER, 8, NOON)

    error = refused.value
    assert (error.status_code, error.code) == (429, "RATE_LIMITED")
    assert error.details == {"retryAfter": "2026-11-26T15:00:00Z", "dailyLimit": 30, "remaining": 5, "requested": 8}
    assert error.message == "오늘 올릴 수 있는 메뉴 사진은 5장 남았습니다. 사진을 5장 이하로 줄이거나 내일 다시 시도해 주세요."
    assert used(limiter) == 25
    acquire_menu_photos(limiter, OWNER, 5, NOON)  # the 5 that fit are accepted


def test_with_nothing_left_the_message_says_to_come_back_tomorrow():
    limiter = InMemoryDailyLimiter(daily_limit=30)
    acquire_menu_photos(limiter, OWNER, 30, NOON)

    with pytest.raises(ApiError) as refused:
        acquire_menu_photos(limiter, OWNER, 1, NOON)

    assert refused.value.message == "오늘 올릴 수 있는 메뉴 사진 30장을 모두 사용했습니다. 내일 다시 시도해 주세요."
    assert refused.value.details["remaining"] == 0


def test_the_limit_in_the_refusal_is_the_setting(monkeypatch):
    monkeypatch.setenv("MENU_PHOTO_DAILY_LIMIT", "4")
    limiter = InMemoryDailyLimiter()

    acquire_menu_photos(limiter, OWNER, 4, NOON)  # exactly the limit is accepted
    with pytest.raises(ApiError) as refused:
        acquire_menu_photos(limiter, OWNER, 1, NOON)

    assert refused.value.details["dailyLimit"] == 4 and "4장을 모두" in refused.value.message


# ---- the upload ----


class FakeSession:
    """Answers `scalar` from a list, in the order create_menu_import asks: the import with this
    idempotency key, the bar's status, the bar's unfinished import (and the key again after a lost
    insert race)."""

    def __init__(self, *scalars, commit_error=None):
        self.scalars, self.commit_error = list(scalars), commit_error
        self.added, self.commits, self.rollbacks = [], 0, 0

    def scalar(self, statement):
        return self.scalars.pop(0)

    def add(self, row):
        self.added.append(row)

    def flush(self):
        pass

    def commit(self):
        if self.commit_error is not None:
            error, self.commit_error = self.commit_error, None
            raise error
        self.commits += 1

    def rollback(self):
        self.rollbacks += 1


class FakeStorage:
    def __init__(self, fail_on_save=None):
        self.saved, self.deleted, self.fail_on_save = [], [], fail_on_save

    def save(self, key, data, content_type):
        if len(self.saved) + 1 == self.fail_on_save:
            raise OSError("disk full")
        self.saved.append(key)

    def delete(self, key):
        self.deleted.append(key)


@pytest.fixture(autouse=True)
def caller_manages_the_bar(monkeypatch):
    monkeypatch.setattr(menu_import_upload, "can_manage_bar", lambda session, principal, bar_id: True)


def new_bar():
    return Bar(id=uuid4(), status=BarStatus.ACTIVE)


def upload(limiter, photos, *, session=None, storage=None, key="key-1", subject=OWNER, now=NOON, bar=None):
    session = session or FakeSession(None, BarStatus.ACTIVE, None)
    storage = storage or FakeStorage()
    result = create_menu_import(
        session, storage, MockMenuExtractor(),
        principal=Principal(kind="supabase", subject=subject, claims={}), bar=bar or new_bar(),
        idempotency_key=key, mode=ImportMode.FULL_REPLACE, owner_note=None,
        uploads=[ImageUpload(f"menu-{n}.jpg", "image/jpeg", io.BytesIO(JPEG + bytes([n]))) for n in range(photos)],
        limiter=limiter, now=now,
    )
    return result, session, storage


def test_an_accepted_upload_counts_its_photos():
    limiter = InMemoryDailyLimiter(daily_limit=30)

    (menu_import, created), session, storage = upload(limiter, 15)

    assert created and menu_import.status == ImportStatus.UPLOADED and len(storage.saved) == 15
    assert used(limiter) == 15 and session.commits == 1


def test_the_last_photos_that_fit_are_accepted_and_one_more_is_refused():
    limiter = InMemoryDailyLimiter(daily_limit=30)
    upload(limiter, 15, key="key-1")
    upload(limiter, 15, key="key-2")  # reaches the limit exactly

    with pytest.raises(ApiError) as refused:
        upload(limiter, 1, key="key-3")

    assert (refused.value.status_code, refused.value.code) == (429, "RATE_LIMITED")
    assert used(limiter) == 30


def test_an_upload_over_what_is_left_stores_nothing():
    limiter = InMemoryDailyLimiter(daily_limit=30)
    upload(limiter, 15, key="key-1")
    upload(limiter, 10, key="key-2")
    session, storage = FakeSession(None, BarStatus.ACTIVE, None), FakeStorage()

    with pytest.raises(ApiError) as refused:
        upload(limiter, 8, key="key-3", session=session, storage=storage)  # 5 left, within the 15 of one upload

    assert refused.value.details["remaining"] == 5 and refused.value.details["requested"] == 8
    assert storage.saved == [] and session.added == [] and session.commits == 0 and used(limiter) == 25
    (_, created), _, _ = upload(limiter, 5, key="key-4")
    assert created and used(limiter) == 30


def test_each_user_has_their_own_count_and_the_next_day_starts_over():
    limiter = InMemoryDailyLimiter(daily_limit=15)
    upload(limiter, 15, now=BEFORE_MIDNIGHT)

    upload(limiter, 15, key="key-2", subject=OTHER, now=BEFORE_MIDNIGHT)
    with pytest.raises(ApiError):
        upload(limiter, 1, key="key-3", now=BEFORE_MIDNIGHT)
    (_, created), _, _ = upload(limiter, 15, key="key-4", now=AT_MIDNIGHT)

    assert created and used(limiter, now=AT_MIDNIGHT) == 15


def test_a_retry_of_the_same_request_is_not_counted_again():
    limiter, bar = InMemoryDailyLimiter(daily_limit=30), new_bar()
    (first, _), _, _ = upload(limiter, 10, bar=bar)

    (again, created), session, storage = upload(limiter, 10, bar=bar, session=FakeSession(first))

    assert again is first and not created and storage.saved == [] and used(limiter) == 10


def test_an_upload_refused_by_an_earlier_check_is_not_counted():
    limiter = InMemoryDailyLimiter(daily_limit=30)
    unfinished = MenuImport(id=uuid4(), status=ImportStatus.PROCESSING)

    with pytest.raises(ApiError) as too_many:
        upload(limiter, MAX_IMAGES + 1)
    with pytest.raises(ApiError) as active:
        upload(limiter, 5, session=FakeSession(None, BarStatus.ACTIVE, unfinished))

    assert (too_many.value.code, active.value.code) == ("UPLOAD_TOO_LARGE", "ACTIVE_IMPORT_EXISTS")
    assert used(limiter) == 0


def test_photos_are_given_back_when_storing_fails():
    limiter, storage = InMemoryDailyLimiter(daily_limit=30), FakeStorage(fail_on_save=3)

    with pytest.raises(OSError, match="disk full"):
        upload(limiter, 5, storage=storage)

    assert used(limiter) == 0 and storage.deleted == storage.saved and len(storage.saved) == 2


def test_the_loser_of_an_insert_race_is_not_counted():
    limiter, bar = InMemoryDailyLimiter(daily_limit=30), new_bar()
    (winner, _), _, _ = upload(limiter, 6, bar=bar)
    lost = FakeSession(None, BarStatus.ACTIVE, None, winner, commit_error=IntegrityError("insert", {}, Exception("duplicate key")))

    (menu_import, created), _, storage = upload(limiter, 6, bar=bar, session=lost)

    assert menu_import is winner and not created and storage.deleted == storage.saved
    assert used(limiter) == 6  # the winner's photos only


def test_without_a_limiter_nothing_is_counted_or_refused():
    session = FakeSession(None, BarStatus.ACTIVE, None)

    menu_import, created = create_menu_import(
        session, FakeStorage(), MockMenuExtractor(), principal=Principal(kind="supabase", subject=OWNER, claims={}),
        bar=new_bar(), idempotency_key="key-1", mode=ImportMode.FULL_REPLACE, owner_note=" ",
        uploads=[ImageUpload("menu.jpg", "image/jpeg", io.BytesIO(JPEG))])

    assert created and menu_import.owner_note is None


def test_without_a_limiter_a_failed_upload_has_nothing_to_give_back():
    storage = FakeStorage(fail_on_save=1)

    with pytest.raises(OSError, match="disk full"):
        create_menu_import(
            FakeSession(None, BarStatus.ACTIVE, None), storage, MockMenuExtractor(),
            principal=Principal(kind="supabase", subject=OWNER, claims={}), bar=new_bar(), idempotency_key="key-1",
            mode=ImportMode.FULL_REPLACE, owner_note=None, uploads=[ImageUpload("menu.jpg", "image/jpeg", io.BytesIO(JPEG))])

    assert storage.saved == []


def test_processing_and_recovery_never_count_photos():
    # Photos are counted once, when the upload is accepted. Reading them (again after a restart, or by
    # another extraction route) happens in menu_import_processing, which has no access to the limiter.
    source = inspect.getsource(menu_import_processing)

    assert "request_limits" not in source and "limiter" not in source
    for function in (menu_import_processing.process_menu_import, menu_import_processing.recover_imports):
        assert "limiter" not in inspect.signature(function).parameters


# ---- the route ----


@pytest.fixture
def api(monkeypatch):
    """The upload route without a database: a fake session, a fixed caller and bar, no processing."""
    limiter, storage, bar = InMemoryDailyLimiter(daily_limit=5), FakeStorage(), new_bar()
    overrides = {
        get_session: lambda: FakeSession(None, BarStatus.ACTIVE, None),
        get_session_factory: lambda: None,
        get_current_user: lambda: Principal(kind="supabase", subject=OWNER, claims={}),
        require_active_bar_manager: lambda: bar,
        deps.get_image_storage: lambda: storage,
        deps.get_menu_extractor: MockMenuExtractor,
        deps.get_matching_llm_layer: lambda: None,
        deps.get_request_limiter: lambda: limiter,
        deps.get_clock: lambda: lambda: NOON,
    }
    monkeypatch.setattr(menu_imports, "start_processing", lambda *args, **kwargs: None)
    app.dependency_overrides.update(overrides)
    client = TestClient(app)
    client.limiter, client.storage, client.path = limiter, storage, f"/api/bars/{bar.id}/menu-imports"
    try:
        yield client
    finally:
        for dependency in overrides:
            app.dependency_overrides.pop(dependency, None)


def post(api, photos, key):
    files = [("images", (f"menu-{n}.jpg", JPEG + bytes([n]), "image/jpeg")) for n in range(photos)]
    return api.post(api.path, headers={"Idempotency-Key": key}, data={"mode": "full_replace"}, files=files)


def test_the_upload_route_answers_429_with_what_is_left(api):
    assert post(api, 3, "key-1").status_code == 202

    response = post(api, 4, "key-2")

    assert response.status_code == 429
    assert response.json() == {"error": {
        "code": "RATE_LIMITED",
        "message": "오늘 올릴 수 있는 메뉴 사진은 2장 남았습니다. 사진을 2장 이하로 줄이거나 내일 다시 시도해 주세요.",
        "details": {"retryAfter": "2026-11-26T15:00:00Z", "dailyLimit": 5, "remaining": 2, "requested": 4},
        "fieldErrors": [],
    }}
    assert len(api.storage.saved) == 3 and used(api.limiter) == 3
    assert post(api, 2, "key-3").status_code == 202 and used(api.limiter) == 5
