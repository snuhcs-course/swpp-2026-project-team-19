# 1a 카탈로그 연수: dev_service

## rules (836줄, 바뀐 줄 2)

| | Top-1 | FM | 틀린 확인 권장 | hard/photo | confirm/choose/register/wrong | 확정 |
|---|---|---|---|---|---|---|
| before | 625/804 | 0 | 3 | 4.207 | 89/44/70/8 | 625 |
| after | 626/804 | 0 | 3 | 4.138 | 90/44/69/7 | 626 |

맞는 확정이 사라진 줄 0, 새로 맞게 확정된 줄 1

| 사진 | 줄 | 정답 | 전 | 후 |
|---|---|---|---|---|
| 011_미라보_04 | 글렌모렌지(Glenmorangie) 12년 오리지널 | glenmorangie-original | ambiguous / ambiguous_bad / wrong: Glenmorangie 12 Calvados Cask Finish | exact_match / correct / confirmed: Glenmorangie The Original |
| 011_미라보_04 | 글렌모렌지(Glenmorangie) 16년 더 넥타 | glenmorangie-nectar-dor | unmatched / unmatched / register:  | ambiguous / ambiguous_ok / confirm CR: Glenmorangie Nectar D'Or |

## server (836줄, 바뀐 줄 2)

| | Top-1 | FM | 틀린 확인 권장 | hard/photo | confirm/choose/register/wrong | 확정 |
|---|---|---|---|---|---|---|
| before | 625/804 | 0 | 3 | 3.862 | 99/84/18/10 | 625 |
| after | 626/804 | 0 | 3 | 3.793 | 100/83/18/9 | 626 |

맞는 확정이 사라진 줄 0, 새로 맞게 확정된 줄 1

| 사진 | 줄 | 정답 | 전 | 후 |
|---|---|---|---|---|
| 011_미라보_04 | 글렌모렌지(Glenmorangie) 12년 오리지널 | glenmorangie-original | ambiguous / ambiguous_bad / wrong: Glenmorangie 12 Calvados Cask Finish | exact_match / correct / confirmed: Glenmorangie The Original |
| 011_미라보_04 | 글렌모렌지(Glenmorangie) 16년 더 넥타 | glenmorangie-nectar-dor | ambiguous / ambiguous_ok / choose: Glenmorangie The Original \|\| Glenmorangie 18 \|\| Glenmorangie Nectar D'Or \|\| Glen | ambiguous / ambiguous_ok / confirm CR: Glenmorangie Nectar D'Or |

