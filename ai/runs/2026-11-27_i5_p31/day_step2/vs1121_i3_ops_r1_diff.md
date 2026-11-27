# i3_ops_label_on_r1.json -> i3_ops_label_r1.json

## server (675줄, 바뀐 줄 6)

| | Top-1 | FM | 틀린 확인 권장 | hard/photo | confirm/choose/register/wrong | 확정 |
|---|---|---|---|---|---|---|
| before | 511/646 | 1 | 3 | 1.576 | 103/39/8/5 | 520 |
| after | 511/646 | 1 | 2 | 1.455 | 107/38/8/2 | 520 |

맞는 확정이 사라진 줄 1, 새로 맞게 확정된 줄 1

| 사진 | 줄 | 정답 | 전 | 후 |
|---|---|---|---|---|
| 015_연림 서울대입구역점_04 | 글렌모렌지 12 라산타 | glenmorangie-lasanta | ambiguous / ambiguous_bad / wrong: Glenmorangie 12 Calvados Cask Finish | exact_match / correct / confirmed: Glenmorangie Lasanta |
| 016_연림 봉천역점_03 | 글렌모렌지 12 | glenmorangie-original | ambiguous / ambiguous_bad / wrong CR: Glenmorangie 12 Calvados Cask Finish | ambiguous / ambiguous_ok / choose: Glenmorangie The Original \|\| Glenmorangie 12 Calvados Cask Finish \|\| Glenmorangi |
| 017_리틀 갤러리_03 | 글랜모랜지 14년 / Glenmorangie 14yr | glenmorangie-quinta-ruban | ambiguous / ambiguous_bad / wrong: Glenmorangie The Original \|\| Glenmorangie 18 \|\| Glenmorangie Lasanta \|\| Glenmora | ambiguous / ambiguous_ok / confirm CR: Glenmorangie Quinta Ruban |
| 017_리틀 갤러리_03 | 글렌모렌지 15년 / Glenmorangie 15yr | glenmorangie-lasanta | ambiguous / ambiguous_ok / choose: Glenmorangie The Original \|\| Glenmorangie 18 \|\| Glenmorangie Lasanta \|\| Glenmora | ambiguous / ambiguous_ok / confirm CR: Glenmorangie Lasanta |
| 017_리틀 갤러리_03 | 글렌모렌지 16년 / Glenmorangie 16yr | glenmorangie-nectar-dor | ambiguous / ambiguous_ok / choose: Glenmorangie The Original \|\| Glenmorangie 18 \|\| Glenmorangie Nectar D'Or \|\| Glen | ambiguous / ambiguous_ok / confirm CR: Glenmorangie Nectar D'Or |
| 018_청춘위스키 봉천_02 | 글렌모렌지 더 넥타 16Y | glenmorangie-nectar-dor | exact_match / correct / confirmed: Glenmorangie Nectar D'Or | ambiguous / ambiguous_ok / confirm CR: Glenmorangie Nectar D'Or |

