from fastapi import APIRouter, Depends, Request, HTTPException
from fastapi.responses import HTMLResponse
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.api.deps import get_db, get_current_user
from app.models.user import User
from app.models.job import Job
from app.core.templates import templates


router = APIRouter(prefix='/user/jobs', tags=['user-jobs'])


@router.get('/{job_id}', response_class=HTMLResponse)
async def job_detail_page(
    job_id: str,
    request: Request,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user)
):
    result = await db.execute(
        select(Job).where(
            Job.id == job_id,
            Job.user_id == user.id
        )
    )
    job = result.scalar_one_or_none()

    if not job or job.user_id != user.id:
        raise HTTPException(status_code=404, detail='Job not found')
    
    return templates.TemplateResponse(
        '/user/jobs/detail.html',
        {
            'request': request,
            'user': user,
            'job': job
        }
    )


@router.get('/{job_id}/state')
async def job_state(
    job_id: str,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user)
):
    result = await db.execute(
        select(Job).where(
            Job.id == job_id,
            Job.user_id == user.id
        )
    )
    job = result.scalar_one_or_none()

    if not job or job.user_id != user.id:
        raise HTTPException(status_code=404, detail='Job not found')
    
    return {
        'status': job.status,
        'error': job.error_message,
        'result': job.result
    }
