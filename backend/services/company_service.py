"""Company upsert service — creates or updates company records from domain."""

from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.models import Company
from backend.services.company_identity import domain_to_company_name, get_logo_url, is_company_domain


async def upsert_company(db: AsyncSession, domain: str) -> Company | None:
    """Create or update a company record from domain. Returns None for platform domains."""
    if not domain or not is_company_domain(domain):
        return None

    stmt = select(Company).where(Company.domain == domain)
    result = await db.execute(stmt)
    company = result.scalar_one_or_none()

    if company:
        company.last_activity_at = datetime.now(timezone.utc)
        return company

    name = domain_to_company_name(domain) or domain.split(".")[0].title()
    logo_url = get_logo_url(domain)

    company = Company(domain=domain, name=name, logo_url=logo_url)
    db.add(company)
    await db.flush()
    return company
