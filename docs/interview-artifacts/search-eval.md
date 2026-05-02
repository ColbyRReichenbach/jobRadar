# Search Eval Report

- Generated at: `2026-05-02T19:35:12.491705+00:00`
- Dataset version: `search_eval_v1`
- Recommended strategy: `semantic_expansion_v1`
- Decision note: Use semantic_expansion_v1 for the next retrieval iteration because it has the strongest recall/MRR blend with the least additional ranking complexity among tied strategies.

## Dataset

- User-scoped documents: 7
- Queries: 6
- Queries with expected relevant documents: 5
- Stale indexed documents: 1
- Indexing fixture failures: 0

## Strategy Results

| Strategy | Status | Recall@3 | Recall@5 | MRR | nDCG@10 | Zero-result rate | p95 latency ms |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: |
| `title_keyword_v1` | completed | 0.8 | 0.8 | 0.8 | 0.8 | 0.3333 | 0.1022 |
| `full_text_keyword_v1` | completed | 0.8 | 0.8 | 0.8 | 0.8 | 0.3333 | 0.4326 |
| `semantic_expansion_v1` | completed | 1.0 | 1.0 | 1.0 | 1.0 | 0.1667 | 0.4926 |
| `hybrid_plus_boost_v1` | completed | 1.0 | 1.0 | 1.0 | 1.0 | 0.1667 | 0.4659 |
| `vector_embedding_v1` | skipped: Embeddings are not provisioned in CI; keep this explicit instead of pretending vector search ran. | - | - | - | - | - | - |

## Query-Level Evidence

| Query | Expected | Top returned |
| --- | --- | --- |
| `assistant search NLP role` | `application:tracebank-data-scientist`, `email:tracebank-interview`, `radar_report:erica-hiring-signals` | `email:tracebank-interview`, `radar_report:erica-hiring-signals`, `application:tracebank-data-scientist`, `contact:alex-morgan` |
| `erica chat voice hiring signals` | `radar_report:erica-hiring-signals` | `radar_report:erica-hiring-signals`, `email:tracebank-interview`, `contact:alex-morgan` |
| `recruiter alex interview` | `email:tracebank-interview`, `contact:alex-morgan` | `email:tracebank-interview`, `contact:alex-morgan` |
| `finops analyst cost dashboards` | `application:finops-analytics` | `application:finops-analytics` |
| `governed white box workflow` | `application:tracebank-data-scientist`, `radar_report:erica-hiring-signals` | `application:tracebank-data-scientist`, `radar_report:erica-hiring-signals`, `application:stale-platform-analytics` |
| `cobol aerospace firmware role` | none expected | none |

## Guardrails

- User isolation passed: `True`
- Foreign documents held out: 1
- Leaked foreign document keys: none

## Production Notes

- `vector_embedding_v1` is explicitly skipped until embeddings are provisioned.
- The semantic strategy is a deterministic expansion proxy, not a claim that vector search is live.
- Hybrid-plus-boost is tracked as a candidate, but tied quality is not enough to justify extra ranking complexity.
- The next production ranking change should require this eval plus live latency/cost telemetry from real traffic.
