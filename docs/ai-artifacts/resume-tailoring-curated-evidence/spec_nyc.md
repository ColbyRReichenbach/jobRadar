---
project_id: spec_nyc
title: S.P.E.C. NYC Valuation and Governance
project_tags: Python, pandas, NumPy, scikit-learn, XGBoost, SHAP, Optuna, MLflow, Pandera, SQLAlchemy, PostgreSQL, H3, ETL, feature engineering, model evaluation, model monitoring, MLOps, Streamlit, Next.js, TypeScript, Zod, AI safety
---

- [CUR-SPEC-ETL-PIPELINE] Built a 1,042-line Python ETL pipeline that loads raw NYC property data, cleans it, extracts apartment/unit tokens, creates property IDs, deduplicates sales, enriches sales history, assigns segments and price tiers, imputes missing values, creates model features, and can load outputs into PostgreSQL.
  evidence_skills: Python, ETL, pandas, PostgreSQL, feature engineering, data cleaning
- [CUR-SPEC-DATASOURCE-ABSTRACTION] Created data source abstractions and canonical schemas/contracts so the same ETL path can operate over downloaded files, CSVs, or database-backed sources.
  evidence_skills: data source abstraction, schema contracts, ETL, CSV processing
- [CUR-SPEC-LEAKAGE-CONTROL] Added leakage-control design by computing H3 price-lag features from training data, validating feature contracts, and using a non-leaky price-tier proxy path.
  evidence_skills: leakage control, H3, feature engineering, feature validation
- [CUR-SPEC-MODEL-PIPELINE] Built a supervised valuation modeling pipeline with time splits, H3 price-lag features, temporal regime features, training feature validation, optional Optuna tuning, and global or routed model strategies.
  evidence_skills: supervised learning, valuation modeling, scikit-learn, Optuna, time split validation
- [CUR-SPEC-EVAL-METRICS] Calculated valuation metrics, segment metrics, and price-tier metrics through a dedicated evaluation layer.
  evidence_skills: model evaluation, valuation metrics, segment analysis, price-tier metrics
- [CUR-SPEC-MODEL-EVIDENCE] Produced readable model evidence artifacts including overall test rows, PPE10, MdAPE, R-squared, segment performance, price-tier performance, train/test row counts, model version, artifact tag, and training timestamp.
  evidence_skills: model evidence, PPE10, MdAPE, R-squared, evaluation artifacts
- [CUR-SPEC-SHAP-EXPLAINABILITY] Generated SHAP artifacts and exposed explainability through Streamlit and Next.js product surfaces.
  evidence_skills: SHAP, explainability, Streamlit, Next.js, model interpretation
- [CUR-SPEC-MONITORING-DRIFT] Built monitoring artifacts for drift and performance status, including alerts and warnings that feed release/retraining decisions.
  evidence_skills: model monitoring, drift detection, alerting, retraining signals
- [CUR-SPEC-RETRAIN-POLICY] Implemented retraining decision logic that combines performance, PPE10, MdAPE, and drift alerts.
  evidence_skills: retraining policy, model monitoring, performance thresholds, drift alerts
- [CUR-SPEC-CHAMPION-CHALLENGER] Implemented champion/challenger and release gate logic in the MLOps layer.
  evidence_skills: champion challenger, MLOps, release gates, model governance
- [CUR-SPEC-STREAMLIT-GOVERNANCE] Built a Streamlit governance dashboard that loads model artifacts, metrics, monitoring outputs, release/retrain decisions, SHAP images, evaluation predictions, and model binaries.
  evidence_skills: Streamlit, governance dashboard, model artifacts, SHAP, MLOps
- [CUR-SPEC-NEXT-CONTRACTS] Built Next.js API routes and BFF clients with Zod request/response contracts for valuation, property lookup/search, nearby lookup, monitoring, governance, and copilot surfaces.
  evidence_skills: Next.js, TypeScript, Zod, API contracts, BFF clients
- [CUR-SPEC-AI-SECURITY] Implemented AI security controls for prompt-injection prevention, token-aware truncation, structured JSON output, recursive text splitting, cost/token limits, retry/error handling, and audit logging.
  evidence_skills: AI safety, prompt-injection prevention, token budgeting, structured outputs, audit logging
- [CUR-SPEC-COPILOT-BOUNDED] Built a bounded copilot path that routes intent, packs grounded context, evaluates safety, calls an LLM when available, validates/shapes the response, and records telemetry/audit.
  evidence_skills: bounded copilot, grounded context, LLM safety, telemetry, audit logging
- [CUR-SPEC-MODEL-QUALITY-BOUNDARY] Documented model-quality limits where monitoring artifacts flag performance/drift alerts and recommend retraining rather than claiming production-grade AVM quality.
  evidence_skills: model-quality governance, drift alerts, performance monitoring, evidence boundaries
- [CUR-SPEC-WEB-MODEL-BOUNDARY] Identified that the web valuation API is heuristic/artifact-backed rather than direct `joblib` model inference, preventing an unsupported production inference claim.
  evidence_skills: evidence governance, model inference boundary, production-readiness review
