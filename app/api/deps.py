from fastapi import Depends, HTTPException, status, Request, Response
from jose import jwt, JWTError
from typing import AsyncGenerator
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.core.config import settings
from app.core.oauth2 import oauth2_scheme
from app.db.session import AsyncSessionLocal
from app.models.user import User
from app.core.jwt import create_access_token
from app.services.auth_service import _set_access_cookie


def get_settings():
    return settings


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    async with AsyncSessionLocal() as session:
        yield session


def extract_token(request: Request) -> str | None:
    auth = request.headers.get('Authorization')
    if auth and auth.startswith("Bearer "):
        return auth.split(" ", 1)[1]
    return request.cookies.get("access_token")


def _decode_jwt(token: str) -> dict:
    """
    Универсальный decode. Бросает JWTError при любой проблеме (включая exp).
    """
    return jwt.decode(
        token,
        settings.SECRET_KEY,
        algorithms=[settings.ALGORITHM]
    )


def _try_refresh_access_token(request: Request, response: Response) -> int | None:
    """
    Пробует взять refresh_token из cookie, провалидировать, выдать новый access_token.
    Возвращает user_id если успешно, иначе None.
    """
    refresh = request.cookies.get('refresh_token')
    if not refresh:
        return None
    
    try:
        payload = _decode_jwt(refresh)
        if payload.get('type') != 'refresh':
            return None
        
        user_id = int(payload.get('sub'))
        new_access_token = create_access_token(user_id)
        _set_access_cookie(response, new_access_token)

        return user_id
    
    except (JWTError, ValueError):
        return None


async def _get_user_by_id(db: AsyncSession, user_id: int) -> User | None:
    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if not user or not user.is_active:
        return None
    return user


async def get_current_user_or_none(
        request: Request,
        response: Response,
        db: AsyncSession = Depends(get_db),
) -> User | None:
    token = extract_token(request)
    user_id: int | None = None
    
    if token:
        try:
            payload = _decode_jwt(token)
            if payload.get('type') == 'access':
                user_id = int(payload.get('sub'))
        except (JWTError, ValueError):
            user_id = None
    
    # если access не сработал — пробуем refresh
    if user_id is None:
        user_id = _try_refresh_access_token(request, response)
    
    if user_id is None:
        return None
    
    return await _get_user_by_id(db, user_id)


async def get_current_user(
        request: Request,
        response: Response,
        db: AsyncSession = Depends(get_db),
) -> User:
    token = extract_token(request)
    user_id: int | None = None
    
    if token:
        try:
            payload = _decode_jwt(token)
            if payload.get('type') != 'access':
                raise HTTPException(status_code=401, detail='Invalid token type')
            user_id = int(payload.get('sub'))
        except (JWTError, ValueError):
            user_id = None
    
    # если access не сработал — пробуем refresh
    if user_id is None:
        user_id = _try_refresh_access_token(request, response)
    
    if user_id is None:
        raise HTTPException(status_code=401, detail='Invalid token')
    
    user = await _get_user_by_id(db, user_id)
    if not user:
        raise HTTPException(status_code=401, detail='Inactive user')
    
    return user


def require_admin(user: User = Depends(get_current_user)):
    if user.role != 'ADMIN':
        raise HTTPException(status_code=403, detail='Admin only')
    return user
