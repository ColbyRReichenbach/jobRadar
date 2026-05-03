from __future__ import annotations

from sqlalchemy import select

from backend.models import Application, CompanyVisit, ResearchProfile, ResearchReport, RoleUmbrella, User, UserProfile, UserRoleInterest


async def load_tracker_context(state):
    db = state["db"]
    profile = (
        await db.execute(select(ResearchProfile).where(ResearchProfile.id == state["profile_id"]))
    ).scalars().first()
    user = (
        await db.execute(select(User).where(User.id == state["user_id"]))
    ).scalars().first()
    user_profile = (
        await db.execute(select(UserProfile).where(UserProfile.user_id == state["user_id"]))
    ).scalars().first()
    interests = (
        await db.execute(
            select(UserRoleInterest, RoleUmbrella)
            .join(RoleUmbrella, UserRoleInterest.umbrella_id == RoleUmbrella.id)
            .where(UserRoleInterest.user_id == state["user_id"])
        )
    ).all()
    recent_apps = (
        await db.execute(
            select(Application)
            .where(Application.user_id == state["user_id"])
            .order_by(Application.applied_at.desc())
            .limit(10)
        )
    ).scalars().all()
    company_visits = (
        await db.execute(
            select(CompanyVisit)
            .where(CompanyVisit.user_id == state["user_id"])
            .order_by(CompanyVisit.last_visited_at.desc())
            .limit(10)
        )
    ).scalars().all()
    previous_report = (
        await db.execute(
            select(ResearchReport)
            .where(
                ResearchReport.user_id == state["user_id"],
                ResearchReport.profile_id == state["profile_id"],
            )
            .order_by(ResearchReport.report_date.desc())
            .limit(1)
        )
    ).scalars().first()

    tracker = {
        "id": str(profile.id),
        "name": profile.name,
        "objective": profile.objective,
        "selected_domains": profile.selected_domains or [],
        "selected_roles": profile.selected_roles or [],
        "selected_companies": profile.selected_companies or [],
        "keywords": profile.keywords or [],
        "excluded_keywords": profile.excluded_keywords or [],
        "source_types": profile.source_types or [],
        "mode": profile.mode,
        "frequency": profile.frequency,
        "depth": profile.depth,
        "notification_mode": profile.notification_mode,
        "minimum_score": profile.minimum_score,
        "target_locations": profile.target_locations or [],
        "remote_types": profile.remote_types or [],
        "seniority_levels": profile.seniority_levels or [],
        "research_source_scopes": profile.research_source_scopes or [],
        "use_profile_context": profile.use_profile_context,
        "include_public_web_research": profile.include_public_web_research,
        "report_prompt_notes": profile.report_prompt_notes,
        "max_search_queries": profile.max_search_queries,
        "max_sources_per_run": profile.max_sources_per_run,
    }
    user_context = {
        "email": user.email if user else None,
        "name": user.name if user else None,
        "preferred_locations": (user.preferred_locations if user else None) or [],
        "preferred_remote_type": user.preferred_remote_type if user else None,
        "target_salary_min": user.target_salary_min if user else None,
        "target_salary_max": user.target_salary_max if user else None,
        "skills": (user_profile.skills if user_profile else None) or [],
        "tools": (user_profile.tools if user_profile else None) or [],
        "certifications": (user_profile.certifications if user_profile else None) or [],
        "experience_years": user_profile.experience_years if user_profile else None,
        "raw_profile_text": user_profile.raw_text if user_profile else None,
        "role_interest_labels": [role.name for _, role in interests],
        "recent_applications": [
            {
                "company": app.company,
                "role_title": app.role_title,
                "status": app.status,
                "job_url": app.job_url,
                "applied_at": app.applied_at.isoformat() if app.applied_at else None,
            }
            for app in recent_apps
        ],
        "company_visits": [
            {
                "domain": visit.domain,
                "url": visit.url,
                "visit_count": visit.visit_count,
                "last_visited_at": visit.last_visited_at.isoformat() if visit.last_visited_at else None,
            }
            for visit in company_visits
        ],
        "previous_report": {
            "id": str(previous_report.id),
            "title": previous_report.title,
            "report_date": previous_report.report_date.isoformat() if previous_report.report_date else None,
            "structured_json": previous_report.structured_json or {},
            "summary_markdown": previous_report.summary_markdown,
        } if previous_report else None,
    }

    return {
        "tracker": tracker,
        "user_context": user_context,
    }
