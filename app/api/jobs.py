import uuid
from typing import Dict, Any

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.api.deps import get_db, get_current_user
from app.models.job import Job
from app.models.user import User
from app.models.workflow import Workflow
from app.schemas.job import JobCreateRequest, JobResponse
from app.services.workflow_mapper import map_inputs_to_workflow
from app.services.storage import save_uploaded_files


router = APIRouter(prefix='/jobs', tags=['jobs'])


@router.post('/', response_model=JobResponse)
async def create_job(
    payload: JobCreateRequest,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user)
):
    # 1. Получаем workflow
    result = await db.execute(
        select(Workflow).where(
            Workflow.slug == payload.workflow_slug,
            Workflow.is_active == True
        )
    )
    workflow = result.scalar_one_or_none()

    if not workflow:
        raise HTTPException(status_code=404, detail='Workflow not found')
    
    # 2. Проверка режима
    spec = workflow.spec_json
    available_modes = {m['id'] for m in spec.get('modes', [])}

    if payload.mode not in available_modes:
        raise HTTPException(status_code=400, detail=f'Invalid mode "{payload.mode}"')
    
    # 3. Сохраняем загруженные файлы
    files = await save_uploaded_files(
        user_id=user.id,
        workflow_slug=workflow.slug,
        files=payload.files
    )

    # 4. Подготавливаем workflow (mapping)
    prepared_workflow = map_inputs_to_workflow(
        workflow_json=workflow.workflow_json,
        spec=workflow.spec_json,
        user_inputs=payload.inputs,
        uploaded_files=files,
        mode=payload.mode
    )

    # 5. Создаём Job (intent)
    job = Job(
        id=uuid.uuid4().hex,
        user_id=user.id,
        workflow_id=workflow.id,
        mode=payload.mode,
        inputs=payload.inputs,
        files=files,
        prepared_workflow=prepared_workflow,
        status='QUEUED'
    )

    db.add(job)
    await db.commit()
    await db.refresh(job)

    return job


@router.get('/', response_model=list[JobResponse])
async def list_jobs(
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user)
):
    result = await db.execute(
        select(Job)
        .where(Job.user_id == user.id)
        .order_by(Job.created_at.desc())
    )
    return result.scalars().all()


@router.get('/{job_id}', response_model=JobResponse)
async def get_job(
    job_id: str,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user)
):
    result = await db.execute(
        select(Job).where(
            Job.id == job_id,
            Job.user_id == user.id
        )
    )
    job = result.scalar_one_or_none()

    if not job:
        raise HTTPException(status_code=404, detail='Job not found')
    
    return job
