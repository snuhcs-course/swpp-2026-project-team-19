"""Rebuild text lines (with boxes) from a CLOVA General OCR V2 response.

Fields come in reading order; `lineBreak: true` marks the last field of a line.
A line is further split where the horizontal gap between two consecutive fields
is larger than GAP_FACTOR x the line height, so side-by-side menu columns that
CLOVA put on one line become separate segments.

    python ai/ocr/lines.py <stem> [--variant off|on]     # print lines from the cache
"""

from __future__ import annotations

import argparse
import statistics
from dataclasses import dataclass, field

GAP_FACTOR = 2.5  # tuned on val only (ai/docs/p12_plan.md)
ROW_TOL = 0.75  # row grouping: max center step, x median segment height (val only)


@dataclass
class Word:
    text: str
    x0: float
    y0: float
    x1: float
    y1: float
    confidence: float | None = None


@dataclass
class Line:
    words: list[Word] = field(default_factory=list)

    @property
    def text(self) -> str:
        return " ".join(w.text for w in self.words)

    @property
    def box(self) -> tuple[float, float, float, float]:
        return (min(w.x0 for w in self.words), min(w.y0 for w in self.words),
                max(w.x1 for w in self.words), max(w.y1 for w in self.words))


def image_result(response: dict) -> dict:
    images = response.get("images") or []
    return images[0] if images else {}


def to_word(f: dict) -> Word:
    vs = (f.get("boundingPoly") or {}).get("vertices") or []
    xs = [v.get("x", 0.0) for v in vs] or [0.0]
    ys = [v.get("y", 0.0) for v in vs] or [0.0]
    return Word(f.get("inferText", ""), min(xs), min(ys), max(xs), max(ys), f.get("inferConfidence"))


def raw_lines(response: dict) -> list[list[Word]]:
    """Group fields by lineBreak, keeping CLOVA's order."""
    lines, cur = [], []
    for f in image_result(response).get("fields") or []:
        cur.append(to_word(f))
        if f.get("lineBreak"):
            lines.append(cur)
            cur = []
    if cur:
        lines.append(cur)
    return lines


def split_gaps(words: list[Word], gap_factor: float = GAP_FACTOR) -> list[list[Word]]:
    """Split one line where the gap to the next word exceeds gap_factor x line height."""
    if len(words) < 2 or gap_factor <= 0:
        return [words]
    height = statistics.median(w.y1 - w.y0 for w in words) or 1.0
    parts, cur = [], [words[0]]
    for prev, w in zip(words, words[1:]):
        if w.x0 - prev.x1 > gap_factor * height:
            parts.append(cur)
            cur = []
        cur.append(w)
    parts.append(cur)
    return parts


def build_lines(response: dict, gap_factor: float = GAP_FACTOR) -> list[Line]:
    return [Line(part) for words in raw_lines(response) for part in split_gaps(words, gap_factor)]


def field_texts(response: dict) -> list[str]:
    return [f.get("inferText", "") for f in image_result(response).get("fields") or []]


def image_size(response: dict, fallback: tuple[int, int] | None = None) -> tuple[float, float]:
    """(width, height) for box scaling: convertedImageInfo, else fallback, else the field extent."""
    info = image_result(response).get("convertedImageInfo") or {}
    if info.get("width") and info.get("height"):
        return float(info["width"]), float(info["height"])
    if fallback:
        return float(fallback[0]), float(fallback[1])
    words = [w for line in raw_lines(response) for w in line] or [Word("", 0, 0, 1, 1)]
    return max(w.x1 for w in words) or 1.0, max(w.y1 for w in words) or 1.0


def format_lines(lines: list[Line], size: tuple[float, float]) -> str:
    """One line per row: `L001 [x0,y0,x1,y1] text`, box scaled to 0-1000 of the image."""
    w, h = size
    out = []
    for i, line in enumerate(lines, 1):
        x0, y0, x1, y1 = line.box
        box = ",".join(str(round(v)) for v in (x0 / w * 1000, y0 / h * 1000, x1 / w * 1000, y1 / h * 1000))
        out.append(f"L{i:03d} [{box}] {line.text}")
    return "\n".join(out)


def group_rows(lines: list[Line]) -> list[list[Line]]:
    """Group segments into visual rows by vertical center, top to bottom; each row is
    sorted left to right. Segments are taken in order of center; one joins the current
    row when its center is within ROW_TOL x the median segment height of the previous
    segment's center (chained, so a slightly tilted row stays together)."""
    if not lines:
        return []
    tol = statistics.median(ln.box[3] - ln.box[1] for ln in lines) * ROW_TOL or 1.0

    def center(ln):
        return (ln.box[1] + ln.box[3]) / 2

    rows, cur = [], []
    for ln in sorted(lines, key=center):
        if cur and center(ln) - center(cur[-1]) > tol:
            rows.append(cur)
            cur = []
        cur.append(ln)
    rows.append(cur)
    return [sorted(r, key=lambda ln: ln.box[0]) for r in rows]


def format_rows(lines: list[Line], size: tuple[float, float]) -> str:
    """One visual row per line: `R001 y=229 | [x0-x1] text | [x0-x1] text`, 0-1000 scale."""
    w, h = size
    out = []
    for i, row in enumerate(group_rows(lines), 1):
        y = round(min(ln.box[1] for ln in row) / h * 1000)
        cells = " | ".join(f"[{round(ln.box[0] / w * 1000)}-{round(ln.box[2] / w * 1000)}] {ln.text}" for ln in row)
        out.append(f"R{i:03d} y={y} | {cells}")
    return "\n".join(out)


def format_tables(response: dict) -> str:
    """Table cells as `T1 r0 c2: text` (rowIndex/columnIndex from CLOVA). Empty if none."""
    out = []
    for ti, table in enumerate(image_result(response).get("tables") or [], 1):
        for cell in table.get("cells") or []:
            text = " ".join(
                w.get("inferText", "")
                for tl in cell.get("cellTextLines") or [] for w in tl.get("cellWords") or [])
            span = ""
            if cell.get("rowSpan", 1) > 1 or cell.get("columnSpan", 1) > 1:
                span = f" (span {cell.get('rowSpan', 1)}x{cell.get('columnSpan', 1)})"
            out.append(f"T{ti} r{cell.get('rowIndex')} c{cell.get('columnIndex')}{span}: {text}")
    return "\n".join(out)


def main() -> None:
    from clova import load_cached

    parser = argparse.ArgumentParser(description="Print rebuilt lines from the OCR cache")
    parser.add_argument("stem")
    parser.add_argument("--variant", default="off", choices=["off", "on"])
    parser.add_argument("--gap", type=float, default=GAP_FACTOR)
    args = parser.parse_args()
    rec = load_cached(args.stem, args.variant)
    if rec is None:
        raise SystemExit(f"no cache for {args.stem} ({args.variant})")
    resp = rec["response"]
    print(format_lines(build_lines(resp, args.gap), image_size(resp)))
    tables = format_tables(resp)
    if tables:
        print("\n" + tables)


if __name__ == "__main__":
    main()
