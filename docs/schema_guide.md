# BottleMap 데이터베이스 스키마 설계 가이드

## 1 문서 목적

이 문서는 `schema_draft.dbml`을 팀원이 함께 검토할 수 있도록 풀어서 설명한 자료다. 각 테이블과 컬럼의 의미, 예시 값, 필요한 이유를 정리하고 사진 업로드부터 AI 추출, 사람 검수, 현재 메뉴판 게시, 평가까지 데이터가 어떻게 연결되는지 설명한다.

메뉴 등록 화면과 백엔드의 구체적인 요청·응답 계약은 [frontend_backend_api_spec.md](frontend_backend_api_spec.md)를 따른다.

현재 DBML은 PostgreSQL을 대상으로 하는 논리 설계 초안이다. PostgreSQL의 네이티브 `uuid`, `timestamptz`와 JSON 계열 타입을 사용하며, 인증 제공자는 Supabase Auth(Google)로 확정했다. ID 생성 위치는 아직 확정되지 않았다. 세부 인덱스와 CHECK 제약은 실제 DDL 작성 단계에서 확정한다.

## 2 핵심 용어

| 용어 | 의미 | 예시 |
|---|---|---|
| 브랜드 | 여러 상품이 공유하는 제조사 또는 브랜드 정체성 | Deanston |
| 상품 | 모든 업장이 공유하는 병 단위의 술 | Deanston 12 |
| 상품 별칭 | 같은 상품을 가리키는 다른 표기 | 딘스톤 12, Deanston 12YO |
| 업장 메뉴 항목 | 특정 업장이 해당 상품을 취급한 기록 | A바가 Deanston 12를 취급함 |
| 메뉴판 | 한 업장에서 현재 고객에게 보여주는 업장 메뉴 항목의 묶음 | A바 현재 위스키 메뉴판 |
| 메뉴판 구성 | 메뉴판에 어떤 업장 메뉴 항목이 들어가는지 나타내는 연결 | 현재 메뉴판에 Deanston 12 포함 |
| 판매 옵션 | 같은 술의 용량과 가격 조합 | 15ml 8,000원, 30ml 15,000원 |
| 메뉴 등록 작업 | 운영자 또는 업주가 한 번에 올린 메뉴 사진 묶음과 처리 과정 | 사진 3장을 전체 교체 모드로 업로드 |
| 추출 항목 | AI가 인식한 상품 또는 비상품 블록 | 딘스톤 12년, 싱글 몰트 제목 |
| 추출 옵션 | 추출 상품 항목에 속한 가격·용량 조합 | 15ml 8,000원, 30ml 15,000원 |
| 평가 세트 | 성능 측정에 사용할 고정된 이미지 묶음 | Iteration 1 Held-out Set |
| 업주 | 운영자 승인을 받아 특정 업장을 관리하는 사용자. 사용자 유형이 아니라 사용자와 업장의 관계다 | 관악 위스키 바의 사장 |
| 업주 신청 | 사용자가 기존 업장 또는 새 업장의 업주가 되겠다고 낸 요청 | 사업자등록번호, 대표자명, 개업일자와 연락처를 적어 관악 위스키 바 업주 신청 |

## 3 전체 데이터 흐름

### 3.1 메뉴 등록과 게시

1. 운영자 또는 해당 업장의 업주가 `menu_imports`를 생성하고 전체 교체 또는 일부 수정 모드를 선택한다.
2. 한 번의 등록 작업에 여러 `menu_images`를 추가한다.
3. 구현 전에 선택한 하나의 추출 방식으로 각 이미지마다 `extraction_runs`를 정확히 하나 실행한다.
4. AI가 인식한 상품·비상품 블록을 `extracted_items`에 저장하고 각 상품의 가격·용량 선택지를 `extracted_options`에 저장한다.
5. `extracted_line_type = product`인 항목은 정확한 상품 별칭이 하나만 일치할 때 단일 후보로 처리한다. 최초 매칭 결과는 `initial_resolution_status`에 고정하고, 후보는 `resolution_candidates`에 저장한다. 그 외 경로에서 후보가 2개 이상이면 점수 차이와 관계없이 LLM으로 재정렬한다.
6. 백엔드가 상위 상품 후보를 임시 선택해 현재 메뉴판과의 변경 초안을 `menu_import_changes`에 저장한다.
7. 운영자 또는 업주가 한 화면에서 항목 역할, 상품명, 가격·용량 옵션, 상품 연결, 신규 카탈로그 제안, 메뉴 변경 초안을 통합 검수한다. 신규 상품은 기존 `brand_id`를 선택하거나 신규 브랜드의 대표 이름과 별칭을 직접 확정해야 한다.
8. 최종 제출 시 백엔드가 모든 결정을 재검증하고 diff를 다시 계산한 뒤 `bar_menu_items`, `menu_board_entries`, `menu_entry_options`에 원자적으로 반영한다.
9. 미완료 등록 작업이 없을 때 운영자나 업주는 사진 없이 현재 메뉴판의 항목 하나를 추가, 수정, 삭제하거나 메뉴판을 비울 수 있다(API 명세 3.14). 이 직접 편집은 `menu_imports`를 만들지 않고 `menu_boards.version`을 확인한 뒤 올린다. 직접 추가에서 카탈로그에 없는 상품은 같은 트랜잭션에서 `brands`, `products`, 별칭으로 만든다.

### 3.2 고객 검색

1. 고객의 검색어를 메뉴 매칭과 같은 정규화 함수로 정규화한다.
2. `brand_aliases.normalized_alias` 정확 일치(해당 브랜드의 활성 상품 전체), `product_aliases.normalized_alias` 정확 일치, 상품 별칭 부분 일치 순서로 상품을 찾고 활성 상품이 나온 첫 단계에서 멈춘다. 브랜드 별칭과 정확히 같은 검색어는 상품 별칭과도 같더라도 브랜드 결과가 된다. 그래서 브랜드 이름은 어떤 표기로 검색해도 같은 상품 집합을 낸다. 이때 검색어와 같은 별칭을 가진 상품(다른 브랜드 상품 포함)을 결과 앞에 둔다. 검색 시점에는 임베딩과 LLM을 사용하지 않는다.
3. 매칭된 모든 상품의 `bar_menu_items`를 찾는다.
4. 활성 업장의 현재 `menu_board_entries`에 연결된 업장 메뉴 항목만 노출한다.
5. `menu_entry_options`에서 가격과 용량을, `menu_boards.published_at`에서 메뉴 갱신일을 가져온다.
6. `bars`의 좌표로 고객 위치와의 거리를 계산한다. 고객 위치는 현재 스키마에 저장하지 않는다.

구체적인 요청·응답 형식은 API 명세의 `GET /api/search/bars`를 따른다.

### 3.3 AI 평가

1. 평가할 이미지 묶음을 `eval_sets`로 정의한다.
2. 각 이미지의 세트 소속을 `eval_samples`에 기록한다.
3. 사람이 만든 상품 정답을 `eval_ground_truth_items`에, 가격·용량 정답을 `eval_ground_truth_options`에 저장한다.
4. 구현 전에 선택한 추출 방식으로 각 이미지의 `extraction_runs`를 실행한다.
5. 정답과 실행 결과를 비교해 이름 F1, 가격 정확도, Top-1 정확도, false-merge 비율을 계산한다. 특히 `initial_resolution_status = exact_match`였지만 정답 상품과 다른 경우를 확실하다고 판단한 잘못된 병합으로 집계할 수 있고, 후보의 `evidence.rule`로 규칙별(`alias`, `S1`, `S2`, `S2b`, `S3`) 잘못된 병합 비율을 나눠 볼 수 있다. OCR+LLM과 Vision LLM 중 어떤 방식을 사용할지는 구현 전 별도 실험으로 결정한다.

### 3.4 업주 등록과 승인

1. 로그인한 사용자가 업주 신청을 낸다. 기존 업장이면 `bar_id`를, 새 업장이면 업장명·주소·전화번호를 적고, 사업자등록번호, 대표자명, 개업일자와 연락처를 함께 적는다. 사업자등록증 사진을 올리면 OCR로 읽은 값이 입력란에 미리 채워진다. 사진은 저장하지 않는다.
2. 백엔드가 국세청 사업자등록정보 진위확인 API로 사업자등록번호, 대표자명, 개업일자를 1차 검증한다. 맞지 않으면 행을 만들지 않고 신청자가 입력을 고친다. 맞으면 `business_verification_result = matched`와 사업자 상태를, 검증 서비스에 연결하지 못하면 `unavailable`을 저장하고 `bar_owner_applications`에 `pending`으로 저장한다.
3. 신청자가 메뉴판 사진을 올린다. 사진은 객체 저장소에, 위치는 `bar_owner_application_menu_images`에 저장한다. `pending`인 동안 다시 올리면 전체를 교체한다.
4. 운영자가 웹 대시보드에서 대기 중인 신청과 검증 결과, 메뉴판 사진을 보고 실제 매장이 있는지 확인한다. `unavailable`이면 다시 검증한다.
5. 승인하면 같은 트랜잭션에서 다음을 처리한다.
   - 기존 업장: 현재 업주가 없는지 다시 확인하고 `bar_owners` 행을 만든다.
   - 새 업장: 운영자가 확인한 업장 정보(좌표 포함)로 `bars` 행을 만들고, 신청의 `bar_id`에 저장한 뒤 `bar_owners` 행을 만든다.
   - 신청 메뉴판 사진이 있고 업장에 미완료 메뉴 등록 작업이 없으면, 그 사진으로 `menu_imports`와 `menu_images`를 만든다(8.1). 커밋한 뒤 AI 처리를 시작하므로 업주가 처음 들어왔을 때 검수가 준비되어 있다.
6. 거절하면 사유를 `rejection_reason`에 남긴다. 신청자는 대기 중인 신청을 직접 취소할 수 있다. 거절되거나 취소되면 신청 메뉴판 사진의 행과 파일을 삭제한다. 거절되거나 취소된 사용자는 새 신청을 낼 수 있다.
7. 승인된 업주는 자기 업장의 정보 수정과 메뉴 등록·검수·반영을 할 수 있다. 권한은 매 요청 `bar_owners`에서 확인하므로 승인이나 해제가 다음 요청부터 반영된다.
8. 운영자는 업주 관계를 해제할 수 있다. 행을 지우지 않고 `revoked_at`을 기록한다.

구체적인 요청·응답 형식은 API 명세의 업주 신청과 승인 절을 따른다.

## 4 Enum 설명

### 4.1 user_type

| 값 | 의미 | 필요한 이유 |
|---|---|---|
| `customer` | 선택적으로 로그인한 일반 고객 | 고객용 추가 기능을 제공할 계정을 나타낸다. 처음 로그인해 생성되는 계정은 모두 이 유형이다. 익명 고객은 `users` 행이 없다. |
| `operator` | 업장 상품 메뉴판을 관리하는 프로젝트 운영자 | 메뉴 등록과 검수 권한을 일반 고객 계정과 분리한다. 운영자도 공개 고객 기능은 이용할 수 있다. |

한 계정은 하나의 전역 사용자 유형만 가진다. 업주는 전역 사용자 유형이 아니라 특정 업장과 사용자의 관계이므로 `bar_owners`로 표현한다(5.4). 업주가 되어도 `user_type`은 바뀌지 않는다.

### 4.2 bar_status

| 값 | 의미 | 필요한 이유 |
|---|---|---|
| `active` | 검색과 서비스에 사용할 수 있는 업장 | 현재 운영 중인 업장만 노출할 수 있다. |
| `inactive` | 폐업 중단 또는 임시 비활성 업장 | 업장 데이터를 삭제하지 않고 검색에서 제외한다. |

### 4.3 import_status

| 값 | 의미 |
|---|---|
| `uploaded` | 사진 업로드가 완료된 초기 상태 |
| `processing` | AI 파이프라인이 실행 중인 상태 |
| `ready_for_review` | 자동 추출·후보 매칭·임시 diff 생성이 끝나 통합 검수를 할 수 있는 상태 |
| `applied` | 운영자가 확정한 변경이 현재 메뉴판에 반영된 상태 |
| `failed` | 업로드 또는 AI 처리에 실패한 상태 |
| `canceled` | 운영자나 업주가 미완료 작업을 반영하지 않고 취소한 상태. 메뉴판과 카탈로그는 바뀌지 않는다 |

이 상태값은 비동기 AI 처리와 사람 검수가 어디까지 진행됐는지 추적하고 중복 적용을 방지한다. 검수 확정과 메뉴판 반영은 같은 트랜잭션에서 일어나므로 성공하면 `ready_for_review`에서 `applied`로 바로 바뀌고, 실패하면 전체가 롤백되어 `ready_for_review`를 유지한다.

`uploaded`, `processing`, `ready_for_review`는 미완료 상태이고 `applied`, `failed`, `canceled`는 최종 상태다. 미완료 작업은 취소할 수 있으며, 취소하면 업장에 미완료 작업이 없어져 새로 업로드할 수 있다. 처리 중에 취소된 작업의 백그라운드 처리 결과는 저장하지 않는다.

### 4.4 import_mode

| 값 | 의미 | 기존 메뉴에 미치는 영향 |
|---|---|---|
| `full_replace` | 현재 메뉴 전체를 새 사진 결과로 교체 | 새 결과에 없는 기존 항목도 제거 후보 diff로 만든다. |
| `partial_update` | 일부 항목만 추가하거나 수정 | 사진에 나오지 않은 기존 항목은 그대로 유지한다. |

### 4.5 pipeline_status

| 값 | 의미 |
|---|---|
| `queued` | 실행 대기 |
| `running` | 실행 중 |
| `succeeded` | 정상 완료 |
| `failed` | 실행 실패 |

### 4.6 extraction_approach

| 값 | 의미 | 예시 |
|---|---|---|
| `ocr_llm` | OCR 결과를 LLM으로 구조화 | Naver Clova OCR + LLM parser |
| `vision_llm` | 이미지에서 Vision LLM이 직접 구조화 | Vision model JSON output |

### 4.7 extracted_line_type

| 값 | 의미 | 상품 매칭 여부 |
|---|---|---|
| `product` | 상품명과 가격·용량 등의 판매 정보를 담은 행 | 상품 후보 생성과 운영자 매칭 검수 대상으로 사용한다. |
| `section_header` | 위스키 종류나 메뉴 구역을 나타내는 제목 행 | 상품 매칭에서 제외한다. |
| `description` | 상품 또는 메뉴 구역에 대한 설명 행 | 상품 매칭에서 제외한다. |
| `unknown` | AI가 역할을 확정하지 못한 행 | 운영자가 역할을 확인하기 전까지 상품 매칭에서 제외한다. |

AI가 반환한 최초 분류는 `extracted_items.extracted_line_type`에 변경 없이 보존한다. 운영자가 다른 역할로 교정하면 `corrected_line_type`에 새 값을 저장한다. 실제 처리에 사용하는 유효 역할은 `COALESCE(corrected_line_type, extracted_line_type)`이다.

### 4.8 resolution_status

| 값 | 의미 |
|---|---|
| `exact_match` | 매칭 규칙이 충돌 없이 정확히 하나의 상품을 확정했다. 규칙은 상품 별칭 정확 일치와 단계 규칙 S1(이름 변형), S2(브랜드+연수·에디션), S2b(기본 상품), S3(숫자가 있는 이름의 1글자 오타)이며, 어느 규칙이 찾았는지는 후보의 `evidence.rule`(`alias`, `S1`, `S2`, `S2b`, `S3`)에 남는다. |
| `ambiguous` | 기존 상품 후보는 있지만 규칙이 하나로 확정하지 못해 운영자 판단이 필요하다. 후보가 하나뿐이어도 확인 권장(`confirmRecommended`)이면 이 상태다. |
| `unmatched` | 상품 매칭을 실행했지만 유효한 기존 상품 후보가 남지 않았다. |

`extracted_items.initial_resolution_status`는 최초 후보 생성이 끝날 때 한 번 저장하고 운영자 검수로 변경하지 않는다. 최초 AI 분류가 비상품이어서 상품 매칭을 실행하지 않은 항목은 `null`이다. 이를 통해 운영자가 상품을 선택하거나 새로 등록한 뒤에도 시스템의 원래 판단을 평가할 수 있다.

### 4.9 review_status

| 값 | 의미 |
|---|---|
| `pending` | 아직 사람이 확인하지 않음 |
| `confirmed` | AI가 추출한 역할과 값을 그대로 승인 |
| `corrected` | 사람이 항목 역할, 이름, 가격, 용량 등을 수정 |
| `rejected` | OCR 잡음이나 중복처럼 사용할 수 없는 인식 행을 제외 |

### 4.10 match_method

| 값 | 의미 |
|---|---|
| `alias` | 정규화된 별칭의 정확 일치가 최종 순위를 결정 |
| `embedding` | 정확 일치 없이 문자열·속성·다국어 임베딩 점수가 최종 순위를 결정 |
| `llm` | 애매한 복수 후보를 LLM이 재정렬해 최종 순위를 결정 |
| `manual` | 운영자가 직접 상품을 선택하거나 등록 |

하나의 상품은 별칭, 속성, 임베딩 등 여러 경로에서 동시에 발견될 수 있다. 이때 후보 행을 경로별로 나누지 않고 `resolution_candidates.evidence`에 모든 신호를 합치며, `method`에는 최종 순위를 결정한 대표 방법 하나만 기록한다.

### 4.11 menu_change_type

| 값 | 의미 |
|---|---|
| `add` | 현재 메뉴판에 없던 항목을 추가 |
| `update` | 기존 항목의 옵션(가격·용량·옵션명)을 수정한다. 옵션이 같고 표시명만 다르면 변경으로 보지 않고 기존 표시명을 유지한다. AI가 같은 메뉴의 이름을 조금씩 다르게 읽어 불필요한 변경이 생기는 것을 막기 위해서다. `update`가 반영될 때는 표시명도 새 값으로 바뀐다. |
| `remove` | 현재 메뉴판에서 항목을 제외 |

### 4.12 menu_change_decision

| 값 | 의미 |
|---|---|
| `pending` | 운영자 결정 대기 |
| `apply` | 제안된 변경을 적용 |
| `ignore` | 제안된 변경을 무시하고 현재 상태 유지 |

### 4.13 eval_sample_kind

| 값 | 의미 |
|---|---|
| `real` | 실제 업장의 메뉴 이미지 |
| `synthetic` | 엣지 케이스 검증을 위한 합성 이미지 |

### 4.14 owner_application_type

| 값 | 의미 |
|---|---|
| `existing_bar` | 이미 `bars`에 있는 업장의 업주가 되겠다는 신청 |
| `new_bar` | 아직 `bars`에 없는 업장을 등록하면서 업주가 되겠다는 신청 |

### 4.15 owner_application_status

| 값 | 의미 |
|---|---|
| `pending` | 운영자 결정 대기 |
| `approved` | 운영자가 승인함. `bar_owners` 행이 만들어졌다 |
| `rejected` | 운영자가 거절함. `rejection_reason`을 신청자에게 보여 준다 |
| `canceled` | 신청자가 대기 중에 취소함 |

`approved`, `rejected`, `canceled`는 최종 상태이며 다시 바뀌지 않는다. 승인 뒤 업주 관계를 해제해도 신청은 `approved`로 남고, 해제는 `bar_owners.revoked_at`으로 표현한다.

### 4.16 business_verification_result

| 값 | 의미 |
|---|---|
| `matched` | 사업자등록번호, 대표자명, 개업일자가 국세청 정보와 맞음 |
| `not_matched` | 맞지 않음. 신청할 때 맞지 않으면 행을 만들지 않으므로, 운영자가 다시 검증했을 때만 저장된다 |
| `unavailable` | 검증 서비스 오류, 시간 초과, 호출 한도 초과로 확인하지 못함. 운영자가 다시 검증한다 |

### 4.17 business_status

| 값 | 의미 |
|---|---|
| `active` | 계속사업자 |
| `suspended` | 휴업자 |
| `closed` | 폐업자 |

휴업이나 폐업 사업자의 신청도 받으며, 승인 여부는 운영자가 판단한다.

### 4.18 operating_exception_kind

| 값 | 의미 |
|---|---|
| `closed_today` | 적용한 날 하루 임시 휴무 |
| `custom_hours` | 적용한 날만 영업시간 변경. `open_time`, `close_time`이 필수다 |
| `vacation` | `start_date`부터 `end_date`까지 임시 휴업 |

## 5 Accounts and Bars

### 5.1 users

**역할:** 로그인한 사용자 계정을 저장한다. 익명 고객은 이 테이블에 행을 만들지 않는다. MVP에서는 운영자가 반드시 로그인하고 고객 로그인은 선택 사항이다.

| 컬럼 | 타입과 제약 | 예시 | 설명과 필요한 이유 |
|---|---|---|---|
| `id` | `uuid`, PK | `11111111-1111-4111-8111-111111111111` | 계정 자체를 식별하는 내부 ID다. 현재 MVP의 업무 테이블은 작업 수행자의 사용자 ID를 참조하지 않는다. |
| `auth_subject` | `varchar(255)`, NOT NULL, UNIQUE | `5b0c3a2e-7d41-4c8e-9f6a-2e1d8b7c4a90` | Supabase Auth의 사용자 ID(access token의 `sub`, UUID 문자열)다. 로그인 결과를 내부 사용자와 연결하고 중복 계정을 방지한다. 로컬 개발용 임시 로그인 사용자는 `local-dev-user`다. |
| `email` | `varchar(255)`, UNIQUE, nullable | `operator@bottlemap.test` | 연락과 계정 식별에 사용할 수 있다. 로그인할 때마다 token의 Google 계정 email로 맞춘다. token에 email이 없거나 다른 계정이 이미 같은 email을 쓰면 `null`로 둔다. |
| `display_name` | `varchar(100)`, nullable | `운영자 A` | 계정 화면에서 사람이 알아볼 이름을 표시한다. 처음 로그인할 때 Google 계정 이름으로 채우고, 이후에는 사용자가 수정한 값을 유지한다. API는 최대 20자로 제한한다. |
| `user_type` | `user_type`, NOT NULL, 기본 `customer` | `operator` | 일반 고객 계정과 프로젝트 운영자 계정을 구분한다. 한 계정에는 하나의 전역 유형만 저장한다. |
| `created_at` | `timestamptz`, NOT NULL | `2026-09-28T03:00:00Z` | 계정 생성 시점을 기록한다. |
| `updated_at` | `timestamptz`, NOT NULL | `2026-09-28T04:00:00Z` | 계정 정보가 마지막으로 변경된 시점을 기록한다. |

**핵심 제약:** `auth_subject`와 `email`의 중복을 막고 `user_type`을 반드시 저장한다. PostgreSQL의 UNIQUE 제약은 NULL끼리 같다고 보지 않으므로 `email`이 `null`인 행은 여러 개 있을 수 있다. 업주 권한은 특정 업장에 종속되므로 `user_type`에 추가하지 않고 `bar_owners`로 표현한다.

### 5.2 bars

**역할:** BottleMap에서 검색되는 물리적 업장과 위치 정보를 저장한다.

| 컬럼 | 타입과 제약 | 예시 | 설명과 필요한 이유 |
|---|---|---|---|
| `id` | `uuid`, PK | `22222222-2222-4222-8222-222222222222` | 업장의 내부 식별자다. |
| `name` | `varchar(150)`, NOT NULL | `관악 위스키 바` | 검색 결과와 상세 화면에 표시할 업장명이다. |
| `address` | `varchar(500)`, NOT NULL | `서울특별시 관악구 관악로 1 2층` | 도로명 주소와 층·호수 등 상세 위치를 하나의 표시용 주소로 저장한다. |
| `latitude` | `decimal(9,6)`, NOT NULL, CHECK -90~90 | `37.478321` | WGS84 위도다. 지도 표시와 고객 위치와의 직선 거리 계산에 사용한다. |
| `longitude` | `decimal(9,6)`, NOT NULL, CHECK -180~180 | `126.951234` | WGS84 경도다. 지도 표시와 고객 위치와의 직선 거리 계산에 사용한다. |
| `phone` | `varchar(30)`, nullable | `02-1234-5678` | 업장 상세 정보로 제공할 수 있다. |
| `description` | `varchar(100)`, nullable | `싱글몰트 위주의 조용한 바` | 업장 한 줄 소개다. 업주나 운영자가 업장 수정(API 명세 3.7)으로 정하고, 앞뒤 공백을 지운 값을 저장하며 공백뿐이면 null이다. 줄바꿈을 허용하고 이스케이프 없이 받은 그대로 저장한다. 업장을 만들 때(생성, 신청 승인)는 받지 않아 null이다. 고객 업장 상세(API 명세 3.9)에 나온다. |
| `default_pour_ml` | `smallint`, nullable, CHECK 1~999 | `30` | 업주가 정한 매장 기본 잔 용량이다. 메뉴 직접 편집과 검수 화면이 잔 옵션의 용량 입력 칸을 미리 채우는 데만 쓴다. 백엔드가 게시 메뉴에 자동으로 적용하지 않으며, 바꿔도 이미 게시된 옵션은 바뀌지 않는다. |
| `tags` | `varchar(24)[]`, NOT NULL, 기본 `{}` | `{싱글몰트,조용한 분위기}` | 매장 태그를 표시 순서대로 저장한다. 최대 5개이고, 태그마다 앞뒤 공백을 지운 1~24자이며 줄바꿈과 제어 문자가 없고, 대소문자를 무시해도 서로 다르다. 업주나 운영자가 업장 수정(API 명세 3.7)으로 목록 전체를 바꾼다. 자유 입력이며 검색에는 쓰지 않는다. 검색에 쓰게 되면 별도 테이블이나 GIN 인덱스를 검토한다. |
| `status` | `bar_status`, NOT NULL, 기본 `active` | `active` | 폐업 또는 서비스 제외 업장을 삭제하지 않고 비활성화한다. |
| `created_at` | `timestamptz`, NOT NULL | `2026-09-28T03:10:00Z` | 업장 등록 시점이다. |
| `updated_at` | `timestamptz`, NOT NULL | `2026-09-28T04:10:00Z` | 주소 전화번호 등의 최종 변경 시점이다. |

**필요한 이유:** 상품 검색 결과를 업장 단위로 묶고 가격 용량 거리 지도 위치를 제공하려면 독립된 업장 엔터티가 필요하다. 

### 5.3 bar_owner_applications

**역할:** 사용자가 기존 업장 또는 새 업장의 업주가 되겠다고 낸 신청과 운영자의 결정을 저장한다.

| 컬럼 | 타입과 제약 | 예시 | 설명과 필요한 이유 |
|---|---|---|---|
| `id` | `uuid`, PK | 신청 ID | |
| `applicant_user_id` | `uuid`, NOT NULL, FK → `users.id` | 신청자 ID | 누가 신청했는지 나타낸다. 승인되면 이 사용자가 업주가 된다. |
| `application_type` | `owner_application_type`, NOT NULL | `existing_bar` | 기존 업장 신청인지 새 업장 등록 신청인지 구분한다. |
| `bar_id` | `uuid`, nullable, FK → `bars.id` | 관악 위스키 바 ID | `existing_bar`는 신청 대상 업장이다. `new_bar`는 승인 전에는 `null`이고, 승인으로 만든 업장 ID를 저장한다. |
| `proposed_bar_name` | `varchar(150)`, nullable | `신림 몰트 하우스` | `new_bar`에서만 쓰며 필수다. 승인할 때 운영자가 고칠 수 있다. |
| `proposed_address` | `varchar(500)`, nullable | `서울특별시 관악구 신림로 2 3층` | `new_bar`에서만 쓰며 필수다. |
| `proposed_phone` | `varchar(30)`, nullable | `02-1234-5678` | `new_bar`에서만 쓰며 선택이다. |
| `business_registration_number` | `char(10)`, NOT NULL | `1234567891` | 하이픈을 뺀 사업자등록번호 10자리이며 검증번호가 맞아야 한다. 운영자가 실제 사업자인지 확인하는 근거다. |
| `representative_name` | `varchar(100)`, NOT NULL | `김사장` | 사업자등록증의 대표자 성명이다. 국세청 진위확인에 필요하다. |
| `opening_date` | `date`, NOT NULL | `2020-03-02` | 사업자등록증의 개업연월일이다. 국세청 진위확인에 필요하다. |
| `business_verification_result` | `business_verification_result`, NOT NULL | `matched` | 마지막 국세청 진위확인 결과다. 운영자가 승인 전에 판단 근거로 본다. |
| `business_status` | `business_status`, nullable | `active` | 마지막 확인에서 국세청이 알려 준 사업자 상태다. 결과가 `matched`가 아니면 `null`이다. 신청자에게도 보여 준다. |
| `business_checked_at` | `timestamptz`, NOT NULL | `2026-10-14T03:00:00Z` | 저장된 검증 결과를 얻은 시각이다. 신청할 때 `unavailable`이 되었으면 그 시도 시각이다. 운영자의 다시 검증이 실패하면 결과와 함께 바뀌지 않는다. |
| `contact_phone` | `varchar(30)`, NOT NULL | `010-1234-5678` | 운영자가 확인을 위해 연락할 번호다. 업장 전화번호와 다를 수 있다. |
| `applicant_note` | `varchar(500)`, nullable | `대표 본인입니다` | 신청자가 남긴 메모다. |
| `status` | `owner_application_status`, NOT NULL, 기본 `pending` | `pending` | 신청 처리 상태다. |
| `reviewed_by_user_id` | `uuid`, nullable, FK → `users.id` | 운영자 ID | 승인하거나 거절한 운영자다. 권한을 준 결정이므로 누가 했는지 남긴다. |
| `reviewed_at` | `timestamptz`, nullable | `2026-10-14T05:00:00Z` | 승인 또는 거절 시각이다. |
| `rejection_reason` | `varchar(500)`, nullable | `사업자등록번호를 확인할 수 없습니다` | 거절할 때 필수이며 신청자에게 보여 준다. |
| `created_at` | `timestamptz`, NOT NULL | `2026-10-14T03:00:00Z` | 신청 시각이다. |
| `updated_at` | `timestamptz`, NOT NULL | `2026-10-14T05:00:00Z` | 상태가 마지막으로 바뀐 시각이다. |

**핵심 제약:**

- `existing_bar`는 `bar_id`가 필수이고 `proposed_*`가 모두 `null`이다. `new_bar`는 `proposed_bar_name`과 `proposed_address`가 필수이고, `bar_id`는 `approved`일 때만 값이 있다.
- 한 사용자는 같은 기존 업장에 `pending` 신청을 하나만 가질 수 있고, 같은 사업자등록번호로 `new_bar` `pending` 신청을 하나만 가질 수 있다. 동시에 들어온 신청도 막도록 두 규칙 모두 PostgreSQL 부분 unique 인덱스로 보장한다(아래 무결성 규칙). 서로 다른 사용자가 같은 업장에 동시에 신청할 수는 있지만, 하나가 승인되면 나머지는 승인할 수 없고 운영자가 거절한다.
- `rejection_reason`은 `rejected`일 때만, 그리고 반드시 값이 있다. `reviewed_by_user_id`와 `reviewed_at`은 `approved`와 `rejected`일 때만 함께 값이 있고, `pending`과 `canceled`에서는 둘 다 `null`이다.
- `business_registration_number`는 숫자 10자리다. 검증번호(마지막 자리) 계산은 API가 확인한다.
- `business_status`는 `business_verification_result = matched`일 때만 값이 있을 수 있다.
- 사업자등록번호, 대표자명, 개업일자, 연락처는 신청자와 운영자에게만 보여 주며 공개 API에 포함하지 않고 로그에도 남기지 않는다. 검증 결과 중 신청자에게는 `business_status`만 보여 준다. 실제 값은 저장소에 커밋하지 않는다.
- 사업자등록증 사진과 OCR로 읽은 값은 저장하지 않는다. 신청자가 확인한 값만 신청으로 저장된다. 메뉴판 사진은 5.5에 따로 저장한다.

### 5.4 bar_owners

**역할:** 운영자가 승인한 업주와 업장의 관계를 저장한다. 업장별 권한 검사는 이 테이블을 기준으로 한다.

| 컬럼 | 타입과 제약 | 예시 | 설명과 필요한 이유 |
|---|---|---|---|
| `id` | `uuid`, PK | 업주 관계 ID | |
| `bar_id` | `uuid`, NOT NULL, FK → `bars.id` | 관악 위스키 바 ID | 관리 대상 업장이다. |
| `user_id` | `uuid`, NOT NULL, FK → `users.id` | 업주 사용자 ID | 한 사용자는 여러 업장의 업주가 될 수 있다. |
| `application_id` | `uuid`, NOT NULL, UNIQUE, FK → `bar_owner_applications.id` | 승인한 신청 ID | 이 관계를 만든 신청이다. 신청 하나는 관계 하나만 만든다. |
| `created_at` | `timestamptz`, NOT NULL | `2026-10-14T05:00:00Z` | 승인으로 관계가 시작된 시각이다. |
| `revoked_at` | `timestamptz`, nullable | `null` | 운영자가 관계를 해제한 시각이다. `null`이면 현재 업주다. |
| `revoked_by_user_id` | `uuid`, nullable, FK → `users.id` | 운영자 ID | 관계를 해제한 운영자다. |

**핵심 제약:** 한 업장에는 현재 업주(`revoked_at`이 `null`인 행)가 최대 한 명이다. PostgreSQL 부분 unique 인덱스(`bar_id` WHERE `revoked_at IS NULL`)와 승인 시 업장 행 잠금으로 보장한다. 해제는 행을 지우지 않고 `revoked_at`을 기록해 이력을 남기며, `revoked_at`과 `revoked_by_user_id`는 함께 값이 있거나 함께 `null`이다. 업주가 되어도 `users.user_type`은 바뀌지 않는다.

**필요한 이유:** 업주 권한은 업장마다 다르므로 전역 `user_type`으로 표현할 수 없다. 신청과 관계를 나누면 신청 이력(증빙, 거절 사유)과 현재 권한을 따로 관리할 수 있고, 권한 검사는 작은 관계 테이블만 조회하면 된다.

### 5.5 bar_owner_application_menu_images

**역할:** 업주 신청에 첨부한 메뉴판 사진의 저장소 위치를 저장한다. 승인할 때 이 사진으로 첫 메뉴 등록 작업을 만든다.

| 컬럼 | 타입과 제약 | 예시 | 설명과 필요한 이유 |
|---|---|---|---|
| `id` | `uuid`, PK | 신청 사진 ID | |
| `application_id` | `uuid`, NOT NULL, FK → `bar_owner_applications.id` | 신청 ID | 어느 신청의 사진인지 나타낸다. |
| `storage_key` | `varchar(500)`, NOT NULL | `owner-applications/cccc.../page-1.jpg` | `menu_images`처럼 바이너리 대신 객체 저장소 위치를 저장한다. |
| `original_filename` | `varchar(255)`, nullable | `IMG_20261030_190112.jpg` | 업로드 당시 파일명이다. |
| `image_order` | `smallint`, NOT NULL | `1` | 여러 장 메뉴판의 순서다. 승인으로 만든 작업의 `menu_images.image_order`가 된다. |
| `content_sha256` | `char(64)`, NOT NULL | SHA-256 16진수 문자열 | 원본 바이트의 SHA-256이다. 승인으로 만든 작업의 `request_fingerprint`(8.1)를 사진을 다시 읽지 않고 계산하기 위해 저장한다. |
| `uploaded_at` | `timestamptz`, NOT NULL | `2026-10-30T10:01:00Z` | 업로드 시각이다. |

**핵심 제약:**

- 한 신청 안에서 `image_order`가 중복되지 않는다(unique).
- 신청이 `pending`일 때만 행을 만들거나 바꾼다. 업로드할 때마다 전체를 교체하며, 교체된 행과 파일은 삭제한다. 업로드는 신청 행을 잠가 승인·거절·취소와 동시에 처리되지 않게 한다.
- 신청이 거절되거나 취소되면 행과 파일을 삭제한다. 업주가 되지 않은 사람의 사진을 남기지 않기 위해서다. 파일 삭제는 DB 커밋 뒤에 하며, 실패하면 로그만 남긴다.
- 승인되면 행을 지우지 않는다. 승인으로 만든 작업의 `menu_images`가 같은 `storage_key`를 가리키므로, 승인 뒤에는 파일을 지우지 않는다.
- 사진은 신청자와 운영자에게만 서명 URL로 보여 주며 공개 API에 포함하지 않는다.

**필요한 이유:** 새 업장 신청은 승인 전까지 업장이 없어 `menu_imports`(`bar_id` NOT NULL)를 만들 수 없다. 그래서 승인 전 사진은 신청에 묶어 두고, 승인할 때 업장이 정해지면 작업으로 옮긴다.

### 5.6 bar_weekly_hours

**역할:** 업장의 요일별 정규 영업시간을 저장한다.

| 컬럼 | 타입과 제약 | 예시 | 설명과 필요한 이유 |
|---|---|---|---|
| `bar_id` | `uuid`, NOT NULL, FK → `bars.id`, PK 일부 | 관악 위스키 바 ID | |
| `day_of_week` | `smallint`, NOT NULL, PK 일부, CHECK 1~7 | `5` | ISO 8601 요일 번호(1 = 월요일). |
| `is_closed` | `boolean`, NOT NULL | `false` | 정기 휴무일이면 `true`다. |
| `open_time` | `time`, nullable | `18:00` | 영업 시작. 서울 현지 시각이며 5분 단위다. |
| `close_time` | `time`, nullable | `02:00` | 영업 종료. `open_time`보다 이르면 다음 날 끝난다(자정 넘김). |

**핵심 제약:**

- 기본 키는 (`bar_id`, `day_of_week`)라서 요일마다 한 행, 영업 구간도 하나다.
- `is_closed = true`이면 `open_time`, `close_time`이 모두 `null`이고, `false`이면 둘 다 값이 있고 서로 다르다.
- 행이 없는 요일은 영업시간 정보가 없는 것이며 정기 휴무와 다르다.
- 업장 수정(API 명세 3.7)의 `weeklyHours`로 업장의 행 전체를 한 번에 바꾼다.

**필요한 이유:** 고객 화면이 영업 상태를 계산하려면(API 명세 3.15.5) 요일별 시각을 구조화된 값으로 가져야 한다. 요일을 행으로 나누면 CHECK 제약으로 규칙을 지킬 수 있다.

### 5.7 bar_operating_exceptions

**역할:** 정규 영업시간 대신 적용하는 임시 휴무나 오늘만의 영업시간 변경을 저장한다.

| 컬럼 | 타입과 제약 | 예시 | 설명과 필요한 이유 |
|---|---|---|---|
| `id` | `uuid`, PK | | |
| `bar_id` | `uuid`, NOT NULL, UNIQUE, FK → `bars.id` | 관악 위스키 바 ID | 업장마다 하나만 있다. |
| `kind` | `operating_exception_kind`, NOT NULL | `vacation` | 4.18 |
| `start_date` | `date`, NOT NULL | `2026-11-10` | 서울 현지 날짜. `closed_today`와 `custom_hours`는 적용한 날이다. |
| `end_date` | `date`, NOT NULL | `2026-11-12` | `start_date` 이후다. `vacation`이 아니면 `start_date`와 같다. |
| `open_time`, `close_time` | `time`, nullable | `20:00`, `01:00` | `custom_hours`에서만 값이 있고 필수다. `close_time`이 더 이르면 다음 날 끝난다. |
| `note` | `varchar(100)`, nullable | `내부 사정으로 늦게 엽니다` | 고객 안내 문구다. 앞뒤 공백을 지운 한 줄이며 공백뿐이면 `null`이다. |
| `created_by_user_id` | `uuid`, nullable, FK → `users.id` | 업주 ID | 누가 적용했는지 남긴다. `users` 행이 없는 임시 로그인 운영자면 `null`이다. |
| `created_at` | `timestamptz`, NOT NULL | `2026-11-02T03:00:00Z` | 적용 시각이다. |

**핵심 제약:**

- 업장마다 최대 한 행(`bar_id` UNIQUE)이다. 새로 적용하면 기존 행을 바꾸고, 취소하면 지운다(API 명세 3.15.2, 3.15.3).
- 끝난 행을 지우는 배치 작업은 없다. API가 응답을 만들 때 현재 서울 시각으로 끝났는지 판단해 숨긴다(API 명세 3.15.4).

**필요한 이유:** 관리 홈의 빠른 변경은 정규 영업시간을 건드리지 않고 정해진 날짜에만 적용되어야 하며, 날짜가 지나면 정규 영업시간으로 자동으로 돌아가야 한다.

### 5.8 bar_photos

**역할:** 고객 업장 상세에 보여 줄 매장 사진의 저장소 위치와 순서를 저장한다.

| 컬럼 | 타입과 제약 | 예시 | 설명과 필요한 이유 |
|---|---|---|---|
| `id` | `uuid`, PK | 사진 ID | 공개 경로 `GET /api/bar-photos/{photoId}`의 ID다. |
| `bar_id` | `uuid`, NOT NULL, FK → `bars.id` | 관악 위스키 바 ID | |
| `storage_key` | `varchar(500)`, NOT NULL | `bars/2222.../photos/1212....jpg` | 메뉴 사진처럼 바이너리 대신 저장소 위치를 저장한다. |
| `content_type` | `varchar(20)`, NOT NULL | `image/jpeg` | 파일 내용으로 판별한 형식이다. 사진을 전달할 때 `Content-Type`으로 쓴다. |
| `content_sha256` | `char(64)`, NOT NULL | SHA-256 16진수 문자열 | 같은 사진을 두 번 올리지 않게 막는다. 응답을 받지 못해 다시 보낸 업로드도 이 값으로 걸러진다. |
| `sort_order` | `smallint`, NOT NULL | `1` | 표시 순서이며 1이 대표 사진이다. 업장 안에서 1부터 빈틈없이 이어진다. |
| `uploaded_by_user_id` | `uuid`, nullable, FK → `users.id` | 업주 ID | 누가 올렸는지 남긴다. `users` 행이 없는 임시 로그인 운영자면 `null`이다. |
| `created_at` | `timestamptz`, NOT NULL | `2026-11-02T03:00:00Z` | 올린 시각이다. |

**핵심 제약:**

- 업장당 최대 15장이다. 추가, 삭제, 순서 변경은 업장 행을 잠그고 처리해 장수와 순서를 지킨다.
- (`bar_id`, `content_sha256`)은 unique다.
- 대표 여부는 따로 저장하지 않고 `sort_order = 1`로 정한다. 업장 목록 API는 업장마다 이 행을 (`bar_id`, `sort_order`) 인덱스로 찾아 `coverPhotoUrl`로 준다.
- 삭제하면 행을 지운 뒤 DB 커밋 다음에 저장소 파일을 지운다. 파일 삭제가 실패하면 로그만 남긴다.
- 저장소는 공개하지 않는다. API가 파일을 읽어 고정 URL로 전달하므로, 메뉴판 사진의 서명 URL과 달리 만료되지 않고 캐시할 수 있다.

**필요한 이유:** 메뉴판 사진(`menu_images`)은 AI 처리와 검수용이라 공개하지 않는다. 고객에게 보여 줄 사진은 공개 범위, 순서, 삭제 규칙이 달라 따로 저장한다.

## 6 Product Catalog

### 6.1 brands

**역할:** 여러 상품이 공유하는 정규 브랜드를 저장한다.

| 컬럼 | 타입과 제약 | 예시 | 설명과 필요한 이유 |
|---|---|---|---|
| `id` | `uuid`, PK | 브랜드 Deanston의 ID | 상품이 브랜드명을 문자열로 반복하지 않고 같은 브랜드를 참조하게 한다. |
| `canonical_name` | `varchar(120)`, NOT NULL, UNIQUE | `Deanston` | 운영자가 선택한 대표 브랜드명이다. 중복 브랜드 생성을 방지한다. |
| `created_by_user_id` | `uuid`, nullable, FK → `users.id` | 브랜드를 만든 업주의 사용자 ID | 검수나 메뉴 직접 추가에서 브랜드를 만든 사용자다. 운영 대시보드에서 업주가 만든 카탈로그를 확인하는 데 쓴다. 시드로 넣은 브랜드는 null이다. |
| `created_at` | `timestamptz`, NOT NULL | `2026-09-28T03:20:00Z` | 브랜드 등록 시점이다. |
| `updated_at` | `timestamptz`, NOT NULL | `2026-09-28T03:20:00Z` | 대표명 등 최종 수정 시점이다. |

**필요한 이유:** AI가 `Deanston`과 `딘스톤`을 같은 브랜드로 정규화한 뒤 연수 에디션을 비교하도록 만든다.

### 6.2 brand_aliases

**역할:** 같은 브랜드를 가리키는 한글 영문 오탈자 등의 표기를 저장한다.

| 컬럼 | 타입과 제약 | 예시 | 설명과 필요한 이유 |
|---|---|---|---|
| `id` | `uuid`, PK | 별칭 행 ID | 별칭 자체를 독립적으로 관리한다. |
| `brand_id` | `uuid`, NOT NULL, FK → `brands.id` | Deanston 브랜드 ID | 별칭이 어떤 정규 브랜드를 가리키는지 연결한다. |
| `alias_text` | `varchar(120)`, NOT NULL | `딘스톤` | 운영자와 사용자에게 보이는 원래 별칭을 보존한다. |
| `normalized_alias` | `varchar(120)`, NOT NULL | `딘스톤` | 공백 대소문자 특수문자 등의 정규화가 끝난 비교용 문자열이다. |
| `language_code` | `varchar(10)`, nullable | `ko` | 언어별 검색과 관리에 사용할 수 있다. |
| `created_at` | `timestamptz`, NOT NULL | `2026-09-28T03:21:00Z` | 별칭 등록 시점이다. |

**핵심 제약:** 같은 브랜드 안에서 같은 `normalized_alias`를 중복 저장하지 않는다. 브랜드를 만들 때 `canonical_name`도 기본 별칭으로 함께 저장하여 모든 브랜드명 검색이 `brand_aliases.normalized_alias`만 사용하게 한다. `normalized_alias` 인덱스는 브랜드 후보 탐색을 빠르게 한다.

**정규화 규칙 변경:** 별칭 행마다 정규화 버전을 저장하지 않는다. 백엔드 정규화 함수를 변경할 때는 `backend/scripts/renormalize_aliases.py`로 `brand_aliases`와 `product_aliases`의 모든 `normalized_alias`를 새 함수로 일괄 재계산한다. 인자 없이 실행해 바뀔 내역과 서로 다른 상품·브랜드가 같은 값을 갖게 되는 경우를 먼저 확인하고, `--apply`로 반영한 뒤 `seed_catalog.py`를 다시 실행해 예전 규칙에서 겹쳐 빠졌던 시드 별칭을 추가한다. 같은 상품·브랜드 안에서 값이 같아진 별칭은 하나만 남긴다. 재계산과 중복 검사를 성공한 뒤에만 새 정규화 함수를 사용하는 백엔드를 활성화한다. 정규화 함수가 Python 코드이므로 마이그레이션이 아니라 그 함수를 그대로 쓰는 스크립트로 재계산한다. 일부 행만 새 규칙으로 바뀐 혼합 상태에서는 검색을 시작하지 않는다.

### 6.3 products

**역할:** 모든 업장이 공유하는 병 단위의 정규 술 상품을 저장한다.

| 컬럼 | 타입과 제약 | 예시 | 설명과 필요한 이유 |
|---|---|---|---|
| `id` | `uuid`, PK | Deanston 12 상품 ID | 업장 메뉴와 검색 결과가 참조하는 정규 상품 식별자다. |
| `category` | `varchar(30)`, NOT NULL, 기본 `whisky` | `whisky` | MVP는 위스키이지만 이후 rum gin wine sake 확장을 위한 구분값이다. |
| `display_name` | `varchar(200)`, NOT NULL | `Deanston 12` | 검색 결과와 운영자 화면에 사용하는 대표 표시명이다. 상품 식별자나 단독 병합 키로 사용하지 않는다. |
| `brand_id` | `uuid`, NOT NULL, FK → `brands.id` | Deanston 브랜드 ID | AI가 추출한 브랜드를 구조적으로 비교한다. |
| `age_years` | `smallint`, nullable | `12` | 연수가 다른 상품의 잘못된 병합을 막는다. NAS 상품은 null이다. |
| `edition_name` | `varchar(150)`, nullable | `Virgin Oak` | 같은 브랜드와 연수여도 다른 에디션을 구분한다. |
| `abv` | `decimal(5,2)`, nullable | `46.30` | 상품 상세에 사용할 수 있는 도수다. MVP 병합의 핵심 키는 아니다. |
| `is_active` | `boolean`, NOT NULL, 기본 true | `true` | 잘못 등록되거나 더 이상 사용할 수 없는 상품을 삭제하지 않고 비활성화한다. |
| `created_from_extracted_item_id` | `uuid`, nullable, FK → `extracted_items.id` | 미등록 상품을 처음 발견한 추출 항목 ID | 메뉴 검수 중 새 상품 생성을 촉발한 원본 이미지와 AI 결과를 찾아가기 위한 출처다. 사전 등록한 상품과 메뉴 직접 추가(API 명세 3.14.3)로 만든 상품은 null이다. |
| `created_by_user_id` | `uuid`, nullable, FK → `users.id` | 상품을 만든 업주의 사용자 ID | 검수나 메뉴 직접 추가에서 상품을 만든 사용자다. 운영 대시보드에서 업주가 만든 상품을 골라 확인하는 데 쓴다. 시드로 넣은 상품은 null이다. |
| `created_at` | `timestamptz`, NOT NULL | `2026-09-28T03:30:00Z` | 상품 등록 시점이다. |
| `updated_at` | `timestamptz`, NOT NULL | `2026-09-28T03:35:00Z` | 상품 정보 최종 수정 시점이다. |

**핵심 원칙:** 브랜드 연수 에디션이 충돌하면 자동 병합하지 않는다. `brand_id + age_years + edition_name`은 후보 생성에 사용하지만 강제 unique 키로 사용하지 않는다.

`created_from_extracted_item_id`는 상품의 생성 출처를 나타내는 선택적 provenance 필드다. 예를 들어 AI가 메뉴 사진에서 기존 카탈로그에 없는 `Deanston Virgin Oak`를 추출하고 운영자가 검수 중 새 상품으로 등록하면, 그때의 `extracted_items.id`를 저장한다. 이 연결을 따라가면 원본 메뉴 이미지, 사용한 모델과 파이프라인, AI 원문, 운영자의 교정 결과를 확인할 수 있다. 이후 다른 메뉴에서 같은 상품이 다시 발견되더라도 이 값은 바꾸지 않으며, 모든 출현 기록을 모으는 용도로 사용하지 않는다. 상품을 처음 만든 사용자는 `created_by_user_id`에 남는다.

### 6.4 product_aliases

**역할:** 같은 병 상품을 가리키는 전체 상품명 표기를 저장하고 검색어 및 AI 결과를 정규 상품에 연결한다.

| 컬럼 | 타입과 제약 | 예시 | 설명과 필요한 이유 |
|---|---|---|---|
| `id` | `uuid`, PK | 상품 별칭 행 ID | 별칭을 독립적으로 관리한다. |
| `product_id` | `uuid`, NOT NULL, FK → `products.id` | Deanston 12 상품 ID | 별칭이 가리키는 정규 상품을 나타낸다. |
| `alias_text` | `varchar(200)`, NOT NULL | `딘스톤 12년` | 원본 표기를 보존한다. |
| `normalized_alias` | `varchar(200)`, NOT NULL | `딘스톤12` | 비교 검색용으로 정규화된 값이다. |
| `language_code` | `varchar(10)`, nullable | `ko` | 언어별 별칭을 관리한다. |
| `is_searchable` | `boolean`, NOT NULL, 기본 true | `true` | 잘못된 별칭이나 내부 전용 표기를 사용자 검색 대상에서 제외할 수 있다. |
| `created_at` | `timestamptz`, NOT NULL | `2026-09-28T03:31:00Z` | 별칭 등록 시점이다. |

**핵심 제약:** `(product_id, normalized_alias)`는 unique지만 `normalized_alias` 자체는 전역 unique가 아니다. 상품을 만들 때 `display_name`도 기본 별칭으로 함께 저장하여 모든 상품명 검색이 `product_aliases.normalized_alias`만 사용하게 한다. 같은 모호한 표기가 여러 상품의 후보가 될 수 있기 때문이다. 정규화 규칙을 변경하면 6.2의 일괄 재생성 규칙을 동일하게 적용한다.

## 7 Published Menus

### 7.1 bar_menu_items

**역할:** 특정 업장이 특정 정규 상품을 취급한 적이 있다는 지속적인 연결을 저장한다.

| 컬럼 | 타입과 제약 | 예시 | 설명과 필요한 이유 |
|---|---|---|---|
| `id` | `uuid`, PK | A바의 Deanston 12 항목 ID | 업장과 상품 조합을 다른 테이블에서 안정적으로 참조한다. |
| `bar_id` | `uuid`, NOT NULL, FK → `bars.id` | 관악 위스키 바 ID | 어느 업장의 항목인지 나타낸다. |
| `product_id` | `uuid`, NOT NULL, FK → `products.id` | Deanston 12 상품 ID | 어떤 정규 상품인지 나타낸다. |
| `created_at` | `timestamptz`, NOT NULL | `2026-09-28T04:30:00Z` | 업장 메뉴 항목 최초 생성 시점이다. |

**핵심 원칙:** `(bar_id, product_id)`는 unique다. 현재 메뉴판에서 빠져도 행은 삭제하지 않는다. 현재 `menu_board_entries`에 연결되면 노출되고 연결되지 않으면 보관된 상태로 본다.

**필요한 이유:** 메뉴판을 교체할 때마다 같은 업장 상품 행을 새로 만들지 않고 과거에 취급했던 항목을 재사용한다.

### 7.2 menu_boards

**역할:** 한 업장에서 현재 고객에게 보여주는 메뉴판 묶음의 헤더다. 업장당 현재 메뉴판은 최대 하나다.

| 컬럼 | 타입과 제약 | 예시 | 설명과 필요한 이유 |
|---|---|---|---|
| `id` | `uuid`, PK | 현재 메뉴판 ID | 메뉴판 구성 항목들을 하나로 묶는다. |
| `bar_id` | `uuid`, NOT NULL, UNIQUE, FK → `bars.id` | 관악 위스키 바 ID | 업장당 현재 메뉴판 하나를 보장한다. |
| `last_import_id` | `uuid`, nullable, FK → `menu_imports.id` | 마지막 일부 수정 작업 ID | 여러 부분 수정이 누적될 수 있으므로 가장 최근 반영 작업을 기록한다. 메뉴 직접 편집은 이 값을 바꾸지 않는다. |
| `version` | `integer`, NOT NULL, 기본 1 | `4` | 메뉴판 버전이다. 검수 반영과 직접 편집이 성공할 때마다 1씩 올린다. 직접 편집은 요청의 버전과 이 값이 다르면 거부해, 다른 사람의 변경을 덮어쓰지 않게 한다(API 명세 3.14.1). |
| `published_at` | `timestamptz`, NOT NULL | `2026-09-28T04:31:00Z` | 고객에게 보여줄 메뉴 최종 업데이트 날짜다. 검수 반영과 직접 편집 모두 갱신한다. 검색 결과의 최신성 표시에 사용한다. |

**필요한 이유:** 업장 메뉴 항목들의 현재 노출 묶음과 게시 메타데이터를 한 곳에서 관리한다.

### 7.3 menu_board_entries

**역할:** 현재 메뉴판에 어떤 업장 메뉴 항목이 들어가는지 나타낸다. 한 행은 메뉴판에 표시된 술 하나다.

| 컬럼 | 타입과 제약 | 예시 | 설명과 필요한 이유 |
|---|---|---|---|
| `id` | `uuid`, PK | 메뉴판 구성 행 ID | 여러 판매 옵션이 참조할 상위 항목이다. |
| `menu_board_id` | `uuid`, NOT NULL, FK → `menu_boards.id` | 현재 메뉴판 ID | 어느 메뉴판에 속하는지 나타낸다. |
| `bar_menu_item_id` | `uuid`, NOT NULL, FK → `bar_menu_items.id` | A바의 Deanston 12 항목 ID | 메뉴판에 표시할 업장 상품을 연결한다. |
| `display_name` | `varchar(200)`, NOT NULL | `딘스톤 12년` | `products.display_name`과 달라도 실제 메뉴판에서 보여줄 표기를 보존한다. |
| `sort_order` | `integer`, NOT NULL | `7` | 업장 전체 메뉴 화면의 표시 순서를 정한다. |
| `created_at` | `timestamptz`, NOT NULL | `2026-09-28T04:31:00Z` | 현재 메뉴판 구성에 추가된 시점이다. |

**핵심 제약:** 한 메뉴판에서 `sort_order`와 `bar_menu_item_id`가 각각 중복되지 않는다.

### 7.4 menu_entry_options

**역할:** 메뉴판에 표시된 술 하나의 용량 가격 옵션을 저장한다.

| 컬럼 | 타입과 제약 | 예시 | 설명과 필요한 이유 |
|---|---|---|---|
| `id` | `uuid`, PK | 판매 옵션 ID | 같은 술의 여러 옵션을 개별 식별한다. |
| `menu_board_entry_id` | `uuid`, NOT NULL, FK → `menu_board_entries.id` | Deanston 12 메뉴판 구성 ID | 어느 술의 판매 옵션인지 연결한다. |
| `source_extracted_option_id` | `uuid`, nullable, FK → `extracted_options.id` | 30ml 가격을 추출한 옵션 ID | 어떤 AI 추출 옵션과 검수에서 게시 옵션이 만들어졌는지 추적한다. 메뉴 직접 편집으로 입력한 옵션은 null이다. |
| `option_label` | `varchar(100)`, nullable | `Large` | ml로 표현되지 않는 실제 메뉴의 옵션명을 보존한다. |
| `pour_ml` | `smallint`, nullable | `30` | 제공 용량이다. 메뉴에 용량이 없으면 null이다. |
| `price_krw` | `integer`, NOT NULL | `15000` | 고객 검색 결과에 표시할 원화 가격이다. |
| `sort_order` | `smallint`, NOT NULL | `2` | 한 술 안에서 옵션 표시 순서를 정한다. |
| `created_at` | `timestamptz`, NOT NULL | `2026-09-28T04:31:00Z` | 옵션 생성 시점이다. |

**예시:** Deanston 12의 `menu_board_entries` 한 행 아래에 `15ml / 8,000원`과 `30ml / 15,000원` 두 행이 존재한다.

**핵심 제약:** 한 메뉴판 구성 안에서 옵션 순서가 중복되지 않는다. 각 노출 항목에 옵션이 최소 하나 존재한다는 규칙은 애플리케이션 또는 최종 DDL에서 보장해야 한다.

## 8 AI Menu Import

### 8.1 menu_imports

**역할:** 운영자 또는 해당 업장의 업주가 한 번에 수행한 메뉴 사진 등록과 검수 게시 작업의 최상위 단위다.

| 컬럼 | 타입과 제약 | 예시 | 설명과 필요한 이유 |
|---|---|---|---|
| `id` | `uuid`, PK | 메뉴 등록 작업 ID | 여러 사진 실행 결과 diff를 하나의 작업으로 묶는다. |
| `idempotency_key` | `varchar(255)`, NOT NULL, UNIQUE | `8b4900ea-7ab8-4f55-a92d-09ec43a8f421` | 모바일 네트워크 재시도로 동일 요청이 반복돼도 같은 메뉴 등록 작업을 반환하여 중복 이미지와 AI 실행 비용을 막는다. |
| `request_fingerprint` | `varchar(64)`, NOT NULL | SHA-256 16진수 문자열 | 동일한 `idempotency_key`로 들어온 재요청의 내용도 원래 요청과 같은지 검증한다. 서로 다른 키로 같은 내용을 다시 등록하는 것은 허용하므로 UNIQUE 제약은 두지 않는다. |
| `bar_id` | `uuid`, NOT NULL, FK → `bars.id` | 관악 위스키 바 ID | 어느 업장의 메뉴를 바꾸는 작업인지 나타낸다. |
| `mode` | `import_mode`, NOT NULL | `full_replace` | 전체 교체와 일부 수정의 diff 규칙을 결정한다. |
| `status` | `import_status`, NOT NULL, 기본 `uploaded` | `ready_for_review` | AI 처리와 통합 검수·반영이 어느 단계인지 관리한다. |
| `review_version` | `integer`, NOT NULL, 기본 `0` | `3` | 통합 검수 응답을 다시 생성할 때 증가한다. 운영자가 본 버전과 제출 시점의 버전을 비교해 오래된 화면에서의 반영을 막는다. |
| `owner_note` | `text`, nullable | `업장 허가 후 9월 메뉴 촬영` | 업장 허가 출처 특이사항 등의 운영 메모다. 현재 이름은 향후 업주 흐름을 고려한 표현이다. |
| `review_confirmed_at` | `timestamptz`, nullable | `2026-09-28T04:30:00Z` | 항목·옵션·상품 매칭·신규 등록 제안·메뉴 diff를 한 번에 최종 승인한 시점이다. |
| `recovery_count` | `smallint`, NOT NULL, 기본 `0` | `1` | 서버 재시작으로 끊긴 처리를 이어서 처리한 횟수다. 3번을 넘으면 더 이어서 처리하지 않고 `failed`로 바꾼다. 특정 사진 때문에 재시작이 반복되는 것을 막는다. 0 이상이어야 한다(CHECK). |
| `created_at` | `timestamptz`, NOT NULL | `2026-09-28T03:40:00Z` | 등록 작업 시작 시점이다. |
| `completed_at` | `timestamptz`, nullable | `2026-09-28T04:31:00Z` | 작업이 최종 상태(`applied`, `failed`, `canceled`)가 된 시점이다. 진행 중이면 null이다. |

**필요한 이유:** 이미지 한 장이나 추출 항목 하나만으로는 전체 교체 일부 수정 최종 승인 상태를 표현할 수 없으므로 작업 단위가 필요하다.

프론트엔드는 메뉴 등록을 시작할 때마다 새로운 `idempotency_key`를 생성해 요청 헤더로 보낸다. 백엔드는 `barId`, `mode`, `ownerNote`, 이미지 순서, 각 이미지 원본 바이트의 SHA-256을 안정적인 형식으로 조합하고 다시 SHA-256을 적용해 `request_fingerprint`를 계산한다. multipart boundary, 임시 URL, 업로드 시각처럼 재시도마다 달라질 수 있는 값은 계산에서 제외한다.

업주 신청 승인으로 만든 작업(3.4)은 `idempotency_key = owner-application:<신청 ID>`로 저장한다. 신청 하나는 한 번만 승인되므로 키가 겹치지 않는다. `request_fingerprint`는 같은 공식으로 계산하되 `ownerNote`는 `null`이고, 이미지 해시는 `bar_owner_application_menu_images.content_sha256`을 쓴다. `menu_images`는 신청 사진과 같은 `storage_key`, `original_filename`, `image_order`로 만든다.

같은 키가 다시 들어오면 새 요청의 fingerprint를 기존 행과 비교한다. fingerprint도 같으면 새 `menu_imports`, `menu_images`, `extraction_runs`를 만들지 않고 기존 작업을 반환한다. fingerprint가 다르면 프론트엔드가 하나의 키를 서로 다른 요청에 재사용한 것이므로 `409 Conflict`로 거부한다. 다른 키에 같은 fingerprint가 들어온 경우에는 별개의 명시적 등록 요청으로 허용한다.

MVP에서는 한 업장에 `uploaded`, `processing`, `ready_for_review` 상태인 미완료 작업을 하나만 허용한다. 새 작업을 만들 때 백엔드는 해당 `bars` 행을 잠그고 진행 중인 작업을 다시 확인한다. 최종 반영 때는 해당 `menu_imports` 행을 잠그고, 전체를 `SERIALIZABLE` 트랜잭션으로 실행하며, 검수 데이터를 만든 뒤 현재 메뉴판이 바뀌었는지 확인한다. 업장마다 미완료 작업은 하나뿐이므로 같은 메뉴판에 동시에 반영하려는 다른 작업은 없다. 이 규칙으로 한 명의 업주가 여러 기기·탭에서 동시에 작업하거나 요청을 재전송해도 오래된 검수 결과가 현재 메뉴판을 덮어쓰는 것을 막는다.

### 8.2 menu_images

**역할:** 한 메뉴 등록 작업에 포함된 원본 이미지들을 저장한다.

| 컬럼 | 타입과 제약 | 예시 | 설명과 필요한 이유 |
|---|---|---|---|
| `id` | `uuid`, PK | 메뉴 이미지 ID | AI 실행과 평가 정답이 참조하는 이미지 식별자다. |
| `menu_import_id` | `uuid`, NOT NULL, FK → `menu_imports.id` | 메뉴 등록 작업 ID | 여러 장의 사진을 하나의 업로드 작업으로 묶는다. |
| `storage_key` | `varchar(500)`, NOT NULL | `menus/bar-22/import-51/page-1.jpg` | 이미지 바이너리 대신 객체 저장소 위치를 저장한다. 공개 URL 만료와 DB 용량 문제를 피한다. |
| `original_filename` | `varchar(255)`, nullable | `IMG_20260928_120301.jpg` | 업로드 당시 파일명을 보존해 운영자가 원본을 식별하게 한다. |
| `image_order` | `smallint`, NOT NULL | `1` | 여러 페이지 메뉴의 순서를 보존한다. |
| `uploaded_at` | `timestamptz`, NOT NULL | `2026-09-28T03:41:00Z` | 실제 업로드 시점을 기록한다. |

**핵심 제약:** 한 등록 작업 안에서 `image_order`가 중복되지 않는다.

### 8.3 extraction_runs

**역할:** 메뉴 이미지에 구현 전에 선택한 AI 파이프라인을 한 번 실행한 기록이다. MVP에서는 이미지마다 실행 행을 하나만 만든다.

| 컬럼 | 타입과 제약 | 예시 | 설명과 필요한 이유 |
|---|---|---|---|
| `id` | `uuid`, PK | 추출 실행 ID | 한 번의 모델 실행을 고유하게 식별한다. |
| `menu_image_id` | `uuid`, NOT NULL, FK → `menu_images.id` | 메뉴 1페이지 이미지 ID | 어떤 이미지에 대한 실행인지 연결한다. |
| `approach` | `extraction_approach`, NOT NULL | `ocr_llm` | 구현 전에 선택한 OCR+LLM 또는 Vision LLM 방식을 기록한다. |
| `provider` | `varchar(100)`, NOT NULL | `Naver Clova` | 외부 제공자를 기록해 재현성과 비용 분석에 활용한다. |
| `model_name` | `varchar(150)`, NOT NULL | `model-x` | 정확한 모델을 기록한다. |
| `pipeline_version` | `varchar(100)`, NOT NULL | `v1.2-ko-menu-rules` | 프롬프트 후처리 규칙 코드 버전을 묶어 재현한다. |
| `status` | `pipeline_status`, NOT NULL, 기본 `queued` | `succeeded` | 비동기 실행 상태와 실패 여부를 기록한다. |
| `raw_output` | `json`, nullable | `{\"items\":[...]}` | 파싱 전 모델 원본 응답과 최초 항목 역할·옵션 구조를 보존해 오류 분석과 재처리를 지원한다. |
| `started_at` | `timestamptz`, nullable | `2026-09-28T03:42:00Z` | 실행 시작 시점이다. |
| `completed_at` | `timestamptz`, nullable | `2026-09-28T03:42:08Z` | 실행 완료 시점과 지연 시간을 계산한다. |
| `created_at` | `timestamptz`, NOT NULL | `2026-09-28T03:41:58Z` | 실행 레코드 생성 시점이다. |

**핵심 제약:** `menu_image_id`는 unique다. 이미지마다 실행 행을 하나만 만든다. 모델 호출은 한 번의 추출 호출 안에서 재시도한다. 연결 오류와 HTTP 429·5xx는 5, 10, 20, 40, 60초 간격으로 최대 `EXTRACTION_MAX_ATTEMPTS`(기본 6)번까지 시도한다. 그래도 실패하면 그 실행 행은 `failed`로 끝나고 오류 내용은 `raw_output`에 남으며, 남은 이미지는 처리하지 않고 등록 작업 전체가 `failed`가 된다. 실패한 작업은 이어서 처리하지 않고 운영자가 새로 업로드한다. 실패한 작업을 다시 시도하는 기능은 Iteration 2 이후 필요하면 검토한다.

**필요한 이유:** 선택한 추출 방식의 모델·파이프라인 버전·원본 응답과 처리 상태를 이미지별로 추적한다.

### 8.4 extracted_items

**역할:** 한 AI 실행이 인식한 상품 항목 또는 비상품 텍스트 블록을 한 번씩 저장한다. 상품명, 항목 역할, 상품 매칭과 검수 상태는 옵션 개수와 무관하게 이 테이블에서 한 번만 관리한다.

| 컬럼 | 타입과 제약 | 예시 | 설명과 필요한 이유 |
|---|---|---|---|
| `id` | `uuid`, PK | 추출 항목 ID | 옵션, 후보 매칭, 신규 상품 생성과 diff가 참조하는 상위 단위다. |
| `extraction_run_id` | `uuid`, NOT NULL, FK → `extraction_runs.id` | 추출 실행 ID | 어느 모델 실행에서 나온 항목인지 연결한다. |
| `item_order` | `smallint`, NOT NULL | `7` | 같은 실행 안에서 AI가 인식한 항목의 원본 표시 순서를 보존한다. |
| `raw_text` | `text`, NOT NULL | `딘스톤 12년 15ml 8.0 / 30ml 15.0` | AI 구조화 전의 상품과 옵션 전체 원문을 보존한다. |
| `extracted_line_type` | `extracted_line_type`, NOT NULL, 기본 `unknown` | `product` | AI가 1차 판별한 역할이다. 평가를 위해 운영자 검수 후에도 변경하지 않는다. |
| `corrected_line_type` | `extracted_line_type`, nullable | `product` | 운영자가 최초 역할을 바꾼 경우에만 교정값을 저장한다. 그대로 승인하면 null이다. |
| `extracted_product_name` | `varchar(200)`, nullable | `딘스톤 12년` | AI가 구조화한 상품명이다. |
| `extracted_brand_name` | `varchar(120)`, nullable | `딘스톤` | AI가 분리한 브랜드 표기다. 브랜드 별칭 조회에 사용한다. |
| `extracted_age_years` | `smallint`, nullable | `12` | AI가 추출한 연수다. 연수 충돌 검사에 사용하며 NAS 또는 미인식이면 null이다. |
| `extracted_edition_name` | `varchar(150)`, nullable | `Virgin Oak` | AI가 추출한 에디션 표기다. 같은 브랜드·연수 상품의 후보를 구분한다. |
| `extracted_abv` | `decimal(5,2)`, nullable | `46.30` | AI가 추출한 도수다. 보조 후보 점수와 검수에 사용한다. |
| `extraction_confidence` | `decimal(5,4)`, nullable | `0.9135` | 낮은 신뢰도 항목을 사람 검수로 보내는 기준이다. |
| `initial_resolution_status` | `resolution_status`, nullable | `exact_match` | 최초 상품 매칭 결과다. 후보 생성 완료 후 고정하며 운영자의 최종 선택과 분리한다. 상품 매칭을 실행하지 않은 항목은 null이다. |
| `selected_product_id` | `uuid`, nullable, FK → `products.id` | Deanston 12 상품 ID | 최종적으로 연결한 정규 상품이다. 애매하거나 미등록이면 검수 전까지 null이다. |
| `selected_match_method` | `match_method`, nullable | `alias` | 1순위 제안을 그대로 확정하면 해당 후보의 `method`를 복사한다. 다른 후보 선택, 직접 검색 또는 신규 상품 등록이면 `manual`을 저장한다. |
| `match_confidence` | `decimal(5,4)`, nullable | `0.9820` | 최종 선택 상품이 `resolution_candidates`에 있으면 그 후보의 `score`를 복사한다. 직접 검색한 상품·신규 상품·비상품은 대응 후보 점수가 없으므로 null이다. 추출 신뢰도와는 별개다. |
| `review_status` | `review_status`, NOT NULL, 기본 `pending` | `corrected` | 사람 검수 여부와 처리 결과를 나타낸다. |
| `corrected_product_name` | `varchar(200)`, nullable | `Deanston 12` | 사람이 수정한 상품명이다. AI 정확도 측정과 최종 게시 입력에 사용한다. |
| `reviewed_at` | `timestamptz`, nullable | `2026-09-28T04:00:00Z` | 항목과 하위 옵션 검수를 완료한 시점이다. |

**핵심 제약:** 한 `extraction_run` 안에서 `item_order`가 중복되지 않는다. 최초 AI 역할은 `extracted_line_type`에 고정하고, 유효 역할은 `COALESCE(corrected_line_type, extracted_line_type)`로 계산한다. `section_header`, `description`, `unknown`도 원문과 함께 보존하지만 최초 자동 처리에서는 상품 후보와 옵션을 만들지 않는 것이 기본이다. 운영자가 실제 상품을 잘못 분류된 항목으로 발견하면 `corrected_line_type = product`로 저장하고 직접 상품을 선택하거나 새 상품을 등록한다. 이 경우 최초 자동 매칭을 실행하지 않았으므로 `initial_resolution_status`는 null을 유지한다.

**최종 매칭 방법:** 현재 `reviewVersion`의 `proposedProductId`를 그대로 확정한 경우에만 그 후보의 `alias`, `embedding`, `llm`을 `selected_match_method`에 복사한다. 운영자가 1순위와 다른 후보를 선택하거나 직접 검색하거나 신규 상품을 만들면 사람의 개입으로 결과가 달라졌으므로 `manual`을 저장한다. 이 구분을 통해 자동 제안의 Top-1 정확도를 평가할 수 있다.

**최종 매칭 점수:** 운영자가 1순위 또는 다른 `resolution_candidate`를 선택하면 선택된 후보의 `score`를 `match_confidence`에 복사한다. 다른 후보를 선택한 경우에도 그 상품에 대해 시스템이 계산했던 점수는 분석용으로 보존하되, `selected_match_method`는 `manual`로 기록한다. 후보 목록에 없던 상품을 직접 검색하거나 신규 상품을 생성한 경우와 비상품·제외 항목은 `match_confidence = null`로 둔다.

### 8.5 extracted_options

**역할:** 하나의 추출 상품 항목에 포함된 가격·용량 선택지를 개별 행으로 저장한다.

| 컬럼 | 타입과 제약 | 예시 | 설명과 필요한 이유 |
|---|---|---|---|
| `id` | `uuid`, PK | 추출 옵션 ID | 게시 메뉴 옵션이 원본 AI 결과를 추적할 때 참조한다. |
| `extracted_item_id` | `uuid`, NOT NULL, FK → `extracted_items.id` | 딘스톤 12년 추출 항목 ID | 여러 옵션을 하나의 상품 항목 아래에 묶는다. |
| `option_order` | `smallint`, NOT NULL | `2` | 같은 상품 항목 안에서 옵션의 원본 표시 순서를 보존한다. |
| `extracted_option_label` | `varchar(100)`, nullable | `Double` | ml로 표현되지 않는 AI 추출 옵션명을 보존한다. |
| `extracted_price_krw` | `integer`, nullable | `15000` | AI가 추출한 원화 가격이다. |
| `extracted_pour_ml` | `smallint`, nullable | `30` | AI가 추출한 제공 용량이다. |
| `corrected_option_label` | `varchar(100)`, nullable | `더블` | 운영자가 수정한 옵션명이다. |
| `corrected_price_krw` | `integer`, nullable | `15000` | 운영자가 수정한 가격이다. |
| `corrected_pour_ml` | `smallint`, nullable | `30` | 운영자가 수정한 용량이다. |

**핵심 제약:** `(extracted_item_id, option_order)`는 unique다. 상품 정보와 검수 상태는 부모 `extracted_items`에 한 번만 저장하며, 상품 항목에는 게시 가능한 옵션이 최소 하나 있어야 한다는 규칙을 애플리케이션 또는 최종 DDL에서 보장한다.

### 8.6 resolution_candidates

**역할:** 하나의 추출 상품 항목에 대해 시스템이 제안한 정규 상품 후보와 순위를 저장한다.

| 컬럼 | 타입과 제약 | 예시 | 설명과 필요한 이유 |
|---|---|---|---|
| `id` | `uuid`, PK | 후보 행 ID | 후보를 개별 관리한다. |
| `extracted_item_id` | `uuid`, NOT NULL, FK → `extracted_items.id` | 딘스톤 12 추출 항목 ID | 후보가 어떤 추출 상품에 대한 것인지 연결한다. |
| `product_id` | `uuid`, NOT NULL, FK → `products.id` | Deanston 12 상품 ID | 후보 정규 상품이다. |
| `candidate_rank` | `smallint`, NOT NULL | `1` | 운영자에게 보여줄 후보 순서와 Top-1 평가에 사용한다. |
| `score` | `decimal(7,6)`, nullable | `0.932100` | 규칙 임베딩 LLM 등이 계산한 비교 점수다. |
| `method` | `match_method`, NOT NULL | `embedding` | 여러 발견 신호 중 후보의 최종 순위를 결정한 대표 방법을 기록한다. |
| `evidence` | `json`, nullable | `{"brandExact":true,"ageExact":true,"embeddingSimilarity":0.91}` | 후보 점수와 순위가 나온 근거를 구조화해 저장한다. 정확 별칭 여부, 브랜드·연수 일치, 에디션 충돌, 문자열·임베딩 유사도, LLM `reasonCode` 등 실제 계산에 사용한 값만 넣는다. 후보를 찾은 매칭 규칙은 `rule`(`alias`, `S1`, `S2`, `S2b`, `S3`)에 기록한다. |
| `created_at` | `timestamptz`, NOT NULL | `2026-09-28T03:42:10Z` | 후보 생성 시점이다. |

**핵심 제약:** 같은 추출 항목에서 순위가 중복되지 않으며 `(extracted_item_id, product_id)`도 unique다. 따라서 하나의 상품은 후보 목록에 한 번만 나타난다. 별칭 정확 일치, 브랜드·연수·에디션 일치, 문자열·임베딩 점수와 LLM 판단은 별도 후보 행이 아니라 하나의 `evidence`로 합친다. 후보를 다시 계산할 때는 기존 후보 행을 최신 결과로 교체하므로 과거 `evidence` 이력은 보존하지 않는다. `evidence`는 운영자 설명과 디버깅을 돕지만 최종 상품 선택 자체는 `extracted_items.selected_product_id`에 기록한다. 후보 재정렬에 사용한 모델과 프롬프트 설정은 백엔드 코드에서 버전 관리하며 후보 행마다 복제하지 않으므로 별도의 `matching_runs` 테이블은 두지 않는다.

### 8.7 menu_import_changes

**역할:** 자동 처리 결과와 현재 메뉴판의 임시 차이를 추가 수정 제거 단위로 저장하고 통합 검수에서 운영자의 최종 결정을 기록한다.

| 컬럼 | 타입과 제약 | 예시 | 설명과 필요한 이유 |
|---|---|---|---|
| `id` | `uuid`, PK | diff 행 ID | 변경 제안을 개별적으로 승인하거나 무시한다. |
| `menu_import_id` | `uuid`, NOT NULL, FK → `menu_imports.id` | 현재 등록 작업 ID | 어떤 등록 작업에서 발생한 diff인지 연결한다. |
| `change_type` | `menu_change_type`, NOT NULL | `remove` | 추가 수정 제거 중 어떤 변경인지 나타낸다. |
| `bar_menu_item_id` | `uuid`, nullable, FK → `bar_menu_items.id` | 기존 Deanston 12 업장 메뉴 항목 ID | 수정 제거 대상이다. 신규 추가는 게시 전까지 아직 행이 없어 null일 수 있다. |
| `extracted_item_id` | `uuid`, nullable, FK → `extracted_items.id` | 새 상품과 옵션을 담은 추출 항목 ID | 추가 수정의 새 데이터 출처다. 제거는 새 사진에 항목이 없으므로 null일 수 있다. |
| `decision` | `menu_change_decision`, NOT NULL, 기본 `pending` | `apply` | 운영자가 변경을 적용할지 무시할지 기록한다. |
| `reviewed_at` | `timestamptz`, nullable | `2026-09-28T04:25:00Z` | 개별 변경 결정 시점이다. |

**필요한 이유:** 운영자가 항목 역할, 옵션 또는 상품 연결을 수정하면 diff도 달라질 수 있다. 최종 제출 시 백엔드는 수정된 결정을 기준으로 최종 변경을 계산해 반영한다. 운영자의 결정은 최종이므로 임시 diff와 달라진 변경도 반영한다. 다만 검수 데이터를 만든 뒤 현재 메뉴판이 바뀌었으면 반영하지 않고, 임시 diff를 다시 만들어 `review_version`을 올린 뒤 최신 검수 데이터를 다시 조회하게 한다. 현재 메뉴판의 항목은 운영자가 `apply`한 `remove`로만 빠진다. AI 누락 때문에 판매 중인 술이 자동으로 사라지는 것을 막고 전체 교체와 일부 수정 모두에서 사람이 최종 결과를 통제한다.

**최신 diff 유지 규칙:** 과거 임시 diff 이력은 보존하지 않는다. 최종 확정 전에 검수 데이터를 재생성하면 백엔드는 해당 `menu_import_id`의 기존 `menu_import_changes`를 삭제하고 새 `pending` 행들을 저장한 뒤 `menu_imports.review_version`을 증가시킨다. 이 세 작업은 하나의 트랜잭션으로 처리한다. 이전 화면의 `changeId`와 `reviewVersion`으로 제출된 요청은 거부한다. 최종 반영 때는 실제로 일어난 일이 남도록 행을 갱신한다. `ignore`한 행은 결정만 기록하고, `apply`한 행은 운영자 결정 때문에 최종 변경이 달라졌으면 그 종류와 대상으로 바꾸며(예: `add`가 `update`가 됨), 결과적으로 아무것도 바꾸지 않았으면 삭제한다. 임시 diff에 없던 변경은 `apply` 행으로 추가한다. 따라서 `applied`가 된 작업의 행은 AI가 처음 제안한 초안이 아니라 실제 반영된 변경과 무시한 제안의 기록이며, 이후에는 교체하지 않는다. 반영 응답의 `added`·`updated`·`removed`·`ignored` 개수도 이 행으로 센다. AI의 최초 판단은 `extracted_items`와 `resolution_candidates`에 남는다.

## 9 Evaluation Data

### 9.1 eval_sets

**역할:** Iteration별로 고정할 평가 이미지 묶음을 정의한다.

| 컬럼 | 타입과 제약 | 예시 | 설명과 필요한 이유 |
|---|---|---|---|
| `id` | `uuid`, PK | 평가 세트 ID | 평가 세트를 다른 세트와 구분한다. |
| `name` | `varchar(150)`, NOT NULL, UNIQUE | `Iteration 1 Held-out Set` | 사람이 알아볼 수 있는 고유 세트 이름이다. |
| `iteration_number` | `smallint`, nullable | `1` | 프로젝트 반복 단계별 성능을 비교한다. |
| `description` | `text`, nullable | `실제 메뉴 사진 10장` | 세트 선정 기준과 목적을 기록한다. |
| `frozen_at` | `timestamptz`, nullable | `2026-10-05T00:00:00Z` | 파이프라인 평가 전에 이미지 구성과 라벨을 동결한 시점이다. 데이터 누수를 방지한다. |
| `created_at` | `timestamptz`, NOT NULL | `2026-10-01T00:00:00Z` | 평가 세트 생성 시점이다. |

### 9.2 eval_samples

**역할:** 어떤 메뉴 이미지가 어떤 평가 세트에 포함되는지 나타내는 연결 테이블이다.

| 컬럼 | 타입과 제약 | 예시 | 설명과 필요한 이유 |
|---|---|---|---|
| `id` | `uuid`, PK | 평가 샘플 ID | 세트 구성 행을 식별한다. |
| `eval_set_id` | `uuid`, NOT NULL, FK → `eval_sets.id` | Iteration 1 세트 ID | 이미지가 속한 평가 세트다. |
| `menu_image_id` | `uuid`, NOT NULL, FK → `menu_images.id` | 실제 메뉴 이미지 ID | 평가할 원본 이미지를 연결한다. |
| `sample_kind` | `eval_sample_kind`, NOT NULL, 기본 `real` | `real` | 실제 이미지와 합성 엣지 케이스를 구분한다. |
| `added_at` | `timestamptz`, NOT NULL | `2026-10-01T01:00:00Z` | 이미지가 세트에 추가된 시점이다. |

**핵심 제약:** 같은 평가 세트에 같은 이미지를 중복 포함하지 않는다. 한 이미지는 여러 평가 세트에 재사용할 수 있다.

### 9.3 eval_ground_truth_items

**역할:** 메뉴 이미지에 대해 사람이 미리 만든 정답 상품 항목을 저장한다. 특정 모델 실행이 아니라 이미지에 연결되므로 여러 파이프라인을 같은 정답으로 평가할 수 있다.

| 컬럼 | 타입과 제약 | 예시 | 설명과 필요한 이유 |
|---|---|---|---|
| `id` | `uuid`, PK | 정답 상품 항목 ID | 정답 항목을 개별 식별한다. |
| `menu_image_id` | `uuid`, NOT NULL, FK → `menu_images.id` | 평가 이미지 ID | 어떤 이미지의 정답인지 연결한다. |
| `item_order` | `smallint`, NOT NULL | `7` | 이미지 안에서 정답 상품 항목의 원본 표시 순서를 보존한다. |
| `product_name_text` | `varchar(200)`, NOT NULL | `Deanston 12` | 사람이 확정한 정답 상품명이다. |
| `product_id` | `uuid`, nullable, FK → `products.id` | Deanston 12 상품 ID | entity resolution의 정답 상품이다. 카탈로그에 아직 없으면 임시로 null일 수 있다. |
| `annotated_at` | `timestamptz`, NOT NULL | `2026-10-01T02:00:00Z` | 정답 작성 시점이다. |

**핵심 제약:** 한 이미지에서 같은 `item_order`의 정답을 중복 저장하지 않는다.

### 9.4 eval_ground_truth_options

**역할:** 하나의 정답 상품 항목에 속한 가격·용량 선택지를 저장한다. `extracted_options`와 같은 계층으로 비교하므로 다중 옵션 정확도를 평가할 수 있다.

| 컬럼 | 타입과 제약 | 예시 | 설명과 필요한 이유 |
|---|---|---|---|
| `id` | `uuid`, PK | 정답 옵션 ID | 정답 가격·용량 조합을 개별 식별한다. |
| `ground_truth_item_id` | `uuid`, NOT NULL, FK → `eval_ground_truth_items.id` | Deanston 12 정답 항목 ID | 옵션이 속한 정답 상품을 연결한다. |
| `option_order` | `smallint`, NOT NULL | `2` | 같은 정답 상품 안에서 옵션의 원본 표시 순서를 보존한다. |
| `option_label` | `varchar(100)`, nullable | `Double` | ml로 표현되지 않는 옵션명의 정답이다. |
| `price_krw` | `integer`, nullable | `15000` | 가격 추출 정확도를 평가할 정답이다. |
| `pour_ml` | `smallint`, nullable | `30` | 용량 추출 정확도를 평가할 정답이다. |

**핵심 제약:** `(ground_truth_item_id, option_order)`는 unique다.

## 10 전체 예시

### 10.1 정규 상품과 업장 메뉴

```text
brands
  Deanston

brand_aliases
  Deanston
  딘스톤

products
  Deanston 12
  brand = Deanston
  age_years = 12
  edition_name = null

product_aliases
  Deanston 12YO
  Deanston Aged 12 Years
  딘스톤 12년

bar_menu_items
  관악 위스키 바 + Deanston 12

menu_board_entries
  표시명 = 딘스톤 12년

menu_entry_options
  15ml = 8,000원
  30ml = 15,000원
```

### 10.2 전체 교체 업로드

현재 메뉴판에 A B C가 있고 새 사진에는 A B D가 있다고 가정한다.

```text
menu_imports.mode = full_replace

menu_import_changes
  A = update 또는 변경 없음
  B = update 또는 변경 없음
  C = remove 후보
  D = add 후보
```

운영자가 diff에서 C 제거와 D 추가를 승인해야 현재 메뉴판에 반영된다. OCR이 C를 놓쳤다면 운영자는 C의 remove를 `ignore`해 유지할 수 있다.

### 10.3 일부 수정 업로드

현재 메뉴판에 A B C가 있고 새 사진에는 B의 새 가격과 D만 있다고 가정한다.

```text
menu_imports.mode = partial_update

menu_import_changes
  B = update 후보
  D = add 후보
```

A와 C는 사진에 없어도 remove 후보가 되지 않으며 현재 메뉴판에 남는다.

## 11 주요 관계 요약

| 부모 | 자식 | 관계 | 의미 |
|---|---|---|---|
| `users` | `bar_owner_applications` | 1:N | 한 사용자가 여러 업주 신청을 낼 수 있다. |
| `bars` | `bar_owner_applications` | 1:N | 한 업장에 여러 사용자가 신청할 수 있다. 새 업장 신청은 승인 전까지 업장이 없다. |
| `bar_owner_applications` | `bar_owners` | 1:0..1 | 승인된 신청 하나가 업주 관계 하나를 만든다. |
| `bar_owner_applications` | `bar_owner_application_menu_images` | 1:N | 한 신청에 메뉴판 사진 여러 장을 첨부할 수 있다. 승인하면 첫 메뉴 등록 작업의 사진이 된다. |
| `bars` | `bar_weekly_hours` | 1:0..7 | 요일마다 정규 영업시간이 최대 하나다. |
| `bars` | `bar_operating_exceptions` | 1:0..1 | 업장에는 임시 휴무가 없거나 하나만 있다. |
| `bars` | `bar_photos` | 1:N | 업장 하나에 매장 사진이 최대 15장이다. |
| `bars` + `users` | `bar_owners` | N:M 해소 | 한 사용자는 여러 업장의 업주가 될 수 있고, 한 업장에는 현재 업주가 최대 한 명이다. |
| `bars` | `menu_imports` | 1:N | 한 업장에 여러 메뉴 등록 작업이 누적된다. |
| `menu_imports` | `menu_images` | 1:N | 한 번의 등록에 여러 사진을 올릴 수 있다. |
| `menu_images` | `extraction_runs` | 1:1 | 구현 전에 선택한 방식으로 사진마다 실행 하나를 만든다. |
| `extraction_runs` | `extracted_items` | 1:N | 한 실행이 여러 상품 또는 비상품 항목을 추출한다. |
| `extracted_items` | `extracted_options` | 1:N | 한 상품 항목에 여러 가격·용량 옵션이 있다. 비상품 항목은 옵션이 없을 수 있다. |
| `extracted_items` | `resolution_candidates` | 1:N | 한 추출 상품 항목에 여러 정규 상품 후보가 있다. |
| `extracted_options` | `menu_entry_options` | 1:N 출처 연결 | 게시된 가격·용량 옵션이 어떤 AI 추출 옵션에서 만들어졌는지 추적한다. |
| `brands` | `products` | 1:N | 브랜드 하나에 여러 연수와 에디션 상품이 있다. |
| `products` | `product_aliases` | 1:N | 상품 하나에 여러 전체 이름 표기가 있다. |
| `bars` + `products` | `bar_menu_items` | N:M 해소 | 같은 상품을 여러 업장이 취급하고 한 업장은 여러 상품을 취급한다. |
| `bars` | `menu_boards` | 1:0..1 | 업장에는 현재 메뉴판이 없거나 하나만 있다. |
| `menu_boards` | `menu_board_entries` | 1:N | 현재 메뉴판은 여러 술 항목을 포함한다. |
| `menu_board_entries` | `menu_entry_options` | 1:N | 한 술에 여러 용량과 가격 옵션이 있다. |
| `eval_sets` | `eval_samples` | 1:N | 평가 세트 하나에 여러 이미지가 포함된다. |
| `menu_images` | `eval_ground_truth_items` | 1:N | 한 평가 이미지에 여러 정답 상품 항목이 있다. |
| `eval_ground_truth_items` | `eval_ground_truth_options` | 1:N | 한 정답 상품 항목에 여러 가격·용량 옵션이 있다. |

## 12 PostgreSQL DDL 작성 시 추가할 제약조건

DBML만으로 충분히 표현하기 어렵거나 현재 초안에 아직 명시하지 않은 규칙이다.

- `latitude`는 -90부터 90, `longitude`는 -180부터 180 범위여야 한다.
- `price_krw`는 0보다 커야 한다.
- `pour_ml`과 `age_years`는 null이 아니면 0보다 커야 한다.
- confidence와 score는 사용 범위에 따라 0부터 1 사이로 제한한다.
- `corrected_line_type`은 null이거나 `extracted_line_type`과 달라야 한다. 같은 역할을 승인한 경우에는 중복 저장하지 않는다.
- `initial_resolution_status`는 최초 AI 분류가 `product`여서 상품 매칭을 실행한 경우에만 후보 생성 완료 후 채운다. 일단 채운 값은 운영자 검수로 변경하지 않는다.
- `completed_at`은 `created_at` 이후여야 한다.
- 통합 검수 최종 제출 전에는 `menu_import_changes.decision = pending`인 행이 없어야 한다.
- 같은 메뉴판에 연결한 `bar_menu_item`은 해당 메뉴판의 `bar_id`와 같은 업장에 속해야 한다.
- 노출되는 `menu_board_entries`에는 `menu_entry_options`가 최소 하나 있어야 한다.
- 전체 교체 또는 일부 수정의 적용은 트랜잭션으로 처리해 메뉴판이 중간 상태로 노출되지 않게 한다.
- 최종 확정은 신규 브랜드·상품 중복 재검사와 생성, 추출 결과 확정, diff 재계산, 현재 메뉴판 반영을 모두 포함한 하나의 `SERIALIZABLE` 트랜잭션으로 실행한다. 직렬화 충돌이면 전체를 롤백하고 처음부터 최대 3회 재시도한다. AI 호출과 객체 저장소 작업 같은 외부 부수 효과는 재시도될 수 있는 이 트랜잭션 안에서 실행하지 않는다.
- 한 업장에는 `uploaded`, `processing`, `ready_for_review` 상태의 `menu_imports`가 동시에 하나만 존재해야 한다. PostgreSQL 부분 unique 인덱스와 업장 행 잠금·트랜잭션 검사를 함께 사용해 보장한다.
- 한 업장에는 `revoked_at IS NULL`인 `bar_owners`가 최대 하나여야 한다. PostgreSQL 부분 unique 인덱스로 보장한다.
- 한 사용자는 같은 업장에 `status = pending`인 `existing_bar` 신청을 하나만 가져야 한다. PostgreSQL 부분 unique 인덱스(`applicant_user_id`, `bar_id` WHERE `status = 'pending' AND application_type = 'existing_bar'`)로 보장한다.
- 한 사용자는 같은 사업자등록번호로 `status = pending`인 `new_bar` 신청을 하나만 가져야 한다. PostgreSQL 부분 unique 인덱스(`applicant_user_id`, `business_registration_number` WHERE `status = 'pending' AND application_type = 'new_bar'`)로 보장한다.
- `bar_owner_applications.business_registration_number`는 숫자 10자리여야 한다.
- `bars.tags`는 5개 이하여야 한다(`cardinality(tags) <= 5`).
- `bar_weekly_hours.day_of_week`는 1부터 7이고, `is_closed`이면 두 시각이 `null`, 아니면 둘 다 값이 있고 서로 달라야 한다.
- `bar_operating_exceptions`는 `end_date >= start_date`이고, `vacation`이 아니면 두 날짜가 같으며, `custom_hours`일 때만 두 시각이 있고 서로 달라야 한다.
- 한 업장의 `bar_photos`에서 `content_sha256`이 중복되지 않아야 한다. unique 인덱스(`bar_id`, `content_sha256`)로 보장한다.
- 한 신청의 `bar_owner_application_menu_images`에서 `image_order`가 중복되지 않아야 한다. unique 인덱스(`application_id`, `image_order`)로 보장한다.
- 외래키 삭제 정책은 이력 보존을 우선해 핵심 사용자 업장 상품 이미지에 `RESTRICT` 또는 soft delete를 검토한다.

> **현재 구현과의 차이 (수정 예정):** 지금 Alembic 마이그레이션에는 업장 좌표 범위(`ck_bars_latitude_range`, `ck_bars_longitude_range`)를 제외한 위의 `CHECK` 제약과 부분 unique 인덱스가 없다. 그동안은 백엔드가 다음처럼 규칙을 지킨다. 위 제약을 추가하는 마이그레이션을 만들 예정이며, 그 전에 기존 데이터가 규칙을 어기지 않는지 확인한다.
>
> - 가격·용량·연수·신뢰도·점수 범위: 요청 스키마와 추출 어댑터가 검사한다.
> - `corrected_line_type`: 최초 분류와 같으면 백엔드가 `null`로 저장한다. `completed_at`은 백엔드가 항상 나중 시각으로 기록한다.
> - 최종 제출 전 `pending` 변경: 모든 변경에 결정이 없으면 `422 MISSING_CHANGE`로 거부한다.
> - 메뉴판 항목의 업장 일치와 옵션 최소 1개: 게시 코드가 해당 업장의 항목만 쓰고, 가격 있는 옵션이 없으면 `NO_PRICED_OPTION`으로 거부한다.
> - 업장당 미완료 작업 하나: 업장 행 잠금과 확인만 있고 부분 unique 인덱스는 없다.
> - 삭제 정책: 외래키에 cascade가 없어(PostgreSQL 기본 `NO ACTION`) 이력이 참조하는 행은 삭제되지 않는다.

## 13 아직 확정되지 않은 항목

- PostgreSQL `uuid` 값의 버전과 생성 위치
- 고객 로그인 후 제공할 추가 기능과 관련 테이블
- 공간 검색을 일반 위도 경도로 계산할지 공간 타입과 인덱스를 사용할지
- enum을 DB enum으로 구현할지 문자열과 CHECK 제약으로 구현할지
- 가격이 반드시 존재해야 하는지, `가격 문의` 같은 값을 허용할지
- 상품 `category`를 자유 문자열로 유지할지 별도 Enum 또는 테이블로 분리할지
- 한 메뉴 이미지에 동일 상품이 여러 줄 등장할 때 하나의 메뉴 항목과 여러 옵션으로 합치는 기준
- 같은 상품이 서로 다른 메뉴 섹션에 중복 노출되는 것을 허용할지

## 14 현재 MVP 범위 밖 기능

요구사항이 추가되지 않는 한 다음 기능은 현재 스키마에 포함하지 않는다.

- 사용자 리뷰와 평점
- 개인화 추천
- 소셜 피드
- 가격 변동 알림
- 오래된 메뉴 신고
- 자연어 검색 기록
- 위스키 이외 카테고리의 상세 전용 속성
- 업주 정산 또는 구독
- 과거 게시 메뉴판의 완전한 버전 이력

## 15 설계 관리 원칙

- `schema_draft.dbml`을 현재 논리 스키마의 source of truth로 사용한다.
- 스키마를 변경할 때 DBML을 먼저 수정하고 이 가이드의 관련 설명과 예시를 함께 갱신한다.
- 확정된 요구사항과 충돌하는 변경은 충돌 내용을 먼저 확인한 뒤 반영한다.
- 모호한 설계 결정은 스키마에 미치는 영향과 선택지 차이를 확인한 후 결정한다.
- PostgreSQL을 기준으로 설계하되 DBML에서는 의미가 분명한 논리 타입을 우선한다.
- 사용자가 요청하기 전에는 DDL을 만들지 않는다.
- DDL이 필요할 때는 DBML에서 파생하며 별도의 수동 스키마를 만들지 않는다.
- 기존에 확정된 요구사항은 새로운 결정과 충돌하는 경우에만 다시 검토한다.

## 16 다음 우선 검토 항목

1. `menu_import_changes`가 여러 가격 옵션의 변경 전 값과 변경 후 값을 충분히 표현하는지 검토한다.
2. `extracted_items`와 `extracted_options`의 검수 결과를 현재 메뉴판에 원자적으로 적용하는 트랜잭션 경계를 정한다.
3. DBMS와 무관하게 DBML 주석으로 먼저 명시할 수 있는 도메인 제약을 검토한다.
4. 메뉴 검수 중 생성된 상품을 운영자 대시보드에서 식별하고 관리하는 기준을 정한다.

