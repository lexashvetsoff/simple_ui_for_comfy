import uuid
from datetime import datetime
from fastapi import APIRouter, Depends, Request, HTTPException, UploadFile
from fastapi.responses import HTMLResponse
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.api.deps import get_db, get_current_user
from app.models.user import User
from app.models.workflow import Workflow
from app.models.job import Job
from app.core.templates import templates
from app.services.limits import check_daily_job_limit
from app.services.storage import save_uploaded_files
from app.services.workflow_mapper import map_inputs_to_workflow
from app.services.scheduler import enqueue_job
from app.schemas.workflow_spec_v2 import WorkflowSpecV2


router = APIRouter(prefix='/user/workflows', tags=['user-workflows'])


@router.get('/{slug}', response_class=HTMLResponse)
async def workflow_run_page(
    slug: str,
    request: Request,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user)
):
    result = await db.execute(
        select(Workflow).where(
            Workflow.slug == slug,
            Workflow.is_active == True
        )
    )
    workflow = result.scalar_one_or_none()

    if not workflow:
        raise HTTPException(status_code=404, detail='Workflow not found')
    
    return templates.TemplateResponse(
        '/user/workflows/run.html',
        {
            'request': request,
            'user': user,
            'workflow': workflow,
            'spec': workflow.spec_json
        }
    )


@router.post('/{slug}/run')
async def run_workflow(
    slug: str,
    request: Request,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user)
):
    # 1. Load workflow
    result = await db.execute(
        select(Workflow).where(
            Workflow.slug == slug,
            Workflow.is_active == True
        )
    )
    workflow = result.scalar_one_or_none()
    if not workflow:
        raise HTTPException(status_code=404, detail='Workflow not found')
    
    # spec = workflow.spec_json
    spec = WorkflowSpecV2.model_validate(workflow.spec_json)

    # 2. Check limits
    await check_daily_job_limit(db=db, user_id=user.id)

    # 3. Parse form-data
    form = await request.form()

    text_inputs = {}
    param_inputs = {}
    image_files = {}
    mask_file: UploadFile | None = None

    for key, value in form.items():
        if key.startswith('text__'):
            text_inputs[key.removeprefix('text__')] = value

        elif key.startswith('param__'):
            param_inputs[key.removeprefix('param__')] = value
        
        elif key.startswith('image__') and hasattr(value, 'filename'):
            image_files[key.removeprefix('image__')] = value
        
        elif key == 'mask' and hasattr(value, 'filename'):
            mask_file = value
    
    # 4. Save uploaded files
    stored_files = await save_uploaded_files(
        user_id=user.id,
        workflow_slug=slug,
        images=image_files,
        mask=mask_file
    )

    # 5. Map inputs → comfy workflow
    workflow_payload = map_inputs_to_workflow(
        workflow_json=workflow.workflow_json,
        spec=spec,
        text_inputs=text_inputs,
        param_inputs=param_inputs,
        uploaded_files=stored_files
    )

    # 6. Create job
    job = Job(
        id=uuid.uuid4().hex,
        user_id=user.id,
        workflow_id=workflow.id,
        mode='default',
        files=stored_files,
        inputs=text_inputs,
        prepared_workflow=workflow_payload,
        status="QUEUED",
    )

    db.add(job)
    await db.commit()
    await db.refresh(job)

    # 7. Enqueue
    await enqueue_job(db=db, job=job)

    # 8. Redirect to job page (следующий этап)
    return {
        'job_id': job.id,
        'status': 'queued'
    }
