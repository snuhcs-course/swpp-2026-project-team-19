# M4: Naver 근거 실시간 판정 (dev 실험, 사전 등록)

2026-10-15 · 박진우 (작성: Claude Code 야간 작업, 검토: 박진우) · 브랜치 `i2-m4-naver-match` (`origin/i2-catalog-v2` `415e78f` + `origin/i2-p17-naver` `d24b004` 머지)

**go 조건은 잠정이다.** 진우가 확인하기 전 제안값이며, 아래 판정도 "잠정 go / 잠정 no-go"로만 쓴다.

## 1. 목적

S1+S2b+S3 → M3a(동결, `1ace927`) 뒤에도 업주가 골라야 하는 줄에 대해, 메뉴 줄 이름과 M3a 번역 영문명으로 Naver를 검색하고, 그 스니펫과 카탈로그 후보를 `ai/naver/judge.py`의 match 모드에 넣어 판정한다. 이렇게 하면 업주 부담((b) 선택 + (c) 직접 등록)이 줄어드는지 잰다.

## 2. 규칙 (바꾸지 않음)

1. **M4 출력은 최대 "확인 권장"(confirm)까지.** 결과는 항상 ambiguous이고 M4 후보는 `method: "llm"`, evidence `{"m4": ...}`. exact(자동 확정)를 만들지 않는다.
2. **거부권:** M3a의 거부권 4개를 그대로 쓴다(`ai/match_llm/m3.py` `M3._vetoes`): `bottler_missing`(양방향), `age_mismatch`, `alias_of_other`, `edition_mismatch`. 짧은 토큰(PX, DR) 규칙도 그대로(없으면 후보는 남기지만 확인 권장 불가). 거부권은 줄의 M3a 번역으로 검사한다.
3. **새 상품 생성 금지.** 판정 결과는 기존 상품 id / `none` / `new` 중 하나. `new`는 기록만 하고 줄은 그대로 (c)다.
4. 확인 권장은 M3 합치기 규칙과 같다: M4가 고른 상품이 거부권을 통과하고, 줄의 현재 후보가 없었거나 고른 상품이 현재 후보 안에 있을 때만 1순위에 `confirmRecommended`. 현재 후보 밖의 상품을 고르면 1순위에 올리되 확인 권장 없이 선택으로 남긴다.

## 3. 대상 줄과 입력

- **대상 줄:** S1+S2b+S3가 확정(exact·multi)하지 않았고, M3a 이후 결과가 (1) 후보 없음, 또는 (2) 후보 2개 이상인데 1순위에 확인 권장이 없는 줄. 정답을 보지 않고 정한다. M3a 번역이 없거나 `kind`가 whisky가 아닌 줄은 M3a와 같이 건너뛴다.
- **Naver 검색:** 질의 ① 메뉴 줄 이름 그대로 ② M3a 번역으로 조립한 영문명(`m3.english_name`, ①과 다를 때). endpoint blog·webkr·cafearticle, `display=10`. encyc는 P17 스모크에서 후보 근거 0건이라 뺐다. 응답은 `<data_dir>/naver_cache/`에 캐시(P17과 같음).
- **근거(evidence):** 결과를 URL로 중복 제거하고, 제목+본문(태그 제거)에 줄의 토큰(번역의 병입사·증류소·브랜드·에디션 토큰, 연수, 한글 줄 이름의 normalize 포함 여부)이 많이 들어간 순으로 4개(`judge.MAX_EVIDENCE`).
- **카탈로그 후보(options, 최대 20개, 이 순서로 채움):**
  1. 줄의 현재 후보(S1+S2b+S3, M3a 후보 포함)
  2. M3a 번역의 병입사·증류소·브랜드로 찾은 브랜드의 상품(M3b의 `family`와 같음)
  3. Naver 결과 한 건의 영문 토큰에 상품 표준명의 핵심 토큰(`m3.core_tokens`)이 모두 있고, 줄에 연수가 있으면 연수도 같은 상품
  - 후보가 하나도 없으면 LLM을 부르지 않고 `no_options`로 기록한다.
- **LLM:** `judge.py` match 모드, `gemini-3.5-flash-lite`, thinking `low`. 입력 `{mode: "match", menu_line, options[{product_id, display_name, age_years, edition_name}], evidence}`. 응답은 `ai/runs/2026-10-15_m4/judge_cache/`에 (프롬프트 SHA-256, 입력 JSON) 키로 캐시.

## 4. 조건과 비교

- 카탈로그 조건은 M3 dev와 같다(`ai/eval/match_eval.py`): C0 = `catalog_v1_draft`, C1 = C0 + dev 정답이 참조하는 new 상품(영문 표준명 별칭 1개). 바마다 그 바 메뉴에서만 나온 별칭을 뺀다. 정답 `eval/match_gold_v1_1.json`, dev = 위스키복춘·서로상·Beck 13장 177줄.
- M3a 번역은 `ai/runs/2026-10-14_m3/cache`를 그대로 쓴다(`--cache-only`, M3a API 호출 0).
- 행: `S1+S2b+S3`, `M3a`(기준), **`M3a+M4`(평가 대상)**, `M4`(참고: M3a 후보 없이 S1+S2b+S3 바로 뒤에 M4. 번역은 질의·거부권에만 씀).

**실행 전에 본 dev 상황 (2026-10-15 M3a 캐시 재채점과 Gemini 없는 dry run `--m4-dry`):** M3a 뒤 대상 줄은 C0 29줄, C1 3줄이다(그 밖에 비위스키 번역 2줄은 건너뜀. C0 (d) 2줄은 후보가 1개라 대상이 아님). 참고 행 `M4`의 대상은 C0 32줄, C1 13줄. C0의 (c) 30줄은 모두 카탈로그에 없는 상품·`unknown`·비위스키라 정답 행동은 "직접 등록"이고, M4가 확인 권장을 내면 전부 오답이다. 그래서 **C0는 M4의 오답 확인 시험**이고, C1에서 M4가 줄일 수 있는 (b)+(c)는 최대 1줄(Hibiki DR, 5줄 중 1줄 = 20%)이다. 이 상황을 보고 지표·기준을 바꾸지 않았다.

## 5. 지표 (C0·C1 각각)

| # | 지표 | 정의 |
| --- | --- | --- |
| 1 | 사진당 업주 부담 | (a) 확인 (b) 선택 (c) 직접 등록 (d) 오답 후보 (`match_eval.burden_kind`, M3와 같음). 합계와 사진당 평균 |
| 2 | (b)+(c) 감소율 | (M3a의 (b)+(c) − M3a+M4의 (b)+(c)) / M3a의 (b)+(c) |
| 3 | M4 확인 오답 비율 | M4가 확인 권장으로 올린 줄(1순위가 M4 후보이고 `confirmRecommended`) 중 1순위가 정답이 아닌 줄의 비율. 정답이 카탈로그에 없거나 `unknown`·`non_whisky`인 줄은 오답 |
| 4 | false merge rate, 알려진 상품 Top-1 | 기존 정의(exact 기준). M4는 exact를 만들지 않으므로 M3a와 같아야 정상 |
| 5 | 확인 권장 수락 시 오답률 | M3 정의 그대로 |
| 6 | M4 판정 분포 | 대상 줄별 same(상품) / new / none / unsure / no_options / 거부권으로 버림, 그리고 `new` 판정 중 정답이 카탈로그에 없는 줄 비율(P36 참고) |
| 7 | 지연 | 대상 줄 1개당 Naver(캐시 미스 요청의 실제 지연 합), Gemini(호출 지연), 합계. 평균·p95 |
| 8 | 호출 수 | Naver API 호출·캐시 히트, Gemini 호출(회차별, 재시도 포함) |

## 6. go 조건 (잠정, 진우 확인 전)

모두 만족하면 잠정 go:
1. dev **C1**에서 `M3a+M4`의 (b)+(c)가 `M3a` 대비 **20% 이상** 줄 것
2. M4 확인 오답 비율 **≤ 10%**를 C0와 C1 **각각**에서 (M4 확인이 0줄인 조건은 0/0으로 통과로 보되 n을 같이 쓴다)
3. false merge rate(exact)가 C0·C1 모두 M3a보다 늘지 않을 것

C0의 (b)+(c) 감소는 판정에 쓰지 않는다(정답이 "직접 등록"이라 줄면 오답이다).

## 7. 프롬프트 수정 한도와 순서

- r0: `judge_prompt_v1.md` 그대로(P17 동결본, match 모드).
- dev 결과를 보고 **최대 2회**(r1, r2) 고칠 수 있다. 고칠 때는 `judge_prompt_v1.md`를 바꾸지 않고 `ai/naver/judge_prompt_m4_v2.md`, `_v3.md`를 새로 만든다(P28은 v1을 쓰므로). 고친 내용과 이유는 모두 `ai/runs/2026-10-15_m4/README.md`와 `ai/runs/ai_usage_log.md`에 남긴다.
- 거부권·대상 줄·후보 구성·go 조건은 dev 결과를 보고 바꾸지 않는다. 엄격 방향(후보를 버리거나 확인 권장을 막는 쪽)의 수정만 허용하고, 하면 기록한다.
- **최종 회차는 마지막으로 돌린 회차**로 한다(좋은 회차 고르기 금지).
- Gemini 호출 상한 200회(M4 전체, 재시도 포함). 429·`RESOURCE_EXHAUSTED`가 나오면 그 자리에서 멈추고(`ai/naver/quota.py`) 캐시로 이어서 할 수 있게 한다.
- test(미라보·포레스트)와 수이·오드비에는 돌리지 않는다. dev를 보고 고친 프롬프트이므로 **dev 숫자는 낙관적**이다.
