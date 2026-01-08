from fastapi import APIRouter, Depends, Request
from fastapi.responses import RedirectResponse, HTMLResponse

from app.models.user import User
from app.api.deps import get_current_user
from app.core.templates import templates


router = APIRouter(tags=['ui'])


@router.get('/', response_class=HTMLResponse)
async def get_main_page(request: Request):
    return RedirectResponse('/login', status_code=302)


@router.get('/login', response_class=HTMLResponse)
async def login_page(
    request: Request,
    # user: User = Depends(get_current_user)
):
    try:
        user = await get_current_user(request)
    except:
        user = ''
    # если уже есть токен и пользователь валиден — редирект
    if user:
        if user.role == 'ADMIN':
            return RedirectResponse('/admin', status_code=302)
        return RedirectResponse('/user', status_code=302)
    
    return templates.TemplateResponse(
        '/ui/login.html',
        {'request': request}
    )
