# before_i3_ops.json -> after_i3_ops.json

## rules (675줄, 바뀐 줄 2)

| | Top-1 | FM | 틀린 확인 권장 | hard/photo | confirm/choose/register/wrong | 확정 |
|---|---|---|---|---|---|---|
| before | 511/646 | 1 | 2 | 2.424 | 75/36/42/2 | 520 |
| after | 511/646 | 1 | 2 | 2.394 | 76/36/41/2 | 520 |

맞는 확정이 사라진 줄 0, 새로 맞게 확정된 줄 0

| 사진 | 줄 | 정답 | 전 | 후 |
|---|---|---|---|---|
| 016_연림 봉천역점_03 | 글렌모렌지 12 | glenmorangie-original | ambiguous / ambiguous_ok / choose: Glenmorangie 12 Calvados Cask Finish \|\| Glenmorangie Lasanta \|\| Glenmorangie The | ambiguous / ambiguous_ok / choose: Glenmorangie 12 Calvados Cask Finish \|\| Glenmorangie Lasanta \|\| Glenmorangie Qui |
| 017_리틀 갤러리_03 | 글렌모렌지 15년 / Glenmorangie 15yr | glenmorangie-lasanta | unmatched / unmatched / register:  | ambiguous / ambiguous_ok / confirm: Glenmorangie Lasanta |

## server (675줄, 바뀐 줄 2)

| | Top-1 | FM | 틀린 확인 권장 | hard/photo | confirm/choose/register/wrong | 확정 |
|---|---|---|---|---|---|---|
| before | 511/646 | 1 | 2 | 1.97 | 90/54/8/3 | 520 |
| after | 511/646 | 1 | 2 | 1.939 | 91/53/8/3 | 520 |

맞는 확정이 사라진 줄 0, 새로 맞게 확정된 줄 0

| 사진 | 줄 | 정답 | 전 | 후 |
|---|---|---|---|---|
| 016_연림 봉천역점_03 | 글렌모렌지 12 | glenmorangie-original | ambiguous / ambiguous_ok / choose: Glenmorangie The Original \|\| Glenmorangie 12 Calvados Cask Finish \|\| Glenmorangi | ambiguous / ambiguous_ok / choose: Glenmorangie The Original \|\| Glenmorangie 12 Calvados Cask Finish \|\| Glenmorangi |
| 017_리틀 갤러리_03 | 글렌모렌지 15년 / Glenmorangie 15yr | glenmorangie-lasanta | ambiguous / ambiguous_ok / choose: Glenmorangie The Original \|\| Glenmorangie 18 \|\| Glenmorangie Lasanta \|\| Glenmora | ambiguous / ambiguous_ok / confirm: Glenmorangie Lasanta |

