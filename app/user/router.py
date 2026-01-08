from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.api.deps import get_db, get_current_user
from app.core.templates import templates
from app.models.user import User
from app.models.workflow import Workflow


router = APIRouter(prefix='/user', tags=['user'])


@router.get('/', response_class=HTMLResponse)
async def user_dashboard(
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
        '/user/dashboard.html',
        {
            'request': request,
            'user': user,
            'grouped_workflows': grouped
        }
    )
