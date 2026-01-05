from sqlalchemy.ext.asyncio import AsyncSession
from app.services.scheduler import enqueue_job
from app.models.job import Job
from app.models.job_execution import JobExecution


async def create_job(
        *,
        db: AsyncSession,
        job: Job
):
    """
    Хук после создания Job (intent).
    """
    # На будущее:
    # - billing
    # - analytics
    # - rate-limit accounting

    await db.commit()
    return job


async def start_job(
        *,
        db: AsyncSession,
        job: Job
):
    """
    Отправляет Job в scheduler.
    """
    if job.status != 'QUEUED':
        return
    
    await enqueue_job(db=db, job=job)


async def handle_execution_result(
        *,
        db: AsyncSession,
        execution: JobExecution,
        result: dict | None = None,
        error: str | None = None
):
    """
    Финализирует Job по результату выполнения execution.
    """
    job = await db.get(Job, execution.job_id)
    if not job:
        return
    
    if error:
        job.status = 'ERROR'
        job.error_message = error
    else:
        job.status = 'DONE'
        job.result = result
    
    await db.commit()


async def handle_execution_failure(
        *,
        db: AsyncSession,
        execution: JobExecution,
        error: str
):
    """
    Обработка ошибки конкретного execution.
    Job здесь НЕ финализируется.
    """
    execution.status = 'ERROR'
    execution.error_message = error

    await db.commit()
