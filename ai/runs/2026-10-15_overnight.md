# 2026-10-15 야간 자율 작업 기록

## 요약

| # | 작업 | 상태 | 브랜치 | 마지막 커밋 | 핵심 숫자 |
|---|---|---|---|---|---|
| 1 | P28 Naver 후보 정밀도 | **완료** (사람 검수 대기) | `i2-p28-naver-precision` | `6763a4f` | 40개 상품 → 후보 142, LLM same 51 (독립병입 8, 정규품 43). 매처 v1과 정면 충돌 0. 정밀도는 검수 후 |
| 2 | M4 Naver 근거 실시간 판정 (dev) | **완료, 잠정 no-go** | `i2-m4-naver-match` | `0a3b5cc` | C1 (b)+(c) M3a 5 → M3a+M4 5 (0%). M4 확인 0, false merge 0. 참고: M4만(M3a 없이) C1 15 → 5, 확인 9/9 정답. 프롬프트 수정 0회 |
| 3 | P29 준비 (신뢰도·검토 기준 표) | **완료** | `i2-m4-naver-match` | `06f048f` | 경로별 dev 정밀도 전부 1.000(오답 0, 상한 2.1~63%). 정책 3개 시뮬레이션, 결론 없음 |
| 4 | P35 하이브리드 백엔드 옵션 | **완료** (PR 미생성) | `i2-p35-hybrid-backend` | `4b396ca` | `EXTRACTION_MODE=gemini(기본)|hybrid`, CLOVA 실패 → Gemini fallback, bbox는 `raw_output`. 테스트 318 passed / 194 skipped(로컬 DB 없음) |
| 5 | P36 Naver 별칭 대기열 | **부분** (2단계 중단) | `i2-p36-naver-queue` | `c8f70bd` | 529개 상품 → 후보 2,240, 규칙 제외 749, LLM 판정 368, **pending_judge 1,123** (Gemini 응답 없음으로 중단, 429 아님) |
| 6 | 문서 초안 (원장, Testing doc) | **완료** | `i2-docs-ai-results` | `f334d37` (+ 이 요약 커밋) | 원장 9행, Testing doc AI 영역 초안("가이드라인 대조 필요") |

머지·PR·DB 변경·배포는 하지 않았다. 모든 브랜치는 push만 했다.

### 사용량

| API | P28 | M4 | P36 | 합 |
|---|---|---|---|---|
| Gemini (`gemini-3.5-flash-lite`, 재시도 포함) | 142 | 36 | 269 | **447** |
| Naver API HUB 검색 | 368 | 165 | 4,542 | **5,075** (하루 한도 25,000) |
| CLOVA OCR | 0 | 0 | 0 | 0 |

429·`RESOURCE_EXHAUSTED`는 한 번도 나지 않았다. P36 2단계 끝에서 Gemini가 330초 동안 응답하지 않는 호출이 연속으로 나서(1회차 5번, 이어서 시도한 2회차 5번) 멈췄다.

### 진우가 아침에 할 일

1. **P28 검수:** `review/p28_review.csv` (브랜치 `i2-p28-naver-precision`) 142줄의 `human_verdict`(same/different/unsure)를 채우고 `python ai/naver/p28_score.py --json ai/runs/2026-10-15_p28/score.json` 실행. v2 태그와 엇갈린 2줄(README 참고)을 먼저 보면 좋음.
2. **M4 잠정 판정 확인:** `ai/runs/2026-10-15_m4/README.md`. go 조건(20%, 10%)이 맞는지, "M4만으로 M3a 수준" 결과를 새로 등록해 test에서 볼지 결정.
3. **P29 정책 선택:** `ai/docs/p29_proposal.md` (브랜치 `i2-m4-naver-match`)의 P1/P2/P3 비교를 보고 결정. dev는 오답 0이라 test 숫자(M3 README)와 같이 볼 것.
4. **P35 리뷰:** `ai/docs/p35_backend_notes.md` (브랜치 `i2-p35-hybrid-backend`)의 PR 초안 → 해울과 확인 후 PR 생성. DB 테스트 194개는 CI에서 확인 필요. bbox 컬럼 제안(2절)은 해울 결정.
5. **P36 이어서:** Gemini가 정상이면 `python ai/naver/run_p36.py --stage 2` (브랜치 `i2-p36-naver-queue`, 남은 1,123개, 약 1.5시간). 검토는 `review/p36_alias_queue.csv`, `p47_only = yes`는 P47 뒤로.
6. **문서:** `ai/docs/results_ledger.md`, `ai/docs/testing_doc_ai_draft.md` (브랜치 `i2-docs-ai-results`) 검토, 과목 가이드라인과 대조. `ai/` 테스트를 CI에 넣을지 결정.
7. **키 확인:** Naver 키가 레포 `.env`에 없어서 기존 코드대로 작업 공간 `.env`에서 읽혔다(지시 "레포 .env에서만"과 다름). 레포 `.env`에 `NAVER_HUB_CLIENT_ID`/`SECRET`을 직접 넣을지 결정. 키 값은 어떤 파일·로그·커밋에도 남기지 않았다(커밋마다 스크립트로 확인).
8. **정리:** 레포 작업 폴더의 `review/final_gold_review.html`(git이 추적하지 않는 파일, P47 사진 크롭이 들어 있을 수 있음)은 열지 않고 그대로 두었다. 커밋하지 말 것. 레포 체크아웃은 시작할 때의 `i2-catalog-v2`로 되돌려 두었다.

## 작업별 기록 (진행 순)

### 1. P28 Naver 후보 정밀도 — 완료 (사람 검수 대기)

- 브랜치 `i2-p28-naver-precision` (base `origin/i2-p17-naver` `d24b004`), push 완료
- 커밋: `8b4a9a7` 사전 등록(`ai/docs/p28_plan.md`, 러너·채점·429 중단), `6763a4f` 실행 결과·검수표
- 핵심 숫자: 40개 상품 → 후보 142개 (독립병입 47, 정규품 95). LLM same 51 (독립병입 8, 정규품 43), different 75, unsure 16. same이 하나라도 나온 상품 25/40 (독립병입 6/20, 정규품 19/20)
- 매처 v1 태그와 LLM 정면 충돌 0건. v2 태그(참고)는 1건씩(other_product→LLM same 1, same→LLM different 1)
- LLM same 신뢰도가 0.9~0.98에 몰려 있음(0.95가 45/51) → 신뢰도 구간 분석은 의미가 약함
- 사용량: Naver 368회, Gemini 142회 (토큰 입력 26만), 429 없음
- 실패·주의: Naver 키가 레포 `.env`에 없어 기존 코드대로 작업 공간 `.env`에서 읽힘(지시와 다름, 진우 확인)
- 아침 할 일: `review/p28_review.csv` 142줄 `human_verdict` → `python ai/naver/p28_score.py`

### 2. M4 Naver 근거 실시간 판정 (dev) — 완료, 잠정 no-go

- 브랜치 `i2-m4-naver-match` (base `origin/i2-catalog-v2` + `origin/i2-p17-naver` 머지 `888468d`), push 완료
- 커밋: `07e556c` 사전 등록(`ai/docs/m4_plan.md`, M4 층·하네스·리포트·테스트), `0a3b5cc` dev r0 결과
- 핵심 숫자: dev C1 (b)+(c) M3a 5 → M3a+M4 5 (감소 0%, go 조건 1 불통과). M4 확인 0줄(C0·C1), false merge 0 유지. C0 오답 확인 시험: 확인 0, 카탈로그에 없는 상품 19줄을 new/none으로 판정
- 참고 행 M4(M3a 없이): C1 (b)+(c) 15 → 5, 확인 9줄 전부 정답 (C0도 확인 3줄 전부 정답) → M3a 대안/백업 가설, 새 등록 필요
- 프롬프트 수정 0회 (유일하게 줄일 수 있던 Hibiki DR은 검색 결과가 무관해서였음. 한 줄 맞추기 수정은 하지 않음)
- 지연: 대상 줄당 Naver 약 0.74초 + Gemini 1.37초
- 사용량: Gemini 36회, Naver 165회(dry run), 429 없음
- 실패 원인/한계: dev에 M3a 뒤 남은 줄이 거의 없어(C1 대상 3줄, 그중 2줄 unknown) 실험이 약함

### 3. P29 준비: 신뢰도·검토 기준 표 — 완료 (API 0회)

- 브랜치 `i2-m4-naver-match`, 커밋 `06f048f`, push 완료
- 산출물 `ai/docs/p29_proposal.md` (결론 없음, 비교표와 trade-off), 스크립트 `ai/eval/p29_paths.py`, 결과 `ai/runs/2026-10-15_p29/dev_paths.json`
- 핵심 숫자 (dev full 파이프라인 C1): alias_exact 138/138, s2_exact 12/12, s2b_confirm 3/3, s3_confirm 5/5, m3a_confirm 13/13 (오답 0이어도 95% 상한 20.6%). M4 확인(참고 파이프라인) 9/9
- 정책 시뮬레이션 (full C1, 사진당 업주가 고르는 C+D): P1 0.46 / P2 0.46 / P3 1.46. 확인 포함 B+C+D: 2.08 / 1.08 / 3.00. dev 오답 노출 0 (모든 정책)
- 주의: dev는 모든 경로 오답 0이라 정책 간 위험 차이가 안 보임. test 숫자(M3 README, 규칙 확인 권장 C0 7/12, M3a C0 7/9)를 참고로 옮겨 적음
- LLM 신뢰도: M4 판정이 0.9 이상에만 있음 → 신뢰도 구간 정책은 표본 부족

### 4. P35 하이브리드 추출 백엔드 옵션 — 완료 (PR 미생성, API 0회)

- 브랜치 `i2-p35-hybrid-backend` (base `origin/i2-catalog-v2` `415e78f`), 커밋 `4b396ca`, push 완료
- `EXTRACTION_MODE=gemini`(기본, 지금 동작) | `hybrid`(CLOVA OCR + Gemini, 동결 프롬프트 v1). CLOVA 실패 → Gemini 단독 fallback + 경고 로그 + `raw_output.hybridFallback`
- bbox: `extraction_runs.raw_output.ocr.lines`(0–1000 좌표)와 `itemSources`(항목별 근거 줄·합친 상자). DB 컬럼은 제안만(`ai/docs/p35_backend_notes.md` 2절, 해울 영역)
- 테스트: 318 passed (기존 288 + 새 30), 194 skipped. **skip은 로컬에 PostgreSQL이 없어서인 DB 테스트(변경 전과 같음) → CI 확인 필요**
- PR 초안: `ai/docs/p35_backend_notes.md` 5절

### 6. 문서 초안 — 완료 (API 0회)

- 브랜치 `i2-docs-ai-results` (base `origin/i2-catalog-v2` `415e78f`), 커밋 `f334d37`, push 완료
- `ai/docs/results_ledger.md`: 9개 실험 행(P14/I1, P11, P22, P12, L1 재채점, M3, E2E, P28, M4). 숫자는 원본에서 그대로 옮김
- `ai/docs/testing_doc_ai_draft.md`: 맨 위 "가이드라인 대조 필요". 확인한 사실: CI(`backend-ci-cd.yml`)는 backend 테스트만 돌리고 `ai/` 테스트는 CI에 없음

### 5. P36 Naver 별칭 후보 대기열 — 부분 완료 (1단계 완료, 2단계 일부)

- 브랜치 `i2-p36-naver-queue` (`i2-p28-naver-precision` + `origin/i2-catalog-v2` 머지 `6bd346f`), push 완료
- 커밋: `b7d4e22` 규칙·러너 등록(`ai/docs/p36_plan.md`), `abf4e51` 1단계 + 2단계 1회차, `c8f70bd` 기록
- 핵심 숫자: 529개 상품 → 후보 2,240개, 규칙 제외 749 (age_mismatch 428, other_product 355, existing_alias 154, bottler_missing 10), 남은 1,491. LLM 판정 368 (same 110, different 162, unsure 96; P28 재사용 111 포함), **pending_judge 1,123**
- P47 전용 상품 82개(후보 239) `p47_only` 표시 — P47 전 승인 금지 권장
- 사용량: Naver 4,542회, Gemini 269회
- 실패 원인: 2단계에서 Gemini가 330초 응답 없음(hard timeout)을 연속으로 냄. 1회 이어서 시도했지만 5회 모두 응답 없음 → 중단. 429·RESOURCE_EXHAUSTED는 아님. `python ai/naver/run_p36.py --stage 2`로 캐시에서 이어서 가능
