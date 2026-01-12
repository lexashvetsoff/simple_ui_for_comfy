import asyncio
from datetime import datetime
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.job import Job
from app.models.job_execution import JobExecution
from app.models.comfy_node import ComfyNode
from app.services.comfy_client import submit_workflow
from app.services.comfy_client import get_prompt_result
from app.services.comfy_prompt_builder import build_prompt_from_ui_workflow


async def select_avilable_node(
        *,
        db: AsyncSession
) -> ComfyNode | None:
    result = await db.execute(
        select(ComfyNode)
        .where(ComfyNode.is_active == True)
        .order_by(ComfyNode.last_seen.desc())
    )
    return result.scalars().first()


async def enqueue_job(
        *,
        db: AsyncSession,
        job: Job
):
    """
    Scheduler entrypoint.
    Просто помечает Job как готовый к выполнению.
    """
    if job.status != 'QUEUED':
        return
    
    # Scheduler loop сам подхватит job
    await db.commit()


async def scheduler_tick(
        *,
        db: AsyncSession,
        batch_size: int = 5
):
    """
    Один тик планировщика.
    """
    # 1. Берём Job, готовые к запуску
    result = await db.execute(
        select(Job)
        .where(Job.status == 'QUEUED')
        .limit(batch_size)
    )
    jobs = result.scalars().all()

    if not jobs:
        return
    
    # 2. Выбираем ноду
    node = await select_avilable_node(db=db)
    if not node:
        return
    
    for job in jobs:
        # 3. Создаём execution
        execution = JobExecution(
            job_id=job.id,
            node_id=node.id,
            status='RUNNING',
            started_at=datetime.now()
        )

        db.add(execution)
        job.status = 'RUNNING'

        await db.commit()
        await db.refresh(execution)

        # 4. Отправляем в ComfyUI
        prompt = build_prompt_from_ui_workflow(job.prepared_workflow)
        try:
            prompt_id = await submit_workflow(
                node=node,
                # workflow=job.prepared_workflow
                workflow=prompt
            )

            execution.prompt_id = prompt_id
            await db.commit()

            from app.services.comfy_progress import ensure_prompt_tracking
            await ensure_prompt_tracking(node=node, prompt_id=prompt_id)
        except Exception as e:
            execution.status = 'ERROR'
            execution.error_message = str(e)
            job.status = 'ERROR'
            job.error_message = str(e)
            await db.commit()


async def poll_execution_status(
        *,
        db: AsyncSession,
        execution: JobExecution
):
    """
    Проверяет статус execution.
    Вызывается воркером / background task.
    """
    # TODO:
    # - запрос к ComfyUI
    # - обновление execution.status
    # - вызов job_service.handle_execution_result
    pass


async def poll_running_executions(
        *,
        db: AsyncSession,
        batch_size: int = 10
):
    """
    Проверяет RUNNING execution и финализирует их.
    """
    result = await db.execute(
        select(JobExecution)
        .where(JobExecution.status == 'RUNNING')
        .limit(batch_size)
    )
    executions = result.scalars().all()

    for execution in executions:
        if not execution.prompt_id:
            continue

        node = await db.get(ComfyNode, execution.node_id)
        if not node:
            continue

        from app.services.job_service import handle_execution_result

        try:
            outputs = await get_prompt_result(node=node, prompt_id=execution.prompt_id)
        except Exception as e:
            await handle_execution_result(
                db=db,
                execution=execution,
                error=str(e)
            )
            continue

        if outputs is None:
            continue

        # execution finished successfully
        execution.status = 'DONE'
        execution.finished_at = datetime.now()
        await db.commit()

        await handle_execution_result(
            db=db,
            execution=execution,
            result=outputs
        )
    