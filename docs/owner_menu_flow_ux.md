# 업주 메뉴 등록 화면 명세 (사진 올리기 → 읽기 → 확인 → 게시)

| 항목 | 내용 |
|---|---|
| 화면 디자인 | I3-P25, 박진우 |
| 구현 | I3-P23 검수 화면, I3-P27 업로드·처리·게시 흐름 (남호진) |
| 시안 | Claude Design 캔버스 "사장님 메뉴 등록 (P25)" — https://claude.ai/artifact/9VyzrvkQx42FxiX5bH14BU (재생 버튼으로 화면을 눌러 볼 수 있다. 공유받아야 열린다) |
| 따르는 문서 | `DESIGN.md`(색·글꼴·크기·5.2 업주 흐름), `Tokens.kt`, `docs/android_icons.md`(`BmIcon`), `docs/frontend_backend_api_spec.md` 4~9장, `docs/menu_ai_matching_flow.md` |
| 기준 코드 | `main` 9d77792 (#68 LLM 매칭 층 포함, `MATCHING_LLM_ENABLED`는 꺼짐), 검수 응답 `sourceBox`는 I3-P25 백엔드 PR |

이 문서는 화면과 동작의 명세이며 API 계약을 바꾸지 않는다. 계약에 없는 것은 10장에 "없을 때의 대체 동작"과 함께 적었다. 화면 배치·문구는 시안이 기준이고, 시안에 보이지 않는 규칙(분류, 버튼이 켜지는 조건, 오류, 상태 보존)은 이 문서가 기준이다. 둘이 다르면 이 문서를 따르고 박진우에게 알린다.

---

## 1. 목표와 원칙

### 1.1 왜 다시 만드는가

지금 개발용 빌드의 검수 화면(`ExtractionReviewViewModel.applyDefaultReview()`)은 검수가 아니라 일괄 승인이다.

- 상품 줄마다 1순위 후보(`proposedProductId`)로 `select_existing_product`를 보낸다. 후보가 여럿이라 확정하지 못한 `ambiguous` 줄도 같다. API 명세 10장은 `proposedProductId`를 확정값으로 쓰지 말라고 한다.
- 후보가 없으면 `create_product`에 `brand.type = new`, `canonicalName = draft.brandText ?: displayName`을 보낸다. `brandText`는 항상 `null`이므로(2.2) 메뉴 줄 전체(예: `시그나토리 쿨일라13`)가 새 브랜드 이름이 된다. 운영 DB에 쓰레기 브랜드·상품이 생긴 원인이다.
- `proposedChanges`를 전부 `apply`한다. 전체 교체의 `remove`(지금 메뉴에서 내리기)도 업주가 보지 않은 채 적용된다.
- LLM 매칭 층(M3a, #68)은 후보를 항상 `ambiguous`로 내고 "확인만 하면 되는 줄"을 `evidence.confirmRecommended`로 표시한다. 이 흐름 없이 LLM 층을 켜면 LLM 후보가 그대로 확정되므로, 서버의 LLM 층은 P23이 나갈 때까지 꺼 둔다.

### 1.2 목표

업주가 **확실하지 않은 줄마다 직접 결정**하게 하되, 그 비용을 **탭 몇 번**으로 줄인다. 타이핑은 가격을 못 읽었을 때, 카탈로그 검색, 새 브랜드 영문 이름(선택)에만 쓴다.

### 1.3 원칙

1. **단계가 보인다.** 업주 흐름은 "사진 올리기 · 읽기 · 확인 · 게시" 네 단계이고 화면 위에 늘 보인다(`DESIGN.md` 5.2). 퍼센트는 없다.
2. **한 번에 질문 하나.** 확인이 필요한 줄마다 카드 한 장, 카드마다 질문 하나("이 술이 맞나요?", "어느 술인가요?"). 요약·자동 목록·게시 확인은 촘촘한 목록으로 둔다(`DESIGN.md` 5.2 "검수에 한 질문-한 화면을 강요하지 말 것"과 이렇게 맞춘다).
3. **쉬운 한국어.** "매칭", "후보", "신뢰도" 같은 말을 쓰지 않는다. 영어는 상품·브랜드의 정식 이름에만 나온다.
4. **가짜 진행률 없음.** 사진은 "2장 중 1장", 카드는 `3 / 9`처럼 실제 개수만 보여 준다. `score`·`extractionConfidence`는 화면에 쓰지 않는다(점수는 순위용 값이지 확률이 아니다).
5. **모두 승인 버튼 없음.** 확인이 필요한 줄은 하나씩 결정해야 게시 버튼이 켜진다. 자동으로 찾은 줄만 탭 없이 포함되며, 요약에서 펼쳐 바꿀 수 있다.
6. **조용히 만들지 않는다.** 새 브랜드는 업주가 "새 브랜드로 만들기"를 눌러야 생긴다. 메뉴 줄 원문을 브랜드 이름으로 쓰지 않는다.
7. **내리기는 업주 결정.** 지금 메뉴에서 빠지는 술은 술마다 "내리기 / 남기기"를 고른다. 기본값이 없다.
8. **잃어버리지 않는다.** 결정은 기기에 저장되어 회전, 프로세스 종료, 네트워크 오류, `REVIEW_OUTDATED` 뒤에도 남는다(6.4).
9. **서버가 주지 않는 정보를 지어내지 않는다.** 예: 읽기 실패 이유, 처리 남은 시간, 바 사진.

---

## 2. 입력 데이터

### 2.1 화면별 API

| 화면 | API | 있음 |
|---|---|---|
| H0 내 바 | `GET /api/me/bars`(내 업장), `GET /api/bars/{barId}/menu`(게시된 메뉴, `publishedAt`), `GET /api/bars/{barId}/menu-imports`(최근 작업, `?status=active`로 진행 중 작업) | `me/bars`는 I3-P7에서 만드는 중. 나머지는 있음 |
| U1 사진 고르기 | `POST /api/bars/{barId}/menu-imports` (multipart `mode`, `ownerNote`, `images`) | 있음 |
| U2 읽는 중, U3 읽기 실패 | `GET /api/menu-imports/{id}` (`status = uploaded·processing·failed`) | 있음 |
| S1~S6 검수 | `GET /api/menu-imports/{id}` (`status = ready_for_review`, 명세 5.4), `GET /api/catalog/products`, `GET /api/catalog/brands` | 있음 |
| S7~S9 게시 | `POST /api/menu-imports/{id}/review-and-apply` (명세 8장) | 있음 |
| 검수 그만두기 | `POST /api/menu-imports/{id}/cancel` (명세 5.7) | **없음**(10장) |

**권한:** 지금은 위 API가 모두 운영자(operator) 전용이다. 업장의 승인된 업주가 부를 수 있게 하는 일은 I3-P22(양해울)다. 그 전에는 운영자 계정으로 같은 흐름을 확인한다.

### 2.2 검수 응답에서 쓰는 필드

| 필드 | 쓰는 곳 |
|---|---|
| `reviewVersion`, `mode`, `barId` | 제출, 내리기 카드 표시 여부(`full_replace`), 현재 메뉴 조회(10장 G7 대체 동작) |
| `images[].imageOrder`, `imageUrl`, `imageUrlExpiresAt` | "메뉴판 2" 표기, 메뉴판 줄 사진, 원본 사진 보기, 만료 시 재조회 |
| `items[].extractedItemId`, `itemOrder` | 카드 키, 정렬(사진 순 → 줄 순), "넷째 줄" 표기 |
| `items[].sourceBox` | 메뉴판 줄 사진 자르기(3.2) |
| `rawText`, `options[]` | 메뉴판 줄 띠(좌표가 없을 때), 가격 줄 |
| `effectiveLineType` | 상품 줄인지, 메뉴 줄이 아닌지 |
| `initialResolutionStatus` | `exact_match` / `ambiguous` / `unmatched` |
| `candidates[]` (`productId`, `candidateRank`, `displayName`, `brandId`, `brandName`, `ageYears`, `editionName`, `matchMethod`, `evidence`) | 카드 종류와 선택지, "왜" 한 줄 |
| `extractedProductName`, `newProductDraft` | 검색어 초기값, 새 술 카드 초기값 |
| `proposedChanges[]` (`changeId`, `changeType`, `extractedItemId`, `barMenuItemId`, `before`) | 제출할 `changeDecisions`, 내리기 카드 |

`score`, `extractionConfidence`, `summary`는 화면에 쓰지 않는다. `proposedProductId`는 "1순위 후보 ID"로만 읽는다(`candidates[0].productId`와 같다).

### 2.3 지금 서버가 실제로 채우는 값 (중요)

- 추출기(hybrid prompt v1: CLOVA OCR + Gemini)는 모든 항목을 `product`로 내고 `extractedBrandName`, `extractedAgeYears`, `extractedEditionName`, `extractedAbv`, `extractionConfidence`를 항상 `null`로 둔다. 따라서 `newProductDraft`는 `displayName`(= 메뉴 줄 이름)과 `category = whisky` 말고는 비어 있다. 새 술 카드의 초기값은 5.6의 대체 규칙으로 만든다.
- 잔·병 가격이 한 줄에 있으면 한 항목에 옵션 둘(`잔`, `병`)로 들어온다.
- 비위스키 섹션(칵테일, 코냑 등)은 추출 단계에서 빠지지만, 섞인 섹션 안의 비위스키(예: 알마냑)는 `product`로 들어온다. 이런 줄을 미리 알려 주는 필드는 없다(10장 G4).
- `effectiveLineType`이 `section_header`·`description`·`unknown`인 줄은 지금 추출기에서는 생기지 않지만 API에 정의되어 있으므로 처리한다.
- `sourceBox`는 hybrid 추출로 읽은 줄에만 있다. OCR이 실패해 Gemini 단독으로 넘어간 사진, OCR 줄 없이 사진에서만 읽은 줄은 `null`이다.
- 서버의 LLM 층이 꺼져 있으면 `confirmRecommended`가 없으므로 CONFIRM 카드는 생기지 않는다. 그 줄들은 CHOOSE나 NEW로 온다. 화면은 LLM 층을 켜도 끄도 같은 코드로 동작해야 한다.

---

## 3. 공통 부품

색·글꼴·크기는 `Tokens.kt`의 이름으로만 쓴다(`DESIGN.md` 0.9). 아래 값은 확인용이다.

| 역할 | 토큰 | 값 |
|---|---|---|
| 바탕 / 카드·입력칸 / 강조한 칸 / 조용한 칩 | `canvas` / `surface` / `surfaceElevated` / `surfaceVariant` | `#211E1B` / `#302B27` / `#3A332E` / `#403832` |
| 주 버튼·선택·현재 단계 | `primary`, 글자 `onPrimary` | `#C99D6B`, `#211A14` |
| 본문 / 보조 글자 | `textPrimary` / `textSecondary` | `#F2EDE8` / `#C7BBB0` |
| 구분선·조용한 테두리 / 입력칸 초점 테두리 | `outlineVariant` / `outline` | `#51473F` / `#786A60` |
| 오류 띠 | `errorContainer`, 글자 `onErrorContainer` | `#8E3736`, `#FFD8CC` |
| 화면 제목(질문) | `headlineSmall` = screenTitle, 북크명조 24sp Bold | 시안은 북크명조 대신 Noto Serif KR로 그렸다 |
| 상품 2줄 / 카드 제목 | `titleMedium` 16sp SemiBold | |
| 본문 / 버튼 글자 / 보조 설명 | `bodyLarge` 16sp / `labelLarge` 14sp / `bodySmall` 12sp | |
| 가격·용량 | `bottleMapPriceTextStyle` 16sp + `bottleMapPourTextStyle` 13sp, 가격 먼저 | `DESIGN.md` 6.6 |
| 주 버튼 / 보조·글자 버튼 | `primaryButtonMinHeight` 56dp / `secondaryButtonMinHeight` 48dp, `BottleMapShapes.button` | |

화면 좌우 여백은 `screenHorizontal`(20dp), 카드 안쪽은 `cardPadding`(16dp), 카드 모서리는 `BottleMapShapes.card`(16dp).

### 3.1 `StepProgress` (`DESIGN.md` 4장 부품 목록)

- 이름 넷: 사진 올리기 · 읽기 · 확인 · 게시. 같은 폭 4칸, 칸마다 3dp 막대 + `bodySmall` 이름.
- 지난 단계와 지금 단계: 막대 `primary`. 지금 단계만 이름이 `primary` SemiBold이고 `aria-current`(TalkBack: "4단계 중 3단계, 확인"). 다음 단계: 막대 `outlineVariant`, 이름 `textMuted`.
- 실패한 단계(U3): 막대와 이름을 `error`(`#FFB4AB`)로. 색만으로 구분하지 않도록 TalkBack에 "읽기 실패"를 넣는다.
- 보이는 화면: U1, U2, U3, S1 요약, S7·S8(게시 전), S9(모두 지남). 카드 화면(S2)에는 단계 대신 `k / N`을 둔다(화면 높이를 카드에 쓴다).

### 3.2 `MenuLineStrip` (새 부품: 메뉴판 줄)

카드 맨 위에서 그 줄이 메뉴판에 어떻게 적혀 있었는지 보여 준다.

- 위에 `bodySmall` 한 줄: "메뉴판 {imageOrder} · {itemOrder}째 줄"(첫째, 둘째 … 열째, 그 뒤는 숫자 "11번째 줄").
- **`sourceBox`가 있으면:** `imageUrl` 사진에서 그 상자를 잘라 보여 준다.
  - 좌표는 사진 가로·세로를 0–1000으로 본 `[x0, y0, x1, y1]`이고, EXIF 회전을 적용한 뒤의 사진 기준이다. 사진을 불러올 때도 EXIF 회전을 적용한다.
  - 상자를 위아래 25%, 좌우 2%씩 넓혀 자른다(글자가 상자에 딱 붙어 잘리지 않게). 사진 밖으로 나가는 부분은 사진 끝까지만.
  - 폭은 화면 폭에 맞추고 높이는 비율대로, 최소 48dp·최대 120dp. 모서리 `BottleMapRadii.small`(8dp).
  - 불러오는 중에는 같은 크기의 `surface` 칸, 실패하면 아래 종이 띠로 바꾼다.
  - 대체 텍스트: "메뉴판 {n}의 줄: {rawText}".
- **`sourceBox`가 `null`이면(또는 사진을 못 불러오면): 종이 띠.** 배경 `#E7DDCB`(병 일러스트 팔레트의 `labelChoices[0]`), 글자 `#2A231D`, 명조 18sp Bold. `rawText`의 이름 부분, 점선, 옵션 글자(예: `시그나토리 쿨일라13 ········ 20,000`)를 한 줄에, 길면 줄바꿈.
- 아래에 가격 줄: `20,000원` + `· 잔` 또는 `30ml`(가격 먼저, `DESIGN.md` 6.6). 가격이 `null`이면 가격 줄을 빼고 카드가 PRICE 단계를 묻는다. 오른쪽에 글자 버튼 "원본 사진 보기"(6.3).

### 3.3 `ProductChoiceRow`와 상품 두 줄 표기

모든 상품 표시는 같은 구조다.

- 1줄(`bodySmall`, `textSecondary`): `brandName` (예: `Signatory Vintage`)
- 2줄(`titleMedium`, `textPrimary`): 달라지는 부분 = `[ageYears → "{n}년", editionName]`을 ` · `로 이은 것. 둘 다 `null`이면 `displayName`에서 앞의 `brandName`을 뗀 나머지, 그것도 비면 `displayName`.
- 3줄(선택, `bodySmall`): 5.4의 "왜" 한 줄. 주의 문구(5.4 1~4)는 `error` 색 + TalkBack "주의:".
- TalkBack 이름은 `displayName` 전체.
- 왼쪽에 병 일러스트 M(24×38dp, `BottleMapSizes.productBottleMedium*`). 브랜드별 모양·색 규칙(`DESIGN.md` 10)이 정해질 때까지는 실루엣 하나 + 라벨 `BottleMapBottleIllustrationPalette.genericLabel`로 모든 상품이 같은 병이다. 장식이므로 TalkBack에서 숨긴다.
- 선택 행: 최소 72dp, 행 전체가 버튼(`Role.RadioButton`). 기본 테두리 1.5dp `outlineVariant`, 고른 행은 테두리 `primary` + 배경 `surfaceElevated` + 3줄 "고른 술"(색만으로 구분하지 않는다).

예: `Arran / Bodega Sherry Cask`, `Signatory Vintage / 13년 · Caol Ila`, `Booker's / Booker's`.

### 3.4 카드 틀

```
[←]           3 / 9                      ← 위: 뒤로(요약으로) + 진행
메뉴판 2 · 첫째 줄                         ← MenuLineStrip
[ 메뉴판 줄 사진 또는 종이 띠 ]
15,000원 30ml                 원본 사진 보기

어느 술인가요?                            ← 명조 24sp, 질문
메뉴판 글자로는 하나로 정하지 못했어요.       ← 부제(있으면)
 … 카드 본문 …

        [ 주 버튼 ]                       ← 카드 종류마다 다름
        [ 보조 버튼 ]
       위스키가 아니에요                     ← 상품 카드 모두에
‹ 이전        남은 확인 7개         다음 ›   ← 아래 고정
```

- 진행: 가운데 `현재 / 전체`만. 막대·퍼센트 없음.
- 이전/다음: 결정하지 않아도 넘어갈 수 있다(게시가 막혀 있으므로 빠뜨릴 수 없다). 첫 카드의 "이전"은 꺼진다. 마지막 카드의 "다음"은 "게시 전 확인"이 된다. 가운데 "남은 확인 n개"는 미결정 카드 수.
- 결정하면 `selectionMs`(180ms) 선택 표시 뒤 **결정하지 않은 다음 카드**로 넘어간다(없으면 S7/S8). 아래에 알림 "저장했어요 · 되돌리기"가 4초 보인다(3.5).
- 이미 결정한 카드로 돌아오면 고른 답이 선택된 상태로 보이고, 다시 고르면 결정이 바뀐다.
- 시스템 뒤로 = 이전 카드. 첫 카드에서 뒤로 = 요약.

### 3.5 알림과 오류 띠

- 결정 알림: 아래쪽(이동 막대 위), `textPrimary` 배경 + `canvas` 글자, 높이 48dp, 오른쪽 글자 버튼 "되돌리기"(`inversePrimary` `#7A532D`). 알림이 떠 있는 동안 아래 버튼을 가리지 않도록 본문 아래 여백을 64dp 둔다.
- 오류 띠(게시 실패 등): 화면 위, `errorContainer` 배경, `BmIcon(ERROR)` + 굵은 한 줄 + 설명 한 줄. 오류 띠가 있어도 사용자가 이미 한 결정은 그대로 보인다.

### 3.6 아이콘

`BmIcon`만 쓴다: 뒤로 `BACK`, 사진 `CAMERA`, 검수 `REVIEW`, 게시 `PUBLISH`, 다시 시도 `RETRY`, 오류 `ERROR`, 빈 상태 `EMPTY`, 검색 `SEARCH`, 내 바 `MANAGE_BAR`, 갱신일 `UPDATED`. 모두 기본 상태(A)다. 선택 상태(B)는 선택·켜짐에만 쓰고, 이 흐름에는 완료 화면의 `PUBLISH` 하나에만 쓴다. 되돌리기·확인 표시에는 맞는 아이콘이 없으므로 글자 버튼으로 둔다.

---

## 4. 사진 올리기와 읽기 (P27)

### 4.1 H0 내 바 (캔버스 "01 내 바")

- 위: "사장님"(라벨) + 마이페이지(`ACCOUNT`). 업장 이름은 명조 24sp. 업장이 여럿이면 업장 고르기는 I3-P39 "내 바 관리"에서 정하고 이 화면은 고른 업장 하나를 보여 준다.
- 게시된 메뉴 칸: `MANAGE_BAR` + "게시된 메뉴 {n}개"(`GET /api/bars/{barId}/menu`의 상품 수) + `UPDATED` "{M월 D일} 갱신"(`publishedAt`, 없으면 "아직 게시한 메뉴가 없어요") + "메뉴판 보기" 행.
- 최근 작업: `GET /api/bars/{barId}/menu-imports` 최근 2개. 행 = 모드("메뉴판 전체 교체" / "일부 수정") + "{날짜} · 사진 {imageCount}장" + 상태("게시함" `applied`, "확인 중" `ready_for_review`, "읽는 중" `uploaded·processing`, "실패" `failed`, "취소" `canceled`). 진행 중 작업을 누르면 그 작업의 U2 또는 S1 요약으로 간다.
- 주 버튼: `CAMERA` "메뉴판 사진 올리기" → U1. 진행 중 작업(`?status=active`)이 있으면 주 버튼은 "확인하던 메뉴판 이어서 하기"가 되고, 그 아래 글자 버튼 "새 사진 올리기"(10장 취소 API가 생기기 전에는 숨긴다).

### 4.2 U1 사진 고르기 ("02 사진 고르기")

- `StepProgress` 1단계. 제목 "메뉴판 사진을 올려 주세요", 부제 "메뉴판 순서대로 5장까지 올릴 수 있어요."
- 사진 칸: 3열 격자, 3:4 썸네일. 각 사진에 순서 번호(왼쪽 아래)와 빼기(오른쪽 위, 터치 44dp 이상, "{n}번 사진 빼기"). 마지막 칸은 "사진 추가"(`CAMERA`, "2 / 5"): 누르면 [카메라로 찍기] [앨범에서 고르기]. 5장이면 사라진다. 순서 바꾸기는 길게 눌러 끌기(이번 범위에서는 선택).
- 올리기 방식(라디오 두 줄, 필수, 기본값 "전체를 새로"):
  - "메뉴판 전체를 새로 올려요" / "사진에 없는 술은 내릴지 하나씩 물어볼게요." → `mode = full_replace`
  - "일부만 바꿔요" / "사진에 있는 술만 더하거나 가격을 바꿔요." → `mode = partial_update`
  - 선택된 행은 테두리 `primary`, 아니면 `outlineVariant`.
- 주 버튼: "사진 {n}장 올리기". 사진이 0장이면 꺼지고 "사진을 한 장 이상 골라 주세요"(I3-P27 "사진 없이 올리지 않기").
- 업로드 전 검사: JPEG·PNG가 아니면 JPEG로 바꾼다(지금 `ImageUploadPreparer`). 한 장 10MB, 합계 30MB를 넘으면 줄여서 올린다.
- 올리는 중: 버튼에 진행 표시 + "올리는 중이에요", 다른 조작 막기. `Idempotency-Key`는 이 화면에서 처음 올릴 때 만들고, 재시도에는 같은 값을 쓴다(지금 `MenuUploadRetryCache`).
- 오류(명세 4.4):

| 오류 | 화면 |
|---|---|
| 네트워크·`5xx` | 오류 띠 "사진을 올리지 못했어요. 인터넷 연결을 확인해 주세요." + [다시 시도](같은 키) |
| `409 ACTIVE_IMPORT_EXISTS` | "확인하던 메뉴판이 있어요" 대화상자 + [이어서 하기] → `details.menuImportId`의 U2 또는 S1. (취소 API가 생기면 [그 작업 그만두고 새로 올리기]) |
| `413 UPLOAD_TOO_LARGE` | "사진이 너무 커요. 사진 수를 줄여 주세요." |
| `415 UNSUPPORTED_IMAGE_TYPE` | "{imageOrder}번 사진은 올릴 수 없는 형식이에요" + 그 사진에 표시 |
| `409 IDEMPOTENCY_KEY_REUSED` | 새 키로 자동 재요청 한 번 |

### 4.3 U2 읽는 중 ("03 읽는 중")

- `StepProgress` 2단계. 제목 "메뉴판을 읽고 있어요", 부제 "화면을 나가도 계속 읽어요."(서버의 백그라운드 작업이라 참이다).
- 가운데 `GlassFillLoading`(96dp) + `role=status` 문구:
  - `completedImages < totalImages`: "사진 {total}장 중 {completed}장을 읽었어요"
  - `completedImages == totalImages`인데 아직 `processing`: "후보를 정리하는 중이에요"(명세 5.2: 모든 사진이 끝나도 잠시 `processing`일 수 있다)
  - 보조: "다 읽으면 확인할 줄을 보여 드릴게요."
- `pollAfterMs`(3초) 간격으로 `GET`. 화면이 보일 때만 부른다. 상태가 바뀌면: `ready_for_review` → S1 요약(또는 4.5의 빈 경우), `failed` → U3, `applied` → S9, `canceled` → "취소된 작업이에요" + [내 바로].
- 아래 보조 버튼 "내 바로 돌아가기". 뒤로도 같다. 다시 들어오면 H0 내 바의 진행 중 작업에서 이어진다.
- 남은 시간, 퍼센트, 단계별 이름(OCR·AI)을 보여 주지 않는다.

### 4.4 U3 읽기 실패 ("03-e 읽기 실패")

- `StepProgress` 2단계를 실패 색으로. 가운데 `ERROR` 아이콘(64dp 원) + 제목 "메뉴판을 읽지 못했어요".
- 설명: `failedImages > 0`이면 "사진 {total}장 중 {failed}장을 읽지 못했어요.", 아니면 "메뉴판을 처리하지 못했어요." 그다음 줄은 늘 "메뉴판이 화면에 꽉 차게, 흔들리지 않게 다시 찍어 주세요."
- 서버 `failure.message`는 고정 문구라 이유를 알려 주지 않는다. 어느 사진이 왜 실패했는지 지어내지 않는다.
- 실패한 작업은 이어서 할 수 없다(명세 5.3). 주 버튼 "사진 다시 올리기" → U1(앞서 고른 사진이 기기에 남아 있으면 미리 채운다). 글자 버튼 "내 바로 돌아가기".

### 4.5 처리 뒤 빈 경우

- 읽은 줄이 0개: "메뉴판에서 술을 찾지 못했어요" + `EMPTY` + [사진 다시 올리기]. `full_replace`면 게시하면 내릴 술만 남으므로 게시 버튼을 두지 않는다. (취소 API 전에는 이 작업이 진행 중으로 남는다. 10장)
- 카드가 0장(모두 자동이고 내릴 술도 없음): 요약을 건너뛰고 S8 "게시할까요?"로 가서 위에 "확인할 줄이 없어요. 모두 자동으로 찾았어요"를 보여 준다.

---

## 5. 검수 (P23)

### 5.1 카드 종류

| 종류 | 시안 | 질문 | 탭 수(보통) |
|---|---|---|---|
| `AUTO` | 요약 "자동으로 찾은 술" | (카드 없음. 요약의 접힌 목록) | 0 |
| `CONFIRM` | 05 확인 권장 | 이 술이 맞나요? | 1 |
| `CHOOSE` | 06 고르기 | 어느 술인가요? | 1 |
| `NEW` | 07 새 술 | 새 술로 등록할게요 | 1~3 |
| `PRICE` | 08 가격 | 가격을 못 읽었어요 | 숫자 입력 + 1 |
| `NOT_MENU` | (시안 없음, 4.8) | 메뉴에 올릴 위스키가 아닌 것 같아요 | 1 |
| `NON_PRODUCT_AUTO` | 요약 | (카드 없음. 요약의 접힌 "제목·설명 줄") | 0 |
| `REMOVE` | 09 내리기 | 지금 메뉴에서 내릴까요? | 술마다 1 |

"위스키 아님"은 두 가지로 나온다. (a) AI가 메뉴 줄로 확신하지 못한 줄(`effectiveLineType = unknown`)은 `NOT_MENU` 카드가 된다. (b) 상품 줄이지만 위스키가 아닌 술(알마냑 등)은 미리 알 방법이 없으므로(10장 G4) 모든 상품 카드에 "위스키가 아니에요" 글자 버튼을 둔다.

### 5.2 분류

```kotlin
val BLOCKING = setOf("ageConflict", "editionConflict", "editionOnlyInExtracted", "editionUnmatched")

fun Candidate.blocked() = evidence.keys.any { it in BLOCKING }
fun Item.hasPricedOption() = options.any { it.extractedPriceKrw != null }

fun classify(item: ReviewItemDto): CardKind = when (item.effectiveLineType) {
    "section_header", "description" -> NON_PRODUCT_AUTO
    "unknown" -> NOT_MENU
    else -> {                                   // "product"
        val top = item.candidates.minByOrNull { it.candidateRank }
        when {
            item.initialResolutionStatus == "exact_match" &&
                item.candidates.size == 1 && !top!!.blocked() ->
                if (item.hasPricedOption()) AUTO else PRICE
            top == null -> NEW                   // unmatched
            top.evidence["confirmRecommended"] == true && !top.blocked() -> CONFIRM
            else -> CHOOSE                       // 후보 여럿, 충돌 있는 단일 후보, multiProduct
        }
    }
}
```

- `exact_match`는 별칭 정확 일치와 단계 규칙 S1·S2·S2b·S3(충돌 없이 하나로 확정)을 모두 포함한다(`evidence.rule`로 구분). 둘 다 `AUTO`다. S1~S3로 확정된 줄은 자동 목록에서 "비슷한 표기로 찾음"이라는 작은 표시를 붙인다(`rule != "alias"`).
- LLM 후보(`matchMethod = llm`)가 붙은 줄은 서버가 항상 `ambiguous`로 내므로 `AUTO`가 되지 않는다. `confirmRecommended`가 있으면 `CONFIRM`, 없으면 `CHOOSE`.
- `CONFIRM`·`CHOOSE`·`NEW`에서 상품을 고른 뒤 그 줄에 가격 있는 옵션이 없으면 같은 카드 안에서 가격 입력 단계(5.7)를 이어서 보여 준다. "메뉴에서 빼기"를 고르면 가격은 묻지 않는다.
- 정의하지 않은 `effectiveLineType`이나 형식이 맞지 않는 항목은 `CHOOSE`(후보가 없으면 `NEW`)로 보낸다. 자동 처리하지 않는 쪽이 안전하다.

### 5.3 카드 순서와 개수

- 카드는 사진 순(`imageOrder`), 사진 안에서 줄 순(`itemOrder`)이다. 종류별로 다시 묶지 않는다. 메뉴판을 위에서 아래로 훑는 순서가 업주에게 자연스럽다.
- `REMOVE` 카드는 `mode = full_replace`이고 `changeType = remove`인 변경이 하나 이상 있을 때 맨 마지막에 **한 장**으로 둔다. 진행 표시 대신 "마지막 확인".
- 진행 표시의 분모는 줄 카드 수다(내리기 카드 제외). 요약 제목의 "N줄"도 같은 수다.

### 5.4 "왜" 한 줄 (evidence → 문구)

한 선택지에 최대 한 줄, 아래 우선순위로 처음 맞는 것만 보여 준다. 모르는 키는 무시한다(명세 5.4).

| 우선 | 조건 (그 후보의 `evidence`) | 문구 |
|---|---|---|
| 1 | `ageConflict` | 연수가 달라요. 이 상품은 {ageYears}년이에요 |
| 2 | `editionUnmatched: [t…]` | 메뉴판의 ‘{t}’가 이 상품엔 없어요 |
| 3 | `editionConflict` / `editionOnlyInExtracted` | 메뉴판에 적힌 에디션이 이 상품과 달라요 |
| 4 | `multiProduct` | 한 줄에 술이 둘 적혀 있어요. 한 줄엔 하나만 연결돼요 |
| 5 | `editionOnlyInProduct: [w…]` | 메뉴판엔 ‘{w}’가 안 적혀 있어요 |
| 6 | `fuzzyAlias` | 메뉴판 글자와 한두 글자 달라요 |
| 7 | `vocabulary` | 한글 표기를 영어로 바꿔 찾았어요 |
| 8 | `matchMethod = llm` | 메뉴판 이름을 AI가 풀어서 찾았어요 |
| 9 | `defaultProduct` 또는 `rule = S2b` | 메뉴판엔 에디션이 없어 기본 제품으로 찾았어요 |

1~4는 주의 문구다(3.3). 이 후보를 고르면 결정 전에 한 번 묻는다(명세 8.7, 흐름 문서 15장): "메뉴판과 다른 점이 있어요. 그래도 이 술로 연결할까요?" [연결하기] [취소].

`evidence.englishName`, `via`, `vetoed`, `shortUnverified`는 디버깅용이므로 보여 주지 않는다.

### 5.5 S1 요약 "N줄만 확인해 주세요" ("04 요약")

```
[←]
사진 올리기 · 읽기 · [확인] · 게시
메뉴판 2장에서 16줄을 읽었어요           (bodySmall)
9줄만 확인해 주세요                     (명조 24sp)

[✓] 자동으로 찾은 술 7줄             ›   (접힌 칸. 누르면 펼침)
    그대로 올라가요. 눌러서 바꿀 수 있어요.
확인할 줄
 맞는지 확인               2줄           (CONFIRM)
 어느 술인지 고르기         3줄           (CHOOSE)
 새 술로 등록              2줄           (NEW)
 가격 적기                 1줄           (PRICE)
 위스키가 맞는지            1줄           (NOT_MENU)
 지금 메뉴에서 빠지는 술     2개           (REMOVE, full_replace일 때만)
   새 사진에 없어서 내릴지 물어볼게요

[ 확인 시작 ]
  나중에 하기
```

- 숫자는 5.2 분류 결과를 센다. 0인 행은 숨긴다. 자동 칸의 체크 표시는 `successContainer` 배경 + `onSuccessContainer` 체크(상태를 뜻하는 색이라 쓴다).
- **자동 목록(펼침)**: 줄마다 원문(작게) + 상품 두 줄 표기 + 가격, S1~S3 규칙으로 찾은 줄은 "비슷한 표기로 찾음". 줄을 누르면 그 줄의 바꾸기 화면(= CHOOSE 카드와 같은 화면: 지금 상품 선택됨, 검색, 새로 등록, 위스키가 아니에요)이 열린다. 바꾼 줄은 "바꿈" 표시. 제목·설명 줄(`NON_PRODUCT_AUTO`)은 따로 접힌 "제목·설명 줄 n줄".
- 확인을 이미 시작했다면 주 버튼은 "이어서 확인 (3 / 9)", 모두 끝났다면 "게시 전 확인".
- "나중에 하기": 결정은 기기에 남는다(6.4). H0 내 바로 간다.
- 위 뒤로: 결정이 하나라도 있으면 "나가도 확인한 내용은 이 기기에 남아요" 알림 후 닫는다.

### 5.6 카드별 본문

**CONFIRM "이 술이 맞나요?" ("05")**
- 본문: 1순위 후보 하나를 `surface` 칸에 크게(병 L 40×64dp + 두 줄 표기, 2줄은 20sp SemiBold) + "왜" 한 줄.
- 버튼: [맞아요](주) / [다른 술이에요](보조) / "위스키가 아니에요".
- [다른 술이에요] → 같은 카드가 CHOOSE 모드로 바뀐다: 나머지 후보(있으면) + [목록에 없어요](검색) + "위스키가 아니에요". 질문은 "어느 술인가요?".

**CHOOSE "어느 술인가요?" ("06")**
- 부제 "메뉴판 글자로는 하나로 정하지 못했어요."
- 후보 전부를 `candidateRank` 순서로 `ProductChoiceRow`. 5개를 넘으면 5개 + "더 보기". 누르면 바로 결정(주의 후보는 5.4 확인 먼저).
- 아래: `SEARCH` "목록에 없어요" → S5 검색. "위스키가 아니에요".
- 이미 다른 줄에 연결한 상품을 고르면: "이 술은 ‘{다른 줄 원문}’에도 연결했어요. 메뉴판엔 먼저 나온 줄 하나만 올라가요." [그래도 연결] [다시 고르기]. (서버는 같은 상품이 여러 줄이면 첫 줄만 게시한다. 10장 G8)

**NEW "새 술로 등록할게요" ("07")**
- 부제 "카탈로그에 없는 술이에요. 맞는지 보고 등록해 주세요."
- `surface` 칸 안의 행(행마다 72dp, 구분선):

| 행 | 초기값 (지금 계약 기준 대체 규칙) | 업주 동작 |
|---|---|---|
| 브랜드(독립 병입이면 "병입사") | `newProductDraft.brandText`가 있으면 그것, 없으면 `extractedProductName`의 첫 단어(공백 전, 끝의 숫자 제외)로 `GET /api/catalog/brands?query=`. 결과가 **정확히 하나**이고 `matchedAlias`가 그 단어와 정규화 비교로 같을 때만 미리 고르고 "카탈로그에 있는 브랜드"(`bodySmall`, 회색 글자)를 붙인다. 여럿이면 선택지로 보여 주고 고르게 한다(명세 6.2: 자동 확정 금지). 없으면 "카탈로그에 없는 브랜드" 상태 | "바꾸기" → 브랜드 검색 시트 |
| 증류소 (독립 병입일 때만) | 브랜드가 정해진 뒤 남은 글자의 첫 단어로 다시 브랜드 검색. 다른 브랜드 하나가 나오면 그 이름 + 칩 "독립 병입"(`surfaceVariant`, 중립색) | "지우기" |
| 숙성 연수 | `newProductDraft.ageYears`, 없으면 남은 글자 끝의 1~2자리 숫자(뒤에 `년`·`Y`·`yo`가 오거나 아무것도 없을 때만. `1호`, `1984`는 연수가 아님) | − / + (48dp 원) / "없음" |
| 시리즈 (선택) | `newProductDraft.editionName`, 없으면 브랜드·증류소·연수를 뺀 나머지 글자 | 입력칸(48dp) |

- 그 아래 `surfaceElevated` 칸 "등록될 이름": 병 M + 두 줄 표기(3.3). 그 아래 `bodySmall` "메뉴판 표기 ‘{extractedProductName}’도 검색어로 저장돼요."
- **이름 조합**(카탈로그 관례, `ai/catalog/README.md` "독립 병입"): 독립 병입은 브랜드 = 병입사, `editionName` = 증류소(+ 시리즈), `displayName` = `{병입사} {증류소} {연수}` (예: `Signatory Vintage Caol Ila 13`). 일반 제품은 `displayName` = `{브랜드} {연수} {시리즈}`에서 빈 값을 뺀다.
- **새 브랜드**: 브랜드 행이 "‘크래프트브로스’는 카탈로그에 없어요" 상태가 되고 [새 브랜드로 만들기] [브랜드 찾기]를 보여 준다. [새 브랜드로 만들기]를 눌러야 "영문 이름(선택)" 입력칸이 열리고 행이 정해진다. 정해지기 전에는 [이대로 등록]이 꺼져 있다. 영문 이름이 비면 `canonicalName`은 업주가 확인한 한글 표기다.
- 버튼: [이대로 등록](주) / `SEARCH` [이미 있는 술이에요](보조 → S5) / "위스키가 아니에요".
- 중복은 서버 검사(`DUPLICATE_BRAND_FOUND`, `DUPLICATE_PRODUCT_FOUND`, 명세 9.5)에 맡긴다. 오류가 오면 8장대로 이 카드로 돌아온다.
- 서버가 `newProductDraft`를 채우게 되면(10장 G2) 대체 규칙 대신 서버 값을 쓴다. 화면은 같다.

**PRICE "가격을 못 읽었어요" ("08")**
- `AUTO`인데 가격이 없는 줄은 PRICE 카드, 다른 카드에서는 상품을 고른 뒤 이어지는 단계다.
- 본문: 병 M + "자동으로 찾은 술" + 상품. 옵션마다 입력칸("잔 · 30ml 가격", 숫자 키패드, 56dp, 오른쪽 "원"). 이미 가격이 있는 옵션은 입력칸 없이 보여 준다.
- 하나 이상 입력하면 [저장](주) 켜짐. 1 이상 정수만(명세 8.1). 보조: "메뉴에서 빼기"(`reject`).
- 이미 읽은 가격을 고치려면 가격 줄 옆 "가격 고치기"(글자 버튼)로 같은 입력을 연다. 모든 카드와 자동 목록 바꾸기 화면에 있다.

**NOT_MENU "메뉴에 올릴 위스키가 아닌 것 같아요"** (시안 없음: CONFIRM 틀에 상품 칸 없이)
- 부제 "AI가 이 줄을 술 이름으로 확신하지 못했어요."
- 버튼: [메뉴에서 빼기](주) / [위스키예요](보조 → S5 검색. 매칭을 하지 않은 줄이라 후보가 없다).

**REMOVE "지금 메뉴에서 내릴까요?" ("09")**
- 위: 뒤로 + "마지막 확인". 부제 "새로 올린 사진에 없는 술이에요. 하나씩 골라 주세요."
- 술마다 `surface` 칸: 두 줄 표기(`before.displayName`. `before`에는 브랜드가 없으므로 1줄 없이 `displayName`만, 또는 같은 상품의 카탈로그 정보가 있으면 3.3대로) + "지금 메뉴 · {가격} {용량}" + [내리기] [남기기] 두 칸(48dp, 처음엔 둘 다 꺼짐, 고른 쪽 `primary`, `aria-pressed`).
- 업주가 이 검수에서 같은 상품(`before.productId`)을 어느 줄에 연결했다면 그 술은 "새 메뉴판에도 있어요" 표시로 바뀌고 고를 필요가 없다(`ignore`, 7.3).
- 모두 고르면 [게시 전 확인]이 켜진다. 남았으면 꺼진 버튼 위에 "아직 n개를 고르지 않았어요". "모두 내리기"는 두지 않는다.

### 5.7 S5 술 찾기 ("10 술 찾기")

- 위: 뒤로(카드로) + 검색칸(56dp, `SEARCH`, 초기값 `extractedProductName`, 1~100자, 초점 테두리 `outline`).
- `GET /api/catalog/products?query=&includeInactive=true&limit=20`. 입력 300ms 뒤 요청, 이전 요청은 취소.
- 위에 "카탈로그에서 찾은 술 {n}개". 결과 행: 병 M + 두 줄 표기 + "‘{matchedAlias}’로 찾았어요". `isActive = false`는 흐린 행 + "판매 중단 상품 · 운영자에게 문의해 주세요", 누를 수 없다(명세 7.2).
- 아래 고정: [찾는 술이 없어요, 새로 등록](보조) → 그 줄의 NEW 카드.
- 상태: 로딩(행 자리 회색 막대 3개), 0건("‘…’로 찾은 술이 없어요" + `EMPTY` + 새로 등록), 오류("불러오지 못했어요" + [다시 시도]). 고르면 카드로 돌아가 결정(연수·에디션이 추출값과 다르면 5.4 확인 대화상자).
- 브랜드 검색 시트: `GET /api/catalog/brands?query=`. 행 = `canonicalName` + `matchedAlias`. 같은 별칭이 여러 브랜드에 걸리면 모두 보이고 자동으로 고르지 않는다. 맨 아래 [‘{검색어}’로 새 브랜드 만들기].

### 5.8 S7·S8 게시 전 ("11 게시 전 (남은 카드 있음)", "12 게시 전 (준비됨)")

```
사진 올리기 · 읽기 · 확인 · [게시]        (남은 카드가 있으면 [확인])
16줄을 모두 확인했어요                   (준비됐을 때만)
게시할까요?
 메뉴에 올라가는 술          14개
   새로 등록하는 술 2개 · 새 브랜드 1개 포함
 올리지 않는 줄              2개
 지금 메뉴에서 내리는 술      1개
 줄별로 다시 보기             ›
           게시하면 손님 검색에 바로 나와요.
[ PUBLISH 게시하기 ]
  검수 그만두기
```

- 숫자는 업주 결정에서 센다. "추가/가격 변경" 수는 서버가 최종 계산하므로(명세 8.7) 여기서 보여 주지 않고 완료 화면에서 서버 결과로 보여 준다.
- **결정하지 않은 카드가 있으면(S7)** 단계는 "확인"에 머물고, 목록에 "아직 확인 안 한 줄 n개"(`primary` 글자), 게시하기는 꺼진다. 그 위 `surfaceElevated` 띠 "n개를 확인해야 게시할 수 있어요" + [이어서 확인 ›](다음 미결정 카드). 꺼진 버튼도 TalkBack이 이유를 읽는다.
- "줄별로 다시 보기": 모든 줄(자동 포함)과 결정 요약. 누르면 해당 카드(자동은 바꾸기 화면)로 간다.
- "검수 그만두기": 확인 대화상자 뒤 `POST .../cancel` → 기기 초안 삭제 → H0 내 바. 취소 API가 생기기 전에는 숨긴다(10장).
- 개발용 빌드에서는 "보낼 요청 보기"로 7장 요청 JSON을 펼쳐 볼 수 있게 해도 좋다.
- 10장 G7 대체 동작: `full_replace`이고 1순위가 아닌 상품을 고른 줄이 있으면, `GET /api/bars/{barId}/menu`의 현재 `productId`와 비교해 "‘{1순위 상품}’은 지금 메뉴에 남아 있어요" 안내를 이 화면에 보여 준다.

### 5.9 S8-1 게시 중, S9 완료, 게시 실패 ("13 게시 완료", "13-e 게시 실패")

- 게시 중: 게시하기 버튼에 진행 표시 + "게시하는 중이에요". 다른 버튼과 뒤로를 막는다(뒤로는 "게시가 끝날 때까지 기다려 주세요" 알림). 퍼센트 없음.
- 완료(S9, 명세 8.8 `result`): `StepProgress` 네 칸 모두 지남. `primaryContainer` 원 안에 `PUBLISH`(선택 상태 B) + "메뉴판을 게시했어요"(명조) + "이제 손님이 {업장 이름}의 술을 찾을 수 있어요." 결과 표: 새로 올린 술 `added`, 가격을 바꾼 술 `updated`, 내린 술 `removed`, 카탈로그에 새로 등록 "술 `createdProducts`개 · 브랜드 `createdBrands`개"(0인 행은 숨김). [메뉴판 보기](업장 메뉴) / "닫기"(H0 내 바). 기기의 검수 초안을 지운다.
- 게시 실패: 위에 오류 띠(3.5), 아래는 S8 그대로, 주 버튼이 `RETRY` "다시 시도". 문구는 8장 표.

---

## 6. 공통 동작

### 6.1 되돌리기

- 결정마다 실행 취소 스택에 `(카드 키, 이전 결정)`을 넣는다(최대 50). 알림의 [되돌리기]는 가장 최근 결정을 이전 값으로 돌리고 그 카드로 이동한다.
- 자동 목록에서 바꾼 것, 내리기 선택, 가격 입력도 같은 스택이다.
- 게시에 성공하면 스택을 비운다.

### 6.2 진행 표시

- 업주 흐름 화면: `StepProgress`(3.1). 카드 화면: `k / N`. 요약·게시 전: "남은 확인 n개" / "아직 확인 안 한 줄 n개".
- 읽는 중: 4.3의 문구만.

### 6.3 원본 사진 보기와 URL 만료

- `imageUrl`을 전체 화면으로 열고 확대·이동할 수 있게 한다. `sourceBox`가 있으면 그 상자를 테두리(`primary` 2dp)로 표시하고 처음부터 그 부분으로 확대해 연다. 대체 텍스트 "메뉴판 {n} 원본 사진".
- 이미지가 `403`으로 실패하거나 `imageUrlExpiresAt`이 지났으면 같은 `GET /api/menu-imports/{id}`를 다시 불러 새 URL만 바꾼다. `reviewVersion`이 같으면 결정은 그대로다(명세 5.4).

### 6.4 상태 보존 (회전, 프로세스 종료, 앱 재시작)

- 저장 단위: `ReviewDraft(menuImportId, reviewVersion, itemDecisions: Map<extractedItemId, ItemDraft>, removeDecisions: Map<barMenuItemId, Boolean>, currentCardKey, undoStack)`.
- 회전·설정 변경: `ViewModel`이 들고 있다.
- 프로세스 종료: `SavedStateHandle`에 `menuImportId`, `currentCardKey`를 둔다. 결정 본문은 아래 파일 저장소에서 다시 읽는다.
- 앱 재시작·나중에 하기: `MenuUploadRetryCache`처럼 앱 내부 저장소의 `ReviewDraftStore`(JSON 파일, 작업 ID별)에 결정할 때마다 저장한다. `applied`·`canceled`가 되면 지운다. 서버에는 중간 저장 API가 없다.
- 다시 열 때: 서버 응답의 `reviewVersion`이 초안과 같으면 그대로 복원하고 "확인하던 곳부터 이어서 할게요" 알림. 다르면 6.5.
- 내리기 결정의 키는 `changeId`가 아니라 `barMenuItemId`다. `changeId`는 diff를 다시 만들 때마다 바뀐다(흐름 문서 13장).

### 6.5 새 버전에 결정 다시 적용 (`REVIEW_OUTDATED`, 재조회)

1. 같은 `extractedItemId`가 있고 결정이 여전히 유효하면(고른 `productId`가 새 응답 후보에 있거나 검색으로 고른 것, 새 상품·비위스키·가격 입력) 그대로 둔다.
2. 그 항목이 없어졌으면 버린다.
3. 내리기 결정은 `barMenuItemId`로 다시 연결한다. 새로 생긴 `remove`는 미결정이다.
4. 화면: "메뉴판이 바뀌어서 다시 확인이 필요해요" + 남은 카드가 있으면 첫 미결정 카드로, 없으면 S8로. 업주가 다시 게시해야 한다(명세 9.4). 자동 제출하지 않는다.

### 6.6 접근성

- 카드 화면 진입 시 TalkBack: "9개 중 3번째, 어느 술인가요?, 메뉴판 줄 러셀 싱글베럴, 15,000원 30ml".
- 선택 행은 `Role.RadioButton`, 내리기/남기기는 두 버튼 그룹으로 상태("선택됨")를 읽는다. 색만으로 상태를 나타내지 않는다.
- 글자 크기 1.3배에서 메뉴판 줄·두 줄 표기가 잘리지 않는다(줄바꿈 허용, 글자 칸에 고정 높이 없음).
- 모든 동작이 실제 버튼이고 초점이 보인다. 터치 영역 48dp 이상.

---

## 7. 업주 동작 → `review-and-apply` 요청

`POST /api/menu-imports/{menuImportId}/review-and-apply`, 본문 `{reviewVersion, itemDecisions[], changeDecisions[]}`(명세 8.1). 모든 항목과 모든 `pending` 변경을 한 번씩 담는다. 정의하지 않은 필드는 보내지 않는다(`EXTRA_FORBIDDEN`).

### 7.1 줄 결정

| 업주 동작 | `action` | `finalLineType` | 그 밖의 필드 |
|---|---|---|---|
| 자동으로 찾은 술 그대로 (`AUTO`) | `select_existing_product` | `product` | `productId` = `candidates[0].productId` |
| 확인 권장에서 [맞아요] | `select_existing_product` | `product` | `productId` = 1순위 |
| 고르기에서 후보 선택 | `select_existing_product` | `product` | `productId` = 고른 후보(1순위가 아니면 서버가 `manual`로 기록) |
| 검색해서 선택 | `select_existing_product` | `product` | `productId` = 검색 결과(활성만) |
| 새 술, 카탈로그 브랜드 | `create_product` | `product` | `brand: {type: "existing", brandId}`, `product: {category: "whisky", displayName, ageYears, editionName, abv: null}`, `aliases: [{aliasText: extractedProductName, languageCode: "ko", isSearchable: true}]` |
| 새 술, 새 브랜드 ([새 브랜드로 만들기]를 누른 경우만) | `create_product` | `product` | `brand: {type: "new", canonicalName: 영문 이름 ?: 업주가 확인한 한글 표기, aliases: [{aliasText: 한글 표기, languageCode: "ko"}](영문 이름이 있을 때만)}`, `product`·`aliases`는 위와 같음 |
| 위스키가 아니에요 (상품 줄) | `reject` | `product` | 없음 |
| 메뉴에서 빼기 (`NOT_MENU`) | `confirm_non_product` | `unknown` | 없음 |
| 메뉴에서 빼기 (가격 카드) | `reject` | `product` | 없음 |
| 위스키예요 (`NOT_MENU`) → 검색·새 술 | 위의 `select_existing_product` / `create_product` | `product` | 위와 같음 |
| 제목·설명 줄 (`NON_PRODUCT_AUTO`) | `confirm_non_product` | `effectiveLineType` | 없음 |
| 가격 입력·고치기 (상품 결정과 함께) | 위 상품 결정 | `product` | `optionDecisions: [{extractedOptionId, correctedPriceKrw}]` 바뀐 옵션만 |

- `correctedProductName`, `aliasesToAdd`는 보내지 않는다(11장 D3).
- 이름 조합에서 빈 값은 빼고 앞뒤 공백을 지운다. `displayName` 1~200자, `editionName` 1~150자, `canonicalName` 1~120자(명세 8.1). 넘으면 카드에서 막는다.

### 7.2 예시

```json
{
  "reviewVersion": 3,
  "itemDecisions": [
    {"extractedItemId": "…i1", "finalLineType": "product", "action": "select_existing_product", "productId": "…bowmore-12"},
    {"extractedItemId": "…i5", "finalLineType": "product", "action": "select_existing_product", "productId": "…hakushu-distillers-reserve"},
    {"extractedItemId": "…i12", "finalLineType": "product", "action": "reject"},
    {"extractedItemId": "…i13", "finalLineType": "product", "action": "create_product",
     "brand": {"type": "existing", "brandId": "…signatory-vintage"},
     "product": {"category": "whisky", "displayName": "Signatory Vintage Caol Ila 13", "ageYears": 13, "editionName": "Caol Ila", "abv": null},
     "aliases": [{"aliasText": "시그나토리 쿨일라13", "languageCode": "ko", "isSearchable": true}]},
    {"extractedItemId": "…i14", "finalLineType": "product", "action": "create_product",
     "brand": {"type": "new", "canonicalName": "Craft Bros", "aliases": [{"aliasText": "크래프트브로스", "languageCode": "ko"}]},
     "product": {"category": "whisky", "displayName": "Craft Bros 독수리 오형제 1호", "ageYears": null, "editionName": "독수리 오형제 1호", "abv": null},
     "aliases": [{"aliasText": "크래프트브로스 독수리 오형제 1호", "languageCode": "ko", "isSearchable": true}]},
    {"extractedItemId": "…i15", "finalLineType": "unknown", "action": "confirm_non_product"},
    {"extractedItemId": "…i16", "finalLineType": "product", "action": "select_existing_product", "productId": "…bookers",
     "optionDecisions": [{"extractedOptionId": "…o16a", "correctedPriceKrw": 28000}]}
  ],
  "changeDecisions": [
    {"changeId": "…c-add-i12", "decision": "ignore"},
    {"changeId": "…c-remove-glenlivet-18", "decision": "apply"},
    {"changeId": "…c-remove-balvenie-14", "decision": "ignore"}
  ]
}
```

### 7.3 `changeDecisions` 규칙

| 변경 | 결정 |
|---|---|
| `add`/`update`, 그 줄이 상품 결정 | `apply` |
| `add`/`update`, 그 줄이 `reject` 또는 `confirm_non_product` | `ignore` (안 하면 `422 CHANGE_WITHOUT_PRODUCT`) |
| `remove`, 업주가 [내리기] | `apply` |
| `remove`, 업주가 [남기기] | `ignore` |
| `remove`, 그 상품을 이 검수의 어떤 줄에 연결함 | `ignore` ("새 메뉴판에도 있어요") |

다른 후보를 골라 임시 diff와 달라진 변경은 서버가 업주 결정으로 다시 계산한다(명세 8.7).

---

## 8. 오류 처리 (게시와 검색)

| 상황 | 화면 | 동작 |
|---|---|---|
| 오프라인·시간 초과 | 오류 띠 "게시하지 못했어요" / "인터넷 연결을 확인해 주세요. 확인한 내용은 그대로 있어요." + [다시 시도] | 같은 요청을 다시 보낸다. 이미 반영됐으면 서버가 같은 결과를 돌려준다(명세 8.8) |
| `502`/`504`/`500`/해석 불가 응답 | "잠시 후 다시 시도해 주세요" + [다시 시도] | 같은 요청 |
| `503 TEMPORARY_WRITE_CONFLICT` | 같은 문구 | 1초 뒤 한 번 자동 재시도, 또 실패하면 [다시 시도] |
| `409 REVIEW_OUTDATED` | "메뉴판이 바뀌어서 다시 확인이 필요해요" | `details.reviewUrl` 재조회 → 6.5 |
| `409 DUPLICATE_PRODUCT_FOUND` | 해당 NEW 카드로 이동, "이미 등록된 술이 있어요" + `existingProduct` 두 줄 표기 + [이 술이에요] [다른 술이에요] | [이 술이에요] → `select_existing_product`. `isActive = false`면 꺼진 버튼 + "판매 중단 상품이라 연결할 수 없어요. 운영자에게 문의해 주세요". [다른 술이에요] → 이름을 고치게 한다 |
| `409 DUPLICATE_BRAND_FOUND` | 해당 NEW 카드, "같은 브랜드가 이미 있어요" + `existingBrand.canonicalName` + [이 브랜드로] | 브랜드를 `existing`으로 바꾼다 |
| `422 VALIDATION_FAILED` | `fieldErrors[].path`의 `itemDecisions[i]`를 카드로 바꿔 그 카드로 이동 | `NO_PRICED_OPTION` → 가격 단계, `PRODUCT_INACTIVE` → "판매 중단 상품" + 다시 고르기, `MISSING_*`/`UNKNOWN_*`/`DUPLICATE_*` → 앱 오류이므로 재조회 후 6.5 |
| `409 INVALID_IMPORT_STATE` | `details.status`에 따라: `applied` → S9, `canceled` → "취소된 작업이에요", 그 밖 → 재조회 | |
| `401` | 세션 갱신 후 한 번 재시도, 실패하면 로그인 | 초안은 남는다 |
| `403 FORBIDDEN` | "이 업장의 메뉴를 관리할 권한이 없어요" | |
| `404 MENU_IMPORT_NOT_FOUND` | "작업을 찾을 수 없어요" + [내 바로] | 초안 삭제 |
| 검색 API 실패 | 검색 화면 안의 오류 + [다시 시도] | 카드 결정에는 영향 없음 |

오류 문구에 서버 원문이나 HTTP 번호를 쓰지 않는다(명세 9.6). `error.code`로만 분기한다.

---

## 9. 수용 기준 (P23·P27 테스트용)

ViewModel 단위 테스트는 시안 시나리오(오드비 메뉴판 2장, 16줄)와 같은 구성의 가짜 응답(JSON 고정값)으로 만들고, 화면은 개발 서버(mock 추출기)로 확인한다.

**업로드·읽기 (P27)**
1. 사진 0장이면 올리기 버튼이 꺼져 있다. 6장째는 고를 수 없다.
2. 올리기 방식을 고르지 않은 상태가 없다(기본값 전체 교체), 고른 값이 `mode`로 간다.
3. 올리는 중 네트워크를 끊으면 오류 띠 + 다시 시도, 다시 시도는 같은 `Idempotency-Key`로 보낸다.
4. `409 ACTIVE_IMPORT_EXISTS`면 [이어서 하기]로 그 작업이 열린다.
5. 읽는 중 문구가 `completedImages`대로 바뀌고, 모두 읽었는데 `processing`이면 "후보를 정리하는 중이에요"다. 퍼센트가 없다.
6. `failed`면 U3, 문구는 `failedImages` 수만 말하고 이유를 지어내지 않는다.
7. 읽는 중 화면을 나갔다 들어와도 같은 작업이 이어진다.

**분류 (P23)**
8. `exact_match` + 후보 1 + 충돌 없음 + 가격 있음 → 카드가 없고 요약 "자동으로 찾은 술"에 센다.
9. `exact_match`인데 가격 있는 옵션이 없음 → PRICE 카드.
10. `ambiguous` + 1순위 `confirmRecommended = true` + 충돌 없음 → CONFIRM 카드.
11. `ambiguous` + 후보 2개 이상 → CHOOSE, 후보가 `candidateRank` 순서로 모두 보인다.
12. `ambiguous` + 후보 1개 + `editionUnmatched` → CHOOSE, 그 후보를 누르면 확인 대화상자.
13. `unmatched`(후보 0) → NEW.
14. `effectiveLineType = unknown` → NOT_MENU. `section_header`/`description` → 카드 없음, `confirm_non_product`로 제출.
15. `matchMethod = llm` 후보는 어떤 경우에도 AUTO가 되지 않는다.
16. `evidence`에 모르는 키가 있어도 화면이 깨지지 않는다.

**메뉴판 줄**
17. `sourceBox`가 있으면 그 줄만 잘린 사진이 보이고, `null`이거나 사진을 못 불러오면 종이 띠가 보인다.
18. 원본 사진 보기가 그 줄 상자를 표시한 채로 열린다.

**요약과 진행**
19. 요약의 숫자 합 = 전체 줄 수, "N줄" = 줄 카드 수. 0인 행은 숨는다.
20. 카드 화면의 진행 표시는 `k / N`뿐이다.
21. 카드가 0장이면 요약 없이 게시 전 화면으로 간다.

**결정과 게시**
22. 미결정 카드가 하나라도 있으면 게시하기가 꺼져 있고 "n개를 확인해야 게시할 수 있어요"가 보인다. "모두 승인" 버튼은 어디에도 없다.
23. 제출 요청에 모든 항목과 모든 `pending` 변경이 한 번씩 있다.
24. `brand.type = new`는 업주가 [새 브랜드로 만들기]를 누른 줄에만 있고, `canonicalName`이 메뉴 줄 원문 전체와 같지 않다(`buildReviewRequest`에 원문을 브랜드로 쓰는 경로가 없음).
25. "위스키가 아니에요"를 고른 줄은 `reject`이고 그 줄의 `add` 변경은 `ignore`다.
26. `remove`는 업주가 고른 대로 `apply`/`ignore`이며, 고르지 않으면 게시할 수 없다. 이 검수에서 연결한 상품의 `remove`는 묻지 않고 `ignore`다.
27. 같은 상품을 두 줄에 연결하려 하면 경고가 뜬다.
28. 1순위가 아닌 후보를 고르면 `productId`가 그 후보다.

**되돌리기·이동·보존**
29. 결정 뒤 [되돌리기]가 결정을 이전 값으로 돌리고 그 카드로 간다.
30. 이전/다음, 시스템 뒤로가 카드 사이를 오가며 결정을 잃지 않는다.
31. 결정 3개 뒤 화면 회전 → 같은 카드, 같은 결정. "활동 유지 안 함"으로 프로세스 종료 뒤 복귀 → 같은 카드, 같은 결정.
32. 앱을 닫았다 다시 열어 같은 작업을 열면 "확인하던 곳부터 이어서 할게요"와 함께 복원된다.

**상태와 오류**
33. 게시 중 네트워크를 끊으면 오류 띠 + [다시 시도], 결정은 그대로, 다시 시도로 게시된다.
34. `REVIEW_OUTDATED` → 재조회 후 남은 결정이 복원되고 바뀐 부분만 다시 묻는다.
35. `DUPLICATE_PRODUCT_FOUND` → 해당 NEW 카드로 이동해 [이 술이에요]로 해결된다.
36. 검색 결과의 판매 중단 상품은 고를 수 없다.
37. `imageUrl` 만료 뒤 원본 사진 보기 → 재조회로 다시 보인다.

**디자인·접근성**
38. 화면 제목만 명조, 나머지 Pretendard, 색·크기는 `Tokens.kt` 이름으로만, 아이콘은 `BmIcon`만, 장식 배지 색 없음(성공·오류 색은 상태에만).
39. 모든 버튼 ≥48dp, 주 버튼 56dp, 글자 1.3배에서 잘림 없음, TalkBack이 카드 번호·질문·메뉴판 줄·가격을 읽는다.

---

## 10. 서버에 아직 없는 것과 대체 동작

| # | 무엇 | 상태 | 없을 때 |
|---|---|---|---|
| B1 | 업주가 메뉴 등록·검수·카탈로그 검색 API를 부르는 권한 | I3-P22 (양해울) | 운영자 계정으로 확인 |
| B2 | `GET /api/me/bars` | I3-P7 (양해울) | 개발용 빌드는 지금처럼 운영자 업장 목록 |
| B3 | `POST /api/menu-imports/{id}/cancel` (명세 5.7) | 명세에만 있음. 박진우가 양해울과 이야기 중 | "검수 그만두기", "새 사진 올리기"를 숨긴다. 진행 중 작업이 있으면 업주는 그 작업을 이어서 하는 수밖에 없다 |
| G1 | 줄 좌표 `sourceBox` | I3-P25 백엔드 PR | 종이 띠(3.2) |
| G2 | `newProductDraft`가 비어 있음 | I3-P30 뒤 매칭 쪽에서 채운다(박진우): 규칙 매칭이 찾은 브랜드·연수, LLM 번역의 병입사·증류소·브랜드·연수·에디션 | 5.6 NEW의 대체 규칙 |
| G4 | 비위스키 판정 | G2와 함께: LLM 번역의 `kind` | 모든 상품 카드에 "위스키가 아니에요" |
| G5 | 비위스키 상품 줄을 기록할 동작 | `reject` + `finalLineType = product`로 보낸다 | — |
| G6 | 한 줄에 두 상품(`multiProduct`) | 한 항목에 상품 하나만 연결된다 | 하나만 고르게 하고 카드에 안내 |
| G7 | 1순위가 아닌 상품을 고르면 기존 메뉴의 1순위 상품이 남음 | `full_replace` 임시 diff에 그 상품의 `remove`가 없다 | S8에 "지금 메뉴에 남아 있어요" 안내 |
| G8 | 같은 상품을 두 줄에 연결하면 첫 줄만 게시 | 서버는 조용히 버린다 | 카드에서 미리 경고 |
| G9 | 중복 오류의 `details` | 코드에는 `extractedItemId`, `existingBrand{brandId, canonicalName}`, `existingProduct.isActive`, `reviewUrl`이 있으나 명세 9.5에 없다 | 코드 기준으로 읽고, 없으면 재조회 |

Android DTO에는 계약에 있는 `proposedChanges[].before`가 빠져 있다. 공백이 아니라 P23에서 추가한다(12장).

---

## 11. 정한 것과 제안

| # | 결정 | 내용 |
|---|---|---|
| D1 | 비위스키 술(알마냑, 코냑, 리큐어)을 메뉴에 올릴지 | 이번엔 올리지 않음(`reject`). 카탈로그 `excluded_non_whisky`와 같은 방침 |
| D2 | S1~S3 규칙으로 확정된 `exact_match`도 자동 포함할지 | 포함. 자동 목록에서 "비슷한 표기로 찾음"으로 구분해 바꿀 수 있게 함 |
| D3 | 업주가 확인한 메뉴 표기를 별칭(`aliasesToAdd`)으로 추가할지 | P23에서는 보내지 않음. 이후 `isSearchable = false`로 매칭에만 쓰는 안을 검토 |
| D4 | 새 브랜드 영문 이름을 모를 때 한글 `canonicalName`을 허용할지 | 허용(업주가 확인한 표기만). 운영자가 나중에 고침 |
| D5 | "모두 내리기"를 둘지 | 두지 않음 |
| D6 | 가격 없는 줄을 게시 전에 꼭 정하게 할지 | 그렇게 함(서버가 `NO_PRICED_OPTION`으로 막기도 함). "메뉴에서 빼기"로 넘길 수 있음 |
| D7 | `DESIGN.md` 5.2와 "한 번에 질문 하나"의 관계 | 질문은 카드 하나에 하나, 요약·자동 목록·게시 확인은 촘촘한 목록. 남호진과 이 해석에 합의할 것 |
| D8 | 중간 결정을 기기에만 저장 | 서버 중간 저장 API 없이 기기 저장 |
| D9 | 서버 LLM 층(`MATCHING_LLM_ENABLED`)을 켜는 시점 | P23 병합과 9장 수용 기준 통과 뒤, I3-P32 결정에 따름 |
| D10 | 병 일러스트 | 브랜드별 규칙이 정해질 때까지 모든 상품이 같은 중립 병(3.3) |

---

## 12. Android 코드 변경

### 12.1 지울 것

- `ExtractionReviewViewModel.applyDefaultReview()`, `MenuImportStatusDto.buildDefaultReviewRequest()`, `ReviewItemDto.defaultDecision()`. 1순위 일괄 선택과 `draft.brandText ?: displayName`으로 새 브랜드를 만드는 경로가 없어진다.
- `ReviewDecisionMapperTest.defaultReview_coversEveryItemAndChangeUsingBackendPolicy`는 새 규칙의 테스트로 바꾼다(PR 설명에 이유를 적는다).
- `ReviewItemUiModel.decisionText`("Use existing product: …" 같은 영어 문구)와 화면의 영어 문구를 모두 한국어로 바꾼다.

### 12.2 새로 둘 것 (ViewModel·순수 함수)

```kotlin
// 순수 함수: 단위 테스트 대상
fun buildReviewCards(dto: MenuImportStatusDto): ReviewPlan            // 5.2 분류, 5.3 순서, 요약 숫자
fun buildReviewRequest(dto: MenuImportStatusDto, draft: ReviewDraft): ReviewAndApplyRequestDto
    // 미결정 카드가 있으면 예외(게시 버튼이 꺼져 있으므로 정상 경로에선 오지 않음)
    // AUTO는 1순위, NON_PRODUCT_AUTO는 confirm_non_product로 채움 (7장)
fun reconcile(old: ReviewDraft, fresh: MenuImportStatusDto): ReviewDraft   // 6.5
fun cropRect(sourceBox: List<Int>, imageWidth: Int, imageHeight: Int): Rect // 3.2, 여유 포함·사진 안으로 자르기

sealed interface LocalDecision {
    data class SelectProduct(val productId: String, val source: Source /* AUTO, TOP, CANDIDATE, SEARCH */) : LocalDecision
    data class CreateProduct(val brand: BrandChoice /* Existing(brandId) | New(canonicalName, koAlias?) */,
                             val displayName: String, val ageYears: Int?, val editionName: String?,
                             val menuSpelling: String) : LocalDecision
    data object NotWhisky : LocalDecision        // reject, finalLineType = effectiveLineType
    data object NotMenuLine : LocalDecision      // confirm_non_product
}
data class ItemDraft(val decision: LocalDecision?, val priceFixes: Map<String, Int> = emptyMap())
```

ViewModel 상태(`StateFlow<ExtractionReviewUiState>`):

```kotlin
sealed interface ExtractionReviewUiState {
    data object Loading
    data class LoadError(val kind: ErrorKind)                       // 다시 시도
    data class Processing(val total: Int, val completed: Int)       // U2
    data class Failed(val total: Int, val failed: Int)              // U3
    data class Canceled(val menuImportId: String)
    data class Reviewing(
        val plan: ReviewPlan, val draft: ReviewDraft,
        val screen: Screen,            // Summary, Card(index), Search(itemId, query), BrandSearch(itemId), Publish
        val pending: Pending?,         // 충돌 확인 대화상자, 같은 상품 경고
        val snackbar: Snackbar?,       // "저장했어요 · 되돌리기"
        val submitError: SubmitError?, // 8장
        val submitting: Boolean,
    )
    data class Applied(val result: AppliedUiModel)
}
```

동작: `decide(cardKey, decision)`, `undo()`, `goTo(index)`, `next()`, `previous()`, `setRemove(barMenuItemId, remove: Boolean)`, `setPrice(itemId, optionId, krw)`, `search(query)`, `searchBrands(query)`, `submit()`, `retrySubmit()`, `cancelImport()`(B3 뒤), `reload()`.

### 12.3 네트워크·데이터 계층

- `OwnerApi`에 추가: `GET api/catalog/brands`, `GET api/catalog/products`, (B2 뒤) `GET api/me/bars`, (B3 뒤) `POST api/menu-imports/{id}/cancel`. G7 대체 동작용 `GET api/bars/{barId}/menu`는 고객 쪽 API를 재사용.
- `OwnerApiModels.kt`: `ReviewItemDto.sourceBox: List<Int>?`, `ProposedChangeDto.before`(`ChangeBeforeDto(productId, displayName, options[menuEntryOptionId, optionLabel, pourMl, priceKrw])`), `ChangeAfterDto.options`, `BrandSearchResponseDto`, `ProductSearchResponseDto`(`isActive`, `matchedAlias`). `ReviewAndApplyRequestDto.itemDecisions`는 `sealed class` + Moshi 어댑터로 바꾸면 `EXTRA_FORBIDDEN`을 컴파일 단계에서 막을 수 있다(권장).
- `OwnerRepository`: 위 API 메서드. `ReviewDraftStore`(`MenuUploadRetryCache`와 같은 방식의 내부 저장 파일).
- `BottleMapApiException.details`에서 `extractedItemId`, `existingProduct`, `existingBrand`, `reviewUrl`, `status`, `menuImportId`를 읽는 작은 파서.

### 12.4 단위 테스트 (최소)

- `buildReviewCards`: 9장 8~16번.
- `buildReviewRequest`: 모든 항목·변경 포함(23), 새 브랜드 경로(24), 비위스키(25), 내리기(26), 가격 수정 `optionDecisions`, 미결정이면 예외.
- `reconcile`: 같은 버전 복원, 항목 삭제, `remove` 재연결(6.5).
- `cropRect`: 여유 포함, 사진 끝에서 자르기, 0–1000 좌표의 비율 변환.

---

## 13. 시안의 목업 데이터

시안의 메뉴 줄과 가격은 DEV 업장 오드비(009)의 라벨(`eval/labels_final_v1.json`)에서, 상품·브랜드 이름은 카탈로그에서 가져왔다. 매칭 결과(카드 종류, 후보, "왜" 문구), 게시된 메뉴 수, 최근 작업, 완료 화면 숫자, 판매 중단 상품은 화면을 보여 주려고 만든 가정이며 실제 실행 결과가 아니다. I3 평가 업장(014–021)과 실제 메뉴 사진은 쓰지 않았다.
