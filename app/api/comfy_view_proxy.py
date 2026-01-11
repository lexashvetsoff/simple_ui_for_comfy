import httpx
from fastapi import APIRouter, Depends, HTTPException, Query
from starlette.responses import Response
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db, get_current_user
from app.models.user import User
from app.models.comfy_node import ComfyNode


router = APIRouter(prefix='/comfy', tags=['comfy-proxy'])


@router.get('/view/{node_id}')
async def comfy_view_proxy(
    node_id: int,
    filename: str = Query(...),
    subfolder: str = Query(...),
    _type: str = Query('output'),
    db: AsyncSession = Depends(get_db),
    _user: User = Depends(get_current_user)
):
    node = await db.get(ComfyNode, node_id)
    if not node or not node.is_active:
        raise HTTPException(status_code=404, detail='Comfy node not found')
    
    base = (node.base_url or '').rstrip('/')
    if not base:
        raise HTTPException(status_code=400, detail='Comfy node base_url is empty')
    
    url = f'{base}/view'
    params = {'filename': filename, 'subfolder': subfolder, 'type': _type}

    try:
        async with httpx.AsyncClient(timeout=60.0) as client:
            response = await client.get(url, params=params)
    except httpx.RequestError as e:
        raise HTTPException(status_code=502, detail=f'Comfy node unreachable: {e}')
    
    if response.status_code != 200:
        raise HTTPException(status_code=502, detail=f'ComfyUI /view error {response.status_code}: {response.text}')
    
    content_type = response.get('content-type', 'application/octet-stream')
    return Response(content=response.content, media_type=content_type)
