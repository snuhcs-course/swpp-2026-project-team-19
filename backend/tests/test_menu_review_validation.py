from uuid import uuid4

import pytest
from pydantic import ValidationError

from app.core.errors import ApiError, field_path
from app.models import MenuChangeType
from app.schemas.menu_review import ReviewAndApplyRequest
from app.services.menu_review_validation import validate_review
from tests.review_support import make_glenfiddich, upload_sample_review
from tests.review_support import valid_body as sample_body


@pytest.fixture
def operator(token_for):
    return {"Authorization": f"Bearer {token_for('operator')}"}


@pytest.fixture
def glenfiddich(db_session):
    return make_glenfiddich(db_session)


@pytest.fixture
def review(client, db_session, image_storage, operator, glenfiddich):
    sample = upload_sample_review(client, db_session, operator, glenfiddich)
    return sample.menu_import, sample.items, sample.changes, sample


def valid_body(review, glenfiddich):
    return sample_body(review[3], glenfiddich)


def validate(db_session, review, body, *, operator=True):
    return validate_review(db_session, review[0], ReviewAndApplyRequest.model_validate(body), operator=operator)


def field_errors(db_session, review, body, *, operator=True):
    with pytest.raises(ApiError) as caught:
        validate(db_session, review, body, operator=operator)
    assert (caught.value.status_code, caught.value.code) == (422, "VALIDATION_FAILED")
    return {(e["path"], e["code"]) for e in caught.value.field_errors}


def test_valid_decisions(db_session, review, glenfiddich):
    result = validate(db_session, review, valid_body(review, glenfiddich))

    assert [entry.index for entry in result.items] == [0, 1, 2, 3, 4]
    assert [entry.is_product for entry in result.items] == [False, True, False, True, False]
    exact = result.items[1]
    assert [(o.label, o.pour_ml, o.price_krw) for o in exact.options] == [(None, 15, 9000), (None, 30, 17000)]
    assert list(result.products) == [glenfiddich[12].id]
    assert len(result.change_decisions) == 3


def test_options_are_the_lines_final_list(db_session, review, glenfiddich):
    """Values are sent whole, an extracted option left out is not published, an added one has no
    extracted option, and a value can be cleared to null (spec 8.1)."""
    body = valid_body(review, glenfiddich)
    first_option = review[1][1].options[0]
    body["itemDecisions"][1]["options"] = [
        {"extractedOptionId": str(first_option.id), "optionLabel": "잔", "pourMl": None, "priceKrw": 9500},
        {"optionLabel": "병", "priceKrw": 160000},
    ]

    exact = validate(db_session, review, body).items[1]

    assert [(o.option, o.label, o.pour_ml, o.price_krw) for o in exact.options] == [
        (first_option, "잔", None, 9500),
        (None, "병", None, 160000),
    ]


def test_items_and_changes_must_each_be_decided_once(db_session, review, glenfiddich):
    body = valid_body(review, glenfiddich)
    body["itemDecisions"][4]["extractedItemId"] = str(uuid4())
    body["itemDecisions"][2]["extractedItemId"] = body["itemDecisions"][0]["extractedItemId"]
    body["changeDecisions"][0]["changeId"] = str(uuid4())
    body["changeDecisions"][1]["changeId"] = body["changeDecisions"][2]["changeId"]

    assert field_errors(db_session, review, body) == {
        ("itemDecisions[4].extractedItemId", "UNKNOWN_ITEM"),
        ("itemDecisions[2].extractedItemId", "DUPLICATE_ITEM"),
        ("itemDecisions", "MISSING_ITEM"),
        ("changeDecisions[0].changeId", "UNKNOWN_CHANGE"),
        ("changeDecisions[2].changeId", "DUPLICATE_CHANGE"),
        ("changeDecisions", "MISSING_CHANGE"),
    }


def test_options_must_name_the_lines_own_options_once(db_session, review, glenfiddich):
    body = valid_body(review, glenfiddich)
    exact, unknown = review[1][1], review[1][3]
    body["itemDecisions"][1]["options"] = [
        {"extractedOptionId": str(unknown.options[0].id), "priceKrw": 1000},
        {"extractedOptionId": str(exact.options[0].id), "pourMl": 15, "priceKrw": 1000},
        {"extractedOptionId": str(exact.options[0].id), "pourMl": 30, "priceKrw": 2000},
    ]

    assert field_errors(db_session, review, body) == {
        ("itemDecisions[1].options[0].extractedOptionId", "UNKNOWN_OPTION"),
        ("itemDecisions[1].options[2].extractedOptionId", "DUPLICATE_OPTION"),
    }


def test_published_options_need_distinct_label_and_pour(db_session, review, glenfiddich):
    body = valid_body(review, glenfiddich)
    body["itemDecisions"][1]["options"] = [{"pourMl": 30, "priceKrw": 9000}, {"pourMl": 30, "priceKrw": 17000}]

    assert field_errors(db_session, review, body) == {("itemDecisions[1].options", "DUPLICATE_OPTION_VALUES")}


def test_an_ignored_items_options_are_not_compared(db_session, review, glenfiddich):
    """The unknown line is kept as proposed (without a product, same name), so its ignored add skips it."""
    body = valid_body(review, glenfiddich)
    unknown = review[1][3]
    body["itemDecisions"][3] = {
        "action": "publish_without_product",
        "extractedItemId": str(unknown.id),
        "finalLineType": "product",
        "kind": "whisky",
        "options": [{"pourMl": 30, "priceKrw": 9000}, {"pourMl": 30, "priceKrw": 17000}],
    }
    add = review[2][MenuChangeType.ADD]
    for decision in body["changeDecisions"]:
        if decision["changeId"] == str(add.id):
            decision["decision"] = "ignore"

    assert validate(db_session, review, body).ignored_lines == {unknown.id}


# ---- publishing without a product (spec 8.10) ----


def without_product(body, index, kind="whisky", **fields):
    decision = body["itemDecisions"][index]
    body["itemDecisions"][index] = {
        "action": "publish_without_product",
        "extractedItemId": decision["extractedItemId"],
        "finalLineType": "product",
        "kind": kind,
        "options": decision.get("options") or [{"priceKrw": 12000}],
        **fields,
    }
    return body


def test_a_line_can_be_published_without_a_product(db_session, review, glenfiddich):
    body = without_product(valid_body(review, glenfiddich), 3, kind="other")

    result = validate(db_session, review, body)

    unknown = result.items[3]
    assert (unknown.is_product, unknown.is_unlinked, unknown.menu_name) == (True, True, "Unknown Distillery 25")
    # Its proposed add can be applied.
    assert len(result.change_decisions) == 3


def test_a_line_without_a_product_needs_a_name_with_a_key(db_session, review, glenfiddich):
    blank = without_product(valid_body(review, glenfiddich), 3, correctedProductName="!!")
    # The header line has no extracted product name, so it needs a corrected one.
    nameless = without_product(valid_body(review, glenfiddich), 0)

    assert field_errors(db_session, review, blank) == {("itemDecisions[3].correctedProductName", "NOT_NORMALIZABLE")}
    assert field_errors(db_session, review, nameless) == {("itemDecisions[0].correctedProductName", "NOT_NORMALIZABLE")}


def test_an_unknown_kind_is_a_shape_error():
    body = {
        "reviewVersion": 1,
        "itemDecisions": [
            {
                "action": "publish_without_product",
                "extractedItemId": str(uuid4()),
                "finalLineType": "product",
                "kind": "beer",
                "options": [{"priceKrw": 8000}],
            }
        ],
        "changeDecisions": [],
    }

    with pytest.raises(ValidationError) as caught:
        ReviewAndApplyRequest.model_validate(body)
    assert [(field_path(tuple(e["loc"])), e["type"]) for e in caught.value.errors()] == [
        ("itemDecisions[0].kind", "enum")
    ]


# ---- the catalog is the operators' (spec 2.2) ----


def test_only_an_operator_creates_products_or_adds_aliases(db_session, review, glenfiddich):
    body = valid_body(review, glenfiddich)
    body["itemDecisions"][1]["aliasesToAdd"] = [{"aliasText": "글렌피딕 십이년"}]

    validate(db_session, review, body)
    assert field_errors(db_session, review, body, operator=False) == {
        ("itemDecisions[1].aliasesToAdd", "OPERATOR_ONLY"),
        ("itemDecisions[3].action", "OPERATOR_ONLY"),
    }


def test_an_owner_may_send_no_aliases(db_session, review, glenfiddich):
    body = without_product(valid_body(review, glenfiddich), 3)
    body["itemDecisions"][1]["aliasesToAdd"] = []

    validate(db_session, review, body, operator=False)


def test_selected_products_and_brands_must_exist(db_session, review, glenfiddich):
    body = valid_body(review, glenfiddich)
    body["itemDecisions"][1]["productId"] = str(glenfiddich[21].id)
    body["itemDecisions"][3]["brand"] = {"type": "existing", "brandId": str(uuid4())}
    assert field_errors(db_session, review, body) == {
        ("itemDecisions[1].productId", "PRODUCT_INACTIVE"),
        ("itemDecisions[3].brand.brandId", "BRAND_NOT_FOUND"),
    }

    body["itemDecisions"][1]["productId"] = str(uuid4())
    body["itemDecisions"][3]["brand"] = {"type": "existing", "brandId": str(glenfiddich["brand"].id)}
    assert field_errors(db_session, review, body) == {("itemDecisions[1].productId", "PRODUCT_NOT_FOUND")}


def test_names_must_survive_normalization(db_session, review, glenfiddich):
    body = valid_body(review, glenfiddich)
    body["itemDecisions"][1]["correctedProductName"] = "!!"
    body["itemDecisions"][1]["aliasesToAdd"] = [{"aliasText": "글렌피딕 십이"}, {"aliasText": "@@"}]
    body["itemDecisions"][3]["brand"] = {"type": "new", "canonicalName": "?", "aliases": [{"aliasText": "~"}]}
    body["itemDecisions"][3]["product"]["displayName"] = "**"
    body["itemDecisions"][3]["aliases"] = [{"aliasText": "()"}]

    assert field_errors(db_session, review, body) == {
        ("itemDecisions[1].correctedProductName", "NOT_NORMALIZABLE"),
        ("itemDecisions[1].aliasesToAdd[1].aliasText", "NOT_NORMALIZABLE"),
        ("itemDecisions[3].brand.canonicalName", "NOT_NORMALIZABLE"),
        ("itemDecisions[3].brand.aliases[0].aliasText", "NOT_NORMALIZABLE"),
        ("itemDecisions[3].product.displayName", "NOT_NORMALIZABLE"),
        ("itemDecisions[3].aliases[0].aliasText", "NOT_NORMALIZABLE"),
    }


def test_applied_changes_need_their_item_kept_as_a_product(db_session, review, glenfiddich):
    body = valid_body(review, glenfiddich)
    body["itemDecisions"][1] = {"action": "reject", "extractedItemId": body["itemDecisions"][1]["extractedItemId"], "finalLineType": "product"}
    update = review[2][MenuChangeType.UPDATE]
    index = next(i for i, d in enumerate(body["changeDecisions"]) if d["changeId"] == str(update.id))

    assert field_errors(db_session, review, body) == {(f"changeDecisions[{index}].decision", "CHANGE_WITHOUT_PRODUCT")}
    body["changeDecisions"][index]["decision"] = "ignore"
    validate(db_session, review, body)


@pytest.mark.parametrize(
    ("decision", "expected"),
    [
        (
            {"action": "confirm_non_product", "finalLineType": "product"},
            ("itemDecisions[0].finalLineType", "LITERAL_ERROR"),
        ),
        (
            {"action": "confirm_non_product", "finalLineType": "unknown", "productId": str(uuid4())},
            ("itemDecisions[0].productId", "EXTRA_FORBIDDEN"),
        ),
        (
            {"action": "select_existing_product", "finalLineType": "section_header", "productId": str(uuid4())},
            ("itemDecisions[0].finalLineType", "LITERAL_ERROR"),
        ),
        ({"action": "merge", "finalLineType": "product"}, ("itemDecisions[0]", "UNION_TAG_INVALID")),
        (
            {
                "action": "select_existing_product",
                "finalLineType": "product",
                "productId": str(uuid4()),
                "options": [{"extractedOptionId": str(uuid4()), "priceKrw": 0}],
            },
            ("itemDecisions[0].options[0].priceKrw", "GREATER_THAN_EQUAL"),
        ),
        (
            {
                "action": "select_existing_product",
                "finalLineType": "product",
                "productId": str(uuid4()),
                "options": [{"priceKrw": 100_000_000}],
            },
            ("itemDecisions[0].options[0].priceKrw", "LESS_THAN_EQUAL"),
        ),
        (
            {"action": "select_existing_product", "finalLineType": "product", "productId": str(uuid4()), "options": []},
            ("itemDecisions[0].options", "TOO_SHORT"),
        ),
        (
            {
                "action": "select_existing_product",
                "finalLineType": "product",
                "productId": str(uuid4()),
                "options": [{"pourMl": ml, "priceKrw": 1000} for ml in range(1, 12)],
            },
            ("itemDecisions[0].options", "TOO_LONG"),
        ),
        (
            {"action": "select_existing_product", "finalLineType": "product", "productId": str(uuid4())},
            ("itemDecisions[0].options", "MISSING"),
        ),
        (
            {
                "action": "create_product",
                "finalLineType": "product",
                "brand": {"type": "new", "canonicalName": "X"},
                "product": {"displayName": "X", "category": "gin"},
                "options": [{"priceKrw": 1000}],
            },
            ("itemDecisions[0].product.category", "LITERAL_ERROR"),
        ),
        (
            {
                "action": "create_product",
                "finalLineType": "product",
                "brand": {"type": "existing"},
                "product": {"displayName": "X"},
                "options": [{"priceKrw": 1000}],
            },
            ("itemDecisions[0].brand.brandId", "MISSING"),
        ),
    ],
)
def test_request_shape_errors_use_request_paths(decision, expected):
    body = {"reviewVersion": 1, "itemDecisions": [{"extractedItemId": str(uuid4()), **decision}], "changeDecisions": []}

    with pytest.raises(ValidationError) as caught:
        ReviewAndApplyRequest.model_validate(body)

    assert expected in {(field_path(tuple(e["loc"])), e["type"].upper()) for e in caught.value.errors()}


def test_names_are_trimmed_and_blank_names_rejected():
    body = {
        "reviewVersion": 1,
        "itemDecisions": [
            {
                "action": "create_product",
                "extractedItemId": str(uuid4()),
                "finalLineType": "product",
                "brand": {"type": "new", "canonicalName": "  New Distillery "},
                "product": {"displayName": "   "},
                "options": [{"priceKrw": 1000}],
            }
        ],
        "changeDecisions": [],
    }

    with pytest.raises(ValidationError) as caught:
        ReviewAndApplyRequest.model_validate(body)
    assert [(field_path(tuple(e["loc"])), e["type"]) for e in caught.value.errors()] == [
        ("itemDecisions[0].product.displayName", "string_too_short")
    ]

    body["itemDecisions"][0]["product"]["displayName"] = " New Distillery 12 "
    decision = ReviewAndApplyRequest.model_validate(body).itemDecisions[0]
    assert (decision.brand.canonicalName, decision.product.displayName) == ("New Distillery", "New Distillery 12")


# ---- a change of several lines (spec 5.4, 8.7, 8.12) ----


def _select(body, index, product, item):
    body["itemDecisions"][index] = {
        "action": "select_existing_product",
        "extractedItemId": str(item.id),
        "finalLineType": "product",
        "productId": str(product.id),
        "options": [
            {"extractedOptionId": str(o.id), "pourMl": o.extracted_pour_ml, "priceKrw": o.extracted_price_krw}
            for o in item.options
        ],
    }


def test_a_change_of_two_lines_applies_while_either_line_is_published(db_session, review, glenfiddich):
    """Both 12 lines were proposed as Glenfiddich 12, so they are one change."""
    _, exact, conflict, *_ = review[1]
    update = review[2][MenuChangeType.UPDATE]
    body = valid_body(review, glenfiddich)
    body["itemDecisions"][1] = {"action": "reject", "extractedItemId": str(exact.id), "finalLineType": "product"}
    _select(body, 2, glenfiddich[12], conflict)

    result = validate(db_session, review, body)

    assert result.change_lines[update.id] == (exact.id, conflict.id)
    assert result.change_lines[review[2][MenuChangeType.REMOVE].id] == ()


def test_an_ignored_change_of_two_lines_skips_each_line_still_its_target(db_session, review, glenfiddich):
    _, exact, conflict, *_ = review[1]
    update = review[2][MenuChangeType.UPDATE]
    body = valid_body(review, glenfiddich)
    _select(body, 2, glenfiddich[12], conflict)
    for decision in body["changeDecisions"]:
        if decision["changeId"] == str(update.id):
            decision["decision"] = "ignore"

    assert validate(db_session, review, body).ignored_lines == {exact.id, conflict.id}
    # A line the reviewer decided to be another product follows that decision.
    _select(body, 2, glenfiddich[15], conflict)
    assert validate(db_session, review, body).ignored_lines == {exact.id}


# ---- prices of merged lines (spec 8.7, 8.12) ----


def _priced(body, index, prices):
    """The line's options replaced with (pour, price) pairs."""
    body["itemDecisions"][index]["options"] = [{"pourMl": pour, "priceKrw": price} for pour, price in prices]


def test_lines_sent_with_one_product_may_not_disagree_on_a_price(db_session, review, glenfiddich):
    _, exact, conflict, *_ = review[1]
    body = valid_body(review, glenfiddich)
    _select(body, 2, glenfiddich[12], conflict)
    _priced(body, 2, [(60, 30000), (30, 21000)])

    # The exact line has 30 ml at 17,000: the later line's option is the one reported.
    assert field_errors(db_session, review, body) == {("itemDecisions[2].options[1]", "OPTION_PRICE_CONFLICT")}
    _priced(body, 2, [(60, 30000), (30, 17000)])  # the same price is the same option
    validate(db_session, review, body)


def test_unlinked_lines_of_one_name_key_are_refused_only_when_none_is_a_whisky(db_session, review, glenfiddich):
    body = valid_body(review, glenfiddich)
    for index in (1, 3):
        line = review[1][index]
        body["itemDecisions"][index] = {
            "action": "publish_without_product",
            "extractedItemId": str(line.id),
            "finalLineType": "product",
            "kind": "other",
            "correctedProductName": "하이볼",
            "options": [{"pourMl": 30, "priceKrw": 9000 if index == 1 else 12000}],
        }
    assert field_errors(db_session, review, body) == {("itemDecisions[3].options[0]", "OPTION_PRICE_CONFLICT")}

    # With a whisky among them the server keeps the earlier price and the operator sees the other.
    body["itemDecisions"][3]["kind"] = "whisky"
    validate(db_session, review, body)
