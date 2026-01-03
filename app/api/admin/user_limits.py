from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.api.deps import get_db, require_admin
from app.models.user_limits import UserLimits
from app.schemas.user_limits import UserLimitsUpdate, UserLimitsOut


router = APIRouter(prefix='/admin/user_limits', tags=['admin-user-limits'])


@router.get('/{user_id}', response_model=UserLimitsOut)
async def get_limits(
    user_id: int,
    db: AsyncSession = Depends(get_db),
    _: None = Depends(require_admin)
):
    result = await db.execute(select(UserLimits).where(UserLimits.user_id == user_id))
    limits = result.scalar_one_or_none()

    if not limits:
        raise HTTPException(status_code=404, detail='Limits not found')
    
    return limits


@router.put('{user_id}', response_model=UserLimitsOut)
async def update_limits(
    user_id: int,
    data: UserLimitsUpdate,
    db: AsyncSession = Depends(get_db),
    _: None = Depends(require_admin)
):
    result = await db.execute(select(UserLimits).where(UserLimits.user_id == user_id))
    limits = result.scalar_one_or_none()

    if not limits:
        raise HTTPException(status_code=404, detail='Limits not found')
    
    limits.max_concurrent_jobs = data.max_concurrent_jobs
    limits.max_jobs_per_day = data.max_jobs_per_day

    await db.commit()
    await db.refresh(limits)

    return limits
