# P30 실행 명령 (I3 test: 추출 r1–r3 → 채점 → 종단 매칭)

2026-10-29 · 박진우 (작성: Claude Code) · 근거: `ai/docs/i3_eval_freeze.md` 3장(P5 추출 동결), 4.2·4.3(종단 입력·실행)

이 문서의 명령을 **위에서 아래 순서 그대로** 한 번씩 돌린다. 결과를 보고 다시 돌리거나 회차를 고르지 않는다(동결 3장). 같은 명령을 다시 돌리는 것은 "이어서 하기"일 때만이다(아래 2절).

## 0. 무엇을 돌리나

- **추출기:** `ai/eval/p30_extract.py`. 배포 서버 코드 `backend/app/extraction/hybrid.py`의 `extract_menu_hybrid`를 **고치지 않고 그대로 불러** 33장 × r1–r3을 돌린다. 모델 `gemini-3.5-flash-lite`, thinking `medium`, 프롬프트 `hybrid-v1`(`hybrid_prompt_v1.md`, SHA-256 `b73f15d2…1ac50`), 재시도는 서버 정책(`call_with_retries`: 6번 시도, 시간 초과·HTTP 429/5xx에 5–60초 간격, 요청 300초·전체 330초). 모델·thinking은 `.env`의 `EXTRACTION_*`를 읽지 않고 동결 값으로 고정한다.
- **API 호출 전에 멈추는 경우:** 추출 코드 파일 9개의 SHA-256이 동결 값과 다를 때(`5d49c8a` 기준, `clova.py`만 `1e149d4`: 사업자등록증용 `deadline_s` 경로만 추가되어 하이브리드 경로는 같음. `hybrid.py`는 #77(`af4aadf`)이 모듈 docstring 한 줄만 바꾼 판도 받는다: 그 파일의 SHA-256 하나만, `FROZEN_CODE_EQUIVALENT`. `5d49c8a` 판으로 시작한 실행 폴더도 그대로 이어 간다), 채점 코드 `ai/eval/score.py`(`15b1eff`: `5d49c8a` 로직 + `--set i3` 라벨 세트만 추가)·`ai/eval/e2e_match.py`(`5d49c8a`)의 SHA-256이 동결 값과 다를 때, 해시 파일 `ai/eval/i3_photo_sha256.json` 자체의 SHA-256이 동결 값(`305c4f0e…`, `15b1eff`)과 다를 때(`--hashes`로 다른 파일을 줘도 같다), 사진 33장 중 하나라도 해시 파일과 다르거나 빠졌을 때, `photo_map.json`이 해시 파일과 다를 때, OCR 캐시가 다른 사진으로 만든 것일 때, 라벨·2층 정답·해시 파일(`eval/labels_i3_v1.json`, `eval/match_gold_i3_v1.json`, `ai/eval/i3_photo_sha256.json`, `FROZEN_RAW`)의 **원본 바이트** SHA-256이 동결 값과 다를 때(CRLF 줄 끝만 다르면 그렇다고 알려 준다, 1절), 동결 4.5의 매칭 구성 요소(`FROZEN_MATCHING`: `staged.py`, `vocab_ko_en.json`, `catalog_v2_service.json`, `llm_layer.py`, 프롬프트 2개, `matching_llm.py`, `gemini_matching_llm.py`, `i3_match_eval.py`, `match_eval.py`)가 빠졌거나 원본 바이트 SHA-256이 4.5 값과 다를 때, 실행 폴더의 `manifest.json`이 이 명령의 구성·입력과 다를 때, `manifest.json` 없이 기록·`.error.json` 등 파일이 남은 폴더일 때. 이 점검은 `--check`에서도 똑같이 한다. 이때 종료 코드는 2이고 API 호출은 0이다.
- **키:** 레포 루트 `.env`의 `GEMINI_API_KEY`, `CLOVA_OCR_INVOKE_URL`, `CLOVA_OCR_SECRET`만 읽는다. 화면·기록·manifest에 쓰지 않고, 오류 문구에 들어 있으면 `***`로 지운 뒤 저장한다.

### CLOVA는 사진당 한 번 (r1–r3 공유)

동결 1장 "사진 사용 제한"이 "가이드라인 v2.3 검수 전 OCR 대조용 CLOVA OCR 캐시를 만들 수 있고, **P30 하이브리드 추출은 그 캐시를 그대로 쓴다**"고 정했다. 그래서 회차마다 CLOVA를 다시 부르지 않는다.

- 캐시: `<BOTTLEMAP_DATA_DIR>/ocr_cache/<파일 stem>__table-off.json` (`ai/ocr/clova.py` 형식, `label_ocr_check.py`가 읽는 그 파일). 캐시가 이미 있으면 CLOVA 호출은 0이다.
- 캐시가 없는 사진만 서버 코드(`app.extraction.clova.call_ocr`, 표 인식 끔)로 **한 번** 부르고 같은 형식으로 캐시에 쓴다. r2·r3은 그 캐시를 쓴다.
- 캐시 응답은 가짜 HTTP 클라이언트로 서버 함수에 넘긴다. 그래서 OCR 줄 표, 프롬프트, Gemini 요청은 서버 코드가 직접 만든다. 이 클라이언트는 서버가 보낼 이미지가 캐시를 만든 이미지와 같은지 확인한다(`sent_sha256`). 원본 바이트를 보내는 사진에서 다르면 멈춘다. EXIF 회전이나 8,000px 축소로 다시 인코딩되는 사진은 Pillow 버전에 따라 바이트가 달라질 수 있어, 해시가 달라도 출처를 확인할 수 있을 때만 쓴다. 이 runner가 만든 캐시는 `source_sha256`이 확인된 사진의 해시와 같아야 한다. `ai/ocr/clova.py`가 만든 캐시는 그때 보낸 이미지(`<data>/prepared/` 또는 `prepared_ocr/`의 `sent_image`)가 아직 `sent_sha256`과 같고, 서버가 보낼 이미지와 크기가 같으며 픽셀 차이가 채널 평균 2 이하(0–255)여야 한다. 확인할 수 없으면 멈추고, 그 캐시 파일을 지우면 다음 명령이 CLOVA를 한 번 불러 새로 만든다.
- 이유: 동결이 그렇게 정했고, 3회 반복으로 재려는 것은 Gemini 응답의 흔들림이다. OCR까지 매번 다시 부르면 회차 차이에 OCR 차이가 섞인다. I2 P47도 같은 방식이었다(`ai/runs/2026-10-17_p47/manifest.json`, `clova_calls: 0`). 서버는 업로드마다 CLOVA를 부르지만, 사진 한 장에 대한 OCR 결과는 서버에서도 한 번만 쓰인다.
- 지연: 기록의 `clova.latency_ms`는 그 캐시를 만든 실제 호출 한 번의 지연이다(세 회차에 같은 값). `gemini.latency_ms`는 회차마다 성공한 시도의 지연이다(서버 `CallResult.latency_ms`, P47 기록의 `latency_ms`와 같은 값).

### 기록 형식 (score.py · i3_match_eval.py가 읽는 형식)

- `<실행 폴더>/<파일 stem>_r<k>.json`, 모델 출력은 `output` = `{"items": [{raw_name, price_krw, pour_ml, unit, source_lines}]}` (P47 `hybrid_final_v1`과 같은 키). 그 밖에 `run`, `photo_id`, `photo_sha256`, `model`, `thinking_level`, `prompt_version`, `prompt_sha256`, `clova{latency_ms, from_cache, cache_sha256, image_check}`, `gemini{latency_ms, attempts}`, 토큰 수, `ocr_lines`, 서버가 만든 `flow_items`·`item_sources`.
- 서버가 받아들이지 않는 응답(JSON·스키마·변환 검증 실패, `InvalidModelOutputError`): 서버에서는 그 사진 추출이 실패하므로 `output: null`(빈 출력으로 채점)로 쓰고 응답은 `raw_text`·`parsed_output`에 남긴다. 모델이 답은 했으므로 다시 돌리지 않는다.
- 서버 재시도 뒤에도 답이 없음(`ModelCallError`): `<stem>_r<k>.error.json`. `score.py`는 이 파일을 읽지 않는다. 다음 명령이 그 사진만 다시 보낸다(동결 3장: 응답이 없을 때만 재시도).
- `manifest.json`: 구성(모델·thinking·프롬프트 버전·SHA-256·재시도 정책), 동결 파일 해시(추출·채점·라벨/정답/해시 파일·매칭), 사진·준비 이미지·OCR 전송 이미지·OCR 캐시 해시, 명령마다 커밋·브랜치·미커밋 변경·호출 수·멈춘 이유. 구성이나 입력이 manifest와 다르면 멈춘다(`--check`도 같은 기준, 다른 구성은 새 `--out`). 새 manifest는 **비어 있거나 없는 폴더**에서만 만든다. manifest 없이 `*_r<k>.json`·`.error.json`(또는 다른 파일)이 있으면 그 기록이 어떤 구성으로 만들어졌는지 알 수 없으므로 멈춘다. 원래 `manifest.json`을 되살리거나 새 빈 `--out`을 쓴다.
- `summary.json`: 회차별 기록 수, 빠진 사진, 서버가 거부한 출력, 재시도 수, 사진당 지연(CLOVA·Gemini 따로 평균·p50·p95·최댓값).

## 1. 준비 (한 번)

PowerShell, 레포 루트에서. 브랜치 `feature/i3-p30-extraction-runner`(병합 뒤에는 `main`).

```
git pull
python -m venv .venv-ai
.\.venv-ai\Scripts\python -m pip install -r ai/requirements.txt
```

**줄 끝(CRLF) 맞추기.** `score.py`(라벨)와 `i3_match_eval.py`(2층 정답, 결과 JSON의 `catalog_file_sha256`·`llm_layer_sha256`)는 파일의 **원본 바이트** SHA-256을 동결 값과 비교한다. Windows에서 `core.autocrlf=true`로 받은 파일은 줄 끝이 CRLF라 내용이 같아도 해시가 달라진다. `.gitattributes`가 라벨·정답·해시 파일 3개를 항상 LF로 받게 하지만, 이미 CRLF로 받아 둔 파일은 다시 받아야 바뀐다. 한 번만 아래를 돌린다(PowerShell, 레포 루트). 이 파일들에 커밋하지 않은 변경이 있으면 지워지므로, 동결 파일은 고치지 않은 상태여야 한다.

```
git config core.autocrlf false
$frozen = @(
  "eval/labels_i3_v1.json", "eval/match_gold_i3_v1.json", "ai/eval/i3_photo_sha256.json",
  "backend/app/matching/staged.py", "backend/app/matching/vocab_ko_en.json", "ai/catalog/catalog_v2_service.json",
  "backend/app/matching/llm_layer.py", "backend/app/matching/prompts/translate_prompt_v3.md",
  "backend/app/matching/prompts/pick_prompt_v1.md", "backend/app/adapters/matching_llm.py",
  "backend/app/adapters/gemini_matching_llm.py", "ai/eval/i3_match_eval.py", "ai/eval/match_eval.py"
)
Remove-Item $frozen
git checkout -- $frozen
git status --short -- $frozen
```

macOS·Linux(bash·zsh, 또는 Git Bash)에서는 같은 목록으로:

```
git config core.autocrlf false
frozen=(eval/labels_i3_v1.json eval/match_gold_i3_v1.json ai/eval/i3_photo_sha256.json
  backend/app/matching/staged.py backend/app/matching/vocab_ko_en.json ai/catalog/catalog_v2_service.json
  backend/app/matching/llm_layer.py backend/app/matching/prompts/translate_prompt_v3.md
  backend/app/matching/prompts/pick_prompt_v1.md backend/app/adapters/matching_llm.py
  backend/app/adapters/gemini_matching_llm.py ai/eval/i3_match_eval.py ai/eval/match_eval.py)
rm -- "${frozen[@]}"
git checkout -- "${frozen[@]}"
git status --short -- "${frozen[@]}"
```

- 마지막 `git status`에 아무것도 나오지 않으면 된다. 파일을 지운 뒤 다시 받는 것은, 이미 받아 둔 파일은 설정을 바꿔도 git이 다시 쓰지 않기 때문이다. `core.autocrlf false`에서는 git이 커밋된 바이트(LF) 그대로 쓴다.
- 그 뒤 `git status --short`에 다른 파일이 많이 `M`으로 나오면 줄 끝만 다른 것이다(CRLF로 받아 둔 나머지 파일). 그대로 두면 `manifest.json`의 `uncommitted_changes`에 추출 코드가 바뀐 것으로 남으므로 전체를 LF로 다시 받는다. 먼저 `git diff --ignore-cr-at-eol --stat`이 아무것도 내지 않는지(줄 끝 말고는 바뀐 것이 없는지) 확인하고, 그때만 `git checkout -- .`을 돌린다. 이 명령은 커밋하지 않은 변경을 모두 지운다. 다시 `git status --short`가 비어 있어야 한다.
- 목록은 `p30_extract.py`의 `FROZEN_RAW`(라벨·정답·해시 파일, `.gitattributes`에 `eol=lf`)와 `FROZEN_MATCHING`(동결 4.5 매칭 구성 요소)이다. 추출 코드(`FROZEN_CODE`)와 채점 코드(`FROZEN_EVAL`)는 CRLF를 LF로 읽어 비교하므로 다시 받지 않아도 된다.
- 다음 절의 `--check`가 이것을 확인한다. 줄 끝만 다르면 `CRLF line ends (Windows core.autocrlf=true ...)`로 멈추고, 그때는 위 명령을 다시 돌린다.

- `.env`(레포 루트)에 `GEMINI_API_KEY`, `CLOVA_OCR_INVOKE_URL`, `CLOVA_OCR_SECRET`이 있어야 한다. `BOTTLEMAP_DATA_DIR`이 없으면 `../bottlemap-p14/data`를 쓴다(다른 평가 스크립트와 같음). 사진은 `<data>/eval_photos_i3/`, `photo_map.json`도 거기.
- 아래 명령은 모두 `.\.venv-ai\Scripts\python`으로 돌린다(PowerShell은 PATH 밖의 실행 파일에 `.\`가 필요하다). 여기서는 `python`으로 적는다.

## 2. 추출 r1 → r2 → r3

### 2.0 점검 (API 호출 0)

```
python ai/eval/p30_extract.py --out ai/runs/2026-10-30_p30/hybrid_i3 --check
```

기대 출력: `photos verified: 33`, `OCR caches: 33/33 present`(캐시가 일부 없으면 `CLOVA calls needed: N`), `r1: 0 done, 33 to run` × 3, `manifest: none yet (new, empty run dir)`(이어서 할 때는 `manifest: N earlier command(s), configuration and inputs match`). `STOP:`이 나오면 원인을 고치기 전에는 아래로 가지 않는다. `--check`는 실제 명령과 같은 점검(동결 파일·원본 바이트·매칭 파일·사진·OCR 캐시·manifest)을 하고 API는 부르지 않는다.

### 2.1 추출 (회차별 명령 하나씩)

```
python ai/eval/p30_extract.py --out ai/runs/2026-10-30_p30/hybrid_i3 --runs 1 --max-calls 45
python ai/eval/p30_extract.py --out ai/runs/2026-10-30_p30/hybrid_i3 --runs 2 --max-calls 45
python ai/eval/p30_extract.py --out ai/runs/2026-10-30_p30/hybrid_i3 --runs 3 --max-calls 45
```

- `--max-calls`: 명령 하나의 Gemini 호출 상한(서버 재시도 포함). 회차당 33회 + 재시도 여유 12. 닿으면 그 사진을 쓰지 않고 멈춘다. CLOVA 상한은 `--max-clova-calls`(기본 33)이고 서버 `call_ocr`의 재시도(최대 3번)도 HTTP 요청마다 하나씩 센다. 재시도 중에 닿으면 그 사진을 쓰지 않고 멈춘다.
- 실행 폴더 이름은 첫날 날짜로 고정한다. 다른 날 이어서 돌려도 같은 `--out`을 쓴다.
- `--runs`는 1, 2, 3만, 오름차순으로 받는다(동결 r1–r3). 다른 숫자나 순서는 인자 오류로 바로 끝난다. 앞 회차가 다 끝나지 않았으면(같은 명령의 `--runs`에 앞 회차를 먼저 넣은 경우는 제외) 뒤 회차는 API 호출 없이 멈춘다: r1 → r2 → r3 순서를 지킨다.
- 사진 사이 간격 4.5초(`--min-interval`, 분당 한도용). 구성과는 무관하다.

**종료 코드와 이어서 하기**

| 코드 | 뜻 | 할 일 |
|---|---|---|
| 0 | 그 회차 33장 기록 완료 | 다음 명령 |
| 2 | 실행 전 점검 실패(해시·CRLF·사진·캐시·키·manifest 불일치, manifest 없는 기록 폴더). API 호출 0 | 원인 수정 후 같은 명령 |
| 3 | 깨끗하게 멈춤: 호출 상한, 할당량(일일 한도 429는 즉시, 분당 429는 서버 재시도 뒤), CLOVA 실패, 답 없음 `.error.json`, Ctrl+C | **같은 명령을 그대로 다시** 돌린다. 이미 있는 기록은 건너뛰고 빠진 사진만 보낸다. 일일 한도면 한도가 풀린 뒤(태평양 자정 = 한국 16:00, 10/30 기준 PDT) |

- r1이 끝나기 전에 r2를 시작하지 않는다(동결 순서). `.error.json`이 남은 사진은 같은 회차 명령을 다시 돌려 채운다. 계속 답이 없으면 그 사진은 빈 출력으로 채점되므로 결과 보고에 적는다.
- 끝나면 `summary.json`의 `r1`–`r3`에서 `records: 33`, `missing: []`, `no_answer_error_files: []`를 확인한다.

## 3. 채점: NFR-1·NFR-2

**33장 × 3회 기록이 모두 있을 때만** 돌린다(`score.py`는 빠진 사진을 빈 출력으로 센다). 채점 바로 전에 `--check`를 다시 돌려 `score.py`·`e2e_match.py`가 동결 그대로인지 확인한다(`STOP: frozen scoring files changed`면 채점하지 않고 원인을 먼저 본다).

```
python ai/eval/p30_extract.py --out ai/runs/2026-10-30_p30/hybrid_i3 --check
python ai/eval/score.py --set i3 ai/runs/2026-10-30_p30/hybrid_i3
```

- 라벨 `eval/labels_i3_v1.json`의 SHA-256을 `score.py`가 확인한다(`486b47c0…`). 결과는 `ai/runs/2026-10-30_p30/hybrid_i3/scores.json`.
- **NFR-1** 이름 추출 = 출력의 `f1_strict` 3회 평균 ≥ 0.90. **NFR-2** 가격 추출 = `price_accuracy` 3회 평균 ≥ 0.95. 최솟값·최댓값을 같이 적고, 기준 비교는 반올림 전 값으로 한다.
- 함께 보고(판정 아님): `f1_lenient`, `item_accuracy`, `unit_confusion`, 바별 숫자(`per_bar_accuracy`), 사진당 지연(`summary.json`의 CLOVA·Gemini 평균·p50·p95).
- 서버가 거부한 출력(`output: null`)은 `score.py` 출력의 `failed calls`에 나온다.

## 4. 종단 매칭: 추출 r*k* ↔ LLM r*k* (M3a)

동결 4.2 "종단 입력", 4.3 "반복"(추출 r*i*에 LLM 회차 r*i*를 짝지음, 3쌍). C2 rules+LLM(서버 M3a, M3b 끔), 카탈로그 `full`·`asis` 둘 다. 결과 JSON의 `rules`가 같은 입력의 rules 결과이므로 rules만 따로 돌리지 않는다.

- 시작 전에 동결 4.3 "실행 전 점검"(dev 5곳 E8 숫자 재현, Gemini 호출 0)을 병합된 `main`에서 다시 통과해야 한다. 라벨 입력 P10 실행(동결 4.3 명령 예)은 이 문서 범위가 아니다.
- 바로 전에 `python ai/eval/p30_extract.py --out ai/runs/2026-10-30_p30/hybrid_i3 --check`를 다시 돌린다. 동결 4.5의 매칭 구성 요소(`FROZEN_MATCHING`)와 2층 정답이 원본 바이트로 4.5 값과 같은지, 추출 기록의 manifest가 맞는지 확인한다. `STOP: frozen matching files`가 나오면(파일이 빠졌거나 바뀜, CRLF) 매칭을 돌리지 않는다. 이 점검은 4.5 SHA-256(파일 바이트 = 동결 커밋의 blob 내용)으로 하고, 커밋 해시로는 하지 않는다(4장 "파일 SHA-256으로 동결").
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

- 실행마다 결과 JSON의 `catalog_file_sha256`, `catalog_digest`, `gold_sha256`, `translate_prompt_sha256`, `llm_layer_sha256`를 동결 4.5 표와 비교한다(`asis`·`full` digest는 4.5의 C1·C2 값). 파일 해시는 `--check`가 이미 확인했으므로, 여기서는 하네스가 만든 `catalog_digest`(파일 없음)가 핵심이다.
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
