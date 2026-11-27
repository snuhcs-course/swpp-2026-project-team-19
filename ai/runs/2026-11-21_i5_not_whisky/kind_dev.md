### ai/runs/2026-11-13_m3a_dev/rules_llm_r1.json

- set `dev`, catalog `service`, input `label`, lines 836, LLM targets 218, cache `ai/runs/2026-11-13_m3a_dev/cache_r1`

| gold | n | `non_whisky` | `whisky` | `unclear` | missing |
|---|---|---|---|---|---|
| non_whisky | 18 | 16 | 2 | 0 | 0 |
| whisky | 184 | 2 | 182 | 0 | 0 |
| unknown | 16 | 0 | 16 | 0 | 0 |

| variant | non-whisky flagged | whisky flagged (wrong) | unknown flagged |
|---|---|---|---|
| A: kind == non_whisky | 16 / 18 | 2 | 0 |
| B: A and no rule candidate | 16 / 18 | 0 | 0 |
| C: A and no candidate after embedding | 15 / 18 | 0 | 0 |

**non-whisky gold, LLM did not say non_whisky** (2)

- `011_미라보_08` **잭다니엘(Jack Daniel) 애플** | gold `non_whisky` | llm `whisky` | rule: ambiguous 1 [Jack Daniel's Old No.7]; after embedding: ambiguous 1 [Jack Daniel's Old No.7]
- `009_오드비_04` **잭다니엘 애플** | gold `non_whisky` | llm `whisky` | rule: unmatched 0; after embedding: ambiguous 2 [Jack Daniel's Old No.7 || Jack Daniel's Single Barrel 100 Proof]

**whisky gold, LLM said non_whisky** (2)

- `009_오드비_01` **크래프트브로스 독수리 오형제 1호** | gold `craft-bros-eagle-1` (Craft Bros Eagle Five Brothers No.1) | llm `non_whisky` | rule: ambiguous 1 [Craft Bros Eagle Five Brothers No.1]; after embedding: ambiguous 1 [Craft Bros Eagle Five Brothers No.1] (gold rank 1)
- `009_오드비_01` **크래프트브로스 독수리 오형제 3호** | gold `craft-bros-eagle-3` (Craft Bros Eagle Five Brothers No.3) | llm `non_whisky` | rule: ambiguous 1 [Craft Bros Eagle Five Brothers No.3]; after embedding: ambiguous 1 [Craft Bros Eagle Five Brothers No.3] (gold rank 1)

**whisky gold, LLM said unclear or gave no item** (0)

- none

**unknown gold, LLM said non_whisky** (0)

- none

**non-whisky gold, LLM said non_whisky (correct flags)** (16)

- `008_서로상_01` **헤네시vsop / Hennessy vsop** | gold `non_whisky` | llm `non_whisky` | rule: unmatched 0; after embedding: unmatched 0
- `008_서로상_01` **레미마틴vsop / Remy Martin vsop** | gold `non_whisky` | llm `non_whisky` | rule: unmatched 0; after embedding: unmatched 0
- `010_수이_04` **김과장 #2 (바베이도스 럼)** | gold `non_whisky` | llm `non_whisky` | rule: unmatched 0; after embedding: ambiguous 1 [Kim Gwajang #4 Clynelish]
- `010_수이_05` **헤네시 VSOP** | gold `non_whisky` | llm `non_whisky` | rule: unmatched 0; after embedding: unmatched 0
- `009_오드비_01` **샤토가호 밀레짐1984 알마냑** | gold `non_whisky` | llm `non_whisky` | rule: unmatched 0; after embedding: unmatched 0
- `009_오드비_01` **샤토가호 밀레짐1991 알마냑** | gold `non_whisky` | llm `non_whisky` | rule: unmatched 0; after embedding: unmatched 0
- `009_오드비_01` **샤토가호 밀레짐1995 알마냑** | gold `non_whisky` | llm `non_whisky` | rule: unmatched 0; after embedding: unmatched 0
- `009_오드비_01` **아르마냑 가호 그랑데카르** | gold `non_whisky` | llm `non_whisky` | rule: unmatched 0; after embedding: unmatched 0
- `009_오드비_01` **아르마냑 가호 브레이스오브가호** | gold `non_whisky` | llm `non_whisky` | rule: unmatched 0; after embedding: unmatched 0
- `009_오드비_01` **아르마냑 가호 에어메일** | gold `non_whisky` | llm `non_whisky` | rule: unmatched 0; after embedding: unmatched 0
- `009_오드비_01` **아르마냑 가호 옵시디언** | gold `non_whisky` | llm `non_whisky` | rule: unmatched 0; after embedding: unmatched 0
- `009_오드비_01` **아르마냑 가호프리미어 엠파이어** | gold `non_whisky` | llm `non_whisky` | rule: unmatched 0; after embedding: unmatched 0
- `009_오드비_09` **기네스 병** | gold `non_whisky` | llm `non_whisky` | rule: unmatched 0; after embedding: unmatched 0
- `009_오드비_09` **산미구엘 병** | gold `non_whisky` | llm `non_whisky` | rule: unmatched 0; after embedding: unmatched 0
- `009_오드비_09` **아사히 병** | gold `non_whisky` | llm `non_whisky` | rule: unmatched 0; after embedding: unmatched 0
- `009_오드비_09` **코로나 병 + 라임(선택)** | gold `non_whisky` | llm `non_whisky` | rule: unmatched 0; after embedding: unmatched 0

