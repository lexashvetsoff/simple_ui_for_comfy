from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from datetime import datetime, timedelta
from fastapi import HTTPException

from app.models.job import Job
from app.models.user_limits import UserLimits


# async def check_user_limits(*, db: AsyncSession, user_id: int):
#     # concurrent jobs
#     concurrent = await db.execute(
#         select(func.count())
#         .select_from(Job)
#         .where(
#             Job.user_id == user_id,
#             Job.status.in_([['QUEUED', 'RUNNING']])
#         )
#     )
#     concurrent_count = concurrent.scalar()

#     limits_result = await db.execute(select(UserLimits).where(UserLimits.user_id == user_id))
#     limits = limits_result.scalar_one()

#     if concurrent_count >= limits.max_concurrent_jobs:
#         raise Exception('Concurrent jobs limit reached')
    
#     # jobs per day
#     since = datetime.now() - timedelta(days=1)
#     daily = await db.execute(
#         select(func.count())
#         .select_from(Job)
#         .where(
#             Job.user_id == user_id,
#             Job.created_at >= since
#         )
#     )

#     if daily.scalar() >= limits.max_jobs_per_day:
#         raise Exception('Daily jobs limit reached')

async def get_user_limits(
        *,
        db: AsyncSession,
        user_id: int,
) -> UserLimits:
    """
    Возвращает UserLimits пользователя или создаёт дефолтные.
    """
    result = await db.execute(select(UserLimits).where(UserLimits.user_id == user_id))
    limits = result.scalar_one_or_none()

    if limits:
        return limits
    
    # если лимиты не созданы — создаём дефолт
    limits = UserLimits(user_id=user_id)

    db.add(limits)
    await db.commit()
    await db.refresh(limits)

    return limits


async def check_daily_job_limit(
        *,
        db: AsyncSession,
        user_id: int
):
    limits = await get_user_limits(db=db, user_id=user_id)

    since = datetime.now() - timedelta(days=1)

    result = await db.execute(
        select(func.count(Job.id)).where(
            Job.user_id == user_id,
            Job.created_at >= since
        )
    )

    used = result.scalar_one()

    if used >= limits.max_jobs_per_day:
        raise HTTPException(status_code=429, detail='Daily job limit exceeded')


async def check_concurrent_jobs_limit(
        *,
        db: AsyncSession,
        user_id: int
):
    limits = await get_user_limits(db=db, user_id=user_id)

    result = await db.execute(
        select(func.count(Job.id)).where(
            Job.user_id == user_id,
            Job.status.in_(["QUEUED", "RUNNING"])
        )
    )

    active = result.scalar_one()

    if active >= limits.max_concurrent_jobs:
        raise HTTPException(status_code=429, detail='Concurrent job limit exceeded')


async def register_job_usage(
        *,
        db: AsyncSession,
        job: Job
):
    """
    Billing / analytics hook.
    """
    # На будущее
    pass
