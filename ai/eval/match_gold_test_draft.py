# AI-generated with Claude Code/Claude Opus 5.5 (Jinwoo Park, 2026-10-13). Reviewed by Jinwoo Park.
"""Layer-2 gold draft for the matching TEST split (미라보, 포레스트).

    python ai/eval/match_gold_test_draft.py   # writes eval/match_gold_test_draft.json

Same conventions as build_match_gold.py (key / new:<key> / unknown). Products new
to the catalog get a standard English name written from general knowledge of the
product, never copied from the menu spelling. Keys shared with Beck (e.g.
kilchoman-sanaig) refer to build_match_gold.NEW_PRODUCTS. Independent bottlings
are separate products from the distillery's own release (catalog rule 2026-10-05).
To be merged into build_match_gold.py as split "test" after human review of REVIEW.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(Path(__file__).parent))
from build_match_gold import NEW_PRODUCTS as BECK_NEW  # noqa: E402

LABELS = REPO_ROOT / "eval" / "labels_heldout_v1.json"
CATALOG = REPO_ROOT / "ai" / "catalog" / "catalog_v1_draft.json"
OUT = REPO_ROOT / "eval" / "match_gold_test_draft.json"

NEW: dict[str, tuple] = {}  # key -> (display_name, brand, age_years, edition_name)


def n(key: str, display: str, brand: str, age: int | None = None, edition: str | None = None) -> str:
    if key in NEW and NEW[key] != (display, brand, age, edition):
        raise ValueError(f"conflicting definition for {key}")
    NEW[key] = (display, brand, age, edition)
    return f"new:{key}"


def b(key: str) -> str:  # product already defined for Beck
    assert key in BECK_NEW, key
    return f"new:{key}"


H = "011_미라보"
G: dict[str, str] = {}  # raw_name -> gold

# ---------- 미라보_01: independent bottlers, blends ----------
LMDW, TWA, SAM = "La Maison du Whisky", "The Whisky Agency", "Samaroli"
WM, HL, SIG = "Wilson & Morgan", "Highland Laird", "signatory"
G.update({
    "라 메종드 위스키(LMDW) 벤네비스 7년 아티스트 콜렉티브": n("lmdw-ben-nevis-7-artist-collective", "LMDW Artist Collective Ben Nevis 7", LMDW, 7, "Artist Collective Ben Nevis"),
    "라 메종드 위스키(LMDW) 쿨일라 9년 아티스트 콜렉티브": n("lmdw-caol-ila-9-artist-collective", "LMDW Artist Collective Caol Ila 9", LMDW, 9, "Artist Collective Caol Ila"),
    "더 위스키 에이전시(TWA) 카발란 솔리스트 올로로소 7년": n("twa-kavalan-oloroso-7", "The Whisky Agency Kavalan Oloroso 7", TWA, 7, "Kavalan Oloroso"),
    "더 위스키 에이전시(TWA) 카발란 솔리스트 포트 8년": n("twa-kavalan-port-8", "The Whisky Agency Kavalan Port 8", TWA, 8, "Kavalan Port"),
    "사마롤리(Smaroli) 로얄 브라클라 14년": n("samaroli-royal-brackla-14", "Samaroli Royal Brackla 14", SAM, 14, "Royal Brackla"),
    "사마롤리(Smaroli) 쿨일라 13년": n("samaroli-caol-ila-13", "Samaroli Caol Ila 13", SAM, 13, "Caol Ila"),
    "디아지오 SR(Diagio SR) SR 22 탈리스커 11년": n("talisker-11-special-release-2022", "Talisker 11 Special Release 2022", "talisker", 11, "Special Release 2022"),
    "디아지오 SR(Diagio SR) SR 23 오반 11년": n("oban-11-special-release-2023", "Oban 11 Special Release 2023", "oban", 11, "Special Release 2023"),
    "디아지오 SR(Diagio SR) SR 23 탈리스커": n("talisker-special-release-2023", "Talisker Special Release 2023", "talisker", None, "Special Release 2023"),
    "디아지오 SR(Diagio SR) SR 23 클라이넬리쉬": n("clynelish-special-release-2023", "Clynelish Special Release 2023", "clynelish", None, "Special Release 2023"),
    "윌슨 앤 모건(Wilson & Morgan) 쿨일라 2014": n("wm-caol-ila-2014", "Wilson & Morgan Caol Ila 2014", WM, None, "Caol Ila 2014"),
    "윌슨 앤 모건(Wilson & Morgan) 아드모어 12년": n("wm-ardmore-12", "Wilson & Morgan Ardmore 12", WM, 12, "Ardmore"),
    "윌슨 앤 모건(Wilson & Morgan) 달유인 15년": n("wm-dailuaine-15", "Wilson & Morgan Dailuaine 15", WM, 15, "Dailuaine"),
    "하이랜드 레어드(Highland Laird) 딘스톤 12년": n("hl-deanston-12", "Highland Laird Deanston 12", HL, 12, "Deanston"),
    "하이랜드 레어드(Highland Laird) 쿨일라 12년": n("hl-caol-ila-12", "Highland Laird Caol Ila 12", HL, 12, "Caol Ila"),
    "하이랜드 레어드(Highland Laird) 녹두 13년": n("hl-knockdhu-13", "Highland Laird Knockdhu 13", HL, 13, "Knockdhu"),
    "하이랜드 레어드(Highland Laird) 글렌토커스 16년": n("hl-glentauchers-16", "Highland Laird Glentauchers 16", HL, 16, "Glentauchers"),
    "하이랜드 레어드(Highland Laird) 발블레어 14년": n("hl-balblair-14", "Highland Laird Balblair 14", HL, 14, "Balblair"),
    "시그나토리 빈티지(Signatory Vintage) 벤네비스 9년 100 프루프": n("signatory-ben-nevis-9-100-proof", "Signatory Vintage 100 Proof Ben Nevis 9", SIG, 9, "100 Proof Ben Nevis"),
    "시그나토리 빈티지(Signatory Vintage) 쿨일라 10년 100 프루프": n("signatory-caol-ila-10-100-proof", "Signatory Vintage 100 Proof Caol Ila 10", SIG, 10, "100 Proof Caol Ila"),
    "시그나토리 빈티지(Signatory Vintage) 벤리악 10년 100 프루프": n("signatory-benriach-10-100-proof", "Signatory Vintage 100 Proof BenRiach 10", SIG, 10, "100 Proof BenRiach"),
    "시그나토리 빈티지(Signatory Vintage) 글렌오드 12년 100 프루프": n("signatory-glen-ord-12-100-proof", "Signatory Vintage 100 Proof Glen Ord 12", SIG, 12, "100 Proof Glen Ord"),
    "시그나토리 빈티지(Signatory Vintage) 링크우드 12년 100 프루프": n("signatory-linkwood-12-100-proof", "Signatory Vintage 100 Proof Linkwood 12", SIG, 12, "100 Proof Linkwood"),
    "시그나토리 빈티지(Signatory Vintage) 스페이사이드 14년": n("signatory-speyside-14", "Signatory Vintage Speyside 14", SIG, 14, "Speyside"),
    "시그나토리 빈티지(Signatory Vintage) 에드라두어 2014": n("signatory-edradour-2014", "Signatory Vintage Edradour 2014", SIG, None, "Edradour 2014"),
    "발렌타인(Ballantine) 17년": n("ballantines-17", "Ballantine's 17", "Ballantine's", 17),
    "발렌타인(Ballantine) 21년": n("ballantines-21", "Ballantine's 21", "Ballantine's", 21),
    "조니워커(Johnnie Walker) 블랙": "johnnie-walker-black",
    "조니워커(Johnnie Walker) 블랙 셰리": n("johnnie-walker-black-sherry", "Johnnie Walker Black Label Sherry Finish", "johnnie_walker", 12, "Black Label Sherry Finish"),
    "조니워커(Johnnie Walker) 그린": n("johnnie-walker-green", "Johnnie Walker Green Label", "johnnie_walker", 15, "Green Label"),
    "조니워커(Johnnie Walker) 18년": n("johnnie-walker-18", "Johnnie Walker 18", "johnnie_walker", 18),
    "조니워커(Johnnie Walker) 블루": "johnnie-walker-blue",
    "맥네어스 럼릭(Macnair's Lum Reek) 12년": n("macnairs-lum-reek-12", "Macnair's Lum Reek 12", "Macnair's", 12, "Lum Reek"),
    "맥네어스 럼릭(Macnair's Lum Reek) 10년 캐스크 스트렝스": n("macnairs-lum-reek-10-cs", "Macnair's Lum Reek 10 Cask Strength", "Macnair's", 10, "Lum Reek Cask Strength"),
    "커티샥(Cutty Shark) 프로히비션": n("cutty-sark-prohibition", "Cutty Sark Prohibition Edition", "Cutty Sark", None, "Prohibition Edition"),
})

# ---------- 미라보_02 ----------
G.update({
    "하이랜드 파크(Highland Park) 12년": "highland-park-12",
    "하이랜드 파크(Highland Park) 캐스크 스트렝스 배치 4": n("highland-park-cs-batch-4", "Highland Park Cask Strength Release No.4", "highland_park", None, "Cask Strength Release No.4"),
    "하이랜드 파크(Highland Park) 캐스크 스트렝스 헤더": "unknown",
    "하이랜드 파크(Highland Park) 15년": n("highland-park-15", "Highland Park 15", "highland_park", 15),
    "하이랜드 파크(Highland Park) 18년": n("highland-park-18", "Highland Park 18 Viking Pride", "highland_park", 18, "Viking Pride"),
    "하이랜드 파크(Highland Park) 16년": n("highland-park-16", "Highland Park 16", "highland_park", 16),
    "글렌킨치(Glenkinchie) 12년": "glenkinchie-12",
    "오큰토션(Auchentoshan) 아메리칸 오크": n("auchentoshan-american-oak", "Auchentoshan American Oak", "auchentoshan", None, "American Oak"),
    "오큰토션(Auchentoshan) 12년": "auchentoshan-12",
    "오큰토션(Auchentoshan) 쇼비뇽 블랑": n("auchentoshan-sauvignon-blanc", "Auchentoshan Sauvignon Blanc Cask", "auchentoshan", None, "Sauvignon Blanc Cask"),
    "오큰토션(Auchentoshan) 쓰리 우드": n("auchentoshan-three-wood", "Auchentoshan Three Wood", "auchentoshan", None, "Three Wood"),
    "오큰토션(Auchentoshan) 18년": n("auchentoshan-18", "Auchentoshan 18", "auchentoshan", 18),
    "스프링뱅크(Springbank) 롱로우 피티드": n("longrow-peated", "Longrow Peated", "Longrow", None, "Peated"),
    "스프링뱅크(Springbank) 10년": n("springbank-10", "Springbank 10", "Springbank", 10),
    "스프링뱅크(Springbank) 12년 캐스크 스트렝스": n("springbank-12-cs", "Springbank 12 Cask Strength", "Springbank", 12, "Cask Strength"),
    "스프링뱅크(Springbank) 15년": n("springbank-15", "Springbank 15", "Springbank", 15),
    "글렌가일(Glengyle) 킬커란 12년": n("kilkerran-12", "Kilkerran 12", "Kilkerran", 12),
    "글렌가일(Glengyle) 해빌리 피티드": n("kilkerran-heavily-peated", "Kilkerran Heavily Peated", "Kilkerran", None, "Heavily Peated"),
    "글렌가일(Glengyle) 킬커란 16년": n("kilkerran-16", "Kilkerran 16", "Kilkerran", 16),
    "글렌스코시아(Glenscotia) 더블 캐스크": n("glen-scotia-double-cask", "Glen Scotia Double Cask", "Glen Scotia", None, "Double Cask"),
    "글렌스코시아(Glenscotia) 15년": n("glen-scotia-15", "Glen Scotia 15", "Glen Scotia", 15),
    "글렌스코시아(Glenscotia) 18년": n("glen-scotia-18", "Glen Scotia 18", "Glen Scotia", 18),
    "글렌스코시아(Glenscotia) 12년 머메이드": n("glen-scotia-12-mermaid", "Glen Scotia 12 Mermaid", "Glen Scotia", 12, "Mermaid"),
    "고든앤맥페일(Gordon&Macphail) 밀튼더프 10년": n("gm-miltonduff-10", "Gordon & MacPhail Miltonduff 10", "Gordon & MacPhail", 10, "Miltonduff"),
    "고든앤맥페일(Gordon&Macphail) 부나하벤 10년": n("gm-bunnahabhain-10", "Gordon & MacPhail Bunnahabhain 10", "Gordon & MacPhail", 10, "Bunnahabhain"),
    "고든앤맥페일(Gordon&Macphail) 부나하벤 헤빌리 피티드 11년": n("gm-bunnahabhain-heavily-peated-11", "Gordon & MacPhail Bunnahabhain Heavily Peated 11", "Gordon & MacPhail", 11, "Bunnahabhain Heavily Peated"),
    "고든앤맥페일(Gordon&Macphail) 글렌로티스 11년": n("gm-glenrothes-11", "Gordon & MacPhail Glenrothes 11", "Gordon & MacPhail", 11, "Glenrothes"),
    "헌터랭(Hunterlaing) 스카라버스": n("scarabus", "Scarabus Islay Single Malt", "Hunter Laing", None, "Scarabus"),
    "헌터랭(Hunterlaing) 로얄 브라클라 14년": n("hunter-laing-royal-brackla-14", "Hunter Laing Royal Brackla 14", "Hunter Laing", 14, "Royal Brackla"),
    "헌터랭(Hunterlaing) 크라겐모어 26년": n("hunter-laing-cragganmore-26", "Hunter Laing Cragganmore 26", "Hunter Laing", 26, "Cragganmore"),
    "더글라스랭(Douglaslaing) 락 아일랜드": n("rock-island", "Douglas Laing Rock Island", "Douglas Laing", None, "Rock Island"),
    "더글라스랭(Douglaslaing) 에피큐리안": n("epicurean", "Douglas Laing The Epicurean", "Douglas Laing", None, "The Epicurean"),
    "더글라스랭(Douglaslaing) 티모러스 비스티": n("timorous-beastie", "Douglas Laing Timorous Beastie", "Douglas Laing", None, "Timorous Beastie"),
    "더글라스랭(Douglaslaing) 골드론": n("gauldrons", "Douglas Laing The Gauldrons", "Douglas Laing", None, "The Gauldrons"),
    "더글라스랭(Douglaslaing) 골드론 캐스크 스트렝스": n("gauldrons-cs", "Douglas Laing The Gauldrons Cask Strength", "Douglas Laing", None, "The Gauldrons Cask Strength"),
    "더글라스랭(Douglaslaing) 골드론 셰리 캐스크": n("gauldrons-sherry", "Douglas Laing The Gauldrons Sherry Cask", "Douglas Laing", None, "The Gauldrons Sherry Cask"),
    "더글라스랭(Douglaslaing) 스칼리웩 윈터 에디션 2025": n("scallywag-winter-2025", "Douglas Laing Scallywag Winter Edition 2025", "Douglas Laing", None, "Scallywag Winter Edition 2025"),
    "더글라스랭(Douglaslaing) 빅피트 윈터 에디션 2025": n("big-peat-winter-2025", "Douglas Laing Big Peat Winter Edition 2025", "Douglas Laing", None, "Big Peat Winter Edition 2025"),
    "블랙애더(Blackadder) 셰리 스네이크": n("blackadder-sherry-snake", "Blackadder Sherry Snake", "Blackadder", None, "Sherry Snake"),
    "콤파스 박스(Compass Box) 오차드 하우스": n("compass-box-orchard-house", "Compass Box Orchard House", "Compass Box", None, "Orchard House"),
    "포트에스케이그(Port Askaig) 8년": n("port-askaig-8", "Port Askaig 8", "Port Askaig", 8),
    "포트에스케이그(Port Askaig) 17년": n("port-askaig-17", "Port Askaig 17", "Port Askaig", 17),
    "엘리먼츠 오브 아일라(Elements of Islay) 버번": n("elements-of-islay-bourbon", "Elements of Islay Bourbon Cask", "Elements of Islay", None, "Bourbon Cask"),
    "엘리먼츠 오브 아일라(Elements of Islay) 셰리": n("elements-of-islay-sherry", "Elements of Islay Sherry Cask", "Elements of Islay", None, "Sherry Cask"),
})

# ---------- 미라보_03 ----------
KIL = "Kilchoman"
G.update({
    "라가불린(Lagavulin) 8년": "lagavulin-8",
    "라가불린(Lagavulin) 11년 스위트 피트": n("lagavulin-11-sweet-peat", "Lagavulin 11 Sweet Peat", "lagavulin", 11, "Sweet Peat"),
    "라가불린(Lagavulin) 디스틸러리 에디션 2023": n("lagavulin-de-2023", "Lagavulin Distillers Edition 2023", "lagavulin", None, "Distillers Edition 2023"),
    "라가불린(Lagavulin) 16년": "lagavulin-16",
    "킬호만(Kilchoman) 마키어 베이": n("kilchoman-machir-bay", "Kilchoman Machir Bay", KIL, None, "Machir Bay"),
    "킬호만(Kilchoman) 사닉": b("kilchoman-sanaig"),
    "킬호만(Kilchoman) 마키어베이 캐스크 스트렝스": n("kilchoman-machir-bay-cs", "Kilchoman Machir Bay Cask Strength", KIL, None, "Machir Bay Cask Strength"),
    "킬호만(Kilchoman) 코리아 스몰배치": n("kilchoman-korea-small-batch", "Kilchoman Korea Small Batch", KIL, None, "Korea Small Batch"),
    "킬호만(Kilchoman) 배치 스트렝스": n("kilchoman-batch-strength", "Kilchoman Batch Strength", KIL, None, "Batch Strength"),
    "킬호만(Kilchoman) 사닉 캐스크 스트렝스": n("kilchoman-sanaig-cs", "Kilchoman Sanaig Cask Strength", KIL, None, "Sanaig Cask Strength"),
    "킬호만(Kilchoman) 피노 셰리 캐스크": n("kilchoman-fino-sherry", "Kilchoman Fino Sherry Cask Matured", KIL, None, "Fino Sherry Cask"),
    "킬호만(Kilchoman) 꼬냑 캐스크": n("kilchoman-cognac-cask", "Kilchoman Cognac Cask Matured", KIL, None, "Cognac Cask"),
    "킬호만(Kilchoman) PX 셰리 캐스크": n("kilchoman-px-sherry", "Kilchoman PX Sherry Cask Matured", KIL, None, "PX Sherry Cask"),
    "킬호만(Kilchoman) 로크곰": n("kilchoman-loch-gorm", "Kilchoman Loch Gorm", KIL, None, "Loch Gorm"),
    "킬호만(Kilchoman) 100% 아일라": n("kilchoman-100-islay", "Kilchoman 100% Islay", KIL, None, "100% Islay"),
    "킬호만(Kilchoman) 포트 싱글 캐스크 피니시": n("kilchoman-port-single-cask", "Kilchoman Port Single Cask Finish", KIL, None, "Port Single Cask Finish"),
    "킬호만(Kilchoman) 소테른 캐스크": n("kilchoman-sauternes-cask", "Kilchoman Sauternes Cask Matured", KIL, None, "Sauternes Cask"),
    "킬호만(Kilchoman) 포트 캐스크": n("kilchoman-port-cask", "Kilchoman Port Cask Matured", KIL, None, "Port Cask"),
    "킬호만(Kilchoman) 16년": n("kilchoman-16", "Kilchoman 16", KIL, 16),
    "브룩라디(Bruichladdich) 스코티시 발리": n("bruichladdich-classic-laddie", "Bruichladdich The Classic Laddie Scottish Barley", "Bruichladdich", None, "The Classic Laddie"),
    "브룩라디(Bruichladdich) 아일라 발리": n("bruichladdich-islay-barley", "Bruichladdich Islay Barley", "Bruichladdich", None, "Islay Barley"),
    "브룩라디(Bruichladdich) 18년": n("bruichladdich-18", "Bruichladdich 18", "Bruichladdich", 18),
    "브룩라디(Bruichladdich) 블랙아트 에디션 11": n("bruichladdich-black-art-11", "Bruichladdich Black Art Edition 11", "Bruichladdich", None, "Black Art Edition 11"),
    "포트샬롯(Port Charllotte) 10년": "port-charlotte-10",
    "포트샬롯(Port Charllotte) 아일라 발리 2014": n("port-charlotte-islay-barley-2014", "Port Charlotte Islay Barley 2014", "port_charlotte", None, "Islay Barley 2014"),
    "포트샬롯(Port Charllotte) PMC:01": n("port-charlotte-pmc-01", "Port Charlotte PMC:01", "port_charlotte", None, "PMC:01"),
    "옥토모어(Octomore) 14.1": n("octomore-14-1", "Octomore 14.1", "octomore", None, "14.1"),
    "옥토모어(Octomore) 14.2": n("octomore-14-2", "Octomore 14.2", "octomore", None, "14.2"),
    "옥토모어(Octomore) 15.1": n("octomore-15-1", "Octomore 15.1", "octomore", None, "15.1"),
    "옥토모어(Octomore) 15.2": n("octomore-15-2", "Octomore 15.2", "octomore", None, "15.2"),
    "옥토모어(Octomore) 15.3": n("octomore-15-3", "Octomore 15.3", "octomore", None, "15.3"),
    "쿨일라(Caol Ila) 12년": b("caol-ila-12"),
    "쿨일라(Caol Ila) 18년": n("caol-ila-18", "Caol Ila 18", "Caol Ila", 18),
    "부나하벤(Bunnahabhain) 12년": "bunnahabhain-12",
    "부나하벤(Bunnahabhain) 크루아 모나": n("bunnahabhain-cruach-mhona", "Bunnahabhain Cruach-Mhòna", "bunnahabhain", None, "Cruach-Mhona"),
    "부나하벤(Bunnahabhain) 안클라닥": n("bunnahabhain-an-cladach", "Bunnahabhain An Cladach", "bunnahabhain", None, "An Cladach"),
    "부나하벤(Bunnahabhain) 토흐카흐": n("bunnahabhain-toiteach-a-dha", "Bunnahabhain Toiteach A Dhà", "bunnahabhain", None, "Toiteach A Dha"),
    "부나하벤(Bunnahabhain) 에리너 그레이뉴": n("bunnahabhain-eirigh-na-greine", "Bunnahabhain Eirigh Na Greine", "bunnahabhain", None, "Eirigh Na Greine"),
    "부나하벤(Bunnahabhain) 12년 캐스크 스트렝스": n("bunnahabhain-12-cs", "Bunnahabhain 12 Cask Strength", "bunnahabhain", 12, "Cask Strength"),
    "부나하벤(Bunnahabhain) 14년 루비포트 캐스크 피니시": n("bunnahabhain-14-ruby-port", "Bunnahabhain 14 Ruby Port Cask Finish", "bunnahabhain", 14, "Ruby Port Cask Finish"),
    "부나하벤(Bunnahabhain) 18년": n("bunnahabhain-18", "Bunnahabhain 18", "bunnahabhain", 18),
    "아란(Arran) 10년": "arran-10",
    "아란(Arran) 쿼터 캐스크": b("arran-quarter-cask"),
    "아란(Arran) 포트 캐스크": n("arran-port-cask", "Arran Port Cask Finish", "arran", None, "Port Cask Finish"),
    "아란(Arran) 아마로네 캐스크": n("arran-amarone-cask", "Arran Amarone Cask Finish", "arran", None, "Amarone Cask Finish"),
    "아란(Arran) 소테른 캐스크": n("arran-sauternes-cask", "Arran Sauternes Cask Finish", "arran", None, "Sauternes Cask Finish"),
    "아란(Arran) 셰리 캐스크 캐스크 스트렝스": "arran-sherry-cask",
    "아란(Arran) 마크리무어 캐스크 스트렝스": n("arran-machrie-moor-cs", "Arran Machrie Moor Cask Strength", "arran", None, "Machrie Moor Cask Strength"),
    "아란(Arran) 마크리무어 10년": n("arran-machrie-moor-10", "Arran Machrie Moor 10", "arran", 10, "Machrie Moor"),
    "아란(Arran) 시그니쳐 시리즈": "unknown",
    "아란(Arran) 프라이빗 캐스크 No.2": n("arran-private-cask-2", "Arran Private Cask No.2", "arran", None, "Private Cask No.2"),
    "아란(Arran) 18년": n("arran-18", "Arran 18", "arran", 18),
    "아란(Arran) 21년": n("arran-21", "Arran 21", "arran", 21),
    "아란(Arran) 25년": n("arran-25", "Arran 25", "arran", 25),
    "탈리스커(Talisker) 스카이": n("talisker-skye", "Talisker Skye", "talisker", None, "Skye"),
    "탈리스커(Talisker) 10년": "talisker-10",
    "탈리스커(Talisker) 더 와일드 블루": n("talisker-wild-blue", "Talisker The Wild Blue", "talisker", None, "The Wild Blue"),
    "탈리스커(Talisker) 스톰": n("talisker-storm", "Talisker Storm", "talisker", None, "Storm"),
    "탈리스커(Talisker) 18년": n("talisker-18", "Talisker 18", "talisker", 18),
    "탈리스커(Talisker) 25년": n("talisker-25", "Talisker 25", "talisker", 25),
})

# ---------- 미라보_04 ----------
GM = "glenmorangie"
G.update({
    "글렌모렌지(Glenmorangie) 12년 오리지널": "glenmorangie-original",
    "글렌모렌지(Glenmorangie) 15년 라산타": "glenmorangie-lasanta",
    "글렌모렌지(Glenmorangie) 14년 퀸타루반": "glenmorangie-quinta-ruban",
    "글렌모렌지(Glenmorangie) 16년 더 넥타": "glenmorangie-nectar-dor",
    "글렌모렌지(Glenmorangie) 12년 칼바도스 피니시": n("glenmorangie-12-calvados", "Glenmorangie 12 Calvados Cask Finish", GM, 12, "Calvados Cask Finish"),
    "글렌모렌지(Glenmorangie) 테일 오브 스파이스": n("glenmorangie-tale-of-spice", "Glenmorangie A Tale of Spices", GM, None, "A Tale of Spices"),
    "글렌모렌지(Glenmorangie) 테일 오브 도쿄": n("glenmorangie-tale-of-tokyo", "Glenmorangie A Tale of Tokyo", GM, None, "A Tale of Tokyo"),
    "글렌모렌지(Glenmorangie) 18년 인피니트": "glenmorangie-18",
    "글렌모렌지(Glenmorangie) 시그넷": "glenmorangie-signet",
    "발블레어(Barblair) 12년": n("balblair-12", "Balblair 12", "Balblair", 12),
    "발블레어(Barblair) 18년": n("balblair-18", "Balblair 18", "Balblair", 18),
    "글렌드로낙(Glendronach) 트레디셔널리 피티드": n("glendronach-traditionally-peated", "GlenDronach Traditionally Peated", "glendronach", None, "Traditionally Peated"),
    "글렌드로낙(Glendronach) 12년": "glendronach-12",
    "글렌드로낙(Glendronach) 포트우드": n("glendronach-port-wood", "GlenDronach Port Wood", "glendronach", None, "Port Wood"),
    "글렌드로낙(Glendronach) 오드 투더 발리": n("glendronach-ode-to-the-valley", "GlenDronach Ode to the Valley", "glendronach", None, "Ode to the Valley"),
    "글렌드로낙(Glendronach) 오드 투더 엡버스": n("glendronach-ode-to-the-embers", "GlenDronach Ode to the Embers", "glendronach", None, "Ode to the Embers"),
    "글렌드로낙(Glendronach) 15년": "glendronach-15",
    "글렌드로낙(Glendronach) 18년": "glendronach-18-allardice",
    "글렌드로낙(Glendronach) 21년": "glendronach-21-parliament",
    "로크로몬드(Loch Lomond) 12년": n("loch-lomond-12", "Loch Lomond 12", "Loch Lomond", 12),
    "로크로몬드(Loch Lomond) 14년": n("loch-lomond-14", "Loch Lomond 14", "Loch Lomond", 14),
    "로크로몬드(Loch Lomond) 18년": n("loch-lomond-18", "Loch Lomond 18", "Loch Lomond", 18),
    "토마틴(Tomatin) 12년": n("tomatin-12", "Tomatin 12", "Tomatin", 12),
    "토마틴(Tomatin) 캐스크 스트렝스": n("tomatin-cs", "Tomatin Cask Strength", "Tomatin", None, "Cask Strength"),
    "토마틴(Tomatin) 14년": n("tomatin-14", "Tomatin 14", "Tomatin", 14),
    "토마틴(Tomatin) 18년": n("tomatin-18", "Tomatin 18", "Tomatin", 18),
    "글렌터렛(Glenturret) 트피플 우드": n("glenturret-triple-wood", "Glenturret Triple Wood", "Glenturret", None, "Triple Wood"),
    "글렌터렛(Glenturret) 10년 피티드": n("glenturret-10-peat-smoked", "Glenturret 10 Peat Smoked", "Glenturret", 10, "Peat Smoked"),
    "글렌터렛(Glenturret) 12년": n("glenturret-12", "Glenturret 12", "Glenturret", 12),
    "글렌기어리(Glengarioch) 15년": n("glen-garioch-15", "Glen Garioch 15", "Glen Garioch", 15),
    "글렌기어리(Glengarioch) 1997 배치12 캐스크 스트렝스": n("glen-garioch-1997-batch-12", "Glen Garioch 1997 Batch 12 Cask Strength", "Glen Garioch", None, "1997 Batch 12 Cask Strength"),
    "아드벡(Ardbeg) 5년 위비스티": n("ardbeg-wee-beastie", "Ardbeg Wee Beastie 5", "ardbeg", 5, "Wee Beastie"),
    "아드벡(Ardbeg) 10년": "ardbeg-10",
    "아드벡(Ardbeg) 안오": "ardbeg-an-oa",
    "아드벡(Ardbeg) 스모키버스": n("ardbeg-smokiverse", "Ardbeg Smokiverse", "ardbeg", None, "Smokiverse"),
    "아드벡(Ardbeg) 우가다일": "ardbeg-uigeadail",
    "아드벡(Ardbeg) 코리브레칸": "ardbeg-corryvreckan",
    "아드벡(Ardbeg) 스펙타큘라": n("ardbeg-spectacular", "Ardbeg Spectacular", "ardbeg", None, "Spectacular"),
    "아드벡(Ardbeg) 14년 앤쏠로지": n("ardbeg-anthology-14", "Ardbeg Anthology 14", "ardbeg", 14, "Anthology"),
    "아드벡(Ardbeg) 19년 트라이반": n("ardbeg-traigh-bhan-19", "Ardbeg Traigh Bhan 19", "ardbeg", 19, "Traigh Bhan"),
    "아드벡(Ardbeg) 23년 Y2K": n("ardbeg-y2k-23", "Ardbeg 23 Y2K", "ardbeg", 23, "Y2K"),
    "아드벡(Ardbeg) 25년": n("ardbeg-25", "Ardbeg 25", "ardbeg", 25),
    "라프로익(Laphroaig) 10년": "laphroaig-10",
    "라프로익(Laphroaig) 셀렉트": n("laphroaig-select", "Laphroaig Select", "laphroaig", None, "Select"),
    "라프로익(Laphroaig) 쿼터 캐스크": "laphroaig-quarter-cask",
    "라프로익(Laphroaig) 10년 셰리 캐스크 피니시": n("laphroaig-10-sherry-finish", "Laphroaig 10 Sherry Oak Finish", "laphroaig", 10, "Sherry Oak Finish"),
    "라프로익(Laphroaig) PX 캐스크": n("laphroaig-px-cask", "Laphroaig PX Cask", "laphroaig", None, "PX Cask"),
    "라프로익(Laphroaig) 10년 캐스크 스트렝스": b("laphroaig-10-cask-strength"),
    "라프로익(Laphroaig) 18년": n("laphroaig-18", "Laphroaig 18", "laphroaig", 18),
    "라프로익(Laphroaig) 25년 캐스크 스트렝스": b("laphroaig-25"),
    "보모어(Bowmore) 10년": n("bowmore-10", "Bowmore 10", "bowmore", 10),
    "보모어(Bowmore) 12년": "bowmore-12",
    "보모어(Bowmore) 15년": "bowmore-15",
    "보모어(Bowmore) 18년": b("bowmore-18"),
    "보모어(Bowmore) 18년 딥 앤 컴플렉스": n("bowmore-18-deep-complex", "Bowmore 18 Deep & Complex", "bowmore", 18, "Deep & Complex"),
    "보모어(Bowmore) 12년 셰리오크": n("bowmore-12-sherry-oak", "Bowmore 12 Sherry Oak", "bowmore", 12, "Sherry Oak"),
    "보모어(Bowmore) 15년 셰리오크": n("bowmore-15-sherry-oak", "Bowmore 15 Sherry Oak", "bowmore", 15, "Sherry Oak"),
    "보모어(Bowmore) 18년 셰리오크": n("bowmore-18-sherry-oak", "Bowmore 18 Sherry Oak", "bowmore", 18, "Sherry Oak"),
})

# ---------- 미라보_05 ----------
G.update({
    "크라겐모어(Cragganmore) 12년": "cragganmore-12",
    "벤로막(Benromach) 10년": "benromach-10",
    "벤로막(Benromach) 12년 캐스크 스트렝스": n("benromach-12-cs", "Benromach 12 Cask Strength", "benromach", 12, "Cask Strength"),
    "벤로막(Benromach) 피트 스모크": n("benromach-peat-smoke", "Benromach Peat Smoke", "benromach", None, "Peat Smoke"),
    "벤로막(Benromach) 2013 빈티지": n("benromach-2013-vintage", "Benromach 2013 Vintage", "benromach", None, "2013 Vintage"),
    "벤로막(Benromach) 15년": "benromach-15",
    "벤로막(Benromach) 싱글 캐스크": "unknown",
    "벤로막(Benromach) 21년": n("benromach-21", "Benromach 21", "benromach", 21),
    "벤리악(Benriach) 10년": n("benriach-10", "BenRiach The Original Ten", "benriach", 10, "The Original Ten"),
    "벤리악(Benriach) 12년": "benriach-12",
    "벤리악(Benriach) 12년 스모키": n("benriach-smoky-12", "BenRiach The Smoky Twelve", "benriach", 12, "The Smoky Twelve"),
    "오반(Oban) 리틀 베이": n("oban-little-bay", "Oban Little Bay", "oban", None, "Little Bay"),
    "오반(Oban) 14년": "oban-14",
    "글렌파클라스(Glenfarclas) 10년": "glenfarclas-10",
    "글렌파클라스(Glenfarclas) 12년": "glenfarclas-12",
    "글렌파클라스(Glenfarclas) 105 캐스크 스트렝스": "glenfarclas-105",
    "글렌파클라스(Glenfarclas) 15년": "glenfarclas-15",
    "글렌파클라스(Glenfarclas) 25년": b("glenfarclas-25"),
    "글렌고인(Glengoyne) 12년": "glengoyne-12",
    "글렌고인(Glengoyne) 15년": n("glengoyne-15", "Glengoyne 15", "glengoyne", 15),
    "글렌고인(Glengoyne) 배치 10 캐스크 스트렝스": n("glengoyne-cs-batch-10", "Glengoyne Cask Strength Batch 10", "glengoyne", None, "Cask Strength Batch 10"),
    "글렌고인(Glengoyne) 18년": n("glengoyne-18", "Glengoyne 18", "glengoyne", 18),
    "클라이넬리쉬(Clynelish) 14년": "clynelish-14",
    "클라이넬리쉬(Clynelish) 디스틸러리 에디션": n("clynelish-de", "Clynelish Distillers Edition", "clynelish", None, "Distillers Edition"),
    "달모어(Dalmore) 12년": "dalmore-12",
    "달모어(Dalmore) 12년 세리캐스크 셀렉트": "dalmore-12-sherry-cask-select",
    "달모어(Dalmore) 포트우드": "dalmore-port-wood",
    "달모어(Dalmore) 15년": "dalmore-15",
    "달모어(Dalmore) 시가몰트": "dalmore-cigar-malt",
    "달모어(Dalmore) 킹 알렉산더 3세": n("dalmore-king-alexander-iii", "The Dalmore King Alexander III", "dalmore", None, "King Alexander III"),
    "달모어(Dalmore) 18년": n("dalmore-18", "The Dalmore 18", "dalmore", 18),
    "아벨라워(Aberlour) 12년": "aberlour-12",
    "아벨라워(Aberlour) 14년": n("aberlour-14", "Aberlour 14", "aberlour", 14),
    "아벨라워(Aberlour) 아부나흐 알바": n("aberlour-abunadh-alba", "Aberlour A'bunadh Alba", "aberlour", None, "A'bunadh Alba"),
    "아벨라워(Aberlour) 아부나흐": "aberlour-abunadh",
    "아벨라워(Aberlour) 16년": n("aberlour-16", "Aberlour 16", "aberlour", 16),
    "에드라두어(Edradour) 10년": "edradour-10",
    "에드라두어(Edradour) 10년 발렌친": n("ballechin-10", "Ballechin 10", "Ballechin", 10),
    "에드라두어(Edradour) 12년 칼레도니아": n("edradour-caledonia-12", "Edradour Caledonia 12", "edradour", 12, "Caledonia"),
    "에드라두어(Edradour) 12년 보르도 캐스크": n("edradour-12-bordeaux", "Edradour 12 Bordeaux Cask", "edradour", 12, "Bordeaux Cask"),
    "에드라두어(Edradour) 12년 캐스크 스트렝스": n("edradour-12-cs", "Edradour 12 Cask Strength", "edradour", 12, "Cask Strength"),
    "에드라두어(Edradour) 12년 소테른 캐스크": n("edradour-12-sauternes", "Edradour 12 Sauternes Cask", "edradour", 12, "Sauternes Cask"),
    "에드라두어(Edradour) 10년 싱글캐스크 캐스크 스트렝스": n("edradour-10-single-cask-cs", "Edradour 10 Single Cask Cask Strength", "edradour", 10, "Single Cask Cask Strength"),
    "에드라두어(Edradour) 21년 캐스크 스트렝스": n("edradour-21-cs", "Edradour 21 Cask Strength", "edradour", 21, "Cask Strength"),
    "달위니(Dalwhinnie) 15년": "dalwhinnie-15",
    "로얄 브라클라(Royal Brackla) 12년": "royal-brackla-12",
    "로얄 브라클라(Royal Brackla) 18년": "royal-brackla-18",
    "로얄 브라클라(Royal Brackla) 21년": n("royal-brackla-21", "Royal Brackla 21", "royal_brackla", 21),
    "아녹(Ancnoc) 12년": n("ancnoc-12", "anCnoc 12", "anCnoc", 12),
    "아녹(Ancnoc) 피티드 셰리": n("ancnoc-peated-sherry", "anCnoc Peated Sherry Cask", "anCnoc", None, "Peated Sherry Cask"),
    "아녹(Ancnoc) 피트 하트": n("ancnoc-peatheart", "anCnoc Peatheart", "anCnoc", None, "Peatheart"),
    "아녹(Ancnoc) 18년": n("ancnoc-18", "anCnoc 18", "anCnoc", 18),
})

# ---------- 미라보_06 ----------
GA = "glenallachie"
G.update({
    "발베니(Balvenie) 12년 더블 우드": "balvenie-12-doublewood",
    "발베니(Balvenie) 12년 아메리칸 오크": n("balvenie-12-american-oak", "The Balvenie 12 American Oak", "balvenie", 12, "American Oak"),
    "발베니(Balvenie) 12년 싱글 배럴": n("balvenie-12-single-barrel", "The Balvenie 12 Single Barrel", "balvenie", 12, "Single Barrel"),
    "발베니(Balvenie) 14년 캐리비안 캐스크": "balvenie-14-caribbean",
    "발베니(Balvenie) 14년 위크 오브 피트": n("balvenie-14-week-of-peat", "The Balvenie 14 The Week of Peat", "balvenie", 14, "The Week of Peat"),
    "발베니(Balvenie) 15년 마데이라 캐스크": n("balvenie-15-madeira", "The Balvenie 15 Madeira Cask", "balvenie", 15, "Madeira Cask"),
    "발베니(Balvenie) 16년 프렌치 오크": n("balvenie-16-french-oak", "The Balvenie 16 French Oak", "balvenie", 16, "French Oak"),
    "발베니(Balvenie) 18년 페드로 히메네즈 캐스크": b("balvenie-18-px"),
    "발베니(Balvenie) 21년 포트 우드": "balvenie-21-portwood",
    "글렌리벳(Glenrivet) 12년 더블 오크": "glenlivet-12",
    "글렌리벳(Glenrivet) 15년 프렌치 오크": "glenlivet-15",
    "글렌리벳(Glenrivet) 18년": "glenlivet-18",
    "글렌그란트(Glengrant) 12년": "glen-grant-12",
    "글렌그란트(Glengrant) 15년": "glen-grant-15",
    "글렌그란트(Glengrant) 18년": "glen-grant-18",
    "모틀락(Mortlach) 16년": n("mortlach-16", "Mortlach 16", "Mortlach", 16),
    "올트모어(Aultmore) 12년": "aultmore-12",
    "올트모어(Aultmore) 18년": n("aultmore-18", "Aultmore 18", "aultmore", 18),
    "올트모어(Aultmore) 21년": n("aultmore-21", "Aultmore 21", "aultmore", 21),
    "에버펠디(Aberfeldy) 12년": n("aberfeldy-12", "Aberfeldy 12", "Aberfeldy", 12),
    "에버펠디(Aberfeldy) 16년": n("aberfeldy-16", "Aberfeldy 16", "Aberfeldy", 16),
    "글렌로티스(Glenrothes) 12년": "glenrothes-12",
    "글렌로티스(Glenrothes) WMC": "glenrothes-whisky-makers-cut",
    "글렌로티스(Glenrothes) 18년": n("glenrothes-18", "The Glenrothes 18", "glenrothes", 18),
    "맥캘란(Maccallan) 12년 더블 캐스크": "macallan-12-double-cask",
    "맥캘란(Maccallan) 12년 셰리 캐스크": "macallan-12-sherry-oak",
    "맥캘란(Maccallan) 15년 더블 캐스크": "macallan-15-double-cask",
    "맥캘란(Maccallan) 클래식컷 2025": n("macallan-classic-cut-2025", "The Macallan Classic Cut 2025", "macallan", None, "Classic Cut 2025"),
    "맥캘란(Maccallan) 18년 더블캐스크": n("macallan-18-double-cask", "The Macallan 18 Double Cask", "macallan", 18, "Double Cask"),
    "맥캘란(Maccallan) 18년 셰리 캐스크": n("macallan-18-sherry-oak", "The Macallan 18 Sherry Oak", "macallan", 18, "Sherry Oak"),
    "글렌피딕(Glenfiddich) 12년": "glenfiddich-12",
    "글렌피딕(Glenfiddich) 12년 아몬티야도 셰리 피니시": "glenfiddich-12-sherry-cask-finish",
    "글렌피딕(Glenfiddich) 14년": n("glenfiddich-14", "Glenfiddich 14 Bourbon Barrel Reserve", "glenfiddich", 14, "Bourbon Barrel Reserve"),
    "글렌피딕(Glenfiddich) 15년": "glenfiddich-15",
    "글렌피딕(Glenfiddich) 18년": "glenfiddich-18",
    "글렌피딕(Glenfiddich) 21년 그란 르제르바": "glenfiddich-21",
    "글렌피딕(Glenfiddich) 23년 그랑 크루": n("glenfiddich-23-grand-cru", "Glenfiddich 23 Grand Cru", "glenfiddich", 23, "Grand Cru"),
    "글렌알라키(Glenallachie) 8년": "glenallachie-8",
    "글렌알라키(Glenallachie) 12년": "glenallachie-12",
    "글렌알라키(Glenallachie) 10년 캐스크 스트렝스": "glenallachie-10-cask-strength",
    "글렌알라키(Glenallachie) 9년 퀴베 캐스크 피니시": n("glenallachie-9-cuvee", "GlenAllachie 9 Cuvée Cask Finish", GA, 9, "Cuvee Cask Finish"),
    "글렌알라키(Glenallachie) 8년 스코티시 오크 피니시": n("glenallachie-8-scottish-oak", "GlenAllachie 8 Scottish Oak Finish", GA, 8, "Scottish Oak Finish"),
    "글렌알라키(Glenallachie) 10년 루비포트 캐스크 피니시": n("glenallachie-10-ruby-port", "GlenAllachie 10 Ruby Port Wood Finish", GA, 10, "Ruby Port Wood Finish"),
    "글렌알라키(Glenallachie) 12년 모스카텔 캐스크 피니시": n("glenallachie-12-moscatel", "GlenAllachie 12 Moscatel Wood Finish", GA, 12, "Moscatel Wood Finish"),
    "글렌알라키(Glenallachie) 10년 스페니시 오크 피니시": n("glenallachie-10-spanish-oak", "GlenAllachie 10 Spanish Virgin Oak Finish", GA, 10, "Spanish Virgin Oak Finish"),
    "글렌알라키(Glenallachie) 15년": "glenallachie-15",
    "글렌알라키(Glenallachie) 18년": "glenallachie-18",
    "글렌알라키(Glenallachie) 18년 PX 펀천": n("glenallachie-18-px-puncheon", "GlenAllachie 18 PX Puncheon", GA, 18, "PX Puncheon"),
    "발렌타인 글렌버기(Glenburgie) 12년": n("glenburgie-12", "Ballantine's Glenburgie 12", "Glenburgie", 12),
    "발렌타인 글렌버기(Glenburgie) 15년": n("glenburgie-15", "Ballantine's Glenburgie 15", "Glenburgie", 15),
    "탐두(Tamdhu) 12년": n("tamdhu-12", "Tamdhu 12", "Tamdhu", 12),
    "탐두(Tamdhu) 배치스트랭스 8": n("tamdhu-batch-strength-8", "Tamdhu Batch Strength No.8", "Tamdhu", None, "Batch Strength No.8"),
    "탐두(Tamdhu) 15년": n("tamdhu-15", "Tamdhu 15", "Tamdhu", 15),
    "탐두(Tamdhu) 18년": n("tamdhu-18", "Tamdhu 18", "Tamdhu", 18),
})

# ---------- 미라보_07: American ----------
G.update({
    "메이커스 마크(Maker's Mark) 버번": "makers-mark",
    "메이커스 마크(Maker's Mark) 46": n("makers-mark-46", "Maker's Mark 46", "makers_mark", None, "46"),
    "메이커스 마크(Maker's Mark) 캐스크 스트렝스": b("makers-mark-cask-strength"),
    "리뎀션(Redemption) 라이": n("redemption-rye", "Redemption Rye", "Redemption", None, "Rye"),
    "놉 크릭(Knob Creek) 버번": "knob-creek",
    "놉 크릭(Knob Creek) 라이": n("knob-creek-rye", "Knob Creek Rye", "knob_creek", None, "Rye"),
    "이글레어(Eagle Rare) 10년": "eagle-rare-10",
    "포로지스(Four Roses) 싱글 배럴": n("four-roses-single-barrel", "Four Roses Single Barrel", "Four Roses", None, "Single Barrel"),
    "러셀(Russel's) 10년 버번": n("russells-reserve-10", "Russell's Reserve 10", "russells_reserve", 10),
    "러셀(Russel's) 버번 싱글 배럴": "russells-reserve-single-barrel",
    "러셀(Russel's) 라이 싱글 배럴": n("russells-reserve-rye-single-barrel", "Russell's Reserve Single Barrel Rye", "russells_reserve", None, "Single Barrel Rye"),
    "1776 제임스 E.페퍼(1776 James E. Pepper) 버번": b("james-e-pepper-1776-bourbon"),
    "1776 제임스 E.페퍼(1776 James E. Pepper) 라이": b("james-e-pepper-1776-rye"),
    "믹터스(Michter's) 버번": n("michters-us1-bourbon", "Michter's US*1 Small Batch Bourbon", "Michter's", None, "US*1 Small Batch Bourbon"),
    "믹터스(Michter's) 라이": n("michters-us1-rye", "Michter's US*1 Single Barrel Rye", "Michter's", None, "US*1 Single Barrel Rye"),
    "사제락(Sazerac) 라이": n("sazerac-rye", "Sazerac Rye", "Sazerac", None, "Rye"),
    "브로큰 배럴(Broken Barrel) 버번 포트 캐스크": n("broken-barrel-port-cask", "Broken Barrel Port Cask Bourbon", "Broken Barrel", None, "Port Cask Bourbon"),
    "베이커스(Baker's) 버번": n("bakers-7", "Baker's 7 Bourbon", "Baker's", 7),
    "바톤 1792(Barton 1792) 1792 풀 프루프": n("1792-full-proof", "1792 Full Proof", "1792", None, "Full Proof"),
    "우드포드 리저브(Woodford Reserve) 버번": "woodford-reserve",
    "우드포드 리저브(Woodford Reserve) 더블오크": "woodford-reserve-double-oaked",
    "우드포드 리저브(Woodford Reserve) 더블 X.O": "unknown",
    "윌렛(Willet) 로완스크릭": "rowans-creek",
    "윌렛(Willet) 팟 스틸 리저브": n("willett-pot-still-reserve", "Willett Pot Still Reserve", "Willett", None, "Pot Still Reserve"),
    "윌렛(Willet) 노아스밀": "noahs-mill",
    "윌렛(Willet) 위티드 버번 8년": n("willett-family-estate-bourbon-8", "Willett Family Estate Bourbon 8", "Willett", 8, "Family Estate Bourbon"),
    "배럴(Barrel) 라이 씨그라스": n("barrell-seagrass", "Barrell Seagrass Rye", "Barrell", None, "Seagrass"),
    "블랑톤(Blanton) 버번 싱글배럴": n("blantons-original", "Blanton's Original Single Barrel", "Blanton's", None, "Original Single Barrel"),
    "블랑톤(Blanton) SFTB": n("blantons-sftb", "Blanton's Straight From The Barrel", "Blanton's", None, "Straight From The Barrel"),
    "부커스(Booker's) 버번": "bookers",
    "일라이저 크레이그(Elijah Craig) 버번 배럴 프루프": n("elijah-craig-barrel-proof", "Elijah Craig Barrel Proof", "Elijah Craig", None, "Barrel Proof"),
})

# ---------- 미라보_08: world ----------
KW, MH, JD, WT = "Ki One", "Milk & Honey", "jack_daniels", "wild_turkey"
G.update({
    "하이 코스트(High Coast) 신코 배치 2": n("high-coast-cinco-batch-2", "High Coast Cinco Batch 2", "High Coast", None, "Cinco Batch 2"),
    "스타워드(Starward) 솔레라": n("starward-solera", "Starward Solera", "Starward", None, "Solera"),
    "오마르(Omar) 버번": n("omar-bourbon-cask", "Omar Bourbon Cask", "Omar", None, "Bourbon Cask"),
    "오마르(Omar) 셰리": n("omar-sherry-cask", "Omar Sherry Cask", "Omar", None, "Sherry Cask"),
    "카발란(Kavalan) 클래식": n("kavalan-classic", "Kavalan Classic", "kavalan", None, "Classic"),
    "카발란(Kavalan) 엑스 버번 오크": n("kavalan-ex-bourbon-oak", "Kavalan Ex-Bourbon Oak", "kavalan", None, "Ex-Bourbon Oak"),
    "카발란(Kavalan) 포트캐스크 피니시": n("kavalan-concertmaster", "Kavalan Concertmaster Port Cask Finish", "kavalan", None, "Concertmaster Port Cask Finish"),
    "카발란(Kavalan) 트리플 셰리": "kavalan-triple-sherry",
    "카발란(Kavalan) 올로로소 셰리": n("kavalan-oloroso-sherry-oak", "Kavalan Oloroso Sherry Oak", "kavalan", None, "Oloroso Sherry Oak"),
    "카발란(Kavalan) 솔리스트 올로로소 셰리": "kavalan-solist-sherry",
    "카발란(Kavalan) 솔리스트 포트": n("kavalan-solist-port", "Kavalan Solist Port", "kavalan", None, "Solist Port"),
    "카발란(Kavalan) 비노 바리끄": "kavalan-solist-vinho-barrique",
    "미셸쿠브어(Michel Couveur) 언익스팩티드 넘버3 CS": n("michel-couvreur-unexpected-3", "Michel Couvreur Unexpected No.3 Cask Strength", "Michel Couvreur", None, "Unexpected No.3"),
    "미셸쿠브어(Michel Couveur) 오버에이지드": n("michel-couvreur-overaged", "Michel Couvreur Overaged", "Michel Couvreur", None, "Overaged"),
    "미셸쿠브어(Michel Couveur) 오버에이지드 코리아 에디션": n("michel-couvreur-overaged-korea", "Michel Couvreur Overaged Korea Edition", "Michel Couvreur", None, "Overaged Korea Edition"),
    "기원(Ki-Won) 배치 3 캐스크 스트렝스": n("kiwon-batch-3-cs", "Ki One Batch 3 Cask Strength", KW, None, "Batch 3 Cask Strength"),
    "기원(Ki-Won) 배치 4 스모크": n("kiwon-batch-4-smoke", "Ki One Batch 4 Smoke", KW, None, "Batch 4 Smoke"),
    "기원(Ki-Won) 배치 4 피티드": n("kiwon-batch-4-peated", "Ki One Batch 4 Peated", KW, None, "Batch 4 Peated"),
    "기원(Ki-Won) 배치 5 포트 캐스크 스트렝스": n("kiwon-batch-5-port-cs", "Ki One Batch 5 Port Cask Strength", KW, None, "Batch 5 Port Cask Strength"),
    "기원(Ki-Won) 배치 7": n("kiwon-batch-7", "Ki One Batch 7", KW, None, "Batch 7"),
    "기원(Ki-Won) 시그니처": n("kiwon-signature", "Ki One Signature", KW, None, "Signature"),
    "기원(Ki-Won) 레드페퍼 캐스크": n("kiwon-red-pepper-cask", "Ki One Red Pepper Cask", KW, None, "Red Pepper Cask"),
    "밀크 앤 허니(M&H) 버번 싱글 캐스크": n("mh-bourbon-single-cask", "Milk & Honey Bourbon Single Cask", MH, None, "Bourbon Single Cask"),
    "밀크 앤 허니(M&H) PX 셰리 싱글 캐스크": n("mh-px-sherry-single-cask", "Milk & Honey PX Sherry Single Cask", MH, None, "PX Sherry Single Cask"),
    "잭다니엘(Jack Daniel) 넘버 7": "jack-daniels-old-no7",
    "잭다니엘(Jack Daniel) 애플": n("jack-daniels-apple", "Jack Daniel's Tennessee Apple", JD, None, "Tennessee Apple"),
    "잭다니엘(Jack Daniel) 싱글 배럴 100 프루프": n("jack-daniels-single-barrel-100", "Jack Daniel's Single Barrel 100 Proof", JD, None, "Single Barrel 100 Proof"),
    "버팔로 트레이스(Buffalo Trace) 버번": b("buffalo-trace"),
    "버팔로 트레이스(Buffalo Trace) 웰러 스페셜 리저브": n("weller-special-reserve", "W.L. Weller Special Reserve", "Weller", None, "Special Reserve"),
    "버팔로 트레이스(Buffalo Trace) 웰러 12년": n("weller-12", "W.L. Weller 12", "Weller", 12),
    "와일드 터키(Wild Turkey) 101 라이": n("wild-turkey-101-rye", "Wild Turkey 101 Rye", WT, None, "101 Rye"),
    "와일드 터키(Wild Turkey) 8년 버번": "wild-turkey-101-8",
    "와일드 터키(Wild Turkey) 레어브리드 버번": "wild-turkey-rare-breed",
    "와일드 터키(Wild Turkey) 레어브리드 라이": n("wild-turkey-rare-breed-rye", "Wild Turkey Rare Breed Rye", WT, None, "Rare Breed Rye"),
    "와일드 터키(Wild Turkey) 12년 버번": n("wild-turkey-12", "Wild Turkey 12", WT, 12),
})

# ---------- 미라보_09: Japan, Ireland, India ----------
G.update({
    "산토리(Santory) 월드 위스키 아오": n("suntory-ao", "Suntory World Whisky AO", "Suntory", None, "World Whisky AO"),
    "산토리(Santory) 히비키 제페니즈 하모니": b("hibiki-japanese-harmony"),
    "산토리(Santory) 하쿠슈 DR": b("hakushu-distillers-reserve"),
    "산토리(Santory) 하쿠슈 12년": n("hakushu-12", "Hakushu 12", "Hakushu", 12),
    "산토리(Santory) 야마자키 DR": n("yamazaki-distillers-reserve", "Yamazaki Distiller's Reserve", "yamazaki", None, "Distiller's Reserve"),
    "산토리(Santory) 야마자키 12년": b("yamazaki-12"),
    "닛카(Nikka) 프롬 더 배럴": n("nikka-from-the-barrel", "Nikka From The Barrel", "Nikka", None, "From The Barrel"),
    "닛카(Nikka) 다케스루 퓨어몰트": n("nikka-taketsuru-pure-malt", "Nikka Taketsuru Pure Malt", "Nikka", None, "Taketsuru Pure Malt"),
    "닛카(Nikka) 요이치 싱글몰트": "yoichi-single-malt",
    "닛카(Nikka) 미야기쿄 싱글몰트": n("miyagikyo-single-malt", "Miyagikyo Single Malt", "Miyagikyo", None, "Single Malt"),
    "나가하마(Nagahama) 더 세컨드 배치": n("nagahama-second-batch", "Nagahama The Second Batch", "Nagahama", None, "The Second Batch"),
    "나가하마(Nagahama) PX 셰리": n("nagahama-px-sherry", "Nagahama PX Sherry Cask", "Nagahama", None, "PX Sherry Cask"),
    "나가하마(Nagahama) 피티드 PX 셰리": n("nagahama-peated-px-sherry", "Nagahama Peated PX Sherry Cask", "Nagahama", None, "Peated PX Sherry Cask"),
    "마르스(Mars) 더 럭키캣 메이 앤 하나": n("mars-lucky-cat-may-hana", "Mars The Lucky Cat May & Hana", "Mars", None, "The Lucky Cat May & Hana"),
    "마르스(Mars) 더 럭키캣 하나 앤 초코": n("mars-lucky-cat-hana-choco", "Mars The Lucky Cat Hana & Choco", "Mars", None, "The Lucky Cat Hana & Choco"),
    "마르스(Mars) 고마가타케 2023 에디션": n("komagatake-2023", "Mars Komagatake 2023 Edition", "Mars", None, "Komagatake 2023 Edition"),
    "마르스(Mars) 고마가타케 2024 에디션": n("komagatake-2024", "Mars Komagatake 2024 Edition", "Mars", None, "Komagatake 2024 Edition"),
    "마르스(Mars) 츠누키 2025 에디션": "tsunuki-the-edition-2025",
    "기린(Kirin) 후지산 로크 시그니처 블랜드": n("fuji-sanroku-signature-blend", "Kirin Fuji Sanroku Signature Blend", "Kirin", None, "Fuji Sanroku Signature Blend"),
    "카노스케(Kanosuke) 싱글몰트": n("kanosuke-single-malt", "Kanosuke Single Malt", "Kanosuke", None, "Single Malt"),
    "카노스케(Kanosuke) 히오키 팟스틸": n("kanosuke-hioki-pot-still", "Kanosuke Hioki Pot Still", "Kanosuke", None, "Hioki Pot Still"),
    "카노스케(Kanosuke) 더블 디스틸러리": n("kanosuke-double-distillery", "Kanosuke Double Distillery", "Kanosuke", None, "Double Distillery"),
    "부쉬밀(Bushmill) 블랙 부쉬": n("bushmills-black-bush", "Bushmills Black Bush", "Bushmills", None, "Black Bush"),
    "부쉬밀(Bushmill) 10년": b("bushmills-10"),
    "부쉬밀(Bushmill) 12년": n("bushmills-12", "Bushmills 12", "Bushmills", 12),
    "레드 브레스트(Red Breast) 12년": n("redbreast-12", "Redbreast 12", "Redbreast", 12),
    "네터잭(Natterjack) 캐스크 스트렝스": n("natterjack-cs", "Natterjack Cask Strength", "Natterjack", None, "Cask Strength"),
    "암룻(Amrut) 인디안": n("amrut-indian", "Amrut Indian Single Malt", "Amrut", None, "Indian Single Malt"),
    "암룻(Amrut) 피티드 인디안": n("amrut-peated-indian", "Amrut Peated Indian Single Malt", "Amrut", None, "Peated Indian Single Malt"),
    "암룻(Amrut) 퓨전": n("amrut-fusion", "Amrut Fusion", "Amrut", None, "Fusion"),
    "암룻(Amrut) 인디안 캐스크 스트렝스": n("amrut-indian-cs", "Amrut Indian Single Malt Cask Strength", "Amrut", None, "Indian Single Malt Cask Strength"),
    "암룻(Amrut) 피티드 인디안 캐스크 스트렝스": n("amrut-peated-cs", "Amrut Peated Indian Cask Strength", "Amrut", None, "Peated Indian Cask Strength"),
    "암룻(Amrut) 나랑기": n("amrut-naarangi", "Amrut Naarangi", "Amrut", None, "Naarangi"),
    "암룻(Amrut) 인터미디에이트 셰리": n("amrut-intermediate-sherry", "Amrut Intermediate Sherry", "Amrut", None, "Intermediate Sherry"),
    "암룻(Amrut) 포토노바": n("amrut-portonova", "Amrut Portonova", "Amrut", None, "Portonova"),
    "폴존(Paul John) 클래식": n("paul-john-classic", "Paul John Classic Select Cask", "paul_john", None, "Classic Select Cask"),
    "폴존(Paul John) 피티드": "paul-john-peated",
    "폴존(Paul John) 올로로소 셰리": "paul-john-oloroso",
    "폴존(Paul John) PX 셰리": n("paul-john-px", "Paul John Pedro Ximenez Select Cask", "paul_john", None, "Pedro Ximenez Select Cask"),
    "폴존(Paul John) 라크리마": n("paul-john-lacrima", "Paul John Lacrima", "paul_john", None, "Lacrima"),
    "폴존(Paul John) 리데레": n("paul-john-ridere", "Paul John Ridere", "paul_john", None, "Ridere"),
})

# ---------- 포레스트_01 (Korean only, no brand header) ----------
F: dict[str, str] = {
    "글렌그란트 10년": "glen-grant-10", "글렌리벳 12년": "glenlivet-12", "글렌피딕 12년": "glenfiddich-12",
    "글렌피딕 15년": "glenfiddich-15", "발베니 12년": "balvenie-12-doublewood",
    "발베니 14년 캐리비안 캐스크": "balvenie-14-caribbean", "맥캘란 12년 더블 캐스크": "macallan-12-double-cask",
    "맥캘란 15년 더블 캐스크": "macallan-15-double-cask", "글렌알라키 10년 CS": "glenallachie-10-cask-strength",
    "글렌알라키 12년": "glenallachie-12", "글렌알라키 15년": "glenallachie-15",
    "로즈아일 12년": n("roseisle-12", "Roseisle 12", "Roseisle", 12),
    "글렌글라사 샌드엔드": n("glenglassaugh-sandend", "Glenglassaugh Sandend", "Glenglassaugh", None, "Sandend"),
    "글렌모렌지 오리지널": "glenmorangie-original", "글렌모렌지 라산타 12년": "glenmorangie-lasanta",
    "글렌모렌지 퀸타 루반 14년": "glenmorangie-quinta-ruban", "글렌모렌지 시그넷": "glenmorangie-signet",
    "글렌드로낙 12년": "glendronach-12", "글렌드로낙 15년": "glendronach-15",
    "글렌드로낙 18년": "glendronach-18-allardice", "글렌드로낙 포트우드": "new:glendronach-port-wood",
    "글렌드로낙 피티드": "new:glendronach-traditionally-peated",
    "글렌드로낙 29년 1993 빈티지 캐스크 보틀링": n("glendronach-1993-29", "GlenDronach 1993 29 Year Vintage Cask Bottling", "glendronach", 29, "1993 Vintage Cask Bottling"),
    "탈리스커 10년": "talisker-10", "달모어 12년": "dalmore-12", "오반 14년": "oban-14", "달위니 15년": "dalwhinnie-15",
    "글렌파클라스 105": "glenfarclas-105", "크라이넬리시 14년": "clynelish-14", "라프로익 10년": "laphroaig-10",
    "라프로익 PX 캐스크": "new:laphroaig-px-cask", "보모어 12년": "bowmore-12", "아드벡 10년": "ardbeg-10",
    "아드벡 우거다일": "ardbeg-uigeadail", "아드벡 코리브레칸": "ardbeg-corryvreckan",
    "아드벡 스펙타큘러": "new:ardbeg-spectacular", "아드벡 25년": "new:ardbeg-25",
    "라가불린 8년": "lagavulin-8", "라가불린 16년": "lagavulin-16", "킬호만 사닉": b("kilchoman-sanaig"),
    "킬호만 배치 스트렝스": "new:kilchoman-batch-strength", "롱로우 피티드": "new:longrow-peated",
    "빅 피트": n("big-peat", "Douglas Laing Big Peat", "Douglas Laing", None, "Big Peat"),
    "옥토모어 13.1": b("octomore-13-1"),
    "옥토모어 14.3": n("octomore-14-3", "Octomore 14.3", "octomore", None, "14.3"),
    "옥토모어 15.3": "new:octomore-15-3",
    "옥토모어 16.3": n("octomore-16-3", "Octomore 16.3", "octomore", None, "16.3"),
    "아란 10년": "arran-10", "마크리무어 CS": "new:arran-machrie-moor-cs", "킬커란 12년": "new:kilkerran-12",
    "스프링뱅크 10년": "new:springbank-10",
    "글렌스코시아 10년": n("glen-scotia-10", "Glen Scotia 10", "Glen Scotia", 10),
    "레드브레스트 12년": "new:redbreast-12", "폴 존 피티드": "paul-john-peated",
    "히비키 하모니": b("hibiki-japanese-harmony"), "야마자키 12년": b("yamazaki-12"),
    "기원 호랑이": n("kiwon-horangi", "Ki One Horangi", "Ki One", None, "Horangi"),
    "조니워커 블랙": "johnnie-walker-black", "조니워커 블루": "johnnie-walker-blue",
    "발렌타인 21년": "new:ballantines-21", "로얄 살루트 21년": "royal-salute-21",
    "듀어스 18년": n("dewars-18", "Dewar's 18", "Dewar's", 18), "몽키 숄더": "monkey-shoulder",
    "메이커스 마크": "makers-mark",
    "와일드터키 81": n("wild-turkey-81", "Wild Turkey 81", "wild_turkey", None, "81"),
    "와일드터키 라이": n("wild-turkey-rye", "Wild Turkey Rye", "wild_turkey", None, "Rye"), "와일드터키 레어브리드": "wild-turkey-rare-breed",
    "사가모어 라이 CS": n("sagamore-rye-cs", "Sagamore Spirit Cask Strength Rye", "Sagamore Spirit", None, "Cask Strength Rye"),
}

# test 평가(10/14) 이후에만 카탈로그에 넣을 별칭. 지금 넣으면 test 메뉴 표기가 카탈로그로 새어 들어감.
POST_TEST_ALIASES = {
    "glenmorangie-lasanta": ["Glenmorangie Lasanta 15", "글렌모렌지 라산타 15년"],
    "glenmorangie-18": ["Glenmorangie 18 Infinita", "글렌모렌지 18년 인피니타"],
    "glenmorangie-nectar-dor": ["Glenmorangie The Nectar 16", "글렌모렌지 16년 더 넥타"],
    "glenmorangie-original": ["Glenmorangie The Original 12", "글렌모렌지 12년 오리지널"],
}

REVIEW = {
    "시그나토리 빈티지(Signatory Vintage) 스페이사이드 14년": "새 상품. 실재 후보: Signatory Speyside 'M' 14 Small Batch. 카탈로그의 Speyside GL(GL = 다른 증류소 코드)과 별개 (진우 검수)",
    "하이랜드 파크(Highland Park) 캐스크 스트렝스 헤더": "Cask Strength는 Release 번호별로 다른 상품 → unknown (진우 검수)",
    "글렌모렌지(Glenmorangie) 12년 오리지널": "카탈로그 The Original(10년). 2024년 리뉴얼로 12년이 됨 → 같은 상품으로 봄. 연수 불일치로 매칭기는 확정 못 할 것",
    "글렌모렌지(Glenmorangie) 15년 라산타": "카탈로그 Lasanta에 연결. 15년 별칭은 test 평가 후 추가 (POST_TEST_ALIASES, 진우 검수)",
    "글렌모렌지(Glenmorangie) 16년 더 넥타": "The Nectar 16 = Nectar D'Or 리뉴얼 (진우 검수)",
    "글렌모렌지(Glenmorangie) 18년 인피니트": "18 Infinita = 18의 리뉴얼명, 같은 상품. 별칭은 test 평가 후 추가 (진우 검수)",
    "글렌리벳(Glenrivet) 12년 더블 오크": "현재 글렌리벳 12 = 12 Double Oak → 카탈로그 The Glenlivet 12",
    "글렌리벳(Glenrivet) 15년 프렌치 오크": "글렌리벳 15 = 15 French Oak Reserve → 카탈로그 The Glenlivet 15",
    "글렌피딕(Glenfiddich) 12년 아몬티야도 셰리 피니시": "카탈로그 12 Sherry Cask Finish와 같은 상품으로 봄 (불확실)",
    "글렌피딕(Glenfiddich) 21년 그란 르제르바": "21 Gran Reserva = 카탈로그 Glenfiddich 21",
    "카발란(Kavalan) 비노 바리끄": "Vinho Barrique 정규 출시는 Solist 라인. 잔 가격 44,000원이 같은 메뉴의 Solist(41,000원)와 같은 급 → Solist Vinho Barrique 유지",
    "와일드 터키(Wild Turkey) 8년 버번": "Beck 판단과 같이 Wild Turkey 101 8 Year로 봄",
    "벤로막(Benromach) 싱글 캐스크": "싱글 캐스크는 캐스크마다 다른 상품, 메뉴에 번호·연도 없음 → unknown (재검색 후 유지)",
    "아란(Arran) 시그니쳐 시리즈": "Signature Series는 Edition 1 Remnant Renegade, Edition 2 등 여러 개 → unknown (재검색 후 유지)",
    "우드포드 리저브(Woodford Reserve) 더블 X.O": "가격 42,000원으로 같은 메뉴 Double Oaked(19,000원)의 2배 이상. 후보 Double Double Oaked('더블 D.O' 오독?). 사진 확인 전까지 unknown",
    "와일드터키 라이": "81 proof 라이는 상품명이 Wild Turkey Rye → 그 상품 (진우 검수). 101 Rye와 별개",
    "발베니 12년": "Beck과 같이 12 DoubleWood에 연결",
    "글렌드로낙 피티드": "미라보의 Traditionally Peated와 같은 상품으로 봄",
    "글렌드로낙(Glendronach) 18년": "카탈로그 유일한 18년(Allardice)에 연결",
    "에드라두어(Edradour) 10년 발렌친": "Ballechin은 에드라두어 증류소의 피트 브랜드 → 별도 브랜드·상품",
}


def main() -> None:
    catalog = json.loads(CATALOG.read_text(encoding="utf-8"))
    keys = {p["key"] for p in catalog["products"]}
    labels = json.loads(LABELS.read_text(encoding="utf-8"))
    photos, missing = [], []
    for p in labels["photos"]:
        if p["bar"] not in ("미라보", "포레스트"):
            continue
        table = F if p["bar"] == "포레스트" else G
        items = []
        for i in p["items"]:
            g = table.get(i["raw_name"])
            if g is None:
                missing.append(i["raw_name"])
                continue
            items.append({"raw_name": i["raw_name"], "unit": i["unit"], "pour_ml": i["pour_ml"], "gold": g})
        photos.append({"photo_id": p["photo_id"], "bar": p["bar"], "split": "test", "items": items})
    if missing:
        raise SystemExit(f"no gold for: {sorted(set(missing))}")
    for p in photos:
        for i in p["items"]:
            g = i["gold"]
            if g.startswith("new:"):
                assert g[4:] in NEW or g[4:] in BECK_NEW, g
            elif g != "unknown":
                assert g in keys, g
    clash = set(NEW) & (keys | set(BECK_NEW))
    assert not clash, clash
    out = {
        "version": "match_gold_test_draft",
        "created": "2026-10-13",
        "labeling": "Claude draft; human review of `review` entries pending",
        "new_products": {k: {"display_name": d, "brand": br, "age_years": a, "edition_name": e}
                         for k, (d, br, a, e) in NEW.items()},
        "review": REVIEW,
        "photos": photos,
    }
    OUT.write_text(json.dumps(out, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    lines = sum(len({i['raw_name'] for i in p['items']}) for p in photos)
    print(f"wrote {OUT.relative_to(REPO_ROOT)}: {len(photos)} photos, {lines} lines, {len(NEW)} new products")


if __name__ == "__main__":
    main()
