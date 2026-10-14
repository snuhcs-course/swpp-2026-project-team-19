# P36 준비: Naver 별칭 후보 대기열 — 실행 기록

2026-10-15 야간 · 실행: Claude Code · 검토: 박진우 · 등록 `ai/docs/p36_plan.md` (`b7d4e22`, 실행 전 커밋) · 브랜치 `i2-p36-naver-queue`

**상태: 부분 완료.** 1단계(Naver + 규칙)는 529개 상품 전부 끝났다. 2단계(LLM 판정)는 Gemini가 응답하지 않아(330초 hard timeout 연속) 멈췄고, **남은 후보 1,123개는 `pending_judge`**다. 429·`RESOURCE_EXHAUSTED`는 아니었다. 카탈로그·DB에는 아무것도 넣지 않았다.

## 1단계 (Naver만)

| 항목 | 값 |
| --- | --- |
| 상품 | 529 (그중 P28 표본 40개는 P28 후보·판정 재사용) |
| 후보가 나온 상품 | 466 |
| 후보 (상품당 최대 5) | 2,240 |
| 규칙 제외 | 749 (사유 1개 555, 2개 190, 3개 4) |
| 남은 후보 | 1,491 |
| Naver 호출 | 4,514 (캐시 318), 재시도 0, 오류 0, 평균 142 ms, p95 232 ms, 1단계 1,138초 |

| 제외 사유 | 후보 수 (중복 포함) |
| --- | --- |
| `age_mismatch` | 428 |
| `other_product` | 355 |
| `existing_alias` | 154 |
| `bottler_missing` | 10 |

- 매처 태그(전체 2,240): new 1,045, ambiguous 564, other_product 355, same 276. 남은 1,491개 중 same 120개는 별칭 일치가 아니라 S2/S3로 이 상품에 붙은 후보(기존 별칭과 정규화가 다름)다.
- 독립병입 상품 64개, 그 후보 179개.
- **`p47_only` 상품 82개, 후보 239개(남은 것 181개).** 수이·오드비에서만 나온 상품이다. P47 평가 전에 승인하지 않기를 권한다(`p36_plan.md`).

## 2단계 (LLM, `judge_prompt_v1` 그대로)

| 남은 후보 1,491개 | same | different | unsure | pending_judge |
| --- | --- | --- | --- | --- |
| P28 판정 재사용 | 43 | 53 | 15 | – |
| 이번 판정 (P36) | 67 | 109 | 81 | – |
| 합 | 110 | 162 | 96 | **1,123** |

- LLM same이 하나라도 있는 상품 71개.
- 1회차: Gemini 호출 264회(재시도 6 포함), 판정 257개, 입력 474,491 / 출력 18,645 토큰, 파싱 오류 0. 330초 응답 없음이 5번 이어져 멈춤.
- 2회차(캐시에서 이어서): 호출 5회(재시도 4 포함) 모두 330초 응답 없음 → 멈춤. 판정 0. 이때 Gemini가 사실상 응답하지 않는 상태라 더 시도하지 않았다.
- 429·`RESOURCE_EXHAUSTED`가 아니므로 Gemini 중단 파일(`gemini_quota_stop.json`)은 생기지 않았다.

## 이어서 하는 법

```
python ai/naver/run_p36.py --stage 2
```

판정 캐시(`judge_cache.json`)에 있는 257개는 다시 부르지 않는다. 남은 1,123개를 1개당 약 5초(호출 간격 4.5초)로 부른다 — 약 1.5시간.

## 파일

- `candidates.json`: 상품별 후보, 근거(endpoint·query·URL·조회 시각·원문 title), 매처 태그, 제외 사유, 판정. `meta.stage2`에는 마지막 실행(2회차) 기록만 남아 있다(1회차 숫자는 위 표)
- `judge_cache.json`: (상품 key, 후보) → 판정
- `../../review/p36_alias_queue.csv`: 대기열 (UTF-8 BOM). 열 `product_key, product, independent, p47_only, candidate, source(naver:<endpoint>), evidence, matcher_tag, exclusion, llm_verdict, llm_confidence, llm_reason, human_decision(빈칸)`

## 검토 순서 제안

1. P28 검수(`review/p28_review.csv`)로 LLM same 정밀도를 먼저 본다. 이 대기열의 LLM 판정을 얼마나 믿을지 정하는 근거다.
2. `exclusion`이 빈 줄 중 `llm_verdict = same`부터 `human_decision`을 채운다. `p47_only = yes`는 P47 뒤로 미룬다.
3. `age_mismatch` 제외에는 리뉴얼 표기(연수가 바뀐 상품)도 들어 있다. 이런 별칭은 사람이 상품을 지정해 넣는다(`naver_plan.md` 6절 d).
