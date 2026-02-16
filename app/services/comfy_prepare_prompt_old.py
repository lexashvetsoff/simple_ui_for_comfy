from __future__ import annotations
import os
from typing import Dict, Any
from app.core.config import settings
from app.services.comfy_client import upload_image_to_comfy


LOAD_IMAGE_TYPES = {"LoadImage", "LoadImageFromPath"}


async def upload_and_patch_images(
        *,
        base_url: str,
        prompt_payload: Dict[str, Any],
        stored_files: Dict[str, str]
) -> Dict[str, Any]:
    """
    stored_files: dict[key -> rel_path] где rel_path относительно STORAGE_ROOT
    prompt_payload: {"prompt": {...}}
    Патчит все LoadImage / LoadImageFromPath:
      - если inputs.image указывает на rel_path или имя файла, которого нет на comfy
      - пытаемся найти подходящий файл в stored_files и залить его на comfy
    """
    prompt = prompt_payload.get("prompt", {})
    if not isinstance(prompt, dict) or not stored_files:
        return prompt_payload

    # Предподготовка: превращаем stored_files в abs paths
    abs_files: Dict[str, str] = {}
    for k, rel in stored_files.items():
        abs_files[k] = os.path.join(settings.STORAGE_ROOT, rel)

    for node_id, node in prompt.items():
        if not isinstance(node, dict):
            continue
        ct = node.get("class_type")
        if ct not in LOAD_IMAGE_TYPES:
            continue

        inputs = node.get("inputs") or {}
        if not isinstance(inputs, dict):
            continue

        # Обычно field называется "image"
        img_val = inputs.get("image")
        # Если это уже имя на comfy (например "some.png"), мы не знаем — но Comfy сам проверит.
        # Тут логика: если img_val совпадает с rel_path из stored_files или похоже на путь — грузим.
        target_abs = None
        target_filename = None

        # 1) если прямо передали rel_path (как у тебя сейчас должно быть)
        if isinstance(img_val, str):
            # если img_val совпал с одним из rel_path
            for k, rel in stored_files.items():
                if img_val == rel:
                    target_abs = abs_files[k]
                    target_filename = os.path.basename(target_abs)
                    break

            # 2) если img_val просто "filename.png", попробуем найти по имени среди stored_files
            if target_abs is None and ("/" not in img_val and "\\" not in img_val):
                for k, ap in abs_files.items():
                    if os.path.basename(ap) == img_val:
                        target_abs = ap
                        target_filename = os.path.basename(ap)
                        break

        # 3) если поле пустое — попробуем взять первый image_... из stored_files
        if target_abs is None:
            # часто ключи вида "image_204" или "image_XXX"
            for k, ap in abs_files.items():
                if k.startswith("image_"):
                    target_abs = ap
                    target_filename = os.path.basename(ap)
                    break

        if not target_abs or not target_filename:
            continue

        if not os.path.exists(target_abs):
            continue

        with open(target_abs, "rb") as f:
            content = f.read()

        remote_name = await upload_image_to_comfy(
            base_url,
            filename=target_filename,
            content=content,
            subfolder="",
            overwrite=True
        )

        inputs["image"] = remote_name
        node["inputs"] = inputs
        prompt[node_id] = node

    prompt_payload["prompt"] = prompt
    return prompt_payload
