# AI Feature Production Spec

Date: 2026-05-11
System: AppTrail / JobRadar AI platform
Evidence status: Current-state notes are based on code inspection and local data counts. Production target sections are proposed architecture.

## Purpose

This spec explains how the current AI features work today and how to evolve them into production-grade AI systems. It is written for interview preparation and implementation planning.

The core production thesis:

```text
User or system signal
  -> classify intent
  -> normalize entities
  -> dedupe against user state
  -> retrieve grounded evidence
  -> generate or recommend only from evidence
  -> validate output
  -> write model/eval/governance artifacts
  -> collect feedback
  -> feed labels/evals back into improvement loops
```

This matters because the app spans Gmail, browser extension job capture, Copilot, Radar research, resume tailoring, and action notifications. Those features should not behave like independent AI demos. They need shared retrieval, entity resolution, dedupe, safety, evaluation, and feedback infrastructure.

## Current Data And Evaluation Reality

### Local Runtime Counts

Recent local database snapshot:

| Table | Count |
| --- | ---: |
| `EmailEvent` | 179 |
| `SearchDocument` | 191 |
| `Alert` | 106 |
| `RecommendedAction` | 18 |
| `ResearchRun` | 14 |
| `ResearchReport` | 10 |
| `ResearchEvidenceItem` | 23 |
| `ResearchSourceItem` | 46 |
| `AiModelCall` | 71 |
| `AiSafetyDecision` | 135 |
| `UserProfile` | 0 |
| `ResumeDraft` | 0 |
| `EmailFeedback` | 0 |
| `CopilotFeedback` | 0 |
| `ResearchFeedback` | 0 |

Interpretation:

- Gmail and Radar have the most runtime evidence.
- Resume tailoring is implemented but has no local profile/draft usage in this snapshot.
- Feedback loops exist structurally, but feedback data is not populated yet.
- Search has a small corpus and should be treated as an early retrieval layer, not a mature RAG index.

### Eval And Label Counts

Current eval files:

| Area | Real examples | Synthetic examples |
| --- | ---: | ---: |
| Email classifier | 12 | 150 |
| Gmail LLM preflight | 0 | 25 |
| Copilot questions | 4 | 50 |
| Copilot router | 8 | 198 |
| Search | 6 | 85 |
| Radar evidence quality | 6 | 120 |
| Red-team safety | 8 total real across small files | 50 synthetic |

Audit/label queues:

- `audit/real_email_audit.csv`: 96 rows including header.
- `audit/synthetic_email_audit_100.csv`: 101 rows including header.
- Gmail combined label queues: roughly 161 to 290 rows depending on file.
- Targeted unlabeled queue: 179 rows including header.

Interpretation:

- The app does not yet have enough real labeled data for deep supervised NLP or transformer fine-tuning.
- The right near-term ML progression is deterministic rules plus real-label audit, then TF-IDF/logistic regression or linear models as baselines, then calibrated model comparison.
- Synthetic data is useful for regression and safety coverage, but production promotion should depend on real held-out data.

## Shared Production Architecture

### Shared Components

The production-grade platform should share these components across features:

| Component | Responsibility |
| --- | --- |
| Intent classifier | Classify user/system input into route, subtype, action intent, and confidence. |
| Entity normalizer | Canonicalize job URLs, company names/domains, contacts, emails, interviews, projects, skills, and source docs. |
| Dedupe gate | Prevent repeated jobs, contacts, interviews, alerts, recommendations, and reports. |
| Evidence store | Persist source documents, chunks, citations, metadata, provenance, and ownership. |
| Hybrid retriever | Combine keyword search, vector search, metadata filters, and reranking. |
| Generation layer | Produce structured outputs with evidence IDs and validation constraints. |
| Validation layer | Reject unsupported claims, malformed actions, unsafe output, and cross-user leakage. |
| Feedback layer | Capture accept, dismiss, thumbs, corrections, edits, merge decisions, and labels. |
| Eval layer | Run offline and online evals before model/prompt/retriever promotion. |
| Artifact registry | Persist every eval run, model/prompt change, dataset version, and promotion decision in one reproducible place. |
| Narrative changelog layer | Capture the human decision trail: what failed, what was observed, why the architecture changed, and what the next eval proved. |
| Prompt/model registry | Track prompt versions, model cards, approved uses, limits, rollback plans, and review cadence. |
| Observability layer | Track costs, latency, prompt version, model, fallback, safety decisions, and quality metrics. |

### Shared Evidence Model

Every AI-generated claim should be traceable to evidence.

Proposed source types:

- `email_event`
- `application`
- `contact`
- `resume`
- `user_profile`
- `project_repo`
- `project_fact`
- `job_description`
- `radar_source`
- `radar_report`
- `calendar_event`
- `copilot_message`

Proposed document model:

```text
UserKnowledgeDocument
  id
  user_id
  source_type
  source_id
  title
  body
  metadata_json
  provenance_json
  visibility
  content_hash
  created_at
  updated_at

DocumentChunk
  id
  document_id
  user_id
  chunk_text
  chunk_index
  token_count
  metadata_json
  embedding_vector
  content_hash
```

The existing `SearchDocument` table is a useful starting point, but production RAG needs chunk-level retrieval and stronger provenance.

### Shared Dedupe Model

Dedupe must happen before action notifications.

Proposed flow:

```text
classified signal
  -> proposed ActionCandidate
  -> normalize target entity
  -> hard duplicate check
  -> soft duplicate check
  -> suppress, link existing, ask review, or create action
  -> create notification only when useful
```

Proposed action fields:

```text
ActionCandidate
  id
  user_id
  source_type
  source_id
  action_type
  target_entity_type
  target_entity_id
  target_fingerprint
  dedupe_key
  duplicate_type
  duplicate_matches_json
  status
  confidence
  requires_confirmation
  evidence_json
  created_at
  updated_at
```

Recommended statuses:

- `proposed`
- `suppressed_duplicate`
- `linked_existing`
- `pending_review`
- `accepted`
- `dismissed`
- `expired`
- `failed_validation`

Stable dedupe key format:

```text
user_id + action_type + target_entity_type + target_fingerprint
```

Examples:

```text
user123:add_job:job_url_hash:abc
user123:add_contact:email:jane@company.com
user123:add_interview:application_id+datetime+interviewer_email
user123:radar_report:profile_id+topic_hash+week_bucket
```

## Feature 1: Gmail Classification

### Current State

Primary files:

- `backend/services/email_classifier.py`
- `backend/services/gmail_intelligence/orchestrator.py`
- `backend/services/gmail_intelligence/feature_extractor.py`
- `backend/services/gmail_intelligence/scorer.py`
- `backend/services/gmail_intelligence/classifier.py`
- `backend/services/gmail_intelligence/preflight.py`
- `backend/services/gmail_intelligence/adjudicator.py`

Current flow:

```text
Gmail message
  -> normalize email
  -> extract lexical/sender/link/recruiting features
  -> score route and subtype
  -> deterministic classification
  -> optional LLM adjudication only for ambiguous cases
  -> persist EmailEvent if job-relevant
  -> index SearchDocument
  -> create alerts / follow-on suggestions
```

The classifier is not currently a vectorizer-based or supervised ML model. It is a hybrid deterministic NLP system with optional LLM adjudication. The default mode is controlled by `GMAIL_CLASSIFIER_MODE`, with modes such as `hybrid_dry_run`, `hybrid`, and `hybrid_no_model`.

Current strengths:

- Strong cold-start strategy with no dependency on large labeled data.
- Explainable feature and scoring path.
- LLM calls are gated by ambiguity and preflight.
- Prompt-injection and privacy checks exist before LLM adjudication.
- Gmail audit and label queues exist.
- Stored events are indexed for search/Copilot.

Current gaps:

- Real label volume is still small.
- Route/subtype thresholds are hand-tuned and need calibration.
- Some rich signals, especially raw candidate URLs, should be passed more directly into the hybrid candidate object.
- False-positive actions are more dangerous than false-positive labels, so downstream action gating must be stricter than classification gating.
- There is no trained TF-IDF/logistic regression baseline yet.

### Production Target

Production Gmail should have four layers:

```text
Layer 1: deterministic high-precision filters
Layer 2: route/subtype classifier
Layer 3: ambiguous-case adjudicator
Layer 4: action candidate extractor
```

Near-term ML progression:

1. Continue collecting real labels from Gmail audit queues.
2. Build a TF-IDF plus logistic regression baseline for route and subtype once labels are adequate.
3. Compare deterministic, TF-IDF, and LLM adjudication in shadow mode.
4. Calibrate confidence thresholds by route.
5. Promote only when real held-out precision/recall improves without increasing unsafe actions.

Production requirements:

- Separate classification confidence from action confidence.
- Persist route, subtype, feature hits, score components, and decision path.
- Track model/prompt/threshold versions.
- Use active learning queues for low-confidence or high-impact messages.
- Never auto-mutate application state unless status update policy and evidence pass strict checks.

### Gmail Evals

Offline metrics:

- Route accuracy.
- Subtype accuracy.
- Precision/recall by class.
- False positive job-relevant rate.
- False negative interview/action-item rate.
- Company extraction accuracy.
- Sender role accuracy.
- Status update allowed precision.
- LLM call rate and cost per 1,000 emails.

Online metrics:

- User correction rate.
- Dismissed alert rate.
- Accepted action rate.
- Time-to-review for suggested interviews or contacts.
- Repeated notification rate per sender/thread/job.

## Feature 2: Action Notifications After Classification

### Current State

Primary files:

- `backend/main.py`
- `backend/services/alerts.py`
- `backend/services/calendar_sync.py`
- `backend/services/email_matcher.py`
- `backend/tasks/poll_gmail.py`

Current behavior:

- Gmail sync creates `EmailEvent`.
- Relevant messages can create alerts.
- Conversation messages can create network-contact alerts.
- Interview request emails appear in `/api/interview-suggestions`.
- Accepted interview suggestions create `Interview` rows.
- Calendar sync can identify interview-like calendar events.

Current strengths:

- Useful user workflow already exists.
- Interview suggestions require user confirmation.
- Contact suggestions are not directly inserted without review.
- Duplicate interview detection exists for scheduled time plus interviewer email.

Current gaps:

- Actions are not yet represented as a unified first-class object.
- Dedupe is scattered across jobs, contacts, links, interviews, and alerts.
- The same job can enter from extension, Gmail, Radar, or Copilot unless each path consistently calls shared dedupe.
- Notifications can be correct individually but noisy collectively.
- Action extraction is mostly deterministic and endpoint-specific.

### Production Target

Action generation should be centralized:

```text
EmailEvent / ExtensionEvent / RadarFinding / CopilotRequest
  -> ActionCandidateExtractor
  -> EntityNormalizer
  -> DedupeGate
  -> PolicyGate
  -> NotificationOrSuppression
```

Action types:

- `add_job_to_pipeline`
- `link_email_to_application`
- `add_network_contact`
- `link_email_to_contact`
- `schedule_interview`
- `follow_up_with_contact`
- `update_application_status`
- `review_radar_opportunity`
- `tailor_resume_for_application`

Policy gates:

- Read-only suggestion vs mutation.
- Requires user confirmation.
- Requires stronger evidence.
- Can be silently linked to existing entity.
- Can be suppressed as duplicate.

### Dedupe Rules

Job actions:

| Match type | Signals | Behavior |
| --- | --- | --- |
| Hard duplicate | Canonical job URL hash, provider job ID, existing `UserApplicationLink` | Suppress "new job"; optionally link source to existing application. |
| Strong soft duplicate | Company domain + normalized role title + location | Show "possible duplicate" review. |
| Weak soft duplicate | Company name + similar title + similar JD text | Low-priority review or no notification if confidence is low. |
| No duplicate | No credible match | Create "add job to pipeline" action. |

Network actions:

| Match type | Signals | Behavior |
| --- | --- | --- |
| Hard duplicate | Normalized email, LinkedIn URL | Suppress "add contact"; link email to existing contact. |
| Strong soft duplicate | Name + company/domain | Show "possible existing contact" review. |
| Weak soft duplicate | Name + same thread/company | Low-priority review. |
| No duplicate | No credible match | Create "add to network" action. |

Interview actions:

| Match type | Signals | Behavior |
| --- | --- | --- |
| Hard duplicate | Same application + datetime + interviewer email | Suppress duplicate. |
| Strong soft duplicate | Same datetime + same company/interviewer name | Review. |
| No duplicate | New confirmed schedule details | Suggest calendar/interview creation. |

### Action Evals

Offline metrics:

- Exact entity match accuracy.
- Duplicate suppression precision.
- False suppression rate.
- Required-field extraction accuracy.
- Side-effect policy accuracy.

Online metrics:

- Accept rate by action type.
- Dismiss rate by action type.
- "Already exists" user complaint rate.
- Repeated notification count per entity per week.
- Merge/keep-separate decision rate.

## Feature 3: Search And Retrieval Layer

### Current State

Primary files:

- `backend/services/search/documents.py`
- `backend/services/search/indexer.py`
- `backend/services/search/backends/postgres.py`
- `backend/services/search/backends/opensearch.py`

Current flow:

```text
source record
  -> SearchDocumentInput
  -> normalize title/subtitle/body/keywords into search_text
  -> Postgres LIKE search by query terms
  -> manual scoring by title/subtitle/body hits
```

Current strengths:

- User-scoped search.
- Simple portable SQL backend works locally.
- Email documents intentionally avoid indexing unlimited raw body text.
- Search powers Copilot fallback and retrieval.

Current gaps:

- No production vectorizer or embedding search.
- No BM25 ranking.
- No chunking.
- No reranking.
- No query rewriting or intent-aware retrieval.
- No source trust/freshness scoring.
- No retrieval eval gate tied to user-facing quality.

### Production Target

Use hybrid retrieval:

```text
query
  -> intent/query decomposition
  -> metadata filters by user/source/date/entity
  -> keyword retrieval
  -> vector retrieval
  -> merge candidates
  -> rerank
  -> evidence packaging
```

Retriever requirements:

- Strict `user_id` filtering.
- Source-type filtering.
- Chunk-level retrieval.
- Metadata filters for company, role, date, application, contact, project, and source freshness.
- Hybrid score that combines lexical match, vector similarity, recency, trust, and entity match.
- Reranker for top candidates.
- Retrieval traces stored for eval/debugging.

Recommended implementation path:

1. Keep Postgres lexical search as fallback.
2. Add `DocumentChunk` and chunking.
3. Add embeddings for chunks.
4. Add BM25 or OpenSearch lexical scoring.
5. Add hybrid merge.
6. Add reranking.
7. Add retrieval evals before using retrieval for high-risk generation.

### Search Evals

Metrics:

- Recall@k.
- MRR.
- nDCG.
- Citation precision.
- Source coverage by feature.
- Query latency.
- Empty-result correctness.
- Cross-user isolation tests.

## Feature 4: Copilot

### Current State

Primary files:

- `backend/routes/copilot.py`
- `backend/services/copilot/orchestrator.py`
- `backend/services/copilot/retrieval.py`
- `backend/services/copilot/guardrails.py`
- `backend/services/copilot/citations.py`

Current flow:

```text
user question
  -> validate/rate-limit/budget
  -> retrieve SearchDocument context
  -> model answers using retrieved_context only
  -> validate citations
  -> store conversation messages
  -> collect thumbs feedback
```

Current strengths:

- User-scoped context.
- Read-only prompt contract.
- Citation validation.
- Search fallback when model is unavailable or invalid.
- Feedback persistence exists.
- Suggested actions are sanitized.

Current gaps:

- Retrieval quality is limited by current lexical search.
- Copilot is not yet a strong routed assistant with tool/action planning.
- It does not have claim-level support validation beyond citation IDs.
- Feedback count is currently zero locally.
- It should not mutate state until action policy and dedupe are centralized.

### Production Target

Copilot should be a routed, evidence-grounded assistant:

```text
message
  -> intent router
  -> retrieval plan
  -> source-specific retriever
  -> answer generator
  -> citation validator
  -> optional ActionCandidate proposal
  -> user confirmation
```

Copilot routes:

- `pipeline_question`
- `email_question`
- `contact_question`
- `radar_question`
- `resume_question`
- `job_search_question`
- `action_request`
- `unsupported_or_unsafe`

Production rules:

- Default to read-only.
- Generate action candidates, not direct mutations.
- Cite evidence IDs for factual claims.
- Abstain when evidence is insufficient.
- Never expose data across users.
- Do not treat untrusted retrieved text as instructions.

### Copilot Evals

Metrics:

- Router accuracy.
- Retrieval recall@k.
- Groundedness.
- Citation validity.
- Unsupported claim rate.
- Abstention quality.
- Safety refusal correctness.
- Feedback reward trend.

## Feature 5: Resume Tailoring

### Current State

Primary files:

- `backend/services/resume_parser.py`
- `backend/services/resume_tailor.py`
- `backend/main.py`
- `backend/models.py`

Current flow:

```text
resume text/PDF
  -> parse into UserProfile fields
  -> application job description
  -> LLM rewrites resume from original resume + JD
  -> reject if unverified new tech skills appear
  -> store ResumeDraft
```

Current strengths:

- Clear privacy/consent boundary.
- Resume parser has deterministic fallback extraction.
- Tailor prompt explicitly forbids invented experience.
- Output validation checks for unverified skill additions.
- Draft persistence exists.

Current gaps:

- The model only sees the current resume and job description.
- It cannot know the real details of projects unless the user already wrote them in the resume.
- It cannot reliably convert the same project from a data engineering angle to a data science angle without more evidence.
- There is no project/repo ingestion.
- There is no user knowledge profile with searchable evidence.
- There is no bullet-level evidence citation.
- There is no resume-specific hallucination eval.

### Production Target

The proposed architecture should be implemented as evidence-grounded resume tailoring:

```text
user uploads profile artifacts
  -> parse and normalize artifacts
  -> create searchable user knowledge documents
  -> job description parser classifies target role
  -> retrieve relevant evidence
  -> draft tailored resume sections
  -> validate every claim against evidence
  -> produce keyword/evidence coverage report
  -> user edits become feedback
```

Supported uploads:

- Existing resume.
- Work experience notes.
- Project descriptions.
- Repo zip.
- GitHub repository URL.
- Portfolio links.
- Certifications.
- Publications.
- Case studies.

Repo zip ingestion:

```text
zip upload
  -> file size/type checks
  -> secret scan
  -> ignore vendor/build/cache files
  -> detect languages/frameworks
  -> parse README/package/test/config files
  -> inspect source structure
  -> summarize project facts
  -> write project_facts.md
  -> chunk/index facts and selected source evidence
```

Project facts should include:

- Problem solved.
- User-facing functionality.
- Data sources.
- Models/algorithms.
- ETL/data engineering pieces.
- NLP/RAG/search pieces.
- Backend/API pieces.
- Frontend/product pieces.
- Testing/eval/observability.
- Scale/performance/security decisions.
- Evidence file paths.

Resume generator output schema:

```text
TailoredResumeDraft
  tailored_text
  sections[]
  bullets[]
    text
    target_requirement_ids[]
    evidence_ids[]
    unsupported_claim_risk
    keyword_coverage[]
    changed_from_original
  changes_summary
  missing_evidence_warnings[]
```

Production rule:

No evidence, no claim. The model can reframe, reorder, and emphasize. It cannot invent.

### Resume Evals

Metrics:

- JD requirement extraction accuracy.
- Evidence recall@k for each requirement.
- Unsupported claim rate per bullet.
- Skill hallucination rate.
- Keyword coverage using supported facts only.
- Human edit distance.
- Recruiter-readability review score.
- User accept/regenerate/edit rate.

## Feature 6: Radar

### Current State

Primary files:

- `backend/tasks/run_research_radar.py`
- `backend/services/research_radar/graph.py`
- `backend/services/research_radar/nodes/*`
- `backend/services/research_radar/llm.py`
- `backend/services/opportunity_radar/*`
- `backend/services/job_sources/*`

Current modes:

1. Internal mode:
   - Uses user-owned/internal signals.
   - Generates opportunity signals, scores, briefs, actions, and alerts.

2. Research/hybrid mode:
   - Runs a graph pipeline:

```text
load_tracker_context
  -> normalize_research_brief
  -> validate_brief
  -> plan_research_tasks
  -> run_search_tasks
  -> fetch_documents
  -> extract_evidence
  -> dedupe_and_rank_evidence
  -> build_report_diff
  -> write_report
  -> derive_report_actions
  -> verify_report
  -> persist_report
  -> emit_alerts
  -> schedule_next_run
```

Current strengths:

- Strong orchestration shape.
- Research runs and steps are persisted.
- Evidence/source/report tables exist.
- Cost, tokens, prompt versions, and failures are tracked.
- Verification node exists.
- Radar already thinks in terms of evidence and reports more than other features.

Current gaps:

- Public web retrieval is open-ended and brittle.
- Source universe is not curated enough per user/profile.
- Radar does not fully leverage verified job source records as the primary source layer.
- Evidence ranking is not yet a robust deterministic trust/freshness/entity-match model.
- Report verification is not yet claim-by-claim.
- Radar can produce useful reports, but production needs stronger source controls and eval gates.

### Production Target

Radar should become a source-registry-driven research system:

```text
user research profile
  -> classify research intent
  -> select source bundles
  -> retrieve/fetch from trusted sources first
  -> extract structured evidence
  -> dedupe by URL/entity/claim
  -> rank by trust/freshness/relevance
  -> write report with claim citations
  -> derive actions through shared ActionCandidate layer
```

Source bundles:

- User pipeline and applications.
- User company visits and extension captures.
- Verified company career pages.
- ATS job source adapters.
- Saved companies.
- Saved roles/domains.
- Public company blogs/news if relevant.
- Research feeds or GitHub sources for technical domains.
- External web search only as a fallback or expansion source.

Radar production controls:

- Source registry with trust tiers.
- Fetch budget per run.
- Freshness window by source type.
- Deduped source URLs.
- Claim-level evidence IDs.
- Report verification that checks each claim has supporting evidence.
- Alerts capped and deduped by profile/topic/entity/time bucket.

### Radar Evals

Metrics:

- Source precision.
- Source freshness.
- Duplicate source URL rate.
- Evidence support score.
- Claim citation coverage.
- Unsupported claim rate.
- Report usefulness rating.
- Action acceptance rate.
- Alert fatigue rate.

## Feature 7: Browser Extension Job Capture

### Current State

Primary behavior:

- The extension can send job/application data into the pipeline.
- Backend job creation checks hard duplicates by normalized job URL.
- Duplicate check endpoint returns hard, soft, or none.
- Source links are sanitized and stored with hashes.

Current strengths:

- Extension capture is already part of the user workflow.
- URL sanitization and private link handling exist.
- Job URL duplicate checks exist.

Current gaps:

- Extension capture and Gmail classification can independently surface the same job.
- Extension capture and Radar can independently surface the same job.
- Extension action notifications should be unified with Gmail/Radar action dedupe.

### Production Target

Extension capture should become one input source into the shared action/entity system:

```text
extension capture
  -> normalize job URL/company/role
  -> check hard duplicate
  -> check soft duplicate
  -> create/link application
  -> suppress duplicate notifications
  -> index resulting application/source evidence
```

Important rule:

If the user already captured a job through the extension, then a later Gmail email about that same job should not create a "new job to add" notification. It should link the email to the existing application and optionally notify only if there is a meaningful update.

## Feature 8: Network And Contact Intelligence

### Current State

Primary files:

- `backend/main.py`
- `backend/services/email_classifier.py`
- `backend/services/email_sender.py`

Current behavior:

- Gmail conversation messages can suggest contacts.
- Contact duplicate endpoint checks email hard match and name soft match.
- Contacts can be kept separate.
- Outreach status can be updated.

Current strengths:

- There is already a network-contact suggestion path.
- Hard and soft contact duplicate checks exist.
- The app supports "keep separate" decisions.

Current gaps:

- Contact suggestions are not yet a unified action candidate.
- Soft duplicate quality needs more entity features such as company, domain, title, thread, LinkedIn, and existing application relationship.
- Network notifications should be suppressed when a sender is already in the network.

### Production Target

Network intelligence should use entity resolution:

```text
email conversation
  -> person entity extraction
  -> normalize email/name/company/domain/title
  -> contact dedupe
  -> decide link existing, suggest merge, or suggest add
```

Entity signals:

- Email address.
- Sender display name.
- Domain.
- Company name.
- Job title/signature.
- LinkedIn URL.
- Existing application relationship.
- Prior thread history.

## Feature 9: AI Governance, Eval Analytics, And Reproducible Artifacts

### Current State

Primary files and models:

- `backend/PROMPT_REGISTRY.md`
- `backend/models.py`
- `backend/services/admin_ai.py`
- `backend/services/reports/*`
- `backend/services/evals/*`
- `docs/interview-artifacts/*`
- `docs/interview-artifacts/feature-changelogs/*`

The codebase already has several governance primitives:

| Object | Current purpose |
| --- | --- |
| `AiModelCall` | Records model, prompt version, variant, status, validation result, fallback state, latency, tokens, cost, metadata, and model card link. |
| `AiSafetyDecision` | Records safety decisions, risk score, prompt-injection score, data classes, consent snapshot, redaction counts, and review status. |
| `AiExperiment` | Represents model/prompt/retriever experiments by surface and task. |
| `AiExperimentAssignment` | Tracks deterministic user-to-variant assignment. |
| `AiShadowRun` | Records candidate variant runs that do not affect the user-visible path. |
| `AiPromotionReport` | Stores promotion recommendations and comparison reports. |
| `AiModelCard` | Documents intended use, prohibited use, limitations, eval dataset version, metrics, guardrails, approval, rollback, and review cadence. |
| `AiArtifact` | Links generated artifacts to users, model calls, artifact types, paths, and metadata. |
| `backend/PROMPT_REGISTRY.md` | Documents prompt text, model choice, purpose, token limits, changelog, and fallbacks. |
| Feature changelogs | Capture architecture decisions, observed failures, RCA, eval artifacts, and implementation plans. |

Current strengths:

- The app is already designed to track model calls instead of treating LLM calls as invisible side effects.
- Prompt versions exist in task configs and model-call rows.
- Promotion report and model-card concepts already exist.
- Admin AI services can aggregate calls, artifacts, experiments, and promotion reports.
- Interview artifact docs already capture eval, risk, cost, governance, and changelog narratives.
- The Gmail classifier changelog shows the strongest version of this workflow: observed eval failures led to a route-first classifier architecture instead of generic prompt tweaking.

Current gaps:

- Evals, prompt changes, model changes, and retriever changes are not yet forced into one automatic run registry.
- A developer can improve a prompt/model locally without automatically producing a comparable artifact.
- There is not yet a single dashboard view that answers: what changed, why did it change, what dataset was used, what got better, what got worse, and whether it was promoted.
- Prompt registry generation exists, but prompt changes should be tied to eval results and release decisions.
- Retriever changes need the same governance treatment as model and prompt changes.
- Dashboard views should show trends over time, not only latest results.
- Changelogs are not yet enforced as part of the release workflow for every AI feature.

### Production Target

Every AI-relevant change should produce a durable artifact.

AI-relevant changes include:

- Model change.
- Prompt change.
- Prompt variable/context change.
- Retriever or embedding model change.
- Chunking strategy change.
- Reranker change.
- Classification threshold change.
- Safety policy change.
- Dedupe policy change.
- Dataset or label version change.

Production workflow:

```text
code/prompt/model/retriever change
  -> run eval suite
  -> capture dataset versions and git SHA
  -> capture prompt/model/retriever versions
  -> capture metrics, costs, failures, and regressions
  -> write artifact
  -> link artifact to AiArtifact
  -> create or update AiPromotionReport
  -> dashboard shows trend and decision
```

The dashboard should make AI behavior auditable over time. It should not only say "new model is better." It should show:

- Which model/prompt/retriever changed.
- Which dataset and label version were used.
- Which metrics improved.
- Which metrics regressed.
- Whether cost/latency changed.
- Whether safety failures changed.
- Which examples flipped from correct to incorrect.
- Which examples flipped from incorrect to correct.
- Whether the change was shadow-only, staged, promoted, rejected, or rolled back.

### Governance Dashboard

Recommended dashboard sections:

| Section | Questions answered |
| --- | --- |
| Overview | Are AI quality, cost, latency, and safety improving over time? |
| Runs | What eval/model/prompt/retriever runs happened, on what code SHA, with what outcome? |
| Prompt Registry | What prompts exist, what changed, who approved them, what evals support them? |
| Model Cards | Which model/prompt versions are approved for each task? What are their limits and rollback plans? |
| Eval Datasets | Which datasets exist, how many real vs synthetic cases, when were they last updated? |
| Feature Scorecards | Gmail, Actions, Search, Copilot, Resume, Radar quality trends by metric. |
| Regression Analysis | Which examples got worse after a change? |
| Cost And Latency | Cost per task, cost per successful outcome, model-call rate, tokens, p95 latency. |
| Safety | Prompt injection blocks, data leakage risk, quarantines, redactions, unsafe outputs. |
| Promotion Reports | Candidate vs control results and final promote/reject/rollback decision. |
| Artifacts | Links to generated Markdown/JSON reports for reproducibility. |
| Changelogs | Human-readable decision history that explains what was observed, why a change was made, and what evidence supports it. |

### Artifact Requirements

Each generated artifact should include:

- Artifact ID.
- Artifact type.
- Created timestamp.
- Git commit SHA.
- Environment.
- Surface and task name.
- Model/provider/version.
- Prompt version and prompt hash.
- Retriever/index version where relevant.
- Dataset name/version/hash.
- Number of real and synthetic examples.
- Evaluation command.
- Metrics.
- Cost and latency summary.
- Safety summary.
- Regression examples.
- Known limitations.
- Decision: promote, reject, shadow more, needs labels, or rollback.
- Links to `AiModelCall`, `AiPromotionReport`, `AiModelCard`, and source eval files.

Recommended artifact types:

- `eval_run_report`
- `prompt_change_report`
- `model_change_report`
- `retriever_change_report`
- `classifier_threshold_report`
- `dedupe_policy_report`
- `safety_policy_report`
- `feature_changelog`
- `decision_log`
- `rca_report`
- `promotion_report`
- `rollback_report`

Recommended artifact layout:

```text
docs/interview-artifacts/generated/
  YYYY-MM-DD-task-change-summary.md
  YYYY-MM-DD-task-change-summary.json

evals/runs/
  task_name/
    YYYY-MM-DDTHH-MM-SSZ/
      config.json
      metrics.json
      predictions.jsonl
      regressions.jsonl
      report.md
```

### Narrative Changelogs And Decision Logs

Metrics explain what happened. Changelogs explain why the team chose the next architecture.

The feature changelog should be written like an engineering lab notebook, not a polished press release. It should preserve the real reasoning trail:

```text
baseline implementation
  -> observed artifacts and failure signs
  -> root cause analysis
  -> architecture decision
  -> implementation changelog
  -> eval artifacts
  -> cost and latency impact
  -> what changed in our understanding
  -> next iteration
```

The Gmail classifier changelog is the model pattern. It explains that the route-first architecture was not chosen because "LLMs are bad." It was chosen because evals and labeled review showed a deeper taxonomy problem: the classifier was asking for lifecycle subtype too early, so job alerts, opportunity discovery, recruiter conversations, and application inbox events were being forced into the wrong bucket.

Good changelog entries should answer:

- What did we believe before this run?
- What data or eval artifact challenged that belief?
- Which examples changed our mind?
- Was the issue prompt wording, taxonomy, retrieval, routing, labels, thresholds, or product policy?
- What architecture decision followed?
- What did we deliberately not change yet?
- What risk did the change reduce?
- What risk did the change introduce?
- What eval or user feedback will decide the next step?

Example decision-log format:

```text
Decision: Move Gmail classifier to route-first architecture.

Observation:
Priority label eval showed route confusion. Opportunity-discovery and job-alert emails
were being forced into lifecycle categories such as conversation or action_item.

Root cause:
The classifier selected lifecycle subtype before deciding the higher-level route.
Generic words like "apply", "candidate", and "opportunity" had different meanings
depending on whether the email came from a job board alert, an ATS inbox message,
or a human recruiter.

Change:
Score route first: filter, opportunity_discovery, conversation, application_inbox,
action_review. Then classify subtype inside the chosen route.

Why this is better:
It separates job-related recall from automatic status precision and prevents
job-alert emails from triggering lifecycle/status actions.

Evidence:
Link to eval report, confusion matrix, case results, and changed examples.

Next question:
Does route-first improve real labeled route accuracy without lowering recall on
interview_request or action_item emails?
```

This changelog layer is also useful externally. Sanitized public versions can become:

- Product build-in-public posts.
- Technical blog posts.
- Interview artifacts.
- Investor/customer updates.
- Community feedback requests.

Public versions must remove private user data, raw emails, private URLs, and sensitive labels. The public story should focus on the engineering loop:

```text
we saw failure mode X
  -> measured it with artifact Y
  -> changed architecture Z
  -> reran eval
  -> learned the next limitation
```

### Prompt Registry Requirements

The prompt registry should become a controlled interface, not just documentation.

For each prompt:

- Task name.
- Surface.
- Prompt version.
- Model.
- Intended use.
- Prohibited use.
- Input data classes.
- Output schema.
- Safety policy.
- Eval dataset version.
- Primary metrics.
- Guardrail metrics.
- Changelog.
- Owner/reviewer.
- Rollback prompt version.

Prompt changes should require:

1. Prompt version bump.
2. Prompt hash change captured.
3. Eval run against relevant datasets.
4. Generated artifact.
5. Promotion report or explicit "not promoted" decision.

### Reproducibility Rules

Production AI workflows should be reproducible enough that another engineer can understand why a change was accepted.

Rules:

- Never promote a model/prompt/retriever change from anecdotal examples alone.
- Store run configs and metrics as machine-readable JSON.
- Store human-readable Markdown summaries for review.
- Store narrative changelog entries for meaningful architecture or prompt decisions.
- Keep real and synthetic eval metrics separate.
- Track dataset versions, not just dataset paths.
- Track prompt hashes, not just prompt names.
- Track retriever/index versions for RAG systems.
- Record negative examples and regressions, not only aggregate scores.
- Link user feedback back to the model call or action candidate that produced it.
- Preserve rejected ideas and non-changes when they explain product judgment.

### Governance Metrics

Platform-wide metrics:

- Eval pass rate over time.
- Real-data pass rate over time.
- Synthetic-data pass rate over time.
- Regression count per release.
- Unsupported claim rate.
- Citation precision.
- Retrieval recall@k.
- Duplicate notification rate.
- User action accept/dismiss rate.
- Safety block rate.
- Prompt-injection block rate.
- Data leakage rate.
- Cost per successful user-visible outcome.
- p50/p95 latency by task.
- Fallback rate.
- Rollback count.
- Changelog coverage rate for promoted AI changes.
- Time from observed failure to documented decision.
- Number of regressions with RCA completed.

Interview framing:

> It does not matter if a model appears to get better if we cannot explain why, reproduce the run, identify regressions, or roll it back. Production AI needs transparent artifacts: prompt registry, model cards, eval reports, promotion reports, safety decisions, and trend dashboards. That turns model iteration into an auditable engineering workflow rather than ad hoc prompt tweaking.

Additional public-building framing:

> The changelog is where the product becomes compelling. It shows the reasoning behind the system: we observed failure modes, changed the architecture for specific reasons, measured the result, and documented what we still do not know. That is more credible than saying "we improved the model."

## Shared Risk And Safety Controls

High-risk inputs:

- Emails.
- Job descriptions.
- Public web pages.
- Repo zips.
- Resume text.
- User free-form prompts.

Controls:

- Treat all external/user-uploaded text as untrusted.
- Strip or isolate prompt-like instructions from retrieved content.
- Run safety preflight before LLM use.
- Enforce user-scoped retrieval.
- Require citations/evidence IDs for factual generation.
- Block direct side effects unless the action policy allows it.
- Redact sensitive data from telemetry.
- Store model call ledgers with prompt/model/version/cost/fallback.

Relevant external references:

- OpenAI evals: https://developers.openai.com/api/docs/guides/evals
- OpenAI model optimization: https://developers.openai.com/api/docs/guides/model-optimization
- OpenAI Structured Outputs: https://developers.openai.com/api/docs/guides/structured-outputs
- OpenAI retrieval/vector stores: https://developers.openai.com/api/docs/guides/retrieval
- RAG paper: https://arxiv.org/abs/2005.11401
- OpenSearch hybrid search: https://docs.opensearch.org/docs/latest/vector-search/ai-search/hybrid-search/
- OWASP Top 10 for LLM Applications: https://owasp.org/www-project-top-10-for-large-language-model-applications/
- NIST AI Risk Management Framework: https://www.nist.gov/itl/ai-risk-management-framework

## Production Roadmap

### Phase 1: Stabilize Current Intelligence

Goals:

- Keep Gmail hybrid classifier as the main classification path.
- Add missing signal pass-through such as candidate URLs.
- Add action candidate objects without changing UX behavior.
- Centralize job/contact/interview dedupe behind one service.
- Add dedupe keys to alerts/recommended actions.
- Expand real Gmail labels.

Deliverables:

- `ActionCandidate` model/service.
- `DedupeGate` service.
- Gmail action extraction produces candidates.
- Extension capture calls the same dedupe service.
- Contact/job/interview duplicate checks are reused, not duplicated.

### Phase 2: Build User Knowledge RAG Foundation

Goals:

- Introduce user knowledge documents and chunks.
- Index resume/profile/application/project/email/radar sources.
- Add embeddings and hybrid retrieval.
- Keep Postgres lexical as fallback.

Deliverables:

- `UserKnowledgeDocument`.
- `DocumentChunk`.
- Chunking pipeline.
- Embedding pipeline.
- Hybrid retrieval interface.
- Retrieval eval harness.

### Phase 3: Evidence-Grounded Resume Tailoring

Goals:

- Add project/repo ingestion.
- Convert repo zip or GitHub repo into verified project facts.
- Tailor resume bullets only from retrieved evidence.

Deliverables:

- Repo ingestion worker.
- `project_facts.md` generator.
- Resume JD parser.
- Evidence-grounded resume draft schema.
- Unsupported claim validator.
- Resume eval suite.

### Phase 4: Production Copilot

Goals:

- Route Copilot requests by intent.
- Use hybrid retrieval.
- Produce answer citations and optional action candidates.
- Keep direct mutation disabled unless explicitly confirmed.

Deliverables:

- Copilot router.
- Source-specific retrieval plans.
- Claim/citation validator.
- Copilot feedback dashboards.
- Red-team evals for leakage and prompt injection.

### Phase 5: Source-Registry Radar

Goals:

- Make Radar source-first.
- Use verified job/company sources before broad web search.
- Strengthen evidence ranking and report verification.
- Route Radar actions through shared action/dedupe layer.

Deliverables:

- Radar source bundle selector.
- Source trust/freshness scoring.
- Claim-level report verifier.
- Radar deduped alerts.
- Radar evidence eval promotion gate.

### Phase 6: Continuous Improvement Loop

Goals:

- Convert user feedback into eval datasets.
- Run shadow experiments.
- Generate promotion reports before changing models/prompts/retrievers.
- Make every AI-relevant change reproducible through artifacts, prompt registry entries, model cards, and dashboard trend lines.

Deliverables:

- Label review UI.
- Feedback-to-eval pipeline.
- Shadow run comparison.
- Model/prompt/retriever promotion report.
- Automatic eval artifact writer.
- Feature changelog writer and decision-log template.
- Prompt registry enforcement.
- AI governance dashboard for run history and quality trends.
- Sanitized public changelog export for build-in-public posts and technical writeups.
- Production dashboards for quality, cost, latency, and safety.

## Interview Narrative

Use this concise explanation:

> The current system started with cold-start NLP constraints, so Gmail classification is a deterministic hybrid classifier with optional LLM adjudication rather than a trained model. That gives explainability and control while we collect labels. The production direction is to turn every AI feature into an evidence-grounded pipeline: classify intent, normalize entities, dedupe actions, retrieve user-scoped evidence, generate structured outputs, validate citations, and collect feedback for evals.

For Bank of America Erica / Chat and Voice alignment:

- Gmail classification maps to intent classification and NLP routing.
- Copilot maps to grounded conversational assistant architecture.
- Resume tailoring maps to RAG plus controlled generation.
- Radar maps to source-grounded research and summarization.
- Action notifications map to entity resolution, risk controls, and side-effect policy.
- Dedupe maps to production reliability and user trust.
- Eval/feedback loops map to responsible AI and model risk management.

Key production claim:

> Classification alone is not enough. In a production assistant, especially one that can recommend actions, the system must resolve entities, check duplicates, verify evidence, and require confirmation before side effects.
