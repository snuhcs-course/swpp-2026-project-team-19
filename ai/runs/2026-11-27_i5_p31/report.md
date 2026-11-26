# I5-P59 매칭 규칙 수정 + I5-P31 매칭 재평가 (2026-11-27, 밤샘 실행)

지시: `_outgoing/i5_p31_p59_night_handoff.md`. 브랜치 `feature/i5-m3a-not-whisky`(로컬 커밋만, push 없음). 진우는 자는 중이라 질문 없이 진행했다.

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

## 진우가 정할 것

(4단계에서 채운다.)

## 0단계: 지금 상태 정리

### 0.1 커밋 나누기

11/21 "위스키 아님" 작업의 커밋 안 된 수정 19개를 네 커밋으로 나눴다(rebase 뒤 해시).

| 커밋 | 내용 |
|---|---|
| `c70bad06` | 카탈로그 v2.4(잭다니엘 애플), 오드비 정답 1줄, 하네스의 dev 예외 삭제, 회귀 fixture·baseline, 고정값 테스트(`test_review_states`, `test_mixed_report`, `test_i3_match_eval`의 digest·`gold_for`), P30 동결 해제 목록에 카탈로그, 정답 수정 후 `mixed_report.*` |
| `8fffff10` | `kind_hint`(`types.py`), `flag_non_whisky`(`llm_layer.py`), 임베딩 단계에서 유지(`embedding.py`), `menu_import_processing.py` 호출부, 백엔드 테스트 3개 파일, P30 동결 해제 목록에 `llm_layer.py` |
| `1854938d` | 하네스 `--flag-non-whisky`와 `not_whisky` 지표, 그 테스트, `ai/eval/i5_kind_table.py` |
| `73bac2a6` | 11/21 보고서, `kind_*.md`, dev M3a 캐시(`cache_dev_r1`, `cache_dev_r2`, 각 26개), `ai_usage_log.md` |

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
