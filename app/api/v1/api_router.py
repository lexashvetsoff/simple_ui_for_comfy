
import io
import uuid
import httpx
import asyncio
from datetime import datetime, timedelta
from fastapi import (
    APIRouter,
    Depends,
    HTTPException,
    status,
    File,
    UploadFile
)
from fastapi.responses import StreamingResponse, Response
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from PIL import Image

from app.core.config import settings
from app.models.job import Job
from app.models.user import User
from app.models.workflow import Workflow
from app.models.comfy_node import ComfyNode
from app.models.job_execution import JobExecution
from app.core.jwt import create_api_token
from app.services.scheduler import enqueue_job
from app.api.deps import get_db, get_current_client
from app.services.storage import save_uploaded_files
from app.schemas.workflow_spec_v2 import WorkflowSpecV2
from app.schemas.auth import TokenRequest, TokenResponse
from app.services.result_normalizer import normalize_job_result
from app.services.workflow_mapper import map_inputs_to_workflow
from app.services.workflow_mapper import normalize_workflow_for_comfy


router = APIRouter(prefix='/api', tags=['api'])


@router.get('/api_health')
async def api_healthcheck():
    return {'status': 'Ok'}


@router.post('/get_token', response_model=TokenResponse)
async def issue_token(request: TokenRequest):
    expected = settings.VALID_CLIENTS.get(request.client_id)
    if not expected or expected != request.client_secret:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail='Invalid client credentials'
        )

    return TokenResponse(
        access_token=create_api_token(request.client_id),
        expire_in=settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60
    )


@router.get('/test_token')
async def test_token(
    _: str = Depends(get_current_client)
):
    return {'status': 'ok'}


@router.post('/remove_bg')
async def remove_bg(
    image: UploadFile = File(...),
    db: AsyncSession = Depends(get_db),
    _: str = Depends(get_current_client)
):
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

    result = await db.execute(
        select(Workflow).where(
            Workflow.slug == 'remove_bg_v2',
            Workflow.is_active == True
        )
    )
    workflow = result.scalar_one_or_none()
    if not workflow:
        raise HTTPException(status_code=404, detail='Workflow not found')

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

    if not normalized:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail='Not result'
        )

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
    return Response(
         content=response.content,
         media_type=content_type
    )
