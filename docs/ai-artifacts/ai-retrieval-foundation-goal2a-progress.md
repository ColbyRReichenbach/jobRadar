# AI Retrieval Foundation Goal 2A Progress

Date: 2026-05-12

## Scope

Implemented only the additive retrieval foundation from `ai-feature-production-spec-final.md`:

- Add user-owned knowledge document and chunk tables.
- Add retrieval trace persistence.
- Add deterministic, dependency-free chunking.
- Index existing source records into the new knowledge-document layer.
- Add portable lexical chunk retrieval.
- Generate a local retrieval eval artifact.

No embeddings, reranking, OpenSearch implementation, broad scraping, autonomous Radar agents, model training, or production-only dependencies were added.

## Implemented

- Added `UserKnowledgeDocument`, `DocumentChunk`, and `RetrievalTrace` models.
- Added Alembic migration `052_retrieval_foundation` with only new tables and indexes.
- Added `backend/services/retrieval/chunking.py` for deterministic whitespace-token chunking.
- Added `backend/services/retrieval/indexer.py` for source-to-knowledge-document upserts from existing `SearchDocumentInput` builders.
- Added `backend/services/retrieval/lexical.py` for user-scoped lexical chunk retrieval and trace persistence.
- Updated `backend/services/search/indexer.py` so existing `index_record` and `reindex_user_documents` also populate the new knowledge document/chunk layer while preserving `SearchDocument` behavior.
- Added `backend/services/retrieval/eval_artifacts.py` and `scripts/collect_retrieval_eval_artifact.py`.
- Generated `docs/ai-artifacts/generated/local-retrieval-eval.json`.

## Follow-Up Review Fixes

After review, three Goal 2A issues were fixed:

- Gmail sync reset now deletes email-derived `UserKnowledgeDocument` and `DocumentChunk` rows, and reports those counts in the reset payload.
- Retrieval traces now store stable result snapshots in `scores_json`, including chunk index, title, snippet, and content hash, so old traces remain useful after chunks are reindexed.
- Lexical retrieval filters are now applied for `source_id(s)`, `document_id(s)`, and `chunk_index/indices`; unsupported or invalid filters return no results and persist a trace status instead of silently ignoring filters.

Local migration status:

- `apptrail-local.db` is now at Alembic head `052_retrieval_foundation`.
- Because the local SQLite database had an empty `alembic_version` row and migration `051` uses SQLite-unsupported `ALTER TABLE` foreign-key operations, local migration required stamping the DB at `049_add_source_intelligence`, applying `050`, manually completing the remaining local SQLite columns/indexes from `051`, stamping `051_action_candidates_traces`, then applying `052` through Alembic.
- This was a local SQLite migration repair only; no production database migration was run.

## Changed Files

- `backend/models.py`
- `backend/alembic/versions/052_retrieval_foundation.py`
- `backend/services/search/indexer.py`
- `backend/services/retrieval/__init__.py`
- `backend/services/retrieval/chunking.py`
- `backend/services/retrieval/indexer.py`
- `backend/services/retrieval/lexical.py`
- `backend/services/retrieval/eval_artifacts.py`
- `scripts/collect_retrieval_eval_artifact.py`
- `tests/conftest.py`
- `tests/test_retrieval_foundation.py`
- `docs/ai-artifacts/generated/local-retrieval-eval.json`
- `docs/ai-artifacts/ai-retrieval-foundation-goal2a-progress.md`

## Validation

- `python3 scripts/collect_retrieval_eval_artifact.py --output docs/ai-artifacts/generated/local-retrieval-eval.json` -> wrote the local retrieval eval artifact.
- `pytest -q tests/test_retrieval_foundation.py` -> 7 passed.
- `pytest -q tests/test_search_indexing.py tests/test_search_user_isolation.py tests/test_search_security.py tests/test_search_eval.py tests/test_copilot_api.py tests/test_copilot_security.py tests/test_copilot_abuse_controls.py tests/test_copilot_eval.py tests/test_copilot_schema.py tests/test_retrieval_foundation.py tests/test_gmail_sync.py::test_gmail_sync_reset_clears_current_user_gmail_state` -> 35 passed.
- `RADAR_ENABLED=true RADAR_RESEARCH_ENABLED=true pytest -q tests/test_research_radar_graph.py tests/test_research_radar_user_context.py tests/test_research_radar_observability.py tests/test_opportunity_radar.py tests/test_radar_lineage.py tests/test_radar_quality_metrics.py tests/test_source_discovery.py` -> 46 passed, 1 dev Redis warning.
- `pytest -q tests/test_runtime_count_artifacts.py tests/test_action_foundation.py` -> 6 passed.
- `python3 -m compileall backend/main.py backend/models.py backend/services/retrieval backend/services/search/indexer.py scripts/collect_retrieval_eval_artifact.py` -> passed.
- `git diff --check` -> no whitespace errors.

## Limitations

- Current Copilot still uses source-level `SearchDocument` retrieval by default. Chunk retrieval is available as a foundation service but is not wired into Copilot answer orchestration in this goal.
- Chunk retrieval is lexical only. There are no embeddings, rerankers, OpenSearch queries, or hybrid retrieval.
- The local eval artifact uses tiny deterministic fixtures and is suitable for smoke validation only, not production quality claims.
- `index_record` now attempts knowledge-document indexing after the existing `SearchDocument` upsert. If the additive indexing path fails, it logs a warning and preserves the existing search-index behavior.
- No production migration was run. Apply Alembic migration `052_retrieval_foundation` before relying on the new retrieval tables outside local/test environments.

## Next Recommended Goal

Goal 2B should introduce a guarded retrieval integration path for Copilot or Radar behind an explicit flag: compare source-level search against chunk retrieval on real evals, persist retrieval traces for both strategies, and only promote chunk retrieval after citation precision and recall improve without increasing unsupported-answer risk.
