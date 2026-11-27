# I5-P19: Gemini API 직접 호출 확인 (stage 2·3)

다시 돌리는 명령 (레포 루트에서, API 10회): `python ai/eval/i5_direct_probe.py --out ai/runs/2026-11-27_direct_probe.md`

`ai/eval/i5_direct_probe.py`: 서버와 같은 호출 방식(google-genai SDK 클라이언트 `app.extraction.gemini.make_client`, Interactions API, thinking `medium`, `store=False`)으로 "ok 한 단어만 답해"를 모델마다 5번, 10초 간격(두 모델 번갈아)으로 보낸다. 재시도 없이 1회씩. 사진·OCR·OpenRouter는 쓰지 않는다. 키는 레포 `.env`의 `GEMINI_API_KEY`(무료 키)이고 출력하지 않는다. 실행할 때마다 아래 표에 줄이 이어 붙는다.

| 시각 (KST) | 모델 | HTTP | 걸린 시간 (초) | 답 / 오류 |
|---|---|---|---|---|
| 2026-11-27 13:33:45 | `gemini-3.8-flash` | 503 | 30.9 | InternalServerError: Error code: 503 - {'error': {'message': 'gemini-3.8-flash is currently experiencing high demand, spikes in demand are usually temporary. Pl |
| 2026-11-27 13:34:26 | `gemini-3.5-flash-lite` | 200 | 1.2 | '알겠습니다.' |
| 2026-11-27 13:34:37 | `gemini-3.8-flash` | 503 | 30.7 | InternalServerError: Error code: 503 - {'error': {'message': 'gemini-3.8-flash is currently experiencing high demand, spikes in demand are usually temporary. Pl |
| 2026-11-27 13:35:18 | `gemini-3.5-flash-lite` | 200 | 1.3 | '네' |
| 2026-11-27 13:35:29 | `gemini-3.8-flash` | 503 | 30.5 | InternalServerError: Error code: 503 - {'error': {'message': 'gemini-3.8-flash is currently experiencing high demand, spikes in demand are usually temporary. Pl |
| 2026-11-27 13:36:09 | `gemini-3.5-flash-lite` | 200 | 1.1 | '네' |
| 2026-11-27 13:36:20 | `gemini-3.8-flash` | 503 | 30.6 | InternalServerError: Error code: 503 - {'error': {'message': 'gemini-3.8-flash is currently experiencing high demand, spikes in demand are usually temporary. Pl |
| 2026-11-27 13:37:01 | `gemini-3.5-flash-lite` | 200 | 1.4 | '네' |
| 2026-11-27 13:37:12 | `gemini-3.8-flash` | 503 | 30.6 | InternalServerError: Error code: 503 - {'error': {'message': 'gemini-3.8-flash is currently experiencing high demand, spikes in demand are usually temporary. Pl |
| 2026-11-27 13:37:53 | `gemini-3.5-flash-lite` | 200 | 1.5 | '네.' |
