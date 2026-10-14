# AI-generated with Claude Code/Claude Opus 5.5 (Jinwoo Park, 2026-10-14, L1). Reviewed by Jinwoo Park.
"""Build labels v1.1: raw_name as printed on the menu (approved fixes only).

    python ai/eval/build_labels_v1_1.py

Reads the approved decisions (review/labels_v1_1_proposals.json), finds the
category-B diffs with label_ocr_check (OCR cache only, no API call) and writes

  eval/labels_v1_1.json          (val,  from eval/labels_v1.json)
  eval/labels_heldout_v1_1.json  (test, from eval/labels_heldout_v1.json)
  eval/labels_changelog.md

The v1 files are not touched. Only raw_name values change: the new file is the
v1 text with those string values replaced in place (item order = file order),
plus the version string and one "revision" line. Item ids are
"<photo_id>#<index>" (0-based position in the photo's items). The build checks
that every other field, the item order and the item count are unchanged.
"""

from __future__ import annotations

import hashlib
import json
import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "ai" / "eval"))
sys.path.insert(0, str(REPO_ROOT / "ai" / "extract"))
import label_ocr_check as check  # noqa: E402
from score import LABEL_SETS  # noqa: E402

DECISIONS = REPO_ROOT / "review" / "labels_v1_1_proposals.json"
CHANGELOG = REPO_ROOT / "eval" / "labels_changelog.md"
APPROVED = "박진우, 2026-10-14"
TARGETS = {  # split -> (v1 set, new file, old version, new version)
    "val": ("val", REPO_ROOT / "eval" / "labels_v1_1.json", "labels_v1", "labels_v1.1"),
    "test": ("test", REPO_ROOT / "eval" / "labels_heldout_v1_1.json", "labels_heldout_v1", "labels_heldout_v1.1"),
}
RAW_NAME = re.compile(r'"raw_name": ("(?:[^"\\]|\\.)*")')


def approved_fixes() -> dict[str, list[check.Diff]]:
    from extract import data_dir
    decisions = json.loads(DECISIONS.read_text(encoding="utf-8"))
    sets = [(s, LABEL_SETS[s]["labels"], data_dir() / LABEL_SETS[s]["photo_dir"]) for s in TARGETS]
    diffs, skipped, crops = check.run(sets, decisions, crop=False)
    if skipped:
        raise SystemExit(f"OCR cache missing: {skipped}")
    out = {s: [] for s in TARGETS}
    for d in diffs:
        if d.category in ("?", "C"):
            raise SystemExit(f"undecided or unapproved category {d.category}: {d.pattern} ({d.photo_id})")
        if d.category == "B":
            out[crops["split"][d.photo_id]].append(d)
    return out


def rebuild(text: str, labels: dict, new_names: dict[str, str]) -> str:
    """Replace the raw_name string of the given item ids in the original text."""
    ids = [f"{p['photo_id']}#{i}" for p in labels["photos"] for i in range(len(p["items"]))]
    matches = list(RAW_NAME.finditer(text))
    flat = [it["raw_name"] for p in labels["photos"] for it in p["items"]]
    assert [json.loads(m[1]) for m in matches] == flat, "raw_name order in text != item order"
    parts, last = [], 0
    for iid, m in zip(ids, matches):
        if iid in new_names:
            parts += [text[last:m.start(1)], json.dumps(new_names[iid], ensure_ascii=False)]
            last = m.end(1)
    return "".join(parts) + text[last:]


def build(split: str, fixes: list[check.Diff]) -> tuple[Path, int, str]:
    v1_set, out_path, old_v, new_v = TARGETS[split]
    src = LABEL_SETS[v1_set]["labels"]
    raw = src.read_bytes()
    assert hashlib.sha256(raw).hexdigest() == LABEL_SETS[v1_set]["sha256"], f"{src.name} hash"
    text = raw.decode("utf-8")
    labels = json.loads(text)
    new_names = {iid: d.new_name for d in fixes for iid in d.item_ids}

    text = rebuild(text, labels, new_names)
    # header: version string, then one revision line in the file's own indentation
    m = re.search(r'\n( +)"version": "' + re.escape(old_v) + '",\n', text)
    assert m, "version line"
    note = (f"v1.1 (2026-10-14): raw_name {len(new_names)}항목을 메뉴판 인쇄 표기대로 수정 "
            f"(승인 {APPROVED}). 그 외 필드·항목 순서·개수는 {src.name}과 같음. 변경 내역 eval/labels_changelog.md. "
            f"ai/catalog/labels_v1_1.json(v1 + product_key)과는 별개 파일")
    text = (text[:m.start()] + f'\n{m[1]}"version": "{new_v}",\n{m[1]}"revision": {json.dumps(note, ensure_ascii=False)},\n'
            + text[m.end():])

    new = json.loads(text)
    old = labels
    assert len(new["photos"]) == len(old["photos"])
    for po, pn in zip(old["photos"], new["photos"]):
        assert {k: v for k, v in po.items() if k != "items"} == {k: v for k, v in pn.items() if k != "items"}
        assert len(po["items"]) == len(pn["items"])
        for i, (a, b) in enumerate(zip(po["items"], pn["items"])):
            iid = f"{po['photo_id']}#{i}"
            assert {k: v for k, v in a.items() if k != "raw_name"} == {k: v for k, v in b.items() if k != "raw_name"}
            assert b["raw_name"] == new_names.get(iid, a["raw_name"]), iid
    assert {k: v for k, v in old.items() if k not in ("photos", "version")} == \
        {k: v for k, v in new.items() if k not in ("photos", "version", "revision")}
    data = text.encode("utf-8")
    out_path.write_bytes(data)
    return out_path, len(new_names), hashlib.sha256(data).hexdigest()


def changelog(fixes: dict[str, list[check.Diff]], built: dict[str, tuple[Path, int, str]]) -> str:
    lines = [
        "# 라벨 변경 기록",
        "",
        "## v1 → v1.1 (2026-10-14, L1)",
        "",
        "기준: 메뉴판에 인쇄된 그대로 (표준 표기로 고치지 않음, 인쇄 오타도 인쇄대로). "
        "`raw_name`만 고쳤고 항목 id·가격·unit·pour_ml·note·순서·개수는 v1과 같다. v1 파일은 수정하지 않았다.",
        "",
        "- 항목 id = `<photo_id>#<index>` (사진의 items 안 0부터 센 위치)",
        "- 찾는 법: `ai/eval/label_ocr_check.py`로 라벨과 CLOVA OCR(캐시, table-off)이 다른 토큰을 뽑고, "
        "사진 크롭으로 인쇄를 확인했다. 결정 파일 `review/labels_v1_1_proposals.json`",
        f"- 승인: {APPROVED}. CLOVA 오독(A)은 라벨 유지, Beck 백틱(`)은 인쇄가 백틱이라 유지, "
        "판독 불확실 4개는 진우 판독으로 확정",
        "- `ai/catalog/labels_v1_1.json`(I1, v1 + product_key, 이름 표기는 v1과 같음)과는 별개 파일이다",
        "",
        "| 파일 | 수정 항목 | SHA-256 |",
        "| --- | --- | --- |",
    ]
    for split, (path, n, sha) in built.items():
        lines.append(f"| `{path.relative_to(REPO_ROOT).as_posix()}` ({split}) | {n} | `{sha}` |")
    lines += ["", "| split | 사진 | 항목 id | 이전 | 이후 | 근거 |", "| --- | --- | --- | --- | --- | --- |"]
    for split, ds in fixes.items():
        for d in sorted(ds, key=lambda d: (d.photo_id, int(d.item_ids[0].split("#")[1]))):
            basis = f"인쇄 확인 (CLOVA `{d.ocr_text}`, 크롭)"
            if d.note and "진우 판독" in d.note:
                basis = f"진우 판독 (CLOVA `{d.ocr_text}`)"
            lines.append(f"| {split} | {d.photo_id} | {', '.join(d.item_ids)} | {d.raw_name} | {d.new_name} | "
                         f"{basis}; 승인 박진우 |")
    return "\n".join(lines) + "\n"


def main() -> None:
    fixes = approved_fixes()
    built = {split: build(split, fixes[split]) for split in TARGETS}
    CHANGELOG.write_text(changelog(fixes, built), encoding="utf-8", newline="\n")
    for split, (path, n, sha) in built.items():
        print(f"{split}: {n} items changed -> {path.relative_to(REPO_ROOT)}  sha256 {sha}")
    print(f"wrote {CHANGELOG.relative_to(REPO_ROOT)}")


if __name__ == "__main__":
    main()
