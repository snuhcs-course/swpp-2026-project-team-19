# I5-P59 매칭 규칙 수정 + I5-P31 매칭 재평가 (2026-11-27, 밤샘 실행 + 낮 실행)

지시: `_outgoing/i5_p31_p59_night_handoff.md`. 브랜치 `feature/i5-m3a-not-whisky`(로컬 커밋만, push 없음). 진우는 자는 중이라 질문 없이 진행했다.

> **11/27 낮 실행으로 갱신** (낮 추가 2까지). 진우 결정(받아 주는 연수, 가드는 끈 채, 1c 해석 맞음)대로 카탈로그 v2.6과 받아 주는 연수를 넣고 2단계(P31 재평가)를 돌렸다. 아래 "맨 먼저" 절과 0~4단계는 밤 실행 기록이다. 그 표의 "라산타 15Y"·"오리지날 10년"은 낮 실행에서 다시 맞게 확정되고, "더 넥타 16Y"는 그대로다(남은 것). 낮 결과는 맨 끝 [낮 실행](#낮-실행-2026-11-27-14시) 절. 낮 호출: Gemini 32회, OpenRouter 0회, CLOVA 0회.

## 맨 먼저: 2단계(P31 재평가)를 돌리지 않았다

**1a(글렌모렌지 연수)에서 맞는 확정이 사라졌다.** 지시("맞는 확정이 하나라도 사라지면 2단계로 넘어가지 말고, 그 줄 목록을 보고서 맨 위에 적은 뒤 1b로 간다")대로 1b·1c는 했고 2단계(Gemini 실행)는 하지 않았다. Gemini 호출 0회.

사라진 맞는 확정 (I3 33장, `full`·`ops` 같음, 규칙과 서버 단계 모두):

| 사진 | 줄 | 정답 | v2.4 | 1a 뒤 | 언제 |
|---|---|---|---|---|---|
| 018_청춘위스키 봉천_02 | 글렌모렌지 더 넥타 16Y | Nectar D'Or | 확정 (S3 편집 거리) | 후보 1개 + 확인 권장 (S2b, `editionOnlyInProduct`: "dor") | 하네스 그대로 |
| 018_청춘위스키 봉천_02 | 글렌모렌지 라산타 15Y | Lasanta | 확정 (별칭) | 후보 1개 (`ageConflict` 15 vs 12) | 추출이 연수를 넘길 때만 |
| 020_네스트_02 | 글렌모렌지 오리지날 10년 | The Original | 확정 (별칭) | 후보 1개 (`ageConflict` 10 vs 12) | 추출이 연수를 넘길 때만 |

- "하네스 그대로"는 지금 평가 방식(줄 이름만 넘김)에서 나는 것이고 Top-1은 그대로다(확정 수가 같다. 같은 실행에서 `글렌모렌지 12 라산타`가 새로 맞게 확정됨).
- "추출이 연수를 넘길 때만"은 하네스가 못 보는 것이다. 서버(`menu_import_processing.py` 310행)는 추출의 `age_years`를 매칭에 넘기고, 별칭으로 찾은 상품의 연수와 다르면 확정하지 않는다. 줄 이름의 연수를 넘기도록 하네스를 감싸 재 보니(`ai/eval/i5_p59_with_age.py`) I3 Top-1이 full 500 → 498, ops 511 → 509로 줄었다. dev는 사라진 줄이 없다.
- 셋 다 후보 1개로 정답 상품이 남으므로 업주는 한 번 눌러 확인하면 된다. 틀린 확정(FM)은 늘지 않았다.

## 진우가 정할 것 (11/27 낮 갱신)

닫힌 것 (진우 결정, 2026-11-27):

- ~~1. 1a를 이대로 둘지, 2단계를 돌릴지~~ **닫힘.** 연수는 옛 병과 새 병 둘 다 받아 주고 상품은 하나로 둔다. 1-다(라산타 15)는 지금 병이 15년이라 카탈로그 쪽 값이 틀렸던 것이다(v2.6에서 Lasanta 12 → 15). 2단계는 낮 실행에서 돌렸다.
- ~~2. 1b 플래그(`MATCHING_MISSING_AGE_GUARD`)를 켤지~~ **닫힘.** 끈 채로 둔다. 좁은 변형은 구현하지 않는다.
- ~~4. 1c 해석 확인~~ **닫힘.** 해석이 맞다(새로 내는 후보만 확정하지 않고, 대표 병의 기존 확정은 그대로).

남은 것:

1. **3단계(3.8 Flash 끝까지 추출) 실행 승인.** 1회 약 $0.92, 3회 약 $2.77, CLOVA 0회. OpenRouter PR(P19)이 main에 들어간 뒤 실행기를 만들어야 한다. 3단계 절.
- ~~"글렌모렌지 더 넥타 16Y"~~ (밤 1-나) **닫힘.** 이름을 "The Nectar"로 바꾸고(v2.7) 관사 규칙을 고쳐 확정된다(진우 결정, "낮 추가"·"낮 추가 2" 절).

밤 실행 호출 수: **Gemini 0회, OpenRouter 0회, CLOVA 0회.** push·PR 생성 없음. `feature/i5-p19-openrouter-extraction`은 읽기만 했다(`git show`, `git diff`).

## 0단계: 지금 상태 정리

### 0.1 커밋 나누기

11/21 "위스키 아님" 작업의 커밋 안 된 수정 19개를 네 커밋으로 나눴다. 해시는 #221 위로 rebase한 뒤의 것이다(맨 끝 절).

| 커밋 | 내용 |
|---|---|
| `9e1d3c89` (옛 `c70bad06`) | 카탈로그 v2.4(잭다니엘 애플), 오드비 정답 1줄, 하네스의 dev 예외 삭제, 회귀 fixture·baseline, 고정값 테스트(`test_review_states`, `test_mixed_report`, `test_i3_match_eval`의 digest·`gold_for`), P30 동결 해제 목록에 카탈로그, 정답 수정 후 `mixed_report.*` |
| `b52114ad` (옛 `8fffff10`) | `kind_hint`(`types.py`), `flag_non_whisky`(`llm_layer.py`), 임베딩 단계에서 유지(`embedding.py`), `menu_import_processing.py` 호출부, 백엔드 테스트 3개 파일, P30 동결 해제 목록에 `llm_layer.py` |
| `1a7ebc76` (옛 `1854938d`) | 하네스 `--flag-non-whisky`와 `not_whisky` 지표, 그 테스트, `ai/eval/i5_kind_table.py` |
| `b8208a2b` (옛 `73bac2a6`, `491d4057`) | 11/21 보고서, `kind_*.md`, `ai_usage_log.md`. dev M3a 캐시(`cache_dev_r1`, `cache_dev_r2`, 각 26개)도 넣었으나 히스토리 정리(맨 끝 절)에서 걷어냈다(디스크에만 있음) |

- 한 파일에 두 작업이 섞인 `i3_match_eval.py`, `test_i3_match_eval.py`, `p30_extract.py`, `test_p30_extract.py`는 hunk 단위로 나눴다. `p30_extract.py`의 해제 목록은 ①에서 카탈로그만, ②에서 `llm_layer.py`를 더한 상태로 들어간다.
- 추적 안 되는 `ai/eval/i5_*.py` 7개 중 이 작업 것은 `i5_kind_table.py` 하나다(11/21 보고서와 사용 기록 기준). 나머지 6개(`i5_model_ladder`, `i5_price_from_lines`, `i5_regression_compare`, `i5_row_align`, `i5_row_pairing`, `i5_title_fix_check`)는 행 맞추기 작업(`2026-11-21_i5_row_pairing`) 것이라 그대로 두었다. 그중 `i5_model_ladder.py`, `i5_row_pairing.py`는 P19 브랜치에도 같은 이름으로 있다.
- `ai_usage_log.md`의 커밋 안 된 추가분에는 같은 날 행 맞추기 작업 기록도 들어 있다. 한 덩어리로 커밋했다(④).
- 커밋하지 않고 둔 것: 11/21 폴더의 큰 결과 JSON(`match/` 22MB, `*_rules_server*.json`, `*_llm_r1_v2_4.json`, `kind_*_rows.json`), P46 캐시, `2026-11-13_m3a_dev/`, hybrid 프롬프트 v2.1·v3 초안.
- 커밋 중 `.git/packed-refs.lock`(11/21 10:35에 생긴 0바이트 파일, 실행 중인 git 없음) 때문에 경고가 났다. 커밋 자체는 들어갔고, 오래된 잠금 파일이라 지웠다.

### 0.2 rebase

`git fetch` 뒤 `origin/main` = `0fae9345`(11/26 22시, 지시와 같음). 충돌 없이 rebase됐다. main의 0e628774 이후 17커밋은 `backend/app/matching`, `ai/`, `eval/`을 건드리지 않았다.

### 0.3 테스트

- 이 환경에서 pytest 기본 임시 폴더(`%TEMP%/pytest-of-user`)에 쓰기 권한이 없어 `tmp_path`를 쓰는 테스트가 오류가 났다. `--basetemp`를 작업 폴더로 주고 다시 돌렸다(코드 문제 아님).
- `ai/eval` + `ai/regression`: 272개 중 271 통과, 1 실패 `test_reencoded_ocr_cache_without_provenance_stops`(11/21부터 실패하던 것. 메시지의 경로 구분자가 Windows에서 `\`라 문자열 비교가 틀림). 4번 돌렸다.
  - 첫 회에만 `test_i3_match_eval.py::test_server_steps_add_candidates_and_never_confirm`도 실패했다. 혼자 돌려도, 그 파일만 돌려도, 전체를 세 번 더 돌려도 통과했다. 원인은 못 찾았다(오류 메시지를 남기지 못함). 이번 커밋 나누기는 코드 내용을 바꾸지 않았으므로 이번 변경 때문은 아니라고 보고 진행했다. **흔들리는 테스트로 "남은 것"에 적는다.**
- 백엔드 매칭 테스트(`app.matching`을 import하는 20개 파일): 440 통과, 119 건너뜀(DB 필요), 실패 0.

### 0.4 규칙만 기대값 (API 0회)

명령(레포 루트, `$P = ai/runs/2026-11-27_i5_p31`):

```
python ai/eval/i3_match_eval.py --set i3 --catalog full --server-steps --json $P/step0/i3_full_rules.json
python ai/eval/i3_match_eval.py --set i3 --catalog ops  --server-steps --json $P/step0/i3_ops_rules.json
python ai/eval/i3_match_eval.py --set dev --catalog service --server-steps --json $P/step0/dev_service_rules.json
```

| | 기대 | 결과 | digest |
|---|---|---|---|
| I3 full | 500/646, FM 1 | 500/646, FM 1, 틀린 확인 권장 3, hard/photo 2.94 (서버 단계 뒤 2.48) | `bc5dc49559cc` |
| I3 ops | 511/646, FM 1 | 511/646, FM 1, 틀린 확인 권장 3, hard/photo 2.52 (2.06) | `72af115bb369` |
| dev service | 625/804 | 625/804, FM 0, 틀린 확인 권장 3, hard/photo 4.21 (3.86) | `2dbcc8672dcb` |

모두 맞다. 1단계로 간다.

## 1단계: P59 규칙과 카탈로그 (API 0회)

백로그 문서 `claude/i4_ai_backlog_2026-11-13.md`는 이 컴퓨터에 없다(프로젝트 문서). 값과 규칙은 인계 문서에 옮겨 적힌 것을 그대로 썼다.

비교 방법: 같은 명령(0.4절)을 바꾼 뒤 다시 돌리고, `ai/eval/i5_p59_compare.py`로 (사진, 줄 이름, 순번)마다 상태·판정·업주 부담·후보·확인 권장을 비교했다. 규칙(`rules`)과 서버 단계 뒤(`server`) 둘 다. 줄별 표는 `step1/*_diff.md`.

### 1a. 카탈로그 연수 (catalog v2.5)

`ai/catalog/catalog_v2_service.json`: The Original 10 → 12, Quinta Ruban 없음 → 14, Lasanta 없음 → 12, Nectar D'Or 없음 → 16. `version` `catalog_v2_5_service`. 별칭은 고치지 않았다(옛 연수 별칭 `Glenmorangie 10`, `글렌모렌지10`, 템플릿 `... Aged 10 Years`, `글렌모렌지 오리지널 10년 숙성`이 남아 있음). README 16장.

**줄 이름만 넘기는 지금 하네스** (`step1/1a_*_diff.md`)

| | 바뀐 줄 | Top-1 | FM | 틀린 확인 권장 | hard/photo (규칙 / 서버 뒤) | confirm/choose/register/wrong (서버 뒤) |
|---|---|---|---|---|---|---|
| dev service | 2 | 625 → 626 / 804 | 0 → 0 | 3 → 3 | 4.21 → 4.14 / 3.86 → 3.79 | 99/84/18/10 → 100/83/18/9 |
| I3 full | 5 | 500 → 500 / 646 | 1 → 1 | 3 → 2 | 2.94 → 2.85 / 2.48 → 2.39 | 84/53/14/15 → 87/53/14/12 |
| I3 ops | 5 | 511 → 511 / 646 | 1 → 1 | 3 → 2 | 2.52 → 2.42 / 2.06 → 1.97 | 87/54/8/6 → 90/54/8/3 |

바뀐 줄 (I3는 full·ops가 같은 5줄):

| 셋 | 줄 | 정답 | 전 | 후 |
|---|---|---|---|---|
| dev | 011_미라보_04 글렌모렌지(Glenmorangie) 12년 오리지널 | The Original | 틀린 후보 1개 (12 Calvados) | **확정, 맞음** |
| dev | 011_미라보_04 글렌모렌지(Glenmorangie) 16년 더 넥타 | Nectar D'Or | 후보 없음 (서버 뒤 임베딩 후보 5개 중 고르기) | 후보 1개 + 확인 권장 |
| I3 | 015_연림 서울대입구역점_04 글렌모렌지 12 라산타 | Lasanta | 틀린 후보 1개 (12 Calvados) | **확정, 맞음** |
| I3 | 016_연림 봉천역점_03 글렌모렌지 12 | The Original | 틀린 후보 1개 + 확인 권장 (12 Calvados) | 후보 3개 중 고르기 (Original 포함) |
| I3 | 017_리틀 갤러리_03 글랜모랜지 14년 / Glenmorangie 14yr | Quinta Ruban | 후보 없음 (서버 뒤 틀린 임베딩 후보) | 후보 1개 (정답) |
| I3 | 017_리틀 갤러리_03 글렌모렌지 16년 / Glenmorangie 16yr | Nectar D'Or | 후보 없음 (서버 뒤 임베딩 후보 중 고르기) | 후보 1개 (정답) |
| I3 | 018_청춘위스키 봉천_02 글렌모렌지 더 넥타 16Y | Nectar D'Or | **확정, 맞음** (S3) | 후보 1개 + 확인 권장 |

- 마지막 줄이 사라진 맞는 확정이다. 전에는 연수 16인 글렌모렌지 상품이 없어 S2가 아무것도 못 찾았고, S3(편집 거리)가 별칭 "글렌모렌지 16 더 넥타"와 맞춰 확정했다. 이제 S2가 Nectar D'Or(16)를 찾는데, 상품 edition "Nectar D'Or"의 "dor"가 줄에 없어 확인 권장으로 낮춘다(`editionOnlyInProduct`). S2가 찾았으므로 S3는 돌지 않는다.
- 틀린 확인 권장 3 → 2: 016 "글렌모렌지 12"가 Calvados 하나만 권하던 것이 없어졌다.

**옛 연수로 적힌 줄 (꼭 볼 것)**: 메뉴에 지금 카탈로그와 다른 연수로 적힌 줄을 정답이 이 네 상품인 줄에서 모두 찾았다.

| 셋 | 줄 | 메뉴 연수 | 카탈로그 연수 | 하네스 그대로 | 추출이 연수를 넘길 때 |
|---|---|---|---|---|---|
| I3 | 020_네스트_02 글렌모렌지 오리지날 10년 | 10 | 12 | 확정 그대로 (별칭) | **확정 → 후보 1개** |
| I3 | 018_청춘위스키 봉천_02 글렌모렌지 라산타 15Y | 15 | 12 | 확정 그대로 (별칭) | **확정 → 후보 1개** |
| I3 | 017_리틀 갤러리_03 글렌모렌지 15년 / Glenmorangie 15yr | 15 | 12 | 후보 없음 그대로 | 후보 없음 그대로 |
| dev | (없음) | | | | |

- "추출이 연수를 넘길 때"는 `ai/eval/i5_p59_with_age.py`로 쟀다. 하네스의 `resolve`를 감싸 줄 이름에서 S2 연수 패턴(`12년`, `12Y`, `12yo`)으로 읽은 연수를 `ExtractedProduct.age_years`로 넘긴다(서버가 추출 결과로 하는 것의 대용). v2.4와 1a를 같은 방식으로 돌려 비교했다(`step1/1a_age_*_diff.md`). 이 방식에서 I3 Top-1은 full 500 → 498, ops 511 → 509, dev 625 → 626. 그 밖의 바뀐 줄은 위 표와 같다.
- "라산타 15Y"·"Glenmorangie 15yr"를 Lasanta로 적은 정답이 두 매장에 있다. 백로그 값(12)과 다르다. 15년 라산타가 있는지는 확인하지 않았다(웹 검색 안 함). **본 셋에서 본 것**이라 정답·카탈로그는 고치지 않았다.
- 회귀 15장(`ai/regression/regression.py`): 통과, 바뀐 줄 없음.

테스트: `ai/eval/test_i5_p59.py`(카탈로그 연수, "Glenmorangie 14" → Quinta Ruban 후보 1개, 비교 스크립트, 연수 넘기는 래퍼), `test_i3_match_eval.py`의 I3 asis digest 고정값(v2.4 `b82cacac…` → v2.5 `541fb3d4…`). AI 테스트 실패는 이전부터의 1개뿐. 새 스크립트 커버리지: `i5_p59_compare.py` 96%, `i5_p59_with_age.py` 88%(빠진 줄은 `if __name__ == "__main__"`), 합 95%.

### 1b. 연수 없는 메뉴 줄의 확정 막기 (플래그, 기본 꺼짐)

**구현.** 규칙(`staged.py`)이 아니라 확정을 뺏기만 하는 연결 가드(`backend/app/matching/linking_guards.py`)에 넣었다. 기존 가드(`unverifiedProduct`, `incompleteName`)와 같은 자리, 같은 결과(후보 1개 + 확인 권장)다.

- 가드 `missingAge`: 확정(`exact_match`)된 상품에 연수가 있고, 줄 이름에 연수가 없고, 추출이 넘긴 연수(`line_age`)도 없으면 확정하지 않는다. 근거 `missingAge: <상품 연수>`, `confirmRecommended`.
- "줄에 연수가 있다": 도수·용량·잔·가격을 뺀 이름에 다른 숫자에 붙지 않은 한두 자리 숫자가 있음(`12년`, `12Y`, `Glenfiddich 12`, `라프로익10`, `#4`도 연수로 침. `14.1`, `2025`, `700ml`는 아님). 함수 `has_age`.
- 설정: 환경변수 `MATCHING_MISSING_AGE_GUARD`(기본 `false`). `true`/`false` 외의 값은 서버 시작 때 멈춘다(`app/main.py`). `backend/README.md` 표와 `backend/.env.example`에 적었다. 메뉴 등록(`menu_import_processing.py`)은 이 값과 `extracted_age_years`를 가드에 넘긴다.
- 하네스: `--missing-age-guard`(`--server-steps` 필요). 하네스는 추출 연수가 없으므로 줄 이름으로만 판단한다.

**측정** (서버 단계 뒤, 카탈로그 v2.5, 규칙만. 꺼짐은 1a 결과와 줄 단위로 같음을 확인. `step1/1b_*_diff.md`)

| | 확정 수 (꺼짐 → 켜짐) | 사라진 맞는 확정 | 사라진 틀린 확정 | Top-1 | FM | 틀린 확인 권장 | hard/photo | confirm/choose/register/wrong |
|---|---|---|---|---|---|---|---|---|
| I3 full | 509 → 484 | 24 | 1 (Ardbeg Anthology) | 500 → 476 / 646 | 1 → 0 | 2 → 3 | 2.39 → 2.42 | 87/53/14/12 → 111/54/14/12 |
| I3 ops | 520 → 495 | 24 | 1 (Ardbeg Anthology) | 511 → 487 / 646 | 1 → 0 | 2 → 3 | 1.97 → 2.00 | 90/54/8/3 → 114/55/8/3 |
| dev service | 626 → 602 | 24 | 0 | 626 → 602 / 804 | 0 → 0 | 3 → 3 | 3.79 → 3.79 | 100/83/18/9 → 124/83/18/9 |

- **"Ardbeg Anthology"(014_테일오브테일즈_07)는 막힌다.** 확정(정답 미상, overconfident) → 후보 1개(Ardbeg Anthology 14) + 확인 권장, 업주 부담 `choose`. I3의 FM 1이 0이 된다. 대신 그 후보가 "틀린 확인 권장"으로 하나 늘었다(정답이 미상이라 맞는 권장으로 세지 않음).
- 사라진 맞는 확정 24줄은 모두 정답 상품이 후보 1개 + 확인 권장으로 남는다(`confirm`, 업주가 한 번 누름). 어려운 줄(choose/register/wrong)은 I3에서 Anthology 1줄만 늘고 dev는 그대로다.
- 사라지는 맞는 확정의 절반 이상은 1a가 연수를 넣은 글렌모렌지 4종이다. 같은 가드를 v2.4 카탈로그(1a 전)로 돌리면 I3 full 500 → 484, dev 625 → 609(각 16줄)로, 1a가 각 8줄을 더한다.

사라지는 맞는 확정 (I3는 full·ops가 같은 24줄):

| 셋 | 줄 (사진) | 확정되던 상품 |
|---|---|---|
| I3 | Johnnie Walker Black Label (014_01), 조니워커 블랙 (015_02, 016_01, 019p2_04, 020_01), 조니워커 블랙 라벨 / Johnnie Walker Black Label (017_02) | Johnnie Walker Black Label |
| I3 | 조니워커 그린 라벨 / Johnnie Walker Green Label (017_02), 조니워커 그린 (019p2_04) | Johnnie Walker Green Label |
| I3 | Ardbeg WEE Beastie (014_07), 아드벡 위비스티 (021_01, 021_02) | Ardbeg Wee Beastie 5 |
| I3 | Glenmorangie Original (014_08, 014_11), 글렌모렌지 오리지널 (015_01, 018_02), 글렌모렌지오리지널 (019p2_01) | Glenmorangie The Original |
| I3 | Glenmorangie Lasanta (014_08), 글렌모렌지라산타 (019p2_01) | Glenmorangie Lasanta |
| I3 | Glenmorangie Quinta Ruban (014_08), 글렌모렌지퀸타루반 (019p2_01) | Glenmorangie Quinta Ruban |
| I3 | Glenmorangie The Nectar (014_08, 014_11), 글렌모렌지더넥타 (019p2_01), 글렌모렌지 더 넥타 (021_01) | Glenmorangie Nectar D'Or |
| dev | 조니워커 블랙 (007_03), 조니워커 블랙 / Jonnie walker black (008_01), 조니워커(Johnnie Walker) 블랙 (011_01), 조니워커블랙 (009_05) | Johnnie Walker Black Label |
| dev | 조니워커(Johnnie Walker) 블랙 셰리 (011_01) | Johnnie Walker Black Label Sherry Finish |
| dev | 조니워커(Johnnie Walker) 그린 (011_01), JohnnieWalker Green (그린) (010_03) | Johnnie Walker Green Label |
| dev | 베이커스(Baker's) 버번 (011_07) | Baker's 7 Bourbon |
| dev | Balvenie American Oak (아메리칸 오크) (010_02) | The Balvenie 12 American Oak |
| dev | Balvenie Single Barrel (싱글배럴) (010_02) | The Balvenie 12 Single Barrel |
| dev | Glenmorangie Calvados Cask (깔바도스 캐스크) (010_03) | Glenmorangie 12 Calvados Cask Finish |
| dev | 아드벡 위 비스티 (009_06) | Ardbeg Wee Beastie 5 |
| dev | 글렌모렌지 오리지널 (007_01, 010_05, 009_08), 글랜모렌지 오리지날 / Glenmorangie OG (008_03) | Glenmorangie The Original |
| dev | 글렌모렌지 라산타 (007_01, 009_08), Glenmorangie Lasanta (라산타) (010_03), 글랜모렌지 라산타 / Glenmorangie Lasanta (008_03) | Glenmorangie Lasanta |
| dev | 글렌모렌지 넥타도르 (007_01), 글랜모렌지 넥타도르 / Glenmorangie Nectar D'or (008_03) | Glenmorangie Nectar D'Or |
| dev | Glenmorangie Quinta Ruban (퀸타루반) (010_03), 글랜모렌지 퀸타루반 / Glenmorangie Quinta Ruban (008_03) | Glenmorangie Quinta Ruban |

(사진 번호는 `014_01` = `014_테일오브테일즈_01`, `019p2` = `019_쏘댓page2` 식으로 줄였다. 원래 이름은 diff 파일에 있다.)

**더 좁은 변형 (구현하지 않음, 제안만)**

- 사라지는 맞는 확정은 "연수가 상품의 이름이 아니라 속성인 대표 병"(조니워커 블랙 12, 글렌모렌지 오리지널 12, 라산타 12 등)이 대부분이다. 메뉴는 이런 병에 연수를 잘 안 적는다.
- (가) **상품 표시명에 연수가 들어 있을 때만**(`Ardbeg Anthology 14`, `Ardbeg Wee Beastie 5`, `Baker's 7 Bourbon`, `The Balvenie 12 American Oak`): 위 목록에서 손으로 세면 I3에서 맞는 확정 3줄(Wee Beastie)만 잃고 Anthology는 막는다. dev는 5줄(Baker's, Balvenie 2, Calvados, Wee Beastie). 카탈로그 표시명 관례에 기대는 규칙이라 표시명이 바뀌면 같이 바뀐다.
- (나) **같은 브랜드·에디션에 연수가 다른 병이 있다고 알려진 시리즈만**(Anthology는 13·14·16 등 해마다 다른 연수): 카탈로그에 시리즈 표시를 따로 둬야 한다. 지금 카탈로그에는 Anthology가 14 하나뿐이라 데이터만으로는 고를 수 없다.
- 어느 쪽이든 근거가 Anthology 한 줄이다. 숫자로 고를 만큼 사례가 없다.

테스트: `backend/tests/test_linking_guards.py` 6개(기본 꺼짐, 연수 없는 줄 2종, 연수 있는 줄·연수 없는 상품은 그대로, 추출 연수, `has_age` 12가지, 설정값), `ai/eval/test_i5_p59.py` 2개(하네스 옵션, 옵션 조합 오류). 커버리지: `linking_guards.py` 100%(분기 포함). 백엔드 전체 1153 통과, 1940 건너뜀(DB 필요). `tests/test_pdf_*.py`, `test_run_uat_inputs.py` 3개 파일은 이 환경에 `pypdfium2`가 없어 수집되지 않아 뺐다(main의 PDF 기능, 이번 변경과 무관). AI 전체 390 중 389 통과(이전부터의 1개 실패).

### 1c. 연수만 적힌 줄 ("글렌모렌지 14년")

**결론: 규칙은 고치지 않았다.** 1a로 연수가 들어간 뒤에는 지금 규칙(S2 브랜드 + 연수, S2b 기본 상품)이 지시한 동작을 이미 한다. 그 동작을 단위 테스트로 고정하고, 데이터 전체에서 빠진 줄이 없는지 쟀다.

- 지금 규칙: 브랜드 + 연수만 적힌 줄은 그 브랜드의 그 연수 상품으로 좁힌다. 그런 상품이 하나이고 에디션이 있으면 후보 1개(확인 권장, 확정 아님). 에디션 없는 대표 병 하나면 S2b 기본 상품으로 확정(예전부터, P47에서 평가한 동작). 둘 이상이면 고르기.
- 지시의 "확정은 하지 않는다"는 이 규칙이 새로 내는 후보에 대한 말로 읽었다. 그대로 읽어 "브랜드 + 연수 줄은 언제나 확정하지 않는다"로 하면 `글렌피딕 15`, `라가불린16` 같은 맞는 확정 수백 줄이 후보로 바뀐다(아래 스캔에서 그 연수 상품이 하나인 줄 I3 207, dev 206의 대부분). `incompleteName`도 그 연수 형제가 없는 브랜드는 확정을 남기므로 같은 원칙으로 보았다.
- 스캔(`ai/eval/i5_p59_age_only.py`, API 0회, `step1/1c_age_only_v2_5.md`): 이름(또는 "A / B"의 한쪽, 괄호 변형)이 브랜드 + 연수뿐인 줄을 모두 찾고, 그 연수 상품이 하나인데 첫 후보로 안 나온 줄을 센다.

| 셋 (1a 뒤) | 브랜드 + 연수만 | 그 연수 상품이 하나 | 그중 첫 후보로 안 나옴 | 에디션인데 확정 (그대로 둠) |
|---|---|---|---|---|
| I3 full | 272 | 207 | 0 | 0 |
| I3 ops | 274 | 209 | 0 | 0 |
| dev service | 263 | 206 | 0 | 4 |

- dev의 "에디션인데 확정" 4줄은 별칭으로 확정된 맞는 줄이다: 하이랜드 파크(Highland Park) 18년 → 18 Viking Pride, 글렌드로낙(Glendronach) 18년·글렌드로낙18 → 18 Allardice, 글렌드로낙(Glendronach) 21년 → 21 Parliament. 그 연수 형제가 카탈로그에 없어 `incompleteName`도 남기는 경우라 그대로 두었다.

**리틀 갤러리 세 줄** (`017_리틀 갤러리_03`, P46 `full`에서 규칙 후보 없음)

| 줄 | 정답 | P46·v2.4 (규칙 / 서버 뒤) | 1a·1c 뒤 (규칙 / 서버 뒤) |
|---|---|---|---|
| 글랜모랜지 14년 / Glenmorangie 14yr | Quinta Ruban | 후보 없음 / 틀린 임베딩 후보 5개 | **후보 1개 = 정답** / 같음 |
| 글렌모렌지 15년 / Glenmorangie 15yr | Lasanta | 후보 없음 / 임베딩 후보 중 고르기 | 그대로 (15년 글렌모렌지 상품 없음) |
| 글렌모렌지 16년 / Glenmorangie 16yr | Nectar D'Or | 후보 없음 / 임베딩 후보 중 고르기 | **후보 1개 = 정답** / 같음 |

- 14yr·16yr 줄은 "14yr"을 연수 14와 글자 "r"로 읽는다. "r"이 아무 상품에도 안 맞아 후보는 1개지만 확인 권장 표시는 붙지 않는다(업주 부담은 똑같이 `confirm`). `yr`을 연수 단위로 읽게 하면 붙는다. 규칙 수정이라 하지 않았다("남은 것").
- 15년 줄은 정답(Lasanta)과 카탈로그 연수(12)가 다르다. 1a 표 참고.

전후 비교: 규칙 코드를 바꾸지 않았으므로 1c 전후 결과는 1a 결과와 줄 단위로 같다.

테스트: `backend/tests/test_resolve_staged.py` 6개(연수 상품 하나 → 후보 1개 4가지 표기, 둘 → 고르기, 대표 병은 확정·없는 연수는 후보 없음), `ai/eval/test_i5_p59.py` 2개(스캔). 커버리지: `i5_p59_age_only.py` 91%.

## 2단계: P31 재평가 — 돌리지 않음 (밤. 낮 실행에서 돌림)

1a에서 맞는 확정이 사라져(맨 위 표) 지시대로 넘어가지 않았다. **Gemini 호출 0회.** 1단계 커밋 상태에서 돌릴 명령은 준비해 두었다(진우가 1a를 그대로 둘지 정한 뒤). 11/21 4.2절과 같은 구성이다.

```powershell
$P = "ai/runs/2026-11-27_i5_p31"; $N = "ai/runs/2026-11-21_i5_not_whisky"; $Q = "ai/runs/2026-11-17_p46"
# dev 5곳 (service), r1·r2. 11/21 캐시를 씨앗으로
foreach ($r in 1,2) {
  python ai/eval/i3_match_eval.py --set dev --catalog service --llm --cache "$P/cache_dev_r$r" `
    --seed-cache "$N/cache_dev_r$r" --server-steps --flag-non-whisky --max-calls 60 --json "$P/match/dev_service_r$r.json"
}
# I3 33장 full·ops, 라벨 입력, r1~r3. P46 캐시를 씨앗으로
foreach ($r in 1,2,3) { foreach ($c in "full","ops") {
  python ai/eval/i3_match_eval.py --set i3 --catalog $c --llm --cache "$P/cache_${c}_label_r$r" `
    --seed-cache "$Q/cache_${c}_label_r$r" --server-steps --flag-non-whisky --max-calls 60 --json "$P/match/i3_${c}_label_r$r.json"
} }
# 1b를 켠 경우: 같은 명령에 --missing-age-guard 를 더하고 --json 이름만 바꾼다 (캐시가 같아 새 호출 없음)
```

- 예상 새 호출: 1a로 LLM 대상 줄이 달라지는 사진만 새로 부른다. 1a에서 바뀐 줄이 있는 사진은 dev 1장(011_미라보_04), I3 4장(015_04, 016_03, 017_03, 018_02)이라 회차·구성마다 0~4회로 본다. 합계 약 30회 이하로 200회 상한에서 멀다(실제 수는 돌려야 안다).
- `--seed-cache`가 받는 캐시 폴더 이름은 11/21·P46 실행의 것을 그대로 썼다. P46의 ops 캐시는 `cache_ops_label_r*`.

## 3단계: 끝까지 추출부터 (준비만, 실행하지 않음)

추출 모델이 3.8 Flash(OpenRouter, P19)로 바뀌었으므로 I3 33장의 추출 → 매칭을 다시 재야 한다.

**확인한 것 (API 0회)**

- 사진과 OCR 캐시: `python ai/eval/p46_extract.py --out <임시> --check` → "photos and OCR caches verified: 33". 33장 모두 `<data_dir>/ocr_cache/<stem>__table-off.json`이 있고, 서버가 보낼 이미지의 SHA-256과 캐시의 `sent_sha256`이 같다.
- P19의 서버 경로 실행기(`ai/eval/i5_server_route_regression.py`, P19 브랜치에서 읽기만 함)도 같은 파일을 `ReplayOcr`로 재생한다. 그래서 **CLOVA 호출 0회**로 돌릴 수 있다.

**실행 방법 (P19가 main에 들어간 뒤)**

이 브랜치에는 OpenRouter 추출 코드(`backend/app/extraction/routed.py`)가 없다. P19가 들어가면:

1. P19의 `i5_server_route_regression.py`를 I3 33장용으로 바꾼 실행기를 만든다(사진 목록 `ai/eval/i3_photo_sha256.json`, 기록을 P46 `hybrid_v2_i3`와 같은 `<stem>_r<k>.json` 형식으로 써서 `i3_match_eval.py --extraction`이 읽게). 프롬프트 v2.1, `google/gemini-3.8-flash`, reasoning medium, 폴백 없음, Gemini API 경로 닫음은 P19 실행과 같게.
2. 추출(33장 × 회차), 채점(`python ai/eval/score.py --set i3 <out>`), 매칭은 P46 4절 명령 그대로:

```powershell
foreach ($r in 1,2,3) { foreach ($c in "full","ops") {
  python ai/eval/i3_match_eval.py --set i3 --catalog $c --extraction "$P/hybrid_v2_1_38flash_i3" --run $r --llm `
    --cache "$P/cache_${c}_e2e_r$r" --server-steps --flag-non-whisky --max-calls 60 --json "$P/match/i3_${c}_e2e_r$r.json"
} }
```

**예상 호출과 비용**

| | 1회 | 3회 |
|---|---|---|
| OpenRouter (3.8 Flash, 사진 1장당 약 $0.028: P19 서버 경로 17장 중앙값 $0.0281) | 33회, 약 **$0.92** | 99회, 약 **$2.77** |
| OpenRouter 최악 (한 장에 2번 시도, 30k 입력 + 48k 출력, P19 실행기의 상한 계산) | 사진당 $0.405 | 상한을 실행기에 두고 돈다 |
| CLOVA | 0회 | 0회 |
| Gemini 무료 키 (M3a 매칭, 사진마다 새 입력이라 full·ops 각 약 31회) | 약 62회 | 약 186회 |

- I3 사진은 회귀 17장보다 줄이 많은 메뉴가 있어 실제 비용은 조금 더 들 수 있다.
- 3회를 돌리면 Gemini 무료 키가 약 186회라 하루 200회 상한에 가깝다. 2단계와 같은 날 돌리면 넘는다.

**진우 승인 필요: 1회 약 $0.92, 3회 약 $2.77** (OpenRouter 남은 $92.36에서).

## 4단계: 마무리

### 최종 테스트 (1c 커밋 뒤)

- `ai` 전체: 392개 중 391 통과, 1 실패(`test_reencoded_ocr_cache_without_provenance_stops`, 11/21부터. Windows 경로 구분자).
- 백엔드 전체(`pypdfium2`가 없어 수집 안 되는 3개 파일 제외): 1159 통과, 1940 건너뜀(DB 필요), 실패 0.
- 회귀 15장(`ai/regression/regression.py`): 통과.

### 남은 것

- **흔들리는 테스트**: `ai/eval/test_i3_match_eval.py::test_server_steps_add_candidates_and_never_confirm`가 0단계 첫 실행에서 한 번 실패하고 이후 6번은 통과했다. 원인 모름.
- **하네스가 추출 연수를 넘기지 않는다.** 서버는 `extracted_age_years`를 매칭에 넘겨 별칭 확정에도 연수 불일치를 본다. 라벨 입력 평가는 이것을 못 본다(1a의 2줄). `i5_p59_with_age.py`는 줄 이름에서 읽은 연수로 대신한 측정용이다. e2e(추출 입력)에서는 추출 기록의 `age_years`를 넘기는 쪽이 서버와 같다.
- **"14yr"의 `yr`을 연수 단위로 읽지 않는다**(`staged._AGE_WITH_UNIT`). 후보는 나오지만 확인 권장 표시가 안 붙는다. 규칙 수정이라 하지 않았다.
- **The Original의 옛 연수 별칭**(`Glenmorangie 10`, `글렌모렌지10`, 템플릿 `... Aged 10 Years`, `글렌모렌지 오리지널 10년 숙성`)이 남아 있다. 이 별칭으로 찾은 줄은 추출이 10을 넘기면 확정되지 않는다. 지울지(옛 병을 다른 상품으로 둘지)는 정하지 않았다.
- **Nectar D'Or 이름**: 메뉴는 "더 넥타"로 적는다. 1a에서 사라진 확정 1줄의 원인이다(진우가 정할 것 1-나).
- **Lasanta 15**: 정답 2줄(018_청춘위스키 봉천_02, 017_리틀 갤러리_03)이 15년을 Lasanta로 적었다(진우가 정할 것 1-다). 본 셋에서 본 것.
- 운영 DB 카탈로그 적재, 평가 스냅샷(`catalog_v2_eval_5bars*.json`)은 그대로.
- 1b의 좁은 변형은 제안만 했다.
- 1a·1b 절의 줄 목록은 I3(본 셋)을 보고 정리한 것이다. 이것을 보고 규칙·카탈로그·정답을 고치지 않았다.

### AI 사용 내역

- 맡긴 일(Claude Code, 진우 자는 동안): 0단계 커밋 나누기(hunk 단위)·rebase·테스트, 1a 카탈로그 수정과 전후 비교 스크립트(`i5_p59_compare.py`)·연수 넘기는 래퍼(`i5_p59_with_age.py`), 1b 가드 구현(백엔드·하네스·설정·문서)과 측정, 1c 스캔(`i5_p59_age_only.py`)과 테스트, 3단계 준비, 이 보고서와 PR 초안(`pr_draft.md`).
- 검증한 것: 0단계 기대값 4개, 1b 꺼짐 결과 = 1a 결과(서버 줄 전체 일치), 1b를 v2.4로도 재서 1a 효과 분리, 1a 바뀐 줄의 원인을 규칙 근거(`rule`, evidence)로 확인, OCR 캐시 33장 `--check`, 새 코드 단위 테스트와 커버리지(새 스크립트 합 96%, `linking_guards.py` 100%).
- 검증하지 못한 것: 서버 경로에서 `MATCHING_MISSING_AGE_GUARD=true`로 실제 메뉴 등록(DB 필요 테스트는 건너뜀), 백로그 원문(이 컴퓨터에 없음), 글렌모렌지 연수 값 자체(웹 검색 안 함).
- 호출: Gemini 0, OpenRouter 0, CLOVA 0.
- 시간: 시계 기준 02:11 ~ 02:50 무렵.

## 낮 실행 (2026-11-27 14시~)

지시: `_outgoing/i5_matching_finish_handoff.md`. 진우 결정 세 가지(받아 주는 연수, 가드 꺼진 채, 1c 해석 맞음)를 반영했다. 시작 전 확인: P19 PR 정리는 다른 폴더(`swpp-p19-openrouter`)에서 끝났고 이 폴더는 추적 파일 수정이 없었다(진우 확인, `git status`로 다시 봄). 로컬 커밋만, push·PR 생성 없음.

### 낮 1단계: 받아 주는 연수 (API 0회)

**저장 위치.** 서버는 운영 DB의 상품 행만 읽는다(`DbCatalog`, `CatalogSnapshot`). 카탈로그 JSON에 필드를 두면 DB 컬럼(스키마 변경)이 있어야 서버에 닿는다. 대신 DB 행의 id는 `seed_catalog.py`가 `catalog_v2_service.json`의 id 그대로 넣으므로(id로 upsert), **매칭 모듈 안의 작은 표**(`backend/app/matching/accepted_ages.py`, 상품 id → 옛 연수)로 두었다. DB 스키마와 API 응답은 바꾸지 않았다. 해울에게 넘길 것은 없다.

| 상품 | 대표 연수 (`age_years`) | 받아 주는 연수 |
|---|---|---|
| Glenmorangie The Original | 12 | 10 |
| Glenmorangie Lasanta | **15** (v2.5의 12 → 고침) | 12 |
| Glenmorangie Quinta Ruban | 14 | 12 |
| Glenmorangie Nectar D'Or | 16 | 없음 |

**구현.**

- `ProductInfo.accepted_ages`(기본 빈 값)와 `fits_age(age)`. 카탈로그 셋(`DbCatalog.get_product`, `CatalogSnapshot`, `InMemoryCatalog.from_seed`)과 평가 하네스(`i3_match_eval.build_catalog`)가 표에서 채운다. 하네스는 표가 없는 옛 규칙 코드(`--rules-repo`)에서는 채우지 않는다.
- 연수를 비교하는 곳 여섯 군데가 `fits_age`를 쓴다: 별칭 확정의 연수 비교(`resolve._compare_attributes`, 추출 연수), 브랜드 + 연수 단계(`staged._narrow_brand`, 줄 연수 또는 추출 연수), 업주가 고른 상품 검사(`pick_check`의 `ageConflict`와 같은 연수 상품 묶음), `incompleteName` 가드의 `age_only`(측정용, 꺼짐), LLM 층의 `age_mismatch` 거부와 토큰 찾기(`llm_layer`).
- 근거: 받아 주는 연수로 맞으면 `ageAccepted: <연수>`. 별칭 확정에서는 `ageExact` 대신, 브랜드 + 연수 단계에서는 `ageMatch`와 함께 붙는다.
- 카탈로그 `catalog_v2_6_service`: Lasanta `age_years` 12 → 15만 바꿨다. README 17장. 옛 연수 별칭(`Glenmorangie 10`, `글렌모렌지10` 등)은 그대로 두었다.
- 하지 않은 것: `ai/eval/match_eval.py`의 `load_catalog`(P47 이전 하네스, I3 동결 파일)는 받아 주는 연수를 채우지 않는다. 고치면 P30 동결 해제 목록에 넣어야 해서 그대로 두었다. 지금 쓰는 실행(`i3_match_eval.py`, 회귀)은 이 함수를 쓰지 않는다.

**처음 잰 결과는 틀렸다.** 하네스가 `ProductInfo`를 직접 만들어 받아 주는 연수가 비어 있었다(I3 "글렌모렌지 12 라산타"가 틀린 후보로 바뀌어 Top-1 500 → 499로 나옴). 원인이 하네스 쪽임을 확인하고 하네스가 표를 채우게 고친 뒤 다시 쟀다. 아래가 고친 뒤 결과다. 규칙·정답·카탈로그는 결과를 보고 고치지 않았다.

**전후 비교 (v2.5 → v2.6, 규칙만 + 서버 단계, API 0회).** 기준(v2.5)은 1단계 커밋 전 HEAD(`5aea7246`, 옛 `d0b692d6`, `a20b6fec`)에서 다시 쟀고 밤 결과(`step1/1b_off_*`, `age_1a_*`)와 줄 단위로 같았다. 줄별 표는 `day_step1/{name,age}_*_diff.md`.

| | 바뀐 줄 | Top-1 | FM | 틀린 확인 권장 | hard/photo (규칙 / 서버 뒤) | confirm/choose/register/wrong (서버 뒤) |
|---|---|---|---|---|---|---|
| dev, 줄 이름만 | 1 | 626 → 627 / 804 | 0 → 0 | 3 → 3 | 4.14 → 4.10 / 3.79 → 3.76 | 100/83/18/9 → 100/82/18/9 |
| dev, 연수 넘김 | 1 | 626 → 627 / 804 | 0 → 0 | 3 → 3 | 4.14 → 4.10 / 3.79 → 3.76 | 100/84/18/8 → 100/83/18/8 |
| I3 full, 줄 이름만 | 2 | 500 → 500 / 646 | 1 → 1 | 2 → 2 | 2.85 → 2.82 / 2.39 → 2.36 | 87/53/14/12 → 88/52/14/12 |
| I3 full, 연수 넘김 | 4 | 498 → 500 / 646 | 1 → 1 | 2 → 2 | 2.85 → 2.82 / 2.39 → 2.36 | 89/53/14/12 → 88/52/14/12 |
| I3 ops, 줄 이름만 | 2 | 511 → 511 / 646 | 1 → 1 | 2 → 2 | 2.42 → 2.39 / 1.97 → 1.94 | 90/54/8/3 → 91/53/8/3 |
| I3 ops, 연수 넘김 | 4 | 509 → 511 / 646 | 1 → 1 | 2 → 2 | 2.42 → 2.39 / 1.97 → 1.94 | 92/54/8/3 → 91/53/8/3 |

- "연수 넘김"은 `i5_p59_with_age.py`(줄 이름의 연수를 추출 연수로 넘김, 서버가 하는 것의 대용)다.
- **사라진 맞는 확정 0, 새 틀린 확정 0.** 연수를 넘겨도 v2.4(밤 1a 전)의 I3 Top-1(full 500, ops 511)으로 돌아왔다.

꼭 볼 줄 (I3는 full·ops 같음):

| 줄 | 기대 | 결과 |
|---|---|---|
| 020_네스트_02 글렌모렌지 오리지날 10년 | 연수를 넘겨도 확정 | **확정, 맞음** (별칭, `ageAccepted: 10`). 줄 이름만 넘기면 전처럼 확정 |
| 018_청춘위스키 봉천_02 글렌모렌지 라산타 15Y | 연수를 넘겨도 확정 | **확정, 맞음** (이제 대표 연수 15와 같음) |
| 015_연림 서울대입구역점_04 글렌모렌지 12 라산타 | 확정 그대로 | 확정 그대로 (S2, `ageAccepted: 12`) |
| 017_리틀 갤러리_03 글렌모렌지 15년 / Glenmorangie 15yr | 후보 없음 → Lasanta 후보 | 후보 1개 = Lasanta (규칙: 후보 없음 → 1개, 서버 뒤: 임베딩 후보 고르기 → 1개) |
| 017_리틀 갤러리_03 글랜모랜지 14년 / 16년 | 정답 후보 1개 그대로 | 그대로 |
| 016_연림 봉천역점_03 글렌모렌지 12 | 후보 여러 개 (Original 포함) | 고르기 4개: The Original, 12 Calvados, Lasanta, Quinta Ruban (v2.5는 Quinta Ruban 없이 3개) |

- 기대에 없던 줄: dev `011_미라보_04 글렌모렌지(Glenmorangie) 15년 라산타`가 후보 없음(서버 뒤 고르기) → **확정, 맞음**.
- "018_청춘위스키 봉천_02 글렌모렌지 더 넥타 16Y"는 그대로(후보 1개 + 확인 권장). 고치지 않았다(남은 것).
- 회귀 15장(`ai/regression/regression.py`): 통과, 기준과 다른 줄 없음.
- **본 셋에서 고침:** 글렌모렌지 연수(밤 1a, 낮 v2.6·받아 주는 연수)는 I3(본 셋)의 줄을 보고 정한 것이다. I3 숫자는 이 수정의 영향을 받은 값이다.

**테스트.**

- 새 `backend/tests/test_accepted_ages.py` 26개: `fits_age`, 추출 연수가 받아 주는 연수·대표 연수일 때 별칭 확정(근거 `ageAccepted`/`ageExact`), 둘 다 아닌 연수는 `ageConflict`, 추출 연수만 있을 때 S2, 줄 연수 3가지, 브랜드 + 연수 후보("글렌모렌지 12" 4개, 근거가 붙는 상품은 Lasanta·Quinta Ruban), 한 상품만 받는 연수(15, 10), 아무도 안 받는 연수(11), **받아 주는 연수가 없는 상품의 줄 6가지는 표가 없을 때와 결과가 같음**, `pick_check` 2개, `incompleteName` 1개, LLM 층 거부 1개, 표와 카탈로그 파일의 연수, DB 두 카탈로그(`DbCatalog`·`CatalogSnapshot`)가 표를 채우는지 1개(DB 필요, 이 환경에서는 건너뜀).
- `ai/eval/test_i5_p59.py`: v2.5 연수 테스트를 v2.6으로(Lasanta 15), 하네스 카탈로그의 받아 주는 연수, 옛 규칙 코드에서 비우는 경우. `test_i3_match_eval.py`: I3 asis digest 고정값 v2.5 `541fb3d4…` → v2.6 `7f96c66a…`.
- 결과: 백엔드 1184 통과, 1941 건너뜀(DB 필요), 실패 0(`pypdfium2`가 없어 수집 안 되는 3개 파일 제외, 밤과 같음). `ai` 전체 394개 중 393 통과, 1 실패는 11/21부터의 `test_reencoded_ocr_cache_without_provenance_stops`(Windows 경로 구분자).
- 커버리지(분기 포함): `accepted_ages.py`, `types.py`, `pick_check.py`, `linking_guards.py`, `llm_layer.py` 100%. `resolve.py` 94.9%, `staged.py` 97.9%, `memory_catalog.py` 96.1%이고 빠진 줄은 이번에 바꾼 줄이 아니다. `db_catalog.py`는 DB 테스트가 건너뛰어 23.6%(밤과 같음).

커밋: `82ca8011` (옛 `34fca19e`, `2eb17f37`).

### 낮 2단계: 매칭 재평가 (Gemini 무료 키 14회)

1단계 커밋 상태(가드 꺼짐, 카탈로그 v2.6)로 밤 보고서 2단계 절의 명령을 그대로 돌렸다(`--max-calls`만 20). 먼저 `--cache-only`로 새로 부를 요청을 셌다(dev 회차마다 1, I3 회차·구성마다 2, 합 14). 실제 새 호출도 14회(`gemini-3.1-flash-lite`, thinking low, 모두 첫 시도에 응답). 캐시는 `cache_dev_r*`, `cache_{full,ops}_label_r*`, 결과는 `match/*.json`(큰 JSON이라 커밋 안 함).

서버 단계 뒤(규칙 + M3a + 임베딩 + 연결 가드), 라벨 입력, 줄 이름만 넘기는 하네스:

| 실행 | Top-1 | FM | 틀린 확인 권장 | hard/photo | confirm/choose/register/wrong | "위스키 아님" 표시: 비위스키 맞게 · 위스키 잘못 · 미상 |
|---|---|---|---|---|---|---|
| dev r1 11/21 (v2.4) | 625/804 | 0 | 3 | 2.69 | 133/54/18/6 | 16/16 · 0/179 · 0/16 |
| dev r1 **오늘 (v2.6)** | **627/804** | 0 | 3 | **2.59** | 134/52/18/5 | 16/16 · 0/177 · 0/16 |
| dev r2 11/21 | 625/804 | 0 | 3 | 2.66 | 134/53/18/6 | 16/16 · 0/179 · 0/16 |
| dev r2 **오늘** | **627/804** | 0 | 3 | **2.55** | 135/51/18/5 | 16/16 · 0/177 · 0/16 |
| I3 full r1 P46 (v2.3) = 11/21 (v2.4) | 500/646 | 1 | 3 | 1.67 | 111/41/8/6 | 11/21: 4/4 · 0/138 · 0/24 |
| I3 full r1 **오늘** | 500/646 | 1 | **2** | **1.55** | 115/40/8/3 | 4/4 · 0/138 · 0/24 |
| I3 full r2 P46 = 11/21 | 500/646 | 1 | 3 | 1.67 | 111/41/9/5 | 11/21: 4/4 · 0/138 · 0/24 |
| I3 full r2 **오늘** | 500/646 | 1 | **2** | **1.55** | 115/40/9/2 | 4/4 · 0/138 · 0/24 |
| I3 full r3 P46 = 11/21 | 500/646 | 1 | 5 | 1.70 | 110/41/9/6 | 11/21: 4/4 · 0/138 · 0/24 |
| I3 full r3 **오늘** | 500/646 | 1 | **4** | **1.58** | 114/40/9/3 | 4/4 · 0/138 · 0/24 |
| I3 ops r1 P46 = 11/21 | 511/646 | 1 | 3 | 1.58 | 103/39/8/5 | 11/21: 4/4 · 0/127 · 0/24 |
| I3 ops r1 **오늘** | 511/646 | 1 | **2** | **1.45** | 107/38/8/2 | 4/4 · 0/127 · 0/24 |
| I3 ops r2 P46 = 11/21 | 511/646 | 1 | 3 | 1.58 | 103/39/8/5 | 11/21: 4/4 · 0/127 · 0/24 |
| I3 ops r2 **오늘** | 511/646 | 1 | **2** | **1.45** | 107/38/8/2 | 4/4 · 0/127 · 0/24 |
| I3 ops r3 P46 = 11/21 | 511/646 | 1 | 3 | 1.61 | 102/40/8/5 | 11/21: 4/4 · 0/127 · 0/24 |
| I3 ops r3 **오늘** | 511/646 | 1 | **2** | **1.48** | 106/39/8/2 | 4/4 · 0/127 · 0/24 |

- P46(I4, 11/17, 카탈로그 v2.3, 표시 없음)과 11/21(v2.4, `--flag-non-whisky`)은 I3에서 숫자가 모두 같다. dev는 P46 실행이 없다.
- **FM은 그대로 1(Ardbeg Anthology), 새 틀린 확정 0.** Top-1은 I3 그대로, dev +2. 틀린 확인 권장은 I3에서 회차마다 1 줄고, 사진당 어려운 줄은 I3 0.12~0.13, dev 0.10~0.11 줄었다.
- "위스키 아님" 표시(플래그 켬, LLM이 `non_whisky`이고 규칙 후보 0일 때)는 11/21과 같다. dev의 위스키 LLM 대상이 179 → 177인 것은 글렌모렌지 2줄이 이제 규칙에서 확정되어 LLM에 가지 않기 때문이다.
- 11/21과 줄 단위로 바뀐 것(r1, `day_step2/vs1121_*_diff.md`)은 모두 글렌모렌지 줄이다. I3 full r1 6줄: 맞는 확정 +1("12 라산타"), −1("더 넥타 16Y" → 후보 1개 + 확인 권장), 틀린 후보 → 정답 후보 1개 + 확인 권장("14yr"), 고르기 → 후보 1개("15yr", "16yr"), 틀린 확인 권장 → 고르기("글렌모렌지 12"). dev r1 3줄: "12년 오리지널"·"15년 라산타" 확정, "16년 더 넥타" 고르기 → 후보 1개.
- 하네스는 줄 이름만 넘긴다(추출 연수 없음). 연수를 넘기는 경우는 1단계 표("연수 넘김")에서 봤고, v2.6에서는 I3 Top-1이 줄 이름만 넘길 때와 같다.
- **본 셋에서 고침:** I3의 위 변화는 I3를 보고 고친 글렌모렌지 연수 때문이다.
- 호출 상한(200)에 닿지 않았다. 안 돌린 실행은 없다.

### 낮 3단계: 보고서, PR 초안

- 이 절, 맨 위 "진우가 정할 것" 갱신, `pr_draft.md`(영문) 갱신, `ai/runs/ai_usage_log.md`.
- 끝까지 추출부터 다시 재는 실험(OpenRouter 약 $0.92/회)은 실행하지 않았다. OpenRouter PR이 main에 들어간 뒤의 일이다(밤 3단계 절).

### 낮 실행 호출 수

**Gemini 14회**(무료 키, dev 2 + I3 12), **OpenRouter 0회, CLOVA 0회.** push·PR 생성 없음.

### 남은 것 (낮)

- **Nectar D'Or 이름 (제안만, 고치지 않음).** "글렌모렌지 더 넥타 16Y"는 S2가 Nectar D'Or(16)를 찾지만 상품 에디션 "Nectar D'Or"의 "dor"가 줄에 없어 확인 권장으로 낮춘다(`editionOnlyInProduct`). 병 이름이 "The Nectar"로 바뀌었으므로:
  - (가) **에디션 이름을 "The Nectar"로, 표시명을 "Glenmorangie The Nectar"로 바꾸고 "Nectar D'Or"·"넥타도르" 표기는 별칭으로 남긴다.** 상품 id는 그대로라 매장 메뉴 연결은 유지된다. "더 넥타 16Y"가 이것으로 확정되는지(한글 "넥타"가 어휘표로 nectar가 되는지)는 재 보지 않았다. 옛 병 메뉴의 "넥타도르" 줄은 별칭으로 계속 확정된다.
  - (나) 에디션은 그대로 두고 메뉴 표기 별칭("글렌모렌지 더 넥타 16Y"류)을 더한다. 이 매장 표기만 고쳐지고 다른 표기("The Nectar 16yo")는 그대로다.
  - 권고는 (가). 지금 병 이름에 맞추는 것이라 다른 매장에도 통한다. 카탈로그 상품 수정이라 진우 결정이 필요하다.
- **흔들리는 테스트**(밤 "남은 것"): 낮에 돌린 ai 테스트(실패 목록을 본 4번)에서는 `test_server_steps_add_candidates_and_never_confirm`가 실패하지 않았다.
- **"14yr"의 `yr`**을 연수 단위로 읽지 않는 것(밤과 같음). 규칙만으로는 확인 권장 표시가 안 붙고, LLM 층 뒤에는 붙는다(`confirm CR`).
- `match_eval.load_catalog`(옛 하네스)는 받아 주는 연수를 채우지 않는다(위 1단계).
- 운영 DB 카탈로그 적재(Seed catalog 워크플로)는 하지 않았다. 적재하면 Lasanta `age_years`가 15가 된다. 받아 주는 연수는 코드라 배포만 하면 된다.
- 확인 못 한 것: DB가 필요한 테스트(새 1개 포함), 서버 메뉴 등록 경로에서 실제 추출 연수로 확인, 연수 값 자체(진우가 준 값, 웹 확인 안 함).

### AI 사용 내역 (낮)

- 맡긴 일(Claude Code): 서버의 카탈로그 적재 경로 확인과 저장 위치 결정, 받아 주는 연수 구현(매칭 모듈 9개 파일, 하네스), 카탈로그 v2.6과 README, 테스트, v2.5 기준 재측정과 전후 비교, Gemini 재평가 8회 실행, 이 절과 PR 초안.
- 검증한 것: v2.5 기준 = 밤 결과(줄 단위 0줄 차이), 처음 측정이 하네스 문제로 틀린 것을 줄 결과로 찾아 고침, 꼭 볼 줄 6개를 결과 JSON의 줄에서 확인, `--cache-only`로 예상 호출 수를 먼저 세고 실제 호출 수(캐시 기록의 시도 수)와 대조, 11/21과 줄 단위 비교, P30 동결 검사(옛 하네스를 고치지 않아 동결 해제 목록은 그대로), 회귀 15장.
- 시간: 시계 기준 14:05 ~ 14:50 무렵.

### 낮 추가: Nectar D'Or 이름 (catalog v2.7, API 0회)

진우 결정("남은 것"의 (가), 2026-11-27): `glenmorangie-nectar-dor`의 표시명을 `Glenmorangie The Nectar`, 에디션을 `The Nectar`로 바꿨다. key·id·별칭은 그대로다(옛 이름 `Glenmorangie Nectar D'Or`, `글렌모렌지 넥타도르` 등은 별칭으로 남고, `Glenmorangie The Nectar` 별칭은 원래 있었다). README 18장.

**결과: 매칭 상태가 바뀐 줄 0.**

- 규칙만 + 서버 단계(줄 이름만, 연수 넘김 둘 다, dev·I3 full·ops): Top-1, FM, 틀린 확인 권장, 업주 부담 모두 v2.6과 같다. 비교 스크립트가 "바뀐 줄"로 세는 것은 후보 표시명 글자("Nectar D'Or" → "The Nectar")뿐이다(`day_nectar/*_diff.md`, 상태·판정·업주 부담은 모든 줄이 같음).
- M3a 재평가 8회를 같은 캐시로 다시 채점했다(`--cache-only`, **새 호출 0회**, `day_nectar/match/`). 규칙·LLM·서버 단계 모두 v2.6 결과와 줄 단위로 같다.
- 회귀 15장 통과. 테스트: 고정값 2개(I3 asis digest v2.7 `1a4e2469…`, 카탈로그 버전·이름 테스트)를 고쳤고, 백엔드 1184 통과, `ai/eval` + `ai/regression` 284 중 283(이전부터의 1개).

**"글렌모렌지 더 넥타 16Y"는 여전히 후보 1개 + 확인 권장이다. 낮추는 이유가 바뀌었다.**

- v2.6: S2가 Nectar D'Or를 찾았지만 에디션 "Nectar D'Or"의 "dor"가 줄에 없어 낮춤(`editionOnlyInProduct`).
- v2.7: 그 이유는 없어졌다. 대신 줄의 "더"가 어느 상품에도 맞지 않는 일반어로 빠지고, 나머지("넥타")로 고른 상품은 확정하지 않는 I4 규칙(`ignoredWords`, `confirmRecommended`)에 걸린다. 같은 상품의 "글렌모렌지 더넥타 16년"(붙여 씀, S2 확정), "글렌모렌지 16 더 넥타"(별칭), "글렌모렌지 더 넥타"(별칭)는 전처럼 확정된다.
- 이 줄을 확정하게 하려면 (나) 메뉴 표기 별칭 "글렌모렌지 더 넥타 16Y"(정규화 `글렌모렌지더넥타16`)를 더하거나, (다) 일반어 규칙에서 "더"처럼 에디션 이름 안의 관사("The Nectar"의 "The")로 맞는 단어는 일반어로 빼지 않게 규칙을 바꿔야 한다. (나)는 이 매장 표기 하나만 고친다. (다)는 규칙 변경이라 dev·I3 전체를 다시 재야 한다. 둘 다 하지 않았다.

### 낮 추가 2: 에디션 이름의 관사 규칙 (규칙 수정, Gemini 18회)

진우 결정("낮 추가"의 (다), 2026-11-27). **규칙:** 줄의 관사(`the`, `더`)는 에디션 이름에 "The"가 있는 상품에서, 같은 줄의 다른 토큰도 그 상품에 맞을 때 에디션 이름의 일부로 맞는다(`staged._has_article`, `_narrow_brand`). 일반어로 빠지지 않으니 I4의 "빼고 고르면 확정하지 않음"에 걸리지 않는다.

- 처음에는 "관사는 에디션에 The가 있는 상품에 언제나 맞음"으로 넣었다. 테스트를 쓰다 "글렌모렌지 더 시그넷"에서 "더"가 The Nectar에도 맞아 Signet 하나를 권하던 줄에 The Nectar가 후보로 붙는 것을 찾아 "다른 토큰도 맞을 때만"으로 좁혔다. dev·I3 결과는 두 형태가 같았다(아래 숫자는 좁힌 것).

**규칙만 + 서버 단계 (v2.7 → 관사 규칙, API 0회, `day_article/{name,age}_*_diff.md`)**

| | 바뀐 줄 | Top-1 | FM | 틀린 확인 권장 | hard/photo (규칙 / 서버 뒤) | confirm/choose/register/wrong (서버 뒤) |
|---|---|---|---|---|---|---|
| dev | 3 | 627 → 630 / 804 | 0 → 0 | 3 → 3 | 4.10 / 3.76 그대로 | 100/82/18/9 → 97/82/18/9 |
| I3 full | 2 | 500 → 502 / 646 | 1 → 1 | 2 → 2 | 2.82 / 2.36 그대로 | 88/52/14/12 → 86/52/14/12 |
| I3 ops | 2 | 511 → 513 / 646 | 1 → 1 | 2 → 2 | 2.39 / 1.94 그대로 | 91/53/8/3 → 89/53/8/3 |

연수를 넘기는 측정(`i5_p59_with_age.py`)도 같은 줄, 같은 증가다. **사라진 맞는 확정 0, 새 틀린 확정 0.** 바뀐 줄은 모두 확인 권장(confirm) → 맞는 확정이다.

| 셋 | 줄 | 정답 |
|---|---|---|
| I3 | 018_청춘위스키 봉천_02 글렌모렌지 더 넥타 16Y | The Nectar |
| I3 | 018_청춘위스키 봉천_01 브룩라디 더 클래식 | Bruichladdich The Classic Laddie Scottish Barley |
| dev | 011_미라보_04 글렌모렌지(Glenmorangie) 16년 더 넥타 | The Nectar |
| dev | 010_수이_03 Glenmorangie The Nectar (더 넥타) | The Nectar |
| dev | 009_오드비_08 글렌모렌지 더 넥타 | The Nectar |

(dev는 `service` 카탈로그라 그 매장의 메뉴 표기 별칭이 빠져 있어, 별칭으로 확정되던 dev 줄도 규칙으로 잰다.)

**M3a 재평가 (같은 구성 8회, 새 호출 18회: dev 3 × 2, I3 2 × 6, 모두 첫 시도).** 규칙에서 확정된 줄이 LLM 대상에서 빠져 그 사진의 M3a 입력이 바뀌었기 때문이다. 결과 `day_article/match/`.

| 실행 | Top-1 | FM | 틀린 확인 권장 | hard/photo | confirm/choose/register/wrong | "위스키 아님" 표시 |
|---|---|---|---|---|---|---|
| dev r1 / r2 | 630/804 (+3) | 0 | 3 / 3 | 2.59 / 2.55 | 131/52/18/5, 132/51/18/5 | 16/16 · 0/174 · 0/16 |
| I3 full r1 / r2 / r3 | 502/646 (+2) | 1 | 2 / 2 / 4 | 1.55 / 1.55 / 1.58 | 113/40/8/3, 113/40/9/2, 112/40/9/3 | 4/4 · 0/136 · 0/24 |
| I3 ops r1 / r2 / r3 | 513/646 (+2) | 1 | 2 / 2 / 2 | 1.45 / 1.45 / 1.48 | 105/38/8/2, 105/38/8/2, 104/39/8/2 | 4/4 · 0/125 · 0/24 |

- v2.6 낮 2단계 표와 비교하면 Top-1만 늘고 FM, 틀린 확인 권장, 사진당 어려운 줄, "위스키 아님" 표시는 같다(위스키 LLM 대상이 2~3줄 준 것은 그 줄들이 규칙에서 확정되기 때문).
- 위 5줄 밖에서 바뀐 줄은 I3 full r3·ops r1·ops r3의 "018_청춘위스키 봉천_01 브룩라디 포트샬롯" 하나다. 같은 사진의 "더 클래식"이 LLM 대상에서 빠져 M3a 입력이 바뀌었고, 새 응답의 후보 목록이 달라졌다(고르기, 정답 포함은 그대로). 규칙 때문이 아니라 LLM 응답 차이다.
- **본 셋에서 고침:** "더 넥타 16Y"는 I3 줄이다. I3 +2는 이 수정의 영향을 받은 값이다.

**테스트.** `backend/tests/test_resolve_staged.py`에 5개: 관사가 에디션 이름의 일부로 맞음 3가지("더 넥타 16Y", "더 넥타", "더 오리지널 12년"), 관사 없는 상품을 가리키는 줄은 전처럼 일반어로 빠짐("더 시그넷" → Signet 권장, `ignoredWords: ["더"]`), 관사만 있는 줄은 아무것도 고르지 않음. 백엔드 1189 통과, 1941 건너뜀, 실패 0. `ai` 394 중 393(이전부터의 1개). 회귀 15장 통과. 문서: `docs/menu_ai_matching_flow.md`에 관사 규칙(I4 일반 단어 문단 뒤)과 받아 주는 연수(10.1장) 두 문단.

**호출:** Gemini 18회(낮 합계 32회), OpenRouter 0, CLOVA 0.

## 히스토리 정리 (2026-11-27 낮, push 없음)

이 절의 해시는 정리 직후의 것이다. 지금 해시는 아래 표의 "rebase 뒤" 열이다.

`origin/main..HEAD`의 각 커밋에서 `ai/runs` 아래 `.md`가 아닌 실행 기록을 걷어냈다(OpenRouter 브랜치와 같은 방식). 디스크의 파일은 지우지 않았다.

- **정리 전 상태:** 브랜치 `backup/i5-m3a-before-rewrite`(= 옛 `fa402fc9`). push하지 않는다.
- **걷어낸 것:** M3a 응답 캐시 308개(`2026-11-21_i5_not_whisky/cache_dev_r1·r2`, `2026-11-27_i5_p31/cache_{dev_r1,dev_r2,full_label_r1~r3,ops_label_r1~r3}`). 모두 이 브랜치에서 새로 더한 파일이라, main에 있던 파일을 되돌린 것은 없다.
- **남긴 것:** `ai/runs/2026-11-21_i5_not_whisky/mixed_report.json`. 실행 기록이 아니라 `ai/regression/test_mixed_report.py`가 비교하는 기대 결과다(진우 결정 (A)).
- **방법:** 임시 브랜치에서 `git filter-branch --index-filter`(위 캐시 폴더만 `git rm --cached`), 빈 커밋 정리 없음. 그 뒤 체크아웃된 브랜치를 `git reset --mixed`로 옮겨 작업 폴더를 건드리지 않았다. 커밋 순서, 메시지, 작성자·커미터와 날짜는 그대로다(옛·새 로그를 비교해 같음을 확인). 메시지에 "dev M3a caches"(`491d4057`), "keeps the M3a caches"(`42576ffe`)라고 적힌 것도 지시대로 그대로 두었다.
- **`.gitignore`:** `/ai/runs/2026-11-21_i5_not_whisky/**/*.{json,jsonl,log,txt}`, 같은 형태의 `2026-11-27_i5_p31`, 예외 `!/ai/runs/2026-11-21_i5_not_whisky/mixed_report.json`(커밋 `fc569125`).

| 옛 해시 | 정리 뒤 | rebase 뒤 (#221 위) | 커밋 |
|---|---|---|---|
| `c70bad06` | `c70bad06` (같음) | `9e1d3c89` | I5: Add Jack Daniel's Tennessee Apple to catalog v2.4 and score it as a whisky |
| `8fffff10` | `8fffff10` (같음) | `b52114ad` | I5: Let the LLM layer note a line it reads as not a whisky (flag off by default) |
| `1854938d` | `1854938d` (같음) | `1a7ebc76` | I5: Measure the not-whisky note in the matching harness (--flag-non-whisky) |
| `73bac2a6` | `491d4057` | `b8208a2b` | I5: Record the not-whisky work (report, kind tables, dev M3a caches, AI usage) |
| `79da3c30` | `95d7af06` | `9b219628` | I5-P59: Set the current Glenmorangie ages in catalog v2.5 |
| `6b2700c8` | `fcd3cb78` | `4f31fd63` | I5-P59: Add the missingAge linking guard for confirmed lines without an age (off by default) |
| `f92b7c3f` | `bf4a5895` | `4a3f44aa` | I5-P59: Pin how brand + age only lines are matched, and scan them |
| `d0b692d6` | `a20b6fec` | `5aea7246` | I5-P59: Report the night run (steps 0-4), the PR draft and the AI usage |
| `34fca19e` | `2eb17f37` | `82ca8011` | I5-P59: Accept the older Glenmorangie ages and set Lasanta to 15 (catalog v2.6) |
| `47b2b727` | `42576ffe` | `bb7803c4` | I5-P31: Re-run the matching evaluation on catalog v2.6, report the day run and the PR draft |
| `8ad7c2e5` | `855979b9` | `92a65584` | I5-P59: Name Glenmorangie Nectar D'Or after its current bottle, The Nectar (catalog v2.7) |
| `fa402fc9` | `a296fb95` | `44294cda` | I5-P59: Let an article of the edition name fit the product ("더 넥타" -> The Nectar) |
| (새) | `fc569125` | `2d79211b` | I5: Keep the run records of the matching runs on the runner's PC |
| (정리 뒤 커밋) | `b6c0f2e9` | `22054b45` | I5-P59: Point the report at the rewritten commits and redo the PR draft on the template |
| (정리 뒤 커밋) | `affaac19` | `527c7ccc` | I5-P59: Record in the PR draft that the Glenmorangie ages and name were checked |
| (정리 뒤 커밋) | `54fc4d0f` | `10a0f700` | I5-P59: Fix three review findings in the measurement scripts |

앞의 세 커밋은 캐시가 없어 트리와 부모가 같으므로 해시가 그대로다.

**확인.**

- 히스토리(`origin/main..HEAD`)에서 `ai/runs` 아래 `.md`가 아닌 파일: `mixed_report.json` 1개(예외로 남긴 것)뿐.
- 최종 트리 vs `backup/i5-m3a-before-rewrite`: 다른 것은 캐시 308개(없음)와 `.gitignore`뿐.
- 깨끗한 checkout(`git worktree`, 실행 기록 없음)에서 테스트: 백엔드 1189 통과, 1941 건너뜀, 실패 0. `ai` 392 통과, 1 건너뜀(CLOVA 키 없음, 그 worktree에 `.env`가 없어서), 1 실패(11/21부터의 `test_reencoded_ocr_cache_without_provenance_stops`). 걷어낸 캐시를 읽는 테스트는 없다.
- 남은 추적 안 되는 파일 중 이 두 폴더의 것은 `step1/1c_age_only_before.md` 하나다(밤 실행에서 커밋하지 않은 것, 그대로 둠).
- `pr_draft.md`는 `.github/pull_request_template.md`의 절(Task and why, What changed, Contract and scope, Verification, Notes for reviewers, After merge)로 다시 썼고, 매칭 규칙 문서(`docs/menu_ai_matching_flow.md`)를 고친 것을 적었다.

## main 위로 rebase (2026-11-27 저녁, #221 머지 뒤)

OpenRouter 추출 PR(#221)이 main에 머지(`f3af49c6`)되어 PR #222가 충돌 상태가 됐다.

- Auto-fix 알림을 받고 먼저 `origin/main`을 merge해 push했다(`1b6ac4ed`). 진우 지시로 이를 rebase로 바꿨다. merge 커밋은 버리고, 브랜치 커밋 16개를 `origin/main` 위에 다시 올려 `--force-with-lease`(lease `1b6ac4ed`)로 push했다. push 직후 head는 `10a0f700`(리뷰 수정 커밋)였고, 이 해시 갱신 커밋이 그 위에 온다.
- **충돌:** `fc569125`(이제 `2d79211b`)의 `.gitignore` 하나. main의 실행 기록 블록(OpenRouter·fallback 폴더)을 먼저 두고 이 브랜치 블록을 뒤에 두어 양쪽을 다 남겼다. 다른 충돌은 없었다.
- **merge가 막힌 것:** 추적 안 되던 로컬 파일 5개가 main이 새로 넣는 경로와 겹쳤다. 작업 공간 `bottlemap-p14/_backup/untracked_before_merge_pr222/`로 옮겼다(3개는 main 것과 같고, `2026-11-21_i5_row_pairing/report.md`, `2026-11-27_direct_probe.md`는 다르다).
- **확인:**
  - 최종 트리가 merge 커밋 `1b6ac4ed`와 같다.
  - 커밋 수, 메시지, 작성자, 날짜는 rebase 전과 같고, merge 커밋은 없다.
  - `git check-ignore`로 보니 `mixed_report.json`은 추적되고, 두 브랜치의 실행 폴더 JSON은 무시된다.
  - 테스트: 백엔드 1363 통과, 1941 건너뜀, 실패 0. `test_pdf_*.py`, `test_edge_guard.py`, `test_run_uat_inputs.py`는 로컬에 `pypdfium2`가 없어 불러오지 못했고 CI가 돌린다. `ai`는 410 통과, 1 실패(원래 있던 `test_reencoded_ocr_cache_without_provenance_stops`).
- **백업:** rebase 전 상태는 로컬 브랜치 `backup/i5-m3a-before-rebase`(= `1b6ac4ed`)에 있다. push하지 않는다. 원격에 `backup/*` 브랜치는 없다.
