import json
import httpx
from typing import Any, Dict, Optional
from fastapi import HTTPException
from app.models.comfy_node import ComfyNode


_OBJECT_INFO_CACHE: dict[str, dict] = {}  # base_url -> object_info


async def get_object_info(base_url: str, *, force: bool = False) -> Dict[str, Any]:
    if not force and base_url in _OBJECT_INFO_CACHE:
        return _OBJECT_INFO_CACHE[base_url]
    
    timeout = httpx.Timeout(10.0, read=60.0)
    async with httpx.AsyncClient(timeout=timeout) as client:
        for path in ('/object_info', '/api/object_info'):
            try:
                response = await client.get(f'{base_url}{path}')
                if response.status_code == 200:
                    data = response.json()
                    if isinstance(data, dict) and data:
                        _OBJECT_INFO_CACHE[base_url] = data
                        return data
            except httpx.RequestError:
                continue
    
    raise HTTPException(status_code=502, detail='Cannot fetch ComfyUI object_info from node')


async def upload_image_to_comfy(
        base_url: str,
        *,
        filename: str,
        content: bytes,
        subfolder: str,
        overwrite: bool = True
) -> str:
    """
    Загружает изображение на ComfyUI (в input).
    Возвращает имя файла, которое надо подставить в LoadImage.inputs.image.
    """
    timeout = httpx.Timeout(10.0, read=60.0)
    async with httpx.AsyncClient(timeout=timeout) as client:
        files = {'image': (filename, content, 'application/octet-stream')}
        data = {'subfolder': subfolder, 'overwrite': 'true' if overwrite else 'false'}

        response = await client.post(f'{base_url}/upload/image', files=files, data=data)
        if response.status_code != 200:
            response = await client.post(f'{base_url}/api/upload/image', files=files, data=data)
        
        if response.status_code != 200:
            raise HTTPException(status_code=502, detail=f'ComfyUI upload error {response.status_code}: {response.text}')
        
        response_json = response.json()
        name = response_json.get('name') or response_json.get('filename')
        if not name:
            raise HTTPException(status_code=502, detail=f'ComfyUI upload response missing name: {response_json}')
        
        if response_json.get('subfolder'):
            return f"{response_json['subfolder']/{name}}"
        return name


def _ensure_prompt_payload(workflow_or_payload: Dict[str, Any]) -> Dict[str, Any]:
    """
    Принимает либо:
      - UI/prompt-graph как dict нод (тогда заворачиваем в {"prompt": ...})
      - уже готовый payload вида {"prompt": {...}} (тогда возвращаем как есть)
    """
    if isinstance(workflow_or_payload, dict) and "prompt" in workflow_or_payload:
        # уже payload
        if not isinstance(workflow_or_payload["prompt"], dict):
            raise ValueError('payload["prompt"] must be a dict')
        return workflow_or_payload

    # иначе считаем, что это prompt-graph dict
    if not isinstance(workflow_or_payload, dict):
        raise ValueError("workflow must be a dict")

    return {"prompt": workflow_or_payload}


async def submit_workflow(
    *,
    node: ComfyNode,
    workflow: dict,
) -> str:
    """
    Отправляет prompt в ComfyUI.
    Возвращает prompt_id.
    """
    url = f"{node.base_url}/prompt"
    payload = _ensure_prompt_payload(workflow)

    # для отладки — пишем РОВНО ТО, ЧТО УШЛО В COMFY
    # with open("payload_comfy.json", "w", encoding="utf-8") as f:
    #     json.dump(payload, f, ensure_ascii=False, indent=2)

    timeout = httpx.Timeout(10.0, read=60.0)

    async with httpx.AsyncClient(timeout=timeout) as client:
        try:
            response = await client.post(url, json=payload)
        except httpx.RequestError as e:
            raise HTTPException(status_code=502, detail=f"Failed to connect to ComfyUI node: {e}")

    if response.status_code != 200:
        raise HTTPException(status_code=502, detail=f"ComfyUI error {response.status_code}: {response.text}")

    data = response.json()

    # для отладки
    # with open("answer_comfy.json", "w", encoding="utf-8") as f:
    #     json.dump(data, f, ensure_ascii=False, indent=2)

    prompt_id = data.get("prompt_id")
    if not prompt_id:
        raise HTTPException(status_code=502, detail="ComfyUI response missing prompt_id")

    return prompt_id


async def get_prompt_status(
    *,
    node: ComfyNode,
    prompt_id: str,
) -> dict | None:
    """
    Возвращает raw-статус prompt или None, если Comfy его ещё не знает.
    """
    url = f"{node.base_url}/history/{prompt_id}"

    async with httpx.AsyncClient(timeout=10.0) as client:
        try:
            response = await client.get(url)
        except httpx.RequestError as e:
            raise HTTPException(status_code=502, detail=f"Failed to poll ComfyUI: {e}")

    if response.status_code != 200:
        raise HTTPException(status_code=502, detail=f"ComfyUI polling error: {response.text}")

    data = response.json()
    return data.get(prompt_id)


async def get_prompt_result(
    *,
    node: ComfyNode,
    prompt_id: str,
) -> dict | None:
    """
    Возвращает outputs workflow или None, если ещё не готов.
    """
    prompt_data = await get_prompt_status(node=node, prompt_id=prompt_id)
    if not prompt_data:
        return None

    status = prompt_data.get("status", {})
    if not status.get("completed"):
        return None

    return prompt_data.get("outputs")
