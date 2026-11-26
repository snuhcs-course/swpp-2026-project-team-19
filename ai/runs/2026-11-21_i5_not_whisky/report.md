# I5: 매칭 단계에서 "위스키 아님" 가려내기 (2026-11-21)

브랜치 `feature/i5-m3a-not-whisky` (main `0e628774`에서 분기). 커밋·push 없음.

## 1단계: 재기 (API 0회)

### 1.1 방법

- 스크립트: `ai/eval/i5_kind_table.py`. `i3_match_eval.py`의 결과 JSON(줄별 정답·규칙 결과)과 그 실행이 쓴 M3a 응답 캐시(`kind`)를 사진·줄 이름으로 잇는다. 새 LLM 호출 없음.
- 대상은 LLM 대상 줄(규칙이 확정하지 못한 줄)이다. 규칙이 확정한 줄은 LLM에 묻지 않으므로 `kind`가 없다.
- 정답 분류: `non_whisky` → 비위스키, 카탈로그에 있거나 없는 상품 → 위스키, `unknown` → 미상.
- 후보 수는 두 시점에서 셌다. "규칙 후보"는 S1+S2b+S3 결과, "임베딩 후 후보"는 서버가 그 뒤에 하는 임베딩 후보 단계와 연결 가드까지 거친 결과다.
- dev의 11-13 실행에는 임베딩 단계 결과가 없어서, 지금 코드로 규칙 + 임베딩만 다시 돌려 붙였다(`dev_service_rules_server.json`). 11-13 이후 규칙이 조금 바뀌어(Top-1 618 → 623줄) 캐시 26개 중 5개는 입력이 달라져 재사용되지 않는다. 그래서 `kind` 표는 11-13 실행 그대로이고, dev의 "임베딩 후 후보"만 지금 코드 기준이다.
- 줄별 목록: `kind_dev.md`, `kind_i3_label.md`, `kind_i3_e2e.md` (같은 폴더, `*_rows.json`은 줄 단위 원자료).

### 1.2 dev 5곳 (836줄 중 LLM 대상 218줄, 1회)

`ai/runs/2026-11-13_m3a_dev/cache_r1`, gemini-3.1-flash-lite thinking low. 인계 문서의 표와 같은 값이 나왔다.

| 정답 | 줄 | `non_whisky` | `whisky` | `unclear` |
|---|---|---|---|---|
| 비위스키 | 18 | 16 | 2 | 0 |
| 위스키 | 184 | 2 | 182 | 0 |
| 미상 | 16 | 0 | 16 | 0 |

비위스키 정답 18줄은 모두 LLM 대상이었다(규칙이 확정한 비위스키 줄 0).

**비위스키 정답인데 `whisky`로 답한 2줄** (2단계에서 정답을 위스키로 고칠 줄)

| 사진 | 줄 | 규칙 후보 | 임베딩 후 후보 |
|---|---|---|---|
| 011_미라보_08 | 잭다니엘(Jack Daniel) 애플 | 1 (Jack Daniel's Old No.7) | 1 (같음) |
| 009_오드비_04 | 잭다니엘 애플 | 0 | 2 (Old No.7, Single Barrel 100 Proof) |

**위스키 정답인데 `non_whisky`로 답한 2줄**

| 사진 | 줄 | 정답 | 규칙 후보 | 임베딩 후 후보 |
|---|---|---|---|---|
| 009_오드비_01 | 크래프트브로스 독수리 오형제 1호 | Craft Bros Eagle Five Brothers No.1 | 1 (정답 상품) | 1 (정답 상품) |
| 009_오드비_01 | 크래프트브로스 독수리 오형제 3호 | Craft Bros Eagle Five Brothers No.3 | 1 (정답 상품) | 1 (정답 상품) |

두 줄 모두 규칙이 정답 상품을 후보 1개로 이미 내고 있었다.

**맞게 `non_whisky`로 답한 16줄**: 헤네시 VSOP 2, 레미마틴 VSOP 1, 김과장 #2 (바베이도스 럼) 1, 아르마냑 8(샤토가호 밀레짐 3, 아르마냑 가호 5), 병맥주 4(기네스·산미구엘·아사히·코로나). 16줄 모두 규칙 후보 0.

### 1.3 변형: 후보가 없을 때만 표시 (dev)

| 변형 | 비위스키를 맞게 표시 | 위스키를 잘못 표시 | 미상을 표시 |
|---|---|---|---|
| A. `kind == non_whisky`이면 표시 | 16 / 18 | 2 | 0 |
| B. A이면서 규칙 후보 0 | 16 / 18 | 0 | 0 |
| C. A이면서 임베딩 후 후보 0 | 15 / 18 | 0 | 0 |

- B는 독수리 오형제 2줄을 지키고, 맞게 표시한 16줄은 하나도 잃지 않는다.
- C는 1줄을 잃는다. "김과장 #2 (바베이도스 럼)"에 임베딩이 "Kim Gwajang #4 Clynelish"를 후보로 붙이기 때문이다. 이 후보는 틀린 후보다.
- 잭다니엘 애플 2줄은 어느 변형에서도 표시되지 않는다(`whisky`로 답했으므로). 2단계에서 정답을 고치면 분모가 16이 되어 A·B는 16 / 16이 된다.

### 1.4 I3 33장 (675줄, 라벨 입력, 3회)

`ai/runs/2026-11-17_p46`의 `cache_<구성>_label_r1~r3`. 비위스키 정답은 4줄이고 모두 LLM 대상이다.

| 구성 | LLM 대상 | 비위스키 4줄 중 `non_whisky` | 위스키 줄 중 `non_whisky` | 위스키 줄 | 미상 24줄 |
|---|---|---|---|---|---|
| full | 166 | 4 / 4 / 4 | 0 / 0 / 0 | 138 모두 `whisky` | r1·r3: `whisky` 24, r2: `whisky` 19 + `unclear` 5 |
| ops | 155 | 4 / 4 / 4 | 0 / 0 / 0 | 127 모두 `whisky` | r1·r3: `whisky` 24, r2: `whisky` 19 + `unclear` 5 |
| asis (참고) | 196 | 4 / 4 / 4 | 0 / 0 / 0 | 168 모두 `whisky` | 3회 모두 `whisky` 24 |

(칸의 `a / b / c`는 r1 / r2 / r3.)

- 비위스키 4줄: `014_테일오브테일즈_04` Legacy — Foursquare Rum SC, `019_쏘댓page2_04` 헤네시 VSOP, 헤네시 XO, `021_무용의 유용_02` 헤네시 VSOP. 네 줄 모두 규칙 후보 0, 임베딩 후 후보 0이다. 그래서 변형 A·B·C가 모두 4 / 4, 잘못 표시 0으로 같다.
- I3에서는 위스키를 `non_whisky`로 답한 줄이 없다.
- r2의 `unclear` 5줄은 모두 `014_테일오브테일즈_04`의 병입사 묶음 줄(Hart Bros — Tormore / Brackla / Pulteney 등, 정답 미상)이다. `unclear`는 표시 대상이 아니다.
- 같은 구성의 r1~r3는 사진별 응답이 대부분 다르다(full 기준 31개 중 r1과 같은 응답이 r2 9개, r3 6개). 다만 full·ops·asis는 같은 줄에 대한 응답을 일부 공유하므로 서로 독립된 9회가 아니다.

### 1.5 I3 추출 입력 (e2e, 참고)

추출(flash-lite, 프롬프트 v2) 결과를 입력으로 한 full·ops 3회. 정답과 짝지어진 줄에서는 라벨 입력과 같다(비위스키 4 / 4, 위스키 잘못 표시 0). 정답과 짝이 없는 줄 중 `non_whisky`로 답한 것은 r1에만 3줄 있다: `017_리틀 갤러리_01`의 Hennesy V.S.O.P, Remy Martin V.S.O.P, Camus Boderies X.O. 추출이 위스키로 넘긴 코냑 줄이고, 후보는 규칙·임베딩 모두 0이다. r2·r3에서는 이 줄들이 매칭으로 넘어오지 않았다.

### 1.6 정리

- `kind == non_whisky` 판정은 dev에서 비위스키 18줄 중 16줄, I3에서 4줄 중 4줄(3회 모두)을 잡았다. 놓친 2줄은 잭다니엘 애플이다.
- 위스키를 잘못 표시한 것은 dev 2줄(독수리 오형제)뿐이고 I3에서는 0이다. 두 줄 모두 규칙 후보가 있어서 "규칙 후보 0일 때만 표시"(B)로 막힌다.
- "임베딩 후 후보 0"(C)은 B보다 맞는 표시를 1줄 더 잃고, 더 막는 줄은 없다.
- 근거가 되는 줄 수가 적다. 위스키를 잘못 표시한 사례는 2줄(한 매장, 한 브랜드)이고, I3의 비위스키는 4줄이다. B가 일반적으로 안전하다고 말하기에는 부족하다. 카탈로그에 없는 위스키가 맥주·코냑처럼 보이는 이름이면 B에서도 표시될 수 있다.

## 2단계: 잭다니엘 애플 (API 0회)

### 2.1 카탈로그 (`ai/catalog/catalog_v2_service.json`, v2.3 → v2.4)

- `excluded_non_whisky`에서 `jack-daniels-apple`을 빼고 상품으로 넣었다. 브랜드는 기존 `jack_daniels`, 표시명 `Jack Daniel's Tennessee Apple`, edition `Tennessee Apple`. 상품 529 → 530, 상품 별칭 4262 → 4271.
- 별칭 9개:
  - 표준 영문명: `Jack Daniel's Tennessee Apple`
  - 메뉴판 표기: `잭다니엘(Jack Daniel) 애플` (미라보), `잭다니엘 애플` (오드비)
  - 통상 표기 (출처 `generated:claude-2026-11-21`, 웹 검색 없이 Claude가 씀, 진우 검수 전): `Jack Daniel's Apple`, `잭 다니엘스 테네시 애플`, `잭다니엘 테네시 애플`, `잭 다니엘스 애플`, `잭다니엘스 애플`, `잭 대니얼스 테네시 애플`
- `version` `catalog_v2_4_service`, `created` 2026-11-21, `based_on`과 `notes`에 변경을 적었다. `ai/catalog/README.md`에 15장을 추가했다.
- 정규화 충돌 검사: 브랜치 `i2-catalog-v2`의 `check_catalog_v2.py`를 이 파일에 돌렸다. 상품 간 충돌 0, 브랜드 간 충돌 0, 무결성 OK(id가 key에서 다시 만든 값과 같음).
- 파일 SHA-256은 `9feb1874…`에서 `eb104dbd…`로 바뀌었다.
- 고치지 않은 것: P47 평가 스냅샷 두 개(`catalog_v2_eval_5bars*.json`, 기록용), 데모 메뉴 seed(`menu_seed_mirabeau_demo_v1.json`, `menu_seed_odbi_demo_v1.json`에는 이 줄이 없다). 운영 DB 적재는 하지 않았다.

### 2.2 정답: 이 줄을 비위스키로 적은 곳

| 파일 | 줄 | 바꾼 것 |
|---|---|---|
| `eval/match_gold_final_v1.json` | 954 | `009_오드비_04` "잭다니엘 애플"의 `gold`: `non_whisky` → `jack-daniels-apple` |
| `eval/match_gold_final_v1.json` | 68 | `review` 메모에 2026-11-21 수정 사유를 적음 |
| `ai/eval/i3_match_eval.py` | 333~334 (삭제) | dev에서 `jack-daniels-apple` 정답을 `non_whisky`로 바꾸던 예외 2줄. 미라보의 "잭다니엘(Jack Daniel) 애플"은 `eval/match_gold_v1_1.json`에 원래 `new:jack-daniels-apple`로 적혀 있고, 이 예외가 비위스키로 바꾸고 있었다 |
| `ai/regression/fixtures/009_오드비_04.json` | 174 | `gold`: `non_whisky` → `jack-daniels-apple` (`regression.py --update`) |
| `ai/regression/baseline.json` | 3597~3602, 7389~7394 | 이 줄의 기준 결과(deployed, heldout): `non_whisky` / unmatched / no_candidate → known / correct / exact_match / confirmed (`--update`) |

혼합 줄 정답 `ai/regression/mixed_lines.json`에는 이 줄이 없다. 라벨에 있는 줄은 매칭 정답이 `non_whisky`이면 비위스키로 세는 구조라서, 위 정답 수정으로 같이 바뀐다. `eval/match_gold_v1_1.json`, `eval/match_gold_v1.json`, `eval/match_gold_test_draft.json`은 처음부터 위스키(`new:jack-daniels-apple`)로 적혀 있어 고칠 것이 없었다.

### 2.3 따라서 고친 테스트와 고정값

| 파일 | 바꾼 것 |
|---|---|
| `ai/eval/test_i3_match_eval.py` | `gold_for`가 이 정답을 `non_whisky`로 바꾼다는 기대 → 다른 상품과 같이 다룬다는 기대. I3 asis 카탈로그 digest 고정값: v2.3의 `7c65fa51…`와 달라졌음을 확인하고 v2.4의 `b82cacac…`를 고정 |
| `ai/eval/p30_extract.py`, `test_p30_extract.py` | P30 동결 해제 목록(`RELEASED_MATCHING`)에 `ai/catalog/catalog_v2_service.json` 추가. I3 때의 해시는 기록으로 남겼다. 이 목록에 넣지 않으면 P30 실행기와 그 테스트 34개가 카탈로그 해시 불일치로 멈춘다 |
| `ai/regression/test_review_states.py` | 검수 상태 고정값: deployed confirmed 397 → 398, no_candidate 16 → 15. heldout confirmed 313 → 314, no_candidate 35 → 34 |
| `ai/regression/test_mixed_report.py` | 기대 줄 수(위스키 461 → 462, 기타 43 → 42), 머리 숫자, 틀린 줄 목록에서 "잭다니엘 애플" 제외. 비교 대상 보고서를 `ai/runs/2026-11-21_i5_not_whisky/mixed_report.*`(정답 수정 후)로 바꿈 |

I4에 보고한 `ai/runs/2026-11-13_p25/mixed_report.*`는 고치지 않았다. 테스트가 "저장된 보고서 = 다시 계산한 보고서"를 요구해서, 정답 수정 후 보고서를 이 폴더에 따로 만들고 테스트가 그것을 보게 했다.

테스트 결과: `ai/eval` + `ai/regression` 271개 중 270 통과, 1 실패. 실패 1개(`test_p30_extract.py::test_reencoded_ocr_cache_without_provenance_stops`)는 수정 전에도 같은 환경에서 실패했다. 카탈로그를 읽는 백엔드 테스트 7개 파일은 25 통과, 69 건너뜀(DB가 필요한 테스트).

### 2.4 숫자 변화 (정답 수정 후)

**추출 쪽 혼합 줄 보고서** (본 사진 15장 × 3회, `mixed_report.md`)

| | 정답 수정 전 (I4 보고) | 정답 수정 후 |
|---|---|---|
| 프롬프트 v2: 비위스키를 위스키로 | 20 | 17 |
| 프롬프트 v2: 비위스키 줄 재현 | 234 / 243 | 231 / 240 |
| 프롬프트 v1: 비위스키를 위스키로 | 61 | 58 |
| 위스키를 비위스키로 (v1, v2) | 0 | 0 |

v2에서 남는 틀린 줄은 헤네시vsop / Hennessy vsop, 레미마틴vsop / Remy Martin vsop, 헤네시 VSOP, 김과장 #2 (바베이도스 럼)이다.

**dev 5곳 규칙 매칭** (836줄, 카탈로그 구성 `service`, 지금 코드)

| | v2.3, 정답 수정 전 | v2.4, 정답 수정 후 |
|---|---|---|
| 카탈로그에 있는 줄 | 802 | 804 |
| Top-1 | 623 / 802 | 625 / 804 |
| 틀린 확인 권장 | 4 | 3 |
| 업주 부담 (confirm / choose / register / wrong) | 89 / 44 / 71 / 9 | 89 / 44 / 70 / 8 |

- 바뀐 줄은 3개다. 잭다니엘 애플 두 표기는 별칭으로 바로 확정된다(이전: 미라보는 Old No.7을 확인 권장하는 틀린 후보, 오드비는 후보 없음). 오드비의 "잭다니엘" 줄은 선택 후보에 Tennessee Apple이 하나 더 붙고 결과는 같다.
- 임베딩 단계까지 가면 미라보의 "잭다니엘(Jack Daniel) 넘버 7"에도 Tennessee Apple이 후보로 하나 더 붙는다(결과 같음).

**1단계 표 (dev, M3a `kind`)**

| 정답 | 수정 전 | 수정 후 |
|---|---|---|
| 비위스키: `non_whisky`로 답함 | 16 / 18 | 16 / 16 |
| 위스키: `non_whisky`로 답함 | 2 / 184 | 2 / 184 |
| 변형 B (규칙 후보 0일 때만 표시): 비위스키 표시 / 위스키 잘못 표시 | 16 / 18, 0 | 16 / 16, 0 |

잭다니엘 애플 두 줄은 이제 규칙이 확정하므로 LLM 대상에서 빠진다(218 → 216줄). 이 표는 11-13 응답을 정답만 바꿔 다시 센 것이다. 두 줄이 대상에서 빠지면 그 사진 2장의 LLM 입력이 달라지므로, 같은 사진의 다른 줄 응답은 새로 호출해야 확인된다(4단계).

**I3 33장**

- 정답은 바뀐 것이 없고(I3 라벨에 잭다니엘 애플 없음), 규칙 결과는 full·ops·asis 모두 줄 단위로 같다(Top-1 500 / 646, 511 / 646, 472 / 564).
- 기존 LLM 캐시로 full·ops r1을 새 카탈로그에서 다시 채점했다. 캐시 31개가 모두 맞고, `kind` 표와 Top-1·업주 부담·FM·틀린 확인 권장이 P46 값과 같다.
- 임베딩 단계에서 후보 순서나 4번째 이후 후보가 바뀐 줄이 있다(full 5줄, ops 3줄, asis 9줄). 결과 판정과 업주 부담은 같다. 상품이 하나 늘어 TF-IDF 가중치가 조금 달라진 영향이다.
- 카탈로그 digest는 바뀌었다(asis `7c65fa51` → `b82cacac`, full `633682b4` → `bc5dc495`, ops `23a66ea4` → `72af115b`). 그래서 이후 I3 숫자는 P46과 "바이트까지 같은 카탈로그"가 아니다.

### 2.5 다른 플레이버드 위스키 (목록만)

라벨 4종(`labels_v1_1`, `labels_heldout_v1_1`, `labels_final_v1`, `labels_i3_v1`)과 혼합 줄 정답 2종에서 허니·파이어·애플·피치·시나몬·리큐어 등의 낱말로 찾았다. **잭다니엘 애플 말고는 플레이버드 위스키가 없다.** 낱말에 걸렸지만 해당하지 않는 줄:

- 밀크 앤 허니(M&H) 2줄: 증류소 이름
- 글렌모렌지 테일 오브 스파이스, 마르스 더 럭키캣 하나 앤 초코: 이름만 그렇고 일반 위스키(이미 위스키 정답)
- Widow Jane Apple Wood Rye: 사과나무 통 숙성 라이(이미 위스키 정답)
- 비위스키 정답으로 남은 줄(dev 16, I3 4)은 코냑, 아르마냑, 럼, 병맥주뿐이다.

## 3단계: 설계안 (코드 수정 없음)

### 3.1 지금 `kind`가 사라지는 곳

메뉴 등록 처리(`backend/app/services/menu_import_processing.py`의 `_resolve_and_draft`)의 순서는 규칙 → LLM 층 → 임베딩 후보 → 연결 가드 → 저장이다.

| 단계 | 파일 | 지금 하는 일 |
|---|---|---|
| LLM 층 | `matching/llm_layer.py` 391행 | `kind != "whisky"`이면 규칙 결과 `base`를 그대로 돌려준다. `non_whisky`와 `unclear`와 "응답 없음"이 구분되지 않는다 |
| 결과 타입 | `matching/types.py` `ResolutionResult` | `status`, `candidates`, `proposed_product_id`, `parts`뿐이다. 줄 단위 메모를 실을 자리가 없다(근거 `evidence`는 후보에만 있다) |
| 임베딩 | `matching/embedding.py` 102행 | 후보 없는 줄에 후보를 붙일 때 `ResolutionResult`를 새로 만든다. 결과에 필드를 더해도 여기서 떨어진다 |
| 연결 가드 | `matching/linking_guards.py` | `replace`로 고치므로 새 필드는 유지된다 |
| 검수 상태 | `matching/review_state.py` | 후보 수와 `confirmRecommended`만 본다. 후보 없는 줄은 `no_candidate` → 저장 상태 `unmatched` |
| 저장 | `models/menu_import.py` `ExtractedItem` | 줄 단위로 저장되는 것은 `extracted_kind`(추출이 붙인 whisky / other), `initial_resolution_status`, 후보 행이다. 매칭 쪽 판정을 담을 컬럼이 없다 |
| 검수 응답 | `schemas/menu_import.py` `ReviewItem` | `extractedKind`, `initialResolutionStatus`, `candidates[].evidence`를 내보낸다. 후보가 없는 줄은 근거를 실을 곳이 없다 |
| 화면 | Android `LivePhotoReviewMapping.kt` 82~93행 | `extractedKind`가 other이면 "그 외 메뉴", 아니면 후보 수로 EXACT / CANDIDATE / AMBIGUOUS / NEW를 정한다. 후보 없는 위스키 줄은 NEW(새 상품 등록)로 보인다 |

같이 확인한 것:

- **비위스키 줄을 저장하는 길은 main에 이미 있다.** `bar_menu_items.product_id`는 nullable이고 `kind`(whisky / other) 컬럼이 있다(#164). 검수 결정 `publish_without_product`에 `kind = other`를 보내면 상품 없이 게시되고, 추출의 판단과 다르면 `corrected_kind`에 남는다(명세 8.10). 인계 문서 6절은 이 저장 방식을 "정하는 중"이라고 했는데 코드에는 들어와 있다.
- **owner-web에는 메뉴 검수 화면이 아직 없다**(신청 폼만 있음). 검수 화면은 Android다.
- **LLM 층은 서버 기본값이 꺼짐이다**(`MATCHING_LLM_ENABLED=false`). 꺼져 있으면 `kind`도 없다. 운영 서버에서 켜져 있는지는 확인하지 못했다.
- 도구 호출 층(`matching/tool_layer.py` 252행, `MATCHING_LLM_MODE=tools`)에도 같은 `kind`가 있고 같은 식으로 버려진다.
- 이름을 고쳐 다시 매칭하는 경로(`matching/rematch.py`)는 LLM을 부르지 않으므로 관계없다.

### 3.2 범위 1: 매칭 층과 평가 하네스만 (진우 영역)

API 응답·DB·화면은 바뀌지 않는다. 판정을 결과 객체까지 싣고, 하네스로 잰다.

1. **`ResolutionResult`에 필드 하나 추가.** `kind_hint: Literal["non_whisky"] | None = None`. 기본값이 None이라 기존 코드와 테스트는 그대로 돈다.
2. **`M3Engine.resolve()`에 플래그.** `LLMLayerConfig.flag_non_whisky: bool = False`(기본 꺼짐). 켜져 있고 `kind == "non_whisky"`이고 표시 조건(3.4)이 맞으면 `replace(base, kind_hint="non_whisky")`를 돌려준다. 후보·상태는 건드리지 않는다. `unclear`와 응답 없음은 지금처럼 `base` 그대로.
3. **임베딩 단계에서 필드 유지.** `embedding.apply_policy`가 새 결과를 만들 때 `kind_hint`를 넘겨받게 한 줄 고친다. 표시된 줄에도 임베딩 후보는 지금처럼 붙는다. 표시는 표시일 뿐이고 다른 동작을 바꾸지 않는다는 원칙 때문이다.
4. **검수 상태는 그대로.** `review_state`와 `stored_status`는 바꾸지 않는다. 표시된 줄은 여전히 `no_candidate` 또는 `choose_candidate`이고, 표시는 그와 별개의 정보다. 규칙이 확정한 줄은 LLM에 묻지 않으므로 표시될 수 없다.
5. **하네스(`ai/eval/i3_match_eval.py`).** 줄 결과에 `kind_hint`를 적고, 요약에 네 숫자를 더한다: 비위스키를 맞게 표시한 줄, 위스키를 잘못 표시한 줄, 미상을 표시한 줄, 표시되지 않고 "후보 없음"으로 남는 줄. `--flag-non-whisky` 옵션으로 켠다.
6. **업주 부담 지표는 정의를 바꾸지 않는다.** 지금 정의(`match_eval.burden_kind`)에서 후보 없는 줄은 정답이 비위스키여도 `register`로 센다. 표시가 붙어도 이 숫자는 그대로 두고, "`register` 중 표시가 붙은 줄"을 따로 적는다. 결과를 보고 판정 기준을 바꾸지 않기 위해서다.
7. **테스트.** 플래그 꺼짐이면 결과가 지금과 같음, 켜짐이면 조건별 표시, 규칙 확정 줄은 표시 없음, 임베딩·가드를 지나도 표시 유지.
8. **도구 호출 층은 이번에 넣지 않는다.** 실험용 모드이고 측정 캐시도 M3a 것이다. 필드는 같이 쓸 수 있게 해 둔다.

범위 1만으로는 서버가 표시를 저장하지도 내보내지도 않는다. 업주 화면에는 아무 변화가 없다.

### 3.3 범위 2: API 응답·DB·화면 (해울·호진과 정할 것, 구현하지 않음)

| 항목 | 정할 것 | 관련 파일 |
|---|---|---|
| 저장 | 줄마다 표시를 어디에 둘지. (가) `extracted_items`에 nullable 컬럼 추가(마이그레이션 필요), (나) 컬럼 없이 `extracted_kind`를 other로 바꿔 저장 | `models/menu_import.py`, alembic, `menu_import_processing.py` 332행 근처 |
| 검수 응답 | (가)이면 `ReviewItem`에 필드 추가(예: `kindHint: "non_whisky" \| null`), 명세 5.4 수정, OpenAPI 재생성 | `schemas/menu_import.py`, `services/menu_import_review.py`, `docs/frontend_backend_api_spec.md`, `owner-web/src/api/schema.d.ts` |
| Android | 응답 모델에 필드 추가, 후보 없는 줄(NEW)에 "위스키가 아닌 것 같아요" 문구와 "그 외 메뉴로 게시" 한 번 누르기 | `network/OwnerApiModels.kt`, `data/owner/review/LivePhotoReviewMapping.kt`, `ui/owner/ExtractionReviewViewModel.kt` |
| 검수 제출 | 새 결정 종류는 필요 없다. 기존 `publish_without_product`(`kind = other`)를 쓴다 | 변경 없음 |
| 설정 | 운영에서 LLM 층과 이 플래그를 켤지, 호출 상한(`MATCHING_LLM_MAX_CALLS`)은 그대로인지 | 서버 환경변수, `backend/README.md` |
| 문서 | 매칭 흐름 문서에 표시 단계 추가 | `docs/menu_ai_matching_flow.md` |

저장 방식 (가)와 (나)의 차이:

- **(가) 새 컬럼 + 새 응답 필드.** 표시와 추출 판단이 따로 남는다. 줄은 여전히 위스키 줄로 보이고 문구만 붙는다. 기본 결정은 바뀌지 않는다. 마이그레이션, 명세, Android 수정이 든다.
- **(나) `extracted_kind = other`로 저장.** API와 화면을 하나도 안 고쳐도 지금 화면이 그 줄을 "그 외 메뉴"로 묶어 보여 준다. 대신 기본 결정이 `publish_without_product`(other)로 바뀌고, 그 줄은 후보와 새 상품 초안이 비게 된다(명세 5.4의 other 줄 규칙). 업주가 그대로 제출하면 위스키가 아닌 메뉴로 게시된다. "표시일 뿐이고 결정은 업주가 한다"보다 한 걸음 더 나간 동작이다. 추출이 붙인 판단과 매칭이 붙인 판단이 한 컬럼에 섞여 나중에 구분할 수 없다.

권고는 (가)다. 진우가 정한 "자동으로 지우지 않는다, 표시일 뿐"에 맞는 쪽이 (가)이기 때문이다. (나)는 팀 간 수정이 없다는 장점이 있지만 잘못 표시된 위스키 줄이 검색에서 빠지는 길이 생긴다.

### 3.4 표시 조건 권고: "규칙 후보가 없을 때만" (변형 B)

1단계 숫자:

| 변형 | dev 비위스키를 맞게 표시 | dev 위스키를 잘못 표시 | I3 비위스키 (3회) | I3 위스키 잘못 표시 |
|---|---|---|---|---|
| A. `non_whisky`이면 표시 | 16 / 16 | 2 / 184 | 4 / 4 | 0 |
| B. A + 규칙 후보 0 | 16 / 16 | 0 / 184 | 4 / 4 | 0 |
| C. A + 임베딩 후 후보 0 | 15 / 16 | 0 / 184 | 4 / 4 | 0 |

(dev 분모는 2단계 정답 수정 후.)

**B를 권고한다.**

- A에서 잘못 표시된 2줄(독수리 오형제 1호·3호)은 규칙이 정답 상품을 후보로 내고 있던 줄이다. B는 이 둘을 막고, 맞는 표시는 하나도 잃지 않는다.
- B는 "카탈로그가 후보를 낸 줄은 건드리지 않는다"로 설명된다. 진우가 정한 "규칙이 확정한 줄에는 묻지 않는다"와 같은 방향이다.
- C는 권고하지 않는다. 임베딩이 붙인 틀린 후보(김과장 #2 럼 → Kim Gwajang #4 Clynelish) 때문에 맞는 표시 1줄을 잃고, B보다 더 막는 줄은 없다. LLM 층 뒤에 오는 임베딩 결과를 기다려야 해서 구현 위치도 달라진다.
- B의 판단 위치는 `M3Engine.resolve()` 안이다. `base.candidates`가 비어 있는지만 보면 된다.

한계:

- B가 위스키를 지킨 근거는 2줄(한 매장, 한 브랜드)이다. 카탈로그에 없는 위스키가 맥주·코냑처럼 보이는 이름이면 규칙 후보가 없으므로 B에서도 표시된다. 그래서 표시는 문구에 그쳐야 하고, 기본 결정을 바꾸는 (나)와 같이 쓰면 위험이 커진다.
- 표시가 붙는 줄은 적다. dev 836줄 중 16줄(1.9%), I3 675줄 중 4줄(0.6%)이다. dev에서 LLM 층 뒤 `register` 42줄 중 16줄, I3(ops)에서 34줄 중 4줄이 표시 대상이다.
- 3회 반복이 있는 것은 I3뿐이고 dev는 1회다. 4단계에서 dev를 다시 재면 반복 간 흔들림을 볼 수 있다.

### 3.5 4단계에서 할 것 (승인 후)

- 범위 1의 1~7번을 구현한다(플래그 기본 꺼짐, 변형은 B. A도 하네스 옵션으로 남겨 비교한다).
- dev 836줄과 I3(full, ops)에서 다시 잰다. I3는 기존 캐시가 그대로 맞아 새 호출이 없다. dev는 2단계 카탈로그 변경과 11-13 이후 규칙 변경으로 캐시가 안 맞는 사진만 새로 호출한다. 1회 기준 최대 26회(사진 수)이고, 60회 상한 안이다. 2회째를 돌리면 넘을 수 있으므로 그때는 멈추고 묻는다.

## 4단계: 구현과 측정

### 4.1 구현 (플래그 기본 꺼짐)

| 파일 | 바꾼 것 |
|---|---|
| `backend/app/matching/types.py` | `ResolutionResult.kind_hint` 추가 (`"non_whisky"` 또는 None, 기본 None) |
| `backend/app/matching/llm_layer.py` | `LLMLayerConfig.flag_non_whisky`(기본 False), `M3Engine.resolve(..., flag_non_whisky=False)`. 켜져 있고 LLM이 `non_whisky`로 답했고 규칙 후보가 0이면 규칙 결과에 `kind_hint`만 붙여 돌려준다. `unclear`, 응답 없음, 규칙 후보가 있는 줄은 지금처럼 그대로 |
| `backend/app/matching/embedding.py` | 후보 없는 줄에 후보를 붙일 때 결과를 새로 만들지 않고 `replace`로 고쳐 `kind_hint`가 남게 함 |
| `backend/app/services/menu_import_processing.py` | 설정의 `flag_non_whisky`를 `resolve()`에 넘김. 환경변수는 만들지 않았다(서버가 표시를 저장·응답하지 않으므로 켤 길을 열지 않음) |
| `ai/eval/i3_match_eval.py` | `--flag-non-whisky` 옵션. 줄 결과에 `kind_hint`, `llm_kind`, `base_n_cand`. 요약 `not_whisky`: 정답 분류별 표시 수, 변형 A·B·C, 표시가 붙은 줄의 업주 부담, "후보 없음" 줄 수와 그중 표시 없는 줄 |
| `ai/eval/p30_extract.py`, `test_p30_extract.py` | P30 동결 해제 목록에 `llm_layer.py` 추가(I3 해시는 기록으로 유지) |

추가한 테스트: `backend/tests/test_llm_layer.py` 5개(표시 조건, 기본 꺼짐, 규칙 후보가 있으면 그대로, `unclear`·응답 없음은 그대로, 위스키 줄은 표시 없음), `test_embedding.py` 1개(임베딩 후보가 붙어도 표시 유지), `test_review_state.py` 1개(검수 상태는 그대로), `ai/eval/test_i3_match_eval.py` 1개(지표 계산).

테스트 결과:

- `ai/eval` + `ai/regression`: 272개 중 271 통과, 1 실패(2단계 전부터 실패하던 `test_reencoded_ocr_cache_without_provenance_stops`).
- 백엔드 매칭 관련 8개 파일: 239 통과, 60 건너뜀. 건너뛴 것은 DB가 필요한 테스트이고, `menu_import_processing.py`의 호출부를 지나는 테스트가 여기 들어 있다. 이 환경에서는 그 한 줄을 실행해 보지 못했다.

업주 부담 지표의 정의(`match_eval.burden_kind`)는 바꾸지 않았다. 표시가 붙어도 그 줄은 이전과 같은 부담으로 세고, 표시가 붙은 줄 수를 따로 적는다.

### 4.2 측정 조건

- 카탈로그 v2.4, 정답 수정 후(2단계). **I4에 보고한 숫자와 다른 조건이다.**
- 모델과 프롬프트는 그대로다(gemini-3.1-flash-lite, thinking low, `translate_prompt_v3.md`).
- I3 33장(675줄): full·ops, r1~r3. P46 캐시가 31개 모두 맞아 새 호출 0회.
- dev 5곳(836줄, 구성 `service`): 2회. r1은 11-13 캐시 19개를 재사용하고 7개를 새로 호출, r2는 26개 모두 새로 호출.
- **새 LLM 호출 33회**(상한 60회). 실패·재시도 없음. 3회차는 누적 59회가 되어 여유가 없어 돌리지 않았다.
- 플래그를 끈 실행을 같은 캐시로 따로 돌려 줄 단위로 비교했다: `kind_hint` 말고는 모든 줄이 같다(dev 2회, I3 6회, LLM 뒤·임베딩 뒤 모두).
- 결과 파일: `match/dev_service_{on,off}_r{1,2}.json`, `match/i3_{full,ops}_label_{on,off}_r{1,2,3}.json`. 새 응답 캐시: `cache_dev_r1`, `cache_dev_r2`.

### 4.3 결과: 표시

| | LLM 대상 | 비위스키를 맞게 표시 | 위스키를 잘못 표시 | 미상을 표시 |
|---|---|---|---|---|
| dev r1 | 211 | 16 / 16 | 0 / 179 | 0 / 16 |
| dev r2 | 211 | 16 / 16 | 0 / 179 | 0 / 16 |
| I3 full r1 / r2 / r3 | 166 | 4 / 4 (3회 모두) | 0 / 138 | 0 / 24 |
| I3 ops r1 / r2 / r3 | 155 | 4 / 4 (3회 모두) | 0 / 127 | 0 / 24 |

변형 비교(dev, r1과 r2가 같음):

| 변형 | 비위스키를 맞게 표시 | 위스키를 잘못 표시 |
|---|---|---|
| A. `non_whisky`이면 표시 | 16 / 16 | 2 / 179 |
| B. A + 규칙 후보 0 (구현한 것) | 16 / 16 | 0 / 179 |
| C. A + 임베딩 후 후보 0 | 15 / 16 | 0 / 179 |

- A에서 잘못 표시되는 2줄은 두 번 다 크래프트브로스 독수리 오형제 1호·3호다. LLM은 새로 물어도 같은 답을 했고, B는 규칙 후보(정답 상품)가 있어 표시하지 않는다.
- 표시된 dev 16줄: 헤네시 VSOP 2, 레미마틴 VSOP 1, 김과장 #2 (바베이도스 럼) 1, 아르마냑 8, 병맥주 4. I3 4줄: Foursquare Rum 1, 헤네시 VSOP 2, 헤네시 XO 1.
- 잭다니엘 애플 두 줄은 규칙이 확정해서 LLM에 가지 않는다. 그 사진 2장의 다른 줄 응답도 표시 결과에 영향이 없었다.
- I3에서는 A·B·C가 같다.

### 4.4 결과: "후보 없음"으로 남는 줄

임베딩 단계까지 거친 뒤(서버가 저장하는 상태) 기준.

| | 후보 없음 | 그중 표시 있음 | 표시 없음 |
|---|---|---|---|
| dev r1, r2 | 18 | 15 | 3 |
| I3 full r1 / r2 / r3 | 8 / 9 / 9 | 4 | 4 / 5 / 5 |
| I3 ops r1 / r2 / r3 | 8 / 8 / 8 | 4 | 4 |

- dev의 표시 없는 3줄은 모두 정답 미상인 위스키 줄이다(SANSIBAR 21y 2줄, 카발란 증류소 킹 카 위스키 올드보틀).
- dev에서 표시된 16줄 중 1줄(김과장 #2 럼)은 임베딩이 틀린 후보(Kim Gwajang #4 Clynelish)를 붙여 "후보 선택" 상태가 된다. 표시는 그대로 남는다.
- LLM 층 직후 기준으로는 후보 없음이 dev 41 / 42줄(표시 16), I3 full 37 / 37 / 36줄, ops 34 / 35 / 34줄(표시 4)이다.

### 4.5 결과: 업주 부담과 매칭 지표 (플래그와 무관하게 같음)

플래그를 켜도 꺼도 아래 숫자는 같다. 표시는 후보와 상태를 바꾸지 않기 때문이다.

| | Top-1 | FM | 틀린 확인 권장 | confirm / choose / register / wrong (임베딩 뒤) |
|---|---|---|---|---|
| dev r1 | 625 / 804 | 0 | 3 | 133 / 54 / 18 / 6 |
| dev r2 | 625 / 804 | 0 | 3 | 134 / 53 / 18 / 6 |
| I3 full r1 / r2 / r3 | 500 / 646 | 1 | 3 | 111/41/8/6, 111/41/9/5, 110/41/9/6 |
| I3 ops r1 / r2 / r3 | 511 / 646 | 1 | 3 | 103/39/8/5, 103/39/8/5, 102/40/8/5 |

- I3의 숫자는 P46 값과 같다(카탈로그에 상품 하나가 늘었지만 줄 결과가 같음).
- 표시가 붙은 줄의 부담 분류(임베딩 뒤): dev는 `register` 15줄 + `wrong` 1줄(김과장 #2 럼), I3는 `register` 4줄.
- 즉 지금 정의로 `register`인 줄 가운데 dev 18줄 중 15줄, I3 8~9줄 중 4줄이 "위스키가 아닌 것 같아요"로 바뀌어 보일 줄이다. 이 줄들을 `register`에서 빼고 세려면 판정 기준(`eval_plan.md`)을 고쳐야 하고, 이번에는 고치지 않았다.

### 4.6 남은 것과 한계

- **업주 화면에는 아직 변화가 없다.** 서버는 표시를 저장하지도 응답에 싣지도 않는다. 3.3절의 범위 2(저장 위치, 검수 응답 필드, Android)가 정해져야 한다.
- 위스키가 잘못 표시될 뻔한 사례는 여전히 2줄(한 매장, 한 브랜드)뿐이다. 규칙 후보가 없는 위스키가 `non_whisky`로 읽힌 사례는 dev·I3에 없었다. 그런 줄이 얼마나 되는지는 이 자료로 알 수 없다.
- 미상 줄은 dev 16줄, I3 24줄 모두 표시되지 않았다.
- dev는 2회, I3는 3회다. I3 3회는 P46 때의 응답이고 이번에 새로 부른 것이 아니다.
- 추출 입력(e2e)은 다시 재지 않았다. 1단계에서 본 대로 추출이 넘긴 코냑 3줄(리틀 갤러리, r1)이 `non_whisky`로 읽혔고 규칙 후보가 0이라, 같은 조건이면 표시된다.
- 도구 호출 층(`MATCHING_LLM_MODE=tools`)에는 넣지 않았다.
