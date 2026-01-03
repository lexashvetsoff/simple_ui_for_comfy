from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.api.deps import get_db
from app.api.deps import require_admin
from app.models.user import User
from app.schemas.user import (
    UserCreate,
    UserUpdate,
    UserOut
)
from app.core.security import hash_password


router = APIRouter(prefix='/admin/users', tags=['admin-users'])


@router.get('/', response_model_by_alias=list[UserOut])
async def list_users(
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_admin)
):
    result = await db.execute(select(User))
    return result.scalars().all()


@router.post('/', response_model=UserOut)
async def create_user(
    data: UserCreate,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_admin)
):
    result = await db.execute(select(User).where(User.email == data.email))
    if result.scalar_one_or_none():
        raise HTTPException(status_code=400, detail='User already exists')
    
    user = User(
        email=data.email,
        password_hash=hash_password(data.password),
        role=data.role,
        is_active=True
    )
    db.add(user)
    await db.commit()
    await db.refresh(user)
    return user


@router.patch('/{user_id}', response_model=UserOut)
async def update_user(
    user_id: int,
    data: UserUpdate,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_admin)
):
    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()

    if not user:
        raise HTTPException(status_code=404, detail='User not found')
    
    # for field, value in data.dict(exclude_unset=True):
    #     setattr(user, field, value)
    
    for field, value in data.model_dump(exclude_unset=True).items():
        setattr(user, field, value)
    
    await db.commit()
    await db.refresh(user)
    return user


@router.delete('/{user_id}')
async def deactivate_user(
    user_id: int,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_admin)
):
    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()

    if not user:
        raise HTTPException(status_code=404, detail='User not found')
    
    user.is_active = False
    await db.commit()

    return {'status': 'deactivated'}
