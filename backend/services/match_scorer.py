"""Match scoring: compare user profile skills against job requirements."""

from typing import Any


def score_match(profile: dict[str, Any], job_tech_stack: list[str], job_description: str = "") -> dict[str, Any]:
    """Score how well a user profile matches a job.

    Returns:
        {
            "score": 0-100 overall match,
            "breakdown": {"skills": 0-100, "tools": 0-100},
            "matched_skills": [...],
            "missing_skills": [...],
            "transferable_skills": [...]
        }
    """
    user_skills = set(s.lower() for s in (profile.get("skills") or []))
    user_tools = set(t.lower() for t in (profile.get("tools") or []))
    all_user_tech = user_skills | user_tools

    job_skills = set(s.lower() for s in job_tech_stack)

    if not job_skills:
        # If no tech stack extracted, try extracting from description
        if job_description:
            from backend.services.tech_extractor import extract_tech_stack
            extracted = extract_tech_stack(job_description)
            job_skills = set(t["name"].lower() for t in extracted)

    if not job_skills:
        return {
            "score": 0,
            "breakdown": {"skills": 0, "tools": 0},
            "matched_skills": [],
            "missing_skills": [],
            "transferable_skills": [],
        }

    matched = all_user_tech & job_skills
    missing = job_skills - all_user_tech

    # Skills score: what % of job requirements does user have
    skills_score = int((len(matched) / len(job_skills)) * 100) if job_skills else 0

    # Find transferable skills (user has but job doesn't list, from same category)
    from backend.services.tech_extractor import TECH_CATEGORIES
    # Build reverse map: tech_name.lower() -> category
    _tech_to_cat: dict[str, str] = {}
    for cat, techs in TECH_CATEGORIES.items():
        for t in techs:
            _tech_to_cat[t.lower()] = cat

    job_categories = set()
    for skill in job_skills:
        cat = _tech_to_cat.get(skill)
        if cat:
            job_categories.add(cat)

    transferable = []
    for skill in (all_user_tech - job_skills):
        cat = _tech_to_cat.get(skill)
        if cat and cat in job_categories:
            transferable.append(skill)

    # Overall score: skills are 100% of the signal for now
    overall = skills_score

    return {
        "score": overall,
        "breakdown": {"skills": skills_score, "tools": skills_score},
        "matched_skills": sorted(matched),
        "missing_skills": sorted(missing),
        "transferable_skills": sorted(transferable[:10]),
    }
