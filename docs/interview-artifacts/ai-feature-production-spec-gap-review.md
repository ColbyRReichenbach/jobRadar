# AI Feature Production Spec Gap Review

Date: 2026-05-11
Reviewed file: `docs/interview-artifacts/ai-feature-production-spec.md`
Review standard: code-verified only. I did not accept implementation claims without checking current repository files or local artifacts.

## Scope Of Product

JobRadar/AppTrail is not one AI feature. The current product scope spans:

- Job/application pipeline tracking from dashboard and browser extension captures.
- Gmail ingestion, classification, application linking, interview suggestions, and network-contact suggestions.
- Search documents used by dashboard search and Copilot retrieval.
- Copilot as a read-only, citation-constrained assistant over user-owned records.
- Resume parsing and tailoring.
- Radar/research workflows that fetch public sources, extract evidence, write reports, derive actions, and emit alerts.
- Source intelligence around job URLs, private links, career pages, ATS providers, and source verification.
- AI governance primitives: model-call ledger, safety decisions, experiments, promotion reports, model cards, feedback, and generated eval artifacts.

The spec's core thesis is directionally right: production AI should classify intent, normalize entities, dedupe, retrieve evidence, validate outputs, collect feedback, and make model/retriever changes auditable. The main problem is that several sections blur implemented state, aspirational architecture, and unverifiable local counts. That should be tightened before using this as an interview or planning artifact.

## Verification Summary

Verified as true:

- Gmail classification is a hybrid deterministic NLP system with optional LLM adjudication in `hybrid` mode. The default env example is `GMAIL_CLASSIFIER_MODE=hybrid_dry_run`, and dry-run does not use the model.
- Gmail preflight performs prompt-injection checks, redaction, prompt-size checks, and leak checks before adjudication.
- Gmail sync extracts raw URLs before body parsing and stores sanitized/source links after classification.
- Search is user-scoped and source-level, not chunk-level.
- The default search backend is SQL `LIKE` retrieval with hand scoring. OpenSearch is a placeholder adapter that raises unavailable errors.
- Copilot retrieves `SearchDocument` context, builds a retrieved-context-only prompt, validates returned citation IDs, stores assistant messages, and supports thumbs feedback.
- Resume tailoring sees only current resume text, job description, target company/role, and parsed skills. It has a skill-addition validator, but no bullet-level evidence grounding.
- Radar has a LangGraph-style pipeline with persisted steps, source/evidence/report persistence, LLM-call cost tracking, and a verifier node.
- Job/contact/interview duplicate checks exist, but they are endpoint-specific rather than unified behind one shared action-candidate layer.
- Eval file line counts in the spec match the checked files: 12 real email classifier examples, 150 synthetic email examples, 25 synthetic Gmail preflight cases, 4 real/50 synthetic Copilot questions, 8 real/198 synthetic Copilot router examples, 6 real/85 synthetic search queries, 6 real/120 synthetic Radar evidence examples, and 8 small real red-team rows plus 50 synthetic red-team rows.

Not verified:

- The "Recent local database snapshot" table in the spec is not verifiable from the current shell. `DATABASE_URL` and `NEON_DATABASE_URL` are not set. `apptrail.db` is an older minimal SQLite DB with 5 email events, 15 applications, and 3 contacts. `apptrail-local.db` has many product tables but zero rows for checked runtime tables and lacks several newer AI/search tables such as `search_documents`, `research_reports`, `ai_model_calls`, and `ai_safety_decisions`.
- The "real examples" in eval files are verified as file counts only. Their provenance, label quality, and held-out status were not independently verified.
- External reference URLs in the spec were not validated in this review.

## High-Priority Gaps And Fixes

### 1. Runtime Data Counts Are Presented As Fact But Are Not Reproducible

Gap:
The spec says the runtime counts are based on a recent local database snapshot, but the accessible local DBs do not reproduce those numbers. This weakens the credibility of the "Current Data And Evaluation Reality" section.

Fix:
Replace the static count table with a generated artifact that includes:

- Database source label, without exposing secrets.
- Git SHA.
- Migration version.
- Count query timestamp.
- Counts by table.
- A note when tables are absent or migrations are stale.

Until that exists, phrase the table as "unverified prior snapshot" or remove it.

Limitation:
Local DB counts are not production quality metrics. They can support interview storytelling, but they should not be used as evidence of production adoption or model quality.

### 2. The Spec Overstates Search Maturity

Gap:
The Search section correctly says current retrieval is simple, but the presence of an OpenSearch backend can read as more mature than it is. The adapter is explicitly a placeholder and raises unavailable errors when used without a concrete client. There is no `DocumentChunk`, embedding vector, BM25, reranker, query planner, or retrieval trace model.

Fix:
Rewrite current state as:

```text
Current search is a user-scoped, source-level lexical index over SearchDocument rows.
The OpenSearch adapter is a future integration placeholder, not a working production backend.
```

Implementation fixes:

- Add `DocumentChunk` or equivalent chunk table.
- Add chunking and embedding jobs.
- Add `RetrievalTrace` rows storing query, filters, candidates, scores, selected context, and downstream model call.
- Keep Postgres lexical retrieval as fallback.
- Only enable hybrid retrieval for Copilot/Radar after recall@k and citation precision improve on real evals.

Limitation:
With the current corpus and lexical scoring, Copilot and Radar cannot be expected to reliably retrieve the right evidence for broad or multi-hop questions.

### 3. Action Generation And Dedupe Are Still Fragmented

Gap:
The spec correctly proposes `ActionCandidate`, but the current app does not have that model/service. Alerts are created directly, `RecommendedAction` is Radar-oriented, and duplicate logic lives in separate job/contact/interview endpoint paths. `Alert` has no `dedupe_key`, `source_id`, `action_candidate_id`, suppression status, or duplicate-match metadata.

Current examples:

- Job duplicate check: hard URL match plus company/title/location soft match.
- Contact duplicate check: email hard match and name soft match.
- Interview suggestion accept: duplicate by scheduled time plus interviewer email.
- Radar alerts have a volume cap, but general Gmail/network alerts do not have a shared duplicate policy.

Fix:
Implement the shared action layer before adding more AI-generated suggestions:

```text
Classified signal
  -> ActionCandidate
  -> EntityNormalizer
  -> DedupeGate
  -> PolicyGate
  -> Alert or suppression
```

Required fields:

- `user_id`
- `source_type`
- `source_id`
- `action_type`
- `target_entity_type`
- `target_fingerprint`
- `dedupe_key`
- `status`
- `confidence`
- `requires_confirmation`
- `evidence_json`
- `duplicate_matches_json`
- `policy_decision`

Then link `Alert` and `RecommendedAction` to `ActionCandidate`.

Limitation:
Without this, "false positive action" risk remains higher than the classifier metrics imply. Correct labels can still create noisy or duplicate product behavior.

### 4. Gmail Current State Needs More Precise Wording

Gap:
The Gmail architecture summary is mostly accurate, but it should be sharper:

- Default `hybrid_dry_run` does not call the LLM; only `hybrid` allows preflight-gated adjudication when `ai_enabled` is true.
- The classifier returns route/subtype/decision metadata, but `EmailEvent` only persists legacy fields such as `classification`, `email_type`, `confidence`, `summary`, and `key_sentence`. Route/subtype are preserved in feedback rows and eval artifacts, not on the primary email event.
- Gmail sync extracts raw candidate URLs before classification, but the classifier candidate object only receives subject/body/sender/sender_email. Href-only URLs can be stored later, but they do not directly inform classifier features.
- Opportunity discovery and action review routes are intentionally not stored as `EmailEvent` rows yet.

Fix:

- Add `EmailClassificationTrace` or extend `EmailEvent` with route, subtype, route confidence, subtype confidence, classifier mode, decision path, threshold version, matched features, and status-update policy.
- Extend `EmailCandidate` with extracted URLs, link classifications, and maybe sanitized source-link metadata.
- Keep route-first classification as the framing, but state clearly that production promotion from dry-run to `hybrid` requires real-label review and cost/safety gates.

Limitation:
The current classifier is suitable for controlled beta routing and label collection. It is not yet a calibrated production classifier for automatic state mutation.

### 5. Copilot Is Grounded By Citation IDs, Not Claim-Level Support

Gap:
Copilot prompt rules say "Use only retrieved_context" and citation IDs are validated against retrieved documents. That prevents citing documents the user did not retrieve, but it does not prove each factual claim is supported by the cited snippet.

Fix:

- Add a route planner for `pipeline_question`, `email_question`, `contact_question`, `radar_question`, `resume_question`, and `unsupported`.
- Add claim extraction after model response.
- Check each claim against retrieved snippets or require abstention.
- Store unsupported-claim warnings and citation coverage in eval artifacts.
- Keep suggested actions read-only until the shared `ActionCandidate` layer exists.

Limitation:
Current Copilot should be described as a read-only, retrieval-constrained assistant with citation-ID validation, not a fully grounded assistant.

### 6. Resume Tailoring Roadmap Is Too Ambitious As Written

Gap:
The production target proposes repo zips, GitHub repo ingestion, project fact generation, evidence-grounded bullets, and bullet-level validation. That is the right long-term architecture, but it is too broad for near-term production without a separate ingestion and security plan.

Unrealistic as near-term:

- "Repo zip -> verified project facts -> tailored resume bullets" as one phase.
- Automatic extraction of "models/algorithms", "scale/performance/security decisions", and "user-facing functionality" from arbitrary repos.
- "No evidence, no claim" for every generated phrase without a structured evidence schema.

Fix:
Split into smaller releases:

1. Manual project facts: user enters project facts, links, and evidence snippets.
2. Resume/JD requirement parser and evidence matcher.
3. Bullet generator with evidence IDs.
4. Secret-scanned repo README/config ingestion only.
5. Optional deeper repo summarization after file allowlists, size limits, binary/vendor exclusions, and evals exist.

Limitation:
Current resume tailoring can reframe existing resume text and block some new skill hallucinations. It cannot reliably discover or verify project details that are not already in the resume or provided skills.

### 7. Radar Needs Source Registry Integration Before Broader Claims

Gap:
Radar has the strongest orchestration shape, but research search currently uses DuckDuckGo HTML search and public web fetching. Job-source adapters and `CompanyJobSource`/`JobPosting` models exist elsewhere in the codebase, but the research graph's search/fetch path is still broad-web first.

Fix:

- Make source bundles explicit inputs to Radar planning.
- Query verified `CompanyJobSource` and `JobPosting` records before public web.
- Store source trust tier and freshness on source/evidence records.
- Add deterministic entity-match/freshness/trust scoring before LLM report writing.
- Upgrade verification from report-level status to claim-level support checks.

Limitation:
Public web retrieval is inherently brittle. Radar reports should stay "needs review" or low-confidence when evidence is sparse, stale, or from broad search fallbacks.

### 8. Governance Exists, But Enforcement Is Not Automatic Yet

Gap:
The spec accurately lists governance primitives and scripts, but it should not imply every AI-relevant change is automatically governed. There is a feature artifact suite and model/promotion tables, but prompt/model/retriever changes are not forced through one CI/release gate.

Fix:

- Add CI jobs for deterministic evals on changed AI surfaces.
- Require generated artifact bundle paths in PR descriptions for AI-affecting changes.
- Track prompt hashes and retriever versions in generated artifacts.
- Store eval run config, metrics, predictions, regressions, and decision JSON under `evals/runs/`.
- Make promotion reports explicitly reference dataset versions and git SHA.

Limitation:
Until enforcement exists, the governance system is a strong scaffold, not a guaranteed production control.

## Logic Gaps In The Spec

### "Every AI-Generated Claim Should Be Traceable" Needs Scope Boundaries

The principle is right for factual claims, user state changes, skill claims, resume bullets, recommendations, and research findings. It is unrealistic for every stylistic sentence, summary transition, or harmless UI phrase.

Fix:
Define claim types:

- Must cite: factual, career-history, job-status, contact, salary, company, research, and action-triggering claims.
- Should cite when possible: summaries and recommendations.
- Need not cite: UI copy, formatting text, neutral acknowledgements, and purely transformative edits with no new facts.

### "Deep Supervised NLP Or Fine-Tuning" Is Correctly Deprioritized, But The Alternative Needs Label Criteria

The spec says deterministic rules then TF-IDF/logistic regression. That is reasonable, but it needs explicit promotion criteria.

Fix:
Before training or promoting a baseline, require:

- Real labels stratified by route/subtype.
- Separate train/validation/test or time-based split.
- Reported confidence calibration.
- False positive action rate, not only classification accuracy.
- Real-data metrics separated from synthetic metrics.

### Current Evals Are Useful But Too Small For Production Claims

The line counts are real, but the real eval sets are tiny. Six search queries, six Radar evidence examples, four Copilot questions, and twelve email classifier rows are regression smoke tests, not production confidence.

Fix:
Rename current real eval sets as "seed real evals" and call synthetic sets "coverage/regression evals." Do not use them as proof of production accuracy.

### Product Risk Is Underweighted Relative To Model Risk

The spec talks about classifier/generator correctness, but the highest product risks are:

- Duplicate or noisy notifications.
- Cross-user data exposure.
- Private URL/token leakage.
- Auto-mutating job state incorrectly.
- Resume hallucinations that affect job applications.
- Radar reports that look authoritative despite weak public evidence.

Fix:
Make side-effect policy and duplicate suppression first-class metrics alongside model metrics.

## Recommended Spec Edits

Replace or add these statements:

- Replace "Recent local database snapshot" with "Prior local snapshot, not reproduced in this review" unless a generated count artifact is attached.
- State "OpenSearch adapter is a placeholder; production search is not implemented."
- State "Copilot validates citation IDs, not semantic support for each claim."
- State "Gmail route/subtype metadata is returned and used in eval/feedback, but not fully persisted on `EmailEvent`."
- State "Default Gmail mode is `hybrid_dry_run`; production LLM adjudication requires setting `GMAIL_CLASSIFIER_MODE=hybrid`."
- State "Repo ingestion is a later controlled ingestion project, not a near-term resume-tailoring dependency."
- State "ActionCandidate and DocumentChunk are proposed models; they do not exist in current code."

## Promotion Checkpoints And Radar Architecture

The spec should add explicit checkpoints for when to switch from simple, controlled systems to more sophisticated AI systems. A production AI roadmap should not say "move to ML" or "move to agents" generically. It should define the data, eval, risk, and product thresholds that justify each switch.

### Gmail Classification Checkpoints

Gmail should progress in stages:

```text
rules and route-first classifier
  -> real-label audit
  -> TF-IDF/logistic regression shadow lane
  -> calibrated route/subtype baseline
  -> optional heavier model only if simpler models fail on measured cases
```

Recommended checkpoint logic:

| Stage | When to use | Switch criteria |
| --- | --- | --- |
| Deterministic route-first classifier | Current cold-start mode. | Keep until real labels cover the main routes and failure modes. |
| TF-IDF/logistic regression shadow model | Once there are roughly 300-500 real labeled emails and at least 30-50 examples for major routes. | Promote only if held-out real route accuracy improves without increasing high-risk false positives. |
| Calibrated route/subtype model | Once real labels support confidence calibration by route. | Use confidence bands for route, subtype, and review queues separately. |
| More sophisticated model or fine-tune | Only after simpler baselines plateau and there are thousands of real labeled examples. | Require documented failure modes, cost/latency budget, safety review, and promotion report. |

Promotion should be based on real held-out data, not synthetic-only results. Synthetic cases are useful for regression coverage and safety tests, but they should not justify production model promotion by themselves.

The most important distinction is:

```text
classification confidence != action confidence
```

Even if a classifier is promoted, action creation still needs entity resolution, evidence checks, dedupe, and policy gating. The switch from "label email" to "suggest or mutate user state" should have a separate threshold.

### Radar Source Architecture

Radar is harder than Gmail because there is no naturally bounded inbox corpus and public web evidence is noisy. The right architecture is not "scrape the web and run RAG over whatever was found." The right architecture is source-registry first:

```text
user research profile
  -> source bundle selector
  -> verified company/job sources first
  -> structured provider adapters and known endpoints
  -> persisted source/job/evidence records
  -> chunked retrieval over trusted evidence
  -> report generation with citations
  -> claim-level verification
  -> ActionCandidate proposals
  -> dedupe and policy gate
```

The codebase already has useful primitives for this direction: `CompanyJobSource`, `JobPosting`, `SourceDiscoveryEvent`, `ApplicationSourceLink`, source verification runs, and adapters for several common job-source providers. The gap is that Radar's research graph still behaves more like broad public-web research, while job-source intelligence is a parallel subsystem. Production Radar should merge these paths.

Recommended source priority:

| Priority | Source type | Use |
| --- | --- | --- |
| 1 | User-owned records | Applications, captured jobs, Gmail events, contacts, saved companies, company visits. |
| 2 | Verified source registry | `CompanyJobSource` rows with verified public access and recent verification. |
| 3 | Provider adapters | Greenhouse, Lever, Ashby, Workable, SmartRecruiters, Workday, structured data, where public access works. |
| 4 | Persisted `JobPosting` records | Structured job evidence with dedupe keys, descriptions, dates, and canonical URLs. |
| 5 | Structured public pages | JSON-LD `JobPosting`, public career pages, engineering blogs, company pages. |
| 6 | Search provider fallback | Used only when direct and verified sources do not answer the research need. |
| 7 | Agentic browsing | Last resort with domain allowlists, budgets, robots/terms checks, and evidence quality gates. |

This makes Radar a source-quality and evidence-retrieval problem first, and an agentic browsing problem second.

### Job Site Limitations

Job sites are structurally difficult:

- Many sites hide provider identifiers behind redirects or client-side routing.
- Some require several clicks or filters before a useful job page appears.
- Some listings are rendered client-side and do not expose stable structured data.
- Some sources rate-limit or block automated access.
- Some require credentialed access or violate acceptable terms for automated scraping.
- Search results are unstable and can return stale, duplicate, or irrelevant pages.
- A broad crawler cannot reliably prove that a company has no matching jobs.

The system should represent these cases explicitly instead of treating them as generic fetch failures.

Recommended source statuses:

- `verified`
- `pending`
- `needs_review`
- `stale`
- `blocked`
- `credentialed_required`
- `robots_disallowed`
- `rate_limited`
- `unsupported_provider`
- `company_identity_conflict`

Radar and job search should surface degraded states honestly. For example, "verified Greenhouse source returned no matching roles today" is very different from "broad search failed to find jobs."

### What Engineering Can Solve

Solvable controls:

- Provider-specific source parsing instead of generic scraping.
- Verified source registry with source trust, freshness, robots/terms risk, and failure reason.
- Scheduled source verification and stale-source demotion.
- Job posting persistence with provider job ID, canonical URL, title, company, location, description hash, and active status.
- Dedupe across extension captures, Gmail links, Radar findings, and persisted postings.
- Source-bundle selection per Radar profile.
- Retrieval traces for every Radar report and Copilot answer.
- Claim-level citation coverage and unsupported-claim metrics.
- Agentic browser fallback only for allowlisted domains and bounded tasks.
- Human review queues for source conflicts and high-value uncertain findings.

Not fully solvable:

- Complete coverage of every job site.
- Reliable scraping of credentialed or anti-automation systems.
- Proving absence of jobs from public web evidence.
- Perfect extraction from arbitrary client-rendered career pages.
- Claim-level truth guarantees when source evidence is stale, contradictory, or incomplete.

Production Radar should therefore make confidence and source coverage visible. It should avoid authoritative reports when evidence is weak.

## Practical Implementation Order

1. Make counts/eval provenance reproducible.
2. Persist classifier traces on Gmail events.
3. Implement `ActionCandidate` and shared `DedupeGate`.
4. Add alert dedupe keys and link alerts to action candidates.
5. Add document chunks and retrieval traces before embeddings.
6. Improve Copilot router and claim-level citation checks.
7. Move Radar to source-bundle-first retrieval using existing job-source records.
8. Add manual project facts before any repo zip ingestion.
9. Enforce eval artifacts in CI/release workflow.
10. Grow real labels and feedback loops before claiming calibrated production ML.

## Bottom Line

The spec has a strong production AI architecture, but it should be more explicit about what is already implemented versus what is proposed. The biggest overclaims are reproducible local counts, search backend maturity, action/dedupe centralization, claim-level grounding, and near-term resume repo ingestion. The safest refreshed framing is:

```text
Current system: strong beta scaffold with deterministic Gmail NLP, source-level lexical retrieval, read-only Copilot, early Radar graph orchestration, and governance primitives.

Production target: shared action candidates, entity normalization, dedupe gates, chunked hybrid retrieval, claim-level validation, reproducible eval artifacts, and real feedback-driven promotion.
```
