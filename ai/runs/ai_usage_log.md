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
