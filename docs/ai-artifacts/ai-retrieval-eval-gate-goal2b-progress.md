# AI Retrieval Eval Gate Goal 2B Progress

Date: 2026-05-12

## Scope

Implemented an eval-only gate that compares current source-level `SearchDocument` retrieval with lexical `DocumentChunk` retrieval from Goal 2A.

This goal did not change Copilot, Radar, search API, or production retrieval routing. No embeddings, reranking, OpenSearch implementation, broad scraping, autonomous agents, or AI generation behavior were added.

## Implemented

- Added `backend/services/retrieval/eval_gate.py`.
- Added manually labeled local retrieval eval fixtures with primary-user and foreign-user documents.
- Runs both retrievers on the same labeled cases:
  - `source_search_documents_v1`
  - `lexical_chunks_v1`
- Generates comparable per-case trace payloads for both strategies.
- Persists real `RetrievalTrace` rows for chunk retrieval during the eval run.
- Reports:
  - `recall_at_3`
  - `mrr`
  - `source_precision_at_3`
  - `citation_precision_at_3`
  - `empty_result_correctness`
  - empty-query behavior
  - unsupported-source behavior
  - user-isolation failures
- Added `scripts/collect_retrieval_eval_gate_artifact.py`.
- Generated `docs/ai-artifacts/generated/local-retrieval-eval-gate.json` locally. This generated file is ignored by git, matching the existing generated artifact convention.

## Follow-Up Review Fixes

After review, three eval-correctness issues were fixed:

- Document-level metrics now dedupe returned document keys while preserving rank, so chunk retrieval cannot inflate precision by returning multiple chunks from the same document.
- The source-level baseline now calls `PostgresSearchBackend` directly, making the eval gate deterministic and independent of `SEARCH_BACKEND`.
- Empty-case expected reasons now match and are asserted against per-case trace status.

## Changed Files

- `backend/services/retrieval/eval_gate.py`
- `scripts/collect_retrieval_eval_gate_artifact.py`
- `tests/test_retrieval_eval_gate.py`
- `docs/ai-artifacts/ai-retrieval-eval-gate-goal2b-progress.md`

Generated locally but ignored:

- `docs/ai-artifacts/generated/local-retrieval-eval-gate.json`

## Validation

- `pytest -q tests/test_retrieval_eval_gate.py` -> 3 passed.
- `python3 scripts/collect_retrieval_eval_gate_artifact.py --output docs/ai-artifacts/generated/local-retrieval-eval-gate.json` -> wrote the local retrieval eval gate artifact.
- `pytest -q tests/test_retrieval_eval_gate.py tests/test_retrieval_foundation.py tests/test_search_indexing.py tests/test_search_user_isolation.py tests/test_search_security.py tests/test_search_eval.py tests/test_copilot_api.py tests/test_copilot_security.py tests/test_copilot_abuse_controls.py tests/test_copilot_eval.py tests/test_copilot_schema.py` -> 37 passed.
- `RADAR_ENABLED=true RADAR_RESEARCH_ENABLED=true pytest -q tests/evals/research_radar/test_eval_harness.py tests/test_research_radar_graph.py tests/test_research_radar_user_context.py tests/test_research_radar_observability.py tests/test_opportunity_radar.py tests/test_radar_lineage.py tests/test_radar_quality_metrics.py tests/test_source_discovery.py` -> 47 passed, 1 dev Redis warning.
- `python3 -m compileall backend/services/retrieval/eval_gate.py scripts/collect_retrieval_eval_gate_artifact.py` -> passed.
- `git diff --check` -> no whitespace errors.

## Current Artifact Result

The local fixture gate currently shows both strategies tying on the small deterministic dataset:

- `source_search_documents_v1`: `recall_at_3=1.0`, `mrr=1.0`, `citation_precision_at_3=1.0`, `user_isolation_failures=0`.
- `lexical_chunks_v1`: `recall_at_3=1.0`, `mrr=1.0`, `citation_precision_at_3=1.0`, `user_isolation_failures=0`.
- Both strategies return empty results for empty queries and unsupported source filters.

Promotion recommendation in the artifact is `do_not_promote_chunk_retrieval_yet` because the fixture set is intentionally tiny and local-only.

## Limitations

- The eval cases are manually labeled local fixtures, not production traffic or held-out user data.
- Citation precision is measured as returned-source relevance because this goal does not generate model answers.
- Chunk retrieval traces are persisted during eval runs, but source-level traces are generated as artifact payloads only; production source-level search behavior remains unchanged.
- The evaluator only compares current portable lexical strategies. It does not evaluate embeddings, reranking, OpenSearch, or hybrid merge logic.
- The gate is suitable for regression and promotion discipline, not for production-quality retrieval claims.

## Next Recommended Goal

Goal 2C should expand the retrieval eval dataset with real sanitized cases and add an opt-in shadow comparison path for Copilot/Radar that records source-search and chunk-search traces side by side during normal use, without changing returned answers. Promotion should remain blocked until chunk retrieval improves recall or citation precision on the larger dataset without user-isolation or unsupported-answer regressions.
