# P24 (I3): 규칙 vs 규칙+생성 한글 별칭 vs 규칙+임베딩 후보 — dev 5곳 오프라인 비교

2026-10-29 밤 실행 · 박진우 (작성: Claude Code) · dev 5개 바(위스키복춘·서로상·미라보·수이·오드비), 라벨 입력, 32장 836줄, 카탈로그 v2.3

결정 메모는 `ai/docs/p24_embedding_decision.md`. 이 폴더는 숫자와 재현 방법이다. **I3 8곳(동결 시험셋)은 열지도 쓰지도 않았다.** 사진은 읽지 않았고 Gemini 등 유료 API 호출은 0회다(M3a 숫자는 E8 캐시 `--cache-only`).

## 파일

| 파일 | 내용 |
|---|---|
| `model_<name>.json` | 임베더 하나의 전체 결과: 카탈로그 4종 × 문서 집합 5종의 recall, 정책 4~5종의 i3_match_eval 지표와 불변식 검사, 확인 권장 보정·하한 스윕 원자료, M3a 조합, 사진당 지연, 메모리 |
| `summary.json` | 위 파일들을 모은 요약 (`summary` 명령의 출력) |

## 재현

모델은 Hugging Face의 ONNX export를 미리 받아 `<models-root>/<owner>--<name>/`에 둔다(가중치·캐시는 커밋하지 않음). 실행 환경: Python 3.12, onnxruntime 1.31.1, tokenizers 0.23.3, numpy 2.5.4, CPU Intel Xeon 2.8GHz(AVX-512 VNNI) 4코어 중 `--threads 2`(2 vCPU 서버 가정). torch는 쓰지 않는다.

```
python ai/eval/p24_embedding_compare.py run --model tfidf --out ai/runs/2026-10-30_p24
for m in minilm-l12 e5-small e5-small-int8 e5-base e5-base-int8 bge-m3; do
  python ai/eval/p24_embedding_compare.py run --model $m --models-root <models-root> --threads 2 --out ai/runs/2026-10-30_p24
done
python ai/eval/p24_embedding_compare.py summary --out ai/runs/2026-10-30_p24
```

모델은 프로세스 하나에 하나씩 돌린다(메모리 숫자를 깨끗하게). `run`은 하네스나 입력(`ai/eval`, `ai/catalog`, `eval`, 서버 매칭 코드)에 미커밋 변경이 있으면 멈추고(`--allow-dirty`로만 진행), 커밋·미커밋 변경·하네스 SHA-256을 `provenance`에 남긴다.

**어느 커밋의 결과인가.** `model_tfidf.json`은 리뷰 반영 뒤 `32b8314`에서 깨끗한 상태로 다시 돌린 값이다(바 인덱스별 fit, 정답 점수가 있는 `unmatched_top`). 나머지 6개는 하네스가 커밋되기 전(`repo_head` `c976b4f` + 미커밋 하네스)에 돌린 값이라 그 커밋으로는 재현되지 않고, `unmatched_top`에 정답 점수가 없어 `summary.json`의 `floor_sweep`이 `null`이다. 모델 하네스 경로는 리뷰 반영으로 바뀌지 않았으므로 recall·정책 숫자는 같아야 하지만, 확인은 현재 커밋으로 다시 돌려야 한다. `e5-small-int8`만 정책 `unmatched_k5+rerank_only`가 있다.

| 이름 | Hugging Face 저장소 | revision | 파일 | 풀링 / 접두어 |
|---|---|---|---|---|
| `tfidf` | (모델 없음) 문자 1~3-gram TF-IDF, 바 인덱스마다 그 인덱스 텍스트로만 fit | — | — | — |
| `minilm-l12` | sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2 | e8f8c211226b894fcb81acc59f3b34ba3efd5f42 | onnx/model.onnx | mean / 없음 |
| `e5-small` | intfloat/multilingual-e5-small | 614241f622f53c4eeff9890bdc4f31cfecc418b3 | onnx/model.onnx | mean / `query: ` |
| `e5-small-int8` | 〃 | 〃 | onnx/model_qint8_avx512_vnni.onnx | 〃 |
| `e5-base` | intfloat/multilingual-e5-base | d128750597153bb5987e10b1c3493a34e5a4502a | onnx/model.onnx | mean / `query: ` |
| `e5-base-int8` | 〃 | 〃 | onnx/model_qint8_avx512_vnni.onnx | 〃 |
| `bge-m3` | BAAI/bge-m3 | 5617a9f61b028005a4858fdac845db406aefb181 | onnx/model.onnx (+ .onnx_data) | 모델의 `sentence_embedding` 출력 |

입력 SHA-256 (모든 `model_*.json`에 기록):

- `ai/catalog/catalog_v2_service.json` (v2.3): `9feb1874aae2ee279aba20efc311cde40ecbd6afaf11b607b7869a578eb981e7`
- `eval/match_gold_v1_1.json`: `2fce4c75d192f407845721488fbb96569ff7dc3c7edd685a03060e1be8bbfbf7`, `eval/match_gold_final_v1.json`: `069ad55a6afef75b357a7e05aab3b2c969e113ccf7d20969def82750fb83ed57`
- `eval/labels_v1_1.json`: `a34249eb…93cf`, `eval/labels_heldout_v1_1.json`: `047bf7d6…c986`, `eval/labels_final_v1.json`: `a8ac42bb…fbf1` (전체 값은 JSON의 `labels_sha256`)
- 바별 카탈로그 digest(`i3_match_eval.catalog_digest`): eval `939ca5bf…`, eval_p17 `26a72253…`, service `b33814c9…`, eval_dropprod `90b2d18e…` (eval·service·eval_dropprod는 i3_match_eval dev 실행과 같은 값)

## 조건

| 조건 | 카탈로그 | 뜻 |
|---|---|---|
| (1) 규칙만 | `eval` | 생성/괄호제거 별칭은 다른 바 메뉴가 같은 표기를 줄 때만 남김 (E8과 같음) |
| (2) 규칙 + 생성 한글 별칭 (P17) | `eval_p17` | `service`에서 괄호제거(template:paren-strip)만 출처인 별칭을 뺀 것 |
| — | `service` | 서비스 카탈로그 그대로. 결과가 `eval_p17`과 줄 단위로 같다(괄호제거 별칭 265개는 S1의 괄호 변형이 이미 처리) |
| — | `eval_dropprod` | `eval`에서 그 바에서만 본 상품을 뺀 것: DB에 없는 술 압박 시험 |
| (3) 규칙 + 임베딩 후보 | 위 카탈로그 각각 | 규칙 결과 위에 `apply_policy`로 임베딩 후보를 붙임. 확정된 줄은 그대로, 새로 만드는 결과는 언제나 `ambiguous` |

모든 카탈로그는 i3_match_eval처럼 바마다 만들고, 그 바 메뉴에서만 온 별칭은 뺀다. 임베딩 인덱스도 그 바 카탈로그에 남은 별칭 원문만 쓴다(자기 메뉴 표기 누출 없음, 단위 테스트로 확인).

문서 집합(무엇을 임베딩하나): `canonical` 표시명, `aliases` 표시명+별칭 전부, `korean` 한글 별칭만, `brand_age` 표시명+"브랜드 별칭 에디션 연수(년)", `all` aliases+brand_age. 상품 점수는 그 상품 텍스트들 중 최고 코사인.

정책: `unmatched_k5`/`k3` 규칙이 못 찾은 줄(unmatched)에만 상위 5/3개, `fill_k5` 후보가 있는 ambiguous 줄(확인 권장 없음)에도 5개까지 채움, `rerank_k5` fill + 임베딩 순서로 재정렬, `unmatched_k5+rerank_only` unmatched에 5개 + ambiguous 줄은 추가 없이 임베딩 순서로 재정렬만. 확인 권장(confirmRecommended)은 어떤 정책도 달지 않는다.

## 결과 1 — 규칙 기준선 (i3_match_eval dev와 같은 숫자)

| 카탈로그 | Top-1 | FM | 틀린 확인 권장 | confirm / choose / register / wrong (합계) | 어려운 줄/사진 |
|---|---|---|---|---|---|
| eval (1) | 0.643 (516/802) | 0 | 3 | 85 / 67 / 150 / 18 | 8.10 |
| eval_p17 (2) | 0.771 (618/802) | 0 | 4 | 85 / 53 / 71 / 9 | 4.59 |
| service | 0.771 (618/802) | 0 | 4 | 85 / 53 / 71 / 9 | 4.59 |
| eval_dropprod | 0.783 (375/479) | 0 | 6 | 42 / 28 / 334 / 57 | 14.45 |

**(3)의 Top-1·FM·틀린 확인 권장은 모든 경우에 규칙과 같다**: 7개 임베더 × 4개 카탈로그 × 5개 문서 집합 × 정책 = 600개 조합 전부 `invariants.holds = true`(새로 확정된 줄 0, 바뀐 확정 줄 0, Top-1 정답 수·FM 수 동일). M3a 조합도 같은 검사를 통과했다. 코드상으로도 `apply_policy`는 확정 결과를 그대로 돌려주고 `ambiguous`만 만든다.

## 결과 2 — 정답이 후보 안에 있나 (규칙이 확정 못한 알려진 줄)

대상 줄 수: eval 286(그중 규칙 unmatched 122), service 184(45), eval_dropprod 104(34). 숫자는 recall@1/3/5/10.

`service` 카탈로그, 문서 집합 `aliases`:

| 임베더 | 임베딩 순위만 | 운영자에게 보이는 목록 (권장 정책) | 사진당 지연 평균 / p95 (ms, 2스레드, 평균 28.8줄, **문서 집합 `all` 인덱스**) | RSS 증가 / 최고 (MB, **실행 전체**) | 파일 (MB) | 카탈로그 5,382텍스트 임베딩 (s) |
|---|---|---|---|---|---|---|
| 규칙만 (후보 목록) | — | 0.62 / 0.71 / 0.71 / 0.71 | — | — | — | — |
| tfidf ² | 0.67 / 0.87 / 0.97 / 0.99 | 0.83 / 0.92 / 0.95 / 0.95 | 199 / 420 (순수 Python) | 0 / 1048 ³ | 0 | 8.7 (인덱스 100개 fit) |
| minilm-l12 | 0.43 / 0.57 / 0.65 / 0.72 | 0.71 / 0.84 / 0.84 / 0.84 ¹ | 323 / 700 | 831 / 1168 | 449 | 38.8 |
| e5-small | 0.92 / 0.99 / 0.99 / 1.00 | 0.84 / 0.95 / 0.95 / 0.96 ¹ | 322 / 654 | 831 / 1168 | 449 | 38.3 |
| **e5-small-int8** | **0.93 / 0.99 / 0.99 / 1.00** | **0.91 / 0.96 / 0.96 / 0.96** | **253 / 519** | **453 / 694** | **113** | **20.7** |
| e5-base | 0.86 / 0.98 / 0.99 / 1.00 | 0.83 / 0.95 / 0.95 / 0.96 ¹ | 963 / 1955 | 1612 / 2144 | 1059 | 141 |
| e5-base-int8 | 0.85 / 0.96 / 0.99 / 1.00 | 0.84 / 0.95 / 0.95 / 0.96 ¹ | 437 / 954 | 654 / 964 | 266 | 62.5 |
| bge-m3 | 0.91 / 0.98 / 0.99 / 1.00 | 0.84 / 0.95 / 0.95 / 0.96 ¹ | 2871 / 6925 | 1479 / 1983 | 2163 | 496 |

¹ `unmatched_k5`(재정렬 없음). 권장 정책 `unmatched_k5+rerank_only`는 tfidf와 e5-small-int8만 돌렸다.
² 바 인덱스별 fit으로 다시 돌린 값. 처음(모든 텍스트로 한 번 fit, 바 자신의 메뉴 표기가 IDF에 섞임)은 0.71 / 0.89 / 0.96 / 0.99, 418 / 716 ms였다.
³ 하네스가 바 인덱스 100개를 동시에 들고 있는 값. 서버는 인덱스 하나다.

카탈로그별 최고값(임베딩 순위 recall@1/@5, 문서 집합):

| 임베더 | eval (생성 별칭 없음) | service | eval_dropprod |
|---|---|---|---|
| tfidf | 0.33/0.66 (all) | 0.70/0.96 (all) | 0.62/0.97 (all) |
| e5-small-int8 | 0.70/0.88 (canonical) | 0.93/0.99 (aliases) | 0.86/0.96 (aliases) |
| bge-m3 | 0.84/0.96 (brand_age) | 0.92/0.99 (all) | 0.86/1.00 (all) |

문서 집합(e5-small-int8, service, @1/@5): canonical 0.63/0.85, aliases 0.93/0.99, korean 0.92/0.98, brand_age 0.71/0.93, all 0.93/0.99. 생성 한글 별칭이 있으면 별칭을 임베딩하는 것이 가장 좋고, 없으면(eval) 표시명이나 브랜드+연수 문자열이 낫다.

## 결과 3 — 업주 부담 (e5-small-int8, aliases, service, 줄 합계)

| 매처 | confirm | choose | register | wrong | 알려진 줄 직접 등록 | 보이는 목록 recall@1/@5 |
|---|---|---|---|---|---|---|
| 규칙 | 85 | 53 | 71 | 9 | 45 | 0.62 / 0.71 |
| 규칙 + 임베딩 (`unmatched_k5+rerank_only`) | 85 | 107 | 0 | 26 | 0 | 0.91 / 0.96 |
| 규칙 + 임베딩 (`fill_k5`) | 46 | 151 | 0 | 21 | 0 | 0.85 / 0.98 |
| 규칙 + M3a (E8 캐시) | 129 | 41 | 43 | 5 | 18 | 0.82 / 0.88 |
| 규칙 + M3a, 그 뒤 임베딩 | 129 | 67 | 0 | 22 | 0 | 0.91 / 0.98 |
| 규칙 + 임베딩, 그 위에 M3a | 129 | 67 | 0 | 22 | 0 | 0.91 / 0.97 |

- 어려운 줄/사진(choose+register+wrong)은 임베딩으로 줄지 않는다(4.59 그대로): register가 choose로 바뀔 뿐이다. 이득은 "검색해서 등록"이 "목록에서 고르기"로 바뀌는 것(알려진 줄 직접 등록 45 → 0, 정답이 보이는 목록 1순위인 비율 0.62 → 0.91).
- `fill_k5`는 후보 1개짜리 ambiguous 줄(confirm)을 choose로 만든다(85 → 46). 그래서 ambiguous 줄에는 추가하지 않고 순서만 바꾼다.
- 없는 술/메뉴 아닌 줄: service에서 규칙 unmatched 71줄 중 26줄은 정답 상품이 없는 줄(unknown/non_whisky)이고, 임베딩은 여기에도 후보를 붙여 wrong이 9 → 26이 된다. 하한 스윕(`summary.json` `floor_sweep`)은 이제 정답 후보 자신의 점수로 "쓸모 있는 줄이 남는가"를 센다. 처음 숫자(e5-small-int8: 하한 0.909면 45/45 유지, 26줄 중 5줄; eval_dropprod 0.889로도 300줄 중 210줄)는 1순위 점수로 센 것이라 남는 정답을 부풀렸고, 모델을 다시 돌리기 전까지 쓰지 않는다. 다시 돌린 TF-IDF: service에서 하한 0.380이면 43/43 유지, 정답 없는 26줄 중 8줄이 후보를 받는다. eval_dropprod에서는 하한 0.210이면 32/32 유지, 없는 술 300줄 중 267줄이 후보를 받는다. 하한이 없는 술에는 거의 듣지 않는다는 결론은 TF-IDF에서도 같다.

## 결과 4 — 임베딩만으로 확인 권장? (e5-small-int8, aliases, 규칙 unmatched 줄의 1순위)

| 카탈로그 | 유사도 ≥ 0.93 | 유사도 ≥ 0.95 |
|---|---|---|
| service | 36줄 중 35 정답 | — |
| eval_dropprod | 72줄 중 22 정답 | 26줄 중 13 정답 |

같은 임계값이 카탈로그에 따라 정밀도 0.97과 0.31로 갈린다(없는 술이면 형제 상품이 높은 유사도로 1순위). 임베딩 점수만으로 확인 권장을 다는 것은 안전하지 않다.

M3a와의 관계(`model_*.json` `llm`): "임베딩 → M3a"로 하면 M3a `combine` 규칙상 LLM이 새로 고른 상품은 임베딩 후보 안에 있을 때만 확인 권장이 된다(교차 확인). eval_dropprod 틀린 확인 권장 14 → 13(LLM 확인 권장 57 → 55, 정답 48 → 47), 그러나 eval에서는 LLM 정답 확인 권장 149 → 119로 30개를 잃는다. service에서는 변화 없음(LLM 확인 권장 68개 중 정답 67, 그대로).

## 하지 않은 것 / 주의

- dev 5곳만. 숫자 대부분(특히 하한·임계값)은 같은 데이터에서 본 것이라 낙관적이다. 채택 판정은 I3 동결 시험셋에서 따로 해야 한다.
- M3a 프롬프트에 임베딩 후보를 넣는 것과 E10 tool calling의 `search_catalog`를 임베딩으로 바꾸는 것은 캐시 키가 바뀌어 Gemini 호출 없이 측정할 수 없어 하지 않았다.
- 지연은 이 컨테이너 CPU(AVX-512 VNNI) 2스레드 값이다. t3.micro(버스터블)에서는 더 느릴 수 있다. TF-IDF 지연은 순수 Python 희소 구현 값이다.
- 하네스는 `i3_match_eval.dev_photos()`만 쓴다(I3 파일이면 거부). 실행 중 `ai/docs/i3_eval_freeze.md`의 한 줄(E10 도구 설명, 230행)이 레포 전체 grep 결과에 섞여 보였다. 바 이름·라벨·정답은 보지 않았다.
