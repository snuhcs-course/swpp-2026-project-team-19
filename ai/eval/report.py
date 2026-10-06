"""Tables for the P14 summary from scored run directories.

    python ai/eval/report.py ai/runs/2026-10-04_A ai/runs/2026-10-04_A2 ai/runs/2026-10-04_B

Reads scores.json (score.py) and the call records; prints Markdown tables:
metrics per condition, per-photo accuracy, error types, cost per photo, and the
decision from eval_plan.md.
"""

from __future__ import annotations

import argparse
import json
import statistics
from collections import Counter, defaultdict
from pathlib import Path

THRESHOLD = 0.85


def fmt(v, digits=3):
    if v is None:
        return "-"
    return f"{v['mean']:.{digits}f} ({v['min']:.{digits}f}–{v['max']:.{digits}f})"


def decide(acc: dict[str, float]) -> str:
    a, a2, b = acc.get("A"), acc.get("A2"), acc.get("B")
    if a is not None and a >= THRESHOLD:
        return f"A {a:.3f} ≥ 0.85 → Flash-Lite 기본값으로 계속, 프롬프트 개선"
    if a2 is not None and a2 >= THRESHOLD:
        return f"A {a:.3f} < 0.85, A2 {a2:.3f} ≥ 0.85 → Flash-Lite + thinking medium 채택"
    if b is not None and b >= THRESHOLD:
        return f"A {a:.3f}·A2 {a2:.3f} < 0.85, B {b:.3f} ≥ 0.85 → 모델 상향을 비용과 함께 결정"
    return f"A {a:.3f}·A2 {a2:.3f}·B {b:.3f} 모두 < 0.85 → 리스크 R1 비상 대응 (OCR + LLM 파싱 검토)"


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("run_dirs", nargs="+", type=Path)
    args = parser.parse_args()

    scores = {}
    for d in args.run_dirs:
        s = json.loads((d / "scores.json").read_text(encoding="utf-8"))
        cond = json.loads((d / "manifest.json").read_text(encoding="utf-8"))["condition"]
        scores[cond] = (d, s)

    print("## 조건별 지표 (5회 평균, 괄호는 최소–최대)\n")
    print("| 조건 | 항목 정답률 | F1 엄격 | F1 관대 | 가격 정확도 | 잔·병 혼동 | 오탐 | 누락 | 실패 호출 |")
    print("| --- | --- | --- | --- | --- | --- | --- | --- | --- |")
    for c, (_, s) in scores.items():
        m = s["summary"]
        print(f"| {c} | {fmt(m['item_accuracy'])} | {fmt(m['f1_strict'])} | {fmt(m['f1_lenient'])} | "
              f"{fmt(m['price_accuracy'])} | {fmt(m['unit_confusion'], 1)} | {fmt(m['fp'], 1)} | "
              f"{fmt(m['fn'], 1)} | {len(s['failed_calls'])} |")

    print("\n## 사진별 항목 정답률 (5회 평균, 최소–최대)\n")
    pids = list(next(iter(scores.values()))[1]["per_photo_accuracy"])
    n_gt = {p["photo_id"]: p["n_gt"] for p in next(iter(scores.values()))[1]["runs"]["1"]["photos"]}
    print("| 사진 | 정답 항목 | " + " | ".join(scores) + " |")
    print("| --- | --- | " + " | ".join("---" for _ in scores) + " |")
    for pid in pids:
        cells = [fmt(s["per_photo_accuracy"][pid]) for _, s in scores.values()]
        print(f"| {pid} | {n_gt[pid]} | " + " | ".join(cells) + " |")

    print("\n## 오류 유형 (5회 합계)\n")
    types = defaultdict(Counter)
    for c, (_, s) in scores.items():
        for run in s["runs"].values():
            for p in run["photos"]:
                for e in p["errors"]:
                    types[e["type"]][c] += 1
    print("| 유형 | " + " | ".join(scores) + " |")
    print("| --- | " + " | ".join("---" for _ in scores) + " |")
    for t, cnt in sorted(types.items(), key=lambda kv: -sum(kv[1].values())):
        print(f"| {t} | " + " | ".join(str(cnt[c]) for c in scores) + " |")

    print("\n## 1장당 비용 (호출 평균)\n")
    print("| 조건 | 입력 토큰 | 출력 토큰 | thought 토큰 | 응답 시간(초) | 재시도 포함 호출 |")
    print("| --- | --- | --- | --- | --- | --- |")
    for c, (d, _) in scores.items():
        recs = [json.loads(f.read_text(encoding="utf-8")) for f in sorted(d.glob("*_r*.json"))
                if not f.name.endswith(".error.json")]
        def avg(k):
            vals = [r[k] for r in recs if r.get(k) is not None]
            return statistics.mean(vals) if vals else 0
        retried = sum(1 for r in recs if r.get("attempts", 1) > 1)
        print(f"| {c} | {avg('input_tokens'):,.0f} | {avg('output_tokens'):,.0f} | "
              f"{avg('thought_tokens'):,.0f} | {avg('latency_ms') / 1000:.1f} | {retried} |")

    acc = {c: s["summary"]["item_accuracy"]["mean"] for c, (_, s) in scores.items()
           if s["summary"]["item_accuracy"]}
    print(f"\n## 판정\n\n{decide(acc)}")


if __name__ == "__main__":
    main()
