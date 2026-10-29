# E8 (I3): 규칙 강화 뒤 M3a 재측정 — 응답 캐시

2026-10-28 · 박진우 (작성: Claude Code) · dev 5개 바(위스키복춘·서로상·미라보·수이·오드비), 라벨 입력

`cache/`는 E8 실행(2026-10-28 18:34, Gemini 111회)의 M3a 응답 115개다. 형식과 키는 `ai/match_llm/llm.py`와 같다(모델, thinking, 프롬프트 SHA-256, 입력 JSON). P10의 실행 전 점검(`ai/docs/i3_eval_freeze.md` 4.3)이 이 캐시만으로 rules+LLM 숫자를 재현한다. Gemini를 부르지 않는다.

```
python ai/eval/i3_match_eval.py --set dev --catalog eval_dropprod --llm \
    --cache <빈 폴더> --seed-cache ai/runs/2026-10-28_e8/cache --cache-only --json <out>
```

E8 C2(= `main` `1d8172d` + P17 카탈로그 v2.3) 숫자. 2026-10-29에 하네스와 #68 서버 LLM 층으로 같은 값을 다시 얻었다.

| 카탈로그 | rules Top-1 / FM / 틀린 확인 권장 / 어려운 줄 | rules+M3a 틀린 확인 권장 / 수락 시 오답률 / 어려운 줄 / LLM 확인 권장 정답 |
|---|---|---|
| `eval` | 0.643 (516/802) / 0 / 3 / 8.10 | 4 / 0.0048 / 4.17 / 149/151 |
| `eval_dropprod` | 0.783 (375/479) / 0 / 6 / 14.45 | 14 / 0.0167 / 13.10 / 48/57 |
| `service` | 0.771 (618/802) / 0 / 4 / 4.59 | 4 / 0.0048 / 3.07 / 67/68 |

E8 실행기(clone·패치 적용·보고서)는 레포 밖에서 돌렸고, 채점 부분은 `ai/eval/i3_match_eval.py`로 옮겼다.
