from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, desc

from app.api.deps import get_db, get_current_user
from app.core.templates import templates
from app.models.user import User
from app.models.workflow import Workflow
from app.models.job import Job


router = APIRouter(prefix='/user', tags=['user'])


@router.get('/', response_class=HTMLResponse)
async def user_dashboard(
    request: Request,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user)
):
    # Workflows
    result = await db.execute(
        select(Workflow)
        .where(Workflow.is_active == True)
        .order_by(Workflow.category, Workflow.name)
    )
    workflows = result.scalars().all()

    workflows_by_category: dict[str, list[Workflow]] = {}
    for wf in workflows:
        key = wf.category or "Other"
        workflows_by_category.setdefault(key, []).append(wf)

    # Recent jobs
    # result = await db.execute(
    #     select(Job)
    #     .where(Job.user_id == user.id)
    #     .order_by(desc(Job.created_at))
    #     .limit(10)
    # )
    # jobs = result.scalars().all()

    stmt = (
        select(Job, User, Workflow)
        .join(User, User.id == Job.user_id)
        .join(Workflow, Workflow.id == Job.workflow_id)
        .where(User.id == user.id)
        .order_by(Job.created_at.desc())
    )
    jobs = (await db.execute(stmt)).all()

    return templates.TemplateResponse(
        '/user/dashboard.html',
        {
            'request': request,
            'user': user,
            'workflows_by_category': workflows_by_category,
            'jobs': jobs,
        },
    ) 


@router.get('/workflows', response_class=HTMLResponse)
async def user_workflows(
    request: Request,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user)
):
    result = await db.execute(
        select(Workflow)
        .where(Workflow.is_active == True)
        .order_by(Workflow.category, Workflow.name)
    )
    workflows = result.scalars().all()

    grouped: dict[str, list[Workflow]] = {}

    for wf in workflows:
        category = wf.category or 'Other'
        grouped.setdefault(category, []).append(wf)

    return templates.TemplateResponse(
        '/user/workflows/workflows.html',
        {
            'request': request,
            'user': user,
            'grouped_workflows': grouped
        }
    )
