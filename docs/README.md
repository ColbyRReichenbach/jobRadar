# Documentation Map

This folder is split by purpose. Not every document should read the same way, and not every document belongs in the remote repo forever.

The rule of thumb:

- product docs should explain the current system clearly
- operational docs should stay precise
- AI artifacts should preserve evidence and decisions
- old plans should move to the archive instead of competing with current truth

## Product Source Of Truth

These are the docs to read if you want to understand AppTrail as it exists today:

- [`../README.md`](../README.md): product overview, local setup, and documentation entrypoint.
- [`../TECHNICAL.md`](../TECHNICAL.md): architecture, implementation tradeoffs, and system shape.
- [`../SECURITY.md`](../SECURITY.md): auth, secrets, consent, extension security, and safeguards.
- [`deployment-checklist.md`](deployment-checklist.md): deployment and rollout checklist.
- [`privacy-policy.md`](privacy-policy.md): product privacy policy.
- [`production-readiness-audit.md`](production-readiness-audit.md): dated launch-readiness audit and remediation record.

## Product Design And Implementation Specs

These are active or near-term product specs. Keep them in the repo while they still describe architecture we are building toward:

- [`radar-research-spec.md`](radar-research-spec.md)
- [`radar-research-sprints.md`](radar-research-sprints.md)
- [`source-intelligence-job-search-spec.md`](source-intelligence-job-search-spec.md)
- [`source-intelligence-implementation-todo.md`](source-intelligence-implementation-todo.md)
- [`source-grounded-radar-copilot-eval-spec.md`](source-grounded-radar-copilot-eval-spec.md)

## AI Evaluation And Governance Artifacts

These docs are evidence, not marketing. Commit them when they document model behavior, evaluation decisions, safety controls, or reproducible AI-system outcomes:

- [`../evals/`](../evals/): sanitized fixture datasets and labeling guidelines.
- [`ai-artifacts/`](ai-artifacts/): AI governance notes, eval reports, model-risk controls, and progress logs.
- [`ai-artifacts/feature-changelogs/`](ai-artifacts/feature-changelogs/): implementation/evaluation changelogs for AI-heavy features.

Generated eval outputs, raw Gmail-derived labeling runs, rendered PDFs/HTML, and local reports stay local and are ignored by `.gitignore`.

## Archive

[`archive/`](archive/) is for historical plans, old audits, retired execution backlogs, and superseded working docs. Keep them when they explain why the product changed. Do not treat them as current product truth.

## Keep Out Of Remote

Do not commit:

- raw Gmail exports or manually labeled private inbox CSVs
- rendered PDFs/HTML unless there is a specific release reason
- local database files
- generated eval/run artifacts
- screenshots or mocks that are not used by the product or committed docs
- private planning notes that duplicate or contradict current docs
