# Resume Tailoring Evidence Experiment Progress

Date: 2026-05-13

## Scope

Implemented the first evidence-grounded resume tailoring experiment as an eval-only pipeline. Production `backend/services/resume_tailor.py` behavior is unchanged.

The experiment follows the Phase 4 rule from the AI production spec:

```text
No evidence, no new factual claim.
```

## What Changed

- Added sanitized markdown project fixtures under `tests/fixtures/resume_tailoring/projects/`.
- Added a sanitized resume fixture and JD eval cases under `tests/fixtures/resume_tailoring/`.
- Added `backend/services/evals/resume_tailoring_eval.py`.
- Added `scripts/run_resume_tailoring_evidence_eval.py`.
- Added focused tests in `tests/test_resume_tailoring_eval.py`.
- Generated a local artifact under `docs/ai-artifacts/generated/resume-tailoring-evidence-eval/`.

## Fixture Format

Project evidence uses committed sanitized markdown files with simple frontmatter:

- `project_id`
- `title`
- `skills`
- `role`
- `source_type`

Evidence items are bullet lines with stable IDs:

```text
- [EV-AI-RAG] Built a lexical retrieval evaluation harness with chunk-level evidence IDs...
```

Private project markdown files are supported locally by passing `--project-dir` to the runner. Private files should stay in ignored local paths unless sanitized.

## Pipeline

```text
sanitized project markdown
  -> parse stable evidence IDs
  -> index each evidence item as SearchDocumentInput
  -> UserKnowledgeDocument / DocumentChunk
  -> lexical chunk retrieval per JD requirement
  -> resume retrieval metrics
  -> prompt-only deterministic draft
  -> evidence-grounded deterministic draft
  -> unsupported-claim and privacy checks
  -> local report bundle
```

The eval does not call a model. Cost is `0`, model-call count is `0`, and draft generation is deterministic.

## Resume Preflight

Added eval-only preflight support for:

- name redaction
- email redaction
- phone redaction
- address/location redaction
- LinkedIn/GitHub/portfolio/project URL redaction
- frozen section placeholders
- section classification as `editable` or `frozen`

Default frozen sections include contact/header and education. Default editable sections include summary, experience, projects, skills, and certifications.

## Eval Cases

The JD fixture contains five cases:

- strong-fit SWE/backend
- applied AI
- data/retrieval adjacent
- adjacent-but-not-perfect product platform
- unrelated enterprise sales role

Each case defines expected requirements and expected supporting project evidence IDs.

## Local Artifact Results

Artifact:

- `docs/ai-artifacts/generated/resume-tailoring-evidence-eval/report.md`
- `docs/ai-artifacts/generated/resume-tailoring-evidence-eval/metrics.json`
- `docs/ai-artifacts/generated/resume-tailoring-evidence-eval/generated_bullets.csv`

Retrieval metrics at `k=3`:

- Recall@3: 100.0%
- Precision@3: 31.9%
- MRR: 1.0
- Missing evidence rate: 0.0%
- Unrelated evidence rate: 68.1%
- Mean latency: 5.094 ms

Generation checks:

- Prompt-only unsupported bullet rate: 100.0%
- Evidence-grounded unsupported bullet rate: 0.0%
- Prompt-only missing evidence ID rate: 100.0%
- Evidence-grounded missing evidence ID rate: 0.0%

Privacy checks after sanitization:

- Raw email leaks: false
- Raw phone leaks: false
- Raw URL leaks: false
- Model calls: 0

## What Improved

- Resume tailoring now has a reproducible local evidence fixture format.
- Project evidence is indexed through the same retrieval foundation used elsewhere.
- Prompt-only and evidence-grounded drafts are comparable in one artifact.
- Unsupported claims are measured instead of assumed.
- The sanitizer and section classifier make protected-section behavior testable before any LLM call.

The artifact supports one narrow claim: on sanitized fixtures, evidence-grounded deterministic drafts reduced missing-evidence and unsupported-claim flags versus prompt-only deterministic drafts.

## What Failed Or Remains Weak

- Precision is low at 31.9%, and unrelated evidence rate is high at 68.1%.
- The fixture corpus is intentionally tiny and sanitized.
- The deterministic draft generator is not a writing-quality benchmark.
- No real private project corpus or human-reviewed JD holdout was used.
- The unrelated role still exercises retrieval noise rather than proving abstention quality in production conditions.

## Embeddings Decision

Embeddings are not justified as the immediate next step. The high unrelated evidence rate suggests ranking can improve, but the eval set is too small to justify vector search yet.

Recommended next gate:

1. Add a larger human-reviewed private project evidence set locally.
2. Add harder JD cases with explicit negative evidence expectations.
3. Rerun lexical retrieval and unsupported-claim checks.
4. Only evaluate embeddings or hybrid retrieval if lexical precision remains poor on the larger reviewed corpus.

## Validation

Commands run:

- `python3 scripts/run_resume_tailoring_evidence_eval.py`
- `pytest -q tests/test_resume_tailoring_eval.py tests/test_resume_tailor.py`

Additional validation should run before commit:

- `python3 -m py_compile backend/services/evals/resume_tailoring_eval.py scripts/run_resume_tailoring_evidence_eval.py`
- `git diff --check`
