# before_age_i3_ops.json -> after_age_i3_ops.json

## rules (675줄, 바뀐 줄 4)

| | Top-1 | FM | 틀린 확인 권장 | hard/photo | confirm/choose/register/wrong | 확정 |
|---|---|---|---|---|---|---|
| before | 509/646 | 1 | 2 | 2.424 | 77/36/42/2 | 518 |
| after | 511/646 | 1 | 2 | 2.394 | 76/36/41/2 | 520 |

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
| before | 509/646 | 1 | 2 | 1.97 | 92/54/8/3 | 518 |
| after | 511/646 | 1 | 2 | 1.939 | 91/53/8/3 | 520 |

맞는 확정이 사라진 줄 0, 새로 맞게 확정된 줄 2

| 사진 | 줄 | 정답 | 전 | 후 |
|---|---|---|---|---|
| 016_연림 봉천역점_03 | 글렌모렌지 12 | glenmorangie-original | ambiguous / ambiguous_ok / choose: Glenmorangie The Original || Glenmorangie 12 Calvados Cask Finish || Glenmorangi | ambiguous / ambiguous_ok / choose: Glenmorangie The Original || Glenmorangie 12 Calvados Cask Finish || Glenmorangi |
| 017_리틀 갤러리_03 | 글렌모렌지 15년 / Glenmorangie 15yr | glenmorangie-lasanta | ambiguous / ambiguous_ok / choose: Glenmorangie The Original || Glenmorangie 18 || Glenmorangie Lasanta || Glenmora | ambiguous / ambiguous_ok / confirm: Glenmorangie Lasanta |
| 018_청춘위스키 봉천_02 | 글렌모렌지 라산타 15Y | glenmorangie-lasanta | ambiguous / ambiguous_ok / confirm: Glenmorangie Lasanta | exact_match / correct / confirmed: Glenmorangie Lasanta |
| 020_네스트_02 | 글렌모렌지 오리지날 10년 | glenmorangie-original | ambiguous / ambiguous_ok / confirm: Glenmorangie The Original | exact_match / correct / confirmed: Glenmorangie The Original |

