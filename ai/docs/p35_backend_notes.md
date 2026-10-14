# P35: 하이브리드 추출을 백엔드 옵션으로 연결 — 작업 노트와 PR 초안

2026-10-15 야간 · 작성: Claude Code · 검토: 박진우, 해울(백엔드) · 브랜치 `i2-p35-hybrid-backend` (base `origin/i2-catalog-v2` `415e78f`)

**PR은 만들지 않았다.** 브랜치만 push했다. 아래 "PR 초안"을 진우·해울이 확인한 뒤 PR로 옮긴다. 실제 CLOVA·Gemini 호출은 하지 않았다(테스트는 mock·fixture만).

## 1. 무엇을 바꿨나

| 파일 | 내용 |
| --- | --- |
| `backend/app/extraction/clova.py` (새) | CLOVA General OCR V2 호출(표 감지 off, 긴 변 8,000px 이상이면 축소 전송, 429·5xx·네트워크 오류 재시도), 줄 재구성(`ai/ocr/lines.py`와 같은 규칙, gap 2.5), 0–1000 좌표 줄 표 |
| `backend/app/extraction/hybrid.py` (새) | `extract_menu_hybrid`: OCR 줄 + 사진 → Gemini. 요청은 `ai/ocr/hybrid.py`(E2E)와 같은 형식(머리말 + `<ocr_lines>` + 이미지, 응답 스키마 `HybridExtraction`). 결과 변환은 기존 `to_flow_items` 그대로 |
| `backend/app/extraction/hybrid_prompt_v1.md` (새) | `ai/ocr/hybrid_prompt_v1.md`의 동결 프롬프트 v1 복사본(바이트 동일, 테스트로 고정) |
| `backend/app/adapters/hybrid_extraction.py` (새) | `HybridMenuExtractor` (`approach = ocr_llm`). OCR 실패 시 `GeminiMenuExtractor`로 fallback, 경고 로그와 `raw_output.hybridFallback` 기록 |
| `backend/app/api/deps.py` | `MENU_EXTRACTOR=gemini`일 때 `EXTRACTION_MODE`(`gemini` 기본 \| `hybrid`)로 선택. 잘못된 값은 시작 시 오류 |
| `backend/app/extraction/convert.py` | 묶기 단계를 `group_items`로 분리(동작 같음). 하이브리드의 항목별 근거 줄 묶기에 재사용 |
| `backend/tests/test_hybrid_extraction_adapter.py` (새) | 30개 테스트 |
| `backend/.env.example`, `backend/README.md` | `EXTRACTION_MODE`, `CLOVA_OCR_INVOKE_URL`, `CLOVA_OCR_SECRET` |

**기본 동작은 바뀌지 않는다.** `EXTRACTION_MODE`가 없으면 지금과 같은 Gemini 단독 추출이고, `MENU_EXTRACTOR` 기본값도 그대로 `mock`이다.

### 모델 설정

하이브리드도 `EXTRACTION_MODEL`, `EXTRACTION_THINKING_LEVEL`을 그대로 쓴다. E2E 하이브리드 실험(`ai/docs/e2e_plan.md`)은 조건 A2(`gemini-3.5-flash-lite`, thinking `medium`)였고, 배포 예시 값과 같다. 다른 값을 넣으면 실험과 다른 설정이 된다.

### 실패 처리

| 단계 | 실패 | 처리 |
| --- | --- | --- |
| 이미지 확인 | JPEG/PNG 아님 | Gemini 단독과 같은 `UnsupportedImageError` (OCR 전) |
| CLOVA OCR | HTTP 오류, 재시도 소진, JSON 아님, `inferResult` ≠ SUCCESS, 잘못된 URL | **Gemini 단독으로 fallback**. `logger.warning("hybrid extraction: CLOVA OCR failed, falling back ...")`, `raw_output = {Gemini meta..., "hybridFallback": {"reason": ...}}`. 비밀값은 로그에 없음(테스트로 확인) |
| Gemini (OCR 성공 후) | 호출 실패, 잘못된 출력 | fallback 없이 실패 처리(Gemini 단독과 같은 `ExtractionError`). 실패 run의 `raw_output`에 OCR 줄 표가 남음 |
| 시작 시 | `EXTRACTION_MODE=hybrid`인데 CLOVA 변수 없음 | 서버 시작 실패(`MENU_EXTRACTOR=gemini with EXTRACTION_MODE=hybrid is not configured: ...`). 기존 Gemini 설정 검사와 같은 방식 |

## 2. OCR 줄 좌표(bbox) 저장 — 지금 한 것과 스키마 제안

**지금(스키마 변경 없음):** `extraction_runs.raw_output`(JSON, 이미 있음)에 넣는다.

```json
{
  "mode": "hybrid",
  "ocr": {"provider": "clova-general-v2", "tableDetection": false, "latencyMs": 900, "attempts": 1,
          "sentSize": [1000, 2000],
          "lines": [{"id": "L002", "box": [100, 100, 380, 120], "text": "페른홀로우 12년"}]},
  "itemSources": [{"itemOrder": 1, "nameLines": ["L002"], "priceLines": ["L003"], "box": [100, 100, 880, 120]}],
  "rawOutput": {"items": [{"raw_name": "...", "source_lines": {"name": ["L002"], "price": ["L003"]}}]}
}
```

- `box`는 사진(EXIF 회전 후 보낸 이미지) 가로·세로를 0–1000으로 본 좌표 `[x0, y0, x1, y1]`. 축소 전송 여부와 상관없이 같은 기준이다.
- `itemSources[].itemOrder`는 `extracted_items.item_order`와 같다(같은 묶기 함수 `group_items`). 모델이 지어낸 줄 번호는 버리고, 근거 줄이 없으면 `box: null`(사진에서만 읽은 줄).
- 업주 확인 화면은 지금도 run의 `raw_output`과 `item_order`로 상자를 찾아 사진을 자를 수 있다.

**제안(코드에 넣지 않음, 해울 영역):**

1. `extracted_items`에 `source_box` (JSON, null 허용; `[x0,y0,x1,y1]` 0–1000) 와 `source_line_ids` (text[] 또는 JSON) 추가. 알렘빅 마이그레이션 1개.
   - 대안: 4개 smallint 컬럼(`source_x0` …). 조회·검증은 쉽지만 컬럼이 늘어난다.
2. `app/adapters/extraction.py`의 `ExtractedItemData`에 `source_box: tuple[int, int, int, int] | None = None` 추가, `menu_import_processing`이 이 값을 새 컬럼에 쓴다. Gemini 단독·mock은 None.
3. 리뷰 API(`schemas/menu_review.py`)에 항목별 `sourceBox` 노출 → 안드로이드 업주 확인 화면에서 메뉴 줄을 잘라 보여줌.
4. 기존 run은 `raw_output.itemSources`에서 채울 수 있다(선택, 일회성 스크립트).

## 3. 검증

- 로컬: `backend/.venv` Python 3.12, `pytest` → **318 passed, 194 skipped**. 기존 288개 + 새 30개. 로컬에 PostgreSQL이 없어 DB 테스트 194개는 skip(`POSTGRES_TEST_DATABASE` 미설정). 바꾸기 전 기준도 288 passed, 194 skipped였다. **DB 테스트는 CI에서 확인해야 한다.**
- 커버리지: 새 파일(`clova.py`, `hybrid.py`, `hybrid_extraction.py`)과 바꾼 `deps.py`, `convert.py`는 로컬에서 100%(누락 줄 목록에 없음). 전체 72%는 DB 테스트 skip 때문이고, CI 기준 98%는 Postgres가 있는 CI에서만 판단된다.
- 실제 API 호출 없음: CLOVA는 `httpx.MockTransport`나 가짜 `call_ocr`, Gemini는 가짜 client(`gemini.make_client` 교체). 재시도 대기도 교체.
- 프롬프트: 백엔드 사본이 `ai/ocr/hybrid_prompt_v1.md`와 같은지 테스트(`test_frozen_prompt_is_the_e2e_prompt`). `.gitattributes`(`*.md eol=lf`)로 해시가 체크아웃과 무관.

## 4. 남은 일·확인할 것

- 실제 CLOVA·Gemini로 사진 1장 동작 확인(키 필요, 이번에는 금지라 안 함).
- 하이브리드는 사진당 CLOVA 1회가 추가된다. E2E 기록의 OCR 지연·비용을 배포 전에 다시 볼 것.
- CLOVA 동시 호출 제한: `ai/ocr/clova.py`는 한 번에 한 장씩 보냈다. 백엔드는 업로드마다 background job이라 동시에 여러 장이 들어오면 제한에 걸릴 수 있다(429 → 재시도 → 실패 시 Gemini 단독 fallback이라 서비스는 계속됨).
- 하이브리드 결과가 서비스 기본이 될지는 E2E 결과(`ai/runs/2026-10-14_e2e/README.md`)와 이 옵션의 실제 확인 후 결정.

## 5. PR 초안 (복사용)

**제목:** P35: Hybrid extraction (CLOVA OCR + Gemini) as an option behind EXTRACTION_MODE

**본문:**

Adds the hybrid extractor from the E2E experiment (`ai/ocr/hybrid.py`, frozen prompt v1) to the backend as an option. Default behavior is unchanged.

- `EXTRACTION_MODE=gemini` (default): the current Gemini-only extractor.
- `EXTRACTION_MODE=hybrid` (with `MENU_EXTRACTOR=gemini`): one CLOVA General OCR call (table detection off), then Gemini with the OCR lines and the photo (`app/extraction/hybrid_prompt_v1.md`, byte-identical to `ai/ocr/hybrid_prompt_v1.md`). `extraction_runs.approach = ocr_llm`.
- If CLOVA fails, the photo goes through the Gemini-only extractor; the fallback is logged and recorded as `raw_output.hybridFallback`.
- OCR line boxes (0-1000 of the image) and per-item source lines and union box are stored in `raw_output` (`ocr.lines`, `itemSources`). No schema change; a proposal for `extracted_items.source_box` is in `ai/docs/p35_backend_notes.md`.
- `convert.to_flow_items` now uses `group_items` (same behavior) so item sources line up with `item_order`.
- New settings: `EXTRACTION_MODE`, `CLOVA_OCR_INVOKE_URL`, `CLOVA_OCR_SECRET` (`.env.example`, README).

Tests: 30 new tests with an httpx MockTransport for CLOVA and a fake Gemini client; no real API call. Locally 318 passed, 194 DB tests skipped (no PostgreSQL); please check CI.

Not done: live check with real keys, DB column for the box (proposal only).

🤖 Generated with [Claude Code](https://claude.com/claude-code)
