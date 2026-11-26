"""I5: how well the matching LLM (M3a) `kind` answer separates whisky from non-whisky.

Reads a result JSON of ai/eval/i3_match_eval.py (rules + LLM run) and the M3a response
cache that run used. No API call.

    python ai/eval/i5_kind_table.py <result.json> [<result.json> ...] [--md <out.md>]

For each LLM target line (a line the rules did not confirm) it joins the gold class with
the `kind` the LLM answered:
  gold non_whisky          -> non-whisky
  gold known / absent      -> whisky (in the catalog / not in the catalog)
  gold unknown             -> unknown
  no gold (end-to-end)     -> unpaired
`kind` is "missing" when the answer has no item for the line.

Candidates are counted at two points:
  rule   -> candidates of the S1+S2b+S3 result (rules section)
  served -> candidates after the embedding step and the linking guards (server section,
            when the result has one). For a non-`whisky` line the LLM layer returns the
            rule result, so this is rule + embedding.
The variant "flag only when there is no candidate" is scored with both counts.
"""
from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
GOLD_CLASS = {"non_whisky": "non_whisky", "known": "whisky", "absent": "whisky", "unknown": "unknown",
              "unpaired": "unpaired"}
KINDS = ("non_whisky", "whisky", "unclear", "missing")
CLASSES = ("non_whisky", "whisky", "unknown", "unpaired")


def load_kinds(result: dict) -> dict[tuple[str, str], str]:
    """(photo_id, name) -> kind, the way M3Engine.translate keys answers (last line of a name wins)."""
    cache_dir = REPO_ROOT / result["llm"]["cache"]
    out: dict[tuple[str, str], str] = {}
    for run in result["llm"]["photo_runs"]:
        key = run.get("cache_key")
        if key is None:
            continue
        record = json.loads((cache_dir / f"{key}.json").read_text(encoding="utf-8"))
        try:
            by_line = {item["line"]: item for item in json.loads(record["output_text"])["items"]}
        except (json.JSONDecodeError, KeyError, TypeError):
            by_line = {}
        for line in record["input"]["lines"]:
            if line["target"]:
                item = by_line.get(line["line"])
                out[(run["photo_id"], line["name"])] = item["kind"] if item else "missing"
    return out


def joined_rows(result: dict, served_from: dict | None = None) -> list[dict]:
    """`served_from`: a rules-only --server-steps result of the same lines, for a run without a
    server section. Right for the lines the LLM layer leaves as the rule result."""
    kinds = load_kinds(result)
    rule_rows = result["rules"]["rows"]
    llm_rows = result["llm"]["rows"]
    served_rows = (served_from or result).get("server", {}).get("rows")
    if served_rows:
        assert [(r["photo_id"], r["name"]) for r in served_rows] == [(r["photo_id"], r["name"]) for r in llm_rows]
    out = []
    for i, row in enumerate(llm_rows):
        if not row["llm_target"]:
            continue
        rule = rule_rows[i]
        assert (rule["photo_id"], rule["name"]) == (row["photo_id"], row["name"])
        served = served_rows[i] if served_rows else None
        out.append({
            "bar": row["bar"], "photo_id": row["photo_id"], "name": row["name"], "gold": row["gold"],
            "gold_kind": row["kind"], "gold_class": GOLD_CLASS[row["kind"]],
            "gold_display": row.get("gold_display", ""),
            "llm_kind": kinds.get((row["photo_id"], row["name"]), "missing"),
            "rule_status": rule["status"], "rule_n": rule["n_cand"], "rule_cands": rule.get("cands", ""),
            "served_status": served["status"] if served else None,
            "served_n": served["n_cand"] if served else None,
            "served_cands": served.get("cands", "") if served else "",
            "served_rank1_gold": served.get("rank1_gold") if served else None,
            "rule_rank1_gold": rule.get("rank1_gold"),
        })
    return out


def table(rows: list[dict], flagged) -> dict[str, Counter]:
    """gold class -> Counter of flagged / not flagged / llm kind."""
    out = {c: Counter() for c in CLASSES}
    for r in rows:
        out[r["gold_class"]][r["llm_kind"]] += 1
        out[r["gold_class"]]["flagged" if flagged(r) else "not_flagged"] += 1
    return out


VARIANTS = {
    "A: kind == non_whisky": lambda r: r["llm_kind"] == "non_whisky",
    "B: A and no rule candidate": lambda r: r["llm_kind"] == "non_whisky" and r["rule_n"] == 0,
    "C: A and no candidate after embedding": lambda r: (r["llm_kind"] == "non_whisky" and r["served_n"] == 0),
}


def md_report(label: str, result: dict, rows: list[dict]) -> str:
    lines = [f"### {label}", "",
             f"- set `{result['set']}`, catalog `{result['catalog']}`, input `{result['input']}`, "
             f"lines {result['lines']}, LLM targets {len(rows)}, cache `{result['llm']['cache']}`", ""]
    conf = table(rows, VARIANTS["A: kind == non_whisky"])
    lines += ["| gold | n | `non_whisky` | `whisky` | `unclear` | missing |", "|---|---|---|---|---|---|"]
    for c in CLASSES:
        n = sum(conf[c][k] for k in KINDS)
        if n:
            lines.append(f"| {c} | {n} | " + " | ".join(str(conf[c][k]) for k in KINDS) + " |")
    lines.append("")
    has_served = rows and rows[0]["served_n"] is not None
    lines += ["| variant | non-whisky flagged | whisky flagged (wrong) | unknown flagged |", "|---|---|---|---|"]
    for name, fn in VARIANTS.items():
        if name.startswith("C") and not has_served:
            continue
        t = table(rows, fn)
        nw = sum(t["non_whisky"][k] for k in KINDS)
        lines.append(f"| {name} | {t['non_whisky']['flagged']} / {nw} | {t['whisky']['flagged']} | "
                     f"{t['unknown']['flagged']} |")
    lines.append("")

    def listing(title: str, picked: list[dict]) -> None:
        lines.append(f"**{title}** ({len(picked)})")
        lines.append("")
        if not picked:
            lines.append("- none")
        for r in picked:
            served = (f"; after embedding: {r['served_status']} {r['served_n']}"
                      + (f" [{r['served_cands']}]" if r["served_cands"] else "")
                      + (" (gold rank 1)" if r["served_rank1_gold"] else "")) if has_served else ""
            lines.append(f"- `{r['photo_id']}` **{r['name']}** | gold `{r['gold']}`"
                         + (f" ({r['gold_display']})" if r["gold_display"] else "")
                         + f" | llm `{r['llm_kind']}` | rule: {r['rule_status']} {r['rule_n']}"
                         + (f" [{r['rule_cands']}]" if r["rule_cands"] else "") + served)
        lines.append("")

    listing("non-whisky gold, LLM did not say non_whisky",
            [r for r in rows if r["gold_class"] == "non_whisky" and r["llm_kind"] != "non_whisky"])
    listing("whisky gold, LLM said non_whisky",
            [r for r in rows if r["gold_class"] == "whisky" and r["llm_kind"] == "non_whisky"])
    listing("whisky gold, LLM said unclear or gave no item",
            [r for r in rows if r["gold_class"] == "whisky" and r["llm_kind"] in ("unclear", "missing")])
    listing("unknown gold, LLM said non_whisky",
            [r for r in rows if r["gold_class"] == "unknown" and r["llm_kind"] == "non_whisky"])
    listing("non-whisky gold, LLM said non_whisky (correct flags)",
            [r for r in rows if r["gold_class"] == "non_whisky" and r["llm_kind"] == "non_whisky"])
    return "\n".join(lines)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("results", nargs="+", type=Path)
    ap.add_argument("--md", type=Path)
    ap.add_argument("--served-from", type=Path, help="rules-only --server-steps result (same lines)")
    ap.add_argument("--rows-json", type=Path, help="joined rows of every result, for later steps")
    args = ap.parse_args(argv)
    parts, dump = [], {}
    for path in args.results:
        result = json.loads(path.read_text(encoding="utf-8"))
        served_from = json.loads(args.served_from.read_text(encoding="utf-8")) if args.served_from else None
        rows = joined_rows(result, served_from)
        parts.append(md_report(path.as_posix(), result, rows))
        dump[path.as_posix()] = rows
    text = "\n\n".join(parts) + "\n"
    if args.md:
        args.md.parent.mkdir(parents=True, exist_ok=True)
        args.md.write_bytes(text.encode("utf-8"))
    else:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stdout.write(text)
    if args.rows_json:
        args.rows_json.write_bytes((json.dumps(dump, ensure_ascii=False, indent=1) + "\n").encode("utf-8"))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
