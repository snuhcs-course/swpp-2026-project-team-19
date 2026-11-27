# i3_full_label_r3.json -> i3_full_label_r3.json

## server (675줄, 바뀐 줄 3)

| | Top-1 | FM | 틀린 확인 권장 | hard/photo | confirm/choose/register/wrong | 확정 |
|---|---|---|---|---|---|---|
| before | 500/646 | 1 | 4 | 1.576 | 114/40/9/3 | 509 |
| after | 502/646 | 1 | 4 | 1.576 | 112/40/9/3 | 511 |

맞는 확정이 사라진 줄 0, 새로 맞게 확정된 줄 2

| 사진 | 줄 | 정답 | 전 | 후 |
|---|---|---|---|---|
| 018_청춘위스키 봉천_01 | 브룩라디 더 클래식 | bruichladdich-classic-laddie | ambiguous / ambiguous_ok / confirm CR: Bruichladdich The Classic Laddie Scottish Barley | exact_match / correct / confirmed: Bruichladdich The Classic Laddie Scottish Barley |
| 018_청춘위스키 봉천_01 | 브룩라디 포트샬롯 | port-charlotte-10 | ambiguous / ambiguous_ok / choose: Port Charlotte 10 || Bruichladdich 18 | ambiguous / ambiguous_ok / choose: Port Charlotte 10 || Port Charlotte Islay Barley 2014 || Port Charlotte PMC:01 |
| 018_청춘위스키 봉천_02 | 글렌모렌지 더 넥타 16Y | glenmorangie-nectar-dor | ambiguous / ambiguous_ok / confirm CR: Glenmorangie The Nectar | exact_match / correct / confirmed: Glenmorangie The Nectar |

