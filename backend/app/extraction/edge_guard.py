"""Drop the whisky lines of a facing page cut off at the photo's left or right edge (I5-P19).

A photo of an open menu book can show a sliver of the next page at its edge. The model reads
those cut lines as whisky lines without a price: on 011_mirabeau_03 the 12 lines of the next page
came out that way, some of them with a glass mark but never a price
(ai/runs/2026-11-26_i5_p19_followup/report.md, section F).

A whisky line is dropped when both hold:

- it has no price: no option has `priceKrw` (a glass or bottle mark or a pour size without a
  price does not count; a line without any option has no price either);
- the box of its OCR name lines lies wholly inside the strip of `strip_permille` at the left or
  the right edge, on the 0-1000 scale of `raw_output.ocr.lines`: the box's left x is at least
  1000 - strip (right strip) or its right x is at most strip (left strip).

Kept: a line with a price, a line without OCR name lines (no box), the non-whisky lines
(`otherItems`, which this does not look at), and every line when `strip_permille` is 0. The top
and bottom edges are not looked at: no photo had lines cut there.

A dropped line is not lost: `raw_output.droppedEdgeRows` lists each one (its place before the
drop, its name, its OCR name lines and their box), and `raw_output.edgeStripPermille` says which
strip was used. The kept lines are numbered again from 1, and `itemSources` with them.

The strip of 100 comes from one photo (011_mirabeau_03). At 150 the guard starts to drop real lines
of a skewed photo (014_tale_07, `Ardbeg Anthology`), so the margin is not wide.
ai/runs/2026-11-27_i5_pr_prep/report.md has the check against the recorded answers.
"""

import logging
import os
from typing import Any

from app.extraction.errors import ExtractionConfigError

logger = logging.getLogger(__name__)

STRIP_SETTING = "EXTRACTION_EDGE_STRIP_PERMILLE"
DEFAULT_STRIP_PERMILLE = 100
MAX_STRIP_PERMILLE = 499  # 500 would make the two strips the whole photo


def load_strip_permille() -> int:
    """EXTRACTION_EDGE_STRIP_PERMILLE: an integer from 0 (off) to 499; raise ExtractionConfigError otherwise."""
    raw = os.getenv(STRIP_SETTING)
    if not raw:
        return DEFAULT_STRIP_PERMILLE
    try:
        value = int(raw)
    except ValueError:
        value = -1
    if not 0 <= value <= MAX_STRIP_PERMILLE:
        raise ExtractionConfigError(
            f"{STRIP_SETTING} must be an integer from 0 (off) to {MAX_STRIP_PERMILLE}, got {raw!r}"
        )
    return value


def in_edge_strip(box: list[int], strip_permille: int) -> bool:
    """The whole box lies in the left or the right strip (0-1000 scale). Never with a strip of 0."""
    return strip_permille > 0 and (box[0] >= 1000 - strip_permille or box[2] <= strip_permille)


def has_price(item: dict[str, Any]) -> bool:
    """Some option of the line has a price."""
    return any(option.get("priceKrw") is not None for option in item["options"])


def name_box(source: dict[str, Any] | None, boxes: dict[str, list[int]]) -> list[int] | None:
    """The union box of a line's OCR name lines; None without any."""
    lines = [boxes[i] for i in (source or {}).get("nameLines") or [] if i in boxes]
    if not lines:
        return None
    return [min(b[0] for b in lines), min(b[1] for b in lines), max(b[2] for b in lines), max(b[3] for b in lines)]


def drop_edge_rows(items: list[dict[str, Any]], meta: dict[str, Any],
                   strip_permille: int) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """The whisky items of a converted answer (hybrid_v2.convert_output) without the facing-page lines.

    `meta` is the hybrid meta: `itemSources` (per item, by `itemOrder`) and `ocr.lines` (the OCR
    line table with its boxes). Returns the kept items and the meta with `itemSources` numbered
    like them, `droppedEdgeRows` and `edgeStripPermille`. Logs one line per photo with the count.
    """
    sources = {source["itemOrder"]: source for source in meta.get("itemSources") or []}
    boxes = {line["id"]: line["box"] for line in (meta.get("ocr") or {}).get("lines") or []}
    kept: list[dict[str, Any]] = []
    dropped: list[dict[str, Any]] = []
    for item in items:
        source = sources.get(item["itemOrder"])
        box = name_box(source, boxes)
        if has_price(item) or box is None or not in_edge_strip(box, strip_permille):
            kept.append(item)
            continue
        dropped.append({"itemOrder": item["itemOrder"], "menuOrder": source.get("menuOrder"),
                        "rawText": item["rawText"], "nameLines": source["nameLines"], "box": box})

    out_items, out_sources = [], []
    for order, item in enumerate(kept, start=1):
        out_items.append({**item, "itemOrder": order})
        if item["itemOrder"] in sources:
            out_sources.append({**sources[item["itemOrder"]], "itemOrder": order})
    logger.log(
        logging.WARNING if dropped else logging.INFO,
        "extraction edge guard dropped=%d strip_permille=%d", len(dropped), strip_permille,
    )
    return out_items, {**meta, "itemSources": out_sources, "droppedEdgeRows": dropped,
                       "edgeStripPermille": strip_permille}
