# P28: Naver 후보 LLM 판정 — 실행 기록 (사람 검수 전)

2026-10-15 야간 · 실행: Claude Code · 검토: 박진우 (아침) · 사전 등록 `ai/docs/p28_plan.md` (`8b4a9a7`, 실행 전 커밋) · 코드·판정 프롬프트 `a22bfee` 그대로

**정밀도는 아직 없다.** `review/p28_review.csv`의 `human_verdict`를 채운 뒤 `python ai/naver/p28_score.py`로 계산한다. 아래는 LLM과 매처가 낸 것만이다.

## 설정

| 항목 | 값 |
| --- | --- |
| 표본 | `eval/naver_sample_v1.json` 40개 (독립병입 20, 정규품 20) |
| 질의·endpoint | 스모크와 같음 (blog, webkr, encyc, cafearticle, `display=10`) |
| 매처 태그 v1 (대표, LLM 입력) | S1+S2b+S3, `catalog_v1_draft` + new 상품 337개 영문명 (C1) |
| 매처 태그 v2 (참고 열) | 같은 매처, `catalog_v2_draft` (`origin/i2-catalog-v2` `415e78f`) 전체 별칭 |
| LLM | `gemini-3.5-flash-lite`, thinking `low`, `judge_prompt_v1.md` sha256 `4665608c…` (LF 기준. 파일은 CRLF로 커밋돼 있어 `sha256sum`은 `caaf4fc2…`) |

## 결과

| 층 | 상품 | 후보가 나온 상품 | 후보 | LLM same | different | unsure | same이 하나라도 나온 상품 |
| --- | --- | --- | --- | --- | --- | --- | --- |
| 독립병입 | 20 | 10 | 47 | 8 | 30 | 9 | 6 |
| 정규품 | 20 | 19 | 95 | 43 | 45 | 7 | 19 |
| 합 | 40 | 29 | 142 | 51 | 75 | 16 | 25 |

### 매처 태그 × LLM 판정

| v1 태그 \ LLM | same | different | unsure | 합 |
| --- | --- | --- | --- | --- |
| same | 5 | 0 | 0 | 5 |
| other_product | 0 | 11 | 1 | 12 |
| ambiguous | 19 | 12 | 1 | 32 |
| new | 27 | 52 | 14 | 93 |

| v2 태그 (참고) \ LLM | same | different | unsure | 합 |
| --- | --- | --- | --- | --- |
| same | 12 | 1 | 0 | 13 |
| other_product | 1 | 12 | 1 | 14 |
| ambiguous | 19 | 18 | 1 | 38 |
| new | 19 | 44 | 14 | 77 |

- v1에서 매처와 LLM이 정면으로 엇갈린 사례(매처 same인데 LLM≠same, 매처 other_product인데 LLM same)는 0건이다.
- v2에서는 1건씩 있다(other_product인데 LLM same 1, same인데 LLM different 1). v2 카탈로그에는 test·P47 바의 메뉴 표기가 별칭으로 들어 있어서 v1에서 new였던 후보 일부가 same·other_product로 바뀐다. 검수 때 이 두 줄을 먼저 보면 좋다.
- `bottler_missing` 후보는 1개였고 LLM은 different로 판정했다.
- 근거로 쓰인 결과: blog 190, webkr 121, cafearticle 84, encyc 1.

### 신뢰도 분포 (주의)

LLM same 51건의 신뢰도는 0.9가 4건, 0.95가 45건, 0.98이 2건이다. **신뢰도가 사실상 한 값이라 신뢰도 구간별 오판률(M3)은 구간을 나누는 의미가 거의 없다.** 사전 등록한 구간대로 계산은 하지만, P29의 임계값 근거로는 쓰기 어렵다.

## 호출·지연

| | 호출 | 캐시 | 재시도 | 평균 지연 | p95 |
| --- | --- | --- | --- | --- | --- |
| Naver | 368 (확인 실행 8 + 본 실행 360) | 12 | 0 | 137 ms | 198 ms |
| Gemini | 142 (확인 실행 5 + 본 실행 137) | 판정 캐시 5 재사용 | 0 | 1,824 ms | 3,573 ms |

Gemini 토큰(본 실행): 입력 260,720, 출력 10,150, thought 0. 429·`RESOURCE_EXHAUSTED` 없음. 실행 시간 689초.

## 파일

- `results.json`: 상품별 질의, 앵커, 후보, 근거 출처(endpoint·query·URL·조회 시각·원문 title), 태그 v1/v2, LLM 판정
- `summary.json`: 위 집계
- `judge_cache.json`: (상품 key, 후보) → 판정. 재실행 시 Gemini를 다시 부르지 않음
- `../../review/p28_review.csv`: 검수표 (UTF-8 BOM, 엑셀로 열림). 열 `human_verdict`(same / different / unsure), `note`를 채운다

## 아침에 할 일

1. `review/p28_review.csv` 142줄에 `human_verdict` 채우기. 기준은 `p28_plan.md` 2절: alias 문자열만 메뉴판에 있을 때 기준 상품으로 특정되는가.
2. `python ai/naver/p28_score.py --json ai/runs/2026-10-15_p28/score.json` → M1(정밀도)·M2(95% 상한)·층별·태그별 결과와 판정(통과/보류/불통과).

## 결과 (사람 검수 후, 2026-10-15 오전)

검수: 박진우, 블라인드(LLM 판정·매처 태그 숨김, 상품 순서 섞음). **142줄 중 68줄만 검수했다.** 처음 5개 상품 25줄은 전부 보고, 나머지 117줄은 Gemini 또는 Claude(아래)가 `same`이라고 한 43줄만 봤다. 두 LLM이 모두 `same`이 아니라고 한 74줄은 사람 판정이 없다. 정밀도(M1·M2)는 LLM `same` 줄이 모두 검수됐으므로 그대로 유효하다. **재현율(`human_same_recall`, M5)은 검수 안 한 74줄이 빠져 있어 실제보다 높게 나온다.**

`python ai/naver/p28_score.py --json ai/runs/2026-10-15_p28/score.json`

| 판정자 | LLM same | 사람도 same | M1 (사람 unsure = 오답) | 오판 95% 상한 | 독립병입 오판 |
| --- | --- | --- | --- | --- | --- |
| **Gemini `gemini-3.5-flash-lite` (사전 등록 대상)** | 51 | 47 | **0.922** | 0.171 | 1 |
| Claude (참고, 같은 142줄 블라인드 판정) | 48 | 46 | 0.958 | 0.125 | 1 |

- **사전 등록 판정: 보류.** M1 0.922 ≥ 0.9이지만 독립병입 층에 사람 `different`인 LLM same이 1건 있다(통과 조건 불충족). → Naver 별칭 후보의 LLM `same`은 사람 검토 우선순위로 쓰고, 자동 등록에는 쓰지 않는다(P36 방식 그대로).
- Gemini 오판 4건: `고든 앤 맥페일 디스커버리 밀튼더프 10`(디스커버리 라인과 기준 상품이 다름), `보모어 15 년 다키스트`(구형 보틀), `카발란 올로로소`(솔리스트 올로로소와 구분 안 됨), `부나하벤 18년 바이알`(사람 unsure). Claude 오판 2건은 이 중 밀튼더프·카발란과 같다. **에디션·라인 이름이 빠지거나 다른 경우가 두 모델의 공통 약점이다.**
- 사람 `same` 49줄 중 Gemini가 47, Claude가 46을 `same`으로 잡았다(검수한 줄 기준).
- 후보 품질: 처음 25줄 중 사람 `same`은 9줄이다. 나머지는 글 조각("라인업 8")이나 다른 상품이었고 LLM이 걸렀다. 후보 추출 정밀도가 낮고 판정 단계가 그것을 거르는 구조다.
- 신뢰도: LLM same 51건 중 47건이 0.95 이상이라 구간별 분석(M3)은 의미가 약하다(사전 예상과 같음).
- Claude 판정 기록: 레포 밖 `Bottlemap_P14/p28_claude/claude142.json`(판정 지시는 `judge_prompt_v1.md` + "에디션·병입사 생략 시 different" 강조 한 줄). Gemini 한도 소진으로 P36 남은 판정을 Claude로 대신하기 위해 같은 표본에서 비교한 것이다.
