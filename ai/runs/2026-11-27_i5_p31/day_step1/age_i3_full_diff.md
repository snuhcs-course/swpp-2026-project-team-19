# before_age_i3_full.json -> after_age_i3_full.json

## rules (675줄, 바뀐 줄 4)

| | Top-1 | FM | 틀린 확인 권장 | hard/photo | confirm/choose/register/wrong | 확정 |
|---|---|---|---|---|---|---|
| before | 498/646 | 1 | 2 | 2.848 | 74/34/58/2 | 507 |
| after | 500/646 | 1 | 2 | 2.818 | 73/34/57/2 | 509 |

맞는 확정이 사라진 줄 0, 새로 맞게 확정된 줄 2

| 사진 | 줄 | 정답 | 전 | 후 |
|---|---|---|---|---|
| 016_연림 봉천역점_03 | 글렌모렌지 12 | glenmorangie-original | ambiguous / ambiguous_ok / choose: Glenmorangie 12 Calvados Cask Finish || Glenmorangie Lasanta || Glenmorangie The | ambiguous / ambiguous_ok / choose: Glenmorangie 12 Calvados Cask Finish || Glenmorangie Lasanta || Glenmorangie Qui |
| 017_리틀 갤러리_03 | 글렌모렌지 15년 / Glenmorangie 15yr | glenmorangie-lasanta | unmatched / unmatched / register:  | ambiguous / ambiguous_ok / confirm: Glenmorangie Lasanta |
| 018_청춘위스키 봉천_02 | 글렌모렌지 라산타 15Y | glenmorangie-lasanta | ambiguous / ambiguous_ok / confirm: Glenmorangie Lasanta | exact_match / correct / confirmed: Glenmorangie Lasanta |
| 020_네스트_02 | 글렌모렌지 오리지날 10년 | glenmorangie-original | ambiguous / ambiguous_ok / confirm: Glenmorangie The Original | exact_match / correct / confirmed: Glenmorangie The Original |

## server (675줄, 바뀐 줄 4)

| | Top-1 | FM | 틀린 확인 권장 | hard/photo | confirm/choose/register/wrong | 확정 |
|---|---|---|---|---|---|---|
| before | 498/646 | 1 | 2 | 2.394 | 89/53/14/12 | 507 |
| after | 500/646 | 1 | 2 | 2.364 | 88/52/14/12 | 509 |

맞는 확정이 사라진 줄 0, 새로 맞게 확정된 줄 2

| 사진 | 줄 | 정답 | 전 | 후 |
|---|---|---|---|---|
| 016_연림 봉천역점_03 | 글렌모렌지 12 | glenmorangie-original | ambiguous / ambiguous_ok / choose: Glenmorangie The Original || Glenmorangie 12 Calvados Cask Finish || Glenmorangi | ambiguous / ambiguous_ok / choose: Glenmorangie The Original || Glenmorangie 12 Calvados Cask Finish || Glenmorangi |
| 017_리틀 갤러리_03 | 글렌모렌지 15년 / Glenmorangie 15yr | glenmorangie-lasanta | ambiguous / ambiguous_ok / choose: Glenmorangie The Original || Glenmorangie 18 || Glenmorangie Lasanta || Glenmora | ambiguous / ambiguous_ok / confirm: Glenmorangie Lasanta |
| 018_청춘위스키 봉천_02 | 글렌모렌지 라산타 15Y | glenmorangie-lasanta | ambiguous / ambiguous_ok / confirm: Glenmorangie Lasanta | exact_match / correct / confirmed: Glenmorangie Lasanta |
| 020_네스트_02 | 글렌모렌지 오리지날 10년 | glenmorangie-original | ambiguous / ambiguous_ok / confirm: Glenmorangie The Original | exact_match / correct / confirmed: Glenmorangie The Original |

