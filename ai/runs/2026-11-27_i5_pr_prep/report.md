# I5-P19: OpenRouter 추출 PR 올리기 전 정리 (2026-11-27)

지시 문서: `../_outgoing/i5_p19_pr_prep_handoff.md`. 브랜치 `feature/i5-p19-openrouter-extraction`(작업 폴더 `swpp-p19-openrouter`). push하지 않았고 PR도 만들지 않았다.

<!-- SUMMARY -->

## A. 실행 기록 파일을 PR에서 빼기

### A.1 한 일

- 이 브랜치가 `ai/runs/` 아래에 새로 추가한 파일 396개 중 `.md`가 아닌 **388개**(`.json` 372, `.log` 14, `.jsonl` 1, `.txt` 1)를 `git rm --cached`로 추적에서만 뺐다. **디스크의 파일은 그대로 있다**(B.3이 이 파일을 읽었다).
- 남긴 것: `.md` 8개(보고서·사전 등록·표), `ai/eval/*.py`, 테스트.
- 뺀 파일을 읽는 테스트는 없었다. 새 테스트(`ai/eval/test_i5_fallback_ladder.py`, `backend/tests/test_*` 6개)는 모두 가짜 데이터를 쓴다. 그래서 `tests/fixtures`로 옮긴 것은 없다.
- 보고서 5개에서 뺀 파일을 가리키는 37곳에 "(기록은 커밋하지 않고 진우 PC에 보관)"을 붙였다. 표의 줄은 마지막 칸에, 문장은 끝에 붙였다. 사전 등록 문서(`2026-11-25_i5_fallback_ladder/preregistration.md`)의 2곳은 나중에 붙인 것임을 알 수 있게 "11/27 추가:"로 시작한다. 보고서의 숫자는 고치지 않았다.

| 보고서 | 붙인 곳 |
|---|---|
| `2026-11-21_i5_row_pairing/report.md` | 25 |
| `2026-11-25_i5_fallback_ladder/preregistration.md` | 2 |
| `2026-11-25_i5_p19_server_route/report.md` | 4 |
| `2026-11-26_i5_a2_p43/report.md` | 1 |
| `2026-11-26_i5_p19_followup/report.md` | 5 |

다른(이미 main에 있는) 실행 폴더를 가리키는 문장(`ai/runs/2026-11-17_p46/...`, `ai/runs/2026-10-14_e2e/...`)에는 붙이지 않았다. 그 기록은 커밋돼 있다.

### A.2 `.gitignore`

넣었다. 이 브랜치의 실행 폴더 5개와 오늘 폴더(`2026-11-27_i5_pr_prep`)에 대해 `.json`, `.jsonl`, `.log`, `.txt`를 무시한다. 폴더 이름을 하나씩 적었다.

- 이유: 이 폴더들의 기록은 디스크에 그대로 있으므로, `git add ai/runs`를 한 번만 해도 388개가 다시 올라간다.
- 와일드카드(`2026-11-2*_i5_*`)를 쓰지 않은 이유: 다른 브랜치의 실행 폴더(예: 메인 클론의 `2026-11-21_i5_not_whisky`, 아직 추적 안 된 기록)까지 무시하게 된다. 그 브랜치에서 기록을 커밋할지는 그 작업에서 정할 일이다.
- 이미 커밋된 다른 실행 폴더(`2026-11-17_p46` 등)는 영향이 없다. 확인: `git check-ignore`로 `2026-11-17_p46/match/x.json`은 무시되지 않고, `2026-11-26_i5_p19_followup/edge_guard.json`은 무시되고, `report.md`는 무시되지 않는다.

### A.3 확인

- `git diff --stat origin/main...HEAD -- ai/runs`: A 커밋 뒤 `.md` 8개만 남는다(아래 "확인 결과"의 명령 출력).
- 테스트는 A 전후가 같다.

| | A 전 | A 후 |
|---|---|---|
| AI (`pytest ai`) | 394 통과, 1 실패 | 394 통과, 1 실패 |
| 백엔드 (`backend`, `pytest`) | 1386 통과, 1940 건너뜀 | 1386 통과, 1940 건너뜀 |

- AI의 1 실패는 `test_p30_extract.py::test_reencoded_ocr_cache_without_provenance_stops`로, Windows의 경로 구분자 때문에 11/21부터 이 PC에서만 실패한다(이번 변경과 무관).
- 백엔드의 1940 건너뜀은 이 PC에 테스트 DB(`POSTGRES_TEST_DATABASE`)가 없어서 DB 테스트가 빠진 것이다. CI는 DB를 붙여 전부 돌린다. `test_pdf_extraction.py`의 5개는 테스트 이름에 PDF 바이트가 들어가 Windows 환경변수 길이 제한에 걸리므로 빼고 돌렸다(11/26 보고서 G.7과 같다). PDF 테스트에 필요한 `pypdfium2`는 11/26에 임시 폴더에 설치한 것을 `PYTHONPATH`로 썼다(venv는 건드리지 않았다).
