# Curated Resume Evidence Cards

These cards are a manual rewrite of the first extracted evidence layer used for
the resume-tailoring retrieval experiment.

The source markdown reports were strong enough to support this rewrite. The
problem was not a lack of source material. The problem was representation:
automated section splitting produced cards that were either too broad, too
mechanical, or too generic for resume citation retrieval.

## Source Reports

- `/Users/colbyreichenbach/Downloads/AppTrail_jobRadar_report (1).md`
- `/Users/colbyreichenbach/Downloads/AiBS_ABS_Observatory_report.md`
- `/Users/colbyreichenbach/Downloads/Augusta_Defended_masters_report.md`
- `/Users/colbyreichenbach/Downloads/Pulse_Tracker_workout_web_report.md`
- `/Users/colbyreichenbach/Downloads/ShelfOps_report.md`
- `/Users/colbyreichenbach/Downloads/SPEC_NYC_report.md`

## Rewrite Policy

- Keep claims small enough to cite in a resume bullet.
- Preserve evidence boundaries from the source reports.
- Do not claim live production outcomes where the report only supports a
  prototype, benchmark, artifact, or local implementation.
- Split broad product sections into line-level capabilities such as ETL,
  model evaluation, governance, privacy controls, integrations, and UI surfaces.
- Avoid vague cards like "the product includes analytics" when a narrower card
  can say what was built and where it sits in the system.
- Keep broad product-level capabilities in `project_tags`.
- Keep card-level `evidence_skills` narrow. A skill belongs on a card only when
  the card's claim itself proves that skill. For example, a PostgreSQL warehouse
  card should not carry unrelated project tags such as data visualization or
  OpenAI unless the claim actually supports those skills.

## Evaluation Caveat

The labels in
`docs/ai-artifacts/generated/resume-tailoring-curated-evidence/curated_jd_cases_labeled.json`
are still machine-derived from existing reviewed parent labels and the
deterministic support verifier. They are useful for measuring whether cleaner
cards help retrieval. They are not final human citation labels.
