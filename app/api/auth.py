from jose import jwt, JWTError
from fastapi import APIRouter, Depends, HTTPException
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.core.config import settings
from app.schemas.auth import LoginRequest, RefreshRequest, Token
from app.core.security import verify_password
from app.core.jwt import create_access_token, create_refresh_token
from app.models.user import User
from app.api.deps import get_db


router = APIRouter(prefix='/auth', tags=['auth'])


# @router.post('/login', response_model=Token)
# async def login(
#     data: LoginRequest,
#     db: AsyncSession = Depends(get_db)
# ):
#     result = await db.execute(select(User).where(User.email == data.email))
#     user = result.scalar_one_or_none()

#     if not user or not verify_password(data.password, user.password_hash):
#         raise HTTPException(status_code=401, detail='Invalid credentials')
    
#     return Token(
#         access_token=create_access_token(user.id),
#         refresh_token=create_refresh_token(user.id),
#     )

@router.post("/login", response_model=Token)
async def login(
    form_data: OAuth2PasswordRequestForm = Depends(),
    db: AsyncSession = Depends(get_db),
):
    # form_data.username == email
    result = await db.execute(
        select(User).where(User.email == form_data.username)
    )
    user = result.scalar_one_or_none()

    if not user or not verify_password(
        form_data.password, user.password_hash
    ):
        raise HTTPException(status_code=401, detail="Invalid credentials")

    if not user.is_active:
        raise HTTPException(status_code=403, detail="User inactive")

    return Token(
        access_token=create_access_token(user.id),
        refresh_token=create_refresh_token(user.id),
    )


@router.post('/refresh', response_model=Token)
async def refresh_token(data: RefreshRequest):
    try:
        payload = jwt.decode(
            data.refresh_token,
            settings.SECRET_KEY,
            algorithms=[settings.ALGORITHM],
        )

        if payload.get('type') != 'refresh':
            raise HTTPException(status_code=401, detail='Invalid token type')
        
        user_id = int(payload.get('sub'))
    
    except (JWTError, ValueError):
        raise HTTPException(status_code=401, detail='Invalid refresh token')
    
    return Token(
        access_token=create_access_token(user_id),
        refresh_token=create_refresh_token(user_id)
    )
