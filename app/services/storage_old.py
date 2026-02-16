import os
import uuid
from typing import Dict
from fastapi import UploadFile, HTTPException
from app.core.config import settings


def ensure_dir(path: str):
    os.makedirs(path, exist_ok=True)


async def save_uploaded_files(
        *,
        user_id: int,
        workflow_slug: str,
        images: Dict[str, UploadFile],
        mask: UploadFile | None = None
) -> Dict[str, str]:
    saved: Dict[str, str] = {}

    if not images and not mask:
        return saved
    
    upload_id = uuid.uuid4().hex

    base_dir = os.path.join(
        settings.STORAGE_ROOT,
        'users',
        str(user_id),
        'uploads',
        workflow_slug,
        upload_id
    )

    ensure_dir(base_dir)

    async def _save_file(key: str, file: UploadFile):
        filename = file.filename or f'{key}.bin'
        path = os.path.join(base_dir, filename)

        with open(path, 'wb') as f:
            f.write(await file.read())
        
        rel_path = os.path.relpath(path, settings.STORAGE_ROOT)
        saved[key] = rel_path
    
    for key, file in images.items():
        await _save_file(key, file)
    
    if mask:
        await _save_file('mask', mask)
    
    return saved


# from __future__ import annotations

# import os
# import uuid
# from pathlib import Path
# from typing import Dict, Optional
# from fastapi import UploadFile
# from app.core.config import settings

# BASE_STORAGE_DIR = Path(settings.STORAGE_ROOT)


# async def _save_one(file: UploadFile, dst_path: Path) -> str:
#     dst_path.parent.mkdir(parents=True, exist_ok=True)

#     data = await file.read()
#     with open(dst_path, "wb") as f:
#         f.write(data)

#     # возвращаем относительный путь (как у тебя и было принято)
#     return str(dst_path.as_posix())


# async def save_uploaded_files(
#     user_id: int,
#     workflow_slug: str,
#     images: Dict[str, UploadFile] | None = None,
#     mask: UploadFile | None = None,
#     mask_key: str = "mask",
# ) -> Dict[str, str]:
#     """
#     Возвращает dict: {spec_key: relative_path}
#     images: ключи ДОЛЖНЫ совпадать с spec.inputs.images[i].key (image_123 ...)
#     mask_key: ключ ДОЛЖЕН совпадать с spec.inputs.mask.key (mask_40 ...)
#     """
#     images = images or {}
#     result: Dict[str, str] = {}

#     # base_dir = BASE_STORAGE_DIR / f"user_{user_id}" / workflow_slug

#     upload_id = uuid.uuid4().hex
#     base_dir = os.path.join(
#         BASE_STORAGE_DIR,
#         'users',
#         f"user_{user_id}",
#         'uploads',
#         workflow_slug,
#         upload_id
#     )

#     # images
#     for key, file in images.items():
#         if not file or not getattr(file, "filename", None):
#             continue
#         ext = os.path.splitext(file.filename)[1] or ".png"
#         # dst = base_dir / "images" / f"{key}{ext}"
#         dst = os.path.join(base_dir, "images", f"{key}{ext}")
#         result[key] = await _save_one(file, dst)

#     # mask
#     if mask and getattr(mask, "filename", None):
#         ext = os.path.splitext(mask.filename)[1] or ".png"
#         # dst = base_dir / "masks" / f"{mask_key}{ext}"
#         dst = os.path.join(base_dir, "masks", f"{mask_key}{ext}")
#         result[mask_key] = await _save_one(mask, dst)

#     return result



# async def save_uploaded_files(
#         *,
#         user_id: int,
#         workflow_slug: str,
#         files: Dict[str, UploadFile]
# ) -> Dict[str, str]:
#     """
#     Сохраняет загруженные файлы и возвращает mapping:
#         input_key -> filepath

#     filepath — относительный путь, пригодный для:
#     - сохранения в БД
#     - передачи в ComfyUI
#     """
#     saved_files: Dict[str, str] = {}

#     if not files:
#         return saved_files
    
#     upload_id = uuid.uuid4().hex

#     base_dir = os.path.join(
#         settings.STORAGE_ROOT,
#         'users',
#         str(user_id),
#         'uploads',
#         workflow_slug,
#         upload_id
#     )

#     ensure_dir(base_dir)

#     for input_key, upload in files.items():
#         if not isinstance(upload, UploadFile):
#             raise HTTPException(status_code=400, detail=f'Invalid file for input "{input_key}"')
        
#         # Безопасное имя файла
#         filename = os.path.basename(upload.filename)
#         ext = os.path.splitext(filename)[1]

#         stored_name = f'{input_key}.{ext}'
#         file_path = os.path.join(base_dir, stored_name)

#         try:
#             contents = await upload.read()
#             with open(file_path, 'wb') as f:
#                 f.write(contents)
#         except Exception as e:
#             raise HTTPException(status_code=500, detail=f'Failed to save file "{upload.filename}": {e}')
        
#         # Относительный путь (важно!)
#         relative_path = os.path.relpath(file_path, settings.STORAGE_ROOT)
#         saved_files[input_key] = relative_path
    
#     return saved_files
