from __future__ import annotations

import uuid
from pathlib import Path
from typing import Dict, Optional
from fastapi import UploadFile
from app.core.config import settings

BASE_STORAGE_DIR = Path(settings.STORAGE_ROOT)


async def _save_one(file: UploadFile, dst_path: Path) -> str:
    dst_path.parent.mkdir(parents=True, exist_ok=True)

    data = await file.read()
    with open(dst_path, "wb") as f:
        f.write(data)

    # возвращаем относительный путь (с прямыми слешами)
    return str(dst_path.as_posix())


async def save_uploaded_files(
    user_id: int,
    workflow_slug: str,
    images: Dict[str, UploadFile] | None = None,
    mask: UploadFile | None = None,
    mask_key: str = "mask",
) -> Dict[str, str]:
    """
    Возвращает dict: {spec_key: relative_path}
    images: ключи ДОЛЖНЫ совпадать с spec.inputs.images[i].key (image_123 ...)
    mask_key: ключ ДОЛЖЕН совпадать с spec.inputs.mask.key (mask_40 ...)
    """
    images = images or {}
    result: Dict[str, str] = {}

    upload_id = uuid.uuid4().hex
    base_dir = (
        BASE_STORAGE_DIR
        / "users"
        / f"user_{user_id}"
        / "uploads"
        / workflow_slug
        / upload_id
    )

    # Сохраняем изображения
    for key, file in images.items():
        if not file or not getattr(file, "filename", None):
            continue
        ext = Path(file.filename).suffix or ".png"
        dst = base_dir / "images" / f"{key}{ext}"
        result[key] = await _save_one(file, dst)

    # Сохраняем маску, если она передана
    if mask and getattr(mask, "filename", None):
        ext = Path(mask.filename).suffix or ".png"
        dst = base_dir / "masks" / f"{mask_key}{ext}"
        result[mask_key] = await _save_one(mask, dst)

    return result