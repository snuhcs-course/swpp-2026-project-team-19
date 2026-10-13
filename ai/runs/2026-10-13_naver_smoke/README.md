# P17 스모크: Naver 후보 → 매처 태그 → LLM 판정

2026-10-13 · 실행: Claude Code · 검토: 박진우 · 코드 `a22bfee` (첫 실행 `run1_initial/`은 `33cdce4`)

**판정과 후보는 기록만 했다. DB·카탈로그에는 아무것도 반영하지 않았고, 자동 확정 임계값도 정하지 않았다** (`ai/docs/naver_plan.md` 1절).

## 설정

| 항목 | 값 |
| --- | --- |
| 상품 | `match_gold_v1`의 new 상품 중 P28 표본(`naver_sample_v1`) 40개를 뺀 나머지에서 seed 20261014로 독립병입 5 + 정규품 5 |
| 질의 | ① 영문 표준명 ② "한글 브랜드 + 연수"(독립병입은 증류소 한글명 포함; 한글 브랜드는 카탈로그 → 없으면 결과에서 학습, 연수 없는 상품은 생략) ③ 영문 표준명 + "위스키" |
| endpoint | blog, webkr, encyc, cafearticle (`display=10`). 쇼핑 검색 제외 |
| 후보 | 상품당 근거 결과 수 상위 5개 |
| 매처 | S1+S2b+S3, 카탈로그 = `catalog_v1_draft` 전체 별칭 + new 상품 337개(영문 표준명 별칭 1개씩, C1 방식) |
| LLM | `gemini-3.5-flash-lite`, thinking `low`, `judge_prompt_v1.md` (sha256 `4665608c…`), 근거 최대 4개 |
| 파일 | `results.json`(상품별 질의·앵커·후보·근거 출처·매처 결과·판정), `summary.json`(집계) |

## 결과

### endpoint별 결과 수 (10개 상품 합)

| endpoint | 받은 결과 | 후보 근거로 쓰인 결과 |
| --- | --- | --- |
| blog | 198 | 36 |
| webkr | 240 | 45 |
| encyc | 60 | 0 |
| cafearticle | 137 | 27 |

encyc(백과사전)는 위스키 개별 상품 항목이 거의 없어 후보를 하나도 만들지 못했다.

### 상품별 한글 후보

| 상품 | 층 | 찾은 후보 | 남긴 후보 | LLM same |
| --- | --- | --- | --- | --- |
| Gordon & MacPhail Bunnahabhain 10 | 독립병입 | 31 | 5 | 1 |
| Gordon & MacPhail Bunnahabhain Heavily Peated 11 | 독립병입 | 0 | 0 | 0 |
| Signatory Vintage 100 Proof Caol Ila 10 | 독립병입 | 35 | 5 | 0 |
| Signatory Vintage 100 Proof Linkwood 12 | 독립병입 | 42 | 5 | 1 |
| Wilson & Morgan Dailuaine 15 | 독립병입 | 0 | 0 | 0 |
| Kilchoman Fino Sherry Cask Matured | 정규품 | 6 | 5 | 4 |
| Kilchoman PX Sherry Cask Matured | 정규품 | 10 | 5 | 0 |
| Ki One Signature | 정규품 | 9 | 5 | 2 |
| Tomatin 12 | 정규품 | 31 | 5 | 1 |
| Wild Turkey Rye | 정규품 | 9 | 5 | 0 |

- 상품당 찾은 후보 평균 17.3개(중앙값 9.5), 남긴 후보 평균 4.0개. **같은 상품으로 판정된 한글 표기가 하나라도 나온 상품은 10개 중 5개** (독립병입 2, 정규품 3).
- 후보 0개인 두 상품은 카탈로그에 한글 병입사명이 없고, 결과에서 "한글(영문)" 병기도 찾지 못했다.
- Kilchoman PX는 학습된 앵커에 "셰리"가 섞여 브랜드 없는 후보("셰리 캐스크" 등)가 상위 5개를 차지했다. LLM은 전부 different·unsure로 걸렀지만 "킬호만 PX…" 후보는 상위에 들지 못했다.

### 매처 태그 × LLM 판정 (후보 40개)

| 매처 태그 \ LLM | same | different | unsure | 합 |
| --- | --- | --- | --- | --- |
| same | 0 | 0 | 0 | 0 |
| other_product | 0 | 2 | 0 | 2 |
| ambiguous | 1 | 8 | 0 | 9 |
| new | 8 | 12 | 9 | 29 |
| **합** | 9 | 22 | 9 | 40 |

`same` 태그가 0인 것은 예상한 결과다. 이 상품들은 카탈로그에 영문 표준명 별칭만 있어서 한글 표기를 매처가 알 수 없다.

### 엇갈린 사례

**정면으로 엇갈린 사례(매처 `same`인데 LLM이 same 아님, 매처 `other_product`인데 LLM same): 0건.**

매처가 확정하지 못했는데 LLM이 `same`이라고 한 9건 (새 별칭 후보. 사람이 보기에 모두 맞는 판정):

| 상품 | 후보 | 매처 | LLM |
| --- | --- | --- | --- |
| Signatory Vintage 100 Proof Linkwood 12 | 시그나토리 2012 링크우드 12 년 100 | ambiguous (후보 3개 중 입력 상품 포함) | same 0.95 |
| Gordon & MacPhail Bunnahabhain 10 | 고든앤맥페일 디스커버리 부나하벤 10 년 | new | same 0.98 |
| Kilchoman Fino Sherry Cask Matured | 킬호만 피노셰리 머추어드 | new | same 0.95 |
| 〃 | 킬호만 피노 셰리 캐스크 | new | same 0.95 |
| 〃 | 킬호만 피노 셰리 캐스크 머추어드 | new | same 0.95 |
| 〃 | 킬호만 피노 쉐리 캐스크 | new | same 0.95 |
| Ki One Signature | 기원 시그니처 | new | same 0.95 |
| 〃 | 기원 시그니쳐 | new | same 0.95 |
| Tomatin 12 | 토마틴 12 년 | new | same 0.95 |

매처가 다른 상품으로 확정한 2건은 LLM도 different였다: Wild Turkey Rye ← "와일드 터키 레어브리드"(→ Rare Breed), "와일드 터키 101 8년"(→ 101 8 Year).

### 첫 실행(`run1_initial/`)과 바꾼 것

첫 실행에서 아래 문제를 보고 추출 규칙과 프롬프트를 고친 뒤 다시 돌렸다 (스모크 상품만 사용, P28 표본은 쓰지 않음). 스모크 결과를 보고 고쳤으므로, **이 스모크 수치는 고친 규칙에 유리하다.** 일반화 성능은 P28에서 처음 잰다.

| 문제 (첫 실행) | 수정 |
| --- | --- |
| LLM이 병입사 없는 "부나하벤 10 년"을 same 0.95 (상품 1개 확인 단계) | 프롬프트: alias 문자열 자체를 판정, `bottling` 필드, 병입사 → 브랜드 → 연수 → 에디션 확인 순서 |
| LLM이 브랜드 없는 "피노 셰리 캐스크 머추어드"를 same 0.9 | 프롬프트: alias에 브랜드가 없으면 same 아님 |
| LLM이 "기원 시그니처 전국"을 same 0.9 | 프롬프트: 상품명이 아닌 단어가 섞이면 unsure. "전국", "포함"을 홍보어로 |
| "위스키의 원액은 토마틴", "병입사 시그나토리 빈티지" 같은 문장 조각이 한글 브랜드로 학습됨 | 괄호 병기에서만, 조사 앞을 잘라내고 2표 이상만 학습 |
| "토마틴 12년 1병 토마틴 전용잔 1개" 같은 후보 | 수량("1병")·띄어 쓴 조사에서 후보를 끊음 |

첫 실행 집계: 매처 new 25 / ambiguous 9 / other_product 2, LLM same 7 / different 29 (unsure 0). 그중 same 2건("피노 셰리 캐스크 머추어드", "기원 시그니처 전국")이 위 오판이다.

### 호출 수와 지연

| 항목 | 값 |
| --- | --- |
| Naver 호출 (첫 실행, 캐시 없이) | 84회, 오류·재시도 0, 지연 평균 140ms / p50 133 / p95 225 / 최대 293 |
| Naver 호출 (최종 실행) | 0회 (96건 모두 캐시) |
| LLM 호출 (최종 실행) | 40회, 오류·재시도·파싱 실패 0, 지연 평균 1.31초 / p50 1.29 / p95 1.60 / 최대 1.72 |
| LLM 토큰 (최종 실행) | 입력 75,754 (호출당 약 1.9k), 출력 3,033, thought 0 |
| 실행 시간 (최종) | 177초 (LLM 호출 간격 4.5초가 대부분) |
| 이 작업 전체 | Naver 약 110회 (일일 한도 25,000/endpoint), LLM 약 133회 |
