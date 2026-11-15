# Mixed-menu extraction report

15 photos, 542 expected rows (whisky 461, cocktail 33, food 5, other 43). Counts in brackets are summed over the records of the run directory.

## ai/runs/2026-11-13_p12/hybrid_v1

| | all runs | r1 | r2 | r3 |
|---|---|---|---|---|
| Records (rejected) | 45 (0) | 15 (0) | 15 (0) | 15 (0) |
| Line recall | 88.3% (1436/1626) | 88.4% (479/542) | 87.8% (476/542) | 88.8% (481/542) |
| Whisky line recall | 99.4% (1375/1383) | 99.8% (460/461) | 98.7% (455/461) | 99.8% (460/461) |
| Non-whisky line recall | 25.1% (61/243) | 23.5% (19/81) | 25.9% (21/81) | 25.9% (21/81) |
| Extra-line rate | 0.5% (8/1444) | 0.2% (1/480) | 1.2% (6/482) | 0.2% (1/482) |
| Price accuracy | 99.8% (1433/1436) | 99.8% (478/479) | 100.0% (476/476) | 99.6% (479/481) |
| Duplicate-line rate | 0.0% (0/1444) | 0.0% (0/480) | 0.0% (0/482) | 0.0% (0/482) |
| Classification error rate | 4.2% (61/1436) | 4.0% (19/479) | 4.4% (21/476) | 4.4% (21/481) |
| Whisky line read as non-whisky | 0 | 0 | 0 | 0 |
| Non-whisky line read as whisky | 61 | 19 | 21 | 21 |
| Wrong non-whisky kind | 0 | 0 | 0 | 0 |

Category of paired lines, expected -> output: other->whisky 61, whisky->whisky 1375

Misclassified lines (and in how many records of the photo):

- 007_위스키복춘_03: 헤네시 VSOP (expected other, got whisky; 2)
- 007_위스키복춘_03: 다니엘 부쥬 로얄 (expected other, got whisky; 2)
- 008_서로상_01: 헤네시vsop / Hennessy vsop (expected other, got whisky; 3)
- 008_서로상_01: 레미마틴vsop / Remy Martin vsop (expected other, got whisky; 3)
- 009_오드비_04: 잭다니엘 애플 (expected other, got whisky; 3)
- 010_수이_04: 13 lines (expected other, got whisky; 3)
- 010_수이_05: 헤네시 VSOP (expected other, got whisky; 3)

Expected lines the output does not have (and in how many records of the photo):

- 007_위스키복춘_01: 카발란 솔리스트 셰리 오크 (whisky; 1)
- 007_위스키복춘_01: 카발란 솔리스트 비노 바리끄 (whisky; 1)
- 007_위스키복춘_01: 카발란 트리플 셰리 (whisky; 1)
- 007_위스키복춘_01: 발베니 12Y (whisky; 1)
- 007_위스키복춘_01: 발베니 14Y (whisky; 1)
- 007_위스키복춘_01: 츠누키 에디션 2025 (whisky; 1)
- 007_위스키복춘_03: 헤네시 VSOP (other; 1)
- 007_위스키복춘_03: 다니엘 부쥬 로얄 (other; 1)
- 007_위스키복춘_04: 33 lines (cocktail; 3)
- 011_미라보_07: 우드포드 리저브(Woodford Reserve) 더블 X.O (whisky; 1)
- 009_오드비_02: 15 lines (other; 3)
- 009_오드비_09: 7 lines (other; 3)
- 010_수이_02: Balvenie 16y French Oak (프렌치 오크) (whisky; 1)
- 010_수이_05: 하몽을 곁들인 감자튀김. (food; 3)
- 010_수이_05: 과일·치즈 플레이트 (food; 3)
- 010_수이_05: 교자 (food; 3)
- 010_수이_05: 훈제굴 플레이트 (food; 3)
- 010_수이_05: 안키모와 바게트 (food; 3)

## ai/runs/2026-11-13_p12/hybrid_v2

| | all runs | r1 | r2 | r3 |
|---|---|---|---|---|
| Records (rejected) | 45 (0) | 15 (0) | 15 (0) | 15 (0) |
| Line recall | 99.3% (1615/1626) | 99.3% (538/542) | 99.3% (538/542) | 99.5% (539/542) |
| Whisky line recall | 99.9% (1381/1383) | 99.8% (460/461) | 99.8% (460/461) | 100.0% (461/461) |
| Non-whisky line recall | 96.3% (234/243) | 96.3% (78/81) | 96.3% (78/81) | 96.3% (78/81) |
| Extra-line rate | 0.1% (2/1617) | 0.2% (1/539) | 0.2% (1/539) | 0.0% (0/539) |
| Price accuracy | 99.6% (1608/1615) | 100.0% (538/538) | 98.7% (531/538) | 100.0% (539/539) |
| Duplicate-line rate | 0.0% (0/1617) | 0.0% (0/539) | 0.0% (0/539) | 0.0% (0/539) |
| Classification error rate | 1.2% (20/1615) | 1.1% (6/538) | 1.3% (7/538) | 1.3% (7/539) |
| Whisky line read as non-whisky | 0 | 0 | 0 | 0 |
| Non-whisky line read as whisky | 20 | 6 | 7 | 7 |
| Wrong non-whisky kind | 0 | 0 | 0 | 0 |

Category of paired lines, expected -> output: cocktail->cocktail 99, food->food 15, other->other 100, other->whisky 20, whisky->whisky 1381

Misclassified lines (and in how many records of the photo):

- 008_서로상_01: 헤네시vsop / Hennessy vsop (expected other, got whisky; 3)
- 008_서로상_01: 레미마틴vsop / Remy Martin vsop (expected other, got whisky; 3)
- 009_오드비_04: 잭다니엘 애플 (expected other, got whisky; 3)
- 010_수이_04: 김과장 #2 (바베이도스 럼) (expected other, got whisky; 3)
- 010_수이_05: 헤네시 VSOP (expected other, got whisky; 2)

Expected lines the output does not have (and in how many records of the photo):

- 011_미라보_07: 우드포드 리저브(Woodford Reserve) 더블 X.O (whisky; 1)
- 009_오드비_09: 올드풀티니 3종 세트 / 행사 (other; 3)
- 009_오드비_09: 사부로마루 피트 위스키 5종 세트 / 행사 (other; 3)
- 009_오드비_09: 아르마냑 가호 5종 세트 / 행사 (other; 3)
- 010_수이_02: Balvenie 16y French Oak (프렌치 오크) (whisky; 1)

