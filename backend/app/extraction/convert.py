# AI-generated with Claude Code/Claude Opus 5.5 (Jinwoo Park, 2026-10-06, PR #10). Reviewed by Jinwoo Park.
"""Convert prompt v1 output to the flow v2 4.3 item format.

Prompt v1 returns one item per (name, glass/bottle) and leaves out section titles,
descriptions and non-whisky sections. So every converted item is a `product`, and
brand, age, edition, ABV and confidence are always null until a prompt fills them.
"""

from typing import Any

OPTION_LABELS = {"glass": "잔", "bottle": "병", None: None}


def to_flow_items(v1_items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Group v1 items into 4.3 items, keeping the model's output order.

    A glass item and a bottle item with the same raw_name that are next to each other
    come from one menu line, so they become one item with two options. Anything else
    stays a separate item: the same name in two places on a menu is not merged.
    (In the P14 A2 runs all 530 glass/bottle pairs were adjacent.)
    """
    groups: list[list[dict[str, Any]]] = []
    for item in v1_items:
        previous = groups[-1] if groups else None
        if (
            previous is not None
            and len(previous) == 1
            and previous[0]["raw_name"] == item["raw_name"]
            and {previous[0]["unit"], item["unit"]} == {"glass", "bottle"}
        ):
            previous.append(item)
        else:
            groups.append([item])

    return [_flow_item(order, group) for order, group in enumerate(groups, start=1)]


def _flow_item(order: int, group: list[dict[str, Any]]) -> dict[str, Any]:
    name = group[0]["raw_name"]
    options = [
        {"optionLabel": OPTION_LABELS[v["unit"]], "pourMl": v["pour_ml"], "priceKrw": v["price_krw"]}
        for v in group
        if v["unit"] is not None or v["pour_ml"] is not None or v["price_krw"] is not None
    ]
    return {
        "itemOrder": order,
        "rawText": name,
        "lineType": "product",
        "productName": name,
        "brandText": None,
        "ageYears": None,
        "editionName": None,
        "abv": None,
        "options": options,
        "confidence": None,
    }
