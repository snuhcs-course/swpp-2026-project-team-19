import hashlib

import pytest

from score import (LABELS_PATH, LABELS_SHA256, aggregate, candidates, lenient_distance,
                   normalize, score_photo, strict_match)


def item(name, price=10000, unit="glass", note=None):
    return {"raw_name": name, "price_krw": price, "pour_ml": None, "unit": unit, "note": note}


# ---------- 이름 정규화·대응 ----------

def test_normalize_lowercases_and_strips_space_punct():
    assert normalize("Glen Grant 18Y") == "glengrant18y"
    assert normalize("GlenAllachie 10Y Cask Strength Batch #9") == "glenallachie10ycaskstrengthbatch9"
    assert normalize("글렌 파클라스-105") == "글렌파클라스105"


def test_slash_split_into_candidates_plus_whole_name():
    assert candidates("글렌그란트 18년 / Glen Grant 18Y") == [
        "글렌그란트18년glengrant18y", "글렌그란트18년", "glengrant18y"]
    assert candidates("헤네시vsop/Hennessy vsop") == [
        "헤네시vsophennessyvsop", "헤네시vsop", "hennessyvsop"]
    assert candidates("Glen Grant 18Y") == ["glengrant18y"]


def test_unspaced_slash_output_still_pairs():
    assert strict_match("헤네시vsop / Hennessy vsop", "헤네시vsop/Hennessy vsop")
    assert strict_match("헤네시vsop / Hennessy vsop", "Hennessy VSOP")


def test_slash_inside_name_pairs_as_whole():
    assert strict_match("Glenfiddich W/Sherry", "Glenfiddich WSherry")
    # a fragment pairs only if it equals a whole label candidate
    assert not strict_match("Glenfiddich W/Sherry", "Sherry Cask")


def test_strict_bilingual_either_side():
    assert strict_match("글렌그란트 18년 / Glen Grant 18Y", "Glen Grant 18Y")
    assert strict_match("글렌그란트 18년", "글렌그란트18년 / GlenGrant 18")
    assert not strict_match("글렌그란트 18년", "글렌그란트 15년")


def test_lenient_one_char_misread_pairs():
    assert lenient_distance("글렌피딕 12y", "글랜피딕 12y") == 1


def test_lenient_age_differs_is_not_pair():
    # eval_plan: 한 글자 차이지만 다른 제품
    assert lenient_distance("글렌피딕12y", "글렌피딕15y") is None
    assert lenient_distance("Glenfiddich 12Y", "Glenfiddich 15Y") is None


def test_lenient_digit_order_and_count_must_match():
    assert lenient_distance("배치 9 10y", "배치 10 9y") is None
    assert lenient_distance("글렌알라키 10년", "글렌알라키 10년 배치 9") is None


def test_lenient_two_edits_is_not_pair():
    assert lenient_distance("글렌피딕 12y", "글랜피닉 12y") is None


def test_lenient_absolute_threshold_not_ratio():
    assert lenient_distance("ab 12", "ac 12") == 1  # short names also allow exactly 1


# ---------- 사진 단위 채점 ----------

def test_perfect_photo():
    gt = [item("A 12"), item("A 12", 200000, "bottle")]
    s = score_photo(gt, [dict(x) for x in gt])
    assert (s["matched"], s["correct"], s["fp"], s["fn"]) == (2, 2, 0, 0)


def test_unit_mismatch_is_fp_plus_fn_and_counted_as_confusion():
    gt = [item("Glen Grant 18Y", 28000, "glass")]
    out = [item("Glen Grant 18Y", 28000, "bottle")]
    s = score_photo(gt, out)
    assert (s["matched"], s["fp"], s["fn"], s["unit_confusion"]) == (0, 1, 1, 1)
    assert aggregate([s])["item_accuracy"] == 0.0


def test_wrong_price_matched_but_not_correct():
    gt = [item("A 12", 28000)]
    s = score_photo(gt, [item("A 12", 2800)])
    assert (s["matched"], s["correct"], s["price_correct"]) == (1, 0, 0)
    assert s["errors"][0]["type"] == "가격 단위 환산 오류"


def test_swapped_glass_bottle_prices_are_price_errors_tagged_as_swap():
    gt = [item("A 12", 15000, "glass"), item("A 12", 300000, "bottle")]
    out = [item("A 12", 300000, "glass"), item("A 12", 15000, "bottle")]
    s = score_photo(gt, out)
    assert (s["matched"], s["correct"], s["unit_confusion"]) == (2, 0, 0)
    assert [e["type"] for e in s["errors"]] == ["잔·병 가격 뒤바뀜"] * 2


def test_null_or_noted_price_checks_name_and_unit_only():
    gt = [item("A 12", None), item("B 15", 30000, note="단위 확신 불가")]
    out = [item("A 12", 5000), item("B 15", None)]
    s = score_photo(gt, out)
    assert (s["correct"], s["priced"]) == (2, 0)
    assert aggregate([s])["price_accuracy"] is None


def test_one_to_one_duplicate_output_is_fp():
    gt = [item("A 12")]
    s = score_photo(gt, [item("A 12"), item("A 12")])
    assert (s["matched"], s["fp"], s["fn"]) == (1, 1, 0)


def test_strict_before_lenient():
    # "글랜 12" could lenient-pair with "글렌 12", but the strict pair takes it first
    gt = [item("글렌 12"), item("글랜 12", 20000)]
    out = [item("글렌 12"), item("글렌 12", 20000)]
    s = score_photo(gt, out)
    assert (s["matched_strict"], s["matched"], s["correct"]) == (1, 2, 2)


def test_prefers_price_matching_pair_on_tie():
    gt = [item("A 12", 10000), item("A 12", 20000)]
    out = [item("A 12", 20000), item("A 12", 10000)]
    assert score_photo(gt, out)["correct"] == 2


def test_empty_label_photo_outputs_are_all_fp():
    s = score_photo([], [item("Mojito"), item("Negroni")])
    assert (s["fp"], s["fn"]) == (2, 0)
    assert {e["type"] for e in s["errors"]} == {"비위스키 포함"}


def test_item_accuracy_denominator_includes_fp():
    gt = [item("A 12"), item("B 15")]
    out = [item("A 12"), item("B 15"), item("C 18")]
    agg = aggregate([score_photo(gt, out)])
    assert agg["item_accuracy"] == pytest.approx(2 / 3)
    assert agg["f1_lenient"] == pytest.approx(2 * (2 / 3) * 1 / (2 / 3 + 1))


def test_aggregate_pools_photos_not_mean_of_photos():
    big = score_photo([item(f"X {i}") for i in range(10)], [item(f"X {i}") for i in range(10)])
    empty = score_photo([], [item("Mojito")])
    assert aggregate([big, empty])["item_accuracy"] == pytest.approx(10 / 11)


def test_labels_file_locked():
    assert hashlib.sha256(LABELS_PATH.read_bytes()).hexdigest() == LABELS_SHA256
