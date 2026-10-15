# test C1 직접 등록 41줄 — 원인·업주 난이도·고칠 방법 (I3 백로그)

2026-10-15 · 박진우 (분석: Claude, API 0회) · 원본 `ai/runs/2026-10-14_m3/test_m3a.json` (M3a, C1), 정답 `eval/match_gold_v1_1.json`

**무엇:** test(미라보 9장 + 포레스트 1장)에서 상품은 카탈로그에 있는데(C1) S1+S2b+S3 → M3a를 거쳐도 후보를 하나도 못 낸 41줄(정답 있는 39 + `unknown` 2). 규칙 수정은 하지 않았고, I3에서 무엇을 고칠지의 근거로 남긴다.

**주의:** test에서 본 줄이다. 이걸 보고 고친 규칙을 같은 test로 다시 재면 숫자가 부풀어 오른다. 수정은 dev에서 만들고 P47이나 새 바로 확인한다.

**카탈로그 v2 서비스판 상태:** 41줄 중 39줄의 메뉴 표기는 이미 `catalog_v2_service.json`에 별칭으로 들어 있다(A3에서 test 바 메뉴 표기를 별칭으로 넣음). 실제 서비스 DB에서는 이 바들의 이 표기가 별칭 정확 일치로 잡힌다. 이 표가 말하는 것은 **처음 보는 바에서 같은 유형의 표기가 나오면 못 잡는다**는 점이다.

## 요약

| 원인 | 줄 | 업주 난이도 | 고칠 방법 |
|---|---|---|---|
| ① 거부 규칙이 정답을 버림 | 17 | 보통, 쉬움 | 거부 규칙 손질(dev에서 오매칭 확인 후) |
| ② 브랜드 표기 불일치(기원 ↔ Ki One) | 8 | 보통 | 브랜드 별칭 "기원/Ki-Won → Ki One" |
| ③ 번역이 틀림 | 6 | 쉬움 | 한국어 브랜드·에디션 별칭(LLM 없이 잡히게) |
| ④ 리뉴얼 연수 불일치(카탈로그 연수 비어 있음) | 4 | 보통 | 카탈로그 연수 규칙 재정의(P47 이후 할 일) |
| ⑤ 디아지오 SR 약칭 | 4 | 보통 | 템플릿 별칭 "SR 22/23 → Special Release 2022/2023" |
| ⑥ 정답 불명확 | 2 | 업주는 알지만 메뉴만으론 특정 불가 | 고칠 대상 아님(직접 등록이 맞음) |

- 업주 쪽의 진짜 위험은 수고보다 **중복 상품**이다. 후보가 없으면 업주가 이미 있는 상품을 못 찾고 새로 만들 수 있다(특히 ②④⑤). I3 업주 화면에서 직접 등록 전에 카탈로그 검색을 먼저 보여줄 것.
- ②③⑤(18줄)는 한국어 브랜드·에디션 표기표와 템플릿 별칭으로 풀리는 유형이다(P36 마감 기록의 I3 방향과 같음).

## 41줄 전체

### ① 거부 규칙이 정답을 버림 (17줄)

| 사진 | 메뉴 줄 | 정답 | LLM 번역 | 거부된 후보(규칙) | 업주 난이도 |
|---|---|---|---|---|---|
| 011_미라보_01 | 더 위스키 에이전시(TWA) 카발란 솔리스트 올로로소 7년 | `new:twa-kavalan-oloroso-7` | The Whisky Agency Kavalan 7 Solist Oloroso | The Whisky Agency Kavalan Oloroso 7 (edition_mismatch) | 쉬움 |
| 011_미라보_01 | 더 위스키 에이전시(TWA) 카발란 솔리스트 포트 8년 | `new:twa-kavalan-port-8` | The Whisky Agency Kavalan 8 Solist Port | The Whisky Agency Kavalan Port 8 (edition_mismatch) | 쉬움 |
| 011_미라보_02 | 하이랜드 파크(Highland Park) 캐스크 스트랭스 배치 4 | `new:highland-park-cs-batch-4` | Highland Park Cask Strength Batch 4 | Highland Park Cask Strength Release No.4 (edition_mismatch) | 보통 |
| 011_미라보_02 | 엘리먼츠 오브 아일라(Elements of Islay) 버번 | `new:elements-of-islay-bourbon` | Elements of Islay Bourbon | Elements of Islay Bourbon Cask (bottler_missing) | 쉬움 |
| 011_미라보_02 | 엘리먼츠 오브 아일라(Elements of Islay) 셰리 | `new:elements-of-islay-sherry` | Elements of Islay Sherry | Elements of Islay Sherry Cask (bottler_missing) | 쉬움 |
| 011_미라보_03 | 탈리스커(Talisker) 더 와일드 블루 | `new:talisker-wild-blue` | Talisker The Wild Explorer Series The Wild Blu | Talisker The Wild Blue (edition_mismatch) | 쉬움 |
| 011_미라보_04 | 글렌드로낙(Glendronach) 오드 투더 발리 | `new:glendronach-ode-to-the-valley` | Glendronach Ode to Loudoun | GlenDronach Ode to the Embers (edition_mismatch); GlenDronach Ode to the Valley (edition_mismatch) | 쉬움 |
| 011_미라보_05 | 클라이넬리쉬(Clynelish) 디스틸러리 에디션 | `new:clynelish-de` | Clynelish Distillery Edition | Clynelish Distillers Edition (edition_mismatch) | 쉬움 |
| 011_미라보_07 | 러셀(Russel's) 10년 버번 | `new:russells-reserve-10` | Russell's Reserve 10 Bourbon | Russell's Reserve 10 (edition_mismatch) | 쉬움 |
| 011_미라보_07 | 러셀(Russel's) 버번 싱글 배럴 | `russells-reserve-single-barrel` | Russell's Reserve Bourbon Single Barrel | Russell's Reserve Single Barrel (edition_mismatch); Russell's Reserve Single Barrel Rye (edition_mismatch) | 쉬움 |
| 011_미라보_07 | 블랑톤(Blanton) 버번 싱글배럴 | `new:blantons-original` | Blanton's Bourbon Single Barrel | Blanton's Original Single Barrel (edition_mismatch); Blanton's Straight From The Barrel (edition_mismatch) | 보통 |
| 011_미라보_07 | 일라이저 크레이그(Elijah Craig) 버번 배럴 프루프 | `new:elijah-craig-barrel-proof` | Elijah Craig Bourbon Barrel Proof | Elijah Craig Barrel Proof (edition_mismatch) | 쉬움 |
| 011_미라보_08 | 하이 코스트(High Coast) 신코 배치 2 | `new:high-coast-cinco-batch-2` | High Coast Cinq Batch 2 | High Coast Cinco Batch 2 (edition_mismatch) | 쉬움 |
| 011_미라보_09 | 마르스(Mars) 더 럭키캣 메이 앤 하나 | `new:mars-lucky-cat-may-hana` | Mars The Lucky Cat May and Hana | Mars The Lucky Cat May & Hana (edition_mismatch); Mars The Lucky Cat Hana & Choco (edition_mismatch) | 쉬움 |
| 011_미라보_09 | 마르스(Mars) 더 럭키캣 하나 앤 초코 | `new:mars-lucky-cat-hana-choco` | Mars The Lucky Cat Hana and Choco | Mars The Lucky Cat Hana & Choco (edition_mismatch); Mars The Lucky Cat May & Hana (edition_mismatch) | 쉬움 |
| 011_미라보_09 | 기린(Kirin) 후지산 로크 시그니처 블랜드 | `new:fuji-sanroku-signature-blend` | Kirin Fuji Single Grain Signature Blend | Kirin Fuji Sanroku Signature Blend (edition_mismatch) | 쉬움 |
| 011_미라보_09 | 폴존(Paul John) PX 셰리 | `new:paul-john-px` | Paul John PX Sherry | Paul John Pedro Ximenez Select Cask (edition_mismatch) | 쉬움 |

### ② 브랜드 표기 불일치(기원 ↔ Ki One) (8줄)

| 사진 | 메뉴 줄 | 정답 | LLM 번역 | 거부된 후보(규칙) | 업주 난이도 |
|---|---|---|---|---|---|
| 011_미라보_08 | 기원(Ki-Won) 배치 3 캐스크 스트랭스 | `new:kiwon-batch-3-cs` | Ki-Won Batch 3 Cask Strength | – | 보통(배치가 많음) |
| 011_미라보_08 | 기원(Ki-Won) 배치 4 스모크 | `new:kiwon-batch-4-smoke` | Ki-Won Batch 4 Smoke | – | 보통(배치가 많음) |
| 011_미라보_08 | 기원(Ki-Won) 배치 4 피티드 | `new:kiwon-batch-4-peated` | Ki-Won Batch 4 Peated | – | 보통(배치가 많음) |
| 011_미라보_08 | 기원(Ki-Won) 배치 5 포트 캐스크 스트랭스 | `new:kiwon-batch-5-port-cs` | Ki-Won Batch 5 Port Cask Strength | – | 보통(배치가 많음) |
| 011_미라보_08 | 기원(Ki-Won) 배치 7 | `new:kiwon-batch-7` | Ki-Won Batch 7 | – | 보통(배치가 많음) |
| 011_미라보_08 | 기원(Ki-Won) 시그니처 | `new:kiwon-signature` | Ki-Won Signature | – | 보통(배치가 많음) |
| 011_미라보_08 | 기원(Ki-Won) 레드페퍼 캐스크 | `new:kiwon-red-pepper-cask` | Ki-Won Red Pepper Cask | – | 보통(배치가 많음) |
| 013_포레스트_01 | 기원 호랑이 | `new:kiwon-horangi` | Three Societies Tiger | – | 보통(배치가 많음) |

### ③ 번역이 틀림 (6줄)

| 사진 | 메뉴 줄 | 정답 | LLM 번역 | 거부된 후보(규칙) | 업주 난이도 |
|---|---|---|---|---|---|
| 011_미라보_04 | 아드벡(Ardbeg) 스모키버스 | `new:ardbeg-smokiverse` | Ardbeg Smoketrails | – | 쉬움 |
| 011_미라보_09 | 폴존(Paul John) 라크리마 | `new:paul-john-lacrima` | Paul John Laxmi | – | 쉬움 |
| 013_포레스트_01 | 글렌드로낙 피티드 | `new:glendronach-traditionally-peated` | The GlenDronach Peated | – | 쉬움 |
| 013_포레스트_01 | 킬호만 사닉 | `new:kilchoman-sanaig` | Kilkerran Saanigh | – | 쉬움 |
| 013_포레스트_01 | 킬호만 배치 스트렝스 | `new:kilchoman-batch-strength` | Kilkerran Batch Strength | – | 쉬움 |
| 013_포레스트_01 | 마크리무어 CS | `new:arran-machrie-moor-cs` | Machrie Moor CS | – | 쉬움 |

### ④ 리뉴얼 연수 불일치(카탈로그 연수 비어 있음) (4줄)

| 사진 | 메뉴 줄 | 정답 | LLM 번역 | 거부된 후보(규칙) | 업주 난이도 |
|---|---|---|---|---|---|
| 011_미라보_04 | 글렌모렌지(Glenmorangie) 15년 라산타 | `glenmorangie-lasanta` | Glenmorangie 15 Lasanta | – | 보통(다른 상품으로 착각해 새로 등록할 위험) |
| 011_미라보_04 | 글렌모렌지(Glenmorangie) 14년 퀸타루반 | `glenmorangie-quinta-ruban` | Glenmorangie 14 Quinta Ruban | – | 보통(다른 상품으로 착각해 새로 등록할 위험) |
| 011_미라보_04 | 글렌모렌지(Glenmorangie) 16년 더 넥타 | `glenmorangie-nectar-dor` | Glenmorangie 16 The Nectar d'Or | – | 보통(다른 상품으로 착각해 새로 등록할 위험) |
| 013_포레스트_01 | 글렌모렌지 퀸타 루반 14년 | `glenmorangie-quinta-ruban` | Glenmorangie 14 Quinta Ruban | – | 보통(다른 상품으로 착각해 새로 등록할 위험) |

### ⑤ 디아지오 SR 약칭 (4줄)

| 사진 | 메뉴 줄 | 정답 | LLM 번역 | 거부된 후보(규칙) | 업주 난이도 |
|---|---|---|---|---|---|
| 011_미라보_01 | 디아지오 SR(Diagio SR) SR 22 탈리스커 11년 | `new:talisker-11-special-release-2022` | Diageo Talisker 11 SR 22 | – | 보통(연도별 선택) |
| 011_미라보_01 | 디아지오 SR(Diagio SR) SR 23 오반 11년 | `new:oban-11-special-release-2023` | Diageo Oban 11 SR 23 | – | 보통(연도별 선택) |
| 011_미라보_01 | 디아지오 SR(Diagio SR) SR 23 탈리스커 | `new:talisker-special-release-2023` | Diageo Talisker SR 23 | – | 보통(연도별 선택) |
| 011_미라보_01 | 디아지오 SR(Diagio SR) SR 23 클라이넬리쉬 | `new:clynelish-special-release-2023` | Diageo Clynelish SR 23 | – | 보통(연도별 선택) |

### ⑥ 정답 불명확 (2줄)

| 사진 | 메뉴 줄 | 정답 | LLM 번역 | 거부된 후보(규칙) | 업주 난이도 |
|---|---|---|---|---|---|
| 011_미라보_02 | 하이랜드 파크(Highland Park) 캐스크 스트랭스 헤더 | `unknown` | Highland Park Cask Strength Hærtha | Highland Park Cask Strength Release No.4 (edition_mismatch) | 업주는 알지만 메뉴만으론 특정 불가 |
| 011_미라보_03 | 아란(Arran) 시그니처 시리즈 | `unknown` | Arran Signature Series | – | 업주는 알지만 메뉴만으론 특정 불가 |

같은 내용의 표: `ai/docs/i3_unmatched_41.csv` (열 `in_catalog_v2_alias` = 메뉴 표기가 카탈로그 v2 서비스판 별칭에 있는지).
