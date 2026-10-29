# P30 실행 명령 (I3 test: 추출 r1–r3 → 채점 → 종단 매칭)

2026-10-29 · 박진우 (작성: Claude Code) · 근거: `ai/docs/i3_eval_freeze.md` 3장(P5 추출 동결), 4.2·4.3(종단 입력·실행)

이 문서의 명령을 **위에서 아래 순서 그대로** 한 번씩 돌린다. 결과를 보고 다시 돌리거나 회차를 고르지 않는다(동결 3장). 같은 명령을 다시 돌리는 것은 "이어서 하기"일 때만이다(아래 2절).

## 0. 무엇을 돌리나

- **추출기:** `ai/eval/p30_extract.py`. 배포 서버 코드 `backend/app/extraction/hybrid.py`의 `extract_menu_hybrid`를 **고치지 않고 그대로 불러** 33장 × r1–r3을 돌린다. 모델 `gemini-3.5-flash-lite`, thinking `medium`, 프롬프트 `hybrid-v1`(`hybrid_prompt_v1.md`, SHA-256 `b73f15d2…1ac50`), 재시도는 서버 정책(`call_with_retries`: 6번 시도, 시간 초과·HTTP 429/5xx에 5–60초 간격, 요청 300초·전체 330초). 모델·thinking은 `.env`의 `EXTRACTION_*`를 읽지 않고 동결 값으로 고정한다.
- **API 호출 전에 멈추는 경우:** 추출 코드 파일 9개의 SHA-256이 동결 값과 다를 때(`5d49c8a` 기준, `clova.py`만 `1e149d4`: 사업자등록증용 `deadline_s` 경로만 추가되어 하이브리드 경로는 같음), 사진 33장 중 하나라도 `ai/eval/i3_photo_sha256.json`과 다르거나 빠졌을 때, `photo_map.json`이 해시 파일과 다를 때, OCR 캐시가 다른 사진으로 만든 것일 때. 이때 종료 코드는 2이고 API 호출은 0이다.
- **키:** 레포 루트 `.env`의 `GEMINI_API_KEY`, `CLOVA_OCR_INVOKE_URL`, `CLOVA_OCR_SECRET`만 읽는다. 화면·기록·manifest에 쓰지 않고, 오류 문구에 들어 있으면 `***`로 지운 뒤 저장한다.

### CLOVA는 사진당 한 번 (r1–r3 공유)

동결 1장 "사진 사용 제한"이 "가이드라인 v2.3 검수 전 OCR 대조용 CLOVA OCR 캐시를 만들 수 있고, **P30 하이브리드 추출은 그 캐시를 그대로 쓴다**"고 정했다. 그래서 회차마다 CLOVA를 다시 부르지 않는다.

- 캐시: `<BOTTLEMAP_DATA_DIR>/ocr_cache/<파일 stem>__table-off.json` (`ai/ocr/clova.py` 형식, `label_ocr_check.py`가 읽는 그 파일). 캐시가 이미 있으면 CLOVA 호출은 0이다.
- 캐시가 없는 사진만 서버 코드(`app.extraction.clova.call_ocr`, 표 인식 끔)로 **한 번** 부르고 같은 형식으로 캐시에 쓴다. r2·r3은 그 캐시를 쓴다.
- 캐시 응답은 가짜 HTTP 클라이언트로 서버 함수에 넘긴다. 그래서 OCR 줄 표, 프롬프트, Gemini 요청은 서버 코드가 직접 만든다. 이 클라이언트는 서버가 보낼 이미지가 캐시를 만든 이미지와 같은지 확인한다(`sent_sha256`). 원본 바이트를 보내는 사진에서 다르면 멈춘다. EXIF 회전이나 8,000px 축소로 다시 인코딩되는 사진은 Pillow 버전에 따라 바이트가 달라질 수 있어, 다르면 기록만 하고 진행한다(원본 사진은 해시로 이미 확인함).
- 이유: 동결이 그렇게 정했고, 3회 반복으로 재려는 것은 Gemini 응답의 흔들림이다. OCR까지 매번 다시 부르면 회차 차이에 OCR 차이가 섞인다. I2 P47도 같은 방식이었다(`ai/runs/2026-10-17_p47/manifest.json`, `clova_calls: 0`). 서버는 업로드마다 CLOVA를 부르지만, 사진 한 장에 대한 OCR 결과는 서버에서도 한 번만 쓰인다.
- 지연: 기록의 `clova.latency_ms`는 그 캐시를 만든 실제 호출 한 번의 지연이다(세 회차에 같은 값). `gemini.latency_ms`는 회차마다 성공한 시도의 지연이다(서버 `CallResult.latency_ms`, P47 기록의 `latency_ms`와 같은 값).

### 기록 형식 (score.py · i3_match_eval.py가 읽는 형식)

- `<실행 폴더>/<파일 stem>_r<k>.json`, 모델 출력은 `output` = `{"items": [{raw_name, price_krw, pour_ml, unit, source_lines}]}` (P47 `hybrid_final_v1`과 같은 키). 그 밖에 `run`, `photo_id`, `photo_sha256`, `model`, `thinking_level`, `prompt_version`, `prompt_sha256`, `clova{latency_ms, from_cache, cache_sha256, image_check}`, `gemini{latency_ms, attempts}`, 토큰 수, `ocr_lines`, 서버가 만든 `flow_items`·`item_sources`.
- 서버가 받아들이지 않는 응답(JSON·스키마·변환 검증 실패, `InvalidModelOutputError`): 서버에서는 그 사진 추출이 실패하므로 `output: null`(빈 출력으로 채점)로 쓰고 응답은 `raw_text`·`parsed_output`에 남긴다. 모델이 답은 했으므로 다시 돌리지 않는다.
- 서버 재시도 뒤에도 답이 없음(`ModelCallError`): `<stem>_r<k>.error.json`. `score.py`는 이 파일을 읽지 않는다. 다음 명령이 그 사진만 다시 보낸다(동결 3장: 응답이 없을 때만 재시도).
- `manifest.json`: 구성(모델·thinking·프롬프트 버전·SHA-256·재시도 정책), 동결 파일 해시, 사진·준비 이미지·OCR 전송 이미지·OCR 캐시 해시, 명령마다 커밋·브랜치·미커밋 변경·호출 수·멈춘 이유. 구성이나 입력이 manifest와 다르면 멈춘다(다른 구성은 새 `--out`).
- `summary.json`: 회차별 기록 수, 빠진 사진, 서버가 거부한 출력, 재시도 수, 사진당 지연(CLOVA·Gemini 따로 평균·p50·p95·최댓값).

## 1. 준비 (한 번)

PowerShell, 레포 루트에서. 브랜치 `feature/i3-p30-extraction-runner`(병합 뒤에는 `main`).

```
git pull
python -m venv .venv-ai
.venv-ai\Scripts\python -m pip install -r ai/requirements.txt
```

- `.env`(레포 루트)에 `GEMINI_API_KEY`, `CLOVA_OCR_INVOKE_URL`, `CLOVA_OCR_SECRET`이 있어야 한다. `BOTTLEMAP_DATA_DIR`이 없으면 `../bottlemap-p14/data`를 쓴다(다른 평가 스크립트와 같음). 사진은 `<data>/eval_photos_i3/`, `photo_map.json`도 거기.
- 아래 명령은 모두 `.venv-ai\Scripts\python`으로 돌린다. 여기서는 `python`으로 적는다.

## 2. 추출 r1 → r2 → r3

### 2.0 점검 (API 호출 0)

```
python ai/eval/p30_extract.py --out ai/runs/2026-10-30_p30/hybrid_i3 --check
```

기대 출력: `photos verified: 33`, `OCR caches: 33/33 present`(캐시가 일부 없으면 `CLOVA calls needed: N`), `r1: 0 done, 33 to run` × 3. `STOP:`이 나오면 원인을 고치기 전에는 아래로 가지 않는다.

### 2.1 추출 (회차별 명령 하나씩)

```
python ai/eval/p30_extract.py --out ai/runs/2026-10-30_p30/hybrid_i3 --runs 1 --max-calls 45
python ai/eval/p30_extract.py --out ai/runs/2026-10-30_p30/hybrid_i3 --runs 2 --max-calls 45
python ai/eval/p30_extract.py --out ai/runs/2026-10-30_p30/hybrid_i3 --runs 3 --max-calls 45
```

- `--max-calls`: 명령 하나의 Gemini 호출 상한(서버 재시도 포함). 회차당 33회 + 재시도 여유 12. 닿으면 그 사진을 쓰지 않고 멈춘다. CLOVA 상한은 `--max-clova-calls`(기본 33).
- 실행 폴더 이름은 첫날 날짜로 고정한다. 다른 날 이어서 돌려도 같은 `--out`을 쓴다.
- 사진 사이 간격 4.5초(`--min-interval`, 분당 한도용). 구성과는 무관하다.

**종료 코드와 이어서 하기**

| 코드 | 뜻 | 할 일 |
|---|---|---|
| 0 | 그 회차 33장 기록 완료 | 다음 명령 |
| 2 | 실행 전 점검 실패(해시·사진·캐시·키·manifest 불일치). API 호출 0 | 원인 수정 후 같은 명령 |
| 3 | 깨끗하게 멈춤: 호출 상한, 할당량(일일 한도 429는 즉시, 분당 429는 서버 재시도 뒤), CLOVA 실패, 답 없음 `.error.json`, Ctrl+C | **같은 명령을 그대로 다시** 돌린다. 이미 있는 기록은 건너뛰고 빠진 사진만 보낸다. 일일 한도면 한도가 풀린 뒤(태평양 자정 = 한국 16:00, 10/30 기준 PDT) |

- r1이 끝나기 전에 r2를 시작하지 않는다(동결 순서). `.error.json`이 남은 사진은 같은 회차 명령을 다시 돌려 채운다. 계속 답이 없으면 그 사진은 빈 출력으로 채점되므로 결과 보고에 적는다.
- 끝나면 `summary.json`의 `r1`–`r3`에서 `records: 33`, `missing: []`, `no_answer_error_files: []`를 확인한다.

## 3. 채점: NFR-1·NFR-2

**33장 × 3회 기록이 모두 있을 때만** 돌린다(`score.py`는 빠진 사진을 빈 출력으로 센다).

```
python ai/eval/score.py --set i3 ai/runs/2026-10-30_p30/hybrid_i3
```

- 라벨 `eval/labels_i3_v1.json`의 SHA-256을 `score.py`가 확인한다(`486b47c0…`). 결과는 `ai/runs/2026-10-30_p30/hybrid_i3/scores.json`.
- **NFR-1** 이름 추출 = 출력의 `f1_strict` 3회 평균 ≥ 0.90. **NFR-2** 가격 추출 = `price_accuracy` 3회 평균 ≥ 0.95. 최솟값·최댓값을 같이 적고, 기준 비교는 반올림 전 값으로 한다.
- 함께 보고(판정 아님): `f1_lenient`, `item_accuracy`, `unit_confusion`, 바별 숫자(`per_bar_accuracy`), 사진당 지연(`summary.json`의 CLOVA·Gemini 평균·p50·p95).
- 서버가 거부한 출력(`output: null`)은 `score.py` 출력의 `failed calls`에 나온다.

## 4. 종단 매칭: 추출 r*k* ↔ LLM r*k* (M3a)

동결 4.2 "종단 입력", 4.3 "반복"(추출 r*i*에 LLM 회차 r*i*를 짝지음, 3쌍). C2 rules+LLM(서버 M3a, M3b 끔), 카탈로그 `full`·`asis` 둘 다. 결과 JSON의 `rules`가 같은 입력의 rules 결과이므로 rules만 따로 돌리지 않는다.

- 시작 전에 동결 4.3 "실행 전 점검"(dev 5곳 E8 숫자 재현, Gemini 호출 0)을 병합된 `main`에서 다시 통과해야 한다. 라벨 입력 P10 실행(동결 4.3 명령 예)은 이 문서 범위가 아니다.
- 응답 캐시는 **(카탈로그, 회차)마다 새 빈 폴더**다. 회차끼리 공유하지 않는다(동결 4.3). 동결 문서 예의 `cache_e2e_r1`은 `full` 하나만 보인 것이고, 두 카탈로그가 캐시를 나눠 쓰면 같은 요청이 캐시에서 돌아와 두 조건이 독립이 아니게 되므로 카탈로그별로 나눈다(판단).
- 키는 `i3_match_eval.py`가 `os.environ`에서 읽는다. 종단 입력은 `e2e_match.load_run`이 레포 `.env`를 불러오므로 따로 설정할 것은 없다. `GEMINI_API_KEY is not set`이 나오면 그 창에서 `.env`를 불러온 뒤 다시 돌린다.

```
python ai/eval/i3_match_eval.py --set i3 --catalog full --extraction ai/runs/2026-10-30_p30/hybrid_i3 --run 1 --llm --cache ai/runs/2026-10-30_p10/cache_e2e_full_r1 --json ai/runs/2026-10-30_p10/c2_full_e2e_r1.json
python ai/eval/i3_match_eval.py --set i3 --catalog asis --extraction ai/runs/2026-10-30_p30/hybrid_i3 --run 1 --llm --cache ai/runs/2026-10-30_p10/cache_e2e_asis_r1 --json ai/runs/2026-10-30_p10/c2_asis_e2e_r1.json
python ai/eval/i3_match_eval.py --set i3 --catalog full --extraction ai/runs/2026-10-30_p30/hybrid_i3 --run 2 --llm --cache ai/runs/2026-10-30_p10/cache_e2e_full_r2 --json ai/runs/2026-10-30_p10/c2_full_e2e_r2.json
python ai/eval/i3_match_eval.py --set i3 --catalog asis --extraction ai/runs/2026-10-30_p30/hybrid_i3 --run 2 --llm --cache ai/runs/2026-10-30_p10/cache_e2e_asis_r2 --json ai/runs/2026-10-30_p10/c2_asis_e2e_r2.json
python ai/eval/i3_match_eval.py --set i3 --catalog full --extraction ai/runs/2026-10-30_p30/hybrid_i3 --run 3 --llm --cache ai/runs/2026-10-30_p10/cache_e2e_full_r3 --json ai/runs/2026-10-30_p10/c2_full_e2e_r3.json
python ai/eval/i3_match_eval.py --set i3 --catalog asis --extraction ai/runs/2026-10-30_p30/hybrid_i3 --run 3 --llm --cache ai/runs/2026-10-30_p10/cache_e2e_asis_r3 --json ai/runs/2026-10-30_p10/c2_asis_e2e_r3.json
```

- 실행마다 결과 JSON의 `catalog_file_sha256`, `catalog_digest`, `gold_sha256`, `translate_prompt_sha256`, `llm_layer_sha256`를 동결 4.5 표와 비교한다(`asis`·`full` digest는 4.5의 C1·C2 값).
- 할당량 오류나 상한(`--max-calls` 기본 250)에서 멈추면 결과가 미완료로 표시된다. **같은 명령(같은 `--cache`)을 다시** 돌리면 빠진 요청만 보낸다.
- 종단 숫자는 판정에 쓰지 않고 함께 보고한다. 종단 Top-1은 `top1_missed_as_fail`(놓친 정답 줄을 실패로 셈)을 쓴다(동결 4.4).

## 5. 예상 API 호출 수

| 단계 | 모델 | 호출 수 | 비고 |
|---|---|---|---|
| 2 추출 r1–r3 | `gemini-3.5-flash-lite` | **99** (33 × 3) + 재시도 | 명령마다 상한 45. I2에서는 재시도 0이 보통이었다 |
| 2 OCR | CLOVA General OCR | 0–33 | 캐시가 33장 다 있으면 0. 없는 사진만 한 번씩 |
| 4 종단 r1–r3 | `gemini-3.1-flash-lite` | **최대 198** (33 × 카탈로그 2 × 3) + 오류 재요청 | 사진당 1회, rules가 확정하지 못한 줄이 없는 사진은 0. 바당 상한 30 |
| (참고) P10 라벨 입력 | `gemini-3.1-flash-lite` | 최대 198 | 동결 4.3, 이 문서 밖 |
| (참고) E10 tools | `gemini-3.1-flash-lite` | 약 500 (상한 ≈ 1,200) | 동결 4.10, P30 추출 뒤에 남은 한도로 |

- **무료 등급 일일 한도는 모델마다 따로다.** 추출(3.5 flash-lite)과 매칭(3.1 flash-lite)은 서로의 한도를 쓰지 않는다. 레포에 3.5 flash-lite의 일일 한도 숫자는 기록되어 있지 않다. 근거: 2026-10-04 P14에서 3.5 flash-lite로 하루 90회 넘게(A·A2 각 45회) 보냈을 때 한도에 걸리지 않았다(3.6 Flash는 하루 20회에서 걸림, `ai/runs/2026-10-04_summary.md`). 그래서 99회는 하루에 들어갈 가능성이 크지만, 돌리기 전에 AI Studio의 rate limit 화면에서 두 모델의 RPD를 확인하고 보고서에 적는다.
- 3.1 flash-lite는 종단 198 + 라벨 입력 198 = 396(동결 4.3 합계)에 E10까지 쓰므로 하루에 끝나지 않을 수 있다. 멈추면 다음 날 같은 명령으로 이어 간다. 끝난 회차는 다시 돌리지 않는다.
- 무료 등급은 입력(메뉴판 사진)이 Google 서비스 개선에 쓰일 수 있다(`ai/runs/ai_usage_log.md`와 같은 판단). 보고서에 적는다.

## 6. 끝난 뒤

- 커밋할 것: `ai/runs/2026-10-30_p30/hybrid_i3/`(기록, `manifest.json`, `summary.json`, `scores.json`)와 `ai/runs/2026-10-30_p10/`의 결과 JSON·캐시. 사진·OCR 캐시(`<data>/`)와 `.env`는 커밋하지 않는다.
- `manifest.json`의 `commands[*].git.uncommitted_changes`가 비어 있는지 본다. 비어 있지 않으면 어떤 파일이었는지 결과 README에 적는다.
- 결과 README에 명령별 호출 수·멈춘 이유(`manifest.json` `commands`)와 `.error.json`·서버 거부 출력 사진을 적는다.
