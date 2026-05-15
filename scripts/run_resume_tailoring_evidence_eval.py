from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from backend.services.evals.resume_tailoring_eval import (
    DEFAULT_JD_CASES,
    DEFAULT_OUTPUT_DIR,
    DEFAULT_PROJECT_DIR,
    DEFAULT_PROJECT_DOC_DIR,
    DEFAULT_RESUME,
    OPENAI_EMBEDDING_MODEL_DEFAULT,
    RETRIEVAL_STRATEGIES,
    RETRIEVAL_STRATEGY_LEXICAL,
    build_resume_tailoring_evidence_eval_artifact,
)
from backend.services.evals.resume_project_ingest import PROJECT_DOC_GRANULARITIES, PROJECT_DOC_GRANULARITY_SECTION


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the offline evidence-grounded resume tailoring eval.")
    parser.add_argument("--project-dir", type=Path, default=DEFAULT_PROJECT_DIR)
    parser.add_argument(
        "--project-doc-dir",
        type=Path,
        action="append",
        default=[],
        help="Local markdown project-doc directory or file to preflight and extract into atomic evidence cards.",
    )
    parser.add_argument(
        "--include-sanitized-project-doc-fixture",
        action="store_true",
        help=f"Also ingest sanitized messy project-doc fixture from {DEFAULT_PROJECT_DOC_DIR}.",
    )
    parser.add_argument("--jd-cases", type=Path, default=DEFAULT_JD_CASES)
    parser.add_argument("--resume", type=Path, default=DEFAULT_RESUME)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--k", type=int, default=3)
    parser.add_argument(
        "--skip-manual-project-fixtures",
        action="store_true",
        help="Do not include the committed toy project evidence fixtures. Use this for real project-doc evals.",
    )
    parser.add_argument(
        "--disable-acceptance-gate",
        action="store_true",
        help="Return raw lexical top-k evidence without the eval-only resume evidence acceptance gate.",
    )
    parser.add_argument(
        "--enable-requirement-cleaner",
        action="store_true",
        help="Classify JD rows before retrieval and skip obvious boilerplate/legal/sales-marketing/domain-only rows.",
    )
    parser.add_argument(
        "--enable-support-verifier",
        action="store_true",
        help="Run the deterministic pairwise support verifier after candidate retrieval/gating.",
    )
    parser.add_argument(
        "--project-doc-granularity",
        choices=sorted(PROJECT_DOC_GRANULARITIES),
        default=PROJECT_DOC_GRANULARITY_SECTION,
        help="Evidence-card granularity for markdown project docs. Default preserves the original section-claim cards.",
    )
    parser.add_argument(
        "--retrieval-strategy",
        choices=sorted(RETRIEVAL_STRATEGIES),
        default=RETRIEVAL_STRATEGY_LEXICAL,
        help="Eval-only retrieval strategy. parent_child_lexical ranks broad cards first, then reranks child evidence cards.",
    )
    parser.add_argument(
        "--embedding-model",
        default=OPENAI_EMBEDDING_MODEL_DEFAULT,
        help="OpenAI embedding model for openai_embedding/openai_hybrid eval strategies.",
    )
    args = parser.parse_args()
    project_doc_dirs = list(args.project_doc_dir)
    if args.include_sanitized_project_doc_fixture:
        project_doc_dirs.append(DEFAULT_PROJECT_DOC_DIR)

    artifact = asyncio.run(
        build_resume_tailoring_evidence_eval_artifact(
            project_dir=args.project_dir,
            project_doc_dirs=project_doc_dirs,
            jd_cases_path=args.jd_cases,
            resume_path=args.resume,
            output_dir=args.output_dir,
            k=args.k,
            include_manual_project_fixtures=not args.skip_manual_project_fixtures,
            acceptance_gate_enabled=not args.disable_acceptance_gate,
            support_verifier_enabled=args.enable_support_verifier,
            requirement_cleaner_enabled=args.enable_requirement_cleaner,
            project_doc_granularity=args.project_doc_granularity,
            retrieval_strategy=args.retrieval_strategy,
            embedding_model=args.embedding_model,
        )
    )
    print(
        json.dumps(
            {
                "output_dir": str(args.output_dir),
                "recall_at_k_mean": artifact["retrieval_metrics"]["recall_at_k_mean"],
                "citation_recall_at_k_mean": artifact["retrieval_metrics"].get("citation_recall_at_k_mean"),
                "citation_precision_at_k_mean": artifact["retrieval_metrics"].get("citation_precision_at_k_mean"),
                "citation_labeled_requirement_count": artifact["retrieval_metrics"].get("requirements_with_expected_citation_evidence"),
                "project_docs_scanned": artifact["project_doc_ingest"]["summary"]["project_doc_count"],
                "project_doc_granularity": artifact["metadata"]["project_doc_granularity"],
                "retrieval_strategy": artifact["metadata"]["retrieval_strategy"],
                "embedding_model": artifact["embedding_retrieval"]["model"],
                "extracted_resume_safe_evidence_count": artifact["extracted_resume_safe_evidence_count"],
                "prompt_only_unsupported_bullet_rate": artifact["generation_quality"]["prompt_only"]["unsupported_bullet_rate"],
                "evidence_grounded_unsupported_bullet_rate": artifact["generation_quality"]["evidence_grounded"]["unsupported_bullet_rate"],
                "accepted_unsupported_false_support_rate": artifact["acceptance_gate"]["accepted_unsupported_false_support_rate"],
                "accepted_candidate_count": artifact["acceptance_gate"]["accepted_candidate_count"],
                "support_verifier_enabled": artifact["support_verifier"]["enabled"],
                "support_verifier_false_support_rate": artifact["support_verifier"]["unsupported_false_support_rate"],
                "support_verifier_rejected_candidate_count": artifact["support_verifier"]["rejected_candidate_count"],
                "requirement_cleaner_skipped_count": artifact["requirement_cleaner"]["skipped_requirement_count"],
                "model_calls": artifact["model_calls"]["count"],
            },
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
