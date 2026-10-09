# AI-generated with ChatGPT (Haeul Yang, 2026-10-06, PR #9). Reviewed by Haeul Yang.
from app.services.search_query import PARTIAL_LIMIT, resolve_search_query
from tests.factories import make_brand, make_product


def names(resolution):
    return [product.display_name for product in resolution.products]


def test_exact_product_alias_matches_after_normalization(db_session):
    brand = make_brand(db_session, "GlenDronach", aliases=("글렌드로낙",))
    make_product(db_session, brand, "GlenDronach 12", aliases=("글렌드로낙 12년",), age_years=12)
    make_product(db_session, brand, "GlenDronach 15", aliases=("글렌드로낙 15년",), age_years=15)

    resolution = resolve_search_query(db_session, " 글렌드로낙  12Y ")

    assert resolution.match_type == "alias_exact"
    assert resolution.normalized_query == "글렌드로낙12"
    assert names(resolution) == ["GlenDronach 12"]
    assert resolution.products[0].brand.canonical_name == "GlenDronach"


def test_alias_shared_by_several_products_returns_all_of_them(db_session):
    brand = make_brand(db_session, "Johnnie Walker")
    make_product(db_session, brand, "Johnnie Walker Black", aliases=("조니워커",))
    make_product(db_session, brand, "Johnnie Walker Blue", aliases=("조니워커",))

    resolution = resolve_search_query(db_session, "조니워커")

    assert resolution.match_type == "alias_exact"
    assert names(resolution) == ["Johnnie Walker Black", "Johnnie Walker Blue"]


def test_product_alias_wins_over_brand_alias(db_session):
    brand = make_brand(db_session, "Yoichi", aliases=("요이치",))
    make_product(db_session, brand, "Yoichi Single Malt", aliases=("요이치",))
    make_product(db_session, brand, "Yoichi 10", age_years=10)

    resolution = resolve_search_query(db_session, "요이치")

    assert resolution.match_type == "alias_exact"
    assert names(resolution) == ["Yoichi Single Malt"]


def test_unsearchable_alias_does_not_match(db_session):
    brand = make_brand(db_session, "Johnnie Walker")
    make_product(db_session, brand, "Johnnie Walker Black", unsearchable_aliases=("Jonnie walker black",))

    resolution = resolve_search_query(db_session, "Jonnie walker black")

    assert resolution.match_type == "none"
    assert resolution.products == []


def test_brand_alias_returns_active_products_of_the_brand(db_session):
    brand = make_brand(db_session, "Glenfiddich", aliases=("글렌피딕",))
    make_product(db_session, brand, "Glenfiddich 18", age_years=18)
    make_product(db_session, brand, "Glenfiddich 12", age_years=12)
    make_product(db_session, brand, "Glenfiddich 15", age_years=15, is_active=False)
    make_product(db_session, make_brand(db_session, "Other"), "Other 12")

    resolution = resolve_search_query(db_session, "글렌피딕")

    assert resolution.match_type == "brand"
    assert names(resolution) == ["Glenfiddich 12", "Glenfiddich 18"]


def test_inactive_product_alias_falls_through_to_the_next_step(db_session):
    brand = make_brand(db_session, "Talisker", aliases=("탈리스커",))
    make_product(db_session, brand, "Talisker 10", aliases=("탈리스커",), is_active=False)
    make_product(db_session, brand, "Talisker Storm")

    resolution = resolve_search_query(db_session, "탈리스커")

    assert resolution.match_type == "brand"
    assert names(resolution) == ["Talisker Storm"]


def test_brand_without_active_products_falls_through_to_partial(db_session):
    make_brand(db_session, "Ardbeg")
    other = make_brand(db_session, "Bottler")
    make_product(db_session, other, "Bottler Ardbeg 2009", aliases=("Ardbeg 2009 Bottler",))

    resolution = resolve_search_query(db_session, "ardbeg")

    assert resolution.match_type == "partial"
    assert names(resolution) == ["Bottler Ardbeg 2009"]


def test_partial_matches_aliases_containing_the_query(db_session):
    brand = make_brand(db_session, "GlenDronach")
    make_product(db_session, brand, "GlenDronach 12", aliases=("글렌드로낙 12년",))
    make_product(db_session, brand, "GlenDronach 15 Revival", aliases=("글렌드로낙 15년 리바이벌",))
    make_product(db_session, make_brand(db_session, "Other"), "Other 12", aliases=("다른 12년",))

    resolution = resolve_search_query(db_session, "드로낙")

    assert resolution.match_type == "partial"
    # The shorter matching alias ranks first.
    assert names(resolution) == ["GlenDronach 12", "GlenDronach 15 Revival"]


def test_partial_ignores_unsearchable_aliases_and_inactive_products(db_session):
    brand = make_brand(db_session, "Brand")
    make_product(db_session, brand, "Visible", aliases=("qwerty one",))
    make_product(db_session, brand, "Typo Only", unsearchable_aliases=("qwerty two",))
    make_product(db_session, brand, "Retired", aliases=("qwerty three",), is_active=False)

    assert names(resolve_search_query(db_session, "qwerty")) == ["Visible"]


def test_partial_is_limited_and_ordered_by_alias_length(db_session):
    brand = make_brand(db_session, "Brand")
    for n in range(PARTIAL_LIMIT + 2):
        make_product(db_session, brand, f"Product {n:02d}", aliases=("zx" + "y" * (n + 1),))

    resolution = resolve_search_query(db_session, "zx")

    assert resolution.match_type == "partial"
    assert names(resolution) == [f"Product {n:02d}" for n in range(PARTIAL_LIMIT)]


def test_no_match_returns_none(db_session):
    make_product(db_session, make_brand(db_session, "Lagavulin"), "Lagavulin 16")

    resolution = resolve_search_query(db_session, "없는위스키")

    assert (resolution.match_type, resolution.products) == ("none", [])
