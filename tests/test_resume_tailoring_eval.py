import json
from pathlib import Path

import pytest
from sqlalchemy import select

from backend.models import DocumentChunk, RetrievalTrace, UserKnowledgeDocument
from backend.services.evals.resume_tailoring_eval import (
    DEFAULT_JD_CASES,
    DEFAULT_PROJECT_DIR,
    DEFAULT_PROJECT_DOC_DIR,
    DEFAULT_RESUME,
    RETRIEVAL_STRATEGY_PARENT_CHILD_LEXICAL,
    build_resume_tailoring_evidence_eval_artifact,
    check_generated_bullets,
    classify_resume_sections,
    index_project_evidence_records,
    load_project_evidence,
    project_records_from_doc_results,
    sanitize_resume_for_llm,
    GeneratedBullet,
)
from backend.services.evals.resume_project_ingest import (
    PROJECT_DOC_GRANULARITY_ATOMIC,
    extract_evidence_cards_from_markdown,
    extract_project_doc_results,
    preflight_markdown_file,
    preflight_markdown_text,
)
from backend.services.evals.resume_requirement_cleaner import classify_requirement_for_retrieval
from backend.services.evals.resume_support_verifier import NOT_ENOUGH_INFO, SUPPORTS, verify_requirement_evidence
from backend.services.retrieval.lexical import retrieve_document_chunks
from scripts.build_resume_tailoring_jd_label_pack import _split_requirement_sentences
from tests.conftest import TEST_USER_ID


def test_project_markdown_fixtures_parse_sanitized_evidence_records():
    records = load_project_evidence(DEFAULT_PROJECT_DIR)

    assert len(records) == 9
    assert {record.evidence_id for record in records} >= {
        "EV-BACKEND-API",
        "EV-AI-RAG",
        "EV-DATA-RANKING",
    }
    assert all(record.source_path.endswith(".md") for record in records)


def test_project_markdown_parser_separates_project_tags_from_evidence_skills(tmp_path: Path):
    project_file = tmp_path / "curated_project.md"
    project_file.write_text(
        "\n".join(
            [
                "---",
                "project_id: curated_project",
                "title: Curated Project",
                "project_tags: PostgreSQL, OpenAI, data visualization",
                "---",
                "",
                "- [CUR-CARD-DB] Built a PostgreSQL warehouse for normalized analytics data.",
                "  evidence_skills: PostgreSQL, SQL, data warehousing",
            ]
        ),
        encoding="utf-8",
    )

    records = load_project_evidence(tmp_path)

    assert len(records) == 1
    assert records[0].skills == ["PostgreSQL", "SQL", "data warehousing"]
    assert records[0].project_tags == ["PostgreSQL", "OpenAI", "data visualization"]
    assert "OpenAI" not in records[0].to_search_document(TEST_USER_ID).keywords


def test_project_doc_preflight_flags_pii_secrets_paths_and_prompt_injection():
    result = preflight_markdown_file(DEFAULT_PROJECT_DOC_DIR / "messy_codebase_report.md")

    assert result.status == "warn"
    assert {
        "raw_email",
        "raw_phone",
        "raw_url",
        "likely_api_key",
        "secret_assignment",
        "long_id",
        "file_path",
        "prompt_injection",
    }.issubset(set(result.reasons))
    assert all("candidate@example.test" not in finding.sample for finding in result.findings)
    assert all("https://example.test/private/report" not in finding.sample for finding in result.findings)


def test_project_doc_preflight_statuses_include_pass_warn_and_block():
    clean = preflight_markdown_text("## Implementation\nBuilt deterministic markdown evidence extraction.")
    warned = preflight_markdown_text("Contact: candidate@example.test")
    blocked = preflight_markdown_text("api_key=sk-prodABCDEFGHIJKLMNOPQRSTUV")
    blocked_secret = preflight_markdown_text("token=supersecretvalue")

    assert clean.status == "pass"
    assert warned.status == "warn"
    assert blocked.status == "block"
    assert "likely_api_key" in blocked.reasons
    assert blocked_secret.status == "block"
    assert blocked_secret.findings[0].sample == "token=[SECRET]"


def test_blocked_project_doc_does_not_emit_resume_safe_cards(tmp_path: Path):
    path = tmp_path / "blocked_project.md"
    path.write_text(
        "\n".join(
            [
                "# Blocked Project",
                "",
                "## Backend Implementation",
                "- Built Python FastAPI services with PostgreSQL and CI tests for workflow automation.",
                "",
                "## Unsafe Appendix",
                "api_key=sk-prodABCDEFGHIJKLMNOPQRSTUV",
            ]
        ),
        encoding="utf-8",
    )

    result = extract_evidence_cards_from_markdown(path)

    assert result.preflight.status == "block"
    assert result.evidence_cards
    assert all(card.resume_safe is False for card in result.evidence_cards)
    assert all(card.preflight_status == "block" for card in result.evidence_cards)


def test_messy_project_doc_extraction_creates_atomic_cards_and_excludes_noise():
    first = extract_evidence_cards_from_markdown(DEFAULT_PROJECT_DOC_DIR / "messy_codebase_report.md")
    second = extract_evidence_cards_from_markdown(DEFAULT_PROJECT_DOC_DIR / "messy_codebase_report.md")

    assert len(first.evidence_cards) >= 6
    assert [card.evidence_id for card in first.evidence_cards] == [card.evidence_id for card in second.evidence_cards]
    assert len({card.source_section for card in first.evidence_cards}) >= 3
    assert any(card.claim_type == "retrieval" for card in first.evidence_cards)
    assert any(card.claim_type == "privacy_safety" for card in first.evidence_cards)
    assert all("node_modules" not in card.claim_text for card in first.evidence_cards)
    assert all("candidate@example.test" not in card.claim_text for card in first.evidence_cards)
    assert all("Unsafe Appendix" not in card.source_section for card in first.evidence_cards)
    assert all(card.resume_safe for card in first.evidence_cards)

    excluded_reasons = {section.reason for section in first.excluded_sections}
    assert "noise_heading" in excluded_reasons
    assert len(first.excluded_sections) >= 2


def test_project_doc_atomic_granularity_splits_broad_claims_with_parent_aliases(tmp_path: Path):
    path = tmp_path / "broad_project.md"
    path.write_text(
        "\n".join(
            [
                "# Broad Project",
                "",
                "## Backend Architecture",
                (
                    "- Built a production analytics platform that supports FastAPI APIs, PostgreSQL data models, "
                    "LightGBM forecasting artifacts, retrieval evaluation reports, and privacy preflight checks."
                ),
            ]
        ),
        encoding="utf-8",
    )

    section_result = extract_evidence_cards_from_markdown(path)
    atomic_result = extract_evidence_cards_from_markdown(path, granularity=PROJECT_DOC_GRANULARITY_ATOMIC)

    assert len(section_result.evidence_cards) == 1
    assert len(atomic_result.evidence_cards) > len(section_result.evidence_cards)
    parent_id = section_result.evidence_cards[0].evidence_id
    child_cards = [card for card in atomic_result.evidence_cards if card.parent_evidence_id == parent_id]
    assert child_cards
    assert all(card.granularity == PROJECT_DOC_GRANULARITY_ATOMIC for card in atomic_result.evidence_cards)
    assert all(card.evidence_id.startswith(f"{parent_id}-A") for card in child_cards)
    assert any("LightGBM" in card.claim_text for card in child_cards)


@pytest.mark.asyncio
async def test_project_evidence_indexes_into_knowledge_chunks_and_retrieves(db_session):
    records = load_project_evidence(DEFAULT_PROJECT_DIR)
    await index_project_evidence_records(db_session, user_id=TEST_USER_ID, records=records)
    await db_session.commit()

    docs = list((await db_session.execute(select(UserKnowledgeDocument))).scalars().all())
    chunks = list((await db_session.execute(select(DocumentChunk))).scalars().all())
    assert len(docs) == len(records)
    assert len(chunks) == len(records)

    results = await retrieve_document_chunks(
        db_session,
        user_id=TEST_USER_ID,
        query="Python FastAPI PostgreSQL Redis Docker backend services",
        limit=3,
        surface="resume_tailoring_eval_test",
    )

    returned_ids = [result.metadata["evidence_id"] for result in results]
    assert "EV-BACKEND-API" in returned_ids
    trace = (await db_session.execute(select(RetrievalTrace))).scalar_one()
    assert trace.surface == "resume_tailoring_eval_test"
    assert trace.status == "ok"
    assert trace.returned_count >= 1


@pytest.mark.asyncio
async def test_extracted_project_doc_cards_are_retrieved_atomically(db_session):
    results = extract_project_doc_results([DEFAULT_PROJECT_DOC_DIR])
    records = project_records_from_doc_results(results)
    assert len(records) >= 5
    await index_project_evidence_records(db_session, user_id=TEST_USER_ID, records=records)
    await db_session.commit()

    chunks = list((await db_session.execute(select(DocumentChunk))).scalars().all())
    assert len(chunks) == len(records)

    retrieval_results = await retrieve_document_chunks(
        db_session,
        user_id=TEST_USER_ID,
        query="preflight raw PII secret-like assignments prompt injection before model call",
        limit=3,
        surface="resume_project_doc_eval_test",
    )

    returned_ids = [result.metadata["evidence_id"] for result in retrieval_results]
    returned_records = {record.evidence_id: record for record in records}
    assert returned_ids
    assert returned_records[returned_ids[0]].claim_type == "privacy_safety"
    assert "raw PII" in returned_records[returned_ids[0]].text
    assert all("Unsafe Appendix" not in result.snippet for result in retrieval_results)


def test_resume_sanitization_redacts_protected_fields_and_classifies_sections():
    resume_text = DEFAULT_RESUME.read_text(encoding="utf-8")
    result = sanitize_resume_for_llm(resume_text)

    assert "avery.candidate@example.test" not in result.sanitized_text
    assert "555-010-0142" not in result.sanitized_text
    assert "https://" not in result.sanitized_text
    assert "Raleigh, NC" not in result.sanitized_text
    assert "[CONTACT_HEADER_REDACTED]" in result.sanitized_text
    assert "[FROZEN_SECTION:education]" in result.sanitized_text
    assert result.placeholder_counts["email"] == 1
    assert result.placeholder_counts["phone"] == 1
    assert result.placeholder_counts["url"] == 3
    assert result.privacy_checks["raw_email_leaks"] is False
    assert result.privacy_checks["raw_phone_leaks"] is False
    assert result.privacy_checks["raw_url_leaks"] is False

    sections = {section.normalized_title: section.classification for section in result.sections}
    assert sections["summary"] == "editable"
    assert sections["experience"] == "editable"
    assert sections["projects"] == "editable"
    assert sections["skills"] == "editable"
    assert sections["education"] == "frozen"


def test_unsupported_claim_checker_flags_missing_evidence_and_protected_mutation():
    records = load_project_evidence(DEFAULT_PROJECT_DIR)
    evidence_by_id = {record.evidence_id: record for record in records}
    original_resume = DEFAULT_RESUME.read_text(encoding="utf-8")
    bullets = [
        GeneratedBullet(
            case_id="case",
            requirement_id="req",
            strategy="prompt_only",
            section="projects",
            text="Led Python API work by 40% without evidence.",
        ),
        GeneratedBullet(
            case_id="case",
            requirement_id="req",
            strategy="evidence_grounded",
            section="projects",
            text=f"{evidence_by_id['EV-AI-RAG'].text} [evidence: EV-AI-RAG]",
            evidence_ids=["EV-AI-RAG"],
        ),
    ]

    issues = check_generated_bullets(
        bullets,
        evidence_by_id=evidence_by_id,
        original_resume_text=original_resume,
        generated_sections={"Education": "Mutated school"},
        original_sections=classify_resume_sections(original_resume),
    )

    issue_names = {issue["issue"] for issue in issues}
    assert "missing_evidence_id" in issue_names
    assert "fabricated_metrics" in issue_names
    assert "inflated_ownership" in issue_names
    assert "protected_section_mutation" in issue_names
    assert not [issue for issue in issues if issue["strategy"] == "evidence_grounded"]


def test_jd_label_pack_requirement_extraction_splits_dense_qualifications():
    description = (
        "Qualifications Basic Qualifications: 2 or more years of relevant work experience with a "
        "Bachelor's Degree or at least 1 years of work experience with an Advanced degree "
        "(e.g. Masters, MBA, JD, MD) Hands-on experience with prototyping, developing, "
        "and delivering generative AI solutions using APIs and simple Python code. "
        "Strong technical acumen and experience in AI platforms, AI/ML, Large Language Models "
        "(LLMs), evals and agentic systems. Analyze user behavior, product metrics, and LLM "
        "model performance to provide actionable insights."
    )

    requirements = _split_requirement_sentences(description)

    assert not any("Masters, MBA, JD, MD" in item for item in requirements)
    assert any(item.startswith("Hands-on experience with prototyping") for item in requirements)
    assert any(item.startswith("Strong technical acumen") for item in requirements)
    assert any(item.startswith("Analyze user behavior") for item in requirements)


def test_resume_requirement_cleaner_skips_boilerplate_and_keeps_actual_requirements():
    legal = classify_requirement_for_retrieval(
        "Applicants will not be discriminated against because of race, veteran status, or any other protected characteristic.",
        case_title="AppOmni - Principal Data Scientist",
    )
    sales = classify_requirement_for_retrieval(
        "Own enterprise sales pipeline, negotiate contracts, and close annual recurring revenue quotas.",
        case_title="Reducto - Account Executive",
    )
    domain_only = classify_requirement_for_retrieval(
        "Advance biological discovery through wet lab capabilities.",
        case_title="CZ Biohub - Machine Learning Engineer, AI",
    )
    actual = classify_requirement_for_retrieval(
        "Leverage LLM-driven evaluation rubrics and adversarial red-teaming to improve reliability.",
        case_title="Cresta - AI Evaluations Lead",
    )
    html_context = classify_requirement_for_retrieval(
        "<p>The <strong>Senior Data Science Product Engineer</strong> plays a key role in the company’s AI strategy.</p>",
        case_title="AppOmni - Data Science Product Engineer",
    )

    assert legal.category == "legal_compensation"
    assert not legal.should_retrieve
    assert sales.category == "sales_marketing_role"
    assert not sales.should_retrieve
    assert domain_only.category == "domain_only"
    assert not domain_only.should_retrieve
    assert actual.category == "actual_requirement"
    assert actual.should_retrieve
    assert html_context.cleaned_query == "The Senior Data Science Product Engineer plays a key role in the company’s AI strategy."
    assert html_context.should_retrieve


def test_pairwise_support_verifier_accepts_specific_support_and_rejects_domain_mismatch():
    supported = verify_requirement_evidence(
        requirement_text="Build LLM policy evaluation reports and retrieval quality dashboards.",
        evidence_id="EV-AI-EVAL",
        evidence_text="Built LLM policy evaluation reports, retrieval dashboards, and preflight checks for an applied AI product.",
        evidence_skills=["llm", "retrieval", "evals"],
        evidence_claim_type="evaluation",
        evidence_section="AI Evaluation Architecture",
    )
    mismatched = verify_requirement_evidence(
        requirement_text="Own enterprise sales pipeline, negotiate contracts, and close annual recurring revenue quotas.",
        evidence_id="EV-ANALYTICS",
        evidence_text="Built product analytics dashboards and SQL data pipelines for user behavior reporting.",
        evidence_skills=["analytics", "sql"],
        evidence_claim_type="analytics",
        evidence_section="Product Analytics",
    )

    assert supported.label == SUPPORTS
    assert supported.accepted is True
    assert mismatched.label == NOT_ENOUGH_INFO
    assert mismatched.accepted is False
    assert "missing_domain_anchor" in mismatched.reasons


@pytest.mark.asyncio
async def test_resume_tailoring_eval_artifact_compares_prompt_only_and_evidence_grounded(tmp_path: Path):
    output_dir = tmp_path / "resume-tailoring-evidence-eval"
    artifact = await build_resume_tailoring_evidence_eval_artifact(
        project_dir=DEFAULT_PROJECT_DIR,
        jd_cases_path=DEFAULT_JD_CASES,
        resume_path=DEFAULT_RESUME,
        output_dir=output_dir,
        k=3,
    )

    assert artifact["artifact"] == "resume_tailoring_evidence_eval"
    assert artifact["project_evidence_count"] == 9
    assert artifact["jd_case_count"] == 5
    assert artifact["retrieval_metrics"]["recall_at_k_mean"] == 1.0
    assert artifact["retrieval_metrics"]["requirements_without_expected_evidence"] == 1
    assert artifact["generation_quality"]["prompt_only"]["unsupported_bullet_rate"] > artifact["generation_quality"]["evidence_grounded"]["unsupported_bullet_rate"]
    assert artifact["generation_quality"]["evidence_grounded"]["bullet_count"] == 11
    assert artifact["generation_quality"]["evidence_grounded"]["missing_evidence_id_rate"] == 0
    assert artifact["generation_quality"]["evidence_grounded"]["correct_abstention_count"] == 1
    assert artifact["generation_quality"]["evidence_grounded"]["unsupported_requirement_generation_count"] == 0
    assert artifact["generation_quality"]["evidence_grounded"]["missed_supported_requirement_count"] == 0
    assert artifact["model_calls"]["count"] == 0

    metrics = json.loads((output_dir / "metrics.json").read_text(encoding="utf-8"))
    assert metrics["trace_summary"]["trace_count"] == 12
    assert (output_dir / "report.md").exists()
    assert (output_dir / "generated_bullets.csv").exists()
    generated_bullets = (output_dir / "generated_bullets.csv").read_text(encoding="utf-8")
    assert "unrelated_sales_role,sales_quota,evidence_grounded" not in generated_bullets


@pytest.mark.asyncio
async def test_resume_tailoring_eval_can_skip_boilerplate_requirements_with_cleaner(tmp_path: Path):
    output_dir = tmp_path / "resume-tailoring-evidence-eval-cleaner"
    artifact = await build_resume_tailoring_evidence_eval_artifact(
        project_dir=DEFAULT_PROJECT_DIR,
        jd_cases_path=DEFAULT_JD_CASES,
        resume_path=DEFAULT_RESUME,
        output_dir=output_dir,
        k=3,
        requirement_cleaner_enabled=True,
    )

    cleaner = artifact["requirement_cleaner"]
    assert cleaner["enabled"] is True
    assert cleaner["skipped_unsupported_requirement_count"] >= 1
    assert cleaner["category_counts"]["sales_marketing_role"] >= 1
    skipped_rows = [row for row in artifact["requirement_results"] if row["retrieval_skipped_by_cleaner"]]
    assert skipped_rows
    assert all(not row["returned_evidence_ids"] for row in skipped_rows)


@pytest.mark.asyncio
async def test_resume_tailoring_eval_can_apply_pairwise_support_verifier(tmp_path: Path):
    output_dir = tmp_path / "resume-tailoring-evidence-eval-support"
    artifact = await build_resume_tailoring_evidence_eval_artifact(
        project_dir=DEFAULT_PROJECT_DIR,
        jd_cases_path=DEFAULT_JD_CASES,
        resume_path=DEFAULT_RESUME,
        output_dir=output_dir,
        k=3,
        support_verifier_enabled=True,
    )

    verifier = artifact["support_verifier"]
    assert verifier["enabled"] is True
    assert verifier["candidate_count"] > 0
    assert verifier["accepted_candidate_count"] > 0
    assert verifier["rejected_candidate_count"] > 0
    assert "not_enough_info" in verifier["label_counts"]
    assert all(row["support_verifier_enabled"] for row in artifact["requirement_results"])
    assert (output_dir / "report.md").read_text(encoding="utf-8").count("Pairwise Support Verifier") == 1


@pytest.mark.asyncio
async def test_resume_tailoring_eval_artifact_includes_project_doc_ingest_summary(tmp_path: Path):
    output_dir = tmp_path / "resume-tailoring-evidence-eval"
    artifact = await build_resume_tailoring_evidence_eval_artifact(
        project_dir=DEFAULT_PROJECT_DIR,
        project_doc_dirs=[DEFAULT_PROJECT_DOC_DIR],
        jd_cases_path=DEFAULT_JD_CASES,
        resume_path=DEFAULT_RESUME,
        output_dir=output_dir,
        k=3,
    )

    ingest = artifact["project_doc_ingest"]["summary"]
    assert ingest["project_doc_count"] == 1
    assert ingest["preflight_status_counts"] == {"warn": 1}
    assert ingest["evidence_card_count"] >= 6
    assert ingest["resume_safe_card_count"] >= 5
    assert ingest["excluded_section_count"] >= 2
    assert artifact["project_evidence_count"] == 9 + ingest["resume_safe_card_count"]
    assert artifact["model_calls"]["count"] == 0

    report = (output_dir / "report.md").read_text(encoding="utf-8")
    assert "Project Doc Ingest" in report
    assert (output_dir / "evidence_cards.csv").exists()


@pytest.mark.asyncio
async def test_atomic_project_doc_eval_scores_child_cards_against_parent_labels(tmp_path: Path):
    project_doc = tmp_path / "broad_project.md"
    project_doc.write_text(
        "\n".join(
            [
                "# Broad Project",
                "",
                "## Model Evaluation",
                (
                    "- Built an applied ML platform that supports FastAPI APIs, PostgreSQL data models, "
                    "LightGBM forecasting artifacts, retrieval evaluation reports, and privacy preflight checks."
                ),
            ]
        ),
        encoding="utf-8",
    )
    parent_id = extract_evidence_cards_from_markdown(project_doc).evidence_cards[0].evidence_id
    jd_cases = tmp_path / "jd_cases.json"
    jd_cases.write_text(
        json.dumps(
            [
                {
                    "id": "ml_platform_role",
                    "title": "Applied ML Engineer",
                    "job_description": "Own model artifacts and retrieval evaluation for production ML workflows.",
                    "control_type": "saved_app",
                    "expected_requirements": [
                        {
                            "id": "lightgbm_artifacts",
                            "query": "LightGBM forecasting artifacts and retrieval evaluation reports",
                            "expected_evidence_ids": [parent_id],
                            "support_label": "direct",
                            "control_type": "saved_app",
                        }
                    ],
                }
            ]
        ),
        encoding="utf-8",
    )

    artifact = await build_resume_tailoring_evidence_eval_artifact(
        project_doc_dirs=[project_doc],
        jd_cases_path=jd_cases,
        resume_path=DEFAULT_RESUME,
        output_dir=tmp_path / "atomic-eval",
        k=3,
        include_manual_project_fixtures=False,
        project_doc_granularity=PROJECT_DOC_GRANULARITY_ATOMIC,
    )

    row = artifact["requirement_results"][0]
    assert row["hit_count"] == 1
    assert parent_id in row["matched_expected_evidence_ids"]
    assert any(parent_id in aliases for aliases in row["returned_evidence_aliases"])
    assert artifact["generation_quality"]["evidence_grounded"]["missed_supported_requirement_count"] == 0


@pytest.mark.asyncio
async def test_parent_child_retrieval_uses_parent_context_and_returns_child_evidence(tmp_path: Path):
    project_doc = tmp_path / "broad_project.md"
    project_doc.write_text(
        "\n".join(
            [
                "# Broad Project",
                "",
                "## AI Evaluation Architecture",
                (
                    "- Built an applied AI platform that supports FastAPI APIs, PostgreSQL data models, "
                    "LLM policy evaluation reports, retrieval quality dashboards, and privacy preflight checks."
                ),
            ]
        ),
        encoding="utf-8",
    )
    parent_id = extract_evidence_cards_from_markdown(project_doc).evidence_cards[0].evidence_id
    jd_cases = tmp_path / "jd_cases.json"
    jd_cases.write_text(
        json.dumps(
            [
                {
                    "id": "ai_eval_role",
                    "title": "AI Evaluation Engineer",
                    "job_description": "Build LLM policy evaluation reporting and retrieval dashboards.",
                    "control_type": "saved_app",
                    "expected_requirements": [
                        {
                            "id": "policy_eval_reports",
                            "query": "LLM policy evaluation reports and retrieval quality dashboards",
                            "expected_evidence_ids": [parent_id],
                            "support_label": "direct",
                            "control_type": "saved_app",
                        }
                    ],
                }
            ]
        ),
        encoding="utf-8",
    )

    artifact = await build_resume_tailoring_evidence_eval_artifact(
        project_doc_dirs=[project_doc],
        jd_cases_path=jd_cases,
        resume_path=DEFAULT_RESUME,
        output_dir=tmp_path / "parent-child-eval",
        k=3,
        include_manual_project_fixtures=False,
        retrieval_strategy=RETRIEVAL_STRATEGY_PARENT_CHILD_LEXICAL,
    )

    row = artifact["requirement_results"][0]
    assert row["retrieval_strategy"] == RETRIEVAL_STRATEGY_PARENT_CHILD_LEXICAL
    assert parent_id in row["parent_returned_evidence_ids"]
    assert row["returned_evidence_ids"]
    assert row["returned_evidence_ids"][0] != parent_id
    assert parent_id in row["matched_expected_evidence_ids"]
    assert row["expected_parent_evidence_ids"] == [parent_id]
    assert row["expected_citation_evidence_ids"] == [parent_id]
    assert artifact["retrieval_metrics"]["parent_recall_at_k_mean"] == artifact["retrieval_metrics"]["recall_at_k_mean"]
    assert artifact["generation_quality"]["evidence_grounded"]["missed_supported_requirement_count"] == 0


@pytest.mark.asyncio
async def test_parent_child_eval_reports_citation_metrics_separately(tmp_path: Path):
    project_doc = tmp_path / "broad_project.md"
    project_doc.write_text(
        "\n".join(
            [
                "# Broad Project",
                "",
                "## AI Evaluation Architecture",
                (
                    "- Built an applied AI platform that supports FastAPI APIs, PostgreSQL data models, "
                    "LLM policy evaluation reports, retrieval quality dashboards, and privacy preflight checks."
                ),
            ]
        ),
        encoding="utf-8",
    )
    parent_id = extract_evidence_cards_from_markdown(project_doc).evidence_cards[0].evidence_id
    child_cards = extract_evidence_cards_from_markdown(project_doc, granularity=PROJECT_DOC_GRANULARITY_ATOMIC).evidence_cards
    child_id = next(card.evidence_id for card in child_cards if "LLM policy" in card.claim_text)
    jd_cases = tmp_path / "jd_cases.json"
    jd_cases.write_text(
        json.dumps(
            [
                {
                    "id": "ai_eval_role",
                    "title": "AI Evaluation Engineer",
                    "job_description": "Build LLM policy evaluation reporting and retrieval dashboards.",
                    "control_type": "saved_app",
                    "expected_requirements": [
                        {
                            "id": "policy_eval_reports",
                            "query": "LLM policy evaluation reports and retrieval quality dashboards",
                            "expected_evidence_ids": [parent_id],
                            "expected_parent_evidence_ids": [parent_id],
                            "expected_citation_evidence_ids": [child_id],
                            "support_label": "direct",
                            "control_type": "saved_app",
                        }
                    ],
                }
            ]
        ),
        encoding="utf-8",
    )

    artifact = await build_resume_tailoring_evidence_eval_artifact(
        project_doc_dirs=[project_doc],
        jd_cases_path=jd_cases,
        resume_path=DEFAULT_RESUME,
        output_dir=tmp_path / "parent-child-citation-eval",
        k=3,
        include_manual_project_fixtures=False,
        retrieval_strategy=RETRIEVAL_STRATEGY_PARENT_CHILD_LEXICAL,
    )

    row = artifact["requirement_results"][0]
    assert parent_id in row["matched_parent_expected_evidence_ids"]
    assert child_id in row["matched_citation_expected_evidence_ids"]
    assert row["citation_hit_count"] == 1
    assert row["citation_label_status"] == "labeled"
    assert artifact["retrieval_metrics"]["requirements_with_expected_citation_evidence"] == 1
    assert artifact["retrieval_metrics"]["citation_recall_at_k_mean"] == 1.0
