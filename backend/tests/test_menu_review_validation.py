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


def validate(db_session, review, body):
    return validate_review(db_session, review[0], ReviewAndApplyRequest.model_validate(body))


def field_errors(db_session, review, body):
    with pytest.raises(ApiError) as caught:
        validate(db_session, review, body)
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


def test_option_corrections_replace_only_the_values_sent(db_session, review, glenfiddich):
    body = valid_body(review, glenfiddich)
    first_option = review[1][1].options[0]
    body["itemDecisions"][1]["optionDecisions"] = [
        {"extractedOptionId": str(first_option.id), "correctedPriceKrw": 9500, "correctedOptionLabel": "잔"}
    ]

    exact = validate(db_session, review, body).items[1]

    assert [(o.label, o.pour_ml, o.price_krw) for o in exact.options] == [("잔", 15, 9500), (None, 30, 17000)]


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


def test_option_decisions_must_name_the_items_options(db_session, review, glenfiddich):
    body = valid_body(review, glenfiddich)
    exact, unknown = review[1][1], review[1][3]
    body["itemDecisions"][1]["optionDecisions"] = [
        {"extractedOptionId": str(unknown.options[0].id), "correctedPriceKrw": 1000},
        {"extractedOptionId": str(exact.options[0].id), "correctedPriceKrw": 1000},
        {"extractedOptionId": str(exact.options[0].id), "correctedPriceKrw": 2000},
    ]

    assert field_errors(db_session, review, body) == {
        ("itemDecisions[1].optionDecisions[0].extractedOptionId", "UNKNOWN_OPTION"),
        ("itemDecisions[1].optionDecisions[2].extractedOptionId", "DUPLICATE_OPTION"),
    }


def test_published_products_need_distinct_priced_options(db_session, review, glenfiddich):
    body = valid_body(review, glenfiddich)
    exact = review[1][1]
    # The header line turned into a product has no options at all.
    body["itemDecisions"][0] = {
        "action": "select_existing_product",
        "extractedItemId": body["itemDecisions"][0]["extractedItemId"],
        "finalLineType": "product",
        "productId": str(glenfiddich[15].id),
    }
    body["itemDecisions"][1]["optionDecisions"] = [{"extractedOptionId": str(exact.options[1].id), "correctedPourMl": 15}]

    assert field_errors(db_session, review, body) == {
        ("itemDecisions[0].optionDecisions", "NO_PRICED_OPTION"),
        ("itemDecisions[1].optionDecisions", "DUPLICATE_OPTION_VALUES"),
    }


def test_an_ignored_item_needs_no_price(db_session, review, glenfiddich):
    unknown = review[1][3]
    unknown.options[0].extracted_price_krw = None
    db_session.flush()
    body = valid_body(review, glenfiddich)
    add = review[2][MenuChangeType.ADD]
    for decision in body["changeDecisions"]:
        if decision["changeId"] == str(add.id):
            decision["decision"] = "ignore"

    assert validate(db_session, review, body).items[3].priced_options == ()
    body["changeDecisions"] = [{**d, "decision": "apply"} for d in body["changeDecisions"]]
    assert field_errors(db_session, review, body) == {("itemDecisions[3].optionDecisions", "NO_PRICED_OPTION")}


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
                "optionDecisions": [{"extractedOptionId": str(uuid4()), "correctedPriceKrw": 0}],
            },
            ("itemDecisions[0].optionDecisions[0].correctedPriceKrw", "GREATER_THAN"),
        ),
        (
            {
                "action": "create_product",
                "finalLineType": "product",
                "brand": {"type": "existing"},
                "product": {"displayName": "X"},
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
