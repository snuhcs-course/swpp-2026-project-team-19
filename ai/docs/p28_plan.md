# P28: Naver 후보 LLM 판정 정밀도 (사전 등록)

2026-10-15 · 박진우 (작성: Claude Code 야간 작업, 검토: 박진우) · 브랜치 `i2-p28-naver-precision` (`origin/i2-p17-naver` `d24b004` 위)

`naver_plan.md` 7절의 P28 등록을 실행한다. 이 문서는 **실행 전에** 지표와 판정 규칙을 고정하려고 쓴다. 실행 후 이 문서의 지표 정의는 바꾸지 않는다.

## 1. 고정한 것

| 항목 | 값 |
| --- | --- |
| 코드·프롬프트 | `a22bfee` (`ai/naver/` 전체, `judge_prompt_v1.md` sha256 `4665608c…`). **판정 프롬프트는 고치지 않는다** |
| 표본 | `eval/naver_sample_v1.json` 40개 (독립병입 20, 정규품 20) |
| 질의·endpoint·후보 수 | 스모크와 같음: 질의 3개(+학습 브랜드 질의), blog·webkr·encyc·cafearticle, `display=10`, 상품당 후보 상위 5개 |
| 매처 태그(대표) | S1+S2b+S3, `catalog_v1_draft` 전체 별칭 + new 상품 337개 영문 표준명 (스모크와 같은 C1 방식). LLM 입력의 `matcher_tag`도 이 태그 |
| 매처 태그(참고 열) | 같은 매처, 카탈로그 = `catalog_v2_draft`(`origin/i2-catalog-v2` `415e78f`) 전체 별칭. LLM 입력에는 넣지 않는다 |
| LLM | `gemini-3.5-flash-lite`, thinking `low`, 근거 최대 4개, 호출 간격 4.5초 |

매처 코드는 두 태그 모두 이 브랜치(`i2-p17-naver`)의 `backend/app/matching`을 쓴다. 카탈로그만 다르다.

`catalog_v2_draft`에는 test 바(미라보·포레스트)와 P47 바(수이·오드비)의 메뉴 표기 별칭이 들어 있다. 이 태그는 "지금 카탈로그로 이 후보가 무엇에 붙는가"를 보는 참고 열이고, 사진·정답은 열지 않는다.

## 2. 사람 검수 (`review/p28_review.csv`)

- 후보 한 줄마다 `human_verdict`를 채운다: `same` / `different` / `unsure`. 기준은 `judge_prompt_v1.md`의 "같은 상품" 정의와 같다: **alias 문자열이 메뉴판에 그대로 적혀 있을 때 그것만으로 기준 상품으로 특정되는가.**
- 검수자는 LLM 판정 열을 가리고 볼 수 있다(열 순서상 LLM 열은 오른쪽 끝 근처).
- `unsure`는 검수자도 근거로 정할 수 없을 때만 쓴다.

## 3. 지표 (`ai/naver/p28_score.py`)

`human_verdict`가 빈 줄은 계산에서 빼고, 빈 줄 수를 따로 출력한다.

| # | 지표 | 정의 |
| --- | --- | --- |
| M1 | **LLM same 정밀도 (대표)** | LLM `same` 줄 중 `human_verdict = same` 비율. 사람 `unsure`는 **틀린 것으로 셈**(보수적) |
| M1b | 같은 값, 사람 `unsure` 제외 | 참고 |
| M2 | false merge 95% 상한 | M1의 오판 수 k / LLM same 수 n에 대한 **단측 Clopper–Pearson 95% 상한**. (k=0, n=40이면 7.2%) |
| M3 | 신뢰도 구간별 오판률 | 구간 `[0, 0.5)`, `[0.5, 0.8)`, `[0.8, 0.9)`, `[0.9, 0.95)`, `[0.95, 1]`. 구간마다 (a) LLM same 줄의 오판률(사람≠same), (b) 전체 줄에서 LLM 판정 ≠ 사람 판정 비율 |
| M4 | 층별 결과 | 독립병입 / 정규품 각각 M1, M2, 후보 수, LLM same 수 |
| M5 | 상품 단위 재현 | 사람이 same으로 본 후보가 하나라도 있는 상품 중, LLM same이 하나라도 있는 상품 비율 (별칭 확보율) |
| M6 | 매처 태그 × 사람 판정 | v1, v2 태그 각각. `other_product` 태그 중 사람 same 수(규칙 제외의 비용) |
| M7 | 규칙 제외 효과 | `bottler_missing` 후보 중 사람 same 수, LLM same 수 |

## 4. 판정 규칙

- `naver_plan.md` 6절 (e)대로 **이 표본으로 자동 확정 기준(false merge ≤ 0.02)을 증명할 수 없다.** P28은 아래만 판정한다.
  - **통과(별칭 후보 제안용으로 사용 가능):** M1 ≥ 0.9 이고 독립병입 층에서 사람 `different`인 LLM same이 0건.
  - **보류:** M1 ≥ 0.8.
  - **불통과:** M1 < 0.8 → P36 대기열에서 LLM same을 우선순위로만 쓰고 판정 근거로는 쓰지 않는다.
- 어느 경우든 등록은 사람 검토(P36)다. 임계값은 P29에서 정한다.

## 5. 기록

- `ai/runs/2026-10-15_p28/results.json` (상품별 질의·후보·근거 출처·태그 v1/v2·LLM 판정), `summary.json` (집계, 호출 수, 지연)
- `review/p28_review.csv` (검수표, UTF-8 BOM)
- Gemini 429 / `RESOURCE_EXHAUSTED`가 나오면 그 자리에서 멈추고, 판정 캐시(`ai/runs/2026-10-15_p28/judge_cache.json`)로 이어서 실행할 수 있게 한다.
