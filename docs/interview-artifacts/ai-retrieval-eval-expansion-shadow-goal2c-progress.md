# Goal 2C Progress: Retrieval Eval Expansion and Shadow Tracing

## Status

Implemented the additive Goal 2C measurement layer. Chunk retrieval is still not promoted into Copilot or Radar answers/recommendations.

## Changed files

- `backend/services/retrieval/eval_gate.py`
  - Expanded the local sanitized eval gate to `retrieval_eval_gate_v2`.
  - Added manually labeled cases across applications, contacts, emails, Radar reports, empty query handling, unsupported source filtering, and a foreign-user-only isolation query.
  - Added explicit comparison fields for chunk-vs-source recall, MRR, citation/source precision, ties/improvements, user isolation, and promotion hold recommendation.
- `backend/services/retrieval/shadow.py`
  - Added an opt-in shadow comparison service that runs source-level `SearchDocument` retrieval and lexical `DocumentChunk` retrieval side by side.
  - Persists comparable `RetrievalTrace` rows for both retrievers on a `<surface>_shadow` surface.
- `backend/services/copilot/retrieval.py`
  - Added disabled-by-default Copilot shadow tracing behind `RETRIEVAL_SHADOW_ENABLED=true` or `COPILOT_RETRIEVAL_SHADOW_ENABLED=true`.
  - Returned Copilot citations still come from the existing source-level search path.
- `tests/test_retrieval_eval_gate.py`
  - Covers the expanded v2 dataset, comparable strategy cases, trace shape, user isolation, empty/unsupported behavior, and promotion recommendation fields.
- `tests/test_retrieval_shadow.py`
  - Covers generic Radar-surface shadow tracing, Copilot opt-in behavior preservation, comparable source/chunk traces, and user isolation.

## Local artifact

Generated the expanded local artifact at:

- `/private/tmp/retrieval-gate-goal2c.json`
- `/private/tmp/retrieval-gate-goal2c-review.json` after follow-up review hardening

Observed artifact summary:

- `document_count`: 10
- `case_count`: 10
- `labeled_case_count`: 7
- `recall_at_3`: source 1.0, chunk 1.0
- `citation_precision_at_3`: source 0.7857142857142857, chunk 0.7857142857142857
- `user_isolation_failures`: 0 for both strategies
- `chunk_recall_improved`: false
- `chunk_recall_tied`: true
- `recommended_strategy_for_promotion`: `none_hold_for_labeled_production_outcomes`

## Follow-up review fixes

- Source-level eval traces now store the same allowed `source_types` filter shape as chunk traces, so unsupported source filters are comparable instead of recording raw unsupported values.
- Chunk eval trace lookup now constrains by surface, normalized query, and retriever version instead of taking the latest trace for the user.
- Copilot shadow tracing now runs inside a nested transaction/savepoint so an optional shadow-trace failure cannot invalidate the main Copilot retrieval request.
- Added a regression test proving Copilot returns the same source-level context when the shadow comparison helper fails.

## Validation commands

- `pytest tests/test_retrieval_eval_gate.py tests/test_retrieval_shadow.py tests/test_retrieval_foundation.py`
  - Passed: 14 tests after follow-up review hardening.
- `python3 scripts/collect_retrieval_eval_gate_artifact.py --output /private/tmp/retrieval-gate-goal2c.json`
  - Passed: artifact generated locally.
- `python3 scripts/collect_retrieval_eval_gate_artifact.py --output /private/tmp/retrieval-gate-goal2c-review.json`
  - Passed: artifact regenerated locally after follow-up review hardening.
- `python3 -m compileall backend/services/retrieval/eval_gate.py backend/services/retrieval/shadow.py backend/services/copilot/retrieval.py scripts/collect_retrieval_eval_gate_artifact.py`
  - Passed.
- `git diff --check`
  - Passed.
- `env RADAR_ENABLED=true RADAR_RESEARCH_ENABLED=true pytest tests/test_search_indexing.py tests/test_search_security.py tests/test_search_eval.py tests/test_copilot_api.py tests/test_copilot_security.py tests/test_copilot_abuse_controls.py tests/test_research_radar_graph.py tests/test_radar_lineage.py tests/test_radar_quality_metrics.py tests/evals/research_radar/test_eval_harness.py tests/test_source_discovery.py`
  - Passed: 42 tests, 1 existing Redis warning.

Note: the same Radar route tests fail locally without the two explicit Radar flags because this workspace's `.env` has `RADAR_ENABLED=false`. With the flags enabled, existing Radar behavior passes.

## Limitations

- The expanded eval set is still small, sanitized, and manually labeled; it is not a production or held-out eval.
- Shadow source traces use returned result count as candidate count because the existing source-level search API does not expose total candidate count.
- Copilot is the only runtime path wired to the env-gated shadow comparison. The shadow service is generic and tested with `surface="radar"`, but Radar runtime behavior was intentionally not changed.
- Citation precision is measured as returned-source relevance; no answer generation or generated citation quality is evaluated.
- No embeddings, reranking, OpenSearch implementation, autonomous agents, broad scraping, or production routing changes were added.

## Recommended next goal

Pause and collect real labeled emails plus observed retrieval outcomes from shadow traces. Use those labels for a promotion decision before Goal 2D. Only proceed to embeddings, hybrid retrieval, or stronger Gmail ML after chunk retrieval shows a real recall or precision advantage without user-isolation regressions.
