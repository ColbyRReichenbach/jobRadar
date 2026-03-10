"""Sprint 8: ATS behavioral intelligence — aggregate patterns per ATS platform."""

from datetime import datetime, timezone

from sqlalchemy import func, select, case
from sqlalchemy.ext.asyncio import AsyncSession

from backend.models import Application, AtsBehavior, Company, EmailEvent


async def compute_ats_metrics(db: AsyncSession) -> list[dict]:
    """Compute behavioral metrics per ATS platform from existing data.

    Metrics computed:
    - avg_response_days: average days between applied_at and first email
    - rejection_rate: % of applications that ended in rejection
    - ghosting_rate: % with no response after 14+ days
    """
    # Get all companies with a known ATS platform
    stmt = (
        select(Company.ats_platform, func.count(Application.id))
        .join(Application, Application.company_id == Company.id)
        .where(Company.ats_platform.isnot(None))
        .group_by(Company.ats_platform)
    )
    result = await db.execute(stmt)
    platform_counts = {row[0]: row[1] for row in result.all()}

    metrics = []

    for platform, total_apps in platform_counts.items():
        if total_apps < 1:
            continue

        # Rejection rate
        rejected_stmt = (
            select(func.count(Application.id))
            .join(Company, Company.id == Application.company_id)
            .where(
                Company.ats_platform == platform,
                Application.status == "rejected",
            )
        )
        rejected_result = await db.execute(rejected_stmt)
        rejected_count = rejected_result.scalar() or 0
        rejection_rate = (rejected_count / total_apps) * 100

        # Ghosting rate: applied 14+ days ago, no emails, not rejected/offer
        from datetime import timedelta
        cutoff = datetime.now(timezone.utc) - timedelta(days=14)
        ghost_stmt = (
            select(func.count(Application.id))
            .join(Company, Company.id == Application.company_id)
            .where(
                Company.ats_platform == platform,
                Application.applied_at < cutoff,
                Application.last_email_at.is_(None),
                Application.status.in_(["applied", "saved"]),
                Application.archived_at.is_(None),
            )
        )
        ghost_result = await db.execute(ghost_stmt)
        ghost_count = ghost_result.scalar() or 0
        ghosting_rate = (ghost_count / total_apps) * 100

        # Average response days (for apps that got at least one email)
        avg_resp_stmt = (
            select(
                func.avg(
                    func.julianday(Application.last_email_at) - func.julianday(Application.applied_at)
                )
            )
            .join(Company, Company.id == Application.company_id)
            .where(
                Company.ats_platform == platform,
                Application.last_email_at.isnot(None),
            )
        )
        avg_resp_result = await db.execute(avg_resp_stmt)
        avg_days = avg_resp_result.scalar()
        avg_response_days = round(avg_days, 1) if avg_days else None

        platform_metrics = [
            {"metric_name": "rejection_rate", "value": round(rejection_rate, 1), "sample_size": total_apps},
            {"metric_name": "ghosting_rate", "value": round(ghosting_rate, 1), "sample_size": total_apps},
        ]
        if avg_response_days is not None:
            platform_metrics.append({
                "metric_name": "avg_response_days",
                "value": avg_response_days,
                "sample_size": total_apps,
            })

        for m in platform_metrics:
            metrics.append({"platform": platform, **m})

        # Upsert into ats_behaviors table
        for m in platform_metrics:
            existing_stmt = select(AtsBehavior).where(
                AtsBehavior.platform == platform,
                AtsBehavior.metric_name == m["metric_name"],
            )
            existing_result = await db.execute(existing_stmt)
            existing = existing_result.scalar_one_or_none()
            if existing:
                existing.metric_value = m["value"]
                existing.sample_size = m["sample_size"]
                existing.last_updated = datetime.now(timezone.utc)
            else:
                db.add(AtsBehavior(
                    platform=platform,
                    metric_name=m["metric_name"],
                    metric_value=m["value"],
                    sample_size=m["sample_size"],
                ))

    await db.commit()
    return metrics


async def get_platform_profile(db: AsyncSession, platform: str) -> dict:
    """Get the behavioral profile for a specific ATS platform."""
    stmt = select(AtsBehavior).where(AtsBehavior.platform == platform)
    result = await db.execute(stmt)
    behaviors = result.scalars().all()

    metrics = {}
    for b in behaviors:
        metrics[b.metric_name] = {
            "value": b.metric_value,
            "sample_size": b.sample_size,
            "last_updated": b.last_updated.isoformat() if b.last_updated else None,
        }

    # Generate insight text
    insights = []
    if "avg_response_days" in metrics:
        days = metrics["avg_response_days"]["value"]
        insights.append(f"{platform} companies typically respond in {days} days")
    if "rejection_rate" in metrics:
        rate = metrics["rejection_rate"]["value"]
        insights.append(f"{rate}% rejection rate across {metrics['rejection_rate']['sample_size']} applications")
    if "ghosting_rate" in metrics:
        rate = metrics["ghosting_rate"]["value"]
        if rate > 50:
            insights.append(f"High ghosting rate ({rate}%) — consider following up proactively")

    return {
        "platform": platform,
        "metrics": metrics,
        "insights": insights,
    }
