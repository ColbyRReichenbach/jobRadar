from backend.services.job_sources.base import NormalizedJobPosting
from backend.services.job_sources.role_matcher import expand_role_query, rank_postings


def _posting(title: str, location: str = "Remote") -> NormalizedJobPosting:
    return NormalizedJobPosting(
        external_job_id=title,
        title=title,
        company_name="Acme",
        company_domain="acme.com",
        description_text=None,
        location_text=location,
        remote_status=None,
        employment_type=None,
        department=None,
        salary_min=None,
        salary_max=None,
        salary_currency=None,
        salary_period=None,
        date_posted=None,
        valid_through=None,
        canonical_url=f"https://example.com/{title}",
        source_type="greenhouse",
        source_confidence=0.9,
        redacted_metadata={},
    )


def test_analyst_expansion_avoids_investment_without_finance_domain():
    expanded = expand_role_query("analyst")

    assert "data analyst" in expanded
    assert "business analyst" in expanded
    assert "investment analyst" not in expanded


def test_role_matcher_ranks_family_and_location():
    matches = rank_postings(
        [_posting("Product Analyst", "Charlotte"), _posting("Senior Recruiter", "Remote")],
        "analyst",
        location="Charlotte",
    )

    assert matches[0].posting.title == "Product Analyst"
    assert "role_family_match" in matches[0].reasons or "title_similarity" in matches[0].reasons
    assert "location_match" in matches[0].reasons

