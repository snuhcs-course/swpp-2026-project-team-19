# P14 실험 설계: Vision LLM 메뉴 추출 PoC

2026-10-04 · 박진우 (2026-10-04 실행 전 보강: 반복 5회, 조건 A2, 전처리 1회 고정, API 설정·메타데이터 확정)

**질문:** Gemini Flash-Lite로 시작해도 되는가? 평가셋 9장에서 항목 정답률을 재고, `eval_plan.md`의 판정 규칙으로 결정한다.

## 조건

| 조건 | 모델 ID (버전 고정) | thinking | 역할 |
| --- | --- | --- | --- |
| A (주) | `gemini-3.5-flash-lite` | `minimal` (모델 기본값) | 쓰려는 저비용 모델 |
| A2 | `gemini-3.5-flash-lite` | `medium` | 모델은 A와 같고 thinking은 B와 같다. A·B 차이가 모델 때문인지 thinking 때문인지 분리 |
| B (참고) | `gemini-3.6-flash` | `medium` (모델 기본값) | A·A2가 하한선을 못 넘을 때 "모델을 올리면 해결되나" 판단용 |

`-latest` 같은 별칭은 쓰지 않는다. 별칭이 가리키는 모델이 바뀌면 같은 실험이 재현되지 않는다.

`thinking_level`은 세 조건 모두 명시해서 넘긴다(A·B는 기본값과 같은 값). 모델 기본값이 바뀌어도 같은 실험이 재현되게 하기 위함이다.

## 고정 변수 (전 조건 공통)

- **프롬프트 v1:** `labeling_guideline_v2.1.md`의 항목 규칙·값 규칙·비위스키 목록 + 출력 JSON 스키마. 프롬프트 파일은 버전을 붙여 저장한다 (`prompt_v1.md`)
- **예시는 텍스트로만 넣는다.** 가이드라인의 예시(입력 줄 → 출력 JSON)만 쓰고, 이미지는 프롬프트에 넣지 않는다. `data/fewshot/` 3장은 예시 원본일 뿐 전체 정답이 없다. 평가셋 사진·라벨을 프롬프트에 넣으면 실험 무효
- **API:** `google-genai` SDK 2.28.0, Interactions API(`client.interactions.create`), `store=False`(요청·응답을 서버에 보관하지 않음)
- **이미지 전처리 (사진당 1회):** EXIF 회전값이 있을 때만 회전 후 EXIF를 제거한 JPEG(quality 95)로 재인코딩, 회전값이 없으면 원본 바이트 그대로. 픽셀 크기는 유지 (위스키복춘 4032×3024 JPEG는 회전값 6). 결과는 `$BOTTLEMAP_DATA_DIR/prepared/`에 한 번 저장하고 모든 호출이 같은 파일을 쓴다. prepared 파일도 사진이므로 레포 밖에 둔다
- **media_resolution:** 기본값 (이미지 1장당 1120토큰). 이번 실험에서는 바꾸지 않는다
- **샘플링:** 사진당 5회 반복. temperature는 넘기지 않는다 (Gemini 3 문서가 기본값 1.0 유지를 강하게 권장, 1.0 미만은 반복·성능 저하 경고). 기록에는 1.0. seed는 설정하지 않는다 (반복 간 변동을 보는 것이 목적)
- **구조화 출력:** `response_format`으로 응답을 JSON 스키마에 강제

출력 스키마:

```json
{"items": [{"raw_name": "string", "price_krw": "integer|null", "pour_ml": "integer|null", "unit": "glass|bottle|null"}]}
```

## 스모크 테스트

본 실행 전 `data/fewshot/fewshot_78_kr_en_glass_bottle.png` 1장 × 조건 A 1회로 형식·스키마·가격 환산만 확인한다. 가이드라인 예시가 이 사진에서 왔으므로 이 결과는 채점하지 않는다. 프롬프트 수정은 이 단계에서만 한다.

스모크 테스트의 토큰 수로 135회 전체를 유료 등급으로 돌렸을 때의 예상 비용을 계산해 남긴다.

## 실행 규모

9장 × 5회 × 3조건 = 135회 호출.

## API 등급

이번 실험은 **무료 등급** 키로 진행한다. 무료 등급은 입력이 서비스 개선에 쓰일 수 있고 `store=False`로도 막을 수 없다. **업주 동의 범위 관련 확인 필요.** `ai/runs/ai_usage_log.md`와 summary에 명시한다.

## 기록

호출마다:
- 조건 ID(A/A2/B), 모델 ID, SDK 버전, API 종류(Interactions), store=False, temperature(1.0), thinking 수준, media_resolution
- prepared 파일 SHA-256, 프롬프트 버전
- 입력·출력·thought 토큰 수, 응답 시간(ms), 시각
- 출력 JSON, 원본 응답

## 분석

1. `eval_plan.md` 기준으로 사진별·조건별 지표 계산 (5회 평균과 최소~최대)
2. 오류를 유형별로 분류해 표로 정리하고 대표 사례를 남긴다
3. 판정 규칙 적용 → 결론 한 줄 (판정은 5회 평균)
4. 비용: 1장당 평균 토큰(입력·출력·thought)·응답 시간
5. 사진별 항목 정답률에서 빽빽한 사진(`007_bokchun_01`, 77항목)에 오류가 몰리면 "다음 실험 후보: media_resolution"으로 적는다. 이번 범위에서 해상도는 바꾸지 않는다
