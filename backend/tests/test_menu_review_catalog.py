import pytest
from pydantic import TypeAdapter
from sqlalchemy import select

from app.core.errors import ApiError
from app.models import Brand, BrandAlias, Product, ProductAlias
from app.schemas.menu_review import BrandDecision, NewProduct, ProductAliasInput, ReviewAndApplyRequest
from app.services.menu_review_catalog import create_catalog_entries, create_new_product
from app.services.menu_review_validation import validate_review
from tests.factories import make_product, make_user
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
    return create_catalog_entries(db_session, sample.menu_import, review, created_by_user_id=None)


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


# ---- a manual add's new product (API spec 3.14.3) ----


def new_product(db_session, brand: dict, product: dict, aliases=(), user=None):
    return create_new_product(
        db_session,
        TypeAdapter(BrandDecision).validate_python(brand),
        NewProduct.model_validate(product),
        [ProductAliasInput.model_validate(alias) for alias in aliases],
        created_by_user_id=user.id if user else None,
    )


def test_a_manual_add_creates_a_product_of_an_existing_brand_and_records_the_user(db_session, glenfiddich):
    user = make_user(db_session)

    product_id = new_product(
        db_session,
        {"type": "existing", "brandId": str(glenfiddich["brand"].id)},
        {"displayName": "Glenfiddich Fire & Cane", "editionName": "Fire & Cane", "abv": 43.0},
        [{"aliasText": "글렌피딕 파이어 앤 케인", "languageCode": "ko"}],
        user,
    )

    product = db_session.get(Product, product_id)
    assert (product.brand_id, product.category, product.created_by_user_id) == (
        glenfiddich["brand"].id,
        "whisky",
        user.id,
    )
    assert product.created_from_extracted_item_id is None
    assert [text for text, _ in aliases_of(db_session, ProductAlias, ProductAlias.product_id, product_id)] == [
        "Glenfiddich Fire & Cane",
        "글렌피딕 파이어 앤 케인",
    ]


def test_a_manual_add_creates_a_new_brand_with_its_creator(db_session, glenfiddich):
    user = make_user(db_session)

    product_id = new_product(
        db_session, {"type": "new", "canonicalName": "Deanston"}, {"displayName": "Deanston Virgin Oak"}, user=user
    )

    brand = db_session.get(Product, product_id).brand
    assert (brand.canonical_name, brand.created_by_user_id) == ("Deanston", user.id)


def test_a_manual_add_of_an_existing_product_is_a_conflict_without_review_fields(db_session, glenfiddich):
    with pytest.raises(ApiError) as caught:
        new_product(
            db_session,
            {"type": "existing", "brandId": str(glenfiddich["brand"].id)},
            {"displayName": "Glenfiddich 21 Year", "ageYears": 21},
        )

    assert (caught.value.status_code, caught.value.code) == (409, "DUPLICATE_PRODUCT_FOUND")
    assert set(caught.value.details) == {"existingProduct"}
    assert caught.value.details["existingProduct"]["isActive"] is False


def test_a_manual_add_reuses_brand_found_by_alias_without_new_brand(db_session, glenfiddich):
    product_id = new_product(
        db_session, {"type": "new", "canonicalName": "글렌피딕"},
        {"displayName": "Glenfiddich BottleMap 88", "ageYears": 88, "editionName": "BottleMap"},
    )
    product = db_session.get(Product, product_id)
    assert product.brand_id == glenfiddich["brand"].id
    assert product.display_name == "Glenfiddich BottleMap 88"


def test_a_duplicate_matching_active_and_inactive_products_names_the_active_one(db_session, glenfiddich):
    brand = glenfiddich["brand"]
    # The inactive product sorts first by name, so only the active-first rule picks the other one.
    make_product(db_session, brand, "Aaa Glenfiddich Select", aliases=("셀렉트",), is_active=False)
    active = make_product(db_session, brand, "Glenfiddich Select", aliases=("셀렉트",))

    with pytest.raises(ApiError) as caught:
        new_product(db_session, {"type": "existing", "brandId": str(brand.id)}, {"displayName": "셀렉트"})

    assert caught.value.details["existingProduct"]["productId"] == str(active.id)


def test_a_duplicate_by_attributes_names_the_active_product_first(db_session, glenfiddich):
    brand = glenfiddich["brand"]
    make_product(db_session, brand, "Aaa Glenfiddich 40", age_years=40, is_active=False)
    active = make_product(db_session, brand, "Glenfiddich 40", age_years=40)

    with pytest.raises(ApiError) as caught:
        new_product(
            db_session, {"type": "existing", "brandId": str(brand.id)}, {"displayName": "Forty", "ageYears": 40}
        )

    assert caught.value.details["existingProduct"]["productId"] == str(active.id)
