# AI 사용 기록

과제 수행 중 AI 도구를 사용한 내역입니다. 새 작업은 아래에 이어서 기록합니다.

| 항목 | 기록할 내용 |
|---|---|
| 도구 | 사용한 도구와 모델 |
| 범위 | AI가 만든 것 |
| 사람 결정 | 사람이 정하거나 고친 것 |
| 검증 | 결과를 확인한 방법 |

---

## 2026-10-05 · P17 매칭 함수 Iteration 1 (정규화 + 별칭 정확 일치)

- **도구:** Claude Code (Claude Opus 5.5), 데스크톱 앱 Code 탭
- **브랜치/PR:** `feature/ai-catalog-seed` (seed 데이터 분리 PR), `feature/ai-matching` (이 작업)

### 진행 순서
1. 담당자가 범위·제약·참고 문서를 지정 (매칭 플로우 v2 6~8·10장, 스키마 가이드 6장·8.4·8.6, `ai/catalog` seed, backend 구조).
2. Claude가 문서와 seed를 읽고 구현 계획을 제시. 코드 작성 전에 확인받음.
3. 담당자가 계획을 검토하고 아래를 결정·수정.
4. Claude가 구현, 테스트, 평가를 수행하고 PR 초안 작성.

### 사람 결정
- uv 설치(`pip install uv`) 후 `uv add --dev pytest`로 lock까지 갱신.
- `ai/catalog/`와 `.gitignore`의 `_ref/`는 별도 PR(`feature/ai-catalog-seed`)로 먼저 올림.
- **에디션 충돌 판정 변경:** 카탈로그 `edition_name`은 영어이고 메뉴 추출값은 한글일 수 있음(Lasanta / 라산타). 정규화한 추출 에디션이 상품의 `edition_name` 또는 별칭(정규화)에 포함되면 일치, 아니면 충돌. 상품에만 에디션이 있으면 exact 허용, 추출값에만 있으면 ambiguous. 10.2를 엄격히 읽은 것과 다르다는 점을 PR에 명시.
- **한/영 병기(`A / B`)를 `resolve_product` 안에서 처리:** 전체 이름을 먼저 조회하고, 일치가 없을 때만 나눠서 조회. 평가 스크립트는 `raw_name`을 나누지 않고 통째로 전달.
- normalize에는 7장 규칙만 둠 (`aged` 삭제 같은 규칙은 추가하지 않고 별칭으로 처리).

### AI가 만든 것
- `backend/app/core/normalize.py`, `backend/app/matching/` (types, resolve, memory_catalog)
- `backend/tests/` 3개 파일 (50개 테스트), `backend/scripts/eval_alias_matching.py`
- seed PR과 매칭 PR의 커밋 메시지, PR 설명

### AI가 제안해 반영된 것 (사람 확인)
- 7장 예시를 맞추려고 공백을 전부 제거. 부작용: `와일드터키 101 8Y`가 `와일드터키1018`이 됨 (별칭도 같은 규칙이라 일관성은 유지).
- `年`은 7장 예시(`12年`)를 위해 연수 표현에 포함.
- 평가에 `--exclude-alias-source` 옵션 추가. 별칭 상당수가 평가 대상 두 바의 메뉴판에서 수집됐기 때문에 이를 뺀 수치도 함께 보기 위함.

### 검증
- `uv run pytest`: 50 passed
- seed 검사: 서로 다른 상품이 같은 정규화 별칭을 갖는 경우 0건
- `labels_v1_1.json` 219항목 평가:

| 조건 | exact_match | 정답률 | 오매칭 |
|---|---|---|---|
| 전체 별칭 | 215/219 (98.2%) | 219/219 (100%) | 0 |
| 평가 바 메뉴 출처 별칭 제외 | 185/219 (84.5%) | 189/219 (86.3%) | 0 |

- 전체 별칭 조건의 100%는 별칭이 같은 메뉴판에서 수집됐기 때문이라 일반화 성능으로 보면 안 됨. 출처를 제외한 조건에서 실패 16개 이름은 모두 unmatched였고(오매칭 0), 브랜드·유사도 단계(Iteration 2)에서 다룰 대상.
- 한/영 병기 70항목은 모두 분리 조회로 exact_match. 코냑 4항목은 unmatched.

### 사용 중 있었던 문제
- Claude가 seed 커밋 제목에 근거 없이 태스크 번호 `P16`을 붙였다가, 푸시 직후 스스로 발견해 번호를 지우고 다시 푸시함 (본인 브랜치, 다른 사람이 받기 전).
- 처음에는 이 PC에 `gh` CLI가 없어 PR을 만들지 못함. 담당자가 `gh`를 설치하고 직접 로그인한 뒤, Claude가 `gh pr create`로 seed PR(#4)과 매칭 Draft PR(#5, base `feature/ai-catalog-seed`)을 생성함.
- 머지: 저장소에 승인 규칙이 없고 팀 약속도 없다는 담당자 확인 후, 담당자 요청으로 Claude가 #4를 squash merge하고, #5를 main 위로 rebase(force-push)해 base를 main으로 바꾼 뒤 테스트 50개 통과와 평가 수치 동일을 확인하고 #5를 Draft 해제 후 squash merge함.
- 샌드박스에서 pytest 기본 임시 폴더(`%TEMP%\pytest-of-user`) 접근이 막혀 `--basetemp`를 따로 지정해 실행함. 코드 문제는 아님.

---

## 2026-10-04 · P14 Vision LLM 메뉴 추출 PoC

- **도구:** Claude Code (Claude Opus 5.5), 데스크톱 앱 Code 탭. 추출 모델은 Gemini (`gemini-3.5-flash-lite`, `gemini-3.6-flash`, 무료 등급)
- **브랜치/PR:** 로컬 `feature/ai-extract-poc`에서 작업, 레포 반영은 A4 PR(`feature/ai-extraction`)에서 함께 함
- **결과:** `ai/runs/2026-10-04_summary.md` (A2 = Flash-Lite + thinking medium 채택, 항목 정답률 0.996)

### 진행 순서와 시간

| 단계 | Claude Code에 맡긴 일 | 사람이 검증한 것 | 시간(대략) | 토큰(대략) |
| --- | --- | --- | --- | --- |
| 0 | 문서 3개(실험 설계·가이드라인 v2.1·평가 계획) 재검토, 라벨/사진 연결 점검 | 이슈 6개 결정, 클론 위치 결정 | 10분 | |
| 1 | 레포 클론, 브랜치 생성, labels_v1.json SHA-256 확인, `.gitignore`·`.env.example` 추가 | 해시 일치 확인 | 5분 | |
| 2 | Gemini API 문서 조사(모델 ID, 구조화 출력, temperature, thinking, media_resolution, 데이터 저장), SDK 2.28.0 타입 정의로 교차 확인, 사진 EXIF 점검 | API 방식·설정값 결정 | 15분 | |
| 2b | 실험 설계·평가 계획 보강 반영(반복 5회, 조건 A2, 판정 규칙, 정답률 정의) | 보강 내용 지시, diff 검토 | 10분 | |
| 3 | `prompt_v1.md` 초안, 가이드라인 대조·평가셋 누출 검사 | 프롬프트 검토 | 10분 | |
| 3b | `extract.py` 작성(전처리 1회 캐시, Interactions 호출, 메타 기록, 재시도), 가짜 클라이언트로 오프라인 검증 | 회전 결과 육안 확인 | 25분 | |
| 4 | 스모크 테스트 1회, 출력과 사진 대조, 유료 등급 비용 추정 | 대조 결과 검토 | 10분 | Gemini 4,839 |
| 5 | `score.py`·테스트 20개, `run_experiment.py`, 파일럿(1장 × A/A2/B × 1회) | 파일럿 출력과 정답 대조 | 30분 | Gemini 약 13k |
| 6 | 본 실행(A·A2 90회 + B 14회), 멈춤 2회 진단·수정, 채점, 오류 사례 분석, summary 초안 | 한도 화면 확인, A·A2 우선 완료 결정, summary 검토 | 2시간 30분 | Gemini 약 48만 |

### 사람 결정
- 무료 등급으로 진행. 무료 등급은 입력(메뉴판 사진)이 서비스 개선에 쓰일 수 있고 `store=False`로도 막을 수 없음. 근거는 메뉴판이 블로그 등에 공개적으로 올라오는 경우가 많다는 판단. **업주 동의서 범위와의 대조는 아직 안 함.**
- 스모크의 쉐리→셰리(외래어 표기 임의 수정)는 prompt_v1을 그대로 두고 진행. 문제가 되면 가이드라인과 프롬프트를 함께 수정 (후속 과제).
- 본 실행 전 이름 후보 분리 규칙 변경: 공백 있는 ` / `만 나누던 것을 모든 슬래시로 나누고 전체 이름도 후보에 포함 (eval_plan 대응 규칙 1에 명시).
- B는 무료 등급 일일 한도(3.6 Flash RPD 20) 초과로 14/45에서 보류. 판정은 A2 행에서 결정돼 B와 무관.

### AI가 만든 것
- `ai/extract/` (prompt_v1.md, extract.py, run_experiment.py), `ai/eval/` (score.py, test_score.py, report.py)
- `ai/runs/2026-10-04_*` 실행 기록과 `2026-10-04_summary.md` 초안

### 검증
- labels_v1.json SHA-256 `c8a2…1dac` 일치 (git blob 기준)
- 스모크: 출력 38항목을 사진과 대조, raw_name 1건(쉐리→셰리) 어긋남
- 파일럿: 복춘_03(16항목)에서 A·A2·B 모두 16/16. 파일럿 결과는 `*_pilot_*`에 따로 두고 본 실행 집계에 넣지 않음
- 회전 확인을 위해 Claude Code가 평가셋 사진(복춘_01) 축소본 1장을 열어봄. prompt_v1은 그 전에 확정됐고 이후 수정은 fewshot 사진 결과로만 함. 축소본은 확인 직후 삭제

### 사용 중 있었던 문제
- Windows `core.autocrlf=true` 때문에 labels_v1.json 해시가 달라 보였음(CRLF 변환). 클론 로컬 설정을 `core.autocrlf=false`로 바꿔 해결.
- Interactions 응답의 `steps`에 보낸 사진(base64)이 echo될 수 있어 원본 응답 저장 시 `input`·`system_instruction`·`user_input` 단계를 제거.
- 본 실행 중 B 호출이 응답 없이 약 50분, 재개 후 20분 이상 멈춤. 원인은 SDK timeout이 읽기 대기 기준이라 전체 시간 상한이 아니었고, SDK 타임아웃 예외를 재시도 대상으로 인식 못 했으며 SDK 자체 재시도와 겹친 것. 호출당 330초 전체 시간 상한(스레드), SDK 재시도 끄고 자체 재시도로 일원화. 멈춘 호출은 결과에 포함되지 않음.
- summary 초안에서 Claude Code가 쓴 "서로상 01은 A가 형식을 지켰다"가 검증 중 틀린 것으로 확인돼 수정(실제로는 영문 먼저 쓴 역순 병기).
- API 키 사용 기록에 이 실험에서 부르지 않은 모델(3.5 Flash, 3.1 Flash Lite) 요청이 있음. 키를 다른 곳에서도 쓰는지 확인 필요.

---

## 2026-10-06 · A4 메뉴 추출 모듈 (P14 → backend)

- **도구:** Claude Code (Claude Opus 5.5), 데스크톱 앱 Code 탭. 실제 API 확인 1회는 Gemini `gemini-3.5-flash-lite` (thinking medium)
- **브랜치/PR:** `feature/ai-extraction` (base `main`)
- **시간(대략):** 약 1시간 30분 (현황 파악 15분, 설계 20분, 구현·테스트 45분, 마무리 10분)
- **토큰(대략):** Gemini 6,560 (실제 API 확인 1회: 입력 2,333 / 출력 2,049 / thought 2,178)

### 진행 순서
1. 담당자가 단계와 멈춤 지점(현황 파악, 설계 확인, 실제 API 확인, 마무리)을 지정.
2. Claude가 현황을 보고: 실험 코드가 레포 클론에 커밋되지 않은 상태로 있었고, 로컬 main이 9커밋 뒤처졌으며, swpp3가 Python 3.11이라 backend(≥3.12)와 맞지 않고, main의 `.gitignore`가 루트 `.env`를 막지 않음.
3. Claude가 실험 출력과 흐름 문서 v2 4.3장의 차이표와 변환안을 제시하고, 담당자가 결정.
4. Claude가 구현, 단위 테스트, 실제 API 1회 확인, PR 작성.

### 사람 결정
- swpp3에 uv 설치, uv가 관리하는 Python 3.12로 `backend/.venv` 생성.
- `ai/runs/`는 summary뿐 아니라 실행 기록 JSON·manifest·scores·run.log까지 전부 올림(재현·검증 근거). 커밋 전 base64·키 검사.
- 첫 커밋은 `.gitignore` 보강(루트 `.env` 차단). 브랜치는 `origin/main`(fb398b9)에서 생성.
- backend 모듈은 실험과 같은 호출 방식(google-genai 2.28.0 고정, Interactions API, A2 설정).
- 4.3장 대비: 이번에는 `product`만 반환(실험 프롬프트 v1 그대로), brandText·ageYears·editionName·abv·confidence는 null. 프롬프트 v2(4.3 전체 반환)는 후속 과제.
- 반환값은 `{"items", "meta"}`. meta에 모델·thinking·프롬프트 해시·토큰·지연·재시도 횟수·변환 전 v1 출력.
- 재시도 기본값은 실험 값(6회, 요청 300초, 전체 330초), 환경변수로 변경 가능. P18은 백그라운드 작업으로 호출.
- 리뷰어 2명 지정, 1명 승인 후 머지(머지는 담당자/팀이 함).

### AI가 만든 것
- `backend/app/extraction/` (config, errors, schema, convert, image, gemini, service, prompt_v1.md 복사본, .gitattributes)
- `backend/tests/test_extraction.py` (52개), `backend/.env.example` 추가분, `.gitignore` 보강
- 이 로그의 P14 절(기존 표 형식 로그를 이 파일 형식으로 옮김), 커밋 메시지, PR 설명

### AI가 제안해 반영된 것 (사람 확인)
- 잔·병 묶기 규칙: 바로 붙어 있고 raw_name이 같으며 unit이 glass·bottle 하나씩인 두 항목만 합침. 근거: A2 출력의 잔·병 쌍 530개 모두 인접.
- EXIF 회전 전처리를 backend에서도 메모리에서 똑같이 수행(Pillow 12.3.0 고정). 받는 MIME은 실험과 같게 jpeg/png만.
- 프롬프트 줄바꿈을 LF로 고정(`.gitattributes` + 로드 시 정규화). `autocrlf=true`인 팀원 PC에서도 프롬프트 바이트가 P14와 같도록.
- 테스트에서 프롬프트 해시와 응답 스키마를 P14 값으로 고정.

### 검증
- `uv run pytest`: 125 passed, 41 skipped (기존 73 + 신규 52). 건너뛴 41개는 DB 테스트로, 로컬에 Postgres(`POSTGRES_TEST_DATABASE`)가 없어서임.
- 실제 API 1회 (`fewshot_78_kr_en_glass_bottle.png`): completed, 재시도 없음, 12.5초. v1 출력 38항목이 P14 스모크 기록과 38/38 같았고(쉐리→셰리 포함) 4.3 형식 21항목(메뉴판 21줄)으로 변환됨. 프롬프트 예시 사진이라 정확도 근거가 아니라 "P14와 동작이 같다"는 확인용.
- uvicorn 기동 후 `/health`·`/openapi.json` 200 확인, 바로 종료 (websockets 17.2 → 16.1.1 다운그레이드 영향 확인).
- 커밋 전 검사: `ai/` 실행 기록에서 API 키 패턴·실제 키 값 0건. 긴 base64는 A2·B 기록 61개의 `steps[].signature`(Gemini thought signature, 1~7KB)뿐이고 이미지 시그니처 0건. 사진·`.env`는 커밋 목록에 없음.

### 사용 중 있었던 문제
- swpp3에 uv가 없고 Python 3.11이라 `pip install uv` 후 uv가 3.12를 받아 venv 생성.
- 레포에 git 작성자 정보가 없어 커밋이 실패. 담당자의 이전 커밋과 같은 이름·이메일을 이 레포 로컬 설정에만 지정.
- google-genai 추가로 `websockets`가 17.2 → 16.1.1로 내려감. 기동 확인으로 대응.
- 실제 API 확인 스크립트를 처음에 import 경로 없이 실행해 실패(API 호출 전). `PYTHONPATH` 지정 후 1회 실행.
- 테스트 1건을 Claude가 잘못 작성(모든 상품 필드가 null인 description을 실패 사례로 둠). 실행에서 드러나 수정.

---

## 2026-10-06 · A6 Gemini 추출기를 메뉴 업로드 처리에 연결

- **도구:** Claude Code (Claude Opus 5.5), 데스크톱 앱 Code 탭. 실제 API 확인 1회는 Gemini `gemini-3.5-flash-lite` (thinking medium)
- **브랜치/PR:** `feature/a6-gemini-extractor` (base `main`, `origin/main` ad453b0에서 생성)
- **시간(대략):** 약 1시간 (현황 파악 15분, 구현 15분, 테스트 15분, 실제 확인·마무리 15분)
- **토큰(대략):** Gemini 7,340 (실제 API 확인 1회: 입력 2,333 / 출력 2,514 / thought 2,493)

### 진행 순서
1. 담당자가 단계와 멈춤 지점(현황 파악, 실제 확인, 마무리)과 금지 사항(A4 로직·프롬프트·설정값, 업로드 처리 서비스, models/alembic, 기본값 변경, 머지)을 지정.
2. Claude가 현황을 보고: adapter 규격(`MenuExtractor`, `ExtractionResult`, `ExtractionError(raw_output)`), deps가 첫 요청 때에야 추출기를 만드는 구조, processing이 실패 시 `raw_output`에 남기는 형식, A4 반환값·예외 4종, 이미지 형식(둘 다 jpeg/png). 필드 매핑·예외 변환 표 제안.
3. 담당자가 제안 4건 승인, Claude가 구현·테스트·실제 확인 1회·PR 작성.

### 사람 결정
- 서버 시작 시 설정 검사를 위해 공용 파일 `app/main.py`에 lifespan 추가 (mock일 때는 영향 없음). PR 설명에 공용 파일 변경으로 명시.
- `adapters/extraction.py`는 import만 하고 수정하지 않음.
- 로컬 Postgres가 없어 실제 확인은 `GeminiMenuExtractor` 직접 호출로 대신하고, 서버 경유 확인은 못 했다고 PR에 명시.
- `ModelCallError`는 모델 출력이 없어도 `raw_output={"attempts": n}`을 남김.
- `provider="google"`, `model_name`=`EXTRACTION_MODEL` 값, `pipeline_version="bottlemap-menu-gemini-promptv1-thinking-medium"` (thinking 수준을 포함).
- 기본값은 `MENU_EXTRACTOR=mock` 유지.

### AI가 만든 것
- `backend/app/adapters/gemini_extraction.py` (`GeminiMenuExtractor`)
- `backend/app/api/deps.py` gemini 선택지, `backend/app/main.py` lifespan
- `backend/tests/test_gemini_extraction_adapter.py` (21개)
- `backend/.env.example`·`backend/README.md` 환경변수 설명, 이 로그 항목, 커밋 메시지, PR 설명

### AI가 제안해 반영된 것 (사람 확인)
- 성공 시 `raw_output`은 A4 `meta` 전체(변환 전 v1 출력, 모델, 토큰, 지연, 재시도 횟수).
- 실패 메시지 앞에 A4 예외 이름을 붙임. processing은 `raw_output.error`에 adapter 클래스 이름(`ExtractionError`)만 남기기 때문.
- `InvalidModelOutputError`는 `meta`와 모델 원문(`rawText`)을 함께 남김. A4가 성공했는데 adapter 검증에서 걸리는 경우도 `meta`를 붙여 다시 던짐.
- mock일 때는 Gemini SDK를 import하지 않도록 deps에서 지연 import.

### 검증
- 전체 pytest: 219 passed, 186 skipped (신규 21개 포함). 건너뛴 186개는 DB 테스트로, 로컬에 Postgres(`POSTGRES_TEST_DATABASE`)가 없어서임. 테스트에서 실제 API 호출 0회(`extract_menu`를 가짜로 바꾸고, 실제 클라이언트 생성은 실패하게 막음).
- 실제 API 1회 (`fewshot_78_kr_en_glass_bottle.png`, `MENU_EXTRACTOR=gemini`로 deps를 거쳐 생성): completed, 재시도 없음, 14.6초. v1 출력 38항목 → 21항목. seed 카탈로그(`InMemoryCatalog`)로 매칭하니 exact_match 18, unmatched 3(글렌알라키 10년 CS 배치 #9~#11). 가이드라인 예시 원본 사진이라 매칭률이 실제보다 높을 수 있음. 일반 성능 근거는 평가셋 결과.
- 커밋 전 검사: `uv.lock`·`pyproject.toml` 변경 없음, `.env`·키·사진 커밋 목록에 없음.

### 사용 중 있었던 문제
- 이 PC의 `backend/.venv`는 Python 3.14.7이고(A4 기록의 3.12 venv와 다름), P18 이후 추가된 `python-multipart`가 없어 업로드 라우트 테스트가 실패. `uv sync --locked`로 맞춤(lock 파일 변경 없음). `uv`가 PATH에 없어 절대 경로로 실행.
- 샌드박스가 시스템 Temp 접근을 막아 `tmp_path` 테스트 12개가 에러. `--basetemp`를 작업 폴더로 지정해 재실행, 모두 통과.
- 로컬 Postgres가 없어 업로드 API → 처리 → 리뷰 데이터 조회 흐름은 확인하지 못함.

## 2026-10-13 · P11 (I2) held-out test 벤치마크 + 프롬프트 v2 val 회귀 확인

- **도구:** Claude Code (Claude Opus 5.5), 데스크톱 앱 Code 탭. 추출은 Gemini `gemini-3.5-flash-lite` (A2: thinking medium), `BOTTLEMAP_PROMPT_VERSION=v2`
- **브랜치/PR:** `i2-p11-heldout-benchmark` (base `origin/i2-p5-heldout-labels`)
- **시간(대략):** 약 1시간 30분 (준비·사진 15분, 파일럿 10분, 본 실행 약 25분, 채점·리포트·분석 30분, 마무리 10분)
- **토큰(대략):** Gemini 495,521 (70회: 파일럿 1 + test 42 + val 27. 입력 197,022 / 출력 122,650 / thought 175,849). 재시도 0회, 실패 0회

### 진행 순서
1. 담당자가 단계(준비 → 사진 → 파일럿 → 본 실행 → 채점·리포트)와 멈춤 지점, 금지 사항(프롬프트·라벨·score.py 채점 규칙, 백엔드·DB·카탈로그 수정, 사진·prepared·.env 커밋, 429 반복 재시도)을 지정.
2. Claude가 준비 상태 확인: 브랜치와 P11 패치 커밋이 이미 로컬에 있어 `git am` 대신 `git patch-id`로 패치와 동일함을 확인. pytest 25개 통과 후 push.
3. 사진 14장 복사(`prepare_test_photos.py`), 파일럿 1회(`011_mirabeau_05`): 52항목 모두 브랜드 제목 포함, unit 전부 glass. 담당자 확인 후 본 실행.
4. test 42회 → val 27회 실행. 429 재시도 줄이 보이면 자식 프로세스를 끊는 감시 래퍼(작업 공간 밖 scratchpad)로 실행.
5. 채점·리포트. val 리포트에서 `report.py`가 A 조건 없이 죽어 담당자 승인 후 수정, 재생성.
6. 담당자 요청으로 Beck_04 오류 분류, 미라보_01·02 제목 누락 쌍 집계(코드·라벨 수정 없이 분석만).

### 결과 (사전 등록 기준, score.py 변경 없음)
- test (14장 × 3): 항목 정답률 0.843 (0.831–0.855), F1 관대 0.924, 가격 정확도 0.981. 바별 Beck 0.897 / 미라보 0.816 / 포레스트 0.946
- val (9장 × 3): 항목 정답률 0.982 (0.964–1.000). I1 v1 A2(5회)는 0.996
- 1장당: test 평균 14.7초·$0.0137, val 9.1초·$0.0079 (유료 환산)

### 사람 결정
- push, 다운로드 폴더 경로, Gemini 69회 본 실행 승인. 파일럿 결과 확인 후 본 실행.
- `report.py`: 조건 A가 없으면 판정 대신 "판정 생략: I1 판정 규칙은 A/A2/B 3조건 비교용" 출력 (I1 A/A2 출력은 그대로임을 확인).
- 이번 채점 결과를 "사전 등록 기준" 결과로 확정. 분석 결과를 보고 규칙·라벨을 바꾸지 않음.

### AI가 만든 것
- `ai/runs/2026-10-13_{pilot_v2,test_v2,val_v2}_A2/`, `2026-10-13_test_report.md`, `2026-10-13_val_report.md`
- `ai/eval/report.py` 판정 생략 분기, 커밋 메시지, 이 로그 항목

### 분석 (제안만, 미적용)
- Beck_04: 오류 30건 전부 가격. 이름·45ml 누락 없음. 가격 열이 이름보다 반 줄 위에 인쇄돼, Balvenie부터 가격이 한 줄씩 밀림(27건) + 마지막 Macallan Sherry 가격 null(r3, 3건).
- 미라보_01·02: 오탐·누락 쌍 중 92쌍(01: 74, 02: 18)이 "라벨 이름에서 앞의 병입사·브랜드 제목만 뺀 것"이고 가격은 모두 일치. Claude는 처음에 "v2가 병입사 제목을 빠뜨림"으로 해석했으나, 담당자가 정정: v2 프롬프트의 "줄에 이미 제품명이 다 있으면 제목을 붙이지 않는다" 규칙대로 출력한 것이고 라벨이 그 규칙과 어긋남. 라벨·프롬프트·score.py는 수정하지 않음.
- 사후 진단 `ai/eval/diag_header.py` (판정 미반영): score.py 대응 후 남은 오탐·누락 중 앞의 "제목(괄호 포함)"만 다르고 unit·가격이 맞는 쌍을 정답으로 다시 침(양방향). test 0.843 → 0.949 (0.919–0.967), 101쌍(미라보_01 74, _02 18, _09 9, 모두 라벨에만 제목). val 0.982 → 0.982 (0쌍). 결과 `ai/runs/2026-10-13_diag_header.md`.

### 검증
- pytest `ai/eval` 25 passed (`--basetemp`을 scratchpad로 지정).
- 커밋 전 검사: 실행 기록은 json/md만(이미지 없음), API 키 패턴 없음, `.env`·사진·prepared 커밋 목록에 없음.

### 사용 중 있었던 문제
- 이 셸에서 `python`이 Microsoft Store 스텁으로 잡히고 전역 Python에 PIL이 없어, 레포 `.venv/Scripts/python.exe`로 실행.
- 샌드박스가 시스템 Temp 접근을 막아 `tmp_path` 테스트 1개가 에러 → `--basetemp` 지정으로 해결.
- `extract.py`는 429도 최대 5회 재시도하므로, 코드를 바꾸지 않고 실행 감시 래퍼로 429 재시도 시 즉시 중단하도록 함(실제 발생 0회).

## 2026-10-13 · P22 (I2) 매칭 평가 하네스 + 매칭기 S1·S2 (dev)

- **도구:** Claude Code (Claude Opus 5.5), 데스크톱 앱 Code 탭. 외부 API 호출 없음 (Gemini 0회)
- **브랜치:** `i2-p22-matching-eval` (base `i2-p11-heldout-benchmark`, P22 패치 `git am`)
- **시간(대략):** 약 1시간 30분 (0단계 준비·정답 수정 20분, S1 25분, S2 35분, 마무리 10분)
- **토큰(대략):** Claude Code 세션 컨텍스트 약 23만 토큰(마무리 시점), Max 플랜 5시간 한도의 6%

### 진행 순서
1. 담당자가 단계(0 준비 → S1 → S2 → 마무리), 단계마다 멈춤, 금지 사항(test 분할 평가·열람, 정답을 결과에 맞춰 수정, 카탈로그 JSON·`resolve_product`·`normalize.py`·메뉴 등록/게시 코드 수정)과 중단 규칙(dev false merge 0.02 초과 시 미채택)을 지정.
2. 0단계: P22 패치 적용·push. 정답 1건 수정("Buffalo Trace / Makrt's Mark"를 `both:`로, 하나만 exact면 `partial`). M0 C1 Top-1이 0.803 → 0.798로 바뀌어 담당자에게 보고, 담당자 결정으로 eval_plan.md 기준선을 옛 값과 사유를 남기고 수정.
3. S1(괄호 병기, 두 상품 묶음 → status `multi`) 구현·측정: dev 변화 없음(괄호 표기 0줄, 묶음 줄은 오타로 미발동). 합성 이름으로 동작 확인.
4. S2(브랜드 + 연수 + 에디션 토큰) 구현·측정: false merge 0, C0 Top-1 0.937, C1 0.884.
5. 마무리: eval_plan.md에 결과 표·주의 두 줄, 이 로그, 커밋·push.

### 결과 (dev, 사전 등록 지표)
- M0 → S1 → S1+S2, C0 Top-1 0.867 → 0.867 → 0.937, C1 0.798 → 0.798 → 0.884. false merge 전부 0, partial C1 1(Buffalo 줄).
- 업주 부담 5 미만 사진: C0 0.62 → 0.69, C1 0.85 → 0.92.
- 새 exact는 전부 정답(C0 10줄, C1 15줄). ambiguous_bad 2줄(C0, 카탈로그에 없는 상품에 같은 브랜드 후보).

### 사람 결정
- push, uv 설치·`uv sync` 승인.
- Buffalo 정답 정의 변경과 M0 기준선 수정(옛 값 0.803 유지 기록).
- S2 위험("해당 연수 상품이 카탈로그에 하나뿐이면 exact")은 test 평가 전에 정책을 정하기로 함. test는 평가·열람하지 않음.

### AI가 만든 것
- `backend/app/matching/staged.py` (`resolve_product_staged`, S1·S2), `types.py`(`ProductInfo.brand_id`, `ResolutionResult.parts`, status `multi`, `CatalogLookup` 브랜드 조회 2개), 메모리·DB 카탈로그 구현
- `ai/eval/match_eval.py`: `both:`·`partial` 판정, 매처 `S1`·`S1+S2`, 평가 카탈로그 브랜드(C1 새 브랜드는 영문명 하나), `build_match_gold.py` 정답 수정·LF 출력
- 테스트 `tests/test_resolve_staged.py`(23개), 메모리·DB 카탈로그 브랜드 조회 테스트, `ai/runs/2026-10-13_match_dev.json`, eval_plan.md 결과 절, 커밋 메시지, 이 로그 항목

### AI가 제안해 반영된 것 (사람 확인)
- M0 기준선 처리 방식 (a) 수정 + 사유 기록.

### 검증
- 0단계 후 M0 C0 숫자가 기준선과 같음을 확인. 단계마다 줄 단위로 status·후보를 비교(S1: 변화 0줄, S2: 바뀐 줄 전부 확인, 새 오답 0).
- 단계 없이 부르면 `resolve_product`와 결과가 같은지 테스트로 확인. DB 카탈로그와 메모리 카탈로그의 staged 결과 일치 테스트 추가(DB 미설정이라 skip).
- 백엔드 pytest 전체: 275 passed, 194 skipped(DB), 실패 0.

### 사용 중 있었던 문제
- backend `.venv`에 boto3가 없어 conftest(autouse fixture) import가 실패, 거의 모든 테스트가 수집 오류 → 승인 후 `uv sync`로 해결.
- `build_match_gold.py`가 Windows에서 CRLF로 써서 gold 파일 전체가 diff로 잡힘 → 출력 줄바꿈을 LF로 고정.
- gold의 새 상품 브랜드 `makers-mark`와 카탈로그 브랜드 key `makers_mark`가 달라 평가 카탈로그에서 다른 브랜드로 잡힘 → 평가 스크립트에서 하이픈을 밑줄로 바꿔 연결.
- 샌드박스가 시스템 Temp를 막아 `tmp_path` 테스트 에러 → `--basetemp`를 scratchpad로 지정.

## 2026-10-13 · P22 (I2) 매칭기 S2b(기본 제품) + S3(편집거리) (dev)

- **도구:** Claude Code (Claude Opus 5.5), 데스크톱 앱 Code 탭. 외부 API 호출 없음
- **브랜치:** `i2-p22-matching-eval`
- **시간(대략):** 약 45분 (사전 등록 5분, 구현 20분, 측정·줄 비교 10분, 테스트·마무리 10분)
- **토큰(대략):** Claude Code 세션 컨텍스트 약 23만 → 약 29만 토큰(이 작업 약 6만)

### 진행 순서
1. 담당자가 S2b 규칙 3개, S3 규칙 6개와 임계값, 측정 명령, 중단 규칙, 금지 사항(정답·카탈로그·normalize·resolve_product 변경, dev를 보고 S3 임계값 조정)을 지정.
2. eval_plan.md에 S2b·S3 규칙을 측정 전에 사전 등록하고 먼저 커밋·push(`7ba8592`). S3 5번 "편집거리 1"은 숫자는 같고 어순만 다른 거리 0도 포함하도록 "1 이하"로 적음.
3. 구현: `CatalogLookup`에 전체 별칭 목록 2개 추가(메모리·DB), `staged.py`에 S2b(`_narrow_brand`의 기본 제품·확인 권장)와 S3(상품 별칭·브랜드 별칭 편집거리, 숫자 일치 필수).
4. 측정 1회, 줄 단위 비교(S1+S2 → S2b, S2b → S3).

### 결과 (dev)
- false merge 전 단계 0 → 중단 규칙 통과.
- 알려진 상품 Top-1: C0 0.937 → 0.916 → 0.916, C1 0.884 → 0.867 → 0.867. 확인 권장: C0 0 → 3 → 6, C1 0 → 3 → 7.
- S2b exact → 확인 권장 3줄(정답 상품 유일 후보). S3 unmatched → 확인 권장 C0 3줄, C1 4줄(정답 상품 유일 후보). 새 오답 0.

### 사람 결정
- S2b·S3 규칙과 임계값(담당자 지정). 임계값은 dev 결과로 조정하지 않음.

### AI가 만든 것
- `staged.py` S2b·S3, `CatalogLookup.list_normalized_aliases` / `list_normalized_brand_aliases`(메모리·DB), `match_eval.py` 매처 2개와 확인 권장 건수
- 테스트 13개(기본 제품 우선, 에디션 상품 확인 권장, 숫자 다르면 후보 제외, 편집거리 exact 조건, 동점 ambiguous, 한글 음절 거리 등)와 카탈로그 목록 테스트, eval_plan.md 사전 등록·결과, 이 로그 항목

### 검증
- 단계별 줄 단위 비교로 바뀐 줄 전부 확인(위 결과). S1+S2 숫자가 이전 측정과 같음을 확인.
- 백엔드 pytest 전체: 288 passed, 194 skipped(DB), 실패 0.

## 2026-10-13 · P22 (I2) test 2층 정답 병합 + C1 정의 수정

- **도구:** Claude Code (Claude Opus 5.5), 데스크톱 앱 Code 탭. 외부 API 호출 없음
- **브랜치:** `i2-p22-matching-eval`
- **시간(대략):** 약 20분
- **토큰(대략):** Claude Code 세션 컨텍스트 약 28만 → 약 31만 토큰

### 진행 순서
1. 담당자가 test 정답 패치 3개(초안 → 검수 반영 → Woodford Double XO Blend) 적용, C1 정의 변경, test 초안 병합, `POST_TEST_ALIASES` 미반영, test split 미실행을 지정.
2. 패치 3개 `git am` (충돌 없음, 정답 초안 파일만 변경).
3. `build_match_gold.py`가 `eval/match_gold_test_draft.json`의 test 사진·새 상품·review를 그대로 복사해 `match_gold_v1.json`에 split "test"로 합침(새 상품 key·review 중복 시 오류).
4. C1 변경 전 dev 측정: test 새 상품 307개가 dev 카탈로그에 섞여 S1+S2 C1 0.884 → 0.867로 바뀜을 확인 → C1을 "평가하는 split의 정답이 참조하는 new 상품만"으로 변경.

### 결과
- 병합: dev 13장 316항목(이전과 동일), test 10장 478항목(초안과 동일), 새 상품 30 + 307 = 337.
- dev 재측정(M0, S1+S2, S1+S2b, S1+S2b+S3): `2026-10-13_match_dev.json`이 병합 전과 완전히 같음. S1+S2 C0 0.937, C1 0.884.
- test split은 실행하지 않음. test 정답 내용은 구조(키·개수)만 확인.

### 검증
- dev 사진·기존 새 상품이 병합 전과 같음, test 사진이 초안과 같음을 스크립트로 비교.
- 백엔드 pytest 전체: 288 passed, 194 skipped(DB).

## 2026-10-13 · P22 (I2) test 매칭 평가 최종 사전 등록 + 동결

- **도구:** Claude Code (Claude Opus 5.5), 데스크톱 앱 Code 탭. 외부 API 호출 없음
- **브랜치:** `i2-p22-matching-eval`, 동결 커밋 `69879fd`
- **시간(대략):** 약 20분
- **토큰(대략):** Claude Code 세션 컨텍스트 약 31만 → 약 34만 토큰

### 진행 순서
1. 담당자가 사전 등록 5개 항목(대상 매처·횟수, 주 지표, 업주 부담 세분화, 판정 규칙, 동결)과 "dev 숫자는 다시 재지 않음"을 지정.
2. `match_eval.py`에 업주 부담 세분화(확인 / 선택 / 직접 등록 / 오답 후보, 사진당)와 "(b)+(c)+(d) 5 미만 사진" 추가. dev로 동작만 확인: 기존 필드는 저장된 결과와 완전히 같고, 사진별 세분화 합 = 기존 업주 부담.
3. eval_plan.md: dev 결과 표에 M0 행과 세분화 열 추가, 최종 사전 등록 절 작성, 커밋(`69879fd`) 후 해시 기록.

### AI가 정한 것 (사람 확인 필요)
- 판정 규칙 4번은 조건을 명시하지 않아 "C0와 C1 각각에서 둘 다 만족"으로 적음.
- (b) 선택에 정답이 `unknown`인 후보 1개 줄을 포함(정답 상품이 없어 "확인"이 아님).

### 검증
- test split 실행 없음. 백엔드 코드 변경 없음.

## 2026-10-13 · P22 (I2) test 매칭 평가 1회 실행

- **도구:** Claude Code (Claude Opus 5.5), 데스크톱 앱 Code 탭. 외부 API 호출 없음
- **브랜치:** `i2-p22-matching-eval`. 실행 커밋 = 동결 커밋 `69879fd` (detached checkout 후 실행, 브랜치로 복귀)
- **시간(대략):** 약 15분
- **토큰(대략):** Claude Code 세션 컨텍스트 약 34만 → 약 37만 토큰

### 진행 순서
1. 담당자가 두 결정(C0·C1 둘 다 만족, `unknown` 후보 1개는 (b))을 확정하고 실행·보고 규칙(6–9번)과 판정 무관 보고 항목(`unknown` 줄 중 confirmRecommended 건수)을 지정.
2. eval_plan.md의 동결 해시 기록과 동결 이후 동결 대상 파일 무변경(`git diff 69879fd HEAD`)을 확인.
3. 동결 커밋에서 사전 등록 명령 1회 실행. 이후 보고 숫자는 결과 JSON과 정답 파일에서만 집계(매처 재실행 없음).

### 결과
- false merge·overconfident 모든 매처·조건 0 → 판정 규칙 4번에 따라 S1+S2b+S3 채택.
- 알려진 상품 Top-1: C0 M0 0.252 / S1+S2 0.770 / S1+S2b+S3 0.778, C1 0.072 / 0.371 / 0.379.
- 이상해 보이는 결과(M0 미라보 0줄, 부담 5 미만 0.00, C1 Top-1 낮음)는 고치지 않고 eval_plan.md에 그대로 기록.

### 검증
- 실행 전후 `git status`로 결과 JSON 외 변경 없음 확인. 매처 코드·정답·임계값 변경 없음.

## 2026-10-14 · P12 (I2) CLOVA OCR 능력 확인

- **도구:** Claude Code (Claude Opus 5.5), 데스크톱 앱 Code 탭. OCR은 CLOVA General OCR V2, 2단계 파싱은 Gemini `gemini-3.5-flash-lite` (A2: thinking medium, E1과 같은 설정)
- **브랜치:** `i2-p12-clova` (base `i2-p11-heldout-benchmark` 6cd2bb8, `git log`로 P11 E1 코드가 있는 브랜치 확인). PR 없음, push 안 함
- **시간(대략):** 약 3시간 30분 (계획·사전 등록 30분, 구현·테스트 50분, 키·URL 문제 해결 20분, val 실행·프롬프트 수정 50분, test 실행 25분, 사진 대조·보고서 35분)
- **호출:** CLOVA 48회 (val 18 + 표 추출 설정 전 재호출 1 + test 28 + 실제 API 단위 테스트 1, 실패·재시도 0, 연결 실패한 시도는 서버에 닿지 않음). Gemini 178회 (파일럿 1 + val 27 × 5판 + test 42), 토큰 1,525,426 (입력 746,493 / 출력 279,008 / thought 499,925), 실패 0

### 진행 순서
1. 담당자가 과제(1단계 재현율, 2단계 파싱, 선택 하이브리드), 원칙(키는 레포 .env만, 프롬프트는 val에서만 수정, 사전 등록), 보고 형식을 지정.
2. Claude가 `ai/docs/p12_plan.md`를 쓰고 OCR·LLM 호출 전에 커밋(d686997). 지표·판정 규칙(Δ = CLOVA+LLM − E1 0.843, ±0.03)을 담음.
3. `ai/ocr/` 구현과 픽스처 테스트. 담당자 추가 지시로 순차 호출, 장축 8,000px 이상 축소 반영(호출 전, plan 변경 이력 기록).
4. 키 문제: 처음 키가 작업 폴더 `.env`에만 있었음 → 담당자가 레포 `.env`로 옮김. 첫 invoke URL은 사설 IP(10.x)로 풀리는 주소라 연결 불가 → 담당자가 콘솔에서 공개 APIGW URL로 교체.
5. val 1장 스모크(2회) → 표 추출이 꺼져 있던 것 확인, 담당자가 켬 → val 9장 OCR, 1단계 재현율 → 2단계 파일럿 1회 → val 3회 × 프롬프트 5판.

### 1단계 (val, 표 인식 off)
- CLOVA 이름 완전 0.991 / 근사 1.000 / 한 줄 0.991, 가격 1.000. 같은 자로 잰 E1: 0.970 / 0.988 / 0.942 / 1.000
- 완전 일치 실패는 `글렌모렌지 퀸타루반` → `퀀타루반` 1건(잔·병 2항목)

### 2단계 파싱 프롬프트 수정 이력 (val 9장 × 3회, 항목 정답률 평균 (최소–최대))

| 판 | 바꾼 것 | 왜 (val에서 본 것) | val 결과 |
| --- | --- | --- | --- |
| v1 | 프롬프트 v2 규칙·텍스트 예시 + OCR 줄 읽는 법 (CLOVA 순서 줄, 0–1000 상자) | 초판. Beck_04(test)에서 나온 "같은 가격 반복 시 행 건너뛰지 않기" 문구는 test 누설이라 초안에서 뺌 | 0.952 (0.883–0.991) |
| v2 | 입력을 y로 묶은 행 단위로(`lines.py` group_rows, 허용 폭 0.75 × 중앙 높이), 이웃 행 가격 x로 열 판단, 가격 없는 열은 항목 안 만듦 | 복춘_01 `노마드` 병 가격 `20`이 OCR 목록 맨 끝에 따로 나와 위 행(에드라두어)에 붙음. 복춘_02 잔 가격만 있는 줄에 병 항목 생성 | 0.912 (0.906–0.914) |
| v3 | v1 입력 형식으로 복귀 + 정렬 규칙(목록 순서 무시, 단별 위→아래 대응과 가격 열 전체의 y 어긋남 확인, 이웃 행 x로 열 판단, 빈 열 항목 금지, 섹션 제목 단별 적용) | v2에서 기운 사진의 오른쪽 단 가격이 이름보다 한 행 위에 있어 행 묶음이 밀림을 고정(복춘_02 Islay 9칸 × 3회), 단이 섞여 브랜디·칵테일 항목 포함 | **0.974 (0.936–0.995)** |
| v4 | v3 + 페이지 맨 위 제목은 모든 단에 적용, null 가격 병 항목 금지 문구 강화 | v3 r3에서 복춘_04(칵테일 전용) 오른쪽 단이 "제목 없음 → 유지"로 12항목 포함. 잔만 있는 줄의 병 null 항목 남음 | 0.857 (0.643–0.982) |
| v5 | v3에서 "섹션 제목 단별 적용" 문구만 뺌 (마지막 판) | v4의 페이지 제목 규칙은 복춘_01 전체를 비우는(r1, thought 0) 부작용 | 0.934 (0.815–0.995) |

- **동결:** v5 실행 전에 plan에 적은 규칙(v3·v5 중 val 평균이 높은 쪽)으로 **v3** 동결. 줄 복원 = v1 방식(CLOVA 순서, 가로 간격 2.5 × 줄 높이에서 열 나눔), 표 인식 off. sha256 `e62c33be4b7fb80769b5f8e71628a480f31f5f0382b66ab8267a63aab0242127`
- **해석 주의:** 같은 프롬프트에서도 호출 간 편차가 크다(v5 r3 복춘_01 0.500, thought 5,734). v1·v3·v5 차이는 한두 호출이 만든 것이라 val로는 구별이 약하다. thinking medium에서 모델이 생각을 건너뛴(thought 0) 호출이 v1·v2·v4에 6–7회 있었고, 그런 호출이 복잡한 사진에서 크게 틀렸다(v1 복춘_01 r3 0.731, v4 r1 0.000). v3·v5에서는 0회
- **test 누설 관련 공개:** v2–v3의 행 정렬 규칙은 val 복춘_01·02 오류에서 나왔지만, Claude는 P11에서 Beck_04(test) 가격 행 밀림을 이미 알고 있었다. test의 Beck_04 결과는 이 규칙에 대한 완전한 블라인드 검증이 아니다
- 프롬프트에 val·test 라벨 이름이 들어가지 않는지 테스트로 검사(E1 프롬프트 v2와 공통인 가이드라인 예시 `글렌파클라스105 CS`는 예외). v2 초안의 예시 행이 val 텍스트(`아란 10Y`)였던 것을 실행 전에 가이드라인 예시로 교체, v4 초안의 소제목 예시 "시그니처"(복춘_04에 있음)도 일반 단어로 교체

### 사람 결정
- 순차 호출, 장축 8,000px 축소, 레포 `.env` 키 입력과 invoke URL 교체, 콘솔 표 추출 켬, val 27회 실행 승인

### 검증
- pytest `ai/ocr` + `ai/eval` 49 passed (실제 API 테스트 포함, `--basetemp` scratchpad)
- 캐시·`ocr_calls.json`·커밋에 시크릿과 invoke URL 호스트 없음을 문자열 검사로 확인. OCR 응답 원본은 레포 밖 `data/ocr_cache/`

### 사용 중 있었던 문제
- Windows에서 Python `write_text`가 `p12_plan.md`를 CRLF로 바꿔 커밋 → LF로 되돌리고 그 로컬 커밋을 amend. 이후 문서 수정은 바이트로 씀

### test 실행 (동결 커밋 cf178d4, 한 번)
- 1단계: CLOVA 이름 완전 0.899 / 근사 0.997, 가격 0.993. E1 같은 자 0.838 / 0.932 / 0.994
- 2단계 v3 (14장 × 3): 항목 정답률 **0.883 (0.821–0.956)**, Δ +0.040 → 사전 등록 규칙 1행 "I3 추출 경로 후보". Beck_04 3회 48/48, 포레스트 3회 1.000, 크라이넬리시 정확
- 사후 진단(제목 유무 무시): 0.949 (0.887–1.000), E1과 같음. 판정 미반영
- 보고서 `ai/runs/2026-10-14_p12_clova/report.md`

### 사진 대조 (Claude가 크롭을 보고 분류, 원본은 레포 밖 scratchpad에만)
- 완전 일치 실패 56개 이름: CLOVA 실제 오독 7, 라벨이 메뉴판 인쇄와 다름 41(캐스크 스트랭스 28, 맥켈란 6 등), 문장부호(백틱) 5, 판독 불확실 3
- 라벨 표기 불일치는 P11의 "외래어 표기 변형" 분류에도 영향(일부는 E1이 맞게 읽음). 라벨은 수정하지 않음, 담당자 결정 사항으로 보고
- test 14장에 손글씨 메뉴 없음(썸네일로 확인)

## 2026-10-14 · L1 (I2) 라벨 v1.1 (메뉴판 인쇄 표기) + 재채점

- **도구:** Claude Code (Claude Opus 5.5), 데스크톱 앱 Code 탭. 외부 API 호출 없음 (Gemini 0, CLOVA 0. CLOVA 캐시와 기존 실행 기록만 사용)
- **브랜치:** `i2-labels-v1-1` (`i2-p12-clova` c3ccf6a + `i2-p22-matching-eval` merge, `ai_usage_log.md` 충돌은 양쪽 섹션 모두 유지). PR 없음, push 안 함
- **시간(대략):** Claude 작업 약 1시간 30분 (도구·검토 페이지 40분, v1.1 빌드·검증 20분, 재채점 15분, 리포트·가이드라인 15분). 담당자 검토 시간 별도
- **토큰(대략):** Claude Code 세션 컨텍스트 약 9만 토큰

### 진행 순서
1. 담당자가 원칙(v1 파일 수정 금지, 인쇄 그대로, raw_name만 수정, API 0회)과 2단계 진행(검토 페이지에서 멈춤 → 승인 후 반영)을 지정.
2. Claude가 `ai/eval/label_ocr_check.py`를 작성(라벨 토큰과 CLOVA OCR 대조, 패턴별 묶음, 사진 크롭). test에서 P12 리포트의 완전 일치 실패 56개 이름을 그대로 재현했고, val에서는 1개를 찾았다.
3. Claude가 크롭을 보고 P12 분류(A–D)를 다시 확인. 리포트와 다른 점 2가지를 질문으로 올림: 엡버스(인쇄 "엠버스"), Beck 백틱(인쇄 자체가 백틱). 검토 페이지 `review/labels_v1_1.html`(커밋 안 함)을 전달하고 멈춤.
4. 담당자 결정을 반영해 `build_labels_v1_1.py`로 v1.1 생성(test 44, val 2항목). `build_match_gold_v1_1.py`로 매칭 정답의 이름만 교체. `rescore_labels_v1_1.py`로 재채점.

### 사람 결정
- 포레스트 "퀸타"가 인쇄대로라 라벨 유지(P12 B → A). Beck 백틱은 인쇄대로라 유지(C 수정 안 함). 엠버스는 B
- D 판독: 미아기쿄 / 셰리캐스크 / 시그니처 / (val) 퀀타루반. Claude 판독 중 세리캐스크(라벨 유지 쪽)는 틀렸음
- 버전 문자열은 `labels_v1.1` 그대로 (`ai/catalog/labels_v1_1.json`과 별개 파일이라고 changelog에 기록)

### AI가 정한 것 (사람 확인 필요)
- 항목 id = `<photo_id>#<index>` (라벨에 id 필드가 없어 위치로 정함)
- `match_gold_v1.json`과 그 빌더는 P22 동결 대상이라 다시 빌드하지 않음. 위치로 맞춰 이름만 바꾼 `eval/match_gold_v1_1.json`을 새로 만듦. `match_eval.py`는 고치지 않고 GOLD 경로만 바꿔 호출
- `score.py`에 `val_v1_1`, `test_v1_1` 라벨 세트를 추가(SHA 고정). 채점 규칙은 그대로
- 가이드라인은 v2.2를 남기고 `labeling_guideline_v2.3.md`를 새로 만듦(규칙 변경 없음, "검수 전 OCR 대조" 절차만 추가)

### 검증
- v1 파일 SHA 그대로(c8a2…1dac, 07bc…98d7). v1.1은 raw_name 외 필드·순서·개수가 같은지 빌드 스크립트가 검사. v1.1을 다시 대조하면 남는 차이는 승인된 A 12개뿐
- 매칭 정답 상품 연결이 v1과 794/794 같음. 동결 파일 `git diff 69879fd HEAD` 빈 결과
- 재채점의 v1 숫자가 저장된 `scores.json` 3개, `2026-10-13_match_test.json`과 완전히 같음
- pytest `ai/eval/test_label_ocr_check.py` + `test_score.py` 31 passed (`--basetemp` scratchpad)

### 사용 중 있었던 문제
- `ai/ocr/test_ocr.py`를 같이 돌렸을 때 실제 API 테스트(`test_live_clova_call`)가 수집됐다. pytest 임시 폴더 권한 오류로 setup에서 멈춰 호출은 일어나지 않았다(CLOVA 0회 유지). 이후 그 파일은 실행하지 않음
- 기본 브라우저 패널이 로컬 HTML을 열지 못해, 검토 페이지는 텍스트 추출로 확인하고 파일로 전달

### 결과
- `ai/runs/2026-10-14_labels_v1_1_rescore.md`: 판정 불변(P12 Δ +0.040 → +0.041, P22 false merge 0). CLOVA+LLM 엄격 F1 +0.071, E1 test 항목 정답률 −0.001(맥켈란 편집 2), 매칭 Top-1 −0.003~−0.008(별칭이 표준 표기)

## 2026-10-14 · M3 (I2) 매칭 LLM 층 (M3a 번역 후 규칙, M3b 후보 고르기)

- **도구:** Claude Code (Claude Opus 5.5), 데스크톱 앱 Code 탭. 외부 API: Gemini `gemini-3.1-flash-lite`(thinking low) 50회(스모크 1, dev 39, test 10). 실행당 상한 200회 안
- **브랜치:** `i2-labels-v1-1`에서 `i2-m3-llm-match`. PR 없음, push 안 함
- **시간(대략):** Claude 작업 약 3시간 (설계·사전 등록 30분, 코드·테스트 1시간, dev 3회차 1시간, test·보고서 30분). 담당자 검토 시간 별도
- **토큰(대략):** Claude Code 세션 약 25만 토큰. Gemini 입력 약 9.9만 / 출력 4.9만 / thought 0.8만

### 진행 순서
1. 담당자가 M3 스펙(원칙 5개, M3a/M3b, 채택 기준, 순서)을 줌. Claude가 해석이 필요한 7가지(거부권 정의, 병입사 목록, 오답률 분모, 번역 대상 줄, 결과 적용, 판정 조건, 캐시 위치)를 질문 → 담당자가 3가지 변경(합치기 방식, C0·C1 둘 다 안전 기준, P17 기준 병입사 목록)
2. 사전 등록 커밋 `5e8dfce` → 코드 → 사진 1장 스모크(Beck_03) 결과 보고 후 dev 전체
3. dev r0 → 문제 사례 유형별 보고 → 담당자 결정으로 수정 1회차(r1) → 2회차(r2) → 거부권 단위 테스트 → 동결 `1ace927` → test 1회

### 프롬프트·규칙 수정 이력 (dev만 보고 수정, 최대 2회)
| 회차 | 번역 프롬프트 | 규칙 | 이유 (dev 사례) | 결과 |
|---|---|---|---|---|
| r0 | v1 | 거부권 3 (bottler_missing 양방향, age_mismatch, alias_of_other) | – | C0 LLM 확인 권장 4/7, 수락 시 오답률 0.017 |
| r1 | v2: `expansions`(약어 풀이) 칸, 라인업이면 소유 브랜드 | + `edition_mismatch`, 중립 단어(cask/oak/barrel/wood/finish 등), 짧은 토큰 단어 일치(없으면 확인 권장 불가) | 메뉴 에디션이 카탈로그에 없을 때 형제 상품에 붙음(Maker's Mark CS, Laphroaig 10 CS, Arran QC), "DR"/"PX" | C0 7/7, 오답률 0. 카발란 DR 마데라 1줄 퇴보(번역이 DR 생략, "Madera") |
| r2 | v3: 에디션 단어 음차·철자 교정, 약어 빼지 않기, 라인업 예시(eval에 없는 단어) | 그대로. + M3b | Machrie Moor, 카발란 DR 마데라 | C1 (c) 4. 되돌림 규칙 미발동. M3b 효과 0 |
- 규칙 추가(r1)는 엄격 방향만이고 사전 등록 절에 기록 후 실행(`0d90655`). 되돌림 규칙도 r2 전에 등록

### 사람 결정
- 결과 적용은 "대체"가 아니라 "합치기"(대체는 비교용 숫자만). 수락 시 오답률은 C0·C1 둘 다
- 병입사 목록은 P17 `IB_BOTTLERS` 그대로(추가 없음; Claude가 처음 넣은 Cadenhead는 뺌)
- `edition_mismatch`를 거부권으로 승격, 짧은 토큰은 빼지 않고 단어 일치, 중립 단어는 양쪽 근거 모두 아님
- C0 LLM 정밀도는 판정 기준 아님, 보고서 맨 위에 계속 표시

### AI가 정한 것 (사람 확인 필요)
- 번역→영문 이름 조립 순서(병입사 증류소 연수 에디션 / 브랜드 연수 에디션), 토큰 규칙의 일반 단어 목록, 확인 권장의 "규칙/LLM" 출처 구분(S1~S3가 이미 확인 권장한 상품에 LLM이 동의하면 규칙)
- 프롬프트 예시는 eval에 없는 상품(Glen Moray, Inchgower, Craigellachie, Tomintoul 등)으로 바꿈. 처음 초안에 eval과 겹치는 예시(Caol Ila 10 100 Proof, Balvenie DoubleWood, 납크릭/Dalwhinny)가 있었고 Claude가 발견해 호출 전에 교체
- 하네스: `burden_kind`에 "후보 여러 개 + 1순위 확인 권장" 분기 추가. 기존 매처 결과는 정답 2종 × 매처 5 × C0·C1 × dev·test 40조합에서 수정 전과 완전히 같음을 확인

### 검증
- pytest `ai/match_llm/` 25개(가짜 상품 거부권 테스트 포함) + `ai/eval/test_score.py` 통과
- r2 결과를 동결 코드로 캐시만 써서 재현(API 0회, 결과 동일)
- 캐시·결과 파일에 API 키 없음 확인(`.env` 값으로 grep 0건)

### 사용 중 있었던 문제
- Windows에서 Python `write_text`가 `eval_plan.md`를 CRLF로 바꿔 첫 사전 등록 커밋 diff가 파일 전체로 잡힘 → LF로 되돌리고 같은 커밋을 amend(push 전, 측정 전)
- Bash heredoc 안의 `'''`가 셸 파싱을 깨서 패치 스크립트 대신 Edit 도구로 수정

### 결과
- `ai/runs/2026-10-14_m3/README.md`: M3a 채택(dev), test 확인에서도 세 기준 만족(C1 (c) 171 → 41, LLM 확인 권장 193/194, 수락 시 오답률 C0 0.015·C1 0.002). C0 LLM 정밀도 7/9. M3b 채택 안 함

## 2026-10-14 · E2E (I2) 하이브리드 추출 → M3a 종단 매칭

- **도구:** Claude Code (Claude Opus 5.5), 데스크톱 앱 Code 탭. 외부 API: Gemini `gemini-3.5-flash-lite`(thinking medium) 61회(스모크 1, val 18, test 42), `gemini-3.1-flash-lite`(thinking low, M3a) 36회. CLOVA 새 호출 0(캐시만). 실행당 한도(3.5 80회, 3.1 60회) 안, 실패·재시도 0
- **브랜치:** `i2-m3-llm-match`(7731422)에서 `i2-e2e-hybrid`. PR 없음, push 안 함
- **시간(대략):** Claude 작업 약 1시간 30분 (기존 코드 파악 20분, 사전 등록·코드·테스트 30분, 실행 20분, 분석·보고서 20분). 담당자 검토 시간 별도
- **토큰(대략):** Claude Code 세션 약 30만 토큰. Gemini 3.5 입력 약 40만 / 출력 23만 / thought 19만, 3.1 입력 약 9.5만 / 출력 10만 / thought 1만

### 진행 순서
1. Claude가 P12(`ai/ocr/parse.py`, `lines.py`, 프롬프트 v3), E1(`extract.py`, 프롬프트 v2), M3(`m3.py`, `match_eval.py`) 코드를 읽고, match gold의 test split이 미라보·포레스트 10장(Beck은 dev)임을 확인
2. `ai/docs/e2e_plan.md`(지표·누락 감지 규칙·`source_lines` 판정 규칙·프롬프트 조정 규칙)와 `hybrid.py`, `hybrid_prompt_v1.md`, `e2e_match.py`, 테스트를 API 호출 전에 커밋(f77649c)
3. `e2e_match.py`에 라벨을 넣어 `test_m3a.json`과 숫자가 같은지 캐시만으로 확인(API 0회, Beck dev도 확인)
4. 스모크(복춘_03 1장) → val 9장 → test 14장 r1 → r2·r3 → 종단 매칭(세 추출 × test·Beck) → `e2e_report.py`로 표 숫자 → README

### AI가 정한 것 (사람 확인 필요)
- 추출 줄과 정답 줄 대응: score.py 짝짓기 + unit 무시 재짝(잔·병 혼동)도 짝으로 인정
- "종단 Top-1"(놓친 줄을 실패로 세는 Top-1)을 추가해 라벨 입력과 비교. 짝지어진 줄 Top-1은 놓친 줄이 빠져 착시가 생김
- 누락 감지의 "가격 같은 줄" 정규식과 표시 기준 max(4, 20%), `source_lines` 텍스트 판정 규칙(정답 근거 줄 라벨이 없어서)
- Beck은 match gold dev라 보조 표로만

### 검증
- pytest `ai/ocr/test_hybrid.py` 24개(가격 줄 판정, 누락 감지, 가짜 클라이언트로 요청 모양, 호출 한도, 프롬프트에 val·test 라벨 이름 없음) + 기존 `test_ocr.py` 통과
- test r1 1.000이 나와 채점 오류·누출을 의심해 확인: 입력 텍스트에 라벨 없음, 관대 일치 12건이 모두 CLOVA 오독·라벨 표기 차이, 항목 수가 라벨과 사진별로 일치
- Beck 결과가 세 추출 모두 같아 확인: 새 API 호출이 실제로 있었고(E1·CLOVA 각 4회), 영문 이름이라 결과가 같았음
- 결과·캐시 파일에 API 키 없음(`.env` 값으로 grep 0건)

### 사용 중 있었던 문제
- **프롬프트 v2 사고:** val v1 오류(복춘_04 칵테일 소제목)를 보고 v2를 만들 때, 파일을 복사한 뒤 Edit 도구가 "먼저 Read 필요"로 실패했는데 이어진 명령(커밋·val 실행)이 그대로 돌아 v1과 같은 내용으로 "v2" 실행 9회를 씀. SHA-256 비교로 발견. 그 실행에서 복춘_04가 맞아 오류가 간헐적임이 보였으므로, 조정 없이 v1으로 test를 돌리기로 함(되돌림 커밋 76c50fb, 실행 폴더는 `hybrid_val_v1_rerun` + NOTE.md)
- `source_lines` 이름 판정 초안이 이름 속 숫자(`SR 22`, `14.1`)를 가격으로 지워 0.948로 나옴 → 원문과 가격 제거본 중 하나라도 맞으면 통과로 고쳐 1.000(측정 규칙 구현 오류 수정, 사전 등록 정의는 그대로)
- pytest 기본 임시 폴더 권한 오류 → `--basetemp`를 스크래치 폴더로
- r2·r3 실행이 길어 셸이 백그라운드로 넘김(중단 아님)

### 결과
- `ai/runs/2026-10-14_e2e/README.md`: 하이브리드 test 0.995(3회, r1 1.000), E1 0.842, CLOVA+LLM 0.883. 종단 Top-1 하이브리드 C0 0.770 / C1 0.377(라벨과 같음, 놓친 줄 0), E1 0.733 / 0.366, CLOVA+LLM 0.726 / 0.331. 가격 근거 줄 인용 오류(r2 미라보_05 15건)와 누락 감지 오탐(비위스키 섹션)은 한계로 기록

## 2026-10-14 · A3 (I2) 카탈로그 v2와 수이·오드바 정답 라벨 (진행 중)

- **도구:** Claude Code (Claude Opus 5.5), 데스크톱 앱 Code 탭. 외부 API 호출 0회(Gemini·CLOVA 모두)
- **브랜치:** `i2-e2e-hybrid`(d3163c0)에서 `i2-catalog-v2`. 시작 전 `git merge-base --is-ancestor`로 `i2-m3-llm-match`, `i2-labels-v1-1`(로컬·origin 모두)이 포함된 것을 확인. 단계별 커밋 후 브랜치로만 push
- **시간(대략, 여기까지):** Claude 작업 약 40분 (기존 카탈로그·정답 구조 파악 15분, 동결 기록 10분, 빌드·검증 스크립트 15분)
- **토큰(대략, 여기까지):** Claude Code 세션 약 15만 토큰

### 진행 순서
1. 0단계: 동결 대상(매처 `backend/app/matching/`, `ai/match_llm/`·`match_eval.py`, 하이브리드 `hybrid.py`·`hybrid_prompt_v1.md`·`lines.py`)이 각 동결 커밋 이후 d3163c0까지 바뀌지 않았음을 `git diff --stat`으로 확인하고 `ai/docs/p47_plan.md` 커밋(69ff7aa)
2. 1단계: v1 생성 스크립트가 레포에 없어 id 규칙을 역산(`brand:`, `balias:<brand>:<text>`, `product:`, `palias:<product>:<text>`, `bar:`; v1 전체 id가 일치). `build_catalog_v2.py`, `check_catalog_v2.py`, `catalog_v2_draft.json` 커밋(b10b31b)
3. 2단계: `BOTTLEMAP_DATA_DIR`(미설정, 기본 `../bottlemap-p14/data`) 아래에 수이·오드바 사진이 없어 지시대로 멈춤

### AI가 정한 것 (사람 확인 필요)
- `jack-daniels-apple`(Tennessee Apple, 위스키 리큐어)를 비위스키로 보고 카탈로그에서 제외(정답 `new_products` 337 → 상품 336). 그 미라보 줄은 별칭을 만들지 않음
- held-out 바(미라보·Beck·포레스트)의 메뉴 표기 별칭을 새 상품뿐 아니라 v1 상품에도 추가(v1 상품 175건). 검수에서 "추정"으로 연결한 줄(예: Macallan 15yo → 15 Double Cask)도 별칭이 되므로 서비스에서 exact가 될 수 있음
- 메뉴 표기 `한글 / 영문`은 v1처럼 부분마다 별칭 하나. 괄호 병기(`글렌모렌지(Glenmorangie) 12년 오리지널`)는 인쇄 그대로 한 별칭
- 새 브랜드 key는 v1 형식(소문자, 영숫자 외 `_`)으로 만들고 별칭은 영문 표준명 하나(`standard`). 한글 브랜드 별칭은 만들지 않음
- 정답의 연수·에디션 값은 그대로 씀(예: Octomore는 v1처럼 `age_years` null)

### 검증
- `check_catalog_v2.py`를 v1에 돌려 README의 수치(상품 내 정규화 중복 127, 브랜드 14, 상품 간 충돌 0)가 재현되는지 확인
- v2 핵심: 상품 간·브랜드 간 정규화 별칭 충돌 0, FK·id 유일성 OK, key로 재생성한 id 동일. 정답이 참조하는 상품은 제외한 1개 외 모두 카탈로그에 있음
