from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db, get_current_user
from app.core.templates import templates
from app.models.user import User


router = APIRouter(prefix='/user', tags=['user'])


@router.get('/', response_class=HTMLResponse)
async def user_dashboard(
    request: Request,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user)
):
    return templates.TemplateResponse(
        '/user/dashboard.html',
        {
            'request': request,
            'user': user
        }
    )
