# I5-P19 후속: 키 제약, 서버 전체 한도, 실제 경로 확인 (2026-11-26)

지시 문서: `../_outgoing/i5_p19_followup_handoff.md`. 브랜치 `feature/i5-p19-openrouter-extraction`. push하지 않았다. 단계가 끝날 때마다 이 문서에 절을 더한다.

## 요약 (C~G, 2026-11-26)

진우가 다시 정해야 하는 것이 두 가지 생겼다.

- **Sonnet 5.5가 회귀 17장에서 가격을 틀렸다 (E).** 복춘_03의 병 가격 6칸을 모두 1/10로 썼고, 미라보_02의 제목 4줄이 빠졌다. 6장에서 통과해 대체 모델로 넣기로 했지만, 17장에는 통과 기준을 못 넘는다. **진우 결정 (2026-11-26): 대체 모델에 그대로 둔다.**
- **2단계(Gemini 3.8 Flash 직접, 무료 키)가 세 번 모두 응답하지 않았다 (D).** 약 한 시간에 걸쳐 3회 모두 503("수요 과다")이었다. 모델 ID는 맞다. 지금 구성에서 OpenRouter가 막히면 실제로 받는 것은 flash-lite(3단계)일 가능성이 크다.

그 밖에:

- 키에는 과목이 건 한도가 있다: 총 $100, 남은 $92.36, 만료 2026-12-20 (C).
- 1단계 Sonnet 호출과 3단계 flash-lite + 프롬프트 v2.1은 실제 API로 한 번씩 동작을 확인했다 (D).
- "가격이 없고 상자가 가장자리에 닿은 행" 규칙은 옆 페이지 60행을 모두 잡는다. 회귀 17장에서는 다른 행을 버리지 않는다 (F).
- PDF 페이지가 새 경로와 두 한도를 타게 준비했고, UAT PDF 3개(5쪽)를 실제로 돌려 기대 줄 24개를 모두 찾았다 (G).
- C~G에 쓴 비용: OpenRouter $1.074 (D $0.042, E $0.983, G $0.050). Gemini 직접 호출 10회(무료 키: D 7회, G 3회), CLOVA 2회.

## A. 키 제약 반영 (문서만)

커밋 `48170149`.

- OpenRouter 키는 과목에서 발급해 준 하나뿐이다. 키를 더 만들 수 없고 대시보드에서 키 한도를 걸 수도 없다. 실험과 서버가 같은 키, 같은 크레딧을 쓴다.
- P19 보고서 6절, `DEPLOY.md`, `env.production.example`에서 "서버용 키를 따로 만들고 한도를 건다"를 지우고 이 전제를 적었다.
- 서버와 평가용 호출은 요청 헤더 `X-Title`로만 구분된다(서버 `bottlemap-menu-extraction`, 평가 스크립트 `menu-extraction-eval`).
- 계정의 데이터 수집 설정은 볼 수 없다. 요청마다 넣는 `provider.data_collection: "deny"`가 유일한 장치다.

## B. 서버 전체 하루 한도

### B.1 한눈에

- **새 테이블 없이 구현했다.** 이미 저장되는 추출 기록(`extraction_runs.raw_output.route`와 `completed_at`)에서 "오늘 OpenRouter 경로로 읽은 사진 수"를 셀 수 있다. 마이그레이션이 없다.
- 설정 `OPENROUTER_DAILY_PHOTO_LIMIT`, 기본 300장. 서버 전체, 한국 시간 하루 단위.
- 넘으면 거절하지 않는다. 그날 남은 사진은 2단계(Gemini 직접)부터 시작한다.
- **재시작해도 남는다.** 재시작 뒤 첫 사진에서 추출 기록을 다시 세어 이어 간다.
- **A2(계정당 30장)는 같은 방법으로 유지할 수 없다.** 등록 기록에 올린 계정이 저장되지 않는다(B.5).
- 모델 호출 0회, 쓴 비용 $0.

### B.2 동작

| 상황 | 동작 |
|---|---|
| 오늘 센 수가 한도 미만 | 0단계(OpenRouter)로 보내고 1장 센다 |
| 한도에 닿음 | OpenRouter를 부르지 않고 2단계부터 시작한다. 기록의 `route.skipped`에 `{"stage": 0, "reason": "daily_paid_limit", "limit": 300}` |
| OpenRouter가 응답하지 않음(재시도 끝에 실패, 402) | 센 1장을 되돌린다. 읽지 못했고 청구도 없다 |
| OpenRouter가 답했는데 스키마가 아님, 두 번 잘림 | 되돌리지 않는다. 청구된 호출이다 |
| 대체 모델(1단계)이 읽음 | 1장으로 센다 |
| 차단기가 열려 OpenRouter를 건너뜀 | 세지 않는다 |
| 한국 시간 자정 | 그날 기록을 다시 세어 0부터 시작한다 |
| 센 수를 읽지 못함(DB 불통) | 한도를 넘은 것으로 보고 2단계부터 시작한다. 다음 사진에서 다시 읽는다 |

로그(WARNING, 서비스 로그에 보인다):

```text
extraction route stage=0 skipped: daily_paid_limit (today's 300 photos through OpenRouter are used up, or could not be counted); starting at stage 2
extraction route stage=2 path=gemini-direct model=... skipped=0:daily_paid_limit
```

### B.3 세는 방법

오늘(KST) 끝난 추출 기록 중 OpenRouter 경로로 읽은 것을 센다.

- 성공한 기록: `raw_output.route.stage`가 0 또는 1.
- OpenRouter가 답한 뒤 실패한 기록: `raw_output.output.route.stage`가 0 또는 1 (등록 처리가 실패 기록의 원문을 `output` 아래에 둔다).
- 세지 않는 것: 2·3단계로 읽은 기록, `MENU_EXTRACTOR=gemini`의 기록(`route` 없음), 모든 경로가 실패한 기록(`stage` 4), 재시작으로 중단된 기록.

PostgreSQL에서 실행되는 문장:

```sql
SELECT count(*) FROM extraction_runs
WHERE completed_at >= '<오늘 KST 자정>'
  AND (CAST(((raw_output -> 'route') ->> 'stage') AS INTEGER) IN (0, 1)
    OR CAST((((raw_output -> 'output') -> 'route') ->> 'stage') AS INTEGER) IN (0, 1))
```

- 이 조회는 재시작 뒤 한 번, 날짜가 바뀔 때 한 번만 한다. 그 사이에는 메모리에서 센다. 사진마다 DB를 읽지 않는다.
- 사진을 OpenRouter에 보내기 전에 자리를 먼저 잡는다. 동시에 처리되는 등록들이 함께 한도를 넘지 못한다.

**정확하지 않은 경우** (모두 덜 세는 쪽이고 규모가 작다)

- 재시작 순간 처리 중이던 사진: 기록이 끝나지 않아 세지 않는다. 복구로 다시 읽을 때 센다.
- 추출 도중 취소된 등록의 사진: 응답이 저장되지 않아 재시작 뒤에는 세지 않는다.
- 같은 키로 돌린 평가 실행: 서버의 추출 기록이 아니므로 세지 않는다. 이 한도는 서버가 쓴 사진만 막는다.

### B.4 운영자 초기화

**만들지 않았다.** 추출 기록에서 세는 방식이라 "지우기"는 기록을 고쳐야만 된다. 대신 설정값으로 충분하다고 판단했다.

- 오늘 더 쓰게 하려면: `OPENROUTER_DAILY_PHOTO_LIMIT`를 올리고 재시작한다. 센 수는 유지된다.
- 당장 지출을 멈추려면: 값을 `1`로 낮추거나 `MENU_EXTRACTOR=gemini`로 되돌린다. 0은 설정값 검사에서 거절된다.
- 재시작이 필요하다는 점이 초기화 API와의 차이다. 재시작하면 처리 중이던 등록은 복구로 이어진다.

### B.5 A2(계정당 30장)를 재시작 뒤에도 유지할 수 있는가

**지금 스키마로는 안 된다.** `menu_imports`에는 올린 계정이 없다(`bar_id`, `created_at`만 있다). `menu_images.uploaded_at`은 있지만 누가 올렸는지는 없다. 그래서 "이 계정이 오늘 올린 사진 수"를 기록에서 셀 수 없다.

필요한 스키마 변경(해울 영역, 구현하지 않았다):

| 변경 | 내용 |
|---|---|
| `menu_imports`에 열 추가 | 올린 계정. `users` 행이 없는 호출자(임시 로그인 operator)도 있으므로 `users.id`보다 token의 `sub`를 문자열로 저장하는 쪽이 한도 장치와 맞는다. 예: `uploaded_by_subject varchar(255) null` |
| 인덱스 | `(uploaded_by_subject, created_at)` |
| 코드 | 업로드할 때 열을 채우고, 한도 장치가 재시작 뒤 `menu_images`를 `menu_imports`와 묶어 오늘 수를 센다 |

- 열이 생기면 이번 서버 전체 한도와 같은 방식(기록에서 읽고 메모리에서 센다)으로 바꿀 수 있다.
- 바꾸지 않으면 지금처럼 배포할 때마다 모든 계정이 다시 30장을 쓴다. 다만 서버 전체 한도 300장이 재시작 뒤에도 남으므로, 배포를 여러 번 해도 하루 지출은 300장분을 넘지 않는다.
- 고칠지는 진우가 정한다.

### B.6 테스트

`backend/tests/test_paid_photo_budget.py` 23개. 추출 기록은 메모리 SQLite에 `extraction_runs` 테이블만 만들어 쓰고, OpenRouter와 Gemini는 가짜다.

| 지시 문서의 항목 | 테스트 |
|---|---|
| 한도 직전 | 마지막 자리까지 OpenRouter로 가고 센다 |
| 초과 후 2단계로 시작 | OpenRouter를 부르지 않고 Gemini 직접으로 읽는다. `skipped`와 로그에 `daily_paid_limit` |
| 날짜가 바뀐 뒤 | KST 자정 1초 전에 넘친 한도가 자정에 다시 열린다. 어제 기록은 세지 않는다 |
| 재시작 뒤 유지 | 서버가 저장하는 형태 그대로 기록을 넣고 새 한도 장치를 만들면 같은 수에서 이어 간다. 재시작 뒤에도 OpenRouter를 더 부르지 않는다 |
| 그 밖 | 응답 없는 호출은 되돌림, 스키마 위반은 유지, DB 불통이면 2단계로, 설정값 오류는 서버 시작 실패 |

- 새 모듈과 고친 모듈의 커버리지는 100%(줄·분기). 백엔드 전체 1,242개 통과, 1,940개 건너뜀(DB 테스트).
- **PostgreSQL에서는 조회를 실행해 보지 못했다.** 이 PC에 DB가 없다. 조회는 SQLite에서 실행해 결과를 확인했고, PostgreSQL용 문장은 글자로만 확인했다(위 SQL). JSON 연산자와 `CAST`는 표준적인 형태지만, 실제 DB에서 한 번 돌려 봐야 한다.
- 조회가 실패하면 서버는 멈추지 않고 사진을 2단계부터 읽는다(돈은 쓰지 않는다). 로그에 `Could not count today's photos read through OpenRouter`가 남는다.

### B.7 같이 고친 것

- `DEPLOY.md`가 "0단계는 INFO로 로그에 남는다"고만 적혀 있었다. 서비스 로그는 WARNING 이상만 보이므로 **0단계로 읽은 사진은 로그에 나오지 않는다**(`raw_output`에는 있다). 그 사실을 적었다. 1~4단계와 건너뜀은 WARNING이라 보인다.

### B.8 넘길 것

**해울**
- B.5의 스키마 변경(진우가 A2를 재시작 뒤에도 유지하기로 정하면).
- 실제 DB에서 B.3의 조회를 한 번 실행해 오류가 없는지 확인.
- `extraction_runs`에 `completed_at` 인덱스가 없다. 조회가 재시작 뒤 한 번, 하루 한 번이라 지금 규모에서는 필요 없다고 봤다.

**진우**
- 300장이 맞는지. 사진 1장당 약 $0.03이면 하루 약 $9다.
- 평가 실행은 이 한도에 잡히지 않는다. 같은 크레딧을 쓰므로 실험은 따로 챙겨야 한다.

### B.9 파일

| 경로 | 내용 |
|---|---|
| `backend/app/services/paid_photo_budget.py` | 추출 기록에서 세는 조회, 하루 한도 장치 |
| `backend/app/extraction/routed.py` | 한도를 넘으면 2단계부터 시작, 설정 `OPENROUTER_DAILY_PHOTO_LIMIT` |
| `backend/app/adapters/openrouter_extraction.py`, `app/api/deps.py` | 추출기에 한도 장치 연결 |
| `backend/tests/test_paid_photo_budget.py` | 테스트 |
| `backend/DEPLOY.md`, `README.md`, `.env.example`, `deploy/env.production.example` | 설정과 확인 방법 |

## C. 남은 크레딧 조회

`GET https://openrouter.ai/api/v1/key` (헤더 `Authorization: Bearer <키>`)로 조회된다. 문서: `https://openrouter.ai/docs/api-reference/limits`. 2026-11-26 조회 결과(키 값과 라벨은 출력하지 않았다):

| 항목 | 값 | 뜻 |
|---|---|---|
| `limit` | 100 | 키에 걸린 크레딧 한도 (USD). **과목이 건 한도다** |
| `limit_remaining` | 92.36 | 남은 크레딧 |
| `limit_reset` | null | 한도는 다시 채워지지 않는다 |
| `usage` | 7.64 | 지금까지 쓴 금액 |
| `usage_daily` / `usage_weekly` / `usage_monthly` | 0.12 / 3.00 / 7.37 | UTC 기준 오늘 / 이번 주 / 이번 달 (조회 시점) |
| `expires_at` | 2026-12-20T14:59:59Z | **키 만료 시각** (한국 시간 12/20 23:59) |
| `is_free_tier` | false | |
| `is_management_key` | false | 관리용 키가 아니다 |
| `rate_limit` | requests -1, interval 10s | 문서가 "더 쓰지 않는 필드, 무시해도 된다"고 적었다 |

- **A에서 "키 한도를 걸 수 없다"고 적은 것은 "우리가 걸 수 없다"는 뜻이다.** 키에는 과목이 건 총 $100 한도가 있고, 다 쓰면 402가 온다(서버는 2단계로 내려간다).
- **속도 제한:** 문서는 유료 모델에 플랫폼 차원의 요청 수 상한이 없다고 적었다. 모델별 제한은 있을 수 있다고만 적혀 있고 숫자는 없다. 동시 호출 제한은 문서에 없다.
- `GET /api/v1/credits`(계정 전체 크레딧)는 403이다. 관리용 키만 부를 수 있다.
- **남은 $92.36으로 얼마나 가는가:** 서버 전체 한도 300장을 매일 다 쓰면 하루 약 $9, 약 10일이다. 키 만료일(12/20)까지는 알파(11/30)부터 20일이다. 실험도 같은 크레딧을 쓴다. 300장을 그대로 둘지는 이 숫자를 보고 정하면 된다.
- `DEPLOY.md`에 확인 명령을 적었다. 서버 코드에는 넣지 않았다.

## D. 실제 API로 경로 확인 (사진 `010_sui_05`, 17칸)

| 확인 | 결과 | 경로 기록 | 17칸 채점 | 토큰 (입력 / 출력 / 추론) | 지연 | 청구액 |
|---|---|---|---|---|---|---|
| 1단계 Sonnet (기본 모델로 지정) | 성공, 스키마에 맞음 | `openrouter`, `anthropic/claude-sonnet-5.5`, 제공자 Google | 17/0/0/0 | 12,672 / 1,651 / 0 | 11.4초 | $0.0419 |
| `models` 배열로 넘어가는 동작 | **확인 불가** | – | – | – | – | – |
| 2단계 Gemini 3.8 Flash 직접 | **3회 모두 503** | – | – | – | – | 무료 키 |
| 3단계 flash-lite + v2.1 | 성공, 스키마에 맞음 | `gemini-direct-lite`, `gemini-3.5-flash-lite` | 16/0/1/0 | 6,346 / 2,126 / 0 | 15.2초 | 무료 키 |

**1단계 Sonnet.** 서버 추출 함수(`extract_menu_routed`)에 기본 모델을 Sonnet으로 지정해 1회. 스키마에 맞는 답이 왔고 17칸 모두 맞다. 채점한 행이 11/25의 3.8 Flash와 같다. 제공자는 Google(Vertex)이었다. 상한 $0.5를 보장하려고 이 호출만 출력 상한을 16,000으로 뒀다(답은 1,651 토큰).

**`models` 배열.** OpenRouter 문서에 대체 모델로 강제로 넘기는 방법이 없다. 문서는 "첫 모델이 오류를 내면 다음 모델을 시도한다"만 적었고, 없는 모델 ID를 첫 모델로 주거나 `provider` 조건으로 첫 모델의 제공자를 없앴을 때 넘어가는지는 적지 않았다. 지시대로 호출하지 않았다. 그래서 **대체 모델에도 `data_collection: "deny"` 조건이 적용되는지, 넘어갔을 때 응답의 `model` 값이 무엇인지는 여전히 모른다.**

**2단계 Gemini 3.8 Flash 직접.**
- 모델 ID는 맞다. Gemini 모델 목록 API에 `gemini-3.8-flash`와 `gemini-3.5-flash-lite`가 모두 있고 `generateContent`를 지원한다.
- 호출은 3회 모두 실패했다(약 한 시간에 걸쳐). 오류는 매번 같다: `503 service_unavailable`, "gemini-3.8-flash is currently experiencing high demand, spikes in demand are usually temporary. Please try again later."
- 429(한도 초과)가 아니라 503(수요 과다)이다. 무료 한도 응답 헤더나 문구는 보지 못했다. SDK가 오류의 응답 헤더를 넘겨주지 않는다.
- 서버 설정으로는 이 단계가 2회 시도한 뒤 3단계로 넘어간다. 오늘 같은 상태면 사진마다 약 5초를 더 쓰고 flash-lite가 읽는다.

**3단계 flash-lite + 프롬프트 v2.1.** 평가한 적 없던 조합이다. 스키마에 맞는 답이 왔다. 17칸 중 16칸 맞음, 틀린 가격 0, 누락 1칸이다. 누락은 `헤네시 VSOP`(병 240,000)를 위스키가 아닌 줄(`other`)로 분류한 것이다. 사진 1장 1회라서 이 조합의 품질을 말해 주지는 않는다. flash-lite가 어려운 사진에서 가격을 미는 것은 11/21에 확인했다(8절).

**호출 수.** OpenRouter 1회($0.042, 상한 $0.5). Gemini 직접 호출 7회: 모델 목록 조회 1회(생성 호출 아님), 3.8 Flash 생성 3회(모두 503), flash-lite 생성 1회, 그리고 **의도하지 않은 요청 2회**. 처음 두 번의 2단계 확인에서 2단계가 503으로 끝나자 닫아 둔 3단계가 없는 모델 ID(`closed`)로 요청을 한 번씩 보냈고 API가 404로 거절했다. 스크립트를 고쳐 세 번째부터는 나가지 않는다.

## E. Sonnet 5.5를 회귀 17장으로

`ai/runs/2026-11-21_i5_row_pairing/report.md` 12절에 적었다. 요점:

| | 맞음 | 틀린 가격 | 누락 | 미라보_02 제목 빠짐 | 사진 1장당 | 지연 중앙값 |
|---|---|---|---|---|---|---|
| 3.8 Flash (서버 코드, 11/25) | 572 | 0 | 0 | 0줄 | $0.0281 | 35.1초 |
| Sonnet 5.5 (11/26) | 557 | 6 | 6 | 4줄 | $0.0578 | 18.9초 |

- 복춘_03의 병 가격 6칸이 모두 1/10이다. 미라보_07의 한 줄은 잔 42,000을 병 420,000으로 썼다.
- 추론 토큰은 17회 중 16회가 0이다.
- 쓴 비용 $0.983 (상한 $2). 1회다.

## F. 옆 페이지 줄 가드 (제안, 구현하지 않았다)

### F.1 서버가 지금 "가격 없는 위스키 행"을 다루는 방식 (코드로 확인)

- **추출:** 가격·용량·잔병 표시가 모두 없는 행은 옵션이 0개인 제품 줄이 된다(`app/extraction/convert.py`의 `_flow_item`).
- **저장과 매칭:** 다른 위스키 줄과 같이 `extracted_items`에 저장되고 제품 매칭도 돈다. 걸러 내는 곳이 없다.
- **검수 화면:** 옵션 없는 줄로 그대로 보인다. OCR 상자가 있으면 사진의 그 위치를 잘라 보여 준다.
- **게시:** 자동으로 게시되지는 않는다. 검수 반영 요청은 게시할 줄마다 옵션이 1개 이상이고 가격이 1원 이상이어야 한다(`app/schemas/menu_review.py`의 `options` 최소 1개, `priceKrw >= 1`). 업주가 가격을 직접 넣어야 게시된다.
- **그래서 옆 페이지 12행이 나오면:** 업주가 검수 화면에서 메뉴에 없는 줄 12개를 하나씩 빼야 한다. 잘못 게시될 위험보다 검수 부담이 문제다.

### F.2 규칙을 기존 기록에 대 본 결과 (API 0회)

규칙: 위스키 행의 가격이 없고, 그 행 이름 줄의 OCR 상자가 사진 가장자리에 닿으면 버린다. 프롬프트 v2.1로 만든 기록 114개, 위스키 행 5,024개에 대 봤다.

| 기록 묶음 | 기록 | 위스키 행 | 가격 없는 행 | 그중 옆 페이지 줄 | 정답에 있는 줄 |
|---|---|---|---|---|---|
| 3.8 Flash, 평가 스크립트 (11/21) | 20 | 732 | 12 | 12 | 0 |
| 3.8 Flash, 서버 코드 (11/25) | 17 | 572 | 0 | 0 | 0 |
| 3.8 Flash, 동시 호출 (11/26) | 6 | 135 | 0 | 0 | 0 |
| Sonnet 5.5, 회귀 17장 (11/26) | 17 | 568 | 0 | 0 | 0 |
| 3.7 Flash, 6장 (11/25) | 18 | 1,002 | 18 | 12 | 6 |
| GPT-6.1 Terra, 6장 (11/25) | 18 | 1,026 | 36 | 36 | 0 |
| Sonnet 5.5, 6장 (11/25) | 18 | 989 | 1 | 0 | 1 |

| 가장자리 여유 (0~1000 눈금) | 옆 페이지 줄 중 버려짐 | 정답에 있는 줄 중 버려짐 |
|---|---|---|
| 0 (정확히 닿음) | 35 / 60 | 3 / 7 |
| 5 | **60 / 60** | 6 / 7 |
| 10, 20, 30 | 60 / 60 | 6 / 7 |

- **옆 페이지 줄 60행(12행 × 5회)을 여유 5 이상에서 모두 잡는다.** 60행의 상자는 모두 사진 오른쪽 끝에 있다(왼쪽 x가 905 이상, 오른쪽 x가 998 또는 1000).
- **회귀 17장에서는 다른 행을 하나도 버리지 않는다.** 채택한 모델(3.8 Flash)과 Sonnet의 회귀 17장 기록에는 옆 페이지 줄 말고 가격 없는 위스키 행이 없다.
- **잘못 버리는 경우가 회귀 17장 밖에 있다.** 3.7 Flash가 tale_07(I3 사진, 비스듬한 사진)에서 가격을 비운 2줄(`Ardbeg Corrybreckan`, `Ardbeg Anthology`)이 3회 모두 왼쪽 끝에 닿아 버려진다(6행). 이 줄은 실제 메뉴에 있는 줄이다. 규칙이 없으면 가격 없는 줄로 검수 화면에 남아 업주가 가격을 넣을 수 있다.
- 가장자리에 닿지 않아 남는 가격 없는 행은 1개다(Sonnet 6장의 복춘_01 `아란 10Y`).

### F.3 판단에 필요한 것

- 규칙은 이 기록에서 옆 페이지 줄을 다 잡지만, 옆 페이지 줄이 나온 사진은 미라보_03 한 장뿐이다. 다른 메뉴판의 옆 페이지가 어디에 걸리는지는 모른다.
- 비스듬하게 찍어 메뉴 줄이 가장자리에 닿는 사진에서는, 모델이 가격을 못 읽은 진짜 줄을 같이 버린다. "오른쪽·왼쪽 끝에 좁게 걸린 상자"처럼 좁히면 줄일 수 있겠지만 대 볼 사례가 tale_07 하나다.
- 버리지 않고 검수 화면에서 "가장자리에 걸린 줄"로 표시만 하는 방법도 있다. 검수 부담은 남지만 진짜 줄을 잃지 않는다.
- 결과를 보고 프롬프트를 고치지 않았다. 계산 스크립트: `ai/eval/i5_edge_guard_check.py`, 결과: `edge_guard.json`.

## G. PDF 경로를 새 추출 경로와 한도에 맞추기

업로드 API, 스펙, 화면은 건드리지 않았다.

### G.1 한눈에

- `MENU_EXTRACTOR=openrouter`일 때 PDF 페이지가 사진과 같은 경로(3.8 Flash → 대체 모델 → Gemini 직접 → flash-lite)를 타는 추출기를 추가했다: `RoutedPdfMenuExtractor`. `MENU_EXTRACTOR=gemini`(hybrid)는 기존 `PdfMenuExtractor` 그대로다.
- 페이지별 기록은 사진과 같은 형식이다(`route`, 토큰, `costUsd`, `latencyMs`). 거기에 기존 PDF 기록처럼 `pdf`(`page`, `kind`, `textLayer`)가 붙는다.
- 차단기와 서버 전체 하루 한도는 사진 추출기의 것을 그대로 같이 쓴다. PDF 페이지도 사진과 같이 세어진다.
- I4-P37의 PDF 가드는 새 경로에서도 동작한다. 다만 **가드의 숫자 두 가지가 새 경로와 맞지 않는다**(G.3).
- UAT PDF 3개(5쪽)를 새 경로로 실제로 돌렸다. 5쪽 모두 0단계로 읽혔고 기대 줄 24개를 모두 찾았다. $0.050.

### G.2 PDF 페이지의 글자는 어디서 오는가 (코드로 확인)

| 페이지 종류 | 글자 출처 | CLOVA 호출 |
|---|---|---|
| `text`: PDF에 글자 층이 있고 믿을 수 있음 | PDF의 글자 층 (`app/extraction/pdf.py`가 단어와 위치를 읽어 CLOVA 응답 모양으로 바꾼다) | **없음** |
| `scanned`: 그림뿐이거나 글자 층을 못 믿음 | CLOVA OCR | **페이지마다 1회** |

- 글자 층을 안 쓰는 경우(`text_layer` 값): 글자가 10자 미만(`none`), 유니코드 값 없는 글자가 5% 초과(`unreadable`), 회전된 페이지(`rotated`), 보이는 영역이 원점에서 시작하지 않음(`offset`), 그림이 절반 이상을 덮고 글자 줄이 5줄 미만(`partial`).
- **스캔한 PDF는 15쪽이면 CLOVA 15회다.** 무료가 월 100회라면 스캔 PDF 7개쯤에 닿는다. 사진도 장마다 1회씩 쓴다. CLOVA 호출 수를 막는 장치는 서버에 없다.
- CLOVA가 실패하면 그 페이지는 사진처럼 Gemini 단독 추출(flash-lite, 프롬프트 v1)로 간다.

### G.3 PDF 가드와 새 경로의 시간

가드의 뜻(PDF 하나가 서버를 오래 붙잡지 않게)은 그대로 유지된다. 새 경로에서 페이지 하나의 제한은 이렇게 걸린다.

| 가드 값 (기본) | 기존 경로 | 새 경로 |
|---|---|---|
| 시도 하나의 시간 (`attempt_timeout_s` 120초) | Gemini 호출 1회를 120초에 끊음 | OpenRouter, Gemini 직접, flash-lite 호출 모두 120초에 끊음. 사진의 330초가 아니다 |
| 페이지의 시도 수 (`page_attempts` 3) | Gemini 3회 | OpenRouter 3회. Gemini 직접과 flash-lite는 각 1회 |
| PDF 전체의 재시도 (`document_retries` 6) | 그대로 | 그대로. 경로를 내려가며 쓴 호출도 센다 |
| 실패한 페이지 수 (`failed_pages` 3), PDF 시간 상한 (`page_budget_s` 90초/쪽) | 그대로 | 그대로 |
| 스캔 페이지의 CLOVA 시간 (`ocr_deadline_s` 60초) | 그대로 | 그대로 |

**맞지 않는 것 두 가지 (값을 바꾸지 않았다. 가드는 I4-P37의 값이라 보고만 한다)**

| 무엇 | 지금 | 새 경로에서의 문제 | 제안 |
|---|---|---|---|
| 페이지 하나의 최악 시간 (`page_seconds`) | 60 + 3 × 120 + 15 = 435초 | 경로가 늘어 호출이 최대 6회다: OpenRouter 3회, 잘린 답 다시 받기 1회, Gemini 직접 1회, flash-lite 1회. 60 + 6 × 120 + 15 = **795초** | `page_seconds` 계산에 3회분(360초)을 더하거나, 새 경로에서는 `page_attempts`를 2로 낮춘다 |
| 시도 하나의 시간 120초 | I4의 flash-lite 측정(p95 58~83초)에서 정한 값 | 3.8 Flash는 한 번에 181초까지 걸린 적이 있다(9.6절, 미라보_02). 120초에 끊으면 정상 호출을 버리고 다시 부르고, 끊긴 호출도 청구될 수 있다. 측정한 p95는 71초라 대부분은 안 걸린다 | 새 경로에서는 200초 |

- "PDF 하나의 모델 호출은 최대 `페이지 수 + document_retries`회"라는 가드의 설명도 새 경로에서는 맞지 않는다. 페이지마다 경로를 내려가는 호출(최대 3회)이 더 붙을 수 있다.
- 가드는 지금도 PDF 전체 시간 상한 뒤에는 새 페이지를 시작하지 않는다. 그래서 바꾸지 않아도 PDF 하나가 무한히 붙잡지는 않는다. 다만 마지막 페이지가 795초까지 갈 수 있다.
- 실패 분류: 모든 경로가 실패한 페이지는 `model_call_failed`, 스키마가 아닌 답은 `invalid_output`으로 나온다.

### G.4 한도

**A2 (계정당 하루 30장).** `acquire_menu_photos(limiter, subject, photos, now)`의 `photos`에 페이지 수를 넘기면 된다. 준비돼 있고 테스트했다.

**B (서버 전체 하루 300장).** 페이지도 사진과 같이 센다.
- 처리 중: PDF 추출기가 사진 추출기의 한도 장치를 그대로 쓴다(복사본이 아니다). 테스트했다.
- 재시작 뒤: 추출 기록에서 다시 센다. **페이지마다 `extraction_runs` 행 하나를 만들고 `raw_output`을 그대로 저장해야** 세어진다. 업로드 쪽이 그렇게 붙여야 한다(G.6).

**PDF 한 개가 남은 한도보다 페이지가 많을 때.** 사진과 같이 **전부 거절하고 남은 수를 알려 준다**(`429 RATE_LIMITED`, `details.remaining`). `acquire_menu_photos`가 이미 그렇게 동작하므로 따로 구현할 것이 없다. 예: 남은 수 5, 8쪽 PDF → 전부 거절, `remaining = 5`. PDF는 사진과 달리 "5쪽만 다시 올리기"가 어렵다. 문구는 "오늘은 5쪽까지 올릴 수 있어요. 쪽수가 적은 파일로 올리거나 내일 다시 올려 주세요" 같은 것이 필요하다(호진에게 넘길 것).

### G.5 실제 확인: UAT PDF 3개

`backend/scripts/run_uat_inputs.py --extractor openrouter --pdf-page-attempts 1`. 3.8 Flash, 프롬프트 v2.1, 대체 모델 없음, 출력 상한 16,000(상한 $1을 보장하려고. 답은 768~3,383 토큰).

| 입력 | 쪽 | 종류 | 경로 | 항목 | 기대 줄 | 모델 시간 | CLOVA | 청구액 |
|---|---|---|---|---|---|---|---|---|
| `pdf-text-design` | 1 | 글자 층 | 0단계 3.8 Flash | 8 | 10 / 10 | 25.7초 | 0회 | $0.0174 |
| `pdf-text-office` | 2 | 글자 층 | 0단계 × 2 | 9 | 7 / 7 | 8.1초, 8.4초 | 0회 | $0.0162 |
| `pdf-scanned` | 2 | 스캔 | 0단계 × 2 | 9 | 7 / 7 | 10.9초, 6.7초 | 2회 (1.4초, 2.1초) | $0.0163 |
| 합 | 5 | | | 26 | **24 / 24** | | 2회 | **$0.0500** |

**I4 기록과의 비교.** 지시 문서가 말한 `ai/runs/`의 P30 UAT 결과는 레포와 작업 폴더에서 찾지 못했다(`ai/docs/p30_run_commands.md`와 스크립트만 있다). 대신 글자 PDF 2개를 예전 경로(Gemini 직접, flash-lite, 프롬프트 v1)로 오늘 한 번 돌렸다. 스캔 PDF는 CLOVA 호출을 아끼려고 돌리지 않았다. 이 비교에 flash-lite 호출 3회(무료 키)를 썼다.

| 입력 | 예전 경로 (flash-lite, v1) | 새 경로 (3.8 Flash, v2.1) |
|---|---|---|
| `pdf-text-design` | 6항목, 기대 줄 10 / 10, 3.6초 | 8항목, 기대 줄 10 / 10, 25.7초 |
| `pdf-text-office` | 7항목, 기대 줄 7 / 7, 4.8초와 37.2초 | 9항목, 기대 줄 7 / 7, 8.1초와 8.4초 |

- 기대 줄은 두 경로 모두 다 찾았다. 새 경로의 항목이 2개씩 많은 것은 프롬프트 v2.1이 위스키가 아닌 줄(칵테일, 음식)도 내기 때문이다.
- 만들어 낸 작은 메뉴(쪽당 4~8줄)라서 정확도 차이를 보여 주는 입력이 아니다. 새 경로가 PDF에서 끝까지 동작하는지를 본 것이다.
- 페이지마다 1회 시도였고 5쪽 모두 첫 시도에 답이 왔다. 2~4단계는 PDF에서 실제 API로 보지 않았다(가짜 응답 테스트만).

### G.6 넘길 것

**해울 (PDF 업로드를 붙일 때)**

| 할 일 | 부를 것 |
|---|---|
| PDF 추출기 얻기 | `pdf_extractor_for(get_menu_extractor())` (`app/adapters/pdf_routed_extraction.py`). `openrouter`면 새 경로, `gemini` + `hybrid`면 기존 추출기를 준다. mock이나 hybrid가 아닌 gemini면 `ExtractionConfigError` |
| 페이지 읽기 | `extractor.pages(data)` → `PdfPage` 목록. `PdfError`의 `code`로 거절 이유 구분 (기존과 같다) |
| 계정당 한도 | 접수할 때 `acquire_menu_photos(limiter, principal.subject, len(pages), now)`. 넘으면 `429`가 그대로 올라온다. 저장에 실패하면 `limiter.release_units(subject, MENU_IMPORT_PHOTOS, day, len(pages))`. 사진 업로드(`create_menu_import`)가 하는 것과 같다 |
| 페이지 추출 | `extract_pdf_pages(extractor, pages)` (가드 포함) |
| 기록 | **페이지마다 `extraction_runs` 행 하나, `raw_output`은 `page.raw_output` 그대로.** 서버 전체 하루 한도가 재시작 뒤 이 행의 `raw_output.route.stage`를 센다 |
| 페이지 수를 미리 세기 | `check_pdf(data)`가 페이지 수만 센다(그림을 그리지 않는다). 한도 검사를 페이지를 읽기 전에 할 수 있다 |

- G.3의 가드 값 두 가지를 바꿀지 정해야 한다(가드는 I4-P37).
- CLOVA 호출 수: 스캔 PDF는 페이지마다 1회다. 월 무료 100회를 넘기지 않으려면 따로 세는 장치가 필요하다. 지금은 없다.
- 스펙: PDF에서 `429`의 `details.requested`는 페이지 수다. 4.5의 "PDF를 받게 되면 페이지 수로 센다" 한 줄이 이미 있다.

**호진**
- PDF가 남은 한도보다 쪽수가 많을 때의 문구(G.4).

### G.7 파일

| 경로 | 내용 |
|---|---|
| `backend/app/adapters/pdf_routed_extraction.py` | `RoutedPdfMenuExtractor`, `pdf_extractor_for` |
| `backend/app/adapters/openrouter_extraction.py` | `extract_with`: OCR 단계를 바꿔 끼울 수 있게 (글자 층) |
| `backend/app/adapters/pdf_guards.py` | 새 추출기에 페이지 제한을 거는 연결, 경로를 내려간 호출까지 세기, OpenRouter 시간 초과 분류 |
| `backend/scripts/run_uat_inputs.py` | `--extractor openrouter`, `--pdf-page-attempts`, 페이지 기록에 경로·토큰·청구액 |
| `backend/tests/test_pdf_routed_extraction.py` | 테스트 26개 (가짜 응답): 0~4단계, 가드, 페이지 수 세기, 두 한도 |
| `ai/runs/2026-11-26_i5_p19_followup/uat_pdf/openrouter/`, `hybrid_flash_lite/` | 실제 실행 기록 |

**테스트 환경.** PDF 테스트는 `pypdfium2`가 필요한데 이 PC의 venv에 없었다. 프로젝트가 고정한 버전(5.13.0)을 임시 폴더에 설치해 돌렸다(venv는 건드리지 않았다). PDF 관련 기존 테스트 121개가 통과했고, `test_pdf_extraction.py`의 5개는 Windows의 환경변수 길이 제한 때문에 실행되지 않았다(테스트 이름에 PDF 바이트가 들어가서 생기는 문제로, 이번 변경과 무관하다).

## 파일 (C~F)

| 경로 | 내용 |
|---|---|
| `ai/eval/i5_route_stage_check.py`, `stage_check/` | D: 단계별 실제 호출과 기록 (`sonnet.json`, `lite.json`, `direct_attempt{1,2,3}_503.json`, `gemini_models.json`) |
| `ai/eval/i5_sonnet_regression_report.py`, `regression_sonnet/` | E: 기록 17개, `summary.json`, `run.log` |
| `ai/eval/i5_edge_guard_check.py`, `edge_guard.json` | F: 가장자리 규칙 계산 |

## AI 사용 내역 (C~G)

Claude Code가 한 일: OpenRouter 문서 확인(키 조회, 대체 모델), 키 정보 조회, 단계별 실제 호출, Sonnet 회귀 실행과 채점, 가장자리 규칙 계산, PDF 추출기 구현과 테스트, UAT PDF 실행, 이 보고서. 검증: 새 테스트 26개와 기존 PDF 테스트, 채점 스크립트는 11/21·11/25 기록으로 같은 숫자가 나오는지 확인. 사람이 정해야 하는 것: Sonnet을 대체 모델에 둘지, 하루 300장, PDF 가드 값, 가장자리 규칙을 쓸지.
