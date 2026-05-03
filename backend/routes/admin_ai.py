from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from backend.database import get_db
from backend.dependencies import require_admin_user
from backend.models import AiPromotionReport, User
from backend.services import admin_ai
from backend.services.feature_flags import admin_ai_ops_enabled
from backend.services.promotion_reports import approve_promotion_report, reject_promotion_report


def require_admin_ai_ops_enabled():
    if not admin_ai_ops_enabled():
        raise HTTPException(status_code=404, detail="AI Ops is disabled")


router = APIRouter(prefix="/api/admin/ai", tags=["admin-ai"], dependencies=[Depends(require_admin_ai_ops_enabled)])


class TraceAccessPayload(BaseModel):
    reason: str = Field(min_length=8, max_length=500)


async def _get_report(db: AsyncSession, report_id: str) -> AiPromotionReport:
    try:
        rid = uuid.UUID(report_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail="Promotion report not found") from exc
    report = await db.get(AiPromotionReport, rid)
    if report is None:
        raise HTTPException(status_code=404, detail="Promotion report not found")
    return report


@router.post("/promotion-reports/{report_id}/approve")
async def approve_report(
    report_id: str,
    db: AsyncSession = Depends(get_db),
    admin: User = Depends(require_admin_user),
):
    report = await _get_report(db, report_id)
    await approve_promotion_report(db, report=report, admin_user_id=admin.id)
    await db.commit()
    await db.refresh(report)
    return {"report_id": str(report.id), "status": report.status, "recommendation": report.recommendation}


@router.get("/telemetry")
async def telemetry(
    db: AsyncSession = Depends(get_db),
    _admin: User = Depends(require_admin_user),
):
    return await admin_ai.telemetry_overview(db)


@router.get("/runs")
async def runs(
    limit: int = 50,
    surface: str | None = None,
    task_name: str | None = None,
    db: AsyncSession = Depends(get_db),
    _admin: User = Depends(require_admin_user),
):
    return {"runs": await admin_ai.list_runs(db, limit=min(max(limit, 1), 100), surface=surface, task_name=task_name)}


@router.get("/runs/{call_id}")
async def run_detail(
    call_id: str,
    db: AsyncSession = Depends(get_db),
    _admin: User = Depends(require_admin_user),
):
    try:
        cid = uuid.UUID(call_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail="AI run not found") from exc
    detail = await admin_ai.run_detail(db, call_id=cid)
    if detail is None:
        raise HTTPException(status_code=404, detail="AI run not found")
    return detail


@router.post("/runs/{call_id}/trace-access")
async def trace_access(
    call_id: str,
    payload: TraceAccessPayload,
    db: AsyncSession = Depends(get_db),
    admin: User = Depends(require_admin_user),
):
    try:
        cid = uuid.UUID(call_id)
        detail = await admin_ai.full_trace_with_access_log(db, call_id=cid, admin_user_id=admin.id, reason=payload.reason)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    if detail is None:
        raise HTTPException(status_code=404, detail="AI run not found")
    await db.commit()
    return detail


@router.get("/artifacts")
async def artifacts(
    limit: int = 50,
    db: AsyncSession = Depends(get_db),
    _admin: User = Depends(require_admin_user),
):
    return {"artifacts": await admin_ai.list_artifacts(db, limit=min(max(limit, 1), 100))}


@router.get("/experiments")
async def experiments(
    db: AsyncSession = Depends(get_db),
    _admin: User = Depends(require_admin_user),
):
    return {"experiments": await admin_ai.list_experiments(db)}


@router.get("/model-cards")
async def model_cards(
    db: AsyncSession = Depends(get_db),
    _admin: User = Depends(require_admin_user),
):
    return {"model_cards": await admin_ai.list_model_cards(db)}


@router.get("/promotion-reports")
async def promotion_reports(
    db: AsyncSession = Depends(get_db),
    _admin: User = Depends(require_admin_user),
):
    return {"promotion_reports": await admin_ai.list_promotion_reports(db)}


@router.get("/trace-access-logs")
async def trace_access_logs(
    limit: int = 50,
    db: AsyncSession = Depends(get_db),
    _admin: User = Depends(require_admin_user),
):
    return {"access_logs": await admin_ai.list_trace_access_logs(db, limit=min(max(limit, 1), 100))}


@router.get("/safety-decisions")
async def safety_decisions(
    limit: int = 50,
    surface: str | None = None,
    task_name: str | None = None,
    policy_decision: str | None = None,
    stage: str | None = None,
    min_risk: float | None = None,
    db: AsyncSession = Depends(get_db),
    _admin: User = Depends(require_admin_user),
):
    return {
        "safety_decisions": await admin_ai.list_safety_decisions(
            db,
            limit=min(max(limit, 1), 100),
            surface=surface,
            task_name=task_name,
            policy_decision=policy_decision,
            stage=stage,
            min_risk=min_risk,
        )
    }


@router.post("/promotion-reports/{report_id}/reject")
async def reject_report(
    report_id: str,
    db: AsyncSession = Depends(get_db),
    admin: User = Depends(require_admin_user),
):
    report = await _get_report(db, report_id)
    await reject_promotion_report(db, report=report, admin_user_id=admin.id)
    await db.commit()
    await db.refresh(report)
    return {"report_id": str(report.id), "status": report.status, "recommendation": report.recommendation}
