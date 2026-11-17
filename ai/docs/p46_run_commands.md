# P46 실행 명령 (I4 동결셋 평가)

I4-P46: I3 동결셋(바 8곳, 사진 33장, `eval/labels_i3_v1.json` 978항목, `eval/match_gold_i3_v1.json` 675줄)에서 I4 코드를 잰다. 지표는 이름 F1(NFR-1), 가격 정확도(NFR-2), 매칭 Top-1(NFR-3), false merge(NFR-4)이고 기준과 정의는 I3와 같다(Testing Documentation 4.1).

## 0. 무엇을 재고 무엇을 재지 않나

| 대상 | I3 이후 바뀐 것 | P46에서 |
|---|---|---|
| 추출 프롬프트 v1 | 없음 (코드·프롬프트·모델 동일) | 다시 돌리지 않는다. P30 기록(2026-11-04)을 기준선으로 쓴다 |
| 추출 프롬프트 v2 (I4-P12) | 새로 생김 | r1–r3 실행 (Gemini 99회) |
| 매칭 규칙 `staged.py` | #158, P18 | 규칙 1회 (API 없음) |
| LLM 층 M3a | 없음 | r1–r3. I3와 같은 요청은 I3 캐시의 답을 쓴다 |
| 임베딩 후보·연결 가드·저장 상태 | 새로 생김 | `--server-steps`로 같이 잰다 |

- **이 셋은 더 이상 처음 보는 셋이 아니다.** I3 결과(P30)를 본 뒤 I4 작업을 했다. I4 규칙 수정은 dev 5곳(836줄)에서 남은 줄을 보고 일반 규칙으로 넣은 것이지만, I3 숫자와 그 오류 유형을 알고 있는 상태에서 한 작업이다. 새 바를 모을 시간이 없어 이 셋을 다시 쓴다(2026-11-09 결정). 보고할 때 이 문단을 같이 적는다.
- **카탈로그 세 가지.** `asis`·`full`은 I3와 바이트까지 같다(digest `7c65fa51…`, `633682b4…`): I3 숫자와 바로 비교한다. NFR-3은 `full`에서 판정한다. `ops`는 서버가 실제로 싣는 카탈로그(서비스 + `catalog_v2_service_i3_additions.json`)에서 그 바의 메뉴 표기 별칭을 뺀 것이다. 추가 상품 61개와 한국어 별칭은 I3 정답을 본 뒤 만든 것이라 `ops` 숫자는 "배포 카탈로그가 이 바들에서 내는 값"이고 처음 보는 바에 대한 측정이 아니다.
- **연림 두 지점은 한 바로 묶는다**(`BAR_GROUPS`): 같은 메뉴판이라 한 지점의 메뉴 표기 별칭이 다른 지점 평가에 남으면 안 된다. `ops`에서 별칭 2개가 이 규칙으로 빠진다. 서비스 카탈로그에는 I3 메뉴 출처 별칭이 없어 `asis`·`full`은 영향이 없다.
- **비위스키 줄.** `eval/mixed_lines_i3_v1.json`: 라벨이 빼 둔 비위스키 줄 14행(2장). 라벨에 이미 있는 non_whisky 6행과 합쳐 20행이다. 프롬프트 v2를 이 사진에 돌리기 **전에** 사진만 보고 만들었다. 20행뿐이라 개수로 보고한다. `"reviewed"`가 비어 있으면 `p46_extract.py`가 멈춘다.

결과를 본 뒤에는 코드·프롬프트·라벨·정답을 고쳐서 다시 재지 않는다. 고칠 것이 보이면 적어 두고 다음 평가셋으로 넘긴다.

## 1. 준비 (PowerShell, 레포 루트)

```powershell
git status --short            # 깨끗해야 한다
python -m pip install -r ai/requirements.txt   # sqlalchemy가 추가됨 (--server-steps)
python -m pytest ai/eval -q -p no:cacheprovider
$P  = "ai/runs/2026-11-17_p46"
$I3 = "..\_outgoing\p30_run\out"          # I3 실행 기록 (P10 캐시, P30 추출)
New-Item -ItemType Directory -Force "$P/match" | Out-Null
```

`GEMINI_API_KEY`는 레포 `.env`에서 읽는다(환경변수가 있으면 그것을 먼저 쓴다). 키는 출력하지 않는다.

## 2. 매칭, 라벨 입력

### 2.1 규칙만 (API 0회)

```powershell
foreach ($c in "asis","full","ops") {
  python ai/eval/i3_match_eval.py --set i3 --catalog $c --server-steps --json "$P/match/${c}_label_rules.json"
}
```

나와야 하는 값(2026-11-17, `a14d086` + 이 브랜치에서 확인). 다르면 멈추고 원인을 본다.

| 카탈로그 | digest | Top-1 | FM | I3 (C2 rules) |
|---|---|---|---|---|
| asis | `7c65fa51c4c8` | 472/564 | 1 | 470/564 |
| full | `633682b4ef2e` | 500/646 (0.774) | 1 | 498/646 (0.771) |
| ops | `23a66ea4c99f` | 511/646 (0.791) | 1 | 없음 |

LLM 층·임베딩·가드는 줄을 확정하지 않으므로 Top-1과 FM은 이 표에서 정해진다. 아래 실행은 후보의 질(확인 표시, 어려운 줄 수, 승인 오류율)을 잰다.

### 2.2 규칙 + M3a, r1–r3

요청은 (모델, thinking, 프롬프트, 줄 목록)으로 캐시된다. 규칙이 바뀌어 대상 줄이 달라진 사진만 새로 부르고, 나머지는 I3 r*k* 캐시의 답을 쓴다(`--seed-cache`). 새 호출은 회차마다 asis 2, full 2, ops 12회 안팎이다(합 약 48회).

```powershell
foreach ($r in 1,2,3) { foreach ($c in "asis","full","ops") {
  $s = if ($c -eq "ops") { "full" } else { $c }
  python ai/eval/i3_match_eval.py --set i3 --catalog $c --llm --cache "$P/cache_${c}_label_r$r" `
    --seed-cache "$I3/2026-10-29_p10/cache_c2_${s}_llm_r$r" --server-steps --max-calls 60 `
    --json "$P/match/${c}_label_llm_r$r.json"
} }
```

`LLM complete=True`가 아니면(할당량, 호출 상한) 같은 명령을 다시 돌린다. 캐시가 있어 빠진 요청만 보낸다.

## 3. 추출, 프롬프트 v2

```powershell
python ai/eval/p46_extract.py --out "$P/hybrid_v2_i3" --check      # API 0회: 사진 33장, OCR 캐시, 비위스키 줄 검수 여부
python ai/eval/p46_extract.py --out "$P/hybrid_v2_i3" --runs 1 2 3 --max-calls 100
python ai/eval/score.py --set i3 "$P/hybrid_v2_i3"
```

- CLOVA는 부르지 않는다. P30이 만든 OCR 캐시를 쓰므로 v1과 v2가 같은 OCR 줄을 읽는다.
- 답이 없는 호출(할당량, 네트워크)에서 멈추면 같은 명령을 다시 돌린다. 있는 기록은 그대로 두고 이어 간다.
- **33장 × 3회 기록이 모두 있을 때만 채점한다**(`score.py`는 빠진 사진을 빈 출력으로 센다): `(Get-ChildItem "$P/hybrid_v2_i3" -Filter "*_r?.json").Count`가 99.
- v1 기준선: `$I3/2026-10-30_p30/hybrid_i3/scores.json` (이름 F1 0.931, 가격 0.966, 항목 0.868).

## 4. 종단 매칭: v2 추출 r*k* ↔ M3a r*k*

`full`(판정, I3 종단과 비교)과 `ops`(배포 카탈로그). 사진마다 한 번씩 새로 부른다(회차·카탈로그당 31회 안팎, 합 약 190회). `asis`는 규칙만 돌린다.

```powershell
foreach ($r in 1,2,3) {
  foreach ($c in "full","ops") {
    python ai/eval/i3_match_eval.py --set i3 --catalog $c --extraction "$P/hybrid_v2_i3" --run $r --llm `
      --cache "$P/cache_${c}_e2e_r$r" --server-steps --max-calls 60 --json "$P/match/${c}_e2e_llm_r$r.json"
  }
  python ai/eval/i3_match_eval.py --set i3 --catalog asis --extraction "$P/hybrid_v2_i3" --run $r --server-steps `
    --json "$P/match/asis_e2e_rules_r$r.json"
}
```

할당량이 모자라면 `ops`를 다음 날로 미룬다. 미완료 실행은 보고서에서 빠지고 이름이 따로 적힌다.

## 5. 보고서

```powershell
python ai/eval/p46_report.py --out $P `
  --extraction "v2=$P/hybrid_v2_i3" --extraction "v1=$I3/2026-10-30_p30/hybrid_i3" `
  --matching (Get-ChildItem "$P/match/*.json").FullName
```

`$P/p46_metrics.json`과 `p46_metrics.md`가 나온다: 추출(v1·v2), 사진의 모든 줄(위스키·비위스키 분류 개수), 매칭(카탈로그 / 입력 / rules·llm·server별 평균 [최소–최대]). PR에는 이 두 파일, 이 문서의 명령, 실행한 커밋 해시(`git rev-parse HEAD`)를 넣는다. 사진과 추출 기록·캐시는 커밋하지 않는다(I3와 같다).

## 6. 읽는 법

- **NFR-1·2**: v2의 이름 F1과 가격 정확도가 기준 이상이고 v1보다 떨어지지 않아야 서버에서 v2를 켤 근거가 된다. v2가 위스키 줄을 비위스키로 보내면 그 줄은 매칭에 들어가지 않으므로 이름 F1(재현율)과 "whisky as non-whisky" 개수에 같이 드러난다.
- **NFR-3**: `full/label/rules`의 Top-1. 2.1 표에서 이미 0.774로 기준(0.90)에 못 미친다. I3(0.771)에서 규칙 수정으로 두 줄 늘었다.
- **NFR-4**: FM 1/675 (0.0015), 기준 이하.
- **server 행**: 임베딩이 후보 없는 줄에 후보를 붙이면 "register"가 줄고, 카탈로그에 없는 상품의 줄은 "wrong"(정답 없는 후보)으로 옮겨 간다. `asis`에서 이 이동이 크다.
- v1 지연은 11/4, v2 지연은 실행일의 값이라 지연은 같은 조건의 비교가 아니다.
