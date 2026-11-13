# BottleMap 프론트엔드-백엔드 API 명세 초안

## 1. 목적과 범위

이 문서는 메뉴판 사진 등록부터 통합 검수와 현재 메뉴판 반영까지, 현재 메뉴판의 직접 편집, 그리고 고객의 상품 검색, 주변·지도 업장 조회와 업장 메뉴 조회에서 프론트엔드와 백엔드가 주고받는 HTTP API를 정의한다.

포함 범위:

- Google 로그인 후 BottleMap 사용자 확인, 인증 오류 처리
- 업주 신청(사업자등록증 사진 읽기, 사업자등록 정보 1차 검증), operator 승인과 업주 권한
- 메뉴 사진 업로드와 비동기 처리 시작
- 처리 상태 polling
- 추출 항목·옵션·상품 후보·임시 diff 통합 조회
- 검수 중 브랜드와 상품 검색
- 검수 중 입력의 초안 저장과 불러오기
- 모든 검수 결정의 일괄 제출과 메뉴 반영
- 현재 메뉴판 항목의 직접 추가, 수정, 삭제와 초기화, 품절, 기간 할인, 판매 정보 확인
- 매장 정보(한 줄 소개, 태그, 정규 영업시간), 임시 휴무, 매장 사진
- 고객의 상품 검색, 주변·지도 업장 조회와 업장 상세 메뉴 조회
- 운영자의 메뉴 항목 확인과 상품 연결
- 고객 홈 화면의 "요즘 많이 찾는 위스키"와 이를 위한 검색 집계
- 멱등성, 검수 버전 충돌과 공통 오류 응답

제외 범위:

- 백엔드와 OCR·LLM·Vision LLM 사이의 요청
- 백엔드와 국세청 사업자등록정보 API 사이의 요청
- 작업 큐와 AI 워커 내부 통신
- 운영자용 카탈로그 일반 CRUD
- SSE와 WebSocket

메뉴 등록은 MVP에서 다음 흐름을 사용한다.

```text
POST 메뉴 등록
→ 202 Accepted
→ GET 상태 polling
→ ready_for_review 통합 응답 표시
→ 필요한 브랜드·상품 검색
→ POST review-and-apply 한 번 제출
→ applied
```

고객 홈 화면은 다음 흐름을 사용한다.

```text
GET 요즘 많이 찾는 위스키 (3.17)
→ 검색창, 최근 검색(기기에 저장), 인기 위스키 카드, 지도로 보기 표시
→ 검색하면 GET 상품 검색 (3.10, query), 카드를 고르면 같은 API를 productId로
→ 지도로 보기를 고르면 지도 화면 (3.13)
```

고객 검색은 다음 흐름을 사용한다.

```text
GET 상품 검색 (검색어 + 선택적 위치)
→ 결과 목록 표시
→ 결과 선택
→ GET 업장 메뉴 조회로 업장 상세 표시
```

주변 업장 조회는 다음 흐름을 사용한다.

```text
GET 주변 업장 조회 (위치 + 반경)
→ 목록과 지도 표시
→ 업장 선택
→ GET 업장 메뉴 조회로 업장 상세 표시
```

지도 화면은 다음 흐름을 사용한다.

```text
지도 카메라 이동이 멈춤
→ GET 지도 영역 업장 조회 (화면 영역)
→ 마커와 목록 표시
→ (선택) GET 업장 이름 검색으로 업장을 찾아 그 위치로 지도 이동
→ 업장 선택
→ GET 업장 메뉴 조회로 업장 상세 표시
```

## 2. 공통 규칙

### 2.1 기본 형식

- 기본 경로: `/api`
- 인증: `Authorization: Bearer <access-token>` (Supabase access token, 3.1)
- 업로드 외 요청과 응답: `application/json`
- 업로드 요청: `multipart/form-data`
- 외부 API 필드명: `camelCase`
- ID: 문자열로 표현한 UUID
- 시각: UTC 기준 RFC 3339 문자열. 예외로 영업시간과 임시 휴무(3.15)의 시각과 날짜는 서울 현지 값을 `"HH:MM"`과 `"YYYY-MM-DD"` 문자열로 쓴다. 특정 순간이 아니라 매주 반복되는 시각이나 달력 날짜라서 UTC로 바꿀 수 없기 때문이다
- 가격: 원 단위 정수
- 좌표: WGS84 위도·경도를 십진 도 숫자로 표현한다. `latitude`는 -90~90, `longitude`는 -180~180이고 소수점 아래 6자리까지 저장한다. 응답의 업장 좌표는 `null`이 아니다(3.9.4)
- 퍼센트·점수: 별도 표기가 없으면 `0.0`부터 `1.0`
- 값이 없다는 의미는 빈 문자열이 아니라 `null`

### 2.2 권한

호출자는 다음 넷으로 나뉜다.

- **비로그인 사용자**: `Authorization` 헤더 없이 호출한다.
- **customer**: 로그인한 일반 사용자(`userType = customer`).
- **업주**: 운영자 승인을 받아 특정 업장을 관리하는 사용자(3.11). `userType`이 아니라 업장별 관계이므로, 같은 사용자도 자기 업장에서만 업주다. 보통 `userType = customer`다.
- **operator**: 프로젝트 운영자(`userType = operator`). 모든 업장을 관리한다.

| API | 비로그인 | customer | 해당 업장의 업주 | operator |
|---|---|---|---|---|
| `GET /api/search/bars`, `GET /api/search/nearby-bars`, `GET /api/search/map-bars`, `GET /api/search/bar-names`, `GET /api/search/popular-products` | O | O | O | O |
| `GET /api/bars/{barId}/menu` | 활성 업장만 | 활성 업장만 | O | O |
| `GET /api/bar-photos/{photoId}`, `GET /api/bar-photos/{photoId}/thumbnail` | O | O | O | O |
| `GET /api/me`, `PATCH /api/me`, `GET /api/me/bars` | | O | O | O |
| `POST /api/owner-applications`, `GET /api/me/owner-applications`, `POST /api/owner-applications/business-certificate-ocr`, `POST /api/owner-applications/business-verification` | | O | O | O |
| `GET /api/owner-applications/{applicationId}` | | 본인 신청만 | 본인 신청만 | O |
| `POST /api/owner-applications/{applicationId}/cancel`, `PUT /api/owner-applications/{applicationId}/menu-photos`, `PUT`과 `DELETE /api/owner-applications/{applicationId}/cover-photo` | | 본인 신청만 | 본인 신청만 | 본인 신청만 |
| `GET /api/owner-applications`, `POST .../approve`, `POST .../reject`, `POST .../verify-business` | | | | O |
| `DELETE /api/bars/{barId}/owner` | | | | O |
| `GET /api/menu-item-checks`, `POST /api/menu-item-checks/{checkId}/resolve` | | | | O |
| `GET /api/bars`, `POST /api/bars`(지금은 구현하지 않음, 3.5) | | | | O |
| `GET /api/bars/{barId}` | | | O | O |
| `PATCH /api/bars/{barId}` | | | O (`status` 제외) | O |
| `GET /api/bars/{barId}/menu-imports`, `POST /api/bars/{barId}/menu-imports` | | | O | O |
| `POST /api/bars/{barId}/menu/items`, `PUT .../menu/items/{barMenuItemId}`, `DELETE .../menu/items/{barMenuItemId}`, `POST /api/bars/{barId}/menu/reset` | | | O | O |
| `PUT /api/bars/{barId}/menu/items/{barMenuItemId}/sold-out`, `POST /api/bars/{barId}/menu/confirm` | | | O | O |
| `PUT /api/bars/{barId}/operating-exception`, `DELETE /api/bars/{barId}/operating-exception` | | | O | O |
| `POST /api/bars/{barId}/photos`, `DELETE .../photos/{photoId}`, `PUT .../photos/order` | | | O | O |
| `GET /api/menu-imports/{menuImportId}`, `PUT .../review-draft`, `POST .../review-and-apply`, `POST .../cancel` | | | 해당 업장의 작업만 | O |
| `GET /api/catalog/brands`, `GET /api/catalog/products` | | | 업장이 하나 이상이면 O | O |
| `POST /api/auth/temp-login` | 임시 로그인이 켜진 서버에서만 O (3.1.3) | 같음 | 같음 | 같음 |
| `GET /health` | O | O | O | O |

`/media/{key}`는 로컬 저장소를 쓰는 개발 환경에서만 있는 사진 파일 경로이며 API 계약이 아니다. 배포 서버(S3)에는 없다. 매장 사진은 이 경로가 아니라 `GET /api/bar-photos/{photoId}`와 `GET /api/bar-photos/{photoId}/thumbnail`(3.16.5)로 전달하며, 이 경로는 모든 환경에 있다.

`/admin/`은 operator 웹 대시보드의 정적 파일(HTML, JS, CSS)이며 API 계약이 아니다. 페이지가 브라우저에서 Supabase Google 로그인을 하고 3.11의 API를 그대로 호출하므로, 권한은 위 표와 같다(operator만 신청 목록을 보고 승인·거절한다). 메뉴 항목 확인 화면도 같은 방식으로 3.18의 API를 호출한다. `/admin/config.js`는 페이지에 공개 설정만 준다: Supabase 프로젝트 URL과 publishable key, 그리고 `new_bar` 승인 화면의 지도와 주소 검색에 쓰는 Kakao JavaScript 키(등록한 도메인에서만 동작). 좌표는 브라우저에서 Kakao Maps JavaScript SDK로 찾으며 백엔드 API는 쓰지 않는다. 승인 요청(3.11.7)의 `latitude`, `longitude`는 지금과 같다.

인증이 필요한 요청에서 백엔드는 다음 순서로 검증한다. 단, JSON 본문을 읽을 수 없거나 multipart 본문의 구조(경계 문자열 등)가 깨졌으면 이 순서와 관계없이 먼저 `400 INVALID_REQUEST`다(9.2).

1. token이 유효한가 (아니면 `401`, 3.1.5)
2. operator 전용 API는 호출자가 operator인가 (아니면 `403 FORBIDDEN`). 대상이 있는지는 그다음에 확인하므로, operator가 아닌 호출자는 없는 `barId`나 `menuImportId`를 보내도 `403`이다. 업장 정보는 공개 API로 이미 볼 수 있어 존재 여부를 숨길 필요가 없다.
3. 요청한 `barId`, `menuImportId`, `applicationId`가 존재하는가 (아니면 각 API의 `404`)

업장별 권한은 대상 업장을 알아야 판단할 수 있다. 그래서 업주도 호출할 수 있는 API는 3번을 먼저 확인한 뒤 "호출자가 operator이거나 대상 업장의 현재 업주인가"(아니면 `403`)를 확인한다. 이 API들에서는 operator나 업주가 아닌 호출자도 없는 `barId`나 `menuImportId`를 보내면 `404`를 받는다. 메뉴 등록 작업은 작업이 속한 업장의 업주인지 확인한다. 카탈로그 검색은 대상이 없으므로 현재 업주인 업장이 하나 이상인지 확인한다.

업주 여부는 매 요청 DB에서 확인하므로 승인과 해제가 다음 요청부터 반영된다. 업주 신청은 다른 사람의 신청이 있는지 알리지 않도록 권한이 없을 때도 `404 OWNER_APPLICATION_NOT_FOUND`를 반환한다(3.11.4).

### 2.3 주요 Enum

`MenuImportStatus`

```text
uploaded
processing
ready_for_review
applied
failed
canceled
```

`uploaded`, `processing`, `ready_for_review`는 미완료 상태이고, `applied`, `failed`, `canceled`는 최종 상태다.

`ImportMode`

```text
full_replace
partial_update
```

`LineType`

```text
product
section_header
description
unknown
```

`InitialResolutionStatus`

```text
exact_match
ambiguous
unmatched
```

`MatchMethod`

```text
alias
embedding
llm
manual
```

`MenuItemKind`

```text
whisky
other
```

메뉴 항목의 종류다. `whisky`는 위스키 메뉴로, 상품에 연결되어 있거나 운영자의 연결을 기다린다. `other`는 진토닉, 콜라 같은 위스키가 아닌 메뉴로, 상품에 연결하지 않는다. 상품에 연결된 항목은 항상 `whisky`다. AI가 메뉴판 줄마다 1차로 판단한 종류(5.4의 `extractedKind`)도 같은 값을 쓴다.

`ChangeType`

```text
add
update
remove
```

`ChangeDecision`

```text
apply
ignore
```

### 2.4 실제 응답 예시

3.11.18, 3.14.10, 3.15.7, 3.16.7, 5.8, 8.9의 예시는 2026-11-09에 로컬 서버(`uvicorn`, PostgreSQL, mock 메뉴 추출기)를 띄우고 HTTP로 호출해 받은 응답이다. 다른 절의 예시는 설명을 위해 손으로 쓴 값이다.

- 바꾼 값은 다음뿐이다. 나머지(필드, 순서, 시각, 문구, 숫자)는 받은 그대로다.
  - **ID**: 문서의 자리표시 ID로 바꾸었다. 첫 글자로 종류를 나눈다: 사용자 `1111…`, 업장 `2222…`, 상품 `4444…`, 메뉴 항목 `5555…`, 메뉴판 `6666…`, 메뉴 등록 작업 `7777…`, 업주 신청 `cccc…`, 브랜드 `dddd…`, 매장 사진 `aaaa…`, 추출 항목 `1000…`, 추출 옵션 `2000…`, 변경 `3000…`, 저장소 경로에만 나오는 ID `ffff…`. 같은 ID는 문서 전체에서 같은 값이다.
  - **호스트**: `http://127.0.0.1:8000/`을 `https://bottlemap.o-r.kr/`로 바꾸었다.
  - **비공개 사진 URL**: 로컬 저장소의 `http://127.0.0.1:8000/media/...`을 `https://storage.example.com/signed/...`로 바꾸었다. 로컬 저장소는 만료되지 않는 URL을 주므로 `imageUrlExpiresAt`이 `null`이다. 배포 서버(S3)에서는 만료 시각이 들어 있다.
- 국세청 진위확인(3.11.2, 3.11.13, 3.11.16)만 가짜 검증기로 바꾸어 `matched`, `not_matched`, 연결 실패를 만들었다. 사업자등록증 OCR(3.11.12)은 서버에 설정이 없는 상태의 응답이다.
- 호출자별 결과 표의 열은 다음 사용자다. 칸의 값은 실제로 받은 HTTP 상태 코드다.
  - **비로그인**: `Authorization` 헤더 없음
  - **customer**: 어느 업장의 업주도 아닌 `customer`
  - **다른 업장의 업주**: 대상이 아닌 업장(신림 몰트 하우스)의 업주
  - **해당 업장의 업주**: 대상 업장(관악 위스키 바, `22222222-2222-4222-8222-222222222222`)의 업주
  - **operator**: 업주가 아닌 `operator`
- 모든 API에서 같은 `401`과 `403` 본문은 아래에 한 번만 싣는다.

`401 UNAUTHENTICATED` (3.1.5). `code`와 형식은 같고 `message`만 다르다.

토큰 없음

```json
{"error": {"code": "UNAUTHENTICATED", "message": "로그인이 필요합니다.", "details": null, "fieldErrors": []}}
```

토큰 만료, 서명 오류 등 토큰을 받아들일 수 없음

```json
{"error": {"code": "UNAUTHENTICATED", "message": "로그인 정보가 만료되었거나 올바르지 않습니다. 다시 로그인해 주세요.", "details": null, "fieldErrors": []}}
```

`403 FORBIDDEN` (operator 전용 API, 또는 operator도 대상 업장의 업주도 아님)

```json
{"error": {"code": "FORBIDDEN", "message": "이 작업을 할 권한이 없습니다.", "details": null, "fieldErrors": []}}
```

## 3. API 요약

| 메서드 | 경로 | 용도 |
|---|---|---|
| `POST` | `/api/auth/temp-login` | 로컬 개발용 임시 access token 발급 (기본 비활성화) |
| `GET` | `/api/me` | 로그인 사용자와 권한 조회 및 최초 사용자 동기화 |
| `PATCH` | `/api/me` | 로그인 사용자 표시 이름 수정 |
| `GET` | `/api/bars` | 운영 대상 업장 목록 및 검색 |
| `POST` | `/api/bars` | 업장 생성. 지금은 구현하지 않는다(3.5) |
| `GET` | `/api/bars/{barId}` | 관리자용(operator, 업주) 업장 상세와 관리 상태 조회 |
| `PATCH` | `/api/bars/{barId}` | 업장 정보 또는 활성 상태 수정 |
| `GET` | `/api/bars/{barId}/menu-imports` | 업장의 진행 중·과거 메뉴 등록 작업 조회 |
| `GET` | `/api/bars/{barId}/menu` | 업장 정보와 현재 게시 메뉴판 조회 (공개) |
| `GET` | `/api/search/bars` | 고객 상품 검색과 판매 업장 목록 조회 (공개) |
| `GET` | `/api/search/nearby-bars` | 고객 위치 반경 안의 활성 업장 조회 (공개) |
| `GET` | `/api/search/map-bars` | 지도 화면 영역 안의 활성 업장 조회 (공개) |
| `GET` | `/api/search/popular-products` | 홈 화면의 요즘 많이 찾는 위스키 (공개) |
| `POST` | `/api/bars/{barId}/menu-imports` | 사진 업로드와 AI 처리 작업 생성 |
| `GET` | `/api/menu-imports/{menuImportId}` | 처리 상태 또는 통합 검수 데이터 조회 |
| `GET` | `/api/catalog/brands` | 검수 중 기존 브랜드 검색 |
| `GET` | `/api/catalog/products` | 검수 중 기존 상품 검색 |
| `PUT` | `/api/menu-imports/{menuImportId}/review-draft` | 검수 중 입력의 초안 저장 |
| `POST` | `/api/menu-imports/{menuImportId}/review-and-apply` | 전체 검수 결정 제출과 원자적 반영 |
| `POST` | `/api/menu-imports/{menuImportId}/cancel` | 미완료 메뉴 등록 작업 취소 |
| `POST` | `/api/bars/{barId}/menu/items` | 메뉴 항목 직접 추가 (필요하면 신규 상품 생성) |
| `PUT` | `/api/bars/{barId}/menu/items/{barMenuItemId}` | 메뉴 항목 직접 수정 |
| `DELETE` | `/api/bars/{barId}/menu/items/{barMenuItemId}` | 메뉴 항목 직접 삭제 |
| `POST` | `/api/bars/{barId}/menu/reset` | 메뉴판 초기화 |
| `PUT` | `/api/bars/{barId}/menu/items/{barMenuItemId}/sold-out` | 메뉴 항목 품절 표시와 해제 |
| `POST` | `/api/bars/{barId}/menu/confirm` | 판매 정보 확인 ("지금도 맞아요") |
| `PUT` | `/api/bars/{barId}/operating-exception` | 임시 휴무나 오늘 영업시간 변경 적용 (기존 것을 바꿈) |
| `DELETE` | `/api/bars/{barId}/operating-exception` | 임시 휴무 취소 |
| `POST` | `/api/bars/{barId}/photos` | 매장 사진 한 장 추가 |
| `DELETE` | `/api/bars/{barId}/photos/{photoId}` | 매장 사진 삭제 |
| `PUT` | `/api/bars/{barId}/photos/order` | 매장 사진 순서 변경 (첫 사진이 대표 사진) |
| `GET` | `/api/bar-photos/{photoId}` | 매장 사진 파일 (공개) |
| `GET` | `/api/bar-photos/{photoId}/thumbnail` | 매장 사진 썸네일 파일 (공개) |
| `GET` | `/api/search/bar-names` | 업장 이름·주소 검색. 업주 신청과 고객 지도 검색용 (공개) |
| `POST` | `/api/owner-applications/business-certificate-ocr` | 사업자등록증 사진에서 신청 항목 읽기 |
| `POST` | `/api/owner-applications/business-verification` | 신청 전 사업자등록 정보 확인. 신청은 만들지 않는다 |
| `POST` | `/api/owner-applications` | 업주 신청과 사업자등록 정보 1차 검증 |
| `GET` | `/api/me/owner-applications` | 내 업주 신청 목록 |
| `GET` | `/api/owner-applications/{applicationId}` | 업주 신청 상세 |
| `POST` | `/api/owner-applications/{applicationId}/cancel` | 업주 신청 취소 |
| `PUT` | `/api/owner-applications/{applicationId}/menu-photos` | 업주 신청의 메뉴판 사진 올리기 (전체 교체) |
| `PUT` | `/api/owner-applications/{applicationId}/cover-photo` | 새 업장 신청의 대표 사진 올리기 (교체) |
| `DELETE` | `/api/owner-applications/{applicationId}/cover-photo` | 새 업장 신청의 대표 사진 삭제 |
| `GET` | `/api/owner-applications` | operator의 업주 신청 목록 |
| `POST` | `/api/owner-applications/{applicationId}/approve` | 업주 신청 승인 |
| `POST` | `/api/owner-applications/{applicationId}/reject` | 업주 신청 거절 |
| `POST` | `/api/owner-applications/{applicationId}/verify-business` | 사업자등록 정보 다시 검증 |
| `GET` | `/api/me/bars` | 내가 업주인 업장 목록 |
| `DELETE` | `/api/bars/{barId}/owner` | 업주 해제 |
| `GET` | `/api/menu-item-checks` | 운영자가 확인할 메뉴 항목 목록 |
| `POST` | `/api/menu-item-checks/{checkId}/resolve` | 메뉴 항목 확인 처리 (상품 연결 등) |

별도의 신규 브랜드·상품 생성 API는 두지 않는다. 신규 카탈로그 데이터는 `review-and-apply` 요청(8.5, 8.6)이나 메뉴 항목 직접 추가 요청(3.14.3) 안에서 제안하고, 그 요청의 트랜잭션에서 생성한다.

### 3.1 로그인과 토큰 검증

BottleMap은 로그인 API를 직접 제공하지 않는다. Google 로그인과 토큰 발급·갱신·로그아웃은 Supabase Auth의 Google provider와 Supabase SDK가 담당하고, BottleMap 백엔드는 Supabase가 발급한 access token을 검증만 한다. `users`에는 비밀번호 컬럼이 없고, Supabase 사용자 ID(token의 `sub`)를 `auth_subject`에 저장한다.

사용자는 다음과 같이 구분한다.

- **비로그인 사용자(익명 사용자)**: 로그인하지 않은 사용자다. `Authorization` 헤더 없이 공개 API(`GET /api/search/bars`, `GET /api/search/nearby-bars`, `GET /api/search/map-bars`, `GET /api/search/bar-names`, `GET /api/search/popular-products`, `GET /api/bars/{barId}/menu`, `GET /api/bar-photos/{photoId}`와 그 `/thumbnail`)만 호출하며 `users` 행을 만들지 않는다.
- **로그인 사용자**: Google 계정으로 로그인한 사용자다. 최초 `GET /api/me` 호출 때 `customer`로 생성된다.
- Supabase의 익명 로그인(anonymous sign-in)은 사용하지 않는다. `is_anonymous = true`인 token은 `401`로 거부한다.

#### 3.1.1 로그인부터 첫 API 호출까지

```text
[Android]
1. Credential Manager로 Google 계정 선택
   - setServerClientId(<Google Web client ID>)   ← Android client ID가 아니라 Web client ID
   - 무작위 rawNonce를 만들고 SHA-256 hex 값을 setNonce로 전달
2. Google ID token 수신
3. Supabase SDK로 ID token 로그인 (provider = Google, idToken, nonce = rawNonce)
4. Supabase 세션 수신 (access token, refresh token). 세션 저장과 자동 갱신은 SDK가 담당
5. GET /api/me
   Authorization: Bearer <Supabase access token>
6. 응답의 userType으로 고객 화면과 운영자 화면 분기. 업주 화면은 GET /api/me/bars가 비어 있지 않을 때 보여 줌(3.11.9)

[BottleMap 백엔드]
1. Supabase JWKS 공개 키로 token 서명 검증 (header의 kid로 키 선택)
2. iss, aud, exp 검증, sub 존재 확인, is_anonymous가 true가 아닌지 확인
3. sub로 users.auth_subject 조회
4. GET /api/me에서 행이 없으면 customer 사용자 생성 (3.2)
5. user_type과 요청 대상 권한은 BottleMap DB 기준으로 검사
```

#### 3.1.2 Supabase access token 검증 규칙

| 항목 | 값 | 비고 |
|---|---|---|
| 서명 키 | `GET {SUPABASE_URL}/auth/v1/.well-known/jwks.json` | header의 `kid`로 키를 고른다 |
| 알고리즘 | `ES256` | Supabase 프로젝트는 ES256 비대칭 signing key로 설정한다(3.1.6). 레거시 HS256 secret은 JWKS에 공개되지 않으므로 받지 않는다 |
| `iss` | `{SUPABASE_URL}/auth/v1` | 예: `https://<project-ref>.supabase.co/auth/v1` |
| `aud` | `authenticated` | |
| 필수 claim | `exp`, `iat`, `sub`, `iss`, `aud` | 하나라도 없으면 `401` |
| `exp`, `iat` 여유 | 30초 | Supabase와 서버의 시계 차이로 막 발급된 token(`iat`가 조금 미래)이나 막 만료된 token을 거부하지 않도록 둔다 |
| `is_anonymous` | `true`면 거부 | Supabase 익명 로그인 token |

- JWKS 응답은 20분보다 오래 캐시하지 않는다(현재 10분). 캐시에 없는 `kid`가 오면 JWKS를 한 번 다시 조회한다. 키 교체 직후에도 정상 token을 거부하지 않기 위해서다. 다시 조회는 30초에 한 번까지만 하므로, 지어낸 `kid`를 반복해 보내도 Supabase를 계속 호출하지 않는다.
- token의 `role`(`authenticated`)은 Supabase의 Postgres 역할이며 BottleMap의 `userType`이 아니다. 백엔드는 권한 판단에 사용하지 않는다.
- `user_metadata`는 사용자가 직접 바꿀 수 있는 값이다. 표시 이름의 초기값으로만 쓰고 권한 판단에는 사용하지 않는다.
- access token 수명은 Supabase 프로젝트 설정을 따르며 기본값은 1시간이다. 로그아웃하면 Supabase 세션은 삭제되지만 이미 발급된 access token은 `exp`까지 서명 검증을 통과한다. 백엔드는 세션 삭제 여부를 따로 확인하지 않으므로 프론트엔드는 로그아웃할 때 저장된 token을 함께 버린다.

#### 3.1.3 임시 로그인 (로컬 개발용)

로컬 개발을 위해 `POST /api/auth/temp-login`을 유지한다. 이 API는 명시적으로 활성화해야 하며, 고정된 `local-dev-user` subject로 짧은 만료 시간의 HS256 JWT를 발급한다. 이 token은 Supabase access token이 아니다.

배포 서버에서는 앱에서 Google 로그인이 가능해질 때까지만 데모용으로 켜 두었고, 2026-11-02에 껐다(`TEMP_AUTH_ENABLED=false`). 배포 서버에서는 다시 켜지 않는다. 켜져 있으면 서버에 접근하는 누구나 같은 임시 계정을 공유하며, `TEMP_AUTH_USER_TYPE=operator`이면 operator 권한을 얻는다. 켜져 있는 동안 서버는 시작할 때마다 경고 로그를 남긴다. 배포 서버 설정은 `backend/DEPLOY.md`를 따른다.

개발 환경에서 `TEMP_AUTH_ENABLED=true`와 32자 이상의 로컬 `TEMP_AUTH_JWT_SECRET`을 설정한 뒤 호출한다. 요청 본문은 없으며, 응답은 세 시간 동안 유효한 bearer token이다.

```http
POST /api/auth/temp-login
```

```json
{
  "accessToken": "<local-development-jwt>",
  "tokenType": "bearer",
  "expiresIn": 10800
}
```

- 백엔드는 `iss = bottlemap-local`인 token을 임시 token으로 보고 `TEMP_AUTH_JWT_SECRET`으로 HS256 검증한다. 그 밖의 token은 3.1.2 규칙으로 검증한다. `TEMP_AUTH_ENABLED`가 `true`가 아니면 임시 token은 `401`이다.
- 임시 사용자도 `auth_subject = local-dev-user`인 `users` 행을 가지며, 다른 사용자처럼 최초 `GET /api/me` 호출 때 생성된다.
- 임시 사용자의 `user_type`은 `TEMP_AUTH_USER_TYPE=customer|operator` 서버 환경 변수를 따른다. 값을 바꾸면 이미 발급된 token에도 다음 요청부터 반영된다. 발급한 token에 남아 있는 `user_type` claim은 검증과 권한 판단에 쓰지 않는다. 요청에서 역할을 선택할 수는 없다.

| 상황 | 응답 |
|---|---|
| `TEMP_AUTH_ENABLED`가 `true`가 아님 | `POST /api/auth/temp-login`이 `404 NOT_FOUND`. API가 없는 것처럼 응답한다 |
| `TEMP_AUTH_JWT_SECRET`이 32자 미만이거나 `TEMP_AUTH_USER_TYPE`이 `customer`·`operator`가 아님 | `POST /api/auth/temp-login`이 `503 SERVICE_UNAVAILABLE` |
| 임시 token을 받았지만 서버의 `TEMP_AUTH_JWT_SECRET`이 없거나 32자 미만, 또는 `TEMP_AUTH_USER_TYPE`이 `customer`·`operator`가 아님 | 토큰이 필요한 API가 `503 SERVICE_UNAVAILABLE` |

#### 3.1.4 기본 사용자 유형과 운영자 권한

- 최초 가입한 사용자는 항상 `customer`다. 신규 가입자를 자동으로 `operator`로 만들지 않는다.
- 클라이언트 요청이나 token claim(`user_metadata` 포함)으로 `userType`을 바꿀 수 없다. 권한은 매 요청 BottleMap DB의 `users.user_type`에서 읽는다.
- `operator` 전환은 이후 별도 기능으로 정의하며 이 문서의 범위가 아니다. 그전까지 로컬에서 operator API를 시험할 때는 임시 로그인과 `TEMP_AUTH_USER_TYPE=operator`를 사용한다. 배포 서버에서는 백엔드 담당자가 DB의 `users.user_type`을 직접 고쳐야만 operator 역할이 부여되며, 바꾼 역할은 해당 사용자의 다음 요청부터 반영된다.
- 업주는 `userType`이 아니라 업장별 관계다. 신청과 승인은 3.11, 권한은 2.2를 따른다.
- `GET /api/me`만 사용자를 생성한다. `users` 행이 없는 사용자가 다른 인증 API를 먼저 호출하면 `customer`와 같게 처리하므로, operator나 업주 권한이 필요한 API는 `403 FORBIDDEN`이다. `PATCH /api/me`와 `POST /api/owner-applications`, 그리고 임시 로그인 operator의 업주 신청 승인, 거절과 업주 해제는 `404 USER_NOT_FOUND`다(3.3, 3.11.2, 3.11.7, 3.11.10).

#### 3.1.5 인증 오류와 프론트엔드 처리

인증 오류는 9.1의 공통 오류 형식을 사용한다. 원인이 달라도 `401`은 모두 `UNAUTHENTICATED` 한 가지 code이고, 응답 header에 `WWW-Authenticate: Bearer`가 포함된다. 프론트엔드는 `message`로 원인을 구분하지 않는다.

| HTTP | code | 발생 조건 | 프론트엔드 처리 |
|---|---|---|---|
| `401` | `UNAUTHENTICATED` | 인증이 필요한 API에 `Authorization` 헤더가 없음 | 로그인 화면으로 이동 |
| `401` | `UNAUTHENTICATED` | access token 만료 | 아래 재시도 흐름 |
| `401` | `UNAUTHENTICATED` | 서명 오류, 알 수 없는 `kid`, `iss`·`aud` 불일치, 필수 claim 누락, `is_anonymous = true`, 임시 로그인이 꺼진 서버에 보낸 임시 token | 아래 재시도 흐름 |
| `403` | `FORBIDDEN` | 로그인했지만 권한이 없는 API 호출 (2.2). 예: operator 전용 API, 업주가 아닌 업장의 관리 API | 접근 차단 안내. 재시도하거나 로그인 화면으로 보내지 않는다. `GET /api/me`를 다시 불러 화면 권한을 갱신할 수 있다 |
| `503` | `SERVICE_UNAVAILABLE` | 서버 인증 설정 누락(`SUPABASE_URL` 등), Supabase JWKS 조회 실패 또는 공개된 키가 없음(프로젝트가 레거시 HS256 secret만 사용), 임시 인증 설정 오류 | 잠시 후 재시도 안내. 로그인 화면으로 보내지 않고 저장된 세션을 유지한다 |

`401` 재시도 흐름:

```text
API 응답 401 UNAUTHENTICATED
→ 이 요청이 이미 한 번 재시도한 요청이면: Supabase 로그아웃 후 로그인 화면
→ 아니면 Supabase SDK로 세션 갱신
   - 성공: 새 access token으로 같은 요청을 한 번만 재시도
   - 실패(refresh token 무효, 세션 종료): Supabase 로그아웃 후 로그인 화면
```

- 프론트엔드는 access token을 따로 보관하지 않고 요청 직전에 SDK의 현재 세션에서 꺼낸다. SDK가 만료 전에 자동으로 갱신하므로 대부분의 요청은 `401` 없이 처리된다.
- 여러 요청이 동시에 `401`을 받아도 세션 갱신은 한 번만 하고, 나머지 요청은 그 결과를 기다려 재시도한다.
- 공개 API 처리:
  - `GET /api/bars/{barId}/menu`는 `Authorization` 헤더가 있으면 token을 검증하고, 잘못된 token이면 `401`을 반환한다. 프론트엔드는 위 재시도 흐름을 똑같이 적용하되, 세션 갱신에 실패하면 로그인 화면으로 보내지 않고 로그아웃한 뒤 헤더 없이 비로그인 사용자로 다시 요청한다. 단, 서버가 지금 token을 확인할 수 없으면(위 표의 `503` 조건) 이 API는 `503` 대신 token이 없는 것처럼 비로그인 사용자로 처리한다. 공개 정보라서 Supabase 장애 중에도 로그인 사용자가 업장 상세를 볼 수 있게 하려는 것이다. 이때는 operator도 비활성 업장을 볼 수 없다(`404`).
  - `GET /api/search/bars`, `GET /api/search/nearby-bars`, `GET /api/search/map-bars`, `GET /api/search/bar-names`, `GET /api/search/popular-products`, `GET /api/bar-photos/{photoId}`와 그 `/thumbnail`(3.16.5)은 `Authorization` 헤더를 읽지 않는다. 어떤 token을 보내도 결과가 같고, Supabase 장애 중에도 막히지 않는다.

#### 3.1.6 백엔드 설정 항목

비밀값은 이 문서에 적지 않는다. Supabase JWKS 검증에는 비밀값이 필요 없으므로, 백엔드는 이 목적으로 Supabase `service_role` key를 갖지 않는다.

| 환경 변수 | 기본값·예시 | 설명 |
|---|---|---|
| `SUPABASE_URL` | `https://<project-ref>.supabase.co` | issuer(`{SUPABASE_URL}/auth/v1`)와 JWKS URL을 만든다. 없으면 Supabase token을 받는 API가 `503` |
| `SUPABASE_JWT_AUDIENCE` | `authenticated` | 허용할 `aud` |
| `SUPABASE_JWT_ALGORITHMS` | `ES256` | 허용할 서명 알고리즘. HS256은 넣지 않는다 |
| `TEMP_AUTH_ENABLED` | `false` | 임시 로그인 사용 여부. 로컬 개발에서만 `true` |
| `TEMP_AUTH_USER_TYPE` | `customer` | 임시 사용자의 역할 (`customer`, `operator`) |
| `TEMP_AUTH_JWT_SECRET` | (비밀값) | 임시 token 서명 키. `.env`에만 둔다 |

서버는 시작할 때 Supabase 설정을 검사한다. 값이 잘못되면(예: `SUPABASE_JWT_ALGORITHMS`에 HS256 포함, `SUPABASE_URL`에 경로가 붙음) 시작하지 않는다. `SUPABASE_URL`이 없는 것만으로는 시작을 막지 않으며, 이때 Supabase token은 `503`이고 임시 로그인은 그대로 동작한다.

Supabase와 Google Cloud 쪽에서 설정할 항목은 다음과 같다. 값은 이 문서에 적지 않는다.

- Google Cloud: Web client ID와 Android client ID(debug·release 서명의 SHA-1 각각)를 만든다.
- Supabase 대시보드 Authentication > Providers > Google: provider를 켜고 위 client ID들을 모두 등록한다. client secret은 대시보드에만 둔다. Skip nonce check는 끈 상태를 유지한다.
- Supabase signing key: ES256 비대칭 키를 사용한다. 레거시 HS256 secret으로는 서명하지 않는다. 키를 교체할 때도 ES256 키로 교체한다.
- Supabase 익명 로그인(anonymous sign-in): 끈다.

### 3.2 현재 사용자 조회

앱을 처음 실행할 때, 로그인 직후, 그리고 화면 권한을 새로 고칠 때 호출한다. 요청 본문은 없다.

```http
GET /api/me
Authorization: Bearer <access-token>
```

`200 OK`. 최초 호출에서 사용자를 생성했을 때도 `200`이다.

```json
{
  "userId": "11111111-1111-4111-8111-111111111111",
  "email": "user@example.com",
  "displayName": "홍길동",
  "userType": "customer",
  "updatedAt": "2026-10-13T09:00:00Z"
}
```

| 필드 | 타입 | null 가능 | 설명 |
|---|---|---|---|
| `userId` | UUID 문자열 | 아니오 | `users.id`. Supabase의 `sub`가 아니다 |
| `email` | 문자열 | 예 | token의 `email`. 없거나 다른 사용자와 겹치면 `null` |
| `displayName` | 문자열, 최대 20자 | 예 | 표시 이름. `null`이면 프론트엔드가 `email` 또는 기본 문구로 표시한다 |
| `userType` | `customer` \| `operator` | 아니오 | 3.1.4 |
| `updatedAt` | RFC 3339 문자열 | 아니오 | 사용자 정보가 마지막으로 바뀐 시각(`users.updated_at`) |

사용자 생성과 동기화 규칙:

- **최초 호출**(`auth_subject`가 없는 경우): `user_type = customer`로 `users` 행을 만든다. `displayName`은 token의 `user_metadata.name`에서 앞뒤 공백을 지운 값으로 채우며, 20자를 넘으면 앞 20자만 저장한다.
- **이후 호출**: `email`은 매번 token 값으로 맞춘다. `displayName`은 덮어쓰지 않으므로 3.3으로 바꾼 이름이 유지된다.
- 같은 사용자가 최초 `GET /api/me`를 동시에 여러 번 호출해도 `users` 행은 하나만 생기고 모든 호출이 같은 사용자를 반환한다.

Google 계정 claim이 없을 때:

| claim | 상황 | 처리 |
|---|---|---|
| `sub` | 없거나 빈 문자열 | `401 UNAUTHENTICATED` |
| `email` | 없거나 빈 문자열 | `email = null`로 두고 로그인 성공 |
| `email` | 다른 `auth_subject`의 사용자가 이미 같은 email을 사용 | `email = null`로 두고 로그인 성공 |
| `user_metadata.name` | 없거나 공백뿐 | `displayName = null` |
| `is_anonymous` | `true` | `401 UNAUTHENTICATED` |

운영자 전용 화면은 `userType = operator`일 때만 보여 준다. 업주 여부는 `userType`에 나타나지 않으므로 `GET /api/me/bars`(3.11.9)로 확인한다. 오류는 3.1.5를 따른다.

### 3.3 현재 사용자 수정

```http
PATCH /api/me
Authorization: Bearer <access-token>
Content-Type: application/json
```

```json
{
  "displayName": "메뉴 검수 담당자"
}
```

```json
{
  "userId": "11111111-1111-4111-8111-111111111111",
  "email": "operator@example.com",
  "displayName": "메뉴 검수 담당자",
  "userType": "operator",
  "updatedAt": "2026-10-04T10:00:00Z"
}
```

| 필드 | 필수 | 규칙 |
|---|---|---|
| `displayName` | 예 | 앞뒤 공백을 지운 뒤 1~20자. 줄바꿈과 제어 문자는 받지 않는다 |

- 글자 수는 유니코드 문자(code point) 단위로 센다. 한글 한 글자와 이모지 하나가 모두 1자다. Kotlin의 `String.length`는 이모지 같은 문자를 2로 세므로, 프론트엔드가 길이를 미리 검사할 때는 `codePointCount`를 쓴다.
- 요청 본문에는 `displayName`만 보낸다. 다른 필드(`email`, `userType` 등)를 보내면 아무것도 바꾸지 않고 `422`이며 `fieldErrors[].code = EXTRA_FORBIDDEN`이다. 이 API로 `email`, `authSubject`, `userType`은 변경할 수 없다.
- 표시 이름을 지우는 기능은 없다. `null`이나 문자열이 아닌 값을 보내면 `STRING_TYPE`이다.
- 지금과 같은 이름을 보내면 아무것도 바꾸지 않고 `200 OK`로 현재 사용자를 돌려준다. `updatedAt`은 저장된 값이 실제로 바뀔 때만 바뀌므로 그대로다(3.2).
- `displayName`만 바꾸며 token의 `email`로 맞추지 않는다. `email` 동기화는 `GET /api/me`만 한다(3.2). 여기서 바꾼 `displayName`은 이후 `GET /api/me`의 동기화로 덮어쓰지 않는다.
- 응답은 `200 OK`이며 형식은 `GET /api/me`와 같다. 프론트엔드는 이 응답으로 화면의 사용자 정보를 바꾼다.

이 API는 사용자를 생성하지 않는다. token은 유효하지만 `users` 행이 없으면 `404 USER_NOT_FOUND`를 반환한다. 프론트엔드는 `GET /api/me`를 호출해 사용자를 만든 뒤 같은 요청을 다시 보낸다.

백엔드는 인증(`401`, 3.1.5), 요청 형식(`422`), `users` 행(`404 USER_NOT_FOUND`) 순서로 확인한다.

| HTTP | code | 발생 조건 | 프론트엔드 처리 |
|---|---|---|---|
| `401` | `UNAUTHENTICATED` | 3.1.5 | 3.1.5 |
| `404` | `USER_NOT_FOUND` | `users` 행이 없음 | `GET /api/me` 호출 후 같은 요청 재시도 |
| `422` | `VALIDATION_FAILED` | `fieldErrors[].path = displayName`: 값이 없음(`MISSING`), 빈 문자열이거나 공백뿐(`BLANK`), 20자 초과(`STRING_TOO_LONG`), 문자열이 아님(`STRING_TYPE`), 줄바꿈이나 제어 문자(`INVALID_CHARACTER`). 다른 필드를 보냄(`EXTRA_FORBIDDEN`, `path`는 보낸 필드 이름) | 입력란 아래에 안내. `EXTRA_FORBIDDEN`과 `STRING_TYPE`은 앱 버그 |
| `503` | `SERVICE_UNAVAILABLE` | 3.1.5 | 3.1.5 |

### 3.4 업장 목록과 검색

```http
GET /api/bars?query=%EA%B4%80%EC%95%85&status=active&limit=20&cursor=<cursor>
Authorization: Bearer <access-token>
```

| Query | 필수 | 기본값 | 설명 |
|---|---|---|---|
| `query` | 아니오 | 없음 | 업장명 또는 주소 검색어 |
| `status` | 아니오 | `active` | `active`, `inactive`, `all` |
| `limit` | 아니오 | `20` | 최대 `100` |
| `cursor` | 아니오 | 없음 | 다음 페이지 cursor |

```json
{
  "items": [
    {
      "barId": "22222222-2222-4222-8222-222222222222",
      "name": "관악 위스키 바",
      "address": "서울특별시 관악구 관악로 1, 2층",
      "latitude": 37.123456,
      "longitude": 126.123456,
      "phone": "02-000-0000",
      "status": "active",
      "coverThumbnailUrl": "https://bottlemap.o-r.kr/api/bar-photos/12121212-1212-4212-8212-121212121211/thumbnail",
      "activeMenuImport": {
        "menuImportId": "77777777-7777-4777-8777-777777777777",
        "status": "ready_for_review"
      }
    }
  ],
  "nextCursor": null
}
```

`activeMenuImport`는 미완료 작업이 없으면 `null`이다. 목록 화면이 별도 요청 없이 기존 작업으로 진입할 수 있도록 제공한다.

`coverThumbnailUrl`은 업장 대표 사진(3.16.1)의 썸네일 URL(`thumbnailUrl`)이며, 사진이 없으면 `null`이다. 3.10, 3.11.11, 3.12, 3.13의 `coverThumbnailUrl`과 같다.

### 3.5 업장 생성

operator가 업장을 직접 만드는 API다.

> **지금은 구현하지 않는다.** 업장은 업주의 `new_bar` 신청을 operator가 승인할 때(3.11.7) 만든다. 업장 등록은 이 신청과 승인을 기본으로 하므로 operator가 직접 만드는 API는 당장 만들지 않으며, 백엔드에도 없다(호출하면 `405 METHOD_NOT_ALLOWED`). 아래 요청과 응답은 나중에 구현할 때를 위한 초안이다. 업장 필드 규칙은 업장 수정(3.7)과 신청 승인(3.11.7)이 함께 쓰므로 지금도 유효하다.

```http
POST /api/bars
Authorization: Bearer <access-token>
Content-Type: application/json
```

```json
{
  "name": "관악 위스키 바",
  "address": "서울특별시 관악구 관악로 1 2층",
  "latitude": 37.478321,
  "longitude": 126.951234,
  "phone": "02-000-0000"
}
```

업장 필드 규칙(3.5, 3.7, 3.11.7 공통):

| 필드 | 생성 시 필수 | 규칙 |
|---|---|---|
| `name` | 예 | 앞뒤 공백을 지운 뒤 1~150자 |
| `address` | 예 | 앞뒤 공백을 지운 뒤 1~500자. 층·호수를 포함한 표시용 주소 |
| `latitude` | 예 | -90~90. 소수점 아래 6자리까지 저장한다 |
| `longitude` | 예 | -180~180. 소수점 아래 6자리까지 저장한다 |
| `phone` | 아니오 | 30자 이하. 없거나 공백뿐이면 `null` |

좌표는 서버가 주소로 계산하지 않는다. 프론트엔드는 지도에서 업장 위치를 고르는 화면을 제공하고, 고른 좌표를 주소와 함께 보낸다. 신청 승인(3.11.7)과 업장 수정(3.7)이 같은 화면을 쓴다.

```http
HTTP/1.1 201 Created
Location: /api/bars/22222222-2222-4222-8222-222222222222
```

응답 본문은 3.6과 같은 형식이다. 새 업장이므로 `status = active`, `description = null`, `defaultPourMl = null`, `tags = []`, `weeklyHours = []`, `operatingException = null`, `photos = []`, `activeMenuImport = null`, `currentMenu = null`, `owner = null`이다.

이름·주소가 비슷한 업장이 있어도 생성을 막지 않으며, 응답에 경고도 담지 않는다. 프론트엔드는 생성 전에 3.4로 같은 업장이 있는지 확인하게 한다.

| HTTP | code | 발생 조건 | 프론트엔드 처리 |
|---|---|---|---|
| `401` | `UNAUTHENTICATED` | 3.1.5 | 3.1.5 |
| `403` | `FORBIDDEN` | operator가 아님 | 3.1.5 |
| `422` | `VALIDATION_FAILED` | 위 규칙 위반 | `fieldErrors` 표시 |

### 3.6 업장 상세 조회

operator와 업주의 업장 관리 화면용 API다. 업장 정보와 관리 상태(진행 중인 메뉴 등록 작업, 현재 메뉴판 요약, 업주)를 반환하며 메뉴 항목은 포함하지 않는다. 메뉴 항목은 3.9로 조회한다. 업장 수정 뒤 재조회와 관리 화면 직접 진입에 사용한다.

operator와 해당 업장의 현재 업주만 호출할 수 있다. 비활성 업장도 `200 OK`로 반환한다.

```http
GET /api/bars/{barId}
Authorization: Bearer <access-token>
```

`200 OK`

```json
{
  "barId": "22222222-2222-4222-8222-222222222222",
  "name": "관악 위스키 바",
  "address": "서울특별시 관악구 관악로 1 2층",
  "latitude": 37.478321,
  "longitude": 126.951234,
  "phone": "02-000-0000",
  "description": "싱글몰트 위주의 조용한 바",
  "defaultPourMl": 30,
  "tags": ["싱글몰트", "조용한 분위기"],
  "weeklyHours": [
    { "dayOfWeek": 1, "closed": true, "openTime": null, "closeTime": null },
    { "dayOfWeek": 5, "closed": false, "openTime": "18:00", "closeTime": "02:00" }
  ],
  "operatingException": {
    "kind": "custom_hours",
    "startDate": "2026-10-04",
    "endDate": "2026-10-04",
    "openTime": "20:00",
    "closeTime": "23:00",
    "note": "내부 사정으로 일찍 마감합니다"
  },
  "photos": [
    { "photoId": "12121212-1212-4212-8212-121212121211", "imageUrl": "https://bottlemap.o-r.kr/api/bar-photos/12121212-1212-4212-8212-121212121211", "thumbnailUrl": "https://bottlemap.o-r.kr/api/bar-photos/12121212-1212-4212-8212-121212121211/thumbnail" }
  ],
  "status": "active",
  "activeMenuImport": {
    "menuImportId": "77777777-7777-4777-8777-777777777777",
    "status": "ready_for_review"
  },
  "currentMenu": {
    "menuBoardId": "66666666-6666-4666-8666-666666666666",
    "menuVersion": 4,
    "publishedAt": "2026-10-04T09:15:00Z",
    "confirmedAt": "2026-10-20T02:30:00Z"
  },
  "owner": {
    "userId": "11111111-1111-4111-8111-111111111111",
    "email": "owner@example.com",
    "displayName": "김사장",
    "ownerSince": "2026-10-14T05:00:00Z"
  },
  "createdAt": "2026-10-01T03:00:00Z",
  "updatedAt": "2026-10-04T09:15:00Z"
}
```

| 필드 | 타입 | null 가능 | 설명 |
|---|---|---|---|
| `barId` | UUID 문자열 | 아니오 | |
| `name` | 문자열 | 아니오 | 업장명 |
| `address` | 문자열 | 아니오 | 층·호수를 포함한 표시용 주소 |
| `latitude`, `longitude` | 숫자 | 아니오 | 업장 좌표(WGS84). 3.9.4 |
| `phone` | 문자열 | 예 | 연락처. 없으면 `null` |
| `description` | 문자열 | 예 | 한 줄 소개. 업주나 operator가 정한다(3.7). 고객 화면(3.9)에도 나온다. 없으면 `null` |
| `defaultPourMl` | 정수 | 예 | 매장 기본 잔 용량(ml). 업주가 매장 정보에서 정한다(3.7). 메뉴 편집과 검수 화면이 잔 옵션의 용량 입력 칸을 미리 채우는 데 쓴다(3.14.2). 서버가 메뉴에 자동으로 적용하지 않으며 고객 화면(3.9)에는 없다. 없으면 `null` |
| `tags` | 문자열 배열 | 아니오 | 매장 태그. 업주나 operator가 정한 순서대로 최대 5개(3.7). 없으면 `[]` |
| `weeklyHours` | 배열 | 아니오 | 정규 영업시간(3.15.1). 정한 요일만 `dayOfWeek` 오름차순으로 온다. 없으면 `[]` |
| `operatingException` | 객체 | 예 | 임시 휴무(3.15.4). 앞으로 시작할 것과 어제 끝난 것도 들어 있으므로, 지금 적용 중인지는 프론트엔드가 판단한다. 없거나 끝난 지 하루가 지났으면 `null` |
| `photos` | 배열 | 아니오 | 매장 사진(3.16). 표시 순서대로 오며 첫 사진이 대표 사진이다. 없으면 `[]` |
| `photos[].photoId` | UUID 문자열 | 아니오 | |
| `photos[].imageUrl` | 문자열 | 아니오 | 사진 파일의 절대 URL(3.16.5). 만료되지 않으며, 같은 `photoId`의 내용은 바뀌지 않는다. 전체 화면과 상세 갤러리에 쓴다 |
| `photos[].thumbnailUrl` | 문자열 | 아니오 | 긴 변 480px 썸네일의 절대 URL(3.16.5). 목록, 격자, 작은 카드에 쓴다 |
| `status` | `active` \| `inactive` | 아니오 | |
| `activeMenuImport` | 객체 | 예 | 미완료 메뉴 등록 작업. 없으면 `null`. 3.4와 같다. 있으면 메뉴 직접 편집을 할 수 없다(3.14.1) |
| `activeMenuImport.menuImportId` | UUID 문자열 | 아니오 | `GET /api/menu-imports/{menuImportId}`로 이어서 진행한다 |
| `activeMenuImport.status` | `uploaded` \| `processing` \| `ready_for_review` | 아니오 | |
| `currentMenu` | 객체 | 예 | 현재 메뉴판 요약. 반영된 메뉴가 없으면 `null` |
| `currentMenu.menuBoardId` | UUID 문자열 | 아니오 | |
| `currentMenu.menuVersion` | 정수 | 아니오 | 메뉴판 버전(3.9의 `menuVersion`과 같다). 관리 홈의 판매 정보 확인(3.14.9)에 그대로 보낸다 |
| `currentMenu.publishedAt` | RFC 3339 문자열 | 아니오 | 현재 메뉴판이 마지막으로 반영된 시각 |
| `currentMenu.confirmedAt` | RFC 3339 문자열 | 예 | 업주나 operator가 판매 정보를 마지막으로 확인한 시각(3.14.9). 확인한 적이 없으면 `null`. 업주 화면의 "최근 갱신"은 `publishedAt`과 이 값 중 늦은 시각이다 |
| `owner` | 객체 | 예 | 현재 업주(3.11). 없으면 `null` |
| `owner.userId` | UUID 문자열 | 아니오 | |
| `owner.email`, `owner.displayName` | 문자열 | 예 | 3.2와 같다 |
| `owner.ownerSince` | RFC 3339 문자열 | 아니오 | 업주 신청이 승인된 시각 |
| `createdAt`, `updatedAt` | RFC 3339 문자열 | 아니오 | |

오류와 프론트엔드 처리:

| HTTP | code | 발생 조건 | 프론트엔드 처리 |
|---|---|---|---|
| `401` | `UNAUTHENTICATED` | token 없음, 만료, 검증 실패 | 3.1.5 |
| `403` | `FORBIDDEN` | operator도 해당 업장의 업주도 아님 | 3.1.5 |
| `404` | `BAR_NOT_FOUND` | 업장이 없거나 `barId`가 UUID 형식이 아님. `details.barId`에 요청한 값을 담는다 | "업장을 찾을 수 없습니다" 안내 후 업장 목록으로 이동 |

### 3.7 업장 수정과 비활성화

```http
PATCH /api/bars/{barId}
Authorization: Bearer <access-token>
Content-Type: application/json
```

operator와 해당 업장의 현재 업주가 호출할 수 있다. 바꿀 필드만 보낸다. 필드 규칙은 3.5와 같다.

```json
{
  "phone": "02-111-2222",
  "status": "inactive"
}
```

| 필드 | 보낼 수 있는 사람 | 규칙 |
|---|---|---|
| `name`, `address` | operator, 업주 | `null`을 보낼 수 없다 |
| `latitude`, `longitude` | operator, 업주 | 둘을 함께 보낸다. 하나만 보내면 `LAT_LNG_REQUIRED_TOGETHER` |
| `phone` | operator, 업주 | `null`을 보내면 연락처를 지운다 |
| `description` | operator, 업주 | 한 줄 소개. 앞뒤 공백을 지운 뒤 100자 이하(줄바꿈도 한 글자로 센다). 공백뿐이면 `null`로 저장한다. `null`을 보내면 지운다. 줄바꿈을 허용하며, 서버는 HTML 이스케이프나 금칙어 검사 없이 받은 그대로 저장한다. 업장 수정에서만 받는다. 업장 생성(3.5)과 신청 승인(3.11.7)에서 보내면 `422`이고 `fieldErrors[].code = EXTRA_FORBIDDEN`이다. 새 업장은 `null`이다 |
| `defaultPourMl` | operator, 업주 | 1~999 정수. `null`을 보내면 지운다. 바꿔도 이미 게시된 메뉴의 용량은 바뀌지 않는다. 업장 수정에서만 받는다. 업장 생성(3.5)과 신청 승인(3.11.7)에서 보내면 `422`이고 `fieldErrors[].code = EXTRA_FORBIDDEN`이다. 새 업장은 `null`이다 |
| `tags` | operator, 업주 | 매장 태그 전체를 이 배열로 바꾼다. `[]`이면 모두 지우며 `null`은 보낼 수 없다. 최대 5개이고, 태그마다 앞뒤 공백을 지운 뒤 1~24자다. 줄바꿈과 제어 문자는 받지 않는다(`INVALID_CHARACTER`). 대소문자만 다른 태그도 같은 태그로 보며, 중복이면 `DUPLICATE_TAG`다. 서버는 앞뒤 공백만 지우고 대소문자와 순서는 받은 그대로 저장한다. 자유 입력이며 서버가 정한 태그 목록은 없다 |
| `weeklyHours` | operator, 업주 | 정규 영업시간 전체를 이 배열로 바꾼다. 형식과 규칙은 3.15.1. `[]`이면 영업시간 정보가 없는 상태가 되며 `null`은 보낼 수 없다 |
| `status` | operator만 | `active` 또는 `inactive`. 업주가 보내면 `403 FORBIDDEN` |

- `address`를 바꿀 때는 `latitude`와 `longitude`도 함께 보낸다. 주소만 보내면 `422`이고 `fieldErrors[].code = COORDINATES_REQUIRED`다. 주소 없이 좌표만 바꿔 위치를 보정할 수는 있다.
- `tags`와 `weeklyHours`도 `description`, `defaultPourMl`처럼 업장 수정에서만 받는다. 업장 생성(3.5)과 신청 승인(3.11.7)에서 보내면 `422`이고 `fieldErrors[].code = EXTRA_FORBIDDEN`이다. 새 업장은 둘 다 `[]`이다.
- 임시 휴무는 3.15.2, 매장 사진은 3.16으로 바꾼다. 이 API로 `operatingException`이나 `photos`를 보내면 `EXTRA_FORBIDDEN`이다.
- 태그는 고객 검색(3.10, 3.12, 3.13)에 쓰지 않는다. 태그로 거르는 검색은 후속 작업이다.
- 오류의 `fieldErrors[].path`는 `tags[2]`, `weeklyHours[1].closeTime`처럼 배열 위치를 가리킨다.
- 빈 본문 `{}`이면 아무것도 바꾸지 않고 현재 값을 반환한다.
- 응답은 `200 OK`이며 본문은 3.6과 같은 형식이다.

업장을 물리 삭제하는 API는 두지 않는다. 운영 중단은 operator가 `status = inactive`로 처리해 메뉴 등록과 이미지 이력을 유지한다. 비활성 업장은 고객 검색과 고객용 업장 상세에서 빠지고, 새 메뉴 등록을 받지 않는다(4.4).

| HTTP | code | 발생 조건 | 프론트엔드 처리 |
|---|---|---|---|
| `401` | `UNAUTHENTICATED` | 3.1.5 | 3.1.5 |
| `403` | `FORBIDDEN` | operator도 해당 업장의 업주도 아님, 또는 업주가 `status`를 보냄 | 3.1.5 |
| `404` | `BAR_NOT_FOUND` | 업장이 없거나 `barId`가 UUID 형식이 아님 | 업장 목록으로 이동 |
| `422` | `VALIDATION_FAILED` | 필드 규칙 위반, `LAT_LNG_REQUIRED_TOGETHER`, `COORDINATES_REQUIRED`, `INVALID_CHARACTER`, `DUPLICATE_TAG`, 영업시간 규칙 위반(3.15.1) | `fieldErrors` 표시 |

### 3.8 업장별 메뉴 등록 작업 목록

화면을 닫았다가 다시 열어도 진행 중인 작업으로 복귀하고, 완료·실패 작업을 확인하기 위한 API다.

```http
GET /api/bars/{barId}/menu-imports?status=active&limit=20&cursor=<cursor>
Authorization: Bearer <access-token>
```

| Query | 필수 | 기본값 | 설명 |
|---|---|---|---|
| `status` | 아니오 | `all` | `active`, `uploaded`, `processing`, `ready_for_review`, `applied`, `failed`, `canceled`, `all` |
| `limit` | 아니오 | `20` | 최대 `100` |
| `cursor` | 아니오 | 없음 | 다음 페이지 cursor |

`active`는 저장 Enum이 아니라 `uploaded`, `processing`, `ready_for_review`를 묶는 API 필터다.

```json
{
  "items": [
    {
      "menuImportId": "77777777-7777-4777-8777-777777777777",
      "mode": "full_replace",
      "status": "ready_for_review",
      "imageCount": 2,
      "reviewVersion": 3,
      "ownerNote": "2026년 10월 메뉴판",
      "createdAt": "2026-10-04T09:00:00Z",
      "completedAt": null
    }
  ],
  "nextCursor": null
}
```

항목을 선택하면 `GET /api/menu-imports/{menuImportId}`를 호출한다.

### 3.9 현재 게시 메뉴 조회

고객 업장 상세 화면용 공개 API다. 업장 기본 정보와 현재 게시 메뉴 전체를 한 번에 반환하므로, 고객 화면은 별도 요청 없이 이름, 주소, 지도 위치와 메뉴를 표시할 수 있다. operator와 업주도 현재 게시 메뉴를 확인할 때 사용한다.

```http
GET /api/bars/{barId}/menu
```

`Authorization` 헤더는 선택이다. 보내면 token을 검증하며, 잘못된 token은 `401`이다(3.1.5). 서버가 token을 확인할 수 없으면 비로그인 사용자로 처리한다(3.1.5).

| 호출자 | 활성 업장 | 비활성 업장 |
|---|---|---|
| 비로그인 사용자, customer | `200` | `404 BAR_NOT_FOUND` (업장이 없는 경우와 구분하지 않는다) |
| 해당 업장의 업주 | `200` | `200` |
| operator | `200` | `200` |

업주 행은 업주 기능(3.11)을 구현하는 I3부터 적용한다. 그 전에는 업주도 customer와 같다.

`200 OK`

```json
{
  "barId": "22222222-2222-4222-8222-222222222222",
  "name": "관악 위스키 바",
  "address": "서울특별시 관악구 관악로 1 2층",
  "latitude": 37.478321,
  "longitude": 126.951234,
  "phone": "02-000-0000",
  "description": "싱글몰트 위주의 조용한 바",
  "tags": ["싱글몰트", "조용한 분위기"],
  "weeklyHours": [
    { "dayOfWeek": 1, "closed": true, "openTime": null, "closeTime": null },
    { "dayOfWeek": 5, "closed": false, "openTime": "18:00", "closeTime": "02:00" }
  ],
  "operatingException": null,
  "photos": [
    { "photoId": "12121212-1212-4212-8212-121212121211", "imageUrl": "https://bottlemap.o-r.kr/api/bar-photos/12121212-1212-4212-8212-121212121211", "thumbnailUrl": "https://bottlemap.o-r.kr/api/bar-photos/12121212-1212-4212-8212-121212121211/thumbnail" },
    { "photoId": "12121212-1212-4212-8212-121212121212", "imageUrl": "https://bottlemap.o-r.kr/api/bar-photos/12121212-1212-4212-8212-121212121212", "thumbnailUrl": "https://bottlemap.o-r.kr/api/bar-photos/12121212-1212-4212-8212-121212121212/thumbnail" }
  ],
  "menuBoardId": "66666666-6666-4666-8666-666666666666",
  "menuVersion": 4,
  "publishedAt": "2026-10-04T09:15:00Z",
  "items": [
    {
      "menuBoardEntryId": "88888888-8888-4888-8888-888888888881",
      "barMenuItemId": "99999999-9999-4999-8999-999999999991",
      "productId": "44444444-4444-4444-8444-444444444444",
      "productName": "Glenfiddich 12",
      "brandId": "dddddddd-dddd-4ddd-8ddd-ddddddddddd2",
      "brandName": "Glenfiddich",
      "category": "whisky",
      "kind": "whisky",
      "displayName": "글렌피딕 12년",
      "sortOrder": 1,
      "soldOut": false,
      "options": [
        {
          "menuEntryOptionId": "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaa1",
          "optionLabel": "잔",
          "pourMl": 30,
          "priceKrw": 17000,
          "discount": {
            "discountedPriceKrw": 14000,
            "startsAt": "2026-11-01T09:00:00Z",
            "endsAt": "2026-11-15T15:00:00Z"
          },
          "sortOrder": 1
        },
        {
          "menuEntryOptionId": "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaa2",
          "optionLabel": "병",
          "pourMl": null,
          "priceKrw": 160000,
          "discount": null,
          "sortOrder": 2
        }
      ]
    },
    {
      "menuBoardEntryId": "88888888-8888-4888-8888-888888888882",
      "barMenuItemId": "99999999-9999-4999-8999-999999999992",
      "productId": "bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbb1",
      "productName": "Deanston 12",
      "brandId": "dddddddd-dddd-4ddd-8ddd-ddddddddddd1",
      "brandName": "Deanston",
      "category": "whisky",
      "kind": "whisky",
      "displayName": "Deanston 12",
      "sortOrder": 2,
      "soldOut": false,
      "options": [
        {
          "menuEntryOptionId": "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaa3",
          "optionLabel": null,
          "pourMl": 15,
          "priceKrw": 8000,
          "discount": null,
          "sortOrder": 1
        }
      ]
    },
    {
      "menuBoardEntryId": "88888888-8888-4888-8888-888888888883",
      "barMenuItemId": "99999999-9999-4999-8999-999999999993",
      "productId": null,
      "productName": null,
      "brandId": null,
      "brandName": null,
      "category": null,
      "kind": "whisky",
      "displayName": "글렌알라키 10년 CS 배치 11",
      "sortOrder": 3,
      "soldOut": false,
      "options": [
        {
          "menuEntryOptionId": "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaa4",
          "optionLabel": null,
          "pourMl": 30,
          "priceKrw": 26000,
          "discount": null,
          "sortOrder": 1
        }
      ]
    },
    {
      "menuBoardEntryId": "88888888-8888-4888-8888-888888888884",
      "barMenuItemId": "99999999-9999-4999-8999-999999999994",
      "productId": null,
      "productName": null,
      "brandId": null,
      "brandName": null,
      "category": null,
      "kind": "other",
      "displayName": "진토닉",
      "sortOrder": 4,
      "soldOut": false,
      "options": [
        {
          "menuEntryOptionId": "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaa5",
          "optionLabel": null,
          "pourMl": null,
          "priceKrw": 12000,
          "discount": null,
          "sortOrder": 1
        }
      ]
    }
  ]
}
```

| 필드 | 타입 | null 가능 | 설명 |
|---|---|---|---|
| `barId` | UUID 문자열 | 아니오 | |
| `name` | 문자열 | 아니오 | 업장명 |
| `address` | 문자열 | 아니오 | 층·호수를 포함한 표시용 주소 |
| `latitude`, `longitude` | 숫자 | 아니오 | 업장 좌표(WGS84). 3.9.4 |
| `phone` | 문자열 | 예 | 연락처. 없으면 `null` |
| `description` | 문자열 | 예 | 한 줄 소개(3.6과 같다). 줄바꿈이 들어 있을 수 있다. 프론트엔드는 HTML로 해석하지 않고 일반 텍스트로 보여 주며, 표시할 줄 수를 제한할 수 있다. 없으면 `null` |
| `tags` | 문자열 배열 | 아니오 | 매장 태그(3.6과 같다). 받은 순서대로 보여 준다. 없으면 `[]` |
| `weeklyHours` | 배열 | 아니오 | 정규 영업시간(3.15.1). 없으면 `[]` |
| `operatingException` | 객체 | 예 | 임시 휴무(3.15.4). `note`는 고객 안내 문구다. 어제 끝난 것도 영업 상태 계산을 위해 들어 있다. 없거나 끝난 지 하루가 지났으면 `null` |
| `photos` | 배열 | 아니오 | 매장 사진(3.6과 같다). 첫 사진이 대표 사진이다. 없으면 `[]`이며, 프론트엔드는 기본 이미지를 보여 준다 |
| `menuBoardId` | UUID 문자열 | 예 | 현재 메뉴판. 반영된 메뉴가 없으면 `null` |
| `menuVersion` | 정수 | 예 | 메뉴판 버전. 검수 반영(8)이나 직접 편집(3.14)으로 메뉴판이 바뀔 때마다 1씩 오른다. 직접 편집 요청에 그대로 보낸다. 메뉴판이 없으면 `null` |
| `publishedAt` | RFC 3339 문자열 | 예 | 현재 메뉴판이 검수 반영이나 직접 편집으로 마지막으로 바뀐 시각. 반영된 메뉴가 없으면 `null` |
| `items` | 배열 | 아니오 | 현재 메뉴판의 항목. 없으면 `[]` |
| `items[].menuBoardEntryId` | UUID 문자열 | 아니오 | |
| `items[].barMenuItemId` | UUID 문자열 | 아니오 | |
| `items[].productId` | UUID 문자열 | 예 | 정규 상품 ID. 상품에 연결되지 않은 항목이면 `null` |
| `items[].productName` | 문자열 | 예 | 정규 상품명(`products.display_name`, 7.2의 `displayName`). 연결되지 않은 항목이면 `null` |
| `items[].brandId`, `items[].brandName` | UUID 문자열, 문자열 | 예 | 상품의 브랜드와 대표 브랜드명. 연결되지 않은 항목이면 `null` |
| `items[].category` | 문자열 | 예 | 상품 분류. 예: `whisky`. 프론트엔드는 이 값과 브랜드로 메뉴를 묶어 보여 줄 수 있다. 연결되지 않은 항목이면 `null` |
| `items[].kind` | `MenuItemKind` | 아니오 | 메뉴 항목의 종류(2.3). `whisky` 또는 `other` |
| `items[].displayName` | 문자열 | 아니오 | 업장 메뉴판에 적힌 표기(`menu_board_entries.display_name`). 정규 상품명이 아니다. 연결되지 않은 항목은 이 이름으로만 보여 준다 |
| `items[].sortOrder` | 정수 | 아니오 | 메뉴판 표시 순서 |
| `items[].soldOut` | 불리언 | 아니오 | 품절이면 `true`(3.14.8). 품절 항목은 operator와 해당 업장의 업주에게만 제자리에 온다. 비로그인 사용자와 customer에게는 품절 항목이 빠지므로 항상 `false`다 |
| `items[].options` | 배열 | 아니오 | 가격·용량 옵션. 최소 1개 |
| `items[].options[].menuEntryOptionId` | UUID 문자열 | 아니오 | |
| `items[].options[].optionLabel` | 문자열 | 예 | 메뉴판의 `잔`, `병` 같은 표기. 없으면 `null` |
| `items[].options[].pourMl` | 정수 | 예 | 용량(ml). 메뉴판에 없으면 `null` |
| `items[].options[].priceKrw` | 정수 | 아니오 | 정가(원). 할인 중이어도 정가다 |
| `items[].options[].discount` | 객체 | 예 | 기간 할인(3.14.2). 끝나지 않은 할인만 오며, 할인이 없거나 끝났으면 `null`. 아직 시작하지 않은 할인도 온다 |
| `items[].options[].discount.discountedPriceKrw` | 정수 | 아니오 | 할인가(원). `priceKrw`보다 낮다 |
| `items[].options[].discount.startsAt`, `items[].options[].discount.endsAt` | RFC 3339 문자열 | 아니오 | 할인 기간. `startsAt` 이상 `endsAt` 미만인 동안 할인가로 판다 |
| `items[].options[].sortOrder` | 정수 | 아니오 | 옵션 표시 순서 |

할인 중인지는 서버가 보내지 않는다. 프론트엔드가 기기의 현재 시각으로 `startsAt ≤ 현재 < endsAt`이면 할인가와 할인 표시를, 아니면 정가를 보여 주며, 화면을 띄워 둔 동안 다시 계산한다(3.15.5의 영업 상태와 같은 방식). 고객 검색(3.10)에도 같은 `discount`가 오므로 검색 결과와 업장 상세의 가격이 같다.

정렬 기준: `items`는 `sortOrder` 오름차순이고, 각 항목의 `options`도 `sortOrder` 오름차순이다. 프론트엔드는 받은 순서대로 표시한다.

영업 상태(영업 중, 영업 종료, 임시 휴무 등)는 응답에 없다. 프론트엔드가 `weeklyHours`와 `operatingException`으로 계산한다(3.15.5).

품절 항목(3.14.8)은 비로그인 사용자와 customer의 응답에서 빠진다. 손님에게 지금 팔지 않는 상품을 보여 주지 않기 위해서다. operator와 해당 업장의 업주에게는 품절을 풀 수 있도록 `soldOut = true`로 제자리에 온다. 업주 화면의 고객 미리보기는 `soldOut = true`인 항목을 빼고 보여 준다. 서버가 token을 확인할 수 없어 비로그인 사용자로 처리할 때(3.1.5)는 operator와 업주에게도 품절 항목이 빠진다.

`items`에는 검수(8)로 현재 메뉴판에 반영된 메뉴 항목과 직접 추가(3.14.3)한 항목만 있다. 섹션 제목, 설명 등 비상품 줄은 포함하지 않는다. 검색 결과에서 진입한 경우 프론트엔드는 검색한 `productId`와 같은 항목을 강조해 표시할 수 있다.

메뉴 항목은 상품 연결과 종류에 따라 세 가지다. 셋 모두 메뉴판에 바로 보인다.

| 항목 | `productId` | `kind` | 고객 검색(3.10)과 인기 위스키(3.17) |
|---|---|---|---|
| 상품에 연결된 위스키 | 값 있음 | `whisky` | 나온다 |
| 연결을 기다리는 위스키 | `null` | `whisky` | 나오지 않는다. 운영자가 상품에 연결하면 그때부터 나온다 |
| 위스키가 아닌 메뉴 | `null` | `other` | 나오지 않는다. 상품에 연결하지 않는다 |

연결을 기다리는 위스키는 카탈로그에서 매칭되지 않은 줄을 업주가 상품 없이 게시한 항목이다(8.10, 3.14.3). 운영자가 확인한 뒤 기존 상품에 연결하거나 카탈로그에 새로 등록해 연결한다(3.18). 연결된 뒤에도 `displayName`, 메뉴판의 위치, 옵션은 그대로다. `barMenuItemId`는 보통 그대로지만, 이 업장이 예전에 판매했던 상품이거나 이미 메뉴판에 있는 상품에 연결하면 그 상품의 항목으로 줄이 옮겨 가 바뀐다(3.14.1의 연결 바꾸기). 프론트엔드는 `productId`가 `null`인 항목을 연결 여부로 구분해 보여 주지 않아도 된다. 고객에게는 셋 모두 메뉴판의 한 줄이다.

#### 3.9.1 게시된 메뉴가 없을 때

모두 `200 OK`이며 업장 기본 정보는 그대로 반환한다.

반영된 메뉴가 한 번도 없으면 `menuBoardId`, `menuVersion`, `publishedAt`이 `null`이고 `items`가 `[]`다. 프론트엔드는 "등록된 메뉴가 없습니다"를 표시한다.

```json
{
  "barId": "22222222-2222-4222-8222-222222222222",
  "name": "관악 위스키 바",
  "address": "서울특별시 관악구 관악로 1 2층",
  "latitude": 37.478321,
  "longitude": 126.951234,
  "phone": null,
  "description": null,
  "tags": [],
  "weeklyHours": [],
  "operatingException": null,
  "photos": [],
  "menuBoardId": null,
  "menuVersion": null,
  "publishedAt": null,
  "items": []
}
```

메뉴판은 있지만 검수에서 모든 항목을 내렸거나 직접 편집으로 모두 지웠으면(3.14.5, 3.14.6), 또는 손님이 볼 때 모든 항목이 품절이면(3.14.8) `menuBoardId`, `menuVersion`, `publishedAt`은 값이 있고 `items`만 `[]`다. 프론트엔드는 "현재 판매 중인 메뉴가 없습니다"를 표시한다.

그 밖에 값이 없을 수 있는 필드는 `phone`, `description`, `operatingException`, 상품에 연결되지 않은 항목의 `productId`, `productName`, `brandId`, `brandName`, `category`, 그리고 `options[].optionLabel`, `options[].pourMl`, `options[].discount`뿐이며 모두 `null`로 온다. `tags`, `weeklyHours`, `photos`는 없으면 `[]`다. 프론트엔드는 해당 표시만 생략하고, 사진이 없으면 기본 이미지를 보여 준다. 업장 이름, 주소, 좌표와 옵션 가격은 항상 값이 있다.

#### 3.9.2 메뉴 등록이 진행 중일 때

이 API는 메뉴 등록 작업의 상태를 반영하지 않는다. 등록 작업이 처리 중(`uploaded`, `processing`)이거나 검수 대기(`ready_for_review`)이거나 실패(`failed`)여도 현재 게시된 메뉴를 그대로 반환하며, 진행 중이라는 표시도 하지 않는다. 고객은 검수를 마치고 `review-and-apply`로 반영된 메뉴와 직접 편집(3.14)한 메뉴만 본다. operator와 업주가 진행 중인 작업을 확인할 때는 3.6의 `activeMenuImport`를 사용한다.

#### 3.9.3 오류와 프론트엔드 처리

| HTTP | code | 발생 조건 | 프론트엔드 처리 |
|---|---|---|---|
| `401` | `UNAUTHENTICATED` | `Authorization` 헤더로 보낸 token이 만료되었거나 검증 실패 | 3.1.5. 세션 갱신에 실패하면 헤더 없이 비로그인 사용자로 다시 요청 |
| `404` | `BAR_NOT_FOUND` | 업장이 없음, `barId`가 UUID 형식이 아님, operator나 해당 업장의 업주가 아닌 호출자의 비활성 업장 조회. `details.barId`에 요청한 값을 담는다 | "업장을 찾을 수 없습니다" 안내 후 이전 화면으로 이동. 검색 결과에서 진입했다면 검색 결과를 다시 불러온다 |
| 네트워크 오류, `5xx` | | | 오류 상태와 재시도 버튼 |

이 API는 공개 API이므로 `403`을 반환하지 않는다.

#### 3.9.4 지도 좌표

- `latitude`, `longitude`는 업장 위치의 WGS84 좌표(십진 도)다. Kakao 지도의 `LatLng.from(latitude, longitude)`에 그대로 넣는다. 같은 업장은 3.4, 3.6, 3.10, 3.11.11, 3.12, 3.13 응답에서도 같은 좌표다.
- 좌표를 모르는 업장은 등록하지 않으므로 응답의 좌표는 `null`이 아니다. 서버는 주소로 좌표를 계산하지 않는다(3.5). `bars` 테이블의 CHECK 제약이 범위를 벗어난 좌표의 저장을 막는다.
- 프론트엔드는 그래도 받은 좌표를 검사한다. 값이 없거나, 유한한 숫자가 아니거나, 범위를 벗어났거나, `0, 0`이면 지도를 열지 않고 위치를 표시할 수 없다고 안내한다. 업장 이름, 주소, 메뉴는 그대로 표시한다.

### 3.10 고객 상품 검색

고객이 위스키 이름을 입력하거나 홈 화면의 카드(3.17)에서 상품을 고르면 해당 상품을 현재 게시 메뉴에 포함한 업장 목록을 반환한다. 로그인 없이 호출할 수 있는 공개 API이며, `Authorization` 헤더를 보내도 사용하지 않는다.

```http
GET /api/search/bars?query=%EA%B8%80%EB%A0%8C%ED%94%BC%EB%94%95&lat=37.478&lng=126.951
```

| Query | 필수 | 기본값 | 설명 |
|---|---|---|---|
| `query` | `productId`가 없으면 예 | 없음 | 검색어. 앞뒤 공백을 지운 뒤 1~100자 |
| `productId` | 아니오 | 없음 | 상품 하나만 검색할 때의 상품 ID(UUID). 홈 화면의 카드를 누를 때 쓴다(3.17.1). `query`와 함께 보낼 수 없다 |
| `lat` | 아니오 | 없음 | 고객 위치 위도. -90~90. `lng`와 함께 보내야 한다 |
| `lng` | 아니오 | 없음 | 고객 위치 경도. -180~180. `lat`과 함께 보내야 한다 |
| `limit` | 아니오 | `50` | 반환할 결과 행(`items`)의 최대 개수. 1~100 |
| `source` | 아니오 | `input` | 검색을 시작한 곳. `input`(검색창에 직접 입력), `recent`(최근 검색을 다시 누름), `popular`(요즘 많이 찾는 위스키 카드를 누름, 3.17). 검색 집계(3.10.6)에만 쓰며 결과에는 영향이 없다 |

고객 위치는 거리 계산에만 사용하며 서버에 저장하지 않는다. 서버 접근 로그에서도 `lat`, `lng`를 지우고 나머지 query(검색어 등)만 남긴다. 인기 위스키 순위를 위한 검색 집계(3.10.6)에도 위치는 남기지 않는다.

#### 3.10.1 검색어 해석

검색어는 메뉴 등록의 상품 매칭과 같은 백엔드 공통 정규화 함수로 정규화한다. 검색 시점에는 임베딩 모델과 LLM을 호출하지 않고, 아래 단계를 순서대로 시도해 활성 상품을 하나라도 찾은 단계에서 멈춘다. 찾은 상품을 판매하는 업장이 없어도 다음 단계로 넘어가지 않는다.

```text
1. brand
   brand_aliases.normalized_alias 정확 일치
   → 해당 브랜드의 활성 상품 전체 (상품 별칭과도 정확히 같아도 이 단계에서 멈춘다)
   + 검색어와 같은 검색용 별칭을 가진 다른 브랜드의 활성 상품
   정확 일치 상품을 먼저 둔다(3.10.2)

2. alias_exact
   product_aliases.normalized_alias 정확 일치
   (is_searchable = true, products.is_active = true)

3. partial
   is_searchable 상품 별칭 중 정규화 검색어를 포함하는 별칭
   → 일치한 상품 최대 10개 (일치한 별칭이 짧은 상품부터)

4. none
   일치하는 상품 없음
   5단계가 켜져 있으면 응답하기 전에 5단계를 시도한다

5. similar (서버 설정 SEARCH_SIMILAR_ENABLED=true일 때만, 기본 꺼짐)
   1~3단계가 아무것도 찾지 못해 none이 될 query 검색에만
   검색어와 활성 상품의 표시명(display_name)·검색용 별칭(is_searchable = true)의
   문자 TF-IDF 코사인 유사도. 상품 점수는 그 상품 텍스트들 중 최고값
   → 유사도 SEARCH_SIMILAR_MIN_SIMILARITY(기본 0.38) 이상인 상품 최대 5개 (유사도 높은 상품부터)
   넘는 상품이 없으면 none 그대로
```

5단계 `similar`는 메뉴 등록의 임베딩 후보 단계(I3-P40, `docs/menu_ai_matching_flow.md` 6장)와 같은 문자 1~3-gram TF-IDF를 서버 프로세스 안에서 계산한다. 모델 파일과 외부 호출이 없고 같은 카탈로그에서는 같은 검색어가 항상 같은 결과를 준다. 검색어는 정규화하지 않고 앞뒤 공백만 지운 원문으로 비교한다(TF-IDF가 스스로 소문자로 바꾸고 공백을 지운다). P40이 메뉴 줄을 읽은 그대로 비교하는 것과 같으며, 하한 0.38도 이 방식으로 정한 값이다. 예: `글렌피딕 12년산` → Glenfiddich 12가 먼저, `잭다니엘 7` → Jack Daniel's Old No.7이 먼저 나온다. `similar`의 상품은 고객이 입력한 상품으로 확인된 것이 아니라 이름이 가장 비슷한 상품이다. 5단계 계산이 실패하면 서버 로그에만 남기고 `none`으로 응답한다.

`productId`로 검색하면 위 단계를 거치지 않는다. 그 상품이 활성 상품이면 `matchType = product`이고 `matchedProducts`는 그 상품 하나다. 없는 상품이거나 비활성 상품이면 `matchType = none`, `matchedProducts = []`다. 홈 화면을 띄운 뒤 상품이 비활성화될 수 있으므로 `404`가 아니라 결과 없음(3.10.4)으로 응답한다. 상품명으로 검색하지 않는 이유는 상품명이 브랜드 별칭이기도 하면(예: `Knob Creek`) 1단계에서 브랜드 전체가 나오기 때문이다.

브랜드 단계를 먼저 시도하는 이유: 대표 상품이 브랜드 이름을 별칭으로 갖는 경우가 많다(예: Royal Brackla 12의 별칭 `Royal Brackla`). 상품 별칭을 먼저 보면 `Royal Brackla`는 12년만, `로얄브라클라`는 그 브랜드의 상품 전체를 돌려주어 고객이 입력한 표기에 따라 결과가 달라진다. 브랜드 이름의 어떤 표기로 찾든 같은 결과를 주기 위해 브랜드 별칭과 정확히 같은 검색어는 브랜드 결과로 해석한다. `로얄브라클라 12년`처럼 브랜드 이름보다 긴 검색어는 브랜드 별칭과 같지 않으므로 상품 별칭 단계에서 그 상품을 찾는다. 브랜드에 활성 상품이 없으면 다음 단계로 넘어간다.

브랜드 결과에서도 고객이 입력한 이름 그대로인 상품을 놓치지 않도록, 검색어와 같은 검색용 별칭을 가진 상품("정확 일치 상품")은 `matchedProducts`와 `items`에서 먼저 둔다. 예를 들어 `요이치`는 Yoichi 브랜드 전체를 돌려주되, 별칭이 `요이치`인 Yoichi Single Malt를 Yoichi 10보다 앞에 둔다. 정확 일치 상품이 다른 브랜드의 상품이어도 결과에 포함한다. 같은 브랜드라도 표기에 따라 정확 일치 상품이 달라질 수 있으므로(예: `Yoichi`는 어떤 상품 별칭과도 같지 않다), 상품 집합은 같아도 순서는 표기에 따라 다를 수 있다.

어느 단계든 일치한 상품이 여러 개이면 모든 상품의 판매 업장을 하나의 목록으로 합쳐 반환한다. 예를 들어 `글렌피딕`이 브랜드 별칭으로 해석되면 Glenfiddich 12, 15, 18을 판매하는 업장이 함께 나온다. 각 결과에는 상품 정보가 포함되므로 프론트엔드는 카드마다 상품명을 표시한다.

검색 시점에 임베딩 모델과 LLM을 호출하지 않는 이유는 다음과 같다. 5단계 `similar`는 모델 호출이 아니라 서버 안의 결정적 문자 TF-IDF 계산이고, 앞 단계가 아무것도 찾지 못했을 때만 실행되므로 이 이유와 충돌하지 않는다.

- 검색은 입력마다 호출되므로 모델 호출 지연과 비용을 피한다. `similar`의 계산은 검색 한 번에 수 ms다(서비스 카탈로그 약 530개 상품·4천여 텍스트 기준). 색인은 첫 계산 때 한 번 만들고 카탈로그가 바뀔 때만 다시 만든다.
- 같은 검색어가 항상 같은 결과를 반환하도록 결정적으로 유지한다.
- 의미가 비슷한 다른 상품이 섞이는 오검색을 막는다. MVP 카탈로그는 운영자가 한글·영문 별칭을 함께 등록하므로 별칭 조회만으로 주요 표기를 처리할 수 있다. 그래서 `similar`는 별칭 단계가 모두 실패했을 때만 시도하고, `matchType = similar`로 구분해 프론트엔드가 "비슷한 상품"으로 보여 줄 수 있게 한다.

#### 3.10.2 결과 구성

결과 한 행은 `업장 × 상품` 조합이며, 같은 업장과 같은 상품의 행은 하나뿐이다. 다음 조건을 모두 만족하는 항목만 포함한다.

- 일치한 상품이 `bar_menu_items`로 업장과 연결되어 있다.
- 해당 `bar_menu_item`이 업장의 현재 `menu_board_entries`에 포함되어 있다.
- 업장의 `status`가 `active`다.

다음 대상은 결과에서 빠진다.

| 대상 | 이유 |
|---|---|
| 게시되지 않은 메뉴 | 처리 중, 검수 중(`ready_for_review`), 실패한 메뉴 등록 작업은 현재 메뉴판을 바꾸지 않는다. `review-and-apply`로 반영된 뒤부터 검색된다 |
| 현재 메뉴판에서 내려간 항목 | `bar_menu_items`에 남아 있어도 현재 `menu_board_entries`에 없으면 제외한다 |
| 비활성 업장 | `bars.status = inactive` |
| 메뉴판이 없는 업장 | 반영된 메뉴가 아직 없다 |
| 비상품 항목 | 섹션 제목, 설명 등 상품이 아닌 줄은 상품과 연결된 메뉴 항목이 되지 않는다 |
| 상품에 연결되지 않은 메뉴 항목 | 연결을 기다리는 위스키와 위스키가 아닌 메뉴(3.9의 `productId = null`). 업장 메뉴(3.9)에는 보이지만 상품이 없어 검색어와 일치할 수 없다. 운영자가 위스키 항목을 상품에 연결하면 그때부터 검색된다. 인기 위스키(3.17)의 `barCount`에도 세지 않는다 |
| 비활성 상품 | `products.is_active = false`인 상품은 어느 단계에서도 일치하지 않는다 |
| 검색 제외 별칭 | `is_searchable = false`인 상품 별칭으로는 `alias_exact`와 `partial`에서 일치하지 않고, `similar`에서도 비교하지 않는다 |
| 품절 항목 | `soldOut`인 항목(3.14.8). 이 API는 공개 API라 호출자와 관계없이 빠지며, 판매 중으로 되돌리면 바로 다시 검색된다 |

정렬 기준:

```text
items
  정확 일치 상품의 행 먼저, 그다음 나머지 (brand 단계에서만 차이가 난다)
  각 묶음 안에서
    lat·lng가 있으면  distanceMeters 오름차순
    lat·lng가 없으면  menuUpdatedAt 내림차순
    동점이면          barName → productDisplayName → barId → productId 오름차순

matchedProducts
  alias_exact  displayName 오름차순
  product      그 상품 하나
  brand        정확 일치 상품 먼저, 그다음 나머지. 각 묶음 안에서 displayName 오름차순
  partial      일치한 별칭이 짧은 상품부터, 같으면 displayName 오름차순
  similar      유사도가 높은 상품부터, 같으면 displayName 오름차순

options
  sortOrder 오름차순
```

개수 제한:

- MVP의 업장 수가 약 20곳이므로 cursor 페이지네이션은 두지 않는다. `items`는 정렬한 뒤 앞에서부터 `limit`개까지만 반환하고, 잘렸으면 `truncated = true`다.
- `matchedProducts`는 `limit`의 영향을 받지 않는다. `partial`은 최대 10개, `similar`는 최대 5개, `brand`는 해당 브랜드의 활성 상품 전체다.
- `matchedProducts[].resultCount`는 `limit`을 적용하기 전의 행 수다. 따라서 `truncated = true`이면 `resultCount`의 합이 `items` 개수보다 크다.

#### 3.10.3 응답

`200 OK`

```json
{
  "query": "글렌피딕",
  "matchType": "brand",
  "matchedProducts": [
    {
      "productId": "44444444-4444-4444-8444-444444444444",
      "displayName": "Glenfiddich 12",
      "brandName": "Glenfiddich",
      "ageYears": 12,
      "editionName": null,
      "resultCount": 2
    },
    {
      "productId": "55555555-5555-4555-8555-555555555555",
      "displayName": "Glenfiddich 15",
      "brandName": "Glenfiddich",
      "ageYears": 15,
      "editionName": null,
      "resultCount": 0
    }
  ],
  "items": [
    {
      "barId": "22222222-2222-4222-8222-222222222222",
      "barName": "관악 위스키 바",
      "address": "서울특별시 관악구 관악로 1 2층",
      "latitude": 37.478321,
      "longitude": 126.951234,
      "distanceMeters": 41,
      "coverThumbnailUrl": "https://bottlemap.o-r.kr/api/bar-photos/12121212-1212-4212-8212-121212121211/thumbnail",
      "productId": "44444444-4444-4444-8444-444444444444",
      "productDisplayName": "Glenfiddich 12",
      "menuDisplayName": "글렌피딕 12년",
      "options": [
        {
          "optionLabel": "잔",
          "pourMl": 30,
          "priceKrw": 17000,
          "discount": {
            "discountedPriceKrw": 14000,
            "startsAt": "2026-11-01T09:00:00Z",
            "endsAt": "2026-11-15T15:00:00Z"
          },
          "sortOrder": 1
        },
        {
          "optionLabel": "병",
          "pourMl": null,
          "priceKrw": 160000,
          "discount": null,
          "sortOrder": 2
        }
      ],
      "menuUpdatedAt": "2026-10-04T09:15:00Z"
    },
    {
      "barId": "33333333-3333-4333-8333-333333333333",
      "barName": "신림 몰트 하우스",
      "address": "서울특별시 관악구 신림로 2 3층",
      "latitude": 37.484102,
      "longitude": 126.929815,
      "distanceMeters": 1989,
      "coverThumbnailUrl": null,
      "productId": "44444444-4444-4444-8444-444444444444",
      "productDisplayName": "Glenfiddich 12",
      "menuDisplayName": "Glenfiddich 12Y",
      "options": [
        {
          "optionLabel": null,
          "pourMl": 15,
          "priceKrw": 9000,
          "discount": null,
          "sortOrder": 1
        }
      ],
      "menuUpdatedAt": "2026-10-02T11:00:00Z"
    }
  ],
  "truncated": false
}
```

| 필드 | 타입 | null 가능 | 설명 |
|---|---|---|---|
| `query` | 문자열 | 예 | 앞뒤 공백을 지운 검색어. 정규화한 값이 아니다. `productId`로 검색했으면 `null` |
| `matchType` | `alias_exact` \| `brand` \| `partial` \| `similar` \| `product` \| `none` | 아니오 | 검색어를 해석한 단계(3.10.1). `product`는 `productId`로 검색해 그 상품을 찾은 경우다. `similar`는 서버가 5단계를 켰을 때만 나오며, 일치하는 별칭이 없어 이름이 비슷한 상품을 돌려준 경우다. 프론트엔드는 모르는 값이 와도 `matchedProducts`와 `items`로 화면을 정해야 한다(3.10.4) |
| `matchedProducts` | 배열 | 아니오 | 검색어로 해석된 상품 전체. 판매 업장이 없는 상품도 포함한다. 없으면 `[]` |
| `matchedProducts[].productId` | UUID 문자열 | 아니오 | |
| `matchedProducts[].displayName` | 문자열 | 아니오 | 정규 상품명(`products.display_name`) |
| `matchedProducts[].brandName` | 문자열 | 아니오 | 브랜드 대표명(`brands.canonical_name`) |
| `matchedProducts[].ageYears` | 정수 | 예 | 숙성 연수. 표기가 없는 상품은 `null` |
| `matchedProducts[].editionName` | 문자열 | 예 | 에디션명. 없으면 `null` |
| `matchedProducts[].resultCount` | 정수 | 아니오 | `limit` 적용 전 이 상품의 결과 행 수. 판매 업장이 없으면 `0` |
| `items` | 배열 | 아니오 | 결과 행. 없으면 `[]` |
| `items[].barId` | UUID 문자열 | 아니오 | |
| `items[].barName` | 문자열 | 아니오 | |
| `items[].address` | 문자열 | 아니오 | |
| `items[].latitude`, `items[].longitude` | 숫자 | 아니오 | 업장 좌표(WGS84). 3.9.4 |
| `items[].distanceMeters` | 정수 | 예 | 고객 위치와 업장 사이의 직선 거리(미터). 위치를 보내지 않으면 `null` |
| `items[].coverThumbnailUrl` | 문자열 | 예 | 업장 대표 사진(`photos`의 첫 사진, 3.16.1)의 썸네일 URL(`thumbnailUrl`). 3.16.5와 같은 고정 URL이다. 사진이 없으면 `null`이며 프론트엔드는 기본 이미지를 보여 준다 |
| `items[].productId` | UUID 문자열 | 아니오 | `matchedProducts`의 상품 중 하나 |
| `items[].productDisplayName` | 문자열 | 아니오 | 정규 상품명(`products.display_name`) |
| `items[].menuDisplayName` | 문자열 | 아니오 | 업장 메뉴판에 적힌 표기(`menu_board_entries.display_name`) |
| `items[].options` | 배열 | 아니오 | 해당 항목의 가격·용량 옵션 전체. 최소 1개. 결과 카드에 어떤 옵션을 표시할지는 프론트엔드가 정한다 |
| `items[].options[].optionLabel` | 문자열 | 예 | 메뉴판의 `잔`, `병` 같은 표기. 없으면 `null` |
| `items[].options[].pourMl` | 정수 | 예 | 용량(ml). 메뉴판에 없으면 `null` |
| `items[].options[].priceKrw` | 정수 | 아니오 | 정가(원) |
| `items[].options[].discount` | 객체 | 예 | 기간 할인. 3.9의 `options[].discount`와 같으며, 할인 중인지는 프론트엔드가 계산한다. 없거나 끝났으면 `null` |
| `items[].options[].sortOrder` | 정수 | 아니오 | 옵션 표시 순서 |
| `items[].menuUpdatedAt` | RFC 3339 문자열 | 아니오 | 업장 현재 메뉴판의 `menu_boards.published_at` |
| `truncated` | 불리언 | 아니오 | `limit`보다 많은 행이 일치했으면 `true` |

#### 3.10.4 결과가 0건일 때

결과가 없어도 `200 OK`이며 `items = []`, `truncated = false`다. 프론트엔드는 다음 두 경우를 구분해 빈 상태를 표시한다.

```text
matchType = none, matchedProducts = []  → 인식할 수 없는 상품명. 다른 이름으로 검색하도록 안내
matchedProducts ≠ [] 이고 items = []    → 상품은 확인했지만 현재 판매하는 업장 없음. matchedProducts의 상품명을 함께 표시
```

`matchType = similar`이면 `matchedProducts`와 `items`는 다른 단계와 같은 형식이고 위 구분도 그대로 쓴다. 다만 상품은 고객이 입력한 이름과 정확히 일치한 것이 아니라 이름이 가장 비슷한 상품이다. 프론트엔드는 결과 위에 "비슷한 메뉴를 보여 드려요" 같은 안내를 보여 줄 수 있다(필수 아님). 안내 없이 다른 결과처럼 보여 줘도 계약 위반은 아니다. `items = []`이면 "상품은 확인했지만"이 아니라 비슷한 상품도 판매하는 업장이 없다는 뜻이다.

```json
{
  "query": "없는 위스키",
  "matchType": "none",
  "matchedProducts": [],
  "items": [],
  "truncated": false
}
```

`productId`로 검색해 `matchType = none`이면 그 상품을 더 찾을 수 없다는 뜻이다. 프론트엔드는 "상품 정보를 찾을 수 없음"을 보여 주고, 홈 화면으로 돌아가면 3.17을 다시 불러온다.

#### 3.10.5 검증 오류와 프론트엔드 처리

입력이 잘못되면 `422 VALIDATION_FAILED`를 반환한다(9.1, 9.3).

| 상황 | `fieldErrors[].path` | `fieldErrors[].code` | 프론트엔드 처리 |
|---|---|---|---|
| `query`와 `productId`를 둘 다 보내거나 둘 다 빠뜨림 | `productId` | `EXACTLY_ONE_REQUIRED` | 앱 버그. 일반 오류와 재시도 |
| `productId`가 UUID가 아님 | `productId` | `UUID_PARSING` | 앱 버그. 일반 오류와 재시도 |
| 빈 문자열이거나 공백뿐 | `query` | `BLANK` | 검색창 아래에 검색어 입력 안내 |
| 앞뒤 공백을 지운 뒤 100자 초과 | `query` | `STRING_TOO_LONG` | 검색창 아래에 100자 제한 안내 |
| 정규화하면 남는 문자가 없음 (예: `!!!`) | `query` | `NOT_SEARCHABLE` | 검색창 아래에 검색할 수 있는 문자가 없다는 안내 |
| `lat`과 `lng` 중 하나만 보냄 | 빠진 쪽 (`lat` 또는 `lng`) | `LAT_LNG_REQUIRED_TOGETHER` | 앱 버그. 일반 오류와 재시도 |
| `lat`, `lng`, `limit`이 범위를 벗어남 | 해당 파라미터 | `GREATER_THAN_EQUAL`, `LESS_THAN_EQUAL` | 앱 버그. 일반 오류와 재시도 |
| `lat`, `lng`, `limit`이 숫자가 아님 | 해당 파라미터 | `FLOAT_PARSING`(`lat`, `lng`), `INT_PARSING`(`limit`) | 앱 버그. 일반 오류와 재시도 |
| `source`가 `input`, `recent`, `popular`가 아님 | `source` | `LITERAL_ERROR` | 앱 버그. 일반 오류와 재시도 |

- 범위, 숫자 형식, UUID 형식, 허용 값 오류는 한 응답의 `fieldErrors`에 여러 개 올 수 있다. 이 검사를 모두 통과한 뒤에 `EXACTLY_ONE_REQUIRED`, `BLANK`, `STRING_TOO_LONG`, `LAT_LNG_REQUIRED_TOGETHER`, `NOT_SEARCHABLE`을 이 순서로 검사하며, 이 단계에서는 처음 걸린 오류 하나만 반환한다.
- 프론트엔드는 요청 전에 검색어의 앞뒤 공백을 지우고, 빈 검색어면 API를 호출하지 않는다. 검색 입력 칸은 100자로 제한한다. 그래도 서버가 `query` 오류를 반환하면 위 표대로 `code`를 기준으로 문구를 보여 준다.
- 위치 권한이 없거나 위치를 얻지 못하면 `lat`과 `lng`를 둘 다 빼고 요청한다. 결과는 `menuUpdatedAt` 순으로 정렬되고 `distanceMeters`는 `null`이다.
- 네트워크 오류와 `5xx`(`500 INTERNAL_ERROR`, `503`, 프록시의 `502`·`504` 포함)는 오류 상태와 재시도 버튼을 보여 준다(9.6).

#### 3.10.6 검색 집계

"요즘 많이 찾는 위스키"(3.17)의 순위를 정하고 카탈로그에 빠진 상품을 찾기 위해, 서버는 이 API가 `200 OK`로 응답한 검색을 서울 날짜(`YYYY-MM-DD`)별로 센다. 검색 한 번을 한 행으로 남기지 않으며, 검색어 원문과 검색 시각도 남기지 않는다.

| 집계 | 키 | 1을 더하는 검색 |
|---|---|---|
| 상품별 검색 수 | 서울 날짜, `productId`, `source` | `matchType = product`인 검색, 또는 `matchType = alias_exact`이고 `matchedProducts`가 정확히 하나인 검색 |
| 인식하지 못한 검색어 | 서울 날짜, 정규화한 검색어 | `query`로 검색해 `matchType = none`인 검색. 아래 보호 규칙에 걸리면 세지 않는다 |

- 브랜드(`brand`), 부분 일치(`partial`), 비슷한 상품(`similar`), 여러 상품이 일치한 `alias_exact`는 어느 집계에도 넣지 않는다. 한 번의 검색이 여러 상품의 수를 올리면 순위가 부풀려지기 때문이다. `similar`는 상품이 하나여도 고객이 입력한 상품으로 확인된 것이 아니므로 상품별 검색 수에 넣지 않고, 결과를 돌려주었으므로 인식하지 못한 검색어에도 넣지 않는다(`partial`과 같다). 따라서 5단계를 켜면 하한을 넘는 비슷한 상품이 있는 검색어는 인식하지 못한 검색어 집계에서 빠진다. `productId`로 검색했는데 `none`인 검색도 넣지 않는다.
- 판매 업장이 없는 상품도 센다. 순위 후보에서만 빠진다(3.17.2).
- `source`는 요청의 값이며, 보내지 않았으면 `input`이다.
- **인식하지 못한 검색어의 보호 규칙**: 고객이 검색창에 이름이나 연락처를 잘못 넣을 수 있으므로 다음을 지킨다.
  - 앞뒤 공백을 지운 원문에 `@`가 있으면 세지 않는다. 정규화한 검색어에서 `-`와 `.`을 뺀 값에 숫자가 7개 이상 이어져도 세지 않는다. 이메일과 전화번호를 거르기 위해서다. 숙성 연수나 빈티지(예: `1990`)는 7자리가 되지 않는다.
  - 한 날짜에 새로 만드는 검색어 행은 1,000개까지다. 그 뒤로는 이미 있는 검색어만 센다.
  - 30일이 지난 행은 지운다.
  - 조회 API는 두지 않는다. 팀원이 데이터베이스에서 직접 보고 카탈로그에 별칭이나 상품을 더하는 데만 쓴다.
- 상품별 검색 수는 90일이 지난 행을 지운다.
- **집계에 남기지 않는 값**: 검색어 원문, 검색 시각(날짜만 남긴다), 위치(`lat`, `lng`), 사용자 ID, IP 주소, 기기 정보, token. 이 API는 `Authorization` 헤더를 읽지 않으므로 누가 검색했는지 알 수 없다. 서버 접근 로그에는 위의 규칙대로 `lat`, `lng`를 뺀 검색어가 남는다.
- 검증 오류(`422`)와 서버 오류로 끝난 요청은 세지 않는다. 집계를 쓰다 실패해도 검색 응답은 그대로 `200 OK`로 보낸다. 실패는 서버 로그에만 남긴다.
- 집계 행은 키마다 하나뿐이므로 검색이 많아져도 행 수에는 상한이 있다. 같은 검색을 반복하면 숫자는 계속 오른다. 요청 수 제한은 이 명세의 범위 밖이다.
- 같은 검색을 다시 불러와도 한 번 더 센다. 프론트엔드는 결과 화면에서 뒤로 갔다가 돌아오는 경우처럼 같은 검색을 다시 보여 줄 때는 이미 받은 결과를 쓰고 3.10을 다시 호출하지 않는다. 사용자가 새로 검색하거나 재시도를 누를 때만 호출한다.

### 3.11 업주 신청과 승인

업주는 `user_type`이 아니라 사용자와 업장의 관계다. 로그인한 사용자가 업주 신청을 내고 operator가 승인하면, 그 사용자는 해당 업장의 업주가 된다. 업주가 되어도 `userType`은 바뀌지 않는다(보통 `customer`). 업주가 할 수 있는 일은 2.2의 권한 표를 따른다.

업장 등록은 operator가 하나씩 입력하는 방식이 아니라, 업주가 `new_bar` 신청으로 직접 등록하고 operator가 승인하는 방식으로 한다. operator가 업장을 직접 만드는 API(3.5)는 지금은 구현하지 않는다.

- 한 업장에는 현재 업주가 최대 한 명이다. 한 사용자는 여러 업장의 업주가 될 수 있다.
- 신청은 두 종류다. `existing_bar`는 이미 등록된 업장의 업주 신청이고, `new_bar`는 아직 없는 업장을 등록하면서 업주가 되는 신청이다.
- 신청자는 사업자등록번호, 대표자명, 개업일자와 연락처를 제출한다. 사업자등록증 사진을 올리면 앞의 세 값을 읽어 입력란을 미리 채울 수 있다(3.11.12).
- 신청을 만든 뒤 메뉴판 사진을 올린다(3.11.15). 승인하면 백엔드가 이 사진으로 메뉴 등록 작업을 만들어 AI 분석을 미리 시작하므로, 업주는 처음 업장 관리에 들어갔을 때 바로 검수할 수 있다(3.11.7).
- `new_bar` 신청은 매장 대표 사진 한 장을 함께 올릴 수 있다(선택, 3.11.17). operator가 신청을 볼 때 실제 매장인지 확인하는 데 쓰고, 승인하면 새 업장의 첫 매장 사진(3.16)이 된다.
- 백엔드는 신청을 받을 때 국세청 사업자등록정보 진위확인 API로 사업자등록번호, 대표자명, 개업일자가 서로 맞는지 1차 검증한다(3.11.2). 맞지 않으면 신청을 만들지 않고 신청자가 입력을 고치게 한다. 검증 서비스에 연결하지 못하면 신청은 받고 결과를 `unavailable`로 남긴다.
- 신청서의 나머지를 채우기 전에 세 값만 먼저 확인할 수도 있다(3.11.16). 확인 결과가 맞으면 백엔드가 잠시 기억했다가, 같은 값으로 신청하면 국세청을 다시 부르지 않고 그 결과를 쓴다.
- 외부 API를 부르는 요청은 사용자마다 하루 5회로 제한한다: 국세청 진위확인(신청할 때 3.11.2와 신청 전 확인 3.11.16을 합쳐서)과 사업자등록증 OCR(3.11.12). 남의 사업자등록번호로 대표자명과 개업일자를 맞춰 보는 시도와 외부 API 호출 한도 소진을 막기 위해서다. 규칙은 3.11.14에 있다.
- operator는 웹 대시보드에서 신청과 검증 결과를 보고, 실제 매장이 있는지 확인한 뒤 승인하거나 거절한다.
- 사업자등록번호, 대표자명, 개업일자, 연락처는 신청자 본인과 operator에게만 보여 준다. 검증 결과 중 신청자에게는 사업자 상태(`businessStatus`)만 보여 준다. 백엔드는 이 값들을 로그에 남기지 않는다.
- 사업자등록번호는 DB에 암호화해 저장한다(`docs/schema_guide.md` 5.3). API 응답에는 지금처럼 원래 번호가 나오며, 클라이언트가 할 일은 없다.
- 같은 사업자등록번호로 낸 다른 대기 중이거나 승인된 신청이 있으면 operator 응답에 경고(`warnings`)가 붙는다(3.11.1). 막지는 않는다.
- 신청 결과는 알림으로 보내지 않는다. 신청자는 3.11.3으로 상태를 확인한다.

```text
[신청자]
GET /api/me                                  (users 행이 없으면 먼저 생성)
GET /api/search/bar-names?query=...          (기존 업장 신청이면 업장 선택, 3.11.11)
POST /api/owner-applications/business-certificate-ocr
                                             (선택. 사업자등록증 사진으로 입력란 채우기, 3.11.12)
POST /api/owner-applications/business-verification
                                             (선택. 세 값만 먼저 국세청에 확인, 3.11.16)
POST /api/owner-applications                 → 1차 검증 후 pending
                                               (정보가 맞지 않으면 422, 입력을 고쳐 다시 신청)
PUT /api/owner-applications/{id}/cover-photo → 매장 대표 사진 저장 (선택, new_bar만, 3.11.17)
PUT /api/owner-applications/{id}/menu-photos → 메뉴판 사진 저장 (pending일 때 전체 교체, 3.11.15)
GET /api/me/owner-applications               → 상태 확인
POST /api/owner-applications/{id}/cancel     → canceled (pending일 때만)

[operator, 웹 대시보드]
GET /api/owner-applications?status=pending  → 대기 목록과 검증 결과
POST /api/owner-applications/{id}/verify-business
                                             (검증 결과가 unavailable이면 다시 검증, 3.11.13)
실제 매장이 있는지 확인
POST /api/owner-applications/{id}/approve    → approved, 업주 관계 생성 (new_bar는 업장도 생성)
                                               신청 메뉴판 사진이 있으면 메뉴 등록 작업을 만들고 AI 분석 시작
                                               new_bar 대표 사진은 새 업장의 첫 매장 사진이 됨
POST /api/owner-applications/{id}/reject     → rejected, 신청 메뉴판 사진과 대표 사진 삭제

[승인 후 업주]
GET /api/me/bars                             → 내가 관리하는 업장
GET /api/bars/{barId}                        → activeMenuImport가 있으면 그 작업의 검수로 이동 (5장)
업장 정보 수정(3.7), 메뉴 등록·검수·반영(3.8, 4~8장)
```

`OwnerApplicationStatus`

```text
pending
approved
rejected
canceled
```

`approved`, `rejected`, `canceled`는 최종 상태이며 다시 바뀌지 않는다. 거절되거나 취소된 사용자는 새 신청을 낼 수 있다.

`BusinessVerificationResult`: 국세청 진위확인 결과

```text
matched       사업자등록번호, 대표자명, 개업일자가 국세청 정보와 맞음
not_matched   맞지 않음 (operator가 다시 검증했을 때만 저장된다. 신청 시점에는 신청을 만들지 않는다)
unavailable   검증 서비스 오류, 시간 초과, 호출 한도 초과로 확인하지 못함
```

국세청 API는 세 값 중 어느 것이 틀렸는지 알려 주지 않으므로 결과는 이 셋뿐이다.

`BusinessStatus`: 국세청이 알려 준 사업자 상태

```text
active      계속사업자
suspended   휴업자
closed      폐업자
```

휴업이나 폐업 사업자도 신청은 받는다. 승인할지는 operator가 판단한다.

#### 3.11.1 업주 신청 응답 형식

3.11의 신청 API는 모두 다음 `OwnerApplication` 형식으로 신청을 반환한다.

```json
{
  "applicationId": "cccccccc-cccc-4ccc-8ccc-ccccccccccc1",
  "applicationType": "existing_bar",
  "status": "pending",
  "applicant": {
    "userId": "11111111-1111-4111-8111-111111111111",
    "email": "owner@example.com",
    "displayName": "김사장"
  },
  "bar": {
    "barId": "22222222-2222-4222-8222-222222222222",
    "name": "관악 위스키 바",
    "address": "서울특별시 관악구 관악로 1 2층"
  },
  "proposedBar": null,
  "businessRegistrationNumber": "1234567891",
  "representativeName": "김사장",
  "openingDate": "2020-03-02",
  "businessStatus": "active",
  "businessVerification": {
    "result": "matched",
    "checkedAt": "2026-10-14T03:00:00Z"
  },
  "warnings": [],
  "contactPhone": "010-1234-5678",
  "applicantNote": "대표 본인입니다",
  "menuPhotos": [
    {
      "imageOrder": 1,
      "imageUrl": "https://storage.example.com/signed/owner-application-menu-1.jpg",
      "imageUrlExpiresAt": "2026-10-14T03:15:00Z"
    }
  ],
  "coverPhoto": null,
  "rejectionReason": null,
  "reviewedAt": null,
  "createdAt": "2026-10-14T03:00:00Z",
  "updatedAt": "2026-10-14T03:00:00Z"
}
```

| 필드 | 타입 | null 가능 | 설명 |
|---|---|---|---|
| `applicationId` | UUID 문자열 | 아니오 | |
| `applicationType` | `existing_bar` \| `new_bar` | 아니오 | |
| `status` | `OwnerApplicationStatus` | 아니오 | |
| `applicant.userId` | UUID 문자열 | 아니오 | 신청자 |
| `applicant.email` | 문자열 | 예 | 3.2와 같다 |
| `applicant.displayName` | 문자열 | 예 | 3.2와 같다 |
| `bar` | 객체 | 예 | `existing_bar`는 신청 대상 업장, `new_bar`는 승인으로 만든 업장. `new_bar`가 승인되기 전에는 `null` |
| `bar.barId`, `bar.name`, `bar.address` | 문자열 | 아니오 | |
| `proposedBar` | 객체 | 예 | `new_bar`에서 신청자가 적은 업장 정보. `existing_bar`는 `null` |
| `proposedBar.name`, `proposedBar.address` | 문자열 | 아니오 | |
| `proposedBar.phone` | 문자열 | 예 | |
| `businessRegistrationNumber` | 문자열 | 예 | 하이픈을 뺀 숫자 10자리. 저장된 번호를 서버의 키로 복호화하지 못할 때(키를 잃었거나 행이 손상됨)만 `null`이다. 이때 operator에게는 `BUSINESS_NUMBER_UNREADABLE` 경고가 붙는다 |
| `representativeName` | 문자열 | 아니오 | 사업자등록증의 대표자 성명 |
| `openingDate` | `YYYY-MM-DD` 문자열 | 아니오 | 사업자등록증의 개업연월일 |
| `businessStatus` | `BusinessStatus` | 예 | 마지막 검증에서 국세청이 알려 준 사업자 상태. 검증 결과가 `matched`가 아니거나 국세청이 상태를 알려 주지 않으면 `null`. 신청자에게도 보여 준다 |
| `businessVerification` | 객체 | 예 | operator에게만 값이 있고, 신청자 본인이 조회하면 `null`. operator가 자기 신청을 신청(3.11.2), 상세 조회(3.11.4), 취소(3.11.5), 사진 변경(3.11.15, 3.11.17)하면 응답에 값이 있다. 내 신청 목록(3.11.3)에서는 operator도 `null`이다 |
| `businessVerification.result` | `BusinessVerificationResult` | 아니오 | 마지막 검증 결과 |
| `businessVerification.checkedAt` | RFC 3339 문자열 | 아니오 | `result`를 얻은 시각. 신청할 때 `unavailable`이 되었으면 그 시도 시각이다. 다시 검증(3.11.13)이 실패하면 `result`와 함께 바뀌지 않는다 |
| `warnings` | 배열 | 예 | operator가 승인 전에 확인할 경고(아래 "경고"). 경고가 없으면 `[]`. `businessVerification`과 같은 규칙으로 operator에게만 값이 있고 신청자 본인에게는 `null`이다. operator가 자기 신청을 볼 때도 값이 있다 |
| `contactPhone` | 문자열 | 아니오 | 운영자가 확인을 위해 연락할 번호 |
| `applicantNote` | 문자열 | 예 | 신청자 메모 |
| `menuPhotos` | 배열 | 아니오 | 신청에 올린 메뉴판 사진(3.11.15). `imageOrder` 순서이며, 올리지 않았거나 거절·취소로 삭제되었으면 `[]` |
| `menuPhotos[].imageOrder` | 정수 | 아니오 | 1부터 시작하는 순서 |
| `menuPhotos[].imageUrl` | 문자열 | 아니오 | 짧은 만료 시간을 가진 서명 URL. 신청자 본인과 operator만 받는다. 만료되었거나 이미지 로딩이 `403`으로 실패하면 신청 상세(3.11.4)를 다시 조회해 새 URL을 받는다 |
| `menuPhotos[].imageUrlExpiresAt` | RFC 3339 문자열 | 예 | `imageUrl` 만료 시각. 만료되지 않는 URL(로컬 저장소)이면 `null` |
| `coverPhoto` | 객체 | 예 | `new_bar` 신청의 매장 대표 사진(3.11.17). 올리지 않았거나, `existing_bar`이거나, 신청이 `pending`이 아니면 `null`이다. 승인되면 업장의 매장 사진(3.16)으로 옮겨지므로 `bar.barId`의 업장 상세(3.6)에서 본다 |
| `coverPhoto.imageUrl`, `coverPhoto.thumbnailUrl` | 문자열 | 아니오 | 다시 인코딩한 사진과 썸네일(3.16.2)의 서명 URL. `menuPhotos[].imageUrl`처럼 신청자 본인과 operator만 받으며, 만료되면 신청 상세(3.11.4)를 다시 조회한다 |
| `coverPhoto.imageUrlExpiresAt` | RFC 3339 문자열 | 예 | 두 URL의 만료 시각. 만료되지 않는 URL(로컬 저장소)이면 `null` |
| `rejectionReason` | 문자열 | 예 | `rejected`일 때만 값이 있다 |
| `reviewedAt` | RFC 3339 문자열 | 예 | 승인 또는 거절 시각. 그 전에는 `null` |
| `createdAt`, `updatedAt` | RFC 3339 문자열 | 아니오 | |

**경고**

`warnings[]`는 operator가 승인하기 전에 확인할 내용이다. 경고는 승인과 거절을 막지 않는다. 각 경고는 다음 공통 형식이다.

| 필드 | 타입 | null 가능 | 설명 |
|---|---|---|---|
| `code` | 문자열 | 아니오 | 경고 종류. 지금은 `BUSINESS_NUMBER_UNREADABLE`과 `BUSINESS_NUMBER_SHARED`이며, 앞으로 늘어날 수 있다. 둘 다 있으면 이 순서다 |
| `message` | 문자열 | 아니오 | 그대로 보여 줄 한국어 문구 |
| `details` | 객체 | 아니오 | `code`마다 다른 형식 |

프론트엔드는 모르는 `code`의 경고를 무시하지 않고 `message`만 보여 준다.

`BUSINESS_NUMBER_UNREADABLE`: 저장된 사업자등록번호를 서버의 키로 복호화하지 못했다. `businessRegistrationNumber`는 `null`이고, `details`는 `{}`이다. 다시 검증(3.11.13)은 `500 BUSINESS_NUMBER_UNREADABLE`이다. 서버의 키 설정을 고쳐야 하며(`backend/DEPLOY.md`의 "Business number keys"), 신청자에게는 경고 없이 `businessRegistrationNumber = null`만 보인다. 한 신청을 읽지 못해도 목록의 다른 신청은 그대로 나온다.

```json
{
  "code": "BUSINESS_NUMBER_UNREADABLE",
  "message": "저장된 사업자등록번호를 읽을 수 없습니다. 서버의 키 설정을 확인해 주세요.",
  "details": {}
}
```

`BUSINESS_NUMBER_SHARED`: 사업자등록번호가 같은 다른 신청이 있다. 번호를 복호화하지 못한 신청도 검색용 값으로 찾는다.

- 대상은 상태가 `pending`이나 `approved`인 신청이다. 신청자와 신청 종류는 가리지 않으며, 같은 신청자의 다른 신청도 포함한다. 지금 보는 신청 자신만 뺀다. `rejected`와 `canceled`는 대상이 아니다.
- 업주가 해제된(3.11.10) 업장의 신청도 `approved`로 남아 있으므로 대상이다.
- 사업자 단위 과세 사업자는 여러 매장이 한 번호를 쓰므로 막지 않고 경고만 한다. operator는 같은 사업자의 다른 매장인지 확인한다.
- 신청자에게는 보여 주지 않는다. 다른 사람이 그 번호로 신청했는지 알아낼 수 있게 되기 때문이다.

```json
{
  "code": "BUSINESS_NUMBER_SHARED",
  "message": "같은 사업자등록번호로 낸 다른 신청이 2건 있습니다. 같은 사업자의 다른 매장인지 확인해 주세요.",
  "details": {
    "applications": [
      {
        "applicationId": "cccccccc-cccc-4ccc-8ccc-ccccccccccc2",
        "status": "approved",
        "applicationType": "existing_bar",
        "barName": "관악 위스키 바",
        "sameApplicant": true
      },
      {
        "applicationId": "cccccccc-cccc-4ccc-8ccc-ccccccccccc3",
        "status": "pending",
        "applicationType": "new_bar",
        "barName": "신림 몰트 2호점",
        "sameApplicant": false
      }
    ]
  }
}
```

| 필드 | 타입 | null 가능 | 설명 |
|---|---|---|---|
| `details.applications` | 배열 | 아니오 | 번호가 같은 다른 신청. 최근 신청부터 |
| `details.applications[].applicationId` | UUID 문자열 | 아니오 | operator는 상세(3.11.4)로 열 수 있다 |
| `details.applications[].status` | `pending` \| `approved` | 아니오 | |
| `details.applications[].applicationType` | `existing_bar` \| `new_bar` | 아니오 | |
| `details.applications[].barName` | 문자열 | 아니오 | 업장 이름. 승인되지 않은 `new_bar`는 신청한 업장 이름(`proposedBar.name`) |
| `details.applications[].sameApplicant` | 불리언 | 아니오 | 지금 보는 신청과 신청자가 같으면 `true` |

#### 3.11.2 업주 신청

로그인한 사용자 누구나 호출할 수 있다. `users` 행이 없으면 `404 USER_NOT_FOUND`이므로 먼저 `GET /api/me`를 호출한다.

```http
POST /api/owner-applications
Authorization: Bearer <access-token>
Content-Type: application/json
```

기존 업장 신청:

```json
{
  "applicationType": "existing_bar",
  "barId": "22222222-2222-4222-8222-222222222222",
  "businessRegistrationNumber": "123-45-67891",
  "representativeName": "김사장",
  "openingDate": "2020-03-02",
  "contactPhone": "010-1234-5678",
  "applicantNote": "대표 본인입니다"
}
```

새 업장 등록 신청:

```json
{
  "applicationType": "new_bar",
  "proposedBar": {
    "name": "신림 몰트 하우스",
    "address": "서울특별시 관악구 신림로 2 3층",
    "phone": "02-1234-5678"
  },
  "businessRegistrationNumber": "123-45-67891",
  "representativeName": "김사장",
  "openingDate": "2020-03-02",
  "contactPhone": "010-1234-5678",
  "applicantNote": null
}
```

| 필드 | 필수 | 규칙 |
|---|---|---|
| `applicationType` | 예 | `existing_bar` 또는 `new_bar`. 없으면 `fieldErrors[].code = UNION_TAG_NOT_FOUND`, 다른 값이면 `UNION_TAG_INVALID`이며, 이 두 오류의 `path`는 빈 문자열이다 |
| `barId` | `existing_bar`만 필수 | 활성 업장의 UUID. 3.11.11로 찾는다. `new_bar`에서 보내면 `EXTRA_FORBIDDEN` |
| `proposedBar` | `new_bar`만 필수 | `existing_bar`에서 보내면 `EXTRA_FORBIDDEN` |
| `proposedBar.name` | 예 | 앞뒤 공백을 지운 뒤 1~150자 |
| `proposedBar.address` | 예 | 앞뒤 공백을 지운 뒤 1~500자 |
| `proposedBar.phone` | 아니오 | 앞뒤 공백을 지운 뒤 30자 이하. 없거나 공백뿐이면 `null` |
| `businessRegistrationNumber` | 예 | 하이픈과 공백을 지운 뒤 숫자 10자리이고, 국세청 검증번호(마지막 자리) 계산이 맞아야 한다. 아니면 `INVALID_BUSINESS_NUMBER`. 하이픈 없이 저장한다 |
| `representativeName` | 예 | 사업자등록증의 대표자 성명 그대로. 앞뒤 공백을 지운 뒤 1~100자 |
| `openingDate` | 예 | 사업자등록증의 개업연월일. `YYYY-MM-DD` 문자열만 받는다(숫자는 `DATE_TYPE`, 형식 오류는 `DATE_FROM_DATETIME_PARSING`). 한국 시간 기준 오늘보다 뒤이면 `DATE_IN_FUTURE` |
| `contactPhone` | 예 | 앞뒤 공백을 지운 뒤 1~30자 |
| `applicantNote` | 아니오 | 500자 이하. 공백뿐이면 `null`로 저장한다 |

길이 규칙이 있는 문자열이 앞뒤 공백을 지운 뒤 비어 있으면 `fieldErrors[].code = STRING_TOO_SHORT`다.

새 업장의 좌표는 신청자가 보내지 않는다. 승인할 때 operator가 주소를 확인하고 좌표를 입력한다(3.11.7).

백엔드는 다음 순서로 확인하고, 처음 걸린 단계의 오류를 반환한다. 사업자등록 정보 검증은 외부 API를 부르므로 마지막에 한다.

1. 요청 형식과 위 필드 규칙 (`422 VALIDATION_FAILED`)
2. `users` 행 (`404 USER_NOT_FOUND`)
3. `existing_bar`의 업장과 현재 업주 (`404 BAR_NOT_FOUND`, `409 BAR_OWNER_EXISTS`)
4. 본인의 대기 중 신청 (`409 OWNER_APPLICATION_EXISTS`). DB의 부분 unique 인덱스로도 보장하므로, 동시에 들어온 같은 신청은 행을 만들 때 하나만 성공하고 나머지는 `409 OWNER_APPLICATION_EXISTS`가 된다. 이때 진위확인 호출 횟수는 이미 쓴 것으로 센다
5. 최근 확인 결과: 같은 사용자가 30분 안에 신청 전 확인(3.11.16)에서 같은 세 값으로 `matched`를 받았으면, 6, 7단계를 건너뛰고 그 결과로 신청을 만든다. 국세청을 부르지 않으므로 횟수도 세지 않는다. `businessVerification.checkedAt`과 `businessStatus`는 그 확인의 값이다
6. 오늘의 진위확인 횟수 (`429 RATE_LIMITED`, 3.11.14)
7. 국세청 진위확인 API로 `businessRegistrationNumber`, `representativeName`, `openingDate` 검증
   - 맞음: 신청을 만들고 `businessVerification.result = matched`, `businessStatus`에 사업자 상태를 저장한다.
   - 맞지 않음: 신청을 만들지 않고 `422 BUSINESS_VERIFICATION_FAILED`를 반환한다.
   - 검증 서비스 오류, 시간 초과, 호출 한도 초과, 또는 서버에 검증 설정이 없음: 신청을 만들고 `businessVerification.result = unavailable`, `businessStatus = null`로 저장한다. operator가 나중에 다시 검증한다(3.11.13).

`201 Created`, `Location: /api/owner-applications/{applicationId}`, 본문은 `OwnerApplication`(`status = pending`)이다.

| HTTP | code | 발생 조건 | 프론트엔드 처리 |
|---|---|---|---|
| `401` | `UNAUTHENTICATED` | 3.1.5 | 3.1.5 |
| `404` | `USER_NOT_FOUND` | `users` 행이 없음 | `GET /api/me` 호출 후 같은 요청 재시도 |
| `404` | `BAR_NOT_FOUND` | `existing_bar`의 업장이 없거나, 비활성이거나, `barId`가 UUID 형식이 아님 | 업장 선택 화면으로 돌아가 다시 선택 |
| `409` | `BAR_OWNER_EXISTS` | 업장에 이미 현재 업주가 있음(본인 포함) | "이미 업주가 등록된 업장입니다" 안내 |
| `409` | `OWNER_APPLICATION_EXISTS` | 같은 사용자의 대기 중인 신청이 있음. `existing_bar`는 같은 업장, `new_bar`는 같은 사업자등록번호의 `new_bar` 신청. `details.applicationId`에 기존 신청 ID | 기존 신청 상세로 이동 |
| `422` | `VALIDATION_FAILED` | 위 규칙 위반. 사업자등록번호 형식이나 검증번호 오류는 `fieldErrors[].code = INVALID_BUSINESS_NUMBER`, 미래의 개업일자는 `DATE_IN_FUTURE` | `fieldErrors` 표시 |
| `422` | `BUSINESS_VERIFICATION_FAILED` | 사업자등록번호, 대표자명, 개업일자가 국세청 정보와 맞지 않음. 신청은 만들어지지 않는다 | 세 값을 사업자등록증과 같게 입력했는지 확인하라고 안내하고, 입력값을 유지한 채 수정하게 한다 |
| `429` | `RATE_LIMITED` | 오늘 진위확인을 5회 했음(3.11.14). 신청은 만들어지지 않는다. `details.retryAfter`에 다음 초기화 시각 | 내일 다시 신청하라고 안내하고, 입력값을 유지한다 |

#### 3.11.3 내 업주 신청 목록

```http
GET /api/me/owner-applications
Authorization: Bearer <access-token>
```

호출자 본인의 신청을 모든 상태에 대해 최근 신청부터 반환한다. 페이지네이션은 두지 않는다. 신청이 없거나 `users` 행이 아직 없으면 `items = []`다. 신청자 본인의 조회이므로 각 신청의 `businessVerification`과 `warnings`는 `null`이고 `businessStatus`만 보여 준다(3.11.1). operator가 호출해도 본인의 신청만 나온다.

```json
{
  "items": [
    { "applicationId": "cccccccc-cccc-4ccc-8ccc-ccccccccccc1", "status": "pending", "...": "OwnerApplication 형식" }
  ]
}
```

#### 3.11.4 업주 신청 상세

```http
GET /api/owner-applications/{applicationId}
Authorization: Bearer <access-token>
```

신청자 본인과 operator만 조회할 수 있다. 응답은 `OwnerApplication`이다. operator가 조회하면 `businessVerification`과 `warnings`(3.11.1)에 값이 있다. 신청이 없거나, 다른 사람의 신청이거나, `applicationId`가 UUID 형식이 아니면 `404 OWNER_APPLICATION_NOT_FOUND`다. 다른 사람의 신청이 있는지는 알려 주지 않는다.

#### 3.11.5 업주 신청 취소

```http
POST /api/owner-applications/{applicationId}/cancel
Authorization: Bearer <access-token>
```

신청자 본인만 호출할 수 있다. 요청 본문은 없다. `pending`이면 `canceled`로 바꾸고 `200 OK`로 `OwnerApplication`을 반환한다. 신청의 메뉴판 사진(3.11.15)과 대표 사진(3.11.17)은 삭제되므로 응답의 `menuPhotos`는 `[]`, `coverPhoto`는 `null`이다.

| HTTP | code | 발생 조건 | 프론트엔드 처리 |
|---|---|---|---|
| `404` | `OWNER_APPLICATION_NOT_FOUND` | 신청이 없거나 본인의 신청이 아님 | 신청 목록 재조회 |
| `409` | `INVALID_APPLICATION_STATE` | `pending`이 아님. `details.status`에 현재 상태 | 신청 상세 재조회 |

#### 3.11.6 operator의 업주 신청 목록

```http
GET /api/owner-applications?status=pending&applicationType=new_bar&limit=20&cursor=<cursor>
Authorization: Bearer <access-token>
```

operator만 호출할 수 있다.

| Query | 필수 | 기본값 | 설명 |
|---|---|---|---|
| `status` | 아니오 | `pending` | `pending`, `approved`, `rejected`, `canceled`, `all` |
| `applicationType` | 아니오 | 없음 | `existing_bar`, `new_bar`. 없으면 둘 다 |
| `verificationResult` | 아니오 | 없음 | `matched`, `not_matched`, `unavailable`. 없으면 모두. 다시 검증할 신청을 찾을 때 쓴다 |
| `limit` | 아니오 | `20` | 1~100 |
| `cursor` | 아니오 | 없음 | 이전 응답의 `nextCursor`. 형식은 정하지 않으며, 같은 필터로만 쓸 수 있다 |

정렬은 `status = pending`이면 오래된 신청부터(처리 순서), 그 외에는 최근 신청부터다. 응답의 각 신청에는 `businessVerification`과 `warnings`(3.11.1)가 들어 있다.

```json
{
  "items": [
    { "applicationId": "cccccccc-cccc-4ccc-8ccc-ccccccccccc1", "status": "pending", "...": "OwnerApplication 형식" }
  ],
  "nextCursor": null
}
```

`nextCursor`는 다음 페이지가 없으면 `null`이다.

| HTTP | code | 발생 조건 | 프론트엔드 처리 |
|---|---|---|---|
| `403` | `FORBIDDEN` | operator가 아님 | 3.1.5 |
| `422` | `VALIDATION_FAILED` | 허용하지 않는 `status`, `applicationType`, `verificationResult`(`LITERAL_ERROR`), `limit` 범위 밖, 읽을 수 없거나 다른 필터에서 받은 `cursor`(`INVALID_CURSOR`) | 필터를 초기화하고 첫 페이지부터 다시 조회 |

#### 3.11.7 업주 신청 승인

```http
POST /api/owner-applications/{applicationId}/approve
Authorization: Bearer <access-token>
Content-Type: application/json
```

operator만 호출할 수 있다. 사업자등록 정보 검증 결과가 `matched`가 아니어도 승인할 수 있다. 판단은 operator가 하며, 대시보드는 `unavailable`인 신청을 먼저 다시 검증(3.11.13)하도록 안내한다.

- `existing_bar`: 요청 본문이 없거나 `{}`다.
- `new_bar`: operator가 확인한 업장 정보를 보낸다. 프론트엔드는 `proposedBar`를 초기값으로 채우고, operator가 주소를 확인해 좌표를 입력한다. 필드 규칙은 3.5와 같다. `description`, `defaultPourMl`, `tags`, `weeklyHours`는 받지 않으며(`EXTRA_FORBIDDEN`, 3.7), 만든 업장은 `description`과 `defaultPourMl`이 `null`, `tags`와 `weeklyHours`가 `[]`다. 업주가 승인 뒤 3.7로 정한다. 임시 휴무도 승인 뒤 3.15로 정한다. 매장 사진은 신청의 대표 사진(3.11.17)이 있으면 그 한 장으로 시작하고, 나머지는 승인 뒤 3.16으로 올린다.

```json
{
  "bar": {
    "name": "신림 몰트 하우스",
    "address": "서울특별시 관악구 신림로 2 3층",
    "latitude": 37.484102,
    "longitude": 126.929815,
    "phone": "02-1234-5678"
  }
}
```

승인은 하나의 트랜잭션에서 처리한다.

- `existing_bar`: 업장 행을 잠그고 현재 업주가 없는지 다시 확인한 뒤 업주 관계를 만든다. 신청 뒤 업장이 비활성화되었어도 승인할 수 있다.
- `new_bar`: `bar`로 `status = active`인 업장을 만들고 업주 관계를 만든다. 만든 업장은 응답의 `bar`에 담긴다. 메뉴가 없으므로 상품 검색에는 메뉴를 반영한 뒤부터 나온다.
- `new_bar`에 대표 사진(3.11.17)이 있으면 같은 트랜잭션에서 그 사진을 새 업장의 첫 매장 사진(3.16, 대표 사진)으로 만든다. 파일은 다시 저장하지 않고 신청 때 저장한 두 파일을 그대로 쓰며, 업로드한 사람은 신청자다. 승인 응답의 `coverPhoto`는 `null`이고, 사진은 업장 상세(3.6)와 업장 목록의 `coverThumbnailUrl`에 나온다. 이때부터 공개 URL(3.16.5)로 누구나 볼 수 있다.
- 공통: 신청에 메뉴판 사진(3.11.15)이 있고 업장에 미완료 메뉴 등록 작업(4.3)이 없으면, 같은 트랜잭션에서 그 사진들로 메뉴 등록 작업을 만든다. 사진 순서가 `imageOrder`이고, `mode`는 업장에 현재 메뉴판이 없으면 `full_replace`, 있으면 `partial_update`이며, `ownerNote`는 `null`이다. 트랜잭션을 커밋한 뒤 4장의 업로드와 같은 AI 처리를 시작한다. 검수에서 확정하기 전에는 메뉴가 게시되지 않는다(8장).
- 사진이 없거나 업장에 이미 미완료 작업이 있으면 작업을 만들지 않고 승인만 한다. 미완료 작업은 operator가 업장에 먼저 올린 작업이나 해제된 이전 업주의 작업처럼 드문 경우에만 있으며, 새 업주가 그 작업을 이어서 처리하거나 취소(5.7)한 뒤 다시 올린다.

`200 OK`, 본문은 `OwnerApplication`(`status = approved`)이다. 신청자는 다음 요청부터 업주 권한을 가진다. 응답에는 만든 작업이 들어 있지 않다. 업주 화면은 업장 상세(3.6)의 `activeMenuImport`로 작업을 찾아 처리 상태나 검수(5장)를 보여 준다. AI 처리가 실패하면 작업은 `failed`가 되며, 업주가 사진을 다시 올린다(4장).

백엔드는 다음 순서로 확인하고, 처음 걸린 단계의 오류를 반환한다.

1. 호출자가 operator인지 (`403 FORBIDDEN`, 2.2)
2. 요청 형식과 `bar` 필드 규칙 (`422 VALIDATION_FAILED`)
3. 호출자의 `users` 행 (`404 USER_NOT_FOUND`). 승인한 operator를 기록해야 하기 때문이다. `users` 행이 없는 operator는 임시 로그인(3.1.3)으로만 생기며, `GET /api/me`를 먼저 호출하면 된다
4. 신청 (`404 OWNER_APPLICATION_NOT_FOUND`)과 상태 (`409 INVALID_APPLICATION_STATE`)
5. 신청 종류에 맞는 본문 (`422 VALIDATION_FAILED`, `bar` 없음은 `MISSING`, `existing_bar`에 `bar`는 `EXTRA_FORBIDDEN`)
6. 업장의 현재 업주 (`409 BAR_OWNER_EXISTS`)

| HTTP | code | 발생 조건 | 프론트엔드 처리 |
|---|---|---|---|
| `403` | `FORBIDDEN` | operator가 아님 | 3.1.5 |
| `404` | `USER_NOT_FOUND` | 호출한 operator의 `users` 행이 없음 | `GET /api/me` 호출 후 같은 요청 재시도 |
| `404` | `OWNER_APPLICATION_NOT_FOUND` | 신청이 없음 | 신청 목록 재조회 |
| `409` | `INVALID_APPLICATION_STATE` | `pending`이 아님. `details.status`에 현재 상태 | 신청 상세 재조회 |
| `409` | `BAR_OWNER_EXISTS` | 업장에 이미 현재 업주가 있음. 같은 업장의 다른 신청이 먼저 승인된 경우 | 이 신청은 거절 처리 |
| `422` | `VALIDATION_FAILED` | `new_bar`인데 `bar`가 없거나 규칙 위반, `existing_bar`인데 `bar`를 보냄(`EXTRA_FORBIDDEN`) | `fieldErrors` 표시 |

#### 3.11.8 업주 신청 거절

```http
POST /api/owner-applications/{applicationId}/reject
Authorization: Bearer <access-token>
Content-Type: application/json
```

```json
{
  "reason": "사업자등록번호를 확인할 수 없습니다."
}
```

operator만 호출할 수 있다. `reason`은 필수이며 앞뒤 공백을 지운 뒤 1~500자다. 신청자에게 그대로 보여 준다. 사업자등록 정보 검증 결과와 관계없이 거절할 수 있다. 신청의 메뉴판 사진(3.11.15)과 대표 사진(3.11.17)은 삭제한다. `200 OK`, 본문은 `OwnerApplication`(`status = rejected`, `menuPhotos = []`, `coverPhoto = null`)이다. 오류는 3.11.7의 `403`, `404`(`USER_NOT_FOUND` 포함), `409 INVALID_APPLICATION_STATE`와 같고, `422 VALIDATION_FAILED`는 `reason`이 없거나(`MISSING`), 공백뿐이거나(`BLANK`), 500자를 넘을 때(`STRING_TOO_LONG`)다.

#### 3.11.9 내가 관리하는 업장 목록

```http
GET /api/me/bars
Authorization: Bearer <access-token>
```

로그인한 사용자 누구나 호출할 수 있다. 호출자가 현재 업주인 업장을 이름순으로 반환한다. 업주가 아니거나 `users` 행이 아직 없으면 `items = []`이며, operator도 본인이 업주인 업장만 나온다(전체 업장은 3.4). 프론트엔드는 목록이 비어 있지 않으면 업주 메뉴를 보여 준다. 업장마다 3.6과 같은 형식이다.

```json
{
  "items": [
    {
      "barId": "22222222-2222-4222-8222-222222222222",
      "name": "관악 위스키 바",
      "address": "서울특별시 관악구 관악로 1 2층",
      "latitude": 37.478321,
      "longitude": 126.951234,
      "phone": "02-000-0000",
      "description": null,
      "defaultPourMl": null,
      "tags": [],
      "weeklyHours": [],
      "operatingException": null,
      "photos": [],
      "status": "active",
      "activeMenuImport": null,
      "currentMenu": {
        "menuBoardId": "66666666-6666-4666-8666-666666666666",
        "menuVersion": 4,
        "publishedAt": "2026-10-04T09:15:00Z",
        "confirmedAt": null
      },
      "owner": {
        "userId": "11111111-1111-4111-8111-111111111111",
        "email": "owner@example.com",
        "displayName": "김사장",
        "ownerSince": "2026-10-14T05:00:00Z"
      },
      "createdAt": "2026-10-01T03:00:00Z",
      "updatedAt": "2026-10-04T09:15:00Z"
    }
  ]
}
```

#### 3.11.10 업주 해제

```http
DELETE /api/bars/{barId}/owner
Authorization: Bearer <access-token>
```

operator만 호출할 수 있다. 요청 본문은 없다. 업장의 현재 업주 관계를 해제하고 `204 No Content`를 반환한다. 기록은 지우지 않고 해제 시각과 해제한 operator를 남긴다. 승인한 업주 신청은 `approved`로 남는다. 해제된 사용자는 다음 요청부터 그 업장의 업주 권한이 없으며, 같은 업장에 다시 업주 신청을 낼 수 있다(3.11.2). 비활성 업장도 해제할 수 있다. 업장에 진행 중인 메뉴 등록 작업은 그대로 남으며 operator나 새 업주가 이어서 처리할 수 있다.

- 해제는 업장 행을 잠근 뒤 한다(3.14.1). 업장 행을 잠그는 요청(메뉴 등록 작업 생성, 검수 반영, 메뉴 직접 편집, 품절, 판매 정보 확인, 임시 휴무, 매장 사진)은 잠근 뒤 업주 권한을 다시 확인하므로, 해제보다 늦게 잠금을 잡은 이전 업주의 요청은 `403 FORBIDDEN`이다. 같은 업장의 `existing_bar` 신청 승인(3.11.7)과도 차례로 처리된다.
- 이미 해제한 업장에 다시 보내면 `404 BAR_OWNER_NOT_FOUND`다. 프론트엔드는 응답을 받지 못해 다시 보낸 요청이 이 오류를 받으면 업장 상세(3.6)를 다시 불러 `owner = null`인지 확인한다.

백엔드는 다음 순서로 확인하고, 처음 걸린 단계의 오류를 반환한다.

1. 호출자가 operator인지 (`403 FORBIDDEN`, 2.2)
2. 호출자의 `users` 행 (`404 USER_NOT_FOUND`). 해제한 operator를 기록해야 하기 때문이다. 3.11.7과 같다
3. 업장 (`404 BAR_NOT_FOUND`)
4. 업장 행을 잠근 뒤 현재 업주 (`404 BAR_OWNER_NOT_FOUND`)

| HTTP | code | 발생 조건 | 프론트엔드 처리 |
|---|---|---|---|
| `403` | `FORBIDDEN` | operator가 아님 | 3.1.5 |
| `404` | `USER_NOT_FOUND` | 호출한 operator의 `users` 행이 없음 | `GET /api/me` 호출 후 같은 요청 재시도 |
| `404` | `BAR_NOT_FOUND` | 업장이 없거나 `barId`가 UUID 형식이 아님 | 업장 목록으로 이동 |
| `404` | `BAR_OWNER_NOT_FOUND` | 업장에 현재 업주가 없음 | 업장 상세(3.6) 재조회 |

#### 3.11.11 업장 이름 검색

업장 이름이나 주소의 일부로 활성 업장을 찾는다. 상품으로 업장을 찾는 고객 검색(3.10)과는 다른 API다. 두 곳에서 사용한다.

- 업주 신청: `existing_bar` 신청에서 신청자가 자기 업장을 고른다.
- 고객 지도 검색: 지도 화면에서 업장 이름으로 찾아 그 위치로 지도를 옮긴다. 이미 불러온 영역 밖의 업장도 찾을 수 있다.

```http
GET /api/search/bar-names?query=%EA%B4%80%EC%95%85&limit=20
```

로그인 없이 호출할 수 있는 공개 API이며 `Authorization` 헤더를 사용하지 않는다. 반환하는 값은 활성 업장의 공개 정보(3.9에서도 볼 수 있는 이름, 주소, 좌표, 대표 사진)와 업주 등록 여부뿐이다.

| Query | 필수 | 기본값 | 설명 |
|---|---|---|---|
| `query` | 예 | 없음 | 업장 이름 또는 주소의 일부. 앞뒤 공백을 지운 뒤 1~100자. 대소문자를 구분하지 않는다 |
| `limit` | 아니오 | `20` | 1~50 |

`200 OK`. 이름순으로 반환하고 페이지네이션은 두지 않는다. 결과가 없으면 `items = []`다.

```json
{
  "items": [
    {
      "barId": "22222222-2222-4222-8222-222222222222",
      "name": "관악 위스키 바",
      "address": "서울특별시 관악구 관악로 1 2층",
      "latitude": 37.478321,
      "longitude": 126.951234,
      "coverThumbnailUrl": "https://bottlemap.o-r.kr/api/bar-photos/12121212-1212-4212-8212-121212121211/thumbnail",
      "hasOwner": true
    }
  ],
  "truncated": false
}
```

| 필드 | 타입 | null 가능 | 설명 |
|---|---|---|---|
| `items[].barId` | UUID 문자열 | 아니오 | |
| `items[].name`, `items[].address` | 문자열 | 아니오 | |
| `items[].latitude`, `items[].longitude` | 숫자 | 아니오 | 업장 좌표(WGS84). 3.9.4. 고객 지도 검색에서 지도를 옮길 위치 |
| `items[].coverThumbnailUrl` | 문자열 | 예 | 업장 대표 사진(`photos`의 첫 사진, 3.16.1)의 썸네일 URL(`thumbnailUrl`). 3.16.5와 같은 고정 URL이다. 사진이 없으면 `null`이며 프론트엔드는 기본 이미지를 보여 준다. 업주 신청에서 자기 업장을 알아보는 데도 쓴다 |
| `items[].hasOwner` | 불리언 | 아니오 | 현재 업주가 있으면 `true`. 이 업장에 신청하면 `409 BAR_OWNER_EXISTS`다 |
| `truncated` | 불리언 | 아니오 | `limit`보다 많이 일치했으면 `true` |

비활성 업장은 결과에 없다.

- 업주 신청: 신청자의 업장이 목록에 없으면 프론트엔드는 `new_bar` 신청을 안내한다. `hasOwner = true`인 업장은 선택할 수 없게 하고 operator 문의를 안내한다.
- 고객 지도 검색: `hasOwner`는 쓰지 않는다. 결과를 고르면 그 좌표로 지도를 옮기고, 옮긴 영역의 업장은 3.13으로 불러온다. 결과가 없으면 등록된 업장이 없다고 안내한다.

| HTTP | code | 발생 조건 | 프론트엔드 처리 |
|---|---|---|---|
| `422` | `VALIDATION_FAILED` | `query` 없음(`MISSING`), 공백뿐(`BLANK`), 100자 초과(`STRING_TOO_LONG`), `limit` 범위 밖 | 검색창 아래에 안내 |

#### 3.11.12 사업자등록증 사진 읽기

신청자가 사업자등록증 사진을 올리면 신청 입력란을 미리 채울 값을 읽어 돌려준다. 신청은 만들지 않으며 선택 기능이다. 사진이 없거나 이 API가 실패해도 신청자는 값을 직접 입력해 3.11.2로 신청할 수 있다.

```http
POST /api/owner-applications/business-certificate-ocr
Authorization: Bearer <access-token>
Content-Type: multipart/form-data
```

| multipart 필드 | 타입 | 필수 | 설명 |
|---|---|---|---|
| `image` | 이미지 파일 1개 | 예 | 사업자등록증 사진. JPEG 또는 PNG, 10MB 이하. 형식 판별은 4.1과 같다 |

로그인한 사용자 누구나 호출할 수 있고 `users` 행이 없어도 된다. 백엔드는 메뉴 사진과 같은 CLOVA OCR로 글자를 읽고 정해진 규칙으로 항목을 찾는다. 처리는 동기이며 작업을 만들지 않는다. **사진과 읽은 값은 서버에 저장하지 않고 로그에도 남기지 않는다.**

`200 OK`

```json
{
  "businessRegistrationNumber": "1234567891",
  "representativeName": "김사장",
  "openingDate": "2020-03-02",
  "businessName": "신림 몰트 하우스",
  "address": "서울특별시 관악구 신림로 2 3층"
}
```

| 필드 | 타입 | null 가능 | 설명 |
|---|---|---|---|
| `businessRegistrationNumber` | 문자열 | 예 | 하이픈을 뺀 10자리. 검증번호 계산(3.11.2)이 맞지 않으면 잘못 읽은 것으로 보고 `null` |
| `representativeName` | 문자열 | 예 | 대표자 성명 |
| `openingDate` | `YYYY-MM-DD` 문자열 | 예 | 개업연월일. 날짜로 읽을 수 없으면 `null` |
| `businessName` | 문자열 | 예 | 상호. `new_bar` 신청의 `proposedBar.name` 초기값으로 쓸 수 있다 |
| `address` | 문자열 | 예 | 사업장 소재지. `new_bar` 신청의 `proposedBar.address` 초기값으로 쓸 수 있다 |

읽지 못한 항목은 `null`이며, 하나도 읽지 못해도 `200`에 모든 값이 `null`이다. 프론트엔드는 읽은 값으로 입력란을 채우고 신청자가 확인하고 고친 뒤 신청하게 한다. 읽은 값을 확인 없이 바로 제출하지 않는다. 사업자등록 정보 검증은 이 API가 아니라 3.11.2에서 한다.

| HTTP | code | 발생 조건 | 프론트엔드 처리 |
|---|---|---|---|
| `401` | `UNAUTHENTICATED` | 3.1.5 | 3.1.5 |
| `413` | `UPLOAD_TOO_LARGE` | 10MB 초과. `details.maxImageBytes`에 제한값 | 사진을 다시 압축해 재시도 |
| `415` | `UNSUPPORTED_IMAGE_TYPE` | JPEG·PNG가 아니거나 선언한 형식과 내용이 다름 | JPEG로 바꿔 재시도 |
| `422` | `VALIDATION_FAILED` | `image` 없음(`MISSING`) 또는 사진이 2개 이상 | 사진 다시 선택 |
| `429` | `RATE_LIMITED` | 오늘 OCR을 5회 했음(3.11.14). `details.retryAfter`에 다음 초기화 시각 | 직접 입력하도록 안내 |
| `503` | `OCR_UNAVAILABLE` | 서버에 OCR 설정이 없거나, OCR 호출이 재시도 후에도 실패 | 직접 입력하도록 안내. 잠시 후 다시 시도할 수 있다 |

#### 3.11.13 사업자등록 정보 다시 검증

```http
POST /api/owner-applications/{applicationId}/verify-business
Authorization: Bearer <access-token>
```

operator만 호출할 수 있다. 요청 본문은 없다. 신청에 저장된 사업자등록번호, 대표자명, 개업일자로 국세청 진위확인 API를 다시 호출하고 결과를 저장한다. 신청할 때 검증 서비스에 연결하지 못한 신청(`unavailable`)이나, 승인 전에 사업자 상태를 다시 확인할 때 쓴다.

- 검증 서비스가 응답하면 `businessVerification.result`(`matched` 또는 `not_matched`), `businessStatus`, `businessVerification.checkedAt`을 바꾸고 `200 OK`로 `OwnerApplication`을 반환한다. 신청 상태(`status`)는 바뀌지 않는다. `not_matched`이면 operator가 거절한다.
- 검증 서비스에 연결하지 못하면 저장된 결과와 `checkedAt`을 바꾸지 않고 `503 BUSINESS_VERIFICATION_UNAVAILABLE`을 반환한다. 실패한 시도는 기록하지 않는다.
- 저장된 사업자등록번호를 서버의 키로 복호화하지 못하면(3.11.1의 `BUSINESS_NUMBER_UNREADABLE`) 국세청을 부르지 않고 `500 BUSINESS_NUMBER_UNREADABLE`을 반환한다. 저장된 결과는 바뀌지 않는다. 다시 시도해도 해결되지 않으므로 검증 설정보다 먼저 확인한다(서버에 검증 설정이 없어도 이 오류다).

| HTTP | code | 발생 조건 | 프론트엔드 처리 |
|---|---|---|---|
| `403` | `FORBIDDEN` | operator가 아님 | 3.1.5 |
| `404` | `OWNER_APPLICATION_NOT_FOUND` | 신청이 없거나 `applicationId`가 UUID 형식이 아님 | 신청 목록 재조회 |
| `409` | `INVALID_APPLICATION_STATE` | `pending`이 아님. `details.status`에 현재 상태 | 신청 상세 재조회 |
| `500` | `BUSINESS_NUMBER_UNREADABLE` | 저장된 사업자등록번호를 복호화하지 못함 | 서버 키 설정 문제라고 안내. 다시 시도해도 해결되지 않는다 |
| `503` | `BUSINESS_VERIFICATION_UNAVAILABLE` | 검증 서비스 오류, 시간 초과, 호출 한도 초과, 또는 서버에 검증 설정이 없음 | 잠시 후 다시 시도 안내 |

#### 3.11.14 진위확인과 OCR 요청 수 제한

| 대상 | 한도 | 세는 요청 |
|---|---|---|
| 국세청 진위확인: 업주 신청(3.11.2)과 신청 전 확인(3.11.16) | 사용자마다 두 API를 합쳐 하루 5회 | 국세청 API를 실제로 호출한 요청. 3.11.2는 1~6단계를, 3.11.16은 요청 형식 검사를 통과한 요청이다. 결과(`matched`, `not_matched`, `unavailable`)와 관계없이 센다. 서버에 검증 설정이 없어 호출하지 않은 요청과, 최근 확인 결과를 써서 호출하지 않은 신청(3.11.2의 5단계)은 세지 않는다 |
| 사업자등록증 OCR (3.11.12) | 사용자마다 하루 5회 | `413`, `415`, `422` 검사를 통과해 CLOVA OCR을 실제로 호출한 요청. 읽은 항목이 없어도, 호출이 실패해 `503`이 되어도 센다. 서버에 OCR 설정이 없어 호출하지 않은 요청은 세지 않는다 |

- 사용자는 token의 `sub`(3.1.2)로 구분한다. OCR은 `users` 행이 없어도 호출할 수 있으므로 `users.id`가 아니라 `sub`로 센다.
- 임시 로그인(3.1.3) 토큰은 모두 `sub`가 같으므로 한도 하나를 함께 쓴다. 임시 로그인은 로컬 개발에서만 쓰므로 이 한계를 받아들인다.
- 진위확인과 OCR 한도는 따로 센다. 진위확인은 신청과 신청 전 확인을 한 한도로 센다. 국세청이 알려 주는 것은 두 API가 같으므로(세 값이 맞는지), 신청 전 확인을 따로 세면 남의 번호를 맞춰 볼 기회가 늘어나기 때문이다. operator의 다시 검증(3.11.13)은 제한하지 않는다.
- 하루는 한국 시간(KST) 자정에 초기화된다.
- 한도를 넘으면 외부 API를 호출하지 않고 `429 RATE_LIMITED`를 반환한다. `details.retryAfter`에 다음 초기화 시각(RFC 3339, UTC)을 담는다.

```json
{
  "error": {
    "code": "RATE_LIMITED",
    "message": "오늘 사업자등록 정보 확인 횟수를 모두 사용했습니다. 내일 다시 시도해 주세요.",
    "details": {
      "retryAfter": "2026-10-28T15:00:00Z"
    },
    "fieldErrors": []
  }
}
```

- 횟수는 서버 메모리에 저장한다. 서버가 재시작되면 횟수가 초기화되며, 이 한계는 받아들인다. API 프로세스가 하나(worker 1개)일 때만 한도가 정확하다.

#### 3.11.15 업주 신청 메뉴판 사진

```http
PUT /api/owner-applications/{applicationId}/menu-photos
Authorization: Bearer <access-token>
Content-Type: multipart/form-data
```

신청자 본인만 호출할 수 있다. 업주 신청(3.11.2)이 `201`로 만들어진 뒤 그 신청의 메뉴판 사진을 저장한다. 사진은 승인할 때 메뉴 등록 작업의 사진이 되어 AI 분석에 쓰이고(3.11.7), operator가 실제 매장인지 확인할 때도 본다.

| 필드 | 타입 | 필수 | 설명 |
|---|---|---|---|
| `images` | 이미지 파일 배열 | 예 | 표시 순서대로 전송한 메뉴판 사진. 배열 순서가 `imageOrder`가 된다 |

- 호출할 때마다 신청의 사진 전체를 이번 요청의 사진으로 바꾼다. 같은 요청을 다시 보내도 결과가 같으므로 `Idempotency-Key`는 받지 않는다. 사진을 추가하거나 순서를 바꾸려면 전체 목록을 다시 보낸다.
- `pending`일 때만 올릴 수 있다. 승인·거절·취소와 동시에 들어오면 신청 행을 잠가 둘 중 하나만 성공한다.
- 업로드 제한과 형식 판별은 메뉴 등록 요청(4.1)과 같다: JPEG·PNG, 최대 15장, 사진당 10MB, 전체 60MB.
- 백엔드는 사진을 메뉴 등록 사진과 같은 비공개 저장소에 둔다. 공개 API에는 나오지 않으며 신청자 본인과 operator만 `menuPhotos`(3.11.1)의 서명 URL로 볼 수 있다.
- 신청이 거절되거나 취소되면 사진을 삭제한다(3.11.5, 3.11.8). 승인되면 메뉴 등록 작업의 사진으로 남는다.
- 신청할 때 사진을 꼭 올려야 하는 것은 아니다. 사진 없이 승인된 업주는 승인 뒤 4장으로 메뉴를 올린다.

백엔드는 다음 순서로 확인하고, 처음 걸린 단계의 오류를 반환한다.

1. 요청 형식 (`422 VALIDATION_FAILED`, `images` 없음은 `MISSING`)
2. 신청과 신청자 (`404 OWNER_APPLICATION_NOT_FOUND`)
3. 신청 상태 (`409 INVALID_APPLICATION_STATE`)
4. 사진 (4.1과 같다): 개수를 확인하고(`413 UPLOAD_TOO_LARGE`), 사진을 순서대로 읽으며 크기(`413`)와 형식(`415 UNSUPPORTED_IMAGE_TYPE`)을 확인한다

`200 OK`, 본문은 `OwnerApplication`(3.11.1)이며 `menuPhotos`에 저장한 사진이 들어 있다.

| HTTP | code | 발생 조건 | 프론트엔드 처리 |
|---|---|---|---|
| `401` | `UNAUTHENTICATED` | 3.1.5 | 3.1.5 |
| `404` | `OWNER_APPLICATION_NOT_FOUND` | 신청이 없거나, 본인의 신청이 아니거나, `applicationId`가 UUID 형식이 아님 | 신청 목록 재조회 |
| `409` | `INVALID_APPLICATION_STATE` | `pending`이 아님. `details.status`에 현재 상태 | 신청 상세 재조회. 승인되었으면 사진은 4장으로 올린다 |
| `413` | `UPLOAD_TOO_LARGE` | 4.4와 같다 | 사진 수를 줄이거나 다시 압축 |
| `415` | `UNSUPPORTED_IMAGE_TYPE` | 4.4와 같다 | 해당 사진을 JPEG로 바꿔 다시 올림 |
| `422` | `VALIDATION_FAILED` | `images`가 없음 | `fieldErrors` 표시 |

신청은 만들어졌지만 사진 업로드가 실패하면, 프론트엔드는 신청을 다시 만들지 않고 같은 `applicationId`로 이 API만 다시 호출한다. 다시 신청하면 `409 OWNER_APPLICATION_EXISTS`(3.11.2)가 되며 `details.applicationId`로 기존 신청을 찾을 수 있다.

#### 3.11.16 신청 전 사업자등록 정보 확인

신청서의 나머지(업장, 연락처, 사진)를 채우기 전에 사업자등록번호, 대표자명, 개업일자가 국세청 정보와 맞는지만 확인한다. 신청은 만들지 않으며 선택 기능이다. 이 API를 부르지 않아도 3.11.2가 같은 검증을 한다.

```http
POST /api/owner-applications/business-verification
Authorization: Bearer <access-token>
Content-Type: application/json
```

```json
{
  "businessRegistrationNumber": "123-45-67891",
  "representativeName": "김사장",
  "openingDate": "2020-03-02"
}
```

세 필드의 규칙은 3.11.2와 같다(`INVALID_BUSINESS_NUMBER`, `DATE_IN_FUTURE`, `STRING_TOO_SHORT` 등). 다른 필드는 `EXTRA_FORBIDDEN`이다.

로그인한 사용자 누구나 호출할 수 있고 `users` 행이 없어도 된다(3.11.12와 같다). 사업자등록번호, 대표자명, 개업일자는 3.11의 다른 API처럼 로그에 남기지 않는다.

`200 OK`

```json
{ "result": "matched" }
```

| `result` | 뜻 | 프론트엔드 처리 |
|---|---|---|
| `matched` | 세 값이 국세청 정보와 맞음 | 다음 단계로 진행. 30분 안에 같은 값으로 신청하면 국세청을 다시 부르지 않는다(3.11.2의 5단계) |
| `not_matched` | 맞지 않음. 국세청은 어느 값이 틀렸는지 알려 주지 않는다 | 세 값을 사업자등록증과 같게 입력했는지 확인하라고 안내하고, 입력값을 유지한 채 수정하게 한다 |
| `unavailable` | 검증 서비스 오류, 시간 초과, 호출 한도 초과, 또는 서버에 검증 설정이 없음 | 확인하지 못했다고 안내하고 그대로 진행하게 한다. 신청(3.11.2)이 다시 확인하며, 그때도 확인하지 못하면 operator가 나중에 확인한다 |

- 사업자 상태(`businessStatus`)는 돌려주지 않는다. 신청자는 신청한 뒤 3.11.1의 `businessStatus`로 본다.
- **횟수**: 국세청을 부른 요청은 신청(3.11.2)과 같은 진위확인 한도에 센다(3.11.14). 결과와 관계없이 세며, 서버에 검증 설정이 없어 부르지 않은 요청은 세지 않는다. 한도를 넘으면 국세청을 부르지 않고 `429 RATE_LIMITED`다.
- **신청에서 다시 쓰는 결과**: `matched`이면 백엔드가 사용자(token의 `sub`)와 세 값, 사업자 상태, 확인 시각을 30분 동안 서버 메모리에 기억한다. 같은 사용자가 그동안 같은 세 값으로 신청하면 이 결과를 쓴다. `not_matched`와 `unavailable`은 기억하지 않으므로, 그 값으로 신청하면 국세청을 다시 부른다. 횟수 기록(3.11.14)처럼 서버가 재시작되면 잊으며, 그때는 신청이 국세청을 다시 부르고 횟수도 하나 더 센다.

| HTTP | code | 발생 조건 | 프론트엔드 처리 |
|---|---|---|---|
| `401` | `UNAUTHENTICATED` | 3.1.5 | 3.1.5 |
| `422` | `VALIDATION_FAILED` | 3.11.2의 세 필드 규칙 위반, 다른 필드(`EXTRA_FORBIDDEN`) | `fieldErrors` 표시 |
| `429` | `RATE_LIMITED` | 오늘 진위확인을 5회 했음(3.11.14). `details.retryAfter`에 다음 초기화 시각 | 내일 다시 시도하라고 안내. 오늘 신청해도 같은 한도에 걸린다 |

#### 3.11.17 새 업장 신청 대표 사진

```http
PUT /api/owner-applications/{applicationId}/cover-photo
Authorization: Bearer <access-token>
Content-Type: multipart/form-data
```

```http
DELETE /api/owner-applications/{applicationId}/cover-photo
Authorization: Bearer <access-token>
```

신청자 본인만 호출할 수 있다. `new_bar` 신청(3.11.2)이 `201`로 만들어진 뒤 매장 대표 사진 한 장을 저장하거나(`PUT`) 지운다(`DELETE`). 선택 사항이다. operator는 신청 상세의 `coverPhoto`(3.11.1)로 사진을 보고 실제 매장인지 확인하며, 승인하면 새 업장의 첫 매장 사진이 된다(3.11.7).

| `PUT` 필드 | 타입 | 필수 | 설명 |
|---|---|---|---|
| `image` | 이미지 파일 | 예 | 사진 한 장 |

- **업로드 검사와 처리**는 매장 사진 추가(3.16.2)와 같다: JPEG와 PNG, 2MB 이하, 긴 변 2048px 이하, 메타데이터를 뺀 JPEG로 다시 인코딩, 긴 변 480px 썸네일. 안드로이드 앱이 올리기 전에 줄이고 압축하는 규칙도 같다.
- **한 장**: 이미 사진이 있으면 새 사진으로 바꾸고 이전 파일은 지운다. 같은 요청을 다시 보내도 결과가 같으므로 `Idempotency-Key`는 받지 않는다.
- **삭제**: `DELETE`는 사진을 지운다. 사진이 없어도 `200`이다(같은 요청을 다시 보내도 결과가 같다).
- **상태**: `pending`일 때만 바꿀 수 있다. 신청 행을 잠그므로 승인, 거절, 취소와 동시에 들어오면 둘 중 하나만 성공한다(3.11.15와 같다).
- **저장소**: 메뉴판 사진과 같은 비공개 저장소에 둔다. 승인 전에는 공개 URL(3.16.5)이 없고, 신청자 본인과 operator만 `coverPhoto`의 서명 URL로 본다.
- **정리**: 신청이 거절되거나 취소되면 파일을 지운다(3.11.5, 3.11.8). 승인되면 파일을 그대로 새 업장의 매장 사진으로 쓴다(3.11.7).

백엔드는 다음 순서로 확인하고, 처음 걸린 단계의 오류를 반환한다. `DELETE`는 1단계와 5단계가 없다.

1. 요청 형식 (`422 VALIDATION_FAILED`, `image`가 없으면 `MISSING`, 두 개 이상이면 `TOO_LONG`)
2. 신청과 신청자 (`404 OWNER_APPLICATION_NOT_FOUND`)
3. 신청 종류 (`409 INVALID_APPLICATION_TYPE`)
4. 신청 상태 (`409 INVALID_APPLICATION_STATE`)
5. 사진 (3.16.2와 같다): 크기(`413 UPLOAD_TOO_LARGE`), 형식(`415 UNSUPPORTED_IMAGE_TYPE`), 가로세로(`422 VALIDATION_FAILED`, `fieldErrors[].code = IMAGE_DIMENSIONS_TOO_LARGE`)

`200 OK`, 본문은 `OwnerApplication`(3.11.1)이며 `coverPhoto`에 저장한 사진이 들어 있다(`DELETE`는 `null`).

| HTTP | code | 발생 조건 | 프론트엔드 처리 |
|---|---|---|---|
| `401` | `UNAUTHENTICATED` | 3.1.5 | 3.1.5 |
| `404` | `OWNER_APPLICATION_NOT_FOUND` | 신청이 없거나, 본인의 신청이 아니거나, `applicationId`가 UUID 형식이 아님 | 신청 목록 재조회 |
| `409` | `INVALID_APPLICATION_TYPE` | `existing_bar` 신청. `details.applicationType` | 기존 업장의 사진은 승인 뒤 3.16으로 올린다 |
| `409` | `INVALID_APPLICATION_STATE` | `pending`이 아님. `details.status`에 현재 상태 | 신청 상세 재조회. 승인되었으면 사진은 3.16으로 바꾼다 |
| `413` | `UPLOAD_TOO_LARGE` | 사진이 2MB를 넘음. `details.maxImageBytes = 2097152` | 품질을 낮춰 다시 압축해 올림 |
| `415` | `UNSUPPORTED_IMAGE_TYPE` | 3.16.6과 같다 | JPEG로 바꿔 다시 올림 |
| `422` | `VALIDATION_FAILED` | `image` 없음이나 두 개 이상, 긴 변 2048px 초과(`IMAGE_DIMENSIONS_TOO_LARGE`) | `fieldErrors` 표시. `IMAGE_DIMENSIONS_TOO_LARGE`이면 줄여서 다시 올림 |

신청 순서는 3.11.2로 신청을 만든 뒤 이 API와 3.11.15를 호출하는 것이다. 신청은 만들어졌지만 사진 업로드가 실패하면, 신청을 다시 만들지 않고 같은 `applicationId`로 이 API만 다시 호출한다.

#### 3.11.18 실제 응답 예시와 호출자별 결과

2.4의 방법으로 받은 응답이다. 김사장이 `new_bar` 신청으로 관악 위스키 바를 등록하는 흐름을 따른다.

**신청 (3.11.2)**. 신청 전 확인(3.11.16)에서 `{"result": "matched"}`를 받은 뒤 같은 세 값으로 신청했으므로 국세청을 다시 부르지 않았다.

```json
{
  "applicationType": "new_bar",
  "proposedBar": {
    "name": "관악 위스키 바",
    "address": "서울특별시 관악구 관악로 1 2층",
    "phone": "02-000-0000"
  },
  "businessRegistrationNumber": "123-45-67891",
  "representativeName": "김사장",
  "openingDate": "2020-03-02",
  "contactPhone": "010-1234-5678",
  "applicantNote": "대표 본인입니다"
}
```

```http
HTTP/1.1 201 Created
Location: /api/owner-applications/cccccccc-cccc-4ccc-8ccc-ccccccccccc1
```

**사진 올리기 (3.11.15, 3.11.17)**. 두 API 모두 multipart이며, 메뉴판 사진은 같은 필드 이름(`images`)을 보낼 순서대로 반복한다.

```sh
curl -X PUT https://bottlemap.o-r.kr/api/owner-applications/cccccccc-cccc-4ccc-8ccc-ccccccccccc1/menu-photos \
  -H "Authorization: Bearer <access-token>" \
  -F "images=@menu-1.jpg;type=image/jpeg" \
  -F "images=@menu-2.jpg;type=image/jpeg"

curl -X PUT https://bottlemap.o-r.kr/api/owner-applications/cccccccc-cccc-4ccc-8ccc-ccccccccccc1/cover-photo \
  -H "Authorization: Bearer <access-token>" \
  -F "image=@storefront.jpg;type=image/jpeg"
```

**사진을 올린 뒤 신청자 본인이 본 신청 (3.11.4)**. 신청자 본인에게는 `businessVerification`과 `warnings`가 `null`이고 `businessStatus`만 보인다.

```json
{
  "applicationId": "cccccccc-cccc-4ccc-8ccc-ccccccccccc1",
  "applicationType": "new_bar",
  "status": "pending",
  "applicant": {
    "userId": "11111111-1111-4111-8111-111111111111",
    "email": "owner@example.com",
    "displayName": "김사장"
  },
  "bar": null,
  "proposedBar": {
    "name": "관악 위스키 바",
    "address": "서울특별시 관악구 관악로 1 2층",
    "phone": "02-000-0000"
  },
  "businessRegistrationNumber": "1234567891",
  "representativeName": "김사장",
  "openingDate": "2020-03-02",
  "businessStatus": "active",
  "businessVerification": null,
  "warnings": null,
  "contactPhone": "010-1234-5678",
  "applicantNote": "대표 본인입니다",
  "menuPhotos": [
    {
      "imageOrder": 1,
      "imageUrl": "https://storage.example.com/signed/owner-applications/cccccccc-cccc-4ccc-8ccc-ccccccccccc1/ffffffff-ffff-4fff-8fff-fffffffffff2/page-1.jpg",
      "imageUrlExpiresAt": null
    },
    {
      "imageOrder": 2,
      "imageUrl": "https://storage.example.com/signed/owner-applications/cccccccc-cccc-4ccc-8ccc-ccccccccccc1/ffffffff-ffff-4fff-8fff-fffffffffff2/page-2.jpg",
      "imageUrlExpiresAt": null
    }
  ],
  "coverPhoto": {
    "imageUrl": "https://storage.example.com/signed/owner-applications/cccccccc-cccc-4ccc-8ccc-ccccccccccc1/cover/ffffffff-ffff-4fff-8fff-fffffffffff1.jpg",
    "thumbnailUrl": "https://storage.example.com/signed/owner-applications/cccccccc-cccc-4ccc-8ccc-ccccccccccc1/cover/ffffffff-ffff-4fff-8fff-fffffffffff1-thumb.jpg",
    "imageUrlExpiresAt": null
  },
  "rejectionReason": null,
  "reviewedAt": null,
  "createdAt": "2026-11-09T12:44:47.655775Z",
  "updatedAt": "2026-11-09T12:44:47.770402Z"
}
```

**operator의 목록 (3.11.6)**. `GET /api/owner-applications?limit=1`. 각 신청은 위와 같고 `businessVerification`과 `warnings`만 채워져 있다. 다음 페이지가 있으므로 `nextCursor`가 있다.

```json
{
  "items": [
    {
      "applicationId": "cccccccc-cccc-4ccc-8ccc-ccccccccccc1",
      "status": "pending",
      "businessVerification": {
        "result": "matched",
        "checkedAt": "2026-11-09T12:44:47.636619Z"
      },
      "warnings": [],
      "...": "나머지는 위 신청과 같다"
    }
  ],
  "nextCursor": "WyJwZW5kaW5nIixudWxsLG51bGwsIjIwMjYtMTEtMDlUMjE6NDQ6NDcuNjU1Nzc1KzA5OjAwIiwiY2NjY2NjY2MtY2NjYy00Y2NjLThjY2MtY2NjY2NjY2NjY2MxIl0"
}
```

**승인 (3.11.7)**. 3.11.7의 요청 예시와 같은 형식으로 좌표를 보냈다. 응답에서 바뀐 필드는 다음과 같다. 대표 사진은 업장의 첫 매장 사진으로 옮겨져 `coverPhoto`가 `null`이 되고, 메뉴판 사진은 메뉴 등록 작업의 사진으로 남는다.

```json
{
  "applicationId": "cccccccc-cccc-4ccc-8ccc-ccccccccccc1",
  "status": "approved",
  "bar": {
    "barId": "22222222-2222-4222-8222-222222222222",
    "name": "관악 위스키 바",
    "address": "서울특별시 관악구 관악로 1 2층"
  },
  "coverPhoto": null,
  "reviewedAt": "2026-11-09T12:44:47.928467Z",
  "updatedAt": "2026-11-09T12:44:47.926513Z",
  "...": "나머지는 승인 전과 같다"
}
```

**거절 (3.11.8)**. 다른 사용자의 `new_bar` 신청을 `{"reason": "사업장 주소에서 매장을 확인할 수 없습니다."}`로 거절했다. 취소(3.11.5)도 `status = canceled`이고 `rejectionReason`이 `null`인 것 말고는 같은 모양이다.

```json
{
  "applicationId": "cccccccc-cccc-4ccc-8ccc-ccccccccccc5",
  "status": "rejected",
  "bar": null,
  "menuPhotos": [],
  "coverPhoto": null,
  "rejectionReason": "사업장 주소에서 매장을 확인할 수 없습니다.",
  "reviewedAt": "2026-11-09T12:44:48.259912Z",
  "...": "나머지는 거절 전과 같다"
}
```

**대표 오류**

같은 신청을 다시 냈을 때 (`409`, 3.11.2). `details.applicationId`의 신청으로 이동한다.

```json
{"error": {"code": "OWNER_APPLICATION_EXISTS", "message": "이미 처리 중인 업주 신청이 있습니다.", "details": {"applicationId": "cccccccc-cccc-4ccc-8ccc-ccccccccccc1"}, "fieldErrors": []}}
```

이미 업주가 있는 업장에 `existing_bar`로 신청했을 때 (`409`, 3.11.2)

```json
{"error": {"code": "BAR_OWNER_EXISTS", "message": "이미 업주가 등록된 업장입니다.", "details": null, "fieldErrors": []}}
```

세 값이 국세청 정보와 맞지 않을 때 (`422`, 3.11.2). 신청은 만들어지지 않는다.

```json
{"error": {"code": "BUSINESS_VERIFICATION_FAILED", "message": "사업자등록번호, 대표자명, 개업일자가 사업자등록증과 같은지 확인해 주세요.", "details": null, "fieldErrors": []}}
```

사업자등록번호의 검증번호가 틀렸을 때와 `applicationType`이 없을 때 (`422`, 3.11.2). 두 경우 모두 `VALIDATION_FAILED`이며 `fieldErrors`만 다르다. `applicationType`이 없으면 `path`가 빈 문자열이다.

```json
{
  "error": {
    "code": "VALIDATION_FAILED",
    "message": "입력값을 확인해 주세요.",
    "details": null,
    "fieldErrors": [
      {
        "path": "businessRegistrationNumber",
        "code": "INVALID_BUSINESS_NUMBER",
        "message": "사업자등록번호를 확인해 주세요."
      }
    ]
  }
}
```

```json
{
  "fieldErrors": [
    {
      "path": "",
      "code": "UNION_TAG_NOT_FOUND",
      "message": "Unable to extract tag using discriminator 'applicationType'"
    }
  ]
}
```

이미 승인한 신청을 다시 승인했을 때 (`409`, 3.11.7). 거절, 취소, 사진 변경, 다시 검증도 `pending`이 아니면 같다.

```json
{"error": {"code": "INVALID_APPLICATION_STATE", "message": "이미 처리된 업주 신청입니다.", "details": {"status": "approved"}, "fieldErrors": []}}
```

`existing_bar` 신청에 대표 사진을 올렸을 때 (`409`, 3.11.17)

```json
{"error": {"code": "INVALID_APPLICATION_TYPE", "message": "새 업장 신청에만 대표 사진을 올릴 수 있습니다.", "details": {"applicationType": "existing_bar"}, "fieldErrors": []}}
```

서버에 OCR 설정이 없을 때 (`503`, 3.11.12)

```json
{"error": {"code": "OCR_UNAVAILABLE", "message": "지금은 사업자등록증 사진을 읽을 수 없습니다. 값을 직접 입력해 주세요.", "details": null, "fieldErrors": []}}
```

**호출자별 결과**. 대상은 customer의 `pending` 신청이다(`existing_bar` 신청, 대표 사진 행은 `new_bar` 신청). 업주 신청은 업장이 아니라 신청자 기준이므로 2.4의 열 대신 아래 열을 쓴다. "다른 로그인 사용자"는 두 업주(대상 업장의 업주와 다른 업장의 업주)로 호출했으며 결과가 같았다.

| API | 비로그인 | 신청자 본인 (customer) | 다른 로그인 사용자 | operator |
|---|---|---|---|---|
| `POST /api/owner-applications` | `401` | `201` | `201` | `201` |
| `GET /api/me/owner-applications` | `401` | `200` | `200` (본인 신청만) | `200` (본인 신청만) |
| `GET /api/owner-applications/{applicationId}` | `401` | `200` | `404` | `200` |
| `POST .../cancel` | `401` | `200` | `404` | `404` |
| `PUT .../menu-photos` | `401` | `200` | `404` | `404` |
| `PUT .../cover-photo`, `DELETE .../cover-photo` | `401` | `200` | `404` | `404` |
| `GET /api/owner-applications` | `401` | `403` | `403` | `200` |
| `POST .../approve`, `POST .../verify-business` | `401` | `403` | `403` | `200` |
| `POST .../reject` (이미 거절한 신청) | `401` | `403` | `403` | `409` |
| `DELETE /api/bars/{barId}/owner` (업주가 없는 업장) | `401` | `403` | `403` | `404` |
| `GET /api/me/bars` | `401` | `200` (`items = []`) | `200` (본인 업장만) | `200` (`items = []`) |

`POST /api/owner-applications`의 `201`은 각자 자기 신청을 만든 결과다. operator가 아닌 호출자는 대상이 없거나 끝난 신청에도 `403`을 받는다(2.2의 검사 순서).

### 3.12 내 주변 업장 조회

고객 위치에서 반경 안에 있는 활성 업장을 모두 반환한다. 고객 위치 기준의 주변 업장 목록에 사용한다. 지도 화면에 보이는 영역은 3.13으로 불러온다. 상품으로 업장을 찾는 고객 검색(3.10), 업장 이름 검색(3.11.11), 지도 영역 조회(3.13)와는 다른 API다.

로그인 없이 호출할 수 있는 공개 API이며, `Authorization` 헤더를 보내도 읽지 않는다(3.1.5). 결과는 호출자와 관계없이 같다.

```http
GET /api/search/nearby-bars?lat=37.478&lng=126.951&radiusMeters=500
```

| Query | 필수 | 기본값 | 설명 |
|---|---|---|---|
| `lat` | 예 | 없음 | 고객 위치 위도. -90~90 (2.1) |
| `lng` | 예 | 없음 | 고객 위치 경도. -180~180 (2.1) |
| `radiusMeters` | 아니오 | `500` | 반경(미터). 정수 1~3000 |

#### 3.12.1 반경 안의 업장

- 활성 업장만 포함한다. 비활성 업장은 operator가 호출해도 결과에 없다.
- 게시된 메뉴가 없는 업장과 메뉴판의 항목이 모두 내려간 업장도 포함한다.
- 거리는 서버가 고객 위치와 업장 좌표 사이의 직선 거리(하버사인 공식)로 계산하고, 미터 단위 정수로 반올림한다. 3.10의 `distanceMeters`와 같은 계산이다.
- 반올림한 `distanceMeters`가 `radiusMeters` 이하인 업장을 포함한다. 거리가 `radiusMeters`와 같은 업장도 포함한다. 따라서 응답의 `distanceMeters`는 `radiusMeters`보다 크지 않다.
- 페이지 없이 조건에 맞는 업장을 모두 반환하며, 결과를 자르지 않는다.
- `distanceMeters` 오름차순으로 정렬하고, 거리가 같으면 `barId` 순으로 정렬한다.
- 서버가 반경으로 거르고 정렬하므로 앱은 결과를 다시 거르거나 정렬하지 않는다. 앱이 자체 계산으로 다시 거르면 지구 반지름 값이나 반올림 차이로 경계의 업장이 빠질 수 있다.

#### 3.12.2 응답

`200 OK`

```json
{
  "items": [
    {
      "barId": "22222222-2222-4222-8222-222222222222",
      "name": "관악 위스키 바",
      "address": "서울특별시 관악구 관악로 1 2층",
      "latitude": 37.478321,
      "longitude": 126.951234,
      "distanceMeters": 41,
      "coverThumbnailUrl": "https://bottlemap.o-r.kr/api/bar-photos/12121212-1212-4212-8212-121212121211/thumbnail",
      "menuUpdatedAt": "2026-10-02T11:00:00Z"
    },
    {
      "barId": "33333333-3333-4333-8333-333333333333",
      "name": "샤로수길 몰트",
      "address": "서울특별시 관악구 관악로14길 10",
      "latitude": 37.479874,
      "longitude": 126.954512,
      "distanceMeters": 373,
      "coverThumbnailUrl": null,
      "menuUpdatedAt": null
    }
  ]
}
```

| 필드 | 타입 | null 가능 | 설명 |
|---|---|---|---|
| `items` | 배열 | 아니오 | 반경 안의 활성 업장 전체. 없으면 `[]` |
| `items[].barId` | UUID 문자열 | 아니오 | |
| `items[].name`, `items[].address` | 문자열 | 아니오 | |
| `items[].latitude`, `items[].longitude` | 숫자 | 아니오 | 업장 좌표(WGS84). 3.9.4 |
| `items[].distanceMeters` | 정수 | 아니오 | 고객 위치와 업장 사이의 직선 거리(미터). `radiusMeters` 이하 |
| `items[].coverThumbnailUrl` | 문자열 | 예 | 업장 대표 사진(`photos`의 첫 사진, 3.16.1)의 썸네일 URL(`thumbnailUrl`). 3.16.5와 같은 고정 URL이다. 사진이 없으면 `null`이며 프론트엔드는 기본 이미지를 보여 준다 |
| `items[].menuUpdatedAt` | RFC 3339 문자열 | 예 | 업장 현재 메뉴판의 `menu_boards.published_at`(3.9의 `publishedAt`과 같은 값). 게시된 메뉴가 한 번도 없으면 `null`이다. 메뉴판은 있지만 항목이 0개이면 값이 있다(3.9.1과 같은 규칙) |

근처에 업장이 없으면 `200 OK`와 `items = []`를 반환한다. 프론트엔드는 반경 안에 업장이 없다는 빈 상태를 표시한다.

#### 3.12.3 위치 정보

- 서버는 `lat`, `lng`를 거리 계산에만 사용하며 DB에 저장하지 않는다.
- 서버 접근 로그에서도 `lat`, `lng`를 지우고 나머지 query만 남긴다(`GET /api/search/nearby-bars?radiusMeters=500`). 3.10의 위치와 같다.

#### 3.12.4 오류와 프론트엔드 처리

입력이 잘못되면 `422 VALIDATION_FAILED`를 반환한다(9.1, 9.3). 한 응답의 `fieldErrors`에 여러 개 올 수 있다.

| 상황 | `fieldErrors[].path` | `fieldErrors[].code` | 프론트엔드 처리 |
|---|---|---|---|
| `lat`이나 `lng`가 없음 | 빠진 파라미터 | `MISSING` | 앱 버그. 일반 오류와 재시도 |
| `lat`, `lng`, `radiusMeters`가 범위를 벗어남(`nan`, `inf` 포함) | 해당 파라미터 | `GREATER_THAN_EQUAL`, `LESS_THAN_EQUAL` | 앱 버그. 일반 오류와 재시도 |
| `lat`, `lng`, `radiusMeters`가 숫자가 아님 | 해당 파라미터 | `FLOAT_PARSING`(`lat`, `lng`), `INT_PARSING`(`radiusMeters`, 소수 포함) | 앱 버그. 일반 오류와 재시도 |

- `lat`, `lng`는 필수이므로 위치 권한이 없거나 위치를 얻지 못하면 이 API를 호출하지 않는다.
- 네트워크 오류와 `5xx`(`500 INTERNAL_ERROR`, 프록시의 `502`·`504` 포함)는 오류 상태와 재시도 버튼을 보여 준다(9.6).
- 이 API는 `401`, `403`, `404`를 반환하지 않으며, 요청 수 제한(`429`)도 없다.

### 3.13 지도 영역 안의 업장 조회

지도 화면에 보이는 영역 안의 활성 업장을 모두 반환한다. 지도 마커와 지도 화면의 목록에 사용한다. 고객 위치를 중심으로 한 반경 조회(3.12)는 반경이 최대 3 km라 그보다 넓은 화면을 채울 수 없으므로, 지도 화면은 이 API를 쓴다.

로그인 없이 호출할 수 있는 공개 API이며, `Authorization` 헤더를 보내도 읽지 않는다(3.1.5). 결과는 호출자와 관계없이 같다.

```http
GET /api/search/map-bars?south=37.470&west=126.940&north=37.490&east=126.970
```

| Query | 필수 | 기본값 | 설명 |
|---|---|---|---|
| `south` | 예 | 없음 | 영역 남쪽 경계 위도. -90~90 |
| `west` | 예 | 없음 | 영역 서쪽 경계 경도. -180~180 |
| `north` | 예 | 없음 | 영역 북쪽 경계 위도. -90~90. `south` 이상 |
| `east` | 예 | 없음 | 영역 동쪽 경계 경도. -180~180. `west` 이상 |

좌표는 WGS84 십진 도다(2.1). 지도 SDK가 주는 화면 영역의 남서·북동 모서리를 그대로 보낸다.

#### 3.13.1 영역 안의 업장

- `south ≤ latitude ≤ north`이고 `west ≤ longitude ≤ east`인 활성 업장을 포함한다. 경계 위의 업장도 포함한다.
- 비활성 업장은 operator가 호출해도 결과에 없다.
- 게시된 메뉴가 없는 업장과 메뉴판의 항목이 모두 내려간 업장도 포함한다(3.12와 같다).
- 페이지 없이 조건에 맞는 업장을 모두 반환하며, 결과를 자르지 않는다. 결과 크기는 영역 상한(3.13.2)으로 제한한다.
- `barId` 순으로 정렬한다. 지도 마커용이라 순서에 의미는 없고, 같은 요청에 항상 같은 순서로 답하기 위한 것이다. 목록을 다른 순서로 보여 줄 때는 프론트엔드가 정렬한다.
- 날짜 변경선(경도 ±180°)을 넘는 영역은 받지 않는다(`west > east`는 `422`). 서비스 지역이 국내라 지도 화면이 날짜 변경선에 걸리지 않는다.

#### 3.13.2 영역 상한

영역의 남북 폭(`north - south`)과 동서 폭(`east - west`)은 각각 `0.2`도 이하여야 한다. 넘으면 `422`다.

| 기준 | 남북 0.2도 | 동서 0.2도 |
|---|---|---|
| 서울(위도 37.5°) | 약 22 km | 약 18 km |
| 제주(위도 33.5°) | 약 22 km | 약 19 km |

- 결과를 자르지 않으므로 응답 크기를 영역으로 제한해야 한다. 0.2도 영역은 약 400 km²로 서울 면적(약 605 km²)의 3분의 2 정도다. 업장이 늘어 서울 전역에 2,000곳이 있어도 한 응답은 1,300곳 정도이며, 항목 하나가 약 250바이트이므로 300 KB 남짓이다.
- 3.12의 최대 반경 3 km(지름 6 km)보다 충분히 넓어, 구 단위부터 여러 구에 걸친 화면까지 한 번에 채울 수 있다. 이보다 넓은 화면에서는 마커가 겹쳐 하나씩 구분할 수 없으므로, 업장 하나하나가 아니라 묶음(클러스터)으로 보여 줘야 한다. 그런 화면은 이 API의 범위가 아니다.
- 미터가 아니라 도 단위로 정해서, 앱이 지도 SDK의 화면 영역만으로 요청 전에 검사할 수 있다. 같은 도라도 동서 거리는 위도가 높을수록 줄지만, 국내에서는 차이가 작다.
- 프론트엔드는 화면 영역이 상한을 넘으면 이 API를 호출하지 않고 지도를 확대하라고 안내한다. 이미 표시한 마커는 지우지 않아도 된다.
- 업장 수가 늘어 상한을 바꿀 때 늘리는 것은 기존 앱을 깨지 않지만(앱이 더 좁은 영역만 요청할 뿐이다), 줄이는 것은 계약 변경이다.

#### 3.13.3 응답

`200 OK`. 항목은 3.12의 항목에서 `distanceMeters`만 뺀 형식이다.

```json
{
  "items": [
    {
      "barId": "22222222-2222-4222-8222-222222222222",
      "name": "관악 위스키 바",
      "address": "서울특별시 관악구 관악로 1 2층",
      "latitude": 37.478321,
      "longitude": 126.951234,
      "coverThumbnailUrl": "https://bottlemap.o-r.kr/api/bar-photos/12121212-1212-4212-8212-121212121211/thumbnail",
      "menuUpdatedAt": "2026-10-02T11:00:00Z"
    },
    {
      "barId": "33333333-3333-4333-8333-333333333333",
      "name": "샤로수길 몰트",
      "address": "서울특별시 관악구 관악로14길 10",
      "latitude": 37.479874,
      "longitude": 126.954512,
      "coverThumbnailUrl": null,
      "menuUpdatedAt": null
    }
  ]
}
```

| 필드 | 타입 | null 가능 | 설명 |
|---|---|---|---|
| `items` | 배열 | 아니오 | 영역 안의 활성 업장 전체. 없으면 `[]` |
| `items[].barId` | UUID 문자열 | 아니오 | |
| `items[].name`, `items[].address` | 문자열 | 아니오 | |
| `items[].latitude`, `items[].longitude` | 숫자 | 아니오 | 업장 좌표(WGS84). 3.9.4 |
| `items[].coverThumbnailUrl` | 문자열 | 예 | 3.12의 `coverThumbnailUrl`과 같다. 업장 대표 사진(`photos`의 첫 사진, 3.16.1)의 썸네일 URL(`thumbnailUrl`). 3.16.5와 같은 고정 URL이다. 사진이 없으면 `null`이며 프론트엔드는 기본 이미지를 보여 준다 |
| `items[].menuUpdatedAt` | RFC 3339 문자열 | 예 | 3.12의 `menuUpdatedAt`과 같다. 게시된 메뉴가 한 번도 없으면 `null`이고, 메뉴판은 있지만 항목이 0개이면 값이 있다 |

영역 안에 업장이 없으면 `200 OK`와 `items = []`를 반환한다. 프론트엔드는 이 영역에 업장이 없다는 빈 상태를 표시한다.

#### 3.13.4 위치 정보

- 지도 영역은 보통 사용자가 있는 곳이나 관심 있는 곳을 드러내므로 고객 위치(3.12.3)와 같게 다룬다.
- 서버는 `south`, `west`, `north`, `east`를 업장을 거르는 데만 사용하며 DB에 저장하지 않는다.
- 서버 접근 로그에서도 네 값을 지우고 경로만 남긴다(`GET /api/search/map-bars`).

#### 3.13.5 오류와 프론트엔드 처리

입력이 잘못되면 `422 VALIDATION_FAILED`를 반환한다(9.1, 9.3).

| 상황 | `fieldErrors[].path` | `fieldErrors[].code` | 프론트엔드 처리 |
|---|---|---|---|
| `south`, `west`, `north`, `east` 중 빠진 값이 있음 | 빠진 파라미터 | `MISSING` | 앱 버그. 일반 오류와 재시도 |
| 범위를 벗어남(`nan`, `inf` 포함) | 해당 파라미터 | `GREATER_THAN_EQUAL`, `LESS_THAN_EQUAL` | 앱 버그. 일반 오류와 재시도 |
| 숫자가 아님 | 해당 파라미터 | `FLOAT_PARSING` | 앱 버그. 일반 오류와 재시도 |
| `south > north` 또는 `west > east` | `north` 또는 `east` | `BOUNDS_INVERTED` | 앱 버그. 일반 오류와 재시도 |
| 남북 폭 또는 동서 폭이 `0.2`도 초과 | `north` 또는 `east` | `BOUNDS_TOO_LARGE` | 지도를 확대하라는 안내. 앱이 요청 전에 검사하므로 보통은 오지 않는다 |

- 빠진 값, 범위, 숫자 형식 오류는 한 응답의 `fieldErrors`에 여러 개 올 수 있다. 이 검사를 모두 통과한 뒤에 `BOUNDS_INVERTED`(남북 먼저), `BOUNDS_TOO_LARGE`(남북 먼저)를 이 순서로 검사하며, 이 단계에서는 처음 걸린 오류 하나만 반환한다.
- 네트워크 오류와 `5xx`(`500 INTERNAL_ERROR`, 프록시의 `502`·`504` 포함)는 오류 상태와 재시도 버튼을 보여 준다(9.6).
- 이 API는 `401`, `403`, `404`를 반환하지 않으며, 요청 수 제한(`429`)도 없다. 지도를 움직일 때마다 호출하므로 프론트엔드는 카메라 이동이 멈춘 뒤에 호출하고, 늦게 도착한 이전 영역의 응답은 버린다.

### 3.14 메뉴 직접 편집

메뉴판 사진 등록과 검수(이 문서의 4~8) 없이 현재 메뉴판의 항목 하나를 추가, 수정, 삭제하거나 메뉴판 전체를 비우는 API다. 검수 단계가 없으므로 요청이 성공하면 그 결과가 바로 게시되어 업장 메뉴(3.9)와 고객 검색(3.10)에 나온다.

| 메서드 | 경로 | 용도 |
|---|---|---|
| `POST` | `/api/bars/{barId}/menu/items` | 항목 추가 (3.14.3) |
| `PUT` | `/api/bars/{barId}/menu/items/{barMenuItemId}` | 항목 수정 (3.14.4) |
| `DELETE` | `/api/bars/{barId}/menu/items/{barMenuItemId}?menuVersion=<n>` | 항목 삭제 (3.14.5) |
| `POST` | `/api/bars/{barId}/menu/reset` | 메뉴판 초기화 (3.14.6) |
| `PUT` | `/api/bars/{barId}/menu/items/{barMenuItemId}/sold-out` | 품절 표시와 해제 (3.14.8) |
| `POST` | `/api/bars/{barId}/menu/confirm` | 판매 정보 확인 (3.14.9) |

#### 3.14.1 공통 규칙

- **권한**: operator와 해당 업장의 현재 업주가 호출할 수 있다(2.2). 비활성 업장은 메뉴를 바꾸지 않으며 `404 BAR_NOT_FOUND`다(4.4와 같다).
- **항목 식별자**: 항목은 `barMenuItemId`로 가리킨다. 상품에 연결된 항목은 업장과 상품의 조합마다 하나이며 메뉴판에서 빠져도 바뀌지 않는다. 상품에 연결되지 않은 항목(3.9)은 업장 안에서 메뉴판 이름으로 구분한다. 이름 키(메뉴판 이름을 백엔드의 공통 정규화 함수로 정규화한 값, 별칭과 같은 함수)가 같으면 같은 항목이다. 현재 메뉴판에서 빠진 미연결 항목은 다시 쓰지 않으며, 같은 이름을 다시 추가하면 새 `barMenuItemId`가 생긴다. `menuBoardEntryId`와 `menuEntryOptionId`는 메뉴판이 바뀔 때마다(검수 반영과 직접 편집 모두) 새로 만들어질 수 있으므로 편집 요청에 쓰지 않는다.
- **연결 바꾸기**: 메뉴판의 한 줄을 다른 상품에 연결하거나 연결을 풀 때(이름을 고친 뒤의 다시 매칭 3.14.4와 8.11, 운영자의 연결 3.18.3) 다음 규칙을 따른다. 상품에 연결된 항목은 상품을 바꾸지 않고, 메뉴판의 줄을 알맞은 항목으로 옮긴다. 업장과 상품의 조합마다 항목이 하나이기 때문이다.
  - 상품 없는 항목을 상품 Q에 연결: 이 업장에 Q의 항목이 없으면 그 항목에 Q를 채우고 이름 키를 지운다. `barMenuItemId`는 그대로다. 메뉴판에 없는 예전 Q 항목이 있으면 줄을 그 항목으로 옮긴다.
  - 상품 P에 연결된 항목을 Q로 바꾸기: 줄을 Q의 항목으로 옮긴다. 메뉴판에 없는 예전 Q 항목이 있으면 그 항목을, 없으면 새 항목을 쓴다. P의 항목은 메뉴판에서 빠진 채로 남아 나중에 다시 쓰인다.
  - 상품 P에 연결된 항목의 연결 풀기: 줄을 새 미연결 위스키 항목(`kind = whisky`, 이름 키는 줄의 이름)으로 옮긴다. P의 항목은 메뉴판에서 빠진 채로 남는다.
  - 줄을 옮겨도 이름(`displayName`), 메뉴판의 위치, 옵션과 할인, 품절 상태는 그대로 옮긴다. 줄의 열린 확인(3.18)도 옮긴 항목으로 옮긴다.
  - Q가 이미 현재 메뉴판의 다른 줄이면 두 줄을 하나로 합친다. 남는 줄은 원래 Q에 연결되어 있던 줄이고, 이름, 위치, 품절 상태는 그 줄의 것을 쓴다. 옵션은 남는 줄의 옵션 뒤에 옮겨 오는 줄의 옵션을 붙이며, 표기(`optionLabel`)와 용량(`pourMl`)이 같은 옵션은 하나만 남긴다. 가격이 다르면 남는 줄의 가격(이미 그 상품으로 손님에게 보이던 가격)과 할인을 쓴다. 이렇게 가격을 버린 경우, 직접 수정의 다시 매칭(3.14.4)이면 합친 항목을 운영자 확인(3.18, 사유 `price_conflict`)에 올리고, 운영자의 연결(3.18.3)이면 운영자가 처리하는 중이므로 올리지 않는다. 합친 옵션은 3개를 넘을 수 있다(3.14.2의 개수 제한은 직접 추가와 수정의 요청에만 적용된다).
  - 줄이 다른 항목으로 옮겨 가면 그 줄의 `barMenuItemId`가 바뀐다. 프론트엔드는 응답(3.9 형식)으로 화면을 바꾼다.
- **미완료 작업이 있을 때**: 업장에 미완료 메뉴 등록 작업(`uploaded`, `processing`, `ready_for_review`)이 있으면 추가, 수정, 삭제, 초기화는 모두 `409 ACTIVE_IMPORT_EXISTS`(`details.menuImportId`, `details.status`)다. 따라서 이 상황에서는 메뉴 편집이 불가능하고, 작업이 `applied`, `failed`, `canceled`가 되면 다시 편집할 수 있다. 검수 중에 메뉴판이 바뀌면 검수자가 오래된 메뉴판을 보고 결정하게 되기 때문이다.
- **메뉴판 버전**: 모든 편집 요청은 3.9에서 받은 `menuVersion`을 보낸다. 메뉴판이 없으면 `null`이다. 서버의 현재 값과 다르면 아무것도 바꾸지 않고 `409 MENU_OUTDATED`(`details.submittedMenuVersion`, `details.currentMenuVersion`)다. 성공한 편집은 `menuVersion`을 1 올리고, 메뉴판이 없을 때의 첫 추가는 메뉴판을 만들고 `menuVersion = 1`이 된다. 검수 반영(8)도 `menuVersion`을 올린다.
- **게시 시각**: 성공하면 `publishedAt`을 업장 행을 잠근 뒤의 현재 시각으로 바꾼다. 트랜잭션이나 요청이 시작한 시각이 아니다(PostgreSQL `now()`가 아니라 `clock_timestamp()`). 잠금을 기다리는 동안 먼저 끝난 판매 정보 확인(3.14.9)보다 이른 시각이 찍히면, 확인하지 않은 새 메뉴가 확인된 것처럼 보이기 때문이다. 검수 반영(8.7)과 판매 정보 확인의 `confirmedAt`도 같은 방식으로 찍는다. `menuBoardId`는 그대로다.
- **응답**: 성공 응답의 본문은 3.9와 같은 형식(업장 정보와 메뉴 전체)이다. 추가는 `201 Created`, 나머지는 `200 OK`다. 프론트엔드는 이 응답으로 화면을 바꾸고 따로 다시 조회하지 않아도 된다.
- **원자성**: 요청 하나는 하나의 트랜잭션이다. 신규 상품 생성(3.14.3)을 포함해 어느 단계에서든 실패하면 아무것도 바뀌지 않는다.
- **동시 요청은 업장 행 잠금으로 차례로 처리한다**: 메뉴판이나 메뉴 항목에 영향을 주는 요청은 모두, 무엇을 확인하기 전에 먼저 같은 업장 행(`bars`)을 `FOR UPDATE`로 잠그고 트랜잭션이 끝날 때까지 잡는다. 업장이 활성인지(비활성이면 `404 BAR_NOT_FOUND`)와 업주 권한처럼 업장 상태에 따라 달라지는 확인은 잠금을 잡은 뒤에 한다(잠그기 전에 이미 확인했다면 잠근 뒤 다시 확인한다). 그래야 확인과 잠금 사이에 업장이 비활성이 되어도 메뉴가 바뀌지 않는다. 대상은 다음과 같다.
  - 메뉴 등록 작업 생성: 사진 업로드(4.1)와 신청 승인의 첫 등록 작업(3.11.7)
  - 검수 반영(8)
  - 직접 편집: 추가, 수정, 삭제, 초기화(3.14.3~3.14.6)
  - 품절 표시(3.14.8)와 판매 정보 확인(3.14.9)

  그래서 같은 업장에 이런 요청이 동시에 와도 하나가 끝난 뒤에 다음 것이 처리되고, 각 요청은 앞 요청이 커밋한 결과를 보고 확인한다. 예를 들어 편집이 먼저면 등록 작업은 바뀐 메뉴판을 기준으로 만들어지고, 등록 작업이 먼저면 편집은 `409 ACTIVE_IMPORT_EXISTS`다. 검수가 항목을 내린 뒤에 온 품절 표시는 `404 MENU_ITEM_NOT_FOUND`이고, 검수 반영으로 버전이 오른 뒤에 온 판매 정보 확인은 `409 MENU_OUTDATED`다. 잠금은 업장마다 따로이므로 다른 업장의 요청은 기다리지 않는다.
- **재시도**: `Idempotency-Key`는 쓰지 않는다. 응답을 받지 못해 같은 요청을 다시 보내면, 앞 요청이 성공했다면 `menuVersion`이 이미 올라 `409 MENU_OUTDATED`를 받는다. 프론트엔드는 3.9를 다시 조회해 변경이 반영되었는지 확인한다.
- **변경 기록**: 누가 언제 메뉴를 바꿨는지는 남기지 않는다. 메뉴 변경 이력은 운영 대시보드의 추가 기능으로 나중에 구현할 예정이다. 직접 추가로 만든 상품과 브랜드에는 만든 사용자를 기록한다(3.14.3).
- **다른 항목은 그대로**: 추가, 수정, 삭제는 요청한 항목만 바꾼다. 다른 항목의 옵션, 할인(3.14.2), 품절(3.14.8)은 그대로 남는다. 서버가 메뉴판을 다시 쓰는 방식으로 구현하더라도 다른 항목의 할인은 같은 옵션에 옮겨야 한다. 초기화(3.14.6)는 모든 항목을 빼므로 할인과 품절도 함께 사라진다.
- **품절과 판매 정보 확인**: 3.14.8과 3.14.9는 메뉴 내용을 바꾸지 않으므로 미완료 작업 규칙과 `menuVersion` 증가, 게시 시각 변경을 적용하지 않는다. 자세한 차이는 각 절에 적었다.
- **검사 순서**: 인증(`401`, 3.1.5) → 요청 형식(`422`) → 업장(`404 BAR_NOT_FOUND`) → 권한(`403`) → 업장 행 잠금 → 업장 상태(비활성이면 `404 BAR_NOT_FOUND`) → 미완료 작업(`409 ACTIVE_IMPORT_EXISTS`) → 메뉴판 버전(`409 MENU_OUTDATED`) → 각 API의 항목 확인과 업무 규칙. 형식 오류는 한 응답에 여러 개 올 수 있다. 요청 본문만으로 판단하는 규칙(`EXACTLY_ONE_REQUIRED`, `DUPLICATE_OPTION_VALUES`, `DISCOUNT_NOT_LOWER`, `END_BEFORE_START`, `DISCOUNT_ENDED`, `NOT_NORMALIZABLE`)은 요청 형식(`422`) 단계에서 함께 확인하고, DB를 봐야 하는 규칙(`PRODUCT_NOT_FOUND`, `PRODUCT_INACTIVE`, `BRAND_NOT_FOUND`)은 마지막 단계에서 확인한다.

#### 3.14.2 옵션

추가와 수정의 `options[]`는 항목의 용량과 가격 줄이다. 3.9의 `items[].options[]`와 같으며 배열 순서가 표시 순서(`sortOrder`)가 된다.

| 필드 | 타입 | 필수 | 규칙 |
|---|---|---|---|
| `optionLabel` | 문자열 | 아니오 | 메뉴판의 `잔`, `병` 같은 표기. 앞뒤 공백을 지운 뒤 1~100자. 없거나 `null`이면 표기 없음 |
| `pourMl` | 정수 | 아니오 | 용량(ml). 1~32767. 없거나 `null`이면 용량 없음 |
| `priceKrw` | 정수 | 예 | 가격(원). 1~99,999,999 (1억 원 미만, 최대 8자리) |
| `discount` | 객체 | 아니오 | 기간 할인. 옵션마다 하나다. 없거나 `null`이면 할인 없음 |
| `discount.discountedPriceKrw` | 정수 | `discount`를 보내면 예 | 할인가(원). 1 이상이고 `priceKrw`보다 낮아야 한다. 같거나 높으면 `DISCOUNT_NOT_LOWER` |
| `discount.startsAt` | RFC 3339 문자열 | `discount`를 보내면 예 | 할인 시작 시각. 시간대를 포함한다(없으면 `TIMEZONE_AWARE`). 이미 지난 시각이어도 된다 |
| `discount.endsAt` | RFC 3339 문자열 | `discount`를 보내면 예 | 할인 종료 시각. 이 시각부터 정가다. `startsAt`보다 늦어야 하고(`END_BEFORE_START`), 요청 시각보다 늦어야 한다(`DISCOUNT_ENDED`) |


- 옵션은 1~3개다. 빈 배열이면 `fieldErrors[].code = TOO_SHORT`, 3개를 넘으면 `TOO_LONG`이다. 현재 메뉴판 UI의 표시 칸 크기에 맞춘 제한이다. 검수(8)로 이미 게시된 항목에 옵션이 4개 이상 있으면, 직접 수정하기 전에 옵션을 명시적으로 3개 이하로 정리해야 한다. 프론트엔드는 기존 옵션을 자동으로 잘라서 저장하지 않는다.
- `optionLabel`과 `pourMl`이 모두 같은 옵션이 둘 이상이면 `DUPLICATE_OPTION_VALUES`다(8과 같다).
- 서버는 `pourMl`을 받은 그대로 저장한다. 매장 기본 잔 용량(3.6의 `defaultPourMl`)을 서버가 채우지 않는다. 프론트엔드는 잔 옵션의 입력 칸을 `defaultPourMl`로 미리 채울 수 있다. 병 옵션에는 채우지 않는다.
- **할인**: 기간은 특정 순간이므로 다른 시각처럼 UTC RFC 3339다(3.15의 현지 시각과 다르다). 할인가로 파는 기간은 `startsAt` 이상 `endsAt` 미만이다. 수정(3.14.4)은 옵션 전체를 바꾸므로, 할인을 유지하려면 3.9에서 받은 `discount`를 그대로 다시 보낸다. 빼고 보내면 할인이 지워진다. 화면을 연 뒤 할인이 끝나 `DISCOUNT_ENDED`를 받으면, 그 할인을 빼고 다시 보낸다. 끝난 할인은 응답에서 `null`이 되며, 서버는 끝난 할인을 지우는 별도 작업을 두지 않는다.
- **품절**은 이 API가 아니라 3.14.8로 바꾼다. 추가와 수정은 품절 여부를 바꾸지 않으며, 새로 추가한 항목은 판매 중이다.

#### 3.14.3 항목 추가

```http
POST /api/bars/{barId}/menu/items
Authorization: Bearer <access-token>
Content-Type: application/json
```

기존 상품을 추가할 때:

```json
{
  "menuVersion": 4,
  "productId": "44444444-4444-4444-8444-444444444444",
  "displayName": "글렌피딕 12년",
  "options": [
    { "optionLabel": "잔", "pourMl": 30, "priceKrw": 17000 },
    { "optionLabel": "병", "pourMl": null, "priceKrw": 160000 }
  ]
}
```

카탈로그에 없는 상품을 만들어 추가할 때:

```json
{
  "menuVersion": 4,
  "newProduct": {
    "brand": { "type": "existing", "brandId": "dddddddd-dddd-4ddd-8ddd-ddddddddddd1" },
    "product": {
      "category": "whisky",
      "displayName": "Deanston Virgin Oak",
      "ageYears": null,
      "editionName": "Virgin Oak",
      "abv": 46.3
    },
    "aliases": [
      { "aliasText": "딘스톤 버진 오크", "languageCode": "ko", "isSearchable": true }
    ]
  },
  "displayName": "딘스톤 버진 오크",
  "options": [
    { "optionLabel": null, "pourMl": 30, "priceKrw": 18000 }
  ]
}
```

| 필드 | 타입 | 필수 | 규칙 |
|---|---|---|---|
상품 없이 추가할 때(연결을 기다리는 위스키 또는 위스키가 아닌 메뉴, 3.9):

```json
{
  "menuVersion": 4,
  "kind": "other",
  "displayName": "진토닉",
  "options": [
    { "optionLabel": null, "pourMl": null, "priceKrw": 12000 }
  ]
}
```

| 필드 | 타입 | 필수 | 규칙 |
|---|---|---|---|
| `menuVersion` | 정수 | 예 (`null` 가능) | 3.14.1. 메뉴판이 없으면 `null` |
| `productId` | UUID 문자열 | `productId`, `newProduct`, `kind` 중 하나 | 활성 상품. 없으면 `PRODUCT_NOT_FOUND`, 비활성이면 `PRODUCT_INACTIVE` |
| `newProduct.brand` | 객체 | `newProduct`를 보내면 예 | 8.1 `create_product`의 `brand`와 같다. 없는 `brandId`는 `BRAND_NOT_FOUND` |
| `newProduct.product` | 객체 | `newProduct`를 보내면 예 | 8.1 `create_product`의 `product`와 같다 |
| `newProduct.aliases` | 배열 | 아니오 | 8.1 `create_product`의 `aliases`와 같다. 기본 `[]` |
| `kind` | `MenuItemKind` | `productId`, `newProduct`, `kind` 중 하나 | 상품 없이 추가할 항목의 종류(2.3). `whisky`이면 운영자의 연결을 기다리는 위스키, `other`이면 위스키가 아닌 메뉴다 |
| `displayName` | 문자열 | `kind`를 보내면 예, 아니면 아니오 | 메뉴판에 보일 이름. 앞뒤 공백을 지운 뒤 1~200자. 상품을 보낼 때 없거나 `null`이면 상품의 `displayName` |
| `options` | 배열 | 예 | 3.14.2 |

- `productId`, `newProduct`, `kind` 중 둘 이상을 보내거나 하나도 보내지 않으면 `422`이고 `fieldErrors[].path = productId`, `code = EXACTLY_ONE_REQUIRED`다.
- `kind`를 보냈는데 `displayName`이 없거나 `null`이면 `422`이고 `fieldErrors[].path = displayName`, `code = MISSING`이다. `displayName`을 정규화한 이름 키(3.14.1)가 빈 값이면 `NOT_NORMALIZABLE`이다.
- 같은 상품이 이미 현재 메뉴판에 있으면 `409 MENU_ITEM_EXISTS`(`details.barMenuItemId`)다. 한 상품은 메뉴판에 한 번만 있고, 용량이나 가격을 더하려면 그 항목을 수정한다(3.14.4). 상품 없이 추가할 때는 이름 키가 같은 미연결 항목이 현재 메뉴판에 있으면 같은 오류다. 종류(`kind`)가 달라도 이름 키가 같으면 같은 항목으로 본다.
- 새 항목은 메뉴판의 맨 끝에 붙는다. 이 업장이 예전에 판매했던 상품이면 그때의 `barMenuItemId`를 다시 쓴다. 상품 없이 추가한 항목은 항상 새 `barMenuItemId`를 받는다(3.14.1).
- `kind = whisky`로 추가한 항목은 운영자 확인 목록(3.18)에 올라가며, 운영자가 상품에 연결하기 전까지 고객 검색에 나오지 않는다(3.9, 3.10.2). 업주가 상품을 고를 수 있으면 `productId`로 추가하는 편이 바로 검색에 나온다.
- `newProduct`를 보내면 같은 트랜잭션 안에서 검수의 신규 생성(8.5, 8.6)과 같은 규칙으로 브랜드와 상품의 중복을 검사한다. 같은 브랜드나 상품이 있으면 아무것도 만들지 않고 `409 DUPLICATE_BRAND_FOUND` 또는 `409 DUPLICATE_PRODUCT_FOUND`다. `details`는 9.5와 같되 `extractedItemId`와 `reviewUrl`이 없다. 프론트엔드는 `details.existingProduct`(또는 `existingBrand`)를 보여 주고, 맞으면 그 `productId`(또는 `brandId`)로 다시 요청한다. `existingProduct.isActive = false`이면 그 상품으로는 추가할 수 없으므로(`PRODUCT_INACTIVE`) 다시 요청하지 않고, 상품 검색(7)에서 고르도록 안내한다(9.5).
- 만든 상품과 브랜드에는 요청한 사용자를 기록한다. 만든 상품과 별칭은 바로 모든 업장의 고객 검색과 메뉴 매칭에 쓰인다.
- 응답 본문에서 추가한 항목은 `productId`로 찾는다. 상품 없이 추가한 항목은 응답 `items`의 마지막 항목이다.

#### 3.14.4 항목 수정

```http
PUT /api/bars/{barId}/menu/items/{barMenuItemId}
Authorization: Bearer <access-token>
Content-Type: application/json
```

```json
{
  "menuVersion": 5,
  "displayName": "글렌피딕 12년",
  "options": [
    {
      "optionLabel": "잔", "pourMl": 30, "priceKrw": 18000,
      "discount": { "discountedPriceKrw": 15000, "startsAt": "2026-11-01T09:00:00Z", "endsAt": "2026-11-15T15:00:00Z" }
    },
    { "optionLabel": "병", "pourMl": null, "priceKrw": 170000, "discount": null }
  ]
}
```

| 필드 | 타입 | 필수 | 규칙 |
|---|---|---|---|
| `menuVersion` | 정수 | 예 | 3.14.1 |
| `displayName` | 문자열 | 예 | 앞뒤 공백을 지운 뒤 1~200자 |
| `options` | 배열 | 예 | 3.14.2. 기존 옵션 전체를 이 배열로 바꾼다 |

- `barMenuItemId`가 이 업장의 현재 메뉴판에 없거나 UUID 형식이 아니면 `404 MENU_ITEM_NOT_FOUND`(`details.barMenuItemId`)다.
- 요청으로 연결할 상품을 정할 수는 없다. 다른 상품으로 바꾸려면 삭제한 뒤 추가한다. 이름을 고쳐 다시 매칭한 결과로만 연결이 바뀐다(아래). 항목의 종류(`kind`)도 바꿀 수 없다. 종류를 잘못 골랐으면 삭제한 뒤 다시 추가한다.
- **이름을 고치면 다시 매칭한다.** `kind = whisky`인 항목의 `displayName`을 정규화한 값이 지금 이름을 정규화한 값과 다르면, 검수의 다시 매칭(8.11)과 같은 규칙으로 새 이름을 다시 매칭한다. 결과가 지금 상품과 같으면 그대로이고, 다른 상품 하나로 확정되면 그 상품으로 연결을 바꾸고, 확정되지 않으면 연결을 푼다(3.14.1의 연결 바꾸기). 연결이 바뀌거나 풀리면 운영자 확인(3.18, 사유 `relinked_by_name` 또는 `unlinked_by_name`)에 올린다. 연결이 풀린 항목은 운영자가 연결할 때까지 고객 검색에 나오지 않는다. 상품 없는 위스키 항목이 확정되면 그 상품에 연결하고 `relinked_by_name`을 더한다. `kind = other`는 다시 매칭하지 않는다.
- 상품에 연결되지 않은 항목(이름을 고쳐 연결이 풀린 항목 포함)은 `displayName`을 바꾸면 이름 키(3.14.1)도 바뀐다. 바뀐 이름 키가 현재 메뉴판의 다른 미연결 항목과 같으면 `409 MENU_ITEM_EXISTS`(`details.barMenuItemId`에 그 항목)이고, 정규화한 값이 빈 값이면 `422 NOT_NORMALIZABLE`이다. `barMenuItemId`와 품절 상태는 그대로다.
- 메뉴판에서의 위치는 그대로다.

#### 3.14.5 항목 삭제

```http
DELETE /api/bars/{barId}/menu/items/{barMenuItemId}?menuVersion=5
Authorization: Bearer <access-token>
```

- `menuVersion` 쿼리는 필수다(3.14.1). 요청 본문은 없다.
- `barMenuItemId`가 이 업장의 현재 메뉴판에 없거나 UUID 형식이 아니면 `404 MENU_ITEM_NOT_FOUND`다.
- 항목은 메뉴판에서만 빠진다. `barMenuItemId`는 남아 같은 상품을 다시 추가할 때 쓰인다.
- 마지막 항목을 지워도 메뉴판은 남는다(3.9.1의 `items = []`).

#### 3.14.6 메뉴판 초기화

```http
POST /api/bars/{barId}/menu/reset
Authorization: Bearer <access-token>
Content-Type: application/json
```

```json
{ "menuVersion": 6 }
```

- 메뉴판의 항목을 모두 뺀다. 메뉴판은 남으므로 응답은 `menuBoardId`, `publishedAt`이 있고 `items = []`다(3.9.1). 고객 화면은 "현재 판매 중인 메뉴가 없습니다"를 표시한다.
- 메뉴판이 없으면(`menuVersion = null`) 아무것도 바꾸지 않고 `200 OK`다.
- 되돌리는 API는 없다. 프론트엔드는 초기화 전에 확인을 받는다.

#### 3.14.7 오류와 프론트엔드 처리

프론트엔드는 오류를 기다리지 않고 편집을 미리 막는다. 메뉴 관리 화면에 들어올 때 3.6(또는 3.11.9)을 다시 불러와 `activeMenuImport`가 있으면 추가, 수정, 삭제, 초기화 버튼을 비활성화하고(품절 표시와 판매 정보 확인은 막지 않는다), 검수 중에는 메뉴를 고칠 수 없다는 안내와 함께 그 작업으로 가는 버튼을 보여 준다. 작업을 반영하거나 취소한 뒤 돌아오면 다시 불러와 편집을 푼다. 아래 `409 ACTIVE_IMPORT_EXISTS`는 화면에 보인 상태가 오래된 경우의 안전장치다.

| HTTP | code | 발생 조건 | 프론트엔드 처리 |
|---|---|---|---|
| `401` | `UNAUTHENTICATED` | 3.1.5 | 3.1.5 |
| `403` | `FORBIDDEN` | operator도 해당 업장의 업주도 아님 | 3.1.5 |
| `404` | `BAR_NOT_FOUND` | 업장이 없거나 `barId`가 UUID 형식이 아님, 비활성 업장 | 업장 목록으로 이동 |
| `404` | `MENU_ITEM_NOT_FOUND` | 수정, 삭제할 항목이 현재 메뉴판에 없음 | 3.9를 다시 불러와 목록 갱신 |
| `409` | `ACTIVE_IMPORT_EXISTS` | 업장에 미완료 메뉴 등록 작업이 있음. `details.menuImportId`, `details.status` | 3.6을 다시 불러와 편집을 막은 화면으로 전환 |
| `409` | `MENU_OUTDATED` | 보낸 `menuVersion`이 현재 값과 다름. 다른 기기나 operator의 편집, 검수 반영, 성공한 요청의 재전송 | 3.9를 다시 불러오고, 입력 중이던 값은 유지한 채 다시 저장하게 함 |
| `409` | `MENU_ITEM_EXISTS` | 추가하려는 상품, 또는 같은 이름 키의 미연결 항목이 이미 메뉴판에 있음(3.14.3). 미연결 항목의 이름을 다른 미연결 항목과 같게 바꿈(3.14.4). `details.barMenuItemId` | 그 항목의 수정 화면으로 안내 |
| `409` | `DUPLICATE_BRAND_FOUND`, `DUPLICATE_PRODUCT_FOUND` | 신규 브랜드나 상품과 같은 것이 이미 있음 (3.14.3, 9.5) | 기존 브랜드나 상품을 보여 주고 고르게 함. `existingProduct.isActive = false`이면 상품 검색으로 안내 |
| `422` | `VALIDATION_FAILED` | 필드 규칙 위반, `TOO_SHORT`, `TOO_LONG`, `DUPLICATE_OPTION_VALUES`, `DISCOUNT_NOT_LOWER`, `DISCOUNT_ENDED`, `END_BEFORE_START`, `EXACTLY_ONE_REQUIRED`, `NOT_NORMALIZABLE`(신규 브랜드·상품 이름이나 별칭, 또는 미연결 항목의 `displayName`에 쓸 수 있는 글자가 없음, 8.7과 같다), `PRODUCT_NOT_FOUND`, `PRODUCT_INACTIVE`, `BRAND_NOT_FOUND` | `fieldErrors` 표시 |
| `503` | `TEMPORARY_WRITE_CONFLICT` | 직렬화 충돌 3회 재시도 실패 | 잠시 후 같은 요청 재시도 |

#### 3.14.8 품절 표시

```http
PUT /api/bars/{barId}/menu/items/{barMenuItemId}/sold-out
Authorization: Bearer <access-token>
Content-Type: application/json
```

```json
{ "soldOut": true }
```

메뉴 항목 하나를 품절로 표시하거나 판매 중으로 되돌린다. 품절은 옵션이 아니라 항목 단위다. 권한은 3.14.1과 같다(operator와 해당 업장의 현재 업주, 비활성 업장은 `404 BAR_NOT_FOUND`).

| 필드 | 타입 | 필수 | 규칙 |
|---|---|---|---|
| `soldOut` | 불리언 | 예 | `true`이면 품절, `false`이면 판매 중 |

- 품절은 메뉴 내용이 아니라 재고 상태이므로 3.14.1의 다음 규칙을 적용하지 않는다.
  - **미완료 작업**: 검수 중에도 바꿀 수 있다. 검수 반영(8)의 "검수 데이터를 만든 뒤 현재 메뉴판이 바뀌었는지" 검사에서도 품절 변경은 메뉴판 변경으로 보지 않는다.
  - **메뉴판 버전**: `menuVersion`을 받지 않고 올리지도 않는다. `publishedAt`도 바뀌지 않는다. 품절은 재고 상태이지 판매 정보(상품과 가격)를 바꾸거나 확인한 것이 아니고, `publishedAt`은 고객 검색의 `menuUpdatedAt`으로도 쓰이기 때문이다. 따라서 업주 화면의 "최근 갱신"(3.6의 `publishedAt`과 `confirmedAt` 중 늦은 시각)도 품절 변경으로는 바뀌지 않는다.
- 값을 정하는 요청이므로 같은 요청을 다시 보내도 결과가 같다. 이미 그 값이어도 `200 OK`다.
- 품절은 항목이 현재 메뉴판에 있는 동안 유지된다. 검수 반영(8)이나 항목 수정(3.14.4)으로 옵션이 바뀌어도 그대로다. 항목이 메뉴판에서 빠지면(검수의 `remove`, 3.14.5 삭제, 3.14.6 초기화) 품절이 풀리므로, 같은 상품을 다시 추가하면 판매 중으로 시작한다.
- 품절 항목은 손님에게 보이지 않는다. 비로그인 사용자와 customer의 3.9 응답과 고객 검색(3.10)에서 빠지고, operator와 해당 업장의 업주의 3.9 응답에만 `soldOut = true`로 나온다. 판매 중으로 되돌리면 바로 다시 보인다.
- `barMenuItemId`가 이 업장의 현재 메뉴판에 없거나 UUID 형식이 아니면 `404 MENU_ITEM_NOT_FOUND`다.
- 서버는 업장 행을 잠근 뒤(3.14.1) 항목이 현재 메뉴판에 있는지 확인하고 품절 값을 쓴다. 그래서 같은 항목을 내리는 검수 반영이나 삭제와 동시에 와도, 메뉴판에서 빠진 항목에 품절이 남지 않는다.

`200 OK`, 본문은 3.9와 같은 형식이다. 프론트엔드는 메뉴 관리 화면에 `activeMenuImport`가 있어도 품절 버튼은 막지 않는다.

| HTTP | code | 발생 조건 | 프론트엔드 처리 |
|---|---|---|---|
| `401` | `UNAUTHENTICATED` | 3.1.5 | 3.1.5 |
| `403` | `FORBIDDEN` | operator도 해당 업장의 업주도 아님 | 3.1.5 |
| `404` | `BAR_NOT_FOUND` | 업장이 없거나 `barId`가 UUID 형식이 아님, 비활성 업장 | 업장 목록으로 이동 |
| `404` | `MENU_ITEM_NOT_FOUND` | 항목이 현재 메뉴판에 없음 | 3.9를 다시 불러와 목록 갱신 |
| `422` | `VALIDATION_FAILED` | `soldOut` 없음(`MISSING`)이나 불리언이 아님(`BOOL_TYPE`). 문자열 `"true"`, 숫자 `1`, `null`도 불리언이 아니다 | `fieldErrors` 표시 |

#### 3.14.9 판매 정보 확인

```http
POST /api/bars/{barId}/menu/confirm
Authorization: Bearer <access-token>
Content-Type: application/json
```

```json
{ "menuVersion": 6 }
```

업주가 관리 홈의 "지금도 맞아요"로 현재 메뉴판의 상품과 가격이 지금도 맞다고 확인한 시각을 남긴다. 메뉴는 바꾸지 않는다. 권한은 3.14.1과 같다.

| 필드 | 타입 | 필수 | 규칙 |
|---|---|---|---|
| `menuVersion` | 정수 | 예 (`null` 가능) | 확인한 화면에서 받은 `menuVersion`(3.9). 메뉴판이 없으면 `null`이다(3.9.1). 서버의 현재 값과 다르면 `409 MENU_OUTDATED`다. 업주가 본 것과 다른 메뉴를 맞다고 확인하지 않게 하기 위해서다 |

- 메뉴판이 없거나 항목이 하나도 없으면 `409 NO_PUBLISHED_MENU`다. 품절 항목도 항목으로 센다. 이 검사는 `menuVersion` 비교보다 먼저 한다. 그래서 메뉴판이 없는 업장에서 `menuVersion = null`을 보내면 `NO_PUBLISHED_MENU`를 받는다. 메뉴판이 있는데 `null`을 보내면 현재 값과 다르므로 `MENU_OUTDATED`다.
- 검사 순서: 인증(`401`, 3.1.5) → 요청 형식(`422`, `menuVersion` 필드가 없으면 `MISSING`) → 업장(`404 BAR_NOT_FOUND`) → 권한(`403`) → 업장 행 잠금(3.14.1) → 업장 상태(비활성이면 `404 BAR_NOT_FOUND`) → 메뉴판과 항목(`409 NO_PUBLISHED_MENU`) → 메뉴판 버전(`409 MENU_OUTDATED`) → 확인 시각 기록. 잠금 안에서 버전을 확인하고 기록하므로, 검수 반영과 동시에 와도 반영 전의 메뉴를 반영 뒤의 시각으로 확인한 것처럼 남지 않는다.
- 메뉴를 바꾸지 않으므로 검수 중에도 할 수 있다(`ACTIVE_IMPORT_EXISTS` 없음). `menuVersion`과 `publishedAt`은 그대로다.
- 확인 시각과 확인한 사용자를 메뉴판에 기록한다. 다시 확인하면 시각을 새로 바꾼다. 같은 요청을 다시 보내도 확인 시각만 조금 늦어질 뿐 결과가 같다.
- 확인 시각은 3.6과 3.11.9의 `currentMenu.confirmedAt`에 나온다. 고객 화면(3.9)과 검색의 `menuUpdatedAt`은 지금처럼 메뉴판을 마지막으로 바꾼 시각(`publishedAt`)이다.
- 검수 반영이나 직접 편집으로 메뉴판이 바뀌어도 `confirmedAt`은 그대로 남는다. 업주 화면의 "최근 갱신"은 프론트엔드가 `publishedAt`과 `confirmedAt` 중 늦은 시각으로 계산한다.

`200 OK`, 본문은 3.6과 같은 형식이다.

| HTTP | code | 발생 조건 | 프론트엔드 처리 |
|---|---|---|---|
| `401` | `UNAUTHENTICATED` | 3.1.5 | 3.1.5 |
| `403` | `FORBIDDEN` | operator도 해당 업장의 업주도 아님 | 3.1.5 |
| `404` | `BAR_NOT_FOUND` | 업장이 없거나 `barId`가 UUID 형식이 아님, 비활성 업장 | 업장 목록으로 이동 |
| `409` | `MENU_OUTDATED` | 보낸 `menuVersion`이 현재 값과 다름 | 3.9를 다시 불러와 바뀐 메뉴를 보여 주고 다시 확인하게 함 |
| `409` | `NO_PUBLISHED_MENU` | 메뉴판이 없거나 항목이 없음 | "지금도 맞아요" 버튼을 숨기고 메뉴 등록으로 안내 |
| `422` | `VALIDATION_FAILED` | `menuVersion` 필드가 없음(`MISSING`)이나 정수도 `null`도 아님 | `fieldErrors` 표시 |

#### 3.14.10 실제 응답 예시와 호출자별 결과

2.4의 방법으로 받은 응답이다. 관악 위스키 바는 검수 반영(8.9)으로 글렌피딕 12년 한 항목이 게시된 상태(`menuVersion = 1`)에서 시작한다. 성공 응답은 3.9와 같은 형식이므로 바뀐 부분만 싣는다.

**항목 추가 (3.14.3)**

```json
{
  "menuVersion": 1,
  "productId": "44444444-4444-4444-8444-444444444442",
  "displayName": "맥캘란 12년 더블캐스크",
  "options": [
    { "optionLabel": "잔", "pourMl": 30, "priceKrw": 22000 },
    { "optionLabel": "병", "pourMl": null, "priceKrw": 210000 }
  ]
}
```

`201 Created`. `menuVersion`이 1 오르고 새 항목이 맨 끝에 붙는다.

```json
{
  "barId": "22222222-2222-4222-8222-222222222222",
  "menuBoardId": "66666666-6666-4666-8666-666666666661",
  "menuVersion": 2,
  "publishedAt": "2026-11-09T12:47:30.129760Z",
  "items": [
    { "barMenuItemId": "55555555-5555-4555-8555-555555555551", "displayName": "글렌피딕 12년", "...": "그대로" },
    {
      "menuBoardEntryId": "88888888-8888-4888-8888-888888888882",
      "barMenuItemId": "55555555-5555-4555-8555-555555555552",
      "productId": "44444444-4444-4444-8444-444444444442",
      "productName": "The Macallan 12 Double Cask",
      "brandId": "dddddddd-dddd-4ddd-8ddd-ddddddddddd2",
      "brandName": "The Macallan",
      "category": "whisky",
      "displayName": "맥캘란 12년 더블캐스크",
      "sortOrder": 2,
      "soldOut": false,
      "options": [
        {
          "menuEntryOptionId": "99999999-9999-4999-8999-999999999993",
          "optionLabel": "잔",
          "pourMl": 30,
          "priceKrw": 22000,
          "discount": null,
          "sortOrder": 1
        },
        {
          "menuEntryOptionId": "99999999-9999-4999-8999-999999999994",
          "optionLabel": "병",
          "pourMl": null,
          "priceKrw": 210000,
          "discount": null,
          "sortOrder": 2
        }
      ]
    }
  ],
  "...": "업장 정보는 3.9와 같다"
}
```

**항목 수정 (3.14.4)**. 잔 옵션에 할인을 넣고 병 옵션은 `"discount": null`로 보냈다(`menuVersion: 2`). 응답의 그 항목이다. 옵션 전체가 바뀌므로 `menuEntryOptionId`도 새로 만들어졌다.

```json
{
  "barMenuItemId": "55555555-5555-4555-8555-555555555552",
  "displayName": "맥캘란 12년 더블캐스크",
  "options": [
    {
      "menuEntryOptionId": "99999999-9999-4999-8999-999999999995",
      "optionLabel": "잔",
      "pourMl": 30,
      "priceKrw": 22000,
      "discount": {
        "discountedPriceKrw": 19000,
        "startsAt": "2026-11-09T09:00:00Z",
        "endsAt": "2026-11-30T15:00:00Z"
      },
      "sortOrder": 1
    },
    {
      "menuEntryOptionId": "99999999-9999-4999-8999-999999999996",
      "optionLabel": "병",
      "pourMl": null,
      "priceKrw": 210000,
      "discount": null,
      "sortOrder": 2
    }
  ],
  "...": "나머지는 위와 같다"
}
```

**품절 표시 (3.14.8)**. 글렌피딕 12년에 `{"soldOut": true}`를 보냈다. 업주가 받는 응답에는 항목이 그대로 있고 `soldOut`만 바뀐다. `menuVersion`(`3`)과 `publishedAt`은 그대로다. 같은 시점에 customer가 3.9를 조회하면 `items`에 맥캘란 12년 더블캐스크 한 항목만 있다.

```json
{
  "menuVersion": 3,
  "publishedAt": "2026-11-09T12:47:30.340339Z",
  "items": [
    { "barMenuItemId": "55555555-5555-4555-8555-555555555551", "displayName": "글렌피딕 12년", "soldOut": true, "...": "그대로" },
    { "barMenuItemId": "55555555-5555-4555-8555-555555555552", "displayName": "맥캘란 12년 더블캐스크", "soldOut": false, "...": "그대로" }
  ],
  "...": "나머지는 3.9와 같다"
}
```

**판매 정보 확인 (3.14.9)**. `{"menuVersion": 3}`. 응답은 3.6 형식이며 `currentMenu.confirmedAt`이 바뀐다.

```json
{
  "barId": "22222222-2222-4222-8222-222222222222",
  "currentMenu": {
    "menuBoardId": "66666666-6666-4666-8666-666666666661",
    "menuVersion": 3,
    "publishedAt": "2026-11-09T12:47:30.340339Z",
    "confirmedAt": "2026-11-09T12:47:30.531179Z"
  },
  "...": "나머지는 3.6과 같다"
}
```

**메뉴판 초기화 (3.14.6)**. 메뉴판이 있으면 남고 항목만 빠진다(첫 번째). 메뉴판이 없는 업장에 `{"menuVersion": null}`을 보내면 아무것도 바뀌지 않는다(두 번째).

```json
{ "menuBoardId": "66666666-6666-4666-8666-666666666661", "menuVersion": 10, "publishedAt": "2026-11-09T12:47:32.323833Z", "items": [] }
```

```json
{ "menuBoardId": null, "menuVersion": null, "publishedAt": null, "items": [] }
```

**대표 오류**

오래된 `menuVersion`을 보냈을 때 (`409`). 판매 정보 확인(3.14.9)도 같은 형식이다.

```json
{"error": {"code": "MENU_OUTDATED", "message": "메뉴가 다른 곳에서 바뀌었습니다. 최신 메뉴를 다시 불러온 뒤 저장해 주세요.", "details": {"submittedMenuVersion": 1, "currentMenuVersion": 2}, "fieldErrors": []}}
```

검수 중인 작업이 있을 때 편집했을 때 (`409`)

```json
{"error": {"code": "ACTIVE_IMPORT_EXISTS", "message": "이 업장에 진행 중인 메뉴 등록 작업이 있습니다.", "details": {"menuImportId": "77777777-7777-4777-8777-777777777771", "status": "ready_for_review"}, "fieldErrors": []}}
```

이미 메뉴판에 있는 상품을 추가했을 때 (`409`)와 현재 메뉴판에 없는 항목을 수정했을 때 (`404`). 둘 다 `details.barMenuItemId`가 있다.

```json
{"error": {"code": "MENU_ITEM_EXISTS", "message": "이 상품은 이미 메뉴에 있습니다. 그 항목을 수정해 주세요.", "details": {"barMenuItemId": "55555555-5555-4555-8555-555555555552"}, "fieldErrors": []}}
```

```json
{"error": {"code": "MENU_ITEM_NOT_FOUND", "message": "메뉴 항목을 찾을 수 없습니다.", "details": {"barMenuItemId": "55555555-5555-4555-8555-555555555553"}, "fieldErrors": []}}
```

`newProduct`로 이미 있는 상품을 만들려 했을 때 (`409`). 검수(9.5)와 달리 `extractedItemId`와 `reviewUrl`이 없다.

```json
{"error": {"code": "DUPLICATE_PRODUCT_FOUND", "message": "같은 상품이 이미 등록되어 있습니다. 기존 상품을 선택해 주세요.", "details": {"existingProduct": {"productId": "44444444-4444-4444-8444-444444444443", "displayName": "Laphroaig 10", "brandId": "dddddddd-dddd-4ddd-8ddd-ddddddddddd3", "brandName": "Laphroaig", "category": "whisky", "ageYears": 10, "editionName": null, "isActive": true}}, "fieldErrors": []}}
```

메뉴판이나 항목이 없는데 판매 정보를 확인했을 때 (`409`, 3.14.9)

```json
{"error": {"code": "NO_PUBLISHED_MENU", "message": "확인할 메뉴가 없습니다. 먼저 메뉴를 등록해 주세요.", "details": null, "fieldErrors": []}}
```

`422 VALIDATION_FAILED`의 `fieldErrors` (본문의 나머지는 9.3과 같다)

| 요청 | `path` | `code` | `message` |
|---|---|---|---|
| 추가에서 `productId`와 `newProduct`를 둘 다 빠뜨림 | `productId` | `EXACTLY_ONE_REQUIRED` | productId와 newProduct 중 하나만 보내야 합니다. |
| 수정에서 이미 끝난 할인을 보냄 | `options[0].discount.endsAt` | `DISCOUNT_ENDED` | 이미 끝난 할인입니다. |
| 품절에 `"soldOut": "true"`(문자열)를 보냄 | `soldOut` | `BOOL_TYPE` | Input should be a valid boolean |
| 메뉴판이 없는 업장의 추가나 초기화에서 `menuVersion` 필드를 뺌 | `menuVersion` | `MISSING` | Field required |

마지막 행처럼 `menuVersion`은 메뉴판이 없을 때도 `null` 값으로 보내야 하며, 필드를 빼면 `422`다(3.14.1).

**호출자별 결과**. 대상은 관악 위스키 바와 그 메뉴 항목이며, 요청은 모두 형식에 맞는 본문과 현재 `menuVersion`으로 보냈다.

| API | 비로그인 | customer | 다른 업장의 업주 | 해당 업장의 업주 | operator |
|---|---|---|---|---|---|
| `POST /api/bars/{barId}/menu/items` | `401` | `403` | `403` | `201` | `201` |
| `PUT .../menu/items/{barMenuItemId}` | `401` | `403` | `403` | `200` | `200` |
| `DELETE .../menu/items/{barMenuItemId}` | `401` | `403` | `403` | `200` | `200` |
| `POST .../menu/reset` | `401` | `403` | `403` | `200` | `200` |
| `PUT .../menu/items/{barMenuItemId}/sold-out` | `401` | `403` | `403` | `200` | `200` |
| `POST .../menu/confirm` | `401` | `403` | `403` | `200` | `200` |

- 없는 `barId`로 보내면 로그인한 호출자는 모두 `404 BAR_NOT_FOUND`다(2.2).
- 요청 형식이 권한보다 먼저다(3.14.1). customer가 `{"menuVersion": "x"}`로 항목을 추가하면 `403`이 아니라 `422`(`menuVersion` `INT_PARSING`, `options` `MISSING`)를 받는다.

### 3.15 영업시간과 임시 휴무

업장의 정규 영업시간과 임시 휴무(오늘 휴무, 오늘만 영업시간 변경, 기간 휴업)를 정한다. 정규 영업시간은 매장 정보 화면에서 다른 정보와 함께 저장하므로 업장 수정(3.7)의 `weeklyHours`로 바꾼다. 임시 휴무는 관리 홈에서 바로 적용하고 취소하므로 따로 3.15.2와 3.15.3으로 바꾼다. 둘 다 3.6, 3.11.9, 3.9 응답에 나온다.

영업시간의 시각과 날짜는 모두 서울 시간(`Asia/Seoul`) 기준의 현지 값이다. 한국에는 서머타임이 없으므로 UTC로 바꾸지 않고 `"HH:MM"`과 `"YYYY-MM-DD"` 문자열로 주고받는다. `createdAt` 같은 순간 시각은 지금처럼 UTC RFC 3339다.

#### 3.15.1 정규 영업시간

`weeklyHours`는 요일별 영업시간 배열이다. 요일마다 영업 구간은 하나이며 브레이크 타임은 없다.

```json
[
  { "dayOfWeek": 1, "closed": true, "openTime": null, "closeTime": null },
  { "dayOfWeek": 5, "closed": false, "openTime": "18:00", "closeTime": "02:00" },
  { "dayOfWeek": 6, "closed": false, "openTime": "17:00", "closeTime": "23:30" }
]
```

| 필드 | 타입 | 필수 | 규칙 |
|---|---|---|---|
| `dayOfWeek` | 정수 | 예 | 1(월)~7(일). ISO 8601 요일 번호다. 배열 안에서 중복되면 `DUPLICATE_DAY` |
| `closed` | 불리언 | 예 | `true`이면 정기 휴무일 |
| `openTime` | `"HH:MM"` 문자열 | `closed = false`이면 예 | 영업 시작. `00:00`~`23:55`, 5분 단위. 형식이나 단위가 틀리면 `INVALID_TIME` |
| `closeTime` | `"HH:MM"` 문자열 | `closed = false`이면 예 | 영업 종료. 규칙은 `openTime`과 같다 |

- 배열에 없는 요일은 "영업시간 정보 없음"이며 정기 휴무와 다르다.
- `closed = true`이면 `openTime`과 `closeTime`을 보내지 않거나 `null`로 보낸다. 값이 있으면 `TIME_ON_CLOSED_DAY`다. `closed = false`인데 둘 중 하나라도 없으면 `MISSING`이다.
- `closeTime`이 `openTime`보다 이르면 다음 날 그 시각에 끝난다(자정 넘김). 예를 들어 금요일 `18:00`~`02:00`은 금요일 18시부터 토요일 2시까지다. 자정에 끝나면 `closeTime = "00:00"`이다. "다음 날" 표시는 따로 보내지 않으며, 프론트엔드는 `closeTime < openTime`이면 "익일"로 표시한다.
- `openTime`과 `closeTime`이 같으면 `SAME_OPEN_CLOSE`다. 24시간 영업은 표현하지 않는다.
- 응답은 `dayOfWeek` 오름차순이고 형식은 요청과 같다. `closed = true`인 요일은 `openTime`, `closeTime`이 `null`이다.
- 평일에 같은 시간 복사 같은 입력 편의 기능은 프론트엔드에서만 처리한다.

#### 3.15.2 임시 휴무 적용

```http
PUT /api/bars/{barId}/operating-exception
Authorization: Bearer <access-token>
Content-Type: application/json
```

operator와 해당 업장의 현재 업주가 호출할 수 있다(2.2). 비활성 업장도 바꿀 수 있다(3.7과 같다). 업장마다 임시 휴무는 하나만 있으며, 이 요청은 기존 임시 휴무(아직 시작하지 않은 기간 휴업 포함)를 이 요청의 내용으로 바꾼다. 같은 요청을 다시 보내도 결과가 같으므로(아래 "재시도") `Idempotency-Key`는 받지 않는다.

`kind`에 따라 보내는 필드가 다르다.

| `kind` | 뜻 | 날짜 | 시간 |
|---|---|---|---|
| `closed_today` | 오늘 하루 임시 휴무 | `date` 필수(`"YYYY-MM-DD"`). 서버의 오늘 날짜와 다르면 `DATE_NOT_TODAY` | 보내지 않는다 |
| `custom_hours` | 오늘만 영업시간 변경 | `date` 필수. 규칙은 `closed_today`와 같다 | `openTime`, `closeTime` 필수. 규칙은 3.15.1과 같으며 자정을 넘길 수 있다 |
| `vacation` | 기간 임시 휴업 | `startDate`, `endDate` 필수(`"YYYY-MM-DD"`). `startDate`가 오늘보다 이르면 `DATE_IN_PAST`, `endDate`가 `startDate`보다 이르면 `END_BEFORE_START`. 하루만 지정해도 된다 | 보내지 않는다 |

- "오늘"은 서버가 요청을 받은 시각의 서울 날짜다. 프론트엔드는 화면을 연 시각이 아니라 적용 버튼을 누른 시각의 서울 날짜를 `date`로 보낸다. 서버가 날짜를 정하지 않는 이유는, 자정 직전에 보낸 요청을 자정이 지나 다시 보냈을 때 다른 날에 적용되지 않게 하기 위해서다.
- `date`가 서버의 오늘과 다르면(기기 시계가 틀렸거나, 자정 무렵에 보낸 요청이 자정이 지나 도착함) `422`이고 `fieldErrors[].code = DATE_NOT_TODAY`다. 프론트엔드는 날짜가 바뀌었다고 안내하고 다시 적용하게 한다.
- **재시도**: 요청의 내용(`kind`, 날짜, 시각, 앞뒤 공백을 지운 `note`)이 현재 임시 휴무와 모두 같으면, 날짜 검사(`DATE_NOT_TODAY`, `DATE_IN_PAST`) 없이 아무것도 바꾸지 않고 `200 OK`로 현재 상태를 돌려준다. 그래서 응답을 받지 못해 자정이 지난 뒤 같은 요청을 다시 보내도 오류 없이 같은 결과를 받는다.
- 공통 필드 `note`는 고객 안내 문구로 선택이다. 앞뒤 공백을 지운 뒤 100자 이하이고, 없거나 공백뿐이면 `null`로 저장한다. 한 줄 문구이므로 줄바꿈과 제어 문자는 받지 않는다(`INVALID_CHARACTER`).
- `kind`에 맞지 않는 필드(예: `closed_today`의 `openTime`)를 보내면 `422`이고 `fieldErrors[].code = EXTRA_FORBIDDEN`이다. `kind`가 없거나 다른 값이면 `UNION_TAG_NOT_FOUND`나 `UNION_TAG_INVALID`다.

```json
{ "kind": "custom_hours", "date": "2026-11-06", "openTime": "20:00", "closeTime": "01:00", "note": "내부 사정으로 늦게 엽니다" }
```

```json
{ "kind": "vacation", "startDate": "2026-11-10", "endDate": "2026-11-12", "note": null }
```

`200 OK`, 본문은 3.6과 같은 형식이며 `operatingException`에 적용한 내용이 들어 있다.

#### 3.15.3 임시 휴무 취소

```http
DELETE /api/bars/{barId}/operating-exception
Authorization: Bearer <access-token>
```

임시 휴무를 지우고 정규 영업시간으로 돌아간다. 권한은 3.15.2와 같다. 임시 휴무가 없거나 이미 끝났어도 `200 OK`이므로 다시 보내도 된다. 본문은 3.6과 같은 형식이며 `operatingException = null`이다.

#### 3.15.4 유효 기간과 응답

3.6, 3.11.9, 3.9의 `operatingException`:

| 필드 | 타입 | null 가능 | 설명 |
|---|---|---|---|
| `kind` | `closed_today` \| `custom_hours` \| `vacation` | 아니오 | |
| `startDate`, `endDate` | `"YYYY-MM-DD"` 문자열 | 아니오 | 적용 날짜. `closed_today`와 `custom_hours`는 적용한 날로 둘이 같다 |
| `openTime`, `closeTime` | `"HH:MM"` 문자열 | 예 | `custom_hours`일 때만 값이 있다. `closeTime < openTime`이면 다음 날 끝난다 |
| `note` | 문자열 | 예 | 고객 안내 문구. 없으면 `null` |

- 임시 휴무는 `endDate` 다음 날 0시에 끝난다. 단, 자정을 넘기는 `custom_hours`는 다음 날 `closeTime`까지 유효하다.
- **응답에는 `endDate` 다음 날이 끝날 때까지 남는다.** 끝난 뒤에도 하루 더 보내는 이유는, 그날 새벽의 영업 상태를 계산할 때 전날의 정규 영업이 넘어오지 않게 막아야 하기 때문이다(3.15.5의 2). 예를 들어 금요일 정규 영업시간이 `18:00`~`02:00`이고 금요일에 `custom_hours` `18:00`~`22:00`을 적용했다면, 토요일 0시 30분에는 금요일 정규 영업이 아니라 이 임시 휴무로 계산해야 영업 종료가 된다.
- 그 다음 날부터 서버는 `operatingException = null`로 보낸다. 끝난 행을 지우는 별도 작업은 두지 않으며, 다음 적용(3.15.2)이나 취소(3.15.3) 때 바뀌거나 지워진다.
- 그래서 응답에 `operatingException`이 있어도 지금 적용 중이라는 뜻은 아니다. 프론트엔드는 아래 기준으로 지금 적용 중인지 판단해 업주 화면의 "오늘 임시 휴무" 같은 표시와 고객 안내 문구에 쓴다. 화면을 띄워 둔 동안에도 바뀔 수 있으므로 3.15.5처럼 다시 계산한다.
  - 적용 중: 오늘이 `startDate`~`endDate` 안이거나, 자정을 넘기는 `custom_hours`의 `endDate` 다음 날이고 현재 시각이 `closeTime`보다 이를 때
  - 예정: `startDate`가 오늘보다 뒤일 때
  - 끝남: 그 밖의 경우. 화면에는 정상 영업으로 보여 준다
- `endDate` 다음 날 새로 임시 휴무를 적용하면 전날 것은 바뀌어 응답에서 빠진다. 그날 새벽에는 전날 정규 영업이 넘어온 것으로 계산될 수 있지만, 드문 경우라 따로 막지 않는다.
- 아직 시작하지 않은 `vacation`(`startDate`가 오늘보다 뒤)도 응답에 나온다. 업주 화면은 "임시 휴업 예정"으로 보여 줄 수 있고, 고객 영업 상태에는 `startDate`부터 반영한다(3.15.5).

#### 3.15.5 고객 영업 상태 계산

서버는 "영업 중" 같은 영업 상태를 보내지 않는다. 프론트엔드가 `weeklyHours`, `operatingException`과 기기의 현재 시각(서울 시간으로 바꾼 값)으로 계산하고, 화면을 띄워 둔 동안 30초마다 다시 계산한다. 서버가 계산하면 응답을 받은 순간에만 맞고, 화면에 머무는 동안에는 결국 프론트엔드가 다시 계산해야 하기 때문이다. 대신 기기 시계가 틀리면 상태도 틀릴 수 있다.

오늘 날짜를 D, 현재 시각을 t라고 할 때 아래 순서로 처음 맞는 결과를 쓴다. "임시 휴무가 D를 덮는다"는 `startDate ≤ D ≤ endDate`라는 뜻이다.

1. 임시 휴무가 D를 덮고 `kind`가 `closed_today`나 `vacation`이면 **임시 휴무**다. D의 0시부터 다음 날 0시까지 휴무이므로, 전날 밤부터 이어지던 영업도 0시에 끝난 것으로 본다.
2. 전날(D-1)에서 넘어온 영업:
   - 임시 휴무가 D-1을 덮으면, 그것이 자정을 넘기는 `custom_hours`이고 t < `closeTime`일 때만 **영업 중**이다. 임시 휴무는 그날의 정규 영업시간을 대신하므로 D-1의 정규 영업은 넘어오지 않는다.
   - 임시 휴무가 D-1을 덮지 않으면, D-1 요일의 정규 영업시간이 자정을 넘기고 t < `closeTime`일 때 **영업 중**이다.
3. 오늘의 영업 구간은 임시 휴무가 D를 덮는 `custom_hours`이면 그 시간이고, 아니면 D 요일의 정규 영업시간(`closed = false`)이다. `openTime ≤ t`이고, 자정을 넘기는 구간이거나 t < `closeTime`이면 **영업 중**이다.
4. 그 밖에는, 오늘 `custom_hours`가 없고 D 요일이 `weeklyHours`에 없으면 **영업시간 정보 없음**, 아니면 **영업 종료**다. 다른 요일이 있어도 오늘 요일이 없으면 정보 없음이다(3.15.1). 정기 휴무(`closed = true`)인 요일은 영업 종료다.

- 고객 안내 문구(`note`)는 임시 휴무가 적용 중인 동안(3.15.4) 영업 상태와 함께 보여 줄 수 있다. 비어 있으면 표시하지 않는다.
- 이 상태는 메뉴 게시 여부(3.6의 `currentMenu`)와 따로 계산한다.
- 업주 화면의 미리보기와 관리 홈도 같은 규칙을 쓴다.

#### 3.15.6 오류와 프론트엔드 처리

백엔드는 다음 순서로 확인하고, 처음 걸린 단계의 오류를 반환한다. 메뉴 직접 편집(3.14.1)과 달리 권한을 요청 형식보다 먼저 확인하므로, operator도 해당 업장의 업주도 아닌 호출자는 본문이 잘못되어도 `422`가 아니라 `403`을 받는다.

1. 인증 (`401`, 3.1.5)
2. 업장 (`404 BAR_NOT_FOUND`)
3. 권한 (`403 FORBIDDEN`)
4. 요청 형식과 3.15.2의 필드 규칙 (`422 VALIDATION_FAILED`). `SAME_OPEN_CLOSE`와 `END_BEFORE_START`도 이 단계다
5. 업장 행을 잠근 뒤 권한 다시 확인 (`403 FORBIDDEN`, 3.11.10). 비활성 업장도 바꿀 수 있으므로 업장 상태는 확인하지 않는다
6. 날짜 (`422`, `DATE_NOT_TODAY`, `DATE_IN_PAST`). 요청이 현재 임시 휴무와 같으면 건너뛴다(3.15.2의 "재시도")

`DELETE`(3.15.3)는 4단계와 6단계가 없다.

| HTTP | code | 발생 조건 | 프론트엔드 처리 |
|---|---|---|---|
| `401` | `UNAUTHENTICATED` | 3.1.5 | 3.1.5 |
| `403` | `FORBIDDEN` | operator도 해당 업장의 업주도 아님 | 3.1.5 |
| `404` | `BAR_NOT_FOUND` | 업장이 없거나 `barId`가 UUID 형식이 아님 | 업장 목록으로 이동 |
| `422` | `VALIDATION_FAILED` | 위 규칙 위반: `MISSING`, `DUPLICATE_DAY`, `INVALID_TIME`, `SAME_OPEN_CLOSE`, `TIME_ON_CLOSED_DAY`, `DATE_IN_PAST`, `DATE_NOT_TODAY`, `END_BEFORE_START`, `INVALID_CHARACTER`, `EXTRA_FORBIDDEN`, `STRING_TOO_LONG`(`note` 100자 초과), `UNION_TAG_NOT_FOUND`와 `UNION_TAG_INVALID`(`kind`가 없거나 다른 값, `path`는 빈 문자열) | `fieldErrors` 표시. `DATE_IN_PAST`이면 날짜를 다시 고르게 하고, `DATE_NOT_TODAY`이면 날짜가 바뀌었다고 안내한 뒤 다시 적용하게 함 |

#### 3.15.7 실제 응답 예시와 호출자별 결과

2.4의 방법으로 받은 응답이다. 서울 날짜로 2026-11-09에 관악 위스키 바에 적용했다. 응답은 3.6 형식이므로 `operatingException`만 싣는다.

**오늘 휴무 (`closed_today`)**

```json
{ "kind": "closed_today", "date": "2026-11-09", "note": "내부 공사로 하루 쉽니다" }
```

```json
{
  "operatingException": {
    "kind": "closed_today",
    "startDate": "2026-11-09",
    "endDate": "2026-11-09",
    "openTime": null,
    "closeTime": null,
    "note": "내부 공사로 하루 쉽니다"
  },
  "...": "나머지는 3.6과 같다"
}
```

같은 요청을 다시 보내도 `200`과 같은 응답이다. 3.15.2의 `custom_hours`와 `vacation` 요청 예시(날짜만 2026-11-09, 2026-11-12~14로 바꿈)에 대한 응답의 `operatingException` 값은 다음과 같다. 응답 전체는 위 `closed_today`처럼 3.6 형식이다. `custom_hours`도 `startDate`와 `endDate`가 같다.

```json
{ "kind": "custom_hours", "startDate": "2026-11-09", "endDate": "2026-11-09", "openTime": "20:00", "closeTime": "01:00", "note": "내부 사정으로 늦게 엽니다" }
```

```json
{ "kind": "vacation", "startDate": "2026-11-12", "endDate": "2026-11-14", "openTime": null, "closeTime": null, "note": null }
```

취소(3.15.3)의 응답은 `"operatingException": null`이다.

**대표 오류**

어제 날짜(`"date": "2026-11-08"`)로 `closed_today`를 보냈을 때 (`422`)

```json
{
  "error": {
    "code": "VALIDATION_FAILED",
    "message": "입력값을 확인해 주세요.",
    "details": null,
    "fieldErrors": [
      {
        "path": "date",
        "code": "DATE_NOT_TODAY",
        "message": "날짜가 바뀌었습니다. 다시 적용해 주세요."
      }
    ]
  }
}
```

나머지 `422`의 `fieldErrors`

| 요청 | `path` | `code` | `message` |
|---|---|---|---|
| `closed_today`에 `"openTime": "18:00"` | `openTime` | `EXTRA_FORBIDDEN` | Extra inputs are not permitted |
| `vacation`의 `startDate`가 어제 | `startDate` | `DATE_IN_PAST` | 지난 날짜부터 시작할 수 없습니다. |
| `"kind": "holiday"` | 빈 문자열 | `UNION_TAG_INVALID` | Input tag 'holiday' found using 'kind' does not match any of the expected tags: 'closed_today', 'custom_hours', 'vacation' |
| `note`가 101자 | `note` | `STRING_TOO_LONG` | String should have at most 100 characters |

**호출자별 결과**. 대상은 관악 위스키 바다.

| API | 비로그인 | customer | 다른 업장의 업주 | 해당 업장의 업주 | operator |
|---|---|---|---|---|---|
| `PUT /api/bars/{barId}/operating-exception` | `401` | `403` | `403` | `200` | `200` |
| `DELETE /api/bars/{barId}/operating-exception` | `401` | `403` | `403` | `200` | `200` |

### 3.16 매장 사진

고객 업장 상세와 업주 매장 정보 화면에 보여 줄 매장 사진이다. 메뉴판 사진(4장)이나 업주 신청 메뉴판 사진(3.11.15)과는 따로 저장하며, 메뉴판 사진은 고객에게 보이지 않는다.

| 메서드 | 경로 | 용도 |
|---|---|---|
| `POST` | `/api/bars/{barId}/photos` | 사진 한 장 추가 (3.16.2) |
| `DELETE` | `/api/bars/{barId}/photos/{photoId}` | 사진 삭제 (3.16.3) |
| `PUT` | `/api/bars/{barId}/photos/order` | 순서 변경과 대표 사진 지정 (3.16.4) |
| `GET` | `/api/bar-photos/{photoId}` | 사진 파일 (3.16.5, 공개) |
| `GET` | `/api/bar-photos/{photoId}/thumbnail` | 썸네일 파일 (3.16.5, 공개) |

#### 3.16.1 공통 규칙

- **권한**: 추가, 삭제, 순서 변경은 operator와 해당 업장의 현재 업주가 호출할 수 있다(2.2). 비활성 업장도 바꿀 수 있다(3.7과 같다). 사진 파일 조회(3.16.5)는 공개다.
- **장수**: 업장당 최대 15장이다. 메뉴판 사진의 15장(4.1)과는 따로 센다.
- **대표 사진**: 표시 순서의 첫 사진이 대표 사진이다. 대표 여부를 따로 저장하지 않으며, 대표 사진을 바꾸려면 그 사진을 맨 앞으로 옮긴다(3.16.4). 대표 사진을 지우면 다음 사진이 대표가 된다. 업장 목록 API(3.4, 3.10, 3.11.11, 3.12, 3.13)는 업장마다 대표 사진의 썸네일 URL만 `coverThumbnailUrl`로 준다. 목록은 업장이 많아(지도는 1,000곳이 넘을 수 있다) 원본을 쓰면 내려받는 양과 메모리가 너무 크기 때문이다.
- **사진이 없을 때**: 0장도 허용하며 마지막 사진도 지울 수 있다. 프론트엔드는 `photos = []`이면 기본 이미지를 보여 준다.
- **신청에서 온 사진**: `new_bar` 신청에 대표 사진(3.11.17)이 있었으면 승인할 때 그 사진이 첫 사진이 된다(3.11.7). 그 뒤에는 다른 사진과 같이 지우고 옮길 수 있다.
- **응답**: 추가, 삭제, 순서 변경의 성공 응답 본문은 `{ "photos": [...] }`이며 3.6의 `photos`와 같은 형식이다. 프론트엔드는 이 응답으로 화면을 바꾸고 따로 다시 조회하지 않아도 된다.
- **동시 요청**: 추가, 삭제, 순서 변경은 업장 행을 잠그고 처리하므로 한 업장에서는 하나씩 차례로 반영된다.
- **저장소**: 메뉴판 사진과 같은 저장소(개발 환경은 로컬 파일, 배포 서버는 비공개 S3 버킷)에 사진마다 다시 인코딩한 사진과 썸네일 두 파일을 둔다(3.16.2). 버킷은 공개하지 않으며, 서버가 파일을 읽어 3.16.5로 전달한다.

#### 3.16.2 사진 추가

```http
POST /api/bars/{barId}/photos
Authorization: Bearer <access-token>
Content-Type: multipart/form-data
```

| 필드 | 타입 | 필수 | 설명 |
|---|---|---|---|
| `image` | 이미지 파일 | 예 | 사진 한 장. 여러 장은 한 장씩 차례로 올린다 |

- JPEG와 PNG만 받으며 형식은 메뉴판 사진(4.1)처럼 파일 내용으로 판별한다. 사진당 **2MB 이하**다. 메뉴판 사진(사진당 10MB)보다 작은 이유는 고객 화면이 업장마다 최대 15장을 내려받기 때문이다.
- 안드로이드 앱은 올리기 전에 **반드시** 사진의 긴 변을 2048px 이하로 줄이고 JPEG로 압축한다. 압축한 뒤에도 2MB를 넘으면 품질을 낮춰 다시 압축한다. PNG나 다른 형식의 사진도 JPEG로 바꿔 올린다.
- **가로세로 크기**: 서버도 긴 변이 2048px 이하인지 확인한다. 2MB 안에도 픽셀 수가 매우 큰 이미지를 담을 수 있어, 고객 기기가 사진을 열다가 메모리가 부족해질 수 있기 때문이다. 넘으면 `422`이고 `fieldErrors[].path = image`, `code = IMAGE_DIMENSIONS_TOO_LARGE`다. 서버는 파일 헤더의 가로세로를 먼저 확인한 뒤 끝까지 디코딩되는지 확인하며, 디코딩되지 않는 파일은 `415 UNSUPPORTED_IMAGE_TYPE`이다.
- **다시 인코딩**: 서버는 받은 파일을 그대로 공개하지 않는다. 검사를 통과한 사진을 디코딩해 EXIF 방향을 적용하고, 메타데이터(EXIF, XMP, 위치, 촬영 시각, 기기 정보 등)를 모두 뺀 JPEG(품질 약 85)로 다시 저장한다. GPS 좌표 같은 정보가 공개 URL로 새어 나가지 않게 하기 위해서다. PNG도 JPEG로 바뀌며, 투명한 부분은 흰색으로 채운다. PNG는 앱이 아닌 클라이언트를 위해 계속 받는다.
- **썸네일**: 같은 단계에서 긴 변 480px(원본이 더 작으면 원본 크기)의 메타데이터 없는 JPEG 썸네일을 함께 만든다. 목록과 격자 화면은 썸네일(`thumbnailUrl`, `coverThumbnailUrl`)을, 전체 화면과 상세 갤러리는 `imageUrl`을 쓴다.
- 새 사진은 맨 뒤에 붙는다. 업장에 사진이 없었다면 대표 사진이 된다.
- **같은 사진**: 같은 업장에 내용이 같은 파일(업로드한 원본 바이트의 SHA-256이 같음. 다시 인코딩한 파일이 아니다)이 이미 있으면 저장하지 않고 `409 PHOTO_EXISTS`이며, `details.photoId`에 기존 사진 ID를 담는다. 응답을 받지 못해 다시 보낸 요청도 이 오류를 받아 사진이 두 장 생기지 않으므로 `Idempotency-Key`는 받지 않는다.
- 검사 순서: 요청 형식(`422`, `image`가 없으면 `MISSING`) → 업장(`404 BAR_NOT_FOUND`) → 권한(`403`) → 크기(`413 UPLOAD_TOO_LARGE`)와 형식(`415 UNSUPPORTED_IMAGE_TYPE`) → 가로세로(`422 VALIDATION_FAILED`, `fieldErrors[].code = IMAGE_DIMENSIONS_TOO_LARGE`) → 같은 사진(`409 PHOTO_EXISTS`) → 장수(`409 PHOTO_LIMIT_REACHED`). 같은 사진을 장수보다 먼저 확인하므로, 15번째 사진을 올린 요청을 다시 보내도 `PHOTO_EXISTS`를 받는다.
- 두 파일을 저장한 뒤 DB에 기록한다. 하나라도 저장에 실패하거나 DB 기록이 실패하면 저장한 파일을 지운다. 받은 원본 파일은 저장하지 않는다.

`201 Created`, 본문은 `{ "photos": [...] }`다.

```json
{
  "photos": [
    { "photoId": "12121212-1212-4212-8212-121212121211", "imageUrl": "https://bottlemap.o-r.kr/api/bar-photos/12121212-1212-4212-8212-121212121211", "thumbnailUrl": "https://bottlemap.o-r.kr/api/bar-photos/12121212-1212-4212-8212-121212121211/thumbnail" },
    { "photoId": "12121212-1212-4212-8212-121212121212", "imageUrl": "https://bottlemap.o-r.kr/api/bar-photos/12121212-1212-4212-8212-121212121212", "thumbnailUrl": "https://bottlemap.o-r.kr/api/bar-photos/12121212-1212-4212-8212-121212121212/thumbnail" }
  ]
}
```

#### 3.16.3 사진 삭제

```http
DELETE /api/bars/{barId}/photos/{photoId}
Authorization: Bearer <access-token>
```

- 사진을 지우고 뒤의 사진을 한 칸씩 앞으로 당긴다. 되돌리는 API는 없으므로 프론트엔드는 지우기 전에 확인을 받는다.
- 이 업장의 사진이 아니거나 이미 지운 사진, `photoId`가 UUID 형식이 아니면 `404 PHOTO_NOT_FOUND`다. 응답을 받지 못해 다시 보낸 요청도 이 오류를 받으므로, 프론트엔드는 3.6을 다시 불러와 확인한다.
- 저장소의 두 파일(사진과 썸네일)은 DB 커밋 뒤에 지운다. 파일 삭제가 실패하면 로그만 남긴다. 지운 사진의 `imageUrl`과 `thumbnailUrl`은 서버에서 바로 `404`가 되지만, 이미 받아 간 기기나 중간 캐시에는 최대 1일 남을 수 있다(3.16.5).

`200 OK`, 본문은 `{ "photos": [...] }`다.

#### 3.16.4 순서 변경

```http
PUT /api/bars/{barId}/photos/order
Authorization: Bearer <access-token>
Content-Type: application/json
```

```json
{ "photoIds": ["12121212-1212-4212-8212-121212121212", "12121212-1212-4212-8212-121212121211"] }
```

- 업장의 사진 전체를 원하는 순서로 보낸다. 첫 사진이 대표 사진이 된다.
- 같은 ID가 두 번 있으면 `422`이고 `fieldErrors[].code = DUPLICATE_ITEM`이다.
- 보낸 ID의 집합이 현재 사진과 다르면(다른 기기에서 추가하거나 지운 경우) 아무것도 바꾸지 않고 `409 PHOTOS_OUTDATED`다. `details.photos`에 현재 사진 목록(3.6의 `photos`와 같은 형식)을 담는다.
- 같은 요청을 다시 보내도 결과가 같다.

`200 OK`, 본문은 `{ "photos": [...] }`다.

#### 3.16.5 사진 파일 조회

```http
GET /api/bar-photos/{photoId}
GET /api/bar-photos/{photoId}/thumbnail
```

앞의 것은 사진, 뒤의 것은 썸네일(3.16.2)을 돌려준다. 아래 규칙은 둘 다 같다.


- 공개 API이며 인증하지 않는다. `Authorization` 헤더를 보내도 확인하지 않는다.
- 응답 본문은 파일 자체다. 서버가 다시 인코딩해 저장하므로 `Content-Type`은 항상 `image/jpeg`이고, `Cache-Control: public, max-age=86400`(1일)을 붙인다. 같은 `photoId`의 내용은 바뀌지 않으므로 프론트엔드의 이미지 캐시는 URL을 키로 써도 된다. 캐시를 1일로 둔 이유는 지운 사진이 기기와 중간 캐시에 오래 남지 않게 하기 위해서다. 지운 사진은 1일 안에 사라지며, 프론트엔드는 업장 응답의 `photos`에 없는 사진을 캐시에 있어도 보여 주지 않는다.
- 업장 응답의 `photos[].imageUrl`, `photos[].thumbnailUrl`, `coverThumbnailUrl`은 이 경로의 절대 URL이다(예: `https://bottlemap.o-r.kr/api/bar-photos/{photoId}/thumbnail`). 서버가 요청을 받은 주소로 만들므로 에뮬레이터(`10.0.2.2`)와 기기에서도 그대로 열린다. 프론트엔드는 URL을 직접 만들지 않고 응답의 URL을 쓴다.
- 메뉴판 사진의 서명 URL(5.4)과 달리 만료되지 않는다.
- 비활성 업장의 사진도 반환한다. 사진 ID는 업장 응답으로만 알 수 있다.
- 지운 사진이나 없는 `photoId`는 `404 PHOTO_NOT_FOUND`이며 본문은 공통 오류 형식(9.1)이다.

#### 3.16.6 오류와 프론트엔드 처리

| HTTP | code | 발생 조건 | 프론트엔드 처리 |
|---|---|---|---|
| `401` | `UNAUTHENTICATED` | 3.1.5. 사진 파일 조회(3.16.5)에는 없다 | 3.1.5 |
| `403` | `FORBIDDEN` | operator도 해당 업장의 업주도 아님 | 3.1.5 |
| `404` | `BAR_NOT_FOUND` | 업장이 없거나 `barId`가 UUID 형식이 아님 | 업장 목록으로 이동 |
| `404` | `PHOTO_NOT_FOUND` | 지우거나 조회할 사진이 없음. `details.photoId` | 업주 화면은 3.6을 다시 불러와 목록 갱신. 고객 화면은 그 사진 자리에 기본 이미지 |
| `409` | `PHOTO_EXISTS` | 내용이 같은 사진이 이미 있음. `details.photoId` | 이미 등록된 사진이라고 안내하고 3.6을 다시 불러옴. 응답을 받지 못해 다시 보낸 요청이었다면 이미 올라간 것이다 |
| `409` | `PHOTO_LIMIT_REACHED` | 이미 15장. `details.maxPhotos = 15` | 사진을 지운 뒤 추가하라고 안내 |
| `409` | `PHOTOS_OUTDATED` | 순서 변경의 ID 목록이 현재 사진과 다름. `details.photos` | `details.photos`로 화면을 바꾸고 다시 정렬하게 함 |
| `413` | `UPLOAD_TOO_LARGE` | 사진이 2MB를 넘음. `details.maxImageBytes = 2097152` | 품질을 낮춰 다시 압축해 올림 |
| `415` | `UNSUPPORTED_IMAGE_TYPE` | JPEG나 PNG가 아니거나, 선언한 형식과 내용이 다르거나, 끝까지 디코딩되지 않음 | JPEG로 바꿔 다시 올림 |
| `422` | `VALIDATION_FAILED` | `image` 없음, 긴 변이 2048px 초과(`IMAGE_DIMENSIONS_TOO_LARGE`), `photoIds` 형식 오류, `DUPLICATE_ITEM` | `fieldErrors` 표시. `IMAGE_DIMENSIONS_TOO_LARGE`이면 줄여서 다시 올림 |

#### 3.16.7 실제 응답 예시와 호출자별 결과

2.4의 방법으로 받은 응답이다. 사진 삭제(3.16.3)의 성공 응답은 3.16.2와 같은 `{ "photos": [...] }`이며 지운 사진만 빠진다.

이미 지운 사진을 다시 지웠을 때 (`404`). 응답을 받지 못해 다시 보낸 삭제도 이 응답을 받는다.

```json
{"error": {"code": "PHOTO_NOT_FOUND", "message": "사진을 찾을 수 없습니다.", "details": {"photoId": "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaa5"}, "fieldErrors": []}}
```

긴 변이 3000px인 사진을 올렸을 때 (`422`, 3.16.2). 최상위 `code`는 `VALIDATION_FAILED`이고 `IMAGE_DIMENSIONS_TOO_LARGE`는 `fieldErrors[].code`에 있다. 업주 신청 대표 사진(3.11.17)도 같다.

```json
{
  "error": {
    "code": "VALIDATION_FAILED",
    "message": "입력값을 확인해 주세요.",
    "details": null,
    "fieldErrors": [
      {
        "path": "image",
        "code": "IMAGE_DIMENSIONS_TOO_LARGE",
        "message": "사진의 긴 변은 2048px 이하여야 합니다."
      }
    ]
  }
}
```

**호출자별 결과**. 대상은 관악 위스키 바의 사진이며, 호출자마다 새 사진을 하나 올린 뒤 지웠다.

| API | 비로그인 | customer | 다른 업장의 업주 | 해당 업장의 업주 | operator |
|---|---|---|---|---|---|
| `DELETE /api/bars/{barId}/photos/{photoId}` | `401` | `403` | `403` | `200` | `200` |

### 3.17 요즘 많이 찾는 위스키

고객 홈 화면의 "요즘 많이 찾는 위스키" 카드에 쓸 상품 목록을 반환한다. 순위는 고객 검색(3.10)의 검색 집계(3.10.6)로 정한다.

```http
GET /api/search/popular-products?limit=10
```

로그인 없이 호출할 수 있는 공개 API이며, 다른 검색 API처럼 `Authorization` 헤더를 읽지 않는다(3.1.5). 결과는 호출자와 관계없이 같다.

| Query | 필수 | 기본값 | 설명 |
|---|---|---|---|
| `limit` | 아니오 | `10` | 반환할 상품의 최대 개수. 1~20 |

#### 3.17.1 홈 화면 구성

고객 홈 화면은 위에서부터 다음으로 구성한다.

| 영역 | 내용 | 데이터 |
|---|---|---|
| 검색창 | 위스키 이름 입력. 검색하면 3.10 결과 화면으로 간다 | 3.10 |
| 최근 검색 | 이 기기에서 검색한 검색어 | 최근 검색 목록은 앱이 기기에만 저장하며 서버로 보내지 않는다. 누르면 그 검색어로 3.10을 `source=recent`로 호출하고, 이 검색은 다른 검색처럼 3.10.6의 집계에만 들어간다 |
| 요즘 많이 찾는 위스키 | 카드마다 상품명과 "바 N곳". 최대 10개를 가로로 넘겨 본다 | 이 API(`limit = 10`) |
| 지도로 보기 | 지도 화면으로 간다 | 3.13 |

- 카드를 누르면 앱은 3.10을 `productId`와 `source=popular`로 호출한다(`query`는 보내지 않는다). 결과에는 그 상품을 파는 업장만 나온다. 상품명으로 검색하면 상품명이 브랜드 별칭이기도 한 경우 브랜드 전체가 나오므로 `productId`를 쓴다(3.10.1). 검색창에서 직접 검색할 때는 `source`를 보내지 않거나 `input`으로 보낸다.
- `items = []`이면 "요즘 많이 찾는 위스키" 영역을 숨긴다. 이 API가 실패해도 홈 화면의 다른 영역은 그대로 보여 주고, 이 영역만 숨기거나 재시도 버튼을 보여 준다.

#### 3.17.2 순위 기준

서버는 요청을 받을 때마다 다음 순서로 상품을 고른다.

1. **후보**: 활성 상품 중 "바 N곳"(`barCount`)이 1 이상인 상품만 후보다. 판매 업장이 0곳인 상품은 눌러도 결과가 없으므로 보여 주지 않는다.
2. **검색 수**: 최근 30일(오늘을 포함한 서울 날짜 30일)의 상품별 검색 수(3.10.6)를 더한다. 집계는 상품 하나로 해석된 검색만 세므로 브랜드 검색이나 부분 일치로 여러 상품이 함께 올라가지 않는다. 검색 출처(`source`)는 지금은 구분하지 않고 `input`, `recent`, `popular`를 모두 더한다. 카드를 누른 검색(`popular`)도 세므로 위에 보이는 상품이 계속 위에 남기 쉽다. 이 효과가 커지면 집계는 그대로 두고 `popular`를 빼고 더하도록 이 기준만 바꾼다.
3. **인기 상품**: 검색 수가 3 이상인 후보를 검색 수 내림차순으로 놓는다. 동점이면 `barCount` 내림차순, `displayName` 오름차순, `productId` 오름차순이다. 1~2번 검색된 상품이 상위에 뜨지 않게 하려고 3번 이상으로 정했다.
4. **대체 기준**: 3의 상품이 `limit`보다 적으면, 아직 넣지 않은 후보를 `barCount` 내림차순, `displayName` 오름차순, `productId` 오름차순으로 채운다. 검색 수가 적은 서비스 초기에도 카드가 비지 않게 하기 위해서다.
5. 앞에서부터 `limit`개를 반환한다.

`barCount`는 고객 검색(3.10.2)에 그 상품의 결과로 나오는 업장 수와 같다. 활성 업장이고, 그 상품이 업장의 현재 메뉴판에 있고, 품절(3.14.8)이 아닌 업장만 센다. 그래서 카드를 눌러 3.10을 `productId`로 검색하면 "바 N곳"과 같은 수의 업장이 나온다. 다만 3.10은 `limit`까지만 반환하므로 `barCount`가 `limit`보다 크면 결과가 잘리고 `truncated = true`다. 이 API의 응답을 받은 뒤 품절이나 메뉴판이 바뀌어도 달라질 수 있다.

홈 화면의 카드를 눌러 한 검색(3.17.1)도 다른 검색과 똑같이 집계되고 순위에 들어간다. 카드를 고른 것도 그 상품에 대한 관심으로 본다.

같은 사람이 여러 번 검색해도 따로 거르지 않는다. 검색 집계에 사용자나 기기를 남기지 않으므로 구분할 수 없기 때문이다.

#### 3.17.3 응답

`200 OK`

```json
{
  "items": [
    {
      "productId": "44444444-4444-4444-8444-444444444444",
      "displayName": "Glenfiddich 12",
      "brandName": "Glenfiddich",
      "ageYears": 12,
      "editionName": null,
      "barCount": 7
    },
    {
      "productId": "bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbb1",
      "displayName": "Deanston 12",
      "brandName": "Deanston",
      "ageYears": 12,
      "editionName": null,
      "barCount": 2
    }
  ]
}
```

| 필드 | 타입 | null 가능 | 설명 |
|---|---|---|---|
| `items` | 배열 | 아니오 | 순위대로 정렬한 상품. 최대 `limit`개. 판매 업장이 있는 상품이 하나도 없으면 `[]` |
| `items[].productId` | UUID 문자열 | 아니오 | |
| `items[].displayName` | 문자열 | 아니오 | 정규 상품명(`products.display_name`). 카드의 상품명이다. 카드를 누르면 `productId`로 3.10을 검색한다 |
| `items[].brandName` | 문자열 | 아니오 | 브랜드 대표명(`brands.canonical_name`) |
| `items[].ageYears` | 정수 | 예 | 숙성 연수. 표기가 없는 상품은 `null` |
| `items[].editionName` | 문자열 | 예 | 에디션명. 없으면 `null` |
| `items[].barCount` | 정수 | 아니오 | 지금 이 상품을 파는 업장 수(3.17.2). 1 이상. 카드에 "바 N곳"으로 표시한다 |

- 검색 수는 응답에 넣지 않는다. 운영 정보이고, 숫자를 보여 주면 순위를 올리려고 검색을 반복할 동기가 생기기 때문이다.
- 응답에는 `Cache-Control: public, max-age=600`(10분)을 붙인다. 순위는 천천히 바뀌므로 앱은 10분 안에 홈 화면으로 돌아오면 다시 받지 않아도 된다.

#### 3.17.4 오류와 프론트엔드 처리

| HTTP | code | 발생 조건 | 프론트엔드 처리 |
|---|---|---|---|
| `422` | `VALIDATION_FAILED` | `limit`이 1~20 밖(`GREATER_THAN_EQUAL`, `LESS_THAN_EQUAL`)이거나 정수가 아님(`INT_PARSING`) | 앱 버그. 이 영역을 숨긴다 |
| 네트워크 오류, `5xx` | | | 이 영역만 숨기거나 재시도 버튼을 보여 준다. 홈 화면의 다른 영역은 그대로 쓴다 |

이 API는 공개 API이므로 `401`과 `403`을 반환하지 않는다.

### 3.18 운영자 메뉴 항목 확인

운영자가 확인해야 할 메뉴 항목을 한 목록에 모으고, 운영자가 각 항목을 상품에 연결하거나 지금 연결이 맞다고 확인하는 API다. operator만 호출할 수 있다. 관리자 웹(`/admin/`)이 이 API로 확인 대기 화면을 보여 준다.

| 메서드 | 경로 | 용도 |
|---|---|---|
| `GET` | `/api/menu-item-checks` | 확인 목록 조회 (3.18.2) |
| `POST` | `/api/menu-item-checks/{checkId}/resolve` | 확인 처리 (3.18.3) |

#### 3.18.1 확인이 생기는 경우

확인 하나는 메뉴 항목 하나(`barMenuItemId`)에 대한 것이다. 한 항목에 열린 확인(`status = open`)은 최대 하나이며, 새 사유가 생기면 열린 확인에 사유를 더한다.

| 사유 (`reasons[]`) | 항목 상태 | 고객 검색 | 생기는 때 |
|---|---|---|---|
| `unlinked` | 상품 없는 위스키 | 나오지 않는다 | 상품 없이 게시(8.10)하거나 상품 없이 직접 추가(3.14.3)한 `kind = whisky` 항목 |
| `relinked_by_name` | 업주가 이름을 고쳐 다시 매칭한 결과 다른 상품에 연결됨. 상품 없던 항목이 연결된 경우도 같다 | 나온다 | 검수 제출(8.11), 직접 수정(3.14.4) |
| `unlinked_by_name` | 업주가 이름을 고쳐 다시 매칭한 결과 연결이 풀림 | 나오지 않는다 | 검수 제출(8.11), 직접 수정(3.14.4) |
| `attribute_conflict` | 고른 상품의 연수나 에디션이 사진에서 읽은 값과 다름 | 나온다 | 검수 제출(8.7) |
| `price_conflict` | 다시 매칭으로 같은 상품의 줄이 여럿이 되거나, 상품 없는 줄이 같은 이름 키로 합쳐져 같은 용량의 가격이 부딪침. 서버가 한 가격을 골랐다 | 상품이 있으면 나온다 | 검수 제출(8.11, 8.12), 직접 수정의 다시 매칭(3.14.1, 3.14.4) |

- 현재 메뉴판에 있는 상품 없는 위스키 항목에는 항상 `unlinked` 또는 `unlinked_by_name` 사유의 열린 확인이 있다. 검수 반영이나 직접 추가로 그런 항목이 생기거나, 위스키가 아닌 메뉴가 다음 검수에서 `kind = whisky`로 바뀌면 같은 트랜잭션에서 확인을 만든다.
- `kind = other`인 항목에는 확인을 만들지 않는다.
- 항목이 현재 메뉴판에서 빠지면(검수의 `remove`, 3.14.5 삭제, 3.14.6 초기화) 그 항목의 열린 확인은 같은 트랜잭션에서 `dismissed`가 된다.
- 확인의 출처(`source`)는 사유를 만든 검수 줄이다. 검수 제출로 사유를 더할 때는 출처도 그 줄로 바꾼다. 직접 추가(3.14.3)로 생긴 확인은 출처가 `null`이다. 직접 수정(3.14.4)으로 사유를 더할 때는 출처를 바꾸지 않는다(없으면 `null`로 둔다). 운영자가 처음 게시된 메뉴판 사진의 그 줄을 계속 볼 수 있게 하기 위해서다.
- 이름을 고쳐 메뉴판의 줄이 다른 항목으로 옮겨 가면(3.14.1의 연결 바꾸기, 8.11의 원래 항목 대신하기) 그 줄의 열린 확인은 `dismissed`가 되지 않고 새 항목으로 옮겨 간다.

#### 3.18.2 확인 목록 조회

```http
GET /api/menu-item-checks?status=open&barId=22222222-2222-4222-8222-222222222222&limit=100
Authorization: Bearer <access-token>
```

| 쿼리 | 필수 | 규칙 |
|---|---|---|
| `status` | 아니오 | `open`, `resolved`, `dismissed` 중 하나. 기본 `open` |
| `barId` | 아니오 | 이 업장의 확인만. 없으면 모든 업장 |
| `limit` | 아니오 | 1~200. 기본 100. 넘치면 `truncated = true` |

정렬: `open`은 `createdAt` 오름차순(오래된 확인부터 처리한다), `resolved`와 `dismissed`는 `resolvedAt` 내림차순. 동점이면 `checkId` 오름차순이다.

`200 OK`

```json
{
  "items": [
    {
      "checkId": "c0c0c0c0-c0c0-4c0c-8c0c-c0c0c0c0c0c1",
      "status": "open",
      "reasons": ["unlinked"],
      "createdAt": "2026-11-13T09:15:00Z",
      "resolvedAt": null,
      "resolution": null,
      "resolvedProductId": null,
      "bar": {
        "barId": "22222222-2222-4222-8222-222222222222",
        "name": "관악 위스키 바",
        "status": "active"
      },
      "item": {
        "barMenuItemId": "99999999-9999-4999-8999-999999999993",
        "kind": "whisky",
        "displayName": "글렌알라키 10년 CS 배치 11",
        "onBoard": true,
        "soldOut": false,
        "product": null,
        "options": [
          { "optionLabel": null, "pourMl": 30, "priceKrw": 26000 }
        ]
      },
      "source": {
        "menuImportId": "77777777-7777-4777-8777-777777777777",
        "extractedItemId": "10000000-0000-4000-8000-000000000004",
        "rawText": "글렌알라키 10 CS batch 11 30ml 26,000",
        "sourceBox": [62, 418, 931, 447],
        "imageUrl": "https://cdn.example.com/signed/menu-image-001",
        "imageUrlExpiresAt": "2026-11-13T09:45:00Z",
        "extractedProductName": "글렌알라키 10 CS batch 11",
        "extractedBrandName": "글렌알라키",
        "extractedAgeYears": 10,
        "extractedEditionName": "Cask Strength Batch 11"
      }
    }
  ],
  "truncated": false
}
```

| 필드 | 타입 | null 가능 | 설명 |
|---|---|---|---|
| `checkId` | UUID 문자열 | 아니오 | |
| `status` | 문자열 | 아니오 | `open`(처리 전), `resolved`(운영자가 처리함), `dismissed`(항목이 메뉴판에서 빠져 닫힘) |
| `reasons` | 문자열 배열 | 아니오 | 3.18.1의 사유. 생긴 순서이며 최소 1개 |
| `createdAt` | RFC 3339 문자열 | 아니오 | 확인이 처음 생긴 시각 |
| `resolvedAt` | RFC 3339 문자열 | 예 | `resolved` 또는 `dismissed`가 된 시각 |
| `resolution` | 문자열 | 예 | `resolved`일 때 처리 방식(3.18.3의 `resolution`) |
| `resolvedProductId` | UUID 문자열 | 예 | 처리한 결과 연결된 상품. `link_existing`, `create_and_link`, `keep`일 때 값이 있다 |
| `bar.barId`, `bar.name`, `bar.status` | | 아니오 | 업장. 비활성 업장의 확인도 목록에 나오지만 처리할 수 없다(3.18.3) |
| `item.barMenuItemId` | UUID 문자열 | 아니오 | 확인 대상 항목 |
| `item.kind` | `MenuItemKind` | 아니오 | 2.3 |
| `item.displayName` | 문자열 | 아니오 | 메뉴판에 보이는 이름. 메뉴판에서 빠진 항목이면 마지막으로 보였던 이름 |
| `item.onBoard` | 불리언 | 아니오 | 지금 현재 메뉴판에 있는지 |
| `item.soldOut` | 불리언 | 아니오 | 3.14.8 |
| `item.product` | 객체 | 예 | 지금 연결된 상품. 7.2의 `productId`, `displayName`, `brandId`, `brandName`, `category`, `ageYears`, `editionName`과 같다. 연결되지 않았으면 `null` |
| `item.options` | 배열 | 아니오 | 지금 메뉴판의 옵션(3.9의 `optionLabel`, `pourMl`, `priceKrw`). 메뉴판에 없으면 `[]` |
| `source` | 객체 | 예 | 사유를 만든 검수 줄. 직접 추가로 생긴 확인이면 `null` |
| `source.rawText`, `source.sourceBox` | | `sourceBox`만 예 | 5.4와 같다. 관리자 웹은 `imageUrl`에서 `sourceBox` 영역을 잘라 보여 준다 |
| `source.imageUrl`, `source.imageUrlExpiresAt` | | `imageUrlExpiresAt`만 예 | 그 줄이 있는 메뉴판 사진. 5.4와 같은 서명 URL이며, 만료되면 목록을 다시 조회한다 |
| `source.extractedProductName`, `extractedBrandName`, `extractedAgeYears`, `extractedEditionName` | | 예 | 5.4와 같은 추출값 |
| `truncated` | 불리언 | 아니오 | `limit` 때문에 잘렸으면 `true` |

오류: `401`(3.1.5), `403 FORBIDDEN`(operator가 아님), `422 VALIDATION_FAILED`(`status`가 허용 값이 아님, `barId`가 UUID 형식이 아님, `limit` 범위 밖). 없는 `barId`는 오류 없이 `items = []`다.

#### 3.18.3 확인 처리

```http
POST /api/menu-item-checks/{checkId}/resolve
Authorization: Bearer <access-token>
Content-Type: application/json
```

기존 상품에 연결할 때. 메뉴판 표기를 별칭으로 함께 넣으면 다음부터 같은 표기가 자동으로 확정된다:

```json
{
  "resolution": "link_existing",
  "productId": "44444444-4444-4444-8444-444444444445",
  "aliasesToAdd": [
    { "aliasText": "글렌알라키 10년 CS 배치 11", "languageCode": "ko", "isSearchable": true }
  ]
}
```

카탈로그에 새로 등록해 연결할 때:

```json
{
  "resolution": "create_and_link",
  "brand": { "type": "existing", "brandId": "dddddddd-dddd-4ddd-8ddd-ddddddddddd3" },
  "product": {
    "category": "whisky",
    "displayName": "GlenAllachie 10 Cask Strength Batch 11",
    "ageYears": 10,
    "editionName": "Cask Strength Batch 11",
    "abv": 58.2
  },
  "aliases": [
    { "aliasText": "글렌알라키 10년 CS 배치 11", "languageCode": "ko", "isSearchable": true }
  ]
}
```

지금 연결이 맞을 때 `{"resolution": "keep"}`, 위스키가 아닌 메뉴일 때 `{"resolution": "mark_as_other"}`를 보낸다.

| `resolution` | 하는 일 | 필드 | 쓸 수 있는 항목 |
|---|---|---|---|
| `link_existing` | 기존 상품에 연결하거나 연결을 바꾼다 | `productId` 필수. `aliasesToAdd` 선택(8.1의 `select_existing_product`와 같은 형식) | 모든 확인 |
| `create_and_link` | 새 상품(필요하면 새 브랜드)을 만들어 연결한다 | `brand`, `product` 필수. `aliases` 선택(8.1의 `create_product`와 같은 형식) | 모든 확인 |
| `keep` | 지금 연결이 맞다고 확인만 한다 | 없음 | 상품에 연결된 항목 |
| `mark_as_other` | 위스키가 아닌 메뉴로 바꾼다(`kind = other`) | 없음 | 상품 없는 항목 |

- 정의하지 않은 필드는 받지 않는다(`EXTRA_FORBIDDEN`).
- `aliasesToAdd`와 `aliases`는 운영자가 그 표기가 이 상품의 정상 표기임을 확인했을 때 보낸다(8.2와 같다). 메뉴판의 오타처럼 손님 검색에는 쓰지 않을 표기는 `isSearchable = false`로 넣는다. 관리자 웹은 연결할 때 메뉴판 이름(`item.displayName`)을 별칭 입력 칸에 미리 채워 둔다.
- 쓸 수 없는 항목에 `keep`이나 `mark_as_other`를 보내면 `422`이고 `fieldErrors[].path = resolution`, `code = RESOLUTION_NOT_ALLOWED`다.

반영 규칙:

- 메뉴를 바꾸는 다른 요청처럼 업장 행을 먼저 잠그고 처리한다(3.14.1). 업장이 비활성이면 `404 BAR_NOT_FOUND`다.
- 업장에 미완료 메뉴 등록 작업이 있으면 아무것도 바꾸지 않고 `409 ACTIVE_IMPORT_EXISTS`(`details.menuImportId`, `details.status`)다. 검수 중인 메뉴판의 항목이 바뀌면 업주의 검수가 오래된 메뉴판을 보고 결정하게 되기 때문이다. 관리자 웹은 이 확인을 건너뛰고 작업이 끝난 뒤 다시 처리한다.
- 확인이 `open`이 아니면 `409 INVALID_CHECK_STATE`(`details.checkId`, `details.status`)다. 같은 요청을 다시 보낸 경우도 같으며, 관리자 웹은 목록을 다시 조회한다.
- **연결** (`link_existing`, `create_and_link`): 3.14.1의 연결 바꾸기 규칙으로 항목의 줄을 그 상품에 연결한다. 이름, 위치, 옵션, 품절 상태는 그대로이며, 예전에 판매했던 상품이면 그때의 항목으로 옮기고, 이미 메뉴판에 있는 상품이면 두 줄을 합친다. 연결한 순간부터 고객 검색(3.10)과 인기 위스키(3.17)에 나온다. 확인은 처리한 뒤 닫히므로 원래 항목(`item.barMenuItemId`)을 가리킨 채 남는다.
  - 지금 연결된 상품과 같은 상품을 보내면 `keep`과 같다. `aliasesToAdd`는 그대로 저장한다.
  - `create_and_link`의 중복 검사는 검수의 신규 생성(8.5, 8.6)과 같다. 같은 브랜드나 상품이 있으면 아무것도 만들지 않고 `409 DUPLICATE_BRAND_FOUND` 또는 `409 DUPLICATE_PRODUCT_FOUND`다. `details`는 9.5와 같되 `extractedItemId`와 `reviewUrl`이 없다. 만든 상품과 브랜드에는 요청한 operator를 기록한다.
- **`keep`**: 메뉴는 바꾸지 않는다.
- **`mark_as_other`**: 항목의 `kind`를 `other`로 바꾼다. 상품 검색에는 계속 나오지 않는다.
- 메뉴판의 항목이 바뀌는 처리(연결, `mark_as_other`)는 메뉴판 버전(`menuVersion`)을 1 올린다. 업주가 열어 둔 직접 편집이 바뀐 항목을 보고 다시 판단하게 하기 위해서다. 고객에게 보이는 이름과 가격은 바뀌지 않으므로 `publishedAt`은 바꾸지 않는다. `keep`과 별칭만 더하는 처리는 버전을 올리지 않는다.
- 처리가 끝나면 확인은 `resolved`가 되고, 처리 방식, 결과 상품, 처리한 사용자와 시각을 기록한다. 요청 하나는 하나의 트랜잭션이며 실패하면 아무것도 바뀌지 않는다.
- 검사 순서: 인증(`401`) → operator(`403`) → 요청 형식(`422`) → 확인(`404 MENU_ITEM_CHECK_NOT_FOUND`) → 업장 행 잠금 → 업장 상태(`404 BAR_NOT_FOUND`) → 미완료 작업(`409 ACTIVE_IMPORT_EXISTS`) → 확인 상태(`409 INVALID_CHECK_STATE`) → 처리 방식과 항목(`422 RESOLUTION_NOT_ALLOWED`) → 상품과 브랜드(`422 PRODUCT_NOT_FOUND`, `PRODUCT_INACTIVE`, `BRAND_NOT_FOUND`, `409 DUPLICATE_*`).

`200 OK`, 본문은 처리한 확인 하나다(3.18.2의 `items[]` 한 개와 같은 형식).

| HTTP | code | 발생 조건 | 관리자 웹 처리 |
|---|---|---|---|
| `401` | `UNAUTHENTICATED` | 3.1.5 | 다시 로그인 |
| `403` | `FORBIDDEN` | operator가 아님 | 접근 차단 |
| `404` | `MENU_ITEM_CHECK_NOT_FOUND` | 확인이 없거나 `checkId`가 UUID 형식이 아님. `details.checkId` | 목록 다시 조회 |
| `404` | `BAR_NOT_FOUND` | 업장이 비활성 | 안내. 업장을 다시 활성화하기 전에는 처리하지 않음 |
| `409` | `ACTIVE_IMPORT_EXISTS` | 업장에 미완료 메뉴 등록 작업이 있음 | 작업이 끝난 뒤 다시 처리하라고 안내 |
| `409` | `INVALID_CHECK_STATE` | 확인이 이미 `resolved` 또는 `dismissed` | 목록 다시 조회 |
| `409` | `DUPLICATE_BRAND_FOUND`, `DUPLICATE_PRODUCT_FOUND` | 새 브랜드나 상품, 또는 별칭이 기존 것과 겹침(9.5) | 기존 브랜드나 상품을 보여 주고 `link_existing`이나 기존 브랜드로 다시 처리 |
| `422` | `VALIDATION_FAILED` | 필드 규칙 위반, `RESOLUTION_NOT_ALLOWED`, `NOT_NORMALIZABLE`, `PRODUCT_NOT_FOUND`, `PRODUCT_INACTIVE`, `BRAND_NOT_FOUND` | `fieldErrors` 표시 |
| `503` | `TEMPORARY_WRITE_CONFLICT` | 직렬화 충돌 3회 재시도 실패 | 잠시 후 같은 요청 재시도 |

## 4. 메뉴 등록 요청

### 4.1 요청

```http
POST /api/bars/{barId}/menu-imports
Authorization: Bearer <access-token>
Idempotency-Key: <client-generated-uuid>
Content-Type: multipart/form-data
```

multipart 필드:

| 필드 | 타입 | 필수 | 설명 |
|---|---|---|---|
| `mode` | `ImportMode` | 예 | 전체 교체 또는 일부 수정 |
| `ownerNote` | 문자열 | 아니오 | 촬영 출처나 작업 메모. 1000자 이하. 공백뿐이면 `null`로 저장 |
| `images` | 이미지 파일 배열 | 예 | 표시 순서대로 전송한 메뉴 사진 |

`Idempotency-Key` 헤더는 필수이며 1~255자다. 프론트엔드는 업로드를 시작할 때마다 새 UUID를 만들고, 같은 업로드를 재시도할 때만 같은 값을 다시 보낸다.

operator와 해당 업장의 현재 업주가 호출할 수 있다.

예시:

```text
mode       = full_replace
ownerNote  = 2026년 10월 메뉴판
images     = [menu-page-1.jpg, menu-page-2.jpg]
```

MVP 업로드 제한:

```text
허용 형식       JPEG, PNG
사진 최대 개수  15장
사진당 최대 크기 10MB
전체 최대 크기  60MB
```

업주 신청의 메뉴판 사진(3.11.15)에도 같은 제한을 쓴다. 안드로이드 앱은 전체 크기가 넘으면 사진을 다시 압축해 올린다. 사진이 많을수록 AI 처리가 오래 걸린다(사진을 한 장씩 차례로 처리한다).

파일 형식은 확장자가 아니라 파일 내용으로 판별하며, 선언한 MIME 형식과 다르면 거절한다(`415 UNSUPPORTED_IMAGE_TYPE`). AI 추출 모듈이 JPEG와 PNG만 모델에 보내므로 HEIC 같은 다른 형식은 받지 않는다. 안드로이드 앱은 다른 형식의 사진을 JPEG로 바꿔 올린다.

배열 순서가 `imageOrder`가 된다. 프론트엔드는 업로드 재시도 시 파일 순서를 바꾸지 않아야 한다.

### 4.2 성공 응답

AI 결과를 기다리지 않고 작업 생성 직후 반환한다.

```http
HTTP/1.1 202 Accepted
Location: /api/menu-imports/77777777-7777-4777-8777-777777777777
Retry-After: 3
```

```json
{
  "menuImportId": "77777777-7777-4777-8777-777777777777",
  "status": "processing",
  "imageCount": 2,
  "statusUrl": "/api/menu-imports/77777777-7777-4777-8777-777777777777",
  "pollAfterMs": 3000
}
```

프론트엔드는 `statusUrl`을 2~3초 간격으로 polling한다.

### 4.3 멱등성

백엔드는 다음 내용을 정규 형식으로 조합해 `requestFingerprint`를 계산한다.

```text
barId
mode
ownerNote
이미지 순서
각 이미지 원본 바이트의 SHA-256
```

처리 규칙:

```text
같은 Idempotency-Key + 같은 requestFingerprint
→ 새 작업을 만들지 않고 기존 menuImport 응답 반환

같은 Idempotency-Key + 다른 requestFingerprint
→ 409 IDEMPOTENCY_KEY_REUSED

다른 Idempotency-Key + 같은 requestFingerprint
→ 별개의 명시적 등록 요청으로 허용
```

한 업장에는 `uploaded`, `processing`, `ready_for_review` 상태의 미완료 작업을 하나만 허용한다. 미완료 작업을 끝내지 않고 새로 올리려면 먼저 그 작업을 취소한다(5.7).

### 4.4 오류와 프론트엔드 처리

| HTTP | code | 발생 조건 | 프론트엔드 처리 |
|---|---|---|---|
| `401` | `UNAUTHENTICATED` | 3.1.5 | 3.1.5 |
| `403` | `FORBIDDEN` | operator도 해당 업장의 업주도 아님 | 3.1.5 |
| `404` | `BAR_NOT_FOUND` | 업장이 없음, `barId`가 UUID 형식이 아님, 비활성 업장 | 업장 목록으로 이동 |
| `409` | `IDEMPOTENCY_KEY_REUSED` | 같은 `Idempotency-Key`로 다른 내용을 보냄. `details.menuImportId`에 그 키로 만든 작업 ID | 새 키로 다시 요청 |
| `409` | `ACTIVE_IMPORT_EXISTS` | 업장에 미완료 작업이 있음. `details.menuImportId`와 `details.status`에 그 작업의 ID와 상태 | 기존 작업으로 이동(`GET /api/menu-imports/{details.menuImportId}`). 새로 올리려면 기존 작업을 취소(5.7)한 뒤 다시 업로드 |
| `413` | `UPLOAD_TOO_LARGE` | 사진 개수, 한 장 크기 또는 전체 크기 초과. `details.maxImages`, `details.maxImageBytes`, `details.maxTotalBytes`에 제한값 | 사진 수를 줄이거나 다시 압축 |
| `415` | `UNSUPPORTED_IMAGE_TYPE` | JPEG·PNG가 아니거나 선언한 형식과 내용이 다름. `details.imageOrder`에 해당 사진 순서 | 해당 사진을 JPEG로 바꿔 다시 업로드 |
| `422` | `VALIDATION_FAILED` | `Idempotency-Key`, `mode`, `images` 누락(`MISSING`), 허용하지 않는 `mode`, `ownerNote` 1000자 초과 | `fieldErrors` 표시 |

같은 키와 같은 내용의 재요청은 오류가 아니라 기존 작업의 `202` 응답을 다시 받는다(4.3).

## 5. 메뉴 등록 상태와 통합 검수 조회

### 5.1 요청

```http
GET /api/menu-imports/{menuImportId}
Authorization: Bearer <access-token>
```

operator와 작업 대상 업장의 현재 업주가 호출할 수 있다. 이 API는 상태에 따라 응답 본문이 달라진다.

| `status` | 응답 | 프론트엔드 처리 |
|---|---|---|
| `uploaded`, `processing` | 5.2 | `pollAfterMs` 뒤 다시 조회 |
| `failed` | 5.3 | polling 중단, 새 업로드 안내 |
| `ready_for_review` | 5.4 | polling 중단, 통합 검수 화면 |
| `applied` | 5.5 | polling 중단, 반영 완료 화면 |
| `canceled` | 5.6 | polling 중단, 취소됨 안내 |

| HTTP | code | 발생 조건 | 프론트엔드 처리 |
|---|---|---|---|
| `401` | `UNAUTHENTICATED` | 3.1.5 | 3.1.5 |
| `403` | `FORBIDDEN` | operator도 작업 대상 업장의 업주도 아님 | 3.1.5 |
| `404` | `MENU_IMPORT_NOT_FOUND` | 작업이 없거나 `menuImportId`가 UUID 형식이 아님 | 작업 목록(3.8)으로 이동 |

### 5.2 처리 중 응답

```json
{
  "menuImportId": "77777777-7777-4777-8777-777777777777",
  "status": "processing",
  "progress": {
    "totalImages": 2,
    "completedImages": 1,
    "failedImages": 0
  },
  "pollAfterMs": 3000
}
```

`uploaded`와 `processing`은 같은 형식이다. `status`만 다르다.

`completedImages`는 AI 호출, 응답 검증과 추출 저장까지 성공한 이미지 수다. 후보 생성과 임시 diff는 모든 이미지의 추출이 끝난 뒤 한 번에 만들므로, 모든 이미지가 완료돼도 잠시 `processing` 상태일 수 있다. 프론트엔드는 이 숫자를 정확한 전체 처리율로 간주하지 않고 진행 안내에만 사용한다.

### 5.3 실패 응답

HTTP 요청 자체는 성공했지만 비동기 작업이 최종 실패한 경우 `200 OK`와 `status = failed`를 반환한다.

```json
{
  "menuImportId": "77777777-7777-4777-8777-777777777777",
  "status": "failed",
  "progress": {
    "totalImages": 2,
    "completedImages": 1,
    "failedImages": 1
  },
  "failure": {
    "code": "IMAGE_EXTRACTION_FAILED",
    "message": "일부 메뉴 이미지를 처리하지 못했습니다."
  }
}
```

`failure.code`는 두 가지다.

| code | 발생 조건 |
|---|---|
| `IMAGE_EXTRACTION_FAILED` | 한 장 이상의 사진에서 메뉴 추출이 재시도 후에도 실패함. `progress.failedImages`가 1 이상이다 |
| `PROCESSING_FAILED` | 특정 사진의 문제가 아니라 추출 뒤 매칭·초안 생성 단계나 서버 내부 오류로 처리가 중단됨. 이때 `progress.failedImages`는 `0`일 수 있다 |

두 경우 모두 같은 작업을 다시 처리하지 않으므로, 프론트엔드는 `failure.message`를 보여 주고 새 업로드를 안내한다.

프론트엔드에는 공급자 원본 오류나 `extraction_runs.raw_output`을 직접 노출하지 않는다.

### 5.4 통합 검수 응답

`status = ready_for_review`이면 상태와 검수 데이터를 한 응답으로 반환한다.

```json
{
  "menuImportId": "77777777-7777-4777-8777-777777777777",
  "barId": "22222222-2222-4222-8222-222222222222",
  "mode": "full_replace",
  "status": "ready_for_review",
  "reviewVersion": 3,
  "images": [
    {
      "imageId": "eeeeeeee-eeee-4eee-8eee-eeeeeeeeeee1",
      "imageOrder": 1,
      "imageUrl": "https://cdn.example.com/signed/menu-image-001",
      "imageUrlExpiresAt": "2026-10-04T09:30:00Z",
      "items": [
        {
          "extractedItemId": "10000000-0000-4000-8000-000000000007",
          "itemOrder": 7,
          "rawText": "딘스톤 12년 15ml 8.0 / 30ml 15.0",
          "sourceBox": [62, 418, 931, 447],
          "extractedLineType": "product",
          "extractedKind": "whisky",
          "correctedLineType": null,
          "effectiveLineType": "product",
          "initialResolutionStatus": "exact_match",
          "extractedProductName": "딘스톤 12년",
          "extractedBrandName": "딘스톤",
          "extractedAgeYears": 12,
          "extractedEditionName": null,
          "extractedAbv": null,
          "extractionConfidence": 0.92,
          "proposedProductId": "bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbb1",
          "options": [
            {
              "extractedOptionId": "20000000-0000-4000-8000-000000000001",
              "optionOrder": 1,
              "extractedOptionLabel": null,
              "extractedPourMl": 15,
              "extractedPriceKrw": 8000
            },
            {
              "extractedOptionId": "20000000-0000-4000-8000-000000000002",
              "optionOrder": 2,
              "extractedOptionLabel": null,
              "extractedPourMl": 30,
              "extractedPriceKrw": 15000
            }
          ],
          "candidates": [
            {
              "productId": "bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbb1",
              "candidateRank": 1,
              "displayName": "Deanston 12",
              "brandId": "dddddddd-dddd-4ddd-8ddd-ddddddddddd1",
              "brandName": "Deanston",
              "category": "whisky",
              "ageYears": 12,
              "editionName": null,
              "abv": 46.3,
              "matchMethod": "alias",
              "score": 1.0,
              "evidence": {
                "aliasExact": true,
                "brandExact": true,
                "ageExact": true
              }
            }
          ],
          "newProductDraft": {
            "brandText": "딘스톤",
            "category": "whisky",
            "displayName": "딘스톤 12년",
            "ageYears": 12,
            "editionName": null,
            "abv": null
          }
        }
      ]
    }
  ],
  "reviewDraft": {
    "draftVersion": 3,
    "reviewVersion": 3,
    "savedAt": "2026-10-04T09:05:00Z",
    "content": {
      "itemDecisions": [
        {
          "extractedItemId": "10000000-0000-4000-8000-000000000007",
          "finalLineType": "product",
          "action": "select_existing_product",
          "productId": "bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbb1"
        }
      ],
      "changeDecisions": [],
      "clientState": { "expandedItemIds": ["10000000-0000-4000-8000-000000000007"] }
    }
  },
  "proposedChanges": [
    {
      "changeId": "30000000-0000-4000-8000-000000000001",
      "changeType": "add",
      "barMenuItemId": null,
      "extractedItemId": "10000000-0000-4000-8000-000000000007",
      "extractedItemIds": ["10000000-0000-4000-8000-000000000007"],
      "before": null,
      "after": {
        "productId": "bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbb1",
        "kind": "whisky",
        "displayName": "Deanston 12",
        "options": [
          {
            "extractedOptionId": "20000000-0000-4000-8000-000000000001",
            "optionLabel": null,
            "pourMl": 15,
            "priceKrw": 8000
          },
          {
            "extractedOptionId": "20000000-0000-4000-8000-000000000002",
            "optionLabel": null,
            "pourMl": 30,
            "priceKrw": 15000
          }
        ]
      },
      "summary": "Deanston 12와 2개 가격 옵션 추가",
      "decision": "pending"
    }
  ]
}
```

응답 규칙:

- `rawText`는 해당 항목의 OCR 원문 블록이다.
- `sourceBox`는 이 항목이 사진의 어디에 있는지다. `[x0, y0, x1, y1]`이고, 각 값은 사진(EXIF 회전을 적용한 뒤)의 가로·세로를 0–1000으로 본 좌표다. x는 왼쪽→오른쪽, y는 위→아래다. 이름과 가격을 읽은 OCR 줄을 모두 감싸는 상자이므로, 검수 화면은 `imageUrl`에서 이 영역을 잘라 메뉴판의 그 줄을 보여 줄 수 있다. OCR+LLM(hybrid) 추출에서만 값이 있고, Gemini 단독·mock 추출, OCR 실패로 Gemini 단독으로 넘어간 사진, OCR 줄 없이 사진에서만 읽은 항목은 `null`이다. `null`이면 `rawText`로 줄을 보여 준다.
- `imageUrl`은 짧은 만료 시간을 가진 서명 URL이다. `imageUrlExpiresAt`이 만료 시각이며, 만료되지 않는 URL(로컬 저장소)이면 `null`이다. 만료되었거나 이미지 로딩이 `403`으로 실패하면 프론트엔드는 같은 `GET /api/menu-imports/{menuImportId}`를 다시 호출해 새 URL을 받는다. 다시 호출해도 `reviewVersion`이 같으면 검수 데이터는 바뀌지 않으므로 사용자가 입력 중인 결정을 유지한다.
- `extractedLineType`은 AI의 최초 분류이며 검수 후에도 변경되지 않는다.
- `extractedKind`는 AI가 판단한 메뉴 종류(2.3의 `MenuItemKind`)다. `extractedLineType = product`인 줄은 `whisky` 또는 `other`이고, 비상품 줄은 `null`이다. AI가 종류를 돌려주지 않으면 `whisky`로 본다. 검수 후에도 변경되지 않는다.
- `extractedKind = other`인 줄(진토닉, 콜라, 안주 등)은 상품 매칭을 하지 않는다. `initialResolutionStatus`, `proposedProductId`, `newProductDraft`는 `null`이고 `candidates`는 `[]`다. 프론트엔드는 이 줄을 "그 외 메뉴"로 묶어 보여 주고, 기본 결정을 `publish_without_product`(`kind = other`, 8.10)로 둔다. 업주가 위스키로 다시 분류하면 상품 검색(7)으로 고르거나 `kind = whisky`로 상품 없이 게시한다. 이때 서버가 그 이름으로 매칭한다(8.11).
- `correctedLineType`은 운영자가 최초 분류를 바꾼 경우에만 값이 있고, 그대로 승인한 경우 `null`이다.
- `effectiveLineType`은 `correctedLineType ?? extractedLineType`으로 계산한 현재 검수 기준 역할이다.
- `initialResolutionStatus`는 최초 상품 매칭 결과다. `exact_match`는 매칭 규칙(상품 별칭 정확 일치 또는 단계 규칙 S1·S2·S2b·S3)이 충돌 없이 상품 하나를 확정한 상태, `ambiguous`는 검토할 후보가 있으나 하나로 확정하지 못한 상태, `unmatched`는 유효 후보가 없는 상태다. 어느 규칙이 후보를 찾았는지는 후보 `evidence.rule`(`alias`, `S1`, `S2`, `S2b`, `S3`)에 있다. 최초 분류가 비상품이거나 위스키가 아닌 메뉴(`extractedKind = other`)라 매칭하지 않은 항목은 `null`이다.
- 서버에서 LLM 매칭 층(M3, 기본 꺼짐)을 켜면 S1~S3가 확정하지 못한 줄에 LLM 후보가 붙을 수 있다. LLM 후보는 `matchMethod = llm`, `evidence.rule`이 `M3a` 또는 `M3b`(서버를 `MATCHING_LLM_MODE=tools`로 켜면 `TOOLS`)이고 그 줄의 다른 후보보다 앞 순위다. LLM이 후보를 낸 줄은 항상 `ambiguous`이며 `exact_match`가 되지 않는다. 1순위 후보 `evidence.confirmRecommended`가 `true`이면 그 후보 하나를 확인만 하면 되는 "확인 권장" 줄이다(S2b·S3 후보에도 붙는다). LLM 후보의 그 밖의 `evidence` 키(`via`, `englishName`, `vetoed`, `shortUnverified`, tools 모드의 `sure`, `editionUnverified`)는 디버깅용이다. 규칙은 `docs/menu_ai_matching_flow.md` 6장 "현재 구현"에 있다.
- 서버에서 임베딩 후보 단계(I3-P40, 기본 꺼짐)를 켜면 규칙과 LLM 층 뒤에도 `unmatched`인 줄에 `matchMethod = embedding` 후보가 최대 5개 붙고 그 줄은 `ambiguous`가 된다. 임베딩 후보에는 `confirmRecommended`가 붙지 않으며 `exact_match`가 되지 않는다. `evidence.rule`은 `embedding`이고 `embeddingSimilarity`(0~1), `matchedText`, `model`은 설명·디버깅용이다. `confirmRecommended`가 없는 `ambiguous` 줄은 후보가 더해지지 않고 순서만 바뀔 수 있으며, 그 후보들의 `evidence`에 `rerankedBy: "embedding"`이 붙는다. 프론트엔드가 할 일은 없다(`matchMethod`의 `embedding`은 위 `MatchMethod` 값에 이미 있다).
- `candidates`는 같은 상품을 중복하지 않으며 `candidateRank` 오름차순이다.
- `proposedProductId`는 `candidateRank = 1`의 상품이거나 후보가 없으면 `null`이다.
- `newProductDraft`는 화면 입력을 돕는 계산값이며 실제 카탈로그 행이 아니다.
- `evidence`는 설명용 보조 정보다. 프론트엔드는 알 수 없는 키를 무시해야 한다.
- `before`와 `after`가 최종 diff 비교의 구조화된 값이다.
- `extractedItemIds`는 이 변경에 합쳐진 모든 추출 항목이다. 같은 상품(상품이 없으면 같은 이름 키)을 제안받은 줄이 여럿이면 옵션을 합쳐 변경 하나로 만들며(8.12), 메뉴 순서대로 담는다. `extractedItemId`는 그 첫 줄이다. 추출 항목이 없는 변경(`remove`)은 `[]`다. 이 변경을 `ignore`하면 담긴 줄 중 최종 결정이 여전히 이 변경의 대상(같은 상품, 상품이 없으면 같은 이름 키)인 줄은 메뉴판을 바꾸지 않는다. 검수자가 다른 상품을 고르거나 이름을 고쳐 대상이 달라진 줄은 그 결정대로 반영한다(8.7).
- `before`와 `after`의 `kind`는 그 메뉴 항목의 종류(2.3)다. `before`는 현재 항목의 값이고, `after`는 그 줄의 `extractedKind`다. 검수자가 다른 종류로 게시하면(8.10) 반영 결과는 그 종류가 된다.
- 제안 상품이 없는 줄(`proposedProductId = null`, 보통 `unmatched`이거나 `extractedKind = other`)은 상품 없이 게시하는 것으로 보고 비교한다. 현재 메뉴판에 이름 키(3.14.1)가 같은 미연결 항목이 있으면 그 항목과 비교해 `update`이거나 변경 없음이고, 없으면 `add`다. 이 변경의 `after.productId`는 `null`이다. 검수자가 그 줄에서 기존 상품을 고르거나 새 상품을 만들면 그 상품으로, 상품 없이 게시하면(8.10) 미연결 항목으로 반영된다. 그 줄을 비상품으로 확정하거나 제외하고 이 변경에 담긴 다른 줄도 게시하지 않으면 이 변경은 `ignore`로 보낸다(8.7의 `CHANGE_WITHOUT_PRODUCT`).
- 현재 메뉴판의 미연결 항목(3.9의 `productId = null`)도 다른 항목처럼 비교한다. `before.productId`는 `null`이고, 전체 교체(`full_replace`)에서 새 사진에 이름 키가 같은 줄이 없으면 `remove`가 된다.
- `summary`는 표시용 문구이며 검증이나 반영 기준으로 사용하지 않는다.
- `reviewDraft`는 이 작업에 저장된 검수 초안(5.9)이다. 저장된 초안이 없으면 `null`이다. 프론트엔드는 검수 화면을 열 때 이 초안의 결정을 화면에 다시 채운다. 초안의 `reviewVersion`이 응답의 `reviewVersion`과 다르면 검수 데이터가 다시 만들어진 것이므로, `extractedItemId`와 `extractedOptionId`가 지금 응답에 있는 결정만 다시 적용하고 `changeDecisions`는 버린다(9.4). 초안의 `draftVersion`은 다음 저장(5.9)에 그대로 보낸다.

`before`와 `after` 규칙:

```text
add:    before = null, after = 추가 제안
update: before = 현재 게시 값, after = 수정 제안
remove: before = 현재 게시 값, after = null
```

### 5.5 반영 완료 응답

```json
{
  "menuImportId": "77777777-7777-4777-8777-777777777777",
  "barId": "22222222-2222-4222-8222-222222222222",
  "status": "applied",
  "reviewVersion": 3,
  "appliedAt": "2026-10-04T09:15:00Z",
  "menuBoardId": "66666666-6666-4666-8666-666666666666"
}
```

### 5.6 취소된 작업 응답

```json
{
  "menuImportId": "77777777-7777-4777-8777-777777777777",
  "barId": "22222222-2222-4222-8222-222222222222",
  "status": "canceled",
  "canceledAt": "2026-10-04T09:20:00Z"
}
```

### 5.7 메뉴 등록 작업 취소

미완료 작업을 반영하지 않고 끝낸다. 업주가 검수를 포기하거나, 처리 중인 작업이 진행되지 않을 때 사용한다. 취소하면 업장에 미완료 작업이 없어지므로 새로 업로드할 수 있다.

```http
POST /api/menu-imports/{menuImportId}/cancel
Authorization: Bearer <access-token>
```

operator와 작업 대상 업장의 현재 업주가 호출할 수 있다. 요청 본문은 없다.

- `uploaded`, `processing`, `ready_for_review`인 작업만 취소할 수 있다. 상태를 `canceled`로 바꾸고 `completedAt`에 취소 시각을 기록한다.
- 현재 메뉴판과 카탈로그는 바뀌지 않는다. 업로드한 사진과 AI 처리 기록은 다른 작업처럼 보존한다.
- 처리 중에 취소하면 백그라운드 처리는 결과를 저장하지 않고 끝난다. 처리가 끝나도 상태는 `canceled`로 남는다.
- 취소와 `review-and-apply`가 동시에 오면 작업 행 잠금으로 먼저 처리된 쪽만 성공하고, 나중 요청은 `409 INVALID_IMPORT_STATE`다.
- 이미 `canceled`인 작업을 다시 취소하면 오류 없이 같은 응답을 반환한다. 네트워크 재시도에 안전하다.

`200 OK`, 본문은 5.6과 같다.

| HTTP | code | 발생 조건 | 프론트엔드 처리 |
|---|---|---|---|
| `401` | `UNAUTHENTICATED` | 3.1.5 | 3.1.5 |
| `403` | `FORBIDDEN` | operator도 작업 대상 업장의 업주도 아님 | 3.1.5 |
| `404` | `MENU_IMPORT_NOT_FOUND` | 작업이 없거나 `menuImportId`가 UUID 형식이 아님 | 작업 목록으로 이동 |
| `409` | `INVALID_IMPORT_STATE` | `applied` 또는 `failed`인 작업. `details.menuImportId`, `details.status`에 현재 상태 | 작업 상세 재조회 |

프론트엔드는 취소 전에 확인을 받는다. `ready_for_review`에서 취소하면 검수 중 입력한 결정은 모두 사라진다. 서버에 저장된 검수 초안(5.9)도 같은 트랜잭션에서 지운다.

### 5.8 실제 응답 예시와 호출자별 결과

2.4의 방법으로 받은 응답이다. 5.4의 예시는 필드 설명을 위해 손으로 쓴 값이고, 이 절은 mock 추출기로 처리한 실제 작업이다.

**통합 검수 응답 (5.4)**. 관악 위스키 바의 업주 신청을 승인할 때(3.11.7) 신청 메뉴판 사진 두 장으로 만들어진 작업이다. 그래서 `imageUrl`이 신청 사진의 경로이고, mock 추출이라 `sourceBox`가 `null`이다. 두 사진의 추출 결과가 같으므로 둘째 사진(`images[1]`)과 첫째 사진의 설명 줄(`itemOrder = 5`), 둘째 사진의 변경 하나를 생략했다.

- 2번 줄은 별칭이 정확히 맞아 `exact_match`다.
- 3번 줄은 같은 상품 후보가 있지만 연수가 달라(`evidence.ageConflict`) `ambiguous`다. 같은 상품을 2번 줄이 먼저 제안했으므로 이 줄의 변경은 없다. 이 예시는 옵션 합치기(8.12) 전에 받은 응답이며, 지금 규칙에서는 2번 줄의 변경에 3번 줄이 합쳐진다(`extractedItemIds`). 이 예시를 받은 뒤에 더한 필드(`extractedKind`, 변경의 `kind`와 `extractedItemIds`, `reviewDraft`)도 아직 없다. 구현한 뒤 다시 받아 바꾼다.
- 4번 줄은 후보가 없어 `unmatched`이며, 그 변경의 `after.productId`가 `null`이다. 이 줄을 `reject`하고 그 변경을 `apply`로 보내면 `CHANGE_WITHOUT_PRODUCT`다(8.9).

```json
{
  "menuImportId": "77777777-7777-4777-8777-777777777771",
  "barId": "22222222-2222-4222-8222-222222222222",
  "mode": "full_replace",
  "status": "ready_for_review",
  "reviewVersion": 1,
  "images": [
    {
      "imageId": "eeeeeeee-eeee-4eee-8eee-eeeeeeeeeee1",
      "imageOrder": 1,
      "imageUrl": "https://storage.example.com/signed/owner-applications/cccccccc-cccc-4ccc-8ccc-ccccccccccc1/ffffffff-ffff-4fff-8fff-fffffffffff2/page-1.jpg",
      "imageUrlExpiresAt": null,
      "items": [
        {
          "extractedItemId": "10000000-0000-4000-8000-000000000001",
          "itemOrder": 1,
          "rawText": "SINGLE MALT",
          "sourceBox": null,
          "extractedLineType": "section_header",
          "correctedLineType": null,
          "effectiveLineType": "section_header",
          "initialResolutionStatus": null,
          "extractedProductName": null,
          "extractedBrandName": null,
          "extractedAgeYears": null,
          "extractedEditionName": null,
          "extractedAbv": null,
          "extractionConfidence": 0.99,
          "proposedProductId": null,
          "options": [],
          "candidates": [],
          "newProductDraft": null
        },
        {
          "extractedItemId": "10000000-0000-4000-8000-000000000002",
          "itemOrder": 2,
          "rawText": "글렌피딕 12년 15ml 9.0 / 30ml 17.0",
          "sourceBox": null,
          "extractedLineType": "product",
          "correctedLineType": null,
          "effectiveLineType": "product",
          "initialResolutionStatus": "exact_match",
          "extractedProductName": "글렌피딕 12년",
          "extractedBrandName": "글렌피딕",
          "extractedAgeYears": 12,
          "extractedEditionName": null,
          "extractedAbv": null,
          "extractionConfidence": 0.93,
          "proposedProductId": "44444444-4444-4444-8444-444444444441",
          "options": [
            { "extractedOptionId": "20000000-0000-4000-8000-000000000001", "optionOrder": 1, "extractedOptionLabel": null, "extractedPourMl": 15, "extractedPriceKrw": 9000 },
            { "extractedOptionId": "20000000-0000-4000-8000-000000000002", "optionOrder": 2, "extractedOptionLabel": null, "extractedPourMl": 30, "extractedPriceKrw": 17000 }
          ],
          "candidates": [
            {
              "productId": "44444444-4444-4444-8444-444444444441",
              "candidateRank": 1,
              "displayName": "Glenfiddich 12",
              "brandId": "dddddddd-dddd-4ddd-8ddd-ddddddddddd1",
              "brandName": "Glenfiddich",
              "category": "whisky",
              "ageYears": 12,
              "editionName": null,
              "abv": null,
              "matchMethod": "alias",
              "score": 1.0,
              "evidence": { "aliasExact": true, "matchedAlias": "글렌피딕12", "ageExact": true, "rule": "alias" }
            }
          ],
          "newProductDraft": { "brandText": "글렌피딕", "category": "whisky", "displayName": "글렌피딕 12년", "ageYears": 12, "editionName": null, "abv": null }
        },
        {
          "extractedItemId": "10000000-0000-4000-8000-000000000003",
          "itemOrder": 3,
          "rawText": "Glenfiddich 12 (15yo) 30ml 21.0",
          "sourceBox": null,
          "extractedLineType": "product",
          "correctedLineType": null,
          "effectiveLineType": "product",
          "initialResolutionStatus": "ambiguous",
          "extractedProductName": "Glenfiddich 12",
          "extractedBrandName": "Glenfiddich",
          "extractedAgeYears": 15,
          "extractedEditionName": null,
          "extractedAbv": null,
          "extractionConfidence": 0.71,
          "proposedProductId": "44444444-4444-4444-8444-444444444441",
          "options": [
            { "extractedOptionId": "20000000-0000-4000-8000-000000000003", "optionOrder": 1, "extractedOptionLabel": null, "extractedPourMl": 30, "extractedPriceKrw": 21000 }
          ],
          "candidates": [
            {
              "productId": "44444444-4444-4444-8444-444444444441",
              "candidateRank": 1,
              "displayName": "Glenfiddich 12",
              "brandId": "dddddddd-dddd-4ddd-8ddd-ddddddddddd1",
              "brandName": "Glenfiddich",
              "category": "whisky",
              "ageYears": 12,
              "editionName": null,
              "abv": null,
              "matchMethod": "alias",
              "score": 1.0,
              "evidence": { "aliasExact": true, "matchedAlias": "glenfiddich12", "ageConflict": true, "rule": "alias" }
            }
          ],
          "newProductDraft": { "brandText": "Glenfiddich", "category": "whisky", "displayName": "Glenfiddich 12", "ageYears": 15, "editionName": null, "abv": null }
        },
        {
          "extractedItemId": "10000000-0000-4000-8000-000000000004",
          "itemOrder": 4,
          "rawText": "Unknown Distillery 25yo 잔 45,000",
          "sourceBox": null,
          "extractedLineType": "product",
          "correctedLineType": null,
          "effectiveLineType": "product",
          "initialResolutionStatus": "unmatched",
          "extractedProductName": "Unknown Distillery 25",
          "extractedBrandName": "Unknown Distillery",
          "extractedAgeYears": 25,
          "extractedEditionName": null,
          "extractedAbv": 48.0,
          "extractionConfidence": 0.88,
          "proposedProductId": null,
          "options": [
            { "extractedOptionId": "20000000-0000-4000-8000-000000000004", "optionOrder": 1, "extractedOptionLabel": "잔", "extractedPourMl": null, "extractedPriceKrw": 45000 }
          ],
          "candidates": [],
          "newProductDraft": { "brandText": "Unknown Distillery", "category": "whisky", "displayName": "Unknown Distillery 25", "ageYears": 25, "editionName": null, "abv": 48.0 }
        }
      ]
    }
  ],
  "proposedChanges": [
    {
      "changeId": "30000000-0000-4000-8000-000000000001",
      "changeType": "add",
      "barMenuItemId": null,
      "extractedItemId": "10000000-0000-4000-8000-000000000002",
      "before": null,
      "after": {
        "productId": "44444444-4444-4444-8444-444444444441",
        "displayName": "Glenfiddich 12",
        "options": [
          { "extractedOptionId": "20000000-0000-4000-8000-000000000001", "optionLabel": null, "pourMl": 15, "priceKrw": 9000 },
          { "extractedOptionId": "20000000-0000-4000-8000-000000000002", "optionLabel": null, "pourMl": 30, "priceKrw": 17000 }
        ]
      },
      "summary": "Glenfiddich 12 추가 (가격 옵션 2개)",
      "decision": "pending"
    },
    {
      "changeId": "30000000-0000-4000-8000-000000000002",
      "changeType": "add",
      "barMenuItemId": null,
      "extractedItemId": "10000000-0000-4000-8000-000000000004",
      "before": null,
      "after": {
        "productId": null,
        "displayName": "Unknown Distillery 25",
        "options": [
          { "extractedOptionId": "20000000-0000-4000-8000-000000000004", "optionLabel": "잔", "pourMl": null, "priceKrw": 45000 }
        ]
      },
      "summary": "Unknown Distillery 25 추가 (가격 옵션 1개)",
      "decision": "pending"
    }
  ]
}
```

**취소 (5.7)**. 위 작업을 취소한 응답이다.

```json
{
  "menuImportId": "77777777-7777-4777-8777-777777777771",
  "barId": "22222222-2222-4222-8222-222222222222",
  "status": "canceled",
  "canceledAt": "2026-11-09T12:46:03.982990Z"
}
```

반영이 끝난 작업을 취소했을 때 (`409`)

```json
{"error": {"code": "INVALID_IMPORT_STATE", "message": "이미 끝난 메뉴 등록 작업은 취소할 수 없습니다.", "details": {"menuImportId": "77777777-7777-4777-8777-777777777773", "status": "applied"}, "fieldErrors": []}}
```

**호출자별 결과**. 대상은 관악 위스키 바의 메뉴 등록 작업이다. 취소 행은 `ready_for_review` 작업에 차례로 보냈으므로 operator의 `200`은 이미 취소된 작업의 같은 응답이다(5.7).

| API | 비로그인 | customer | 다른 업장의 업주 | 해당 업장의 업주 | operator |
|---|---|---|---|---|---|
| `GET /api/menu-imports/{menuImportId}` | `401` | `403` | `403` | `200` | `200` |
| `GET /api/menu-imports/{menuImportId}` (없는 ID) | `401` | `404` | `404` | `404` | `404` |
| `POST /api/menu-imports/{menuImportId}/cancel` | `401` | `403` | `403` | `200` | `200` |

### 5.9 검수 초안 저장

업주가 게시하기 전까지 검수 화면에서 입력한 내용(맞아요, 후보 선택, 이름, 가격과 용량 수정, 제외 등)을 서버에 저장한다. "나중에 하기"로 나갔다가 다른 기기나 operator 웹에서 같은 검수를 이어 할 수 있게 하기 위해서다. 저장한 초안은 통합 검수 응답(5.4)의 `reviewDraft`로 불러온다.

```http
PUT /api/menu-imports/{menuImportId}/review-draft
Authorization: Bearer <access-token>
Content-Type: application/json
```

```json
{
  "draftVersion": 3,
  "reviewVersion": 3,
  "content": {
    "itemDecisions": [
      {
        "extractedItemId": "10000000-0000-4000-8000-000000000007",
        "finalLineType": "product",
        "action": "select_existing_product",
        "productId": "bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbb1",
        "options": [
          { "extractedOptionId": "20000000-0000-4000-8000-000000000001", "optionLabel": null, "pourMl": 15, "priceKrw": 8000 }
        ]
      },
      {
        "extractedItemId": "10000000-0000-4000-8000-000000000004",
        "finalLineType": "product",
        "action": "reject"
      }
    ],
    "changeDecisions": [
      { "changeId": "30000000-0000-4000-8000-000000000001", "decision": "apply" }
    ],
    "clientState": { "expandedItemIds": [] }
  }
}
```

operator와 작업 대상 업장의 현재 업주가 호출할 수 있다(검수 제출과 같다).

| 필드 | 타입 | 필수 | 규칙 |
|---|---|---|---|
| `draftVersion` | 정수 | 예 | 마지막으로 읽은 초안의 버전(5.4의 `reviewDraft.draftVersion`, 또는 직전 저장 응답의 값). 저장된 초안이 없으면 `0`. 0 이상 |
| `reviewVersion` | 정수 | 예 | 이 초안을 입력한 검수 응답의 `reviewVersion`. 1 이상. 현재 값과 달라도 저장한다 |
| `content` | 객체 | 예 | 초안 내용. 아래 형식 |

`content` 형식. 앱과 operator 웹이 같은 초안을 읽기 위한 형식이다.

| 필드 | 설명 |
|---|---|
| `itemDecisions` | 배열. 검수 제출(8.1)의 `itemDecisions[]`와 같은 형식이되, `extractedItemId` 외의 모든 필드를 생략할 수 있다. 아직 결정하지 않은 줄은 넣지 않는다. 입력 중인 값은 제출 형식의 필드에 담는다(예: 고르기 전의 `action` 없이 고친 `correctedProductName`과 `options`만) |
| `changeDecisions` | 배열. 검수 제출의 `changeDecisions[]`와 같은 형식. 결정한 변경만 넣는다 |
| `clientState` | 객체. 화면 상태(펼친 카드, 입력 중인 기본 잔 용량 등)를 담는 클라이언트 전용 칸. 서버와 다른 클라이언트는 해석하지 않으며, 다른 클라이언트의 `clientState`는 무시한다 |

세 필드 모두 선택이다. 정의하지 않은 최상위 필드도 거부하지 않고 그대로 저장한다.

저장 규칙:

- **검증**: 초안은 미완성이므로 검수 제출만큼 검사하지 않는다. `content`가 JSON 객체인지와 크기만 확인하고 내용은 그대로 저장한다. 결정의 실제 검증은 제출(8.7) 때 한다. `content`를 JSON으로 쓴 크기가 256KB(262,144바이트)를 넘으면 `413 REVIEW_DRAFT_TOO_LARGE`(`details.maxBytes`)다.
- **상태**: 작업이 `ready_for_review`일 때만 저장한다. 아니면 `409 INVALID_IMPORT_STATE`(`details.menuImportId`, `details.status`)다.
- **동시 수정**: 요청의 `draftVersion`이 서버의 현재 초안 버전과 다르면 아무것도 저장하지 않고 `409 REVIEW_DRAFT_OUTDATED`다. 같은 검수를 두 기기에서, 또는 업주와 operator가 함께 고칠 때 서로의 입력을 덮어쓰지 않게 하기 위해서다. 같으면 초안을 바꾸고 버전을 1 올린다.
- **잠금**: 메뉴판을 바꾸지 않으므로 업장 행은 잠그지 않는다. 작업 행만 잠그고 상태와 버전을 확인한다. 그래서 검수 제출, 취소와 동시에 와도 차례로 처리되고, 제출이나 취소가 먼저 끝나면 저장은 `409 INVALID_IMPORT_STATE`다.
- **지우기**: 검수 제출(8)이나 취소(5.7)가 성공하면 같은 트랜잭션에서 초안을 지운다. 초안 버전은 그대로 둔다. 검수 데이터가 다시 만들어져도(`REVIEW_OUTDATED`, 9.4) 초안은 지우지 않는다. 사용자가 그 입력을 다시 적용해야 하기 때문이다.
- **검사 순서**: 인증(`401`) → 요청 형식(`422`), 크기(`413`) → 작업(`404 MENU_IMPORT_NOT_FOUND`) → 권한(`403`) → 작업 행 잠금 → 상태(`409 INVALID_IMPORT_STATE`) → 초안 버전(`409 REVIEW_DRAFT_OUTDATED`).

`200 OK`

```json
{
  "menuImportId": "77777777-7777-4777-8777-777777777777",
  "draftVersion": 4,
  "savedAt": "2026-10-04T09:06:00Z"
}
```

| HTTP | code | 발생 조건 | 프론트엔드 처리 |
|---|---|---|---|
| `401` | `UNAUTHENTICATED` | 3.1.5 | 3.1.5 |
| `403` | `FORBIDDEN` | operator도 작업 대상 업장의 업주도 아님 | 3.1.5 |
| `404` | `MENU_IMPORT_NOT_FOUND` | 작업이 없거나 `menuImportId`가 UUID 형식이 아님 | 작업 목록으로 이동 |
| `409` | `INVALID_IMPORT_STATE` | 작업이 `ready_for_review`가 아님. 다른 곳에서 제출되었거나 취소됨 | 작업 상세를 다시 조회해 상태에 맞는 화면으로 이동 |
| `409` | `REVIEW_DRAFT_OUTDATED` | 다른 기기나 다른 사람이 먼저 저장함. `details.currentDraftVersion`, `details.savedAt`, `details.reviewUrl` | 아래 |
| `413` | `REVIEW_DRAFT_TOO_LARGE` | `content`가 256KB를 넘음. `details.maxBytes` | 기기에만 저장하고 서버 저장은 멈춤. 앱 버그로 보고 기록 |
| `422` | `VALIDATION_FAILED` | `draftVersion`, `reviewVersion`이 범위 밖이거나, `content`가 객체가 아님 | 앱 버그로 보고 기록 |

프론트엔드 처리:

- 입력이 멈추고 몇 초 뒤, 그리고 "나중에 하기"로 검수 화면을 나갈 때 저장한다. 성공 응답의 `draftVersion`을 다음 저장에 보낸다.
- 서버 저장이 실패해도(네트워크 오류, `5xx`) 입력은 기기에 남겨 두고 다시 보낸다. 화면에는 "이 기기에는 저장됐어요"를 보여 주고 재시도를 제공한다.
- `REVIEW_DRAFT_OUTDATED`를 받으면 `details.reviewUrl`로 최신 검수 응답(5.4)을 다시 받아, 다른 곳에서 저장된 초안(`reviewDraft`)을 보여 주고 그 초안으로 이어 할지, 이 기기의 입력으로 덮어쓸지 고르게 한다. 덮어쓰면 새로 받은 `draftVersion`으로 다시 저장한다.

**호출자별 결과**. 대상은 `ready_for_review`인 관악 위스키 바의 작업이다.

| API | 비로그인 | customer | 다른 업장의 업주 | 해당 업장의 업주 | operator |
|---|---|---|---|---|---|
| `PUT /api/menu-imports/{menuImportId}/review-draft` | `401` | `403` | `403` | `200` | `200` |

이 표는 구현 전에 권한 규칙(2.2)으로 적은 값이다. 구현한 뒤 2.4의 방법으로 받아 확인한다.

## 6. 검수 보조 브랜드 검색

신규 상품 등록 중 기존 브랜드를 선택하기 위한 읽기 전용 API다.

### 6.1 요청

```http
GET /api/catalog/brands?query=%EB%94%98%EC%8A%A4%ED%86%A4&limit=20
Authorization: Bearer <access-token>
```

| Query | 필수 | 기본값 | 설명 |
|---|---|---|---|
| `query` | 예 | 없음 | 브랜드명 또는 별칭 검색어 |
| `limit` | 아니오 | `20` | 최대 `50` |

### 6.2 응답

```json
{
  "items": [
    {
      "brandId": "dddddddd-dddd-4ddd-8ddd-ddddddddddd1",
      "canonicalName": "Deanston",
      "matchedAlias": "딘스톤"
    }
  ]
}
```

동일한 정규화 별칭이 여러 브랜드에 연결되면 모두 반환한다. 프론트엔드는 자동으로 하나를 확정하지 않는다.

## 7. 검수 보조 상품 검색

자동 후보에 없거나 다른 상품을 운영자가 직접 찾기 위한 읽기 전용 API다.

### 7.1 요청

```http
GET /api/catalog/products?query=%EB%94%98%EC%8A%A4%ED%86%A4%2012&brandId=dddddddd-dddd-4ddd-8ddd-ddddddddddd1&includeInactive=true&limit=20
Authorization: Bearer <access-token>
```

| Query | 필수 | 기본값 | 설명 |
|---|---|---|---|
| `query` | 예 | 없음 | 상품명 또는 별칭 검색어 |
| `brandId` | 아니오 | 없음 | 특정 브랜드로 제한 |
| `includeInactive` | 아니오 | `true` | 중복 생성을 막기 위해 검수 검색에서는 비활성 상품도 포함 |
| `limit` | 아니오 | `20` | 최대 `50` |

### 7.2 응답

```json
{
  "items": [
    {
      "productId": "bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbb1",
      "displayName": "Deanston 12",
      "brandId": "dddddddd-dddd-4ddd-8ddd-ddddddddddd1",
      "brandName": "Deanston",
      "category": "whisky",
      "ageYears": 12,
      "editionName": null,
      "abv": 46.3,
      "isActive": true,
      "matchedAlias": "딘스톤 12년"
    }
  ]
}
```

비활성 상품(`isActive = false`)은 같은 상품을 새로 만드는 일을 막기 위해 검색 결과에 보여 준다. 하지만 메뉴에 연결할 수는 없다. `select_existing_product`로 비활성 상품을 제출하면 `422 VALIDATION_FAILED`(`fieldErrors[].code = PRODUCT_INACTIVE`)다. 상품을 다시 활성화하는 API는 이 문서의 범위가 아니다(1장 제외 범위의 카탈로그 CRUD).

프론트엔드 처리: 비활성 상품은 "비활성 상품" 표시와 함께 보여 주되 선택할 수 없게 한다. 같은 상품을 새로 만들려고 하면 백엔드가 `409 DUPLICATE_PRODUCT_FOUND`로 막으므로(9.5), 이 경우 사용자에게 operator 문의를 안내한다.

## 8. 통합 검수 제출과 메뉴 반영

### 8.1 요청

```http
POST /api/menu-imports/{menuImportId}/review-and-apply
Authorization: Bearer <access-token>
Content-Type: application/json
```

최상위 요청:

| 필드 | 타입 | 필수 | 설명 |
|---|---|---|---|
| `reviewVersion` | 정수 | 예 | 조회한 통합 검수 응답의 버전 |
| `itemDecisions` | 배열 | 예 | 모든 추출 항목의 최종 결정 |
| `changeDecisions` | 배열 | 예 | 모든 임시 diff의 적용 또는 무시 결정 |

한 화면의 결정을 한 번에 제출한다. 제출 전까지의 입력은 검수 초안(5.9)으로 저장하며, 초안은 메뉴판과 카탈로그를 바꾸지 않는다. 제출에 성공하면 초안을 지운다. operator와 작업 대상 업장의 현재 업주가 호출할 수 있다.

모든 객체는 정의하지 않은 필드를 받지 않는다(`EXTRA_FORBIDDEN`). 예를 들어 `confirm_non_product`에 `options`를 보내면 거부한다. 문자열 필드는 앞뒤 공백을 지운 뒤 길이를 검사한다.

`itemDecisions[]`는 `action`에 따라 네 형식 중 하나다.

| `action` | 용도 | `finalLineType` | 필드 |
|---|---|---|---|
| `select_existing_product` | 기존 상품에 연결 | `product` | `extractedItemId`, `productId`, `options` 필수. `correctedProductName`, `aliasesToAdd` 선택 |
| `create_product` | 새 상품(필요하면 새 브랜드)을 만들어 연결 | `product` | `extractedItemId`, `brand`, `product`, `options` 필수. `correctedProductName`, `aliases` 선택 |
| `publish_without_product` | 상품 없이 메뉴 항목으로 게시 (8.10) | `product` | `extractedItemId`, `kind`, `options` 필수. `correctedProductName` 선택 |
| `confirm_non_product` | 비상품 줄로 확정 | `section_header`, `description`, `unknown` | `extractedItemId`만 |
| `reject` | 잡음·중복 등으로 제외 | 어떤 값이든 | `extractedItemId`만 |

업주 화면은 카탈로그에서 찾지 못한 줄을 `create_product`가 아니라 `publish_without_product`로 보낸다. 브랜드와 상품 정보는 업주가 아니라 운영자가 정하기 때문이다(8.10). `create_product`는 그대로 두며, operator가 검수할 때 쓸 수 있다.

메뉴 항목으로 게시하는 결정(`select_existing_product`, `create_product`, `publish_without_product`)의 공통 필드:

| 필드 | 필수 | 규칙 |
|---|---|---|
| `extractedItemId` | 예 | 검수 응답의 항목 ID |
| `correctedProductName` | 아니오 | 메뉴판에 보일 이름. 1~200자. 없거나 `null`이면 추출한 이름을 쓴다. 추출한 이름과 다르면 서버가 이 이름으로 다시 매칭한다(8.11) |
| `options` | 예 | 그 줄의 최종 옵션 목록 전체. 1~10개이며, 빈 배열이면 `TOO_SHORT`, 10개를 넘으면 `TOO_LONG`이다. 배열 순서가 표시 순서다 |
| `options[].extractedOptionId` | 아니오 | 이 옵션이 나온 추출 옵션의 ID. 업주가 새로 더한 옵션이면 없거나 `null`이다. 그 항목의 옵션이 아니면 `UNKNOWN_OPTION`, 한 줄에서 같은 ID를 두 번 쓰면 `DUPLICATE_OPTION`이다 |
| `options[].optionLabel` | 아니오 | 메뉴판의 `잔`, `병` 같은 표기. 앞뒤 공백을 지운 뒤 1~100자. 없거나 `null`이면 표기 없음 |
| `options[].pourMl` | 아니오 | 용량(ml). 1~32767 정수. 없거나 `null`이면 용량 없음 |
| `options[].priceKrw` | 예 | 가격(원). 1~99,999,999 정수(3.14.2와 같다) |

`options`는 직접 편집(3.14.2)의 옵션과 같은 형식에 `extractedOptionId`를 더하고 할인을 뺀 것이다. 값은 고칠 부분만이 아니라 최종 값을 모두 보낸다.

- **옵션 삭제**: 목록에 없는 추출 옵션은 게시하지 않는다. AI가 잘못 읽은 옵션(예: 연도를 가격으로 읽음)은 빼고 보낸다.
- **옵션 추가**: `extractedOptionId`가 없는 옵션은 업주가 새로 더한 옵션이다. AI가 놓친 옵션과, 옵션이 하나도 추출되지 않은 줄의 가격이 여기에 들어간다.
- **값 지우기**: `optionLabel`과 `pourMl`은 `null`로 보내면 지워진다. 예를 들어 병 옵션에 잘못 잡힌 용량을 지울 수 있다.
- **가격**: 모든 옵션에 가격이 있어야 한다. 가격을 모르는 옵션은 보내지 않는다.
- **같은 값**: 한 줄 안에서 `optionLabel`과 `pourMl`이 모두 같은 옵션이 둘 이상이면 `DUPLICATE_OPTION_VALUES`다(3.14.2와 같다).
- **기본 잔 용량**: 서버는 `pourMl`을 받은 그대로 저장한다. 메뉴판에 용량이 없는 잔 옵션은 프론트엔드가 매장 기본 잔 용량(3.6의 `defaultPourMl`)을 `pourMl`에 채워 보낸다. 병 옵션에는 채우지 않는다.
- **저장**: 게시된 옵션의 출처(`menu_entry_options.source_extracted_option_id`)에 `extractedOptionId`를 저장하고, 새로 더한 옵션은 `null`이다. 추출 옵션의 값과 다르게 보낸 값은 그 추출 옵션의 교정값(`corrected_*`)에도 기록한다. 삭제와 추가는 게시된 옵션의 출처와 비교해 알 수 있으므로 따로 저장하지 않는다.

검수에서는 할인(3.14.2)을 정하지 않는다. `options`에 할인 필드는 없으며, 보내면 `EXTRA_FORBIDDEN`이다. 할인은 메뉴를 반영한 뒤 직접 편집(3.14.4)으로 정한다. 메뉴판 사진에 할인이 적힌 경우가 드물고, 할인은 기간이 있어 사진에서 읽을 수 없기 때문이다. 반영할 때 기존 할인이 이어지는 규칙은 8.7을 따른다.

`select_existing_product`의 추가 필드:

| 필드 | 필수 | 규칙 |
|---|---|---|
| `productId` | 예 | 활성 상품의 ID. 비활성이면 `PRODUCT_INACTIVE`(7.2) |
| `aliasesToAdd` | 아니오 | 이 상품에 추가할 별칭. 기본 `[]` |
| `aliasesToAdd[].aliasText` | 예 | 1~200자 |
| `aliasesToAdd[].languageCode` | 아니오 | 10자 이하. 예: `ko`, `en` |
| `aliasesToAdd[].isSearchable` | 아니오 | 고객 검색에 쓸지 여부. 기본 `true` |

`create_product`의 추가 필드:

| 필드 | 필수 | 규칙 |
|---|---|---|
| `brand.type` | 예 | `existing` 또는 `new` |
| `brand.brandId` | `existing`만 필수 | 기존 브랜드 ID |
| `brand.canonicalName` | `new`만 필수 | 1~120자. 별칭으로도 함께 저장한다 |
| `brand.aliases` | 아니오 | `new`만. `aliasText` 1~120자, `languageCode` 10자 이하. 기본 `[]` |
| `product.category` | 아니오 | 1~30자. 기본 `whisky` |
| `product.displayName` | 예 | 대표 상품명. 1~200자. 별칭으로도 함께 저장한다 |
| `product.ageYears` | 아니오 | 0~200 정수 |
| `product.editionName` | 아니오 | 1~150자 |
| `product.abv` | 아니오 | 0 초과 100 이하 |
| `aliases` | 아니오 | `aliasesToAdd`와 같은 형식. 기본 `[]` |

`publish_without_product`의 추가 필드:

| 필드 | 필수 | 규칙 |
|---|---|---|
| `kind` | 예 | `MenuItemKind`(2.3). `whisky`이면 운영자의 연결을 기다리는 위스키, `other`이면 위스키가 아닌 메뉴다 |

`changeDecisions[]`는 `changeId`(필수)와 `decision`(`apply` 또는 `ignore`, 필수)이다. `reviewVersion`은 1 이상 정수다. 추출 항목에 연결된 변경(`extractedItemIds`가 빈 배열이 아닌 변경)은 그 줄 중 하나라도 메뉴 항목으로 게시할 때(`select_existing_product`, `create_product`, `publish_without_product`)만 `apply`할 수 있다(8.7).

### 8.2 기존 상품 선택 예시

```json
{
  "reviewVersion": 3,
  "itemDecisions": [
    {
      "extractedItemId": "10000000-0000-4000-8000-000000000007",
      "finalLineType": "product",
      "action": "select_existing_product",
      "productId": "bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbb1",
      "correctedProductName": "딘스톤 12년",
      "aliasesToAdd": [
        {
          "aliasText": "딘스톤 12년",
          "languageCode": "ko",
          "isSearchable": true
        }
      ],
      "options": [
        {
          "extractedOptionId": "20000000-0000-4000-8000-000000000001",
          "optionLabel": null,
          "pourMl": 15,
          "priceKrw": 8000
        },
        {
          "extractedOptionId": "20000000-0000-4000-8000-000000000002",
          "optionLabel": null,
          "pourMl": 30,
          "priceKrw": 15000
        },
        {
          "extractedOptionId": null,
          "optionLabel": "병",
          "pourMl": null,
          "priceKrw": 160000
        }
      ]
    }
  ],
  "changeDecisions": [
    {
      "changeId": "30000000-0000-4000-8000-000000000001",
      "decision": "apply"
    }
  ]
}
```

저장 규칙:

```text
productId == proposedProductId
→ selectedMatchMethod = 1순위 후보의 matchMethod

다른 후보 또는 검색 결과를 선택
→ selectedMatchMethod = manual

선택 상품이 candidates에 존재
→ matchConfidence = 선택 후보의 score

후보에 없던 검색 상품
→ matchConfidence = null
```

`aliasesToAdd`는 운영자가 실제 동일 상품의 정상 표기임을 확인한 경우에만 보낸다. 단순 공백 차이와 명백한 OCR 오류는 보내지 않는다.

`finalLineType`이 응답의 `extractedLineType`과 같으면 백엔드는 `corrected_line_type = null`로 유지한다. 서로 다르면 `corrected_line_type = finalLineType`을 저장한다. `initial_resolution_status`는 어떤 검수 결정을 제출하더라도 변경하지 않는다.

### 8.3 비상품 확정 예시

```json
{
  "extractedItemId": "10000000-0000-4000-8000-000000000003",
  "finalLineType": "section_header",
  "action": "confirm_non_product"
}
```

`confirm_non_product`의 `finalLineType`은 `section_header`, `description`, `unknown` 중 하나여야 하며 상품과 옵션 필드를 보내지 않는다.

### 8.4 항목 제외 예시

```json
{
  "extractedItemId": "10000000-0000-4000-8000-000000000004",
  "finalLineType": "unknown",
  "action": "reject"
}
```

OCR 잡음, 중복 인식 또는 사용할 수 없는 항목에 사용한다.

### 8.5 기존 브랜드로 신규 상품 생성

```json
{
  "extractedItemId": "10000000-0000-4000-8000-000000000007",
  "finalLineType": "product",
  "action": "create_product",
  "correctedProductName": "딘스톤 버진 오크",
  "brand": {
    "type": "existing",
    "brandId": "dddddddd-dddd-4ddd-8ddd-ddddddddddd1"
  },
  "product": {
    "category": "whisky",
    "displayName": "Deanston Virgin Oak",
    "ageYears": null,
    "editionName": "Virgin Oak",
    "abv": 46.3
  },
  "aliases": [
    {
      "aliasText": "딘스톤 버진 오크",
      "languageCode": "ko",
      "isSearchable": true
    },
    {
      "aliasText": "Deanston Virgin Oak",
      "languageCode": "en",
      "isSearchable": true
    }
  ],
  "options": [
    {
      "extractedOptionId": "20000000-0000-4000-8000-000000000001",
      "optionLabel": null,
      "pourMl": 15,
      "priceKrw": 12000
    }
  ]
}
```

### 8.6 신규 브랜드와 신규 상품 생성

```json
{
  "extractedItemId": "10000000-0000-4000-8000-000000000009",
  "finalLineType": "product",
  "action": "create_product",
  "brand": {
    "type": "new",
    "canonicalName": "New Distillery",
    "aliases": [
      {
        "aliasText": "뉴 디스틸러리",
        "languageCode": "ko"
      },
      {
        "aliasText": "New Distillery",
        "languageCode": "en"
      }
    ]
  },
  "product": {
    "category": "whisky",
    "displayName": "New Distillery 12",
    "ageYears": 12,
    "editionName": null,
    "abv": 46.0
  },
  "aliases": [
    {
      "aliasText": "뉴 디스틸러리 12년",
      "languageCode": "ko",
      "isSearchable": true
    },
    {
      "aliasText": "New Distillery 12YO",
      "languageCode": "en",
      "isSearchable": true
    }
  ],
  "options": [
    {
      "extractedOptionId": "20000000-0000-4000-8000-000000000003",
      "optionLabel": null,
      "pourMl": 15,
      "priceKrw": 14000
    }
  ]
}
```

백엔드는 `normalizedAlias`를 요청받지 않는다. 모든 브랜드·상품 별칭의 정규화값은 백엔드의 단일 정규화 함수가 생성한다.

### 8.7 최종 요청 검증 규칙

- `menuImport.status`는 `ready_for_review`여야 한다.
- 요청의 `reviewVersion`은 현재 값과 같아야 한다.
- `itemDecisions`는 검수 대상 항목을 빠짐없이 한 번씩 포함해야 한다.
- `changeDecisions`는 현재 `pending` 변경을 빠짐없이 한 번씩 포함해야 한다.
- 변경의 `extractedItemIds`에 담긴 줄을 모두 `confirm_non_product`나 `reject`로 결정했으면 그 변경은 `ignore`여야 한다. `apply`이면 `fieldErrors[].path = changeDecisions[i].decision`, `code = CHANGE_WITHOUT_PRODUCT`다. 담긴 줄 중 하나라도 메뉴 항목으로 게시하면 `apply`할 수 있다. 예: 잔 줄과 병 줄이 합쳐진 변경에서 잔 줄만 제외하고 병 줄을 게시하려면 `apply`로 보낸다. 추출 항목이 없는 변경(`remove`)에는 이 규칙이 없다.
- 변경을 `ignore`하면 그 변경에 담긴 줄 중 최종 결정이 여전히 그 변경의 대상(같은 상품, 상품이 없으면 같은 이름 키)인 줄은 메뉴판을 바꾸지 않는다. 대상이 달라진 줄은 그 결정대로 반영한다.
- `finalLineType = product`이면 `select_existing_product`, `create_product`, `publish_without_product` 중 하나여야 한다.
- 메뉴 항목으로 게시하는 줄은 `options`가 1~10개이고 모든 옵션에 가격이 있어야 한다(8.1). 상품 없이 게시하는 줄도 같다. `extractedOptionId`는 그 줄의 추출 옵션이어야 하고 한 줄에서 겹치지 않아야 한다.
- 같은 상품(상품 없는 줄은 같은 이름 키)으로 게시하는 줄이 여럿이면 옵션을 합쳐 한 항목으로 게시한다(8.12). 같은 `productId`로 제출한 줄끼리(다시 매칭으로 상품이 바뀐 줄 제외) 표기와 용량이 같은 옵션의 가격이 다르면 `fieldErrors[].code = OPTION_PRICE_CONFLICT`다. 다시 매칭이나 이름 키 때문에 합쳐진 줄의 충돌은 거부하지 않는다(8.12).
- `publish_without_product`의 메뉴판 이름(`correctedProductName ?? extractedProductName`)이 없거나, 정규화한 이름 키(3.14.1)가 빈 값이면 `fieldErrors[].path = itemDecisions[i].correctedProductName`, `code = NOT_NORMALIZABLE`이다.
- 기존 상품은 존재하고 연결 가능한 상태여야 한다.
- 이름을 고친 위스키 줄은 이 이름으로 다시 매칭하고, 그 결과로 연결할 상품을 정한다(8.11). 제출한 `productId`와 달라져도 거부하지 않는다.
- 선택한 상품의 연수나 에디션이 추출값과 충돌해도 거부하지 않고, 제출하기 전에 확인도 묻지 않는다. AI가 잘못 읽은 값을 바로잡을 수 있어야 하고, 연결이 맞는지는 업주보다 운영자가 정확하게 판단하기 때문이다. 대신 서버가 비교해 충돌하면 그 상품에 연결해 게시하고 운영자 확인(3.18, 사유 `attribute_conflict`)에 올린다.
  - 대상: `select_existing_product`로 게시하는 줄 중 이름을 고치지 않은 줄(8.11의 대상이 아닌 줄)이다. 후보에서 고른 상품과 검색에서 고른 상품 모두 같다. 이름을 고친 줄은 추출한 연수와 에디션이 예전 이름에서 나온 값이고, 다시 매칭(8.11)이 연결을 정하므로 비교하지 않는다. `create_product`와 `publish_without_product`도 비교하지 않는다.
  - 비교: 최종 상품과 그 줄의 `extractedAgeYears`, `extractedEditionName`을 매칭 흐름 문서 10장의 규칙으로 서버가 직접 비교한다. 후보의 `evidence`에 기대지 않으므로 검색으로 고른 상품도 같은 기준이다. 연수가 둘 다 있고 다르거나(`ageConflict`), 추출 에디션이 상품의 에디션명과 그 상품의 별칭 어디에도 없거나(`editionConflict`), 에디션이 추출값 쪽에만 있으면(`editionOnlyInExtracted`) 충돌이다. 자동 확정(`exact_match`)된 상품은 이 규칙으로 충돌이 없어 확정된 것이므로 그대로 받아들이면 확인에 올라가지 않는다.
  - 제출한 사람과 관계없이 같다. operator가 제출해도 확인에 올린다. 고르는 사람과 확인하는 사람이 같더라도 한 번 더 보게 하기 위해서다.
  - 확인은 반영과 같은 트랜잭션에서 만들고, 출처는 그 검수 줄이다. 운영자는 확인 목록(3.18.2)에서 연결된 상품의 연수와 에디션, 추출값, 사진의 그 줄을 함께 보고, 맞으면 `keep`, 틀리면 `link_existing`으로 처리한다(3.18.3).
  - 프론트엔드는 이 충돌로 업주에게 확인을 묻지 않는다. 후보의 `evidence`는 지금처럼 표시용으로만 쓴다.
- 신규 브랜드·상품은 트랜잭션 안에서 중복을 다시 검사한다.
- 백엔드는 운영자가 제출한 결정으로 최종 변경을 계산해 반영한다. 다른 후보를 고르거나 가격을 고쳐서 임시 diff와 달라진 변경도 운영자의 결정이므로 그대로 반영한다.
- 현재 메뉴판의 항목은 운영자가 `apply`한 `remove`로만 빠진다.
- 검수 데이터를 만든 뒤 현재 메뉴판이 바뀌었으면(다른 작업이 먼저 게시된 경우 등) 반영하지 않는다. 백엔드는 임시 diff를 다시 만들고 `reviewVersion`을 올린 뒤 `REVIEW_OUTDATED`를 반환한다.
- 반영은 메뉴 등록 작업을 잠그기 전에 업장 행을 먼저 잠근다(3.14.1). 같은 업장의 직접 편집, 품절 표시, 판매 정보 확인, 새 등록 작업과 차례로 처리하기 위해서다. 잠근 뒤 업장이 비활성이면 아무것도 반영하지 않고 `404 BAR_NOT_FOUND`(`details.barId`)다. 비활성 업장은 메뉴를 바꾸지 않기 때문이다(3.14.1, 4.4). 이미 반영된 작업을 다시 보낸 경우에도 같다.
- 반영할 때 품절과 할인은 다음처럼 이어진다. 품절(3.14.8)은 메뉴판에 남는 항목에서 그대로 유지되고, `remove`로 빠진 항목에서는 풀린다. 할인(3.14.2)은 반영 뒤에도 표기(`optionLabel`), 용량(`pourMl`), 정가(`priceKrw`)가 모두 같은 옵션이 남으면 그 옵션에 그대로 유지된다. 정가가 바뀌거나 옵션이 없어지면 할인이 지워진다. 정가가 바뀌면 원래 할인가가 맞는지 알 수 없기 때문이다. 품절 변경과 판매 정보 확인은 "검수 데이터를 만든 뒤 현재 메뉴판이 바뀌었는지" 검사에서 메뉴판 변경으로 보지 않는다.
- 반영에 성공하면 메뉴판 버전(3.9의 `menuVersion`)을 1 올리고, `publishedAt`을 업장 행을 잠근 뒤의 현재 시각으로 바꾼다(3.14.1의 게시 시각). 미완료 작업이 있는 동안에는 메뉴 직접 편집(3.14)을 받지 않으므로, 검수 중에 직접 편집으로 메뉴판이 바뀌는 일은 없다.

### 8.8 성공 응답

```http
HTTP/1.1 200 OK
```

```json
{
  "menuImportId": "77777777-7777-4777-8777-777777777777",
  "status": "applied",
  "reviewVersion": 3,
  "appliedAt": "2026-10-04T09:15:00Z",
  "menuBoardId": "66666666-6666-4666-8666-666666666666",
  "result": {
    "added": 3,
    "updated": 2,
    "removed": 1,
    "ignored": 1,
    "createdBrands": 0,
    "createdProducts": 1,
    "unlinkedWhisky": 1
  }
}
```

`result.unlinkedWhisky`는 이번 반영으로 메뉴판에 추가되거나 바뀐 항목 중 상품 없는 위스키 항목(`kind = whisky`, `productId = null`)의 수다. 줄이 아니라 항목을 세므로, 이름 키가 같아 합쳐진 줄들(8.12)은 하나로 센다. 상품 없이 게시한 줄(8.10)과 다시 매칭으로 연결이 풀린 줄(8.11)을 모두 센다. 메뉴판에 원래 있던 미연결 항목이 바뀌지 않고 남은 경우는 세지 않는다.

최종 확정과 메뉴판 반영은 하나의 `SERIALIZABLE` 트랜잭션이다. 성공하면 상태가 `ready_for_review`에서 `applied`로 바로 바뀐다.

네트워크 타임아웃 후 같은 요청이 다시 들어왔는데 이미 `applied`라면 변경을 다시 적용하지 않고 현재 적용 결과를 반환한다.

### 8.9 실제 응답 예시와 호출자별 결과

2.4의 방법으로 받은 응답이다. 5.8의 작업을 취소한 뒤 메뉴판 사진 한 장을 다시 올려(4장) 만든 작업으로, mock 추출 결과는 5.8의 첫째 사진과 같다.

**요청**. 머리말과 설명 줄은 비상품으로 확정하고, 2번과 3번 줄은 같은 상품(Glenfiddich 12)에 연결하고, 후보가 없는 4번 줄은 제외했다. 변경은 2번 줄의 `add`를 적용하고 4번 줄의 `add`는 무시했다. 이 요청은 옵션 목록 전체 제출(8.1의 `options`) 전의 형식이라 지금 규칙에서는 `options`가 없어 거부된다. 구현한 뒤 새 형식으로 다시 받아 바꾼다.

```json
{
  "reviewVersion": 1,
  "itemDecisions": [
    { "extractedItemId": "10000000-0000-4000-8000-000000000011", "finalLineType": "section_header", "action": "confirm_non_product" },
    { "extractedItemId": "10000000-0000-4000-8000-000000000012", "finalLineType": "product", "action": "select_existing_product", "productId": "44444444-4444-4444-8444-444444444441" },
    { "extractedItemId": "10000000-0000-4000-8000-000000000013", "finalLineType": "product", "action": "select_existing_product", "productId": "44444444-4444-4444-8444-444444444441" },
    { "extractedItemId": "10000000-0000-4000-8000-000000000014", "finalLineType": "product", "action": "reject" },
    { "extractedItemId": "10000000-0000-4000-8000-000000000015", "finalLineType": "description", "action": "confirm_non_product" }
  ],
  "changeDecisions": [
    { "changeId": "30000000-0000-4000-8000-000000000004", "decision": "apply" },
    { "changeId": "30000000-0000-4000-8000-000000000005", "decision": "ignore" }
  ]
}
```

**성공 응답**. 같은 상품의 두 줄이 한 항목으로 게시되어 `added = 1`이다. 같은 요청을 다시 보내도 같은 응답이다. 이 응답은 옵션 합치기(8.12) 전의 규칙(첫 줄만 게시)으로 받은 것이며, 구현한 뒤 다시 받아 바꾼다.

```json
{
  "menuImportId": "77777777-7777-4777-8777-777777777773",
  "status": "applied",
  "reviewVersion": 1,
  "appliedAt": "2026-11-09T12:46:34.781545Z",
  "menuBoardId": "66666666-6666-4666-8666-666666666661",
  "result": {
    "added": 1,
    "updated": 0,
    "removed": 0,
    "ignored": 1,
    "createdBrands": 0,
    "createdProducts": 0
  }
}
```

**대표 오류**

첫 항목의 결정을 빼고, 제외한 4번 줄의 변경(과 둘째 사진의 같은 변경)을 `apply`로 보냈을 때 (`422`). 문제가 모두 한 응답에 온다.

```json
{
  "error": {
    "code": "VALIDATION_FAILED",
    "message": "입력값을 확인해 주세요.",
    "details": null,
    "fieldErrors": [
      {
        "path": "itemDecisions",
        "code": "MISSING_ITEM",
        "message": "결정하지 않은 항목이 1개 있습니다."
      },
      {
        "path": "changeDecisions[1].decision",
        "code": "CHANGE_WITHOUT_PRODUCT",
        "message": "상품으로 확정하지 않은 항목의 변경은 적용할 수 없습니다."
      },
      {
        "path": "changeDecisions[2].decision",
        "code": "CHANGE_WITHOUT_PRODUCT",
        "message": "상품으로 확정하지 않은 항목의 변경은 적용할 수 없습니다."
      }
    ]
  }
}
```

검수 중에 operator가 업장을 비활성화한 뒤 제출했을 때 (`404`, 8.7). 아무것도 반영되지 않는다.

```json
{"error": {"code": "BAR_NOT_FOUND", "message": "업장을 찾을 수 없습니다.", "details": {"barId": "22222222-2222-4222-8222-222222222223"}, "fieldErrors": []}}
```

`reviewVersion`이 다를 때의 `409 REVIEW_OUTDATED`는 9.1의 예시와 같은 형식이다.

**호출자별 결과**. 대상은 `ready_for_review`인 위 작업이며, 표의 왼쪽 열부터 차례로 위 요청 본문을 그대로 보냈다. 해당 업장의 업주가 반영했고, 그 뒤 operator의 `200`은 이미 반영된 작업의 같은 결과다(8.8).

| API | 비로그인 | customer | 다른 업장의 업주 | 해당 업장의 업주 | operator |
|---|---|---|---|---|---|
| `POST /api/menu-imports/{menuImportId}/review-and-apply` | `401` | `403` | `403` | `200` | `200` |

### 8.10 상품 없이 게시

카탈로그에서 찾지 못한 위스키 줄과 위스키가 아닌 메뉴 줄은 상품에 연결하지 않고 그 업장의 메뉴에만 게시한다. 업주는 카탈로그에 상품이 있는지 알 수 없고, 브랜드, 연수, 중복 여부는 운영자가 더 정확하게 판단하기 때문이다.

```json
{
  "extractedItemId": "10000000-0000-4000-8000-000000000004",
  "finalLineType": "product",
  "action": "publish_without_product",
  "kind": "whisky",
  "correctedProductName": "Unknown Distillery 25년"
}
```

반영 규칙:

- 메뉴판 이름은 `correctedProductName ?? extractedProductName`이다.
- 현재 메뉴판에 이름 키(3.14.1)가 같은 미연결 항목이 있으면 그 항목을 갱신한다. `barMenuItemId`와 품절 상태는 그대로이고, 종류는 이번에 보낸 `kind`로 바뀐다. 없으면 새 미연결 항목을 만든다. 현재 메뉴판에서 빠진 예전 미연결 항목은 다시 쓰지 않는다.
- 같은 제출에서 이름 키가 같은 줄이 여럿이면 같은 항목으로 본다. 같은 상품에 연결한 줄이 여럿일 때와 같은 규칙을 따른다(8.12).
- `kind = whisky`인 항목은 메뉴판에 바로 보이지만, 운영자가 상품에 연결하기 전까지 고객 검색과 인기 위스키에 나오지 않는다(3.9, 3.10.2). 반영과 같은 트랜잭션에서 운영자 확인(3.18, 사유 `unlinked`)을 만든다. `kind = other`인 항목은 상품에 연결하지 않으며 메뉴판에만 보인다.
- 추출 항목에는 `selected_product_id = null`로 저장한다. `finalLineType`이 `product`이므로 `confirm_non_product`와 구분된다. `selectedMatchMethod`와 `matchConfidence`도 `null`이다.
- 반영 응답의 `result`는 다른 항목과 같이 센다. `createdProducts`에는 세지 않는다.

AI가 위스키가 아닌 메뉴로 분류한 줄(5.4의 `extractedKind = other`)은 보통 `kind = other`로 이 결정을 보낸다. 반대로 AI가 위스키로 분류한 줄도 업주가 위스키가 아닌 메뉴로 바꿔 `kind = other`로 보낼 수 있다.

프론트엔드 처리: 게시 완료 화면에서 반영 응답의 `result.unlinkedWhisky`(8.8)가 1 이상이면 "새로 등록한 메뉴는 다음 날부터 위스키 검색에 나와요"를 한 번 보여 준다. 다시 매칭으로 연결이 풀린 줄(8.11)도 여기에 들어가므로, 프론트엔드가 제출한 결정만으로 판단하지 않는다.

### 8.11 이름을 고친 줄의 다시 매칭

업주가 메뉴판 이름을 고치면 서버가 고친 이름으로 다시 매칭한다. 이름이 바뀌었는데 예전 이름으로 정한 연결을 그대로 두면 다른 위스키가 그 상품으로 검색될 수 있기 때문이다. 연결이 바뀌거나 풀리면 운영자 확인(3.18)에 올려, 기계가 바꾼 연결을 사람이 본다.

**대상**: `finalLineType = product`인 줄 중 다음 결정이고, `correctedProductName`을 정규화한 값(7장의 정규화 함수)이 `extractedProductName`을 정규화한 값과 다른 줄이다. 띄어쓰기나 기호만 다르면 다시 매칭하지 않는다. `extractedProductName`이 `null`이면 고친 것으로 본다.

| 결정 | 다시 매칭 |
|---|---|
| `select_existing_product` | 한다. 업주가 후보나 검색에서 직접 고른 상품도 같다 |
| `publish_without_product`, `kind = whisky` | 한다 |
| `publish_without_product`, `kind = whisky`, 그 줄의 `extractedKind = other` | 이름을 고치지 않아도 한다. AI가 위스키가 아닌 메뉴로 보아 처리 단계에서 매칭하지 않았기 때문이다 |
| `publish_without_product`, `kind = other` | 하지 않는다 |
| `create_product` | 하지 않는다. 새 상품의 이름과 별칭을 이 요청이 정하기 때문이다 |

**매칭 방법**: 처리 단계와 같은 규칙 매처(별칭 정확 일치와 단계 규칙 S1, S2, S2b, S3, 매칭 흐름 문서 6장)를 고친 이름 하나로 실행한다. AI가 읽은 브랜드, 연수, 에디션, 도수는 예전 이름에서 나온 값이므로 넣지 않는다. LLM 층과 임베딩 후보 단계는 서버 설정과 관계없이 쓰지 않는다. 제출 요청에서는 AI를 호출하지 않기 때문이다(11).

**결과**:

| 다시 매칭 결과 | 반영 | 운영자 확인 사유 |
|---|---|---|
| 제출한 상품과 같은 상품 하나로 확정(`exact_match`) | 제출한 상품에 연결 | 없음 |
| 다른 상품 하나로 확정 | 확정된 상품에 연결 | `relinked_by_name` |
| 확정하지 못함(`ambiguous`, `unmatched`) | 상품 없는 위스키로 게시(8.10과 같다) | `unlinked_by_name` |
| `publish_without_product`인 줄이 상품 하나로 확정 | 확정된 상품에 연결 | `relinked_by_name` |
| `publish_without_product`인 줄이 확정되지 않음 | 상품 없는 위스키로 게시 | `unlinked`(8.10) |

- 확정된 상품이 비활성이면 확정되지 않은 것으로 본다. 규칙 매처는 활성 상품만 찾는다.
- 연결이 바뀐 줄의 추출 항목에는 최종 상품을 `selected_product_id`에 저장하고 `selectedMatchMethod = manual`, `matchConfidence = null`로 둔다. 사람이 이름을 고쳐 결과가 달라졌기 때문이다. 연결이 풀린 줄은 `publish_without_product`와 같다(8.10).
- `aliasesToAdd`는 제출한 상품이 그대로 연결될 때만 저장한다. 연결이 바뀌거나 풀리면 저장하지 않는다. 운영자가 확인할 때 별칭을 넣는다(3.18.3).
- **원래 항목을 대신한다**: 그 줄이 임시 diff에서 현재 메뉴판의 항목 X와 비교되었고(`update`이거나 변경 없음) 그 변경을 무시하지 않았는데, 다시 매칭으로 X와 다른 상품이 되거나 연결이 풀리면 새 항목이 X의 자리를 대신한다. X는 `remove` 변경 없이도 메뉴판에서 빠지며, 위치와 품절 상태는 새 항목으로 옮긴다(3.14.1의 연결 바꾸기). 업주는 카드 하나를 고쳤으므로 메뉴판에도 한 줄만 남아야 하기 때문이다. 업주가 다른 후보나 검색 결과를 직접 골라 상품이 달라진 경우는 지금처럼 X가 남는다(8.7).
- 다시 매칭으로 같은 상품의 줄이 여럿이 되면 옵션을 합친다(8.12). 그 때문에 같은 표기와 용량에 가격이 부딪치면 거부하지 않고 운영자 확인(3.18, 사유 `price_conflict`)에 올린다(8.12).
- 반영 응답의 `result`는 최종 결과로 센다. 연결이 풀린 줄은 `unlinkedWhisky`에 들어간다(8.8).

### 8.12 같은 상품의 여러 줄

같은 위스키가 메뉴판의 여러 줄에 나오면(잔 메뉴와 보틀 코너, 추천 코너, 두 사진에 찍힌 같은 줄) 게시된 메뉴에는 한 항목만 두고, 모든 줄의 옵션을 모은다. 메뉴판을 섹션으로 나눠 보여 주지 않으므로 같은 위스키가 두 번 보이면 헷갈리지만, 둘째 줄의 가격과 옵션도 실제 판매 정보라 버리면 안 되기 때문이다.

예: "글렌피딕 12 잔 15,000"과 보틀 코너의 "글렌피딕 12 병 180,000"은 잔 15,000과 병 180,000 옵션을 가진 한 항목이 된다.

**같은 항목으로 보는 줄**: 최종 상품이 같은 줄이다. 상품 없이 게시하는 줄은 이름 키(3.14.1)가 같으면 같은 항목이다. 최종 상품은 업주의 결정과 다시 매칭(8.11)을 거친 결과다.

**합치는 규칙**:

- 항목의 메뉴판 이름과 위치는 메뉴 순서(사진 순서, 그 안의 줄 순서)에서 첫 줄의 것이다. 상품 없이 게시하는 줄의 `kind`도 첫 줄의 것이다.
- 옵션은 첫 줄의 옵션, 그다음 줄의 옵션 순서로 이어 붙인다.
- 표기(`optionLabel`)와 용량(`pourMl`)이 같고 가격도 같은 옵션은 하나만 남긴다(같은 메뉴판을 두 번 찍은 경우).
- 합친 옵션은 3개를 넘을 수 있다. 검수 반영에는 옵션 개수 제한이 없다(3.14.2).
- 할인은 지금처럼 표기, 용량, 정가가 같은 옵션에 이어진다(8.7).

**같은 표기와 용량에 가격이 다를 때**:

| 언제 | 처리 |
|---|---|
| 업주가 같은 `productId`로 제출한 줄끼리 부딪침(다시 매칭으로 상품이 바뀌지 않은 줄) | 거부한다. `422 VALIDATION_FAILED`이고, 부딪친 옵션마다 `fieldErrors[].path`가 뒤에 오는 줄의 그 옵션(`itemDecisions[i].options[j]`), `code = OPTION_PRICE_CONFLICT`다. 아무것도 반영하지 않는다. 프론트엔드가 `productId`로 미리 묶어 막을 수 있는 충돌이다 |
| 다시 매칭(8.11) 때문에 같은 상품이 된 줄끼리 부딪침 | 거부하지 않는다. 업주는 이 충돌을 화면에서 볼 수 없었기 때문이다. 이름을 고치지 않은 줄의 가격을 쓰고, 둘 다 고쳤으면 메뉴 순서가 앞선 줄의 가격을 쓴다. 합친 항목을 운영자 확인(3.18, 사유 `price_conflict`)에 올린다 |
| 상품 없이 게시하는 줄끼리 이름 키가 같아 부딪침 | 거부하지 않는다. 이름 키는 서버의 정규화 함수로 계산하므로 프론트엔드가 같은 묶음을 미리 알 수 없기 때문이다(예: "글렌알라키 10 CS"와 "글렌알라키10CS"). 메뉴 순서가 앞선 줄의 가격을 쓴다. `kind = whisky`이면 합친 항목의 열린 확인(3.18)에 사유 `price_conflict`를 더하고, `kind = other`이면 확인을 만들지 않는다 |

**프론트엔드 처리**: 같은 `productId`로 제출하는 줄의 충돌은 프론트엔드가 제출 전에 막는다는 전제다. 서버의 `OPTION_PRICE_CONFLICT`는 그 전제가 깨졌을 때의 안전장치다.

- 검수 화면은 같은 상품으로 정해진 카드를 "같은 위스키가 두 줄 있어 하나로 합쳤어요"로 묶고, 합친 옵션을 보여 준다. 상품 없이 게시하는 줄은 메뉴판 이름이 똑같은 카드만 묶어 보여 줄 수 있으며, 서버는 정규화한 이름 키로 더 넓게 합칠 수 있다(위 표의 셋째 줄). 같은 상품의 줄은 임시 diff 변경의 `extractedItemIds`(5.4)로도 알 수 있다. 업주가 후보나 검색에서 상품을 고르면 그 결과로 다시 묶는다.
- 같은 표기와 용량에 가격이 다른 옵션이 있으면 업주가 하나를 고르게 하고, 고르기 전에는 게시 버튼을 막는다. 고르지 않은 옵션은 그 줄의 `options`에서 빼고 제출한다(8.1).
- 묶인 카드는 서로 다른 위스키가 같은 상품으로 잘못 매칭된 것을 업주가 알아챌 기회이기도 하다. 업주가 한 줄의 상품을 바꾸면 묶음에서 빠진다.
- 그래도 `OPTION_PRICE_CONFLICT`를 받으면 해당 카드의 묶음을 열어 다시 고르게 한다.

**임시 diff와 검수 응답**: 처리 단계의 임시 diff(5.4)도 같은 상품을 제안받은 줄을 합쳐 변경 하나로 만든다. 변경의 `after.options`는 합친 옵션이고, `extractedItemIds`는 합친 모든 줄이다. `apply`는 담긴 줄 중 하나라도 메뉴 항목으로 게시하면 할 수 있다(8.7). 그 변경을 `ignore`하면 담긴 줄 중 최종 결정이 여전히 이 변경의 대상(같은 상품, 상품이 없으면 같은 이름 키)인 줄은 메뉴판을 바꾸지 않는다. 검수자가 다른 상품을 고르거나 이름을 고쳐 대상이 달라진 줄은 그 결정대로 반영한다(8.7).

## 9. 오류 응답

### 9.1 공통 형식

```json
{
  "error": {
    "code": "REVIEW_OUTDATED",
    "message": "검수 데이터가 변경되었습니다. 최신 내용을 다시 확인해 주세요.",
    "details": {
      "menuImportId": "77777777-7777-4777-8777-777777777777",
      "submittedReviewVersion": 2,
      "currentReviewVersion": 3,
      "reviewUrl": "/api/menu-imports/77777777-7777-4777-8777-777777777777"
    },
    "fieldErrors": []
  }
}
```

API가 보내는 오류는 예상하지 못한 서버 오류(`500 INTERNAL_ERROR`)까지 모두 이 형식이다. API 앞단의 프록시나 네트워크에서 생긴 오류는 예외이며 9.6을 따른다.

`error.message`는 사용자 표시가 가능한 한국어 기본 문구다. 프론트엔드는 분기 처리에 `message`가 아니라 `code`를 사용한다. `fieldErrors[].message`는 9.3처럼 영어일 수 있으므로, 프론트엔드는 필드 오류를 표시할 때 `code`를 기준으로 자체 문구를 보여 준다.

### 9.2 주요 오류 코드

| HTTP | code | 발생 조건 | 프론트엔드 처리 |
|---|---|---|---|
| `400` | `INVALID_REQUEST` | JSON 또는 multipart 형식 오류 | 요청 구성 확인 |
| `401` | `UNAUTHENTICATED` | 토큰 없음, 만료, 서명·claim 오류 (3.1.5) | 세션 갱신 후 한 번 재시도. 실패하면 로그인 이동 |
| `403` | `FORBIDDEN` | 권한이 없는 API 호출: operator 전용 API, 업주가 아닌 업장·작업의 관리 API, 업주의 `status` 변경 (2.2) | 접근 차단 |
| `404` | `BAR_NOT_FOUND` | 업장이 없음, `barId` 형식 오류, operator나 업주가 아닌 호출자의 비활성 업장 조회 (3.6, 3.9) | 안내 후 이전 화면 이동 |
| `404` | `OWNER_APPLICATION_NOT_FOUND` | 업주 신청이 없거나 조회 권한이 없음 (3.11) | 신청 목록 재조회 |
| `404` | `BAR_OWNER_NOT_FOUND` | 업주 해제 대상 업장에 현재 업주가 없음 (3.11.10) | 업장 상세 재조회 |
| `404` | `MENU_IMPORT_NOT_FOUND` | 등록 작업이 없음 | 작업 목록 이동 |
| `404` | `MENU_ITEM_NOT_FOUND` | 직접 수정, 삭제할 항목이 현재 메뉴판에 없음. `details.barMenuItemId` (3.14) | 메뉴 다시 조회 |
| `404` | `MENU_ITEM_CHECK_NOT_FOUND` | 운영자가 처리할 메뉴 항목 확인이 없음. `details.checkId` (3.18.3) | 확인 목록 다시 조회 |
| `404` | `PHOTO_NOT_FOUND` | 삭제하거나 조회할 매장 사진이 없음. `details.photoId` (3.16) | 업장 상세 다시 조회 |
| `404` | `USER_NOT_FOUND` | `GET /api/me`로 사용자를 만들기 전에 `PATCH /api/me`, `POST /api/owner-applications`, 업주 신청 승인과 거절(3.11.7, 3.11.8), 업주 해제(3.11.10) 호출 | `GET /api/me` 호출 후 같은 요청 재시도 |
| `404` | `NOT_FOUND` | 존재하지 않는 경로, 또는 비활성화된 임시 로그인 호출 | 요청 경로·서버 설정 확인 |
| `405` | `METHOD_NOT_ALLOWED` | 경로는 있지만 허용하지 않는 HTTP 메서드 | 요청 메서드 확인 |
| `409` | `BAR_OWNER_EXISTS` | 이미 현재 업주가 있는 업장에 신청 또는 승인 (3.11) | 안내. operator는 해당 신청을 거절 |
| `409` | `OWNER_APPLICATION_EXISTS` | 같은 업장, 또는 같은 사업자등록번호의 `new_bar`에 본인의 대기 중 신청이 있음 (3.11.2) | `details.applicationId`의 신청으로 이동 |
| `409` | `INVALID_APPLICATION_STATE` | `pending`이 아닌 신청의 승인·거절·취소·다시 검증, 사진 변경 (3.11) | 신청 상세 재조회 |
| `409` | `INVALID_APPLICATION_TYPE` | `existing_bar` 신청에 대표 사진을 올리거나 지움. `details.applicationType` (3.11.17) | 기존 업장의 사진은 승인 뒤 3.16으로 올림 |
| `409` | `IDEMPOTENCY_KEY_REUSED` | 같은 키에 다른 요청 내용 | 새 키로 명시적 재요청 |
| `409` | `ACTIVE_IMPORT_EXISTS` | 업장에 미완료 작업이 이미 있는데 새 작업을 올리거나(4.4) 메뉴를 직접 편집하거나(3.14) 운영자가 메뉴 항목 확인을 처리함(3.18.3). `details.menuImportId`, `details.status` | 기존 작업으로 이동하거나 취소(5.7) 후 다시 요청 |
| `409` | `MENU_OUTDATED` | 직접 편집이나 판매 정보 확인(3.14.9) 요청의 `menuVersion`이 현재 메뉴판 버전과 다름. `details.submittedMenuVersion`, `details.currentMenuVersion` (3.14) | 메뉴 다시 조회 후 다시 저장 |
| `409` | `NO_PUBLISHED_MENU` | 판매 정보 확인(3.14.9)을 했는데 메뉴판이 없거나 항목이 없음 | 메뉴 등록으로 안내 |
| `409` | `MENU_ITEM_EXISTS` | 직접 추가하려는 상품, 또는 이름 키가 같은 미연결 항목이 이미 현재 메뉴판에 있음(3.14.3). 미연결 항목의 이름을 다른 미연결 항목과 같게 바꿈(3.14.4). `details.barMenuItemId` | 그 항목 수정으로 안내 |
| `409` | `PHOTO_EXISTS` | 내용이 같은 매장 사진이 이미 있음. `details.photoId` (3.16.2) | 이미 등록된 사진이라고 안내하고 사진 목록 다시 조회 |
| `409` | `PHOTO_LIMIT_REACHED` | 매장 사진이 이미 15장. `details.maxPhotos` (3.16.2) | 사진을 지운 뒤 추가하라고 안내 |
| `409` | `PHOTOS_OUTDATED` | 순서 변경에 보낸 사진 ID가 현재 사진과 다름. `details.photos` (3.16.4) | `details.photos`로 화면을 바꾸고 다시 정렬하게 함 |
| `409` | `INVALID_CHECK_STATE` | 이미 `resolved` 또는 `dismissed`인 메뉴 항목 확인을 처리함. `details.checkId`, `details.status` (3.18.3) | 확인 목록 다시 조회 |
| `409` | `INVALID_IMPORT_STATE` | 현재 상태에서 요청 불가. 예: `ready_for_review`가 아닌 작업의 검수 제출, `applied`·`failed` 작업의 취소. `details.menuImportId`, `details.status`에 현재 상태 | 상태 재조회 |
| `409` | `REVIEW_DRAFT_OUTDATED` | 검수 초안 저장(5.9)의 `draftVersion`이 현재 초안 버전과 다름. `details.currentDraftVersion`, `details.savedAt`, `details.reviewUrl` | 최신 검수 응답을 다시 받아 어느 초안을 쓸지 고르게 함 |
| `409` | `REVIEW_OUTDATED` | `reviewVersion` 불일치, 또는 검수 데이터를 만든 뒤 현재 메뉴판이 바뀜 | `details.reviewUrl`로 최신 검수 데이터 재조회 |
| `409` | `DUPLICATE_BRAND_FOUND` | 신규 브랜드와 동일할 수 있는 브랜드 발견 (검수 또는 직접 추가) | 기존 브랜드 선택 화면 표시 |
| `409` | `DUPLICATE_PRODUCT_FOUND` | 신규 상품과 동일한 상품 발견, 또는 제출한 이름·별칭이 기존 상품의 별칭과 일치 | 기존 상품 선택 화면 표시. 다른 상품이면 겹치는 별칭을 빼고 다시 제출. `existingProduct.isActive = false`이면 상품 검색으로 안내 (9.5) |
| `413` | `REVIEW_DRAFT_TOO_LARGE` | 검수 초안(5.9)의 `content`가 256KB를 넘음. `details.maxBytes` | 기기에만 저장하고 서버 저장을 멈춤 |
| `413` | `UPLOAD_TOO_LARGE` | 파일 개수 또는 크기 초과 | 이미지 축소 또는 개수 조정 |
| `415` | `UNSUPPORTED_IMAGE_TYPE` | 지원하지 않는 이미지 형식 | 지원 형식 안내 |
| `422` | `VALIDATION_FAILED` | 필드 값이나 옵션 구성이 잘못됨 | `fieldErrors` 표시 |
| `422` | `BUSINESS_VERIFICATION_FAILED` | 업주 신청의 사업자등록번호, 대표자명, 개업일자가 국세청 정보와 맞지 않음 (3.11.2) | 입력값을 유지한 채 수정 안내 |
| `429` | `RATE_LIMITED` | 진위확인(업주 신청과 신청 전 확인 합산) 또는 사업자등록증 OCR을 오늘 5회 했음. `details.retryAfter`에 다음 초기화 시각 (3.11.14) | 내일 다시 시도 안내. OCR은 직접 입력 안내 |
| `503` | `OCR_UNAVAILABLE` | 사업자등록증 사진을 읽는 OCR 설정이 없거나 호출 실패 (3.11.12) | 직접 입력 안내 |
| `503` | `BUSINESS_VERIFICATION_UNAVAILABLE` | operator의 다시 검증에서 국세청 API에 연결하지 못함 (3.11.13) | 잠시 후 재시도 안내 |
| `500` | `BUSINESS_NUMBER_UNREADABLE` | operator의 다시 검증에서 저장된 사업자등록번호를 복호화하지 못함 (3.11.13) | 서버 키 설정 문제라고 안내. 재시도하지 않음 |
| `503` | `TEMPORARY_WRITE_CONFLICT` | 직렬화 충돌 3회 재시도 실패 (검수 제출, 메뉴 직접 편집) | 잠시 후 같은 요청 재시도 |
| `500` | `INTERNAL_ERROR` | 예상하지 못한 서버 오류(DB 연결 실패, 코드 오류 등). 모든 API에서 생길 수 있다. 원인은 응답에 담지 않고 서버 로그에만 남긴다 | 잠시 후 재시도 안내 |
| `503` | `SERVICE_UNAVAILABLE` | 서버의 인증 설정 누락 또는 오류, Supabase JWKS 조회 실패 (3.1.5) | 잠시 후 재시도 안내. 로그인 화면으로 보내지 않음 |

- `400 INVALID_REQUEST`는 JSON 본문을 읽을 수 없거나 multipart 본문의 구조(경계 문자열 등)가 깨졌을 때이며 `fieldErrors`는 비어 있다. JSON으로 읽었지만 필드 값이 규칙에 맞지 않으면 `422 VALIDATION_FAILED`다. 끝이 잘린 multipart 본문은 읽을 수 있는 부분까지만 읽히므로, 빠진 필드가 `422`의 `MISSING`으로 나올 수 있다. 서버는 요청 본문을 다른 검사보다 먼저 읽으므로, 이 오류는 인증(`401`)과 각 API의 확인 순서보다 먼저 나온다. 앱이 만든 요청에서는 생기지 않으므로 앱 버그로 본다.
- 라우팅이나 인증 단계에서 생긴 HTTP 오류 중 위 표에 없는 상태 코드도 같은 공통 형식으로 반환한다. 없는 경로는 `404 NOT_FOUND`, 경로는 있지만 메서드가 다르면 `405 METHOD_NOT_ALLOWED`, 그 밖은 `code = HTTP_ERROR`다. 프론트엔드는 HTTP 상태 코드 기준의 일반 오류 메시지를 보여 준다.

### 9.3 필드 검증 오류 예시

```json
{
  "error": {
    "code": "VALIDATION_FAILED",
    "message": "입력값을 확인해 주세요.",
    "details": null,
    "fieldErrors": [
      {
        "path": "itemDecisions[0].options[1].priceKrw",
        "code": "GREATER_THAN",
        "message": "Input should be greater than 0"
      }
    ]
  }
}
```

`fieldErrors`의 `code`와 `message`는 두 종류다.

- **요청 형식 검증**(필수값, 길이, 숫자 범위, 허용 값 등): Pydantic 오류 종류를 대문자로 바꾼 값을 `code`로 쓴다. 예: `MISSING`, `STRING_TOO_LONG`, `STRING_TOO_SHORT`, `TOO_SHORT`, `TOO_LONG`, `GREATER_THAN`, `GREATER_THAN_EQUAL`, `LESS_THAN_EQUAL`, `LITERAL_ERROR`, `UUID_PARSING`, `INT_PARSING`, `FLOAT_PARSING`, `BOOL_TYPE`, `DATE_TYPE`, `DATE_FROM_DATETIME_PARSING`, `EXTRA_FORBIDDEN`, `UNION_TAG_NOT_FOUND`, `UNION_TAG_INVALID`, `TIMEZONE_AWARE`. `message`는 Pydantic의 영어 기본 문구다.
- **업무 규칙 검증**: 백엔드가 정한 `code`와 한국어 `message`를 쓴다. 예: `BLANK`, `NOT_SEARCHABLE`, `LAT_LNG_REQUIRED_TOGETHER`, `INVALID_CURSOR`, `MISSING_ITEM`, `DUPLICATE_ITEM`, `UNKNOWN_ITEM`, `MISSING_CHANGE`, `DUPLICATE_CHANGE`, `UNKNOWN_CHANGE`, `UNKNOWN_OPTION`, `DUPLICATE_OPTION`, `DUPLICATE_OPTION_VALUES`, `EXACTLY_ONE_REQUIRED`, `PRODUCT_NOT_FOUND`, `PRODUCT_INACTIVE`, `BRAND_NOT_FOUND`, `CHANGE_WITHOUT_PRODUCT`, `NOT_NORMALIZABLE`, `INVALID_BUSINESS_NUMBER`, `DATE_IN_FUTURE`, `COORDINATES_REQUIRED`, `BOUNDS_INVERTED`, `BOUNDS_TOO_LARGE`, `INVALID_CHARACTER`, `DUPLICATE_TAG`, `DUPLICATE_DAY`, `INVALID_TIME`, `SAME_OPEN_CLOSE`, `TIME_ON_CLOSED_DAY`, `DATE_IN_PAST`, `DATE_NOT_TODAY`, `END_BEFORE_START`, `IMAGE_DIMENSIONS_TOO_LARGE`, `DISCOUNT_NOT_LOWER`, `DISCOUNT_ENDED`, `RESOLUTION_NOT_ALLOWED`, `OPTION_PRICE_CONFLICT`.

### 9.4 검수 버전 충돌

`REVIEW_OUTDATED`가 발생하면 최종 반영은 전부 롤백된다. 서버에 저장된 검수 초안(5.9)은 지우지 않는다. 프론트엔드는 사용자의 로컬 입력을 즉시 버리지 말고 최신 검수 응답을 받은 뒤 항목 ID 기준으로 재적용 가능한 수정값을 보여줄 수 있다. 사용자는 바뀐 diff를 확인하고 다시 제출해야 한다.

### 9.5 신규 브랜드와 상품 중복 발견

```json
{
  "error": {
    "code": "DUPLICATE_PRODUCT_FOUND",
    "message": "동일한 상품이 먼저 등록되었습니다.",
    "details": {
      "extractedItemId": "10000000-0000-4000-8000-000000000007",
      "existingProduct": {
        "productId": "bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbb2",
        "displayName": "Deanston Virgin Oak",
        "brandId": "dddddddd-dddd-4ddd-8ddd-ddddddddddd1",
        "brandName": "Deanston",
        "category": "whisky",
        "ageYears": null,
        "editionName": "Virgin Oak",
        "isActive": true
      },
      "reviewUrl": "/api/menu-imports/77777777-7777-4777-8777-777777777777"
    },
    "fieldErrors": []
  }
}
```

| 필드 | 타입 | null 가능 | 설명 |
|---|---|---|---|
| `extractedItemId` | UUID 문자열 | 아니오 | 중복이 난 검수 항목. 직접 추가(3.14.3)에는 없다 |
| `existingProduct.productId`, `displayName`, `brandId`, `brandName`, `category` | 7.2와 같다 | 아니오 | 이미 있는 상품 |
| `existingProduct.ageYears`, `editionName` | 7.2와 같다 | 예 | |
| `existingProduct.isActive` | 불리언 | 아니오 | 활성 상품인지. `false`이면 그 상품을 고를 수 없다(`PRODUCT_INACTIVE`) |
| `reviewUrl` | 문자열 | 아니오 | 검수 데이터 경로. 직접 추가에는 없다 |

중복 검사는 비활성 상품도 대상으로 한다(같은 상품을 다시 만들지 않기 위해서다). 제출한 이름이나 별칭이 여러 상품에 걸리면 활성 상품을 먼저 돌려준다. 비활성 상품은 대부분 잘못 만들어져 정리된 중복이고, 실제 상품은 따로 활성 상태로 있기 때문이다.

프론트엔드 처리:

- `isActive = true`: 기존 상품을 보여 주고, 맞으면 그 상품을 선택해(검수는 `select_existing_product`, 직접 추가는 `productId`) 다시 제출한다. 다른 상품이면 겹치는 별칭을 빼고 다시 제출한다.
- `isActive = false`: 그 상품으로 다시 제출하지 않는다. 이미 정리된 상품과 이름이 겹친다고 안내하고 상품 검색(7)에서 고르게 한다. 검색에도 없으면 operator 문의를 안내한다(7.2).

신규 브랜드가 기존 브랜드와 같으면 `409 DUPLICATE_BRAND_FOUND`다.

```json
{
  "error": {
    "code": "DUPLICATE_BRAND_FOUND",
    "message": "같은 브랜드가 이미 등록되어 있습니다. 기존 브랜드를 선택해 주세요.",
    "details": {
      "extractedItemId": "10000000-0000-4000-8000-000000000009",
      "existingBrand": {
        "brandId": "dddddddd-dddd-4ddd-8ddd-ddddddddddd1",
        "canonicalName": "Deanston"
      },
      "reviewUrl": "/api/menu-imports/77777777-7777-4777-8777-777777777777"
    },
    "fieldErrors": []
  }
}
```

| 필드 | 타입 | null 가능 | 설명 |
|---|---|---|---|
| `extractedItemId`, `reviewUrl` | | 아니오 | 상품 중복과 같다. 직접 추가에는 없다 |
| `existingBrand.brandId` | UUID 문자열 | 아니오 | 이미 있는 브랜드 |
| `existingBrand.canonicalName` | 문자열 | 아니오 | 대표 브랜드명 |

프론트엔드는 기존 브랜드를 보여 주고, 맞으면 `brand`를 `{"type": "existing", "brandId": ...}`로 바꿔 다시 제출한다. 브랜드에는 비활성 상태가 없다.

두 오류 모두 아무것도 만들지 않는다. 검수에서는 `menuImport`가 `ready_for_review`를 유지하고, 직접 추가에서는 메뉴판이 바뀌지 않는다.

### 9.6 API가 만들지 않은 오류

다음 오류는 API가 만든 응답이 아니므로 9.1 형식이 아닐 수 있다. 프론트엔드는 응답 본문을 9.1 형식으로 읽지 못하면 `message`를 쓰지 않고 HTTP 상태나 오류 종류로 판단한다.

| 상황 | 클라이언트가 받는 것 | 프론트엔드 처리 |
|---|---|---|
| 기기가 오프라인이거나, 연결·응답 시간이 초과됨 | 응답 없음 | 네트워크 연결 확인 안내와 재시도 |
| API 프로세스가 멈췄거나 다시 시작하는 중 | 프록시(Caddy)의 `502` 또는 `504`. 본문이 비어 있거나 JSON이 아니다 | 서버 오류로 보고 잠시 후 재시도 안내 |
| 요청 본문이 프록시 한도(65MB)를 넘음 | 프록시의 `413`. JSON이 아니다 | `413 UPLOAD_TOO_LARGE`(4.4)와 같게 사진 수나 크기를 줄이도록 안내. 정상적인 업로드는 API의 한도(전체 60MB)에 먼저 걸린다 |
| 응답 본문이 기대한 JSON이 아님 | `2xx`이지만 해석할 수 없는 본문 | 네트워크 오류가 아니라 서버 응답 오류로 보고 재시도 안내 |

서버 오류 문구에는 서버가 보낸 원문이나 HTTP 상태 번호를 그대로 노출하지 않는다.

## 10. 프론트엔드 상태 처리 기준

```text
uploaded 또는 processing
→ 로딩 화면
→ pollAfterMs 후 GET 재호출
→ 오래 진행되지 않으면 취소(5.7) 후 새 업로드를 고를 수 있게 함

ready_for_review
→ images, items, candidates, proposedChanges로 통합 검수 화면 구성

failed
→ failure 메시지 표시
→ 사용자가 새 업로드 작업을 시작하도록 안내

applied
→ 반영 완료 화면
→ 현재 메뉴판으로 이동 가능

canceled
→ 취소된 작업임을 표시
→ 새 업로드 작업을 시작할 수 있음
```

프론트엔드는 `proposedProductId`나 `proposedChanges`를 확정값으로 취급하지 않는다. 실제 반영 기준은 `review-and-apply`에 제출한 결정과 백엔드의 최종 재검증 결과다.

## 11. 구현 시 고정할 계약

- 프론트엔드는 `normalizedAlias`를 생성하거나 제출하지 않는다.
- 프론트엔드는 후보 점수만으로 상품을 자동 확정하지 않는다.
- 백엔드는 한 `extractedItemId`에 같은 `productId` 후보를 중복 반환하지 않는다.
- `extractedLineType`과 `initialResolutionStatus`는 최초 시스템 판단이므로 검수 제출로 덮어쓰지 않는다.
- 프론트엔드는 표시와 입력 초기값에 `effectiveLineType`을 사용하고, 최종 결정은 `finalLineType`으로 제출한다.
- 후보 `evidence`에 새 키가 추가되어도 프론트엔드가 깨지지 않아야 한다.
- 임시 diff는 최신 버전만 유효하다.
- 모든 변경 요청은 현재 `reviewVersion`을 포함한다.
- `review-and-apply` 성공 전에는 카탈로그와 현재 메뉴판이 변경되지 않는다. 검수 초안 저장(5.9)도 바꾸지 않는다.
- 검수 초안의 `content`는 서버가 해석하지 않는다. 결정의 형식은 제출(8.1)과 같고, `clientState`는 저장한 클라이언트만 해석한다.
- 최종 요청에서 AI를 다시 호출하지 않는다. 이름을 고친 줄의 다시 매칭(8.11)은 규칙 매처만 쓴다.
- 최종 요청은 부분 성공하지 않는다. 하나라도 실패하면 전체 롤백한다.
- 메뉴 직접 편집(3.14)은 항목을 `barMenuItemId`로만 가리킨다. `menuBoardEntryId`와 `menuEntryOptionId`는 메뉴판이 바뀌면 달라질 수 있다.
- 메뉴 직접 편집 요청은 모두 조회한 `menuVersion`을 포함하며, 업장에 미완료 메뉴 등록 작업이 있으면 받지 않는다. 품절 표시(3.14.8)와 판매 정보 확인(3.14.9)은 예외로 검수 중에도 받는다.
- 고객 검색은 서울 날짜별 집계(3.10.6)로만 센다. 집계에는 검색어 원문, 검색 시각, 위치, 사용자, IP, 기기 정보를 남기지 않으며(서버 접근 로그에는 위치를 뺀 검색어가 남는다), 인식하지 못한 검색어만 보호 규칙을 거쳐 정규화한 형태로 30일 동안 남긴다. 최근 검색 목록은 앱이 기기에만 저장한다.
- 홈 화면의 카드는 3.10을 `productId`로 검색한다. `query`와 `productId`는 함께 보낼 수 없다.
- "요즘 많이 찾는 위스키"(3.17)의 `barCount`는 고객 검색(3.10)에 나오는 업장 수와 같은 규칙으로 센다. 검색 수는 응답에 넣지 않는다.
- 메뉴 항목은 상품에 연결되지 않을 수 있다(3.9). 이때 `productId`, `productName`, `brandId`, `brandName`, `category`는 `null`이고, 프론트엔드는 `displayName`으로 보여 준다. 상품에 연결되지 않은 항목은 고객 검색(3.10)과 인기 위스키(3.17)에 나오지 않는다.
- 품절 항목은 손님(비로그인 사용자와 customer)의 3.9와 고객 검색(3.10)에서 빠진다. operator와 해당 업장의 업주만 3.9에서 `soldOut = true`로 받는다.
- 할인 중인지는 프론트엔드가 `discount.startsAt`, `endsAt`과 현재 시각으로 계산한다. `priceKrw`는 항상 정가다.
- `summary`나 사용자 표시 문자열을 서버 검증 기준으로 사용하지 않는다.
- 매장 태그와 정규 영업시간은 업장 수정(3.7)에서 배열 전체를 바꾼다. 일부만 바꾸는 요청은 없다.
- 영업 상태는 서버가 계산하지 않는다. 프론트엔드가 3.15.5의 규칙으로 계산한다. `operatingException`은 `endDate` 다음 날까지 응답에 남으므로, 지금 적용 중인지도 프론트엔드가 판단한다(3.15.4).
- 매장 사진의 `imageUrl`과 `thumbnailUrl`은 만료되지 않는 고정 URL이며, 프론트엔드는 URL을 직접 만들지 않는다. 대표 사진은 `photos`의 첫 항목이며, 업장 목록 API에서는 `coverThumbnailUrl`(사진이 없으면 `null`)이다.
