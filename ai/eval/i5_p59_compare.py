"""Line-by-line comparison of two i3_match_eval.py results (I5-P59). API 0 calls.

    python ai/eval/i5_p59_compare.py BEFORE.json AFTER.json [--section rules server llm] [--md out.md]

For each section present in both files, the rows are paired by (photo_id, name, occurrence) and a
row counts as changed when its status, outcome, burden, candidates or confirm_recommended differ.
Prints the headline numbers of both files and every changed row, and returns them as a dict.
"""

import argparse
import json
from collections import Counter
from pathlib import Path

FIELDS = ("status", "outcome", "burden", "cands", "confirm_recommended")


def keyed(rows: list[dict]) -> dict:
    seen: Counter = Counter()
    out = {}
    for row in rows:
        k = (row["photo_id"], row["name"])
        out[(*k, seen[k])] = row
        seen[k] += 1
    return out


def headline(section: dict) -> dict:
    a = section["all"]
    burden = Counter(r["burden"] for r in section["rows"])
    return {"top1": f"{a['correct']}/{a['known']}", "fm": a["fm"], "wrong_cr": a["wrong_cr"],
            "hard_per_photo": round(a["hard_per_photo"], 3),
            "confirm/choose/register/wrong": "/".join(str(burden[b]) for b in ("confirm", "choose", "register", "wrong")),
            "confirmed": burden["confirmed"]}


def compare(before: dict, after: dict, sections: list[str]) -> dict:
    out = {}
    for sec in sections:
        if sec not in before or sec not in after:
            continue
        b, a = keyed(before[sec]["rows"]), keyed(after[sec]["rows"])
        if set(b) != set(a):
            raise SystemExit(f"{sec}: the two results do not have the same lines")
        changed = []
        for k in b:
            if any(b[k].get(f) != a[k].get(f) for f in FIELDS):
                changed.append({"photo_id": k[0], "name": k[1], "gold": b[k].get("gold"),
                                "before": {f: b[k].get(f) for f in FIELDS},
                                "after": {f: a[k].get(f) for f in FIELDS}})
        lost = [c for c in changed if c["before"]["outcome"] == "correct" and c["after"]["outcome"] != "correct"]
        gained = [c for c in changed if c["after"]["outcome"] == "correct" and c["before"]["outcome"] != "correct"]
        out[sec] = {"before": headline(before[sec]), "after": headline(after[sec]), "lines": len(b),
                    "changed": changed, "lost_correct_confirmations": lost, "new_correct_confirmations": gained}
    return out


def cell(value) -> str:
    """A Markdown table cell: `|` in a value (gold "both:a|b", candidates "A || B") would start a new column."""
    return str(value).replace("|", r"\|")


def to_md(result: dict, title: str) -> str:
    lines = [f"# {title}", ""]
    for sec, r in result.items():
        lines += [f"## {sec} ({r['lines']}줄, 바뀐 줄 {len(r['changed'])})", "",
                  "| | Top-1 | FM | 틀린 확인 권장 | hard/photo | confirm/choose/register/wrong | 확정 |", "|---|---|---|---|---|---|---|"]
        for when in ("before", "after"):
            h = r[when]
            lines.append(f"| {when} | {h['top1']} | {h['fm']} | {h['wrong_cr']} | {h['hard_per_photo']} | "
                         f"{h['confirm/choose/register/wrong']} | {h['confirmed']} |")
        lines += ["", f"맞는 확정이 사라진 줄 {len(r['lost_correct_confirmations'])}, 새로 맞게 확정된 줄 "
                  f"{len(r['new_correct_confirmations'])}", ""]
        if r["changed"]:
            lines += ["| 사진 | 줄 | 정답 | 전 | 후 |", "|---|---|---|---|---|"]
            for c in r["changed"]:
                fmt = lambda s: f"{s['status']} / {s['outcome']} / {s['burden']}{' CR' if s['confirm_recommended'] else ''}: {s['cands'][:80]}"
                lines.append("| " + " | ".join(cell(v) for v in (c["photo_id"], c["name"], c["gold"], fmt(c["before"]),
                                                                   fmt(c["after"]))) + " |")
            lines.append("")
    return "\n".join(lines) + "\n"


def main(argv=None) -> dict:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("before", type=Path)
    ap.add_argument("after", type=Path)
    ap.add_argument("--section", nargs="+", default=["rules", "llm", "server"])
    ap.add_argument("--md", type=Path)
    ap.add_argument("--title", default="")
    args = ap.parse_args(argv)
    load = lambda p: json.loads(p.read_text(encoding="utf-8"))
    result = compare(load(args.before), load(args.after), args.section)
    md = to_md(result, args.title or f"{args.before.name} -> {args.after.name}")
    if args.md:
        args.md.parent.mkdir(parents=True, exist_ok=True)
        args.md.write_text(md, encoding="utf-8", newline="\n")
    print(md)
    return result


if __name__ == "__main__":
    main()
