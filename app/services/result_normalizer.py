from typing import Any, Dict, List, Optional


# def _as_storage_url(path: str) -> str:
#     """
#     Приводим путь к URL, который реально отдаётся через:
#       app.mount('/storage', StaticFiles(...))
#     Ожидаем, что path уже относительный (например: users/1/outputs/x.png)
#     либо абсолютный внутри STORAGE_ROOT — тогда лучше заранее хранить относительный.
#     """
#     path = path.replace('\\', '/').lstrip('/')
#     if path.startswith('storage/'):
#         path = path[len('storage/')]
#     return f'/storage/{path}'


# def normalize_job_result(result: Optional[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
#     """
#     Делает result пригодным для UI:

#     Возвращает:
#     {
#       "images": [{"url": "/storage/..."}]
#     }

#     Пытается поддержать несколько типичных форматов ComfyUI outputs.
#     """
#     if not result:
#         return None
    
#     images: List[Dict[str, str]] = []

#     # Частый вариант: outputs[node_id]["images"] = [{ "filename": "...", "subfolder": "...", ... }]
#     outputs = result.get('outputs') if isinstance(result, dict) else None
#     if isinstance(outputs, dict):
#         for _, out in outputs.items():
#             if not isinstance(out, dict):
#                 continue
#             imgs = out.get('images')
#             if isinstance(imgs, list):
#                 for item in imgs:
#                     # item может быть dict с filename/subfolder
#                     if isinstance(item, dict):
#                         filename = item.get('filename')
#                         subfolder = item.get('subfolder') or ''
#                         if filename:
#                             rel = f'{subfolder}/{filename}'.strip('/')
#                             images.append({'url': _as_storage_url(rel)})
#                     # или уже строка-путь
#                     elif isinstance(item, str):
#                         images.append({'url': _as_storage_url(item)})
    
#     # Если уже есть images как список строк
#     if not images and isinstance(result, dict) and isinstance(result.get('images'), list):
#         for p in result['images']:
#             if isinstance(p, str):
#                 images.append({'url': _as_storage_url(p)})
    
#     return {'images': images}


def _extract_images_from_node_payload(node_payload: Any) -> List[Dict[str, Any]]:
    """
    node_payload examples:
      {"images": [{"filename": "...", "subfolder": "", "type": "temp"}]}
      {"gifs": [...]}
      {"videos": [...]}
    """
    if not isinstance(node_payload, dict):
        return []

    imgs = node_payload.get("images")
    if not isinstance(imgs, list):
        return []

    out: List[Dict[str, Any]] = []
    for item in imgs:
        if not isinstance(item, dict):
            continue
        # required minimal fields for ComfyUI view
        filename = item.get("filename")
        if not filename:
            continue
        out.append(
            {
                "filename": filename,
                "subfolder": item.get("subfolder") or "",
                "type": item.get("type") or "output",
            }
        )
    return out


def normalize_job_result(raw_result: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    """
    Normalizes stored Job.result into UI-friendly structure.

    Returns:
      {"images": [ {filename, subfolder, type}, ... ]}

    Supports multiple possible shapes:
      A) {"12": {"images":[...]}, "13": {...}}
      B) {"outputs": {"12": {"images":[...]}}}
      C) {"prompt_id": "...", "outputs": {...}}  (ComfyUI history-like)
      D) {"images":[...]}  (already normalized-ish)
    """
    if not raw_result or not isinstance(raw_result, dict):
        return {"images": []}

    # Case D: already has top-level images
    if isinstance(raw_result.get("images"), list):
        images: List[Dict[str, Any]] = []
        for item in raw_result["images"]:
            if isinstance(item, dict) and item.get("filename"):
                images.append(
                    {
                        "filename": item["filename"],
                        "subfolder": item.get("subfolder") or "",
                        "type": item.get("type") or "output",
                    }
                )
        return {"images": images}

    # Case B/C: wrapped outputs
    outputs = raw_result.get("outputs")
    if isinstance(outputs, dict):
        images: List[Dict[str, Any]] = []
        for _, node_payload in outputs.items():
            images.extend(_extract_images_from_node_payload(node_payload))
        return {"images": images}

    # Case A: node_id -> payload
    images: List[Dict[str, Any]] = []
    for _, node_payload in raw_result.items():
        images.extend(_extract_images_from_node_payload(node_payload))

    return {"images": images}
