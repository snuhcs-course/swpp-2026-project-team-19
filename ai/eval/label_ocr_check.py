# AI-generated with Claude Code/Claude Opus 5.5 (Jinwoo Park, 2026-10-14, L1). Reviewed by Jinwoo Park.
"""Check label names against the printed menu text read by CLOVA OCR.

    python ai/eval/label_ocr_check.py --set test --out review/test_ocr_check.html
    python ai/eval/label_ocr_check.py --labels eval/new.json --photos <data_dir>/new_photos \\
        --out review/new_ocr_check.html
    python ai/eval/label_ocr_check.py --set test --set val --decisions review/labels_v1_1_proposals.json \\
        --out review/labels_v1_1.html --json review/labels_v1_1_candidates.json

Run before the human review of a new bar's labels (labeling guideline v2.3,
"검수 전 OCR 대조"). No API call: only the OCR cache (<data_dir>/ocr_cache/,
table-off) is read; a photo without a cached response is listed as skipped.

Each label name is split into tokens like recall.name_candidates (whole name,
score.normalize per token). A token that does not occur in the photo's
normalized OCR text is looked up approximately: the OCR substring with the
smallest edit distance (<= max(1, len // 3)). The result is one "diff" per
token: label text, OCR text (original characters, punctuation kept), edit
distance and the photo crop of the OCR line. Diffs are grouped into patterns
"label token -> OCR token" (normalized). A token with no close OCR substring is
listed as "OCR에 없음" (often a brand title the label adds on purpose).

Limitation: a token is only looked up when it is absent from the whole photo
text, so a label spelling that is printed elsewhere on the same photo is not
flagged.

--decisions (optional) classifies patterns for a label revision:
  {"patterns": {"<pattern>": {"category": "A|B|C|D", "print": "...", "note": "..."}},
   "items": {"<photo_id>#<index>": {...same fields, overrides the pattern...}},
   "questions": ["...shown at the top of the page..."]}
  A = OCR misread (label kept), B = label differs from the print (fix),
  C = punctuation (fix), D = uncertain reading (human check). "print" overrides
  the replacement text (default: the OCR original text).
Item ids are "<photo_id>#<index>", index = 0-based position in the photo's items.
"""

from __future__ import annotations

import argparse
import base64
import html
import io
import json
import re
import sys
import unicodedata
from collections import defaultdict
from dataclasses import asdict, dataclass, field
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "ai" / "eval"))
sys.path.insert(0, str(REPO_ROOT / "ai" / "ocr"))
sys.path.insert(0, str(REPO_ROOT / "ai" / "extract"))
from score import LABEL_SETS, normalize  # noqa: E402

TOKEN_SPLIT = re.compile(r"[\s/()\[\]]+")  # same as recall.TOKEN_SPLIT
CATEGORY_TITLES = {
    "B": "B. 라벨이 메뉴판 인쇄와 다름 → 인쇄대로 수정",
    "C": "C. 문장부호 → 인쇄대로 수정",
    "D": "D. 판독 불확실 → 진우 판독 필요 (수정안 없음)",
    "A": "A. CLOVA 오독 → 라벨 유지",
    "?": "미분류",
    "missing": "OCR에 없음 (근사 일치도 없음)",
}
CATEGORY_ORDER = ["B", "C", "D", "?", "A", "missing"]


# ---------- OCR text with a map back to the fields ----------

@dataclass
class OcrText:
    """Normalized photo text; pos[k] = (field index, char index) of normalized char k."""
    fields: list[dict]
    s: str = ""
    pos: list[tuple[int, int]] = field(default_factory=list)

    def __post_init__(self):
        chars = []
        for fi, f in enumerate(self.fields):
            for ci, ch in enumerate(f.get("inferText", "")):
                for n in normalize(ch):
                    chars.append(n)
                    self.pos.append((fi, ci))
        self.s = "".join(chars)

    def original(self, start: int, end: int) -> str:
        """Original OCR characters for normalized span [start, end), punctuation kept,
        fields joined by a space."""
        (f0, c0), (f1, c1) = self.pos[start], self.pos[end - 1]
        parts = []
        for fi in range(f0, f1 + 1):
            t = self.fields[fi].get("inferText", "")
            parts.append(t[c0 if fi == f0 else 0: c1 + 1 if fi == f1 else len(t)])
        return " ".join(parts)

    def field_span(self, start: int, end: int) -> tuple[int, int]:
        return self.pos[start][0], self.pos[end - 1][0]


def best_substrings(pattern: str, text: str) -> tuple[int, list[tuple[int, int]]]:
    """Smallest edit distance of `pattern` to a substring of `text` and every
    (start, end) reaching it (Sellers, with start tracking)."""
    n = len(text)
    prev_d, prev_s = [0] * (n + 1), list(range(n + 1))
    for i, pc in enumerate(pattern, 1):
        cur_d, cur_s = [i] + [0] * n, [0] + [0] * n
        for j, tc in enumerate(text, 1):
            best = (prev_d[j - 1] + (pc != tc), prev_s[j - 1])
            for cand in ((prev_d[j] + 1, prev_s[j]), (cur_d[j - 1] + 1, cur_s[j - 1])):
                if cand[0] < best[0]:
                    best = cand
            cur_d[j], cur_s[j] = best
        prev_d, prev_s = cur_d, cur_s
    d = min(prev_d)
    return d, [(prev_s[j], j) for j in range(n + 1) if prev_d[j] == d and j > prev_s[j]]


def jamo_distance(a: str, b: str) -> int:
    """Edit distance over Hangul jamo (NFD), for breaking ties between syllable edits."""
    from score import levenshtein
    return levenshtein(unicodedata.normalize("NFD", a), unicodedata.normalize("NFD", b))


def max_distance(token: str) -> int:
    return max(1, len(token) // 3)


# ---------- diffs ----------

@dataclass
class Diff:
    item_ids: list[str]  # items sharing this name in the photo (glass/bottle rows)
    photo_id: str
    stem: str
    raw_name: str
    label_piece: str  # original label text of the token
    label_token: str  # normalized
    ocr_text: str | None  # original OCR characters, None if not found
    ocr_token: str | None  # normalized
    distance: int | None
    fields: tuple[int, int] | None  # OCR field index span
    category: str = "?"
    print_text: str | None = None
    new_name: str | None = None
    note: str | None = None

    @property
    def pattern(self) -> str:
        return f"{self.label_token}→{self.ocr_token}" if self.ocr_token else f"{self.label_token}→(없음)"


def label_pieces(raw_name: str) -> list[tuple[str, str]]:
    """(original piece, normalized token) for the whole name."""
    return [(p, normalize(p)) for p in TOKEN_SPLIT.split(raw_name) if normalize(p)]


def check_photo(photo_id: str, stem: str, items: list[dict], ocr: OcrText) -> list[Diff]:
    names: dict[str, list[str]] = defaultdict(list)
    for i, it in enumerate(items):
        names[it["raw_name"]].append(f"{photo_id}#{i}")
    occurrences = defaultdict(list)  # exact token -> start positions in ocr.s
    diffs = []
    for raw_name, ids in names.items():
        pieces = label_pieces(raw_name)
        anchors = []
        for _, tok in pieces:
            if tok in ocr.s:
                if tok not in occurrences:
                    occurrences[tok] = [m.start() for m in re.finditer(re.escape(tok), ocr.s)]
                anchors.append(occurrences[tok])
        # the rarest exact token anchors where this name sits on the photo
        anchor = min(anchors, key=len) if anchors else []
        for piece, tok in pieces:
            if tok in ocr.s or len(tok) < 2:
                continue
            d, spans = best_substrings(tok, ocr.s)
            if d > max_distance(tok) or not spans:
                diffs.append(Diff(ids, photo_id, stem, raw_name, piece, tok, None, None, None, None,
                                  category="missing"))
                continue
            # same-length substitution first (not a shorter span with a deletion), then the
            # closest spelling by jamo (전/젼 over 전/어), then nearest the anchor
            start, end = min(spans, key=lambda se: (abs(se[1] - se[0] - len(tok)),
                                                     jamo_distance(tok, ocr.s[se[0]:se[1]]),
                                                     min((abs(se[0] - a) for a in anchor), default=0)))
            text = ocr.original(start, end)
            diffs.append(Diff(ids, photo_id, stem, raw_name, piece, tok, text, ocr.s[start:end], d,
                              ocr.field_span(start, end)))
    return diffs


def apply_decisions(diffs: list[Diff], decisions: dict) -> None:
    patterns, items = decisions.get("patterns", {}), decisions.get("items", {})
    for df in diffs:
        if df.category == "missing" and df.pattern not in patterns:
            continue
        dec = dict(patterns.get(df.pattern, {}))
        for iid in df.item_ids:
            dec.update(items.get(iid, {}))
        df.category = dec.get("category", df.category)
        df.note = dec.get("note")
        if df.category in ("B", "C"):
            df.print_text = dec.get("print", df.ocr_text)
    # one new name per raw name (a name can carry several fixed tokens)
    by_name = defaultdict(list)
    for df in diffs:
        if df.category in ("B", "C"):
            by_name[(df.photo_id, df.raw_name)].append(df)
    for group in by_name.values():
        new = group[0].raw_name
        for df in group:
            if new.count(df.label_piece) != 1:
                raise SystemExit(f"label piece {df.label_piece!r} not unique in {new!r}")
            new = new.replace(df.label_piece, df.print_text)
        for df in group:
            df.new_name = new


# ---------- photos ----------

def load_set(labels_path: Path, photo_dir: Path) -> tuple[dict, dict[str, str]]:
    """Label file and photo_id -> file stem (from photo_dir/photo_map.json)."""
    labels = json.loads(labels_path.read_text(encoding="utf-8"))
    m = json.loads((photo_dir / "photo_map.json").read_text(encoding="utf-8"))["map"]
    return labels, {pid: Path(fn).stem for fn, pid in m.items()}


def crop_b64(image, response: dict, fields: tuple[int, int], width: int = 900) -> str:
    """JPEG data of the OCR line(s) around the field span, the span boxed in red."""
    from PIL import Image, ImageDraw
    from lines import image_result, to_word

    fs = image_result(response).get("fields") or []
    # widen to the whole OCR line(s): back to the previous lineBreak, forward to the next
    a, b = fields
    while a > 0 and not fs[a - 1].get("lineBreak"):
        a -= 1
    while b < len(fs) - 1 and not fs[b].get("lineBreak"):
        b += 1
    line = [to_word(f) for f in fs[a:b + 1]]
    hit = [to_word(f) for f in fs[fields[0]:fields[1] + 1]]
    h = max(w.y1 - w.y0 for w in line)
    x0 = max(0, min(w.x0 for w in line) - 1.5 * h)
    x1 = min(image.width, max(w.x1 for w in line) + 1.5 * h)
    # cap very long lines (2-column menus joined by CLOVA) around the hit
    hx0, hx1 = min(w.x0 for w in hit), max(w.x1 for w in hit)
    if x1 - x0 > 30 * h:
        x0, x1 = max(0, hx0 - 12 * h), min(image.width, hx1 + 12 * h)
    y0 = max(0, min(w.y0 for w in line) - 1.2 * h)
    y1 = min(image.height, max(w.y1 for w in line) + 1.2 * h)
    crop = image.crop((int(x0), int(y0), int(x1), int(y1))).convert("RGB")
    draw = ImageDraw.Draw(crop)
    pad = 0.15 * h
    draw.rectangle((hx0 - x0 - pad, min(w.y0 for w in hit) - y0 - pad,
                    hx1 - x0 + pad, max(w.y1 for w in hit) - y0 + pad),
                   outline=(220, 30, 30), width=max(2, int(h / 12)))
    # small screenshots (digital menus) are enlarged up to 4x so the glyphs are readable
    target = width if crop.width > width else min(width, crop.width * 4, max(crop.width, 600))
    if target != crop.width:
        crop = crop.resize((target, max(1, round(crop.height * target / crop.width))), Image.LANCZOS)
    buf = io.BytesIO()
    crop.save(buf, "JPEG", quality=85)
    return base64.b64encode(buf.getvalue()).decode()


# ---------- HTML ----------

CSS = """
:root{--bg:#fbfaf7;--fg:#1d1c1a;--mut:#6b6862;--line:#e3e0d9;--card:#fff;--old:#b4232a;--new:#1a7f37;--hl:#fff3c4}
@media (prefers-color-scheme:dark){:root{--bg:#1b1a18;--fg:#ecebe8;--mut:#a29f98;--line:#3a3834;--card:#25231f;--old:#ff8a8a;--new:#6fdc8c;--hl:#4a3f12}}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--fg);font:15px/1.55 system-ui,"Apple SD Gothic Neo","Malgun Gothic",sans-serif}
main{max-width:1100px;margin:0 auto;padding:24px 16px 80px}h1{font-size:24px;margin:0 0 4px}h2{font-size:19px;margin:40px 0 8px;border-bottom:2px solid var(--line);padding-bottom:6px}
h3{font-size:16px;margin:24px 0 6px}.mut{color:var(--mut)}.toc a{color:inherit}table{border-collapse:collapse;width:100%;margin:8px 0}
th,td{border-bottom:1px solid var(--line);padding:6px 8px;text-align:left;vertical-align:top}th{font-weight:600;font-size:13px;color:var(--mut)}
.pat{background:var(--card);border:1px solid var(--line);border-radius:10px;padding:12px 14px;margin:14px 0}
.old{color:var(--old);text-decoration:line-through}.new{color:var(--new);font-weight:600}code{background:var(--hl);padding:0 3px;border-radius:3px}
.ex{display:grid;grid-template-columns:minmax(0,1fr);gap:6px;margin:12px 0;padding-top:10px;border-top:1px dashed var(--line)}
.ex img{max-width:100%;height:auto;border:1px solid var(--line);border-radius:6px;display:block}
.kv{display:grid;grid-template-columns:7em minmax(0,1fr);gap:2px 10px;font-size:14px}.kv b{font-weight:500;color:var(--mut)}
.badge{display:inline-block;font-size:12px;padding:1px 7px;border-radius:9px;border:1px solid var(--line);margin-left:6px}
details summary{cursor:pointer;color:var(--mut)}
"""


def esc(s) -> str:
    return html.escape("" if s is None else str(s))


def render(diffs: list[Diff], crops: dict, title: str, intro: str, questions: list[str] | None = None) -> str:
    groups: dict[str, dict[str, list[Diff]]] = defaultdict(lambda: defaultdict(list))
    for df in diffs:
        groups[df.category][df.pattern].append(df)
    out = [f"<!doctype html><html lang='ko'><head><meta charset='utf-8'>"
           f"<meta name='viewport' content='width=device-width,initial-scale=1'><title>{esc(title)}</title>"
           f"<style>{CSS}</style></head><body><main><h1>{esc(title)}</h1>{intro}"]
    if questions:
        out.append("<div class='pat'><h3>결정 필요</h3><ol>" + "".join(f"<li>{esc(q)}</li>" for q in questions)
                   + "</ol></div>")
    # summary table
    out.append("<h2>요약</h2><table><tr><th>분류</th><th>패턴</th><th>이름</th><th>항목</th><th>split</th></tr>")
    for cat in CATEGORY_ORDER:
        if cat not in groups:
            continue
        ds = [d for ps in groups[cat].values() for d in ps]
        splits = sorted({crops["split"][d.photo_id] for d in ds})
        out.append(f"<tr><td><a href='#cat-{cat}'>{esc(CATEGORY_TITLES[cat])}</a></td><td>{len(groups[cat])}</td>"
                   f"<td>{len(ds)}</td><td>{sum(len(d.item_ids) for d in ds)}</td><td>{esc(', '.join(splits))}</td></tr>")
    out.append("</table>")
    for cat in CATEGORY_ORDER:
        if cat not in groups:
            continue
        collapsed = cat in ("A", "missing")
        out.append(f"<h2 id='cat-{cat}'>{esc(CATEGORY_TITLES[cat])}</h2>")
        if collapsed:
            out.append("<details><summary>펼치기</summary>")
        pats = sorted(groups[cat].items(), key=lambda kv: (-len(kv[1]), kv[0]))
        if not collapsed:
            out.append("<table><tr><th>패턴</th><th>이름</th><th>사진</th></tr>")
            for pat, ds in pats:
                photos = sorted({d.photo_id for d in ds})
                out.append(f"<tr><td><a href='#p-{esc(cat)}-{esc(pat)}'>{esc(ds[0].label_piece)} → "
                           f"{esc(ds[0].print_text or ds[0].ocr_text or '(없음)')}</a></td><td>{len(ds)}</td>"
                           f"<td>{esc(', '.join(photos))}</td></tr>")
            out.append("</table>")
        for pat, ds in pats:
            d0 = ds[0]
            splits = sorted({crops["split"][d.photo_id] for d in ds})
            target = d0.print_text or d0.ocr_text or "(없음)"
            out.append(f"<div class='pat' id='p-{esc(cat)}-{esc(pat)}'><h3><span class='old'>{esc(d0.label_piece)}</span> → "
                       f"<span class='new'>{esc(target)}</span> <span class='mut'>· {len(ds)}개 이름</span>"
                       + "".join(f"<span class='badge'>{esc(s)}</span>" for s in splits) + "</h3>")
            if d0.note:
                out.append(f"<p class='mut'>{esc(d0.note)}</p>")
            # every name in a list; crops: first diff of each photo plus up to 2 more per photo
            out.append("<table><tr><th>항목 id</th><th>기존 표기</th><th>새 표기</th><th>CLOVA 원문</th></tr>")
            for d in ds:
                out.append(f"<tr><td>{esc(', '.join(d.item_ids))}</td><td>{esc(d.raw_name)}</td>"
                           f"<td class='new'>{esc(d.new_name or ('(판독 후 결정)' if cat == 'D' else '—'))}</td><td><code>{esc(d.ocr_text)}</code>"
                           + (f" <span class='mut'>(편집 {d.distance})</span>" if d.distance is not None else "")
                           + "</td></tr>")
            out.append("</table>")
            shown, seen = defaultdict(int), set()
            limit = 1 if cat in ("A", "missing") else 3
            for d in ds:
                key = (d.photo_id, d.stem, d.fields)
                if (d.fields is None or shown[d.photo_id] >= limit or key in seen
                        or key not in crops["img"]):
                    continue
                shown[d.photo_id] += 1
                seen.add(key)
                out.append(f"<div class='ex'><div class='kv'><b>사진</b><span>{esc(d.photo_id)} "
                           f"<span class='mut'>({esc(d.stem)})</span></span>"
                           f"<b>기존</b><span class='old'>{esc(d.raw_name)}</span>"
                           f"<b>새 표기</b><span class='new'>{esc(d.new_name or '—')}</span>"
                           f"<b>CLOVA</b><span><code>{esc(d.ocr_text)}</code></span></div>"
                           f"<img loading='lazy' alt='{esc(d.photo_id)} 크롭' src='data:image/jpeg;base64,{crops['img'][key]}'></div>")
            out.append("</div>")
        if collapsed:
            out.append("</details>")
    out.append("</main></body></html>")
    return "\n".join(out)


# ---------- main ----------

def run(sets: list[tuple[str, Path, Path]], decisions: dict | None, crop: bool = True):
    from clova import load_cached
    from PIL import Image
    from extract import data_dir

    diffs, skipped = [], []
    crops = {"img": {}, "split": {}}
    for split, labels_path, photo_dir in sets:
        labels, id_to_stem = load_set(labels_path, photo_dir)
        for photo in labels["photos"]:
            pid = photo["photo_id"]
            crops["split"][pid] = split
            stem = id_to_stem.get(pid)
            rec = load_cached(stem, "off") if stem else None
            if rec is None:
                skipped.append(pid)
                continue
            ocr = OcrText((rec["response"].get("images") or [{}])[0].get("fields") or [])
            ds = check_photo(pid, stem, photo["items"], ocr)
            diffs.extend(ds)
            if crop and ds:
                img_path = data_dir() / "prepared" / rec["meta"]["sent_image"]
                if rec["meta"].get("resized"):
                    img_path = data_dir() / "prepared_ocr" / rec["meta"]["sent_image"]
                with Image.open(img_path) as im:
                    im.load()
                    for d in ds:
                        if d.fields is not None:
                            crops["img"].setdefault((pid, stem, d.fields), crop_b64(im, rec["response"], d.fields))
    if decisions:
        apply_decisions(diffs, decisions)
    return diffs, skipped, crops


def main() -> None:
    from extract import data_dir

    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--set", dest="sets", action="append", choices=list(LABEL_SETS),
                        help="known label set(s); repeatable")
    parser.add_argument("--labels", type=Path, help="label file (with --photos), e.g. a new bar")
    parser.add_argument("--photos", type=Path, help="photo dir holding photo_map.json")
    parser.add_argument("--decisions", type=Path)
    parser.add_argument("--out", type=Path, required=True, help="HTML review page")
    parser.add_argument("--json", type=Path, help="also write the diffs as JSON")
    parser.add_argument("--title", default="라벨 ↔ OCR 표기 대조")
    args = parser.parse_args()

    sets = [(s, LABEL_SETS[s]["labels"], data_dir() / LABEL_SETS[s]["photo_dir"]) for s in args.sets or []]
    if args.labels:
        if not args.photos:
            parser.error("--labels needs --photos")
        sets.append((args.labels.stem, args.labels, args.photos))
    if not sets:
        parser.error("give --set or --labels")
    decisions = json.loads(args.decisions.read_text(encoding="utf-8")) if args.decisions else None
    diffs, skipped, crops = run(sets, decisions)

    intro = (f"<p class='mut'>라벨: {esc(', '.join(str(p.relative_to(REPO_ROOT)) if p.is_relative_to(REPO_ROOT) else str(p) for _, p, _ in sets))}"
             f" · OCR: CLOVA 캐시(table-off) · 사진 크롭은 레포 밖 data/에서 생성 (이 파일은 커밋하지 않음)</p>"
             + (f"<p>OCR 캐시 없음(건너뜀): {esc(', '.join(skipped))}</p>" if skipped else ""))
    args.out.parent.mkdir(parents=True, exist_ok=True)
    questions = (decisions or {}).get("questions")
    args.out.write_text(render(diffs, crops, args.title, intro, questions), encoding="utf-8")
    if args.json:
        rows = [{**asdict(d), "pattern": d.pattern, "split": crops["split"][d.photo_id]} for d in diffs]
        args.json.write_text(json.dumps(rows, ensure_ascii=False, indent=1), encoding="utf-8")
    counts = defaultdict(int)
    for d in diffs:
        counts[d.category] += 1
    print(f"diffs {len(diffs)} " + " ".join(f"{k}={v}" for k, v in sorted(counts.items()))
          + (f" · skipped {skipped}" if skipped else ""))
    print(f"wrote {args.out}")


if __name__ == "__main__":
    main()
