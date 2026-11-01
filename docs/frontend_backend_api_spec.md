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
- 모든 검수 결정의 일괄 제출과 메뉴 반영
- 현재 메뉴판 항목의 직접 추가, 수정, 삭제와 초기화, 품절, 기간 할인, 판매 정보 확인
- 매장 정보(한 줄 소개, 태그, 정규 영업시간), 임시 휴무, 매장 사진
- 고객의 상품 검색, 주변·지도 업장 조회와 업장 상세 메뉴 조회
- 멱등성, 검수 버전 충돌과 공통 오류 응답

제외 범위:

- 백엔드와 OCR·LLM·Vision LLM 사이의 요청
- 백엔드와 국세청 사업자등록정보 API 사이의 요청
- 작업 큐와 AI 워커 내부 통신
- 운영자용 카탈로그 일반 CRUD
- 중간 검수 결과 자동 저장
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
| `GET /api/search/bars`, `GET /api/search/nearby-bars`, `GET /api/search/map-bars`, `GET /api/search/bar-names` | O | O | O | O |
| `GET /api/bars/{barId}/menu` | 활성 업장만 | 활성 업장만 | O | O |
| `GET /api/bar-photos/{photoId}`, `GET /api/bar-photos/{photoId}/thumbnail` | O | O | O | O |
| `GET /api/me`, `PATCH /api/me`, `GET /api/me/bars` | | O | O | O |
| `POST /api/owner-applications`, `GET /api/me/owner-applications`, `POST /api/owner-applications/business-certificate-ocr` | | O | O | O |
| `GET /api/owner-applications/{applicationId}` | | 본인 신청만 | 본인 신청만 | O |
| `POST /api/owner-applications/{applicationId}/cancel`, `PUT /api/owner-applications/{applicationId}/menu-photos` | | 본인 신청만 | 본인 신청만 | 본인 신청만 |
| `GET /api/owner-applications`, `POST .../approve`, `POST .../reject`, `POST .../verify-business` | | | | O |
| `DELETE /api/bars/{barId}/owner` | | | | O |
| `GET /api/bars`, `POST /api/bars` | | | | O |
| `GET /api/bars/{barId}` | | | O | O |
| `PATCH /api/bars/{barId}` | | | O (`status` 제외) | O |
| `GET /api/bars/{barId}/menu-imports`, `POST /api/bars/{barId}/menu-imports` | | | O | O |
| `POST /api/bars/{barId}/menu/items`, `PUT .../menu/items/{barMenuItemId}`, `DELETE .../menu/items/{barMenuItemId}`, `POST /api/bars/{barId}/menu/reset` | | | O | O |
| `PUT /api/bars/{barId}/menu/items/{barMenuItemId}/sold-out`, `POST /api/bars/{barId}/menu/confirm` | | | O | O |
| `PUT /api/bars/{barId}/operating-exception`, `DELETE /api/bars/{barId}/operating-exception` | | | O | O |
| `POST /api/bars/{barId}/photos`, `DELETE .../photos/{photoId}`, `PUT .../photos/order` | | | O | O |
| `GET /api/menu-imports/{menuImportId}`, `POST .../review-and-apply`, `POST .../cancel` | | | 해당 업장의 작업만 | O |
| `GET /api/catalog/brands`, `GET /api/catalog/products` | | | 업장이 하나 이상이면 O | O |
| `POST /api/auth/temp-login` | 임시 로그인이 켜진 서버에서만 O (3.1.3) | 같음 | 같음 | 같음 |
| `GET /health` | O | O | O | O |

`/media/{key}`는 로컬 저장소를 쓰는 개발 환경에서만 있는 사진 파일 경로이며 API 계약이 아니다. 배포 서버(S3)에는 없다. 매장 사진은 이 경로가 아니라 `GET /api/bar-photos/{photoId}`와 `GET /api/bar-photos/{photoId}/thumbnail`(3.16.5)로 전달하며, 이 경로는 모든 환경에 있다.

인증이 필요한 요청에서 백엔드는 다음 순서로 검증한다.

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

## 3. API 요약

| 메서드 | 경로 | 용도 |
|---|---|---|
| `POST` | `/api/auth/temp-login` | 로컬 개발용 임시 access token 발급 (기본 비활성화) |
| `GET` | `/api/me` | 로그인 사용자와 권한 조회 및 최초 사용자 동기화 |
| `PATCH` | `/api/me` | 로그인 사용자 표시 이름 수정 |
| `GET` | `/api/bars` | 운영 대상 업장 목록 및 검색 |
| `POST` | `/api/bars` | 업장 생성 |
| `GET` | `/api/bars/{barId}` | 관리자용(operator, 업주) 업장 상세와 관리 상태 조회 |
| `PATCH` | `/api/bars/{barId}` | 업장 정보 또는 활성 상태 수정 |
| `GET` | `/api/bars/{barId}/menu-imports` | 업장의 진행 중·과거 메뉴 등록 작업 조회 |
| `GET` | `/api/bars/{barId}/menu` | 업장 정보와 현재 게시 메뉴판 조회 (공개) |
| `GET` | `/api/search/bars` | 고객 상품 검색과 판매 업장 목록 조회 (공개) |
| `GET` | `/api/search/nearby-bars` | 고객 위치 반경 안의 활성 업장 조회 (공개) |
| `GET` | `/api/search/map-bars` | 지도 화면 영역 안의 활성 업장 조회 (공개) |
| `POST` | `/api/bars/{barId}/menu-imports` | 사진 업로드와 AI 처리 작업 생성 |
| `GET` | `/api/menu-imports/{menuImportId}` | 처리 상태 또는 통합 검수 데이터 조회 |
| `GET` | `/api/catalog/brands` | 검수 중 기존 브랜드 검색 |
| `GET` | `/api/catalog/products` | 검수 중 기존 상품 검색 |
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
| `POST` | `/api/owner-applications` | 업주 신청과 사업자등록 정보 1차 검증 |
| `GET` | `/api/me/owner-applications` | 내 업주 신청 목록 |
| `GET` | `/api/owner-applications/{applicationId}` | 업주 신청 상세 |
| `POST` | `/api/owner-applications/{applicationId}/cancel` | 업주 신청 취소 |
| `PUT` | `/api/owner-applications/{applicationId}/menu-photos` | 업주 신청의 메뉴판 사진 올리기 (전체 교체) |
| `GET` | `/api/owner-applications` | operator의 업주 신청 목록 |
| `POST` | `/api/owner-applications/{applicationId}/approve` | 업주 신청 승인 |
| `POST` | `/api/owner-applications/{applicationId}/reject` | 업주 신청 거절 |
| `POST` | `/api/owner-applications/{applicationId}/verify-business` | 사업자등록 정보 다시 검증 |
| `GET` | `/api/me/bars` | 내가 업주인 업장 목록 |
| `DELETE` | `/api/bars/{barId}/owner` | 업주 해제 |

별도의 신규 브랜드·상품 생성 API는 두지 않는다. 신규 카탈로그 데이터는 `review-and-apply` 요청(8.5, 8.6)이나 메뉴 항목 직접 추가 요청(3.14.3) 안에서 제안하고, 그 요청의 트랜잭션에서 생성한다.

### 3.1 로그인과 토큰 검증

BottleMap은 로그인 API를 직접 제공하지 않는다. Google 로그인과 토큰 발급·갱신·로그아웃은 Supabase Auth의 Google provider와 Supabase SDK가 담당하고, BottleMap 백엔드는 Supabase가 발급한 access token을 검증만 한다. `users`에는 비밀번호 컬럼이 없고, Supabase 사용자 ID(token의 `sub`)를 `auth_subject`에 저장한다.

사용자는 다음과 같이 구분한다.

- **비로그인 사용자(익명 사용자)**: 로그인하지 않은 사용자다. `Authorization` 헤더 없이 공개 API(`GET /api/search/bars`, `GET /api/search/nearby-bars`, `GET /api/search/map-bars`, `GET /api/search/bar-names`, `GET /api/bars/{barId}/menu`, `GET /api/bar-photos/{photoId}`와 그 `/thumbnail`)만 호출하며 `users` 행을 만들지 않는다.
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

Supabase 연동 전과 로컬 개발을 위해 `POST /api/auth/temp-login`을 유지한다. 이 API는 명시적으로 활성화해야 하며, 고정된 `local-dev-user` subject로 짧은 만료 시간의 HS256 JWT를 발급한다. 이 token은 Supabase access token이 아니다.

배포 서버에서는 앱에서 Google 로그인이 가능해질 때까지만 데모용으로 켜 둘 수 있고, Google 로그인이 가능해지면 끈다(`TEMP_AUTH_ENABLED=false`). 켜져 있는 동안에는 서버에 접근하는 누구나 같은 임시 계정을 공유하며, `TEMP_AUTH_USER_TYPE=operator`이면 operator 권한을 얻는다. 켜져 있는 동안 서버는 시작할 때마다 경고 로그를 남긴다. 끄는 절차는 `backend/DEPLOY.md`를 따른다.

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
- `GET /api/me`만 사용자를 생성한다. `users` 행이 없는 사용자가 다른 인증 API를 먼저 호출하면 `customer`와 같게 처리하므로, operator나 업주 권한이 필요한 API는 `403 FORBIDDEN`이다. `PATCH /api/me`와 `POST /api/owner-applications`, 그리고 임시 로그인 operator의 업주 신청 승인·거절은 `404 USER_NOT_FOUND`다(3.3, 3.11.2, 3.11.7).

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
  - `GET /api/search/bars`, `GET /api/search/nearby-bars`, `GET /api/search/map-bars`, `GET /api/search/bar-names`, `GET /api/bar-photos/{photoId}`와 그 `/thumbnail`(3.16.5)은 `Authorization` 헤더를 읽지 않는다. 어떤 token을 보내도 결과가 같고, Supabase 장애 중에도 막히지 않는다.

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
| `displayName` | 예 | 앞뒤 공백을 지운 뒤 1~20자 |

검증 오류는 `422 VALIDATION_FAILED`이며 `fieldErrors[].path`는 `displayName`이다. 값이 없으면 `MISSING`, 공백뿐이면 `BLANK`, 20자를 넘으면 `STRING_TOO_LONG`이다.

이 API로 `email`, `authSubject`, `userType`은 변경할 수 없다. 여기서 바꾼 `displayName`은 이후 `GET /api/me`의 동기화로 덮어쓰지 않는다(3.2). 응답 형식은 `GET /api/me`와 같다.

이 API는 사용자를 생성하지 않는다. token은 유효하지만 `users` 행이 없으면 `404 USER_NOT_FOUND`를 반환한다. 프론트엔드는 `GET /api/me`를 호출해 사용자를 만든 뒤 같은 요청을 다시 보낸다. 인증 오류는 3.1.5를 따른다.

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

operator가 업장을 직접 만드는 API다. 업주가 있는 업장은 업주의 `new_bar` 신청과 승인(3.11)으로 만드는 것을 기본으로 한다.

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

좌표는 서버가 주소로 계산하지 않는다. 프론트엔드는 지도에서 업장 위치를 고르는 화면을 제공하고, 고른 좌표를 주소와 함께 보낸다. operator의 업장 생성, 신청 승인(3.11.7)과 업장 수정(3.7)이 같은 화면을 쓴다.

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

operator와 업주의 업장 관리 화면용 API다. 업장 정보와 관리 상태(진행 중인 메뉴 등록 작업, 현재 메뉴판 요약, 업주)를 반환하며 메뉴 항목은 포함하지 않는다. 메뉴 항목은 3.9로 조회한다. 업장 생성 직후(3.5의 `Location`), 업장 수정 뒤 재조회, 관리 화면 직접 진입에 사용한다.

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
| `items` | 배열 | 아니오 | 현재 메뉴판의 상품 항목. 없으면 `[]` |
| `items[].menuBoardEntryId` | UUID 문자열 | 아니오 | |
| `items[].barMenuItemId` | UUID 문자열 | 아니오 | |
| `items[].productId` | UUID 문자열 | 아니오 | 정규 상품 ID |
| `items[].productName` | 문자열 | 아니오 | 정규 상품명(`products.display_name`, 7.2의 `displayName`) |
| `items[].brandId`, `items[].brandName` | UUID 문자열, 문자열 | 아니오 | 상품의 브랜드와 대표 브랜드명 |
| `items[].category` | 문자열 | 아니오 | 상품 분류. 예: `whisky`. 프론트엔드는 이 값과 브랜드로 메뉴를 묶어 보여 줄 수 있다 |
| `items[].displayName` | 문자열 | 아니오 | 업장 메뉴판에 적힌 표기(`menu_board_entries.display_name`). 정규 상품명이 아니다 |
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

`items`에는 상품으로 확정되어 현재 메뉴판에 반영된 항목과 직접 추가한 항목만 있다. 섹션 제목, 설명 등 비상품 줄은 포함하지 않는다. 검색 결과에서 진입한 경우 프론트엔드는 검색한 `productId`와 같은 항목을 강조해 표시할 수 있다.

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

그 밖에 값이 없을 수 있는 필드는 `phone`, `description`, `operatingException`, `options[].optionLabel`, `options[].pourMl`, `options[].discount`뿐이며 모두 `null`로 온다. `tags`, `weeklyHours`, `photos`는 없으면 `[]`다. 프론트엔드는 해당 표시만 생략하고, 사진이 없으면 기본 이미지를 보여 준다. 업장 이름, 주소, 좌표와 옵션 가격은 항상 값이 있다.

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

고객이 위스키 이름을 입력하면 해당 상품을 현재 게시 메뉴에 포함한 업장 목록을 반환한다. 로그인 없이 호출할 수 있는 공개 API이며, `Authorization` 헤더를 보내도 사용하지 않는다.

```http
GET /api/search/bars?query=%EA%B8%80%EB%A0%8C%ED%94%BC%EB%94%95&lat=37.478&lng=126.951
```

| Query | 필수 | 기본값 | 설명 |
|---|---|---|---|
| `query` | 예 | 없음 | 검색어. 앞뒤 공백을 지운 뒤 1~100자 |
| `lat` | 아니오 | 없음 | 고객 위치 위도. -90~90. `lng`와 함께 보내야 한다 |
| `lng` | 아니오 | 없음 | 고객 위치 경도. -180~180. `lat`과 함께 보내야 한다 |
| `limit` | 아니오 | `50` | 반환할 결과 행(`items`)의 최대 개수. 1~100 |

고객 위치는 거리 계산에만 사용하며 서버에 저장하지 않는다. 서버 접근 로그에서도 `lat`, `lng`를 지우고 나머지 query(검색어 등)만 남긴다.

#### 3.10.1 검색어 해석

검색어는 메뉴 등록의 상품 매칭과 같은 백엔드 공통 정규화 함수로 정규화한다. 검색 시점에는 임베딩과 LLM을 호출하지 않고, 아래 단계를 순서대로 시도해 활성 상품을 하나라도 찾은 단계에서 멈춘다. 찾은 상품을 판매하는 업장이 없어도 다음 단계로 넘어가지 않는다.

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
```

브랜드 단계를 먼저 시도하는 이유: 대표 상품이 브랜드 이름을 별칭으로 갖는 경우가 많다(예: Royal Brackla 12의 별칭 `Royal Brackla`). 상품 별칭을 먼저 보면 `Royal Brackla`는 12년만, `로얄브라클라`는 그 브랜드의 상품 전체를 돌려주어 고객이 입력한 표기에 따라 결과가 달라진다. 브랜드 이름의 어떤 표기로 찾든 같은 결과를 주기 위해 브랜드 별칭과 정확히 같은 검색어는 브랜드 결과로 해석한다. `로얄브라클라 12년`처럼 브랜드 이름보다 긴 검색어는 브랜드 별칭과 같지 않으므로 상품 별칭 단계에서 그 상품을 찾는다. 브랜드에 활성 상품이 없으면 다음 단계로 넘어간다.

브랜드 결과에서도 고객이 입력한 이름 그대로인 상품을 놓치지 않도록, 검색어와 같은 검색용 별칭을 가진 상품("정확 일치 상품")은 `matchedProducts`와 `items`에서 먼저 둔다. 예를 들어 `요이치`는 Yoichi 브랜드 전체를 돌려주되, 별칭이 `요이치`인 Yoichi Single Malt를 Yoichi 10보다 앞에 둔다. 정확 일치 상품이 다른 브랜드의 상품이어도 결과에 포함한다. 같은 브랜드라도 표기에 따라 정확 일치 상품이 달라질 수 있으므로(예: `Yoichi`는 어떤 상품 별칭과도 같지 않다), 상품 집합은 같아도 순서는 표기에 따라 다를 수 있다.

어느 단계든 일치한 상품이 여러 개이면 모든 상품의 판매 업장을 하나의 목록으로 합쳐 반환한다. 예를 들어 `글렌피딕`이 브랜드 별칭으로 해석되면 Glenfiddich 12, 15, 18을 판매하는 업장이 함께 나온다. 각 결과에는 상품 정보가 포함되므로 프론트엔드는 카드마다 상품명을 표시한다.

검색 시점에 임베딩과 LLM을 사용하지 않는 이유는 다음과 같다.

- 검색은 입력마다 호출되므로 모델 호출 지연과 비용을 피한다.
- 같은 검색어가 항상 같은 결과를 반환하도록 결정적으로 유지한다.
- 의미가 비슷한 다른 상품이 섞이는 오검색을 막는다. MVP 카탈로그는 운영자가 한글·영문 별칭을 함께 등록하므로 별칭 조회만으로 주요 표기를 처리할 수 있다.

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
| 비활성 상품 | `products.is_active = false`인 상품은 어느 단계에서도 일치하지 않는다 |
| 검색 제외 별칭 | `is_searchable = false`인 상품 별칭으로는 `alias_exact`와 `partial`에서 일치하지 않는다 |
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
  brand        정확 일치 상품 먼저, 그다음 나머지. 각 묶음 안에서 displayName 오름차순
  partial      일치한 별칭이 짧은 상품부터, 같으면 displayName 오름차순

options
  sortOrder 오름차순
```

개수 제한:

- MVP의 업장 수가 약 20곳이므로 cursor 페이지네이션은 두지 않는다. `items`는 정렬한 뒤 앞에서부터 `limit`개까지만 반환하고, 잘렸으면 `truncated = true`다.
- `matchedProducts`는 `limit`의 영향을 받지 않는다. `partial`은 최대 10개, `brand`는 해당 브랜드의 활성 상품 전체다.
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
| `query` | 문자열 | 아니오 | 앞뒤 공백을 지운 검색어. 정규화한 값이 아니다 |
| `matchType` | `alias_exact` \| `brand` \| `partial` \| `none` | 아니오 | 검색어를 해석한 단계(3.10.1) |
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

```json
{
  "query": "없는 위스키",
  "matchType": "none",
  "matchedProducts": [],
  "items": [],
  "truncated": false
}
```

#### 3.10.5 검증 오류와 프론트엔드 처리

입력이 잘못되면 `422 VALIDATION_FAILED`를 반환한다(9.1, 9.3).

| 상황 | `fieldErrors[].path` | `fieldErrors[].code` | 프론트엔드 처리 |
|---|---|---|---|
| `query` 파라미터 없음 | `query` | `MISSING` | 앱 버그. 일반 오류와 재시도 |
| 빈 문자열이거나 공백뿐 | `query` | `BLANK` | 검색창 아래에 검색어 입력 안내 |
| 앞뒤 공백을 지운 뒤 100자 초과 | `query` | `STRING_TOO_LONG` | 검색창 아래에 100자 제한 안내 |
| 정규화하면 남는 문자가 없음 (예: `!!!`) | `query` | `NOT_SEARCHABLE` | 검색창 아래에 검색할 수 있는 문자가 없다는 안내 |
| `lat`과 `lng` 중 하나만 보냄 | 빠진 쪽 (`lat` 또는 `lng`) | `LAT_LNG_REQUIRED_TOGETHER` | 앱 버그. 일반 오류와 재시도 |
| `lat`, `lng`, `limit`이 범위를 벗어남 | 해당 파라미터 | `GREATER_THAN_EQUAL`, `LESS_THAN_EQUAL` | 앱 버그. 일반 오류와 재시도 |
| `lat`, `lng`, `limit`이 숫자가 아님 | 해당 파라미터 | `FLOAT_PARSING`(`lat`, `lng`), `INT_PARSING`(`limit`) | 앱 버그. 일반 오류와 재시도 |

- 파라미터 누락, 범위, 숫자 형식 오류는 한 응답의 `fieldErrors`에 여러 개 올 수 있다. 이 검사를 모두 통과한 뒤에 `BLANK`, `STRING_TOO_LONG`, `LAT_LNG_REQUIRED_TOGETHER`, `NOT_SEARCHABLE`을 이 순서로 검사하며, 이 단계에서는 처음 걸린 오류 하나만 반환한다.
- 프론트엔드는 요청 전에 검색어의 앞뒤 공백을 지우고, 빈 검색어면 API를 호출하지 않는다. 검색 입력 칸은 100자로 제한한다. 그래도 서버가 `query` 오류를 반환하면 위 표대로 `code`를 기준으로 문구를 보여 준다.
- 위치 권한이 없거나 위치를 얻지 못하면 `lat`과 `lng`를 둘 다 빼고 요청한다. 결과는 `menuUpdatedAt` 순으로 정렬되고 `distanceMeters`는 `null`이다.
- 네트워크 오류와 `5xx`(`500 INTERNAL_ERROR`, `503`, 프록시의 `502`·`504` 포함)는 오류 상태와 재시도 버튼을 보여 준다(9.6).

### 3.11 업주 신청과 승인

업주는 `user_type`이 아니라 사용자와 업장의 관계다. 로그인한 사용자가 업주 신청을 내고 operator가 승인하면, 그 사용자는 해당 업장의 업주가 된다. 업주가 되어도 `userType`은 바뀌지 않는다(보통 `customer`). 업주가 할 수 있는 일은 2.2의 권한 표를 따른다.

서비스 규모가 커지면 업장 등록은 operator가 하나씩 입력하는 방식(3.5)이 아니라, 업주가 `new_bar` 신청으로 직접 등록하고 operator가 승인하는 방식을 기본으로 한다.

- 한 업장에는 현재 업주가 최대 한 명이다. 한 사용자는 여러 업장의 업주가 될 수 있다.
- 신청은 두 종류다. `existing_bar`는 이미 등록된 업장의 업주 신청이고, `new_bar`는 아직 없는 업장을 등록하면서 업주가 되는 신청이다.
- 신청자는 사업자등록번호, 대표자명, 개업일자와 연락처를 제출한다. 사업자등록증 사진을 올리면 앞의 세 값을 읽어 입력란을 미리 채울 수 있다(3.11.12).
- 신청을 만든 뒤 메뉴판 사진을 올린다(3.11.15). 승인하면 백엔드가 이 사진으로 메뉴 등록 작업을 만들어 AI 분석을 미리 시작하므로, 업주는 처음 업장 관리에 들어갔을 때 바로 검수할 수 있다(3.11.7).
- 백엔드는 신청을 받을 때 국세청 사업자등록정보 진위확인 API로 사업자등록번호, 대표자명, 개업일자가 서로 맞는지 1차 검증한다(3.11.2). 맞지 않으면 신청을 만들지 않고 신청자가 입력을 고치게 한다. 검증 서비스에 연결하지 못하면 신청은 받고 결과를 `unavailable`로 남긴다.
- 외부 API를 부르는 두 요청은 사용자마다 하루 5회로 제한한다: 신청할 때의 국세청 진위확인(3.11.2)과 사업자등록증 OCR(3.11.12). 남의 사업자등록번호로 대표자명과 개업일자를 맞춰 보는 시도와 외부 API 호출 한도 소진을 막기 위해서다. 규칙은 3.11.14에 있다.
- operator는 웹 대시보드에서 신청과 검증 결과를 보고, 실제 매장이 있는지 확인한 뒤 승인하거나 거절한다.
- 사업자등록번호, 대표자명, 개업일자, 연락처는 신청자 본인과 operator에게만 보여 준다. 검증 결과 중 신청자에게는 사업자 상태(`businessStatus`)만 보여 준다. 백엔드는 이 값들을 로그에 남기지 않는다.
- 신청 결과는 알림으로 보내지 않는다. 신청자는 3.11.3으로 상태를 확인한다.

```text
[신청자]
GET /api/me                                  (users 행이 없으면 먼저 생성)
GET /api/search/bar-names?query=...          (기존 업장 신청이면 업장 선택, 3.11.11)
POST /api/owner-applications/business-certificate-ocr
                                             (선택. 사업자등록증 사진으로 입력란 채우기, 3.11.12)
POST /api/owner-applications                 → 1차 검증 후 pending
                                               (정보가 맞지 않으면 422, 입력을 고쳐 다시 신청)
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
POST /api/owner-applications/{id}/reject     → rejected, 신청 메뉴판 사진 삭제

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
  "contactPhone": "010-1234-5678",
  "applicantNote": "대표 본인입니다",
  "menuPhotos": [
    {
      "imageOrder": 1,
      "imageUrl": "https://storage.example.com/signed/owner-application-menu-1.jpg",
      "imageUrlExpiresAt": "2026-10-14T03:15:00Z"
    }
  ],
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
| `businessRegistrationNumber` | 문자열 | 아니오 | 하이픈을 뺀 숫자 10자리 |
| `representativeName` | 문자열 | 아니오 | 사업자등록증의 대표자 성명 |
| `openingDate` | `YYYY-MM-DD` 문자열 | 아니오 | 사업자등록증의 개업연월일 |
| `businessStatus` | `BusinessStatus` | 예 | 마지막 검증에서 국세청이 알려 준 사업자 상태. 검증 결과가 `matched`가 아니거나 국세청이 상태를 알려 주지 않으면 `null`. 신청자에게도 보여 준다 |
| `businessVerification` | 객체 | 예 | operator에게만 값이 있고, 신청자 본인이 조회하면 `null` |
| `businessVerification.result` | `BusinessVerificationResult` | 아니오 | 마지막 검증 결과 |
| `businessVerification.checkedAt` | RFC 3339 문자열 | 아니오 | `result`를 얻은 시각. 신청할 때 `unavailable`이 되었으면 그 시도 시각이다. 다시 검증(3.11.13)이 실패하면 `result`와 함께 바뀌지 않는다 |
| `contactPhone` | 문자열 | 아니오 | 운영자가 확인을 위해 연락할 번호 |
| `applicantNote` | 문자열 | 예 | 신청자 메모 |
| `menuPhotos` | 배열 | 아니오 | 신청에 올린 메뉴판 사진(3.11.15). `imageOrder` 순서이며, 올리지 않았거나 거절·취소로 삭제되었으면 `[]` |
| `menuPhotos[].imageOrder` | 정수 | 아니오 | 1부터 시작하는 순서 |
| `menuPhotos[].imageUrl` | 문자열 | 아니오 | 짧은 만료 시간을 가진 서명 URL. 신청자 본인과 operator만 받는다. 만료되었거나 이미지 로딩이 `403`으로 실패하면 신청 상세(3.11.4)를 다시 조회해 새 URL을 받는다 |
| `menuPhotos[].imageUrlExpiresAt` | RFC 3339 문자열 | 예 | `imageUrl` 만료 시각. 만료되지 않는 URL(로컬 저장소)이면 `null` |
| `rejectionReason` | 문자열 | 예 | `rejected`일 때만 값이 있다 |
| `reviewedAt` | RFC 3339 문자열 | 예 | 승인 또는 거절 시각. 그 전에는 `null` |
| `createdAt`, `updatedAt` | RFC 3339 문자열 | 아니오 | |

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
5. 오늘의 진위확인 횟수 (`429 RATE_LIMITED`, 3.11.14)
6. 국세청 진위확인 API로 `businessRegistrationNumber`, `representativeName`, `openingDate` 검증
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

호출자 본인의 신청을 모든 상태에 대해 최근 신청부터 반환한다. 페이지네이션은 두지 않는다. 신청이 없거나 `users` 행이 아직 없으면 `items = []`다. 신청자 본인의 조회이므로 각 신청의 `businessVerification`은 `null`이고 `businessStatus`만 보여 준다(3.11.1). operator가 호출해도 본인의 신청만 나온다.

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

신청자 본인과 operator만 조회할 수 있다. 응답은 `OwnerApplication`이다. 신청이 없거나, 다른 사람의 신청이거나, `applicationId`가 UUID 형식이 아니면 `404 OWNER_APPLICATION_NOT_FOUND`다. 다른 사람의 신청이 있는지는 알려 주지 않는다.

#### 3.11.5 업주 신청 취소

```http
POST /api/owner-applications/{applicationId}/cancel
Authorization: Bearer <access-token>
```

신청자 본인만 호출할 수 있다. 요청 본문은 없다. `pending`이면 `canceled`로 바꾸고 `200 OK`로 `OwnerApplication`을 반환한다. 신청의 메뉴판 사진(3.11.15)은 삭제되므로 응답의 `menuPhotos`는 `[]`다.

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

정렬은 `status = pending`이면 오래된 신청부터(처리 순서), 그 외에는 최근 신청부터다. 응답의 각 신청에는 `businessVerification`이 들어 있다.

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
- `new_bar`: operator가 확인한 업장 정보를 보낸다. 프론트엔드는 `proposedBar`를 초기값으로 채우고, operator가 주소를 확인해 좌표를 입력한다. 필드 규칙은 3.5와 같다. `description`, `defaultPourMl`, `tags`, `weeklyHours`는 받지 않으며(`EXTRA_FORBIDDEN`, 3.7), 만든 업장은 `description`과 `defaultPourMl`이 `null`, `tags`와 `weeklyHours`가 `[]`다. 업주가 승인 뒤 3.7로 정한다. 임시 휴무와 매장 사진도 승인 뒤 3.15, 3.16으로 정한다.

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

operator만 호출할 수 있다. `reason`은 필수이며 앞뒤 공백을 지운 뒤 1~500자다. 신청자에게 그대로 보여 준다. 사업자등록 정보 검증 결과와 관계없이 거절할 수 있다. 신청의 메뉴판 사진(3.11.15)은 삭제한다. `200 OK`, 본문은 `OwnerApplication`(`status = rejected`, `menuPhotos = []`)이다. 오류는 3.11.7의 `403`, `404`(`USER_NOT_FOUND` 포함), `409 INVALID_APPLICATION_STATE`와 같고, `422 VALIDATION_FAILED`는 `reason`이 없거나(`MISSING`), 공백뿐이거나(`BLANK`), 500자를 넘을 때(`STRING_TOO_LONG`)다.

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

operator만 호출할 수 있다. 업장의 현재 업주 관계를 해제하고 `204 No Content`를 반환한다. 기록은 지우지 않고 해제 시각을 남긴다. 해제된 사용자는 다음 요청부터 그 업장의 업주 권한이 없다. 업장에 진행 중인 메뉴 등록 작업은 그대로 남으며 operator나 새 업주가 이어서 처리할 수 있다.

| HTTP | code | 발생 조건 | 프론트엔드 처리 |
|---|---|---|---|
| `403` | `FORBIDDEN` | operator가 아님 | 3.1.5 |
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

| HTTP | code | 발생 조건 | 프론트엔드 처리 |
|---|---|---|---|
| `403` | `FORBIDDEN` | operator가 아님 | 3.1.5 |
| `404` | `OWNER_APPLICATION_NOT_FOUND` | 신청이 없거나 `applicationId`가 UUID 형식이 아님 | 신청 목록 재조회 |
| `409` | `INVALID_APPLICATION_STATE` | `pending`이 아님. `details.status`에 현재 상태 | 신청 상세 재조회 |
| `503` | `BUSINESS_VERIFICATION_UNAVAILABLE` | 검증 서비스 오류, 시간 초과, 호출 한도 초과, 또는 서버에 검증 설정이 없음 | 잠시 후 다시 시도 안내 |

#### 3.11.14 진위확인과 OCR 요청 수 제한

| 대상 | 한도 | 세는 요청 |
|---|---|---|
| 업주 신청의 국세청 진위확인 (3.11.2) | 사용자마다 하루 5회 | 3.11.2의 1~5단계를 통과해 국세청 API를 실제로 호출한 요청. 결과(`matched`, `not_matched`, `unavailable`)와 관계없이 센다. 서버에 검증 설정이 없어 호출하지 않은 요청은 세지 않는다 |
| 사업자등록증 OCR (3.11.12) | 사용자마다 하루 5회 | `413`, `415`, `422` 검사를 통과해 CLOVA OCR을 실제로 호출한 요청. 읽은 항목이 없어도, 호출이 실패해 `503`이 되어도 센다. 서버에 OCR 설정이 없어 호출하지 않은 요청은 세지 않는다 |

- 사용자는 token의 `sub`(3.1.2)로 구분한다. OCR은 `users` 행이 없어도 호출할 수 있으므로 `users.id`가 아니라 `sub`로 센다.
- 임시 로그인(3.1.3) 토큰은 모두 `sub`가 같으므로 한도 하나를 함께 쓴다. 임시 로그인은 로컬 개발과 Google 로그인 전환 전의 데모 서버에서만 쓰므로 이 한계를 받아들인다.
- 두 한도는 따로 센다. operator의 다시 검증(3.11.13)은 제한하지 않는다.
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
- **항목 식별자**: 항목은 `barMenuItemId`로 가리킨다. 업장과 상품의 조합마다 하나이며 메뉴판에서 빠져도 바뀌지 않는다. `menuBoardEntryId`와 `menuEntryOptionId`는 메뉴판이 바뀔 때마다(검수 반영과 직접 편집 모두) 새로 만들어질 수 있으므로 편집 요청에 쓰지 않는다.
- **미완료 작업이 있을 때**: 업장에 미완료 메뉴 등록 작업(`uploaded`, `processing`, `ready_for_review`)이 있으면 추가, 수정, 삭제, 초기화는 모두 `409 ACTIVE_IMPORT_EXISTS`(`details.menuImportId`, `details.status`)다. 따라서 이 상황에서는 메뉴 편집이 불가능하고, 작업이 `applied`, `failed`, `canceled`가 되면 다시 편집할 수 있다. 검수 중에 메뉴판이 바뀌면 검수자가 오래된 메뉴판을 보고 결정하게 되기 때문이다.
- **메뉴판 버전**: 모든 편집 요청은 3.9에서 받은 `menuVersion`을 보낸다. 메뉴판이 없으면 `null`이다. 서버의 현재 값과 다르면 아무것도 바꾸지 않고 `409 MENU_OUTDATED`(`details.submittedMenuVersion`, `details.currentMenuVersion`)다. 성공한 편집은 `menuVersion`을 1 올리고, 메뉴판이 없을 때의 첫 추가는 메뉴판을 만들고 `menuVersion = 1`이 된다. 검수 반영(8)도 `menuVersion`을 올린다.
- **게시 시각**: 성공하면 `publishedAt`을 요청 시각으로 바꾼다. `menuBoardId`는 그대로다.
- **응답**: 성공 응답의 본문은 3.9와 같은 형식(업장 정보와 메뉴 전체)이다. 추가는 `201 Created`, 나머지는 `200 OK`다. 프론트엔드는 이 응답으로 화면을 바꾸고 따로 다시 조회하지 않아도 된다.
- **원자성**: 요청 하나는 하나의 트랜잭션이다. 신규 상품 생성(3.14.3)을 포함해 어느 단계에서든 실패하면 아무것도 바뀌지 않는다.
- **동시 요청은 업장 행 잠금으로 차례로 처리한다**: 메뉴판이나 메뉴 항목에 영향을 주는 요청은 모두, 무엇을 확인하기 전에 먼저 같은 업장 행(`bars`)을 `FOR UPDATE`로 잠그고 트랜잭션이 끝날 때까지 잡는다. 대상은 다음과 같다.
  - 메뉴 등록 작업 생성: 사진 업로드(4.1)와 신청 승인의 첫 등록 작업(3.11.7)
  - 검수 반영(8)
  - 직접 편집: 추가, 수정, 삭제, 초기화(3.14.3~3.14.6)
  - 품절 표시(3.14.8)와 판매 정보 확인(3.14.9)

  그래서 같은 업장에 이런 요청이 동시에 와도 하나가 끝난 뒤에 다음 것이 처리되고, 각 요청은 앞 요청이 커밋한 결과를 보고 확인한다. 예를 들어 편집이 먼저면 등록 작업은 바뀐 메뉴판을 기준으로 만들어지고, 등록 작업이 먼저면 편집은 `409 ACTIVE_IMPORT_EXISTS`다. 검수가 항목을 내린 뒤에 온 품절 표시는 `404 MENU_ITEM_NOT_FOUND`이고, 검수 반영으로 버전이 오른 뒤에 온 판매 정보 확인은 `409 MENU_OUTDATED`다. 잠금은 업장마다 따로이므로 다른 업장의 요청은 기다리지 않는다.
- **재시도**: `Idempotency-Key`는 쓰지 않는다. 응답을 받지 못해 같은 요청을 다시 보내면, 앞 요청이 성공했다면 `menuVersion`이 이미 올라 `409 MENU_OUTDATED`를 받는다. 프론트엔드는 3.9를 다시 조회해 변경이 반영되었는지 확인한다.
- **변경 기록**: 누가 언제 메뉴를 바꿨는지는 남기지 않는다. 메뉴 변경 이력은 운영 대시보드의 추가 기능으로 나중에 구현할 예정이다. 직접 추가로 만든 상품과 브랜드에는 만든 사용자를 기록한다(3.14.3).
- **다른 항목은 그대로**: 추가, 수정, 삭제는 요청한 항목만 바꾼다. 다른 항목의 옵션, 할인(3.14.2), 품절(3.14.8)은 그대로 남는다. 서버가 메뉴판을 다시 쓰는 방식으로 구현하더라도 다른 항목의 할인은 같은 옵션에 옮겨야 한다. 초기화(3.14.6)는 모든 항목을 빼므로 할인과 품절도 함께 사라진다.
- **품절과 판매 정보 확인**: 3.14.8과 3.14.9는 메뉴 내용을 바꾸지 않으므로 미완료 작업 규칙과 `menuVersion` 증가, 게시 시각 변경을 적용하지 않는다. 자세한 차이는 각 절에 적었다.
- **검사 순서**: 요청 형식(`422`) → 업장(`404 BAR_NOT_FOUND`) → 권한(`403`) → 미완료 작업(`409 ACTIVE_IMPORT_EXISTS`) → 메뉴판 버전(`409 MENU_OUTDATED`) → 각 API의 항목 확인과 업무 규칙. 형식 오류는 한 응답에 여러 개 올 수 있다.

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
| `menuVersion` | 정수 | 예 (`null` 가능) | 3.14.1. 메뉴판이 없으면 `null` |
| `productId` | UUID 문자열 | `productId`와 `newProduct` 중 하나 | 활성 상품. 없으면 `PRODUCT_NOT_FOUND`, 비활성이면 `PRODUCT_INACTIVE` |
| `newProduct.brand` | 객체 | `newProduct`를 보내면 예 | 8.1 `create_product`의 `brand`와 같다. 없는 `brandId`는 `BRAND_NOT_FOUND` |
| `newProduct.product` | 객체 | `newProduct`를 보내면 예 | 8.1 `create_product`의 `product`와 같다 |
| `newProduct.aliases` | 배열 | 아니오 | 8.1 `create_product`의 `aliases`와 같다. 기본 `[]` |
| `displayName` | 문자열 | 아니오 | 메뉴판에 보일 이름. 앞뒤 공백을 지운 뒤 1~200자. 없거나 `null`이면 상품의 `displayName` |
| `options` | 배열 | 예 | 3.14.2 |

- `productId`와 `newProduct`를 둘 다 보내거나 둘 다 빠뜨리면 `422`이고 `fieldErrors[].path = productId`, `code = EXACTLY_ONE_REQUIRED`다.
- 같은 상품이 이미 현재 메뉴판에 있으면 `409 MENU_ITEM_EXISTS`(`details.barMenuItemId`)다. 한 상품은 메뉴판에 한 번만 있고, 용량이나 가격을 더하려면 그 항목을 수정한다(3.14.4).
- 새 항목은 메뉴판의 맨 끝에 붙는다. 이 업장이 예전에 판매했던 상품이면 그때의 `barMenuItemId`를 다시 쓴다.
- `newProduct`를 보내면 같은 트랜잭션 안에서 검수의 신규 생성(8.5, 8.6)과 같은 규칙으로 브랜드와 상품의 중복을 검사한다. 같은 브랜드나 상품이 있으면 아무것도 만들지 않고 `409 DUPLICATE_BRAND_FOUND` 또는 `409 DUPLICATE_PRODUCT_FOUND`다. `details`는 9.5와 같되 `extractedItemId`와 `reviewUrl`이 없다. 프론트엔드는 `details.existingProduct`(또는 `existingBrand`)를 보여 주고, 맞으면 그 `productId`(또는 `brandId`)로 다시 요청한다. `existingProduct.isActive = false`이면 그 상품으로는 추가할 수 없으므로(`PRODUCT_INACTIVE`) 다시 요청하지 않고, 상품 검색(7)에서 고르도록 안내한다(9.5).
- 만든 상품과 브랜드에는 요청한 사용자를 기록한다. 만든 상품과 별칭은 바로 모든 업장의 고객 검색과 메뉴 매칭에 쓰인다.
- 응답 본문에서 추가한 항목은 `productId`로 찾는다.

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
- 연결된 상품은 바꿀 수 없다. 다른 상품으로 바꾸려면 삭제한 뒤 추가한다.
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
| `409` | `MENU_ITEM_EXISTS` | 추가하려는 상품이 이미 메뉴판에 있음. `details.barMenuItemId` | 그 항목의 수정 화면으로 안내 |
| `409` | `DUPLICATE_BRAND_FOUND`, `DUPLICATE_PRODUCT_FOUND` | 신규 브랜드나 상품과 같은 것이 이미 있음 (3.14.3, 9.5) | 기존 브랜드나 상품을 보여 주고 고르게 함. `existingProduct.isActive = false`이면 상품 검색으로 안내 |
| `422` | `VALIDATION_FAILED` | 필드 규칙 위반, `TOO_SHORT`, `TOO_LONG`, `DUPLICATE_OPTION_VALUES`, `DISCOUNT_NOT_LOWER`, `DISCOUNT_ENDED`, `END_BEFORE_START`, `EXACTLY_ONE_REQUIRED`, `PRODUCT_NOT_FOUND`, `PRODUCT_INACTIVE`, `BRAND_NOT_FOUND` | `fieldErrors` 표시 |
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
  - **메뉴판 버전**: `menuVersion`을 받지 않고 올리지도 않는다. `publishedAt`도 바뀌지 않는다.
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
| `422` | `VALIDATION_FAILED` | `soldOut` 없음(`MISSING`)이나 불리언이 아님 | `fieldErrors` 표시 |

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
- 검사 순서: 요청 형식(`422`, `menuVersion` 필드가 없으면 `MISSING`) → 업장(`404 BAR_NOT_FOUND`) → 권한(`403`) → 업장 행 잠금(3.14.1) → 메뉴판과 항목(`409 NO_PUBLISHED_MENU`) → 메뉴판 버전(`409 MENU_OUTDATED`) → 확인 시각 기록. 잠금 안에서 버전을 확인하고 기록하므로, 검수 반영과 동시에 와도 반영 전의 메뉴를 반영 뒤의 시각으로 확인한 것처럼 남지 않는다.
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

| HTTP | code | 발생 조건 | 프론트엔드 처리 |
|---|---|---|---|
| `401` | `UNAUTHENTICATED` | 3.1.5 | 3.1.5 |
| `403` | `FORBIDDEN` | operator도 해당 업장의 업주도 아님 | 3.1.5 |
| `404` | `BAR_NOT_FOUND` | 업장이 없거나 `barId`가 UUID 형식이 아님 | 업장 목록으로 이동 |
| `422` | `VALIDATION_FAILED` | 위 규칙 위반: `MISSING`, `DUPLICATE_DAY`, `INVALID_TIME`, `SAME_OPEN_CLOSE`, `TIME_ON_CLOSED_DAY`, `DATE_IN_PAST`, `DATE_NOT_TODAY`, `END_BEFORE_START`, `INVALID_CHARACTER`, `EXTRA_FORBIDDEN` | `fieldErrors` 표시. `DATE_IN_PAST`이면 날짜를 다시 고르게 하고, `DATE_NOT_TODAY`이면 날짜가 바뀌었다고 안내한 뒤 다시 적용하게 함 |

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
- 검사 순서: 요청 형식(`422`, `image`가 없으면 `MISSING`) → 업장(`404 BAR_NOT_FOUND`) → 권한(`403`) → 크기(`413 UPLOAD_TOO_LARGE`)와 형식(`415 UNSUPPORTED_IMAGE_TYPE`) → 가로세로(`422 IMAGE_DIMENSIONS_TOO_LARGE`) → 같은 사진(`409 PHOTO_EXISTS`) → 장수(`409 PHOTO_LIMIT_REACHED`). 같은 사진을 장수보다 먼저 확인하므로, 15번째 사진을 올린 요청을 다시 보내도 `PHOTO_EXISTS`를 받는다.
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
  "proposedChanges": [
    {
      "changeId": "30000000-0000-4000-8000-000000000001",
      "changeType": "add",
      "barMenuItemId": null,
      "extractedItemId": "10000000-0000-4000-8000-000000000007",
      "before": null,
      "after": {
        "productId": "bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbb1",
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
- `correctedLineType`은 운영자가 최초 분류를 바꾼 경우에만 값이 있고, 그대로 승인한 경우 `null`이다.
- `effectiveLineType`은 `correctedLineType ?? extractedLineType`으로 계산한 현재 검수 기준 역할이다.
- `initialResolutionStatus`는 최초 상품 매칭 결과다. `exact_match`는 매칭 규칙(상품 별칭 정확 일치 또는 단계 규칙 S1·S2·S2b·S3)이 충돌 없이 상품 하나를 확정한 상태, `ambiguous`는 검토할 후보가 있으나 하나로 확정하지 못한 상태, `unmatched`는 유효 후보가 없는 상태다. 어느 규칙이 후보를 찾았는지는 후보 `evidence.rule`(`alias`, `S1`, `S2`, `S2b`, `S3`)에 있다. 최초 분류가 비상품이라 매칭하지 않은 항목은 `null`이다.
- 서버에서 LLM 매칭 층(M3, 기본 꺼짐)을 켜면 S1~S3가 확정하지 못한 줄에 LLM 후보가 붙을 수 있다. LLM 후보는 `matchMethod = llm`, `evidence.rule`이 `M3a` 또는 `M3b`이고 그 줄의 다른 후보보다 앞 순위다. LLM이 후보를 낸 줄은 항상 `ambiguous`이며 `exact_match`가 되지 않는다. 1순위 후보 `evidence.confirmRecommended`가 `true`이면 그 후보 하나를 확인만 하면 되는 "확인 권장" 줄이다(S2b·S3 후보에도 붙는다). LLM 후보의 그 밖의 `evidence` 키(`via`, `englishName`, `vetoed`, `shortUnverified`)는 디버깅용이다. 규칙은 `docs/menu_ai_matching_flow.md` 6장 "현재 구현"에 있다.
- `candidates`는 같은 상품을 중복하지 않으며 `candidateRank` 오름차순이다.
- `proposedProductId`는 `candidateRank = 1`의 상품이거나 후보가 없으면 `null`이다.
- `newProductDraft`는 화면 입력을 돕는 계산값이며 실제 카탈로그 행이 아니다.
- `evidence`는 설명용 보조 정보다. 프론트엔드는 알 수 없는 키를 무시해야 한다.
- `before`와 `after`가 최종 diff 비교의 구조화된 값이다.
- `summary`는 표시용 문구이며 검증이나 반영 기준으로 사용하지 않는다.

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
| `409` | `INVALID_IMPORT_STATE` | `applied` 또는 `failed`인 작업. `details.status`에 현재 상태 | 작업 상세 재조회 |

프론트엔드는 취소 전에 확인을 받는다. `ready_for_review`에서 취소하면 검수 중 입력한 결정은 모두 사라진다.

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

한 화면의 결정을 한 번에 제출하며 중간 항목 저장 API는 사용하지 않는다. operator와 작업 대상 업장의 현재 업주가 호출할 수 있다.

모든 객체는 정의하지 않은 필드를 받지 않는다(`EXTRA_FORBIDDEN`). 예를 들어 `confirm_non_product`에 `optionDecisions`를 보내면 거부한다. 문자열 필드는 앞뒤 공백을 지운 뒤 길이를 검사한다.

`itemDecisions[]`는 `action`에 따라 네 형식 중 하나다.

| `action` | 용도 | `finalLineType` | 필드 |
|---|---|---|---|
| `select_existing_product` | 기존 상품에 연결 | `product` | `extractedItemId`, `productId` 필수. `correctedProductName`, `optionDecisions`, `aliasesToAdd` 선택 |
| `create_product` | 새 상품(필요하면 새 브랜드)을 만들어 연결 | `product` | `extractedItemId`, `brand`, `product` 필수. `correctedProductName`, `optionDecisions`, `aliases` 선택 |
| `confirm_non_product` | 비상품 줄로 확정 | `section_header`, `description`, `unknown` | `extractedItemId`만 |
| `reject` | 잡음·중복 등으로 제외 | 어떤 값이든 | `extractedItemId`만 |

상품 결정(`select_existing_product`, `create_product`)의 공통 필드:

| 필드 | 필수 | 규칙 |
|---|---|---|
| `extractedItemId` | 예 | 검수 응답의 항목 ID |
| `correctedProductName` | 아니오 | 메뉴판에 보일 이름. 1~200자. 없거나 `null`이면 추출한 이름을 쓴다 |
| `optionDecisions` | 아니오 | 고칠 옵션만 보낸다. 보내지 않은 옵션은 추출값 그대로 반영한다. 기본 `[]` |
| `optionDecisions[].extractedOptionId` | 예 | 그 항목의 옵션 ID |
| `optionDecisions[].correctedOptionLabel` | 아니오 | 1~100자. 없거나 `null`이면 추출값 유지 |
| `optionDecisions[].correctedPriceKrw` | 아니오 | 1~2,147,483,647 정수. 없거나 `null`이면 추출값 유지 |
| `optionDecisions[].correctedPourMl` | 아니오 | 1~32767 정수. 없거나 `null`이면 추출값 유지 |

`optionDecisions`의 필드는 "없음 또는 `null` = 고치지 않음"이다. 따라서 추출된 값을 지워 `null`로 만들 수는 없다. 가격이 없는 옵션은 게시하지 않으며, 게시할 상품에는 가격 있는 옵션이 최소 하나 있어야 한다(`NO_PRICED_OPTION`).

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

`changeDecisions[]`는 `changeId`(필수)와 `decision`(`apply` 또는 `ignore`, 필수)이다. `reviewVersion`은 1 이상 정수다.

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
      "optionDecisions": [
        {
          "extractedOptionId": "20000000-0000-4000-8000-000000000001",
          "correctedOptionLabel": null,
          "correctedPriceKrw": 8000,
          "correctedPourMl": 15
        },
        {
          "extractedOptionId": "20000000-0000-4000-8000-000000000002",
          "correctedOptionLabel": null,
          "correctedPriceKrw": 15000,
          "correctedPourMl": 30
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
  "optionDecisions": [
    {
      "extractedOptionId": "20000000-0000-4000-8000-000000000001",
      "correctedPriceKrw": 12000,
      "correctedPourMl": 15
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
  "optionDecisions": [
    {
      "extractedOptionId": "20000000-0000-4000-8000-000000000003",
      "correctedPriceKrw": 14000,
      "correctedPourMl": 15
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
- `finalLineType = product`이면 `select_existing_product` 또는 `create_product`여야 한다.
- 게시할 상품 항목에는 가격이 있는 유효 옵션이 최소 하나 있어야 한다.
- 기존 상품은 존재하고 연결 가능한 상태여야 한다.
- 선택한 상품의 연수·에디션이 추출값과 충돌해도 거부하지 않는다. AI가 잘못 읽은 값을 운영자가 바로잡을 수 있어야 하기 때문이다. 프론트엔드는 이런 선택을 제출하기 전에 운영자에게 한 번 확인을 받는다(후보 `evidence`의 `ageConflict`, `editionConflict`, `editionOnlyInExtracted`, 또는 검색으로 고른 상품의 `ageYears`·`editionName`과 추출값 비교).
- 신규 브랜드·상품은 트랜잭션 안에서 중복을 다시 검사한다.
- 백엔드는 운영자가 제출한 결정으로 최종 변경을 계산해 반영한다. 다른 후보를 고르거나 가격을 고쳐서 임시 diff와 달라진 변경도 운영자의 결정이므로 그대로 반영한다.
- 현재 메뉴판의 항목은 운영자가 `apply`한 `remove`로만 빠진다.
- 검수 데이터를 만든 뒤 현재 메뉴판이 바뀌었으면(다른 작업이 먼저 게시된 경우 등) 반영하지 않는다. 백엔드는 임시 diff를 다시 만들고 `reviewVersion`을 올린 뒤 `REVIEW_OUTDATED`를 반환한다.
- 반영은 메뉴 등록 작업을 잠그기 전에 업장 행을 먼저 잠근다(3.14.1). 같은 업장의 직접 편집, 품절 표시, 판매 정보 확인, 새 등록 작업과 차례로 처리하기 위해서다.
- 반영할 때 품절과 할인은 다음처럼 이어진다. 품절(3.14.8)은 메뉴판에 남는 항목에서 그대로 유지되고, `remove`로 빠진 항목에서는 풀린다. 할인(3.14.2)은 반영 뒤에도 표기(`optionLabel`), 용량(`pourMl`), 정가(`priceKrw`)가 모두 같은 옵션이 남으면 그 옵션에 그대로 유지된다. 정가가 바뀌거나 옵션이 없어지면 할인이 지워진다. 정가가 바뀌면 원래 할인가가 맞는지 알 수 없기 때문이다. 품절 변경과 판매 정보 확인은 "검수 데이터를 만든 뒤 현재 메뉴판이 바뀌었는지" 검사에서 메뉴판 변경으로 보지 않는다.
- 반영에 성공하면 메뉴판 버전(3.9의 `menuVersion`)을 1 올린다. 미완료 작업이 있는 동안에는 메뉴 직접 편집(3.14)을 받지 않으므로, 검수 중에 직접 편집으로 메뉴판이 바뀌는 일은 없다.

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
    "createdProducts": 1
  }
}
```

최종 확정과 메뉴판 반영은 하나의 `SERIALIZABLE` 트랜잭션이다. 성공하면 상태가 `ready_for_review`에서 `applied`로 바로 바뀐다.

네트워크 타임아웃 후 같은 요청이 다시 들어왔는데 이미 `applied`라면 변경을 다시 적용하지 않고 현재 적용 결과를 반환한다.

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
| `404` | `PHOTO_NOT_FOUND` | 삭제하거나 조회할 매장 사진이 없음. `details.photoId` (3.16) | 업장 상세 다시 조회 |
| `404` | `USER_NOT_FOUND` | `GET /api/me`로 사용자를 만들기 전에 `PATCH /api/me`, `POST /api/owner-applications`, 업주 신청 승인·거절(3.11.7, 3.11.8) 호출 | `GET /api/me` 호출 후 같은 요청 재시도 |
| `404` | `NOT_FOUND` | 존재하지 않는 경로, 또는 비활성화된 임시 로그인 호출 | 요청 경로·서버 설정 확인 |
| `405` | `METHOD_NOT_ALLOWED` | 경로는 있지만 허용하지 않는 HTTP 메서드 | 요청 메서드 확인 |
| `409` | `BAR_OWNER_EXISTS` | 이미 현재 업주가 있는 업장에 신청 또는 승인 (3.11) | 안내. operator는 해당 신청을 거절 |
| `409` | `OWNER_APPLICATION_EXISTS` | 같은 업장, 또는 같은 사업자등록번호의 `new_bar`에 본인의 대기 중 신청이 있음 (3.11.2) | `details.applicationId`의 신청으로 이동 |
| `409` | `INVALID_APPLICATION_STATE` | `pending`이 아닌 신청의 승인·거절·취소·다시 검증 (3.11) | 신청 상세 재조회 |
| `409` | `IDEMPOTENCY_KEY_REUSED` | 같은 키에 다른 요청 내용 | 새 키로 명시적 재요청 |
| `409` | `ACTIVE_IMPORT_EXISTS` | 업장에 미완료 작업이 이미 있는데 새 작업을 올리거나(4.4) 메뉴를 직접 편집함(3.14). `details.menuImportId`, `details.status` | 기존 작업으로 이동하거나 취소(5.7) 후 다시 요청 |
| `409` | `MENU_OUTDATED` | 직접 편집이나 판매 정보 확인(3.14.9) 요청의 `menuVersion`이 현재 메뉴판 버전과 다름. `details.submittedMenuVersion`, `details.currentMenuVersion` (3.14) | 메뉴 다시 조회 후 다시 저장 |
| `409` | `NO_PUBLISHED_MENU` | 판매 정보 확인(3.14.9)을 했는데 메뉴판이 없거나 항목이 없음 | 메뉴 등록으로 안내 |
| `409` | `MENU_ITEM_EXISTS` | 직접 추가하려는 상품이 이미 현재 메뉴판에 있음. `details.barMenuItemId` (3.14.3) | 그 항목 수정으로 안내 |
| `409` | `PHOTO_EXISTS` | 내용이 같은 매장 사진이 이미 있음. `details.photoId` (3.16.2) | 이미 등록된 사진이라고 안내하고 사진 목록 다시 조회 |
| `409` | `PHOTO_LIMIT_REACHED` | 매장 사진이 이미 15장. `details.maxPhotos` (3.16.2) | 사진을 지운 뒤 추가하라고 안내 |
| `409` | `PHOTOS_OUTDATED` | 순서 변경에 보낸 사진 ID가 현재 사진과 다름. `details.photos` (3.16.4) | `details.photos`로 화면을 바꾸고 다시 정렬하게 함 |
| `409` | `INVALID_IMPORT_STATE` | 현재 상태에서 요청 불가. 예: `ready_for_review`가 아닌 작업의 검수 제출, `applied`·`failed` 작업의 취소. `details.status`에 현재 상태 | 상태 재조회 |
| `409` | `REVIEW_OUTDATED` | `reviewVersion` 불일치, 또는 검수 데이터를 만든 뒤 현재 메뉴판이 바뀜 | `details.reviewUrl`로 최신 검수 데이터 재조회 |
| `409` | `DUPLICATE_BRAND_FOUND` | 신규 브랜드와 동일할 수 있는 브랜드 발견 (검수 또는 직접 추가) | 기존 브랜드 선택 화면 표시 |
| `409` | `DUPLICATE_PRODUCT_FOUND` | 신규 상품과 동일한 상품 발견, 또는 제출한 이름·별칭이 기존 상품의 별칭과 일치 | 기존 상품 선택 화면 표시. 다른 상품이면 겹치는 별칭을 빼고 다시 제출. `existingProduct.isActive = false`이면 상품 검색으로 안내 (9.5) |
| `413` | `UPLOAD_TOO_LARGE` | 파일 개수 또는 크기 초과 | 이미지 축소 또는 개수 조정 |
| `415` | `UNSUPPORTED_IMAGE_TYPE` | 지원하지 않는 이미지 형식 | 지원 형식 안내 |
| `422` | `VALIDATION_FAILED` | 필드 값이나 옵션 구성이 잘못됨 | `fieldErrors` 표시 |
| `422` | `BUSINESS_VERIFICATION_FAILED` | 업주 신청의 사업자등록번호, 대표자명, 개업일자가 국세청 정보와 맞지 않음 (3.11.2) | 입력값을 유지한 채 수정 안내 |
| `429` | `RATE_LIMITED` | 업주 신청의 진위확인 또는 사업자등록증 OCR을 오늘 5회 했음. `details.retryAfter`에 다음 초기화 시각 (3.11.14) | 내일 다시 시도 안내. OCR은 직접 입력 안내 |
| `503` | `OCR_UNAVAILABLE` | 사업자등록증 사진을 읽는 OCR 설정이 없거나 호출 실패 (3.11.12) | 직접 입력 안내 |
| `503` | `BUSINESS_VERIFICATION_UNAVAILABLE` | operator의 다시 검증에서 국세청 API에 연결하지 못함 (3.11.13) | 잠시 후 재시도 안내 |
| `503` | `TEMPORARY_WRITE_CONFLICT` | 직렬화 충돌 3회 재시도 실패 (검수 제출, 메뉴 직접 편집) | 잠시 후 같은 요청 재시도 |
| `500` | `INTERNAL_ERROR` | 예상하지 못한 서버 오류(DB 연결 실패, 코드 오류 등). 모든 API에서 생길 수 있다. 원인은 응답에 담지 않고 서버 로그에만 남긴다 | 잠시 후 재시도 안내 |
| `503` | `SERVICE_UNAVAILABLE` | 서버의 인증 설정 누락 또는 오류, Supabase JWKS 조회 실패 (3.1.5) | 잠시 후 재시도 안내. 로그인 화면으로 보내지 않음 |

라우팅이나 인증 단계에서 생긴 HTTP 오류 중 위 표에 없는 상태 코드는 같은 공통 형식에 `code = HTTP_ERROR`로 반환한다. 프론트엔드는 HTTP 상태 코드 기준의 일반 오류 메시지를 보여 준다.

> **현재 구현과의 차이 (수정 예정):** 지금 백엔드는 JSON 형식이 깨진 요청에 `400 INVALID_REQUEST` 대신 `422 VALIDATION_FAILED`를 반환한다. 이때 `fieldErrors[].code`는 `JSON_INVALID`이고 `path`는 필드 이름이 아니라 문자 위치(예: `[1]`)다. FastAPI가 JSON 해석 실패를 입력 검증 오류로 처리하기 때문이며, 위 표대로 `400 INVALID_REQUEST`를 반환하도록 백엔드를 고칠 예정이다.

### 9.3 필드 검증 오류 예시

```json
{
  "error": {
    "code": "VALIDATION_FAILED",
    "message": "입력값을 확인해 주세요.",
    "details": null,
    "fieldErrors": [
      {
        "path": "itemDecisions[0].optionDecisions[1].correctedPriceKrw",
        "code": "GREATER_THAN",
        "message": "Input should be greater than 0"
      }
    ]
  }
}
```

`fieldErrors`의 `code`와 `message`는 두 종류다.

- **요청 형식 검증**(필수값, 길이, 숫자 범위, 허용 값 등): Pydantic 오류 종류를 대문자로 바꾼 값을 `code`로 쓴다. 예: `MISSING`, `STRING_TOO_LONG`, `STRING_TOO_SHORT`, `TOO_SHORT`, `TOO_LONG`, `GREATER_THAN`, `GREATER_THAN_EQUAL`, `LESS_THAN_EQUAL`, `LITERAL_ERROR`, `UUID_PARSING`, `INT_PARSING`, `FLOAT_PARSING`, `DATE_TYPE`, `DATE_FROM_DATETIME_PARSING`, `EXTRA_FORBIDDEN`, `UNION_TAG_NOT_FOUND`, `UNION_TAG_INVALID`, `TIMEZONE_AWARE`. `message`는 Pydantic의 영어 기본 문구다.
- **업무 규칙 검증**: 백엔드가 정한 `code`와 한국어 `message`를 쓴다. 예: `BLANK`, `NOT_SEARCHABLE`, `LAT_LNG_REQUIRED_TOGETHER`, `INVALID_CURSOR`, `MISSING_ITEM`, `DUPLICATE_ITEM`, `UNKNOWN_ITEM`, `MISSING_CHANGE`, `DUPLICATE_CHANGE`, `UNKNOWN_CHANGE`, `UNKNOWN_OPTION`, `DUPLICATE_OPTION`, `DUPLICATE_OPTION_VALUES`, `EXACTLY_ONE_REQUIRED`, `NO_PRICED_OPTION`, `PRODUCT_NOT_FOUND`, `PRODUCT_INACTIVE`, `BRAND_NOT_FOUND`, `CHANGE_WITHOUT_PRODUCT`, `NOT_NORMALIZABLE`, `INVALID_BUSINESS_NUMBER`, `DATE_IN_FUTURE`, `COORDINATES_REQUIRED`, `BOUNDS_INVERTED`, `BOUNDS_TOO_LARGE`, `INVALID_CHARACTER`, `DUPLICATE_TAG`, `DUPLICATE_DAY`, `INVALID_TIME`, `SAME_OPEN_CLOSE`, `TIME_ON_CLOSED_DAY`, `DATE_IN_PAST`, `DATE_NOT_TODAY`, `END_BEFORE_START`, `IMAGE_DIMENSIONS_TOO_LARGE`, `DISCOUNT_NOT_LOWER`, `DISCOUNT_ENDED`.

### 9.4 검수 버전 충돌

`REVIEW_OUTDATED`가 발생하면 최종 반영은 전부 롤백된다. 프론트엔드는 사용자의 로컬 입력을 즉시 버리지 말고 최신 검수 응답을 받은 뒤 항목 ID 기준으로 재적용 가능한 수정값을 보여줄 수 있다. 사용자는 바뀐 diff를 확인하고 다시 제출해야 한다.

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

> **현재 구현과의 차이 (수정 예정):** 지금 백엔드는 걸린 상품 중 상품명 순으로 첫 번째를 돌려주므로, 활성 상품이 함께 걸려도 비활성 상품이 돌아올 수 있다. 메뉴 직접 편집을 구현할 때 활성 상품을 먼저 돌려주도록 고친다.

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
- `review-and-apply` 성공 전에는 카탈로그와 현재 메뉴판이 변경되지 않는다.
- 최종 요청에서 AI를 다시 호출하지 않는다.
- 최종 요청은 부분 성공하지 않는다. 하나라도 실패하면 전체 롤백한다.
- 메뉴 직접 편집(3.14)은 항목을 `barMenuItemId`로만 가리킨다. `menuBoardEntryId`와 `menuEntryOptionId`는 메뉴판이 바뀌면 달라질 수 있다.
- 메뉴 직접 편집 요청은 모두 조회한 `menuVersion`을 포함하며, 업장에 미완료 메뉴 등록 작업이 있으면 받지 않는다. 품절 표시(3.14.8)와 판매 정보 확인(3.14.9)은 예외로 검수 중에도 받는다.
- 품절 항목은 손님(비로그인 사용자와 customer)의 3.9와 고객 검색(3.10)에서 빠진다. operator와 해당 업장의 업주만 3.9에서 `soldOut = true`로 받는다.
- 할인 중인지는 프론트엔드가 `discount.startsAt`, `endsAt`과 현재 시각으로 계산한다. `priceKrw`는 항상 정가다.
- `summary`나 사용자 표시 문자열을 서버 검증 기준으로 사용하지 않는다.
- 매장 태그와 정규 영업시간은 업장 수정(3.7)에서 배열 전체를 바꾼다. 일부만 바꾸는 요청은 없다.
- 영업 상태는 서버가 계산하지 않는다. 프론트엔드가 3.15.5의 규칙으로 계산한다. `operatingException`은 `endDate` 다음 날까지 응답에 남으므로, 지금 적용 중인지도 프론트엔드가 판단한다(3.15.4).
- 매장 사진의 `imageUrl`과 `thumbnailUrl`은 만료되지 않는 고정 URL이며, 프론트엔드는 URL을 직접 만들지 않는다. 대표 사진은 `photos`의 첫 항목이며, 업장 목록 API에서는 `coverThumbnailUrl`(사진이 없으면 `null`)이다.
