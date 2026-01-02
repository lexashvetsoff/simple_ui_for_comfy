from fastapi import Depends, HTTPException, status
from jose import jwt, JWTError
from typing import AsyncGenerator
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.core.config import settings
from app.core.oauth2 import oauth2_scheme
from app.db.session import AsyncSessionLocal
from app.models.user import User


def get_settings():
    return settings


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    async with AsyncSessionLocal() as session:
        yield session


async def get_current_user(
        token: str = Depends(oauth2_scheme),
        db: AsyncSession = Depends(get_db),
) -> User:
    if not token:
        raise HTTPException(status_code=401, detail='Not authenticated')
    
    try:
        payload = jwt.decode(
            token,
            settings.SECRET_KEY,
            algorithms=[settings.ALGORITHM],
        )

        if payload.get('type') != 'access':
            raise HTTPException(status_code=401, detail='Invalid token type')

        user_id = int(payload.get('sub'))
    except (JWTError, ValueError):
        raise HTTPException(status_code=401, detail='Invalid token')
    
    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()

    if not user or not user.is_active:
        raise HTTPException(status_code=401, detail='Inactive user')
    
    return user


def require_admin(user: User = Depends(get_current_user)):
    if user.role != 'ADMIN':
        raise HTTPException(status_code=403, detail='Admin only')
    return user
