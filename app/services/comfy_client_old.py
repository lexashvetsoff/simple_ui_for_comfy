import json
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

    # для отладки
    with open('payload_comfy.json', 'w', encoding='utf-8') as f:
        json.dump(workflow, f)

    timeout = httpx.Timeout(10.0, read=30.0)

    async with httpx.AsyncClient(timeout=timeout) as client:
        try:
            # response = await client.post(url, json=payload)
            response = await client.post(url, json=workflow)
        except httpx.RequestError as e:
            raise HTTPException(status_code=502, detail=f'Failed to connect to ComfyUI node: {e}')
    
    if response.status_code != 200:
        raise HTTPException(status_code=502, detail=f'ComfyUI error {response.status_code}: {response.text}')
    
    data = response.json()

    # для отладки
    with open('answer_comfy.json', 'w', encoding='utf-8') as f:
        json.dump(data, f)

    prompt_id = data.get('prompt_id')
    if not prompt_id:
        raise HTTPException(status_code=502, detail='ComfyUI response missing prompt_id')
    
    return prompt_id


async def get_prompt_status(
        *,
        node: ComfyNode,
        prompt_id: str
) -> dict | None:
    """
    Возвращает raw-статус prompt или None, если ещё не готов.
    """
    url = f'{node.base_url}/history/{prompt_id}'

    async with httpx.AsyncClient(timeout=10.0) as client:
        try:
            response = await client.get(url)
        except httpx.RequestError as e:
            raise HTTPException(status_code=502, detail=f'Failed to poll ComfyUI: {e}')
    
    if response.status_code != 200:
        raise HTTPException(status_code=502, detail=f'ComfyUI polling error: {response.text}')
    
    data = response.json()

    prompt_data = data.get(prompt_id)
    if not prompt_data:
        return None
    
    return prompt_data


async def get_prompt_result(
        *,
        node: ComfyNode,
        prompt_id: str
) -> dict | None:
    """
    Возвращает outputs workflow или None, если ещё не готов.
    """
    prompt_data = await get_prompt_status(node=node, prompt_id=prompt_id)
    if not prompt_data:
        return None
    
    status = prompt_data.get('status', {})
    if not status.get('completed'):
        return None
    
    return prompt_data.get('outputs')
