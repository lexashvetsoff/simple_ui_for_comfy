from __future__ import annotations

from typing import Any, Dict, Optional

import httpx
from fastapi import HTTPException

from app.models.comfy_node import ComfyNode


def _ensure_prompt_payload(workflow_or_payload: Dict[str, Any]) -> Dict[str, Any]:
    """
    ComfyUI /prompt expects {"prompt": {...}}.
    """
    if isinstance(workflow_or_payload, dict) and "prompt" in workflow_or_payload:
        return workflow_or_payload
    raise HTTPException(status_code=400, detail="Invalid payload: missing 'prompt' key")


async def submit_workflow(*, node: ComfyNode, workflow: Dict[str, Any]) -> str:
    url = f"{node.base_url}/prompt"
    payload = _ensure_prompt_payload(workflow)

    timeout = httpx.Timeout(10.0, read=60.0)
    async with httpx.AsyncClient(timeout=timeout) as client:
        try:
            response = await client.post(url, json=payload)
        except httpx.RequestError as e:
            raise HTTPException(status_code=502, detail=f"Failed to connect to ComfyUI node: {e}")

    if response.status_code != 200:
        raise HTTPException(status_code=502, detail=f"ComfyUI error {response.status_code}: {response.text}")

    data = response.json()
    prompt_id = data.get("prompt_id")
    if not prompt_id:
        raise HTTPException(status_code=502, detail="ComfyUI response missing prompt_id")
    return str(prompt_id)


async def get_object_info(*, node: ComfyNode) -> Dict[str, Any]:
    """
    GET /object_info — источник истины для типов, COMBO и порядка widgets_values.
    """
    url = f"{node.base_url}/object_info"
    timeout = httpx.Timeout(10.0, read=60.0)

    async with httpx.AsyncClient(timeout=timeout) as client:
        try:
            r = await client.get(url)
        except httpx.RequestError as e:
            raise HTTPException(status_code=502, detail=f"Failed to connect to ComfyUI node: {e}")

    if r.status_code != 200:
        raise HTTPException(status_code=502, detail=f"ComfyUI error {r.status_code}: {r.text}")

    data = r.json()
    if not isinstance(data, dict):
        raise HTTPException(status_code=502, detail="ComfyUI /object_info returned invalid JSON")
    return data


async def get_prompt_result(*, node: ComfyNode, prompt_id: str) -> Optional[Dict[str, Any]]:
    url = f"{node.base_url}/history/{prompt_id}"
    timeout = httpx.Timeout(10.0, read=60.0)

    async with httpx.AsyncClient(timeout=timeout) as client:
        try:
            r = await client.get(url)
        except httpx.RequestError as e:
            raise HTTPException(status_code=502, detail=f"Failed to connect to ComfyUI node: {e}")

    if r.status_code != 200:
        raise HTTPException(status_code=502, detail=f"ComfyUI error {r.status_code}: {r.text}")

    data = r.json()
    if not isinstance(data, dict):
        raise HTTPException(status_code=502, detail="ComfyUI /history returned invalid JSON")

    item = data.get(prompt_id)
    if not item:
        return None

    status = (item.get("status") or {}).get("status_str")
    if status and status.lower() in ("running", "pending", "queued"):
        return None

    outputs = item.get("outputs")
    return outputs if isinstance(outputs, dict) else None


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
            return f"{response_json['subfolder']}/{name}"
        return name
