from backend.models import AiAdminAccessLog, AiArtifact, AiModelCall, AiModelCard, AiModelPricing


def test_ai_ledger_schema_exposes_required_tables_and_security_columns():
    assert AiModelCall.__tablename__ == "ai_model_calls"
    assert AiArtifact.__tablename__ == "ai_artifacts"
    assert AiModelPricing.__tablename__ == "ai_model_pricing"
    assert AiModelCard.__tablename__ == "ai_model_cards"
    assert AiAdminAccessLog.__tablename__ == "ai_admin_access_logs"

    model_call_columns = AiModelCall.__table__.columns
    for column in (
        "user_id",
        "surface",
        "task_name",
        "model",
        "prompt_version",
        "status",
        "prompt_tokens",
        "cached_input_tokens",
        "reasoning_tokens",
        "output_tokens",
        "billable_input_tokens",
        "billable_output_tokens",
        "cost_estimate_cents",
        "cost_breakdown",
        "request_metadata",
        "response_metadata",
        "model_card_id",
    ):
        assert column in model_call_columns

    access_log_columns = AiAdminAccessLog.__table__.columns
    assert "reason" in access_log_columns
    assert "admin_user_id" in access_log_columns
