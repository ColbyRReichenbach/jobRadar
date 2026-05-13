# Documentation Map

This folder has three different kinds of documents. Treat them differently when deciding what belongs in the remote repo.

## Product Source Of Truth

These docs describe the product or operational posture as it should be understood today:

- [`../README.md`](../README.md): product overview, local setup, and documentation entrypoint.
- [`../TECHNICAL.md`](../TECHNICAL.md): architecture, implementation tradeoffs, and system shape.
- [`../SECURITY.md`](../SECURITY.md): auth, secrets, consent, extension security, and safeguards.
- [`deployment-checklist.md`](deployment-checklist.md): deployment and rollout checklist.
- [`privacy-policy.md`](privacy-policy.md): product privacy policy.
- [`production-readiness-audit.md`](production-readiness-audit.md): latest launch-readiness audit.

## Product Design And Implementation Specs

These docs are product-adjacent specs. Keep them in the repo while they describe active or near-term architecture:

- [`radar-research-spec.md`](radar-research-spec.md)
- [`radar-research-sprints.md`](radar-research-sprints.md)
- [`source-intelligence-job-search-spec.md`](source-intelligence-job-search-spec.md)
- [`source-intelligence-implementation-todo.md`](source-intelligence-implementation-todo.md)
- [`source-grounded-radar-copilot-eval-spec.md`](source-grounded-radar-copilot-eval-spec.md)

## AI Evaluation And Governance Artifacts

These are committed when they document model behavior, evaluation decisions, safety controls, or reproducible AI-system evidence:

- [`../evals/`](../evals/): sanitized fixture datasets and labeling guidelines.
- [`ai-artifacts/`](ai-artifacts/): AI governance notes, eval reports, model-risk controls, and progress logs.
- [`ai-artifacts/feature-changelogs/`](ai-artifacts/feature-changelogs/): implementation/evaluation changelogs for AI-heavy features.

Generated eval outputs, raw Gmail-derived labeling runs, rendered PDFs/HTML, and local reports stay local and are ignored by `.gitignore`.

## Archive

[`archive/`](archive/) contains historical plans, old audits, retired execution backlogs, and superseded working docs. Move docs there when they are still useful context but should not be treated as current product truth.

## Keep Out Of Remote

Do not commit:

- raw Gmail exports or manually labeled private inbox CSVs
- rendered PDFs/HTML unless there is a specific release reason
- local database files
- generated eval/run artifacts
- screenshots or mocks that are not used by the product or committed docs
- private planning notes that duplicate or contradict current docs
