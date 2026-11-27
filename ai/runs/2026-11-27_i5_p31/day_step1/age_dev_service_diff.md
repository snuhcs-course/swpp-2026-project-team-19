# before_age_dev_service.json -> after_age_dev_service.json

## rules (836줄, 바뀐 줄 1)

| | Top-1 | FM | 틀린 확인 권장 | hard/photo | confirm/choose/register/wrong | 확정 |
|---|---|---|---|---|---|---|
| before | 626/804 | 0 | 3 | 4.138 | 90/43/71/6 | 626 |
| after | 627/804 | 0 | 3 | 4.103 | 90/43/70/6 | 627 |

맞는 확정이 사라진 줄 0, 새로 맞게 확정된 줄 1

| 사진 | 줄 | 정답 | 전 | 후 |
|---|---|---|---|---|
| 011_미라보_04 | 글렌모렌지(Glenmorangie) 15년 라산타 | glenmorangie-lasanta | unmatched / unmatched / register:  | exact_match / correct / confirmed: Glenmorangie Lasanta |

## server (836줄, 바뀐 줄 1)

| | Top-1 | FM | 틀린 확인 권장 | hard/photo | confirm/choose/register/wrong | 확정 |
|---|---|---|---|---|---|---|
| before | 626/804 | 0 | 3 | 3.793 | 100/84/18/8 | 626 |
| after | 627/804 | 0 | 3 | 3.759 | 100/83/18/8 | 627 |

맞는 확정이 사라진 줄 0, 새로 맞게 확정된 줄 1

| 사진 | 줄 | 정답 | 전 | 후 |
|---|---|---|---|---|
| 011_미라보_04 | 글렌모렌지(Glenmorangie) 15년 라산타 | glenmorangie-lasanta | ambiguous / ambiguous_ok / choose: Glenmorangie The Original || Glenmorangie 18 || Glenmorangie Lasanta || Glenmora | exact_match / correct / confirmed: Glenmorangie Lasanta |

