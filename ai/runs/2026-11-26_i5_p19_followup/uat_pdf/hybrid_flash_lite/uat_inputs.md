# UAT inputs through the extraction pipeline (I4-P30)

2 inputs, 2 without a failure. Latency: the model call, the OCR call, and the whole input as the script measured it.

| Input | Kind | Items | Expected lines found | Model | OCR | Whole | Attempts | Failure reason |
|---|---|---|---|---|---|---|---|---|
| pdf-text-design | pdf | 6 | 10/10 | 3.6 s | - | 3.7 s | 1 | - |
| pdf-text-office | pdf | 7 | 7/7 | 42.0 s | - | 42.0 s | 2 | - |

## pdf-text-design

PDF import: text PDF exported from a design tool, one page, glass and bottle columns. File: `backend/tests/fixtures/pdf/text_menu_design.pdf`.
- Page 1 (text, text layer used): 6 items, model 3.6 s, OCR -, attempts 1

| Name | Prices |
|---|---|
| 글렌피딕 12년 | 15,000 (30ml), 190,000 (병) |
| 발베니 12년 더블우드 | 22,000 (30ml), 280,000 (병) |
| 탈리스커 10년 | 16,000 (30ml) |
| 라가불린 16년 | 26,000 (30ml), 340,000 (병) |
| 메이커스 마크 | 11,000 (잔), 130,000 (병) |
| 와일드터키 101 | 12,000 (잔) |

## pdf-text-office

PDF import: text PDF exported from an office document, two pages. File: `backend/tests/fixtures/pdf/text_menu_office.pdf`.
- Page 1 (text, text layer used): 5 items, model 4.8 s, OCR -, attempts 1
- Page 2 (text, text layer used): 2 items, model 37.2 s, OCR -, attempts 1

| Name | Prices |
|---|---|
| 아드벡 10 년 | 17,000 (잔) |
| 라프로익 10 년 | 16,000 (잔) |
| 맥캘란 12 년 셰리 오크 | 25,000 (잔) |
| 글렌드로낙 12 년 | 18,000 (잔) |
| 조니워커 블랙 라벨 | 11,000 (잔) |
| 버팔로 트레이스 | 12,000 (잔) |
| 우드포드 리저브 | 15,000 (잔) |
