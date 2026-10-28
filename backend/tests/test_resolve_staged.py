from uuid import UUID

import pytest

from app.matching import ExtractedProduct, ProductInfo, resolve_product
from app.matching.memory_catalog import InMemoryCatalog
from app.matching.staged import resolve_product_staged


def _id(n: int) -> UUID:
    return UUID(int=n)


ABERLOUR, GLENFIDDICH, BUFFALO, MAKERS, MACALLAN, KAVALAN = (_id(100 + n) for n in range(6))
ABERLOUR_12, GLENFIDDICH_12, GLENFIDDICH_15, BUFFALO_TRACE, MAKERS_MARK = (_id(n) for n in range(1, 6))
MACALLAN_12_SHERRY, MACALLAN_12_DOUBLE, MACALLAN_15_DOUBLE = (_id(n) for n in range(6, 9))
SOLIST_SHERRY, SOLIST_VINHO, TRIPLE_SHERRY = (_id(n) for n in range(9, 12))


@pytest.fixture
def catalog():
    products = [
        ProductInfo(ABERLOUR_12, "Aberlour 12", age_years=12, brand_id=ABERLOUR),
        ProductInfo(GLENFIDDICH_12, "Glenfiddich 12", age_years=12, brand_id=GLENFIDDICH),
        ProductInfo(GLENFIDDICH_15, "Glenfiddich 15", age_years=15, brand_id=GLENFIDDICH),
        ProductInfo(BUFFALO_TRACE, "Buffalo Trace", brand_id=BUFFALO),
        ProductInfo(MAKERS_MARK, "Maker's Mark", brand_id=MAKERS),
        ProductInfo(MACALLAN_12_SHERRY, "Macallan 12 Sherry Oak", 12, "Sherry Oak", brand_id=MACALLAN),
        ProductInfo(MACALLAN_12_DOUBLE, "Macallan 12 Double Cask", 12, "Double Cask", brand_id=MACALLAN),
        ProductInfo(MACALLAN_15_DOUBLE, "Macallan 15 Double Cask", 15, "Double Cask", brand_id=MACALLAN),
        ProductInfo(SOLIST_SHERRY, "Kavalan Solist Oloroso Sherry", None, "Solist Oloroso Sherry", brand_id=KAVALAN),
        ProductInfo(SOLIST_VINHO, "Kavalan Solist Vinho Barrique", None, "Solist Vinho Barrique", brand_id=KAVALAN),
        ProductInfo(TRIPLE_SHERRY, "Kavalan Triple Sherry Cask", None, "Triple Sherry Cask", brand_id=KAVALAN),
    ]
    aliases = [
        (ABERLOUR_12, "Aberlour 12"),
        (ABERLOUR_12, "아벨라워 12년"),
        (GLENFIDDICH_12, "Glenfiddich 12"),
        (GLENFIDDICH_12, "글렌피딕 12년"),
        (GLENFIDDICH_15, "Glenfiddich 15"),
        (BUFFALO_TRACE, "Buffalo Trace"),
        (MAKERS_MARK, "Maker's Mark"),
        (MACALLAN_12_SHERRY, "Macallan 12 Sherry Oak"),
        (MACALLAN_12_SHERRY, "맥캘란 12년 셰리 오크"),
        (MACALLAN_12_DOUBLE, "Macallan 12 Double Cask"),
        (MACALLAN_12_DOUBLE, "맥캘란 12년 더블 캐스크"),
        (MACALLAN_15_DOUBLE, "Macallan 15 Double Cask"),
        (SOLIST_SHERRY, "Kavalan Solist Oloroso Sherry"),
        (SOLIST_SHERRY, "카발란 솔리스트 셰리"),
        (SOLIST_VINHO, "Kavalan Solist Vinho Barrique"),
        (TRIPLE_SHERRY, "Kavalan Triple Sherry Cask"),
        (TRIPLE_SHERRY, "카발란 트리플 셰리 캐스크"),
    ]
    brand_aliases = [
        (ABERLOUR, "Aberlour"),
        (ABERLOUR, "아벨라워"),
        (GLENFIDDICH, "Glenfiddich"),
        (MACALLAN, "Macallan"),
        (MACALLAN, "The Macallan"),
        (MACALLAN, "맥캘란"),
        (KAVALAN, "Kavalan"),
        (KAVALAN, "카발란"),
    ]
    return InMemoryCatalog(products, aliases, brand_aliases)


def s1(name: str, catalog, **fields):
    return resolve_product_staged(ExtractedProduct(product_name=name, **fields), catalog, {"S1"})


def test_no_stages_is_resolve_product(catalog):
    for name in ("아벨라워(Aberlour) 12년", "Buffalo Trace / Maker's Mark", "Glenfiddich 12", None):
        item = ExtractedProduct(product_name=name)
        assert resolve_product_staged(item, catalog) == resolve_product(item, catalog)


def test_unknown_stage_is_rejected(catalog):
    with pytest.raises(ValueError):
        resolve_product_staged(ExtractedProduct(product_name="Aberlour 12"), catalog, {"S9"})


@pytest.mark.parametrize("name", ["아벨라워(Aberlour) 12년", "Aberlour (아벨라워) 12Y", "아벨라워 (Aberlour)12년"])
def test_parenthesized_name_is_looked_up_both_ways(catalog, name):
    assert resolve_product(ExtractedProduct(product_name=name), catalog).status == "unmatched"

    result = s1(name, catalog)

    assert result.status == "exact_match"
    assert result.proposed_product_id == ABERLOUR_12
    assert result.candidates[0].evidence["parenExpanded"] in ("아벨라워 12년", "Aberlour 12년", "Aberlour 12Y")


def test_parenthesized_name_keeps_the_age_conflict_check(catalog):
    result = s1("아벨라워(Aberlour) 12년", catalog, age_years=15)

    assert result.status == "ambiguous"
    assert result.candidates[0].evidence["ageConflict"] is True


def test_two_products_of_different_brands_are_multi(catalog):
    result = s1("Buffalo Trace / Maker's Mark", catalog)

    assert result.status == "multi"
    assert result.proposed_product_id is None
    assert [part.proposed_product_id for part in result.parts] == [BUFFALO_TRACE, MAKERS_MARK]
    assert [part.status for part in result.parts] == ["exact_match", "exact_match"]
    assert [c.product_id for c in result.candidates] == [BUFFALO_TRACE, MAKERS_MARK]
    assert result.candidates[1].evidence["multiProduct"] == "Maker's Mark"


def test_two_products_need_both_sides_exact(catalog):
    # A typo on one side: M0 behaviour (the side that matched) is kept.
    result = s1("Buffalo Trace / Makrt's Mark", catalog)

    assert result.status == "exact_match"
    assert result.proposed_product_id == BUFFALO_TRACE


def test_two_products_of_the_same_brand_are_not_multi(catalog):
    result = s1("Glenfiddich 12 / Glenfiddich 15", catalog)

    assert result.status == "ambiguous"
    assert result.parts == ()


def test_korean_english_pair_stays_one_product(catalog):
    result = s1("글렌피딕 12년 / Glenfiddich 12", catalog)

    assert result.status == "exact_match"
    assert result.proposed_product_id == GLENFIDDICH_12
    assert result.parts == ()


def test_korean_english_pair_of_different_products_is_not_multi(catalog):
    # Different scripts mean "Korean / English" of one line, never two products.
    result = s1("아벨라워 12년 / Glenfiddich 12", catalog)

    assert result.status == "ambiguous"


def s2(name: str, catalog, **fields):
    return resolve_product_staged(ExtractedProduct(product_name=name, **fields), catalog, {"S1", "S2"})


def test_s2_needs_s1(catalog):
    with pytest.raises(ValueError):
        resolve_product_staged(ExtractedProduct(product_name="Macallan 15yo"), catalog, {"S2"})


def test_s2_does_not_touch_alias_matches(catalog):
    for name in ("Macallan 12 Sherry Oak", "맥캘란 12년 셰리 오크", "Glenfiddich 12 / Glenfiddich 15"):
        assert s2(name, catalog) == s1(name, catalog)


def test_brand_and_the_only_product_of_that_age_is_exact(catalog):
    assert s1("Macallan 15yo", catalog).status == "unmatched"

    result = s2("Macallan 15yo", catalog)

    assert result.status == "exact_match"
    assert result.proposed_product_id == MACALLAN_15_DOUBLE
    assert result.candidates[0].evidence == {
        "brandMatch": "macallan", "ageMatch": 15, "brandName": "Macallan 15yo", "rule": "S2"
    }


def test_edition_token_picks_one_of_the_products_of_that_age(catalog):
    result = s2("맥캘란 더블캐스크 12Y", catalog)

    assert result.status == "exact_match"
    assert result.proposed_product_id == MACALLAN_12_DOUBLE
    evidence = result.candidates[0].evidence
    assert (evidence["brandMatch"], evidence["ageMatch"], evidence["editionMatch"]) == ("맥캘란", 12, ["더블캐스크"])


def test_brand_found_without_spaces_and_in_parentheses(catalog):
    assert s2("맥캘란15년", catalog).proposed_product_id == MACALLAN_15_DOUBLE
    result = s2("맥켈란(The Macallan) 15Y", catalog)
    assert result.status == "exact_match"
    assert result.proposed_product_id == MACALLAN_15_DOUBLE


def test_same_age_several_products_is_ambiguous(catalog):
    result = s2("Macallan 12yo", catalog)

    assert result.status == "ambiguous"
    assert {c.product_id for c in result.candidates} == {MACALLAN_12_SHERRY, MACALLAN_12_DOUBLE}


def test_age_conflict_is_never_exact(catalog):
    # No Macallan 18 in the catalog: the 12 and 15 year products are not offered.
    assert s2("Macallan 18yo", catalog).status == "unmatched"
    # The extracted age is used when the name has none, and it conflicts too.
    assert s2("Macallan Double Cask", catalog, age_years=18).status == "unmatched"


def test_edition_token_that_fits_no_product_blocks_exact(catalog):
    result = s2("Macallan 15yo Sherry Oak", catalog)

    assert result.status == "ambiguous"
    assert result.proposed_product_id == MACALLAN_15_DOUBLE
    assert result.candidates[0].evidence["editionUnmatched"] == ["sherry", "oak"]


def test_without_age_edition_tokens_must_pick_one_product(catalog):
    assert s2("카발란 트리플 셰리", catalog).proposed_product_id == TRIPLE_SHERRY
    assert s2("카발란 트리플 셰리", catalog).status == "exact_match"

    solist = s2("Kavalan Solist", catalog)
    assert solist.status == "ambiguous"
    assert {c.product_id for c in solist.candidates} == {SOLIST_SHERRY, SOLIST_VINHO}

    # Brand only: the owner chooses.
    assert s2("Kavalan", catalog).status == "ambiguous"
    # Nothing in the name fits any Kavalan product.
    assert s2("Kavalan Distillery Reserve", catalog).status == "unmatched"


def test_short_and_neutral_tokens(catalog):
    # "PX" is too short to check, so it blocks exact; "Whisky" is ignored.
    assert s2("Macallan 15yo PX", catalog).status == "ambiguous"
    assert s2("Macallan 15yo Whisky", catalog).status == "exact_match"


def test_unknown_brand_is_unmatched(catalog):
    assert s2("Dalwhinny 15yo", catalog).status == "unmatched"


def test_two_products_found_by_brand_and_age(catalog):
    result = s2("Macallan 15yo / Aberlour 12yo", catalog)

    assert result.status == "multi"
    assert [part.proposed_product_id for part in result.parts] == [MACALLAN_15_DOUBLE, ABERLOUR_12]


# --- S2b: default product, S3: edit distance -----------------------------------------

FIDDICH = _id(200)
FIDDICH_12, FIDDICH_12_SHERRY, FIDDICH_15_SOLERA = (_id(n) for n in range(201, 204))


@pytest.fixture
def glenfiddich():
    products = [
        ProductInfo(FIDDICH_12, "Glenfiddich 12", age_years=12, brand_id=FIDDICH),
        ProductInfo(FIDDICH_12_SHERRY, "Glenfiddich 12 Sherry Cask Finish", 12, "Sherry Cask Finish", brand_id=FIDDICH),
        ProductInfo(FIDDICH_15_SOLERA, "Glenfiddich 15 Solera", 15, "Solera", brand_id=FIDDICH),
    ]
    aliases = [(product.product_id, product.display_name) for product in products]
    return InMemoryCatalog(products, aliases, [(FIDDICH, "Glenfiddich"), (FIDDICH, "글렌피딕")])


def staged(name: str, catalog, *stages: str):
    return resolve_product_staged(ExtractedProduct(product_name=name), catalog, {"S1", "S2", *stages})


def test_s2b_and_s3_need_the_stage_below(glenfiddich):
    with pytest.raises(ValueError):
        resolve_product_staged(ExtractedProduct(product_name="x"), glenfiddich, {"S1", "S2b"})
    with pytest.raises(ValueError):
        resolve_product_staged(ExtractedProduct(product_name="x"), glenfiddich, {"S1", "S2", "S3"})


def test_default_product_without_edition_wins_when_no_edition_token(glenfiddich):
    assert staged("글렌피딕 12년", glenfiddich).status == "ambiguous"  # S2 alone

    result = staged("글렌피딕 12년", glenfiddich, "S2b")

    assert result.status == "exact_match"
    assert result.proposed_product_id == FIDDICH_12
    assert result.candidates[0].evidence["defaultProduct"] is True


def test_edition_token_still_picks_the_edition_product(glenfiddich):
    result = staged("Glenfiddich 12yo Sherry", glenfiddich, "S2b")

    assert result.status == "exact_match"
    assert result.proposed_product_id == FIDDICH_12_SHERRY


def test_only_product_of_that_age_with_an_edition_is_confirm_recommended(glenfiddich):
    assert staged("글렌피딕 15년", glenfiddich).status == "exact_match"  # S2 alone

    result = staged("글렌피딕 15년", glenfiddich, "S2b")

    assert result.status == "ambiguous"
    [candidate] = result.candidates
    assert candidate.product_id == FIDDICH_15_SOLERA
    assert candidate.evidence["confirmRecommended"] is True


def test_s2b_leaves_the_s2_cases_with_several_editions_ambiguous(catalog):
    result = staged("Macallan 12yo", catalog, "S2b")

    assert result.status == "ambiguous"
    assert {c.product_id for c in result.candidates} == {MACALLAN_12_SHERRY, MACALLAN_12_DOUBLE}
    assert all("confirmRecommended" not in c.evidence for c in result.candidates)


def test_edit_distance_counts_hangul_syllables():
    from app.matching.staged import edit_distance

    assert edit_distance("납크릭", "놉크릭", 1) == 1
    assert edit_distance("dalwhinny", "dalwhinnie", 2) == 2
    assert edit_distance("dalwhinny", "dalwhinnie", 1) == 2  # over the limit -> limit + 1


def test_edit_distance_needs_the_same_digits(glenfiddich):
    s3 = ("S2b", "S3")
    # 16 and 18 are not in the catalog; "glenfiddich15..." is never a candidate.
    assert staged("Glenfiddich 16yo", glenfiddich, *s3).status == "unmatched"
    assert staged("Glenfidich 18yo", glenfiddich, *s3).status == "unmatched"


def test_edit_distance_one_with_digits_and_one_candidate_is_exact(glenfiddich):
    result = staged("Glenfidich 12yo", glenfiddich, "S2b", "S3")

    assert staged("Glenfidich 12yo", glenfiddich, "S2b").status == "unmatched"
    assert result.status == "exact_match"
    assert result.proposed_product_id == FIDDICH_12
    assert result.candidates[0].evidence["editDistance"] == 1


def test_edit_distance_two_is_confirm_recommended(glenfiddich):
    result = staged("Glanfidich 15yo", glenfiddich, "S2b", "S3")

    assert result.status == "ambiguous"
    [candidate] = result.candidates
    assert candidate.product_id == FIDDICH_15_SOLERA
    assert candidate.evidence["editDistance"] == 2
    assert candidate.evidence["confirmRecommended"] is True


def test_edit_distance_without_digits_is_never_exact(catalog):
    result = staged("Makers Mork", catalog, "S2b", "S3")

    assert result.status == "ambiguous"
    assert result.proposed_product_id == MAKERS_MARK
    assert result.candidates[0].evidence["confirmRecommended"] is True


def test_edit_distance_ties_are_ambiguous():
    first, second = _id(301), _id(302)
    catalog = InMemoryCatalog(
        [ProductInfo(first, "Abcd 10", 10), ProductInfo(second, "Abce 10", 10)],
        [(first, "Abcd 10"), (second, "Abce 10")],
    )

    result = staged("Abcf 10", catalog, "S2b", "S3")

    assert result.status == "ambiguous"
    assert {c.product_id for c in result.candidates} == {first, second}
    assert all("confirmRecommended" not in c.evidence for c in result.candidates)


def test_s3_runs_only_when_s2_found_nothing(catalog):
    # S2 already offers the Kavalan Solist products; S3 does not add anything.
    assert staged("Kavalan Solist", catalog, "S2b", "S3") == staged("Kavalan Solist", catalog, "S2b")


# ---- I2-A22: the step that found each candidate is recorded as evidence["rule"] ----


def rules(result):
    return [c.evidence.get("rule") for c in result.candidates]


def test_no_stages_records_no_rule(catalog):
    result = resolve_product_staged(ExtractedProduct(product_name="Glenfiddich 12"), catalog)

    assert result.status == "exact_match"
    assert rules(result) == [None]


def test_rule_of_each_step(catalog, glenfiddich):
    cases = [
        (staged("Glenfiddich 12", glenfiddich, "S2b", "S3"), "exact_match", "alias"),
        (s1("아벨라워(Aberlour) 12년", catalog), "exact_match", "S1"),
        (staged("맥캘란 더블캐스크 12Y", catalog), "exact_match", "S2"),
        (staged("글렌피딕 12년", glenfiddich, "S2b"), "exact_match", "S2b"),  # default product
        (staged("글렌피딕 15년", glenfiddich, "S2b"), "ambiguous", "S2b"),  # confirm recommended
        (staged("Glenfidich 12yo", glenfiddich, "S2b", "S3"), "exact_match", "S3"),
        (staged("Glanfidich 15yo", glenfiddich, "S2b", "S3"), "ambiguous", "S3"),
    ]
    for result, status, rule in cases:
        assert result.status == status
        assert rules(result) == [rule] * len(result.candidates)


def test_two_products_on_one_line_are_an_s1_rule(catalog):
    assert rules(s1("Buffalo Trace / Maker's Mark", catalog)) == ["S1", "S1"]


def test_ambiguous_s2_candidates_record_s2(catalog):
    result = staged("Macallan 12yo", catalog, "S2b")

    assert result.status == "ambiguous"
    assert rules(result) == ["S2", "S2"]


# ---- I3-A4: safety rules (short Hangul names, editions only in the product) and vocabulary ----

MENU_STAGES = ("S1", "S2", "S2b", "S3")
BOWMORE, ARRAN, ANCNOC = (_id(400 + n) for n in range(3))
BOWMORE_18, ARRAN_18, ANCNOC_12, ANCNOC_PEATED_SHERRY, LAPHROAIG_10 = (_id(n) for n in range(401, 406))


@pytest.fixture
def islands():
    products = [
        ProductInfo(BOWMORE_18, "Bowmore 18", age_years=18, brand_id=BOWMORE),
        ProductInfo(ARRAN_18, "Arran 18", age_years=18, brand_id=ARRAN),
        ProductInfo(ANCNOC_12, "anCnoc 12", age_years=12, brand_id=ANCNOC),
        ProductInfo(ANCNOC_PEATED_SHERRY, "anCnoc Peated Sherry Cask", None, "Peated Sherry Cask", brand_id=ANCNOC),
        ProductInfo(LAPHROAIG_10, "Laphroaig 10", age_years=10),
    ]
    aliases = [(product.product_id, product.display_name) for product in products]
    aliases += [(BOWMORE_18, "보모어 18년"), (ARRAN_18, "아란 18년"), (LAPHROAIG_10, "라프로익 10년")]
    aliases += [(ANCNOC_PEATED_SHERRY, "아녹 피티드 셰리")]
    brand_aliases = [(BOWMORE, "Bowmore"), (ARRAN, "Arran"), (ANCNOC, "anCnoc"), (ANCNOC, "아녹")]
    return InMemoryCatalog(products, aliases, brand_aliases)


def menu(name: str, catalog):
    return resolve_product_staged(ExtractedProduct(product_name=name), catalog, MENU_STAGES)


def test_short_hangul_name_one_syllable_off_is_not_confirmed(islands):
    # 달모어 18 is one syllable from 보모어 18, 아녹 18 from 아란 18: other brands, not typos.
    assert menu("달모어(Dalmore) 18년", islands).status == "unmatched"
    assert menu("아녹 18", islands).status == "unmatched"
    # Four syllables or more is still a typo of that product.
    result = menu("라프로윅 10년", islands)
    assert result.status == "exact_match"
    assert result.proposed_product_id == LAPHROAIG_10


def test_short_hangul_brand_one_syllable_off_is_not_confirmed():
    # Only a brand alias is close, so the brand-distance path of S3 is the one tried.
    catalog = InMemoryCatalog(
        [ProductInfo(BOWMORE_18, "Bowmore 18", age_years=18, brand_id=BOWMORE)],
        [(BOWMORE_18, "Bowmore 18")],
        [(BOWMORE, "Bowmore"), (BOWMORE, "보모어")],
    )
    assert menu("달모어 18년", catalog).status == "unmatched"
    assert menu("Bowmor 18", catalog).proposed_product_id == BOWMORE_18
    assert menu("Bowmor 18", catalog).status == "exact_match"


def test_short_hangul_name_check():
    from app.matching.staged import _short_hangul_name

    assert _short_hangul_name("달모어18")
    assert _short_hangul_name("18아녹")
    assert not _short_hangul_name("라프로윅10")
    assert not _short_hangul_name("bowmor18")
    assert not _short_hangul_name("")


def test_edition_words_only_in_the_product_need_confirmation(islands):
    # "Sherry" fits only Peated Sherry Cask, but "Peated" is not on the line.
    result = menu("anCnoc Sherry (아녹)", islands)

    assert result.status == "ambiguous"
    [candidate] = result.candidates
    assert candidate.product_id == ANCNOC_PEATED_SHERRY
    assert candidate.evidence["editionOnlyInProduct"] == ["peated"]
    assert candidate.evidence["confirmRecommended"] is True
    assert candidate.evidence["rule"] == "S2"
    # The brand written again in parentheses is not an edition token.
    assert "editionUnmatched" not in candidate.evidence


def test_every_edition_word_on_the_line_is_exact(islands):
    for name in ("anCnoc Peated Sherry", "아녹 셰리 피티드", "아녹(anCnoc) 피티드 쉐리 캐스크"):
        result = menu(name, islands)
        assert result.status == "exact_match", name
        assert result.proposed_product_id == ANCNOC_PEATED_SHERRY


def test_a_product_alias_covers_korean_edition_words(catalog, monkeypatch):
    # Without the vocabulary, "더블캐스크" is still covered by the alias "맥캘란 12년 더블 캐스크".
    monkeypatch.setattr("app.matching.staged._VOCABULARY", None)

    assert staged("맥캘란 더블캐스크 12Y", catalog).status == "exact_match"
    result = staged("카발란 트리플 셰리", catalog)
    assert result.status == "ambiguous"
    assert result.candidates[0].evidence["editionOnlyInProduct"] == ["triple", "sherry"]


def test_brand_written_again_is_not_an_edition_token(catalog):
    # Neither the token "맥캘란" nor the variant "맥캘란" (every Macallan product) gets in the way.
    result = s2("Macallan 15yo (맥캘란)", catalog)
    assert result.status == "exact_match"
    assert result.proposed_product_id == MACALLAN_15_DOUBLE
    # A brand-only name is still used when nothing else finds a product.
    result = s2("Macallan Blue (맥캘란)", catalog)
    assert result.status == "ambiguous"
    assert len(result.candidates) == 3


def test_tokens_too_short_to_check_do_not_rule_products_out(catalog):
    result = s2("Kavalan DR", catalog)

    assert result.status == "ambiguous"
    assert {c.product_id for c in result.candidates} == {SOLIST_SHERRY, SOLIST_VINHO, TRIPLE_SHERRY}


def test_korean_whisky_words_are_tried_in_english(catalog):
    # "쉐리오크" is not in any alias; in English it is "sherry oak".
    result = staged("맥캘란 12년 쉐리오크", catalog, "S2b", "S3")

    assert result.status == "exact_match"
    assert result.proposed_product_id == MACALLAN_12_SHERRY
    assert result.candidates[0].evidence["vocabulary"] == "맥캘란 12년 sherry oak"
    assert result.candidates[0].evidence["rule"] == "S2"


def test_vocabulary_retry_is_taken_only_when_it_helps(catalog, monkeypatch):
    # The English name does not confirm the line: the first result is kept.
    result = staged("맥캘란 12년 블루", catalog, "S2b", "S3")
    assert result.status == "ambiguous"
    assert all("vocabulary" not in c.evidence for c in result.candidates)
    # Confirmed lines and names without a vocabulary word are not tried again.
    assert "vocabulary" not in staged("맥캘란 12년 셰리 오크", catalog, "S2b").candidates[0].evidence
    assert staged("Glenfiddich 16yo", catalog, "S2b", "S3").status == "unmatched"
    # S1 alone never uses the vocabulary.
    assert s1("맥캘란 12년 쉐리오크", catalog).status == "unmatched"
    monkeypatch.setattr("app.matching.staged._VOCABULARY", None)
    assert staged("맥캘란 12년 쉐리오크", catalog, "S2b", "S3").status == "ambiguous"


def test_vocabulary_gives_candidates_to_a_line_that_had_none():
    triple = _id(501)
    catalog = InMemoryCatalog(
        [ProductInfo(triple, "Kavalan Triple Sherry Cask", None, "Triple Sherry Cask", brand_id=KAVALAN)],
        [(triple, "Kavalan Triple Sherry Cask")],
        [(KAVALAN, "Kavalan")],
    )
    # Without the vocabulary neither "카발란" nor "트리플" is known.
    assert menu("카발란 트리플", catalog).candidates[0].evidence["vocabulary"] == "kavalan triple"
    result = menu("Kavalan 트리플", catalog)
    assert result.status == "ambiguous"
    [candidate] = result.candidates
    assert candidate.product_id == triple
    assert candidate.evidence["editionOnlyInProduct"] == ["sherry"]
    assert candidate.evidence["vocabulary"] == "Kavalan triple"


def test_a_product_without_edition_has_no_edition_words_to_check():
    # The token "피딕" fits the alias "글렌피딕 12년" of a product with no edition name.
    brand, twelve = _id(601), _id(602)
    catalog = InMemoryCatalog(
        [ProductInfo(twelve, "Glenfiddich 12", age_years=12, brand_id=brand)],
        [(twelve, "Glenfiddich 12"), (twelve, "글렌피딕 12년")],
        [(brand, "Glenfiddich")],
    )

    result = menu("Glenfiddich 피딕 12", catalog)

    assert result.status == "exact_match"
    assert result.candidates[0].evidence["editionMatch"] == ["피딕"]


# ---- I3-A4 review fixes ----

KIM, OCTOMORE, MACALLAN_CUT = (_id(700 + n) for n in range(3))
KIM_3, KIM_4, OCTO_14, OCTO_16, CUT_2020, KIM_PLAIN = (_id(n) for n in range(711, 717))


@pytest.fixture
def numbered():
    products = [
        ProductInfo(KIM_3, "Kim Gwajang #3 Highland Park", None, "#3 Highland Park", brand_id=KIM),
        ProductInfo(KIM_4, "Kim Gwajang #4 Clynelish", None, "#4 Clynelish", brand_id=KIM),
        ProductInfo(KIM_PLAIN, "Kim Gwajang Blend", None, "Blend", brand_id=KIM),
        ProductInfo(OCTO_14, "Octomore 14.1", None, "14.1", brand_id=OCTOMORE),
        ProductInfo(CUT_2020, "The Macallan Classic Cut 2020", None, "Classic Cut 2020", brand_id=MACALLAN_CUT),
    ]
    aliases = [(product.product_id, product.display_name) for product in products]
    brand_aliases = [(KIM, "Kim Gwajang"), (KIM, "김과장"), (OCTOMORE, "Octomore"), (OCTOMORE, "옥토모어")]
    brand_aliases += [(MACALLAN_CUT, "Macallan"), (MACALLAN_CUT, "맥캘란")]
    return InMemoryCatalog(products, aliases, brand_aliases)


def test_a_different_number_on_the_line_rules_a_product_out(numbered):
    assert [c.product_id for c in menu("김과장 #3 Highland Park", numbered).candidates] == [KIM_3]
    # "#4" is not #3: Highland Park fits, but the number rules the product out.
    assert menu("김과장 #4 Highland Park", numbered).status == "unmatched"
    # Years and decimals too, also through a variant that is only the brand.
    assert menu("맥캘란 클래식컷 2025", numbered).status == "unmatched"
    assert menu("Octomore 16.2 (옥토모어)", numbered).status == "unmatched"
    # The same number keeps the product.
    assert menu("Octomore 14.1", numbered).proposed_product_id == OCTO_14


def test_number_conflict_ignores_the_age():
    from app.matching.staged import _number_conflict

    eight = ProductInfo(_id(720), "Wild Turkey 101 8 Year", 8)
    assert not _number_conflict(eight, ["101"])
    assert _number_conflict(eight, ["81"])
    assert not _number_conflict(ProductInfo(_id(721), "Laphroaig 10", 10), ["2023"])


def test_short_letter_tokens_only_do_not_rule_products_out(numbered, catalog):
    # "DR" cannot be checked, so every Kavalan product stays; "#2" (a number) still decides.
    assert len(s2("Kavalan DR", catalog).candidates) == 3
    assert menu("김과장 #2", numbered).status == "unmatched"


@pytest.mark.parametrize("name", ["더 달무어 18", "The 달무어 18", "달무어-18", "달-무어 18"])
def test_short_hangul_guard_ignores_article_and_punctuation(name):
    catalog = InMemoryCatalog(
        [ProductInfo(BOWMORE_18, "Bowmore 18", age_years=18, brand_id=BOWMORE)],
        [(BOWMORE_18, "Bowmore 18"), (BOWMORE_18, "달모어 18")],
        [(BOWMORE, "Bowmore")],
    )
    assert menu(name, catalog).status == "unmatched"


def test_hangul_the_vocabulary_does_not_know_may_be_the_missing_words():
    brand, vinho = _id(731), _id(732)
    catalog = InMemoryCatalog(
        [ProductInfo(vinho, "Kavalan Vinho Barrique", None, "Vinho Barrique", brand_id=brand)],
        [(vinho, "Kavalan Vinho Barrique"), (vinho, "카발란 비노 바리끄 셰리")],
        [(brand, "Kavalan"), (brand, "카발란")],
    )
    # "비노 바리끄" is not in the vocabulary: vinho and barrique may be those words.
    assert menu("카발란 비노 바리끄", catalog).status == "exact_match"


def test_a_brand_split_over_tokens_is_still_the_brand():
    brand, orchard, other = _id(741), _id(742), _id(743)
    catalog = InMemoryCatalog(
        [
            ProductInfo(orchard, "Compass Box Orchard House", None, "Orchard House", brand_id=brand),
            ProductInfo(other, "Compass Box Hedonism", None, "Hedonism", brand_id=brand),
        ],
        [(orchard, "Compass Box Orchard House"), (orchard, "컴파스 박스 오차드 하우스"), (other, "Compass Box Hedonism")],
        [(brand, "Compass Box"), (brand, "컴파스박스")],
    )
    # "컴파스", "박스" spell the brand: no edition token, so no product is picked.
    result = menu("Compass Box (컴파스 박스)", catalog)
    assert result.status == "ambiguous"
    assert len(result.candidates) == 2


def test_alias_remainder_without_letters_covers_nothing():
    brand, octo = _id(751), _id(752)
    catalog = InMemoryCatalog(
        [ProductInfo(octo, "Octomore 16.1 Super Heavily Peated", None, "16.1 Super Heavily Peated", brand_id=brand)],
        [(octo, "Octomore 16.1 Super Heavily Peated"), (octo, "Octomore 16.1")],
        [(brand, "Octomore")],
    )
    # The alias "octomore16.1" leaves "." after the brand and digits; it must not cover the line.
    result = menu("Octomore 16.1 Super", catalog)
    assert result.status == "ambiguous"
    assert result.candidates[0].evidence["editionOnlyInProduct"] == ["heavily", "peated"]


def test_vocabulary_retry_needs_an_edition_word_that_fits():
    signatory, macduff = _id(761), _id(762)
    catalog = InMemoryCatalog(
        [ProductInfo(macduff, "Signatory Vintage Macduff 13", 13, "Macduff 13", brand_id=signatory)],
        [(macduff, "Signatory Vintage Macduff 13")],
        [(signatory, "Signatory"), (signatory, "시그나토리")],
    )
    # "쿨일라" is Caol Ila: the Macduff of the same age is not offered.
    assert menu("시그나토리 쿨일라13", catalog).status == "unmatched"


JD, FARCLAS, MICHTERS = (_id(800 + n) for n in range(3))
NO7, FARCLAS_105, CUT_2020_B, OCTO_14_B, US1 = (_id(n) for n in range(811, 816))


@pytest.fixture
def strengths():
    products = [
        ProductInfo(NO7, "Jack Daniel's Old No.7", None, "Old No.7", brand_id=JD),
        ProductInfo(FARCLAS_105, "Glenfarclas 105", None, "105", brand_id=FARCLAS),
        ProductInfo(CUT_2020_B, "The Macallan Classic Cut 2020", None, "Classic Cut 2020", brand_id=MACALLAN_CUT),
        ProductInfo(OCTO_14_B, "Octomore 14.1", None, "14.1", brand_id=OCTOMORE),
        ProductInfo(US1, "Michter's US*1 Small Batch Bourbon", None, "US*1 Small Batch Bourbon", brand_id=MICHTERS),
    ]
    aliases = [(product.product_id, product.display_name) for product in products]
    aliases += [(NO7, "잭다니엘 넘버7"), (US1, "믹터스 US1 버번")]
    brand_aliases = [(JD, "잭다니엘"), (FARCLAS, "Glenfarclas"), (FARCLAS, "글렌파클라스"), (MACALLAN_CUT, "맥캘란")]
    brand_aliases += [(OCTOMORE, "옥토모어"), (MICHTERS, "믹터스")]
    return InMemoryCatalog(products, aliases, brand_aliases)


@pytest.mark.parametrize(
    ("name", "product"),
    [
        ("잭다니엘 넘버7 40%", NO7),
        ("글렌파클라스 105 60%", FARCLAS_105),
        ("Glenfarclas 105 700 ml", FARCLAS_105),
        ("Glenfarclas 105 700ml 16,000원", FARCLAS_105),
        ("맥캘란 클래식컷 2020 52.5%", CUT_2020_B),
        ("옥토모어 14.1 59.1%", OCTO_14_B),
        ("옥토모어 14.1 1.6", OCTO_14_B),  # price written as 1.6 (16,000): 14.1 still matches
        ("믹터스 US1 버번 45.7%", US1),
    ],
)
def test_strength_volume_and_price_are_not_product_numbers(strengths, name, product):
    assert product in {c.product_id for c in menu(name, strengths).candidates}


def test_line_numbers_leave_out_measures():
    from app.matching.staged import _line_numbers

    assert _line_numbers("Glenfarclas 105 60% 700 ml 2잔 16,000원") == ["105"]
    assert _line_numbers("옥토모어 14.1 59.1도") == ["14.1"]
