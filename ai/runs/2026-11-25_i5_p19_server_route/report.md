# I5-P19: 서버 추출 경로를 OpenRouter로 (2026-11-25)

지시 문서: `../_outgoing/i5_p19_a2_fallback_handoff.md` 2단계. 브랜치 `feature/i5-p19-openrouter-extraction`, 구현 커밋 `10b5156e`. push하지 않았다.

## 0. 진우가 확인할 기본값

지시 문서의 "아직 안 정해진 것"을 아래 기본값으로 구현했다. 바꾸려면 설정값만 바꾸면 되는 것과 코드를 바꿔야 하는 것을 나눠 적는다.

| 항목 | 구현한 기본값 | 바꾸는 방법 |
|---|---|---|
| OpenRouter 402(크레딧 소진·키 한도 도달) | 2단계(Gemini 직접 호출)로 보낸다. 재시도하지 않는다 | 코드 (`routed.py`) |
| 차단기 | OpenRouter 호출이 연속 3회 실패하면 10분 동안 건너뛴다. 402도 실패로 센다 | 설정 `OPENROUTER_BREAKER_FAILURES`, `OPENROUTER_BREAKER_COOLDOWN_S` |
| P18의 평가셋 규칙 | I3 동결 해제 (11/25 진우 확인) | – |
| 대체 모델 배열 | `anthropic/claude-sonnet-5.5` 하나 (11/25 진우 결정) | 설정 `OPENROUTER_FALLBACK_MODELS` |
| A2 하루 한도 | 3단계에서 구현한다 (계정당 30장) | – |

지시 문서에 없어서 내가 정한 것도 있다. 3절에 적었다.

## 1. 한눈에

- **새 서버 코드 경로로 회귀 17장을 1회 돌린 결과는 11/21 기록과 같다.** 572칸 중 맞음 572, 틀린 가격 0, 누락 0, 이름만 실패 0.
- 17장 모두 0단계(`google/gemini-3.8-flash`, 제공자 Google)로 읽혔다. 잘린 시도 0건.
- 쓴 비용 $0.478 (상한 $1). 사진 1장당 $0.0281.
- 가짜 응답 테스트 70개로 경로 0 → 1 → 2 → 3 → 4, 차단기, 402, 잘림 재시도, 스키마 위반, 기존 설정 유지를 확인했다. 새 모듈 3개의 커버리지는 100%다.
- DB 스키마는 바꾸지 않았다.

## 2. 전후 비교 (회귀 17장, 정답 572칸)

| | 지금 서버에 가까운 것: flash-lite 직접, 프롬프트 v2 (11/21, 1회) | 3.8 Flash + v2.1, 평가 스크립트 (11/21, 1회) | 3.8 Flash + v2.1, **새 서버 코드** (오늘, 1회) |
|---|---|---|---|
| 맞음 | 552 | 572 | **572** |
| 틀린 가격 | 6 (모두 이웃 행) | 0 | **0** |
| 누락 | 13 | 0 | **0** |
| 이름만 실패 | 1 | 0 | **0** |
| 남는 행 | 12 | 12 (미라보_03의 옆 페이지 12행) | **0** |
| 지연 중앙값 / p95 / 최대 | 11.5초 / 23.7초 / 28.2초 | 26.2초 / 42.5초 / 79.7초 | **35.1초 / 55.9초 / 75.7초** |
| 사진 1장당 비용 | $0.0164 (공시 단가로 계산한 값. 실제로는 무료 키) | $0.0273 | **$0.0281** |
| 17장 합 | $0.279 (계산값) | $0.464 | **$0.478** |

- **정확도:** flash-lite가 틀리거나 놓친 20칸(복춘_01 14칸, 오드비_09 4칸, 미라보_07 1칸, 수이_02 1칸)이 새 경로에서는 모두 맞다.
- **지연:** 중앙값이 flash-lite의 약 3배다. I3 동결 기준(p95 60초 이하)은 이 17장에서 넘지 않았다(55.9초). 11/21의 3회 측정에서는 p95가 71초였다(9.6절).
- **비용:** flash-lite 계산값의 약 1.7배다.
- 채점한 행(이름·가격·용량·unit)이 11/21 평가 스크립트 기록과 완전히 같은 사진은 17장 중 16장이다. 다른 한 장은 미라보_03으로, 오늘은 옆 페이지 12행이 나오지 않았다(60행). 점수는 두 날 모두 60칸 전부 맞음이다.
- **비교의 한계:** "지금 서버" 열은 프롬프트 v2 기록이다. 지시 문서는 서버가 프롬프트 v1이라고 적었는데, 이 17장의 flash-lite + v1 기록 중 같은 함수로 채점할 수 있는 것은 없어서 v2 기록을 썼다. 세 열 모두 1회다.

사진별 결과는 `summary.json`과 `run.log`의 표에 있다.

**실행 중에 있었던 일.** 미라보_05에서 첫 시도가 약 4분 뒤 연결 끊김(`ReadError`, 원격 호스트가 연결을 끊음)으로 끝났고, 5초 뒤 재시도가 36초 만에 답을 받았다. 새 코드의 재시도가 실제로 동작한 한 건이다. 그 사진은 접수부터 답까지 283초가 걸렸다. 표의 지연은 답이 나온 시도의 시간이다. 끊긴 시도가 청구됐는지는 응답이 없어서 알 수 없다.

**이 실행이 배포 설정과 다른 점.** 대체 모델 없이 3.8 Flash만 불렀고, Gemini 직접 경로(2·3단계)는 닫았다. 질문이 "새 코드로 3.8 Flash를 부르면 11/21과 같은가"이고, Sonnet이 켜져 있으면 한 번 호출의 최대액이 $1.08이라 상한 $1을 보장할 수 없어서다. 1~4단계로 넘어가는 동작은 실제 API로 확인하지 않았다.

## 3. 구현

| 파일 | 내용 |
|---|---|
| `backend/app/extraction/openrouter.py` | OpenRouter 호출. 요청 형식은 `i5_model_ladder.py`와 같다. 설정 읽기, 재시도, 벽시계 상한, 402 분류 |
| `backend/app/extraction/routed.py` | 경로 전환을 한 곳에서 관리. 차단기, 잘림 재시도, 경로 기록과 로그 |
| `backend/app/adapters/openrouter_extraction.py` | `MenuExtractor` 구현. 등록 처리 코드는 바꾸지 않았다 |
| `backend/app/api/deps.py` | `MENU_EXTRACTOR=openrouter` 분기 추가 |
| `backend/tests/test_openrouter_extraction.py`, `test_deploy_files.py` | 테스트 (외부 API 0회) |
| `backend/deploy/env.production.example`, `.env.example`, `README.md`, `DEPLOY.md` | 새 설정, 키 등록, 경로 순서, 로그로 경로 확인하는 법 |
| `ai/eval/i5_server_route_regression.py` | 이 보고서의 회귀 실행·채점 |

**경로**

| 단계 | 경로 | 넘어가는 조건 |
|---|---|---|
| 0 | OpenRouter `google/gemini-3.8-flash` | 항상 먼저 |
| 1 | OpenRouter `anthropic/claude-sonnet-5.5` (`models` 배열, 같은 요청) | 0의 제공자가 전부 실패 (OpenRouter가 스스로 넘긴다) |
| 2 | Gemini API `EXTRACTION_DIRECT_MODEL` | OpenRouter 호출이 재시도 끝에 실패, 402, 또는 차단기가 열림 |
| 3 | Gemini API `EXTRACTION_MODEL` (flash-lite) | 2가 실패 |
| 4 | 추출 실패로 표시 | 전부 실패 |

**재시도와 시간 상한.** `gemini.py`와 같다: 408·429·5xx·연결 오류·시간 초과를 5·10·20·40·60초 간격으로 재시도(최대 6회 시도), 시도마다 벽시계 상한 **330초**(요청 시간 초과 300초). 실측 최대 181초보다 길다. 기존 설정 `EXTRACTION_MAX_ATTEMPTS`, `EXTRACTION_REQUEST_TIMEOUT_S`, `EXTRACTION_WALL_TIMEOUT_S`를 같이 쓴다.

**어느 경로가 읽었는지.**
- 추출 기록 `extraction_runs.raw_output`: `route`(`stage`, `path`, `model`, `provider`, 건너뛴 단계와 이유), `inputTokens`, `outputTokens`, `thoughtTokens`, `costUsd`, `latencyMs`, `attempts`, `truncatedAttempts`.
- 로그: 사진마다 `extraction route stage=N path=… model=… provider=… input_tokens=… output_tokens=… thought_tokens=… cost_usd=… latency_ms=…` 한 줄. 0단계는 INFO, 나머지는 WARNING. flash-lite로 읽은 사진은 `grep "extraction route stage=3"`로 찾는다.

**지시 문서에 없어서 내가 정한 것**

| 정한 것 | 이유 |
|---|---|
| 답이 왔는데 스키마가 아니거나 두 번 잘리면 **다음 경로로 보내지 않고 그 사진을 실패로 표시한다** | 경로는 동작한 것이다. 기존 추출기도 이 경우 실패로 끝낸다. 차단기에도 세지 않는다 |
| 2단계(Gemini 3.8 Flash 직접)는 2회만 시도하고 3단계로 넘긴다 (`EXTRACTION_DIRECT_MAX_ATTEMPTS`) | 무료 한도 429는 1~2분 기다려도 풀리지 않는다. 6회 다 기다리면 사진마다 2분 넘게 멈춘다 |
| 2단계가 429가 아닌 이유로 실패해도 3단계로 넘긴다 | "전부 실패해야 4단계"에 맞췄다 |
| 프롬프트 설정을 새 변수 `OPENROUTER_EXTRACTION_PROMPT`(`v2`, `v2.1`, 기본 `v2.1`)로 따로 뒀다 | 기존 `EXTRACTION_HYBRID_PROMPT`에 `v2.1`을 넣으면 `MENU_EXTRACTOR=gemini`로 되돌릴 때 서버가 시작하지 않는다 |
| Gemini 직접 호출의 모델 ID를 필수 설정 `EXTRACTION_DIRECT_MODEL`로 뒀다 (예시 값 `gemini-3.8-flash`) | 직접 호출용 모델 ID는 이번에 실제로 불러 보지 않았다. **진우가 ID를 확인해야 한다** |
| CLOVA OCR이 실패하면 기존 hybrid 추출기처럼 사진만 보는 Gemini 추출(flash-lite, 프롬프트 v1)로 보낸다 | 기존 동작을 그대로 따랐다 |
| 요청 헤더 `X-Title`은 `bottlemap-menu-extraction` | OpenRouter 대시보드에서 평가용 호출과 구분된다 |

## 4. 테스트

- `backend/tests/test_openrouter_extraction.py` 69개, `test_deploy_files.py`에 1개 추가. OpenRouter는 가짜 HTTP 클라이언트, Gemini는 가짜 SDK 클라이언트, CLOVA는 가짜 호출이다.
- 확인한 것: 0·1·2·3·4단계 각각, 차단기 열림·10분 뒤 한 번 통과·성공 시 닫힘, 402(HTTP 402와 200 본문 안의 402), 잘림 1회 재시도와 두 번 잘림, 스키마 위반, 응답 없는 호출의 벽시계 상한, 키가 오류 문구·로그·repr에 나오지 않는 것.
- **기존 값 유지:** OpenRouter 설정이 있어도(잘못된 값이어도) `MENU_EXTRACTOR=gemini`는 전과 같은 추출기, 같은 모델, 같은 `pipeline_version`을 준다. 기존 추출 테스트는 그대로 통과한다.
- 백엔드 전체: 1,188개 통과, 1,940개 건너뜀(DB 테스트, 이 PC에 `POSTGRES_TEST_DATABASE` 없음). `test_pdf_extraction.py`, `test_pdf_guards.py`, `test_run_uat_inputs.py`는 이 PC의 venv에 `pypdfium2`가 없어 수집되지 않았다. **DB 테스트와 PDF 테스트는 CI에서 확인해야 한다.**
- 커버리지: `openrouter.py`, `routed.py`, `openrouter_extraction.py` 모두 100%(줄·분기). 백엔드 전체 기준 98%는 DB 테스트가 도는 CI에서만 잴 수 있다.

## 5. 확인하지 못한 것

- **1단계(`models` 배열로 Sonnet에 넘어가는 것)를 실제 API로 보지 않았다.** OpenRouter 문서에는 대체 모델에도 `provider` 조건(`data_collection: "deny"`, `require_parameters`)이 적용되는지 적혀 있지 않다. 넘어갔을 때 기록의 `route.provider`로 확인해야 한다.
- **2·3단계를 실제 Gemini API로 부르지 않았다.** flash-lite + 프롬프트 v2.1 조합은 평가한 적이 없다.
- **PDF는 이 경로를 타지 않는다.** `PdfMenuExtractor`는 기존 hybrid 추출기(Gemini 직접)를 쓴다. 업로드 API가 아직 PDF를 받지 않아서 손대지 않았다.
- 응답의 `model` 값으로 0단계와 1단계를 가른다. 오늘 0단계 응답의 `model`은 요청한 ID와 같았다. 대체 모델 응답의 값은 보지 못했다.

## 6. 넘길 것

**해울**
- `extraction_runs.model_name`은 업로드 때 기록돼서 항상 0단계 모델 ID다. 실제로 읽은 모델은 `raw_output.model`과 `raw_output.route`에 있다. 열 단위로 조회하려면 처리 끝에 `model_name`을 고쳐 쓰거나 열을 추가해야 한다. 구현하지 않았다.
- P40 점검 항목: `MENU_EXTRACTOR=gemini`로 되돌리는 끄기 스위치가 OpenRouter 설정이 남아 있어도 동작한다(테스트 있음).
- P41: 한 번의 호출이 최대 330초, 재시도까지 합치면 사진 한 장이 10분 넘게 걸릴 수 있다. 헬스 체크가 긴 추출 호출을 죽이지 않는지 확인이 필요하다.
- 매칭 LLM이 429를 받으면: `app/matching/llm_layer.py`가 모든 예외를 잡아 경고 로그(`matching LLM … call failed`)만 남기고 답 없음으로 처리하고, 등록 처리도 계층 전체 실패 시 규칙 결과를 그대로 둔다. 조용히 규칙 결과로 넘어간다(코드로만 확인).

**진우**
- **(2026-11-26 고침)** OpenRouter 키는 과목에서 발급해 준 하나뿐이다. 키를 더 만들 수 없고 대시보드에서 키 한도를 걸 수도 없다. 실험과 서버가 같은 키, 같은 크레딧을 쓴다.
  - 그래서 지출 상한은 서버가 직접 지킨다. 서버 전체 하루 한도(OpenRouter 경로로 읽은 사진 수, `OPENROUTER_DAILY_PHOTO_LIMIT`)로 대신한다. 구현과 결과는 `ai/runs/2026-11-26_i5_p19_followup/report.md`에 있다.
  - 평가용 호출과 서버 호출은 요청 헤더 `X-Title`로만 구분된다(서버 `bottlemap-menu-extraction`, 평가 스크립트 `menu-extraction-eval`).
  - 계정의 데이터 수집 설정은 볼 수 없다. 요청마다 넣는 `provider.data_collection: "deny"`가 유일한 장치다.
  - 같은 키를 서버 `.env`에 등록한다(배포 워크플로는 키를 보내지 않는다).
- `EXTRACTION_DIRECT_MODEL`에 넣을 Gemini 직접 호출 모델 ID를 확인한다.
- 개인정보 처리방침에 Google 무료 경로(2·3단계)를 적는다.
- 회귀 기준선(`ai/regression/baseline.json`)을 새 모델 출력으로 다시 잡을지 정한다. 바꾸지 않았다.

## 7. 파일

| 경로 | 내용 |
|---|---|
| `ai/runs/2026-11-25_i5_p19_server_route/<stem>.json` | 기록 17개: 서버가 저장할 meta(OCR 줄 표 제외)와 채점한 행 |
| `…/summary.json` | 사진별 점수(세 묶음), 합계, 지연·비용 |
| `…/run.log` | 실행 출력과 사진별 표 |

## 8. AI 사용 내역

Claude Code가 한 일: 서버 코드 파악, 모듈 3개와 테스트 작성, 설정 문서 반영, OpenRouter 문서 확인(대체 모델 배열, 402, 200 응답 안의 오류), 회귀 17장 실행과 채점, 이 보고서. 검증: 가짜 응답 테스트 70개, 11/21 기록을 같은 함수로 다시 채점해 보고서 숫자와 일치 확인, 실제 호출 17장. 사람이 정한 것: 대체 모델(Sonnet 5.5), 2단계 진행 승인.
