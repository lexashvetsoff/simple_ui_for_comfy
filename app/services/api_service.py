import uuid
import httpx
import asyncio
from datetime import datetime, timedelta
from fastapi import UploadFile, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.models.job import Job
from app.models.user import User
from app.models.workflow import Workflow
from app.models.comfy_node import ComfyNode
from app.models.job_execution import JobExecution
from app.services.scheduler import enqueue_job
from app.services.storage import save_uploaded_files
from app.schemas.workflow_spec_v2 import WorkflowSpecV2
from app.services.result_normalizer import normalize_job_result
from app.services.workflow_mapper import map_inputs_to_workflow
from app.services.workflow_mapper import normalize_workflow_for_comfy


async def submit_workflow_for_api(
    db: AsyncSession,
    workflow: Workflow,
    image: UploadFile
) -> Job:
    # system@system - пользователь для битрикса (что бы не переписывать сейчас логику сохранения файла)
    result = await db.execute(
        select(User).where(
            User.email == 'system@system',
            User.is_active == True
        )
    )
    system_user = result.scalar_one_or_none()
    if not system_user:
        raise HTTPException(status_code=404, detail='System user not found')

    spec = WorkflowSpecV2.model_validate(workflow.spec_json)
    
    text_inputs = {}
    param_inputs = {}
    image_files = {}
    mask_file = None
    mask_key = spec.inputs.mask.key if spec.inputs.mask else 'mask'
    
    # image_name = f'image_{image.filename.split(sep='.')[0]}'
    image_name = 'image_1'
    image_files[image_name] = image

    stored_files = await save_uploaded_files(
        user_id=system_user.id,
        workflow_slug=workflow.slug,
        images=image_files,
        mask=mask_file,
        mask_key=mask_key
    )

    workflow_payload = map_inputs_to_workflow(
        workflow_json=workflow.workflow_json,
        spec=spec,
        text_inputs=text_inputs,
        param_inputs=param_inputs,
        uploaded_files=stored_files
    )

    workflow_payload = normalize_workflow_for_comfy(workflow_payload)

    job = Job(
        id=uuid.uuid4().hex,
        user_id=system_user.id,
        workflow_id=workflow.id,
        mode='default',
        files=stored_files,
        inputs=text_inputs,
        prepared_workflow=workflow_payload,
        status='QUEUED'
    )

    db.add(job)
    await db.commit()
    await db.refresh(job)
    await enqueue_job(db=db, job=job)

    return job


async def get_job_result(
    db: AsyncSession,
    job: Job
):
    normalized = None
    
    while True:
        if datetime.now() >= job.created_at + timedelta(minutes=5):
            raise HTTPException(
                status_code=status.HTTP_504_GATEWAY_TIMEOUT,
                detail='Request processing took more than 5 minutes... Interrupted'
            )

        await db.refresh(job)
        if job.status == 'DONE':
            normalized = normalize_job_result(job.result) if job.result else None
            break

        await asyncio.sleep(1)

    return normalized


async def get_image_from_node(
    db: AsyncSession,
    job: Job,
    normalized: dict
):
    result = await db.execute(
        select(JobExecution)
        .where(JobExecution.job_id == job.id)
        .order_by(JobExecution.started_at.desc().nullslast())
        .limit(1)
    )
    execution = result.scalars().first()
    if not execution or not execution.node_id:
            raise HTTPException(status_code=404, detail='Job execution not found')

    node = await db.get(ComfyNode, execution.node_id)
    if not node:
            raise HTTPException(status_code=404, detail='Comfy node not found')

    base_url = node.base_url.rstrip('/')
    url = f'{base_url}/view'

    res_image = next(
        (img for img in normalized['images'] if img['filename'].startswith('ComfyUI_')),
        None
    )
    if not res_image:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail='Result not found'
            )

    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.get(
                    url,
                    params={
                        'filename': res_image['filename'],
                        'subfolder': res_image['subfolder'],
                        'type': res_image['type']
                    }
                )
    except Exception as e:
            raise HTTPException(status_code=502, detail=f'Failed to fetch image from ComfyUI: {e}')

    if response.status_code != 200:
            raise HTTPException(status_code=502, detail=f'ComfyUI returned {response.status_code}: {response.text}')

    content_type = response.headers.get('content-type', 'image/png')

    return {
        'content': response.content,
        'content_type': content_type
    }


async def execute_workflow(
    workflow_slug: str,
    image: UploadFile,
    db: AsyncSession
):
    result = await db.execute(
        select(Workflow).where(
            Workflow.slug == workflow_slug,
            Workflow.is_active == True
        )
    )
    workflow = result.scalar_one_or_none()
    if not workflow:
        raise HTTPException(status_code=404, detail='Workflow not found')

    job = await submit_workflow_for_api(db, workflow, image)

    normalized = await get_job_result(db, job)

    if not normalized:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail='Not result'
        )

    result = await get_image_from_node(db, job, normalized)
    return result
