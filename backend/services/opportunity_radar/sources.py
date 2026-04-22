import hashlib
import json
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.models import (
    Application,
    Company,
    CompanyTechProfile,
    CompanyVisit,
    ResearchProfile,
)
from .schemas import SourceCandidate



def _hash_payload(payload: dict) -> str:
    encoded = json.dumps(payload, sort_keys=True, default=str).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


async def collect_internal_sources(db: AsyncSession, profile: ResearchProfile, user_id) -> list[SourceCandidate]:
    candidates: list[SourceCandidate] = []
    selected_companies = {c.lower().strip() for c in (profile.selected_companies or []) if isinstance(c, str) and c.strip()}
    enabled_source_types = {s.lower().strip() for s in (profile.source_types or []) if isinstance(s, str) and s.strip()}
    if not enabled_source_types:
        enabled_source_types = {"application", "company_visit", "company_tech"}

    apps = []
    if "application" in enabled_source_types:
        app_stmt = select(Application).where(Application.user_id == user_id)
        apps = (await db.execute(app_stmt)).scalars().all()
    user_company_ids: set = set()
    user_company_domains: set[str] = set()
    for app in apps:
        company_key = app.company.lower().strip()
        if selected_companies and company_key not in selected_companies:
            continue

        payload = {
            "company": app.company,
            "role_title": app.role_title,
            "job_url": app.job_url,
            "status": app.status,
            "applied_at": app.applied_at.isoformat() if app.applied_at else None,
        }
        if app.company_id:
            user_company_ids.add(app.company_id)
        url = app.job_url or f"apptrail://applications/{app.id}"
        candidates.append(
            SourceCandidate(
                source_type="application",
                source_name="internal_application",
                source_url=url,
                external_id=str(app.id),
                title=f"{app.company} — {app.role_title}",
                raw_text=app.description_text,
                raw_json=payload,
                company_domain=None,
                company_name=app.company,
                role_title=app.role_title,
                published_at=app.applied_at,
                content_hash=_hash_payload(payload),
            )
        )

    visits = []
    if "company_visit" in enabled_source_types:
        visit_stmt = select(CompanyVisit).where(CompanyVisit.user_id == user_id)
        visits = (await db.execute(visit_stmt)).scalars().all()
    for visit in visits:
        domain_key = (visit.domain or "").lower().strip()
        if selected_companies and domain_key not in selected_companies:
            continue
        if domain_key:
            user_company_domains.add(domain_key)

        payload = {
            "domain": visit.domain,
            "visit_count": visit.visit_count,
            "last_visited_at": visit.last_visited_at.isoformat() if visit.last_visited_at else None,
        }
        candidates.append(
            SourceCandidate(
                source_type="company_visit",
                source_name="internal_company_visit",
                source_url=visit.url or f"https://{visit.domain}",
                external_id=str(visit.id),
                title=f"Career page visits for {visit.domain}",
                raw_text=None,
                raw_json=payload,
                company_domain=visit.domain,
                company_name=visit.domain,
                role_title=None,
                published_at=visit.last_visited_at,
                content_hash=_hash_payload(payload),
            )
        )

    if "company_tech" not in enabled_source_types:
        return candidates

    tech_stmt = select(CompanyTechProfile, Company).join(Company, Company.id == CompanyTechProfile.company_id)
    if user_company_ids:
        tech_stmt = tech_stmt.where(CompanyTechProfile.company_id.in_(user_company_ids))
    elif user_company_domains:
        tech_stmt = tech_stmt.where(Company.domain.in_(user_company_domains))
    elif selected_companies:
        tech_stmt = tech_stmt.where(Company.domain.in_(selected_companies))
    else:
        return candidates
    tech_rows = (await db.execute(tech_stmt)).all()
    for tech, company in tech_rows:
        payload = {
            "company": company.name,
            "domain": company.domain,
            "tech_name": tech.tech_name,
            "category": tech.category,
            "mention_count": tech.mention_count,
            "last_seen_at": tech.last_seen_at.isoformat() if tech.last_seen_at else None,
        }
        candidates.append(
            SourceCandidate(
                source_type="company_tech",
                source_name="internal_company_tech",
                source_url=f"apptrail://companies/{company.domain}/tech/{tech.id}",
                external_id=str(tech.id),
                title=f"{company.name} tech signal: {tech.tech_name}",
                raw_text=f"{company.name} mentioned {tech.tech_name}",
                raw_json=payload,
                company_domain=company.domain,
                company_name=company.name,
                role_title=None,
                published_at=tech.last_seen_at or datetime.now(timezone.utc),
                content_hash=_hash_payload(payload),
            )
        )

    return candidates
