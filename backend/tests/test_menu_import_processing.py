import json
from contextlib import nullcontext
from decimal import Decimal
from pathlib import Path

import pytest
from sqlalchemy import select

from app.adapters.extraction import (
    ExtractionError,
    ExtractionResult,
    MockMenuExtractor,
    load_fixture,
    parse_extraction_response,
)
from app.adapters.matching_llm import MatchingLLMError
from app.api.deps import get_matching_llm_layer, get_menu_extractor
from app.main import app
from app.matching.llm_layer import LLMLayerConfig
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
from app.services import menu_import_processing
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


@pytest.mark.skipif(not (CATALOG_DIR / "catalog_v2_service.json").exists(), reason="ai/catalog seed is not checked out")
def test_label_fixture_against_the_seed_catalog(client, db_session, image_storage, operator):
    catalog = json.loads((CATALOG_DIR / "catalog_v2_service.json").read_text(encoding="utf-8"))
    bars = json.loads((CATALOG_DIR / "bars_v2.json").read_text(encoding="utf-8"))
    seed(db_session.connection(), catalog, bars)
    bar = make_bar(db_session)

    menu_import = load_import(db_session, upload(client, bar, operator, filenames=("menu.jpg",)))

    statuses = [i.initial_resolution_status for i in items_of(menu_import) if i.extracted_line_type == LineType.PRODUCT]
    assert (statuses.count(ResolutionStatus.EXACT_MATCH), statuses.count(ResolutionStatus.UNMATCHED)) == (8, 2)
    assert {c[0] for c in changes_of(db_session, menu_import)} == {MenuChangeType.ADD}
    assert len(changes_of(db_session, menu_import)) == 10


# ---- I2-A18: staged matching rules in menu import ----


def product_line(order, name):
    return {
        "itemOrder": order, "rawText": f"{name} 15,000", "lineType": "product", "productName": name,
        "brandText": None, "ageYears": None, "editionName": None, "abv": None,
        "options": [{"optionLabel": "잔", "pourMl": None, "priceKrw": 15000}], "confidence": None,
    }


@pytest.fixture
def menu_lines(use_extractor):
    def use(*names):
        payload = {"items": [product_line(order, name) for order, name in enumerate(names, start=1)]}

        class LinesExtractor(MockMenuExtractor):
            def extract(self, image, content_type, filename):
                return ExtractionResult(items=parse_extraction_response(payload), raw_output=payload)

        use_extractor(LinesExtractor())

    return use


@pytest.mark.parametrize(
    ("name", "status", "age", "evidence_key", "rule"),
    [
        # Each line is unmatched by the Iteration 1 alias lookup alone.
        ("글렌피딕(Glenfiddich) 12년", ResolutionStatus.EXACT_MATCH, 12, "parenExpanded", "S1"),  # name variant
        ("글렌피딕 12년 싱글몰트", ResolutionStatus.AMBIGUOUS, 12, "ageMatch", "S2"),  # brand + age
        ("글렌피닥 15년", ResolutionStatus.EXACT_MATCH, 15, "editDistance", "S3"),  # one-letter typo
    ],
)
def test_staged_rules_match_lines_without_an_exact_alias(
    client, db_session, image_storage, operator, glenfiddich, menu_lines, name, status, age, evidence_key, rule
):
    menu_lines(name)

    [item] = items_of(load_import(db_session, upload(client, make_bar(db_session), operator)))

    assert item.initial_resolution_status == status
    [candidate] = item.candidates
    assert candidate.product_id == glenfiddich[age].id
    assert candidate.method == MatchMethod.ALIAS
    assert evidence_key in candidate.evidence
    assert candidate.evidence["rule"] == rule  # I2-A22: tells a rule's exact_match from an exact alias match


def test_line_naming_two_products_is_stored_as_ambiguous(client, db_session, image_storage, operator, menu_lines):
    buffalo = make_product(db_session, make_brand(db_session, "Buffalo Trace"), "Buffalo Trace")
    makers = make_product(db_session, make_brand(db_session, "Maker's Mark"), "Maker's Mark")
    menu_lines("Buffalo Trace / Maker's Mark")

    menu_import = load_import(db_session, upload(client, make_bar(db_session), operator))

    assert menu_import.status == ImportStatus.READY_FOR_REVIEW
    [item] = items_of(menu_import)
    assert item.initial_resolution_status == ResolutionStatus.AMBIGUOUS
    assert [(c.candidate_rank, c.product_id, c.evidence["multiProduct"], c.evidence["rule"]) for c in item.candidates] == [
        (1, buffalo.id, "Buffalo Trace", "S1"),
        (2, makers.id, "Maker's Mark", "S1"),
    ]


# ---- I3: the LLM matching layer (M3) after S1–S3; the LLM is always a fake ----


class FakeMatchingLLM:
    """M3a answers come from `by_name` (menu line name -> translation); M3b always says "unsure".

    `answer` replaces the M3a answer: an exception is raised, a str is returned as is.
    """

    def __init__(self, by_name=None, answer=None, on_call=None):
        self.by_name = by_name or {}
        self.answer = answer
        self.on_call = on_call
        self.payloads = []

    def generate_json(self, prompt, payload, response_schema):
        self.payloads.append(payload)
        if self.on_call is not None:
            self.on_call()
        if "menu_line" in payload:
            return json.dumps({"choice": "unsure", "reason": ""})
        if isinstance(self.answer, Exception):
            raise self.answer
        if self.answer is not None:
            return self.answer
        items = [{"line": line["line"], **self.by_name[line["name"]]}
                 for line in payload["lines"] if line["target"] and line["name"] in self.by_name]
        return json.dumps({"items": items}, ensure_ascii=False)


def translation(**fields):
    return {"bottler_en": None, "distillery_en": None, "brand_en": None, "age": None, "edition_tokens_en": [],
            "expansions": [], "kind": "whisky", **fields}


CAOL_ILA_12 = translation(brand_en="Caol Ila", age=12)


@pytest.fixture
def caol_ila(db_session):
    brand = make_brand(db_session, "Caol Ila")  # no Korean brand alias: S1–S3 leave "카올 일라 12" unmatched
    return {
        12: make_product(db_session, brand, "Caol Ila 12", aliases=("쿨일라 12년",), age_years=12),
        18: make_product(db_session, brand, "Caol Ila 18", age_years=18),
    }


@pytest.fixture
def use_llm_layer():
    def use(llm, max_calls=30, use_m3b=False):
        app.dependency_overrides[get_matching_llm_layer] = lambda: LLMLayerConfig(llm, max_calls, use_m3b)
        return llm

    yield use
    app.dependency_overrides.pop(get_matching_llm_layer, None)


def candidates_of(item):
    return [(c.product_id, c.candidate_rank, c.method, c.score, c.evidence) for c in item.candidates]


def test_llm_layer_is_off_by_default(client, db_session, image_storage, operator, caol_ila, menu_lines, monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "secret-test-key")
    monkeypatch.setenv("MATCHING_LLM_ENABLED", "false")
    assert get_matching_llm_layer() is None

    def refuse(*args, **kwargs):
        raise AssertionError("the LLM layer must not run while it is off")

    monkeypatch.setattr(menu_import_processing, "M3Engine", refuse)
    monkeypatch.setattr(menu_import_processing, "CatalogSnapshot", refuse)
    menu_lines("Caol Ila 18", "카올 일라 12")

    menu_import = load_import(db_session, upload(client, make_bar(db_session), operator))

    assert menu_import.status == ImportStatus.READY_FOR_REVIEW
    exact, unknown = items_of(menu_import)
    assert (exact.initial_resolution_status, unknown.initial_resolution_status) == (
        ResolutionStatus.EXACT_MATCH, ResolutionStatus.UNMATCHED)
    assert unknown.candidates == []


def test_llm_candidates_are_ambiguous_and_never_selected(
    client, db_session, image_storage, operator, caol_ila, use_extractor, use_llm_layer
):
    payload = {"items": [product_line(1, "Caol Ila 18"), product_line(2, "카올 일라 12"), product_line(3, "하이볼"),
                         {**product_line(4, "x"), "productName": None}]}

    class LinesExtractor(MockMenuExtractor):
        def extract(self, image, content_type, filename):
            return ExtractionResult(items=parse_extraction_response(payload), raw_output=payload)

    use_extractor(LinesExtractor())
    llm = use_llm_layer(FakeMatchingLLM({"카올 일라 12": CAOL_ILA_12, "하이볼": translation(kind="non_whisky")}))

    import_id = upload(client, make_bar(db_session), operator)

    menu_import = load_import(db_session, import_id)
    assert menu_import.status == ImportStatus.READY_FOR_REVIEW
    # One M3a request per photo: every line in order, the unconfirmed ones marked (a line without a name is left out).
    assert llm.payloads == [{"lines": [{"line": 1, "name": "Caol Ila 18", "target": False},
                                       {"line": 2, "name": "카올 일라 12", "target": True},
                                       {"line": 3, "name": "하이볼", "target": True}]}]
    exact, llm_line, non_whisky, nameless = items_of(menu_import)
    assert [i.initial_resolution_status for i in (exact, llm_line, non_whisky, nameless)] == [
        ResolutionStatus.EXACT_MATCH, ResolutionStatus.AMBIGUOUS, ResolutionStatus.UNMATCHED, ResolutionStatus.UNMATCHED]
    assert candidates_of(llm_line) == [(caol_ila[12].id, 1, MatchMethod.LLM, Decimal("0.500000"), {
        "rule": "M3a", "via": ["relookup", "tokens"], "englishName": "Caol Ila 12", "confirmRecommended": True})]
    assert non_whisky.candidates == [] and nameless.candidates == []
    # A candidate only: nothing is selected or published until the owner confirms it.
    assert llm_line.selected_product_id is None and llm_line.review_status.value == "pending"
    assert (MenuChangeType.ADD, llm_line.id, None) in changes_of(db_session, menu_import)

    [image] = client.get(f"/api/menu-imports/{import_id}", headers=operator).json()["images"]
    item = image["items"][1]
    assert (item["initialResolutionStatus"], item["proposedProductId"]) == ("ambiguous", str(caol_ila[12].id))
    [candidate] = item["candidates"]
    assert (candidate["matchMethod"], candidate["score"], candidate["evidence"]["rule"]) == ("llm", 0.5, "M3a")
    assert candidate["evidence"]["confirmRecommended"] is True


def test_llm_candidates_come_before_the_rule_candidates(
    client, db_session, image_storage, operator, glenfiddich, menu_lines, use_llm_layer
):
    sherry = make_product(db_session, glenfiddich[12].brand, "Glenfiddich 12 Sherry Cask", age_years=12,
                          edition_name="Sherry Cask")
    menu_lines("글렌피딕 12년 싱글몰트")  # S2: brand + age, two products of that age
    use_llm_layer(FakeMatchingLLM({"글렌피딕 12년 싱글몰트": translation(brand_en="Glenfiddich", age=12)}))

    [item] = items_of(load_import(db_session, upload(client, make_bar(db_session), operator)))

    assert item.initial_resolution_status == ResolutionStatus.AMBIGUOUS
    (llm_id, _, llm_method, _, llm_evidence), (rule_id, rank, rule_method, _, rule_evidence) = candidates_of(item)
    assert (llm_id, llm_method, llm_evidence["rule"], llm_evidence["confirmRecommended"]) == (
        glenfiddich[12].id, MatchMethod.LLM, "M3a", True)  # the LLM pick is one of the rule candidates
    assert (rule_id, rank, rule_method, rule_evidence["rule"]) == (sherry.id, 2, MatchMethod.ALIAS, "S2")


def test_call_cap_leaves_the_remaining_lines_with_their_rule_result(
    client, db_session, image_storage, operator, caol_ila, menu_lines, use_llm_layer
):
    menu_lines("카올 일라 12", "카올 일라 12")  # the same name twice on each photo
    llm = use_llm_layer(FakeMatchingLLM({"카올 일라 12": CAOL_ILA_12}), max_calls=1)

    items = items_of(load_import(
        db_session, upload(client, make_bar(db_session), operator, filenames=("sample.jpg", "sample-2.jpg"))))

    # One request (photo 1), whose lines list the name once; both of its items get the LLM candidate.
    assert llm.payloads == [{"lines": [{"line": 1, "name": "카올 일라 12", "target": True}]}]
    assert [[c.method for c in item.candidates] for item in items[:2]] == [[MatchMethod.LLM], [MatchMethod.LLM]]
    assert [(item.initial_resolution_status, item.candidates) for item in items[2:]] == [
        (ResolutionStatus.UNMATCHED, [])] * 2


@pytest.mark.parametrize(
    "answer", [MatchingLLMError("gave up"), RuntimeError("API down"), TimeoutError(), "not json", '{"items": "x"}']
)
def test_llm_failure_keeps_the_rule_results(
    client, db_session, image_storage, operator, glenfiddich, menu_lines, use_llm_layer, answer
):
    menu_lines("글렌피딕 12년 싱글몰트", "글렌피딕 18년")
    llm = use_llm_layer(FakeMatchingLLM(answer=answer))

    menu_import = load_import(db_session, upload(client, make_bar(db_session), operator))

    assert len(llm.payloads) == 1 and menu_import.status == ImportStatus.READY_FOR_REVIEW
    rule_line, unknown = items_of(menu_import)
    assert rule_line.initial_resolution_status == ResolutionStatus.AMBIGUOUS
    assert [(c.product_id, c.method, c.evidence["rule"]) for c in rule_line.candidates] == [
        (glenfiddich[12].id, MatchMethod.ALIAS, "S2")]
    assert (unknown.initial_resolution_status, unknown.candidates) == (ResolutionStatus.UNMATCHED, [])


@pytest.mark.parametrize("broken", ["CatalogSnapshot", "M3Engine"])
def test_bug_in_the_layer_keeps_the_rule_results(
    client, db_session, image_storage, operator, caol_ila, menu_lines, use_llm_layer, monkeypatch, caplog, broken
):
    def bug(*args, **kwargs):
        raise KeyError("bug")

    monkeypatch.setattr(menu_import_processing, broken, bug)
    menu_lines("Caol Ila 18", "카올 일라 12")
    use_llm_layer(FakeMatchingLLM({"카올 일라 12": CAOL_ILA_12}))

    menu_import = load_import(db_session, upload(client, make_bar(db_session), operator))

    assert menu_import.status == ImportStatus.READY_FOR_REVIEW
    assert [i.initial_resolution_status for i in items_of(menu_import)] == [
        ResolutionStatus.EXACT_MATCH, ResolutionStatus.UNMATCHED]
    assert "the LLM matching layer failed; keeping the rule results" in caplog.text


def test_no_transaction_is_open_during_llm_calls(
    client, db_session, image_storage, operator, caol_ila, menu_lines, use_llm_layer
):
    in_transaction = []
    menu_lines("카올 일라 12")
    use_llm_layer(FakeMatchingLLM({"카올 일라 12": CAOL_ILA_12},
                                  on_call=lambda: in_transaction.append(db_session.in_transaction())))

    upload(client, make_bar(db_session), operator, filenames=("sample.jpg", "sample-2.jpg"))

    assert in_transaction == [False, False]


def test_no_call_when_every_line_is_confirmed(
    client, db_session, image_storage, operator, caol_ila, menu_lines, use_llm_layer
):
    menu_lines("Caol Ila 18", "쿨일라 12년")
    llm = use_llm_layer(FakeMatchingLLM())

    menu_import = load_import(db_session, upload(client, make_bar(db_session), operator))

    assert llm.payloads == []
    assert {i.initial_resolution_status for i in items_of(menu_import)} == {ResolutionStatus.EXACT_MATCH}


def test_m3b_runs_only_when_enabled(client, db_session, image_storage, operator, caol_ila, menu_lines, use_llm_layer):
    menu_lines("꿀일라 시크릿")
    secret = translation(brand_en="Caol Ila", edition_tokens_en=["Secret"])  # M3a finds nothing
    llm = use_llm_layer(FakeMatchingLLM({"꿀일라 시크릿": secret}), use_m3b=True)

    [item] = items_of(load_import(db_session, upload(client, make_bar(db_session), operator)))

    assert ["lines" in p for p in llm.payloads] == [True, False]  # M3a, then M3b (which says "unsure")
    assert (item.initial_resolution_status, item.candidates) == (ResolutionStatus.UNMATCHED, [])
