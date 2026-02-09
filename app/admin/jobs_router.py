from datetime import datetime, timedelta
from fastapi import APIRouter, Depends, Request, HTTPException, Query
from fastapi.responses import HTMLResponse
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, or_

from app.api.deps import get_db, require_admin
from app.models.job import Job
from app.models.user import User
from app.models.workflow import Workflow
from app.models.job_execution import JobExecution
from app.models.comfy_node import ComfyNode
from app.core.templates import templates


router = APIRouter(prefix="/admin/jobs", tags=["admin-jobs"])


@router.get("/health", response_class=HTMLResponse)
async def admin_jobs_health(
    request: Request,
    db: AsyncSession = Depends(get_db),
    admin: User = Depends(require_admin),
    minutes: int = Query(default=60, ge=5, le=24*60),
):
    since = datetime.now() - timedelta(minutes=minutes)

    # Jobs stats (за последние N минут)
    jobs_stats_rows = (await db.execute(
        select(Job.status, func.count(Job.id))
        .where(Job.created_at >= since)
        .group_by(Job.status)
    )).all()
    jobs_stats = {status: cnt for status, cnt in jobs_stats_rows}

    # Active queue: сколько QUEUED/RUNNING сейчас (в целом)
    live_rows = (await db.execute(
        select(Job.status, func.count(Job.id))
        .where(Job.status.in_(["QUEUED", "RUNNING"]))
        .group_by(Job.status)
    )).all()
    live_stats = {status: cnt for status, cnt in live_rows}

    # Nodes list
    nodes = (await db.execute(
        select(ComfyNode).order_by(ComfyNode.is_active.desc(), ComfyNode.priority.asc(), ComfyNode.id.asc())
    )).scalars().all()

    # Per-node queue (по executions)
    # сколько executions QUEUED/RUNNING на каждом node_id
    per_node_rows = (await db.execute(
        select(JobExecution.node_id, JobExecution.status, func.count(JobExecution.id))
        .where(JobExecution.status.in_(["QUEUED", "RUNNING"]))
        .group_by(JobExecution.node_id, JobExecution.status)
    )).all()

    per_node = {}
    for node_id, st, cnt in per_node_rows:
        per_node.setdefault(node_id, {})[st] = cnt

    return templates.TemplateResponse(
        "/admin/jobs/health.html",
        {
            "request": request,
            "user": admin,
            "minutes": minutes,
            "since": since,
            "jobs_stats": jobs_stats,
            "live_stats": live_stats,
            "nodes": nodes,
            "per_node": per_node,
        },
    )


@router.get("/", response_class=HTMLResponse)
async def admin_jobs_list(
    request: Request,
    db: AsyncSession = Depends(get_db),
    admin: User = Depends(require_admin),

    status: str | None = Query(default=None),
    q: str | None = Query(default=None),
    workflow: str | None = Query(default=None),  # slug
    user: str | None = Query(default=None),      # email or id(int)

    limit: int = Query(default=50, ge=10, le=200),
    offset: int = Query(default=0, ge=0),
):
    stmt = (
        select(Job, User, Workflow)
        .join(User, User.id == Job.user_id)
        .join(Workflow, Workflow.id == Job.workflow_id)
    )

    if status:
        stmt = stmt.where(Job.status == status)

    if workflow:
        stmt = stmt.where(Workflow.slug == workflow)

    if user:
        # если числом — user_id, иначе email
        if user.isdigit():
            stmt = stmt.where(Job.user_id == int(user))
        else:
            stmt = stmt.where(User.email.ilike(f"%{user}%"))

    if q:
        qq = f"%{q}%"
        stmt = stmt.where(
            or_(
                Job.id.ilike(qq),
                User.email.ilike(qq),
                Workflow.slug.ilike(qq),
                Workflow.name.ilike(qq),
            )
        )

    # total для пагинации (через subquery от уже отфильтрованного stmt)
    total_stmt = select(func.count()).select_from(stmt.with_only_columns(Job.id).subquery())
    total = (await db.execute(total_stmt)).scalar_one()

    stmt = stmt.order_by(Job.created_at.desc()).limit(limit).offset(offset)
    jobs = (await db.execute(stmt)).all()

    return templates.TemplateResponse(
        "/admin/jobs/list.html",
        {
            "request": request,
            "user": admin,
            "jobs": jobs,
            "total": total,
            "limit": limit,
            "offset": offset,
            "filters": {
                "status": status or "",
                "q": q or "",
                "workflow": workflow or "",
                "user": user or "",
            },
        },
    )


@router.get("/{job_id}", response_class=HTMLResponse)
async def admin_job_detail(
    job_id: str,
    request: Request,
    db: AsyncSession = Depends(get_db),
    admin: User = Depends(require_admin),
):
    row = (await db.execute(
        select(Job, User, Workflow)
        .join(User, User.id == Job.user_id)
        .join(Workflow, Workflow.id == Job.workflow_id)
        .where(Job.id == job_id)
        .limit(1)
    )).first()

    if not row:
        raise HTTPException(status_code=404, detail="Job not found")

    job, job_user, wf = row

    # executions + comfy node name
    exec_rows = (await db.execute(
        select(JobExecution, ComfyNode)
        .outerjoin(ComfyNode, ComfyNode.id == JobExecution.node_id)
        .where(JobExecution.job_id == job_id)
        .order_by(JobExecution.created_at.asc())
    )).all()

    # “Finished” можно вычислить как max(finished_at) из executions
    finished_at = None
    for e, _node in exec_rows:
        if e.finished_at and (finished_at is None or e.finished_at > finished_at):
            finished_at = e.finished_at

    return templates.TemplateResponse(
        "/admin/jobs/detail.html",
        {
            "request": request,
            "user": admin,
            "job": job,
            "job_user": job_user,
            "workflow": wf,
            "exec_rows": exec_rows,
            "computed_finished_at": finished_at,
        },
    )
