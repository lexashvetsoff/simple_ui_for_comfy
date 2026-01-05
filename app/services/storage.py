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
        files: Dict[str, UploadFile]
) -> Dict[str, str]:
    """
    Сохраняет загруженные файлы и возвращает mapping:
        input_key -> filepath

    filepath — относительный путь, пригодный для:
    - сохранения в БД
    - передачи в ComfyUI
    """
    saved_files: Dict[str, str] = {}

    if not files:
        return saved_files
    
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

    for input_key, upload in files.items():
        if not isinstance(upload, UploadFile):
            raise HTTPException(status_code=400, detail=f'Invalid file for input "{input_key}"')
        
        # Безопасное имя файла
        filename = os.path.basename(upload.filename)
        ext = os.path.splitext(filename)[1]

        stored_name = f'{input_key}.{ext}'
        file_path = os.path.join(base_dir, stored_name)

        try:
            contents = await upload.read()
            with open(file_path, 'wb') as f:
                f.write(contents)
        except Exception as e:
            raise HTTPException(status_code=500, detail=f'Failed to save file "{upload.filename}": {e}')
        
        # Относительный путь (важно!)
        relative_path = os.path.relpath(file_path, settings.STORAGE_ROOT)
        saved_files[input_key] = relative_path
    
    return saved_files
