# Testing documentation — AI 영역 (초안)

> **가이드라인 대조 필요.** 과목의 Testing documentation 가이드라인 문서가 레포에 없어서 일반적인 wiki 테스트 문서 형식으로 썼다. 제출 전에 과목 가이드라인의 필수 항목·형식과 맞춰야 한다.

2026-10-15 · 작성: Claude Code (야간 작업) · 검토: 박진우 · 근거: `ai/docs/results_ledger.md`와 각 실험의 원본 문서

BottleMap의 AI 부분(메뉴판 추출, 상품 매칭, Naver 별칭 후보)을 어떻게 시험하는지 정리한다. 두 층으로 나뉜다.

1. **평가(evaluation):** 정답 데이터에 대해 모델·규칙의 성능을 재는 실험. 사전 등록한 지표와 판정 규칙으로 판단한다.
2. **단위 테스트(unit test):** 코드가 정해진 대로 동작하는지 확인. API를 부르지 않는 fixture·mock 기반이다.

---

## 1. 평가 방법

### 1.1 데이터 분할

| 셋 | 바 | 용도 | 비고 |
|---|---|---|---|
| I1 평가셋 → **val** | 위스키복춘, 서로상 | I1 판정(P14), I2부터 프롬프트 개발용 val | 이 두 바 메뉴로 카탈로그·별칭과 프롬프트를 만들었으므로 I2부터 test로 쓰지 않는다 |
| **test** (추출) | 미라보, Beck, 포레스트 | P11·P12·E2E 추출 평가 | 14장 575항목 |
| **dev** (매칭) | 위스키복춘, 서로상, Beck | P22·M3·M4 조정 | 13장 177줄 |
| **test** (매칭) | 미라보, 포레스트 | P22·M3 동결 후 1회 | 10장 478줄 |
| **P47 최종** | 수이, 오드비 | 최종 평가 전용 | 동결 기록(`ai/docs/p47_plan.md`) 뒤 라벨링. 그 전에는 열지도, 실행하지도 않는다 |
| Naver 표본 | `eval/naver_sample_v1.json` | P28 | new 상품에서 층별(독립병입 20, 정규품 20) seed 고정 추출. 다른 작업보다 먼저 커밋 |

- 정답 파일: 추출 `eval/labels_v1.json`(I1, SHA-256 고정), `eval/labels_heldout_v1.json`, v1.1(인쇄 표기, `eval/labels_changelog.md`); 매칭 `eval/match_gold_v1.json`, `eval/match_gold_v1_1.json`.
- 라벨 규칙: `ai/docs/labeling_guideline_v2.1.md` → `v2.2` → `v2.3`(OCR 대조 후 검수).
- 매칭은 카탈로그 조건을 둘로 본다: **C0** = 카탈로그 그대로(정답 상품이 없는 줄이 많아 false merge 시험), **C1** = C0 + 그 분할 정답의 new 상품(영문 표준명 별칭 1개; "상품은 DB에 있고 이 메뉴 표기만 새로움"). 바마다 그 바 메뉴에서만 나온 별칭은 뺀다.

### 1.2 사전 등록

모든 실험은 **실행 전에** 지표·판정 규칙을 문서에 적고 커밋한다. 결과를 본 뒤 판정 기준을 바꾸지 않는다.

| 실험 | 사전 등록 문서 |
|---|---|
| P14 / I1 | `ai/docs/experiment_p14.md`, `ai/docs/eval_plan.md` |
| P11 | `ai/docs/eval_plan.md` 데이터 분할 절 |
| P22 | `ai/docs/eval_plan.md` 매칭 평가 절 (test 전 최종 등록, 동결 커밋 `69879fd`) |
| P12 | `ai/docs/p12_plan.md` (`d686997`) |
| M3 | `ai/docs/eval_plan.md` M3 사전 등록 절 (동결 `1ace927`) |
| E2E | `ai/docs/e2e_plan.md` (`f77649c`) |
| P28 | `ai/docs/naver_plan.md` 7절, `ai/docs/p28_plan.md` (`8b4a9a7`) |
| M4 | `ai/docs/m4_plan.md` (`07e556c`) |

공통 규칙:
- dev(val)에서만 조정하고, test는 동결 커밋에서 등록한 명령으로 한 번 돌린다. test 결과로 규칙을 바꾸지 않는다.
- dev 결과를 보고 규칙을 바꿀 때는 **엄격한 방향(후보를 버리거나 확인 권장을 막는 쪽)만** 허용하고 기록한다(예: M3 `edition_mismatch` 추가).
- 프롬프트 수정 횟수에 상한을 둔다(M3 2회, E2E 1회, M4 2회). 마지막 회차를 최종으로 한다.
- LLM 호출은 실행마다 상한을 두고(M3·M4 200회), 응답을 캐시해 API 없이 재채점할 수 있게 한다(`--cache-only`).
- 사후 진단(예: P11 "제목 규칙 무관" 0.949)은 판정에 쓰지 않는다고 명시하고 따로 보고한다.

### 1.3 지표 정의

**추출** (`ai/docs/eval_plan.md`, `ai/eval/score.py`)
- 항목 대응: 정답 항목과 출력 항목을 이름으로 짝짓는다. 엄격(정규화 후 같음)과 관대(편집거리 허용, 숫자는 같아야 함). 한/영 병기는 앞뒤를 각각 후보로 본다.
- **항목 정답률(대표)**: 관대 대응 후 이름·가격·잔/병이 모두 맞은 항목 비율. 회차별 값의 평균과 범위.
- F1(엄격·관대), 가격 정확도, 잔·병 혼동(건/회), 오탐·누락(건/회).

**매칭** (`ai/eval/match_eval.py`)
- 줄 결과: correct, partial(한 줄 두 상품 중 하나), ambiguous_ok / ambiguous_bad, unmatched, **false_merge**(다른 상품에 exact, 또는 카탈로그에 없는 상품·비위스키를 기존 상품에 exact), overconfident(`unknown` 줄을 확정).
- **false merge rate(대표 위험 지표)** = (false_merge + overconfident) / 줄.
- 알려진 상품 Top-1: exact로 정답 상품.
- **업주 부담**(사진당 확정 아닌 줄): (a) 확인 (b) 선택 (c) 직접 등록 (d) 오답 후보. 보조 지표: 사진당 5개 미만 비율.
- 확인 권장(`confirmRecommended`)을 규칙(S2b·S3)이 낸 것과 LLM(M3a·M4)이 낸 것으로 나눠 정답 비율, **확인 권장 수락 시 오답률**.

**Naver 별칭 후보** (`ai/naver/p28_score.py`)
- LLM same 정밀도(사람 `unsure`는 오답으로 셈), 오판의 단측 Clopper–Pearson 95% 상한, 신뢰도 구간별 오판률, 독립병입/정규품 층별.

### 1.4 결과 요약

전체 표는 `ai/docs/results_ledger.md`. 주요 판정:
- P14: A2(Flash-Lite + thinking medium) 채택, val 항목 정답률 0.996.
- P11: test 0.843 (I1 하한 0.85에 약간 못 미침).
- P22: S1+S2b+S3 채택 (test false merge 0).
- P12: CLOVA+LLM을 추출 경로 후보로 (Δ +0.040).
- M3: M3a 채택 (test C1 (c) 171 → 41).
- E2E: 판정 없음, 하이브리드 test 0.995.
- P28: 사람 검수 대기. M4: 잠정 no-go (dev).

---

## 2. 단위 테스트

### 2.1 목록

API 키 없이 돈다(실제 호출 테스트는 키가 있을 때만 돌고, 아래 명령에서는 뺀다). 개수는 2026-10-15 `pytest --collect-only` 기준(파라미터 케이스 포함).

| 파일 | 개수 | 내용 | 브랜치 |
|---|---|---|---|
| `ai/eval/test_score.py` | 25 | 추출 채점: 항목 대응(엄격·관대, 병기 분리), 가격·잔/병 오류 분류, 집계, 정답 파일 잠금(SHA) | `origin/i2-catalog-v2` |
| `ai/eval/test_label_ocr_check.py` | 6 | 라벨 ↔ OCR 표기 대조, 승인한 수정안으로 라벨 재생성 | 〃 |
| `ai/ocr/test_ocr.py` | 26 (+ 실제 호출 1) | CLOVA 줄 재구성, 이름·가격 재현율, 요청 형식·캐시·비밀값 미저장·재시도, 파서 호출, 프롬프트에 평가 사진 내용 없음 | 〃 |
| `ai/ocr/test_hybrid.py` | 24 | 하이브리드 요청 형식, 가격 줄 판정, 누락 감지, 호출 상한, 프롬프트에 평가 사진 내용 없음 | 〃 |
| `ai/match_llm/test_m3.py` | 12 | M3a 번역 → 재조회·토큰 규칙, M3b 고르기, 합치기·대체, 짧은 토큰, 응답 캐시(`--cache-only`) | 〃 |
| `ai/match_llm/test_vetoes.py` | 13 | 거부권 4개(bottler_missing 양방향, age_mismatch, alias_of_other, edition_mismatch)와 짧은 토큰 규칙. 평가셋에 없는 가짜 상품으로 작성 | 〃 |
| `ai/naver/test_naver.py` | 16 (+ 실제 호출 2) | Naver 클라이언트(캐시·재시도·키 미기록), 후보 추출, 매처 태그, 판정 형식 | `origin/i2-p17-naver` |
| `ai/naver/test_p28.py` | 3 | P28 채점(상한, unsure 처리), 429 즉시 중단 | `i2-p28-naver-precision` |
| `ai/match_llm/test_m4.py` | 8 | M4: exact 미생성, 거부권, new/unsure 무변경, 확인 권장 조건, 대상 줄 규칙 | `i2-m4-naver-match` |
| `backend/tests/test_normalize.py` | 26 | 공통 정규화(매칭 플로우 7장) | `origin/i2-catalog-v2` |
| `backend/tests/test_resolve.py` | 20 | 별칭 정확 일치 매처(M0) | 〃 |
| `backend/tests/test_resolve_staged.py` | 35 | S1, S2, S2b, S3 단계 | 〃 |
| `backend/tests/test_memory_catalog.py` | 7 | 메모리 카탈로그, seed 로딩 | 〃 |
| `backend/tests/test_db_catalog.py` | 5 | DB 카탈로그(PostgreSQL 필요) | 〃 |
| `backend/tests/test_extraction.py` | 52 | 백엔드 추출(이미지 전처리, 재시도·타임아웃, 응답 스키마, 변환) | 〃 |
| `backend/tests/test_extraction_adapter.py` | 30 | 추출 결과 형식 검사, mock 추출기 | 〃 |
| `backend/tests/test_gemini_extraction_adapter.py` | 21 | Gemini 어댑터, `MENU_EXTRACTOR` 선택, 키 미노출 | 〃 |
| `backend/tests/test_hybrid_extraction_adapter.py` | 30 | 하이브리드 어댑터(CLOVA mock transport, 가짜 Gemini), OCR 실패 fallback, bbox, `EXTRACTION_MODE` | `i2-p35-hybrid-backend` |

### 2.2 실행 명령

레포 루트에서:

```bash
# AI 실험 코드 (ai/), 실제 API 호출 테스트 제외
python -m pytest ai -k "not live"
```

```bash
# 백엔드 (AI 관련 포함 전체). DB 테스트는 POSTGRES_TEST_DATABASE가 있을 때만 돈다
cd backend && uv run pytest --cov
```

재채점(평가 숫자 재현, API 0회) 예:

```bash
python ai/eval/match_eval.py --split dev --gold eval/match_gold_v1_1.json --matcher S1+S2b+S3 M3a --m3-cache ai/runs/2026-10-14_m3/cache --cache-only
```

### 2.3 CI에서 도는 AI 테스트

- 워크플로 `.github/workflows/backend-ci-cd.yml` 하나다. PR(경로 `backend/**`, `ai/catalog/**`, `eval/**`)과 main push에서 `backend/`의 pytest를 PostgreSQL 18 서비스와 함께 돌리고, **커버리지 98% 미만이면 실패**한다.
- 그래서 CI에서 도는 AI 관련 테스트는 **백엔드 안의 것**이다: 정규화·매처(M0, S1–S3)·카탈로그 seed 로딩(`ai/catalog/*.json`을 읽음)·추출 서비스와 어댑터.
- **`ai/` 폴더의 테스트(채점, OCR, M3/M4, Naver)는 CI에서 돌지 않는다.** 실험 브랜치에서 로컬로 돌리고, 결과를 각 run의 사용 기록(`ai/runs/ai_usage_log.md`)에 적는다. CI에 넣을지는 결정이 필요하다.
- 실제 Gemini·CLOVA·Naver 호출은 CI에서 하지 않는다(키 없음, mock·fixture만).

---

## 3. 알려진 한계

- 평가 바가 적다(추출 test 3곳, 매칭 test 2곳). 미라보 한 곳이 test 항목의 71%라 바 하나의 레이아웃이 점수를 크게 흔든다(P11).
- dev 숫자는 dev에서 조정한 규칙의 결과라 낙관적이다. LLM 경로의 오답 0은 표본이 작아 95% 상한이 크다(`ai/docs/p29_proposal.md` 2절).
- 자동 확정 기준(false merge ≤ 0.02)은 지금 표본으로 증명할 수 없다(`ai/docs/naver_plan.md` 6절 (e)).
- 로컬 개발 환경에 PostgreSQL이 없으면 DB 테스트가 skip된다. 머지 전 CI 결과를 확인한다.
