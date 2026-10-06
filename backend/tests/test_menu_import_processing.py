import json
from contextlib import nullcontext
from decimal import Decimal
from pathlib import Path

import pytest
from sqlalchemy import select

from app.adapters.extraction import ExtractionError, MockMenuExtractor, load_fixture
from app.api.deps import get_menu_extractor
from app.main import app
from app.models import (
    ExtractedItem,
    ImportMode,
    ImportStatus,
    LineType,
    MatchMethod,
    MenuChangeType,
    MenuImport,
    MenuImportChange,
    PipelineStatus,
    ResolutionStatus,
)
from app.services.menu_import_processing import process_menu_import
from scripts.seed_catalog import seed
from tests.factories import make_bar, make_brand, make_product, publish_menu

JPEG = b"\xff\xd8\xff\xe0" + b"jpeg-body"
CATALOG_DIR = Path(__file__).resolve().parents[2] / "ai" / "catalog"


@pytest.fixture
def operator(token_for):
    return {"Authorization": f"Bearer {token_for('operator')}"}


@pytest.fixture
def glenfiddich(db_session):
    brand = make_brand(db_session, "Glenfiddich", aliases=("글렌피딕",))
    return {
        12: make_product(db_session, brand, "Glenfiddich 12", aliases=("글렌피딕 12년",), age_years=12),
        15: make_product(db_session, brand, "Glenfiddich 15", aliases=("글렌피딕 15년",), age_years=15),
    }


@pytest.fixture
def use_extractor():
    def use(extractor):
        app.dependency_overrides[get_menu_extractor] = lambda: extractor

    yield use
    app.dependency_overrides.pop(get_menu_extractor, None)


def upload(client, bar, headers, filenames=("sample.jpg",), mode="full_replace", key="key-1"):
    response = client.post(
        f"/api/bars/{bar.id}/menu-imports",
        headers={**headers, "Idempotency-Key": key},
        data={"mode": mode},
        files=[("images", (name, JPEG, "image/jpeg")) for name in filenames],
    )
    assert response.status_code == 202, response.text
    return response.json()["menuImportId"]


def load_import(db_session, import_id):
    db_session.expire_all()
    return db_session.get(MenuImport, import_id)


def items_of(menu_import):
    return [item for image in menu_import.images for item in image.extraction_run.items]


def changes_of(db_session, menu_import):
    rows = db_session.scalars(select(MenuImportChange).where(MenuImportChange.menu_import_id == menu_import.id))
    return sorted((c.change_type, c.extracted_item_id, c.bar_menu_item_id) for c in rows)


def test_sample_upload_is_extracted_matched_and_ready_for_review(client, db_session, image_storage, operator, glenfiddich):
    bar = make_bar(db_session)

    menu_import = load_import(db_session, upload(client, bar, operator))

    assert (menu_import.status, menu_import.review_version, menu_import.completed_at) == (
        ImportStatus.READY_FOR_REVIEW,
        1,
        None,
    )
    run = menu_import.images[0].extraction_run
    assert run.status == PipelineStatus.SUCCEEDED
    assert run.raw_output == load_fixture("sample")
    assert run.started_at is not None and run.completed_at is not None

    items = items_of(menu_import)
    assert [i.extracted_line_type for i in items] == [
        LineType.SECTION_HEADER,
        LineType.PRODUCT,
        LineType.PRODUCT,
        LineType.PRODUCT,
        LineType.DESCRIPTION,
    ]
    assert [i.initial_resolution_status for i in items] == [
        None,
        ResolutionStatus.EXACT_MATCH,
        ResolutionStatus.AMBIGUOUS,
        ResolutionStatus.UNMATCHED,
        None,
    ]
    header, exact, conflict, unknown, _ = items
    assert header.options == [] and header.candidates == []
    assert [(o.option_order, o.extracted_pour_ml, o.extracted_price_krw) for o in exact.options] == [(1, 15, 9000), (2, 30, 17000)]
    assert (exact.extracted_age_years, exact.extraction_confidence) == (12, Decimal("0.9300"))
    [candidate] = exact.candidates
    assert (candidate.product_id, candidate.candidate_rank, candidate.method, candidate.score) == (
        glenfiddich[12].id,
        1,
        MatchMethod.ALIAS,
        Decimal("1.000000"),
    )
    assert candidate.evidence["aliasExact"] is True
    assert conflict.candidates[0].product_id == glenfiddich[12].id
    assert conflict.candidates[0].evidence.get("ageConflict") is True
    assert unknown.candidates == []
    # Nothing is selected or reviewed until the operator submits the review.
    assert all(i.selected_product_id is None and i.review_status.value == "pending" for i in items)


def test_draft_diff_against_an_empty_board(client, db_session, image_storage, operator, glenfiddich):
    bar = make_bar(db_session)

    menu_import = load_import(db_session, upload(client, bar, operator))

    _, exact, _, unknown, _ = items_of(menu_import)
    # The age-conflict line proposes Glenfiddich 12 again, so only its first occurrence counts.
    assert changes_of(db_session, menu_import) == sorted(
        [(MenuChangeType.ADD, exact.id, None), (MenuChangeType.ADD, unknown.id, None)]
    )
    assert all(
        c.decision.value == "pending"
        for c in db_session.scalars(select(MenuImportChange).where(MenuImportChange.menu_import_id == menu_import.id))
    )


@pytest.mark.parametrize(
    ("mode", "board_price", "expected"),
    [
        ("full_replace", 9000, {"remove"}),
        ("full_replace", 8000, {"update", "remove"}),
        ("partial_update", 9000, set()),
        ("partial_update", 8000, {"update"}),
    ],
)
def test_draft_diff_against_a_published_board(
    client, db_session, image_storage, operator, glenfiddich, mode, board_price, expected
):
    bar = make_bar(db_session)
    board = publish_menu(
        db_session,
        bar,
        [
            (glenfiddich[12], "글렌피딕 12년", [(None, 15, board_price), (None, 30, 17000)]),
            (glenfiddich[15], "글렌피딕 15년", [(None, 30, 21000)]),
        ],
    )
    twelve_item, fifteen_item = (entry.bar_menu_item_id for entry in board.entries)

    menu_import = load_import(db_session, upload(client, bar, operator, mode=mode))

    _, exact, _, unknown, _ = items_of(menu_import)
    expected_rows = {
        "update": (MenuChangeType.UPDATE, exact.id, twelve_item),
        "remove": (MenuChangeType.REMOVE, None, fifteen_item),
    }
    assert changes_of(db_session, menu_import) == sorted(
        [(MenuChangeType.ADD, unknown.id, None)] + [expected_rows[name] for name in expected]
    )


def test_failed_extraction_fails_the_import(client, db_session, image_storage, operator):
    bar = make_bar(db_session)

    menu_import = load_import(db_session, upload(client, bar, operator, filenames=("fail.jpg",)))

    assert menu_import.status == ImportStatus.FAILED
    assert menu_import.completed_at is not None
    run = menu_import.images[0].extraction_run
    assert run.status == PipelineStatus.FAILED
    assert run.raw_output["error"] == "ExtractionError"
    assert run.items == []


def test_first_failed_image_stops_the_remaining_ones(client, db_session, image_storage, operator):
    bar = make_bar(db_session)

    menu_import = load_import(
        db_session, upload(client, bar, operator, filenames=("sample.jpg", "fail.jpg", "sample-2.jpg"))
    )

    assert menu_import.status == ImportStatus.FAILED
    assert [i.extraction_run.status for i in menu_import.images] == [
        PipelineStatus.SUCCEEDED,
        PipelineStatus.FAILED,
        PipelineStatus.QUEUED,
    ]
    # Results of the image that succeeded are kept for later analysis.
    assert len(menu_import.images[0].extraction_run.items) == 5
    assert changes_of(db_session, menu_import) == []


def test_failed_run_keeps_the_model_output(client, db_session, image_storage, operator, use_extractor):
    class UnparseableExtractor(MockMenuExtractor):
        def extract(self, image, content_type, filename):
            raise ExtractionError("not valid JSON", raw_output={"text": "{items: [", "attempts": 1})

    use_extractor(UnparseableExtractor())

    menu_import = load_import(db_session, upload(client, make_bar(db_session), operator))

    assert menu_import.images[0].extraction_run.raw_output == {
        "error": "ExtractionError",
        "message": "not valid JSON",
        "output": {"text": "{items: [", "attempts": 1},
    }


def test_no_transaction_is_open_while_extracting(client, db_session, image_storage, operator, use_extractor):
    in_transaction = []

    class CheckingExtractor(MockMenuExtractor):
        def extract(self, image, content_type, filename):
            # A real model call takes minutes; it must not hold a database transaction.
            in_transaction.append(db_session.in_transaction())
            return super().extract(image, content_type, filename)

    use_extractor(CheckingExtractor())

    upload(client, make_bar(db_session), operator, filenames=("sample.jpg", "sample-2.jpg"))

    assert in_transaction == [False, False]


def test_missing_image_file_fails_the_import(client, db_session, image_storage, operator, monkeypatch):
    def lost(key):
        raise FileNotFoundError(key)

    monkeypatch.setattr(image_storage, "read", lost)
    bar = make_bar(db_session)

    menu_import = load_import(db_session, upload(client, bar, operator))

    assert menu_import.status == ImportStatus.FAILED
    assert menu_import.images[0].extraction_run.raw_output["error"] == "FileNotFoundError"


def test_unexpected_error_does_not_leave_the_import_processing(
    client, db_session, image_storage, operator, use_extractor
):
    class BrokenExtractor(MockMenuExtractor):
        def extract(self, image, content_type, filename):
            raise RuntimeError("bug")

    use_extractor(BrokenExtractor())
    bar = make_bar(db_session)

    menu_import = load_import(db_session, upload(client, bar, operator))

    assert menu_import.status == ImportStatus.FAILED


def test_extractor_receives_the_detected_type_and_original_file_name(
    client, db_session, image_storage, operator, use_extractor
):
    seen = []

    class RecordingExtractor(MockMenuExtractor):
        def extract(self, image, content_type, filename):
            seen.append((image, content_type, filename))
            return super().extract(image, content_type, filename)

    use_extractor(RecordingExtractor())

    upload(client, make_bar(db_session), operator, filenames=("sample.jpg",))

    assert seen == [(JPEG, "image/jpeg", "sample.jpg")]


@pytest.mark.parametrize("status", [ImportStatus.UPLOADED, ImportStatus.READY_FOR_REVIEW, ImportStatus.FAILED])
def test_processing_runs_only_for_imports_in_processing(db_session, image_storage, status):
    from app.models import ExtractionApproach, ExtractionRun, MenuImage

    bar = make_bar(db_session)
    menu_import = MenuImport(
        idempotency_key="k", request_fingerprint="f", bar_id=bar.id, mode=ImportMode.FULL_REPLACE, status=status
    )
    db_session.add(menu_import)
    db_session.flush()
    image = MenuImage(menu_import_id=menu_import.id, storage_key="menus/x/page-1.jpg", image_order=1)
    db_session.add(image)
    db_session.flush()
    db_session.add(
        ExtractionRun(
            menu_image_id=image.id, approach=ExtractionApproach.VISION_LLM, provider="m", model_name="m", pipeline_version="v"
        )
    )
    db_session.flush()

    process_menu_import(lambda: nullcontext(db_session), image_storage, MockMenuExtractor(), menu_import.id)

    assert load_import(db_session, menu_import.id).status == status
    assert db_session.scalars(select(ExtractedItem)).all() == []


@pytest.mark.skipif(not (CATALOG_DIR / "catalog_v1_draft.json").exists(), reason="ai/catalog seed is not checked out")
def test_label_fixture_against_the_seed_catalog(client, db_session, image_storage, operator):
    catalog = json.loads((CATALOG_DIR / "catalog_v1_draft.json").read_text(encoding="utf-8"))
    bars = json.loads((CATALOG_DIR / "bars_v1.json").read_text(encoding="utf-8"))
    seed(db_session.connection(), catalog, bars)
    bar = make_bar(db_session)

    menu_import = load_import(db_session, upload(client, bar, operator, filenames=("menu.jpg",)))

    statuses = [i.initial_resolution_status for i in items_of(menu_import) if i.extracted_line_type == LineType.PRODUCT]
    assert (statuses.count(ResolutionStatus.EXACT_MATCH), statuses.count(ResolutionStatus.UNMATCHED)) == (8, 2)
    assert {c[0] for c in changes_of(db_session, menu_import)} == {MenuChangeType.ADD}
    assert len(changes_of(db_session, menu_import)) == 10
