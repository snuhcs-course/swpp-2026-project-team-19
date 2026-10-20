# BottleMap DB seed 데이터 v1

2026-10-05 · 박진우 (AI 담당) · 기준 스키마: `BottleMap_schema_draft_v2.dbml`

DBML v2의 Product Catalog, Accounts and Bars, Published Menus 테이블에 넣을 seed 데이터입니다.

## 1. 파일 목록

| 파일 | 내용 | 적재 |
|---|---|---|
| `catalog_v1_draft.json` | 브랜드 57, 브랜드 별칭 151, 상품 111, 상품 별칭 592 | O |
| `bars_v1.json` | 바 2곳 (위스키복춘, 서로상) | O |
| `menu_seed_seorosang_v1.json` | 서로상 게시 메뉴: 항목 35, 판매 옵션 70 | 선택 (10/6 회의에서 결정) |
| `labels_v1_1.json` | 평가셋 정답지 (AI 평가용) | X |

`menu_seed_seorosang_v1.json`은 데모에서 검색이 AI 상태와 상관없이 동작하게 하는 용도입니다. 위스키복춘은 라이브 등록 시연용으로 게시 메뉴를 비워두었습니다.

## 2. 테이블 매핑

### catalog_v1_draft.json

| JSON 경로 | 테이블 | 컬럼 매핑 |
|---|---|---|
| `brands[]` | `brands` | `id`, `canonical_name` |
| `brands[].aliases[]` | `brand_aliases` | `id`, `brand_id` = 상위 `brands[].id`, `alias_text`, `language_code` |
| `products[]` | `products` | `id`, `brand_id`, `category`, `display_name`, `age_years`, `edition_name`, `abv` |
| `products[].aliases[]` | `product_aliases` | `id`, `product_id` = 상위 `products[].id`, `alias_text`, `language_code`, `is_searchable` |

`products.is_active`는 전부 true, `created_from_extracted_item_id`는 전부 null입니다 (수동 등록 상품).

### bars_v1.json

| JSON 경로 | 테이블 | 컬럼 매핑 |
|---|---|---|
| `bars[]` | `bars` | `id`, `name`, `address`, `latitude`, `longitude`, `phone`, `status` |

### menu_seed_seorosang_v1.json

| JSON 경로 | 테이블 | 컬럼 매핑 |
|---|---|---|
| 최상위 | `menu_boards` | `id` = `menu_board_id`, `bar_id`, `last_import_id` = null, `published_at` = 적재 시각 |
| `entries[]` | `bar_menu_items` | `id` = `bar_menu_item_id`, `bar_id`, `product_id` |
| `entries[]` | `menu_board_entries` | `id` = `menu_board_entry_id`, `menu_board_id`, `bar_menu_item_id`, `display_name`, `sort_order` |
| `entries[].options[]` | `menu_entry_options` | `id`, `menu_board_entry_id` = 상위 항목, `option_label`, `pour_ml`, `price_krw`, `sort_order` |

`menu_entry_options.source_extracted_option_id`는 null입니다 (AI 추출이 아닌 수동 입력).

## 3. 적재 시 꼭 확인할 것

**id는 이미 채워져 있습니다.** 모든 id는 UUIDv5이고 FK도 연결되어 있어서 그대로 넣으면 됩니다. 스크립트로 다시 생성해도 같은 값이 나옵니다.

**`normalized_alias`는 비어 있습니다.** 매칭 플로우 7장대로 백엔드 공통 정규화 함수로 채워 주세요. 정규화 규칙은 7장 그대로 구현하면 되고, 표기 변형은 전부 별칭으로 넣었습니다.

**같은 상품 안에서 정규화 결과가 겹치는 별칭은 건너뛰어 주세요.** 원문이 다른 표기 변형을 여러 개 넣었기 때문에, 정규화하면 같아지는 경우가 있습니다.

| 상품 | alias_text | 정규화 결과 |
|---|---|---|
| GlenDronach 12 | `글렌드로낙 12년` | `글렌드로낙12` |
| GlenDronach 12 | `글렌드로낙 12Y` | `글렌드로낙12` |

`(product_id, normalized_alias)`가 unique라서 두 번째 insert가 실패합니다. 처음 것만 넣고 나머지는 건너뛰면 됩니다 (예: `ON CONFLICT DO NOTHING`). 매칭은 `normalized_alias`만 비교하므로 하나만 있어도 결과는 같습니다. 대략 상품 쪽 127건, 브랜드 쪽 14건이 해당합니다.

서로 다른 상품끼리 겹치는 별칭은 없는 것을 확인했습니다 (매칭 플로우 7장 규칙으로 임시 구현해서 검사).

**`created_at`, `updated_at`은 적재 시각으로 채워 주세요.**

## 4. 적재하지 않는 필드

| 필드 | 위치 | 용도 |
|---|---|---|
| `key`, `brand_key`, `product_key`, `bar_key` | 전체 | 사람이 읽기 위한 식별자. id 생성 재료 |
| `sources` | 별칭 | 별칭 출처 태그. AI 평가 스크립트 전용 |
| `kakao_place_id` | 바 | 카카오맵 장소 ID. 카카오맵 연동 때 컬럼 추가 여부 결정 |
| `label_bar_name` | 바 | 평가셋 라벨과 연결용 |
| `excluded_non_whisky`, `notes`, `version` 등 | 최상위 | 문서용 메타데이터 |

## 5. 값이 비어 있는 이유

**`abv` (도수): 전부 null.** 메뉴판에 도수가 없고, 매칭·검색에 쓰이지 않습니다. 배치마다 도수가 다른 제품도 있어서 추측으로 채우지 않았습니다. 상세 화면에 도수를 보여주기로 하면 출처를 달아 채우겠습니다.

**`pour_ml` (잔 용량): 전부 null.** 메뉴판에 용량이 없고, 스키마 가이드 7.4의 "메뉴에 용량이 없으면 null" 규칙을 따랐습니다. AI 추출도 보이지 않는 값은 null로 주기 때문에, seed에만 값을 넣으면 바마다 표시가 달라집니다. 서로상의 기본 잔 용량이 확인되면 채우겠습니다. 잔과 병은 `option_label`(`잔`, `병`)로 구분됩니다.

## 6. 데이터 기준 (참고)

- **상품 범위:** 지금까지 확인한 위스키 전부. 평가셋 두 바에서 84개, 온라인 메뉴판에서 27개입니다. 코냑 등 위스키가 아닌 술은 넣지 않았습니다.
- **독립 병입:** 병입사를 브랜드로 둡니다. 예: `Signatory Vintage Macduff 13`의 브랜드는 Signatory Vintage이고, 증류소(Macduff)는 `edition_name`에 있습니다.
- **연수:** 공식 연수가 있고 바뀐 이력이 없으면 `age_years`에 넣었습니다. 예: Glenmorangie The Original = 10.
- **브랜드명:** 메뉴와 검색에 실제로 쓰이는 이름을 브랜드로 둡니다. 예: Octomore, Port Charlotte, Yoichi는 각각 별도 브랜드입니다.
- **별칭 출처:** 기준 표기, 실제 메뉴판 표기(두 바, 온라인 메뉴판), 패턴 생성 표기(예: `GlenDronach Aged 12 Years`), 외부 데이터(Wikidata, 식약처)입니다.
- **id:** UUIDv5이고 `key`를 재료로 만듭니다. 표시명을 고쳐도 id는 유지됩니다.
- **검색 제외 별칭:** 메뉴판 오타(`Jonnie walker black`, `Jonnie walker blue`)는 `is_searchable = false`입니다. 메뉴 매칭에는 쓰이지만 고객 검색 자동완성에는 나오지 않습니다.

---

# 카탈로그 v2 (2026-10-14, A3)

v1 위에 평가 정답의 새 상품과 메뉴판 표기를 더한 판입니다. 형식과 테이블 매핑(2장)은 v1과 같습니다.

## 7. v2 파일

| 파일 | 내용 | 적재 |
|---|---|---|
| `catalog_v2_service.json` | 전체. 브랜드 148, 브랜드 별칭 242, 상품 529, 상품 별칭 1767 | O (백엔드 적재 요청용) |
| `catalog_v2_eval_5bars.json` | P47 평가용. 상품은 전부, `menu:수이`·`menu:오드비`만 출처인 별칭 254개 제외 (상품 529, 별칭 1513) | X |
| `catalog_v2_eval_5bars_drop_products.json` | 새 상품 판정 테스트용 (`--drop-products`). 수이·오드비에서만 나온 상품 82개와 그 브랜드 18개까지 제외 (상품 447, 별칭 1431) | X |
| `catalog_v2_draft.json` | 위 스냅샷의 원본 | X |
| `bars_v2.json` | 바 7곳 (v1 2곳 + 미라보, 벡(Beck), 포레스트, 오드비, 수이) | O |

main에는 적재 대상인 `catalog_v2_service.json`과 `bars_v2.json`만 있습니다. 적재하지 않는 파일(`catalog_v2_draft.json`, 평가 스냅샷 두 개)과 생성·검사 스크립트는 AI 브랜치 `i2-catalog-v2`에 있습니다. 만드는 순서: `python ai/catalog/build_catalog_v2.py` → `python ai/catalog/export_snapshot.py --drop-products` → `python ai/catalog/check_catalog_v2.py <파일...>`.

## 8. v2에서 추가된 것

| 단계 | 새 브랜드 | 새 상품 | 새 상품 별칭 | 기존 별칭에 출처만 추가 |
|---|---|---|---|---|
| 1. 핵심: `eval/match_gold_v1_1.json` new_products, 미라보·Beck·포레스트 메뉴 표기, `POST_TEST_ALIASES` | 73 | 336 | 336 (표준명) + 495 (메뉴) + 8 (POST_TEST) | 72 |
| 3. 수이·오드비: `eval/match_gold_final_v1.json` (박진우 검수 후) | 18 | 82 | 82 (표준명) + 254 (메뉴) | 31 |

- **새 상품 별칭:** 표준 영문명(`standard`), 그리고 그 상품으로 연결된 메뉴판 인쇄 표기(`menu:<바>`)입니다. 기존 v1 상품에도 그 바의 메뉴 표기를 별칭으로 넣었습니다. 확인된 표기는 모두 별칭으로 넣어 별칭 단계에서 최대한 걸러내는 것이 목표입니다(정답 검수에서 "추정"으로 연결한 줄 포함).
- **표기 규칙:** `한글 / 영문` 줄은 부분마다 별칭 하나, 괄호 병기(`Ardbeg 10y (아드벡)`, `글렌모렌지(Glenmorangie) 12년 오리지널`)는 인쇄 그대로 한 별칭입니다. 오드비 행사 줄의 꼬리표 ` / 행사`는 별칭에 넣지 않았습니다. `unknown`·`non_whisky`·`both:` 줄은 별칭을 만들지 않습니다.
- **제외:** `jack-daniels-apple`(Tennessee Apple, 위스키 리큐어)는 비위스키라 넣지 않았습니다(`excluded_non_whisky`).
- **id:** v1과 같은 UUIDv5 네임스페이스 `6b1a1f4e-19b0-4c7a-9a7e-b0771e3a0019`. 재료는 `brand:<key>`, `balias:<브랜드 key>:<표기>`, `product:<key>`, `palias:<상품 key>:<표기>`, `bar:<key>`입니다.

## 9. 적재하지 않는 필드 (v2 추가)

| 필드 | 위치 | 용도 |
|---|---|---|
| `sources` | 상품 | 그 상품이 메뉴에 있는 바(`menu:<바>`). AI 평가 스크립트 전용 |
| `first_seen` | 상품 | 그 상품을 처음 본 바 (라벨링 순서 기준). AI 평가 스크립트 전용 |

4장의 필드(별칭 `sources`, `key` 등)도 그대로 적재하지 않습니다. **적재기는 상품의 `sources`, `first_seen`을 무시하면 됩니다.**

## 10. v2 검증 결과 (`check_catalog_v2.py`, 백엔드 `app.core.normalize` 사용)

| 검사 | service | eval_5bars | eval_5bars_drop_products |
|---|---|---|---|
| 서로 다른 상품이 같은 정규화 별칭 | **0** | 0 | 0 |
| 서로 다른 브랜드가 같은 정규화 별칭 | 0 | 0 | 0 |
| 같은 상품 안의 정규화 중복 (적재 시 skip) | 210 | 159 | 159 |
| 같은 브랜드 안의 정규화 중복 (적재 시 skip) | 14 | 14 | 14 |
| FK 무결성, id 유일성 | OK | OK | OK |
| key로 id 재생성 시 동일 | OK | OK | OK |

같은 상품 안의 정규화 중복은 v1과 같이 `ON CONFLICT DO NOTHING`으로 건너뛰면 됩니다(3장). 검사기를 v1에 돌리면 3장의 수치(상품 127, 브랜드 14, 충돌 0)가 그대로 나옵니다.

**출처별 상품 별칭 수 (service):** standard 684, template 167, menu:미라보 414, menu:수이 151, menu:오드비 134, menu:P5온라인 88, menu:위스키복춘 76, menu:서로상 70, menu:포레스트 68, menu:Beck 61, mfds 1. 브랜드 별칭은 standard 238, wikidata 5.

**바별 상품 수 (그 바 메뉴에 있는 상품, service):** 미라보 406, 수이 136, 오드비 134, 위스키복춘 76, 포레스트 68, Beck 63, P5온라인 53, 서로상 35.

## 11. bars_v2.json

카카오맵 장소 검색과 장소 패널에서 2026-10-14에 확인했습니다. `name`은 카카오맵 장소명, `label_bar_name`은 평가 라벨의 바 이름입니다.

| key | name | 확인 근거 | 비어 있는 칸 |
|---|---|---|---|
| mirabeau | 미라보 | 후보 2곳 중 블로그 후기가 위스키 바(위스키 테이스팅 코스)인 봉천로 541 | 없음 |
| beck | 벡 | 장소 블로그 제목이 "Beck" | 없음 |
| forest | 포레스트 | 관악구가 아니라 하남시 미사. 팀이 알려준 주소(2026-10-15)와 카카오 장소 1200932955(칵테일바)의 도로명 주소가 같고, 블로그 후기에 위스키 바로 나옴 (2026-10-15 확인) | 없음 |
| odbi | 오드비 | 블로그 "샤로수길 위스키바 오드비" | 없음 (전화는 카카오맵 미등록이라 팀이 알려준 0507 가상번호, 2026-10-15) |
| sui | 수이 | 카카오 메뉴(하몽을 곁들인 감자튀김, 교자, 안키모와 바게트)가 사진 010_sui_05의 Dish Menu와 같음 | 전화 null (TODO, 카카오맵 미등록) |

## 생성 별칭 (2026-10-15)

`catalog_v2_service.json`에 출처 `generated:claude-2026-10-15`인 별칭을 더했다: 브랜드 한국어 표기 216개, 상품 한국어 별칭 940개(상품 472개). Claude가 웹 검색 없이 만들고, 자동 검사(다른 상품·브랜드 별칭과 정규화 충돌, 상품에 없는 숫자, 연수 누락, 독립병입 병입사 누락, 에디션 없이 브랜드+연수만 있는 표기)를 통과한 것을 박진우가 검토했다. `check_catalog_v2.py`: 상품 간·브랜드 간 충돌 0, integrity OK. 평가용 스냅샷(`catalog_v2_eval_5bars.json`, P47)에는 넣지 않았다. 되돌릴 별칭 id 목록은 이 PR 설명에 첨부.

적재: `cd backend && uv run --no-sync --env-file .env python scripts/seed_catalog.py --catalog ../ai/catalog/catalog_v2_service.json --bars ../ai/catalog/bars_v2.json` (추가만 하고 기존 행은 지우지 않음).

괄호 제거 별칭(출처 `template:paren-strip`) 265개: 메뉴 별칭의 괄호 부분을 뺀 형태(예: '쿨일라(Caol Ila) 12년' → '쿨일라 12년'). 고객 검색은 메뉴 매칭 S1과 달리 괄호를 처리하지 않아서 넣음. 연수·에디션이 빠지거나 다른 상품과 겹치면 제외. 검사 규칙 오류로 빠졌던 생성 별칭 19개(숫자 에디션 등)도 복구. 오프라인 검색 측정(손님형 검색어 600개): 47% → 51%, 실제 Naver 표기 49개: 21 → 26.
