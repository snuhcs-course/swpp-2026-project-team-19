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
