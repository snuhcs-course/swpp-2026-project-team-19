# Naver 후보 수집 + LLM 확인 계획 (P17·P18)

2026-10-13 · 박진우 (작성: Claude Code, 검토: 박진우) · 브랜치 `i2-p17-naver`

메뉴 표기(한글·병입사식)를 카탈로그 별칭으로 보강하기 위해, NAVER API HUB 검색 결과에서 상품별 한글 표기 후보를 모으고 LLM으로 같은 상품인지 확인하는 프로토타입이다. P22 test에서 상품이 DB에 있어도 메뉴 표기를 못 찾은 168줄(C1)이 출발점이다 (`2026-10-13_match_summary`, 남은 오류 3).

## 1. 원칙

- **Naver 결과와 LLM 판정은 후보 제안과 판정 기록까지만 한다.** 이번 작업에서는 DB와 카탈로그(`catalog_v1_draft.json`)에 아무것도 반영하지 않는다.
- 나중에 서비스에 붙일 때의 구분:
  - **매칭**(메뉴 줄 → 기존 상품): LLM 신뢰도가 임계값 이상이면 자동 확정해서 바로 서비스한다.
  - **등록**(새 상품·새 별칭 생성): 판정과 상관없이 사람이 검토한다 (P36).
  - 임계값은 P29(10/15)에서 측정 근거로 정한다. **이번에는 정하지 않는다.**
- 모든 후보에 출처를 기록한다: endpoint, query, 결과 URL, 조회 시각, 원문 title.
- API 키(NAVER API HUB, Gemini)는 `.env`에서만 읽고, 로그와 결과 파일에 남기지 않는다.
- 응답 캐시(`<data_dir>/naver_cache/`)는 레포 밖에 두고 커밋하지 않는다.

## 2. 평가 표본 (P28용, 이번 작업에서 실행·열람 금지)

- 대상: `eval/match_gold_v1.json`의 new 상품 337개 (dev 30 + test 307; test 324 중 dev와 겹치는 17개는 dev로 셈하지 않고 한 번만 셈).
- 층: **독립병입**(병입사가 다른 증류소 원액을 자기 이름으로 낸 상품) 20, **증류소 정규품**(그 외) 20.
- 독립병입 판정은 new 상품의 `brand`가 아래 병입사 목록에 있는지로 정한다. 목록은 표본 추출 전에 `ai/naver/sample.py`의 `IB_BOTTLERS`에 고정했다.
  - Signatory, Gordon & MacPhail, Douglas Laing, Hunter Laing, La Maison du Whisky, The Whisky Agency, Samaroli, Wilson & Morgan, Highland Laird, Elements of Islay, Port Askaig, Blackadder
  - 정규품으로 둔 경계 사례: Compass Box·Michel Couvreur(블렌더·숙성사), Macnair's(GlenAllachie 소유 브랜드), Ki One(국내 증류소).
- 추출: `random.Random(20261013)`로 각 층에서 20개씩 비복원 추출 → `eval/naver_sample_v1.json`. 이 파일은 다른 작업보다 먼저 커밋했다.
- 이 40개는 P17 스모크·프롬프트 수정에 쓰지 않는다. 스모크 표본은 이 40개를 뺀 나머지에서 뽑는다.

## 3. P17 구성 (`ai/naver/`)

| 파일 | 역할 |
| --- | --- |
| `client.py` | NAVER API HUB 검색. `GET https://naverapihub.apigw.ntruss.com/search/v1/{blog,webkr,encyc,cafearticle}`, 헤더 `X-NCP-APIGW-API-KEY-ID` / `X-NCP-APIGW-API-KEY` (ncloud 문서 `naver-api-hub-overview`, `naver-api-hub-search-examples`로 확인). 쇼핑 검색은 API HUB에 없음. 초당 4회 이하, 429·5xx·네트워크 오류는 3회까지 재시도, 응답은 `<data_dir>/naver_cache/`에 캐시(처음 조회 시각 유지) |
| `candidates.py` | 질의 생성, 결과 title·description에서 한글 표기 후보 추출. 태그·엔티티·홍보 문구 제거. 후보마다 근거(endpoint, query, URL, 조회 시각, 원문 title, 정리한 snippet) |
| `tagger.py` | 후보 별칭을 매처 S1+S2b+S3로 조회해 `same` / `other_product` / `ambiguous` / `new` |
| `judge.py`, `judge_prompt_v1.md` | `judge(candidate) -> {verdict, product_id, confidence, reason, meta}`. alias 모드(지금)와 match 모드(S4: 메뉴 줄 → 후보 중 선택)를 같은 형식으로 받음 |
| `run_smoke.py` | 스모크 실행·집계 |
| `test_naver.py` | 응답 픽스처로 단위 테스트 16개, 키가 있을 때만 실제 호출 2개 |

키는 레포 `.env`를 먼저 읽고, 없는 이름은 작업 공간 `.env`(데이터 폴더 옆)에서 채운다. 결과 파일에는 요청 경로와 파라미터만 남기고 헤더는 남기지 않는다.

### 한글 후보를 뽑는 방법

1. 질의: ① 영문 표준명 ② "한글 브랜드 + 연수"(독립병입은 증류소 한글명 포함; 연수 없는 상품은 생략) ③ 영문 표준명 + "위스키".
2. 앵커: 카탈로그 브랜드의 한글 별칭(`brand`). 없으면 결과의 괄호 병기 "한글(Brand)", "Brand(한글)", "한글 전체명(Brand …)"에서 학습(`learned`, 2표 이상). 독립병입은 에디션에 나오는 증류소의 한글 별칭도 앵커로 둔다(`edition_brand`). 이 후보는 병입사 이름이 빠진 위험 사례를 일부러 남기는 것이다.
3. 정리한 텍스트를 구분자·홍보어·수량("1병")·띄어 쓴 조사에서 끊고, 앵커로 시작하는 6토큰 이하 구간을 후보로 삼는다. 조사가 붙은 토큰("10년은")에서 끊고, 앵커만 있는 후보는 버린다.
4. 근거 결과 수가 많은 순으로 상품당 5개를 LLM에 보낸다.

### LLM 판정 지침 (`judge_prompt_v1.md`)

- 판정 대상은 alias **문자열 자체**다. 근거 글에 병입사가 나와도 alias에 없으면 같은 상품이 아니다.
- `different`: 독립병입 ↔ 정규품, 연수 다름, 에디션 다름(캐스크 스트렝스, 피니시, 배치, 빈티지), 리뉴얼 전후라도 연수 다름, 브랜드 다름.
- `unsure`: 근거에서 브랜드와 연수(연수 없는 상품은 에디션)가 모두 확인되지 않을 때, alias에 브랜드가 없을 때, 상품명이 아닌 단어가 섞였을 때.
- 근거에 없는 사실은 추측하지 않는다.
- 모델 `gemini-3.5-flash-lite`, thinking `low`. **자동 확정 임계값은 정하지 않았다.**
- 프롬프트는 스모크 10개로만 고쳤다. P28 표본은 쓰지 않았다.

## 4. P17 스모크 결과 요약

상세: `ai/runs/2026-10-13_naver_smoke/README.md`.

- 10개 상품(독립병입 5, 정규품 5)에서 후보 40개. 같은 상품으로 판정된 한글 표기가 하나라도 나온 상품 5개, 후보 0개 2개(둘 다 독립병입).
- 매처 태그: new 29, ambiguous 9, other_product 2, same 0. LLM: same 9, different 22, unsure 9.
- 매처 `same`/`other_product`와 LLM이 정면으로 엇갈린 사례 0건. LLM same 9건은 모두 사람이 봐도 맞는 판정이다.
- encyc는 후보를 하나도 만들지 못했다. 근거로 쓰인 결과는 webkr 45, blog 36, cafearticle 27이다.
- 첫 실행에서 LLM 오판 3건(병입사 없는 alias, 브랜드 없는 alias, 잡음 섞인 alias를 same)을 보고 프롬프트를 고쳤다. **스모크 수치는 고친 규칙에 유리하므로 일반화 성능으로 보지 않는다.**

## 5. P18: 출처 스키마 제안

현재 DB(`backend/app/models`)에는 별칭 출처 컬럼이 없다. 출처(`sources`: `standard`, `menu:<bar>`)는 seed JSON(`catalog_v1_draft.json`)에만 있다. 매칭 쪽은 이미 `extracted_items.selected_match_method`(`alias`/`embedding`/`llm`/`manual`), `match_confidence`, `resolution_candidates.evidence`(JSON)가 있다.

| 대상 | 제안 | 값 |
| --- | --- | --- |
| `products` | `sources` (text[]) | `standard`(수동 표준 목록), `menu:<bar>`(메뉴에서 처음 등록), `naver:<endpoint>`(Naver 후보로 등록) |
| | `first_seen_bar_id`, `first_seen_at` | 처음 나온 바와 날짜. 메뉴 등록이면 `created_from_extracted_item_id`에서 채움 |
| | `reviewed_by` (user id), `reviewed_at` | 등록을 승인한 사람 (P36). 사람 검토 없이는 null |
| `product_aliases` | `sources` (text[]) | seed의 `sources`를 그대로 옮기고 `naver:<endpoint>` 추가 |
| | `reviewed_by`, `reviewed_at` | 별칭 등록 승인자 |
| 새 표 `alias_evidence` | `alias_id`, `endpoint`, `query`, `url`, `fetched_at`, `title_raw` | Naver 근거. 한 별칭에 여러 행 |
| `extracted_items` (LLM이 만든 연결) | 기존 `selected_match_method = llm`, `match_confidence` + 새 `match_model`, `match_prompt_version` | 예: `gemini-3.5-flash-lite`, `judge_prompt_v1` |
| `resolution_candidates.evidence` | 기존 JSON에 `{"llm": {verdict, confidence, reason, model, prompt_version}}` | 후보별 LLM 판정 기록 |

**`catalog_v1_draft` 이전 방법 (실행하지 않음, 해울과 협의):**
1. 상품 `sources` = 그 상품 별칭 `sources`의 합집합. 111개 상품은 수동 구축이라 `standard`를 넣고, 메뉴에서 나온 별칭이 있으면 `menu:<bar>`도 넣는다.
2. `first_seen`: 메뉴 출처가 있으면 가장 먼저 라벨링한 바(위스키복춘·서로상), 날짜는 seed 작성일 2026-10-05. 없으면 null.
3. `reviewed_by`: seed는 진우가 직접 확인했으므로 진우 계정, `reviewed_at` = 2026-10-05.
4. 별칭 `sources`는 seed 값 그대로. seed에 없는 `naver:*`는 P36 검토를 통과한 것만 추가.
5. alembic 마이그레이션 1개(컬럼 추가 + 새 표), seed 로더가 `sources`를 읽게 수정. **이번 작업에서는 DB 마이그레이션을 하지 않았다.**

## 6. P18: 위험과 대응 규칙

| # | 위험 | 지금 근거 | 대응 규칙 |
| --- | --- | --- | --- |
| a | **중복 등록**: 이미 있는 상품을 새로 만듦 | P22 test C1에서 상품이 DB에 있는데 메뉴 표기를 못 찾은 **168줄** (`2026-10-13_match_summary`) | 등록 전에 매처(S1+S2b+S3)를 영문명·한글명 둘 다로 돌려 후보가 있으면 경고하고, 검토자가 "이 상품이 아님"을 고른 뒤에만 등록 |
| b | **잘못된 별칭**: Naver 결과의 다른 상품명이 별칭으로 들어감 | 스모크 후보 40개 중 매처 `other_product` **2개(5%)**, LLM `different` **22개(55%)**. 다른 상품을 가리키는 후보가 섞이는 것은 흔하다 | `other_product` 태그 후보는 LLM 판정과 상관없이 별칭으로 넣지 않음. LLM `same`도 등록은 사람 검토(P36) |
| c | **독립병입 ↔ 정규품 혼동** | 스모크에서 병입사 이름이 빠진 후보 2개(`bottler_missing`), 최종 판정은 둘 다 different. 단, 프롬프트 수정 전에는 "부나하벤 10 년"을 same 0.95로 판정 | 독립병입 상품의 후보에 병입사 이름이 없으면(`bottler_missing`) 규칙으로 제외. LLM 판정에 맡기지 않음 |
| d | **리뉴얼·단종명** (글렌모렌지) | P22 C0에서 카탈로그에 있는데 못 찾은 9줄 중 6줄. 스모크에서 연수가 다른 후보 4개(+ 연수 단위 없는 "부나하벤 11") 모두 LLM different | 연수가 다른 후보는 같은 상품으로 자동 연결하지 않음. 리뉴얼 별칭은 사람이 상품을 지정해 추가(`POST_TEST_ALIASES` 방식) |
| e | **LLM 오판** (자동 확정 경로의 false merge) | 스모크 첫 실행 오판 3건 / same 7건 | 기준 0.02 이하. P28 표본 40개로는 증명할 수 없다: 0건이어도 95% 상한이 약 7.5%(3/40; 정확한 값 7.2%)다. 0.02를 보이려면 오판 0건 기준 약 150건이 필요하므로, **메뉴 줄 단위의 leave-one-bar-out(dev 바 3곳)과 새 held-out 바 test로 잰다** |

### 지금 데이터로 계산한 수치

계산: `catalog_v1_draft.json`, `match_gold_v1.json`. 독립병입 판정은 2절 목록. P28 표본은 개수에만 포함하고 예시에서는 뺐다.

| 수치 | 값 |
| --- | --- |
| 서로 다른 상품이 같은 정규화 별칭을 공유하는 건수 (카탈로그 상품 111개, 정규화 별칭 465개) | **0** |
| 위 + new 상품 337개의 영문 표준명 별칭 | **0** |
| 서로 다른 브랜드가 같은 정규화 브랜드 별칭을 공유하는 건수 | **0** |
| 독립병입 new 상품 | 42 |
| 그중 에디션에서 증류소 브랜드를 식별 | 16 (나머지 26은 블렌디드 몰트·지역명·카탈로그에 없는 증류소) |
| 그중 같은 증류소의 정규품이 카탈로그·gold에 있음 | **16** |
| 그중 증류소와 연수까지 정규품과 겹침 | **2** (1개는 P28 표본. 표본 밖 예: Highland Laird Caol Ila 12 ↔ Caol Ila 12) |

- 별칭 공유 0건은 지금 카탈로그가 사람이 만든 것이라서다. Naver 후보를 별칭으로 넣기 시작하면 공유 별칭이 생길 수 있다. 스모크의 "와일드터키 101"은 매처가 101 8 Year와 101 Rye 둘 다 후보로 낸 표기라, 한쪽 별칭으로 넣으면 다른 쪽 메뉴 줄이 잘못 붙는다. 같은 표기가 두 상품에 들어가면 `product_aliases`는 전역 unique가 아니므로 매처가 ambiguous로 처리한다.
- 증류소·연수가 겹치는 독립병입은 메뉴에 병입사 이름이 빠지면 매처 S2(브랜드 + 연수)가 정규품으로 확정할 수 있는 경우다. (c) 규칙과 업주 검토 UI의 "병입사 이름이 있는데 후보가 정규품뿐이면 경고"(P22 제안 4)로 막는다.

## 7. 다음 단계

- **P28 (10/15):** `naver_sample_v1` 40개로 처음 실행. 같은 코드·프롬프트(`a22bfee`)로 고정하고, 사람이 후보별 정답(same/different)을 단 뒤 LLM 판정의 정확도와 신뢰도별 오판률을 잰다.
- **P29 (10/15):** 매칭 자동 확정 임계값. (e)대로 메뉴 줄 단위 leave-one-bar-out과 새 바 test로 정한다.
- **P36:** 등록(새 상품·새 별칭) 사람 검토 화면. 이 문서의 출처 필드를 보여준다.
- 추출 개선 후보: 후보 0개 상품(한글 병입사명 사전), 학습 앵커 잡음("셰리").
