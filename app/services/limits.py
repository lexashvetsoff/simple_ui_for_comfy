from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from datetime import datetime, timedelta

from app.models.job import Job
from app.models.user_limits import UserLimits


async def check_user_limits(db: AsyncSession, user_id: int):
    # concurrent jobs
    concurrent = await db.execute(
        select(func.count())
        .select_from(Job)
        .where(
            Job.user_id == user_id,
            Job.status.in_([['QUEUED', 'RUNNING']])
        )
    )
    concurrent_count = concurrent.scalar()

    limits_result = await db.execute(select(UserLimits).where(UserLimits.user_id == user_id))
    limits = limits_result.scalar_one()

    if concurrent_count >= limits.max_concurrent_jobs:
        raise Exception('Concurrent jobs limit reached')
    
    # jobs per day
    since = datetime.now() - timedelta(days=1)
    daily = await db.execute(
        select(func.count())
        .select_from(Job)
        .where(
            Job.user_id == user_id,
            Job.created_at >= since
        )
    )

    if daily.scalar() >= limits.max_jobs_per_day:
        raise Exception('Daily jobs limit reached')