import pytest

from backend.services.model_cards import create_model_card, get_model_card, missing_model_card_warning


@pytest.mark.asyncio
async def test_model_card_lookup_and_missing_warning(db_session):
    warning = await missing_model_card_warning(
        db_session,
        task_name="email_classifier",
        model="gpt-4o-mini",
        prompt_version="v3",
    )
    assert warning is not None
    assert "Missing model card" in warning.message

    created = await create_model_card(
        db_session,
        task_name="email_classifier",
        model="gpt-4o-mini",
        prompt_version="v3",
        intended_use="Classify job-search email into product categories.",
        prohibited_use="Do not use for legal, medical, or hiring decisions.",
        limitations="Can misclassify ambiguous recruiting-adjacent newsletters.",
        eval_dataset_version="email-classifier-v1",
        primary_metrics={"recall": 0.98},
        guardrail_metrics={"pii_leakage": 0},
        rollback_plan="Disable AI classifier and use deterministic rule fallback.",
        review_cadence="monthly",
    )
    await db_session.commit()

    card = await get_model_card(
        db_session,
        task_name="email_classifier",
        model="gpt-4o-mini",
        prompt_version="v3",
    )
    assert card.id == created.id
    assert card.approval_status == "draft"
    assert card.primary_metrics["recall"] == 0.98

    warning = await missing_model_card_warning(
        db_session,
        task_name="email_classifier",
        model="gpt-4o-mini",
        prompt_version="v3",
    )
    assert warning is None
