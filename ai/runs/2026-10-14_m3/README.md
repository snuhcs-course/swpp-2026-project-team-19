# M3 (I2): 매칭 LLM 층 — dev 개발과 test 확인 1회

2026-10-14 · 박진우 (작성: Claude Code, 검토: 박진우) · 브랜치 `i2-m3-llm-match` · 사전 등록 `ai/docs/eval_plan.md` "M3 사전 등록" 절

## 맨 위 지표: LLM이 낸 확인 권장의 정답 비율 (C0는 판정 기준 아님, 계속 같이 보고)

| 셋 | 회차 | C0 | C1 |
|---|---|---|---|
| dev | r0 (프롬프트 v1) | **4/7 (0.57)** | 8/8 |
| dev | r1a (규칙만 수정) | 7/7 | 10/10 |
| dev | r1 (규칙 + v2) | 7/7 | 12/12 |
| dev | r2 (v3, 최종) | 7/7 | 13/13 |
| **test** | **M3a (동결)** | **7/9 (0.78)** | **193/194 (0.995)** |

"LLM이 낸 것" = 1순위가 LLM 후보이고 S1~S3가 그 상품을 확인 권장으로 내지 않았던 줄. S1~S3가 이미 확인 권장한 상품에 LLM이 동의한 줄은 "규칙"으로 센다.

## 판정

- **M3a 채택.** dev(사전 등록 판정): C1 (c) 직접 등록 10 → 4, C1 LLM 확인 권장 13/13, 확인 권장 수락 시 오답률 C0 0.000·C1 0.000. 세 기준 모두 만족.
- **test 확인 (같은 기준을 적용, 판정을 바꾸지 않음):** C1 (c) 171 → 41, C1 LLM 확인 권장 0.995, 수락 시 오답률 C0 0.015·C1 0.002. 세 기준 모두 만족. 단, **C0 LLM 정밀도 7/9**로 dev보다 낮고, C0 수락 시 오답률이 기준선 0.010(규칙의 확인 권장 오답 5줄)에서 0.015로 올랐다.
- **M3b 채택 안 함.** dev r2에서 M3a 대비 C1 (c)가 4 → 4로 줄지 않음(기준 1). 호출 16회, 고른 상품 0. test에는 돌리지 않았다(사전 등록).
- 알려진 상품 Top-1과 false merge rate는 모든 회차·셋에서 S1+S2b+S3와 같다(LLM은 exact를 만들지 않음).
- **동결 커밋:** `1ace9275718ddb55e00827c1db49461204fb445f` (번역 프롬프트 v3, 거부권 4개). test는 이 커밋에서 등록 명령으로 1회 실행했다(`test_m3a.json`, 출력 `test_m3a_stdout.txt`). 실행 후 코드·프롬프트·규칙은 바꾸지 않았다.

## 비교표

열: Top-1 = 알려진 상품 Top-1, FM = false merge rate, (a) 확인 (b) 선택 (c) 직접 등록 (d) 오답 후보 = 줄 수 합계, bcd<5 = 사진당 (b)+(c)+(d) 5 미만 비율, 수락 오답 = 확인 권장 수락 시 오답률, (c)→ = S1~S3에서 unmatched였다가 후보가 생긴 줄(그중 정답이 후보에 있는 줄), (c)→(d) = 그중 정답이 후보에 없는 줄. 정답 `eval/match_gold_v1_1.json`, dev 177줄(13장), test 478줄(10장).

### dev (회차 이력, 합치기 방식)

| 회차 | 내용 | 조건 | Top-1 | FM | (a) | (b) | (c) | (d) | bcd<5 | 규칙 확인 권장 | LLM 확인 권장 | 수락 오답 | (c)→ | (c)→(d) |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 기준 | S1+S2b+S3 | C0 | 0.909 | 0.000 | 11 | 4 | 30 | 2 | 0.77 | 7/7 | – | 0.000 | – | – |
| r0 | 번역 v1, 거부권 3 | C0 | 0.909 | 0.000 | 11 | 4 | 28 | 4 | 0.77 | 7/7 | 4/7 | 0.017 | 0 | 2 |
| r1a | + edition_mismatch, 중립 단어, 짧은 토큰 (v1 번역 캐시) | C0 | 0.909 | 0.000 | 14 | 1 | 30 | 2 | 0.77 | 7/7 | 7/7 | 0.000 | 0 | 0 |
| r1 | + 번역 v2 (expansions, 라인업) | C0 | 0.909 | 0.000 | 14 | 1 | 30 | 2 | 0.77 | 7/7 | 7/7 | 0.000 | 0 | 0 |
| r2 | 번역 v3 (에디션 철자, 약어 유지, 라인업 예시) | C0 | 0.909 | 0.000 | 14 | 1 | 30 | 2 | 0.77 | 7/7 | 7/7 | 0.000 | 0 | 0 |
| r2 | + M3b | C0 | 0.909 | 0.000 | 14 | 1 | 30 | 2 | 0.77 | 7/7 | 7/7 | 0.000 | 0 | 0 |
| 기준 | S1+S2b+S3 | C1 | 0.861 | 0.000 | 12 | 5 | 10 | 0 | 0.92 | 8/8 | – | 0.000 | – | – |
| r0 | | C1 | 0.861 | 0.000 | 16 | 5 | 6 | 0 | 0.92 | 8/8 | 8/8 | 0.000 | 4 (4) | 0 |
| r1a | | C1 | 0.861 | 0.000 | 20 | 1 | 6 | 0 | 1.00 | 8/8 | 10/10 | 0.000 | 4 (4) | 0 |
| r1 | | C1 | 0.861 | 0.000 | 20 | 1 | 6 | 0 | 1.00 | 8/8 | 12/12 | 0.000 | 4 (4) | 0 |
| r2 | | C1 | 0.861 | 0.000 | 22 | 1 | **4** | 0 | 1.00 | 8/8 | 13/13 | 0.000 | 6 (6) | 0 |
| r2 | + M3b | C1 | 0.861 | 0.000 | 22 | 1 | 4 | 0 | 1.00 | 8/8 | 13/13 | 0.000 | 6 (6) | 0 |

대체 방식(비교용, `M3a/replace`, `M3a+M3b/replace`)은 dev 모든 회차에서 합치기와 숫자가 같았다(r0 대체도 C0 4/7, 0.017). 결과 파일: `dev_r0_m3a.json`, `dev_r1a_rules_v1prompt.json`, `dev_r1_m3a.json`, `dev_r2_v3_m3b.json`.

회차별 바뀐 줄:
- r0 → r1a (규칙): C0 확인 권장 오답 3줄(Maker's Mark Cask Strength → Maker's Mark, Laphroaig 10 Cask Strength → Laphroaig 10, Arran Quarter Cask → Bodega Sherry Cask)이 `edition_mismatch`로 사라짐. 카발란 DR 마데라캐스크(C0) (d) → (c). 달모어 12 쉐리, Macallan 12 Sheryy Cask, 카발란 솔리스트 셰리 오크가 (b) → 정답 확인 권장. 발베니 18 PX(C1)는 짧은 토큰 규칙으로 확인 권장 → 후보 1개(정답).
- r1a → r1 (v2): Hakushu DR (c) → 확인 권장(expansions "Distiller's Reserve"), 발베니 18 PX 확인 권장 회복("Pedro Ximenez"). 카발란 DR 마데라캐스크(C1) 후보 1개 → (c) 퇴보(v2 번역이 "DR"을 빼고 "Madera"로 씀).
- r1 → r2 (v3): Machrie Moor (c) → 확인 권장(brand Arran, 정답). 카발란 DR 마데라캐스크(C1) 후보 1개(정답)로 회복. 되돌림 규칙 미발동.

### test (확인 1회, 동결 커밋)

| 매처 | 조건 | Top-1 | FM | (a) | (b) | (c) | (d) | bcd<5 | 규칙 확인 권장 | LLM 확인 권장 | 수락 오답 | (c)→ | (c)→(d) |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| S1+S2b+S3 | C0 | 0.770 | 0.000 | 19 | 3 | 311 | 41 | 0.00 | 7/12 | – | 0.010 | – | – |
| **M3a** | C0 | 0.770 | 0.000 | 23 | 1 | 309 | 41 | 0.00 | 7/12 | 7/9 | 0.015 | 2 (2) | 0 |
| M3a 대체 | C0 | 0.770 | 0.000 | 23 | 1 | 309 | 41 | 0.00 | 7/12 | 7/9 | 0.015 | 2 (2) | 0 |
| S1+S2b+S3 | C1 | 0.377 | 0.000 | 62 | 45 | 171 | 21 | 0.00 | 14/18 | – | 0.008 | – | – |
| **M3a** | C1 | 0.377 | 0.000 | 219 | 37 | **41** | **2** | 0.10 | 14/14 | 193/194 | 0.002 | 130 (130) | 0 |
| M3a 대체 | C1 | 0.377 | 0.000 | 236 | 20 | 41 | 2 | 0.20 | 14/14 | 210/211 | 0.002 | 130 (130) | 0 |

- C1에서 (c) → (a)·(b)로 올라온 130줄은 전부 정답이 후보에 있다(확인 권장 117, 선택 13). (d)도 21 → 2.
- 대체 방식은 C1에서 선택 17줄을 확인 권장으로 더 바꾸고(210/211), 오답은 늘지 않았다. 판정은 사전 등록대로 합치기로 한다.
- "부담 5 미만 사진"은 여전히 0(미라보 1장 31–60줄). (b)+(c)+(d) 5 미만 사진은 C1에서 0.00 → 0.10.
- 기준선의 규칙 확인 권장 오답(C0 5줄, C1 4줄)은 P22 S2b·S3 결과로, M3와 무관하게 이미 있었다. 정답 상품이 카탈로그에 없는데 다른 상품 1개에 확인 권장: 글렌가일 킬커란 12년, 아녹 피티드 셰리, 놉 크릭 라이, 잭다니엘 애플(C0·C1), 벤리악 10년 → Benromach 10(S3 편집거리, C0). M3a의 재조회가 같은 후보를 다시 찾으면 1순위가 LLM 후보가 되지만, S1~S3가 이미 확인 권장한 상품이라 "규칙"으로 센다.

## 호출·지연·토큰

| 실행 | 종류 | 새 API 호출 | 캐시 히트 | 평균 지연 | 입력 | 출력 | thought |
|---|---|---|---|---|---|---|---|
| 스모크 (Beck_03 1장) | M3a | 1 | 0 | 4.9 s | 1,572 | 1,258 | 119 |
| dev r0 | M3a | 7 | 1 | 2.6 s | 11,546 | 3,853 | 969 |
| dev r1a | M3a | 0 | 8 | (캐시) | | | |
| dev r1 | M3a | 8 | 0 | 3.7 s | 13,154 | 4,323 | 894 |
| dev r2 | M3a | 8 | 0 | 4.1 s | 14,242 | 4,343 | 934 |
| dev r2 | M3b | 16 | 16 | 2.1 s | 31,048 | 1,622 | 4,036 |
| test | M3a | 10 | 0 | 10.2 s | 27,965 | 33,645 | 1,143 |

합계 API 호출 50회(실행당 상한 200 이내), 모델 `gemini-3.1-flash-lite`, thinking `low`, 파싱 오류 0. test는 사진 1장당 1회(대상 줄 29–54개)라 출력이 크다(1장 평균 3.4천 토큰). M3b 토큰은 C0·C1 요청 32건 합(16건은 같은 입력 캐시). 응답 캐시 `cache/`(키 = 모델, thinking, 프롬프트 SHA-256, 입력 JSON). 재채점은 `--cache-only`로 API 0회.

## LLM이 틀린 줄 전체

### 확인 권장 오답 (LLM이 낸 것)

| 셋 | 조건 | 줄 | 정답 | LLM 확인 권장 | 원인 |
|---|---|---|---|---|---|
| test | C0 | 발베니(Balvenie) 12년 싱글 배럴 | new: The Balvenie 12 Single Barrel (카탈로그에 없음) | The Balvenie 12 DoubleWood | 에디션 "Single", "Barrel"이 둘 다 중립 단어라 `edition_mismatch`가 검사할 토큰이 남지 않음. 재조회의 S2b 기본 제품 규칙이 DoubleWood를 냄 |
| test | C0 | 카발란(Kavalan) 올로로소 셰리 | new: Kavalan Oloroso Sherry Oak (없음) | Kavalan Solist Oloroso Sherry | 메뉴 토큰(Oloroso, Sherry)은 모두 맞지만 후보에 메뉴에 없는 에디션 "Solist"가 더 있음. 거부권은 "메뉴 토큰이 후보에 있는가"만 보고 반대 방향은 보지 않음 |
| test | C1 | 벤로막(Benromach) 싱글 캐스크 | unknown | Benromach 12 Cask Strength | 에디션 "Single", "Cask"가 둘 다 중립 → 브랜드의 유일한 연수 없는 일치 후보가 확인 권장이 됨 |
| dev r0 | C0 | Maker\`s Mark Cask Strength / Laphroaig 10yo Cask Strength / Arran Quarter Cask | new (없음) | Maker's Mark / Laphroaig 10 / Arran Bodega Sherry Cask | 에디션 토큰 무시 → r1에서 `edition_mismatch`로 해결 |

dev r2(최종)에는 LLM 확인 권장 오답이 없다.

### 확인 권장은 아니지만 LLM 후보가 1순위로 틀린 줄 (정답이 후보에 없음)

| 셋 | 조건 | 줄 | LLM 후보 | 비고 |
|---|---|---|---|---|
| test | C0 | 라프로익(Laphroaig) PX 캐스크 (2장) | Laphroaig Quarter Cask | "PX"가 짧은 토큰이라 확인 권장은 막힘. S1~S3도 같은 후보(이미 (d)) |
| test | C0 | 우드포드 리저브 더블 X.O | Woodford Reserve Double Oaked | "X.O"가 "x", "o"로 쪼개져 짧은 토큰 → 확인 권장 막힘. S1~S3도 이미 (d) |

세 줄 다 S1+S2b+S3에서 이미 (d)였고 M3a가 (d)를 늘리지 않았다(C0 41 → 41).

### 거부권이 막은 후보

| 셋 | 조건 | 규칙 | 막은 후보 (줄 단위 중복 포함) | 그중 정답 상품 |
|---|---|---|---|---|
| dev r2 | C0 / C1 | edition_mismatch | 9 / 6 | 0 / 0 |
| test | C0 | edition_mismatch | 52 | 15 |
| test | C1 | edition_mismatch | 108 | 34 |
| test | C1 | bottler_missing | 2 | 2 |
| test | C1 | bottler_missing (reverse) | 1 | 0 |

`age_mismatch`, `alias_of_other`는 dev·test에서 발동 0회(단위 테스트로만 확인). 줄별 전체 목록(번역, 후보, 규칙, 정답)은 `test_m3a.json` / `dev_r2_v3_m3b.json`의 `results[].m3_lines[].vetoed`.

- **정답을 막은 경우 (test C1 36줄: edition_mismatch 34 + bottler_missing 2, 후보 손실이지 오답은 아님):**
  - "Bourbon"을 에디션 토큰으로 검사 12줄(Maker's Mark·Knob Creek·Woodford Reserve·Booker's·Buffalo Trace 버번, Russell's Reserve 10·싱글 배럴, Blanton's 싱글배럴, Elijah Craig 배럴 프루프, Wild Turkey 8년·12년·레어브리드). "버번"이 분류어인데 중립 단어 목록에 없음
  - 리뉴얼명·같은 상품으로 본 정답 연결 9줄(Glenmorangie 18 인피니트, Glenlivet 12 더블 오크·15 프렌치 오크, Glenfiddich 21 그란 레제르바, Glenfiddich 12 아몬티야또 셰리 피니시, Glenfarclas 105 캐스크 스트랭스, Laphroaig 25 캐스크 스트랭스, Arran 셰리 캐스크 캐스크 스트랭스, 하이랜드 파크 CS 배치 4). 메뉴 에디션이 카탈로그 표준명·별칭에 없음(`POST_TEST_ALIASES`류 별칭 문제)
  - 번역 오류 5줄(Ode to the Valley → "Loudoun", The Wild Blue → "Explorer Series … Blu", Distillers Edition → "Distillery", Cinco → "Cinq", 후지산로쿠 → "Single Grain" 추가)
  - 상품 쪽 표기·토큰화 차이 8줄(TWA 카발란 "솔리스트" 올로로소·포트: 메뉴엔 있고 표준명엔 없음, Bowmore 18 Deep & Complex·Mars Lucky Cat 2줄: 번역 "and" ↔ 표준명 "&", Willett "Wheated", Paul John 올로로소·PX 셰리: 표준명 "Select Cask"에 "Sherry" 없음)
  - `bottler_missing` 2줄: 엘리먼츠 오브 아일라 버번·셰리. 번역이 "Elements of Islay"를 `bottler_en`이 아니라 `brand_en`에 넣어 병입사 없음으로 판정됨
- **정상 차단 예:** 하이랜드 레어드 쿨일라 12년 → Caol Ila 12(정규품) `bottler_missing (reverse)`. 정답 Highland Laird Caol Ila 12만 남아 확인 권장(정답). P18 c의 독립병입 ↔ 정규품 위험을 test에서 실제로 막은 사례. 그 밖에 Laphroaig 10 CS → Laphroaig 10, Maker's Mark CS → Maker's Mark, Bunnahabhain 12 CS → Bunnahabhain 12, Arran 쿼터·포트·아마로네·소테른 캐스크 → Bodega Sherry Cask 등 C0의 형제 상품 37건을 막았다.

## 번역이 틀린 사례 (test, 유형별)

대상 줄 374개(C0 기준, C1과 같은 번역). 정답 표준명과 번역을 자동 대조해 다른 줄(91)을 직접 읽고 분류했다. 메뉴에 그 단어가 없어서 생긴 차이(예: Highland Park 18 → 메뉴에 "Viking Pride" 없음, Glenmorangie 리뉴얼 연수)는 번역 오류에서 뺐다.

| 유형 | 줄 수 | 예 | 결과 |
|---|---|---|---|
| 메뉴에 없는 단어 생성·다른 단어로 바꿈 | 8 | 오드 투더 발리 → "Ode to Loudoun", 스모키버스 → "Smoketrails", 라크리마 → "Laxmi", 사닉 → "Saanigh", 더 와일드 블루 → "+Explorer Series", 후지산 로크 → "+Single Grain", 호랑이 → "Tiger", 신코 → "Cinq" | 대부분 `edition_mismatch`로 정답까지 버려져 (c). 오답 확정은 없음 |
| 브랜드 오인 | 3 | 킬호만 사닉·킬호만 배치 스트렝스 → brand "Kilkerran", 기원 호랑이 → "Three Societies" | 다른 브랜드 검색 → 후보 없음 |
| 브랜드 음차를 정식 표기로 못 고침 | 10 | 기원 → "Ki-Won"(정식 Ki One) 7줄, 골드론 → "Goldron"(Gauldrons) 3줄(칸 배치와 겹침) | Ki One 7줄 C1 (c). 골드론은 Douglas Laing 가족이 후보 → (b) 1, 확인 권장 2(정답) |
| 칸 배치 오류 | 16 | 병입사 자체 라인 이름을 brand_en에(Douglas Laing 락 아일랜드·에피큐리안·골드론 등 8, Hunter Laing 스카라버스, Blackadder 셰리 스네이크: 10), Elements of Islay를 brand_en에(2), "디아지오 SR"의 Diageo를 bottler_en에(4) | 병입사 라인 10줄: 조립이 병입사 + 증류소만 써서 C1에서 가족 전체가 후보 → (b) 7, 정답 확인 권장 3(골드론 CS·셰리 캐스크, 셰리 스네이크). Elements of Islay: `bottler_missing`으로 정답 차단. Diageo SR: 재조회 이름이 "Diageo 11 SR 22"가 되어 실패 |
| 연도 약어 미풀이 | 4 | "SR 22/23"의 22·23을 2022·2023으로 풀지 않음(위 Diageo 4줄과 같은 줄) | (c) |
| 철자 차이 (경미) | 2 | "Tale of Spice"(Spices), "Peated"(Peat Smoked) | `edition_mismatch` 또는 후보 없음 |

번역 v3에서 병입사를 지어낸 사례는 0(bottler_en은 줄이나 제목에 병입사가 있을 때만 채워짐). 비위스키 판정 오류 0.

## 한계와 다음 작업 제안 (이번에 바꾸지 않음)

1. **중립 단어만으로 된 에디션** ("Single Barrel", "Single Cask")은 `edition_mismatch`가 검사할 토큰이 없어 test 확인 권장 오답 3건 중 2건의 원인이 됐다. 중립 단어가 에디션의 전부일 때는 확인 권장 불가로 두는 규칙이 후보다.
2. **반대 방향 에디션** (후보에만 있는 "Solist" 같은 에디션) 검사가 없다. 1건 오답.
3. **"Bourbon"(분류어)**이 에디션으로 검사돼 정답 12줄을 막았다. 중립 단어 후보. 단, "Rye"는 상품을 가르므로 중립이 아니다.
4. **병입사 이름이 brand_en에 들어간 경우**(Elements of Islay, Douglas Laing 블렌드)를 병입사로 보지 않는다. 조립·거부권에서 brand_en도 병입사 목록과 대조하는 것이 후보다.
5. 위 1–4는 test를 본 뒤의 제안이므로, 넣으려면 새 dev(다른 바)에서 다시 사전 등록하고 잰다(P29).
6. M3b는 이번 카탈로그·dev에서 효과가 없었다. C0 16건 전부 "none"이 맞았다는 점은 "새 상품 등록" 판단 근거(P36)로 다시 볼 만하다.
7. dev에 독립병입 줄이 없어 `bottler_missing`은 단위 테스트(`ai/match_llm/test_vetoes.py`, 가짜 상품)와 test에서만 확인됐다.

## 재현

```
python ai/eval/match_eval.py --split dev --gold eval/match_gold_v1_1.json --matcher S1+S2b+S3 M3a M3a+M3b M3a/replace M3a+M3b/replace --m3-cache ai/runs/2026-10-14_m3/cache --cache-only
python ai/eval/match_eval.py --split test --gold eval/match_gold_v1_1.json --matcher S1+S2b+S3 M3a M3a/replace --m3-cache ai/runs/2026-10-14_m3/cache --cache-only
BOTTLEMAP_M3_TRANSLATE=v1 python ai/eval/match_eval.py ... --cache-only   # r0/r1a 번역(v1), v2는 r1
```
r0 숫자는 r0 당시 코드(커밋 `cabcd1b` 이전 규칙)의 결과 파일로 남겼고, 현재 코드로 v1 번역을 재채점하면 r1a가 나온다.
