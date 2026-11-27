# dev_service_on_r1.json -> dev_service_r1.json

## server (836줄, 바뀐 줄 3)

| | Top-1 | FM | 틀린 확인 권장 | hard/photo | confirm/choose/register/wrong | 확정 |
|---|---|---|---|---|---|---|
| before | 625/804 | 0 | 3 | 2.69 | 133/54/18/6 | 625 |
| after | 627/804 | 0 | 3 | 2.586 | 134/52/18/5 | 627 |

맞는 확정이 사라진 줄 0, 새로 맞게 확정된 줄 2

| 사진 | 줄 | 정답 | 전 | 후 |
|---|---|---|---|---|
| 011_미라보_04 | 글렌모렌지(Glenmorangie) 12년 오리지널 | glenmorangie-original | ambiguous / ambiguous_bad / wrong: Glenmorangie 12 Calvados Cask Finish | exact_match / correct / confirmed: Glenmorangie The Original |
| 011_미라보_04 | 글렌모렌지(Glenmorangie) 15년 라산타 | glenmorangie-lasanta | ambiguous / ambiguous_ok / choose: Glenmorangie The Original || Glenmorangie 18 || Glenmorangie Lasanta || Glenmora | exact_match / correct / confirmed: Glenmorangie Lasanta |
| 011_미라보_04 | 글렌모렌지(Glenmorangie) 16년 더 넥타 | glenmorangie-nectar-dor | ambiguous / ambiguous_ok / choose: Glenmorangie The Original || Glenmorangie 18 || Glenmorangie Nectar D'Or || Glen | ambiguous / ambiguous_ok / confirm CR: Glenmorangie Nectar D'Or |

