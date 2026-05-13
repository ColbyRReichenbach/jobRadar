from pathlib import Path

from backend.services.ai_retention import reprocessing_policy_snapshot


def test_reprocessing_policy_preserves_audit_lineage_and_requires_review():
    policy = reprocessing_policy_snapshot()

    assert policy["requires_new_model_call"] is True
    assert policy["preserve_original_artifacts"] is True
    assert policy["promotion_requires_admin_review"] is True
    assert policy["rollback_requires_previous_model_card"] is True
    assert policy["shadow_outputs_visible_to_user"] is False
    assert "success" in policy["allowed_source_statuses"]
    assert "failure" in policy["allowed_reprocess_statuses"]


def test_reprocessing_policy_is_documented_for_ai_system_review():
    doc = Path("docs/ai-artifacts/model-risk-management.md")
    assert doc.exists()
    text = doc.read_text()

    required_terms = [
        "new model call",
        "preserve the original artifact",
        "admin review",
        "rollback",
        "shadow outputs are not user-visible",
    ]
    for term in required_terms:
        assert term in text
