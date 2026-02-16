from __future__ import annotations

import os
from pathlib import Path
from typing import Dict, Any

from app.core.config import settings
from app.services.comfy_client import upload_image_to_comfy

# Константы для типов узлов, как во втором файле
IMAGE_NODE_TYPES = {"LoadImage", "LoadImageFromPath"}
MASK_NODE_TYPES = {"LoadMask"}


async def upload_and_patch_images(
    *,
    base_url: str,
    prompt_payload: Dict[str, Any],
    stored_files: Dict[str, str],
) -> Dict[str, Any]:
    """
    - Загружает все изображения и маски из stored_files на ComfyUI.
    - Патчит узлы LoadImage / LoadImageFromPath / LoadMask в соответствии с ключами.
    """
    prompt = prompt_payload.get("prompt")
    if not isinstance(prompt, dict) or not stored_files:
        return prompt_payload

    storage_root = Path(settings.STORAGE_ROOT)
    uploaded: Dict[str, str] = {}  # key -> remote_name

    # 1. Загружаем все подходящие файлы (image_*, mask_*, mask)
    for key, rel_path in stored_files.items():
        if not isinstance(key, str) or not isinstance(rel_path, str):
            continue
        if not (key.startswith("image_") or key.startswith("mask_") or key == "mask"):
            continue

        # Определяем абсолютный путь
        abs_path = storage_root / rel_path
        if not abs_path.exists():
            # Возможно rel_path уже абсолютный
            abs_path = Path(rel_path)
            if not abs_path.exists():
                continue

        # Формируем имя файла для Comfy: ключ + расширение
        ext = os.path.splitext(str(abs_path))[1] or ".png"
        name = f"{key}{ext}"

        with open(abs_path, "rb") as f:
            content = f.read()

        remote_name = await upload_image_to_comfy(
            base_url,
            filename=name,
            content=content,
            subfolder="",
            overwrite=True,
        )
        uploaded[key] = remote_name

    # 2. Патчим узлы в соответствии с загруженными файлами
    for node_id, node in prompt.items():
        if not isinstance(node, dict):
            continue
        class_type = node.get("class_type")
        inputs = node.get("inputs")
        if not isinstance(inputs, dict):
            continue

        # Обработка узлов загрузки изображений
        if class_type in IMAGE_NODE_TYPES:
            key = f"image_{node_id}"
            if key in uploaded:
                inputs["image"] = uploaded[key]
                node["inputs"] = inputs

        # Обработка узлов загрузки масок
        if class_type in MASK_NODE_TYPES:
            key1 = f"mask_{node_id}"
            if key1 in uploaded:
                inputs["image"] = uploaded[key1]
                node["inputs"] = inputs
            elif "mask" in uploaded:
                inputs["image"] = uploaded["mask"]
                node["inputs"] = inputs

    prompt_payload["prompt"] = prompt
    return prompt_payload