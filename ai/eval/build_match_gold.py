# AI-generated with Claude Code/Claude Opus 5.5 (Jinwoo Park, 2026-10-13). Reviewed by Jinwoo Park.
"""Build eval/match_gold_v1.json: the product each labeled menu line refers to.

    python ai/eval/build_match_gold.py

Layer 2 of the labels (layer 1 = extraction labels). Every item of
labels_v1_1.json (val) and labels_heldout_v1.json (Beck only for now) gets
`gold`:
  - an existing catalog product key            e.g. "talisker-10"
  - "new:<key>" for a product missing from the catalog; NEW_PRODUCTS gives its
    standard English name, age and edition (no menu spelling is used as alias)
  - "both:<key>|<key>" when one line names two products ("A / B" with one price);
    the line means both products, so a matcher has to return both
  - "unknown" when the line is too short to tell which product it is
  - "non_whisky" for cognac etc. (expected: unmatched)
REVIEW lists links a human should confirm. Matching split (eval_plan.md): dev =
위스키복춘, 서로상, Beck; test = 미라보, 포레스트. The test photos, their new products
and review notes are copied from eval/match_gold_test_draft.json (built by
match_gold_test_draft.py, reviewed by Jinwoo); its POST_TEST_ALIASES are not used.
"""

from __future__ import annotations

import json
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
VAL = REPO_ROOT / "ai" / "catalog" / "labels_v1_1.json"
TEST = REPO_ROOT / "eval" / "labels_heldout_v1.json"
CATALOG = REPO_ROOT / "ai" / "catalog" / "catalog_v1_draft.json"
TEST_DRAFT = REPO_ROOT / "eval" / "match_gold_test_draft.json"
OUT = REPO_ROOT / "eval" / "match_gold_v1.json"

# Products not in catalog_v1_draft. brand: an existing brand key or a new brand's English name.
NEW_PRODUCTS = {
    "buffalo-trace": ("Buffalo Trace", "Buffalo Trace", None, None),
    "four-roses-small-batch": ("Four Roses Small Batch", "Four Roses", None, "Small Batch"),
    "james-e-pepper-1776-rye": ("James E. Pepper 1776 Straight Rye", "James E. Pepper", None, "1776 Straight Rye"),
    "james-e-pepper-1776-bourbon": ("James E. Pepper 1776 Straight Bourbon", "James E. Pepper", None, "1776 Straight Bourbon"),
    "cleveland-black-reserve": ("Cleveland Black Reserve Bourbon", "Cleveland", None, "Black Reserve"),
    "eh-taylor-small-batch": ("Colonel E.H. Taylor Small Batch", "E.H. Taylor", None, "Small Batch"),
    "templeton-rye-barrel-strength": ("Templeton Rye Barrel Strength", "Templeton", None, "Rye Barrel Strength"),
    "makers-mark-cask-strength": ("Maker's Mark Cask Strength", "makers-mark", None, "Cask Strength"),
    "old-pepper-rye-single-barrel": ("Old Pepper Rye Single Barrel", "Old Pepper", None, "Rye Single Barrel"),
    "arran-quarter-cask": ("Arran Quarter Cask", "arran", None, "Quarter Cask"),
    "lagavulin-12-2018": ("Lagavulin 12 Special Release 2018", "lagavulin", 12, "Special Release 2018"),
    "laphroaig-10-cask-strength": ("Laphroaig 10 Cask Strength", "laphroaig", 10, "Cask Strength"),
    "octomore-13-1": ("Octomore 13.1", "octomore", None, "13.1"),
    "macallan-classic-cut-2020": ("The Macallan Classic Cut 2020", "macallan", None, "Classic Cut 2020"),
    "arran-machrie-moor": ("Arran Machrie Moor", "arran", None, "Machrie Moor"),
    "hakushu-distillers-reserve": ("Hakushu Distiller's Reserve", "Hakushu", None, "Distiller's Reserve"),
    "hibiki-japanese-harmony": ("Hibiki Japanese Harmony", "Hibiki", None, "Japanese Harmony"),
    "bowmore-18": ("Bowmore 18", "bowmore", 18, None),
    "yamazaki-12": ("Yamazaki 12", "yamazaki", 12, None),
    "ballantines-30": ("Ballantine's 30", "Ballantine's", 30, None),
    "glenfarclas-25": ("Glenfarclas 25", "glenfarclas", 25, None),
    "caol-ila-25": ("Caol Ila 25", "Caol Ila", 25, None),
    "laphroaig-25": ("Laphroaig 25", "laphroaig", 25, None),
    "hibiki-21": ("Hibiki 21", "Hibiki", 21, None),
    "hibiki-blenders-choice": ("Hibiki Blender's Choice", "Hibiki", None, "Blender's Choice"),
    "balvenie-18-px": ("The Balvenie 18 Pedro Ximenez Cask", "balvenie", 18, "Pedro Ximenez Cask"),
    "kavalan-distillery-reserve-madeira": ("Kavalan Distillery Reserve Madeira Cask", "kavalan", None,
                                           "Distillery Reserve Madeira Cask"),
    "bushmills-10": ("Bushmills 10", "Bushmills", 10, None),
    "caol-ila-12": ("Caol Ila 12", "Caol Ila", 12, None),
    "kilchoman-sanaig": ("Kilchoman Sanaig", "Kilchoman", None, "Sanaig"),
}

# Beck: raw_name -> gold (same for every unit / pour of that line)
BECK = {
    "Buffalo Trace / Makrt's Mark": "both:new:buffalo-trace|makers-mark",
    "Wildturkey 101": "wild-turkey-101-8",
    "Four Roses Small Batch": "new:four-roses-small-batch",
    "James E Pepper 1776 Rye Whiskey": "new:james-e-pepper-1776-rye",
    "James E Pepper 1776 Bourbon Whiskey": "new:james-e-pepper-1776-bourbon",
    "Cleveland Black Reserve Bourbon": "new:cleveland-black-reserve",
    "Rowan`s Creek": "rowans-creek",
    "Taylor Small Batch": "new:eh-taylor-small-batch",
    "Templeton Rye Barrel Strength": "new:templeton-rye-barrel-strength",
    "Maker`s Mark Cask Strength": "new:makers-mark-cask-strength",
    "Old Pepper Rye Single Barrel": "new:old-pepper-rye-single-barrel",
    "Noah`s Mill": "noahs-mill",
    "Booker`s": "bookers",
    "Arran Quarter Cask": "new:arran-quarter-cask",
    "Arran Sherry cask": "arran-sherry-cask",
    "Ardbeg Uigeadail": "ardbeg-uigeadail",
    "Glenfarclas 105": "glenfarclas-105",
    "Abelour A`bunadh": "aberlour-abunadh",
    "Lagavulin 12yo 2018": "new:lagavulin-12-2018",
    "Laphroaig 10yo Cask Strength": "new:laphroaig-10-cask-strength",
    "Kavalan Solist": "unknown",
    "Octomore 13.1": "new:octomore-13-1",
    "Macallan Classic Cut 2020": "new:macallan-classic-cut-2020",
    "Glenfiddich 15yo": "glenfiddich-15",
    "Oban 14yo": "oban-14",
    "Glengrant 15yo": "glen-grant-15",
    "Dalwhinny 15yo": "dalwhinnie-15",
    "Glenlivet 15yo": "glenlivet-15",
    "Bowmore 15yo": "bowmore-15",
    "Machrie Moor": "new:arran-machrie-moor",
    "Hakushu DR": "new:hakushu-distillers-reserve",
    "Hibiki DR": "new:hibiki-japanese-harmony",
    "Lagavulin 16yo": "lagavulin-16",
    "Glenfiddich 18yo": "glenfiddich-18",
    "Bowmore 18yo": "new:bowmore-18",
    "Macallan 15yo": "macallan-15-double-cask",
    "Glenmorangie Signet": "glenmorangie-signet",
    "Yamazaki 12yo": "new:yamazaki-12",
    "Ballentine 30yo": "new:ballantines-30",
    "Glenfiddich 21yo": "glenfiddich-21",
    "Macallan 18yo": "unknown",
    "Glenfarclas 25yo": "new:glenfarclas-25",
    "Caol ila 25yo": "new:caol-ila-25",
    "라프로익 25년": "new:laphroaig-25",
    "히비키 21년": "new:hibiki-21",
    "히비키 블랜더스 쵸이스": "new:hibiki-blenders-choice",
    "발베니 18년 PX": "new:balvenie-18-px",
    "카발란 DR 마데라캐스크": "new:kavalan-distillery-reserve-madeira",
    "Talisker 10yo": "talisker-10",
    "Bushmil 10yo": "new:bushmills-10",
    "Glengrant 10yo": "glen-grant-10",
    "Auchentoshan 12yo": "auchentoshan-12",
    "Glenfiddich 12yo": "glenfiddich-12",
    "Bowmore 12yo": "bowmore-12",
    "Laphroaig 10yo": "laphroaig-10",
    "Glenlivet 12yo": "glenlivet-12",
    "Caol Ila 12yo": "new:caol-ila-12",
    "Ardbeg 10yo": "ardbeg-10",
    "Balvenie 12yo": "balvenie-12-doublewood",
    "Glendronach 12yo": "glendronach-12",
    "Kilchoman Sanaig": "new:kilchoman-sanaig",
    "Laphroaig Quater Cask": "laphroaig-quarter-cask",
    "Macallan 12yo Double Cask": "macallan-12-double-cask",
    "Macallan 12yo Sheryy Cask": "macallan-12-sherry-oak",
}

# Links a human should confirm before the gold file is final.
REVIEW = {
    "Buffalo Trace / Makrt's Mark": "한 줄에 두 상품, 가격 하나. 두 상품 모두를 뜻함: 둘 다 내야 정답, 하나만 확정하면 partial",
    "Wildturkey 101": "카탈로그 Wild Turkey 101 8 Year와 같은 상품으로 봄 (국내 101은 8년 표기)",
    "Taylor Small Batch": "Colonel E.H. Taylor Small Batch로 추정 (Old Taylor일 수도)",
    "Arran Sherry cask": "캐스크 스트렝스 섹션. 카탈로그 Arran Bodega Sherry Cask(CS 제품)와 같은 상품으로 봄",
    "Kavalan Solist": "솔리스트 중 어느 캐스크인지 없음 → unknown (업주 선택 대상)",
    "Hibiki DR": "히비키에는 Distiller's Reserve가 없음. Japanese Harmony로 추정",
    "Macallan 15yo": "카탈로그 유일한 15년(Double Cask)에 연결. 국내 유통 15년은 대부분 Double Cask",
    "Macallan 18yo": "Sherry Oak / Double Cask 구분 없음 → unknown",
    "Balvenie 12yo": "카탈로그 12 DoubleWood에 연결. 메뉴에 에디션 없음",
    "Macallan 12yo Sheryy Cask": "카탈로그 12 Sherry Oak와 같은 상품으로 봄",
    "카발란 DR 마데라캐스크": "Distillery Reserve Madeira로 추정",
}


def main() -> None:
    catalog = json.loads(CATALOG.read_text(encoding="utf-8"))
    keys = {p["key"] for p in catalog["products"]}
    brand_keys = {b["key"] for b in catalog["brands"]} if catalog["brands"] and "key" in catalog["brands"][0] else set()

    photos = []
    for p in json.loads(VAL.read_text(encoding="utf-8"))["photos"]:
        items = [{"raw_name": i["raw_name"], "unit": i["unit"], "pour_ml": i["pour_ml"],
                  "gold": i["product_key"] or "non_whisky"} for i in p["items"]]
        photos.append({"photo_id": p["photo_id"], "bar": p["bar"], "split": "dev", "items": items})

    missing = set(BECK)
    for p in json.loads(TEST.read_text(encoding="utf-8"))["photos"]:
        if p["bar"] != "Beck":
            continue
        items = []
        for i in p["items"]:
            gold = BECK[i["raw_name"]]
            missing.discard(i["raw_name"])
            items.append({"raw_name": i["raw_name"], "unit": i["unit"], "pour_ml": i["pour_ml"], "gold": gold})
        photos.append({"photo_id": p["photo_id"], "bar": p["bar"], "split": "dev", "items": items})
    if missing:
        raise SystemExit(f"BECK names not in labels: {sorted(missing)}")

    # test split: copied as is from the reviewed draft
    draft = json.loads(TEST_DRAFT.read_text(encoding="utf-8"))
    new_products = {k: {"display_name": d, "brand": b, "age_years": a, "edition_name": e}
                    for k, (d, b, a, e) in NEW_PRODUCTS.items()}
    assert not set(draft["new_products"]) & set(new_products), "new product key defined twice"
    assert not set(draft["review"]) & set(REVIEW), "review note defined twice"
    new_products.update(draft["new_products"])
    for p in draft["photos"]:
        assert p["split"] == "test" and p["bar"] in ("미라보", "포레스트"), p["photo_id"]
        photos.append(p)

    # every referenced key must exist
    for p in photos:
        for i in p["items"]:
            for ref in i["gold"].removeprefix("both:").split("|"):
                if ref.startswith("new:"):
                    assert ref[4:] in new_products, ref
                elif ref not in ("unknown", "non_whisky"):
                    assert ref in keys, ref
    for key in new_products:
        assert key not in keys, f"{key} already in catalog"

    out = {
        "version": "match_gold_v1",
        "created": "2026-10-13",
        "split": {"dev": ["위스키복춘", "서로상", "Beck"], "test": ["미라보", "포레스트"]},
        "labeling": "val: labels_v1_1 product_key (I1). Beck: Claude draft, review pending. "
                    "test: match_gold_test_draft (Claude draft, Jinwoo's review applied)",
        "new_products": new_products,
        "review": {**REVIEW, **draft["review"]},
        "photos": photos,
    }
    OUT.write_text(json.dumps(out, ensure_ascii=False, indent=1) + "\n", encoding="utf-8", newline="\n")
    for split in ("dev", "test"):
        chosen = [p for p in photos if p["split"] == split]
        n = sum(len(p["items"]) for p in chosen)
        print(f"{split}: {len(chosen)} photos, {n} items")
    print(f"wrote {OUT.relative_to(REPO_ROOT)}: {len(photos)} photos, {len(new_products)} new products")


if __name__ == "__main__":
    main()
