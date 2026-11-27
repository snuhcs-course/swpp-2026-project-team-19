# I5-P19: OpenRouter 추출 PR 올리기 전 정리 (2026-11-27)

지시 문서: `../_outgoing/i5_p19_pr_prep_handoff.md`. 브랜치 `feature/i5-p19-openrouter-extraction`(작업 폴더 `swpp-p19-openrouter`). push하지 않았고 PR도 만들지 않았다.

## 요약

- **A (커밋):** 실행 기록 388개를 추적에서 뺐다(디스크에는 있음). 보고서 37곳에 보관 위치를 적었고 `.gitignore`에 이 폴더들의 기록 패턴을 넣었다. 테스트는 A 전후가 같다.
- **B (커밋):** 옆 페이지 줄 가드를 넣었다. 처음 규칙("옵션 0개")으로는 B.3에서 기대값과 달라 멈췄고(옆 페이지 줄 24개가 잔 표시만 있는 줄), 진우 결정으로 "가격 없는 위스키 줄"로 고친 뒤 **60/60, 0/7, 572/572, 그 밖 0**으로 기대값과 같다. 띠 너비는 바꾸지 않았다. 새 테스트 42개, 손댄 모듈 4개 커버리지 100%.
- **C (커밋):** `pr_draft.md`.
- **D (커밋):** Gemini 직접 호출 10회(13:34). `gemini-3.8-flash` 503 5/5, `gemini-3.5-flash-lite` 200 5/5.
- **F:** 히스토리 정리. 정리 전 상태는 `backup/i5-p19-before-rewrite`(push 금지). 이 브랜치의 모든 커밋에서 기록 388개를 걷어냈다. 커밋 17개의 순서·메시지·작성자·작성/커밋 날짜는 그대로이고, 최종 트리는 정리 전과 같다. 해시가 바뀌었고 표는 F절. 이 마지막 커밋에서 보고서와 `pr_draft.md`의 옛 해시를 새 해시로 고쳤다.
- 호출 수: **OpenRouter 0, CLOVA 0, Gemini 10**(D, 무료 키).
- push하지 않았고 PR도 만들지 않았다.

### 진우가 확인할 것

1. B.1의 적용 범위 판단: `MENU_EXTRACTOR=gemini`와 그 PDF에는 걸지 않았고, OpenRouter 경로의 PDF 스캔 페이지에는 걸었다.
2. D: 2단계(`gemini-3.8-flash`, 무료 키)가 낮에도 5/5 503이다. 15시·18시 측정을 이어 붙인 뒤에도 같으면 2단계를 그대로 둘지 정해야 한다.
3. C: `pr_draft.md`는 원본 초안 형식이라 PR 템플릿 절에 옮겨야 한다.
4. F: 백업 브랜치 `backup/i5-p19-before-rewrite`는 push하지 않는다.

## A. 실행 기록 파일을 PR에서 빼기

### A.1 한 일

- 이 브랜치가 `ai/runs/` 아래에 새로 추가한 파일 396개 중 `.md`가 아닌 **388개**(`.json` 372, `.log` 14, `.jsonl` 1, `.txt` 1)를 `git rm --cached`로 추적에서만 뺐다. **디스크의 파일은 그대로 있다**(B.3이 이 파일을 읽었다).
- 남긴 것: `.md` 8개(보고서·사전 등록·표), `ai/eval/*.py`, 테스트.
- 뺀 파일을 읽는 테스트는 없었다. 새 테스트(`ai/eval/test_i5_fallback_ladder.py`, `backend/tests/test_*` 6개)는 모두 가짜 데이터를 쓴다. 그래서 `tests/fixtures`로 옮긴 것은 없다.
- 보고서 5개에서 뺀 파일을 가리키는 37곳에 "(기록은 커밋하지 않고 진우 PC에 보관)"을 붙였다. 표의 줄은 마지막 칸에, 문장은 끝에 붙였다. 사전 등록 문서(`2026-11-25_i5_fallback_ladder/preregistration.md`)의 2곳은 나중에 붙인 것임을 알 수 있게 "11/27 추가:"로 시작한다. 보고서의 숫자는 고치지 않았다.

| 보고서 | 붙인 곳 |
|---|---|
| `2026-11-21_i5_row_pairing/report.md` | 25 |
| `2026-11-25_i5_fallback_ladder/preregistration.md` | 2 |
| `2026-11-25_i5_p19_server_route/report.md` | 4 |
| `2026-11-26_i5_a2_p43/report.md` | 1 |
| `2026-11-26_i5_p19_followup/report.md` | 5 |

다른(이미 main에 있는) 실행 폴더를 가리키는 문장(`ai/runs/2026-11-17_p46/...`, `ai/runs/2026-10-14_e2e/...`)에는 붙이지 않았다. 그 기록은 커밋돼 있다.

### A.2 `.gitignore`

넣었다. 이 브랜치의 실행 폴더 5개와 오늘 폴더(`2026-11-27_i5_pr_prep`)에 대해 `.json`, `.jsonl`, `.log`, `.txt`를 무시한다. 폴더 이름을 하나씩 적었다.

- 이유: 이 폴더들의 기록은 디스크에 그대로 있으므로, `git add ai/runs`를 한 번만 해도 388개가 다시 올라간다.
- 와일드카드(`2026-11-2*_i5_*`)를 쓰지 않은 이유: 다른 브랜치의 실행 폴더(예: 메인 클론의 `2026-11-21_i5_not_whisky`, 아직 추적 안 된 기록)까지 무시하게 된다. 그 브랜치에서 기록을 커밋할지는 그 작업에서 정할 일이다.
- 이미 커밋된 다른 실행 폴더(`2026-11-17_p46` 등)는 영향이 없다. 확인: `git check-ignore`로 `2026-11-17_p46/match/x.json`은 무시되지 않고, `2026-11-26_i5_p19_followup/edge_guard.json`은 무시되고, `report.md`는 무시되지 않는다.

### A.3 확인

- `git diff --stat origin/main...HEAD -- ai/runs`: A 커밋 뒤 `.md` 8개만 남는다(아래 "확인 결과"의 명령 출력).
- 테스트는 A 전후가 같다.

| | A 전 | A 후 |
|---|---|---|
| AI (`pytest ai`) | 394 통과, 1 실패 | 394 통과, 1 실패 |
| 백엔드 (`backend`, `pytest`) | 1386 통과, 1940 건너뜀 | 1386 통과, 1940 건너뜀 |

- AI의 1 실패는 `test_p30_extract.py::test_reencoded_ocr_cache_without_provenance_stops`로, Windows의 경로 구분자 때문에 11/21부터 이 PC에서만 실패한다(이번 변경과 무관).
- 백엔드의 1940 건너뜀은 이 PC에 테스트 DB(`POSTGRES_TEST_DATABASE`)가 없어서 DB 테스트가 빠진 것이다. CI는 DB를 붙여 전부 돌린다. `test_pdf_extraction.py`의 5개는 테스트 이름에 PDF 바이트가 들어가 Windows 환경변수 길이 제한에 걸리므로 빼고 돌렸다(11/26 보고서 G.7과 같다). PDF 테스트에 필요한 `pypdfium2`는 11/26에 임시 폴더에 설치한 것을 `PYTHONPATH`로 썼다(venv는 건드리지 않았다).

## B. 옆 페이지 줄 가드

### B.0 규칙을 고친 경위

처음에는 지시 문서 B.2의 첫 문장("가격·용량·잔병 표시가 모두 없는 줄(옵션 0개)")대로 구현했고, B.3에서 기대값과 달라 멈췄다(12:40). 옆 페이지 줄 60개 중 24개(3.8 Flash 11/21 `011_mirabeau_03_r1`의 12줄, 3.7 Flash 11/25 `r3`의 12줄)와 진짜 줄 2개(3.7 Flash `014_tale_07_r2`의 Ardbeg 2줄)는 모델이 가격·용량 없이 `unit: "glass"`만 붙였고, 서버 변환(`convert._flow_item`)이 이것을 옵션 1개(`잔`, 가격 없음)로 만들어 규칙에 걸리지 않았다. 그때의 결과는 옆 페이지 36/36(60줄 중 24줄은 대상 밖), 진짜 줄 0/5였다.

**진우 결정(11/27):** 규칙은 "가격이 없는 위스키 줄"로 통일한다. 잔/병 표시나 용량이 있어도 가격이 없으면 대상이다. 상자 조건과 띠 너비(10%)는 그대로다. 지시 문서 B.2의 두 문장도 이 정의로 고쳤다.

### B.1 규칙과 넣은 곳

**가격이 없는 위스키 줄(어느 옵션에도 `priceKrw`가 없는 줄, 옵션이 없는 줄 포함) 중에서, 이름 줄의 OCR 상자 전체가 좌우 끝 띠 안(왼쪽 x ≥ 1000 − 띠, 또는 오른쪽 x ≤ 띠)이면 버린다.** 띠 기본값은 100이다.

| 파일 | 내용 |
|---|---|
| `backend/app/extraction/edge_guard.py` (새 파일) | `drop_edge_rows(items, meta, strip_permille)`. 상자는 **이름 줄만**으로 만든다(가격 줄은 넣지 않는다). 버린 줄은 `raw_output.droppedEdgeRows`(원래 순번, menuOrder, 이름, 이름 줄, 상자)에, 띠는 `raw_output.edgeStripPermille`에 남는다. 남은 줄은 1부터 다시 번호를 매기고 `itemSources`도 같이 바꾼다. 사진당 로그 한 줄 `extraction edge guard dropped=N strip_permille=S`(버린 게 있으면 WARNING, 없으면 INFO. 서비스 로그는 WARNING 이상만 보이므로 버린 사진만 보인다) |
| 설정 `EXTRACTION_EDGE_STRIP_PERMILLE` | 기본 100, 0이면 끔. 0~499의 정수가 아니면 `ExtractionConfigError`이고, 다른 설정처럼 서버 시작 때 `MENU_EXTRACTOR=openrouter is not configured: ...`로 멈춘다 (`routed.load_route_settings` → `RouteSettings.edge_strip_permille`) |
| `backend/app/adapters/openrouter_extraction.py` | `extract_with`: `extract_menu_routed`의 결과(서버 변환 뒤) → 가드 → `in_menu_order` → 저장·매칭. 0~3단계(OpenRouter, 대체 모델, Gemini 직접, flash-lite)가 모두 이 한 곳을 지난다. `edge_guard=False` 인자 추가 |
| `backend/app/adapters/pdf_routed_extraction.py` | 글자 층 페이지는 `edge_guard=False`. 스캔 페이지는 사진과 같은 `extract`를 타므로 가드가 걸린다 |
| `backend/.env.example`, `deploy/env.production.example`, `README.md`, `DEPLOY.md` | 설정, 로그, `droppedEdgeRows` 찾는 법 |
| `ai/eval/i5_edge_guard_check.py` | 서버의 `convert_output`과 `drop_edge_rows`를 그대로 불러 기록에 대 본다. 기대값과 다르면 종료 코드 1 |

적용 범위를 정한 이유(지시 문서 B.2의 "판단해서 적는다"):

- `MENU_EXTRACTOR=gemini`(HybridMenuExtractor)에는 **걸지 않았다.** 이 경로는 바꾸지 않고 "돌아갈 길"로 둔다는 것이 P19의 원칙이고(`openrouter_extraction.py` 머리말), 기본 프롬프트가 v1이라 근거로 쓴 기록(전부 v2.1)과 출력이 다르다. 같은 이유로 `MENU_EXTRACTOR=gemini`의 PDF(`PdfMenuExtractor`)에도 걸지 않았다.
- PDF는 `MENU_EXTRACTOR=openrouter`의 **스캔 페이지에만** 건다. 스캔 페이지는 사진과 똑같이 CLOVA를 거쳐 같은 경로를 타고, 펼친 책을 스캔하면 옆 페이지가 찍힐 수 있다. 글자 층 페이지는 지시대로 걸지 않는다(글자 층에는 그 페이지의 줄만 있다).
- CLOVA가 실패해 Gemini 단독으로 읽은 사진은 OCR 상자가 없으므로 아무것도 버리지 않는다("상자 없는 줄은 남긴다").
- 위스키가 아닌 줄(`otherItems`)은 보지 않는다.
- API 스펙, DB 스키마, 화면은 바꾸지 않았다. 버린 줄은 검수 화면에 나오지 않을 뿐이고 응답 형식은 같다.

### B.2 B.3 확인 결과: 기대값과 같다

`python ai/eval/i5_edge_guard_check.py --out ai/runs/2026-11-27_i5_pr_prep/edge_guard_check.json` (API 0회, 종료 코드 0, 출력은 같은 폴더 `edge_guard_check_stdout.txt`. 기록은 커밋하지 않고 진우 PC에 보관)

| | 기대 | 결과 |
|---|---|---|
| 옆 페이지 줄 중 버려짐 | 60 / 60 | **60 / 60** |
| 정답에 있는 줄 중 버려짐 | 0 / 7 | **0 / 7** |
| 회귀 17장 (3.8 Flash 서버 코드 기록) 채점 | 572 / 572 그대로 | **572 / 572** (가드 전후 같음: 틀림·누락·이름만 실패·남는 행 0) |
| 그 밖에 버려지는 줄 | 0 | **0** |

| 기록 묶음 | 기록 | 위스키 행 (모델) | 위스키 줄 (서버 변환) | 가격 없는 줄 | 옆 페이지 | 정답에 있음 |
|---|---|---|---|---|---|---|
| 3.8 Flash, 평가 스크립트 (11/21) | 20 | 732 | 621 | 12 | 12 | 0 |
| 3.8 Flash, 서버 코드 (11/25) | 17 | 572 | 461 | 0 | 0 | 0 |
| 3.8 Flash, 동시 호출 (11/26) | 6 | 135 | 119 | 0 | 0 | 0 |
| Sonnet 5.5, 회귀 17장 (11/26) | 17 | 568 | 457 | 0 | 0 | 0 |
| 3.7 Flash, 6장 (11/25) | 18 | 1,002 | 762 | 18 | 12 | 6 |
| GPT-6.1 Terra, 6장 (11/25) | 18 | 1,026 | 786 | 36 | 36 | 0 |
| Sonnet 5.5, 6장 (11/25) | 18 | 989 | 750 | 1 | 0 | 1 |
| 합 | **114** | **5,024** | 3,956 | 67 | 60 | 7 |

("위스키 줄"은 잔 행과 병 행을 한 줄로 묶은 수다.)

버려진 60줄의 이름 상자 왼쪽 x는 905, 943, 958로 모두 오른쪽 10% 안이다. 남은 진짜 줄 7개의 상자는 (0~169) Ardbeg Corrybreckan ×3, (1~142) Ardbeg Anthology ×3, (553~623) 아란 10Y ×1이다(지시 문서 B.1 표와 같다).

띠 너비별(참고용. 너비는 바꾸지 않았다):

| 띠 너비 | 옆 페이지 줄 중 버려짐 | 정답에 있는 줄 중 버려짐 |
|---|---|---|
| 0 (끔) | 0 / 60 | 0 / 7 |
| 50 | 25 / 60 | 0 / 7 |
| **100 (기본값)** | **60 / 60** | **0 / 7** |
| 150 | 60 / 60 | 3 / 7 (Ardbeg Anthology ×3) |
| 200 | 60 / 60 | 6 / 7 |

### B.3 테스트

`backend/tests/test_edge_guard.py` 42개. fixture `backend/tests/fixtures/edge_guard_rows.json`: 위 67줄의 이름, 이름 상자, 종류만(메뉴 줄 전체나 OCR 표는 옮기지 않았다).

- 67줄에서 60줄이 버려지고 7줄이 남는다. 같은 67줄에 잔 표시만 붙여도 같다. 띠 150이면 Ardbeg Anthology가 걸리기 시작한다.
- 남는 것: 띠 안이라도 가격이 있는 줄(옵션 하나에만 가격이 있어도, 가격 0원도), 이름 줄이 없는 줄, `itemSources` 항목이 없는 줄, OCR 표가 없는 meta, 띠 0.
- 버리는 것: 띠 안의 가격 없는 줄은 옵션이 없어도, 잔·병 표시만 있어도, 용량만 있어도.
- 상자는 이름 줄로만 만든다(가운데의 가격 줄이 상자를 넓히지 않는다). 띠 경계(900, 100 포함)와 양쪽 끝에 다 닿는 상자.
- 기록: `droppedEdgeRows`의 내용, 남은 줄과 `itemSources`의 새 번호, `menuOrder`·`otherItems`·`route`가 그대로인지, 입력을 바꾸지 않는지. 로그 한 줄(WARNING/INFO).
- 설정: 기본 100, 0, 150, 499, 잘못된 값(-1, 500, 1000, `10%`, `0.1`) 거절, 서버 시작 때 멈춤.
- 넣은 곳: 0~3단계 모두, 띠는 `RouteSettings`에서, `extract_with(edge_guard=False)`, PDF 스캔 페이지는 걸리고 글자 층 페이지는 안 걸림.

커버리지(분기 포함): `edge_guard.py`, `routed.py`, `openrouter_extraction.py`, `pdf_routed_extraction.py` 모두 **100%**.

| | B 전 (A 후) | B 후 |
|---|---|---|
| 백엔드 | 1386 통과, 1940 건너뜀 | **1428 통과** (새 테스트 42), 1940 건너뜀, 실패 0 |
| AI | 394 통과, 1 실패 | 394 통과, 1 실패 (같은 Windows 전용 실패) |

### B.4 한계 (B.5)

- 옆 페이지 줄이 나온 사진은 미라보_03 **한 장뿐**이다. 10%는 그 한 장에서 나온 값이다. 다른 메뉴판의 옆 페이지가 어디에 걸리는지는 모른다.
- 띠를 15%로 넓히면 진짜 줄 3개(tale_07의 Ardbeg Anthology, 3.7 Flash 3회)가 걸리기 시작한다. 여유가 넓지 않다.
- 가격을 못 읽은 진짜 줄이 사진의 좌우 10% 안에만 있으면 같이 버려진다(지금 기록에는 없다). 업주에게는 그 줄이 검수 화면에 안 보인다.
- 알파에서 버려진 줄이 나오면 `extraction_runs.raw_output.droppedEdgeRows`로 확인한다. 서비스 로그는 `journalctl -u bottlemap-api | grep "extraction edge guard"`(버린 사진만 WARNING으로 보인다).

## C. PR 본문 초안

`ai/runs/2026-11-27_i5_pr_prep/pr_draft.md`. 원본 `../_outgoing/i5_p19_pr_description_EN.md`는 그대로 두었다.

- 맨 위 "Decide before pushing" 메모를 지우고 "Run records are not committed; reports only."로 바꿨다(히스토리에서도 뺐다는 문장 포함, F).
- Summary와 Route 절에 옆 페이지 줄 가드 한 줄씩, Evidence 표에 가드 한 줄(60/60, 0/7, 572/572, 한계 한 문장)과 D의 결과 한 줄.
- 테스트 수: 백엔드 1,428 통과(옛 초안 1,242), AI 394 통과·1 실패(Windows 전용), `test_edge_guard.py` 42개 추가.
- "Not verified"의 stage 2 문장을 D 결과로 바꾸고, Deploy에 `EXTRACTION_EDGE_STRIP_PERMILLE`(선택)을 넣었다. 보고서 목록에 이 보고서를 넣었다.
- 커밋 수(18)와 이 브랜치의 해시(`afe127c0` → `e2fa7874`)는 히스토리 정리 뒤 새 값으로 고쳤다(F).
- 끝줄 `🤖 Generated with [Claude Code](https://claude.com/claude-code)`는 그대로다.
- PR 템플릿(`.github/pull_request_template.md`)의 절 이름과는 아직 다르다(원본 초안 형식 그대로). 올릴 때 템플릿에 옮겨야 한다.

## D. Gemini 직접 호출 확인

`ai/runs/2026-11-27_direct_probe.md` (명령은 파일 맨 위), 스크립트 `ai/eval/i5_direct_probe.py`. 서버와 같은 SDK 클라이언트(`gemini.make_client`, SDK 재시도 끔), Interactions API, thinking `medium`, `store=False`, 호출마다 1회(재시도 없음). 두 모델을 번갈아 10초 간격으로 5번씩, **Gemini 호출 10회**(무료 키).

| 시각 (KST) | 모델 | 결과 | 걸린 시간 |
|---|---|---|---|
| 13:33:45 ~ 13:37:12 | `gemini-3.8-flash` (2단계) | **503 5/5** "currently experiencing high demand" | 30.5~30.9초 (매번 약 31초 뒤에 503) |
| 13:34:26 ~ 13:37:53 | `gemini-3.5-flash-lite` (3단계) | 200 5/5 ("네", "알겠습니다.") | 1.1~1.5초 |

- 11/26 17~18시(3/3 503)에 이어 낮 13시에도 2단계는 5/5 503이다. 이 측정으로는 시간대 문제라고 볼 근거가 없다. 15시·18시 측정을 이어 붙이면 판단할 수 있다.
- 503이 매번 약 31초 걸린다. 서버 설정(`EXTRACTION_DIRECT_MAX_ATTEMPTS=2`, 대기 5초)이면 OpenRouter가 실패한 사진 하나가 3단계로 가기 전에 2단계에서 1분 넘게 쓴다(계산값, 실측 아님).
- 3단계는 정상이다.
- 출력 파일에 키 값이 없는 것을 확인했다(키 문자열 검색 0건).

## F. 히스토리 정리 (진우 요청)

### F.1 한 일

1. 정리 전 상태를 `backup/i5-p19-before-rewrite`(`344b42f5`)로 남겼다. **push하지 않는다.**
2. `git filter-branch --index-filter "git rm --cached --ignore-unmatch --pathspec-from-file=<목록>" -- origin/main..HEAD`. 목록은 A에서 뺀 것과 같은 388개 경로다. 이 브랜치의 커밋들이 `ai/runs/` 아래에 추가한 `.md`가 아닌 파일 전부이고, 그중 `origin/main`에 있는 것은 0개다.
   - 범위는 `origin/main..HEAD`(17개)뿐이다. 바탕 커밋 `54a0bf26`과 main의 커밋은 건드리지 않았다.
   - 커밋을 합치거나 빼지 않았다(`--prune-empty` 안 씀). 빈 커밋이 된 것도 없다.
   - filter-branch가 만드는 `refs/original/...`은 백업 브랜치와 같은 커밋이라 지웠다.
3. 디스크의 기록 파일은 그대로다(예: `2026-11-26_i5_p19_followup/edge_guard.json`).

### F.2 확인

| 확인 | 결과 |
|---|---|
| `git log --name-only origin/main..HEAD -- ai/runs`에서 `.md`가 아닌 파일 | **0개** |
| 17개 커밋 각각의 트리에 388개 경로 중 하나라도 있는지 | **0** |
| `git diff backup/i5-p19-before-rewrite HEAD` | **비어 있음** (0줄) |
| 커밋 순서, 작성자, 작성 날짜, 커밋 날짜, 제목 (`git log --format='%an|%ad|%cd|%s'`) | 정리 전과 **같음** |
| 커밋 메시지 본문 전체 | 정리 전과 **같음** (md5 같음) |
| 테스트 (정리 뒤) | 백엔드 1428 통과·1940 건너뜀·실패 0, AI 394 통과·1 실패(Windows 전용, 전과 같음) |

- 통과 기준을 호출 전에 커밋한 순서도 그대로 남았다. P18의 "Fix the photos, condition and pass criterion ... before any call"(`e2fa7874`)이 "Run the fallback model ladder (54 calls)"(`ff17f6b4`)보다 앞이다.
- A 커밋(`41d43982`)은 이제 388개를 지우는 변경이 없다(처음부터 없었으므로). `.gitignore`와 보고서 표시만 남았다. 메시지는 지시대로 바꾸지 않아서 "git rm --cached"라는 설명이 그대로 있다.
- 바꿀 수 없어서 남은 옛 해시: P18 사다리 실행 커밋(`ff17f6b4`)의 메시지 본문에 `afe127c0`이 있다(메시지는 그대로 둔다). 새 해시는 `e2fa7874`다.

### F.3 옛 해시 → 새 해시

| # | 옛 해시 | 새 해시 | 제목 |
|---|---|---|---|
| 1 | `63148315` | `79895cc1` | I5: Bring the 2026-11-21 model ladder, its records and hybrid prompt v2.1 to this branch |
| 2 | `afe127c0` | `e2fa7874` | I5-P18: Fix the photos, condition and pass criterion of the fallback model ladder before any call |
| 3 | `48bc012f` | `ff17f6b4` | I5-P18: Run the fallback model ladder (54 calls) and report it as section 11 |
| 4 | `70db01e2` | `d8ee22fb` | I5-P18: Record the decision to put claude-sonnet-5.5 in the fallback models array |
| 5 | `10b5156e` | `0118b03f` | I5-P19: Add menu extraction through OpenRouter with a fallback ladder to the Gemini API |
| 6 | `439aa0be` | `dd8b1002` | I5-P19: Run the 17 regression photos through the server's OpenRouter route and report the comparison |
| 7 | `e825ec5a` | `828a03d4` | I5-A2: Limit the menu photos one user may upload per day (30 by default) |
| 8 | `51f54d30` | `10fc50cf` | I5-P43: Check that menu imports processed at the same time do not hold each other up |
| 9 | `4857da3e` | `71bba5d7` | I5-P43: Run three imports at the same time through the server's extraction code with real calls |
| 10 | `48170149` | `e75a93b8` | I5-P19: Correct the key assumption: one course-issued OpenRouter key, no key limit |
| 11 | `1bed96e4` | `4ed72b54` | I5-P19: Add a server-wide daily limit on photos read through OpenRouter that survives a restart |
| 12 | `27936f76` | `ab03b417` | I5-P19: Let PDF pages take the OpenRouter route ladder and count against the same limits |
| 13 | `2c63ba1e` | `c548907c` | I5-P19: Report the follow-up checks: credits, real calls per stage, Sonnet on 17 photos, edge guard, PDFs |
| 14 | `d8b589d8` | `59b390a1` | I5-P19: Record the decision to keep claude-sonnet-5.5 in the fallback models array |
| 15 | `0d08d2e0` | `41d43982` | I5-P19: Stop tracking the run records of this branch; keep the reports only |
| 16 | `5d830205` | `26952b6f` | I5-P19: Drop whisky lines of a facing page cut off at the photo's left or right edge |
| 17 | `344b42f5` | `392a77a5` | I5-P19: Draft the PR description and probe the Gemini API routes directly |
| 18 | – | (이 커밋) | I5-P19: Point the reports at the rewritten commit hashes |

보고서에서 고친 곳: `2026-11-21_i5_row_pairing/report.md`(`afe127c0` → `e2fa7874`), `2026-11-25_i5_p19_server_route/report.md`(`10b5156e` → `0118b03f`), `2026-11-26_i5_a2_p43/report.md`(`e825ec5a` → `828a03d4`), `2026-11-26_i5_p19_followup/report.md`(`48170149` → `e75a93b8`), `pr_draft.md`(`afe127c0` → `e2fa7874`). 이 보고서는 위 표와 F.1의 `344b42f5`(백업)만 옛 해시로 적는다.

## AI 사용 내역

Claude Code(Opus 5.5)가 한 일: 기록 파일 목록 뽑기와 추적 해제, 보고서 37곳 표시, `.gitignore`, 가드 코드와 테스트 42개·fixture, 설정 문서, 확인 스크립트 고치기와 실행, 첫 규칙의 불일치 원인 진단(모델 기록에서 가격 없는 위스키 행의 unit 확인), PR 초안, 직접 호출 스크립트와 실행, 히스토리 정리와 확인, 이 보고서.
사람이 정한 것(진우): 가드 규칙을 "가격 없는 위스키 줄"로(B.0), 히스토리 정리.
검증: A·B·F 전후 테스트 수 비교, 손댄 모듈 커버리지, `git diff --stat`, `git check-ignore`, 확인 스크립트가 지시 문서의 기록 수(114)·행 수(5,024)·상자 값과 같은 값을 내는지, 직접 호출 출력에 키가 없는지, 정리 전후 트리·메타데이터 비교.
호출: OpenRouter 0, CLOVA 0, Gemini 10(D). 약 2시간 30분.

## H. Sonnet 복춘_03 재확인

11/26 Sonnet 5.5 회귀 17장 실행(row_pairing 보고서 12절, 후속 보고서 E절)에서 복춘_03의 병 가격 6칸이 모두 1/10이었다. 1회 결과였으므로, 같은 사진을 같은 조건으로 3번 더 읽혀 매번 나는지 본다.

### H.1 조건과 판정 기준 (첫 호출 전에 커밋)

- 사진: `007_bokchun_03` 한 장. 정답은 회귀 fixture의 16칸(잔 10, 병 6).
- 요청: 11/26 기록을 만든 함수 그대로. `i5_model_ladder` stage 3(`anthropic/claude-sonnet-5.5`, OpenRouter, `reasoning.effort` medium), 조건 B(사진 + OCR 줄, 저장된 CLOVA 캐시 재생, CLOVA 호출 0회), 프롬프트 v2.1, `max_tokens` 48000. 실행 전에 프롬프트 sha256(`b14b09b4…`), 준비된 사진 sha256(`427f3c12…`), OCR 줄 수(44)가 11/26 기록과 같은지 확인한다(`--check`에서 같음을 확인했다).
- 3회(r2, r3, r4), **재시도 없음.** 답이 없거나 형식이 틀린 호출도 다시 하지 않고 그대로 기록한다.
- 비용: 3회 합 상한 $0.5. 호출 전마다 "지금까지 + $0.15"가 상한 안이어야 하고, $0.15를 넘은 호출이 있으면 멈춘다. ($0.15는 11/26 이 사진 호출 $0.039의 약 4배다. 48,000 토큰 상한까지 다 쓰면 한 번에 약 $0.54가 될 수 있지만, 11/26 Sonnet 17회 중 가장 비싼 호출은 $0.088이었다.)
- 채점: `i5_model_ladder.score_rows`(11/26과 같은 함수). 이 함수로 11/26 r1을 다시 채점하면 10 / 6 / 0(맞음/틀림/누락)으로 보고서 12절과 같다.
- **판정:** 새 3회 중 "병 가격 6칸이 모두 정답의 1/10"인 회차 수를 센다.
  - 3회 → "이 사진에서 재현되는 약점"
  - 0회 → "11/26은 한 번의 결과"
  - 1~2회 → "흔들림"
  - 6칸 중 일부만 1/10인 회차는 세지 않고 칸 수를 따로 적는다. 답이 없거나 형식이 틀린 회차가 있으면 판정하지 않고 그대로 보고한다.
- 결과를 보고 기준이나 횟수를 바꾸지 않는다.
- 스크립트: `ai/eval/i5_sonnet_bokchun03_repeat.py`. 기록은 `ai/runs/2026-11-27_i5_pr_prep/sonnet_bokchun03/`(커밋하지 않고 진우 PC에 보관).
