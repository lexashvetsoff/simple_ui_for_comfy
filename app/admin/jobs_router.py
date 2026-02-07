from fastapi import APIRouter, Depends, Request, HTTPException, Query
from fastapi.responses import HTMLResponse
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, or_
from sqlalchemy.orm import aliased

from app.api.deps import get_db, require_admin
from app.models.job import Job
from app.models.user import User
from app.models.workflow import Workflow
from app.models.job_execution import JobExecution
from app.core.templates import templates

router = APIRouter(prefix='/admin/jobs', tags=['admin-jobs'])

@router.get('/', response_class=HTMLResponse)
async def admin_jobs_list(
    request: Request,
    db: AsyncSession = Depends(get_db),
    admin: User = Depends(require_admin),

    status: str | None = Query(default=None),
    q: str | None = Query(default=None),
    workflow: str | None = Query(default=None),  # slug
    user: str | None = Query(default=None),      # email or id

    limit: int = Query(default=50, ge=10, le=200),
    offset: int = Query(default=0, ge=0),
):
    stmt = (
        select(Job, User, Workflow)
        .join(User, User.id == Job.user_id)
        .join(Workflow, Workflow.id == Job.workflow_id)
    )

    # filters
    if status:
        stmt = stmt.where(Job.status == status)

    if workflow:
        stmt = stmt.where(Workflow.slug == workflow)

    if user:
        # если похоже на uuid — ищем по user_id, иначе по email
        # if len(user) >= 32:
        #     stmt = stmt.where(Job.user_id == user)
        # else:
        #     stmt = stmt.where(User.email.ilike(f"%{user}%"))

        # если число то это id — ищем по user_id, иначе по email
        if isinstance(user, int):
            stmt = stmt.where(Job.user_id == user)
        else:
            stmt = stmt.where(User.email.ilike(f"%{user}%"))

    if q:
        qq = f"%{q}%"
        stmt = stmt.where(
            or_(
                Job.id.cast(str).ilike(qq),      # иногда нужно cast; если не работает в твоём диалекте — уберём
                User.email.ilike(qq),
                Workflow.slug.ilike(qq),
                Workflow.name.ilike(qq),
            )
        )

    # total count (для пагинации)
    count_stmt = (
        select(func.count())
        .select_from(
            select(Job.id)
            .join(User, User.id == Job.user_id)
            .join(Workflow, Workflow.id == Job.workflow_id)
            .subquery()
        )
    )

    count_stmt = select(func.count()).select_from(stmt.with_only_columns(Job.id).subquery())

    total = (await db.execute(count_stmt)).scalar_one()

    stmt = stmt.order_by(Job.created_at.desc()).limit(limit).offset(offset)
    jobs = (await db.execute(stmt)).all()

    return templates.TemplateResponse(
        "admin/jobs/list.html",
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
            }
        }
    )


@router.get("/{job_id}", response_class=HTMLResponse)
async def admin_job_detail(
    job_id: str,
    request: Request,
    db: AsyncSession = Depends(get_db),
    admin: User = Depends(require_admin),
):
    stmt = (
        select(Job, User, Workflow)
        .join(User, User.id == Job.user_id)
        .join(Workflow, Workflow.id == Job.workflow_id)
        .where(Job.id == job_id)
        .limit(1)
    )
    row = (await db.execute(stmt)).first()
    if not row:
        raise HTTPException(status_code=404, detail="Job not found")

    job, job_user, wf = row

    execs = (await db.execute(
        select(JobExecution)
        .where(JobExecution.job_id == job_id)
        .order_by(JobExecution.created_at.asc())
    )).scalars().all()

    return templates.TemplateResponse(
        "admin/jobs/detail.html",
        {
            "request": request,
            "user": admin,
            "job": job,
            "job_user": job_user,
            "workflow": wf,
            "executions": execs,
        }
    )
