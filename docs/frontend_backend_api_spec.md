# BottleMap 프론트엔드-백엔드 API 명세 초안

## 1. 목적과 범위

이 문서는 메뉴판 사진 등록부터 통합 검수와 현재 메뉴판 반영까지, 그리고 고객의 상품 검색과 업장 메뉴 조회에서 프론트엔드와 백엔드가 주고받는 HTTP API를 정의한다.

포함 범위:

- Google 로그인 후 BottleMap 사용자 확인, 인증 오류 처리
- 메뉴 사진 업로드와 비동기 처리 시작
- 처리 상태 polling
- 추출 항목·옵션·상품 후보·임시 diff 통합 조회
- 검수 중 브랜드와 상품 검색
- 모든 검수 결정의 일괄 제출과 메뉴 반영
- 고객의 상품 검색과 업장 상세 메뉴 조회
- 멱등성, 검수 버전 충돌과 공통 오류 응답

제외 범위:

- 백엔드와 OCR·LLM·Vision LLM 사이의 요청
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

## 2. 공통 규칙

### 2.1 기본 형식

- 기본 경로: `/api`
- 인증: `Authorization: Bearer <access-token>` (Supabase access token, 3.1)
- 업로드 외 요청과 응답: `application/json`
- 업로드 요청: `multipart/form-data`
- 외부 API 필드명: `camelCase`
- ID: 문자열로 표현한 UUID
- 시각: UTC 기준 RFC 3339 문자열
- 가격: 원 단위 정수
- 퍼센트·점수: 별도 표기가 없으면 `0.0`부터 `1.0`
- 값이 없다는 의미는 빈 문자열이 아니라 `null`

### 2.2 권한

현재 MVP에서 메뉴 등록·검수, 업장 관리와 카탈로그 검색 API는 `users.user_type = operator`만 호출할 수 있다. `GET /api/me`는 로그인한 customer와 operator가 모두 호출할 수 있다. 고객 검색 `GET /api/search/bars`와 활성 업장의 `GET /api/bars/{barId}/menu`는 로그인 없이(비로그인 사용자) 호출할 수 있는 공개 API다. 향후 업주 계정이 추가되어도 API 형식은 유지하고 백엔드의 업장별 권한 검사만 확장한다.

인증이 필요한 요청에서 백엔드는 다음을 검증한다.

- 토큰이 유효한가
- 호출자가 메뉴 등록 권한을 가졌는가
- 요청한 `barId` 또는 `menuImportId`가 호출자에게 허용되는가

### 2.3 주요 Enum

`MenuImportStatus`

```text
uploaded
processing
ready_for_review
applied
failed
```

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
| `GET` | `/api/bars/{barId}` | 업장 상세 조회 |
| `PATCH` | `/api/bars/{barId}` | 업장 정보 또는 활성 상태 수정 |
| `GET` | `/api/bars/{barId}/menu-imports` | 업장의 진행 중·과거 메뉴 등록 작업 조회 |
| `GET` | `/api/bars/{barId}/menu` | 업장 정보와 현재 게시 메뉴판 조회 (공개) |
| `GET` | `/api/search/bars` | 고객 상품 검색과 판매 업장 목록 조회 (공개) |
| `POST` | `/api/bars/{barId}/menu-imports` | 사진 업로드와 AI 처리 작업 생성 |
| `GET` | `/api/menu-imports/{menuImportId}` | 처리 상태 또는 통합 검수 데이터 조회 |
| `GET` | `/api/catalog/brands` | 검수 중 기존 브랜드 검색 |
| `GET` | `/api/catalog/products` | 검수 중 기존 상품 검색 |
| `POST` | `/api/menu-imports/{menuImportId}/review-and-apply` | 전체 검수 결정 제출과 원자적 반영 |

별도의 신규 브랜드·상품 생성 API는 두지 않는다. 신규 카탈로그 데이터는 `review-and-apply` 요청 안에서 제안하고 최종 트랜잭션에서 생성한다.

### 3.1 로그인과 토큰 검증

BottleMap은 로그인 API를 직접 제공하지 않는다. Google 로그인과 토큰 발급·갱신·로그아웃은 Supabase Auth의 Google provider와 Supabase SDK가 담당하고, BottleMap 백엔드는 Supabase가 발급한 access token을 검증만 한다. `users`에는 비밀번호 컬럼이 없고, Supabase 사용자 ID(token의 `sub`)를 `auth_subject`에 저장한다.

사용자는 다음과 같이 구분한다.

- **비로그인 사용자(익명 사용자)**: 로그인하지 않은 사용자다. `Authorization` 헤더 없이 공개 API(`GET /api/search/bars`, `GET /api/bars/{barId}/menu`)만 호출하며 `users` 행을 만들지 않는다.
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
6. 응답의 userType으로 고객 화면과 운영자 화면 분기

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
| `is_anonymous` | `true`면 거부 | Supabase 익명 로그인 token |

- JWKS 응답은 20분보다 오래 캐시하지 않는다. 캐시에 없는 `kid`가 오면 JWKS를 한 번 다시 조회한다. 키 교체 직후에도 정상 token을 거부하지 않기 위해서다.
- token의 `role`(`authenticated`)은 Supabase의 Postgres 역할이며 BottleMap의 `userType`이 아니다. 백엔드는 권한 판단에 사용하지 않는다.
- `user_metadata`는 사용자가 직접 바꿀 수 있는 값이다. 표시 이름의 초기값으로만 쓰고 권한 판단에는 사용하지 않는다.
- access token 수명은 Supabase 프로젝트 설정을 따르며 기본값은 1시간이다. 로그아웃하면 Supabase 세션은 삭제되지만 이미 발급된 access token은 `exp`까지 서명 검증을 통과한다. 백엔드는 세션 삭제 여부를 따로 확인하지 않으므로 프론트엔드는 로그아웃할 때 저장된 token을 함께 버린다.

#### 3.1.3 임시 로그인 (로컬 개발용)

Supabase 연동 전과 로컬 개발을 위해 `POST /api/auth/temp-login`을 유지한다. 이 API는 명시적으로 활성화해야 하며, 고정된 `local-dev-user` subject로 짧은 만료 시간의 HS256 JWT를 발급한다. 이 token은 Supabase access token이 아니다.

배포 서버에서는 앱에서 Google 로그인이 가능해질 때까지만 데모용으로 켜 둘 수 있고, Google 로그인이 가능해지면 끈다(`TEMP_AUTH_ENABLED=false`). 켜져 있는 동안에는 서버에 접근하는 누구나 같은 임시 계정을 공유하며, `TEMP_AUTH_USER_TYPE=operator`이면 operator 권한을 얻는다.

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
- 임시 사용자의 `user_type`은 `TEMP_AUTH_USER_TYPE=customer|operator` 서버 환경 변수를 따른다. 값을 바꾸면 다음 요청부터 반영된다. 요청에서 역할을 선택할 수는 없다.

| 상황 | 응답 |
|---|---|
| `TEMP_AUTH_ENABLED`가 `true`가 아님 | `POST /api/auth/temp-login`이 `404 NOT_FOUND`. API가 없는 것처럼 응답한다 |
| `TEMP_AUTH_JWT_SECRET`이 32자 미만이거나 `TEMP_AUTH_USER_TYPE`이 `customer`·`operator`가 아님 | `POST /api/auth/temp-login`이 `503 SERVICE_UNAVAILABLE` |
| 임시 token을 받았지만 서버의 `TEMP_AUTH_JWT_SECRET`이 없거나 32자 미만, 또는 `TEMP_AUTH_USER_TYPE`이 `customer`·`operator`가 아님 | 토큰이 필요한 API가 `503 SERVICE_UNAVAILABLE` |

#### 3.1.4 기본 사용자 유형과 운영자 권한

- 최초 가입한 사용자는 항상 `customer`다. 신규 가입자를 자동으로 `operator`로 만들지 않는다.
- 클라이언트 요청이나 token claim(`user_metadata` 포함)으로 `userType`을 바꿀 수 없다. 권한은 매 요청 BottleMap DB의 `users.user_type`에서 읽는다.
- `operator` 전환과 업주(바 사장) 등록은 이후 별도 기능으로 정의하며 이 문서의 범위가 아니다. 그전까지 로컬에서 operator API를 시험할 때는 임시 로그인과 `TEMP_AUTH_USER_TYPE=operator`를 사용한다.
- `GET /api/me`만 사용자를 생성한다. `users` 행이 없는 사용자가 다른 인증 API를 먼저 호출하면 `customer`와 같게 처리하므로, operator 전용 API는 `403 FORBIDDEN`이다. `PATCH /api/me`는 `404 USER_NOT_FOUND`다(3.3).

#### 3.1.5 인증 오류와 프론트엔드 처리

인증 오류는 9.1의 공통 오류 형식을 사용한다. 원인이 달라도 `401`은 모두 `UNAUTHENTICATED` 한 가지 code이고, 응답 header에 `WWW-Authenticate: Bearer`가 포함된다. 프론트엔드는 `message`로 원인을 구분하지 않는다.

| HTTP | code | 발생 조건 | 프론트엔드 처리 |
|---|---|---|---|
| `401` | `UNAUTHENTICATED` | 인증이 필요한 API에 `Authorization` 헤더가 없음 | 로그인 화면으로 이동 |
| `401` | `UNAUTHENTICATED` | access token 만료 | 아래 재시도 흐름 |
| `401` | `UNAUTHENTICATED` | 서명 오류, 알 수 없는 `kid`, `iss`·`aud` 불일치, 필수 claim 누락, `is_anonymous = true`, 임시 로그인이 꺼진 서버에 보낸 임시 token | 아래 재시도 흐름 |
| `403` | `FORBIDDEN` | 로그인했지만 `operator`가 아닌 사용자가 operator 전용 API 호출 | 접근 차단 안내. 재시도하거나 로그인 화면으로 보내지 않는다. `GET /api/me`를 다시 불러 화면 권한을 갱신할 수 있다 |
| `503` | `SERVICE_UNAVAILABLE` | 서버 인증 설정 누락(`SUPABASE_URL` 등), Supabase JWKS 조회 실패, 임시 인증 설정 오류 | 잠시 후 재시도 안내. 로그인 화면으로 보내지 않고 저장된 세션을 유지한다 |

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
  - `GET /api/bars/{barId}/menu`는 `Authorization` 헤더가 있으면 token을 검증하고, 잘못된 token이면 `401`을 반환한다. 프론트엔드는 위 재시도 흐름을 똑같이 적용하되, 세션 갱신에 실패하면 로그인 화면으로 보내지 않고 로그아웃한 뒤 헤더 없이 비로그인 사용자로 다시 요청한다.
  - `GET /api/search/bars`는 `Authorization` 헤더를 사용하지 않는다.

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

운영자 전용 화면은 `userType = operator`일 때만 보여 준다. 오류는 3.1.5를 따른다.

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
      "barId": "bar-001",
      "name": "관악 위스키 바",
      "address": "서울특별시 관악구 관악로 1, 2층",
      "latitude": 37.123456,
      "longitude": 126.123456,
      "phone": "02-000-0000",
      "status": "active",
      "activeMenuImport": {
        "menuImportId": "import-001",
        "status": "ready_for_review"
      }
    }
  ],
  "nextCursor": null
}
```

`activeMenuImport`는 미완료 작업이 없으면 `null`이다. 목록 화면이 별도 요청 없이 기존 작업으로 진입할 수 있도록 제공한다.

### 3.5 업장 생성

```http
POST /api/bars
Authorization: Bearer <access-token>
Content-Type: application/json
```

```json
{
  "name": "관악 위스키 바",
  "address": "서울특별시 관악구 관악로 1, 2층",
  "latitude": 37.123456,
  "longitude": 126.123456,
  "phone": "02-000-0000"
}
```

```http
HTTP/1.1 201 Created
Location: /api/bars/bar-001
```

```json
{
  "barId": "bar-001",
  "name": "관악 위스키 바",
  "address": "서울특별시 관악구 관악로 1, 2층",
  "latitude": 37.123456,
  "longitude": 126.123456,
  "phone": "02-000-0000",
  "status": "active",
  "createdAt": "2026-10-04T09:00:00Z",
  "updatedAt": "2026-10-04T09:00:00Z"
}
```

백엔드는 이름·주소가 비슷한 기존 업장을 조회해 중복 가능성을 경고할 수 있지만 이름 유사성만으로 생성을 자동 차단하지 않는다.

### 3.6 업장 상세 조회

```http
GET /api/bars/{barId}
Authorization: Bearer <access-token>
```

```json
{
  "barId": "bar-001",
  "name": "관악 위스키 바",
  "address": "서울특별시 관악구 관악로 1, 2층",
  "latitude": 37.123456,
  "longitude": 126.123456,
  "phone": "02-000-0000",
  "status": "active",
  "activeMenuImport": null,
  "currentMenu": {
    "menuBoardId": "menu-board-001",
    "publishedAt": "2026-10-04T09:15:00Z"
  },
  "createdAt": "2026-10-01T03:00:00Z",
  "updatedAt": "2026-10-04T09:15:00Z"
}
```

### 3.7 업장 수정과 비활성화

```http
PATCH /api/bars/{barId}
Authorization: Bearer <access-token>
Content-Type: application/json
```

변경할 필드만 전송한다.

```json
{
  "phone": "02-111-2222",
  "status": "inactive"
}
```

```json
{
  "barId": "bar-001",
  "name": "관악 위스키 바",
  "address": "서울특별시 관악구 관악로 1, 2층",
  "latitude": 37.123456,
  "longitude": 126.123456,
  "phone": "02-111-2222",
  "status": "inactive",
  "updatedAt": "2026-10-04T10:10:00Z"
}
```

업장을 물리 삭제하는 API는 두지 않는다. 운영 중단은 `status = inactive`로 처리해 메뉴 등록과 이미지 이력을 유지한다.

### 3.8 업장별 메뉴 등록 작업 목록

화면을 닫았다가 다시 열어도 진행 중인 작업으로 복귀하고, 완료·실패 작업을 확인하기 위한 API다.

```http
GET /api/bars/{barId}/menu-imports?status=active&limit=20&cursor=<cursor>
Authorization: Bearer <access-token>
```

| Query | 필수 | 기본값 | 설명 |
|---|---|---|---|
| `status` | 아니오 | `all` | `active`, `uploaded`, `processing`, `ready_for_review`, `applied`, `failed`, `all` |
| `limit` | 아니오 | `20` | 최대 `100` |
| `cursor` | 아니오 | 없음 | 다음 페이지 cursor |

`active`는 저장 Enum이 아니라 `uploaded`, `processing`, `ready_for_review`를 묶는 API 필터다.

```json
{
  "items": [
    {
      "menuImportId": "import-001",
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

```http
GET /api/bars/{barId}/menu
```

고객 업장 상세 화면과 운영자 화면이 함께 사용한다. 활성 업장의 현재 메뉴 조회는 인증 없이 허용한다. 비활성 업장은 operator만 조회할 수 있으며, 인증하지 않은 호출에는 업장이 없는 경우와 같은 `404 BAR_NOT_FOUND`를 반환한다.

고객 업장 상세 화면이 별도 요청 없이 이름, 주소와 지도 위치를 표시할 수 있도록 업장 기본 정보를 함께 반환한다.

```json
{
  "barId": "bar-001",
  "name": "관악 위스키 바",
  "address": "서울특별시 관악구 관악로 1, 2층",
  "latitude": 37.123456,
  "longitude": 126.123456,
  "phone": "02-000-0000",
  "menuBoardId": "menu-board-001",
  "publishedAt": "2026-10-04T09:15:00Z",
  "items": [
    {
      "menuBoardEntryId": "entry-001",
      "barMenuItemId": "bar-menu-item-001",
      "productId": "product-deanston-12",
      "displayName": "Deanston 12",
      "sortOrder": 1,
      "options": [
        {
          "menuEntryOptionId": "entry-option-001",
          "optionLabel": null,
          "pourMl": 15,
          "priceKrw": 8000,
          "sortOrder": 1
        },
        {
          "menuEntryOptionId": "entry-option-002",
          "optionLabel": null,
          "pourMl": 30,
          "priceKrw": 15000,
          "sortOrder": 2
        }
      ]
    }
  ]
}
```

현재 게시 메뉴가 없으면 `200 OK`로 빈 상태를 반환한다.

```json
{
  "barId": "bar-001",
  "name": "관악 위스키 바",
  "address": "서울특별시 관악구 관악로 1, 2층",
  "latitude": 37.123456,
  "longitude": 126.123456,
  "phone": "02-000-0000",
  "menuBoardId": null,
  "publishedAt": null,
  "items": []
}
```

`items[].displayName`은 업장 메뉴판에 적힌 표기(`menu_board_entries.display_name`)이고, `productId`는 정규 상품 ID다. 검색 결과에서 진입한 경우 프론트엔드는 검색한 `productId`와 같은 항목을 강조해 표시할 수 있다.

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

고객 위치는 거리 계산에만 사용하며 서버에 저장하지 않는다.

#### 3.10.1 검색어 해석

검색어는 메뉴 등록의 상품 매칭과 같은 백엔드 공통 정규화 함수로 정규화한다. 검색 시점에는 임베딩과 LLM을 호출하지 않고, 아래 단계를 순서대로 시도해 활성 상품을 하나라도 찾은 단계에서 멈춘다. 찾은 상품을 판매하는 업장이 없어도 다음 단계로 넘어가지 않는다.

```text
1. alias_exact
   product_aliases.normalized_alias 정확 일치
   (is_searchable = true, products.is_active = true)

2. brand
   brand_aliases.normalized_alias 정확 일치
   → 해당 브랜드의 활성 상품 전체

3. partial
   is_searchable 상품 별칭 중 정규화 검색어를 포함하는 별칭
   → 일치한 상품 최대 10개 (일치한 별칭이 짧은 상품부터)

4. none
   일치하는 상품 없음
```

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

정렬 기준:

```text
items
  lat·lng가 있으면  distanceMeters 오름차순
  lat·lng가 없으면  menuUpdatedAt 내림차순
  동점이면          barName → productDisplayName → barId → productId 오름차순

matchedProducts
  alias_exact, brand  displayName 오름차순
  partial             일치한 별칭이 짧은 상품부터, 같으면 displayName 오름차순

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
      "productId": "44444444-4444-4444-8444-444444444444",
      "productDisplayName": "Glenfiddich 12",
      "menuDisplayName": "글렌피딕 12년",
      "options": [
        {
          "optionLabel": "잔",
          "pourMl": 30,
          "priceKrw": 17000,
          "sortOrder": 1
        },
        {
          "optionLabel": "병",
          "pourMl": null,
          "priceKrw": 160000,
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
      "productId": "44444444-4444-4444-8444-444444444444",
      "productDisplayName": "Glenfiddich 12",
      "menuDisplayName": "Glenfiddich 12Y",
      "options": [
        {
          "optionLabel": null,
          "pourMl": 15,
          "priceKrw": 9000,
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
| `items[].latitude`, `items[].longitude` | 숫자 | 아니오 | 업장 좌표 |
| `items[].distanceMeters` | 정수 | 예 | 고객 위치와 업장 사이의 직선 거리(미터). 위치를 보내지 않으면 `null` |
| `items[].productId` | UUID 문자열 | 아니오 | `matchedProducts`의 상품 중 하나 |
| `items[].productDisplayName` | 문자열 | 아니오 | 정규 상품명(`products.display_name`) |
| `items[].menuDisplayName` | 문자열 | 아니오 | 업장 메뉴판에 적힌 표기(`menu_board_entries.display_name`) |
| `items[].options` | 배열 | 아니오 | 해당 항목의 가격·용량 옵션 전체. 최소 1개. 결과 카드에 어떤 옵션을 표시할지는 프론트엔드가 정한다 |
| `items[].options[].optionLabel` | 문자열 | 예 | 메뉴판의 `잔`, `병` 같은 표기. 없으면 `null` |
| `items[].options[].pourMl` | 정수 | 예 | 용량(ml). 메뉴판에 없으면 `null` |
| `items[].options[].priceKrw` | 정수 | 아니오 | 가격(원) |
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
- 네트워크 오류와 `5xx`는 오류 상태와 재시도 버튼을 보여 준다.

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
| `ownerNote` | 문자열 | 아니오 | 촬영 출처나 작업 메모 |
| `images` | 이미지 파일 배열 | 예 | 표시 순서대로 전송한 메뉴 사진 |

예시:

```text
mode       = full_replace
ownerNote  = 2026년 10월 메뉴판
images     = [menu-page-1.jpg, menu-page-2.jpg]
```

MVP 업로드 제한:

```text
허용 형식       JPEG, PNG
사진 최대 개수  5장
사진당 최대 크기 10MB
전체 최대 크기  30MB
```

파일 형식은 확장자가 아니라 파일 내용으로 판별하며, 선언한 MIME 형식과 다르면 거절한다(`415 UNSUPPORTED_IMAGE_TYPE`). AI 추출 모듈이 JPEG와 PNG만 모델에 보내므로 HEIC 같은 다른 형식은 받지 않는다. 안드로이드 앱은 다른 형식의 사진을 JPEG로 바꿔 올린다.

배열 순서가 `imageOrder`가 된다. 프론트엔드는 업로드 재시도 시 파일 순서를 바꾸지 않아야 한다.

### 4.2 성공 응답

AI 결과를 기다리지 않고 작업 생성 직후 반환한다.

```http
HTTP/1.1 202 Accepted
Location: /api/menu-imports/import-001
Retry-After: 3
```

```json
{
  "menuImportId": "import-001",
  "status": "processing",
  "imageCount": 2,
  "statusUrl": "/api/menu-imports/import-001",
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

한 업장에는 `uploaded`, `processing`, `ready_for_review` 상태의 미완료 작업을 하나만 허용한다.

## 5. 메뉴 등록 상태와 통합 검수 조회

### 5.1 요청

```http
GET /api/menu-imports/{menuImportId}
Authorization: Bearer <access-token>
```

이 API는 상태에 따라 응답 본문이 달라진다.

### 5.2 처리 중 응답

```json
{
  "menuImportId": "import-001",
  "status": "processing",
  "progress": {
    "totalImages": 2,
    "completedImages": 1,
    "failedImages": 0
  },
  "pollAfterMs": 3000
}
```

`completedImages`는 AI 호출, 응답 검증과 추출 저장까지 성공한 이미지 수다. 후보 생성과 임시 diff는 모든 이미지의 추출이 끝난 뒤 한 번에 만들므로, 모든 이미지가 완료돼도 잠시 `processing` 상태일 수 있다. 프론트엔드는 이 숫자를 정확한 전체 처리율로 간주하지 않고 진행 안내에만 사용한다.

### 5.3 실패 응답

HTTP 요청 자체는 성공했지만 비동기 작업이 최종 실패한 경우 `200 OK`와 `status = failed`를 반환한다.

```json
{
  "menuImportId": "import-001",
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
  "menuImportId": "import-001",
  "barId": "bar-001",
  "mode": "full_replace",
  "status": "ready_for_review",
  "reviewVersion": 3,
  "images": [
    {
      "imageId": "image-001",
      "imageOrder": 1,
      "imageUrl": "https://cdn.example.com/signed/menu-image-001",
      "imageUrlExpiresAt": "2026-10-04T09:30:00Z",
      "items": [
        {
          "extractedItemId": "item-007",
          "itemOrder": 7,
          "rawText": "딘스톤 12년 15ml 8.0 / 30ml 15.0",
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
          "proposedProductId": "product-deanston-12",
          "options": [
            {
              "extractedOptionId": "option-001",
              "optionOrder": 1,
              "extractedOptionLabel": null,
              "extractedPourMl": 15,
              "extractedPriceKrw": 8000
            },
            {
              "extractedOptionId": "option-002",
              "optionOrder": 2,
              "extractedOptionLabel": null,
              "extractedPourMl": 30,
              "extractedPriceKrw": 15000
            }
          ],
          "candidates": [
            {
              "productId": "product-deanston-12",
              "candidateRank": 1,
              "displayName": "Deanston 12",
              "brandId": "brand-deanston",
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
      "changeId": "change-001",
      "changeType": "add",
      "barMenuItemId": null,
      "extractedItemId": "item-007",
      "before": null,
      "after": {
        "productId": "product-deanston-12",
        "displayName": "Deanston 12",
        "options": [
          {
            "extractedOptionId": "option-001",
            "optionLabel": null,
            "pourMl": 15,
            "priceKrw": 8000
          },
          {
            "extractedOptionId": "option-002",
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
- `imageUrl`은 짧은 만료 시간을 가진 서명 URL이다.
- `extractedLineType`은 AI의 최초 분류이며 검수 후에도 변경되지 않는다.
- `correctedLineType`은 운영자가 최초 분류를 바꾼 경우에만 값이 있고, 그대로 승인한 경우 `null`이다.
- `effectiveLineType`은 `correctedLineType ?? extractedLineType`으로 계산한 현재 검수 기준 역할이다.
- `initialResolutionStatus`는 최초 상품 매칭 결과다. `exact_match`는 충돌 없는 단일 정확 별칭 일치, `ambiguous`는 검토할 후보가 있으나 정확 단일 일치가 아닌 상태, `unmatched`는 유효 후보가 없는 상태다. 최초 분류가 비상품이라 매칭하지 않은 항목은 `null`이다.
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
  "menuImportId": "import-001",
  "barId": "bar-001",
  "status": "applied",
  "reviewVersion": 3,
  "appliedAt": "2026-10-04T09:15:00Z",
  "menuBoardId": "menu-board-001"
}
```

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
      "brandId": "brand-deanston",
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
GET /api/catalog/products?query=%EB%94%98%EC%8A%A4%ED%86%A4%2012&brandId=brand-deanston&includeInactive=true&limit=20
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
      "productId": "product-deanston-12",
      "displayName": "Deanston 12",
      "brandId": "brand-deanston",
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

비활성 상품은 중복 확인을 위해 보여줄 수 있지만, 그대로 메뉴에 연결하려면 백엔드 정책에 따라 활성화 절차가 추가로 필요할 수 있다.

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

한 화면의 결정을 한 번에 제출하며 중간 항목 저장 API는 사용하지 않는다.

### 8.2 기존 상품 선택 예시

```json
{
  "reviewVersion": 3,
  "itemDecisions": [
    {
      "extractedItemId": "item-007",
      "finalLineType": "product",
      "action": "select_existing_product",
      "productId": "product-deanston-12",
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
          "extractedOptionId": "option-001",
          "correctedOptionLabel": null,
          "correctedPriceKrw": 8000,
          "correctedPourMl": 15
        },
        {
          "extractedOptionId": "option-002",
          "correctedOptionLabel": null,
          "correctedPriceKrw": 15000,
          "correctedPourMl": 30
        }
      ]
    }
  ],
  "changeDecisions": [
    {
      "changeId": "change-001",
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
  "extractedItemId": "item-003",
  "finalLineType": "section_header",
  "action": "confirm_non_product"
}
```

`confirm_non_product`의 `finalLineType`은 `section_header`, `description`, `unknown` 중 하나여야 하며 상품과 옵션 필드를 보내지 않는다.

### 8.4 항목 제외 예시

```json
{
  "extractedItemId": "item-004",
  "finalLineType": "unknown",
  "action": "reject"
}
```

OCR 잡음, 중복 인식 또는 사용할 수 없는 항목에 사용한다.

### 8.5 기존 브랜드로 신규 상품 생성

```json
{
  "extractedItemId": "item-007",
  "finalLineType": "product",
  "action": "create_product",
  "correctedProductName": "딘스톤 버진 오크",
  "brand": {
    "type": "existing",
    "brandId": "brand-deanston"
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
      "extractedOptionId": "option-001",
      "correctedPriceKrw": 12000,
      "correctedPourMl": 15
    }
  ]
}
```

### 8.6 신규 브랜드와 신규 상품 생성

```json
{
  "extractedItemId": "item-009",
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
      "extractedOptionId": "option-003",
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

### 8.8 성공 응답

```http
HTTP/1.1 200 OK
```

```json
{
  "menuImportId": "import-001",
  "status": "applied",
  "reviewVersion": 3,
  "appliedAt": "2026-10-04T09:15:00Z",
  "menuBoardId": "menu-board-001",
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
      "menuImportId": "import-001",
      "submittedReviewVersion": 2,
      "currentReviewVersion": 3,
      "reviewUrl": "/api/menu-imports/import-001"
    },
    "fieldErrors": []
  }
}
```

`error.message`는 사용자 표시가 가능한 한국어 기본 문구다. 프론트엔드는 분기 처리에 `message`가 아니라 `code`를 사용한다. `fieldErrors[].message`는 9.3처럼 영어일 수 있으므로, 프론트엔드는 필드 오류를 표시할 때 `code`를 기준으로 자체 문구를 보여 준다.

### 9.2 주요 오류 코드

| HTTP | code | 발생 조건 | 프론트엔드 처리 |
|---|---|---|---|
| `400` | `INVALID_REQUEST` | JSON 또는 multipart 형식 오류 | 요청 구성 확인 |
| `401` | `UNAUTHENTICATED` | 토큰 없음, 만료, 서명·claim 오류 (3.1.5) | 세션 갱신 후 한 번 재시도. 실패하면 로그인 이동 |
| `403` | `FORBIDDEN` | operator가 아닌 사용자의 operator 전용 API 호출, 또는 업장·작업 접근 권한 없음 | 접근 차단 |
| `404` | `BAR_NOT_FOUND` | 업장이 없음 | 이전 화면 이동 |
| `404` | `MENU_IMPORT_NOT_FOUND` | 등록 작업이 없음 | 작업 목록 이동 |
| `404` | `USER_NOT_FOUND` | `GET /api/me`로 사용자를 만들기 전에 `PATCH /api/me` 호출 | `GET /api/me` 호출 후 같은 요청 재시도 |
| `404` | `NOT_FOUND` | 존재하지 않는 경로, 또는 비활성화된 임시 로그인 호출 | 요청 경로·서버 설정 확인 |
| `405` | `METHOD_NOT_ALLOWED` | 경로는 있지만 허용하지 않는 HTTP 메서드 | 요청 메서드 확인 |
| `409` | `IDEMPOTENCY_KEY_REUSED` | 같은 키에 다른 요청 내용 | 새 키로 명시적 재요청 |
| `409` | `ACTIVE_IMPORT_EXISTS` | 업장에 미완료 작업이 이미 있음 | 기존 작업으로 이동 |
| `409` | `INVALID_IMPORT_STATE` | 현재 상태에서 요청 불가 | 상태 재조회 |
| `409` | `REVIEW_OUTDATED` | `reviewVersion` 불일치, 또는 검수 데이터를 만든 뒤 현재 메뉴판이 바뀜 | `details.reviewUrl`로 최신 검수 데이터 재조회 |
| `409` | `DUPLICATE_BRAND_FOUND` | 신규 브랜드와 동일할 수 있는 브랜드 발견 | 기존 브랜드 선택 화면 표시 |
| `409` | `DUPLICATE_PRODUCT_FOUND` | 신규 상품과 동일한 상품 발견, 또는 제출한 이름·별칭이 기존 상품의 별칭과 일치 | 기존 상품 선택 화면 표시. 다른 상품이면 겹치는 별칭을 빼고 다시 제출 |
| `413` | `UPLOAD_TOO_LARGE` | 파일 개수 또는 크기 초과 | 이미지 축소 또는 개수 조정 |
| `415` | `UNSUPPORTED_IMAGE_TYPE` | 지원하지 않는 이미지 형식 | 지원 형식 안내 |
| `422` | `VALIDATION_FAILED` | 필드 값이나 옵션 구성이 잘못됨 | `fieldErrors` 표시 |
| `503` | `TEMPORARY_WRITE_CONFLICT` | 직렬화 충돌 3회 재시도 실패 | 잠시 후 동일 검수 요청 재시도 |
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

- **요청 형식 검증**(필수값, 길이, 숫자 범위, 허용 값 등): Pydantic 오류 종류를 대문자로 바꾼 값을 `code`로 쓴다. 예: `MISSING`, `STRING_TOO_LONG`, `STRING_TOO_SHORT`, `GREATER_THAN`, `GREATER_THAN_EQUAL`, `LESS_THAN_EQUAL`, `LITERAL_ERROR`, `UUID_PARSING`, `INT_PARSING`, `FLOAT_PARSING`, `EXTRA_FORBIDDEN`. `message`는 Pydantic의 영어 기본 문구다.
- **업무 규칙 검증**: 백엔드가 정한 `code`와 한국어 `message`를 쓴다. 예: `BLANK`, `NOT_SEARCHABLE`, `LAT_LNG_REQUIRED_TOGETHER`, `INVALID_CURSOR`, `MISSING_ITEM`, `DUPLICATE_ITEM`, `UNKNOWN_ITEM`, `MISSING_CHANGE`, `DUPLICATE_CHANGE`, `UNKNOWN_CHANGE`, `UNKNOWN_OPTION`, `DUPLICATE_OPTION`, `DUPLICATE_OPTION_VALUES`, `NO_PRICED_OPTION`, `PRODUCT_NOT_FOUND`, `PRODUCT_INACTIVE`, `BRAND_NOT_FOUND`, `CHANGE_WITHOUT_PRODUCT`, `NOT_NORMALIZABLE`.

### 9.4 검수 버전 충돌

`REVIEW_OUTDATED`가 발생하면 최종 반영은 전부 롤백된다. 프론트엔드는 사용자의 로컬 입력을 즉시 버리지 말고 최신 검수 응답을 받은 뒤 항목 ID 기준으로 재적용 가능한 수정값을 보여줄 수 있다. 사용자는 바뀐 diff를 확인하고 다시 제출해야 한다.

### 9.5 신규 상품 중복 발견

```json
{
  "error": {
    "code": "DUPLICATE_PRODUCT_FOUND",
    "message": "동일한 상품이 먼저 등록되었습니다.",
    "details": {
      "extractedItemId": "item-007",
      "existingProduct": {
        "productId": "product-existing",
        "displayName": "Deanston Virgin Oak",
        "brandId": "brand-deanston",
        "brandName": "Deanston",
        "category": "whisky",
        "ageYears": null,
        "editionName": "Virgin Oak"
      },
      "reviewUrl": "/api/menu-imports/import-001"
    },
    "fieldErrors": []
  }
}
```

이 경우 신규 상품은 생성되지 않고 `menuImport`는 `ready_for_review`를 유지한다.

## 10. 프론트엔드 상태 처리 기준

```text
uploaded 또는 processing
→ 로딩 화면
→ pollAfterMs 후 GET 재호출

ready_for_review
→ images, items, candidates, proposedChanges로 통합 검수 화면 구성

failed
→ failure 메시지 표시
→ 사용자가 새 업로드 작업을 시작하도록 안내

applied
→ 반영 완료 화면
→ 현재 메뉴판으로 이동 가능
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
- `summary`나 사용자 표시 문자열을 서버 검증 기준으로 사용하지 않는다.
