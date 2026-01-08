from fastapi import APIRouter, Depends, Request, HTTPException
from fastapi.responses import HTMLResponse
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.api.deps import get_db, get_current_user
from app.models.user import User
from app.models.workflow import Workflow
from app.core.templates import templates


router = APIRouter(prefix='/user/workflows', tags=['user-workflows'])


@router.get('/{slug}', response_class=HTTPException)
async def workflow_run_page(
    slug: str,
    request: Request,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user)
):
    result = await db.execute(
        select(Workflow).where(
            Workflow.slug == slug,
            Workflow.is_active == True
        )
    )
    workflow = result.scalar_one_or_none()

    if not workflow:
        raise HTTPException(status_code=404, detail='Workflow not found')
    
    return templates.TemplateResponse(
        '/user/workflows/run.html',
        {
            'request': request,
            'user': user,
            'workflow': workflow,
            'spec': workflow.spec_json
        }
    )
