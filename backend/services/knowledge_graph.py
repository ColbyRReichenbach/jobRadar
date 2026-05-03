"""Sprint 15: Knowledge Graph retrieval layer.

Assembles full company context from all data sources into a single structured response.
"""

import logging

from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from backend.models import (
    Application, Company, Contact, EmailEvent, CompanyTechProfile,
    AtsBehavior, WarmConnection,
)
from backend.services.aggregate_privacy import (
    aggregate_min_users,
    bucket_count,
    distinct_company_user_count,
    distinct_ats_user_count,
    has_enough_contributors,
)

logger = logging.getLogger(__name__)


async def get_company_context(db: AsyncSession, domain: str, user_id=None) -> dict:
    """Assemble full company context from all data sources.

    Returns a comprehensive profile including:
    - Company identity (name, logo, industry, size)
    - Job applications
    - Contacts
    - Email history
    - Tech stack
    - ATS behavior profile
    - Response time stats
    - Warm connections
    """
    # 1. Company identity
    company_stmt = select(Company).where(Company.domain == domain)
    company_result = await db.execute(company_stmt)
    company = company_result.scalar_one_or_none()

    if not company:
        return {
            "domain": domain,
            "found": False,
            "identity": {"domain": domain},
            "applications": [],
            "contacts": [],
            "emails": [],
            "tech_stack": [],
            "ats_profile": None,
            "response_stats": {},
            "warm_connections": [],
        }

    identity = {
        "id": str(company.id),
        "domain": company.domain,
        "name": company.name,
        "logo_url": company.logo_url,
        "industry": company.industry,
        "size": company.size,
        "ats_platform": company.ats_platform,
        "first_seen_at": company.first_seen_at.isoformat() if company.first_seen_at else None,
        "last_activity_at": company.last_activity_at.isoformat() if company.last_activity_at else None,
    }

    # 2. Applications
    app_stmt = select(Application).where(
        Application.company_id == company.id
    ).order_by(Application.applied_at.desc()).limit(50)
    if user_id:
        app_stmt = app_stmt.where(Application.user_id == user_id)
    app_result = await db.execute(app_stmt)
    applications = []
    for a in app_result.scalars().all():
        applications.append({
            "id": str(a.id),
            "role_title": a.role_title,
            "status": a.status,
            "applied_at": a.applied_at.isoformat() if a.applied_at else None,
            "match_score": a.match_score,
            "listing_alive": a.listing_alive,
            "first_response_days": a.first_response_days,
        })

    # 3. Contacts
    contact_stmt = select(Contact).where(
        Contact.company_id == company.id
    ).limit(50)
    if user_id:
        contact_stmt = contact_stmt.where(Contact.user_id == user_id)
    contact_result = await db.execute(contact_stmt)
    contacts = []
    for c in contact_result.scalars().all():
        contacts.append({
            "id": str(c.id),
            "name": c.name,
            "email": c.email,
            "title": c.title,
            "source": c.source,
            "reached_out": c.reached_out,
            "response_received": c.response_received,
        })

    # 4. Email history
    email_stmt = select(EmailEvent).options(
        selectinload(EmailEvent.application)
    ).where(
        EmailEvent.company_id == company.id
    ).order_by(EmailEvent.received_at.desc()).limit(20)
    if user_id:
        email_stmt = email_stmt.where(EmailEvent.user_id == user_id)
    email_result = await db.execute(email_stmt)
    emails = []
    for e in email_result.scalars().all():
        emails.append({
            "id": str(e.id),
            "subject": e.subject,
            "sender": e.sender,
            "classification": e.classification,
            "received_at": e.received_at.isoformat() if e.received_at else None,
            "is_from_user": e.is_from_user,
        })

    # 5. Tech stack
    company_contributor_count = await distinct_company_user_count(db, company.id)
    tech_stack = []
    if has_enough_contributors(company_contributor_count):
        tech_stmt = select(CompanyTechProfile).where(
            CompanyTechProfile.company_id == company.id
        ).order_by(CompanyTechProfile.mention_count.desc())
        tech_result = await db.execute(tech_stmt)
        tech_stack = [
            {
                "name": t.tech_name,
                "category": t.category,
                "mention_bucket": bucket_count(t.mention_count),
            }
            for t in tech_result.scalars().all()
        ]

    # 6. ATS behavior profile
    ats_profile = None
    if company.ats_platform:
        ats_contributor_count = await distinct_ats_user_count(db, company.ats_platform)
        if has_enough_contributors(ats_contributor_count):
            ats_stmt = select(AtsBehavior).where(
                AtsBehavior.platform == company.ats_platform,
                AtsBehavior.sample_size >= aggregate_min_users(),
            )
            ats_result = await db.execute(ats_stmt)
            metrics = {}
            for m in ats_result.scalars().all():
                metrics[m.metric_name] = {
                    "value": m.metric_value,
                    "sample_size_bucket": bucket_count(m.sample_size),
                    "contributor_bucket": bucket_count(ats_contributor_count),
                }
            if metrics:
                ats_profile = {
                    "platform": company.ats_platform,
                    "metrics": metrics,
                    "aggregate_status": "available",
                    "minimum_user_count": aggregate_min_users(),
                }

    # 7. Response time stats
    response_stats = {}
    if applications:
        response_days = [a["first_response_days"] for a in applications if a["first_response_days"] is not None]
        if response_days:
            response_stats = {
                "avg_response_days": round(sum(response_days) / len(response_days), 1),
                "min_response_days": min(response_days),
                "max_response_days": max(response_days),
                "sample_size": len(response_days),
            }

    # 8. Warm connections
    warm_stmt = select(WarmConnection).where(
        WarmConnection.company_domain == domain
    ).order_by(WarmConnection.email_count.desc()).limit(10)
    if user_id:
        warm_stmt = warm_stmt.where(WarmConnection.user_id == user_id)
    warm_result = await db.execute(warm_stmt)
    warm_connections = [
        {
            "contact_email": w.contact_email,
            "contact_name": w.contact_name,
            "email_count": w.email_count,
            "last_interaction_at": w.last_interaction_at.isoformat() if w.last_interaction_at else None,
        }
        for w in warm_result.scalars().all()
    ]

    return {
        "domain": domain,
        "found": True,
        "identity": identity,
        "applications": applications,
        "contacts": contacts,
        "emails": emails,
        "tech_stack": tech_stack,
        "ats_profile": ats_profile,
        "response_stats": response_stats,
        "warm_connections": warm_connections,
        "summary": {
            "total_applications": len(applications),
            "total_contacts": len(contacts),
            "total_emails": len(emails),
            "tech_count": len(tech_stack),
            "has_warm_paths": len(warm_connections) > 0,
        },
    }
