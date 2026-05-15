---
project_id: shelfops
title: ShelfOps Replenishment Platform
project_tags: Python, FastAPI, SQLAlchemy, PostgreSQL, Alembic, Redis, Celery, LightGBM, XGBoost, MLflow, SHAP, Pandera, Square API, EDI, SFTP, Kafka, React, TypeScript, MLOps, forecasting, inventory optimization, human-in-the-loop decision support
---

- [CUR-SHELFOPS-FASTAPI-ROUTES] Built a FastAPI backend with versioned routers for stores, products, data, forecasts, alerts, integrations, inventory, purchase orders, replenishment, models, ML alerts, experiments, anomalies, outcomes, MLOps, reports, simulations, and websocket alerts.
  evidence_skills: FastAPI, API design, backend routes, websocket alerts
- [CUR-SHELFOPS-TENANT-DB] Implemented tenant-scoped async SQLAlchemy sessions that set PostgreSQL tenant context with `set_config('app.current_customer_id', ...)`.
  evidence_skills: SQLAlchemy, PostgreSQL, multitenancy, tenant isolation
- [CUR-SHELFOPS-ORM-SCOPE] Built 40 SQLAlchemy ORM models covering customers, stores, products, suppliers, transactions, inventory, forecasts, accuracy, reorder points, alerts, purchase orders, integrations, anomalies, EDI logs, model versions, dataset snapshots, backtests, shadow predictions, retraining logs, tenant readiness, experiments, and recommendation outcomes.
  evidence_skills: SQLAlchemy, ORM modeling, PostgreSQL, data modeling
- [CUR-SHELFOPS-DATA-SOURCES] Built data ingestion paths for M5/Walmart benchmarks, FreshRetailNet-50K, CSV onboarding, Square, EDI, SFTP, and Kafka/event streams.
  evidence_skills: data ingestion, Square API, EDI, SFTP, Kafka, CSV onboarding
- [CUR-SHELFOPS-SQUARE-INTEGRATION] Implemented Square OAuth/webhook surfaces, mapping preview/confirmation, paginated catalog retrieval, inventory count retrieval, order retrieval, sync health, dead-letter handling, and replay API surfaces.
  evidence_skills: Square API, OAuth, webhooks, catalog sync, dead-letter handling
- [CUR-SHELFOPS-FORECAST-ARTIFACT] Built an active LightGBM Poisson demand forecasting champion with model metadata, feature importance, SHAP artifacts, registry entries, and champion metadata.
  evidence_skills: LightGBM, demand forecasting, SHAP, model registry, feature importance
- [CUR-SHELFOPS-FORECAST-METRICS] Tracked forecasting metrics including MAE, MAPE, WAPE, MASE, bias, interval coverage, holdout metrics, cutoff date, row count, stores, products, date range, and feature set.
  evidence_skills: forecasting metrics, model evaluation, WAPE, MASE, bias analysis
- [CUR-SHELFOPS-CONFORMAL-INTERVALS] Implemented split-conformal residual quantiles and interval coverage summaries for forecast uncertainty.
  evidence_skills: conformal prediction, uncertainty intervals, forecast calibration
- [CUR-SHELFOPS-CHAMPION-GATES] Implemented champion/challenger gates that consider stockout miss rate, overstock rate, overstock dollars, opportunity-cost confidence, and regression tolerances.
  evidence_skills: champion challenger, model gates, inventory metrics, regression testing
- [CUR-SHELFOPS-TENANT-READINESS] Evaluated tenant ML readiness based on history, store/product counts, accuracy sample counts, and active champion state.
  evidence_skills: ML readiness, data sufficiency checks, tenant evaluation
- [CUR-SHELFOPS-REPLENISHMENT-POLICY] Generated replenishment recommendations from forecast windows, inventory position, lead time, safety stock, EOQ, stockout risk, overstock risk, and model metadata.
  evidence_skills: replenishment optimization, inventory policy, safety stock, EOQ, forecasting
- [CUR-SHELFOPS-DECISION-WORKFLOW] Built human-in-the-loop buyer workflows for queue generation, queue listing, recommendation detail, accept, edit, reject, impact summaries, suggested purchase orders, approval, rejection, receiving, and decision history.
  evidence_skills: human-in-the-loop workflows, decision support, purchase orders, buyer UX
- [CUR-SHELFOPS-OUTCOME-RECORDS] Persisted decision history and outcome records to support later pilot measurement and feedback loops.
  evidence_skills: outcome tracking, feedback loops, decision history, pilot measurement
- [CUR-SHELFOPS-REPORTING] Built reporting routes for inventory health, forecast accuracy, stockout risk, vendor scorecards, replenishment replay comparisons, and impact scorecards.
  evidence_skills: reporting APIs, inventory analytics, vendor scorecards, impact analysis
- [CUR-SHELFOPS-MLOPS-SURFACES] Built MLOps routes and frontend components for model drivers, feature importance, backtests, calibration, model arena, segment metrics, policy comparison, data quality events, and data readiness.
  evidence_skills: MLOps, model monitoring, backtesting, calibration, data quality
- [CUR-SHELFOPS-PRE-PILOT-BOUNDARY] Preserved the evidence boundary that the product is pre-pilot and benchmark-backed rather than claiming measured merchant ROI.
  evidence_skills: evidence governance, pilot boundary, benchmark-backed evaluation
