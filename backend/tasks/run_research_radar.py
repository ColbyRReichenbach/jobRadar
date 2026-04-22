import asyncio
import logging
from datetime import datetime, timezone
from urllib.parse import urlencode
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.celery_app import celery_app
from backend.services.opportunity_radar.action_generator import generate_actions
from backend.services.opportunity_radar.brief_generator import generate_briefs
from backend.services.opportunity_radar.signal_extractor import extract_signals
from backend.services.opportunity_radar.signal_scorer import score_signal
from backend.services.opportunity_radar.sources import collect_internal_sources

logger = logging.getLogger(__name__)


def _run_async(coro):
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


def _alert_action_url(path: str, **params: str | None) -> str:
    clean_params = {key: value for key, value in params.items() if value}
    query = urlencode(clean_params)
    return f"{path}?{query}" if query else path


async def _load_run_and_profile(db: AsyncSession, run_id: UUID):
    from backend.models import ResearchProfile, ResearchRun

    run = (
        await db.execute(select(ResearchRun).where(ResearchRun.id == run_id))
    ).scalars().first()
    if not run:
        return None, None

    profile = (
        await db.execute(select(ResearchProfile).where(ResearchProfile.id == run.profile_id))
    ).scalars().first()
    return run, profile


async def _create_step(
    db: AsyncSession,
    *,
    run_id,
    user_id,
    profile_id,
    step_name: str,
    step_order: int,
    status: str = "queued",
    input_json: dict | None = None,
    output_json: dict | None = None,
    error_message: str | None = None,
):
    from backend.models import ResearchRunStep

    step = ResearchRunStep(
        run_id=run_id,
        user_id=user_id,
        profile_id=profile_id,
        step_name=step_name,
        step_order=step_order,
        status=status,
        input_json=input_json,
        output_json=output_json,
        error_message=error_message,
        started_at=datetime.now(timezone.utc) if status == "running" else None,
        completed_at=datetime.now(timezone.utc) if status in {"succeeded", "failed"} else None,
    )
    db.add(step)
    await db.flush()
    return step


async def _mark_step(
    db: AsyncSession,
    step,
    *,
    status: str,
    output_json: dict | None = None,
    error_message: str | None = None,
) -> None:
    step.status = status
    if output_json is not None:
        step.output_json = output_json
    if error_message is not None:
        step.error_message = error_message[:2000]
    if step.started_at is None:
        step.started_at = datetime.now(timezone.utc)
    step.completed_at = datetime.now(timezone.utc)
    await db.flush()


async def _execute_internal_mode(db: AsyncSession, run, profile, *, finalize_run: bool) -> None:
    from backend.models import (
        Company,
        OpportunityBrief,
        OpportunityScore,
        OpportunitySignal,
        RecommendedAction,
        ResearchSourceItem,
    )
    from backend.services.alerts import create_user_alert

    run.current_step = "collect_internal_sources"
    await db.flush()

    collect_step = await _create_step(
        db,
        run_id=run.id,
        user_id=run.user_id,
        profile_id=profile.id,
        step_name="collect_internal_sources",
        step_order=1,
        status="running",
        input_json={
            "mode": run.mode,
            "source_types": profile.source_types or [],
        },
    )
    await db.commit()

    candidates = await collect_internal_sources(db, profile, run.user_id)
    source_items: list[ResearchSourceItem] = []
    for candidate in candidates:
        company_id = None
        if candidate.company_domain:
            company = (
                await db.execute(select(Company).where(Company.domain == candidate.company_domain))
            ).scalars().first()
            if company:
                company_id = company.id

        existing_stmt = select(ResearchSourceItem).where(
            ResearchSourceItem.user_id == run.user_id,
            ResearchSourceItem.source_url == candidate.source_url,
            ResearchSourceItem.content_hash == candidate.content_hash,
        )
        existing = (await db.execute(existing_stmt)).scalars().first()
        if existing:
            source_items.append(existing)
            continue

        item = ResearchSourceItem(
            run_id=run.id,
            user_id=run.user_id,
            profile_id=profile.id,
            company_id=company_id,
            source_type=candidate.source_type,
            source_name=candidate.source_name,
            source_url=candidate.source_url,
            external_id=candidate.external_id,
            title=candidate.title,
            raw_text=candidate.raw_text,
            raw_json=candidate.raw_json,
            published_at=candidate.published_at,
            content_hash=candidate.content_hash,
        )
        db.add(item)
        source_items.append(item)

    await db.flush()
    await _mark_step(
        db,
        collect_step,
        status="succeeded",
        output_json={"source_count": len(source_items)},
    )

    run.current_step = "process_internal_signals"
    process_step = await _create_step(
        db,
        run_id=run.id,
        user_id=run.user_id,
        profile_id=profile.id,
        step_name="process_internal_signals",
        step_order=2,
        status="running",
        input_json={"source_count": len(source_items), "minimum_score": profile.minimum_score},
    )
    await db.commit()

    signal_counter: dict[str, int] = {}
    action_count = 0
    for item in source_items:
        generated = extract_signals(
            item,
            user_id=run.user_id,
            profile_id=profile.id,
            run_id=run.id,
            company_id=item.company_id,
        )
        for signal in generated:
            duplicate_stmt = select(OpportunitySignal).where(
                OpportunitySignal.user_id == run.user_id,
                OpportunitySignal.source_item_id == item.id,
                OpportunitySignal.event_type == signal.event_type,
            )
            existing_signal = (await db.execute(duplicate_stmt)).scalars().first()
            if existing_signal:
                continue

            db.add(signal)
            await db.flush()

            scoring = score_signal(signal, profile=profile)
            score_row = OpportunityScore(
                signal_id=signal.id,
                user_id=run.user_id,
                profile_id=profile.id,
                **scoring,
            )
            db.add(score_row)

            brief_payload = generate_briefs(signal, scoring)
            brief = OpportunityBrief(
                user_id=run.user_id,
                profile_id=profile.id,
                run_id=run.id,
                signal_id=signal.id,
                **brief_payload,
            )
            db.add(brief)
            await db.flush()

            for action_payload in generate_actions(signal, scoring):
                db.add(
                    RecommendedAction(
                        user_id=run.user_id,
                        profile_id=profile.id,
                        signal_id=signal.id,
                        brief_id=brief.id,
                        company_id=signal.company_id,
                        action_type=action_payload["action_type"],
                        title=action_payload["title"],
                        body=action_payload.get("body"),
                        payload=action_payload.get("payload"),
                        priority=action_payload.get("priority", 50),
                    )
                )
                action_count += 1

            if scoring["total_score"] >= max(profile.minimum_score, 85):
                await create_user_alert(
                    db,
                    user_id=run.user_id,
                    alert_type="opportunity_signal",
                    title=f"Radar signal: {signal.title}",
                    body=signal.summary,
                    action_url=_alert_action_url("/radar", profile_id=str(profile.id), signal_id=str(signal.id)),
                )

            signal_counter[signal.event_type] = signal_counter.get(signal.event_type, 0) + 1

    run.source_counts = {"total": len(source_items)}
    run.signal_counts = signal_counter
    if finalize_run:
        run.status = "succeeded"
        run.current_step = "completed"
        run.completed_at = datetime.now(timezone.utc)
        profile.last_run_at = run.completed_at
        profile.last_successful_run_at = run.completed_at
    await _mark_step(
        db,
        process_step,
        status="succeeded",
        output_json={
            "signal_counts": signal_counter,
            "action_count": action_count,
        },
    )
    await db.commit()


async def execute_research_run(db: AsyncSession, run_id: UUID) -> None:
    from backend.models import ResearchRun, ResearchRunStep
    from backend.services.alerts import create_user_alert
    from backend.services.research_radar import run_research_graph

    run, profile = await _load_run_and_profile(db, run_id)
    if not run or not profile:
        logger.warning("Research run %s could not be loaded", run_id)
        return
    if run.status not in {"queued", "retrying"}:
        logger.info("Research run %s already in terminal/non-queue state %s", run_id, run.status)
        return

    run.status = "running"
    run.mode = run.mode or profile.mode
    run.started_at = run.started_at or datetime.now(timezone.utc)
    run.current_step = "dispatch"
    run.error_message = None
    await db.commit()

    try:
        if run.mode in {"internal", "hybrid"}:
            await _execute_internal_mode(db, run, profile, finalize_run=run.mode == "internal")

        if run.mode in {"research", "hybrid"}:
            await run_research_graph(
                db,
                run_id=run.id,
                profile_id=profile.id,
                user_id=run.user_id,
                mode=run.mode,
                trigger=run.trigger_reason or run.run_type,
            )

            run, profile = await _load_run_and_profile(db, run_id)
            if run and profile:
                profile.last_run_at = run.completed_at or datetime.now(timezone.utc)
                if run.status in {"published", "ready"}:
                    profile.last_successful_run_at = profile.last_run_at
                await db.commit()
    except Exception as exc:
        await db.rollback()
        run, profile = await _load_run_and_profile(db, run_id)
        if not run:
            return

        pending_step = (
            await db.execute(
                select(ResearchRunStep).where(
                    ResearchRunStep.run_id == run.id,
                    ResearchRunStep.status == "running",
                ).order_by(ResearchRunStep.step_order.desc())
            )
        ).scalars().first()
        if pending_step:
            await _mark_step(
                db,
                pending_step,
                status="failed",
                error_message=str(exc),
                output_json=pending_step.output_json or {},
            )

        failed_step_name = pending_step.step_name if pending_step else (run.status_detail or {}).get("failed_step") or run.current_step
        run.status = "failed"
        run.error_message = str(exc)[:2000]
        run.current_step = failed_step_name
        run.status_detail = {
            "failed_step": failed_step_name,
        }
        run.completed_at = datetime.now(timezone.utc)
        await create_user_alert(
            db,
            user_id=run.user_id,
            alert_type="research_run_failed",
            title=f"Radar run failed for {profile.name if profile else 'tracker'}",
            body=run.error_message,
            action_url=_alert_action_url("/radar", profile_id=str(run.profile_id)),
        )
        await db.commit()
        logger.exception("Research run %s failed", run_id)


async def execute_research_run_with_new_session(run_id: UUID) -> None:
    from backend.database import async_session_factory

    async with async_session_factory() as db:
        await execute_research_run(db, run_id)


async def dispatch_due_research_profiles_async() -> int:
    from backend.database import async_session_factory
    from backend.models import ResearchProfile, ResearchRun

    async with async_session_factory() as db:
        now = datetime.now(timezone.utc)
        due_profiles = (
            await db.execute(
                select(ResearchProfile).where(
                    ResearchProfile.active == True,
                    ResearchProfile.next_run_at.isnot(None),
                    ResearchProfile.next_run_at <= now,
                )
            )
        ).scalars().all()

        queued = 0
        queued_run_ids: list[str] = []
        for profile in due_profiles:
            run = ResearchRun(
                user_id=profile.user_id,
                profile_id=profile.id,
                run_type="scheduled",
                mode=profile.mode,
                trigger_reason="scheduled_due",
                status="queued",
            )
            db.add(run)
            await db.flush()
            queued_run_ids.append(str(run.id))
            queued += 1

        if queued:
            await db.commit()
            for run_id in queued_run_ids:
                run_research_radar.delay(run_id)
        return queued


@celery_app.task(bind=True, max_retries=3)
def run_research_radar(self, run_id: str):
    try:
        return _run_async(execute_research_run_with_new_session(UUID(run_id)))
    except Exception as exc:
        logger.error("Research radar task failed for %s: %s", run_id, exc)
        raise self.retry(exc=exc, countdown=60 * (2 ** self.request.retries))


@celery_app.task(bind=True, max_retries=3)
def dispatch_due_research_profiles(self):
    try:
        return _run_async(dispatch_due_research_profiles_async())
    except Exception as exc:
        logger.error("Research dispatcher task failed: %s", exc)
        raise self.retry(exc=exc, countdown=60 * (2 ** self.request.retries))
