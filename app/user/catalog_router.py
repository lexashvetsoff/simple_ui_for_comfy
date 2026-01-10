from collections import defaultdict
from typing import Dict, List

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.api.deps import get_db, get_current_user
from app.models.user import User
from app.models.workflow import Workflow
from app.services.workflow_catalog import prepare_workflow_catalog_item
from app.core.templates import templates


router = APIRouter(prefix='/user', tags=['user-catalog'])


@router.get('/catalog', response_class=HTMLResponse)
async def user_catalog(
    request: Request,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user)
):
    result = await db.execute(
        select(Workflow)
        .where(Workflow.is_active == True)
        .order_by(
            Workflow.category.nulls_last(),
            Workflow.created_at.desc()
        )
    )
    workflows = result.scalars().all()

    catalog: Dict[str | None, List[Dict]] = defaultdict(list)

    for workflow in workflows:
        item = prepare_workflow_catalog_item(
            workflow=workflow,
            spec=workflow.spec_json
        )

        catalog[workflow.category].append(item)
    
    return templates.TemplateResponse(
        '/user/catalog/index.html',
        {
            'request': request,
            'user': user,
            'catalog': dict(catalog)
        }
    )
