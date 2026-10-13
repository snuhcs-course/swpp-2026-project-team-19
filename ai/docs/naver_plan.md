# Naver 후보 수집 + LLM 확인 계획 (P17·P18)

2026-10-13 · 박진우 (작성: Claude Code, 검토: 박진우) · 브랜치 `i2-p17-naver`

메뉴 표기(한글·병입사식)를 카탈로그 별칭으로 보강하기 위해, NAVER API HUB 검색 결과에서 상품별 한글 표기 후보를 모으고 LLM으로 같은 상품인지 확인하는 프로토타입이다. P22 test에서 상품이 DB에 있어도 메뉴 표기를 못 찾은 168줄(C1)이 출발점이다 (`2026-10-13_match_summary`, 남은 오류 3).

## 1. 원칙

- **Naver 결과와 LLM 판정은 후보 제안과 판정 기록까지만 한다.** 이번 작업에서는 DB와 카탈로그(`catalog_v1_draft.json`)에 아무것도 반영하지 않는다.
- 나중에 서비스에 붙일 때의 구분:
  - **매칭**(메뉴 줄 → 기존 상품): LLM 신뢰도가 임계값 이상이면 자동 확정해서 바로 서비스한다.
  - **등록**(새 상품·새 별칭 생성): 판정과 상관없이 사람이 검토한다 (P36).
  - 임계값은 P29(10/15)에서 측정 근거로 정한다. **이번에는 정하지 않는다.**
- 모든 후보에 출처를 기록한다: endpoint, query, 결과 URL, 조회 시각, 원문 title.
- API 키(NAVER API HUB, Gemini)는 `.env`에서만 읽고, 로그와 결과 파일에 남기지 않는다.
- 응답 캐시(`<data_dir>/naver_cache/`)는 레포 밖에 두고 커밋하지 않는다.

## 2. 평가 표본 (P28용, 이번 작업에서 실행·열람 금지)

- 대상: `eval/match_gold_v1.json`의 new 상품 337개 (dev 30 + test 307; test 324 중 dev와 겹치는 17개는 dev로 셈하지 않고 한 번만 셈).
- 층: **독립병입**(병입사가 다른 증류소 원액을 자기 이름으로 낸 상품) 20, **증류소 정규품**(그 외) 20.
- 독립병입 판정은 new 상품의 `brand`가 아래 병입사 목록에 있는지로 정한다. 목록은 표본 추출 전에 `ai/naver/sample.py`의 `IB_BOTTLERS`에 고정했다.
  - Signatory, Gordon & MacPhail, Douglas Laing, Hunter Laing, La Maison du Whisky, The Whisky Agency, Samaroli, Wilson & Morgan, Highland Laird, Elements of Islay, Port Askaig, Blackadder
  - 정규품으로 둔 경계 사례: Compass Box·Michel Couvreur(블렌더·숙성사), Macnair's(GlenAllachie 소유 브랜드), Ki One(국내 증류소).
- 추출: `random.Random(20261013)`로 각 층에서 20개씩 비복원 추출 → `eval/naver_sample_v1.json`. 이 파일은 다른 작업보다 먼저 커밋했다.
- 이 40개는 P17 스모크·프롬프트 수정에 쓰지 않는다. 스모크 표본은 이 40개를 뺀 나머지에서 뽑는다.
