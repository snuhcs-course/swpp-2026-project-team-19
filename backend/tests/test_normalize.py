import pytest

from app.core.normalize import normalize


def test_section_7_example():
    assert normalize(" 딘스톤 12年 ") == "딘스톤12"


@pytest.mark.parametrize(
    "text",
    [
        "Glenfiddich 12",
        "Glenfiddich 12Y",
        "Glenfiddich 12y",
        "Glenfiddich 12 Y",
        "Glenfiddich 12 YO",
        "Glenfiddich 12yo",
        "Glenfiddich 12 Years Old",
        "Glenfiddich 12 years",
        "Glenfiddich 12 Year Old",
        "Glenfiddich 12年",
    ],
)
def test_english_age_expressions(text):
    assert normalize(text) == "glenfiddich12"


@pytest.mark.parametrize("text", ["글렌피딕 12년", "글렌피딕12년", "글렌피딕 12Y", "글렌피딕  12 "])
def test_korean_age_expressions(text):
    assert normalize(text) == "글렌피딕12"


def test_age_suffix_followed_by_letters_is_kept():
    # Not an age expression, so the "y" stays.
    assert normalize("Balvenie 12yDW") == "balvenie12ydw"
    assert normalize("12 Yamazaki") == "12yamazaki"


def test_age_suffix_needs_a_number():
    assert normalize("Old Pulteney") == "oldpulteney"
    assert normalize("Aged 12 Years") == "aged12"


def test_lowercase_and_whitespace():
    assert normalize("  DALMORE   Aged\t15 ") == normalize("dalmore aged 15")
    assert normalize("GlenAllachie") == normalize("glenallachie") == "glenallachie"


def test_nfkc_full_width_characters():
    assert normalize("Ｇｌｅｎ　Ｇｒａｎｔ　１５") == "glengrant15"


def test_special_dashes_unified():
    assert normalize("Port–Charlotte") == "port-charlotte"
    assert normalize("Port—Charlotte") == "port-charlotte"
    assert normalize("Port−Charlotte") == "port-charlotte"


def test_unneeded_special_characters_removed():
    assert normalize("Jack Daniel's") == "jackdaniels"
    assert normalize("Maker’s Mark") == "makersmark"
    assert normalize("Glenmorangie Nectar D'Or!") == "glenmorangienectardor"
    assert normalize("[Signatory] Macduff_13") == "signatorymacduff13"


def test_decimal_point_kept():
    assert normalize("옥토모어 16.1") == "옥토모어16.1"
    assert normalize("Octomore 16.1") == "octomore16.1"


def test_non_decimal_dots_removed():
    assert normalize("Jack Daniel's Old No.7") == "jackdanielsoldno7"
    assert normalize("12 Y.") == "12"


def test_units_and_price_commas():
    assert normalize("30㎖") == normalize("30 ML") == normalize("30ml") == "30ml"
    assert normalize("15,000") == "15000"


def test_empty_and_symbols_only():
    assert normalize("") == ""
    assert normalize("  !! ") == ""


def test_idempotent():
    for text in [" 딘스톤 12年 ", "Octomore 16.1", "Balvenie 12yDW", "Jack Daniel's Old No.7"]:
        once = normalize(text)
        assert normalize(once) == once
