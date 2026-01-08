from fastapi import APIRouter, Depends, Request, Form
from fastapi.responses import RedirectResponse, HTMLResponse
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.models.user import User
from app.api.deps import get_current_user, get_db, get_current_user_or_none
from app.core.security import verify_password, hash_password
from app.core.jwt import create_access_token
from app.core.templates import templates


router = APIRouter(tags=['ui'])


@router.get('/', response_class=HTMLResponse)
async def get_main_page(request: Request):
    return RedirectResponse('/login', status_code=302)


@router.get('/login', response_class=HTMLResponse)
async def login_page(
    request: Request,
    user: User | None = Depends(get_current_user_or_none)
):
    # если уже есть токен и пользователь валиден — редирект
    if isinstance(user, User):
        if user:
            if user.role == 'ADMIN':
                return RedirectResponse('/admin', status_code=302)
            return RedirectResponse('/user', status_code=302)
        
    return templates.TemplateResponse(
        '/ui/login.html',
        {'request': request}
    )


@router.post('/login')
async def user_login(
    request: Request,
    username: str = Form(...),
    password: str = Form(...),
    db: AsyncSession = Depends(get_db)
):
    result = await db.execute(select(User).where(User.email == username))
    user = result.scalar_one_or_none()

    if (
        not user
        or not verify_password(password, user.password_hash)
        or not user.is_active
    ):
        return templates.TemplateResponse(
            '/ui/login.html',
            {'request': request, 'error': 'Invalid credintials or not user'},
            status_code=400,
        )
    
    access_token = create_access_token(user.id)

    response = RedirectResponse(
        url='/login',
        status_code=302
    )

    response.set_cookie(
        key='access_token',
        value=access_token,
        httponly=True,
        samesite='lax'
    )

    return response
