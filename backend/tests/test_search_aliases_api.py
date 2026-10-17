# AI-generated with Claude Code/Claude Opus 5.5 (Haeul Yang, 2026-10-17). Reviewed by Haeul Yang.
"""Customer search finds the same whisky by its Korean and English names (API spec, section 3.10.1).

A product search must give the same response, apart from the `query` echo, whichever language,
spacing, letter case, age notation or digit width the customer types. A brand search gives the same
products; their order can differ only when one spelling is also a product's own alias.
"""

import pytest

from tests.factories import make_bar, make_brand, make_product, publish_menu

ORIGIN = {"lat": 37.478, "lng": 126.951}


@pytest.fixture
def glenfiddich(db_session):
    brand = make_brand(db_session, "Glenfiddich", aliases=("글렌피딕",))
    products = {
        age: make_product(db_session, brand, f"Glenfiddich {age}", aliases=(f"글렌피딕 {age}년",), age_years=age)
        for age in (12, 15, 18)
    }
    seorosang = make_bar(db_session, "Seorosang", latitude="37.477648", longitude="126.963763")
    malt = make_bar(db_session, "Malt House", latitude="37.484102", longitude="126.929815")
    publish_menu(
        db_session,
        seorosang,
        [(products[12], "글렌피딕 12년", [("잔", 30, 17000)]), (products[18], "글렌피딕 18년", [("잔", 30, 32000)])],
    )
    publish_menu(db_session, malt, [(products[12], "Glenfiddich 12Y", [(None, 15, 9000)])])
    return products


def search(client, query, **params):
    response = client.get("/api/search/bars", params={"query": query, **params})
    assert response.status_code == 200, response.text
    return response.json()


def without_query(body):
    """The response apart from `query`, which echoes what was typed."""
    return {key: value for key, value in body.items() if key != "query"}


def products_and_rows(body):
    return (
        {p["productId"] for p in body["matchedProducts"]},
        {(i["barId"], i["productId"]) for i in body["items"]},
    )


@pytest.mark.parametrize("location", [{}, ORIGIN], ids=["no location", "with location"])
def test_korean_and_english_product_names_give_the_same_result(client, glenfiddich, location):
    korean = search(client, "글렌피딕 12년", **location)
    english = search(client, "Glenfiddich 12", **location)

    assert without_query(korean) == without_query(english)
    assert korean["matchType"] == "alias_exact"
    assert [p["displayName"] for p in korean["matchedProducts"]] == ["Glenfiddich 12"]
    assert len(korean["items"]) == 2


@pytest.mark.parametrize(
    "query",
    [
        # spacing
        "글렌피딕12년",
        " 글렌 피딕  12 년 ",
        "Glen fiddich 12",
        "Glenfiddich12",
        # letter case
        "GLENFIDDICH 12",
        "glenfiddich 12",
        # age notation
        "Glenfiddich 12Y",
        "Glenfiddich 12yo",
        "Glenfiddich 12 years old",
        "Glenfiddich 12Years",
        "글렌피딕 12",
        "글렌피딕 12年",
        "글렌피딕 12y",
        # full-width letters and digits
        "글렌피딕 １２년",
        "Ｇｌｅｎｆｉｄｄｉｃｈ　１２",
        # Korean and English mixed
        "Glenfiddich 12년",
    ],
)
def test_spelling_variants_give_the_same_result(client, glenfiddich, query):
    expected = search(client, "Glenfiddich 12", **ORIGIN)

    assert without_query(search(client, query, **ORIGIN)) == without_query(expected)


@pytest.mark.parametrize(
    ("korean", "english", "product"),
    [("글렌피딕 15", "Glenfiddich 15", "Glenfiddich 15"), ("글렌피딕 18년", "Glenfiddich 18", "Glenfiddich 18")],
)
def test_the_age_picks_the_product(client, glenfiddich, korean, english, product):
    korean_body, english_body = search(client, korean), search(client, english)

    assert without_query(korean_body) == without_query(english_body)
    assert [p["displayName"] for p in korean_body["matchedProducts"]] == [product]
    # The 15 is not sold anywhere: recognized, but no rows rather than the 12's rows.
    assert {i["productDisplayName"] for i in korean_body["items"]} <= {product}


@pytest.mark.parametrize("query", ["Glenfiddich", "GLENFIDDICH", "glen fiddich", "글렌 피딕"])
def test_korean_and_english_brand_names_give_the_same_result(client, glenfiddich, query):
    # No product has the bare brand name as an alias, so even the order is the same.
    expected = search(client, "글렌피딕", **ORIGIN)

    body = search(client, query, **ORIGIN)

    assert without_query(body) == without_query(expected)
    assert body["matchType"] == "brand"
    assert [p["displayName"] for p in body["matchedProducts"]] == ["Glenfiddich 12", "Glenfiddich 15", "Glenfiddich 18"]


def test_every_spelling_of_a_brand_gives_the_same_products(client, db_session):
    # As in the service catalog: the flagship 12 has the brand name as an alias, the Korean names do not.
    brand = make_brand(db_session, "Royal Brackla", aliases=("로얄브라클라", "로열 브라클라"))
    twelve = make_product(db_session, brand, "Royal Brackla 12", aliases=("Royal Brackla", "로얄브라클라 12년"))
    eighteen = make_product(db_session, brand, "Royal Brackla 18", aliases=("로얄브라클라 18년",))
    bar = make_bar(db_session, "Seorosang")
    publish_menu(db_session, bar, [(twelve, "12", [(None, 30, 1)]), (eighteen, "18", [(None, 30, 1)])])

    bodies = [search(client, query) for query in ("Royal Brackla", "로얄브라클라", "로열 브라클라", "ROYAL BRACKLA")]

    assert {body["matchType"] for body in bodies} == {"brand"}
    assert all(products_and_rows(body) == products_and_rows(bodies[0]) for body in bodies)
    assert len(bodies[0]["matchedProducts"]) == 2
    # Only "Royal Brackla" is also the 12's own alias, so only it lists the 12 first on purpose.
    assert bodies[0]["matchedProducts"][0]["displayName"] == "Royal Brackla 12"


def test_korean_and_english_partial_names_give_the_same_products(client, glenfiddich):
    korean, english = search(client, "피딕"), search(client, "fiddich")

    assert korean["matchType"] == english["matchType"] == "partial"
    assert products_and_rows(korean) == products_and_rows(english)
    assert len(korean["matchedProducts"]) == 3
