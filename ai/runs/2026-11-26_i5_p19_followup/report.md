# I5-P19 후속: 키 제약, 서버 전체 한도, 실제 경로 확인 (2026-11-26)

지시 문서: `../_outgoing/i5_p19_followup_handoff.md`. 브랜치 `feature/i5-p19-openrouter-extraction`. push하지 않았다. 단계가 끝날 때마다 이 문서에 절을 더한다.

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
