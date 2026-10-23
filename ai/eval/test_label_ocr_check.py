"""Unit tests for label_ocr_check.py and build_labels_v1_1.rebuild (no photos, no API)."""

from __future__ import annotations

import json

import build_labels_v1_1 as build
import label_ocr_check as check


def field(text, x0, line_break=False):
    return {"inferText": text, "lineBreak": line_break,
            "boundingPoly": {"vertices": [{"x": x0, "y": 0}, {"x": x0 + 10, "y": 0},
                                          {"x": x0 + 10, "y": 10}, {"x": x0, "y": 10}]}}


def test_best_substrings_finds_one_edit():
    d, spans = check.best_substrings("스트렝스", "캐스크스트랭스배치")
    assert d == 1 and (3, 7) in spans


def test_same_length_and_jamo_tie_break():
    ocr = check.OcrText([field("암룻", 0), field("퓨어", 20, True), field("퓨젼", 0, True)])
    [d] = check.check_photo("p", "s", [{"raw_name": "암룻 퓨전"}], ocr)
    assert d.ocr_text == "퓨젼" and d.distance == 1


def test_original_text_keeps_punctuation():
    ocr = check.OcrText([field("Rowan's", 0), field("Creek", 20, True)])
    [d] = check.check_photo("p", "s", [{"raw_name": "Rowan`s Creek"}], ocr)
    assert (d.label_piece, d.ocr_text, d.pattern) == ("Rowan`s", "Rowan's", "rowan`s→rowans")


def test_glass_bottle_rows_share_one_diff_and_missing_token():
    ocr = check.OcrText([field("글렌모렌지", 0), field("퀀타루반", 20, True)])
    items = [{"raw_name": "글렌모렌지 퀸타루반"}, {"raw_name": "글렌모렌지 퀸타루반"},
             {"raw_name": "아드벡 우거다일"}]
    diffs = check.check_photo("p", "s", items, ocr)
    found = [d for d in diffs if d.category == "?"]
    assert len(found) == 1 and found[0].item_ids == ["p#0", "p#1"]
    assert {d.label_token for d in diffs if d.category == "missing"} == {"아드벡", "우거다일"}


def test_decisions_build_new_name():
    ocr = check.OcrText([field("캐스크", 0), field("스트랭스", 20, True)])
    diffs = check.check_photo("p", "s", [{"raw_name": "캐스크 스트렝스"}], ocr)
    check.apply_decisions(diffs, {"patterns": {"스트렝스→스트랭스": {"category": "B"}}})
    assert diffs[0].new_name == "캐스크 스트랭스"


def test_rebuild_changes_only_the_given_raw_names():
    labels = {"photos": [{"photo_id": "a", "items": [{"raw_name": "x", "unit": "glass"},
                                                      {"raw_name": "x", "unit": "bottle"}]}]}
    text = '{\n "photos": [{"photo_id": "a", "items": [\n  {"raw_name": "x", "unit": "glass"},\n' \
           '  {"raw_name": "x", "unit": "bottle"}]}]\n}\n'
    assert json.loads(text) == labels
    out = build.rebuild(text, labels, {"a#1": "y"})
    assert out == text.replace('{"raw_name": "x", "unit": "bottle"}', '{"raw_name": "y", "unit": "bottle"}')
