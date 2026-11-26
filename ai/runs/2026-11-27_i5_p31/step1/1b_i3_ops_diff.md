# 1b 연수 없는 줄 가드 꺼짐 → 켜짐: i3_ops

## server (675줄, 바뀐 줄 25)

| | Top-1 | FM | 틀린 확인 권장 | hard/photo | confirm/choose/register/wrong | 확정 |
|---|---|---|---|---|---|---|
| before | 511/646 | 1 | 2 | 1.97 | 90/54/8/3 | 520 |
| after | 487/646 | 0 | 3 | 2.0 | 114/55/8/3 | 495 |

맞는 확정이 사라진 줄 24, 새로 맞게 확정된 줄 0

| 사진 | 줄 | 정답 | 전 | 후 |
|---|---|---|---|---|
| 014_테일오브테일즈_01 | Johnnie Walker Black Label | johnnie-walker-black | exact_match / correct / confirmed: Johnnie Walker Black Label | ambiguous / ambiguous_ok / confirm CR: Johnnie Walker Black Label |
| 014_테일오브테일즈_07 | Ardbeg WEE Beastie | ardbeg-wee-beastie | exact_match / correct / confirmed: Ardbeg Wee Beastie 5 | ambiguous / ambiguous_ok / confirm CR: Ardbeg Wee Beastie 5 |
| 014_테일오브테일즈_07 | Ardbeg Anthology | unknown | exact_match / overconfident / confirmed: Ardbeg Anthology 14 | ambiguous / ambiguous_ok / choose CR: Ardbeg Anthology 14 |
| 014_테일오브테일즈_08 | Glenmorangie Original | glenmorangie-original | exact_match / correct / confirmed: Glenmorangie The Original | ambiguous / ambiguous_ok / confirm CR: Glenmorangie The Original |
| 014_테일오브테일즈_08 | Glenmorangie Lasanta | glenmorangie-lasanta | exact_match / correct / confirmed: Glenmorangie Lasanta | ambiguous / ambiguous_ok / confirm CR: Glenmorangie Lasanta |
| 014_테일오브테일즈_08 | Glenmorangie Quinta Ruban | glenmorangie-quinta-ruban | exact_match / correct / confirmed: Glenmorangie Quinta Ruban | ambiguous / ambiguous_ok / confirm CR: Glenmorangie Quinta Ruban |
| 014_테일오브테일즈_08 | Glenmorangie The Nectar | glenmorangie-nectar-dor | exact_match / correct / confirmed: Glenmorangie Nectar D'Or | ambiguous / ambiguous_ok / confirm CR: Glenmorangie Nectar D'Or |
| 014_테일오브테일즈_11 | Glenmorangie Original | glenmorangie-original | exact_match / correct / confirmed: Glenmorangie The Original | ambiguous / ambiguous_ok / confirm CR: Glenmorangie The Original |
| 014_테일오브테일즈_11 | Glenmorangie The Nectar | glenmorangie-nectar-dor | exact_match / correct / confirmed: Glenmorangie Nectar D'Or | ambiguous / ambiguous_ok / confirm CR: Glenmorangie Nectar D'Or |
| 015_연림 서울대입구역점_01 | 글렌모렌지 오리지널 | glenmorangie-original | exact_match / correct / confirmed: Glenmorangie The Original | ambiguous / ambiguous_ok / confirm CR: Glenmorangie The Original |
| 015_연림 서울대입구역점_02 | 조니워커 블랙 | johnnie-walker-black | exact_match / correct / confirmed: Johnnie Walker Black Label | ambiguous / ambiguous_ok / confirm CR: Johnnie Walker Black Label |
| 016_연림 봉천역점_01 | 조니워커 블랙 | johnnie-walker-black | exact_match / correct / confirmed: Johnnie Walker Black Label | ambiguous / ambiguous_ok / confirm CR: Johnnie Walker Black Label |
| 017_리틀 갤러리_02 | 조니워커 블랙 라벨 / Johnnie Walker Black Label | johnnie-walker-black | exact_match / correct / confirmed: Johnnie Walker Black Label | ambiguous / ambiguous_ok / confirm CR: Johnnie Walker Black Label |
| 017_리틀 갤러리_02 | 조니워커 그린 라벨 / Johnnie Walker Green Label | johnnie-walker-green | exact_match / correct / confirmed: Johnnie Walker Green Label | ambiguous / ambiguous_ok / confirm CR: Johnnie Walker Green Label |
| 018_청춘위스키 봉천_02 | 글렌모렌지 오리지널 | glenmorangie-original | exact_match / correct / confirmed: Glenmorangie The Original | ambiguous / ambiguous_ok / confirm CR: Glenmorangie The Original |
| 019_쏘댓page2_01 | 글렌모렌지오리지널 | glenmorangie-original | exact_match / correct / confirmed: Glenmorangie The Original | ambiguous / ambiguous_ok / confirm CR: Glenmorangie The Original |
| 019_쏘댓page2_01 | 글렌모렌지라산타 | glenmorangie-lasanta | exact_match / correct / confirmed: Glenmorangie Lasanta | ambiguous / ambiguous_ok / confirm CR: Glenmorangie Lasanta |
| 019_쏘댓page2_01 | 글렌모렌지퀸타루반 | glenmorangie-quinta-ruban | exact_match / correct / confirmed: Glenmorangie Quinta Ruban | ambiguous / ambiguous_ok / confirm CR: Glenmorangie Quinta Ruban |
| 019_쏘댓page2_01 | 글렌모렌지더넥타 | glenmorangie-nectar-dor | exact_match / correct / confirmed: Glenmorangie Nectar D'Or | ambiguous / ambiguous_ok / confirm CR: Glenmorangie Nectar D'Or |
| 019_쏘댓page2_04 | 조니워커 블랙 | johnnie-walker-black | exact_match / correct / confirmed: Johnnie Walker Black Label | ambiguous / ambiguous_ok / confirm CR: Johnnie Walker Black Label |
| 019_쏘댓page2_04 | 조니워커 그린 | johnnie-walker-green | exact_match / correct / confirmed: Johnnie Walker Green Label | ambiguous / ambiguous_ok / confirm CR: Johnnie Walker Green Label |
| 020_네스트_01 | 조니워커 블랙 | johnnie-walker-black | exact_match / correct / confirmed: Johnnie Walker Black Label | ambiguous / ambiguous_ok / confirm CR: Johnnie Walker Black Label |
| 021_무용의 유용_01 | 글렌모렌지 더 넥타 | glenmorangie-nectar-dor | exact_match / correct / confirmed: Glenmorangie Nectar D'Or | ambiguous / ambiguous_ok / confirm CR: Glenmorangie Nectar D'Or |
| 021_무용의 유용_01 | 아드벡 위비스티 | ardbeg-wee-beastie | exact_match / correct / confirmed: Ardbeg Wee Beastie 5 | ambiguous / ambiguous_ok / confirm CR: Ardbeg Wee Beastie 5 |
| 021_무용의 유용_02 | 아드벡 위비스티 | ardbeg-wee-beastie | exact_match / correct / confirmed: Ardbeg Wee Beastie 5 | ambiguous / ambiguous_ok / confirm CR: Ardbeg Wee Beastie 5 |

