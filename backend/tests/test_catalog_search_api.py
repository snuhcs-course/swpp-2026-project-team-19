import pytest

from tests.factories import make_brand, make_product


@pytest.fixture
def operator(token_for):
    return {"Authorization": f"Bearer {token_for('operator')}"}


@pytest.fixture
def catalog(db_session):
    glenfiddich = make_brand(db_session, "Glenfiddich", aliases=("글렌피딕",))
    glenfarclas = make_brand(db_session, "Glenfarclas", aliases=("글렌파클라스",))
    glen_scotia = make_brand(db_session, "Glen Scotia")
    return {
        "glenfiddich": glenfiddich,
        "glenfarclas": glenfarclas,
        "glen_scotia": glen_scotia,
        "g12": make_product(db_session, glenfiddich, "Glenfiddich 12", aliases=("글렌피딕 12년",), age_years=12),
        "g15": make_product(
            db_session, glenfiddich, "Glenfiddich 15", age_years=15, unsearchable_aliases=("글렌피딕15 솔레라",)
        ),
        "g21": make_product(db_session, glenfiddich, "Glenfiddich 21", age_years=21, is_active=False),
        "f105": make_product(db_session, glenfarclas, "Glenfarclas 105", aliases=("글렌파클라스 105",)),
    }


def get(client, path, headers, **params):
    response = client.get(path, params=params, headers=headers)
    assert response.status_code == 200, response.text
    return response.json()["items"]


def test_brand_exact_alias_comes_first(client, operator, catalog):
    items = get(client, "/api/catalog/brands", operator, query="glen")

    # No exact match: shortest matching alias first, then name.
    assert [(i["canonicalName"], i["matchedAlias"]) for i in items] == [
        ("Glen Scotia", "Glen Scotia"),
        ("Glenfarclas", "Glenfarclas"),
        ("Glenfiddich", "Glenfiddich"),
    ]
    [exact] = get(client, "/api/catalog/brands", operator, query=" 글렌피딕 ")
    assert exact == {
        "brandId": str(catalog["glenfiddich"].id),
        "canonicalName": "Glenfiddich",
        "matchedAlias": "글렌피딕",
    }


def test_brands_sharing_an_alias_are_all_returned(client, db_session, operator):
    make_brand(db_session, "Springbank", aliases=("SB",))
    make_brand(db_session, "Smokehead", aliases=("SB",))

    items = get(client, "/api/catalog/brands", operator, query="sb")

    assert [(i["canonicalName"], i["matchedAlias"]) for i in items] == [("Smokehead", "SB"), ("Springbank", "SB")]


def test_product_search_ranks_and_describes_products(client, operator, catalog):
    items = get(client, "/api/catalog/products", operator, query="글렌피딕 12년")

    assert items[0] == {
        "productId": str(catalog["g12"].id),
        "displayName": "Glenfiddich 12",
        "brandId": str(catalog["glenfiddich"].id),
        "brandName": "Glenfiddich",
        "category": "whisky",
        "ageYears": 12,
        "editionName": None,
        "abv": None,
        "isActive": True,
        "matchedAlias": "글렌피딕 12년",
    }
    # Shortest matching alias first ("glenfiddich12" before "glenfarclas105"), then name.
    assert [i["displayName"] for i in get(client, "/api/catalog/products", operator, query="glenf")] == [
        "Glenfiddich 12",
        "Glenfiddich 15",
        "Glenfiddich 21",
        "Glenfarclas 105",
    ]


def test_product_search_includes_inactive_products_and_hidden_aliases(client, operator, catalog):
    items = get(client, "/api/catalog/products", operator, query="글렌피딕15 솔레라")
    assert [(i["displayName"], i["matchedAlias"]) for i in items] == [("Glenfiddich 15", "글렌피딕15 솔레라")]

    inactive = get(client, "/api/catalog/products", operator, query="Glenfiddich 21")
    assert [(i["displayName"], i["isActive"]) for i in inactive] == [("Glenfiddich 21", False)]
    assert get(client, "/api/catalog/products", operator, query="Glenfiddich 21", includeInactive="false") == []


def test_product_search_by_brand_and_limit(client, operator, catalog):
    by_brand = get(client, "/api/catalog/products", operator, query="glen", brandId=str(catalog["glenfarclas"].id))
    assert [i["displayName"] for i in by_brand] == ["Glenfarclas 105"]

    limited = get(client, "/api/catalog/products", operator, query="glen", limit=2)
    assert len(limited) == 2


def test_no_match_is_an_empty_list(client, operator, catalog):
    assert get(client, "/api/catalog/brands", operator, query="없는브랜드") == []
    assert get(client, "/api/catalog/products", operator, query="없는상품") == []


@pytest.mark.parametrize("path", ["/api/catalog/brands", "/api/catalog/products"])
@pytest.mark.parametrize(
    ("params", "code"),
    [({}, "MISSING"), ({"query": "  "}, "BLANK"), ({"query": "!!!"}, "NOT_SEARCHABLE"), ({"query": "a", "limit": 51}, "LESS_THAN_EQUAL")],
)
def test_invalid_queries(client, operator, path, params, code):
    response = client.get(path, params=params, headers=operator)

    assert response.status_code == 422
    assert response.json()["error"]["fieldErrors"][0]["code"] == code


@pytest.mark.parametrize("path", ["/api/catalog/brands", "/api/catalog/products"])
def test_operators_only(client, token_for, path):
    customer = {"Authorization": f"Bearer {token_for('customer')}"}

    assert client.get(path, params={"query": "glen"}, headers=customer).status_code == 403
    assert client.get(path, params={"query": "glen"}).status_code == 401
