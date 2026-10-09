# AI-generated with ChatGPT (Haeul Yang, 2026-10-06, PR #12, #17). Reviewed by Haeul Yang.
import pytest
from sqlalchemy import select

from app.core.errors import ApiError
from app.models import Brand, BrandAlias, Product, ProductAlias
from app.schemas.menu_review import ReviewAndApplyRequest
from app.services.menu_review_catalog import create_catalog_entries
from app.services.menu_review_validation import validate_review
from tests.review_support import make_glenfiddich, upload_sample_review, valid_body


@pytest.fixture
def operator(token_for):
    return {"Authorization": f"Bearer {token_for('operator')}"}


@pytest.fixture
def glenfiddich(db_session):
    return make_glenfiddich(db_session)


@pytest.fixture
def sample(client, db_session, image_storage, operator, glenfiddich):
    return upload_sample_review(client, db_session, operator, glenfiddich)


def run(db_session, sample, body):
    review = validate_review(db_session, sample.menu_import, ReviewAndApplyRequest.model_validate(body))
    return create_catalog_entries(db_session, sample.menu_import, review)


def conflict(db_session, sample, body):
    with pytest.raises(ApiError) as caught:
        run(db_session, sample, body)
    assert caught.value.status_code == 409
    return caught.value


def aliases_of(db_session, model, owner_column, owner_id):
    rows = db_session.execute(select(model.alias_text, model.normalized_alias).where(owner_column == owner_id))
    # Sorted here: the database collation orders Korean and Latin text differently (C locally, en_US on RDS).
    return sorted(tuple(row) for row in rows)


def test_new_brand_and_product(db_session, sample, glenfiddich):
    body = valid_body(sample, glenfiddich)
    body["itemDecisions"][3]["brand"]["aliases"] = [{"aliasText": "언노운 디스틸러리", "languageCode": "ko"}]
    body["itemDecisions"][3]["product"].update({"editionName": "Cask Strength", "abv": 48.0})
    body["itemDecisions"][3]["aliases"] = [
        {"aliasText": "언노운 25년", "languageCode": "ko"},
        {"aliasText": "Unknown 25 CS", "isSearchable": False},
    ]
    unknown = sample.items[3]

    result = run(db_session, sample, body)

    assert (result.created_brands, result.created_products) == (1, 1)
    product = db_session.get(Product, result.product_ids[unknown.id])
    assert (product.display_name, product.age_years, product.edition_name, float(product.abv), product.category) == (
        "Unknown Distillery 25",
        25,
        "Cask Strength",
        48.0,
        "whisky",
    )
    assert (product.is_active, product.created_from_extracted_item_id) == (True, unknown.id)
    brand = db_session.get(Brand, product.brand_id)
    assert brand.canonical_name == "Unknown Distillery"
    assert aliases_of(db_session, BrandAlias, BrandAlias.brand_id, brand.id) == [
        ("Unknown Distillery", "unknowndistillery"),
        ("언노운 디스틸러리", "언노운디스틸러리"),
    ]
    assert aliases_of(db_session, ProductAlias, ProductAlias.product_id, product.id) == [
        ("Unknown 25 CS", "unknown25cs"),
        ("Unknown Distillery 25", "unknowndistillery25"),
        ("언노운 25년", "언노운25"),
    ]
    hidden = db_session.scalar(select(ProductAlias).where(ProductAlias.alias_text == "Unknown 25 CS"))
    assert hidden.is_searchable is False
    # The existing product selection is passed through.
    assert result.product_ids[sample.items[1].id] == glenfiddich[12].id


def test_new_product_of_an_existing_brand(db_session, sample, glenfiddich):
    body = valid_body(sample, glenfiddich)
    body["itemDecisions"][3]["brand"] = {"type": "existing", "brandId": str(glenfiddich["brand"].id)}
    # Same brand and age as Glenfiddich 12 but another edition: a different product.
    body["itemDecisions"][3]["product"] = {"displayName": "Glenfiddich 12 Sherry Cask", "ageYears": 12, "editionName": "Sherry Cask"}

    result = run(db_session, sample, body)

    product = db_session.get(Product, result.product_ids[sample.items[3].id])
    assert (product.brand_id, result.created_brands, result.created_products) == (glenfiddich["brand"].id, 0, 1)


@pytest.mark.parametrize("name", ["글렌피딕", "Glenfiddich", "GLENFIDDICH "])
def test_a_new_brand_that_exists_is_a_conflict(db_session, sample, glenfiddich, name):
    body = valid_body(sample, glenfiddich)
    body["itemDecisions"][3]["brand"]["canonicalName"] = name

    error = conflict(db_session, sample, body)

    assert error.code == "DUPLICATE_BRAND_FOUND"
    assert error.details == {
        "extractedItemId": str(sample.items[3].id),
        "existingBrand": {"brandId": str(glenfiddich["brand"].id), "canonicalName": "Glenfiddich"},
        "reviewUrl": f"/api/menu-imports/{sample.menu_import.id}",
    }


def test_a_brand_alias_that_exists_is_a_conflict(db_session, sample, glenfiddich):
    body = valid_body(sample, glenfiddich)
    body["itemDecisions"][3]["brand"]["aliases"] = [{"aliasText": "글렌피딕"}]

    assert conflict(db_session, sample, body).code == "DUPLICATE_BRAND_FOUND"


def test_a_product_with_an_existing_alias_is_a_conflict_even_when_inactive(db_session, sample, glenfiddich):
    body = valid_body(sample, glenfiddich)
    body["itemDecisions"][3]["brand"] = {"type": "existing", "brandId": str(glenfiddich["brand"].id)}
    body["itemDecisions"][3]["product"] = {"displayName": "Glenfiddich 21 Gran Reserva", "ageYears": 21, "editionName": "Gran Reserva"}
    body["itemDecisions"][3]["aliases"] = [{"aliasText": "Glenfiddich 21"}]

    error = conflict(db_session, sample, body)

    assert error.code == "DUPLICATE_PRODUCT_FOUND"
    assert error.details["existingProduct"] == {
        "productId": str(glenfiddich[21].id),
        "displayName": "Glenfiddich 21",
        "brandId": str(glenfiddich["brand"].id),
        "brandName": "Glenfiddich",
        "category": "whisky",
        "ageYears": 21,
        "editionName": None,
        "isActive": False,
    }


def test_a_product_with_the_same_attributes_is_a_conflict(db_session, sample, glenfiddich):
    body = valid_body(sample, glenfiddich)
    body["itemDecisions"][3]["brand"] = {"type": "existing", "brandId": str(glenfiddich["brand"].id)}
    body["itemDecisions"][3]["product"] = {"displayName": "Glenfiddich Twelve", "ageYears": 12}

    error = conflict(db_session, sample, body)

    assert error.details["existingProduct"]["productId"] == str(glenfiddich[12].id)


def test_rows_created_earlier_in_the_same_submission_are_reused(db_session, sample, glenfiddich):
    body = valid_body(sample, glenfiddich)
    new_product = body["itemDecisions"][3]
    second = {**new_product, "extractedItemId": body["itemDecisions"][2]["extractedItemId"]}
    body["itemDecisions"][2] = second  # the ambiguous line names the same new product

    result = run(db_session, sample, body)

    assert (result.created_brands, result.created_products) == (1, 1)
    assert result.product_ids[sample.items[2].id] == result.product_ids[sample.items[3].id]


def test_two_products_of_one_new_brand(db_session, sample, glenfiddich):
    body = valid_body(sample, glenfiddich)
    body["itemDecisions"][2] = {
        **body["itemDecisions"][3],
        "extractedItemId": body["itemDecisions"][2]["extractedItemId"],
        "product": {"displayName": "Unknown Distillery 18", "ageYears": 18},
    }

    result = run(db_session, sample, body)

    first, second = (db_session.get(Product, result.product_ids[sample.items[i].id]) for i in (2, 3))
    assert (result.created_brands, result.created_products) == (1, 2)
    assert first.brand_id == second.brand_id


def test_confirmed_aliases_are_added_once(db_session, sample, glenfiddich):
    body = valid_body(sample, glenfiddich)
    body["itemDecisions"][1]["aliasesToAdd"] = [
        {"aliasText": "글렌피딕 십이년", "languageCode": "ko"},
        {"aliasText": "글렌피딕 12년"},  # already an alias
        {"aliasText": "글렌피딕  십이년"},  # same after normalization
    ]

    run(db_session, sample, body)

    assert aliases_of(db_session, ProductAlias, ProductAlias.product_id, glenfiddich[12].id) == [
        ("Glenfiddich 12", "glenfiddich12"),
        ("글렌피딕 12년", "글렌피딕12"),
        ("글렌피딕 십이년", "글렌피딕십이년"),
    ]
