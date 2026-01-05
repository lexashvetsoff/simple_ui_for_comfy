import httpx
from typing import Any
from fastapi import HTTPException
from app.models.comfy_node import ComfyNode


async def submit_workflow(
        *,
        node: ComfyNode,
        workflow: dict
):
    """
    Отправляет workflow в ComfyUI.
    Возвращает prompt_id.
    """
    url = f'{node.base_url}/prompt'
    payload = {
        'prompt': workflow
    }

    timeout = httpx.Timeout(10.0, read=30.0)

    async with httpx.AsyncClient(timeout=timeout) as client:
        try:
            response = await client.post(url, json=payload)
        except httpx.RequestError as e:
            raise HTTPException(status_code=502, detail=f'Failed to connect to ComfyUI node: {e}')
    
    if response.status_code != 200:
        raise HTTPException(status_code=502, detail=f'ComfyUI error {response.status_code}: {response.text}')
    
    data = response.json()

    prompt_id = data.get('prompt_id')
    if not prompt_id:
        raise HTTPException(status_code=502, detail='ComfyUI response missing prompt_id')
    
    return prompt_id
