import uuid
import json
from datetime import datetime
from typing import List, Dict, Any
from fastapi import APIRouter, Depends, Request, HTTPException, UploadFile
from fastapi.responses import HTMLResponse, RedirectResponse
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
from app.services.workflow_mapper import normalize_workflow_for_comfy
from app.services.scheduler import enqueue_job
from app.schemas.workflow_spec_v2 import WorkflowSpecV2
from app.services.spec_grooping import prepare_spec_groups
from app.services.comfy_service import _patch_widget_fields_for_seed_in_spec


router = APIRouter(prefix='/user/workflows', tags=['user-workflows'])


def sort_loadimage_nodes(data: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    Сортирует элементы с label='LoadImage' по полю label внутри списка images.
    Если таких элементов меньше двух, возвращает копию исходного списка.
    """
    # Собираем индексы и сами элементы, у которых label == 'LoadImage'
    loadimage_indices = []
    loadimage_nodes = []
    for i, node in enumerate(data):
        if node.get('label') == 'LoadImage':
            loadimage_indices.append(i)
            loadimage_nodes.append(node)

    # Если сортировка не требуется
    if len(loadimage_nodes) <= 1:
        return data.copy()

    # Функция для извлечения ключа сортировки из узла LoadImage
    def get_sort_key(node: Dict[str, Any]) -> str:
        images = node.get('images', [])
        if images and isinstance(images, list) and len(images) > 0:
            # Берём label из первого элемента списка images (по примеру данных)
            return images[0].get('label', '')
        return ''  # если структура нарушена, такой элемент уйдёт в конец

    # Сортируем LoadImage узлы
    sorted_loadimage_nodes = sorted(loadimage_nodes, key=get_sort_key)

    # Вставляем отсортированные узлы обратно на свои позиции
    result = data.copy()
    for idx, node in zip(loadimage_indices, sorted_loadimage_nodes):
        result[idx] = node

    return result


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
    
    # groups = prepare_spec_groups(spec=workflow.spec_json, workflow_json=workflow.workflow_json)
    groups_visible_first, groups_hidden_only = prepare_spec_groups(
        spec=workflow.spec_json,
        workflow_json=workflow.workflow_json
    )
    
    # return templates.TemplateResponse(
    #     '/user/workflows/run.html',
    #     {
    #         'request': request,
    #         'user': user,
    #         'workflow': workflow,
    #         'spec': workflow.spec_json,
    #         'groups': groups
    #     }
    # )
    groups_visible = sort_loadimage_nodes(groups_visible_first)
    return templates.TemplateResponse(
        '/user/workflows/run.html',
        {
            'request': request,
            'user': user,
            'workflow': workflow,
            'spec': workflow.spec_json,
            'visible_groups': groups_visible,
            'hidden_only_groups': groups_hidden_only
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
    # patch_spec = _patch_widget_fields_for_seed_in_spec(workflow.spec_json)

    # patch_spec = _patch_widget_fields_for_seed_in_spec(patch_spec)
    # with open('patch_spec.json', 'w') as f:
    #     json.dump(patch_spec, f)
    
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
    mask_key = spec.inputs.mask.key if spec.inputs.mask else 'mask'

    stored_files = await save_uploaded_files(
        user_id=user.id,
        workflow_slug=slug,
        images=image_files,
        mask=mask_file,
        mask_key=mask_key
    )

    # 5. Map inputs → comfy workflow
    workflow_payload = map_inputs_to_workflow(
        workflow_json=workflow.workflow_json,
        spec=spec,
        text_inputs=text_inputs,
        param_inputs=param_inputs,
        uploaded_files=stored_files
    )
    workflow_payload = normalize_workflow_for_comfy(workflow_payload)

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
    # return {
    #     'job_id': job.id,
    #     'status': 'queued'
    # }
    return RedirectResponse(
        url=f'/user/jobs/{job.id}',
        status_code=302
    )
