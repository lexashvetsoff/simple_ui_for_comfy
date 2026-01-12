import httpx
from urllib.parse import urlencode
from fastapi import APIRouter, Depends, Request, HTTPException, Query
from fastapi.responses import HTMLResponse, JSONResponse, Response
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.api.deps import get_db, get_current_user
from app.models.user import User
from app.models.job import Job
from app.models.job_execution import JobExecution
from app.models.comfy_node import ComfyNode
from app.services.result_normalizer import normalize_job_result
from app.services.comfy_progress import get_progress
from app.core.templates import templates


router = APIRouter(prefix='/user/jobs', tags=['user-jobs'])


async def _get_user_job_or_404(
        db: AsyncSession,
        user: User,
        job_id: str
) -> Job:
    job = await db.get(Job, job_id)
    if not job or job.user_id != user.id:
        raise HTTPException(status_code=404, detail='Job not found')
    return job


async def _get_latest_execution(
        db: AsyncSession,
        job_id: str
) -> JobExecution | None:
    result = await db.execute(
        select(JobExecution)
        .where(JobExecution.job_id == job_id)
        .order_by(JobExecution.started_at.desc().nullslast())
        .limit(1)
    )
    return result.scalars().first()


def _pathc_result_urls(job_id: str, normalized: dict | None) -> dict | None:
    """
    Ожидаем формат примерно:
    {
      "images": [
        {"filename": "...", "subfolder": "", "type": "temp", ...}
      ]
    }
    либо уже может быть:
    {"images":[{"url": "..."}]}
    """
    if not normalized or not isinstance(normalized, dict):
        return normalized
    
    images = normalized.get('images')
    if not isinstance(images, list):
        return normalized
    
    for img in images:
        if not isinstance(img, dict):
            continue

        # если url уже есть — ничего не трогаем
        if img.get('url'):
            continue

        filename = img.get('filename')
        if not filename:
            continue

        subfolder = img.get('subfolder', '') or ''
        ftype = img.get('type', 'output') or 'ouyput'

        qs = urlencode({'filename': filename, 'subfolder': subfolder, 'type': ftype})
        img['url'] = f'/user/jobs/{job_id}/image?{qs}'
    
    return normalized


@router.get('/{job_id}', response_class=HTMLResponse)
async def job_detail_page(
    job_id: str,
    request: Request,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user)
):
    job = await _get_user_job_or_404(db, user, job_id)

    # чтобы страница могла сразу что-то показать без первого fetch
    normalized = normalize_job_result(job.result) if job.result else None
    normalized = _pathc_result_urls(job.id, normalized)
    
    return templates.TemplateResponse(
        '/user/jobs/detail.html',
        {
            'request': request,
            'user': user,
            'job': job,
            'job_result': normalized
        }
    )


@router.get('/{job_id}/state')
async def job_state(
    job_id: str,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user)
):
    job = await _get_user_job_or_404(db, user, job_id)

    # result -> нормализуем под UI
    normalized = normalize_job_result(job.result) if job.result else None
    normalized = _pathc_result_urls(job.id, normalized)

    progress = None
    prompt_id = None

    result = await db.execute(
        select(JobExecution)
        .where(JobExecution.job_id == job_id)
        .order_by(JobExecution.started_at.desc().nullslast())
        .limit(1)
    )
    execution = result.scalars().first()

    if execution and execution.prompt_id:
        prompt_id = execution.prompt_id
        progress = await get_progress(prompt_id)
    
    return JSONResponse(
        {
            'id': job.id,
            'status': job.status, # QUEUED | RUNNING | DONE | ERROR
            'error': job.error_message,
            'result': normalized,
            'prompt_id': prompt_id,
            'progress': progress,
            'created_at': job.created_at.isoformat() if job.created_at else None
        }
    )


@router.get('/{job_id}/image')
async def job_image_proxy(
    job_id: str,
    filename: str = Query(...),
    subfolder: str = Query(...),
    type: str = Query('output'),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user)
):
    """
    Проксирует ComfyUI /view для конкретного job.
    Важно: берем node из последнего JobExecution.
    """
    job = await _get_user_job_or_404(db, user, job_id)
    execution = await _get_latest_execution(db, job.id)

    if not execution or not execution.node_id:
        raise HTTPException(status_code=404, detail='Job execution not found')
    
    node = await db.get(ComfyNode, execution.node_id)
    if not node:
        raise HTTPException(status_code=404, detail='Comfy node not found')
    
    base_url = node.base_url.rstrip('/')
    url = f'{base_url}/view'

    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.get(
                url,
                params={'filename': filename, 'subfolder': subfolder, 'type': type}
            )
    except Exception as e:
        raise HTTPException(status_code=502, detail=f'Failed to fetch image from ComfyUI: {e}')
    
    if response.status_code != 200:
        raise HTTPException(status_code=502, detail=f'ComfyUI returned {response.status_code}: {response.text}')
    
    content_type = response.headers.get('content-type', 'image/png')
    return Response(content=response.content, media_type=content_type)
