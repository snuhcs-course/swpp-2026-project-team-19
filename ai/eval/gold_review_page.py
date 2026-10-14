# AI-generated with Claude Code/Claude Opus 5.5 (Jinwoo Park, 2026-10-14, A3). Review pending.
"""HTML page for the human review of a layer-2 gold draft: each `review` entry with the
current gold link and photo crops of its menu lines (OCR cache only, no API call).

    python ai/eval/gold_review_page.py --gold eval/match_gold_final_v1.json \\
        --labels eval/labels_final_v1.json --photos <data_dir>/eval_photos_final \\
        --out review/final_gold_review.html [--skip "<review key>" ...]

Lines of an entry: label names contained in the entry key, plus the explicit patterns in
EXTRA for entries that name a group of lines. The page has photos in it: do not commit
(review/*.html is git-ignored). Decisions typed on the page are copied out as JSON.
"""

from __future__ import annotations

import argparse
import html
import re
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(Path(__file__).parent))
from label_ocr_check import (OcrText, best_substrings, crop_b64, jamo_distance, load_set,  # noqa: E402
                             max_distance, normalize)

PAREN = re.compile(r"\s*\([^)]*\)")
# Entries that describe a group of lines: raw_name prefixes (or exact names) of their lines.
EXTRA = {
    "독립병입 브랜드": ["The Nectar", "The Maltman", "Eld Vatten", "김과장", "잭비버스", "아쿠아비타",
                   "크래프트브로스", "더 노스스타", "SANSIBAR", "몰트맨"],
    "아쿠아비타 쿨리22/23/24": ["아쿠아비타"],
    "김과장 #3 / #4": ["김과장 #3", "김과장 #4"],
    "크래프트브로스 독수리 오형제 1호 / 3호": ["크래프트브로스"],
    "The Nectar 11y / 12y": ["The Nectar"],
    "샤토가호 / 아르마냑 가호 (오드비_01, 8줄)": ["샤토가호", "아르마냑"],
    "기네스·산미구엘·아사히·코로나 병 (오드비_09)": ["기네스", "산미구엘", "아사히", "코로나"],
    "헤네시 VSOP (수이_05)": ["헤네시 VSOP"],
}


def entry_lines(key: str, items: list[tuple[str, int, dict]]) -> list[tuple[str, int, dict]]:
    prefixes = EXTRA.get(key)
    if prefixes:
        return [t for t in items if any(t[2]["raw_name"].startswith(p) for p in prefixes)]
    parts = {key, *key.split(" / ")}
    return [t for t in items if t[2]["raw_name"] in parts
            or PAREN.sub("", t[2]["raw_name"]).strip() in parts]


def line_extra(ocr: OcrText, span: tuple[int, int], name: str) -> int:
    """Letters (not digits) on the span's whole OCR line beyond the name; prices do not count."""
    fs, (a, b) = ocr.fields, span
    while a > 0 and not fs[a - 1].get("lineBreak"):
        a -= 1
    while b < len(fs) - 1 and not fs[b].get("lineBreak"):
        b += 1
    text = normalize(" ".join(f.get("inferText", "") for f in fs[a:b + 1])).replace(name, "", 1)
    return sum(not c.isdigit() for c in text)


def locate(ocr: OcrText, raw_name: str) -> tuple[tuple[int, int] | None, str]:
    """Field span of the line in the OCR text and how it was found: the whole name exactly, else the
    whole name within edit distance max(1, len // 3) (OCR misreads such as 셰리 -> 세리; ties broken
    by jamo distance), else its longest token (may hit another line; flagged on the page)."""
    whole = normalize(raw_name)
    starts = [k for k in range(len(ocr.s)) if ocr.s.startswith(whole, k)]
    if starts:
        # a short name also occurs inside a longer line ("SANSIBAR 21y" in "SANSIBAR 21y Batch4"):
        # take the occurrence whose OCR line has the fewest other letters
        k = min(starts, key=lambda k: line_extra(ocr, ocr.field_span(k, k + len(whole)), whole))
        return ocr.field_span(k, k + len(whole)), "exact"
    d, spans = best_substrings(whole, ocr.s)
    if spans and d <= max_distance(whole):
        a, b = min(spans, key=lambda s: jamo_distance(whole, ocr.s[s[0]:s[1]]))
        return ocr.field_span(a, b), f"approx (distance {d})"
    tokens = sorted((normalize(t) for t in raw_name.replace("(", " ").replace(")", " ").split()),
                    key=len, reverse=True)
    for p in tokens:
        if len(p) >= 2 and (k := ocr.s.find(p)) >= 0:
            return ocr.field_span(k, k + len(p)), f"token '{p}' only (check the crop)"
    return None, "not found"


def main() -> None:
    from PIL import Image
    sys.path.insert(0, str(REPO_ROOT / "ai" / "ocr"))
    sys.path.insert(0, str(REPO_ROOT / "ai" / "extract"))
    from clova import load_cached
    from extract import data_dir
    from lines import image_result

    ap = argparse.ArgumentParser()
    ap.add_argument("--gold", type=Path, required=True)
    ap.add_argument("--labels", type=Path, required=True)
    ap.add_argument("--photos", type=Path, required=True)
    ap.add_argument("--catalog", type=Path, default=REPO_ROOT / "ai" / "catalog" / "catalog_v2_draft.json")
    ap.add_argument("--skip", action="append", default=[], help="review keys already decided")
    ap.add_argument("--out", type=Path, required=True)
    args = ap.parse_args()

    gold = json.loads(args.gold.read_text(encoding="utf-8"))
    names = {p["key"]: p["display_name"] for p in json.loads(args.catalog.read_text(encoding="utf-8"))["products"]}
    labels, id_to_stem = load_set(args.labels, args.photos)
    price = {(p["photo_id"], k): i["price_krw"] for p in labels["photos"] for k, i in enumerate(p["items"])}
    items = [(p["photo_id"], k, i) for p in gold["photos"] for k, i in enumerate(p["items"])]

    def gold_text(g: str) -> str:
        if g.startswith("new:"):
            np_ = gold["new_products"][g[4:]]
            return f"new: {np_['display_name']} (연수 {np_['age_years']}, 브랜드 {np_['brand']})"
        return g if g in ("unknown", "non_whisky") else f"{g} — {names.get(g, '?')}"

    ocr_cache: dict[str, tuple] = {}

    def crop(photo_id: str, raw_name: str) -> str | None:
        stem = id_to_stem[photo_id]
        if stem not in ocr_cache:
            rec = load_cached(stem, "off")
            img = data_dir() / "prepared" / rec["meta"]["sent_image"]
            if not img.exists():
                img = data_dir() / "prepared_ocr" / rec["meta"]["sent_image"]
            with Image.open(img) as im:
                ocr_cache[stem] = (im.copy(), rec["response"], OcrText(image_result(rec["response"]).get("fields") or []))
        im, resp, ocr = ocr_cache[stem]
        span, how = locate(ocr, raw_name)
        return (crop_b64(im, resp, span) if span else None), how

    cards, missing, located = [], [], []
    keys = [k for k in gold["review"] if k not in args.skip]
    for n, key in enumerate(keys, 1):
        lines = entry_lines(key, items)
        rows = []
        for photo_id, idx, it in lines:
            b64, how = crop(photo_id, it["raw_name"])
            located.append((photo_id, it["raw_name"], how))
            if b64 is None:
                missing.append(it["raw_name"])
            img = f"<img src='data:image/jpeg;base64,{b64}'>" if b64 else "<div class='mut'>OCR에서 줄을 못 찾음</div>"
            warn = "" if how == "exact" else f" · <span class='mut'>크롭 위치: {html.escape(how)}</span>"
            rows.append(f"<div class='line'><div class='meta'><b>{html.escape(it['raw_name'])}</b> "
                        f"<span class='mut'>{photo_id} #{idx + 1} · {it['unit']} · "
                        f"{price[(photo_id, idx)] or 0:,}원</span>{warn}<br>"
                        f"현재 정답: <code>{html.escape(gold_text(it['gold']))}</code></div>{img}</div>")
        if not rows:
            rows.append("<div class='mut'>연결된 줄 없음 (일반 메모)</div>")
        cards.append(
            f"<section data-key='{html.escape(key, quote=True)}'><h2>{n}. {html.escape(key)}</h2>"
            f"<p class='note'>{html.escape(gold['review'][key])}</p>{''.join(rows)}"
            "<div class='decide'><label><input type='radio' name='d{n}' value='ok' checked> 그대로</label> "
            "<label><input type='radio' name='d{n}' value='fix'> 수정</label> "
            "<input class='fix' placeholder='수정 내용 (예: unknown, new: 상품명, 카탈로그 key)'></div></section>"
            .replace("{n}", str(n)))

    page = f"""<!doctype html><html lang="ko"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><title>2층 정답 검수</title>
<style>
:root{{--bg:#fbfaf7;--fg:#1d1c1a;--mut:#77736b;--line:#e4e0d8;--card:#fff;--acc:#b5482b}}
@media (prefers-color-scheme:dark){{:root{{--bg:#1b1a18;--fg:#ecebe7;--mut:#a39f96;--line:#38352f;--card:#24221f;--acc:#e07a5a}}}}
*{{box-sizing:border-box}}body{{margin:0;background:var(--bg);color:var(--fg);font:15px/1.55 system-ui,"Apple SD Gothic Neo","Malgun Gothic",sans-serif}}
main{{max-width:960px;margin:0 auto;padding:24px 16px 80px}}h1{{font-size:22px;margin:0 0 4px}}
section{{background:var(--card);border:1px solid var(--line);border-radius:10px;padding:14px 16px;margin:14px 0}}
h2{{font-size:16px;margin:0 0 6px}}.note{{margin:0 0 10px}}.mut{{color:var(--mut);font-size:13px}}
.line{{border-top:1px solid var(--line);padding:10px 0}}.line img{{max-width:100%;display:block;margin-top:6px;border-radius:4px}}
code{{font-size:13px}}.decide{{border-top:1px solid var(--line);padding-top:10px;display:flex;gap:12px;flex-wrap:wrap;align-items:center}}
.fix{{flex:1;min-width:220px;padding:6px 8px;border:1px solid var(--line);border-radius:6px;background:var(--bg);color:var(--fg)}}
#bar{{position:fixed;bottom:0;left:0;right:0;background:var(--card);border-top:1px solid var(--line);padding:10px 16px;display:flex;gap:10px;justify-content:center}}
button{{background:var(--acc);color:#fff;border:0;border-radius:6px;padding:8px 14px;font-weight:600;cursor:pointer}}
</style></head><body><main>
<h1>수이·오드비 2층 정답 검수</h1>
<p class="mut">{html.escape(args.gold.name)} · 검수 항목 {len(keys)}건 (이미 결정한 {len(args.skip)}건 제외) · 빨간 상자 = OCR에서 찾은 줄 이름.
'수정'을 고르고 내용을 적은 뒤 아래 버튼으로 JSON을 복사해 Claude에게 붙여 넣으세요.</p>
{''.join(cards)}
</main><div id="bar"><button id="copy">수정 사항 JSON 복사</button><span id="msg" class="mut"></span></div>
<script>
document.getElementById('copy').onclick = async () => {{
  const out = {{}};
  document.querySelectorAll('section').forEach(s => {{
    const r = s.querySelector('input[type=radio]:checked');
    if (r && r.value === 'fix') out[s.dataset.key] = s.querySelector('.fix').value;
  }});
  const text = JSON.stringify(out, null, 1);
  try {{ await navigator.clipboard.writeText(text); document.getElementById('msg').textContent = Object.keys(out).length + '건 복사됨'; }}
  catch (e) {{ prompt('복사해 주세요', text); }}
}};
</script></body></html>"""
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_bytes(page.encode("utf-8"))
    n_lines = sum(c.count("class='line'") for c in cards)
    print(f"wrote {args.out}: {len(keys)} entries, {n_lines} lines; not found in OCR: {missing}")
    for photo_id, name, how in located:
        if how != "exact":
            print(f"  {photo_id} {name}: {how}")


if __name__ == "__main__":
    main()
