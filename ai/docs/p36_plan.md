# P36 준비: 카탈로그 v2 전체 Naver 별칭 후보 대기열 (실행 전 등록)

2026-10-15 야간 · 작성: Claude Code · 검토: 박진우 · 브랜치 `i2-p36-naver-queue` (`i2-p28-naver-precision` + `origin/i2-catalog-v2` 머지)

**카탈로그와 DB에는 아무것도 넣지 않는다.** 결과는 사람이 검토할 대기열(`review/p36_alias_queue.csv`)뿐이다.

## 대상과 방법

- 대상: `ai/catalog/catalog_v2_service.json` 상품 529개 전부. P28 표본 40개는 P28 결과(`ai/runs/2026-10-15_p28/results.json`)의 후보와 LLM 판정을 그대로 쓰고, 태그·제외 사유만 이 카탈로그로 다시 계산한다.
- 1단계(Naver만): P17 코드(`a22bfee`) 그대로 질의·후보 추출(상품당 상위 5개). 한글 브랜드 별칭은 `catalog_v2_service`에서 찾는다. Naver 초당 4회 이하, 캐시(`<data_dir>/naver_cache/`), 하루 25,000회 안.
- 독립병입 판정: M3·P17 병입사 목록(12곳)을 브랜드 key 또는 이름으로 대조(`match_eval.product_meta`와 같음).
- 매처 태그: S1+S2b+S3, 카탈로그 = `catalog_v2_service` 전체 별칭.
- 2단계(LLM): 1·2번 작업 뒤 Gemini 한도가 남아 있을 때만, 제외되지 않은 후보에 `judge.py` alias 모드(`judge_prompt_v1`, 바꾸지 않음). 429·`RESOURCE_EXHAUSTED`가 나오면 멈추고 남은 후보는 `pending_judge`로 둔다. 판정 캐시로 이어서 할 수 있다.

## 자동 제외 규칙 (LLM 없이, 여러 개가 붙을 수 있음)

| 사유 | 규칙 |
| --- | --- |
| `other_product` | 매처가 다른 상품으로 확정(또는 다른 상품을 포함한 두 상품 결과) |
| `bottler_missing` | 독립병입 상품인데 후보에 병입사 이름(브랜드·학습 앵커)이 없음 (`candidates.bottler_missing`) |
| `age_mismatch` | 후보에 연수가 있고 상품 연수와 다름(상품이 무연수인데 후보에 연수가 있는 경우 포함) |
| `existing_alias` | 후보의 정규화 결과가 그 상품의 기존 별칭과 같음 |

## 표시만 하는 것

- `p47_only`: 상품의 출처가 `menu:수이`·`menu:오드비`뿐인 상품(P47 바에서만 나온 상품). **P47 평가 전에 이 상품의 별칭을 승인하면 P47 메뉴 표기가 카탈로그에 새어 들어갈 수 있다.** 검토는 P47 이후로 미루는 것을 권한다. 수이·오드비 사진과 정답 파일은 열지 않았다(카탈로그의 `sources` 필드만 읽음).

## 기록

`ai/runs/2026-10-15_p36/candidates.json`(상품별 후보·근거·태그·제외 사유·판정), `judge_cache.json`, `README.md`.
