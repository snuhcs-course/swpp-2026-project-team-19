"""Evaluate Iteration 1 matching (normalize + exact alias) against the labeled menu items.

Each label's `raw_name` is passed to `resolve_product` as is, so the
"Korean / English" split inside the resolver is evaluated too. Only the
product name is given; other extracted fields stay null.

    cd backend
    uv run python scripts/eval_alias_matching.py
    # without the alias spellings collected from the two evaluation bars' menus
    uv run python scripts/eval_alias_matching.py \
        --exclude-alias-source menu:위스키복춘 --exclude-alias-source menu:서로상
"""

import argparse
import json
import sys
from collections import Counter
from pathlib import Path
from uuid import UUID

BACKEND_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_DIR))

from app.matching import ExtractedProduct, resolve_product  # noqa: E402
from app.matching.memory_catalog import InMemoryCatalog  # noqa: E402

CATALOG_DIR = BACKEND_DIR.parent / "ai" / "catalog"


def evaluate(items: list[dict], catalog: InMemoryCatalog) -> list[dict]:
    rows = []
    for item in items:
        result = resolve_product(ExtractedProduct(product_name=item["raw_name"]), catalog)
        gold = UUID(item["product_id"]) if item["product_id"] else None
        proposed = result.proposed_product_id
        if item["expected_resolution"] == "unmatched":
            correct = result.status == "unmatched"
        else:
            correct = result.status == "exact_match" and proposed == gold
        rows.append(
            {
                "raw_name": item["raw_name"],
                "expected": item["expected_resolution"],
                "gold_key": item["product_key"],
                "status": result.status,
                "proposed": proposed,
                "correct": correct,
                "wrong_exact": result.status == "exact_match" and proposed != gold,
                "candidates": len(result.candidates),
            }
        )
    return rows


def summarize(title: str, rows: list[dict]) -> None:
    total = len(rows)
    statuses = Counter(row["status"] for row in rows)
    correct = sum(row["correct"] for row in rows)
    wrong_exact = sum(row["wrong_exact"] for row in rows)
    print(f"[{title}] n={total}")
    print(f"  exact_match rate : {statuses['exact_match']}/{total} ({statuses['exact_match'] / total:.1%})")
    print(f"  accuracy         : {correct}/{total} ({correct / total:.1%})")
    print(f"  wrong exact match: {wrong_exact}")
    print(
        f"  status counts    : exact_match={statuses['exact_match']} "
        f"ambiguous={statuses['ambiguous']} unmatched={statuses['unmatched']}"
    )
    by_expected = Counter((row["expected"], row["status"]) for row in rows)
    print("  expected -> status: " + ", ".join(f"{e}->{s}={n}" for (e, s), n in sorted(by_expected.items())))


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--catalog", type=Path, default=CATALOG_DIR / "catalog_v1_draft.json")
    parser.add_argument("--labels", type=Path, default=CATALOG_DIR / "labels_v1_1.json")
    parser.add_argument(
        "--exclude-alias-source",
        action="append",
        default=[],
        metavar="SOURCE",
        help="drop aliases whose sources are all excluded, e.g. 'menu:서로상' (repeatable)",
    )
    args = parser.parse_args()

    catalog = InMemoryCatalog.from_seed(args.catalog, exclude_sources=args.exclude_alias_source)
    labels = json.loads(args.labels.read_text(encoding="utf-8"))
    items = [item for photo in labels["photos"] for item in photo["items"]]

    rows = evaluate(items, catalog)
    print(f"catalog: {args.catalog.name}  labels: {args.labels.name} ({labels['version']})")
    print(f"excluded alias sources: {', '.join(args.exclude_alias_source) or 'none'}\n")
    summarize("items", rows)

    # Each menu line appears once per option (glass, bottle), so also report distinct names.
    distinct = list({(row["raw_name"], row["gold_key"]): row for row in rows}.values())
    summarize("distinct raw_name", distinct)

    failures = [row for row in distinct if not row["correct"]]
    print(f"\nincorrect distinct names: {len(failures)}")
    for row in failures:
        proposed = catalog.get_product(row["proposed"]).display_name if row["proposed"] else None
        print(
            f"  {row['raw_name']!r}: expected {row['expected']} ({row['gold_key']}), "
            f"got {row['status']} -> {proposed} [{row['candidates']} candidates]"
        )


if __name__ == "__main__":
    main()
