from fastapi import APIRouter, Depends, Request, HTTPException
from fastapi.responses import HTMLResponse
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.api.deps import get_db, require_admin
from app.models.job import Job
from app.models.user import User
from app.models.workflow import Workflow
from app.core.templates import templates


router = APIRouter(prefix='/admin/jobs', tags=['admin-jobs'])


@router.get('/', response_class=HTMLResponse)
async def admin_jobs_list(
    request: Request,
    db: AsyncSession = Depends(get_db),
    admin: User = Depends(require_admin)
):
    result = await db.execute(
        select(Job, User, Workflow)
        .join(User, User.id == Job.user_id)
        .join(Workflow, Workflow.id == Job.workflow_id)
        .order_by(Job.created_at.desc())
        .limit(100)
    )

    jobs = result.all()

    return templates.TemplateResponse(
        '/admin/jobs/list.html',
        {
            'request': request,
            'user': admin,
            'jobs': jobs
        }
    )


@router.get('/{job_id}', response_class=HTMLResponse)
async def admin_job_detail(
    job_id: str,
    request: Request,
    db: AsyncSession = Depends(get_db),
    admin: User = Depends(require_admin)
):
    job = await db.get(Job, job_id)
    if not job:
        raise HTTPException(status_code=404, detail='Job not found')
    
    return templates.TemplateResponse(
        '/admin/jobs/detail.html',
        {
            'request': request,
            'user': admin,
            'job': job
        }
    )
